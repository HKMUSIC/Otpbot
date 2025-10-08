import os
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, Text
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from pymongo import MongoClient
from telethon import TelegramClient
from telethon.sessions import StringSession

from config import BOT_TOKEN, ADMIN_IDS

# ===== MongoDB Setup =====
MONGO_URI = os.getenv("MONGO_URI") or "mongodb+srv://Sony:Sony123@sony0.soh6m14.mongodb.net/?retryWrites=true&w=majority&appName=Sony0"
client = MongoClient(MONGO_URI)
db = client["QuickCodes"]
countries_col = db["countries"]
numbers_col = db["numbers"]

# ===== Bot Setup =====
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ===== Helpers =====
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

admin_sessions = {}  # Temporarily store the flow: {user_id: {"step":..., "country":..., "number":..., "password":...}}

# ===== /addnumber Command =====
@dp.message(Command("addnumber"))
async def cmd_add_number(msg: Message):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized")

    countries = list(countries_col.find({}))
    if not countries:
        return await msg.answer("❌ No countries available. Add country first.")

    kb = InlineKeyboardBuilder()
    for c in countries:
        kb.button(c["name"], callback_data=f"addnumber_country:{c['name']}")
    kb.adjust(2)
    await msg.answer("Select country to add number:", reply_markup=kb.as_markup())

# ===== Select Country =====
@dp.callback_query(F.data.startswith("addnumber_country:"))
async def callback_addnumber_country(cq: CallbackQuery):
    await cq.answer()
    _, country_name = cq.data.split(":")
    admin_sessions[cq.from_user.id] = {"step": "number", "country": country_name}
    await cq.message.answer(f"📱 Enter the Telegram number for {country_name} (with +country code):")

# ===== Capture Number =====
@dp.message()
async def capture_number(msg: Message):
    session = admin_sessions.get(msg.from_user.id)
    if not session: return

    if session["step"] == "number":
        session["number"] = msg.text.strip()
        session["step"] = "password"
        return await msg.answer(f"🔑 Enter password for {session['number']}:")

    if session["step"] == "password":
        session["password"] = msg.text.strip()
        session["step"] = "otp"
        return await msg.answer(f"📩 Enter OTP received on {session['number']}:")

    if session["step"] == "otp":
        otp = msg.text.strip()
        session["otp"] = otp
        await msg.answer("⏳ Generating String Session...")
        # Generate string session
        try:
            from config import API_ID, API_HASH
            client = TelegramClient(StringSession(), API_ID, API_HASH)
            await client.start(phone=session["number"], password=session["password"], code_callback=lambda: otp)
            string_sess = client.session.save()
            await client.disconnect()

            # Save to DB
            numbers_col.insert_one({
                "country": session["country"],
                "number": session["number"],
                "password": session["password"],
                "string_session": string_sess,
                "used": False,
            })
            await msg.answer(f"✅ Number added successfully for {session['country']}!\nNumber: {session['number']}")
        except Exception as e:
            await msg.answer(f"❌ Failed to generate string session: {e}")
        finally:
            admin_sessions.pop(msg.from_user.id, None)
