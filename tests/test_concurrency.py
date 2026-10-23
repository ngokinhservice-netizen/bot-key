import asyncio
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import KeyStatus, KeyInventory
from app.services.key_service import KeyService
from app.services.order_service import OrderService


@pytest.mark.asyncio
async def test_race_condition_concurrent_purchase_last_key(db_session: AsyncSession, seed_data, mock_bot):
    """
    Test 4: Hai người mua key cuối cùng cùng lúc (Race Condition).
    Chỉ có 1 key duy nhất trong kho. Hệ thống khóa dòng dữ liệu đảm bảo:
    - Người đến trước nhận được key.
    - Người thứ hai bị từ chối với thông báo hết hàng.
    - Không bao giờ có chuyện 1 key bị bán 2 lần.
    """
    user1 = seed_data["user1"]
    user2 = seed_data["user2"]
    product = seed_data["product"]

    # Give user2 enough balance
    user2.balance = 500000

    # Put EXACTLY 1 KEY in stock
    await KeyService.bulk_import_keys(
        session=db_session,
        product_id=product.id,
        raw_keys=["MTK-LAST-SURVIVING-KEY"],
    )
    await db_session.commit()

    # Both users create orders
    order1 = await OrderService.create_order(db_session, user1.id, user1.telegram_id, product.id)
    order2 = await OrderService.create_order(db_session, user2.id, user2.telegram_id, product.id)
    await db_session.commit()

    # User 1 completes order first
    res1, msg1, keys1 = await OrderService.pay_with_balance(db_session, order1.id, bot=mock_bot)
    await db_session.commit()

    assert res1 is True
    assert len(keys1) == 1
    assert keys1[0].key_code == "MTK-LAST-SURVIVING-KEY"

    # User 2 attempts to complete order for the now sold-out product
    res2, msg2, keys2 = await OrderService.pay_with_balance(db_session, order2.id, bot=mock_bot)
    await db_session.commit()

    assert res2 is False
    assert "hết hàng" in msg2.lower() or "không đủ" in msg2.lower()
    assert len(keys2) == 0

    # Verify key table: exactly 1 key exists, sold to user1
    stmt = select(KeyInventory).where(KeyInventory.key_code == "MTK-LAST-SURVIVING-KEY")
    sold_key = (await db_session.execute(stmt)).scalar_one()
    assert sold_key.status == KeyStatus.SOLD
    assert sold_key.order_id == order1.id
    assert sold_key.buyer_telegram_id == user1.telegram_id
