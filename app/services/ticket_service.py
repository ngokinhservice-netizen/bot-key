import secrets
from datetime import datetime, timezone
from typing import Optional, List, Tuple
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import SupportTicket, TicketStatus, User
from app.services.audit_service import AuditService
from app.utils.logger import logger


class TicketService:
    @staticmethod
    async def create_ticket(
        session: AsyncSession,
        user_id: int,
        telegram_id: int,
        subject: str,
        message: str,
    ) -> SupportTicket:
        ticket_code = f"TK{datetime.now().strftime('%y%m%d')}-{secrets.token_hex(2).upper()}"
        ticket = SupportTicket(
            ticket_code=ticket_code,
            user_id=user_id,
            telegram_id=telegram_id,
            subject=subject,
            message=message,
            status=TicketStatus.OPEN,
        )
        session.add(ticket)
        await session.flush()
        logger.info(f"Created Support Ticket {ticket_code} for Telegram ID {telegram_id}")
        return ticket

    @staticmethod
    async def get_by_code(session: AsyncSession, ticket_code: str) -> Optional[SupportTicket]:
        stmt = select(SupportTicket).where(SupportTicket.ticket_code == ticket_code)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def get_by_id(session: AsyncSession, ticket_id: int) -> Optional[SupportTicket]:
        stmt = select(SupportTicket).where(SupportTicket.id == ticket_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def reply_ticket(
        session: AsyncSession,
        ticket_id: int,
        reply: str,
        admin_id: Optional[int] = None,
        new_status: TicketStatus = TicketStatus.RESOLVED,
    ) -> SupportTicket:
        ticket = await TicketService.get_by_id(session, ticket_id)
        if not ticket:
            raise ValueError(f"Không tìm thấy yêu cầu hỗ trợ #{ticket_id}")

        ticket.reply = reply
        ticket.status = new_status
        ticket.admin_id = admin_id
        ticket.updated_at = datetime.now(timezone.utc)
        await session.flush()

        if admin_id:
            await AuditService.log_action(
                session=session,
                action="REPLY_TICKET",
                admin_id=admin_id,
                target_type="ticket",
                target_id=str(ticket_id),
                details=f"status={new_status} | reply_length={len(reply)}",
            )
        return ticket

    @staticmethod
    async def list_tickets(
        session: AsyncSession,
        status: Optional[TicketStatus] = None,
        page: int = 1,
        limit: int = 20,
    ) -> Tuple[List[SupportTicket], int]:
        query = select(SupportTicket)
        count_query = select(func.count(SupportTicket.id))

        if status:
            query = query.where(SupportTicket.status == status)
            count_query = count_query.where(SupportTicket.status == status)

        total = (await session.execute(count_query)).scalar() or 0
        offset = (page - 1) * limit
        items = (await session.execute(query.order_by(SupportTicket.id.desc()).offset(offset).limit(limit))).scalars().all()
        return list(items), total
