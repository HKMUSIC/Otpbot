import datetime
from bson import ObjectId
from aiogram import F
from aiogram.types import CallbackQuery, Message, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import StateFilter, Command
from mustjoin import check_join

# Recharge FSM
class RechargeState(StatesGroup):
    choose_method = State()
    waiting_deposit_screenshot = State()
    admin_waiting_amount = State()  # For admin input

# Store pending txn per admin
pending_admin_amounts = {}

def register_recharge_handlers(dp, bot, users_col, txns_col, ADMIN_IDS):

    # ================= Helper =================
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

    # ================= Entry Points =================
    @dp.callback_query(F.data == "recharge")
    async def recharge_start_button(cq: CallbackQuery, state: FSMContext):
        await start_recharge_flow(cq.message, state)
        await cq.answer()

    @dp.message(Command("recharge"))
    async def recharge_start_command(message: Message, state: FSMContext):
        if not await check_join(bot, message):
            return
        await start_recharge_flow(message, state)

    # ================= Flow Handlers =================
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
            "Payments will be processed via admin approval."
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
        await start_recharge_flow(cq.message, state)
        await cq.answer()

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
        kb.button(text="Deposit", callback_data="send_deposit")
        kb.button(text="Go Back", callback_data="go_back")
        kb.adjust(2)

        text = (
            "🔝 Send INR on this QR Code.\n"
            "💳 Or Pay To:\n\n<code>itsakt5@ptyes</code>\n"
            "✅ After Payment, Click Deposit Button."
        )

        msg = await cq.message.answer_photo(
            photo=qr_image, caption=text, parse_mode="HTML", reply_markup=kb.as_markup()
        )
        await state.update_data(recharge_msg_id=msg.message_id)
        await cq.answer()

    @dp.callback_query(F.data == "send_deposit", StateFilter(RechargeState.choose_method))
    async def send_deposit(cq: CallbackQuery, state: FSMContext):
        try:
            await cq.message.delete()
        except:
            pass
        await cq.message.answer("📸 Please send a screenshot of your payment.")
        await state.set_state(RechargeState.waiting_deposit_screenshot)
        await cq.answer()

    # ================= Screenshot received =================
    @dp.message(StateFilter(RechargeState.waiting_deposit_screenshot), F.photo)
    async def screenshot_received(message: Message, state: FSMContext):
        screenshot = message.photo[-1].file_id
        user_id = message.from_user.id
        username = message.from_user.username or "N/A"
        full_name = message.from_user.full_name

        txn_doc = {
            "user_id": user_id,
            "username": username,
            "full_name": full_name,
            "screenshot": screenshot,
            "status": "pending",
            "created_at": datetime.datetime.utcnow(),
        }
        txn_id = txns_col.insert_one(txn_doc).inserted_id

        await message.answer(
            "✅ Your payment screenshot has been sent to the admin for verification.\n"
            "Please wait for approval."
        )
        await state.clear()

        # Send to admins
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
                        f"<b>New Payment Request</b>\n\n"
                        f"👤 Name: {full_name}\n"
                        f"🆔 ID: {user_id}\n"
                        f"🔗 Username: @{username}\n\n"
                        "Please review and approve/decline below."
                    ),
                    parse_mode="HTML",
                    reply_markup=kb.as_markup()
                )
            except Exception:
                pass

    # ================= Admin approves =================
    @dp.callback_query(F.data.startswith("approve_txn:"))
    async def approve_txn(cq: CallbackQuery, state: FSMContext):
        txn_id = cq.data.split(":")[1]
        txns_col.update_one({"_id": ObjectId(txn_id)}, {"$set": {"status": "approved_waiting_amount"}})

        # Store txn per admin
        pending_admin_amounts[cq.from_user.id] = txn_id
        await cq.message.answer("💰 Please reply with the amount to add for this user.")
        await state.set_state(RechargeState.admin_waiting_amount)
        await cq.answer()

    # ================= Admin sends amount =================
    @dp.message(StateFilter(RechargeState.admin_waiting_amount), F.text)
    async def admin_add_amount(message: Message, state: FSMContext):
        admin_id = message.from_user.id
        txn_id = pending_admin_amounts.get(admin_id)

        if not txn_id:
            await message.answer("⚠️ No pending transaction found.")
            await state.clear()
            return

        if not message.text.replace(".", "").isdigit():
            await message.answer("❌ Please enter a valid numeric amount.")
            return

        amount = float(message.text.strip())
        txn = txns_col.find_one({"_id": ObjectId(txn_id)})

        if not txn:
            await message.answer("⚠️ Transaction not found.")
            await state.clear()
            pending_admin_amounts.pop(admin_id, None)
            return

        user_id = txn["user_id"]
        users_col.update_one({"_id": user_id}, {"$inc": {"balance": amount}}, upsert=True)
        txns_col.update_one({"_id": ObjectId(txn_id)}, {"$set": {"status": "approved", "amount": amount}})

        await message.answer(f"✅ Added ₹{amount} to user {txn['full_name']} (@{txn['username']}).")
        await state.clear()
        pending_admin_amounts.pop(admin_id, None)

        # Notify user
        try:
            await bot.send_message(
                user_id,
                f"🎉 Your payment of ₹{amount} has been approved and added to your balance!"
            )
        except Exception:
            pass

    # ================= Admin declines =================
    @dp.callback_query(F.data.startswith("decline_txn:"))
    async def decline_txn(cq: CallbackQuery):
        txn_id = cq.data.split(":")[1]
        txns_col.update_one({"_id": ObjectId(txn_id)}, {"$set": {"status": "declined"}})
        txn = txns_col.find_one({"_id": ObjectId(txn_id)})

        await cq.message.answer("❌ Payment has been declined.")
        try:
            await bot.send_message(
                txn["user_id"],
                "❌ Your payment was declined by the admin. Please contact support for details."
            )
        except Exception:
            pass
        await cq.answer()
