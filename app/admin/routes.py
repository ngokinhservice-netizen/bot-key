import csv
import io
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Request, Depends, Form, File, UploadFile, status, Response
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.config.settings import settings
from app.database.session import get_db
from app.database.models import (
    AdminUser,
    AdminRole,
    Product,
    KeyInventory,
    KeyStatus,
    Order,
    OrderStatus,
    User,
    DiscountCode,
    DiscountType,
    SupportTicket,
    TicketStatus,
    AuditLog,
    WalletTxType,
)
from app.admin.auth import (
    get_current_admin,
    require_roles,
    verify_password,
    create_access_token,
)
from app.services.product_service import ProductService
from app.services.key_service import KeyService
from app.services.order_service import OrderService
from app.services.user_service import UserService
from app.services.discount_service import DiscountService
from app.services.ticket_service import TicketService
from app.services.audit_service import AuditService
from app.services.setting_service import SettingService
from app.bot.bot_instance import get_bot
from app.utils.helpers import format_vnd
from app.utils.logger import logger

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/admin/templates")


# --- Auth Routes ---

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
async def login_submit(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_db),
):
    stmt = select(AdminUser).where(AdminUser.username == username.strip())
    admin = (await session.execute(stmt)).scalar_one_or_none()

    if not admin or not verify_password(password, admin.hashed_password):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Tên đăng nhập hoặc mật khẩu không chính xác!"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    if not admin.is_active:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Tài khoản của bạn đã bị vô hiệu hóa!"},
            status_code=status.HTTP_403_FORBIDDEN,
        )

    # Issue JWT token
    token = create_access_token({"sub": str(admin.id), "role": admin.role.value})
    redirect = RedirectResponse(url="/admin/dashboard", status_code=status.HTTP_302_FOUND)
    redirect.set_cookie(
        key="admin_token",
        value=token,
        httponly=True,
        max_age=settings.JWT_EXPIRE_MINUTES * 60,
        samesite="lax",
    )
    return redirect


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("admin_token")
    return response


# --- Dashboard ---

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    week_start = now - timedelta(days=7)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    # Revenue metrics (from COMPLETED orders)
    async def get_rev(since: Optional[datetime]) -> int:
        q = select(func.coalesce(func.sum(Order.final_amount), 0)).where(
            Order.status == OrderStatus.COMPLETED
        )
        if since:
            q = q.where(Order.created_at >= since)
        return (await session.execute(q)).scalar() or 0

    rev_today = await get_rev(today_start)
    rev_week = await get_rev(week_start)
    rev_month = await get_rev(month_start)
    rev_total = await get_rev(None)

    # Order counts
    async def get_order_count(stat: Optional[OrderStatus]) -> int:
        q = select(func.count(Order.id))
        if stat:
            q = q.where(Order.status == stat)
        return (await session.execute(q)).scalar() or 0

    orders_completed = await get_order_count(OrderStatus.COMPLETED)
    orders_pending = await get_order_count(OrderStatus.PENDING)

    # Total users
    total_users = (await session.execute(select(func.count(User.id)))).scalar() or 0

    # Keys in stock
    keys_available = (
        await session.execute(
            select(func.count(KeyInventory.id)).where(KeyInventory.status == KeyStatus.AVAILABLE)
        )
    ).scalar() or 0

    # Products with stock
    products_stock = await ProductService.list_all_for_admin(session)

    # Recent 5 orders
    recent_orders_stmt = select(Order).order_by(Order.id.desc()).limit(5)
    recent_orders = list((await session.execute(recent_orders_stmt)).scalars().all())
    for o in recent_orders:
        o.final_amount_formatted = format_vnd(o.final_amount)

    # Revenue chart data (last 7 days)
    labels = []
    values = []
    for i in range(6, -1, -1):
        day_date = now - timedelta(days=i)
        day_start = datetime(day_date.year, day_date.month, day_date.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        labels.append(day_start.strftime("%d/%m"))
        day_rev = (
            await session.execute(
                select(func.coalesce(func.sum(Order.final_amount), 0)).where(
                    and_(
                        Order.status == OrderStatus.COMPLETED,
                        Order.created_at >= day_start,
                        Order.created_at < day_end,
                    )
                )
            )
        ).scalar() or 0
        values.append(int(day_rev))

    stats = {
        "revenue_today": format_vnd(rev_today),
        "revenue_week": format_vnd(rev_week),
        "revenue_month": format_vnd(rev_month),
        "revenue_total": format_vnd(rev_total),
        "orders_completed": orders_completed,
        "orders_pending": orders_pending,
        "total_users": total_users,
        "keys_available": keys_available,
    }

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "admin": admin,
            "stats": stats,
            "products_stock": products_stock,
            "recent_orders": recent_orders,
            "chart_data": {"labels": labels, "values": values},
        },
    )


# --- Products Management ---

@router.get("/products", response_class=HTMLResponse)
async def products_page(
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
):
    products = await ProductService.list_all_for_admin(session)
    for p, _ in products:
        p.price_formatted = format_vnd(p.price)

    return templates.TemplateResponse(
        "products.html",
        {"request": request, "admin": admin, "products": products},
    )


@router.post("/products/create")
async def create_product_submit(
    name: str = Form(...),
    slug: str = Form(...),
    price: int = Form(...),
    duration_days: int = Form(30),
    description: str = Form(""),
    activation_guide: Optional[str] = Form(None),
    admin: AdminUser = Depends(require_roles([AdminRole.SUPER_ADMIN, AdminRole.ORDER_MANAGER])),
    session: AsyncSession = Depends(get_db),
):
    await ProductService.create_product(
        session=session,
        name=name,
        slug=slug,
        price=price,
        duration_days=duration_days,
        description=description,
        activation_guide=activation_guide,
        admin_id=admin.id,
    )
    await session.commit()
    return RedirectResponse(url="/admin/products", status_code=status.HTTP_302_FOUND)


@router.post("/products/{product_id}/toggle")
async def toggle_product_submit(
    product_id: int,
    admin: AdminUser = Depends(require_roles([AdminRole.SUPER_ADMIN, AdminRole.ORDER_MANAGER])),
    session: AsyncSession = Depends(get_db),
):
    product = await ProductService.get_by_id(session, product_id)
    if product:
        await ProductService.update_product(
            session=session,
            product_id=product_id,
            is_active=not product.is_active,
            admin_id=admin.id,
        )
        await session.commit()
    return RedirectResponse(url="/admin/products", status_code=status.HTTP_302_FOUND)


# --- Key Inventory Management ---

@router.get("/inventory", response_class=HTMLResponse)
async def inventory_page(
    request: Request,
    product_id: Optional[int] = None,
    status_str: Optional[str] = None,
    search: Optional[str] = None,
    admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
):
    stat_enum = None
    if status_str and status_str in KeyStatus.__members__:
        stat_enum = KeyStatus[status_str]

    keys, total = await KeyService.list_keys_for_admin(
        session=session,
        product_id=product_id,
        status=stat_enum,
        search=search,
        page=1,
        limit=100,
    )

    all_products = [p for p, _ in await ProductService.list_all_for_admin(session)]

    return templates.TemplateResponse(
        "inventory.html",
        {
            "request": request,
            "admin": admin,
            "keys": keys,
            "total_keys": total,
            "all_products": all_products,
            "selected_product_id": product_id,
            "selected_status": status_str,
            "search_query": search,
            "message": None,
        },
    )


@router.post("/inventory/import")
async def import_keys_submit(
    request: Request,
    product_id: int = Form(...),
    raw_keys: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    admin: AdminUser = Depends(require_roles([AdminRole.SUPER_ADMIN, AdminRole.ORDER_MANAGER])),
    session: AsyncSession = Depends(get_db),
):
    key_lines = []
    if raw_keys:
        key_lines.extend(raw_keys.splitlines())

    if file and file.filename:
        content = await file.read()
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("latin-1")
        key_lines.extend(text.splitlines())

    added, duplicates = await KeyService.bulk_import_keys(
        session=session,
        product_id=product_id,
        raw_keys=key_lines,
        admin_id=admin.id,
    )
    await session.commit()

    return RedirectResponse(
        url=f"/admin/inventory?product_id={product_id}",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/inventory/{key_id}/revoke")
async def revoke_key_submit(
    key_id: int,
    admin: AdminUser = Depends(require_roles([AdminRole.SUPER_ADMIN, AdminRole.ORDER_MANAGER])),
    session: AsyncSession = Depends(get_db),
):
    await KeyService.revoke_key(
        session=session,
        key_id=key_id,
        reason="Thu hồi bởi Admin",
        admin_id=admin.id,
    )
    await session.commit()
    return RedirectResponse(url="/admin/inventory", status_code=status.HTTP_302_FOUND)


# --- Orders Management ---

@router.get("/orders", response_class=HTMLResponse)
async def orders_page(
    request: Request,
    status_str: Optional[str] = None,
    search: Optional[str] = None,
    admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
):
    stat_enum = None
    if status_str and status_str in OrderStatus.__members__:
        stat_enum = OrderStatus[status_str]

    orders, total = await OrderService.list_orders_for_admin(
        session=session,
        status=stat_enum,
        search=search,
        page=1,
        limit=100,
    )

    for o in orders:
        o.final_amount_formatted = format_vnd(o.final_amount)
        o.discount_amount_formatted = format_vnd(o.discount_amount)

    return templates.TemplateResponse(
        "orders.html",
        {
            "request": request,
            "admin": admin,
            "orders": orders,
            "total_orders": total,
            "selected_status": status_str,
            "search_query": search,
        },
    )


@router.post("/orders/{order_id}/refund")
async def refund_order_submit(
    order_id: int,
    reason: str = Form("Hoàn tiền theo yêu cầu khách hàng"),
    admin: AdminUser = Depends(require_roles([AdminRole.SUPER_ADMIN, AdminRole.ORDER_MANAGER])),
    session: AsyncSession = Depends(get_db),
):
    bot = get_bot()
    await OrderService.refund_order(
        session=session,
        order_id=order_id,
        admin_id=admin.id,
        reason=reason,
        refund_to_wallet=True,
        bot=bot,
    )
    await session.commit()
    return RedirectResponse(url="/admin/orders", status_code=status.HTTP_302_FOUND)


# --- Users & Balance Management ---

@router.get("/users", response_class=HTMLResponse)
async def users_page(
    request: Request,
    search: Optional[str] = None,
    admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
):
    users, total = await UserService.list_users(session=session, page=1, limit=100, search=search)
    for u in users:
        u.balance_formatted = format_vnd(u.balance)

    return templates.TemplateResponse(
        "users.html",
        {
            "request": request,
            "admin": admin,
            "users": users,
            "total_users": total,
            "search_query": search,
        },
    )


@router.post("/users/{user_id}/toggle-ban")
async def toggle_ban_submit(
    user_id: int,
    admin: AdminUser = Depends(require_roles([AdminRole.SUPER_ADMIN])),
    session: AsyncSession = Depends(get_db),
):
    user = await UserService.get_by_id(session, user_id)
    if user:
        await UserService.set_ban_status(
            session=session,
            user_id=user_id,
            is_banned=not user.is_banned,
            admin_id=admin.id,
            reason="Thao tác từ Admin Dashboard",
        )
        await session.commit()
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)


@router.post("/users/adjust-balance")
async def adjust_balance_submit(
    user_id: int = Form(...),
    amount: int = Form(...),
    reason: str = Form(...),
    admin: AdminUser = Depends(require_roles([AdminRole.SUPER_ADMIN])),
    session: AsyncSession = Depends(get_db),
):
    """
    Adjust user balance. Strictly restricted to SUPER_ADMIN per specification.
    """
    await UserService.adjust_balance(
        session=session,
        user_id=user_id,
        amount=amount,
        tx_type=WalletTxType.ADMIN_ADJUST,
        reference_code=f"MANUAL_ADJUST_{datetime.now().strftime('%y%m%d%H%M%S')}",
        description=reason,
        admin_id=admin.id,
    )
    await session.commit()
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_302_FOUND)


# --- Discounts ---

@router.get("/discounts", response_class=HTMLResponse)
async def discounts_page(
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
):
    discounts = await DiscountService.list_codes(session)
    for d in discounts:
        d.discount_value_formatted = format_vnd(d.discount_value)
        d.min_order_amount_formatted = format_vnd(d.min_order_amount)

    return templates.TemplateResponse(
        "discounts.html",
        {"request": request, "admin": admin, "discounts": discounts},
    )


@router.post("/discounts/create")
async def create_discount_submit(
    code: str = Form(...),
    discount_type: str = Form(...),
    discount_value: int = Form(...),
    max_uses: int = Form(100),
    min_order_amount: int = Form(0),
    days_valid: int = Form(30),
    admin: AdminUser = Depends(require_roles([AdminRole.SUPER_ADMIN, AdminRole.ORDER_MANAGER])),
    session: AsyncSession = Depends(get_db),
):
    start = datetime.now(timezone.utc)
    end = start + timedelta(days=days_valid)
    dtype = DiscountType.PERCENT if discount_type == "PERCENT" else DiscountType.FIXED

    await DiscountService.create_code(
        session=session,
        code=code,
        discount_type=dtype,
        discount_value=discount_value,
        max_uses=max_uses,
        start_date=start,
        end_date=end,
        min_order_amount=min_order_amount,
        admin_id=admin.id,
    )
    await session.commit()
    return RedirectResponse(url="/admin/discounts", status_code=status.HTTP_302_FOUND)


# --- Support Tickets ---

@router.get("/tickets", response_class=HTMLResponse)
async def tickets_page(
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
):
    tickets, _ = await TicketService.list_tickets(session)
    return templates.TemplateResponse(
        "tickets.html",
        {"request": request, "admin": admin, "tickets": tickets},
    )


@router.post("/tickets/reply")
async def reply_ticket_submit(
    ticket_id: int = Form(...),
    reply_text: str = Form(...),
    admin: AdminUser = Depends(require_roles([AdminRole.SUPER_ADMIN, AdminRole.ORDER_MANAGER, AdminRole.SUPPORT])),
    session: AsyncSession = Depends(get_db),
):
    ticket = await TicketService.reply_ticket(
        session=session,
        ticket_id=ticket_id,
        reply=reply_text,
        admin_id=admin.id,
    )
    await session.commit()

    # Deliver message to customer via Telegram bot
    try:
        bot = get_bot()
        msg = (
            f"📩 <b>PHẢN HỒI YÊU CẦU HỖ TRỢ #{ticket.ticket_code}</b>\n\n"
            f"Kỹ thuật viên SHARK COMPANY đã phản hồi vấn đề của bạn:\n\n"
            f"<i>\"{reply_text}\"</i>\n\n"
            f"Nếu cần hỗ trợ thêm, bạn có thể gửi tin nhắn phản hồi tiếp qua mục <b>🎧 Hỗ trợ</b>."
        )
        await bot.send_message(chat_id=ticket.telegram_id, text=msg, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Could not deliver ticket reply to Telegram ID {ticket.telegram_id}: {e}")

    return RedirectResponse(url="/admin/tickets", status_code=status.HTTP_302_FOUND)


# --- Broadcast Notification ---

@router.get("/broadcast", response_class=HTMLResponse)
async def broadcast_page(
    request: Request,
    admin: AdminUser = Depends(require_roles([AdminRole.SUPER_ADMIN])),
):
    return templates.TemplateResponse(
        "broadcast.html",
        {"request": request, "admin": admin, "message": None},
    )


@router.post("/broadcast/send")
async def send_broadcast_submit(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    admin: AdminUser = Depends(require_roles([AdminRole.SUPER_ADMIN])),
    session: AsyncSession = Depends(get_db),
):
    bot = get_bot()
    users, _ = await UserService.list_users(session, page=1, limit=10000)

    broadcast_msg = f"📢 <b>{title.upper()}</b>\n\n{content}"
    sent = 0
    failed = 0

    for u in users:
        if u.is_banned:
            continue
        try:
            await bot.send_message(chat_id=u.telegram_id, text=broadcast_msg, parse_mode="HTML")
            sent += 1
            await asyncio.sleep(0.05)  # Telegram rate limit prevention
        except Exception:
            failed += 1

    await AuditService.log_action(
        session=session,
        action="BROADCAST_MESSAGE",
        admin_id=admin.id,
        details=f"title={title} | sent={sent} | failed={failed}",
    )
    await session.commit()

    return templates.TemplateResponse(
        "broadcast.html",
        {
            "request": request,
            "admin": admin,
            "message": f"Đã gửi thành công {sent} tin nhắn ({failed} người dùng chặn bot hoặc lỗi).",
        },
    )


# --- Audit Logs ---

@router.get("/audit-logs", response_class=HTMLResponse)
async def audit_logs_page(
    request: Request,
    admin: AdminUser = Depends(require_roles([AdminRole.SUPER_ADMIN])),
    session: AsyncSession = Depends(get_db),
):
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(100)
    logs = list((await session.execute(stmt)).scalars().all())

    return templates.TemplateResponse(
        "audit_logs.html",
        {"request": request, "admin": admin, "logs": logs},
    )


# --- Bank & Payment Settings ---

@router.get("/bank-settings", response_class=HTMLResponse)
async def bank_settings_page(
    request: Request,
    admin: AdminUser = Depends(require_roles([AdminRole.SUPER_ADMIN])),
    session: AsyncSession = Depends(get_db),
):
    bank_info = await SettingService.get_bank_info(session)
    return templates.TemplateResponse(
        "bank_settings.html",
        {
            "request": request,
            "admin": admin,
            "bank_info": bank_info,
            "message": None,
        },
    )


@router.post("/bank-settings")
async def update_bank_settings(
    request: Request,
    bank_name: str = Form(...),
    bank_account: str = Form(...),
    account_name: str = Form(...),
    sepay_api_key: Optional[str] = Form(None),
    admin: AdminUser = Depends(require_roles([AdminRole.SUPER_ADMIN])),
    session: AsyncSession = Depends(get_db),
):
    await SettingService.update_bank_info(
        session=session,
        bank_name=bank_name,
        bank_account=bank_account,
        account_name=account_name,
        sepay_api_key=sepay_api_key,
        admin_id=admin.id,
    )
    await session.commit()

    bank_info = await SettingService.get_bank_info(session)
    return templates.TemplateResponse(
        "bank_settings.html",
        {
            "request": request,
            "admin": admin,
            "bank_info": bank_info,
            "message": "✅ Đã cập nhật thành công tài khoản ngân hàng thụ hưởng và SePay!",
        },
    )


# --- CSV Export ---

@router.get("/export/orders.csv")
async def export_orders_csv(
    admin: AdminUser = Depends(require_roles([AdminRole.SUPER_ADMIN, AdminRole.ORDER_MANAGER])),
    session: AsyncSession = Depends(get_db),
):
    stmt = select(Order).order_by(Order.id.desc())
    orders = list((await session.execute(stmt)).scalars().all())

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Order Code", "Telegram ID", "Product ID", "Amount", "Discount",
        "Final Amount", "Status", "Payment Method", "Created At"
    ])

    for o in orders:
        writer.writerow([
            o.id, o.order_code, o.telegram_id, o.product_id, o.original_amount,
            o.discount_amount, o.final_amount, o.status.value, o.payment_method.value,
            o.created_at.strftime("%Y-%m-%d %H:%M:%S")
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=mtk_orders.csv"}
    )
