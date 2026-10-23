import pytest
from unittest.mock import AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import OrderStatus, KeyStatus
from app.services.key_service import KeyService
from app.services.order_service import OrderService


@pytest.mark.asyncio
async def test_user_blocked_bot_keys_saved_and_retrievable(db_session: AsyncSession, seed_data):
    """
    Test 6: Người dùng chặn bot (Telegram Forbidden/Blocked).
    Khi bot không thể gửi tin nhắn riêng cho khách:
    - Đơn hàng vẫn hoàn tất và giữ trạng thái COMPLETED.
    - Key vẫn được gắn với Telegram ID của người mua an toàn trong DB.
    - Người dùng có thể lấy lại key bất cứ lúc nào qua hàm get_user_keys (nút 'Key của tôi').
    """
    user1 = seed_data["user1"]
    product = seed_data["product"]

    await KeyService.bulk_import_keys(db_session, product.id, ["MTK-SAFE-KEY-FOR-BLOCKED-USER"])
    await db_session.commit()

    order = await OrderService.create_order(db_session, user1.id, user1.telegram_id, product.id)
    await db_session.commit()

    # Create mock bot that simulates user blocking the bot
    blocked_bot = AsyncMock()
    blocked_bot.send_message.side_effect = Exception("Forbidden: bot was blocked by the user")

    # Complete order
    success, msg, keys = await OrderService.complete_order(
        session=db_session,
        order_id=order.id,
        bot=blocked_bot,
    )
    await db_session.commit()

    # Order must still succeed!
    assert success is True
    assert order.status == OrderStatus.COMPLETED
    assert len(keys) == 1
    assert keys[0].key_code == "MTK-SAFE-KEY-FOR-BLOCKED-USER"
    assert keys[0].status == KeyStatus.SOLD

    # Retrieve keys through "Key của tôi" logic
    user_keys, total = await KeyService.get_user_keys(
        session=db_session,
        buyer_telegram_id=user1.telegram_id,
    )
    assert total >= 1
    retrieved_codes = [k.key_code for k in user_keys]
    assert "MTK-SAFE-KEY-FOR-BLOCKED-USER" in retrieved_codes
