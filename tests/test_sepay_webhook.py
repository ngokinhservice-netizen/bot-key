import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import OrderStatus, KeyStatus, PaymentStatus, KeyInventory
from app.services.key_service import KeyService
from app.services.order_service import OrderService
from app.payments.webhook_handler import WebhookHandler


@pytest.mark.asyncio
async def test_sepay_webhook_underpaid_amount(db_session: AsyncSession, seed_data, mock_bot):
    """
    Test 2: Thanh toán sai số tiền (Thiếu tiền).
    Server không được giao key và phải chuyển trạng thái sang PARTIAL_PAID.
    """
    user1 = seed_data["user1"]
    product = seed_data["product"]

    # 1. Add key and create order for 100,000 VND
    await KeyService.bulk_import_keys(db_session, product.id, ["MTK-PARTIAL-KEY-01"])
    order = await OrderService.create_order(db_session, user1.id, user1.telegram_id, product.id)
    await db_session.commit()

    # 2. Simulate SePay webhook with underpaid transfer (50,000 VND instead of 100,000 VND)
    webhook_payload = {
        "id": 99901,
        "gateway": "MBBank",
        "transferType": "in",
        "transferAmount": 50000,  # 50k < 100k
        "content": f"{order.order_code} chuyen tien",
        "referenceCode": "MB_REF_001",
    }

    success, msg, code = await WebhookHandler.process_sepay_webhook(
        session=db_session,
        payload=webhook_payload,
        bot=mock_bot,
    )
    await db_session.commit()

    # 3. Assert: Order is marked PARTIAL_PAID, Key NOT assigned
    assert order.status == OrderStatus.PARTIAL_PAID
    stmt = select(KeyInventory).where(KeyInventory.key_code == "MTK-PARTIAL-KEY-01")
    key = (await db_session.execute(stmt)).scalar_one()
    assert key.status == KeyStatus.AVAILABLE
    assert key.order_id is None


@pytest.mark.asyncio
async def test_sepay_webhook_idempotency_duplicate(db_session: AsyncSession, seed_data, mock_bot):
    """
    Test 3: Webhook gửi lặp lại nhiều lần với cùng 1 mã giao dịch.
    Hệ thống chống xử lý trùng lặp và không giao thêm key.
    """
    user1 = seed_data["user1"]
    product = seed_data["product"]

    await KeyService.bulk_import_keys(db_session, product.id, ["MTK-IDEMP-KEY-01", "MTK-IDEMP-KEY-02"])
    order = await OrderService.create_order(db_session, user1.id, user1.telegram_id, product.id)
    await db_session.commit()

    webhook_payload = {
        "id": 88801,
        "gateway": "MBBank",
        "transferType": "in",
        "transferAmount": 100000,
        "content": f"{order.order_code} thanh toan",
        "referenceCode": "MB_REF_888",
    }

    # First delivery
    s1, m1, c1 = await WebhookHandler.process_sepay_webhook(db_session, webhook_payload, bot=mock_bot)
    await db_session.commit()
    assert order.status == OrderStatus.COMPLETED

    # Count sold keys
    stmt = select(KeyInventory).where(KeyInventory.order_id == order.id)
    assigned_keys = list((await db_session.execute(stmt)).scalars().all())
    assert len(assigned_keys) == 1

    # Second delivery (Duplicate webhook call)
    s2, m2, c2 = await WebhookHandler.process_sepay_webhook(db_session, webhook_payload, bot=mock_bot)
    await db_session.commit()

    assert s2 is True
    assert "Idempotent" in m2 or "tồn tại" in m2

    # Still only 1 key assigned, second key remains AVAILABLE
    stmt = select(KeyInventory).where(KeyInventory.order_id == order.id)
    assigned_keys_after = list((await db_session.execute(stmt)).scalars().all())
    assert len(assigned_keys_after) == 1


@pytest.mark.asyncio
async def test_sepay_webhook_wallet_deposit(db_session: AsyncSession, seed_data, mock_bot):
    """Test wallet deposit via bank transfer with NAP<telegram_id> content"""
    user2 = seed_data["user2"]
    initial_balance = user2.balance

    deposit_payload = {
        "id": 77701,
        "gateway": "Techcombank",
        "transferType": "in",
        "transferAmount": 200000,
        "content": f"NAP{user2.telegram_id}ABC",
        "referenceCode": "TCB_REF_777",
    }

    s, m, c = await WebhookHandler.process_sepay_webhook(db_session, deposit_payload, bot=mock_bot)
    await db_session.commit()

    assert s is True
    assert user2.balance == initial_balance + 200000
