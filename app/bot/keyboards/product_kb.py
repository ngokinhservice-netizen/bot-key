from typing import List, Tuple, Optional
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.database.models import Product
from app.utils.helpers import format_vnd


def get_product_list_keyboard(products_with_stock: List[Tuple[Product, int]]) -> InlineKeyboardMarkup:
    """Generate keyboard for selecting a software product - 1 tap directly to QR checkout"""
    rows = []
    for prod, stock in products_with_stock:
        duration_text = f"{prod.duration_days} ngày"
        btn_text = f"🟢 {prod.name} ({duration_text}) - {format_vnd(prod.price)}"
        rows.append([InlineKeyboardButton(text=btn_text, callback_data=f"prod:buy:{prod.id}")])

    rows.append([InlineKeyboardButton(text="🔙 Quay lại Menu chính", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_product_detail_keyboard(product_id: int, in_stock: bool) -> InlineKeyboardMarkup:
    """Detail view keyboard (kept for backward compatibility)"""
    rows = []
    if in_stock:
        rows.append([
            InlineKeyboardButton(text="⚡ Mua ngay", callback_data=f"prod:buy:{product_id}")
        ])
    else:
        rows.append([
            InlineKeyboardButton(text="⚠️ Tạm hết hàng - Báo cho Admin", callback_data="menu:support")
        ])

    rows.append([
        InlineKeyboardButton(text="🔙 Danh mục sản phẩm", callback_data="menu:buy_key"),
        InlineKeyboardButton(text="🏠 Menu chính", callback_data="menu:home"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_checkout_payment_keyboard(
    order_id: int,
    user_balance: int,
    order_amount: int,
) -> InlineKeyboardMarkup:
    """Payment method selection (kept for backward compatibility)"""
    rows = []
    rows.append([
        InlineKeyboardButton(text="🏷️ Nhập mã giảm giá (Voucher)", callback_data=f"order:voucher:{order_id}")
    ])
    rows.append([
        InlineKeyboardButton(text="🏦 Chuyển khoản VietQR (SePay tự động 24/7)", callback_data=f"pay:sepay:{order_id}")
    ])
    if user_balance >= order_amount:
        balance_text = f"💰 Thanh toán bằng Ví (Số dư: {format_vnd(user_balance)})"
        rows.append([
            InlineKeyboardButton(text=balance_text, callback_data=f"pay:wallet:{order_id}")
        ])
    rows.append([
        InlineKeyboardButton(text="❌ Hủy đơn hàng", callback_data=f"order:cancel:{order_id}"),
        InlineKeyboardButton(text="🏠 Menu chính", callback_data="menu:home"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_order_payment_qr_keyboard(
    order_id: int,
    has_voucher: bool = False,
) -> InlineKeyboardMarkup:
    """Streamlined keyboard shown under the QR code photo"""
    rows = []

    # 1. Voucher button (if not already applied)
    if not has_voucher:
        rows.append([InlineKeyboardButton(text="🏷️ Nhập mã giảm giá (Voucher)", callback_data=f"order:voucher:{order_id}")])

    # 2. Check payment status
    rows.append([InlineKeyboardButton(text="🔄 Kiểm tra thanh toán ngay", callback_data=f"order:check_status:{order_id}")])

    # 3. Direct Support to Admin Telegram
    rows.append([InlineKeyboardButton(text="💬 Nhắn Admin hỗ trợ (@sharkklee)", url="https://t.me/sharkklee")])

    # 4. Change package or cancel
    rows.append([
        InlineKeyboardButton(text="🔙 Đổi gói khác", callback_data=f"order:change_pkg:{order_id}"),
        InlineKeyboardButton(text="❌ Hủy đơn", callback_data=f"order:cancel:{order_id}"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)
