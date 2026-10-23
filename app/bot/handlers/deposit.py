from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, BufferedInputFile
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from app.config.settings import settings
from app.database.models import User
from app.services.user_service import UserService
from app.services.setting_service import SettingService
from app.payments.sepay import SePayGateway
from app.bot.keyboards.wallet_kb import (
    get_deposit_amounts_keyboard,
    get_deposit_qr_keyboard,
)
from app.bot.keyboards.main_menu import get_back_to_main_keyboard
from app.bot.handlers.states import DepositStates
from app.utils.helpers import format_vnd, generate_deposit_code
from app.utils.logger import logger

router = Router(name="deposit_router")


@router.callback_query(F.data == "menu:deposit")
async def choose_deposit_amount(callback: CallbackQuery, user: User):
    """Show deposit denomination menu"""
    text = (
        f"💰 <b>NẠP TIỀN VÀO VÍ MTK</b>\n\n"
        f"• Số dư hiện tại: <b>{format_vnd(user.balance)}</b>\n"
        f"• Tự động cộng tiền trong 3 - 10 giây qua SePay.\n"
        f"• Tối thiểu: 10.000 đ | Tối đa: 20.000.000 đ\n\n"
        f"<i>Vui lòng chọn hoặc nhập số tiền muốn nạp:</i>"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_deposit_amounts_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("deposit:amount:"))
async def handle_deposit_amount_selection(callback: CallbackQuery, state: FSMContext, session: AsyncSession, user: User):
    """Handle selected deposit amount"""
    val = callback.data.split(":")[2]
    if val == "custom":
        await state.set_state(DepositStates.waiting_for_custom_amount)
        await callback.message.answer(
            "✏️ <b>Nhập số tiền muốn nạp (VND):</b>\n\nVí dụ: gửi <code>150000</code>",
            parse_mode="HTML"
        )
        await callback.answer()
        return

    amount = int(val)
    await show_deposit_instruction(callback.message, session, user, amount)
    await callback.answer()


@router.message(DepositStates.waiting_for_custom_amount)
async def process_custom_deposit_input(message: Message, state: FSMContext, session: AsyncSession, user: User):
    """Process user input custom amount"""
    await state.clear()
    raw = message.text.replace(".", "").replace(",", "").replace("đ", "").strip() if message.text else ""
    try:
        amount = int(raw)
        if amount < 10000:
            await message.answer("⚠️ Số tiền nạp tối thiểu là 10.000 đ. Vui lòng thử lại!", reply_markup=get_back_to_main_keyboard())
            return
        if amount > 50000000:
            await message.answer("⚠️ Số tiền nạp vượt hạn mức (tối đa 50.000.000 đ).", reply_markup=get_back_to_main_keyboard())
            return
    except ValueError:
        await message.answer("⚠️ Số tiền không hợp lệ. Vui lòng chỉ nhập số!", reply_markup=get_back_to_main_keyboard())
        return

    await show_deposit_instruction(message, session, user, amount)


async def show_deposit_instruction(message_target, session: AsyncSession, user: User, amount: int):
    """Render VietQR bank transfer details for deposit with automatic QR photo"""
    bank_info = await SettingService.get_bank_info(session)
    transfer_code = generate_deposit_code(user.telegram_id)

    text = (
        f"🏦 <b>THÔNG TIN CHUYỂN KHOẢN NẠP TIỀN</b>\n\n"
        f"• Ngân hàng: <b>{bank_info['bank_name']}</b>\n"
        f"• Số tài khoản: <code>{bank_info['bank_account']}</code>\n"
        f"• Tên chủ tài khoản: <b>{bank_info['account_name']}</b>\n"
        f"• Số tiền: <b>{format_vnd(amount)}</b>\n"
        f"• Nội dung chuyển khoản: <code>{transfer_code}</code>\n\n"
        f"⚠️ <b>LƯU Ý BẮT BUỘC:</b>\n"
        f"Phải nhập chính xác nội dung: <code>{transfer_code}</code>\n"
        f"Hệ thống sẽ tự động cộng <b>{format_vnd(amount)}</b> vào số dư của bạn ngay khi nhận được tiền."
    )

    # 1. Fetch QR code and convert to PNG bytes for direct photo display
    png_bytes = await SePayGateway.get_vietqr_image_bytes(
        amount=amount,
        content=transfer_code,
        bank_name=bank_info["bank_name"],
        account_number=bank_info["bank_account"],
        account_name=bank_info["account_name"],
    )

    if png_bytes:
        try:
            if hasattr(message_target, "delete"):
                try:
                    await message_target.delete()
                except Exception:
                    pass
            await message_target.answer_photo(
                photo=BufferedInputFile(png_bytes, filename="vietqr.png"),
                caption=text,
                reply_markup=get_deposit_qr_keyboard(),
                parse_mode="HTML"
            )
            return
        except Exception as e:
            logger.warning(f"Failed to send deposit QR photo: {e}")

    # Fallback to text message if photo conversion fails
    qr_url = SePayGateway.generate_vietqr_url(
        amount=amount,
        content=transfer_code,
        bank_name=bank_info["bank_name"],
        account_number=bank_info["bank_account"],
        account_name=bank_info["account_name"],
    )

    if hasattr(message_target, "edit_text"):
        try:
            await message_target.edit_text(text, reply_markup=get_deposit_qr_keyboard(qr_url), parse_mode="HTML")
            return
        except Exception:
            pass

    await message_target.answer(text, reply_markup=get_deposit_qr_keyboard(qr_url), parse_mode="HTML")


@router.callback_query(F.data == "deposit:refresh")
async def refresh_balance(callback: CallbackQuery, session: AsyncSession, user: User):
    """Check and refresh current balance"""
    refreshed_user = await UserService.get_by_telegram_id(session, user.telegram_id)
    balance = refreshed_user.balance if refreshed_user else 0
    await callback.answer(f"💰 Số dư hiện tại của bạn: {format_vnd(balance)}", show_alert=True)
