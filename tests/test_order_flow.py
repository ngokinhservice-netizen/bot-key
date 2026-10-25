import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import OrderStatus, KeyStatus, KeyInventory
from app.services.key_service import KeyService
from app.services.order_service import OrderService


@pytest.mark.asyncio
async def test_order_purchase_success_via_balance(db_session: AsyncSession, seed_data, mock_bot):
    """Test 1: Mua key thành công bằng số dư ví nội bộ"""
    user1 = seed_data["user1"]
    product = seed_data["product"]

    # 1. Import a key into inventory
    await KeyService.bulk_import_keys(
        session=db_session,
        product_id=product.id,
        raw_keys=["MTK-TEST-KEY-001"],
    )
    await db_session.commit()

    # 2. Create pending order
    order = await OrderService.create_order(
        session=db_session,
        user_id=user1.id,
        telegram_id=user1.telegram_id,
        product_id=product.id,
        quantity=1,
    )
    await db_session.commit()
    assert order.status == OrderStatus.PENDING

    # 3. Pay with wallet balance
    success, msg, keys = await OrderService.pay_with_balance(
        session=db_session,
        order_id=order.id,
        bot=mock_bot,
    )
    await db_session.commit()

    # 4. Verify outcomes
    assert success is True
    assert len(keys) == 1
    assert keys[0].key_code == "MTK-TEST-KEY-001"
    assert keys[0].status == KeyStatus.SOLD
    assert keys[0].buyer_telegram_id == user1.telegram_id
    assert order.status == OrderStatus.COMPLETED

    # Verify wallet deduction (500000 - 100000 = 400000)
    assert user1.balance == 400000


@pytest.mark.asyncio
async def test_out_of_stock_allows_order_and_marks_completed(db_session: AsyncSession, seed_data, mock_bot):
    """Test 5: Kho hết key vẫn cho mua và khi thanh toán vẫn báo đơn xanh COMPLETED"""
    user1 = seed_data["user1"]
    product = seed_data["product"]

    # No keys imported for this product, order should still be created successfully
    order = await OrderService.create_order(
        session=db_session,
        user_id=user1.id,
        telegram_id=user1.telegram_id,
        product_id=product.id,
        quantity=1,
    )
    assert order.status == OrderStatus.PENDING

    # When completed, order should be marked COMPLETED (báo xanh)
    success, msg, keys = await OrderService.complete_order(
        session=db_session,
        order_id=order.id,
        bot=mock_bot,
    )
    assert success is True
    assert order.status == OrderStatus.COMPLETED
    assert len(keys) == 0  # No auto keys delivered, manual delivery flagged
    assert "hết key" in order.note


@pytest.mark.asyncio
async def test_order_expiration_timeout(db_session: AsyncSession, seed_data):
    """Test 7: Đơn hàng bị timeout thì tự động hủy"""
    user1 = seed_data["user1"]
    product = seed_data["product"]

    # Add 1 key
    await KeyService.bulk_import_keys(db_session, product.id, ["MTK-KEY-TIMEOUT-01"])
    await db_session.commit()

    order = await OrderService.create_order(
        session=db_session,
        user_id=user1.id,
        telegram_id=user1.telegram_id,
        product_id=product.id,
        quantity=1,
    )
    # Manually backdate expires_at to 10 minutes ago
    order.expires_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    await db_session.commit()

    # Run background canceler
    cancelled_count = await OrderService.cancel_expired_pending_orders(db_session)
    await db_session.commit()

    assert cancelled_count >= 1
    assert order.status == OrderStatus.CANCELLED


@pytest.mark.asyncio
async def test_order_refund_flow(db_session: AsyncSession, seed_data, mock_bot):
    """Test 8: Hoàn tiền hoặc hủy đơn: thu hồi key, hoàn tiền vào ví"""
    user1 = seed_data["user1"]
    product = seed_data["product"]
    admin = seed_data["super_admin"]

    await KeyService.bulk_import_keys(db_session, product.id, ["MTK-REFUND-KEY-01"])
    await db_session.commit()

    # Purchase
    order = await OrderService.create_order(db_session, user1.id, user1.telegram_id, product.id)
    await db_session.commit()
    await OrderService.pay_with_balance(db_session, order.id, bot=mock_bot)
    await db_session.commit()

    balance_after_pay = user1.balance

    # Perform refund
    refund_res = await OrderService.refund_order(
        session=db_session,
        order_id=order.id,
        admin_id=admin.id,
        reason="Khách hàng đổi ý",
        refund_to_wallet=True,
        bot=mock_bot,
    )
    await db_session.commit()

    assert refund_res is True
    assert order.status == OrderStatus.REFUNDED
    assert user1.balance == balance_after_pay + order.final_amount

    # Verify key was marked REVOKED
    stmt = select(KeyInventory).where(KeyInventory.order_id == order.id)
    keys = list((await db_session.execute(stmt)).scalars().all())
    assert keys[0].status == KeyStatus.REVOKED
