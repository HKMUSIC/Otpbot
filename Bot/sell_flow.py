import os, asyncio, html, random, string, re
from datetime import datetime, timezone
from aiogram import F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from telethon import TelegramClient, functions, types
from telethon.sessions import StringSession
from pymongo import MongoClient


# ============ CONFIG ============ #
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
LOG_CHANNEL = os.getenv("LOG_CHANNEL")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["QuickCodes"]
users_col = db["users"]
sell_rates_col = db["sell_rates"]
sales_col = db["sales"]


# ============ FSM STATES ============ #
class SellAccount(StatesGroup):
    waiting_number = State()
    waiting_otp = State()


# ============ HANDLER ============ #
def register_sell_handlers(dp, bot):
    @dp.callback_query(F.data == "sell")
    async def callback_sell(cq: CallbackQuery, state: FSMContext):
        """Show current sell rates and ask for number"""
        rates = list(sell_rates_col.find({}))
        if not rates:
            return await cq.message.answer("❌ No sell rates set by admin yet.")

        msg_text = "📋 <b>Sell Rates:</b>\n\n"
        for r in rates:
            msg_text += f"{r['country']} - ₹{r['price']}\n"
        msg_text += "\n💬 Send the <b>number</b> you want to sell (e.g., +14151234567)"
        await cq.message.answer(msg_text, parse_mode="HTML")
        await state.set_state(SellAccount.waiting_number)

    # Step 1: User sends number
    @dp.message(SellAccount.waiting_number)
    async def handle_sell_number(msg: Message, state: FSMContext):
        number = msg.text.strip()
        if not re.match(r"^\+\d{6,15}$", number):
            await state.clear()
            return await msg.answer("❌ Invalid number format. Use format like +14151234567")

        # Detect country
        countries = list(sell_rates_col.find({}))
        detected_country = None
        for c in countries:
            if number.startswith(c.get("code", "")):
                detected_country = c["country"]
                price = c["price"]
                break

        if not detected_country:
            await state.clear()
            return await msg.answer("❌ Couldn't detect your country from number prefix.")

        # Create Telethon session
        session = StringSession()
        client = TelegramClient(session, API_ID, API_HASH)
        await client.connect()

        try:
            sent = await client.send_code_request(number)
            await msg.answer("📩 Code sent! Please check Telegram or SMS for OTP.")
            await state.update_data(
                session=session.save(),
                number=number,
                country=detected_country,
                price=price,
                phone_code_hash=sent.phone_code_hash,
            )
            await client.disconnect()
            await state.set_state(SellAccount.waiting_otp)

        except Exception as e:
            await client.disconnect()
            await msg.answer(f"❌ Error sending code: <code>{html.escape(str(e))}</code>", parse_mode="HTML")
            await state.clear()

    # Step 2: Handle OTP
    @dp.message(StateFilter(SellAccount.waiting_otp))
    async def handle_sell_otp(msg: Message, state: FSMContext):
        data = await state.get_data()
        session_str = data["session"]
        number = data["number"]
        country = data["country"]
        price = data["price"]
        phone_code_hash = data["phone_code_hash"]

        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await client.connect()
        try:
            await client.sign_in(phone=number, code=msg.text.strip(), phone_code_hash=phone_code_hash)

            # Change password (optional random new password)
            new_password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
            try:
                await client(functions.account.UpdatePasswordSettingsRequest(
                    password=None,
                    new_settings=types.account.PasswordInputSettings(new_password=new_password)
                ))
            except Exception:
                pass

            string_session = client.session.save()
            await client.log_out()
            await client.disconnect()

            # Save in DB
            sales_col.insert_one({
                "user_id": msg.from_user.id,
                "username": msg.from_user.username,
                "number": number,
                "country": country,
                "price": price,
                "string_session": string_session,
                "password": new_password,
                "status": "pending",
                "created_at": datetime.now(timezone.utc)
            })

            await msg.answer(f"✅ Your account listed successfully!\n\n💰 You'll receive ₹{price} in 24 hours after verification.")
            await state.clear()

            # Notify admins
            log_text = (
                f"📢 <b>New Account Sell Request</b>\n\n"
                f"👤 User: @{msg.from_user.username or msg.from_user.id}\n"
                f"📞 Number: {number}\n"
                f"🌍 Country: {country}\n"
                f"💸 Price: ₹{price}\n"
                f"🔑 Password: <code>{new_password}</code>\n\n"
                f"<b>StringSession:</b>\n<code>{string_session}</code>"
            )
            await bot.send_message(LOG_CHANNEL, log_text, parse_mode="HTML")

            # Schedule check after 24 hours
            asyncio.create_task(check_release_payment(bot, number))

        except Exception as e:
            await client.disconnect()
            await msg.answer(f"❌ Error verifying OTP: <code>{html.escape(str(e))}</code>", parse_mode="HTML")
            await state.clear()


# ============ 24-HOUR CHECK ============ #
async def check_release_payment(bot, number):
    """After 24h, notify admin to approve or reject"""
    await asyncio.sleep(86400)  # 24 hours
    sale = sales_col.find_one({"number": number, "status": "pending"})
    if not sale:
        return

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="✅ Approve", callback_data=f"approve_sell:{number}"),
        InlineKeyboardButton(text="❌ Reject", callback_data=f"reject_sell:{number}")
    )
    await bot.send_message(LOG_CHANNEL, f"⏰ 24h passed. Release payment for {number}?", reply_markup=kb.as_markup())
