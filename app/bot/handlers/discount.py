from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import User, DiscountCode
from app.bot.keyboards.main_menu import get_back_to_main_keyboard
from app.utils.helpers import format_vnd

router = Router(name="discount_router")


@router.callback_query(F.data == "menu:discount")
async def show_discount_info(callback: CallbackQuery, session: AsyncSession):
    """Show active discount codes / voucher policy"""
    # Fetch active public discount codes
    stmt = select(DiscountCode).where(DiscountCode.is_active == True).limit(5)
    codes = list((await session.execute(stmt)).scalars().all())

    lines = [
        "🎁 <b>CHƯƠNG TRÌNH KHUYẾN MÃI & MÃ GIẢM GIÁ</b>\n",
        "Hệ thống thường xuyên tung ra các mã giảm giá đặc quyền cho khách hàng SHARK COMPANY.\n",
    ]

    if codes:
        lines.append("🔥 <b>Mã đang phát hành:</b>")
        for c in codes:
            val_str = f"{c.discount_value}%" if c.discount_type.value == "PERCENT" else format_vnd(c.discount_value)
            lines.append(f"• Mã: <code>{c.code}</code> (Giảm {val_str})")
    else:
        lines.append("<i>Hiện tại chưa có mã công khai. Hãy theo dõi kênh thông báo để săn voucher nhé!</i>")

    lines.append("\n💡 <i>Mã giảm giá có thể áp dụng trực tiếp tại bước xác nhận đơn hàng khi bấm Mua key.</i>")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=get_back_to_main_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()
