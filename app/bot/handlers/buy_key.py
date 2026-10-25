from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, BufferedInputFile
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from app.config.settings import settings
from app.database.models import User, Order, OrderStatus
from app.services.product_service import ProductService
from app.services.order_service import OrderService
from app.services.setting_service import SettingService
from app.payments.sepay import SePayGateway
from app.bot.keyboards.product_kb import (
    get_product_list_keyboard,
    get_order_payment_qr_keyboard,
)
from app.bot.keyboards.main_menu import get_back_to_main_keyboard
from app.bot.handlers.states import OrderStates
from app.utils.helpers import format_vnd
from app.utils.logger import logger

router = Router(name="buy_key_router")


@router.callback_query(F.data == "menu:buy_key")
async def show_product_catalog(callback: CallbackQuery, session: AsyncSession):
    """Display product catalog - 1 tap directly to QR payment"""
    products = await ProductService.list_active_products(session)
    if not products:
        await callback.message.edit_text(
            "🛒 Hiện tại chưa có sản phẩm nào được mở bán. Vui lòng quay lại sau!",
            reply_markup=get_back_to_main_keyboard(),
        )
        await callback.answer()
        return

    text = (
        "🛒 <b>CHỌN GÓI BẢN QUYỀN PHẦN MỀM SHARK COMPANY</b>\n\n"
        "💡 <i>Chạm vào gói bạn muốn mua bên dưới để nhận mã QR thanh toán và nhận key tự động:</i>"
    )

    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(
            text,
            reply_markup=get_product_list_keyboard(products),
            parse_mode="HTML"
        )
    else:
        await callback.message.edit_text(
            text,
            reply_markup=get_product_list_keyboard(products),
            parse_mode="HTML"
        )
    await callback.answer()


async def render_order_qr_screen(message_target, session: AsyncSession, order: Order, user: User):
    """Render VietQR bank transfer details for order with automatic QR photo"""
    product = await ProductService.get_by_id(session, order.product_id)
    product_name = product.name if product else "Sản phẩm SHARK COMPANY"
    duration = f"({product.duration_days} ngày)" if product else ""
    bank_info = await SettingService.get_bank_info(session)

    discount_line = ""
    if order.discount_amount > 0:
        discount_line = f"• <b>Giảm giá voucher:</b> -{format_vnd(order.discount_amount)}\n"

    text = (
        f"🏦 <b>THANH TOÁN: {product_name.upper()} {duration}</b>\n\n"
        f"• <b>Số tiền cần chuyển:</b> <b>{format_vnd(order.final_amount)}</b>\n"
        f"{discount_line}"
        f"• <b>Ngân hàng:</b> <b>{bank_info['bank_name']}</b>\n"
        f"• <b>Số tài khoản:</b> <code>{bank_info['bank_account']}</code>\n"
        f"• <b>Tên chủ tài khoản:</b> <b>{bank_info['account_name']}</b>\n"
        f"• <b>Nội dung chuyển khoản:</b> <code>{order.order_code}</code>\n\n"
        f"⚡ <i>Quét mã QR ở trên hoặc chuyển khoản chính xác nội dung <code>{order.order_code}</code>. Sau 3-10 giây hệ thống sẽ tự động nhả key cho bạn!</i>"
    )

    png_bytes = await SePayGateway.get_vietqr_image_bytes(
        amount=order.final_amount,
        content=order.order_code,
        bank_name=bank_info["bank_name"],
        account_number=bank_info["bank_account"],
        account_name=bank_info["account_name"],
    )

    keyboard = get_order_payment_qr_keyboard(
        order_id=order.id,
        has_voucher=(order.discount_amount > 0),
    )

    if png_bytes:
        try:
            if hasattr(message_target, "delete"):
                try:
                    await message_target.delete()
                except Exception:
                    pass
            await message_target.answer_photo(
                photo=BufferedInputFile(png_bytes, filename="vietqr.png"),
                caption=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            return
        except Exception as e:
            logger.warning(f"Failed to send order QR photo: {e}")

    # Fallback to text message if photo conversion fails
    qr_url = SePayGateway.generate_vietqr_url(
        amount=order.final_amount,
        content=order.order_code,
        bank_name=bank_info["bank_name"],
        account_number=bank_info["bank_account"],
        account_name=bank_info["account_name"],
    )

    if hasattr(message_target, "edit_text"):
        try:
            await message_target.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            return
        except Exception:
            pass

    await message_target.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data.startswith("prod:buy:") | F.data.startswith("prod:view:") | F.data.startswith("order:checkout:"))
async def handle_buy_product(callback: CallbackQuery, session: AsyncSession, user: User):
    """Instant checkout: tap product -> instantly create order and show QR!"""
    product_id = int(callback.data.split(":")[2])

    try:
        order = await OrderService.create_order(
            session=session,
            user_id=user.id,
            telegram_id=user.telegram_id,
            product_id=product_id,
            quantity=1,
        )
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return

    await render_order_qr_screen(callback.message, session, order, user)
    await callback.answer()


@router.callback_query(F.data.startswith("pay:sepay:"))
async def pay_via_sepay_bank(callback: CallbackQuery, session: AsyncSession, user: User):
    """Show bank transfer instructions and QR code via SePay (fallback handler)"""
    order_id = int(callback.data.split(":")[2])
    order = await OrderService.get_by_id(session, order_id)
    if not order or order.status != OrderStatus.PENDING:
        await callback.answer("Đơn hàng không tồn tại hoặc đã hết hạn.", show_alert=True)
        return
    await render_order_qr_screen(callback.message, session, order, user)
    await callback.answer()


@router.callback_query(F.data.startswith("pay:wallet:"))
async def pay_via_wallet(callback: CallbackQuery, session: AsyncSession, user: User):
    """Pay using internal wallet balance"""
    order_id = int(callback.data.split(":")[2])
    bot = callback.bot

    success, msg, keys = await OrderService.pay_with_balance(
        session=session,
        order_id=order_id,
        bot=bot,
    )

    if not success:
        await callback.answer(msg, show_alert=True)
        return

    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.answer("Thanh toán thành công! Key đã được gửi.", show_alert=True)
    await callback.message.answer(
        "🎉 <b>GIAO DỊCH THÀNH CÔNG!</b>\n\n"
        "Key bản quyền phần mềm đã được gửi vào hộp thư tin nhắn của bạn.\n"
        "Bạn cũng có thể xem lại trong mục <b>📦 Key của tôi</b>.",
        reply_markup=get_back_to_main_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("order:check_status:"))
async def check_order_status(callback: CallbackQuery, session: AsyncSession):
    """Check if payment has arrived"""
    order_id = int(callback.data.split(":")[2])
    order = await OrderService.get_by_id(session, order_id)

    if not order:
        await callback.answer("Đơn hàng không tồn tại.", show_alert=True)
        return

    if order.status == OrderStatus.COMPLETED:
        await callback.answer("✅ Đơn hàng đã thanh toán thành công! Vui lòng kiểm tra tin nhắn nhận key.", show_alert=True)
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(
            "🎉 <b>ĐƠN HÀNG ĐÃ THANH TOÁN THÀNH CÔNG!</b>\n\n"
            "Key đã được gửi trong tin nhắn riêng. Bấm 'Key của tôi' để xem lại.",
            reply_markup=get_back_to_main_keyboard(),
            parse_mode="HTML"
        )
    elif order.status == OrderStatus.PARTIAL_PAID:
        await callback.answer("⚠️ Thanh toán thiếu tiền! Vui lòng liên hệ hỗ trợ.", show_alert=True)
    else:
        await callback.answer("⏳ Hệ thống chưa nhận được tiền hoặc ngân hàng đang xử lý. Vui lòng thử lại sau vài giây!", show_alert=True)


@router.callback_query(F.data.startswith("order:change_pkg:"))
async def change_package(callback: CallbackQuery, session: AsyncSession):
    """Cancel current order and go back to product list to pick another package"""
    order_id = int(callback.data.split(":")[2])
    order = await OrderService.get_by_id(session, order_id)
    if order and order.status == OrderStatus.PENDING:
        order.status = OrderStatus.CANCELLED
        await session.flush()

    try:
        await callback.message.delete()
    except Exception:
        pass

    products = await ProductService.list_active_products(session)
    text = (
        "🛒 <b>CHỌN GÓI BẢN QUYỀN PHẦN MỀM SHARK COMPANY</b>\n\n"
        "💡 <i>Chạm vào gói bạn muốn mua bên dưới để nhận mã QR thanh toán và nhận key tự động:</i>"
    )
    await callback.message.answer(
        text,
        reply_markup=get_product_list_keyboard(products),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("order:cancel:"))
async def cancel_order(callback: CallbackQuery, session: AsyncSession):
    """Cancel a pending order"""
    order_id = int(callback.data.split(":")[2])
    order = await OrderService.get_by_id(session, order_id)
    if order and order.status == OrderStatus.PENDING:
        order.status = OrderStatus.CANCELLED
        await session.flush()
        await callback.answer("Đã hủy đơn hàng.", show_alert=True)
    else:
        await callback.answer("Không thể hủy đơn hàng này.", show_alert=True)

    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer(
        "❌ <b>Đơn hàng đã được hủy.</b>",
        reply_markup=get_back_to_main_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("order:voucher:"))
async def prompt_voucher_code(callback: CallbackQuery, state: FSMContext):
    """Prompt user to enter discount code for order"""
    order_id = int(callback.data.split(":")[2])
    await state.update_data(order_id=order_id)
    await state.set_state(OrderStates.waiting_for_discount_code)
    await callback.message.answer(
        "🏷️ <b>Nhập mã giảm giá:</b>\n\n"
        "Vui lòng gửi mã voucher của bạn vào tin nhắn:",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(OrderStates.waiting_for_discount_code)
async def process_voucher_input(message: Message, state: FSMContext, session: AsyncSession, user: User):
    """Process user submitted voucher code and instantly re-render discounted QR"""
    data = await state.get_data()
    order_id = data.get("order_id")
    code_text = message.text.strip() if message.text else ""

    await state.clear()

    order = await OrderService.get_by_id(session, order_id)
    if not order or order.status != OrderStatus.PENDING:
        await message.answer("Đơn hàng không tồn tại hoặc đã hết hạn.", reply_markup=get_back_to_main_keyboard())
        return

    # Check voucher
    from app.services.discount_service import DiscountService
    is_valid, msg, discount_obj, disc_val = await DiscountService.validate_code(
        session=session,
        code_str=code_text,
        product_id=order.product_id,
        order_amount=order.original_amount,
    )

    if not is_valid:
        await message.answer(f"❌ {msg}\n\nVui lòng thử lại mã khác hoặc thanh toán theo giá gốc ở trên.")
        return

    # Apply discount to order
    order.discount_code_id = discount_obj.id
    order.discount_amount = disc_val
    order.final_amount = max(0, order.original_amount - disc_val)

    await DiscountService.redeem_code(
        session=session,
        discount_id=discount_obj.id,
        order_id=order.id,
        user_id=user.id,
        discount_amount=disc_val,
    )
    await session.flush()

    await message.answer(
        f"🎉 <b>Áp dụng mã '{code_text.upper()}' thành công!</b>\n"
        f"Bạn được giảm: <b>-{format_vnd(disc_val)}</b>\n"
        f"Đang tạo mã QR thanh toán mới...",
        parse_mode="HTML"
    )

    # Re-render QR screen with the discounted amount
    await render_order_qr_screen(message, session, order, user)
