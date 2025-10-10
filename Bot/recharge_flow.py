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
    """Register manual recharge flow."""

    # ===== Helper =====
    async def start_recharge_flow(message: Message, state: FSMContext):
        kb = InlineKeyboardBuilder()
        kb.button(text="Pay Manually", callback_data="recharge_manual")
        kb.adjust(1)

        text = (
            "💰 Add Funds to Your Account\n\n"
            "We currently accept only UPI payments.\n\n"
            "⚙️ Automatic payments are disabled for now.\n"
            "💡 Choose Manual Recharge below."
        )
        msg = await message.answer(text, reply_markup=kb.as_markup())
        await state.update_data(recharge_msg_id=msg.message_id)
        await state.set_state(RechargeState.choose_method)

    # ===== Entry Points =====
    @dp.callback_query(F.data == "recharge")
    async def recharge_start_button(cq: CallbackQuery, state: FSMContext):
        await cq.answer()
        await start_recharge_flow(cq.message, state)

    @dp.message(Command("recharge"))
    async def recharge_start_command(message: Message, state: FSMContext):
        if not await check_join(bot, message):
            return
        await start_recharge_flow(message, state)

    # ===== Manual Payment Selected =====
    @dp.callback_query(F.data == "recharge_manual", StateFilter(RechargeState.choose_method))
    async def recharge_manual(cq: CallbackQuery, state: FSMContext):
        await cq.answer()
        data = await state.get_data()
        msg_id = data.get("recharge_msg_id")

        kb = InlineKeyboardBuilder()
        kb.button(text="Deposit Now", callback_data="deposit_now")
        kb.adjust(1)

        text = (
            f"👋 Hello {cq.from_user.full_name},\n\n"
            "You selected Manual Recharge.\n"
            "Pay via UPI, then click Deposit Now."
        )
        await bot.edit_message_text(
            chat_id=cq.from_user.id,
            message_id=msg_id,
            text=text,
            reply_markup=kb.as_markup()
        )

    # ===== Deposit Now =====
    @dp.callback_query(F.data == "deposit_now", StateFilter(RechargeState.choose_method))
    async def deposit_now(cq: CallbackQuery, state: FSMContext):
        await cq.answer()
        data = await state.get_data()
        msg_id = data.get("recharge_msg_id")

        qr_image = FSInputFile("IMG_20251008_085640_972.jpg")
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ I've Paid", callback_data="paid_done")
        kb.adjust(1)

        caption = (
            "🔝 Send your payment to this UPI:\n<pre>itsakt5@ptyes</pre>\n\n"
            "Or scan the QR below 👇\n\n"
            "✅ After paying, click 'I've Paid'."
        )
        await bot.edit_message_media(
            chat_id=cq.from_user.id,
            message_id=msg_id,
            media=qr_image,
            caption=caption,
            parse_mode="HTML",
            reply_markup=kb.as_markup()
        )
        await state.set_state(RechargeState.waiting_deposit_screenshot)

    # ===== User confirms payment done =====
    @dp.callback_query(F.data == "paid_done", StateFilter(RechargeState.waiting_deposit_screenshot))
    async def paid_done(cq: CallbackQuery, state: FSMContext):
        await cq.answer()
        await cq.message.answer("📸 Please send a screenshot of your payment.")
        await state.set_state(RechargeState.waiting_deposit_screenshot)

    # ===== Screenshot received =====
    @dp.message(StateFilter(RechargeState.waiting_deposit_screenshot), F.photo)
    async def screenshot_received(msg: Message, state: FSMContext):
        await state.update_data(screenshot=msg.photo[-1].file_id)
        await msg.answer("💰 Please enter the <b>amount</b> you sent (in ₹):", parse_mode="HTML")
        await state.set_state(RechargeState.waiting_deposit_amount)

    # ===== Amount received =====
    @dp.message(StateFilter(RechargeState.waiting_deposit_amount), F.text)
    async def amount_received(msg: Message, state: FSMContext):
        text = msg.text.strip()
        if not text.replace(".", "", 1).isdigit():
            return await msg.answer("❌ Invalid amount. Please enter a number (e.g., 100).")
        await state.update_data(amount=float(text))
        await msg.answer("🔑 Please send your Payment ID / UTR:")
        await state.set_state(RechargeState.waiting_payment_id)

    # ===== Payment ID received =====
    @dp.message(StateFilter(RechargeState.waiting_payment_id), F.text)
    async def payment_id_received(msg: Message, state: FSMContext):
        data = await state.get_data()
        screenshot = data.get("screenshot")
        amount = data.get("amount")
        payment_id = msg.text.strip()

        user_id = msg.from_user.id
        username = msg.from_user.username or "None"
        full_name = msg.from_user.full_name

        txn_doc = {
            "user_id": user_id,
            "username": username,
            "full_name": full_name,
            "amount": amount,
            "payment_id": payment_id,
            "screenshot": screenshot,
            "status": "pending",
            "created_at": datetime.datetime.utcnow(),
        }
        txn_id = txns_col.insert_one(txn_doc).inserted_id

        await msg.answer(
            "✅ Your payment request has been sent to admin for approval.\n⏳ Please wait 5–10 minutes."
        )
        await state.clear()

        # Notify Admins
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
                        f"User ID: {user_id}\n"
                        f"Amount: ₹{amount}\n"
                        f"UTR/Payment ID: {payment_id}"
                    ),
                    parse_mode="HTML",
                    reply_markup=kb.as_markup()
                )
            except Exception as e:
                print("Admin notification error:", e)
