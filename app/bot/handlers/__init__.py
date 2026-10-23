from aiogram import Dispatcher
from app.bot.handlers.start import router as start_router
from app.bot.handlers.buy_key import router as buy_key_router
from app.bot.handlers.my_keys import router as my_keys_router
from app.bot.handlers.deposit import router as deposit_router
from app.bot.handlers.transactions import router as transactions_router
from app.bot.handlers.discount import router as discount_router
from app.bot.handlers.affiliate import router as affiliate_router
from app.bot.handlers.support import router as support_router
from app.bot.handlers.terms import router as terms_router
from app.bot.handlers.admin_ops import router as admin_ops_router


def register_all_handlers(dp: Dispatcher) -> None:
    """Register all bot handler routers to Dispatcher"""
    dp.include_router(admin_ops_router)
    dp.include_router(start_router)
    dp.include_router(buy_key_router)
    dp.include_router(my_keys_router)
    dp.include_router(deposit_router)
    dp.include_router(transactions_router)
    dp.include_router(discount_router)
    dp.include_router(affiliate_router)
    dp.include_router(support_router)
    dp.include_router(terms_router)
