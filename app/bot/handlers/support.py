from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from app.config.settings import settings
from app.database.models import User
from app.services.ticket_service import TicketService
from app.bot.handlers.states import TicketStates
from app.bot.keyboards.main_menu import get_back_to_main_keyboard
from app.utils.logger import logger

router = Router(name="support_router")


@router.callback_query(F.data == "menu:support")
async def show_support_menu(callback: CallbackQuery):
    """Show support options"""
    text = (
        "🎧 <b>TRUNG TÂM HỖ TRỢ KHÁCH HÀNG SHARK COMPANY</b>\n\n"
        "Đội ngũ kỹ thuật SHARK COMPANY luôn sẵn sàng hỗ trợ bạn 24/7:\n\n"
        "• Bảo hành đổi key mới nếu lỗi do nhà sản xuất.\n"
        "• Hướng dẫn cài đặt và kích hoạt bản quyền từ A - Z.\n"
        "• Tra soát thanh toán bị sai nội dung hoặc thiếu tiền.\n\n"
        f"👤 <b>Admin hỗ trợ:</b> @{settings.SUPPORT_TELEGRAM_USERNAME} (ID: <code>{settings.SUPER_ADMIN_TELEGRAM_ID}</code>)\n\n"
        "<i>Vui lòng bấm nút bên dưới để nhắn tin trực tiếp với Admin:</i>"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Chat trực tiếp Admin (@sharkklee)", url=f"https://t.me/{settings.SUPPORT_TELEGRAM_USERNAME}")],
            [InlineKeyboardButton(text="✍️ Gửi yêu cầu hỗ trợ qua Bot", callback_data="ticket:new")],
            [InlineKeyboardButton(text="🔙 Quay lại Menu chính", callback_data="menu:home")],
        ]
    )

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "ticket:new")
async def start_new_ticket(callback: CallbackQuery, state: FSMContext):
    """Prompt user to describe support issue"""
    await state.set_state(TicketStates.waiting_for_message)
    await callback.message.answer(
        "✍️ <b>GỬI YÊU CẦU HỖ TRỢ</b>\n\n"
        "Vui lòng nhập nội dung chi tiết vấn đề bạn đang gặp (Mã đơn hàng, mã key bị lỗi, hoặc thắc mắc):\n"
        "<i>Đội ngũ kỹ thuật viên sẽ phản hồi bạn sớm nhất qua bot này.</i>",
        reply_markup=get_back_to_main_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(TicketStates.waiting_for_message)
async def submit_ticket_message(message: Message, state: FSMContext, session: AsyncSession, user: User):
    """Save support ticket to database"""
    await state.clear()
    msg_text = message.text.strip() if message.text else "Không có nội dung"

    ticket = await TicketService.create_ticket(
        session=session,
        user_id=user.id,
        telegram_id=user.telegram_id,
        subject="Yêu cầu hỗ trợ khách hàng",
        message=msg_text,
    )

    # Notify Super Admin if configured
    if settings.SUPER_ADMIN_TELEGRAM_ID and settings.SUPER_ADMIN_TELEGRAM_ID > 0:
        try:
            bot = message.bot
            admin_msg = (
                f"🎫 <b>[YÊU CẦU HỖ TRỢ MỚI #{ticket.ticket_code}]</b>\n\n"
                f"• Khách hàng: Telegram ID <code>{user.telegram_id}</code> (@{user.username or 'N/A'})\n"
                f"• Nội dung: <i>{msg_text}</i>\n"
            )
            await bot.send_message(chat_id=settings.SUPER_ADMIN_TELEGRAM_ID, text=admin_msg, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Could not alert admin about new ticket: {e}")

    await message.answer(
        f"✅ <b>ĐÃ GỬI YÊU CẦU HỖ TRỢ THÀNH CÔNG!</b>\n\n"
        f"Mã phiếu: <code>#{ticket.ticket_code}</code>\n"
        f"Kỹ thuật viên SHARK COMPANY đã tiếp nhận và sẽ phản hồi bạn trong thời gian sớm nhất.",
        reply_markup=get_back_to_main_keyboard(),
        parse_mode="HTML"
    )
