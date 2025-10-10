# recharge_flow.py
import datetime
from aiogram import F
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from bson import ObjectId
from aiogram.filters import StateFilter

# ========== FSM ==========
class RechargeState(StatesGroup):
    choose_method = State()
    waiting_deposit_screenshot = State()
    admin_waiting_amount = State()  # Admin enters amount for approval

# ========== Pending txn tracking ==========
pending_admin_txns = {}  # admin_id -> txn_id

# ========== Handler Registration ==========
def register_recharge_handlers(dp, bot, users_col, txns_col, ADMIN_IDS):

    # ---------- Start Recharge ----------
    @dp.callback_query(F.data == "recharge")
    @dp.message(F.text == "/recharge")
    async def recharge_start(entry, state: FSMContext):
        kb = InlineKeyboardBuilder()
        kb.button(text="💳 Manual Payment", callback_data="recharge_manual")
        kb.adjust(1)

        text = (
            "💰 Recharge Your Account\n\n"
            "Currently, automatic payments are disabled.\n"
            "Please choose manual payment to continue."
        )

        if isinstance(entry, CallbackQuery):
            await entry.message.answer(text, reply_markup=kb.as_markup())
            await entry.answer()
        else:
            await entry.answer(text, reply_markup=kb.as_markup())
        await state.set_state(RechargeState.choose_method)

    # ---------- Choose Manual ----------
    @dp.callback_query(F.data == "recharge_manual", StateFilter(RechargeState.choose_method))
    async def recharge_manual(cq: CallbackQuery, state: FSMContext):
        kb = InlineKeyboardBuilder()
        kb.button(text="Send Payment Screenshot", callback_data="send_deposit")
        kb.adjust(1)

        text = (
            "📌 Manual Payment Selected\n"
            "Please send a screenshot of your payment to continue."
        )
        await cq.message.answer(text, reply_markup=kb.as_markup())
        await state.set_state(RechargeState.waiting_deposit_screenshot)
        await cq.answer()

    # ---------- Receive Screenshot ----------
    @dp.message(StateFilter(RechargeState.waiting_deposit_screenshot), F.photo)
    async def screenshot_received(msg: Message, state: FSMContext):
        screenshot_id = msg.photo[-1].file_id
        txn_doc = {
            "user_id": msg.from_user.id,
            "username": msg.from_user.username,
            "full_name": msg.from_user.full_name,
            "screenshot": screenshot_id,
            "status": "pending",
            "created_at": datetime.datetime.utcnow(),
        }
        txn_id = txns_col.insert_one(txn_doc).inserted_id

        await msg.answer("✅ Screenshot sent to admin. Awaiting approval.")

        # Send to all admins
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Approve", callback_data=f"approve_txn:{txn_id}")
        kb.button(text="❌ Decline", callback_data=f"decline_txn:{txn_id}")
        kb.adjust(2)

        for admin_id in ADMIN_IDS:
            try:
                await bot.send_photo(
                    chat_id=admin_id,
                    photo=screenshot_id,
                    caption=(
                        f"<b>New Payment Request</b>\n\n"
                        f"👤 {msg.from_user.full_name}\n"
                        f"🆔 {msg.from_user.id}\n"
                        f"🔗 @{msg.from_user.username or 'N/A'}\n"
                    ),
                    parse_mode="HTML",
                    reply_markup=kb.as_markup()
                )
            except Exception:
                pass
        await state.clear()

    # ---------- Admin Approves ----------
    @dp.callback_query(F.data.startswith("approve_txn:"))
    async def approve_txn(cq: CallbackQuery, state: FSMContext):
        txn_id = cq.data.split(":")[1]
        txns_col.update_one({"_id": ObjectId(txn_id)}, {"$set": {"status": "approved_waiting_amount"}})

        pending_admin_txns[cq.from_user.id] = txn_id
        await cq.message.answer("💰 Reply with the amount to credit this user (numbers only).")
        await state.set_state(RechargeState.admin_waiting_amount)
        await cq.answer()

    # ---------- Admin Enters Amount ----------
    @dp.message(StateFilter(RechargeState.admin_waiting_amount))
    async def admin_enter_amount(msg: Message, state: FSMContext):
        admin_id = msg.from_user.id
        txn_id = pending_admin_txns.get(admin_id)
        if not txn_id:
            await msg.answer("⚠️ No pending transaction found.")
            await state.clear()
            return

        text = msg.text.strip()
        if not text.replace(".", "", 1).isdigit():
            return await msg.answer("❌ Invalid input. Send only numeric amount.")

        amount = float(text)
        txn = txns_col.find_one({"_id": ObjectId(txn_id)})
        if not txn:
            await msg.answer("⚠️ Transaction not found.")
            await state.clear()
            pending_admin_txns.pop(admin_id, None)
            return

        user_id = txn["user_id"]
        users_col.update_one({"_id": user_id}, {"$inc": {"balance": amount}}, upsert=True)
        txns_col.update_one({"_id": ObjectId(txn_id)}, {"$set": {"status": "approved", "amount": amount}})

        await msg.answer(f"✅ Added ₹{amount:.2f} to {txn['full_name']} (@{txn['username']}).")
        pending_admin_txns.pop(admin_id, None)
        await state.clear()

        try:
            await bot.send_message(user_id, f"🎉 Your payment of ₹{amount:.2f} has been credited!")
        except Exception:
            pass

    # ---------- Admin Declines ----------
    @dp.callback_query(F.data.startswith("decline_txn:"))
    async def decline_txn(cq: CallbackQuery):
        txn_id = cq.data.split(":")[1]
        txns_col.update_one({"_id": ObjectId(txn_id)}, {"$set": {"status": "declined"}})
        txn = txns_col.find_one({"_id": ObjectId(txn_id)})

        await cq.message.answer("❌ Payment declined.")
        try:
            await bot.send_message(txn["user_id"], "❌ Your payment was declined by admin.")
        except Exception:
            pass
        await cq.answer()
