from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import AuditLog
from app.utils.logger import logger


class AuditService:
    @staticmethod
    async def log_action(
        session: AsyncSession,
        action: str,
        admin_id: Optional[int] = None,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        details: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> AuditLog:
        """Record an audit trail log for sensitive operations"""
        entry = AuditLog(
            admin_id=admin_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id else None,
            details=details,
            ip_address=ip_address,
        )
        session.add(entry)
        await session.flush()
        logger.info(f"AUDIT | action={action} | admin_id={admin_id} | target={target_type}:{target_id}")
        return entry
