from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.config.settings import settings


def get_main_menu_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Main menu inline keyboard - streamlined for direct QR purchasing"""
    buttons = [
        [
            InlineKeyboardButton(text="🛒 Mua key (Quét VietQR tự động)", callback_data="menu:buy_key"),
        ],
        [
            InlineKeyboardButton(text="📦 Key của tôi", callback_data="menu:my_keys:1"),
            InlineKeyboardButton(text="🧾 Lịch sử đơn hàng", callback_data="menu:transactions"),
        ],
        [
            InlineKeyboardButton(text="🎁 Mã giảm giá", callback_data="menu:discount"),
            InlineKeyboardButton(text="👥 Cộng tác viên", callback_data="menu:affiliate"),
        ],
        [
            InlineKeyboardButton(text="💬 Hỗ trợ Admin (@sharkklee)", url=f"https://t.me/{settings.SUPPORT_TELEGRAM_USERNAME}"),
            InlineKeyboardButton(text="📜 Điều khoản", callback_data="menu:terms"),
        ],
    ]

    if is_admin:
        buttons.insert(0, [
            InlineKeyboardButton(text="👑 Quản trị Admin", callback_data="admin:menu"),
            InlineKeyboardButton(text="📖 Sổ tay lệnh Admin", callback_data="admin:cheat_sheet"),
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_back_to_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Quay lại Menu chính", callback_data="menu:home")]
        ]
    )
