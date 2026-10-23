from datetime import datetime, timezone
from typing import Optional, List, Tuple
from sqlalchemy import select, func, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import KeyInventory, KeyStatus, Product, Order
from app.services.audit_service import AuditService
from app.utils.logger import logger


class KeyService:
    @staticmethod
    async def bulk_import_keys(
        session: AsyncSession,
        product_id: int,
        raw_keys: List[str],
        admin_id: Optional[int] = None,
    ) -> Tuple[int, int]:
        """
        Import multiple license keys for a product.
        Cleans whitespace, deduplicates against DB and within the import list.
        Returns (added_count, duplicate_count).
        """
        # 1. Clean and deduplicate within import list
        cleaned_keys = []
        seen = set()
        for k in raw_keys:
            key_str = k.strip()
            if key_str and key_str not in seen:
                seen.add(key_str)
                cleaned_keys.append(key_str)

        if not cleaned_keys:
            return 0, 0

        # 2. Check existing keys in DB
        stmt = select(KeyInventory.key_code).where(KeyInventory.key_code.in_(cleaned_keys))
        res = await session.execute(stmt)
        existing_in_db = set(res.scalars().all())

        new_keys = [k for k in cleaned_keys if k not in existing_in_db]
        duplicate_count = len(raw_keys) - len(new_keys)

        # 3. Insert new keys
        now = datetime.now(timezone.utc)
        items_to_add = [
            KeyInventory(
                product_id=product_id,
                key_code=k,
                status=KeyStatus.AVAILABLE,
                created_at=now,
                updated_at=now,
            )
            for k in new_keys
        ]
        session.add_all(items_to_add)
        await session.flush()

        if admin_id and items_to_add:
            await AuditService.log_action(
                session=session,
                action="BULK_IMPORT_KEYS",
                admin_id=admin_id,
                target_type="product",
                target_id=str(product_id),
                details=f"imported={len(items_to_add)} | duplicates_skipped={duplicate_count}",
            )

        logger.info(
            f"Imported {len(items_to_add)} keys for Product #{product_id} ({duplicate_count} duplicates skipped)"
        )
        return len(items_to_add), duplicate_count

    @staticmethod
    async def lock_and_assign_keys(
        session: AsyncSession,
        product_id: int,
        quantity: int,
        order_id: int,
        buyer_telegram_id: int,
    ) -> List[KeyInventory]:
        """
        Atomically lock and assign `quantity` AVAILABLE keys to an order.
        Uses `with_for_update` row locking to prevent race conditions when two users
        purchase the last available key at the exact same millisecond.
        """
        # Find available keys with row-level lock
        stmt = (
            select(KeyInventory)
            .where(
                and_(
                    KeyInventory.product_id == product_id,
                    KeyInventory.status == KeyStatus.AVAILABLE,
                )
            )
            .with_for_update()
            .limit(quantity)
        )
        res = await session.execute(stmt)
        keys = list(res.scalars().all())

        if len(keys) < quantity:
            raise ValueError(
                f"Kho key không đủ hàng! Cần {quantity} key nhưng chỉ còn {len(keys)} key khả dụng."
            )

        now = datetime.now(timezone.utc)
        for key in keys:
            # Double check status before updating
            if key.status != KeyStatus.AVAILABLE:
                raise ValueError(f"Key #{key.id} vừa được người khác mua hoặc thay đổi trạng thái.")
            key.status = KeyStatus.SOLD
            key.order_id = order_id
            key.buyer_telegram_id = buyer_telegram_id
            key.delivered_at = now
            key.updated_at = now

        await session.flush()
        logger.info(
            f"Assigned {len(keys)} key(s) to Order #{order_id} for Telegram ID {buyer_telegram_id}"
        )
        return keys

    @staticmethod
    async def get_user_keys(
        session: AsyncSession,
        buyer_telegram_id: int,
        page: int = 1,
        limit: int = 5,
    ) -> Tuple[List[KeyInventory], int]:
        """Get keys owned by a user with pagination"""
        count_stmt = select(func.count(KeyInventory.id)).where(
            KeyInventory.buyer_telegram_id == buyer_telegram_id
        )
        total = (await session.execute(count_stmt)).scalar() or 0

        offset = (page - 1) * limit
        stmt = (
            select(KeyInventory)
            .where(KeyInventory.buyer_telegram_id == buyer_telegram_id)
            .order_by(KeyInventory.delivered_at.desc().nullslast(), KeyInventory.id.desc())
            .offset(offset)
            .limit(limit)
        )
        res = await session.execute(stmt)
        return list(res.scalars().all()), total

    @staticmethod
    async def get_key_by_id(session: AsyncSession, key_id: int) -> Optional[KeyInventory]:
        stmt = select(KeyInventory).where(KeyInventory.id == key_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def revoke_key(
        session: AsyncSession,
        key_id: int,
        reason: str,
        admin_id: Optional[int] = None,
    ) -> KeyInventory:
        """Revoke a key (mark REVOKED) e.g. for refund or abuse"""
        key = await KeyService.get_key_by_id(session, key_id)
        if not key:
            raise ValueError(f"Không tìm thấy key #{key_id}")

        old_status = key.status
        key.status = KeyStatus.REVOKED
        key.updated_at = datetime.now(timezone.utc)
        await session.flush()

        if admin_id:
            await AuditService.log_action(
                session=session,
                action="REVOKE_KEY",
                admin_id=admin_id,
                target_type="key",
                target_id=str(key_id),
                details=f"status={old_status}->REVOKED | reason={reason}",
            )
        return key

    @staticmethod
    async def list_keys_for_admin(
        session: AsyncSession,
        product_id: Optional[int] = None,
        status: Optional[KeyStatus] = None,
        search: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> Tuple[List[KeyInventory], int]:
        query = select(KeyInventory)
        count_query = select(func.count(KeyInventory.id))

        filters = []
        if product_id:
            filters.append(KeyInventory.product_id == product_id)
        if status:
            filters.append(KeyInventory.status == status)
        if search:
            filters.append(KeyInventory.key_code.ilike(f"%{search}%"))

        if filters:
            query = query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        total = (await session.execute(count_query)).scalar() or 0
        offset = (page - 1) * limit
        items = (await session.execute(query.order_by(KeyInventory.id.desc()).offset(offset).limit(limit))).scalars().all()
        return list(items), total
