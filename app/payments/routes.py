from typing import Optional, Dict, Any
from fastapi import APIRouter, Request, Header, Query, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.config.settings import settings
from app.database.session import get_db
from app.payments.sepay import SePayGateway
from app.payments.webhook_handler import WebhookHandler
from app.services.setting_service import SettingService
from app.bot.bot_instance import get_bot
from app.utils.logger import logger

payment_router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


@payment_router.post("/sepay/webhook")
async def sepay_webhook_endpoint(
    request: Request,
    authorization: Optional[str] = Header(None),
    api_key: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db),
):
    """
    Official SePay Webhook endpoint.
    Handles SePay dashboard test pings and real payment callbacks with authentication.
    """
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse JSON body from webhook: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body")

    # Check if this is a test ping from SePay dashboard (e.g. "Gửi thử")
    tx_id = str(payload.get("id") or payload.get("referenceCode") or "")
    payload_str = str(payload).lower()
    is_test_ping = (not tx_id or tx_id == "0" or "test" in payload_str or "ping" in payload_str)

    # Get current configured API key
    db_bank_info = await SettingService.get_bank_info(session)
    configured_key = db_bank_info.get("sepay_api_key") or settings.SEPAY_API_KEY

    # Extract incoming token
    incoming_token = None
    if authorization:
        parts = authorization.strip().split()
        incoming_token = parts[1] if len(parts) == 2 else authorization.strip()
    elif api_key:
        incoming_token = api_key.strip()

    # If incoming token is provided and we are still using demo placeholder, auto-save the real token
    if incoming_token and (not configured_key or configured_key == "sepay_api_key_demo"):
        await SettingService.set_setting(session, "SEPAY_API_KEY", incoming_token, "Auto-captured from SePay webhook")
        await session.commit()
        configured_key = incoming_token
        logger.info(f"Auto-configured SePay API Key from webhook: {incoming_token[:6]}***")

    # If not a test ping, strictly enforce authentication if configured
    if not is_test_ping and configured_key and configured_key != "sepay_api_key_demo":
        if incoming_token != configured_key:
            logger.warning("Rejected unauthorized webhook attempt (Token mismatch).")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized webhook request",
            )

    bot = get_bot()
    success, message, code = await WebhookHandler.process_sepay_webhook(
        session=session,
        payload=payload,
        bot=bot,
    )

    await session.commit()
    return {"success": success, "message": message}


@payment_router.post("/test/simulate")
async def simulate_test_payment(
    payload: Dict[str, Any],
    session: AsyncSession = Depends(get_db),
):
    """
    Sandbox / Test Payment simulation endpoint.
    STRICT SECURITY RULE: Only operational when ALLOW_TEST_PAYMENTS=True.
    Strictly forbidden and disabled in production.
    """
    if not settings.ALLOW_TEST_PAYMENTS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chế độ thanh toán thử nghiệm (ALLOW_TEST_PAYMENTS) đang bị tắt trong cấu hình hệ thống.",
        )

    bot = get_bot()
    success, message, code = await WebhookHandler.process_sepay_webhook(
        session=session,
        payload=payload,
        bot=bot,
    )
    await session.commit()
    return {"success": success, "message": message, "mode": "TEST_SIMULATION"}
