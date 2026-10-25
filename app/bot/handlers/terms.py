from aiogram import Router, F
from aiogram.types import CallbackQuery
from app.bot.keyboards.main_menu import get_back_to_main_keyboard

router = Router(name="terms_router")


@router.callback_query(F.data == "menu:terms")
async def show_terms_of_service(callback: CallbackQuery):
    """Display MTK Terms of Service and Warranty Policy"""
    text = (
        "📜 <b>ĐIỀU KHOẢN DỊCH VỤ & CHÍNH SÁCH BẢO HÀNH SHARK COMPANY</b>\n\n"
        "<b>1. Quy định giao nhận key:</b>\n"
        "• Hệ thống giao key tự động 100% qua Telegram ngay sau khi nhận được thanh toán hợp lệ.\n"
        "• Khách hàng chịu trách nhiệm bảo mật key cá nhân sau khi nhận.\n\n"
        "<b>2. Chính sách bảo hành:</b>\n"
        "• Cam kết 1 đổi 1 trong suốt thời gian bảo hành nếu key gặp lỗi kích hoạt từ hệ thống.\n"
        "• Không bảo hành trong trường hợp chia sẻ key cho nhiều thiết bị vượt quá số lượng cho phép của phần mềm hoặc vi phạm điều khoản của nhà phát triển.\n\n"
        "<b>3. Chính sách hoàn tiền:</b>\n"
        "• Hoàn 100% tiền vào số dư ví nếu kho hết key hoặc hệ thống lỗi không thể cung cấp bản quyền trong vòng 24 giờ.\n\n"
        "<b>4. Hỗ trợ khách hàng:</b>\n"
        "• Đội ngũ kỹ thuật hỗ trợ trực tuyến 24/7 qua mục <b>🎧 Hỗ trợ</b>."
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_back_to_main_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()
