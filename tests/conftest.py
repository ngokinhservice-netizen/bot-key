import pytest
import pytest_asyncio
from unittest.mock import AsyncMock
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.database.models import Base, User, Product, AdminUser, AdminRole
from app.admin.auth import hash_password

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def mock_bot():
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=True)
    return bot


@pytest_asyncio.fixture
async def seed_data(db_session: AsyncSession):
    # Sample user
    user1 = User(
        telegram_id=111111111,
        username="buyer_one",
        full_name="Nguyễn Văn A",
        balance=500000,
        is_banned=False,
    )
    user2 = User(
        telegram_id=222222222,
        username="buyer_two",
        full_name="Trần Thị B",
        balance=10000,
        is_banned=False,
    )
    db_session.add_all([user1, user2])

    # Sample product
    product = Product(
        name="MTK Task – Key 30 ngày",
        slug="mtk-task-30d",
        description="Bản quyền 30 ngày",
        price=100000,
        duration_days=30,
        is_active=True,
    )
    db_session.add(product)
    await db_session.flush()

    # Sample admin users
    super_admin = AdminUser(
        username="superadmin",
        hashed_password=hash_password("admin123"),
        role=AdminRole.SUPER_ADMIN,
        is_active=True,
    )
    staff_support = AdminUser(
        username="staff_support",
        hashed_password=hash_password("staff123"),
        role=AdminRole.SUPPORT,
        is_active=True,
    )
    db_session.add_all([super_admin, staff_support])

    await db_session.commit()
    return {"user1": user1, "user2": user2, "product": product, "super_admin": super_admin, "staff": staff_support}
