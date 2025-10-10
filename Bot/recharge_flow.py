import datetime
from bson import ObjectId
from aiogram import F
from aiogram.types import CallbackQuery, Message, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import StateFilter, Command
from mustjoin import check_join

# ===== Recharge FSM =====
class RechargeState(StatesGroup):
    choose_method = State()
    waiting_deposit_screenshot = State()
    waiting_deposit_amount = State()
    waiting_payment_id = State()

def register_recharge_handlers(dp, bot, users_col, txns_col, ADMIN_IDS):
    """Registers recharge flow handlers."""

    # ===== Helper: Start Recharge =====
    async def start_recharge_flow(message: Message, state: FSMContext):
        kb = InlineKeyboardBuilder()
        kb.button(text="Pay Manually", callback_data="recharge_manual")
        kb.button(text="Automatic", callback_data="recharge_auto")
        kb.adjust(2)

        text = (
            "💰 Add Funds to Your Account\n\n"
            "We only accept payments via UPI.\n"
            "• Automatic payments have been stopped for security reasons.\n\n"
            "Please choose a method below:"
        )

        msg = await message.answer(text, reply_markup=kb.as_markup())
        await state.update_data(recharge_msg_id=msg.message_id)
        await state.set_state(RechargeState.choose_method)

    # ===== Entry Points =====
    @dp.callback_query(F.data == "recharge")
    async def recharge_start_button(cq: CallbackQuery, state: FSMContext):
        await start_recharge_flow(cq.message, state)
        await cq.answer()

    @dp.message(Command("recharge"))
    async def recharge_start_command(message: Message, state: FSMContext):
        if not await check_join(bot, message):
            return
        await start_recharge_flow(message, state)

    # ===== Flow Handlers =====
    @dp.callback_query(F.data == "recharge_auto", StateFilter(RechargeState.choose_method))
    async def recharge_auto(cq: CallbackQuery):
        await cq.answer(
            "⚠️ Automatic payment feature is currently unavailable. Please choose manual payment.",
            show_alert=True
        )

    @dp.callback_query(F.data == "recharge_manual", StateFilter(RechargeState.choose_method))
    async def recharge_manual(cq: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        msg_id = data.get("recharge_msg_id")

        kb = InlineKeyboardBuilder()
        kb.button(text="Deposit Now", callback_data="deposit_now")
        kb.button(text="Go Back", callback_data="go_back")
        kb.adjust(2)

        text = (
            f"Hello {cq.from_user.full_name},\n\n"
            "You have chosen the manual method to add balance to your account.\n"
            "Payment will be processed via admin approval."
        )

        await bot.edit_message_text(
            text=text,
            chat_id=cq.from_user.id,
            message_id=msg_id,
            reply_markup=kb.as_markup()
        )
        await cq.answer()

    @dp.callback_query(F.data == "go_back", StateFilter(RechargeState.choose_method))
    async def recharge_go_back(cq: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        msg_id = data.get("recharge_msg_id")

        kb = InlineKeyboardBuilder()
        kb.button(text="Pay Manually", callback_data="recharge_manual")
        kb.button(text="Automatic", callback_data="recharge_auto")
        kb.adjust(2)

        text = (
            "💰 Add Funds to Your Account\n\n"
            "We only accept payments via UPI.\n"
            "• Automatic payments have been stopped for security reasons.\n\n"
            "Please choose a method below:"
        )

        await bot.edit_message_text(
            text=text,
            chat_id=cq.from_user.id,
            message_id=msg_id,
            reply_markup=kb.as_markup()
        )
        await cq.answer()

    # ===== Deposit Now / UPI QR =====
    @dp.callback_query(F.data == "deposit_now", StateFilter(RechargeState.choose_method))
    async def deposit_now(cq: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        msg_id = data.get("recharge_msg_id")

        kb = InlineKeyboardBuilder()
        kb.button(text="UPI", callback_data="upi_qr")
        kb.button(text="Go Back", callback_data="go_back")
        kb.adjust(2)

        text = "Select the UPI method below to deposit your funds.\n\n1 INR = 1 INR"

        await bot.edit_message_text(
            text=text,
            chat_id=cq.from_user.id,
            message_id=msg_id,
            reply_markup=kb.as_markup()
        )
        await cq.answer()

    @dp.callback_query(F.data == "upi_qr", StateFilter(RechargeState.choose_method))
    async def upi_qr(cq: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        msg_id = data.get("recharge_msg_id")
        try:
            await bot.delete_message(chat_id=cq.from_user.id, message_id=msg_id)
        except:
            pass

        qr_image = FSInputFile("IMG_20251008_085640_972.jpg")

        kb = InlineKeyboardBuilder()
        kb.button(text="✅ I've Paid", callback_data="paid_done")
        kb.adjust(1)

        caption = (
            "🔝 Send INR on this QR Code.\n\n"
            "💳 Or Pay To:\n<pre>itsakt5@ptyes</pre>\n\n"
            "✅ After Payment, click 'I've Paid'."
        )

        msg = await cq.message.answer_photo(photo=qr_image, caption=caption, parse_mode="HTML", reply_markup=kb.as_markup())
        await state.update_data(recharge_msg_id=msg.message_id)
        await cq.answer()

    # ===== Paid Done =====
    @dp.callback_query(F.data == "paid_done", StateFilter(RechargeState.choose_method))
    async def paid_done(cq: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        qr_msg_id = data.get("recharge_msg_id")
        try:
            await bot.delete_message(chat_id=cq.from_user.id, message_id=qr_msg_id)
        except:
            pass
        await cq.message.answer("📸 Please send a screenshot of your payment.")
        await state.set_state(RechargeState.waiting_deposit_screenshot)
        await cq.answer()

    # ===== Screenshot Received =====
    @dp.message(StateFilter(RechargeState.waiting_deposit_screenshot))
    async def screenshot_received(message: Message, state: FSMContext):
        if not message.photo:
            await message.answer("❌ Please send a valid screenshot image.")
            return
        await state.update_data(screenshot=message.photo[-1].file_id)
        await message.answer("💰 Enter the amount you sent (in ₹):")
        await state.set_state(RechargeState.waiting_deposit_amount)

    # ===== Amount Received =====
    @dp.message(StateFilter(RechargeState.waiting_deposit_amount))
    async def amount_received(message: Message, state: FSMContext):
        amt = message.text.strip()
        if not amt.replace(".", "", 1).isdigit():
            await message.answer("❌ Invalid amount. Enter numbers only.")
            return
        await state.update_data(amount=float(amt))
        await message.answer("🔑 Please send your Payment ID / UTR:")
        await state.set_state(RechargeState.waiting_payment_id)

    # ===== Payment ID Received =====
    @dp.message(StateFilter(RechargeState.waiting_payment_id))
    async def payment_id_received(message: Message, state: FSMContext):
        data = await state.get_data()
        screenshot = data.get("screenshot")
        amount = data.get("amount")
        payment_id = message.text.strip()
        user_id = message.from_user.id
        username = message.from_user.username or "None"
        full_name = message.from_user.full_name

        txn_doc = {
            "user_id": user_id,
            "username": username,
            "full_name": full_name,
            "amount": amount,
            "payment_id": payment_id,
            "screenshot": screenshot,
            "status": "pending",
            "created_at": datetime.datetime.utcnow()
        }
        txn_id = txns_col.insert_one(txn_doc).inserted_id

        await message.answer("✅ Your payment request has been sent to the admin. Please wait for approval.")
        await state.clear()

        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Approve", callback_data=f"approve_txn:{txn_id}")
        kb.button(text="❌ Decline", callback_data=f"decline_txn:{txn_id}")
        kb.adjust(2)

        for admin_id in ADMIN_IDS:
            try:
                await bot.send_photo(
                    chat_id=admin_id,
                    photo=screenshot,
                    caption=(
                        f"<b>Payment Approval Request</b>\n\n"
                        f"Name: {full_name}\n"
                        f"Username: @{username}\n"
                        f"ID: {user_id}\n"
                        f"Amount: ₹{amount}\n"
                        f"UTR / Payment ID: {payment_id}"
                    ),
                    parse_mode="HTML",
                    reply_markup=kb.as_markup()
                )
            except Exception:
                pass
