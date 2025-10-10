import os
import asyncio
import datetime
import html
from bson import ObjectId
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from pymongo import MongoClient
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

from recharge_flow import register_recharge_handlers  # external recharge module
from readymade_accounts import register_readymade_accounts_handlers
from mustjoin import check_join
from config import BOT_TOKEN, ADMIN_IDS
from otp_fetcher import fetch_otp_for_number

# ===== MongoDB Setup =====
MONGO_URI = os.getenv("MONGO_URI") or "mongodb+srv://Sony:Sony123@sony0.soh6m14.mongodb.net/?retryWrites=true&w=majority&appName=Sony0"
client = MongoClient(MONGO_URI)
db = client["QuickCodes"]
users_col = db["users"]
orders_col = db["orders"]
countries_col = db["countries"]
numbers_col = db["numbers"]

# ===== Bot Setup =====
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ===== FSM for admin adding number =====
class AddNumberStates(StatesGroup):
    waiting_country = State()
    waiting_number = State()
    waiting_password = State()

class AddSession(StatesGroup):
    waiting_country = State()
    waiting_number = State()
    waiting_otp = State()
    waiting_password = State()

# ===== Helpers =====
def get_or_create_user(user_id: int, username: str | None):
    user = users_col.find_one({"_id": user_id})
    if not user:
        user = {"_id": user_id, "username": username or None, "balance": 0.0}
        users_col.insert_one(user)
    return user

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# ===== START =====
@dp.message(Command("start"))
async def cmd_start(m: Message):
    if not await check_join(bot, m):
        return

    get_or_create_user(m.from_user.id, m.from_user.username)

    text = (
        "<b>Welcome to Bot – ⚡ Fastest Telegram OTP Bot!</b>\n"
        "<i>📖 How to use Bot:</i>\n"
        "1️⃣ Recharge\n2️⃣ Select Country\n3️⃣ Buy Account and 📩 Receive OTP\n"
        "🚀 Enjoy Fast OTP Services!"
    )

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="💵 Balance", callback_data="balance"),
        InlineKeyboardButton(text="🛒 Buy Account", callback_data="buy")
    )
    kb.row(
        InlineKeyboardButton(text="💳 Recharge", callback_data="recharge"),
        InlineKeyboardButton(text="🛠️ Support", url="https://t.me/iamvalrik")
    )
    kb.row(
        InlineKeyboardButton(text="📦 Your Info", callback_data="stats"),
        InlineKeyboardButton(text="🆘 How to Use?", callback_data="howto")
    )

    menu_msg = await m.answer("Loading menu...", reply_markup=None)
    await menu_msg.edit_text(text, reply_markup=kb.as_markup())

# ===== Balance =====
@dp.callback_query(F.data=="balance")
async def show_balance(cq: CallbackQuery):
    user = users_col.find_one({"_id": cq.from_user.id})
    await cq.answer(f"💰 Balance: {user['balance']:.2f} ₹" if user else "💰 Balance: 0 ₹", show_alert=True)

@dp.message(Command("balance"))
async def cmd_balance(msg: Message):
    user = users_col.find_one({"_id": msg.from_user.id})
    await msg.answer(f"💰 Balance: {user['balance']:.2f} ₹" if user else "💰 Balance: 0 ₹")

# ===== Buy Flow =====
async def send_country_menu(message, previous=""):
    countries = list(countries_col.find({}))
    if not countries:
        return await message.edit_text("❌ No countries available. Admin must add stock first.")
    kb = InlineKeyboardBuilder()
    for c in countries:
        kb.button(text=html.escape(c["name"]), callback_data=f"country:{c['name']}")
    kb.adjust(2)
    if previous:
        kb.row(InlineKeyboardButton(text="🔙 Back", callback_data=previous))
    await message.edit_text("🌍 Select a country:", reply_markup=kb.as_markup())

@dp.callback_query(F.data=="buy")
async def callback_buy(cq: CallbackQuery):
    await cq.answer()
    await send_country_menu(cq.message, previous="start_menu")

@dp.callback_query(F.data.startswith("country:"))
async def callback_country(cq: CallbackQuery):
    await cq.answer()
    _, country_name = cq.data.split(":", 1)
    country = countries_col.find_one({"name": country_name})
    if not country:
        return await cq.answer("❌ Country not found", show_alert=True)

    text = (
        f"⚡ Telegram Account Info\n\n"
        f"🌍 Country : {html.escape(country['name'])}\n"
        f"💸 Price : ₹{country['price']}\n"
        f"📦 Available : {country['stock']}\n"
        f"🔍 Reliable | Affordable | Good Quality\n\n"
        f"⚠️ Use Telegram X only to login.\n"
        f"🚫 Not responsible for freeze/ban."
    )

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="💳 Buy Now", callback_data=f"buy_now:{country_name}"),
        InlineKeyboardButton(text="🔙 Back", callback_data="buy")
    )
    await cq.message.edit_text(text, reply_markup=kb.as_markup())

# ===== Buy Now Flow with OTP grab =====
@dp.callback_query(F.data.startswith("buy_now:"))
async def callback_buy_now(cq: CallbackQuery):
    await cq.answer()
    _, country_name = cq.data.split(":", 1)
    
    country = countries_col.find_one({"name": country_name})
    if not country:
        return await cq.answer("❌ Country not found", show_alert=True)
    
    user = get_or_create_user(cq.from_user.id, cq.from_user.username)
    
    if user["balance"] < country["price"]:
        return await cq.answer("⚠️ Insufficient balance", show_alert=True)
    
    number_doc = numbers_col.find_one({"country": country_name, "used": False})
    if not number_doc:
        return await cq.answer("❌ No available numbers for this country.", show_alert=True)
    
    # Deduct balance and mark number as used
    users_col.update_one({"_id": user["_id"]}, {"$inc": {"balance": -country["price"]}})
    numbers_col.update_one({"_id": number_doc["_id"]}, {"$set": {"used": True}})
    countries_col.update_one({"name": country_name}, {"$inc": {"stock": -1}})
    
    orders_col.insert_one({
        "user_id": user["_id"],
        "country": country_name,
        "number": number_doc["number"],
        "price": country["price"],
        "status": "purchased",
        "created_at": datetime.datetime.utcnow()
    })
    
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="🔑 Get OTP", callback_data=f"grab_otp:{str(number_doc['_id'])}")
    )
    
    text = (
        f"✅ Purchase Successful!\n\n"
        f"🌍 Country: {html.escape(country_name)}\n"
        f"📱 Your Number: {html.escape(number_doc['number'])}\n"
        f"💸 Deducted: {country['price']}\n"
        f"💰 Balance Left: {user['balance'] - country['price']:.2f}\n\n"
        "👉 Click below to get OTP when you are ready to login in Telegram."
    )
    
    await cq.message.edit_text(text, reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("grab_otp:"))
async def callback_grab_otp(cq: CallbackQuery):
    await cq.answer()
    _, number_id = cq.data.split(":", 1)
    try:
        number_doc = numbers_col.find_one({"_id": ObjectId(number_id)})
    except:
        return await cq.answer("❌ Invalid number ID.", show_alert=True)
    
    if not number_doc:
        return await cq.answer("❌ Number not found", show_alert=True)
    
    string_session = number_doc.get("string_session")
    api_id = int(os.getenv("API_ID"))
    api_hash = os.getenv("API_HASH")
    
    if not string_session:
        return await cq.answer("❌ No string session found for this number.", show_alert=True)
    
    client = TelegramClient(StringSession(string_session), api_id, api_hash)
    await client.connect()
    
    try:
        code = ""
        async for msg in client.iter_messages("777000", limit=5):
            if msg.message and msg.message.isdigit():
                code = msg.message
                break
        
        if not code:
            await cq.answer("⚠️ No OTP received yet. Try again in a few seconds.", show_alert=True)
        else:
            await cq.message.answer(
                f"🔑 OTP for {number_doc['number']}:\n<code>{code}</code>",
                parse_mode="HTML"
            )
    except SessionPasswordNeededError:
        await cq.message.answer("🔐 This account has 2FA enabled. Use the password manually.")
    except Exception as e:
        await cq.message.answer(f"❌ Failed to grab OTP: {e}")
    finally:
        await client.disconnect()

# ===== Admin Add Number =====
@dp.message(Command("add"))
async def cmd_add_start(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized.")
    countries = list(countries_col.find({}))
    if not countries:
        return await msg.answer("❌ No countries found. Add some countries first in DB.")
    kb = InlineKeyboardBuilder()
    for c in countries:
        kb.button(text=c["name"], callback_data=f"add_country:{c['name']}")
    kb.adjust(2)
    await msg.answer("🌍 Select the country you want to add a number for:", reply_markup=kb.as_markup())
    await state.set_state(AddSession.waiting_country)

@dp.callback_query(F.data.startswith("add_country:"))
async def callback_add_country(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    _, country_name = cq.data.split(":", 1)
    await state.update_data(country=country_name)
    await cq.message.answer(f"📞 Enter the phone number for {country_name} (e.g., +14151234567):")
    await state.set_state(AddSession.waiting_number)

@dp.message(AddSession.waiting_number)
async def add_number_get_code(msg: Message, state: FSMContext):
    data = await state.get_data()
    country = data["country"]
    phone = msg.text.strip()
    await state.update_data(number=phone)

    api_id = int(os.getenv("API_ID"))
    api_hash = os.getenv("API_HASH")

    session = StringSession()
    client = TelegramClient(session, api_id, api_hash)
    await client.connect()

    try:
        sent = await client.send_code_request(phone)
        await msg.answer("📩 Code sent! Please enter the OTP you received on Telegram or SMS:")
        await state.update_data(
            session=session.save(),
            phone_code_hash=sent.phone_code_hash
        )
        await client.disconnect()
        await state.set_state(AddSession.waiting_otp)
    except Exception as e:
        await client.disconnect()
        await msg.answer(f"❌ Failed to send code: {e}")

@dp.message(AddSession.waiting_otp)
async def add_number_verify_code(msg: Message, state: FSMContext):
    data = await state.get_data()
    country = data["country"]
    phone = data["number"]
    session_str = data["session"]
    phone_code_hash = data.get("phone_code_hash")

    api_id = int(os.getenv("API_ID"))
    api_hash = os.getenv("API_HASH")

    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    await client.connect()

    try:
        await client.sign_in(phone=phone, code=msg.text.strip(), phone_code_hash=phone_code_hash)
        string_session = client.session.save()
        await client.disconnect()
        numbers_col.insert_one({
            "country": country,
            "number": phone,
            "string_session": string_session,
            "used": False
        })
        countries_col.update_one({"name": country}, {"$inc": {"stock": 1}}, upsert=True)
        await msg.answer(f"✅ Added number {phone} for {country} successfully!")
        await state.clear()
    except Exception as e:
        if "PASSWORD" in str(e).upper() or "two-step" in str(e).lower():
            await msg.answer("🔐 Two-step verification is enabled. Please send the password for this account:")
            await state.update_data(session=session_str)
            await state.set_state(AddSession.waiting_password)
        else:
            await msg.answer(f"❌ Error verifying code: {e}")
            await client.disconnect()

@dp.message(AddSession.waiting_password)
async def add_number_with_password(msg: Message, state: FSMContext):
    data = await state.get_data()
    country = data["country"]
    phone = data["number"]
    session_str = data["session"]

    api_id = int(os.getenv("API_ID"))
    api_hash = os.getenv("API_HASH")

    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    await client.connect()
    try:
        await client.sign_in(password=msg.text.strip())
        string_session = client.session.save()
        await client.disconnect()
        numbers_col.insert_one({
            "country": country,
            "number": phone,
            "string_session": string_session,
            "used": False
        })
        countries_col.update_one({"name": country}, {"$inc": {"stock": 1}}, upsert=True)
        await msg.answer(f"✅ Added number {phone} (with 2FA) for {country}.")
        await state.clear()
    except Exception as e:
        await client.disconnect()
        await msg.answer(f"❌ Error signing in with password: {e}")

# ===== Admin commands: addcountry, removecountry, db =====
@dp.message(Command("addcountry"))
async def cmd_add_country(msg: Message):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized.")
    await msg.answer("🌍 Send the country name and price separated by a comma (e.g., India,50):")

@dp.message()
async def handle_add_country(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    if "," not in msg.text:
        return
    name, price = msg.text.split(",", 1)
    try:
        price = float(price.strip())
    except ValueError:
        return await msg.answer("❌ Invalid price format.")
    countries_col.update_one({"name": name.strip()}, {"$set": {"price": price, "stock": 0}}, upsert=True)
    await msg.answer(f"✅ Country {name.strip()} added/updated with price {price}.")

@dp.message(Command("removecountry"))
async def cmd_remove_country(msg: Message):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized.")
    await msg.answer("🌍 Send the country name to remove:")

@dp.message()
async def handle_remove_country(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    countries_col.delete_one({"name": msg.text.strip()})
    await msg.answer(f"✅ Country {msg.text.strip()} removed.")

@dp.message(Command("db"))
async def cmd_db(msg: Message):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized.")
    numbers = numbers_col.find({})
    text = "<b>All numbers in DB:</b>\n\n"
    for n in numbers:
        text += f"📱 {n['number']} | Country: {n['country']} | Used: {n['used']}\n"
    await msg.answer(text)

# ===== Register external handlers =====
register_readymade_accounts_handlers(dp=dp, bot=bot, users_col=users_col)
register_recharge_handlers(dp=dp, bot=bot, users_col=users_col, txns_col=db["transactions"], ADMIN_IDS=ADMIN_IDS)

# ===== Runner =====
async def main():
    print("Bot started.")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
