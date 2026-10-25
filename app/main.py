import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from app.config.settings import settings
from app.database.session import init_db, async_session_factory
from app.database.models import AdminUser, AdminRole, Product
from app.admin.auth import hash_password
from app.admin.routes import router as admin_router
from app.payments.routes import payment_router
from app.bot import setup_bot
from app.services.order_service import OrderService
from app.utils.logger import logger

bot_task = None
cleanup_task = None
keepalive_task = None


async def background_keepalive():
    """Ping health endpoint periodically to keep Cloud host (Render) awake 24/7"""
    import os, aiohttp
    await asyncio.sleep(60)  # Wait 1 minute after boot
    while True:
        try:
            render_url = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("WEB_BASE_URL")
            target = f"{render_url.rstrip('/')}/health" if render_url else f"http://localhost:{settings.PORT}/health"
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(target) as resp:
                    if resp.status == 200:
                        logger.debug(f"Keepalive ping successful to {target}")
        except Exception as e:
            logger.debug(f"Keepalive ping notice: {e}")
        await asyncio.sleep(480)  # Every 8 minutes


async def seed_initial_data():
    """Seed initial Super Admin and sample products if table is empty"""
    async with async_session_factory() as session:
        # 1. Super Admin
        admin_check = await session.execute(
            select(AdminUser).where(AdminUser.username == settings.ADMIN_DEFAULT_USERNAME)
        )
        if not admin_check.scalar_one_or_none():
            super_admin = AdminUser(
                username=settings.ADMIN_DEFAULT_USERNAME,
                hashed_password=hash_password(settings.ADMIN_DEFAULT_PASSWORD),
                role=AdminRole.SUPER_ADMIN,
                is_active=True,
            )
            session.add(super_admin)
            logger.info(f"Seeded default Super Admin: '{settings.ADMIN_DEFAULT_USERNAME}'")

        # 2. Seed / Update 4 Core Products from User Specifications
        desired_products = [
            {
                "name": "Bản ngày",
                "slug": "ban-ngay",
                "description": "Dùng cho 1 ngày thi — có thể chọn ngày sau",
                "price": 347000,
                "duration_days": 1,
                "activation_guide": "Nhập key vào phần mềm để kích hoạt Bản ngày (1 ngày thi).",
            },
            {
                "name": "Full kỳ",
                "slug": "full-ky",
                "description": "Dùng trong suốt kỳ thi",
                "price": 833000,
                "duration_days": 90,
                "activation_guide": "Nhập key vào phần mềm để kích hoạt Full kỳ (toàn bộ kỳ thi).",
            },
            {
                "name": "SEB kỳ",
                "slug": "seb-ky",
                "description": "Tải đề và dùng đáp án SEB; không kèm EOS/PEA",
                "price": 100000,
                "duration_days": 90,
                "activation_guide": "Kích hoạt bản quyền SEB kỳ trong phần mềm.",
            },
            {
                "name": "SEB ngày",
                "slug": "seb-ngay",
                "description": "SEB đến cuối ngày upload đề đầu tiên",
                "price": 50000,
                "duration_days": 1,
                "activation_guide": "Kích hoạt bản quyền SEB ngày trong phần mềm.",
            },
        ]
        for pdata in desired_products:
            stmt = select(Product).where(Product.slug == pdata["slug"])
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if not existing:
                p = Product(
                    name=pdata["name"],
                    slug=pdata["slug"],
                    description=pdata["description"],
                    price=pdata["price"],
                    duration_days=pdata["duration_days"],
                    is_active=True,
                    activation_guide=pdata["activation_guide"],
                )
                session.add(p)
                logger.info(f"Seeded product: {pdata['name']} ({pdata['price']} đ)")
            else:
                existing.name = pdata["name"]
                existing.description = pdata["description"]
                existing.price = pdata["price"]
                existing.duration_days = pdata["duration_days"]

        await session.commit()


async def background_order_cleaner():
    """Periodically cancel expired pending orders every 60 seconds"""
    while True:
        try:
            async with async_session_factory() as session:
                await OrderService.cancel_expired_pending_orders(session)
                await session.commit()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in background_order_cleaner: {e}")
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global bot_task, cleanup_task

    logger.info("=== STARTING SHARK COMPANY KEY BOT SYSTEM ===")
    # 1. Init Database
    await init_db()
    await seed_initial_data()

    # 2. Start Bot Polling in background task
    bot, dp = setup_bot()

    # Check if token is configured
    async def run_bot_polling():
        try:
            logger.info("Starting Telegram Bot polling (drop_pending_updates=True, IPv4 forced)...")
            await dp.start_polling(bot, drop_pending_updates=True)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Telegram Bot polling encountered error: {e}")

    if settings.TELEGRAM_BOT_TOKEN and not settings.TELEGRAM_BOT_TOKEN.startswith("1234567890:"):
        bot_task = asyncio.create_task(run_bot_polling())
    else:
        logger.warning(
            "TELEGRAM_BOT_TOKEN is not configured or using default demo placeholder! Telegram polling skipped."
        )

    # 3. Start background order cleaner
    cleanup_task = asyncio.create_task(background_order_cleaner())

    # 4. Start background keepalive ping to prevent Cloud sleep
    keepalive_task = asyncio.create_task(background_keepalive())

    yield

    logger.info("=== SHUTTING DOWN SHARK COMPANY KEY BOT SYSTEM ===")
    if keepalive_task:
        keepalive_task.cancel()
    if cleanup_task:
        cleanup_task.cancel()
    if bot_task:
        bot_task.cancel()
        try:
            await bot.session.close()
        except Exception:
            pass


app = FastAPI(
    title="SHARK COMPANY Key Bot & Admin API",
    description="Hệ thống bán key bản quyền phần mềm tự động SHARK COMPANY với SePay Webhook & Telegram Bot",
    version="1.0.0",
    lifespan=lifespan,
)

# Include Routers
app.include_router(admin_router)
app.include_router(payment_router)


@app.get("/")
async def root():
    return RedirectResponse(url="/admin/login")


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "SHARK COMPANY Key Bot",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
    )
