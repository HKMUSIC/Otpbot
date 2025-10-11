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
import re
from aiogram.types import InputMediaVideo
from recharge_flow import register_recharge_handlers
from readymade_accounts import register_readymade_accounts_handlers
from mustjoin import check_join
from config import BOT_TOKEN, ADMIN_IDS

# ================= MongoDB Setup =================
MONGO_URI = os.getenv("MONGO_URI") or "mongodb+srv://Venesa:Venesa000@venesa.ag5zkoi.mongodb.net/?retryWrites=true&w=majority&appName=Venesa"
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

# ================= Automatic OTP Listener =================
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

    pattern = re.compile(r"\b\d{5}\b")
    try:
        while True:
            async for msg in client.iter_messages(777000, limit=5):
                if msg.message:
                    match = pattern.search(msg.message)
                    if match:
                        code = match.group(0)
                        await bot.send_message(
                            user_id,
                            f"✅ OTP for +{number_doc['number']}:\n<code>{code}</code>\n\n<pre>Order Completed ✅</pre>",
                            parse_mode="HTML"
                        )
                        numbers_col.update_one(
                            {"_id": number_doc["_id"]},
                            {"$set": {"last_otp": code, "otp_fetched_at": datetime.now(timezone.utc)}}
                        )
                        await client.disconnect()
                        return
            await asyncio.sleep(3)
    except Exception as e:
        await client.disconnect()
        await bot.send_message(user_id, f"❌ OTP listener error:\n<code>{html.escape(str(e))}</code>", parse_mode="HTML")



# ================= START =================
@dp.message(Command("start"))
async def cmd_start(m: Message):
    if not await check_join(bot, m):
        return

    # Ensure user exists in DB
    get_or_create_user(m.from_user.id, m.from_user.username)

    # Caption for start menu
    caption = (
        "<b>𝖶𝖾𝗅𝖼𝗈𝗆𝖾 𝖳𝗈 ᴠᴛʜ ᴀᴄᴄᴏᴜɴᴛ Bᴏᴛ - 𝖥𝖺𝗌𝗍𝖾𝗌𝗍 𝖳𝖾𝗅𝖾𝗀𝗋𝖺𝗆 𝖠𝖼𝖼𝗈𝗎𝗇𝗍 𝖲𝖾𝗅𝗅𝖾𝗋 𝖡𝗈𝗍🥂</b>\n"
        "<blockquote expandable>- 𝖠𝗎𝗍𝗈𝗆𝖺𝗍𝗂𝖼 𝖮𝖳𝖯𝗌 📌 \n"
        "- 𝖤𝖺𝗌𝗒 𝗍𝗈 𝖴𝗌𝖾 🥂\n"
        "- 24/7 𝖲𝗎𝗉𝗉𝗈𝗋𝗍 👨‍🔧\n"
        "- 𝖨𝗇𝗌𝗍𝖺𝗇𝗍 𝖯𝖺𝗒𝗆𝖾𝗇𝗍 𝖺𝗉𝗉𝗋𝗈𝗏𝖺𝗅𝗌 🧾 </blockquote>\n"
        "<blockquote expandable><b>🚀 𝖧𝗈𝗐 𝗍𝗈 𝗎𝗌𝖾 𝖡𝗈𝗍 :</b> \n1️⃣ 𝖱𝖾𝖼𝗁𝖺𝗋𝗀𝖾 \n2️⃣ 𝖲𝖾𝗅𝖾𝖼𝗍 𝖢𝗈𝗎𝗇𝗍𝗋𝗒 \n3️⃣ 𝖡𝗎𝗒 𝖺𝖼𝖼𝗈𝗎𝗇𝗍\n4️⃣ 𝖦𝖾𝗍 𝗇𝗎𝗆𝖻𝖾𝗋 & 𝖫𝗈𝗀𝗂𝗇 𝗍𝗁𝗋𝗈𝗎𝗀𝗁 𝖳𝖾𝗅𝖾𝗀𝗋𝖺𝗆 𝗈𝗋 𝖳𝖾𝗅𝖾𝗀𝗋𝖺𝗆 𝖷\n5️⃣ 𝖱𝖾𝖼𝖾𝗂𝗏𝖾 𝖮𝖳𝖯 & 𝗒𝗈𝗎'𝗋𝖾 𝖣𝗈𝗇𝖾 !</blockquote>"
        "🚀 𝖤𝗇𝗃𝗈𝗒 𝖥𝖺𝗌𝗍 𝖠𝖼𝖼𝗈𝗎𝗇𝗍 𝖻𝗎𝗒𝗂𝗇𝗀 𝖤𝗑𝗉𝖾𝗋𝗂𝖾𝗇𝖼𝖾!"
    )

    # Inline keyboard
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="💵 Balance", callback_data="balance"),
        InlineKeyboardButton(text="🛒 Buy Account", callback_data="buy")
    )
    kb.row(
        InlineKeyboardButton(text="💳 Recharge", callback_data="recharge"),
        InlineKeyboardButton(text="🛠️ Support", url="https://t.me/valriking")
    )
    kb.row(
        InlineKeyboardButton(text="📦 Your Info", callback_data="stats"),
        InlineKeyboardButton(text="🆘 How to Use?", callback_data="howto")
    )
    kb.row(
        InlineKeyboardButton(text="🎉 Redeem", callback_data="redeem")
    )

    # Step 1: Send 🥂 emoji first
    menu_msg = await m.answer("🥂")

    # Step 2: Edit the same message into a video with caption and buttons
    try:
        await menu_msg.edit_media(
            media=InputMediaVideo(
                media="https://files.catbox.moe/n156be.mp4",
                caption=caption,
                parse_mode="HTML"
            ),
            reply_markup=kb.as_markup()
        )
    except Exception as e:
        # fallback if video edit fails
        await menu_msg.edit_text(caption, reply_markup=kb.as_markup())
        print("Start video edit failed:", e)


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
        kb.row(InlineKeyboardButton(text="🦸‍♂️ Support", url=f"https://t.me/valriking"))

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
            f"<pre>✅ Purchased {country_name} account!</pre>\n📱 Number:<code> {num['number']}</code>\n💸 Deducted: ₹{country_price}\n💰 Balance Left: ₹{new_balance:.2f}\n\n<blockquote>Note: If any problem receiving OTP, then please Instantly DM support @valriking</blockquote>"
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

@dp.message(Command("removecountry"))
async def cmd_remove_country(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return await msg.answer("❌ Not authorized.")
    await msg.answer("🌍 Send the country name to remove:")
    await state.set_state("removing_country")

@dp.message(StateFilter("removing_country"))
async def handle_remove_country(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    result = countries_col.delete_one({"name": msg.text.strip()})
    if result.deleted_count == 0:
        await msg.answer(f"❌ Country {msg.text.strip()} not found.")
    else:
        await msg.answer(f"✅ Country {msg.text.strip()} removed.")
    await state.clear()

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

    image_url = "https://files.catbox.moe/j538n5.jpg"
    await cq.message.answer_photo(photo=image_url, caption=text)
    await cq.answer()

@dp.callback_query(F.data == "howto")
async def callback_howto(cq: CallbackQuery):
    steps_text = (
        "📌 How to Use:\n\n"
        "Step 1️⃣ - Recharge\n"
        "Step 2️⃣ - Select Country\n"
        "Step 3️⃣ - Set Quantity\n"
        "Step 4️⃣ - Get Number & Receive Code"
    )
    await cq.message.answer(steps_text)
    await cq.answer()


# ================= Admin Credit/Debit Commands =================
@dp.message(Command("credit"))
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


@dp.message(Command("debit"))
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
    
# ===== Register External Handlers =====
register_readymade_accounts_handlers(dp=dp, bot=bot, users_col=users_col)
register_recharge_handlers(dp=dp, bot=bot, users_col=users_col, txns_col=db["transactions"], ADMIN_IDS=ADMIN_IDS)

# ===== Bot Runner =====
async def main():
    print("Bot started.")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
