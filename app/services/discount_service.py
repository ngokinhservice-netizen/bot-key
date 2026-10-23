from datetime import datetime, timezone
from typing import Optional, List, Tuple
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import DiscountCode, DiscountRedemption, DiscountType
from app.services.audit_service import AuditService
from app.utils.logger import logger
from app.utils.helpers import format_vnd


class DiscountService:
    @staticmethod
    async def validate_code(
        session: AsyncSession,
        code_str: str,
        product_id: int,
        order_amount: int,
    ) -> Tuple[bool, str, Optional[DiscountCode], int]:
        """
        Validate a discount code for an order.
        Returns: (is_valid, message, discount_obj, discount_amount)
        """
        code_cleaned = code_str.strip().upper()
        stmt = select(DiscountCode).where(DiscountCode.code == code_cleaned)
        res = await session.execute(stmt)
        discount = res.scalar_one_or_none()

        if not discount:
            return False, "Mã giảm giá không tồn tại hoặc đã bị xóa.", None, 0

        if not discount.is_active:
            return False, "Mã giảm giá này hiện đang tạm ngừng kích hoạt.", None, 0

        now = datetime.now(timezone.utc)
        start_tz = discount.start_date.replace(tzinfo=timezone.utc) if discount.start_date.tzinfo is None else discount.start_date
        end_tz = discount.end_date.replace(tzinfo=timezone.utc) if discount.end_date.tzinfo is None else discount.end_date

        if now < start_tz:
            return False, "Mã giảm giá chưa đến ngày có hiệu lực.", None, 0

        if now > end_tz:
            return False, "Mã giảm giá đã hết hạn sử dụng.", None, 0

        if discount.current_uses >= discount.max_uses:
            return False, "Mã giảm giá đã hết lượt sử dụng.", None, 0

        if discount.product_id is not None and discount.product_id != product_id:
            return False, "Mã giảm giá không áp dụng cho sản phẩm này.", None, 0

        if order_amount < discount.min_order_amount:
            return (
                False,
                f"Đơn hàng chưa đạt giá trị tối thiểu {format_vnd(discount.min_order_amount)} để dùng mã này.",
                None,
                0,
            )

        # Calculate discount amount
        if discount.discount_type == DiscountType.PERCENT:
            calculated = int(order_amount * (discount.discount_value / 100.0))
        else:
            calculated = int(discount.discount_value)

        # Cap discount at order amount
        discount_amount = min(calculated, order_amount)
        return True, "Áp dụng mã giảm giá thành công!", discount, discount_amount

    @staticmethod
    async def redeem_code(
        session: AsyncSession,
        discount_id: int,
        order_id: int,
        user_id: int,
        discount_amount: int,
    ) -> DiscountRedemption:
        # Increment usage count with lock
        stmt = select(DiscountCode).where(DiscountCode.id == discount_id).with_for_update()
        res = await session.execute(stmt)
        discount = res.scalar_one_or_none()
        if not discount:
            raise ValueError("Mã giảm giá không tồn tại.")

        discount.current_uses += 1

        redemption = DiscountRedemption(
            discount_id=discount_id,
            order_id=order_id,
            user_id=user_id,
            discount_amount=discount_amount,
        )
        session.add(redemption)
        await session.flush()
        logger.info(f"Redeemed discount #{discount_id} ({discount.code}) for Order #{order_id}: -{discount_amount} VND")
        return redemption

    @staticmethod
    async def create_code(
        session: AsyncSession,
        code: str,
        discount_type: DiscountType,
        discount_value: int,
        max_uses: int,
        start_date: datetime,
        end_date: datetime,
        min_order_amount: int = 0,
        product_id: Optional[int] = None,
        admin_id: Optional[int] = None,
    ) -> DiscountCode:
        code_clean = code.strip().upper()
        existing_stmt = select(DiscountCode).where(DiscountCode.code == code_clean)
        existing = (await session.execute(existing_stmt)).scalar_one_or_none()
        if existing:
            raise ValueError(f"Mã giảm giá '{code_clean}' đã tồn tại trên hệ thống.")

        dc = DiscountCode(
            code=code_clean,
            discount_type=discount_type,
            discount_value=discount_value,
            max_uses=max_uses,
            min_order_amount=min_order_amount,
            product_id=product_id,
            start_date=start_date,
            end_date=end_date,
            is_active=True,
        )
        session.add(dc)
        await session.flush()

        if admin_id:
            await AuditService.log_action(
                session=session,
                action="CREATE_DISCOUNT",
                admin_id=admin_id,
                target_type="discount",
                target_id=str(dc.id),
                details=f"code={code_clean} | type={discount_type} | val={discount_value} | max={max_uses}",
            )
        return dc

    @staticmethod
    async def list_codes(session: AsyncSession) -> List[DiscountCode]:
        stmt = select(DiscountCode).order_by(DiscountCode.id.desc())
        res = await session.execute(stmt)
        return list(res.scalars().all())
