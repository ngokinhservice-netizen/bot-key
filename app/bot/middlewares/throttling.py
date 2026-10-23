import time
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TgUser, CallbackQuery


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate_limit_seconds: float = 0.5):
        self.rate_limit = rate_limit_seconds
        self.user_last_action: Dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        tg_user: TgUser = data.get("event_from_user")
        if not tg_user:
            return await handler(event, data)

        now = time.time()
        last_time = self.user_last_action.get(tg_user.id, 0.0)

        if now - last_time < self.rate_limit:
            if isinstance(event, CallbackQuery):
                await event.answer("⚠️ Thao tác quá nhanh, vui lòng chờ giây lát!", show_alert=False)
            return

        self.user_last_action[tg_user.id] = now
        return await handler(event, data)
