from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import User
from app.services.affiliate_service import AffiliateService
from app.bot.keyboards.main_menu import get_back_to_main_keyboard
from app.utils.helpers import format_vnd

router = Router(name="affiliate_router")


@router.callback_query(F.data == "menu:affiliate")
async def show_affiliate_dashboard(callback: CallbackQuery, session: AsyncSession, user: User):
    """Show affiliate link, commission rate, and earnings"""
    aff = await AffiliateService.get_or_create_affiliate(session, user.id)
    bot_info = await callback.bot.get_me()
    bot_username = bot_info.username or "mtk_key_bot"

    ref_link = f"https://t.me/{bot_username}?start={aff.referral_code}"

    text = (
        f"👥 <b>CHƯƠNG TRÌNH CỘNG TÁC VIÊN (AFFILIATE)</b>\n\n"
        f"Kiếm thu nhập thụ động hấp dẫn khi giới thiệu bạn bè mua key tại SHARK COMPANY!\n\n"
        f"🔗 <b>Link giới thiệu của bạn:</b>\n"
        f"<code>{ref_link}</code>\n"
        f"<i>(Chạm vào link để sao chép và gửi cho bạn bè)</i>\n\n"
        f"📊 <b>Thống kê hoa hồng:</b>\n"
        f"• Tỷ lệ hoa hồng: <b>{aff.commission_rate}%</b> / mỗi đơn hàng thành công\n"
        f"• Tổng thu nhập đã nhận: <b>{format_vnd(aff.total_earnings)}</b>\n"
        f"• Số dư hoa hồng tích lũy: <b>{format_vnd(aff.pending_balance)}</b>\n\n"
        f"💡 <i>Hoa hồng được tự động cộng trực tiếp vào ví số dư của bạn ngay khi người được giới thiệu thanh toán đơn hàng thành công!</i>"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_back_to_main_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()
