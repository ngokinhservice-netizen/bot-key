from app.bot.bot_instance import get_bot, get_dispatcher
from app.bot.middlewares.db_middleware import DbSessionMiddleware
from app.bot.middlewares.auth_middleware import AuthMiddleware
from app.bot.middlewares.throttling import ThrottlingMiddleware
from app.bot.handlers import register_all_handlers


def setup_bot():
    bot = get_bot()
    dp = get_dispatcher()

    # Outer middlewares run before filters
    dp.update.outer_middleware(DbSessionMiddleware())
    dp.update.outer_middleware(AuthMiddleware())
    dp.message.middleware(ThrottlingMiddleware())
    dp.callback_query.middleware(ThrottlingMiddleware())

    # Register handlers
    register_all_handlers(dp)
    return bot, dp


__all__ = ["get_bot", "get_dispatcher", "setup_bot"]
