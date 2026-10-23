import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import AdminRole
from app.admin.auth import require_roles
from app.services.key_service import KeyService
from app.services.order_service import OrderService


@pytest.mark.asyncio
async def test_idor_prevent_user_accessing_others_keys(db_session: AsyncSession, seed_data, mock_bot):
    """
    Test 9: Ngăn chặn người dùng truy cập dữ liệu của người khác (IDOR Prevention).
    User 1 mua key, User 2 truy vấn kho key của mình -> Tuyệt đối không thấy key của User 1.
    """
    user1 = seed_data["user1"]
    user2 = seed_data["user2"]
    product = seed_data["product"]

    # User 1 purchases a key
    await KeyService.bulk_import_keys(db_session, product.id, ["MTK-USER1-CONFIDENTIAL-KEY"])
    await db_session.commit()

    order1 = await OrderService.create_order(db_session, user1.id, user1.telegram_id, product.id)
    await db_session.commit()
    await OrderService.pay_with_balance(db_session, order1.id, bot=mock_bot)
    await db_session.commit()

    # User 2 queries their own keys
    user2_keys, user2_total = await KeyService.get_user_keys(
        session=db_session,
        buyer_telegram_id=user2.telegram_id,
    )

    # Assert: User 2 has 0 keys
    assert user2_total == 0
    assert len(user2_keys) == 0

    # User 1 queries their keys
    user1_keys, user1_total = await KeyService.get_user_keys(
        session=db_session,
        buyer_telegram_id=user1.telegram_id,
    )
    assert user1_total >= 1
    assert any(k.key_code == "MTK-USER1-CONFIDENTIAL-KEY" for k in user1_keys)


@pytest.mark.asyncio
async def test_rbac_staff_cannot_perform_super_admin_actions(seed_data):
    """
    Test 10: Phân quyền RBAC.
    Nhân viên cấp SUPPORT hoặc ORDER_MANAGER cố tình gọi endpoint yêu cầu quyền SUPER_ADMIN
    phải bị chặn với HTTP 403 Forbidden.
    """
    staff_user = seed_data["staff"]
    super_admin_user = seed_data["super_admin"]

    # Role checker requiring SUPER_ADMIN
    checker = require_roles([AdminRole.SUPER_ADMIN])

    # 1. Staff with SUPPORT role tries to access -> Expect 403
    with pytest.raises(HTTPException) as exc_info:
        await checker(admin=staff_user)
    assert exc_info.value.status_code == 403

    # 2. Super Admin tries to access -> Allowed
    result = await checker(admin=super_admin_user)
    assert result.username == "superadmin"
