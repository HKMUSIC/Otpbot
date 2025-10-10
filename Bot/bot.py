import os
import re
import asyncio
import datetime
import html
from bson import ObjectId
from typing import Optional, List

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    FSInputFile,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from pymongo import MongoClient

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

# ---- External helpers (your project) ----
from mustjoin import check_join
from config import BOT_TOKEN, ADMIN_IDS

# ======= Mongo =======
MONGO_URI = os.getenv("MONGO_URI") or "mongodb://localhost:27017"
client = MongoClient(MONGO_URI)
db = client["QuickCodes"]
users_col = db["users"]
orders_col = db["orders"]
countries_col = db["countries"]
numbers_col = db["numbers"]
txns_col = db["transactions"]

# ======= Bot & Dispatcher =======
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ======= States =======
class RechargeState(StatesGroup):
    choose_method = State()
    waiting_deposit_screenshot = State()
    waiting_deposit_amount = State()
    waiting_payment_id = State()

class PurchaseState(StatesGroup):
    waiting_quantity = State()

class AddNumberStates(StatesGroup):
    waiting_country = State()
    waiting_number = State()
    waiting_otp = State()
    waiting_password = State()

class AdminAdjustBalanceState(StatesGroup):
    waiting_input = State()

# ======= Helpers =======
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def get_or_create_user_sync(user_id: int, username: Optional[str]):
    """Sync helper (call in thread) — ensures a user doc exists and returns it."""
    u = users_col.find_one({"_id": user_id})
    if not u:
        u = {"_id": user_id, "username": username or None, "balance": 0.0}
        users_col.insert_one(u)
    return u

async def get_or_create_user(user_id: int, username: Optional[str]):
    return await asyncio.to_thread(get_or_create_user_sync, user_id, username)

def stringify(obj):
    return str(obj)

# OTP extraction helper: find a 4-8 digit code in message text
_otp_re = re.compile(r"\b(\d{4,8})\b")

def extract_otp_from_text(text: str) -> Optional[str]:
    m = _otp_re.search(text)
    return m.group(1) if m else None

# ======= Start / Menu =======
async def build_main_menu_markup():
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
    return kb.as_markup()

@dp.message(Command("start"))
async def cmd_start(m: Message):
    if not await check_join(bot, m):
        return
    await asyncio.to_thread(get_or_create_user_sync, m.from_user.id, m.from_user.username)

    text = (
        "<b>Welcome to Bot – ⚡ Fastest Telegram OTP Bot!</b>\n"
        "<i>📖 How to use Bot:</i>\n"
        "1️⃣ Recharge\n2️⃣ Select Country\n3️⃣ Buy Account and 📩 Receive OTP\n"
        "🚀 Enjoy Fast OTP Services!"
    )
    menu_msg = await m.answer("Loading menu...")
    await menu_msg.edit_text(text, reply_markup=await build_main_menu_markup())

# ======= Balance =======
@dp.callback_query(F.data == "balance")
async def show_balance(cq: CallbackQuery):
    user = await asyncio.to_thread(lambda: users_col.find_one({"_id": cq.from_user.id}))
    bal = user["balance"] if user else 0.0
    await cq.answer(f"💰 Balance: ₹{bal:.2f}", show_alert=True)

@dp.message(Command("balance"))
async def cmd_balance(msg: Message):
    user = await asyncio.to_thread(lambda: users_col.find_one({"_id": msg.from_user.id}))
    bal = user["balance"] if user else 0.0
    await msg.answer(f"💰 Balance: ₹{bal:.2f}")

# ======= Start Menu (return) =======
@dp.callback_query(F.data == "start_menu")
async def callback_start_menu(cq: CallbackQuery):
    await cq.answer()
    text = (
        "<b>Welcome to Bot – ⚡ Fastest Telegram OTP Bot!</b>\n"
        "<i>📖 How to use Bot:</i>\n"
        "1️⃣ Recharge\n2️⃣ Select Country\n3️⃣ Buy Account and 📩 Receive OTP\n"
        "🚀 Enjoy Fast OTP Services!"
    )
    await cq.message.edit_text(text, reply_markup=await build_main_menu_markup())

# ======= BUY FLOW =======
async def send_country_menu(message, previous="start_menu"):
    countries = await asyncio.to_thread(lambda: list(countries_col.find({})))
    if not countries:
        return await message.edit_text("❌ No countries available. Admin must add stock first.")
    kb = InlineKeyboardBuilder()
    for c in countries:
        kb.button(text=html.escape(c["name"]), callback_data=f"country:{c['name']}")
    kb.adjust(2)
    kb.row(InlineKeyboardButton(text="🔙 Back", callback_data=previous))
    await message.edit_text("🌍 Select a country:", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "buy")
async def callback_buy(cq: CallbackQuery):
    await cq.answer()
    await send_country_menu(cq.message, previous="start_menu")

@dp.callback_query(F.data.startswith("country:"))
async def callback_country(cq: CallbackQuery):
    await cq.answer()
    _, country_name = cq.data.split(":", 1)
    country = await asyncio.to_thread(lambda: countries_col.find_one({"name": country_name}))
    if not country:
        return await cq.answer("❌ Country not found", show_alert=True)

    text = (
        f"⚡ Telegram Account Info\n\n"
        f"🌍 Country : {html.escape(country['name'])}\n"
        f"💸 Price : ₹{country['price']}\n"
        f"📦 Available : {country.get('stock', 0)}\n"
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

# ======= BUY NOW: ask quantity (stores in FSM) =======
@dp.callback_query(F.data.startswith("buy_now:"))
async def callback_buy_now(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    _, country_name = cq.data.split(":", 1)

    country = await asyncio.to_thread(lambda: countries_col.find_one({"name": country_name}))
    if not country:
        return await cq.answer("❌ Country not found", show_alert=True)

    # Save necessary details to FSM
    await state.update_data(country_name=country_name, country_price=country["price"], country_stock=country.get("stock", 0))
    await state.set_state(PurchaseState.waiting_quantity)

    await cq.message.edit_text(
        f"📦 How many {html.escape(country_name)} accounts do you want to buy?\n📝 Send only a number (e.g., 1, 5, 10)."
    )

# ======= Handle quantity message =======
@dp.message(StateFilter(PurchaseState.waiting_quantity))
async def handle_quantity(msg: Message, state: FSMContext):
    data = await state.get_data()
    country_name = data.get("country_name")
    country_price = float(data.get("country_price", 0))
    country_stock = int(data.get("country_stock", 0))

    # Validate quantity
    try:
        quantity = int(msg.text.strip())
        if quantity <= 0:
            raise ValueError
    except Exception:
        return await msg.answer("❌ Invalid number. Please send a valid integer (e.g., 1, 5).")

    total_cost = country_price * quantity

    user = await get_or_create_user(msg.from_user.id, msg.from_user.username)
    user_balance = user.get("balance", 0.0)

    if user_balance < total_cost:
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="💳 Add Funds", callback_data="recharge"))
        return await msg.answer(
            f"🚫 Insufficient Balance!\n💰 Your Balance: ₹{user_balance:.2f}\n🧾 Total Required: ₹{total_cost:.2f}",
            reply_markup=kb.as_markup()
        )

    # Check stock from DB fresh
    country = await asyncio.to_thread(lambda: countries_col.find_one({"name": country_name}))
    if not country:
        await state.clear()
        return await msg.answer("❌ Country not found (it may have been removed).")
    if country.get("stock", 0) < quantity:
        await state.clear()
        return await msg.answer(f"❌ Only {country.get('stock', 0)} account(s) left for {country_name}.")

    # Fetch unsold numbers (limit quantity)
    def fetch_numbers():
        return list(numbers_col.find({"country": country_name, "used": False}).limit(quantity))
    unsold_numbers = await asyncio.to_thread(fetch_numbers)

    if len(unsold_numbers) < quantity:
        await state.clear()
        return await msg.answer(f"❌ Only {len(unsold_numbers)} account(s) available for {country_name}.")

    # Deduct balance and mark numbers used (atomic-ish in thread)
    def commit_purchase():
        users_col.update_one({"_id": user["_id"]}, {"$inc": {"balance": -total_cost}})
        numbers_ids = []
        for n in unsold_numbers:
            numbers_ids.append(n["_id"])
            numbers_col.update_one({"_id": n["_id"]}, {"$set": {"used": True}})
            orders_col.insert_one({
                "user_id": user["_id"],
                "country": country_name,
                "number": n["number"],
                "price": country_price,
                "status": "purchased",
                "created_at": datetime.datetime.utcnow()
            })
        countries_col.update_one({"name": country_name}, {"$inc": {"stock": -len(numbers_ids)}})
        return users_col.find_one({"_id": user["_id"]})
    new_user_doc = await asyncio.to_thread(commit_purchase)
    new_balance = new_user_doc["balance"]

    # Send purchased numbers with Get OTP button (one message per number)
    for n in unsold_numbers:
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="🔑 Get OTP", callback_data=f"grab_otp:{str(n['_id'])}"))
        await msg.answer(
            f"✅ Purchased {country_name} account!\n📱 Number: {n['number']}\n💸 Deducted: ₹{country_price}\n💰 Balance Left: ₹{new_balance:.2f}",
            reply_markup=kb.as_markup()
        )

    await state.clear()

# ======= Grab OTP =======
@dp.callback_query(F.data.startswith("grab_otp:"))
async def callback_grab_otp(cq: CallbackQuery):
    await cq.answer("⏳ Fetching OTP...", show_alert=True)
    _, number_id = cq.data.split(":", 1)

    # Convert to ObjectId
    try:
        obj_id = ObjectId(number_id)
    except Exception:
        return await cq.answer("❌ Invalid number id", show_alert=True)

    number_doc = await asyncio.to_thread(lambda: numbers_col.find_one({"_id": obj_id}))
    if not number_doc:
        return await cq.answer("❌ Number not found", show_alert=True)

    string_session = number_doc.get("string_session")
    if not string_session:
        return await cq.answer("❌ No string session found for this number.", show_alert=True)

    api_id = int(os.getenv("API_ID") or 0)
    api_hash = os.getenv("API_HASH") or ""

    async def fetch_and_send():
        client = TelegramClient(StringSession(string_session), api_id, api_hash)
        await client.connect()
        try:
            found_code = None
            async for msg in client.iter_messages("777000", limit=20):
                text = getattr(msg, "message", None)
                if not text:
                    continue
                if isinstance(text, (bytes, bytearray)):
                    text = text.decode(errors="ignore")
                if not text:
                    continue
                code = extract_otp_from_text(str(text))
                if code:
                    found_code = code
                    break
            if found_code:
                await cq.message.answer(f"🔑 OTP for {number_doc['number']}:\n<code>{found_code}</code>", parse_mode="HTML")
            else:
                await cq.message.answer("⚠️ No OTP received yet. Try again in a few seconds.")
        except SessionPasswordNeededError:
            await cq.message.answer("🔐 2FA enabled for this account. Please use the password manually.")
        except Exception as e:
            await cq.message.answer(f"❌ Failed to grab OTP: {e}")
        finally:
            await client.disconnect()

    asyncio.create_task(fetch_and_send())

# ======= ADMIN: Add Number (Telethon) =======
@dp.message(Command("add"))
async def cmd_add_start(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized")
    countries = await asyncio.to_thread(lambda: list(countries_col.find({})))
    if not countries:
        return await msg.answer("❌ No countries found")
    kb = InlineKeyboardBuilder()
    for c in countries:
        kb.button(text=c["name"], callback_data=f"add_country:{c['name']}")
    kb.adjust(2)
    await msg.answer("🌍 Select country to add number:", reply_markup=kb.as_markup())
    await state.set_state(AddNumberStates.waiting_country)

@dp.callback_query(F.data.startswith("add_country:"))
async def callback_add_country(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    _, country_name = cq.data.split(":", 1)
    await state.update_data(country=country_name)
    await cq.message.answer(f"📞 Enter phone number for {country_name} (with international code, e.g. +1415...):")
    await state.set_state(AddNumberStates.waiting_number)

@dp.message(StateFilter(AddNumberStates.waiting_number))
async def add_number_get_code(msg: Message, state: FSMContext):
    data = await state.get_data()
    country = data["country"]
    phone = msg.text.strip()
    await state.update_data(number=phone)

    api_id = int(os.getenv("API_ID") or 0)
    api_hash = os.getenv("API_HASH") or ""

    session = StringSession()
    client = TelegramClient(session, api_id, api_hash)
    await client.connect()
    try:
        sent = await client.send_code_request(phone)
        await msg.answer("📩 Code sent! Enter OTP now:")
        await state.update_data(session=session.save(), phone_code_hash=sent.phone_code_hash)
        await client.disconnect()
        await state.set_state(AddNumberStates.waiting_otp)
    except Exception as e:
        await client.disconnect()
        await msg.answer(f"❌ Failed to send code: {e}")

@dp.message(StateFilter(AddNumberStates.waiting_otp))
async def add_number_verify_code(msg: Message, state: FSMContext):
    data = await state.get_data()
    country = data["country"]
    phone = data["number"]
    session_str = data.get("session")
    phone_code_hash = data.get("phone_code_hash")

    api_id = int(os.getenv("API_ID") or 0)
    api_hash = os.getenv("API_HASH") or ""

    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    await client.connect()
    try:
        await client.sign_in(phone=phone, code=msg.text.strip(), phone_code_hash=phone_code_hash)
        string_session = client.session.save()
        await client.disconnect()
        await asyncio.to_thread(lambda: numbers_col.insert_one({
            "country": country, "number": phone, "string_session": string_session, "used": False
        }))
        await asyncio.to_thread(lambda: countries_col.update_one({"name": country}, {"$inc": {"stock": 1}}, upsert=True))
        await msg.answer(f"✅ Added number {phone} for {country}")
        await state.clear()
    except Exception as e:
        if "PASSWORD" in str(e).upper() or "two-step" in str(e).lower():
            # Need password flow
            await msg.answer("🔐 Two-step enabled. Send password now:")
            await state.update_data(session=session_str)
            await state.set_state(AddNumberStates.waiting_password)
        else:
            await client.disconnect()
            await msg.answer(f"❌ Error: {e}")

@dp.message(StateFilter(AddNumberStates.waiting_password))
async def add_number_with_password(msg: Message, state: FSMContext):
    data = await state.get_data()
    country = data["country"]
    phone = data["number"]
    session_str = data["session"]

    api_id = int(os.getenv("API_ID") or 0)
    api_hash = os.getenv("API_HASH") or ""

    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    await client.connect()
    try:
        await client.sign_in(password=msg.text.strip())
        string_session = client.session.save()
        await client.disconnect()
        await asyncio.to_thread(lambda: numbers_col.insert_one({
            "country": country, "number": phone, "string_session": string_session, "used": False
        }))
        await asyncio.to_thread(lambda: countries_col.update_one({"name": country}, {"$inc": {"stock": 1}}, upsert=True))
        await msg.answer(f"✅ Added number {phone} with 2FA for {country}")
        await state.clear()
    except Exception as e:
        await client.disconnect()
        await msg.answer(f"❌ Error signing in with password: {e}")

# ======= Admin country commands =======
@dp.message(Command("addcountry"))
async def cmd_add_country(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized")
    await msg.answer("Send country and price: e.g., India,50")
    await state.set_state("adding_country")

@dp.message(StateFilter("adding_country"))
async def handle_add_country(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    if "," not in msg.text:
        return await msg.answer("❌ Invalid format. Example: India,50")
    name, price = msg.text.split(",", 1)
    try:
        price = float(price.strip())
    except Exception:
        return await msg.answer("❌ Invalid price")
    await asyncio.to_thread(lambda: countries_col.update_one({"name": name.strip()}, {"$set": {"price": price, "stock": 0}}, upsert=True))
    await msg.answer(f"✅ Country {name.strip()} added/updated: ₹{price}")
    await state.clear()

@dp.message(Command("removecountry"))
async def cmd_remove_country(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized")
    await msg.answer("Send country name to remove:")
    await state.set_state("removing_country")

@dp.message(StateFilter("removing_country"))
async def handle_remove_country(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    result = await asyncio.to_thread(lambda: countries_col.delete_one({"name": msg.text.strip()}))
    if result.deleted_count == 0:
        await msg.answer(f"❌ Country {msg.text.strip()} not found.")
    else:
        await msg.answer(f"✅ Country {msg.text.strip()} removed.")
    await state.clear()

@dp.message(Command("db"))
async def cmd_db(msg: Message):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized")
    numbers = await asyncio.to_thread(lambda: list(numbers_col.find({})))
    if not numbers:
        return await msg.answer("❌ No numbers in DB.")
    text = "<b>All numbers in DB:</b>\n\n"
    for n in numbers:
        text += f"📱 {n['number']} | Country: {n['country']} | Used: {n.get('used', False)}\n"
        if len(text) > 3000:
            await msg.answer(text)
            text = ""
    if text:
        await msg.answer(text)

# ======= Admin credit/debit =======
@dp.message(Command("credit"))
async def cmd_credit(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return await msg.answer("❌ Not authorized")
    await msg.answer("Send user_id and amount: e.g., 123456,50")
    await state.set_state(AdminAdjustBalanceState.waiting_input)
    await state.update_data(action="credit")

@dp.message(Command("debit"))
async def cmd_debit(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return await msg.answer("❌ Not authorized")
    await msg.answer("Send user_id and amount: e.g., 123456,50")
    await state.set_state(AdminAdjustBalanceState.waiting_input)
    await state.update_data(action="debit")

@dp.message(StateFilter(AdminAdjustBalanceState.waiting_input))
async def handle_adjust_balance(msg: Message, state: FSMContext):
    data = await state.get_data()
    action = data.get("action")
    if "," not in msg.text:
        return await msg.answer("❌ Invalid format")
    uid_str, amt_str = msg.text.split(",", 1)
    try:
        user_id = int(uid_str.strip())
        amount = float(amt_str.strip())
    except Exception:
        return await msg.answer("❌ Invalid values")
    user = await asyncio.to_thread(lambda: users_col.find_one({"_id": user_id}))
    if not user:
        return await msg.answer("❌ User not found")
    if action == "credit":
        await asyncio.to_thread(lambda: users_col.update_one({"_id": user_id}, {"$inc": {"balance": amount}}))
        new_balance = user["balance"] + amount
    else:
        new_balance = max(user["balance"] - amount, 0.0)
        await asyncio.to_thread(lambda: users_col.update_one({"_id": user_id}, {"$set": {"balance": new_balance}}))
    await msg.answer(f"✅ {action.capitalize()}ed ₹{amount:.2f}. New balance: ₹{new_balance:.2f}")
    await state.clear()

# ======= RECHARGE FLOW (integrated) =======
@dp.callback_query(F.data == "recharge")
async def recharge_start_button(cq: CallbackQuery, state: FSMContext):
    # starts the recharge flow and stores main message id
    kb = InlineKeyboardBuilder()
    kb.button(text="Pay Manually", callback_data="recharge_manual")
    kb.button(text="Automatic", callback_data="recharge_auto")
    kb.adjust(2)

    text = (
        "💰 Add Funds to Your Account\n\n"
        "We only accept payments via UPI.\n\n"
        "Please choose a method below:"
    )
    msg = await cq.message.answer(text, reply_markup=kb.as_markup())
    await state.update_data(recharge_msg_id=msg.message_id)
    await state.set_state(RechargeState.choose_method)
    await cq.answer()

@dp.message(Command("recharge"))
async def recharge_start_command(msg: Message, state: FSMContext):
    if not await check_join(bot, msg):
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="Pay Manually", callback_data="recharge_manual")
    kb.button(text="Automatic", callback_data="recharge_auto")
    kb.adjust(2)
    text = (
        "💰 Add Funds to Your Account\n\n"
        "We only accept payments via UPI.\n\n"
        "Please choose a method below:"
    )
    reply = await msg.answer(text, reply_markup=kb.as_markup())
    await state.update_data(recharge_msg_id=reply.message_id)
    await state.set_state(RechargeState.choose_method)

@dp.callback_query(F.data == "recharge_manual", StateFilter(RechargeState.choose_method))
async def recharge_manual(cq: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    msg_id = data.get("recharge_msg_id")
    kb = InlineKeyboardBuilder()
    kb.button(text="Deposit Now", callback_data="deposit_now")
    kb.button(text="Go Back", callback_data="go_back_recharge")
    kb.adjust(2)
    text = (
        f"👋 Hello {cq.from_user.full_name},\n\n"
        "You selected manual payment. Click Deposit Now when ready."
    )
    # try to edit original message if exists; otherwise send a new one
    try:
        await bot.edit_message_text(chat_id=cq.from_user.id, message_id=msg_id, text=text, reply_markup=kb.as_markup())
    except Exception:
        await cq.message.answer(text, reply_markup=kb.as_markup())
    await cq.answer()

@dp.callback_query(F.data == "go_back_recharge", StateFilter(RechargeState.choose_method))
async def go_back_recharge(cq: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    msg_id = data.get("recharge_msg_id")
    kb = InlineKeyboardBuilder()
    kb.button(text="Pay Manually", callback_data="recharge_manual")
    kb.button(text="Automatic", callback_data="recharge_auto")
    kb.adjust(2)
    text = (
        "💰 Add Funds to Your Account\n\n"
        "We only accept payments via UPI.\n\n"
        "Please choose a method below:"
    )
    try:
        await bot.edit_message_text(chat_id=cq.from_user.id, message_id=msg_id, text=text, reply_markup=kb.as_markup())
    except Exception:
        await cq.message.answer(text, reply_markup=kb.as_markup())
    await cq.answer()

@dp.callback_query(F.data == "deposit_now", StateFilter(RechargeState.choose_method))
async def deposit_now(cq: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    msg_id = data.get("recharge_msg_id")
    # delete previous if possible
    try:
        await bot.delete_message(chat_id=cq.from_user.id, message_id=msg_id)
    except Exception:
        pass

    qr_file = FSInputFile("IMG_20251008_085640_972.jpg")
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ I've Paid", callback_data="paid_done")
    kb.adjust(1)
    caption = (
        "🔝 Send your payment to this UPI:\n<pre>itsakt5@ptyes</pre>\n\n"
        "Or scan the QR below 👇\n\n"
        "✅ After paying, click 'I've Paid'."
    )
    msg = await cq.message.answer_photo(photo=qr_file, caption=caption, parse_mode="HTML", reply_markup=kb.as_markup())
    await state.update_data(recharge_msg_id=msg.message_id)
    await cq.answer()

@dp.callback_query(F.data == "paid_done", StateFilter(RechargeState.choose_method))
async def paid_done(cq: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    qr_msg_id = data.get("recharge_msg_id")
    try:
        await bot.delete_message(chat_id=cq.from_user.id, message_id=qr_msg_id)
    except Exception:
        pass
    await cq.message.answer("📸 Please send a screenshot of your payment.")
    await state.set_state(RechargeState.waiting_deposit_screenshot)
    await cq.answer()

@dp.message(StateFilter(RechargeState.waiting_deposit_screenshot), F.photo)
async def screenshot_received(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    await state.update_data(screenshot=file_id)
    await message.answer("💰 Enter the amount you sent (integers only):")
    await state.set_state(RechargeState.waiting_deposit_amount)

@dp.message(StateFilter(RechargeState.waiting_deposit_amount), F.text)
async def amount_received(message: Message, state: FSMContext):
    amount_text = message.text.strip()
    if not amount_text.isdigit():
        return await message.answer("❌ Invalid amount. Enter integers only (e.g., 100).")
    amount = int(amount_text)
    await state.update_data(amount=amount)

    # Add amount to user's balance immediately (requested)
    user_id = message.from_user.id

    def add_balance():
        u = users_col.find_one({"_id": user_id})
        if not u:
            users_col.insert_one({"_id": user_id, "username": message.from_user.username or None, "balance": float(amount)})
            return float(amount)
        else:
            users_col.update_one({"_id": user_id}, {"$inc": {"balance": float(amount)}})
            u2 = users_col.find_one({"_id": user_id})
            return float(u2.get("balance", 0.0))
    new_balance = await asyncio.to_thread(add_balance)

    await message.answer(f"✅ ₹{amount} has been added to your balance (pending admin verification). Current balance: ₹{new_balance:.2f}\n\n🔑 Please send your Payment ID / UTR:")
    await state.set_state(RechargeState.waiting_payment_id)

@dp.message(StateFilter(RechargeState.waiting_payment_id), F.text)
async def payment_id_received(message: Message, state: FSMContext):
    data = await state.get_data()
    screenshot = data.get("screenshot")
    amount = data.get("amount")
    payment_id = message.text.strip()
    user_id = message.from_user.id
    username = message.from_user.username or "None"
    full_name = message.from_user.full_name

    txn_doc = {
        "user_id": user_id,
        "username": username,
        "full_name": full_name,
        "amount": amount,
        "payment_id": payment_id,
        "screenshot": screenshot,
        "status": "pending",
        "created_at": datetime.datetime.utcnow()
    }
    txn_id = await asyncio.to_thread(lambda: txns_col.insert_one(txn_doc).inserted_id)

    await message.answer("✅ Your payment request has been sent to the admin. Please wait for approval.")
    await state.clear()

    # Notify admins
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Approve", callback_data=f"approve_txn:{str(txn_id)}")
    kb.button(text="❌ Decline", callback_data=f"decline_txn:{str(txn_id)}")
    kb.adjust(2)

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_photo(
                chat_id=admin_id,
                photo=screenshot,
                caption=(
                    f"<b>Payment Approval Request</b>\n\n"
                    f"Name: {full_name}\n"
                    f"Username: @{username}\n"
                    f"ID: {user_id}\n"
                    f"Amount: ₹{amount}\n"
                    f"UTR / Payment ID: {payment_id}"
                ),
                parse_mode="HTML",
                reply_markup=kb.as_markup()
            )
        except Exception:
            pass

# ======= Admin approve/decline handlers (for txns) =======
@dp.callback_query(F.data.startswith("approve_txn:"))
async def approve_txn(cq: CallbackQuery):
    await cq.answer()
    _, txn_id_str = cq.data.split(":", 1)
    try:
        txn_obj = txns_col.find_one({"_id": ObjectId(txn_id_str)})
    except Exception:
        return await cq.answer("❌ Invalid txn id", show_alert=True)
    if not txn_obj:
        return await cq.answer("❌ Transaction not found", show_alert=True)

    # mark approved
    txns_col.update_one({"_id": txn_obj["_id"]}, {"$set": {"status": "approved", "approved_by": cq.from_user.id, "approved_at": datetime.datetime.utcnow()}})
    # notify user
    try:
        await bot.send_message(txn_obj["user_id"], f"✅ Your payment of ₹{txn_obj['amount']} has been approved by admin.")
    except Exception:
        pass
    await cq.message.answer("✅ Transaction approved.")

@dp.callback_query(F.data.startswith("decline_txn:"))
async def decline_txn(cq: CallbackQuery):
    await cq.answer()
    _, txn_id_str = cq.data.split(":", 1)
    try:
        txn_obj = txns_col.find_one({"_id": ObjectId(txn_id_str)})
    except Exception:
        return await cq.answer("❌ Invalid txn id", show_alert=True)
    if not txn_obj:
        return await cq.answer("❌ Transaction not found", show_alert=True)

    # mark declined
    txns_col.update_one({"_id": txn_obj["_id"]}, {"$set": {"status": "declined", "declined_by": cq.from_user.id, "declined_at": datetime.datetime.utcnow()}})

    # refund the balance we added earlier
    def refund():
        users_col.update_one({"_id": txn_obj["user_id"]}, {"$inc": {"balance": -float(txn_obj["amount"])}})
    await asyncio.to_thread(refund)

    try:
        await bot.send_message(txn_obj["user_id"], f"❌ Your payment of ₹{txn_obj['amount']} was declined by admin. Amount has been reverted.")
    except Exception:
        pass
    await cq.message.answer("✅ Transaction declined and refunded.")

# ======= Runner =======
async def main():
    print("Bot started.")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
