from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple
from sqlalchemy import select, and_, func, String
from sqlalchemy.ext.asyncio import AsyncSession
from app.config.settings import settings
from app.database.models import (
    Order,
    OrderItem,
    OrderStatus,
    PaymentMethod,
    Payment,
    PaymentStatus,
    KeyStatus,
    KeyInventory,
    User,
    Product,
    WalletTxType,
)
from app.services.product_service import ProductService
from app.services.key_service import KeyService
from app.services.discount_service import DiscountService
from app.services.affiliate_service import AffiliateService
from app.services.user_service import UserService
from app.services.audit_service import AuditService
from app.utils.logger import logger
from app.utils.helpers import generate_order_code, format_vnd


class OrderService:
    @staticmethod
    async def create_order(
        session: AsyncSession,
        user_id: int,
        telegram_id: int,
        product_id: int,
        quantity: int = 1,
        discount_code_str: Optional[str] = None,
        payment_method: PaymentMethod = PaymentMethod.SEPAY,
    ) -> Order:
        """
        Create a new pending order.
        Validates product, stock availability, and applies discount coupon if valid.
        """
        product = await ProductService.get_by_id(session, product_id)
        if not product or not product.is_active:
            raise ValueError("Sản phẩm không tồn tại hoặc đã ngừng kinh doanh.")

        # Check stock availability
        stock = await ProductService.get_stock_count(session, product_id)
        if stock < quantity:
            raise ValueError(f"Sản phẩm tạm thời hết hàng (Còn {stock} key khả dụng, cần {quantity}).")

        original_amount = product.price * quantity
        discount_amount = 0
        discount_obj = None

        if discount_code_str:
            is_valid, msg, discount_obj, disc_val = await DiscountService.validate_code(
                session=session,
                code_str=discount_code_str,
                product_id=product_id,
                order_amount=original_amount,
            )
            if not is_valid:
                raise ValueError(msg)
            discount_amount = disc_val

        final_amount = max(0, original_amount - discount_amount)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=settings.ORDER_EXPIRE_MINUTES)
        order_code = generate_order_code()

        order = Order(
            order_code=order_code,
            user_id=user_id,
            telegram_id=telegram_id,
            product_id=product_id,
            quantity=quantity,
            original_amount=original_amount,
            discount_amount=discount_amount,
            final_amount=final_amount,
            status=OrderStatus.PENDING,
            payment_method=payment_method,
            discount_code_id=discount_obj.id if discount_obj else None,
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
        )
        session.add(order)
        await session.flush()

        # Add Order Item
        item = OrderItem(
            order_id=order.id,
            product_id=product_id,
            quantity=quantity,
            unit_price=product.price,
            subtotal=original_amount,
            created_at=now,
        )
        session.add(item)

        # Record discount redemption if used
        if discount_obj and discount_amount > 0:
            await DiscountService.redeem_code(
                session=session,
                discount_id=discount_obj.id,
                order_id=order.id,
                user_id=user_id,
                discount_amount=discount_amount,
            )

        await session.flush()
        logger.info(
            f"Created Order #{order.id} [{order_code}] for Telegram ID {telegram_id}: {format_vnd(final_amount)} (Method: {payment_method})"
        )
        return order

    @staticmethod
    async def get_by_code(session: AsyncSession, order_code: str) -> Optional[Order]:
        stmt = select(Order).where(Order.order_code == order_code)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def get_by_id(session: AsyncSession, order_id: int) -> Optional[Order]:
        stmt = select(Order).where(Order.id == order_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def complete_order(
        session: AsyncSession,
        order_id: int,
        bot=None,
    ) -> Tuple[bool, str, List[KeyInventory]]:
        """
        Complete an order after verified payment:
        1. Atomically lock & assign keys to the order.
        2. Mark order as COMPLETED.
        3. Trigger affiliate commission.
        4. Send private Telegram message with keys & activation guide.
        (If sending fails due to user blocking the bot, keep order COMPLETED and keys safe in DB).
        """
        order = await OrderService.get_by_id(session, order_id)
        if not order:
            raise ValueError(f"Không tìm thấy đơn hàng #{order_id}")

        if order.status == OrderStatus.COMPLETED:
            # Already completed (idempotent call)
            stmt = select(KeyInventory).where(KeyInventory.order_id == order.id)
            existing_keys = list((await session.execute(stmt)).scalars().all())
            return True, "Đơn hàng đã được xử lý thành công trước đó.", existing_keys

        # Lock and assign keys
        try:
            keys = await KeyService.lock_and_assign_keys(
                session=session,
                product_id=order.product_id,
                quantity=order.quantity,
                order_id=order.id,
                buyer_telegram_id=order.telegram_id,
            )
        except ValueError as e:
            # Out of stock or concurrent conflict
            logger.error(f"Cannot deliver keys for Order #{order.id}: {e}")
            order.status = OrderStatus.FAILED
            order.note = f"Lỗi xuất kho: {str(e)}"
            await session.flush()
            return False, str(e), []

        # Update order status
        now = datetime.now(timezone.utc)
        order.status = OrderStatus.COMPLETED
        order.updated_at = now
        await session.flush()

        # Record affiliate commission
        try:
            await AffiliateService.record_commission(
                session=session,
                order_id=order.id,
                buyer_id=order.user_id,
                order_amount=order.final_amount,
            )
        except Exception as e:
            logger.error(f"Failed to record affiliate commission for order #{order.id}: {e}")

        # Fetch product info
        product = await ProductService.get_by_id(session, order.product_id)
        product_name = product.name if product else "Phần mềm MTK"
        guide = product.activation_guide if product and product.activation_guide else "Kích hoạt bằng cách nhập key vào phần mềm."

        # Format key list for message
        key_list_str = "\n".join([f"🔑 `<code>{k.key_code}</code>`" for k in keys])

        delivery_msg = (
            f"🎉 <b>THANH TOÁN THÀNH CÔNG! ĐƠN HÀNG #{order.order_code}</b>\n\n"
            f"📦 <b>Sản phẩm:</b> {product_name}\n"
            f"⏳ <b>Thời hạn:</b> {product.duration_days if product else 'N/A'} ngày\n"
            f"💰 <b>Thanh toán:</b> {format_vnd(order.final_amount)}\n\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🔑 <b>DANH SÁCH KEY CỦA BẠN:</b>\n"
            f"{key_list_str}\n"
            f"<i>(Chạm vào key để sao chép nhanh)</i>\n"
            f"━━━━━━━━━━━━━━━━━━━\n\n"
            f"📖 <b>Hướng dẫn kích hoạt:</b>\n{guide}\n\n"
            f"💡 Bạn luôn có thể xem lại key trong mục <b>📦 Key của tôi</b> bất cứ lúc nào."
        )

        # Send private Telegram message
        if bot:
            try:
                await bot.send_message(
                    chat_id=order.telegram_id,
                    text=delivery_msg,
                    parse_mode="HTML",
                )
                logger.info(f"Delivered key(s) to Telegram ID {order.telegram_id} for Order #{order.order_code}")
            except Exception as e:
                # User blocked bot or chat unavailable:
                # Do NOT rollback! Keys are safely stored in DB for retrieval via /start -> "Key của tôi".
                logger.warning(
                    f"Could not send Telegram message to user {order.telegram_id} (bot might be blocked): {e}. Keys remain safe in DB."
                )

            # Notify Super Admin
            if settings.SUPER_ADMIN_TELEGRAM_ID and settings.SUPER_ADMIN_TELEGRAM_ID > 0:
                try:
                    admin_notice = (
                        f"🔔 <b>[ĐƠN HÀNG MỚI THÀNH CÔNG]</b>\n\n"
                        f"• Mã đơn: <code>{order.order_code}</code>\n"
                        f"• Khách hàng: Telegram ID <code>{order.telegram_id}</code>\n"
                        f"• Sản phẩm: {product_name}\n"
                        f"• Số tiền: <b>{format_vnd(order.final_amount)}</b>\n"
                        f"• Phương thức: {order.payment_method}"
                    )
                    await bot.send_message(
                        chat_id=settings.SUPER_ADMIN_TELEGRAM_ID,
                        text=admin_notice,
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.warning(f"Could not send admin notification: {e}")

        return True, "Đơn hàng hoàn tất và đã giao key thành công.", keys

    @staticmethod
    async def pay_with_balance(
        session: AsyncSession,
        order_id: int,
        bot=None,
    ) -> Tuple[bool, str, List[KeyInventory]]:
        """Pay order directly using internal wallet balance"""
        order = await OrderService.get_by_id(session, order_id)
        if not order:
            raise ValueError("Không tìm thấy đơn hàng.")

        if order.status != OrderStatus.PENDING:
            raise ValueError("Đơn hàng này không ở trạng thái chờ thanh toán.")

        # Deduct wallet balance safely
        try:
            await UserService.adjust_balance(
                session=session,
                user_id=order.user_id,
                amount=-order.final_amount,
                tx_type=WalletTxType.PURCHASE,
                reference_code=order.order_code,
                description=f"Thanh toán đơn hàng #{order.order_code}",
            )
        except ValueError as e:
            return False, str(e), []

        order.payment_method = PaymentMethod.WALLET
        order.status = OrderStatus.PAID
        await session.flush()

        # Complete and deliver key
        return await OrderService.complete_order(session, order.id, bot=bot)

    @staticmethod
    async def refund_order(
        session: AsyncSession,
        order_id: int,
        admin_id: int,
        reason: str,
        refund_to_wallet: bool = True,
        bot=None,
    ) -> bool:
        """
        Refund an order:
        - Revoke all keys associated with this order.
        - Refund final_amount to user's wallet if requested.
        - Cancel affiliate commission.
        - Set status to REFUNDED.
        - Log audit trail.
        """
        order = await OrderService.get_by_id(session, order_id)
        if not order:
            raise ValueError(f"Không tìm thấy đơn #{order_id}")

        if order.status not in [OrderStatus.COMPLETED, OrderStatus.PAID]:
            raise ValueError(f"Chỉ có thể hoàn tiền đơn đã thanh toán hoặc hoàn tất (Hiện tại: {order.status})")

        # 1. Revoke keys
        stmt = select(KeyInventory).where(KeyInventory.order_id == order.id)
        keys = list((await session.execute(stmt)).scalars().all())
        now = datetime.now(timezone.utc)
        for k in keys:
            k.status = KeyStatus.REVOKED
            k.updated_at = now

        # 2. Refund money to user's wallet
        if refund_to_wallet and order.final_amount > 0:
            await UserService.adjust_balance(
                session=session,
                user_id=order.user_id,
                amount=order.final_amount,
                tx_type=WalletTxType.REFUND,
                reference_code=f"REFUND_{order.order_code}",
                description=f"Hoàn tiền đơn #{order.order_code}: {reason}",
                admin_id=admin_id,
            )

        # 3. Cancel affiliate commission
        await AffiliateService.cancel_commission_for_order(session, order.id, admin_id=admin_id)

        # 4. Mark order refunded
        order.status = OrderStatus.REFUNDED
        order.note = f"Hoàn tiền bởi Admin #{admin_id}: {reason}"
        order.updated_at = now
        await session.flush()

        await AuditService.log_action(
            session=session,
            action="REFUND_ORDER",
            admin_id=admin_id,
            target_type="order",
            target_id=str(order.id),
            details=f"amount={order.final_amount} | reason={reason} | keys_revoked={len(keys)}",
        )

        # 5. Notify user if bot is available
        if bot:
            try:
                msg = (
                    f"ℹ️ <b>THÔNG BÁO HOÀN TIỀN</b>\n\n"
                    f"Đơn hàng <code>#{order.order_code}</code> đã được hoàn lại số tiền <b>{format_vnd(order.final_amount)}</b> vào số dư ví của bạn.\n"
                    f"Lý do: <i>{reason}</i>\n"
                    f"Các key trong đơn hàng này đã được thu hồi."
                )
                await bot.send_message(chat_id=order.telegram_id, text=msg, parse_mode="HTML")
            except Exception as e:
                logger.warning(f"Could not notify user about refund: {e}")

        return True

    @staticmethod
    async def cancel_expired_pending_orders(session: AsyncSession) -> int:
        """Cancel orders that remained in PENDING past expires_at"""
        now = datetime.now(timezone.utc)
        stmt = select(Order).where(
            and_(
                Order.status == OrderStatus.PENDING,
                Order.expires_at < now,
            )
        )
        res = await session.execute(stmt)
        expired_orders = list(res.scalars().all())

        for o in expired_orders:
            o.status = OrderStatus.CANCELLED
            o.note = "Hết hạn thanh toán tự động."
            o.updated_at = now

        if expired_orders:
            await session.flush()
            logger.info(f"Cancelled {len(expired_orders)} expired pending order(s).")
        return len(expired_orders)

    @staticmethod
    async def list_orders_for_admin(
        session: AsyncSession,
        status: Optional[OrderStatus] = None,
        search: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> Tuple[List[Order], int]:
        query = select(Order)
        count_query = select(func.count(Order.id))

        filters = []
        if status:
            filters.append(Order.status == status)
        if search:
            filters.append(
                Order.order_code.ilike(f"%{search}%")
                | func.cast(Order.telegram_id, String).ilike(f"%{search}%")
            )

        if filters:
            query = query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        total = (await session.execute(count_query)).scalar() or 0
        offset = (page - 1) * limit
        items = (await session.execute(query.order_by(Order.id.desc()).offset(offset).limit(limit))).scalars().all()
        return list(items), total
