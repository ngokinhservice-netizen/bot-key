import json
from typing import Dict, Any, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config.settings import settings
from app.database.models import (
    WebhookEvent,
    WebhookStatus,
    Payment,
    PaymentStatus,
    Order,
    OrderStatus,
    WalletTxType,
)
from app.services.order_service import OrderService
from app.services.user_service import UserService
from app.utils.logger import logger
from app.utils.helpers import (
    parse_order_code_from_content,
    parse_deposit_code_from_content,
    format_vnd,
)


class WebhookHandler:
    @staticmethod
    async def process_sepay_webhook(
        session: AsyncSession,
        payload: Dict[str, Any],
        bot=None,
    ) -> Tuple[bool, str, int]:
        """
        Process incoming SePay Webhook transaction.
        Returns: (success: bool, message: str, status_code: int)
        """
        # SePay payload fields
        tx_id = str(payload.get("id") or payload.get("referenceCode") or "")
        transfer_type = str(payload.get("transferType", "in")).lower()
        transfer_amount = int(payload.get("transferAmount", 0) or 0)
        content = str(payload.get("content", "") or payload.get("description", ""))

        if not tx_id or tx_id == "0":
            return True, "Ping test kết nối SePay Webhook thành công (HTTP 200)", 200

        # Only process incoming money (transferType == "in")
        if transfer_type != "in":
            logger.info(f"Ignoring outgoing transfer: tx_id={tx_id}, type={transfer_type}")
            return True, "Bỏ qua giao dịch tiền ra", 200

        raw_json = json.dumps(payload, ensure_ascii=False)

        # 1. Idempotency Check: prevent processing duplicate webhook deliveries
        existing_event = await session.execute(
            select(WebhookEvent).where(WebhookEvent.event_id == tx_id)
        )
        if existing_event.scalar_one_or_none():
            logger.warning(f"Duplicate webhook received for tx_id={tx_id}. Skipping processing.")
            return True, "Giao dịch đã được xử lý trước đó (Idempotent).", 200

        # Also check existing payment transaction_id
        existing_pay = await session.execute(
            select(Payment).where(Payment.transaction_id == tx_id)
        )
        if existing_pay.scalar_one_or_none():
            logger.warning(f"Payment with tx_id={tx_id} already exists in database. Skipping.")
            return True, "Payment record đã tồn tại.", 200

        # Record webhook event first
        webhook_evt = WebhookEvent(
            event_id=tx_id,
            provider="sepay",
            event_type="transfer_in",
            payload=raw_json,
            status=WebhookStatus.PROCESSED,
        )
        session.add(webhook_evt)

        # 2. Case A: Check if content matches an Order (DH...)
        order_code = parse_order_code_from_content(content)
        if order_code:
            order = await OrderService.get_by_code(session, order_code)
            if not order:
                logger.warning(f"Order {order_code} not found for payment tx_id={tx_id}")
                # Create orphaned payment record for manual review
                pay = Payment(
                    order_id=None,
                    user_id=None,
                    transaction_id=tx_id,
                    provider="sepay",
                    amount=transfer_amount,
                    status=PaymentStatus.PENDING,
                    payload_json=raw_json,
                )
                session.add(pay)
                await session.flush()
                return True, f"Không tìm thấy đơn hàng {order_code}, lưu trạng thái chờ đối soát", 200

            # Record payment against order
            pay = Payment(
                order_id=order.id,
                user_id=order.user_id,
                transaction_id=tx_id,
                provider="sepay",
                amount=transfer_amount,
                status=PaymentStatus.SUCCESS if transfer_amount >= order.final_amount else PaymentStatus.PARTIAL,
                payload_json=raw_json,
            )
            session.add(pay)

            # Check exact or sufficient amount
            if transfer_amount < order.final_amount:
                # Underpayment security rule: DO NOT deliver key!
                order.status = OrderStatus.PARTIAL_PAID
                order.note = (
                    f"Thanh toán thiếu: nhận {format_vnd(transfer_amount)}/{format_vnd(order.final_amount)} (tx: {tx_id})"
                )
                await session.flush()
                logger.warning(
                    f"Order #{order.order_code} underpaid: {transfer_amount} < {order.final_amount}. Marked PARTIAL_PAID."
                )

                if bot:
                    try:
                        warn_msg = (
                            f"⚠️ <b>CẢNH BÁO THANH TOÁN THIẾU TIỀN!</b>\n\n"
                            f"Đơn hàng: <code>#{order.order_code}</code>\n"
                            f"Số tiền cần thanh toán: <b>{format_vnd(order.final_amount)}</b>\n"
                            f"Số tiền nhận được: <b>{format_vnd(transfer_amount)}</b>\n\n"
                            f"Hệ thống không thể tự động giao key. Vui lòng bấm <b>🎧 Hỗ trợ</b> để nhân viên xử lý."
                        )
                        await bot.send_message(chat_id=order.telegram_id, text=warn_msg, parse_mode="HTML")
                    except Exception as e:
                        logger.warning(f"Could not alert underpaid user: {e}")

                return True, "Thanh toán thiếu tiền, đã chuyển trạng thái chờ xử lý", 200

            # Sufficient amount: Complete order & deliver keys
            order.status = OrderStatus.PAID
            await session.flush()

            success, msg, keys = await OrderService.complete_order(session, order.id, bot=bot)
            return True, f"Xử lý đơn #{order.order_code}: {msg}", 200

        # 3. Case B: Check if content matches Wallet Deposit (NAP...)
        deposit_match = parse_deposit_code_from_content(content)
        if deposit_match:
            telegram_id, dep_code = deposit_match
            user = await UserService.get_by_telegram_id(session, telegram_id)
            if not user:
                logger.warning(f"Deposit target Telegram ID {telegram_id} not found in DB.")
                pay = Payment(
                    transaction_id=tx_id,
                    provider="sepay",
                    amount=transfer_amount,
                    status=PaymentStatus.PENDING,
                    payload_json=raw_json,
                )
                session.add(pay)
                await session.flush()
                return True, f"Telegram ID {telegram_id} không tồn tại, đã lưu chờ tra soát", 200

            # Credit user balance safely
            tx = await UserService.adjust_balance(
                session=session,
                user_id=user.id,
                amount=transfer_amount,
                tx_type=WalletTxType.DEPOSIT,
                reference_code=tx_id,
                description=f"Nạp tiền qua chuyển khoản SePay (Nội dung: {dep_code})",
            )

            # Record payment
            pay = Payment(
                user_id=user.id,
                transaction_id=tx_id,
                provider="sepay",
                amount=transfer_amount,
                status=PaymentStatus.SUCCESS,
                payload_json=raw_json,
            )
            session.add(pay)
            await session.flush()

            # Notify user via bot
            if bot:
                try:
                    dep_msg = (
                        f"💰 <b>NẠP TIỀN VÀO VÍ THÀNH CÔNG!</b>\n\n"
                        f"• Số tiền nạp: <b>+{format_vnd(transfer_amount)}</b>\n"
                        f"• Số dư mới: <b>{format_vnd(tx.balance_after)}</b>\n"
                        f"• Mã giao dịch: <code>{tx_id}</code>\n\n"
                        f"Bây giờ bạn có thể dùng số dư để mua key tự động với tốc độ tức thì!"
                    )
                    await bot.send_message(chat_id=user.telegram_id, text=dep_msg, parse_mode="HTML")
                except Exception as e:
                    logger.warning(f"Could not notify deposit to user {user.telegram_id}: {e}")

            return True, f"Nạp thành công {format_vnd(transfer_amount)} cho Telegram ID {telegram_id}", 200

        # 4. Unknown transfer content
        logger.info(f"Unmatched bank transfer received: tx_id={tx_id}, content='{content}'")
        pay = Payment(
            transaction_id=tx_id,
            provider="sepay",
            amount=transfer_amount,
            status=PaymentStatus.PENDING,
            payload_json=raw_json,
        )
        session.add(pay)
        await session.flush()
        return True, "Nội dung chuyển khoản không khớp đơn hàng hoặc nạp tiền", 200
