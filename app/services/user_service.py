from typing import Optional, List, Tuple
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import User, WalletTransaction, WalletTxType, Affiliate
from app.services.audit_service import AuditService
from app.utils.logger import logger
from app.utils.helpers import format_vnd


class UserService:
    @staticmethod
    async def get_or_create_user(
        session: AsyncSession,
        telegram_id: int,
        username: Optional[str] = None,
        full_name: Optional[str] = None,
        referrer_code: Optional[str] = None,
    ) -> User:
        """Get an existing user or create a new user from Telegram data"""
        stmt = select(User).where(User.telegram_id == telegram_id)
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()

        if user:
            # Update latest username or full_name if changed
            changed = False
            if username and user.username != username:
                user.username = username
                changed = True
            if full_name and user.full_name != full_name:
                user.full_name = full_name
                changed = True
            if changed:
                await session.flush()
            return user

        # Resolve referrer if provided
        referred_by_id = None
        if referrer_code:
            aff_stmt = select(Affiliate).where(Affiliate.referral_code == referrer_code)
            aff_res = await session.execute(aff_stmt)
            aff = aff_res.scalar_one_or_none()
            if aff and aff.user_id != telegram_id:
                referred_by_id = aff.user_id

        user = User(
            telegram_id=telegram_id,
            username=username,
            full_name=full_name,
            balance=0,
            is_banned=False,
            referred_by_id=referred_by_id,
        )
        session.add(user)
        await session.flush()
        logger.info(f"Registered new Telegram user: ID={user.id}, TelegramID={telegram_id}, Name={full_name}")
        return user

    @staticmethod
    async def get_by_telegram_id(session: AsyncSession, telegram_id: int) -> Optional[User]:
        stmt = select(User).where(User.telegram_id == telegram_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def get_by_id(session: AsyncSession, user_id: int) -> Optional[User]:
        stmt = select(User).where(User.id == user_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def adjust_balance(
        session: AsyncSession,
        user_id: int,
        amount: int,
        tx_type: WalletTxType,
        reference_code: str,
        description: str,
        admin_id: Optional[int] = None,
    ) -> WalletTransaction:
        """
        Safely adjust user wallet balance with atomic lock and non-negative constraint.
        amount can be positive (deposit, refund, credit) or negative (payment, debit).
        """
        # Lock user row for update
        stmt = select(User).where(User.id == user_id).with_for_update()
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        if not user:
            raise ValueError(f"User #{user_id} not found.")

        balance_before = user.balance
        new_balance = balance_before + amount

        if new_balance < 0:
            raise ValueError(
                f"Số dư không đủ. Hiện có: {format_vnd(balance_before)}, yêu cầu trừ: {format_vnd(abs(amount))}"
            )

        user.balance = new_balance

        tx = WalletTransaction(
            user_id=user_id,
            amount=amount,
            balance_before=balance_before,
            balance_after=new_balance,
            tx_type=tx_type,
            reference_code=reference_code,
            description=description,
        )
        session.add(tx)
        await session.flush()

        if admin_id:
            await AuditService.log_action(
                session=session,
                action="ADJUST_BALANCE",
                admin_id=admin_id,
                target_type="user",
                target_id=str(user_id),
                details=f"amount={amount} | balance={balance_before}->{new_balance} | reason={description} | ref={reference_code}",
            )

        logger.info(
            f"WALLET TX: User #{user_id} | Amount: {amount:+d} | Balance: {balance_before} -> {new_balance} | Type: {tx_type}"
        )
        return tx

    @staticmethod
    async def set_ban_status(
        session: AsyncSession,
        user_id: int,
        is_banned: bool,
        admin_id: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> User:
        user = await UserService.get_by_id(session, user_id)
        if not user:
            raise ValueError(f"User #{user_id} not found.")
        user.is_banned = is_banned
        await session.flush()

        if admin_id:
            action = "BAN_USER" if is_banned else "UNBAN_USER"
            await AuditService.log_action(
                session=session,
                action=action,
                admin_id=admin_id,
                target_type="user",
                target_id=str(user_id),
                details=f"banned={is_banned} | reason={reason}",
            )
        return user

    @staticmethod
    async def list_users(
        session: AsyncSession,
        page: int = 1,
        limit: int = 20,
        search: Optional[str] = None,
    ) -> Tuple[List[User], int]:
        query = select(User)
        count_query = select(func.count(User.id))

        if search:
            search_pattern = f"%{search}%"
            filter_clause = (
                User.username.ilike(search_pattern)
                | User.full_name.ilike(search_pattern)
                | func.cast(User.telegram_id, String).ilike(search_pattern)
            )
            query = query.where(filter_clause)
            count_query = count_query.where(filter_clause)

        total = (await session.execute(count_query)).scalar() or 0
        offset = (page - 1) * limit
        items = (await session.execute(query.order_by(User.id.desc()).offset(offset).limit(limit))).scalars().all()
        return list(items), total
