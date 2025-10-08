import os
import asyncio
import datetime
import html
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from pymongo import MongoClient

from readymade_accounts import register_readymade_accounts_handlers
from mustjoin import check_join
from config import BOT_TOKEN, ADMIN_IDS, DEFAULT_CURRENCY, MIN_BALANCE_REQUIRED
from otp_fetcher import fetch_otp_for_number  # Separate OTP fetching module

# ===== MongoDB Setup =====
MONGO_URI = os.getenv("MONGO_URI") or "mongodb+srv://Sony:Sony123@sony0.soh6m14.mongodb.net/?retryWrites=true&w=majority&appName=Sony0"
client = MongoClient(MONGO_URI)
db = client["QuickCodes"]
users_col = db["users"]
orders_col = db["orders"]
countries_col = db["countries"]
numbers_col = db["numbers"]  # Each number with string session, password, used status

# ===== Bot Setup =====
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

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
        InlineKeyboardButton("💵 Balance", callback_data="balance"),
        InlineKeyboardButton("🛒 Buy Account", callback_data="buy")
    )
    kb.row(
        InlineKeyboardButton("💳 Recharge", callback_data="recharge"),
        InlineKeyboardButton("🛠️ Support", url="https://t.me/iamvalrik")
    )
    kb.row(
        InlineKeyboardButton("📦 Your Info", callback_data="stats"),
        InlineKeyboardButton("🆘 How to Use?", callback_data="howto")
    )
    await m.answer(text, reply_markup=kb.as_markup())

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
@dp.callback_query(F.data=="buy")
async def callback_buy(cq: CallbackQuery):
    await cq.answer()
    countries = list(countries_col.find({}))
    if not countries:
        return await cq.message.answer("❌ No countries available. Admin must add stock first.")

    kb = InlineKeyboardBuilder()
    for c in countries:
        kb.button(html.escape(c["name"]), callback_data=f"country:{c['name']}")
    kb.adjust(2)
    await cq.message.answer("🌍 Select a country:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("country:"))
async def callback_country(cq: CallbackQuery):
    await cq.answer()
    _, country_name = cq.data.split(":")
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
        InlineKeyboardButton("💳 Buy Now", callback_data=f"buy_now:{country_name}"),
        InlineKeyboardButton("🔙 Back", callback_data="buy")
    )
    await cq.message.answer(text, reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("buy_now:"))
async def callback_buy_now(cq: CallbackQuery):
    await cq.answer()
    _, country_name = cq.data.split(":")
    country = countries_col.find_one({"name": country_name})
    if not country or country["stock"] <= 0:
        return await cq.answer("❌ Out of stock or country not found", show_alert=True)

    user = get_or_create_user(cq.from_user.id, cq.from_user.username)
    if user["balance"] < country["price"]:
        return await cq.answer("⚠️ Insufficient balance", show_alert=True)

    # Pick first available number
    number_doc = numbers_col.find_one({"country": country_name, "used": False})
    if not number_doc:
        return await cq.answer("❌ No available numbers for this country.", show_alert=True)

    # Deduct balance and mark number as used
    users_col.update_one({"_id": user["_id"]}, {"$inc": {"balance": -country["price"]}})
    numbers_col.update_one({"_id": number_doc["_id"]}, {"$set": {"used": True}})
    countries_col.update_one({"name": country_name}, {"$inc": {"stock": -1}})

    # Insert order
    orders_col.insert_one({
        "user_id": user["_id"],
        "country": country_name,
        "number": number_doc["number"],
        "price": country["price"],
        "status": "purchased",
        "created_at": datetime.datetime.utcnow()
    })

    text = (
        f"✅ Purchase Successful!\n\n"
        f"🌍 Country: {html.escape(country_name)}\n"
        f"📱 Number: {html.escape(number_doc['number'])}\n"
        f"💸 Deducted: {country['price']}\n"
        f"💰 Balance Left: {user['balance'] - country['price']:.2f}\n\n"
        "👉 Copy the number and open Telegram X, paste the number, request login."
    )

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton("📋 Copy Number", callback_data=f"copy_number:{number_doc['number']}"),
        InlineKeyboardButton("🔑 Get OTP", callback_data=f"get_otp:{number_doc['_id']}")
    )
    await cq.message.answer(text, reply_markup=kb.as_markup())

# ===== Get OTP =====
@dp.callback_query(F.data.startswith("get_otp:"))
async def callback_get_otp(cq: CallbackQuery):
    await cq.answer()
    _, number_id = cq.data.split(":")
    number_doc = numbers_col.find_one({"_id": number_id})
    if not number_doc:
        return await cq.answer("❌ Number not found", show_alert=True)

    otp = await fetch_otp_for_number(number_doc)
    if not otp:
        return await cq.answer("❌ Failed to fetch OTP. Try again.", show_alert=True)

    text = (
        f"🚚 OTP Delivered Successfully!\n\n"
        f"📱 {html.escape(number_doc['number'])}\n"
        f"🔑 OTP: {otp}\n"
        f"PASS: {html.escape(number_doc['password'])}\n\n"
        "⚠️ This message will be deleted after 3 minutes.\n"
        "👉 Enter this OTP in Telegram X. Max 2 attempts."
    )
    await cq.message.answer(text)
    numbers_col.delete_one({"_id": number_doc["_id"]})
    await asyncio.sleep(180)
    await cq.message.delete()

# ===== Admin: Add Stock =====
@dp.message(Command("addstock"))
async def cmd_add_stock(msg: Message):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized")
    try:
        _, country_name, price, stock = msg.text.split()
        price = float(price)
        stock = int(stock)
    except Exception:
        return await msg.answer("Usage: /addstock <Country> <Price> <Stock>")

    countries_col.update_one(
        {"name": country_name},
        {"$set": {"price": price}, "$inc": {"stock": stock}},
        upsert=True
    )
    await msg.answer(f"✅ {stock} accounts added for {country_name} at ₹{price} each.")

# ===== Admin: Add Numbers =====
@dp.message(Command("addnumber"))
async def cmd_add_number(msg: Message):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized")
    try:
        _, country_name, number, password = msg.text.split()
    except Exception:
        return await msg.answer("Usage: /addnumber <Country> <Number> <Password>")

    numbers_col.insert_one({
        "country": country_name,
        "number": number,
        "password": password,
        "used": False
    })
    # Ensure country exists
    countries_col.update_one({"name": country_name}, {"$setOnInsert": {"stock": 0, "price": 0}}, upsert=True)
    await msg.answer(f"✅ Number {number} added for {country_name}.")

# ===== Admin: View/Delete Stock =====
@dp.message(Command("viewstock"))
async def cmd_view_stock(msg: Message):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized")
    kb = InlineKeyboardBuilder()
    for c in countries_col.find({}):
        kb.button(c["name"], callback_data=f"viewstock_country:{c['name']}")
    kb.adjust(2)
    await msg.answer("Select country to view stock:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("viewstock_country:"))
async def callback_view_stock_country(cq: CallbackQuery):
    await cq.answer()
    _, country_name = cq.data.split(":")
    numbers = list(numbers_col.find({"country": country_name, "used": False}))
    if not numbers:
        return await cq.message.answer("❌ No stock for this country.")

    msg_text = f"📦 Available numbers for {country_name}:\n"
    for n in numbers:
        msg_text += f"{n['number']} | PASS: {n['password']} | Used: {n.get('used', False)}\n"
    await cq.message.answer(msg_text)

@dp.message(Command("deletestock"))
async def cmd_delete_stock(msg: Message):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized")
    try:
        _, country_name = msg.text.split()
    except Exception:
        return await msg.answer("Usage: /deletestock <Country>")
    numbers_col.delete_many({"country": country_name, "used": False})
    await msg.answer(f"✅ All unused stock deleted for {country_name}.")

# ===== How To Use =====
@dp.callback_query(F.data=="howto")
async def callback_howto(cq: CallbackQuery):
    if not await check_join(bot, cq.message): return
    await cq.message.answer("📖 How to use: Recharge → Select Country → Buy → Get OTP")
    await cq.answer()

# ===== Stats =====
@dp.message(Command("stats"))
async def cmd_stats(msg: Message):
    if not await check_join(bot, msg): return
    user = users_col.find_one({"_id": msg.from_user.id})
    if not user: return await msg.answer("❌ No data found")
    await msg.answer(f"📊 Balance: ₹{user.get('balance', 0):.2f}")

@dp.callback_query(F.data=="stats")
async def callback_stats(cq: CallbackQuery):
    user = users_col.find_one({"_id": cq.from_user.id})
    if not user: return await cq.answer("❌ No data found", show_alert=True)
    await cq.message.answer(f"📊 Balance: ₹{user.get('balance', 0):.2f}")
    await cq.answer()

# ===== Support =====
@dp.message(Command("support"))
async def cmd_support(msg: Message):
    if not await check_join(bot, msg): return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("💬 Contact Support", url="https://t.me/hehe_stalker")]
    ])
    await msg.answer(f"👋 {msg.from_user.full_name}, contact support if needed.", reply_markup=kb)

# ===== Register external handlers =====
register_readymade_accounts_handlers(dp=dp, bot=bot, users_col=users_col)

# ===== Runner =====
async def main():
    print("Bot started.")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
