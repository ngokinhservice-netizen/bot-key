import secrets
import string
from typing import Optional, List, Tuple
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.config.settings import settings
from app.database.models import (
    Affiliate,
    AffiliateCommission,
    CommissionStatus,
    User,
    WalletTxType,
)
from app.services.user_service import UserService
from app.services.audit_service import AuditService
from app.utils.logger import logger


class AffiliateService:
    @staticmethod
    async def get_or_create_affiliate(session: AsyncSession, user_id: int) -> Affiliate:
        stmt = select(Affiliate).where(Affiliate.user_id == user_id)
        res = await session.execute(stmt)
        aff = res.scalar_one_or_none()

        if aff:
            return aff

        # Generate unique referral code: REF + random chars
        chars = string.ascii_uppercase + string.digits
        for _ in range(10):
            rand = ''.join(secrets.choice(chars) for _ in range(6))
            ref_code = f"REF{rand}"
            check = await session.execute(select(Affiliate).where(Affiliate.referral_code == ref_code))
            if not check.scalar_one_or_none():
                break

        aff = Affiliate(
            user_id=user_id,
            referral_code=ref_code,
            commission_rate=settings.DEFAULT_AFFILIATE_COMMISSION_PERCENT,
            total_earnings=0,
            pending_balance=0,
        )
        session.add(aff)
        await session.flush()
        logger.info(f"Created Affiliate profile for user #{user_id} with code {ref_code}")
        return aff

    @staticmethod
    async def record_commission(
        session: AsyncSession,
        order_id: int,
        buyer_id: int,
        order_amount: int,
    ) -> Optional[AffiliateCommission]:
        """
        Record commission for referrer when buyer places an order.
        Checks: buyer must have referred_by_id, and cannot self-refer.
        """
        buyer = await UserService.get_by_id(session, buyer_id)
        if not buyer or not buyer.referred_by_id:
            return None

        # Anti-fraud: cannot refer oneself
        if buyer.referred_by_id == buyer_id:
            logger.warning(f"Anti-fraud: User #{buyer_id} attempted self-referral on order #{order_id}")
            return None

        # Check existing commission for this order
        check_stmt = select(AffiliateCommission).where(AffiliateCommission.order_id == order_id)
        existing = (await session.execute(check_stmt)).scalar_one_or_none()
        if existing:
            return existing

        affiliate = await AffiliateService.get_or_create_affiliate(session, buyer.referred_by_id)
        commission_amount = int(order_amount * (affiliate.commission_rate / 100.0))

        if commission_amount <= 0:
            return None

        commission = AffiliateCommission(
            affiliate_id=affiliate.id,
            order_id=order_id,
            buyer_id=buyer_id,
            order_amount=order_amount,
            commission_amount=commission_amount,
            status=CommissionStatus.APPROVED,  # Approved upon successful order
        )
        session.add(commission)

        # Update affiliate totals
        affiliate.total_earnings += commission_amount
        affiliate.pending_balance += commission_amount

        # Also credit directly to referrer's wallet balance so they can spend or withdraw
        await UserService.adjust_balance(
            session=session,
            user_id=affiliate.user_id,
            amount=commission_amount,
            tx_type=WalletTxType.DEPOSIT,
            reference_code=f"COMM_DH{order_id}",
            description=f"Hoa hồng giới thiệu từ đơn #{order_id} ({affiliate.commission_rate}%)",
        )

        await session.flush()
        logger.info(
            f"Commission granted: Affiliate #{affiliate.id} (User #{affiliate.user_id}) received +{commission_amount} VND from Order #{order_id}"
        )
        return commission

    @staticmethod
    async def cancel_commission_for_order(session: AsyncSession, order_id: int, admin_id: Optional[int] = None):
        """Rollback commission if order is refunded or cancelled"""
        stmt = select(AffiliateCommission).where(
            and_(
                AffiliateCommission.order_id == order_id,
                AffiliateCommission.status.in_([CommissionStatus.PENDING, CommissionStatus.APPROVED]),
            )
        )
        res = await session.execute(stmt)
        commissions = list(res.scalars().all())

        for comm in commissions:
            comm.status = CommissionStatus.CANCELLED
            aff_stmt = select(Affiliate).where(Affiliate.id == comm.affiliate_id)
            aff = (await session.execute(aff_stmt)).scalar_one_or_none()
            if aff:
                aff.total_earnings = max(0, aff.total_earnings - comm.commission_amount)
                # Deduct from user balance if already credited
                try:
                    await UserService.adjust_balance(
                        session=session,
                        user_id=aff.user_id,
                        amount=-comm.commission_amount,
                        tx_type=WalletTxType.PURCHASE,
                        reference_code=f"COMM_REVOKE_DH{order_id}",
                        description=f"Thu hồi hoa hồng do đơn #{order_id} bị hoàn tiền/hủy",
                        admin_id=admin_id,
                    )
                except ValueError:
                    logger.warning(f"Could not deduct revoked commission from user #{aff.user_id} due to low balance.")

        await session.flush()
