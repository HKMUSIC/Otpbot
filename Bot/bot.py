import os
import asyncio
import html
from aiogram.fsm.context import FSMContext
from datetime import datetime, timezone
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
from aiogram.utils.deep_linking import create_start_link
import re
from aiogram import types
import random
from aiogram.types import InputMediaVideo
from recharge_flow import register_recharge_handlers
from mustjoin import check_join
from config import BOT_TOKEN, ADMIN_IDS

# ================= MongoDB Setup =================
MONGO_URI = os.getenv("MONGO_URI") or "mongodb+srv://Hkbots:hk123@gamechanger0.ck6qqyl.mongodb.net/?retryWrites=true&w=majority&appName=Gamechanger0"
client = MongoClient(MONGO_URI)
db = client["QuickCodes"]
users_col = db["users"]
orders_col = db["orders"]
countries_col = db["countries"]
numbers_col = db["numbers"]

# ================= Bot Setup =================
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ================= FSM =================
class AddSession(StatesGroup):
    waiting_country = State()
    waiting_number = State()
    waiting_otp = State()
    waiting_password = State()

# ================= Helpers =================
def get_or_create_user(user_id: int, username: str | None):
    user = users_col.find_one({"_id": user_id})
    if not user:
        user = {"_id": user_id, "username": username or None, "balance": 0.0}
        users_col.insert_one(user)
    return user

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# ================ Automatic OTP Listener =================
async def otp_listener(number_doc, user_id):
    string_session = number_doc.get("string_session")
    if not string_session:
        return

    api_id = int(os.getenv("API_ID"))
    api_hash = os.getenv("API_HASH")

    client = TelegramClient(StringSession(string_session), api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        return

    pattern = re.compile(r"\b\d{5}\b")  # OTP pattern

    try:
        while True:
            async for msg in client.iter_messages(777000, limit=5):
                if msg.message:
                    match = pattern.search(msg.message)
                    if match:
                        code = match.group(0)

                        # --- Send OTP to user ---
                        await bot.send_message(
                            user_id,
                            f"✅ OTP for +{number_doc['number']}:\n\nOTP - <code>{code}</code>\nPass - <code>9923</code>\n\n<pre>Order Completed ✅</pre>",
                            parse_mode="HTML"
                        )
                        # --- Get buyer info ---
                        user = users_col.find_one({"_id": user_id})
                        buyer_name = user.get("username") or f"User {user_id}"
                        country = number_doc.get("country", "Unknown")
                        price = number_doc.get("price", "N/A")
                        number = number_doc.get("number", "Unknown")
                        
                        channel_message = (
                            f"<pre>✅ <b>𝖠𝖼𝖼𝗈𝗎𝗇𝗍 𝖯𝗎𝗋𝖼𝗁𝖺𝗌𝖾 𝖲𝗎𝖼𝖼𝖾𝗌𝗌𝖿𝗎𝗅</b></pre>\n\n"
                            f"• For country :- {country}\n"
                            f"<b>• Application Type :- Telegram </b>\n\n"
                            f"<b>• Number :- h̶i̶d̶d̶e̶n̶•••• 📞</b>\n"
                            f"<b>• OTP :- {code}</b>\n"
                            f"<b>• Price :- ₹{price}</b>\n\n"
                            f"We are glad to have you as a customer!\n"
                            f"<b>• @tgaccbototp</b>"
                        )
                        await bot.send_message("@tgaccbototp", channel_message, parse_mode="HTML")
                        balance = user.get("balance", "N/A")
                        admin_message = (
                            f"<pre>📢 New Purchase Alert</pre>\n\n"
                            f"<pre>• Application: Telegram</pre>\n"
                            f"<b>• Country:</b> {country}\n"
                            f"<b>• Number:</b> +{number}\n"
                            f"<b>• OTP Received:</b> <code>{code}</code>\n\n"
                            f"<b>👤 User:</b> {buyer_name} (<code>{user_id}</code>)\n"
                            f"<b>💰 User Balance:</b> ₹{balance}"
                        )
                        await bot.send_message("@otprecvier", admin_message, parse_mode="HTML")
                        numbers_col.update_one(
                            {"_id": number_doc["_id"]},
                            {"$set": {"last_otp": code, "otp_fetched_at": datetime.now(timezone.utc)}})
                        await client.disconnect()
                        return

            await asyncio.sleep(3)
    except Exception as e:
        await client.disconnect()
        await bot.send_message(
            user_id,
            f"❌ OTP listener error:\n<code>{html.escape(str(e))}</code>",
            parse_mode="HTML"
        )

# === your channel usernames / ids ===
REQUIRED_CHANNELS = [
    "@OTPGRABER",         # Public channel
    "-1002711907665"        # Private channel ID
]

PRIVATE_INVITE_LINK = "https://t.me/+zwbBO92AGRFjY2U1"   # Your private channel invite link

@dp.message(Command("start"))
async def cmd_start(m: Message):
    args = m.text.split()
    referred_by = None
    is_ref_link = False

    if len(args) > 1 and args[1].startswith("ref"):
        is_ref_link = True
        try:
            referred_by = int(args[1][3:])
        except:
            referred_by = None

    user = users_col.find_one({"_id": m.from_user.id})
    get_or_create_user(m.from_user.id, m.from_user.username)

    # 🔒 Check if user joined both required channels
    not_joined = []
    for channel in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(channel, m.from_user.id)
            if member.status not in ["member", "administrator", "creator"]:
                not_joined.append(channel)
        except Exception:
            not_joined.append(channel)

    # ❌ If not joined, show join buttons and stop further execution
    if not_joined:
        kb = InlineKeyboardBuilder()
        
        for ch in not_joined:
            if ch.startswith("-100"):   # PRIVATE CHANNEL
                kb.button(text="Join Private Channel", url=PRIVATE_INVITE_LINK)
            else:                      # PUBLIC CHANNEL
                kb.button(
                    text=f"Join {ch.replace('@', '')}",
                    url=f"https://t.me/{ch.replace('@', '')}"
                )

        kb.button(text="✅ I've Joined", callback_data="check_join")
        kb.adjust(1)

        return await m.answer(
            "🚫 <b>You must join our channels before using the bot:</b>",
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )  
    caption = (
        "<b>𝖶𝖾𝗅𝖼𝗈𝗆𝖾 𝖳𝗈 ᴛɢ ᴀᴄᴄᴏᴜɴᴛ ʀᴏʙᴏᴛ - 𝖥𝖺𝗌𝗍𝖾𝗌𝖳 𝖳𝖾𝗅𝖾𝗀𝗋𝖺𝗆 𝖠𝖼𝖼𝗈𝗎𝗇𝗍 𝖲𝖾𝗅𝗅𝖾𝗋 𝖡𝗈𝗍🥂</b>\n"
        "<blockquote expandable>- 𝖠𝗎𝗍𝗈𝗆𝖺𝗍𝗂𝖼 𝖮𝖳𝖯𝗌 📌 \n"
        "- 𝖤𝖺𝗌𝗒 𝗍𝗈 𝖴𝗌𝖾 🥂\n"
        "- 24/7 𝖲𝗎𝗉𝗉𝗈𝗋𝗍 👨‍🔧\n"
        "- 𝖨𝗇𝗌𝗍𝖺𝗇𝗍 𝖯𝖺𝗒𝗆𝖾𝗇𝗍 𝖺𝗉𝗉𝗋𝗈𝗏𝖺𝗅𝗌 🧾 </blockquote>\n"
        "<blockquote expandable><b>🚀 𝖧𝗈𝗐 𝗍𝗈 𝗎𝗌𝖾 𝖡𝗈𝗍 :</b> \n1️⃣ 𝖱𝖾𝖼𝗁𝖺𝗋𝗀𝖾 \n2️⃣ 𝖲𝖾𝗅𝖾𝖼𝗍 𝖢𝗈𝗎𝗇𝗍𝗋𝗒 \n3️⃣ 𝖡𝗎𝗒 𝖺𝖼𝖼𝗈𝗎𝗇𝗍\n4️⃣ 𝖦𝖾𝗍 𝗇𝗎𝗆𝖻𝖾𝗋 & 𝖫𝗈𝗀𝗂𝗇 𝗍𝗁𝗋𝗈𝗎𝗀𝗁 𝖳𝖾𝗅𝖾𝗀𝗋𝖺𝗆 𝗈𝗋 𝖳𝖾𝗅𝖾𝗀𝗋𝖺𝗆 𝖷\n5️⃣ 𝖱𝖾𝖼𝖾𝗂𝗏𝖾 𝖮𝖳𝖯 & 𝗒𝗈𝗎'𝗋𝖾 𝖣𝗈𝗇𝖾 !</blockquote>"
        "🚀 𝖤𝗇𝗃𝗈𝗒 𝖥𝖺𝗌𝗍 𝖠𝖼𝖼𝗈𝗎𝗇𝗍 𝖻𝗎𝗒𝗂𝗇𝗀 𝖤𝗑𝗉𝖾𝗋𝗂𝖾𝗇𝖼𝖾!"
    )

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="💵 Balance", callback_data="balance"),
        InlineKeyboardButton(text="🛒 Buy Account", callback_data="buy")
    )
    kb.row(
        InlineKeyboardButton(text="💳 Recharge", callback_data="recharge"),
        InlineKeyboardButton(text="🛠️ Support", url="https://t.me/II_SPEED_II")
    )
    kb.row(
        InlineKeyboardButton(text="📦 Your Info", callback_data="stats"),
        InlineKeyboardButton(text="🆘 How to Use?", callback_data="howto")
    )
    kb.row(
        InlineKeyboardButton(text="🎉 Redeem", callback_data="redeem"),
    )

    menu_msg = await m.answer("🥂")
    try:
        await menu_msg.edit_media(
            media=InputMediaVideo(
                media="https://files.catbox.moe/277p2q.mp4",
                caption=caption,
                parse_mode="HTML"
            ),
            reply_markup=kb.as_markup()
        )
    except Exception as e:
        await menu_msg.edit_text(caption, reply_markup=kb.as_markup())
        print("Start video edit failed:", e)
        
@dp.callback_query(F.data == "check_join")
async def check_join(cq: CallbackQuery):
    not_joined = []
    for channel in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(channel, cq.from_user.id)
            if member.status not in ["member", "administrator", "creator"]:
                not_joined.append(channel)
        except Exception:
            not_joined.append(channel)

    if not_joined:
        return await cq.answer("❌ You haven’t joined all required channels yet!", show_alert=True)

    await cq.message.delete()
    await cmd_start(cq.message)  # restart start command after verification
    
# ================= Balance =================
@dp.callback_query(F.data == "balance")
async def show_balance(cq: CallbackQuery):
    user = users_col.find_one({"_id": cq.from_user.id})
    await cq.answer(f"💰 Balance: {user['balance']:.2f} ₹" if user else "💰 Balance: 0 ₹", show_alert=True)

@dp.message(Command("balance"))
async def cmd_balance(msg: Message):
    user = users_col.find_one({"_id": msg.from_user.id})
    await msg.answer(f"💰 Balance: {user['balance']:.2f} ₹" if user else "💰 Balance: 0 ₹")


# ================= Buy Flow =================
async def send_country_menu(message, previous=""):
    countries = await asyncio.to_thread(lambda: list(countries_col.find({})))
    if not countries:
        return await message.answer("❌ No countries available. Admin must add stock first.")

    kb = InlineKeyboardBuilder()
    for c in countries:
        kb.button(text=html.escape(c["name"]), callback_data=f"country:{c['name']}")
    kb.adjust(2)

    if previous:
        kb.row(InlineKeyboardButton(text="🦸‍♂️ Support", url=f"https://t.me/II_SPEED_II"))

    # Send a new message for country selection (do not edit the start message)
    country_msg = await message.answer("🌍 Select a country:", reply_markup=kb.as_markup())
    return country_msg  # return message to use for editing later


@dp.callback_query(F.data == "buy")
async def callback_buy(cq: CallbackQuery):
    await cq.answer()
    # Send a new message for countries menu
    await send_country_menu(cq.message, previous="buy")


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
        f"📦 Available : {country['stock']}\n"
        f"🔍 Reliable | Affordable | Good Quality\n\n"
        f"⚠️ Use Telegram X only to login.\n"
        f"🚫 Not responsible for freeze/ban."
    )

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="💳 Buy Now", callback_data=f"buy_now:{country_name}"),
        InlineKeyboardButton(text="🔙 Back", callback_data="buy")  # Back edits the same message
    )

    # Edit the current country message instead of sending a new one
    await cq.message.edit_text(text, reply_markup=kb.as_markup())

# ================= Buy Now Flow =================
@dp.callback_query(F.data.startswith("buy_now:"))
async def callback_buy_now(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    _, country_name = cq.data.split(":", 1)
    country, user = await asyncio.to_thread(lambda: (
        countries_col.find_one({"name": country_name}),
        get_or_create_user(cq.from_user.id, cq.from_user.username)
    ))
    if not country:
        return await cq.answer("❌ Country not found", show_alert=True)
    await state.update_data(country_name=country_name, country_price=country["price"], country_stock=country["stock"])
    await state.set_state("waiting_quantity")
    await cq.message.edit_text(
        f"📦 How many {html.escape(country_name)} accounts do you want to buy?\n"
        "📝 Send only a number (e.g., 1, 5, 10)."
    )

# ================= Handle Quantity =================
@dp.message(StateFilter("waiting_quantity"))
async def handle_quantity(msg: Message, state: FSMContext):
    data = await state.get_data()
    country_name = data["country_name"]
    country_price = data["country_price"]
    country_stock = data["country_stock"]
    try:
        quantity = int(msg.text.strip())
        if quantity <= 0:
            raise ValueError
    except ValueError:
        return await msg.answer("❌ Invalid number. Please send a valid integer.")

    total_cost = country_price * quantity
    user = await asyncio.to_thread(lambda: get_or_create_user(msg.from_user.id, msg.from_user.username))
    user_balance = user.get("balance", 0)
    if user_balance < total_cost:
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="💳 Add Funds", callback_data="recharge"))
        return await msg.answer(
            f"🚫 Insufficient Balance!\n💰 Your Balance: ₹{user_balance:.2f}\n🧾 Total Required: ₹{total_cost:.2f}",
            reply_markup=kb.as_markup()
        )

        
    if country_stock < quantity:
        await state.clear()  # <- ADD THIS LINE
        return await msg.answer(f"❌ Only {country_stock} account(s) left for {country_name}.")

    unsold_numbers = await asyncio.to_thread(lambda: list(numbers_col.find({"country": country_name, "used": False}).limit(quantity)))
    if len(unsold_numbers) < quantity:
        return await msg.answer(f"❌ Only {len(unsold_numbers)} account(s) available for {country_name}.")

    new_balance = user_balance - total_cost

    # ===== DB Update safely =====
    def update_db():
        try:
            users_col.update_one({"_id": user["_id"]}, {"$set": {"balance": new_balance}})
            for num in unsold_numbers:
                numbers_col.update_one({"_id": num["_id"]}, {"$set": {"used": True}})
                orders_col.insert_one({
                    "user_id": user["_id"],
                    "country": country_name,
                    "number": num["number"],
                    "price": country_price,
                    "status": "purchased",
                    "created_at": datetime.now(timezone.utc)
                })
            countries_col.update_one({"name": country_name}, {"$inc": {"stock": -quantity}})
        except Exception as e:
            print("DB update error:", e)
    await asyncio.to_thread(update_db)

    # Send numbers and start OTP listeners automatically
    for num in unsold_numbers:
        await msg.answer(
            f"<pre>✅ Purchased {country_name} account!</pre>\n📱 Number:<code> +{num['number']}</code>\n💸 Deducted: ₹{country_price}\n💰 Balance Left: ₹{new_balance:.2f}\n\n<blockquote>Note: If any problem receiving OTP, then please Instantly DM support @II_SPEED_II</blockquote>"
        )
        # start OTP listener in background
        asyncio.create_task(otp_listener(num, msg.from_user.id))

    await state.clear()

# ================= Admin Add Number Flow =================
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
        await state.update_data(session=session.save(), phone_code_hash=sent.phone_code_hash)
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
        # Send confirmation with string session for verification
        await msg.answer(f"✅ Added number {phone} for {country} successfully!\n🔑 String Session:\n<code>{string_session}</code>", parse_mode="HTML")
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
        # Send confirmation with string session for verification
        await msg.answer(
            f"✅ Added number {phone} (with 2FA) for {country} successfully!\n\n"
            f"🔑 String Session:\n<blockquote expandable><code>{string_session}</code></blockquote>",
            parse_mode="HTML"
        )
        await state.clear()
    except Exception as e:
        await client.disconnect()
        await msg.answer(f"❌ Error signing in with password: {e}")

# ================= /sales Command =================
@dp.message(Command("sales"))
async def cmd_sales(msg: Message):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ You are not authorized to view sales report.")

    # Fetch all orders
    all_orders = list(orders_col.find({"status": "purchased"}))
    if not all_orders:
        return await msg.answer("📊 No sales data found yet.")

    # Compute totals
    total_numbers_sold = sum(order.get("price", 0) / order.get("price", 0) * 1 for order in all_orders)  # fallback in case quantity isn't stored
    total_numbers_sold = len(all_orders)  # Each order is 1 number in your system
    total_earnings = sum(order.get("price", 0) for order in all_orders)
    average_price = total_earnings / total_numbers_sold if total_numbers_sold else 0

    report = (
        "📊 <b>Bot Profit Report</b>\n\n"
        f"🔢 Total Numbers Sold: {total_numbers_sold}\n"
        f"💰 Total Earnings: ₹{total_earnings:.2f}\n"
        f"⚖️ Average Price/Number: ₹{average_price:.2f}"
    )

    await msg.answer(report, parse_mode="HTML")

# ===== Admin Country Commands =====
@dp.message(Command("addcountry"))
async def cmd_add_country(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized.")
    await msg.answer("🌍 Send the country name and price separated by a comma (e.g., India,50):")
    await state.set_state("adding_country")

@dp.message(StateFilter("adding_country"))
async def handle_add_country(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    if "," not in msg.text:
        return await msg.answer("❌ Invalid format. Example: India,50")
    name, price = msg.text.split(",", 1)
    try:
        price = float(price.strip())
    except ValueError:
        return await msg.answer("❌ Invalid price format.")
    countries_col.update_one({"name": name.strip()}, {"$set": {"price": price, "stock": 0}}, upsert=True)
    await msg.answer(f"✅ Country {name.strip()} added/updated with price {price}.")
    await state.clear()

# ================= Admin: Remove Country =================
@dp.message(Command("removecountry"))
async def cmd_remove_country(msg: Message):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized.")

    countries = list(countries_col.find({}))
    if not countries:
        return await msg.answer("📭 No countries to remove.")

    kb = InlineKeyboardBuilder()
    for c in countries:
        kb.button(text=c["name"], callback_data=f"removecountry:{c['name']}")
    kb.adjust(2)
    await msg.answer("🌍 Select a country to remove:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("removecountry:"))
async def callback_remove_country(cq: CallbackQuery):
    await cq.answer()
    _, country_name = cq.data.split(":", 1)

    result = countries_col.delete_one({"name": country_name})
    if result.deleted_count == 0:
        await cq.message.edit_text(f"❌ Country <b>{country_name}</b> not found.", parse_mode="HTML")
    else:
        await cq.message.edit_text(f"✅ Country <b>{country_name}</b> removed successfully.", parse_mode="HTML")

@dp.message(Command("db"))
async def cmd_db(msg: Message):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized.")

    countries = list(countries_col.find({}))
    if not countries:
        return await msg.answer("❌ No countries found in DB.")

    text = "📚 <b>Numbers in Database by Country:</b>\n\n"

    for c in countries:
        country_name = c["name"]
        numbers = list(numbers_col.find({"country": country_name}))
        text += f"🌍 <b>{country_name}:</b>\n"
        if numbers:
            for num in numbers:
                text += f"• {num['number']} {'✅' if num.get('used') else ''}\n"
        else:
            text += "No number\n"
        text += "\n"

    await msg.answer(text, parse_mode="HTML")



# ================= Admin: Edit Country =================
class EditCountry(StatesGroup):
    waiting_new_name = State()
    waiting_new_price = State()

@dp.message(Command("editcountry"))
async def cmd_edit_country(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized.")
    countries = list(countries_col.find({}))
    if not countries:
        return await msg.answer("📭 No countries to edit.")
    kb = InlineKeyboardBuilder()
    for c in countries:
        kb.button(text=c["name"], callback_data=f"editcountry:{c['name']}")
    kb.adjust(2)
    await msg.answer("🌍 Select a country to edit:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("editcountry:"))
async def callback_edit_country(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    _, country_name = cq.data.split(":", 1)
    country = countries_col.find_one({"name": country_name})
    if not country:
        return await cq.message.edit_text(f"❌ Country {country_name} not found.")

    await state.update_data(country_name=country_name)

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="✏️ Change Name", callback_data="editcountry_change_name"),
        InlineKeyboardButton(text="💰 Change Price", callback_data="editcountry_change_price")
    )
    kb.row(InlineKeyboardButton(text="❌ Cancel", callback_data="editcountry_cancel"))
    await cq.message.edit_text(
        f"🛠️ Editing Country: <b>{country_name}</b>\n"
        f"💸 Current Price: ₹{country['price']}",
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )

@dp.callback_query(F.data == "editcountry_change_name")
async def callback_edit_change_name(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    data = await state.get_data()
    country_name = data.get("country_name")
    await cq.message.answer(f"✏️ Send new name for <b>{country_name}</b>:", parse_mode="HTML")
    await state.set_state(EditCountry.waiting_new_name)

@dp.message(StateFilter(EditCountry.waiting_new_name))
async def handle_new_country_name(msg: Message, state: FSMContext):
    data = await state.get_data()
    old_name = data.get("country_name")
    new_name = msg.text.strip()

    countries_col.update_one({"name": old_name}, {"$set": {"name": new_name}})
    numbers_col.update_many({"country": old_name}, {"$set": {"country": new_name}})
    await msg.answer(f"✅ Country name changed from <b>{old_name}</b> → <b>{new_name}</b>", parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data == "editcountry_change_price")
async def callback_edit_change_price(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    data = await state.get_data()
    country_name = data.get("country_name")
    await cq.message.answer(f"💰 Send new price for <b>{country_name}</b>:", parse_mode="HTML")
    await state.set_state(EditCountry.waiting_new_price)

@dp.message(StateFilter(EditCountry.waiting_new_price))
async def handle_new_country_price(msg: Message, state: FSMContext):
    data = await state.get_data()
    country_name = data.get("country_name")
    try:
        price = float(msg.text.strip())
        if price <= 0:
            raise ValueError
    except ValueError:
        return await msg.answer("❌ Invalid price format. Please send a valid number.")

    countries_col.update_one({"name": country_name}, {"$set": {"price": price}})
    await msg.answer(f"✅ Updated price for <b>{country_name}</b> to ₹{price:.2f}", parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data == "editcountry_cancel")
async def callback_edit_cancel(cq: CallbackQuery, state: FSMContext):
    await cq.answer("❌ Cancelled")
    await state.clear()
    await cq.message.edit_text("❌ Edit cancelled.")


@dp.callback_query(F.data == "stats")
async def callback_stats(cq: CallbackQuery):
    user = users_col.find_one({"_id": cq.from_user.id})
    if not user:
        user = get_or_create_user(cq.from_user.id, cq.from_user.username)

    text = (
        f"👤 Name: {cq.from_user.full_name}\n"
        f"💻 Username: @{cq.from_user.username if cq.from_user.username else 'N/A'}\n"
        f"🆔 User ID: {cq.from_user.id}\n"
        f"💰 Balance: ₹{user.get('balance', 0.0):.2f}"
    )

    image_url = "https://files.catbox.moe/a3o6j9.jpg"
    
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="📲 Support", url=f"https://t.me/II_SPEED_II"))
    
    await cq.message.answer_photo(photo=image_url, caption=text, parse_mode="HTML", reply_markup=kb.as_markup())
    await cq.answer()

@dp.callback_query(F.data == "howto")
async def callback_howto(cq: CallbackQuery):
    steps_text = ("📚 FᴀQ & Sᴜᴘᴘᴏʀᴛ 😊\n\n🔗 𝙃𝙤𝙬 𝙩𝙤 𝙪𝙨𝙚:  👉 @USEOTPBOT\n💬 Oғғɪᴄɪᴀʟ Sᴜᴘᴘᴏʀᴛ:   👉 @II_SPEED_II\n🤖 Oғғɪᴄɪᴀʟ Bᴏᴛ:     👉 @tgaccOtpbot\n\n🛟 Fᴇᴇʟ Fʀᴇᴇ Tᴏ Rᴇᴀᴄʜ Oᴜᴛ Iғ Yᴏᴜ Nᴇᴇᴅ Aɴʏ Hᴇʟᴘ!")

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="📲 Support", url=f"https://t.me/II_SPEED_II"),
        InlineKeyboardButton(text="🔗 𝙃𝙤𝙬 𝙩𝙤 𝙪𝙨𝙚", url=f"https://t.me/USEOTPBOT")
    )
    
    await cq.message.answer(steps_text, parse_mode="HTML", reply_markup=kb.as_markup())
    await cq.answer()

@dp.callback_query(F.data == "refer")
async def callback_refer(cq: CallbackQuery):
    user = get_or_create_user(cq.from_user.id, cq.from_user.username)
    # Create a referral link
    bot_username = (await bot.get_me()).username
    refer_link = f"https://t.me/{bot_username}?start=ref{cq.from_user.id}"

    text = (
        "🎁 <b>Refer & Earn Program</b>\n\n"
        "Invite your friends to use the bot and earn <b>2%</b> of every recharge they make!\n\n"
        f"🔗 <b>Your Referral Link:</b>\n<code>{refer_link}</code>\n\n"
        "💡 Share your link and start earning passive income!"
    )

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="📤 Share Link", url=f"https://t.me/share/url?url={refer_link}&text=Join%20and%20earn%20with%20this%20bot!"))

    await cq.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await cq.answer()

# ================= Admin Credit/Debit Commands =================
@dp.message(Command("addbal"))
async def cmd_credit(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized.")
    
    await msg.answer("💰 Send user ID and amount to credit separated by a comma (e.g., 123456789,50):")
    await state.set_state("credit_waiting")

@dp.message(StateFilter("credit_waiting"))
async def handle_credit(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return

    if "," not in msg.text:
        return await msg.answer("❌ Invalid format. Example: 123456789,50")

    user_id_str, amount_str = msg.text.split(",", 1)
    try:
        user_id = int(user_id_str.strip())
        amount = float(amount_str.strip())
    except ValueError:
        return await msg.answer("❌ Invalid user ID or amount format.")

    user = users_col.find_one({"_id": user_id})
    if not user:
        return await msg.answer(f"❌ User with ID {user_id} not found.")

    new_balance = user.get("balance", 0.0) + amount
    users_col.update_one({"_id": user_id}, {"$set": {"balance": new_balance}})
    await msg.answer(f"✅ Credited ₹{amount:.2f} to {user.get('username') or user_id}\n💰 New Balance: ₹{new_balance:.2f}")
    await state.clear()


@dp.message(Command("removebal"))
async def cmd_debit(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized.")
    
    await msg.answer("💸 Send user ID and amount to debit separated by a comma (e.g., 123456789,50):")
    await state.set_state("debit_waiting")

@dp.message(StateFilter("debit_waiting"))
async def handle_debit(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return

    if "," not in msg.text:
        return await msg.answer("❌ Invalid format. Example: 123456789,50")

    user_id_str, amount_str = msg.text.split(",", 1)
    try:
        user_id = int(user_id_str.strip())
        amount = float(amount_str.strip())
    except ValueError:
        return await msg.answer("❌ Invalid user ID or amount format.")

    user = users_col.find_one({"_id": user_id})
    if not user:
        return await msg.answer(f"❌ User with ID {user_id} not found.")

    new_balance = max(user.get("balance", 0.0) - amount, 0.0)
    users_col.update_one({"_id": user_id}, {"$set": {"balance": new_balance}})
    await msg.answer(f"✅ Debited ₹{amount:.2f} from {user.get('username') or user_id}\n💰 New Balance: ₹{new_balance:.2f}")
    await state.clear()











    # ================= MongoDB Redeem Collection =================
redeem_col = db["redeem_codes"]  # Add this at top with other collections

# ================= Redeem FSM =================
class RedeemState(StatesGroup):
    # For auto-generated redeem codes
    waiting_amount = State()          # Admin enters amount
    waiting_limit = State()           # Admin selects max users via inline numeric keypad

    # For custom redeem codes
    waiting_code = State()            # Admin enters custom code (e.g. DIWALI100)
    waiting_amount_custom = State()   # Admin enters amount for custom code
    waiting_limit_custom = State()    # Admin selects max users for custom code

class UserRedeemState(StatesGroup):
    waiting_code = State()            # User enters redeem code
    
# ================= Helper =================
import random, string
def generate_code(length=8):
    """Generate code like HEIKE938"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))



    
        # ================= Admin: Create Custom Redeem =================
@dp.message(Command("cusredeem"))
async def cmd_custom_redeem(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized.")
    await msg.answer("🎟️ Enter the custom redeem code (e.g. DIWALI100):")
    await state.set_state(RedeemState.waiting_code)

# ================= Admin: Handle Custom Code =================
@dp.message(StateFilter(RedeemState.waiting_code))
async def handle_custom_code(msg: Message, state: FSMContext):
    code = msg.text.strip().upper()
    if redeem_col.find_one({"code": code}):
        return await msg.answer("⚠️ This code already exists. Try another one.")

    await state.update_data(custom_code=code)
    await msg.answer("💰 Enter the amount for this redeem code:")
    await state.set_state(RedeemState.waiting_amount_custom)

# ================= Admin: Handle Custom Amount =================
@dp.message(StateFilter(RedeemState.waiting_amount_custom))
async def handle_custom_amount(msg: Message, state: FSMContext):
    try:
        amount = float(msg.text.strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        return await msg.answer("❌ Invalid amount. Send a number like 50 or 100.")

    await state.update_data(amount=amount, limit_str="")

    # Inline numeric keypad
    kb = InlineKeyboardBuilder()
    for row in (("1", "2", "3"), ("4", "5", "6"), ("7", "8", "9"), ("0", "❌", "✅")):
        kb.row(*[InlineKeyboardButton(text=btn, callback_data=f"cusredeemnum:{btn}") for btn in row])

    await msg.answer(
        "👥 Select max number of users who can claim this custom code:\n<b>0</b>",
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )
    await state.set_state(RedeemState.waiting_limit_custom)

# ================= Admin: Handle Custom Inline Number Pad =================
@dp.callback_query(F.data.startswith("cusredeemnum:"))
async def handle_custom_redeem_number(cq: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    current = data.get("limit_str", "")
    value = cq.data.split(":")[1]

    if value == "❌":
        current = current[:-1]
    elif value == "✅":
        if not current:
            await cq.answer("❌ Please select at least one user.", show_alert=True)
            return
        try:
            limit = int(current)
        except ValueError:
            await cq.answer("❌ Invalid number.", show_alert=True)
            return

        code = data.get("custom_code")
        amount = data.get("amount")
        created_at = datetime.utcnow()

        # Insert redeem into MongoDB
        redeem_col.insert_one({
            "code": code,
            "amount": amount,
            "max_claims": limit,
            "claimed_count": 0,
            "claimed_users": [],
            "created_at": created_at
        })

        await cq.message.edit_text(
            f"✅ Custom redeem code created!\n\n"
            f"🎟️ Code: <code>{code}</code>\n"
            f"💰 Amount: ₹{amount:.2f}\n"
            f"👥 Max Claims: {limit}",
            parse_mode="HTML"
        )
        await state.clear()
        return
    else:
        current += value
        if len(current) > 6:
            current = current[:6]

    await state.update_data(limit_str=current)

    # Rebuild keypad dynamically
    kb = InlineKeyboardBuilder()
    for row in (("1", "2", "3"), ("4", "5", "6"), ("7", "8", "9"), ("0", "❌", "✅")):
        kb.row(*[InlineKeyboardButton(text=btn, callback_data=f"cusredeemnum:{btn}") for btn in row])

    await cq.message.edit_text(
        f"👥 Select max number of users who can claim this custom code:\n<b>{current or '0'}</b>",
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )
    await cq.answer()
        


# ================= Admin: View Redeems =================
@dp.message(Command("redeemlist"))
async def cmd_redeem_list(msg: Message):
    if not is_admin(msg.from_user.id):
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

# ================= User: Redeem Code =================
@dp.callback_query(F.data == "redeem")
async def callback_user_redeem(cq: CallbackQuery, state: FSMContext):
    await cq.answer("✅ Send your redeem code now!", show_alert=False)
    await cq.message.answer("🎟️ Send your redeem code below:")
    await state.set_state(UserRedeemState.waiting_code)

# Command /redeem
@dp.message(F.text == "/redeem")
async def command_user_redeem(message: Message, state: FSMContext):
    await message.answer("✅ Send your redeem code now!")
    await message.answer("🎟️ Send your redeem code below:")
    await state.set_state(UserRedeemState.waiting_code)

@dp.message(StateFilter(UserRedeemState.waiting_code))
async def handle_user_redeem(msg: Message, state: FSMContext):
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

    if msg.from_user.id in redeem.get("claimed_users", []):
        await msg.answer("⚠️ You have already claimed this code.")
        return await state.clear()

    # Credit user balance
    users_col.update_one({"_id": msg.from_user.id}, {"$inc": {"balance": redeem["amount"]}})
    redeem_col.update_one(
        {"code": code},
        {"$inc": {"claimed_count": 1}, "$push": {"claimed_users": msg.from_user.id}}
    )

    await msg.answer(
        f"✅ Code <b>{code}</b> redeemed successfully!\n💰 You received ₹{redeem['amount']:.2f}",
        parse_mode="HTML"
    )
    await state.clear()

@dp.message(Command("editsell"))
async def cmd_editsell(msg: Message):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized.")

    await msg.answer("📋 Send the list in format:\n\n<code>USA ₹50\nIndia ₹10\nUK ₹20</code>")

    @dp.message()  # Next message from admin
    async def handle_sell_edit(m: Message):
        sell_rates_col.delete_many({})
        for line in m.text.splitlines():
            try:
                parts = line.split("₹")
                country = parts[0].strip()
                price = float(parts[1].strip())
                code = "+1" if "USA" in country else "+91" if "India" in country else ""  # add more or editable
                sell_rates_col.insert_one({"country": country, "price": price, "code": code})
            except:
                continue
        await m.answer("✅ Sell rates updated.")
        

# ================= Admin Broadcast (Forward Version - Aiogram Fix) =================
@dp.message(Command("broadcast"))
async def cmd_broadcast(msg: Message):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized.")

    if not msg.reply_to_message:
        return await msg.answer("⚠️ Reply to the message you want to broadcast with /broadcast.")

    broadcast_msg = msg.reply_to_message
    users = list(users_col.find({}))

    if not users:
        return await msg.answer("⚠️ No users found to broadcast.")

    sent_count = 0
    failed_count = 0

    for user in users:
        user_id = user["_id"]
        try:
            await bot.forward_message(
                chat_id=user_id,
                from_chat_id=broadcast_msg.chat.id,
                message_id=broadcast_msg.message_id
            )
            sent_count += 1
        except Exception as e:
            failed_count += 1
            print(f"Failed to send to {user_id}: {e}")

    await msg.answer(f"✅ Broadcast completed!\n\nSent: {sent_count}\nFailed: {failed_count}")
    

# ===== Register External Handlers =====
register_recharge_handlers(dp=dp, bot=bot, users_col=users_col, txns_col=db["transactions"], ADMIN_IDS=ADMIN_IDS)

# ===== Bot Runner =====
async def main():
    print("Bot started.")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())



