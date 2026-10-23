from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import User
from app.services.key_service import KeyService
from app.services.product_service import ProductService
from app.bot.keyboards.main_menu import get_back_to_main_keyboard

router = Router(name="my_keys_router")


@router.callback_query(F.data.startswith("menu:my_keys:"))
async def view_my_keys(callback: CallbackQuery, session: AsyncSession, user: User):
    """View keys owned by current user with pagination"""
    parts = callback.data.split(":")
    page = int(parts[2]) if len(parts) > 2 else 1
    limit = 5

    keys, total = await KeyService.get_user_keys(
        session=session,
        buyer_telegram_id=user.telegram_id,
        page=page,
        limit=limit,
    )

    if total == 0:
        await callback.message.edit_text(
            "📦 <b>BẠN CHƯA CÓ KEY NÀO</b>\n\n"
            "Bạn chưa mua sản phẩm nào trên hệ thống hoặc các đơn hàng trước đó chưa thanh toán.\n"
            "Hãy bấm <b>🛒 Mua key</b> để trải nghiệm dịch vụ phân phối tự động nhé!",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🛒 Mua key ngay", callback_data="menu:buy_key")],
                    [InlineKeyboardButton(text="🏠 Menu chính", callback_data="menu:home")],
                ]
            ),
            parse_mode="HTML"
        )
        await callback.answer()
        return

    total_pages = (total + limit - 1) // limit

    lines = [
        f"📦 <b>KHO KEY CỦA BẠN (Trang {page}/{total_pages} - Tổng: {total} key)</b>\n",
        "<i>(Chạm vào mã key để sao chép nhanh vào bộ nhớ tạm)</i>\n",
    ]

    for idx, key in enumerate(keys, 1):
        product = await ProductService.get_by_id(session, key.product_id)
        prod_name = product.name if product else "Phần mềm MTK"
        deliv_date = key.delivered_at.strftime("%d/%m/%Y %H:%M") if key.delivered_at else "N/A"
        status_tag = "✅ Còn hạn" if key.status.value == "SOLD" else f"⚠️ {key.status.value}"

        lines.append(
            f"<b>{idx + (page - 1) * limit}. {prod_name}</b>\n"
            f"🔑 Mã key: <code>{key.key_code}</code>\n"
            f"📅 Ngày nhận: {deliv_date} | Trạng thái: {status_tag}\n"
        )

    # Navigation buttons
    nav_buttons = []
    if page > 1:
        nav_buttons.append(
            InlineKeyboardButton(text="⬅️ Trang trước", callback_data=f"menu:my_keys:{page - 1}")
        )
    if page < total_pages:
        nav_buttons.append(
            InlineKeyboardButton(text="Trang sau ➡️", callback_data=f"menu:my_keys:{page + 1}")
        )

    keyboard_rows = []
    if nav_buttons:
        keyboard_rows.append(nav_buttons)

    keyboard_rows.append([
        InlineKeyboardButton(text="🎧 Báo lỗi key / Hỗ trợ", callback_data="menu:support"),
        InlineKeyboardButton(text="🏠 Menu chính", callback_data="menu:home"),
    ])

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode="HTML"
    )
    await callback.answer()
