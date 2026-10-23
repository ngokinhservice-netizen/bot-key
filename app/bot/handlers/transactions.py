from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import User, Order, WalletTransaction
from app.bot.keyboards.main_menu import get_back_to_main_keyboard
from app.utils.helpers import format_vnd

router = Router(name="transactions_router")


@router.callback_query(F.data == "menu:transactions")
async def show_transaction_history(callback: CallbackQuery, session: AsyncSession, user: User):
    """View recent orders and wallet transactions for this user only"""
    # 1. Fetch recent orders (last 5)
    order_stmt = (
        select(Order)
        .where(Order.user_id == user.id)
        .order_by(Order.id.desc())
        .limit(5)
    )
    orders = list((await session.execute(order_stmt)).scalars().all())

    # 2. Fetch recent wallet transactions (last 5)
    tx_stmt = (
        select(WalletTransaction)
        .where(WalletTransaction.user_id == user.id)
        .order_by(WalletTransaction.id.desc())
        .limit(5)
    )
    transactions = list((await session.execute(tx_stmt)).scalars().all())

    lines = ["🧾 <b>LỊCH SỬ GIAO DỊCH CỦA BẠN</b>\n"]

    lines.append("📦 <b>Đơn hàng gần đây:</b>")
    if not orders:
        lines.append("<i>(Chưa có đơn hàng nào)</i>")
    else:
        for o in orders:
            status_emoji = "✅" if o.status.value in ["COMPLETED", "PAID"] else "⏳" if o.status.value == "PENDING" else "❌"
            dt = o.created_at.strftime("%d/%m %H:%M")
            lines.append(f"• {status_emoji} <code>#{o.order_code}</code> | {format_vnd(o.final_amount)} | {dt}")

    lines.append("\n💰 <b>Biến động số dư ví:</b>")
    if not transactions:
        lines.append("<i>(Chưa có giao dịch ví nào)</i>")
    else:
        for t in transactions:
            sign = "+" if t.amount > 0 else ""
            dt = t.created_at.strftime("%d/%m %H:%M")
            lines.append(f"• <code>{sign}{format_vnd(t.amount)}</code> ({t.tx_type.value}) | {dt}")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=get_back_to_main_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()
