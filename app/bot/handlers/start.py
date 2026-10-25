from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from app.config.settings import settings
from app.database.models import User
from app.bot.keyboards.main_menu import get_main_menu_keyboard
from app.utils.helpers import format_vnd

router = Router(name="start_router")


def is_user_admin(telegram_id: int) -> bool:
    return telegram_id == settings.SUPER_ADMIN_TELEGRAM_ID


def build_welcome_text(user: User) -> str:
    user_name = user.full_name or user.username or "Khách hàng"
    return (
        f"⚡ <b>CHÀO MỪNG ĐẾN VỚI SHARK COMPANY</b> ⚡\n"
        f"<i>Hệ thống phân phối bản quyền phần mềm tự động 24/7</i>\n\n"
        f"👤 <b>Tài khoản:</b> {user_name}\n"
        f"🆔 <b>Telegram ID:</b> <code>{user.telegram_id}</code>\n\n"
        f"🚀 <b>Cam kết từ SHARK COMPANY:</b>\n"
        f"• Key chính hãng 100%, bảo hành trọn đời gói mua.\n"
        f"• Mua quét QR tự động nhả key ngay sau 3-10 giây.\n"
        f"• Hỗ trợ kỹ thuật và kích hoạt nhanh chóng.\n\n"
        f"👉 <i>Vui lòng chọn chức năng bên dưới để tiếp tục:</i>"
    )


@router.message(CommandStart())
async def handle_start_command(message: Message, user: User):
    """Handle /start command"""
    text = build_welcome_text(user)
    is_adm = is_user_admin(user.telegram_id)
    await message.answer(text, reply_markup=get_main_menu_keyboard(is_admin=is_adm), parse_mode="HTML")


@router.callback_query(F.data == "menu:home")
async def handle_menu_home_callback(callback: CallbackQuery, user: User):
    """Return to main menu"""
    text = build_welcome_text(user)
    is_adm = is_user_admin(user.telegram_id)
    if callback.message.photo:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(
            text,
            reply_markup=get_main_menu_keyboard(is_admin=is_adm),
            parse_mode="HTML"
        )
    else:
        try:
            await callback.message.edit_text(
                text,
                reply_markup=get_main_menu_keyboard(is_admin=is_adm),
                parse_mode="HTML"
            )
        except Exception:
            await callback.message.answer(
                text,
                reply_markup=get_main_menu_keyboard(is_admin=is_adm),
                parse_mode="HTML"
            )
    await callback.answer()
