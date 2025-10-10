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
    manual_selected = State()
    waiting_screenshot = State()
    waiting_amount = State()
    waiting_payment_id = State()


def register_recharge_handlers(dp, bot, users_col, txns_col, ADMIN_IDS):
    """Registers the full recharge system handlers."""

    # ========= START FLOW =========
    async def start_recharge_flow(message: Message, state: FSMContext):
        kb = InlineKeyboardBuilder()
        kb.button(text="Pay Manually", callback_data="recharge_manual")
        kb.button(text="Automatic", callback_data="recharge_auto")
        kb.adjust(2)

        text = (
            "💰 <b>Add Funds to Your Account</b>\n\n"
            "We currently accept only UPI payments.\n\n"
            "⚙️ Automatic method is disabled for now.\n"
            "💡 Please choose <b>Manual</b> recharge method below."
        )
        await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        await state.set_state(RechargeState.choose_method)

    # ========= ENTRY =========
    @dp.callback_query(F.data == "recharge")
    async def recharge_start_button(cq: CallbackQuery, state: FSMContext):
        await cq.answer()
        await start_recharge_flow(cq.message, state)

    @dp.message(Command("recharge"))
    async def recharge_start_command(msg: Message, state: FSMContext):
        if not await check_join(bot, msg):
            return
        await start_recharge_flow(msg, state)

    # ========= AUTO BLOCK =========
    @dp.callback_query(F.data == "recharge_auto", StateFilter(RechargeState.choose_method))
    async def recharge_auto(cq: CallbackQuery):
        await cq.answer(
            "⚠️ Automatic payment is disabled. Use Manual instead.",
            show_alert=True
        )

    # ========= MANUAL SELECT =========
    @dp.callback_query(F.data == "recharge_manual", StateFilter(RechargeState.choose_method))
    async def recharge_manual(cq: CallbackQuery, state: FSMContext):
        await cq.answer()
        kb = InlineKeyboardBuilder()
        kb.button(text="Deposit Now", callback_data="deposit_now")
        kb.adjust(1)
        text = (
            f"👋 Hello {cq.from_user.full_name},\n\n"
            "You selected <b>Manual Recharge</b> method.\n\n"
            "In this method, you pay manually via UPI, send screenshot, and wait for admin approval.\n\n"
            "➡️ Click <b>Deposit Now</b> when you are ready."
        )
        await cq.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
        await state.set_state(RechargeState.manual_selected)

    # ========= DEPOSIT NOW =========
    @dp.callback_query(F.data == "deposit_now", StateFilter(RechargeState.manual_selected))
    async def deposit_now(cq: CallbackQuery, state: FSMContext):
        await cq.answer()
        qr_image = FSInputFile("IMG_20251008_085640_972.jpg")

        kb = InlineKeyboardBuilder()
        kb.button(text="✅ I've Paid", callback_data="paid_done")
        kb.adjust(1)

        text = (
            "🔝 Send your payment to this UPI:\n\n"
            "<pre>itsakt5@ptyes</pre>\n\n"
            "Or scan this QR below 👇\n\n"
            "✅ After paying, click <b>I've Paid</b>."
        )
        await cq.message.answer_photo(photo=qr_image, caption=text, parse_mode="HTML", reply_markup=kb.as_markup())

    # ========= USER CONFIRMS PAID =========
    @dp.callback_query(F.data == "paid_done", StateFilter(RechargeState.manual_selected))
    async def paid_done(cq: CallbackQuery, state: FSMContext):
        await cq.answer()
        await cq.message.answer("📸 Please send a <b>screenshot</b> of your payment.", parse_mode="HTML")
        await state.set_state(RechargeState.waiting_screenshot)

    # ========= USER SENDS SCREENSHOT =========
    @dp.message(StateFilter(RechargeState.waiting_screenshot), F.photo)
    async def screenshot_received(msg: Message, state: FSMContext):
        file_id = msg.photo[-1].file_id
        await state.update_data(screenshot=file_id)
        await msg.answer("💰 Please enter the <b>amount</b> you sent (in ₹):", parse_mode="HTML")
        await state.set_state(RechargeState.waiting_amount)

    # ========= AMOUNT =========
    @dp.message(StateFilter(RechargeState.waiting_amount), F.text)
    async def amount_received(msg: Message, state: FSMContext):
        text = msg.text.strip()
        if not text.replace(".", "", 1).isdigit():
            await msg.answer("❌ Invalid amount. Please send a number (e.g. 100).")
            return

        await state.update_data(amount=float(text))
        await msg.answer("🔑 Send your <b>UTR / Payment ID</b>:", parse_mode="HTML")
        await state.set_state(RechargeState.waiting_payment_id)

    # ========= PAYMENT ID =========
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

        await msg.answer("✅ Your payment request has been sent to admin for approval.\n\n⏳ Please wait 5–10 minutes.", parse_mode="HTML")
        await state.clear()

        # === Notify Admins ===
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
                        f"<b>🧾 Payment Approval Request</b>\n\n"
                        f"<b>Name:</b> {full_name}\n"
                        f"<b>Username:</b> @{username}\n"
                        f"<b>User ID:</b> {user_id}\n"
                        f"<b>Amount:</b> ₹{amount}\n"
                        f"<b>UTR/Payment ID:</b> {payment_id}"
                    ),
                    parse_mode="HTML",
                    reply_markup=kb.as_markup()
                )
            except Exception as e:
                print("Admin notify error:", e)
