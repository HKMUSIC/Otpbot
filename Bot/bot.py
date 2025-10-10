import os
import datetime
import html
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.executor import start_polling
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from pymongo import MongoClient
from bson import ObjectId
from telethon import TelegramClient
from telethon.sessions import StringSession

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
ADMIN_IDS = [int(i) for i in os.getenv("ADMIN_IDS", "").split(",") if i]
ORDER_CHANNEL_ID = os.getenv("ORDER_CHANNEL_ID")  # Channel ID as string, e.g., "-1001234567890"

MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["QuickCodes"]
users_col = db["users"]
orders_col = db["orders"]
countries_col = db["countries"]
numbers_col = db["numbers"]

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())

# FSM States
class AddNumberStates(StatesGroup):
    waiting_country = State()
    waiting_number = State()
    waiting_otp = State()
    waiting_password = State()

class AdminAdjustBalanceState(StatesGroup):
    waiting_input = State()

# Helpers
def is_admin(user_id):
    return user_id in ADMIN_IDS

def get_or_create_user(user_id, username):
    user = users_col.find_one({"_id": user_id})
    if not user:
        user = {"_id": user_id, "username": username, "balance": 0.0}
        users_col.insert_one(user)
    return user

# Start/Welcome
@dp.message_handler(commands="start")
async def cmd_start(m: Message):
    get_or_create_user(m.from_user.id, m.from_user.username)
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("💵 Balance", callback_data="balance"),
        InlineKeyboardButton("🛒 Buy Account", callback_data="buy"),
        InlineKeyboardButton("💳 Recharge", callback_data="recharge"),
        InlineKeyboardButton("🛠️ Support", url="https://t.me/iamvalrik"),
        InlineKeyboardButton("📦 Your Info", callback_data="stats"),
        InlineKeyboardButton("🆘 How to Use?", callback_data="howto")
    )
    await m.answer(
        "<b>Welcome to Bot – ⚡ Fastest Telegram OTP Bot!</b>\n\n"
        "<i>📖 How to use Bot:</i>\n"
        "1️⃣ Recharge\n2️⃣ Select Country\n3️⃣ Buy Account and 📩 Receive OTP\n"
        "🚀 Enjoy Fast OTP Services!",
        reply_markup=kb
    )

# Balance
@dp.callback_query_handler(lambda c: c.data == "balance")
async def show_balance(cq: CallbackQuery):
    user = users_col.find_one({"_id": cq.from_user.id})
    await cq.answer(f"💰 Balance: {user['balance']:.2f} ₹" if user else "💰 Balance: 0 ₹", show_alert=True)

# Countries Menu
def country_menu_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    countries = list(countries_col.find({}))
    for c in countries:
        kb.add(InlineKeyboardButton(c["name"], callback_data=f"country_{c['name']}"))
    kb.add(InlineKeyboardButton("🔙 Back", callback_data="main"))
    return kb

@dp.callback_query_handler(lambda c: c.data == "buy")
async def callback_buy(cq: CallbackQuery):
    await cq.message.edit_text("🌍 Select a country:", reply_markup=country_menu_keyboard())

@dp.callback_query_handler(lambda c: c.data.startswith("country_"))
async def callback_country(cq: CallbackQuery):
    country_name = cq.data.split("_", 1)[1]
    country = countries_col.find_one({"name": country_name})
    if not country:
        await cq.answer("❌ Country not found", show_alert=True)
        return
    price = country.get("price", 0)
    stock = numbers_col.count_documents({"country": country_name, "used": False})
    text = (
        f"⚡ Telegram Account Info\n\n"
        f"🌍 Country: {html.escape(country_name)}\n"
        f"💸 Price: ₹{price}\n"
        f"📦 Available: {stock}\n"
        "🔍 Reliable | Affordable | Good Quality\n\n"
        "⚠️ Use Telegram X only to login.\n"
        "🚫 Not responsible for freeze/ban."
    )
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("💳 Buy Now", callback_data=f"buy_now_{country_name}"),
        InlineKeyboardButton("🔙 Back", callback_data="buy")
    )
    await cq.message.edit_text(text, reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("buy_now_"))
async def callback_buy_now(cq: CallbackQuery):
    country_name = cq.data.split("_", 2)[2]
    country = countries_col.find_one({"name": country_name})
    user = get_or_create_user(cq.from_user.id, cq.from_user.username)
    price = country.get("price", 0)
    stock = numbers_col.count_documents({"country": country_name, "used": False})
    if stock <= 0:
        await cq.answer("❌ Stock not available", show_alert=True)
        return
    if user["balance"] < price:
        await cq.answer("⚠️ Insufficient balance", show_alert=True)
        return
    number_doc = numbers_col.find_one({"country": country_name, "used": False})
    if not number_doc:
        await cq.answer("❌ No available numbers", show_alert=True)
        return
    # Deduct balance, mark number as used, log order
    users_col.update_one({"_id": user["_id"]}, {"$inc": {"balance": -price}})
    numbers_col.update_one({"_id": number_doc["_id"]}, {"$set": {"used": True}})
    orders_col.insert_one({
        "user_id": user["_id"],
        "country": country_name,
        "number": number_doc["number"],
        "price": price,
        "status": "purchased",
        "created_at": datetime.datetime.utcnow()
    })
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🔑 Get OTP", callback_data=f"grab_otp_{number_doc['_id']}_1"),
        InlineKeyboardButton("🔙 Back", callback_data="buy")
    )
    await cq.message.edit_text(
        f"✅ Purchase Successful!\n"
        f"🌍 {country_name}\n"
        f"📱 {number_doc['number']}\n"
        f"💸 {price}\n"
        f"💰 Balance Left: {user['balance']-price:.2f}\n"
        "👉 Click below to get OTP.",
        reply_markup=kb
    )
    # Notify channel/admin
    try:
        if ORDER_CHANNEL_ID:
            await bot.send_message(
                int(ORDER_CHANNEL_ID),
                f"📦 Order Completed!\n"
                f"👤 User: {cq.from_user.full_name} (@{cq.from_user.username})\n"
                f"🌍 Country: {number_doc['country']}\n"
                f"📱 Number: {number_doc['number']}\n"
                f"💸 Price: ₹{price}"
            )
    except Exception:
        pass

# OTP Retrieval with 3 tries
@dp.callback_query_handler(lambda c: c.data.startswith("grab_otp_"))
async def callback_grab_otp(cq: CallbackQuery):
    parts = cq.data.split("_")
    number_id = parts[2]
    tries = int(parts[3]) if len(parts) > 3 else 1
    number_doc = numbers_col.find_one({"_id": ObjectId(number_id)})
    if not number_doc:
        await cq.answer("❌ Number not found", show_alert=True)
        return
    string_session = number_doc.get("string_session")
    if not string_session:
        await cq.answer("❌ String session missing", show_alert=True)
        return
    client = TelegramClient(StringSession(string_session), API_ID, API_HASH)
    await client.connect()
    otp_code = None
    try:
        async for msg in client.iter_messages("777000", limit=10):
            if msg.message and msg.message.isdigit():
                otp_code = msg.message
                break
        if otp_code:
            await cq.message.edit_text(
                f"✅ OTP Received!\n📱 {number_doc['number']}\n🔑 OTP: <code>{otp_code}</code>",
                parse_mode="HTML"
            )
        elif tries < 3:
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton(f"Try Again ({tries+1}/3)", callback_data=f"grab_otp_{number_id}_{tries+1}"))
            await cq.message.edit_text("❌ OTP not received yet. Click below to try again.", reply_markup=kb)
        else:
            await cq.message.edit_text("❌ Failed to retrieve OTP after 3 tries. DM the owner for help.")
    finally:
        await client.disconnect()

# Admin: Add Country
@dp.message_handler(commands=["addcountry"])
async def cmd_add_country(msg: Message):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized")
    await msg.answer("Send country and price: e.g., India,50")

@dp.message_handler(lambda m: is_admin(m.from_user.id) and "," in m.text)
async def handle_add_country(msg: Message):
    name, price = msg.text.split(",", 1)
    try: price = float(price.strip())
    except: return await msg.answer("❌ Invalid price")
    countries_col.update_one({"name": name.strip()}, {"$set": {"price": price}}, upsert=True)
    await msg.answer(f"✅ Country {name.strip()} added/updated: ₹{price}")

# Admin: Remove Country
@dp.message_handler(commands=["removecountry"])
async def cmd_remove_country(msg: Message):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized")
    countries = list(countries_col.find({}))
    if not countries:
        return await msg.answer("❌ No countries to remove.")
    kb = InlineKeyboardMarkup(row_width=2)
    for c in countries:
        kb.add(InlineKeyboardButton(c["name"], callback_data=f"rem_country_{c['name']}"))
    await msg.answer("Select country to remove:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("rem_country_"))
async def callback_remove_country(cq: CallbackQuery):
    country = cq.data.split("_", 2)[2]
    countries_col.delete_one({"name": country})
    await cq.message.edit_text(f"✅ Country {country} removed.")

# Admin: Credit/Debit
@dp.message_handler(commands=["credit"])
async def cmd_credit(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized")
    await msg.answer("Send user_id and amount: e.g., 123456,50")
    await AdminAdjustBalanceState.waiting_input.set()
    await state.update_data(action="credit")

@dp.message_handler(commands=["debit"])
async def cmd_debit(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized")
    await msg.answer("Send user_id and amount: e.g., 123456,50")
    await AdminAdjustBalanceState.waiting_input.set()
    await state.update_data(action="debit")

@dp.message_handler(state=AdminAdjustBalanceState.waiting_input)
async def handle_adjust_balance(msg: Message, state: FSMContext):
    data = await state.get_data()
    action = data.get("action")
    if "," not in msg.text:
        return await msg.answer("❌ Invalid format")
    uid_str, amt_str = msg.text.split(",", 1)
    try:
        user_id = int(uid_str.strip())
        amount = float(amt_str.strip())
    except:
        return await msg.answer("❌ Invalid values")
    user = users_col.find_one({"_id": user_id})
    if not user:
        return await msg.answer("❌ User not found")
    if action == "credit":
        new_balance = user["balance"] + amount
    else:
        new_balance = max(user["balance"] - amount, 0)
    users_col.update_one({"_id": user_id}, {"$set": {"balance": new_balance}})
    await msg.answer(f"✅ {action.capitalize()}ed ₹{amount:.2f}. New balance: ₹{new_balance:.2f}")
    await state.finish()

if __name__ == "__main__":
    print("Bot started.")
    start_polling(dp, skip_updates=True)
