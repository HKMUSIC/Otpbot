from aiogram import F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import random, string, datetime

# ================= FSM =================
class RedeemState(StatesGroup):
    waiting_code = State()
    waiting_value = State()
    waiting_limit = State()

# ================= Helpers =================
def generate_code(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# ================= Register =================
def register_redeem_handlers(dp, bot, db, ADMIN_IDS):
    users_col = db["users"]
    redeem_col = db["redeem_codes"]

    # ================= User Redeem =================
    @dp.callback_query(F.data == "redeem")
async def callback_redeem(cq: CallbackQuery, state: FSMContext):
    try:
        await cq.answer("✅ Send your redeem code now!", show_alert=False)
    except:
        pass
    await cq.message.answer("🎟️ Send your redeem code below:")
    await state.set_state(RedeemState.waiting_code)
    @dp.message(RedeemState.waiting_code)
    async def handle_redeem_code(msg: Message, state: FSMContext):
        code = msg.text.strip().upper()
        redeem = redeem_col.find_one({"code": code})

        if not redeem:
            await msg.answer("❌ Invalid or expired redeem code.")
            return await state.clear()

        if redeem["claimed_count"] >= redeem["max_claims"]:
            await msg.answer("🚫 This code has reached its claim limit.")
            return await state.clear()

        user = users_col.find_one({"_id": msg.from_user.id})
        if not user:
            await msg.answer("⚠️ Please use /start first.")
            return await state.clear()

        # Check if already claimed
        if msg.from_user.id in redeem.get("claimed_users", []):
            await msg.answer("⚠️ You have already claimed this code.")
            return await state.clear()

        # Credit user
        users_col.update_one(
            {"_id": msg.from_user.id},
            {"$inc": {"balance": redeem["amount"]}}
        )

        # Update redeem record
        redeem_col.update_one(
            {"code": code},
            {
                "$inc": {"claimed_count": 1},
                "$push": {"claimed_users": msg.from_user.id}
            }
        )

        await msg.answer(
            f"✅ Code <b>{code}</b> redeemed successfully!\n💰 You received ₹{redeem['amount']:.2f}",
            parse_mode="HTML"
        )
        await state.clear()

    # ================= Admin Create Redeem =================
    @dp.message(Command("/createredeem"))
    async def cmd_create_redeem(msg: Message, state: FSMContext):
        if msg.from_user.id not in ADMIN_IDS:
            return await msg.answer("❌ Not authorized.")
        await msg.answer("💰 Enter the amount for this redeem code:")
        await state.set_state(RedeemState.waiting_value)

    @dp.message(RedeemState.waiting_value)
    async def handle_redeem_amount(msg: Message, state: FSMContext):
        try:
            amount = float(msg.text.strip())
            if amount <= 0:
                raise ValueError
        except ValueError:
            return await msg.answer("❌ Invalid amount. Send a number like 50 or 100.")
        await state.update_data(amount=amount)
        await msg.answer("👥 Enter max number of users who can claim this code:")
        await state.set_state(RedeemState.waiting_limit)

    @dp.message(RedeemState.waiting_limit)
    async def handle_redeem_limit(msg: Message, state: FSMContext):
        try:
            limit = int(msg.text.strip())
            if limit <= 0:
                raise ValueError
        except ValueError:
            return await msg.answer("❌ Invalid number. Send a positive integer.")

        data = await state.get_data()
        amount = data["amount"]
        code = generate_code()
        created_at = datetime.datetime.utcnow()

        redeem_col.insert_one({
            "code": code,
            "amount": amount,
            "max_claims": limit,
            "claimed_count": 0,
            "claimed_users": [],
            "created_at": created_at
        })

        await msg.answer(
            f"✅ Redeem code created!\n\n"
            f"🎟️ Code: <code>{code}</code>\n"
            f"💰 Amount: ₹{amount:.2f}\n"
            f"👥 Max Claims: {limit}",
            parse_mode="HTML"
        )
        await state.clear()

    # ================= Admin View Redeems =================
    @dp.message(Command("/redeemlist"))
    async def cmd_redeem_list(msg: Message):
        if msg.from_user.id not in ADMIN_IDS:
            return await msg.answer("❌ Not authorized.")

        redeems = list(redeem_col.find())
        if not redeems:
            return await msg.answer("📭 No redeem codes found.")

        text = "🎟️ <b>Active Redeem Codes:</b>\n\n"
        for r in redeems:
            text += (
                f"Code: <code>{r['code']}</code>\n"
                f"💰 Amount: ₹{r['amount']}\n"
                f"👥 {r['claimed_count']} / {r['max_claims']} claimed\n\n"
            )
        await msg.answer(text, parse_mode="HTML")
