from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TgUser, Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.user_service import UserService
from app.utils.logger import logger


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        tg_user: TgUser = data.get("event_from_user")
        if not tg_user:
            return await handler(event, data)

        session: AsyncSession = data.get("session")
        if not session:
            return await handler(event, data)

        # Extract potential referral code if message starts with /start REF...
        ref_code = None
        if isinstance(event, Message) and event.text and event.text.startswith("/start REF"):
            parts = event.text.split()
            if len(parts) > 1:
                ref_code = parts[1].strip()

        # Get or create DB User
        user = await UserService.get_or_create_user(
            session=session,
            telegram_id=tg_user.id,
            username=tg_user.username,
            full_name=tg_user.full_name,
            referrer_code=ref_code,
        )

        # Ban check
        if user.is_banned:
            banned_text = "⛔ <b>Tài khoản của bạn đã bị khóa!</b>\nVui lòng liên hệ quản trị viên để biết thêm chi tiết."
            if isinstance(event, Message):
                await event.answer(banned_text, parse_mode="HTML")
            elif isinstance(event, CallbackQuery):
                await event.answer("Tài khoản của bạn đã bị khóa!", show_alert=True)
            return

        data["user"] = user
        return await handler(event, data)
