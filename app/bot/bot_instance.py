import socket
import aiohttp
from typing import Optional
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from app.config.settings import settings


class IPv4AiohttpSession(AiohttpSession):
    """Force IPv4 TCP connection to bypass ISP / Windows IPv6 routing issues with Telegram API"""
    async def create_session(self) -> aiohttp.ClientSession:
        return aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(family=socket.AF_INET),
            json_serialize=self.json_dumps,
        )


bot: Optional[Bot] = None
dp: Optional[Dispatcher] = None


def get_bot() -> Bot:
    global bot
    if bot is None:
        session = IPv4AiohttpSession()
        bot = Bot(
            token=settings.TELEGRAM_BOT_TOKEN,
            session=session,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
    return bot


def get_dispatcher() -> Dispatcher:
    global dp
    if dp is None:
        dp = Dispatcher()
    return dp
