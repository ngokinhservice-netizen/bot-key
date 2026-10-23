from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.config.settings import settings
from app.database.models import User, Product, KeyInventory, KeyStatus, Order, OrderStatus, DiscountType
from app.services.setting_service import SettingService
from app.services.key_service import KeyService
from app.services.product_service import ProductService
from app.services.discount_service import DiscountService
from app.utils.helpers import format_vnd
from app.utils.logger import logger

router = Router(name="admin_ops_router")


def is_admin(telegram_id: int) -> bool:
    """Strict authorization: ONLY the configured Super Admin Telegram ID is permitted"""
    if telegram_id == settings.SUPER_ADMIN_TELEGRAM_ID:
        return True
    logger.warning(f"Security: Unauthorized access attempt to admin function by Telegram ID {telegram_id}")
    return False


@router.message(Command("admin"))
@router.callback_query(F.data == "admin:menu")
async def handle_admin_panel_command(event, session: AsyncSession):
    """Admin quick command panel"""
    user_id = event.from_user.id
    if not is_admin(user_id):
        return

    bank_info = await SettingService.get_bank_info(session)
    products_stock = await ProductService.list_all_for_admin(session)

    stock_lines = []
    for p, stock in products_stock:
        stock_lines.append(f"• <b>{p.name}</b> (slug: <code>{p.slug}</code>): <b>{stock} key</b>")

    text = (
        "👑 <b>BẢNG QUẢN TRỊ ADMIN (TELEGRAM)</b>\n\n"
        f"🏦 <b>Tài khoản nhận tiền hiện tại:</b>\n"
        f"• Ngân hàng: <b>{bank_info['bank_name']}</b>\n"
        f"• Số tài khoản: <code>{bank_info['bank_account']}</code>\n"
        f"• Chủ tài khoản: <b>{bank_info['account_name']}</b>\n\n"
        f"📦 <b>Tồn kho 4 sản phẩm:</b>\n"
        + "\n".join(stock_lines) + "\n\n"
        f"⚡ <b>Lệnh nhanh cho Admin:</b>\n"
        f"1. <b>Đổi STK nhận tiền:</b>\n"
        f"<code>/setbank &lt;NgânHàng&gt; &lt;STK&gt; &lt;TênChủTK&gt;</code>\n"
        f"<i>Ví dụ:</i> <code>/setbank MBBank 0123456789 NGUYEN VAN A</code>\n\n"
        f"2. <b>Nạp key vào kho:</b>\n"
        f"<code>/nhapkey &lt;slug&gt; &lt;key1,key2,key3&gt;</code>\n"
        f"<i>Ví dụ:</i> <code>/nhapkey ban-ngay KEY1,KEY2,KEY3</code>\n\n"
        f"3. <b>Xem thống kê:</b> <code>/thongke</code>"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📖 Sổ tay tất cả lệnh Admin", callback_data="admin:cheat_sheet")],
            [InlineKeyboardButton(text="📊 Thống kê tồn kho", callback_data="admin:quick_stock")],
            [InlineKeyboardButton(text="🏦 Đổi STK nhận tiền", callback_data="admin:prompt_setbank")],
            [InlineKeyboardButton(text="🔑 Hướng dẫn nạp key", callback_data="admin:prompt_addkey")],
            [InlineKeyboardButton(text="🔙 Menu chính", callback_data="menu:home")],
        ]
    )

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await event.answer()
    else:
        await event.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.message(Command("lenh", "helpadmin", "sotay"))
@router.callback_query(F.data == "admin:cheat_sheet")
async def handle_cheat_sheet(event):
    """Cheat sheet / quick command reference for the Super Admin"""
    user_id = event.from_user.id
    if not is_admin(user_id):
        return

    text = (
        "📖 <b>SỔ TAY TỔNG HỢP LỆNH ADMIN (CHẠM ĐỂ COPY)</b>\n\n"
        "Chào Admin! Chạm vào dòng lệnh bất kỳ bên dưới để tự động copy:\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🏦 <b>1. CÀI ĐẶT / ĐỔI STK NHẬN TIỀN (SEPAY)</b>\n"
        "• <i>Cú pháp:</i> <code>/setbank &lt;NgânHàng&gt; &lt;STK&gt; &lt;TênChủTK&gt;</code>\n"
        "• <i>Ví dụ mẫu (chạm copy):</i>\n"
        "<code>/setbank VPBank 0342938622 LEE DANG KHOA</code>\n"
        "<code>/setbank MBBank 0342938622 LEE DANG KHOA</code>\n"
        "<i>(Đổi xong thì mã QR nạp tiền của khách sẽ tự động cập nhật STK mới)</i>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🔑 <b>2. NẠP THÊM KEY VÀO KHO (BÁN TỰ ĐỘNG)</b>\n"
        "• <i>Cú pháp:</i> <code>/nhapkey &lt;mã-sản-phẩm&gt; &lt;danh sách key&gt;</code>\n"
        "<i>(Các key cách nhau bằng dấu phẩy hoặc xuống dòng)</i>\n\n"
        "<b>Mẫu lệnh nạp cho từng gói (chạm copy):</b>\n"
        "• Gói 1: Bản ngày (347.000 đ):\n"
        "<code>/nhapkey ban-ngay KEY1, KEY2, KEY3</code>\n\n"
        "• Gói 2: Full kỳ (833.000 đ):\n"
        "<code>/nhapkey full-ky KEY1, KEY2, KEY3</code>\n\n"
        "• Gói 3: SEB kỳ (100.000 đ):\n"
        "<code>/nhapkey seb-ky KEY1, KEY2, KEY3</code>\n\n"
        "• Gói 4: SEB ngày (50.000 đ):\n"
        "<code>/nhapkey seb-ngay KEY1, KEY2, KEY3</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🏷️ <b>3. TẠO MÃ GIẢM GIÁ (VOUCHER) CHO KHÁCH</b>\n"
        "• <i>Cú pháp:</i> <code>/taoma &lt;MãCode&gt; &lt;MứcGiảm&gt; &lt;SốLượtDùng&gt;</code>\n"
        "• <i>Ví dụ giảm tiền VND (chạm copy):</i>\n"
        "<code>/taoma GIAM50K 50000 100</code>\n"
        "<code>/taoma KM20K 20000 50</code>\n"
        "• <i>Ví dụ giảm theo % (chạm copy):</i>\n"
        "<code>/taoma VIP10 10% 100</code>\n"
        "<code>/taoma SALE20 20% 50</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📊 <b>4. BÁO CÁO & THỐNG KÊ</b>\n"
        "• Xem tồn kho 4 gói & doanh thu: <code>/thongke</code>\n"
        "• Mở bảng quản trị: <code>/admin</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🌐 <b>5. WEB QUẢN TRỊ ADMIN PANEL</b>\n"
        "• Link: <code>http://localhost:8000/admin/login</code>\n"
        "• Tài khoản: <code>admin</code>\n"
        "• Mật khẩu: <code>Admin@MTK2026!</code>"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👑 Bảng quản trị Admin", callback_data="admin:menu")],
            [InlineKeyboardButton(text="🔙 Về Menu chính", callback_data="menu:home")],
        ]
    )

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await event.answer()
    else:
        await event.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.message(Command("setbank"))
async def handle_setbank_command(message: Message, session: AsyncSession, user: User):
    """Command to set bank account: /setbank MBBank 0123456789 NGUYEN VAN A"""
    if not is_admin(user.telegram_id):
        return

    text = message.text.replace("/setbank", "").strip() if message.text else ""
    parts = text.split(maxsplit=2)

    if len(parts) < 3:
        await message.answer(
            "⚠️ <b>Cú pháp chưa đúng!</b>\n\n"
            "Vui lòng nhập theo cú pháp:\n"
            "<code>/setbank &lt;TênNgânHàng&gt; &lt;SốTàiKhoản&gt; &lt;TênChủTàiKhoản&gt;</code>\n\n"
            "<i>Ví dụ:</i>\n"
            "<code>/setbank MBBank 0123456789 NGUYEN VAN A</code>",
            parse_mode="HTML"
        )
        return

    bank_name, bank_account, account_name = parts[0], parts[1], parts[2]

    await SettingService.update_bank_info(
        session=session,
        bank_name=bank_name,
        bank_account=bank_account,
        account_name=account_name,
    )
    await session.commit()

    await message.answer(
        f"✅ <b>ĐÃ CẬP NHẬT THÀNH CÔNG TÀI KHOẢN NHẬN TIỀN!</b>\n\n"
        f"• Ngân hàng: <b>{bank_name.upper()}</b>\n"
        f"• Số tài khoản: <code>{bank_account}</code>\n"
        f"• Tên chủ tài khoản: <b>{account_name.upper()}</b>\n\n"
        f"Mọi đơn hàng và mã VietQR từ bây giờ sẽ tự động hiển thị số tài khoản này cho khách chuyển khoản.",
        parse_mode="HTML"
    )


@router.message(Command("nhapkey"))
async def handle_nhapkey_command(message: Message, session: AsyncSession, user: User):
    """Command to add keys: /nhapkey ban-ngay KEY1,KEY2,KEY3"""
    if not is_admin(user.telegram_id):
        return

    text = message.text.replace("/nhapkey", "").strip() if message.text else ""
    parts = text.split(maxsplit=1)

    if len(parts) < 2:
        await message.answer(
            "⚠️ <b>Cú pháp chưa đúng!</b>\n\n"
            "Vui lòng nhập theo cú pháp:\n"
            "<code>/nhapkey &lt;slug_sản_phẩm&gt; &lt;danh sách key phân cách bằng dấu phẩy hoặc xuống dòng&gt;</code>\n\n"
            "<i>Danh sách slug:</i>\n"
            "• <code>ban-ngay</code> (Bản ngày)\n"
            "• <code>full-ky</code> (Full kỳ)\n"
            "• <code>seb-ky</code> (SEB kỳ)\n"
            "• <code>seb-ngay</code> (SEB ngày)\n\n"
            "<i>Ví dụ:</i>\n"
            "<code>/nhapkey ban-ngay KEY-DAY-001, KEY-DAY-002</code>",
            parse_mode="HTML"
        )
        return

    slug, keys_raw = parts[0].strip().lower(), parts[1]
    product = await ProductService.get_by_slug(session, slug)
    if not product:
        await message.answer(f"❌ Không tìm thấy sản phẩm có slug '<code>{slug}</code>'!", parse_mode="HTML")
        return

    # Split by commas or newlines
    raw_list = [k.strip() for k in keys_raw.replace("\n", ",").split(",") if k.strip()]
    if not raw_list:
        await message.answer("❌ Danh sách key trống.", parse_mode="HTML")
        return

    added, duplicates = await KeyService.bulk_import_keys(
        session=session,
        product_id=product.id,
        raw_keys=raw_list,
    )
    await session.commit()

    total_stock = await ProductService.get_stock_count(session, product.id)

    await message.answer(
        f"✅ <b>NẠP KEY THÀNH CÔNG!</b>\n\n"
        f"• Sản phẩm: <b>{product.name}</b>\n"
        f"• Số key vừa nạp: <b>+{added} key</b>\n"
        f"• Key trùng bị bỏ qua: <b>{duplicates} key</b>\n"
        f"• Tổng tồn kho hiện tại: <b>{total_stock} key khả dụng</b>\n\n"
        f"Khách hàng mua gói này sẽ được bot tự động nhả key ngay lập tức!",
        parse_mode="HTML"
    )


@router.message(Command("thongke"))
@router.callback_query(F.data == "admin:quick_stock")
async def handle_thongke_command(event, session: AsyncSession):
    """View quick stock status for all products"""
    user_id = event.from_user.id
    if not is_admin(user_id):
        return

    products_stock = await ProductService.list_all_for_admin(session)
    total_rev = (await session.execute(
        select(func.coalesce(func.sum(Order.final_amount), 0)).where(Order.status == OrderStatus.COMPLETED)
    )).scalar() or 0
    orders_count = (await session.execute(
        select(func.count(Order.id)).where(Order.status == OrderStatus.COMPLETED)
    )).scalar() or 0

    lines = [
        "📊 <b>BÁO CÁO NHANH KHO KEY & DOANH THU MTK</b>\n",
        f"💰 Tổng doanh thu: <b>{format_vnd(total_rev)}</b>",
        f"🧾 Đơn hoàn tất: <b>{orders_count} đơn</b>\n",
        "📦 <b>Chi tiết tồn kho:</b>"
    ]

    for p, stock in products_stock:
        status_icon = "🟢" if stock > 0 else "🔴"
        lines.append(f"{status_icon} <b>{p.name}</b> (<code>{p.slug}</code>): <b>{stock} key</b> ({format_vnd(p.price)})")

    text = "\n".join(lines)

    if isinstance(event, CallbackQuery):
        await event.message.answer(text, parse_mode="HTML")
        await event.answer()
    else:
        await event.answer(text, parse_mode="HTML")


@router.callback_query(F.data == "admin:prompt_setbank")
async def prompt_setbank(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.message.answer(
        "🏦 <b>CẬP NHẬT TÀI KHOẢN NGÂN HÀNG THỤ HƯỞNG</b>\n\n"
        "Vui lòng gửi tin nhắn theo cú pháp:\n"
        "<code>/setbank &lt;NgânHàng&gt; &lt;STK&gt; &lt;TênChủTK&gt;</code>\n\n"
        "<i>Ví dụ:</i>\n"
        "<code>/setbank MBBank 0987654321 NGUYEN VAN A</code>",
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin:prompt_addkey")
async def prompt_addkey(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.message.answer(
        "🔑 <b>NẠP THÊM KEY VÀO KHO</b>\n\n"
        "Vui lòng gửi tin nhắn theo cú pháp:\n"
        "<code>/nhapkey &lt;slug&gt; &lt;key1,key2,key3&gt;</code>\n\n"
        "<i>Các slug của 4 sản phẩm:</i>\n"
        "• <code>ban-ngay</code> (Bản ngày - 347.000 đ)\n"
        "• <code>full-ky</code> (Full kỳ - 833.000 đ)\n"
        "• <code>seb-ky</code> (SEB kỳ - 100.000 đ)\n"
        "• <code>seb-ngay</code> (SEB ngày - 50.000 đ)\n\n"
        "<i>Ví dụ:</i>\n"
        "<code>/nhapkey ban-ngay KEY-DAY-111, KEY-DAY-222</code>",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(Command("taoma"))
async def handle_create_voucher_command(message: Message, session: AsyncSession, user: User):
    """Command to create discount code: /taoma <code_name> <value> [max_uses]"""
    if not is_admin(user.telegram_id):
        return

    text = message.text.replace("/taoma", "").strip() if message.text else ""
    parts = text.split()

    if len(parts) < 2:
        await message.answer(
            "⚠️ <b>Cú pháp chưa đúng!</b>\n\n"
            "Vui lòng nhập theo cú pháp:\n"
            "<code>/taoma &lt;MãCode&gt; &lt;GiáTrịGiảm&gt; [SốLượtDùng]</code>\n\n"
            "<i>Ví dụ:</i>\n"
            "• Giảm 20.000 đ cho 100 lượt dùng: <code>/taoma GIAM20K 20000 100</code>\n"
            "• Giảm 10% cho 50 lượt dùng: <code>/taoma VIP10 10% 50</code>",
            parse_mode="HTML"
        )
        return

    code_str = parts[0].strip().upper()
    val_raw = parts[1].strip()
    max_uses = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 100

    from datetime import datetime, timedelta, timezone
    start = datetime.now(timezone.utc)
    end = start + timedelta(days=90)

    if "%" in val_raw:
        dtype = DiscountType.PERCENT
        val = int(val_raw.replace("%", "").strip())
        val_display = f"{val}%"
    else:
        dtype = DiscountType.FIXED
        val = int(val_raw.replace("k", "000").replace("K", "000").replace(".", "").replace(",", "").strip())
        val_display = format_vnd(val)

    try:
        dc = await DiscountService.create_code(
            session=session,
            code=code_str,
            discount_type=dtype,
            discount_value=val,
            max_uses=max_uses,
            start_date=start,
            end_date=end,
        )
        await session.commit()
        await message.answer(
            f"✅ <b>TẠO MÃ GIẢM GIÁ THÀNH CÔNG!</b>\n\n"
            f"• Mã voucher: <code>{dc.code}</code>\n"
            f"• Mức giảm: <b>{val_display}</b>\n"
            f"• Lượt sử dụng: <b>{dc.max_uses} lượt</b>\n"
            f"• Hạn dùng: 90 ngày\n\n"
            f"Khách hàng có thể nhập mã này tại ô 'Nhập mã giảm giá (Voucher)' khi mua key!",
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ Lỗi: {e}", parse_mode="HTML")
