from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.utils.helpers import format_vnd


def get_deposit_amounts_keyboard() -> InlineKeyboardMarkup:
    """Preset deposit amounts"""
    rows = [
        [
            InlineKeyboardButton(text="20.000 đ", callback_data="deposit:amount:20000"),
            InlineKeyboardButton(text="50.000 đ", callback_data="deposit:amount:50000"),
        ],
        [
            InlineKeyboardButton(text="100.000 đ", callback_data="deposit:amount:100000"),
            InlineKeyboardButton(text="200.000 đ", callback_data="deposit:amount:200000"),
        ],
        [
            InlineKeyboardButton(text="500.000 đ", callback_data="deposit:amount:500000"),
            InlineKeyboardButton(text="✏️ Số tiền tùy chọn", callback_data="deposit:amount:custom"),
        ],
        [
            InlineKeyboardButton(text="🔙 Quay lại Menu chính", callback_data="menu:home"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_deposit_qr_keyboard(qr_url: str = "") -> InlineKeyboardMarkup:
    buttons = []
    if qr_url:
        buttons.append([InlineKeyboardButton(text="🔍 Mở link VietQR", url=qr_url)])
    buttons.append([InlineKeyboardButton(text="🔄 Kiểm tra số dư", callback_data="deposit:refresh")])
    buttons.append([InlineKeyboardButton(text="🏠 Menu chính", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
