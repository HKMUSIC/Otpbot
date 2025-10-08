import os
import asyncio
import aiohttp
import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from pymongo import MongoClient
from bson import ObjectId

# External modules
from readymade_accounts import register_readymade_accounts_handlers
from provider import PROVIDER_BASE_URL, PROVIDER_API_KEY, ProviderClient, ProviderError
from mustjoin import check_join
from config import BOT_TOKEN, ADMIN_IDS, DEFAULT_CURRENCY, MIN_BALANCE_REQUIRED

# Separated handler registration functions
from recharge_flow import register_recharge_handlers
from admin_approval import register_admin_approval_handlers
from admin_commands import register_admin_command_handlers

# ===== MongoDB Setup =====
MONGO_URI = "mongodb+srv://Sony:Sony123@sony0.soh6m14.mongodb.net/?retryWrites=true&w=majority&appName=Sony0"
client = MongoClient(MONGO_URI)
db = client["QuickCodes"]
users_col = db["users"]
orders_col = db["orders"]
txns_col = db["transactions"]

# ===== Bot Setup =====
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
provider = ProviderClient()

# ===== Helpers =====
def get_or_create_user(user_id: int, username: str | None):
    user = users_col.find_one({"_id": user_id})
    if not user:
        user = {"_id": user_id, "username": username or None, "balance": 0.0}
        users_col.insert_one(user)
    return user

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# ===== Poll OTP Helper =====
async def poll_for_otp(order_id: ObjectId, provider_order_id: str, chat_id: int):
    expiry_time = datetime.datetime.utcnow() + datetime.timedelta(minutes=15)
    while datetime.datetime.utcnow() < expiry_time:
        await asyncio.sleep(5)
        try:
            resp = await provider.get_sms(provider_order_id)
        except ProviderError:
            continue

        order = orders_col.find_one({"_id": order_id})
        if not order:
            return

        status = resp.get("status")
        if status == "sms_received":
            otp_text = resp.get("sms")
            if otp_text:
                orders_col.update_one(
                    {"_id": order_id},
                    {"$set": {"status": "received", "otp_text": otp_text}}
                )
                await bot.send_message(
                    chat_id,
                    f"✅ OTP Received:\n<code>{otp_text}</code>\n\n"
                    f"<blockquote>✅ Order Completed - Any Queries, Visit @QuickCodesGC</blockquote>"
                )
            return

        elif resp.get("status") == "cancelled":
            orders_col.update_one({"_id": order_id}, {"$set": {"status": "cancelled"}})
            await bot.send_message(chat_id, "✅ Balance Updated")
            
            return

    
    # Timeout
    order = orders_col.find_one({"_id": order_id})
    if order and order["status"] == "waiting_sms":
        users_col.update_one({"_id": order["user_id"]}, {"$inc": {"balance": order["price"]}})
        orders_col.update_one({"_id": order_id}, {"$set": {"status": "cancelled"}})
        await bot.send_message(chat_id, "❌ OTP not received in time. Order cancelled and balance refunded.")

# ===== Provider Cancel Helper =====
async def cancel_number_on_provider(activation_id: str) -> bool:
    cancel_url = f"{PROVIDER_BASE_URL}?api_key={PROVIDER_API_KEY}&action=setStatus&status=8&id={activation_id}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(cancel_url) as resp:
                text = await resp.text()
                return "OK" in text or "STATUS_CANCEL" in text
    except Exception as e:
        print(f"Provider cancel failed: {e}")
        return False

# ===== START Command =====
@dp.message(Command("start"))
async def cmd_start(m: Message):
    if not await check_join(bot, m):
        return

    # Save or create user
    get_or_create_user(m.from_user.id, m.from_user.username)

    # Send small first message
    await m.answer("🧑‍💻")

    # Main welcome text with linked "!"
    text = (
        "<b>Welcome to Bot – ⚡ Most Trusted and Fastest OTP Bot!</b>\n"
        "<i><blockquote>📖 How to use Bot:</blockquote></i>\n"
        "<blockquote expandable>1️⃣ Recharge\n2️⃣ Select Country + Operator\n3️⃣ Select App\n4️⃣ Click on Purchase and 📩 Receive OTP</blockquote>\n"
        "🚀 Enjoy Fast OTP Services<a href=\"https://files.catbox.moe/c1pxci.mp4\">!</a>"
    )
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="💵 Balance", callback_data="balance"),
        InlineKeyboardButton(text="📲 Get Number", callback_data="buy")
    )
    kb.row(
        InlineKeyboardButton(text="💳 Recharge", callback_data="recharge"),
        InlineKeyboardButton(text="🛠️ Support", url="https://t.me/hehe_stalker")
    )
    kb.row(
        InlineKeyboardButton(text="📜 Terms of Use", url="https://telegra.ph/Terms-of-Use--Quick-Codes-Bot-08-31"),
        InlineKeyboardButton(text="📦 Your Info", callback_data="stats")
    )
    kb.row(InlineKeyboardButton(text="🆘 How to Use?", callback_data="howto"))
    await m.answer(text, reply_markup=kb.as_markup())

# ===== Balance =====
@dp.callback_query(F.data == "balance")
async def show_balance(cq: CallbackQuery):
    user = users_col.find_one({"_id": cq.from_user.id})
    bal = user["balance"] if user else 0.0
    await cq.answer(f"💰 Your balance: {bal:.2f} ₹", show_alert=True)

@dp.message(Command("balance"))
async def cmd_balance(msg: Message):
    user = users_col.find_one({"_id": msg.from_user.id})
    bal = user["balance"] if user else 0.0
    await msg.answer(f"💰 Your balance: {bal:.2f} ₹")

# ===== Purchase Flow =====
@dp.callback_query(F.data == "buy")
async def callback_buy(cq: CallbackQuery):
    await cq.answer()
    kb = InlineKeyboardBuilder()
    kb.button(text="🇮🇳 India", callback_data="buy_country:India")
    kb.button(text="🇺🇿 Uzbekistan", callback_data="buy_country:Uzbekistan")
    kb.button(text="🇺🇿 Uzbekistan-Spam-Acc", callback_data="buy_country:Uzbekistan-Spam-Acc")
    kb.button(text="🇺🇸 USA", callback_data="buy_country:USA")
    kb.button(text="🇮🇳 Indian-Old-2024", callback_data="buy_country:Indian-Old-2024")
    kb.button(text="🇮🇳 Indian-Old-2023", callback_data="buy_country:Indian-Old-2023")
    kb.button(text="🇨🇴 Colombia", callback_data="buy_country:Colombia")
    kb.button(text="🇨🇴 Colombia-Old", callback_data="buy_country:Colombia-Old")
    kb.button(text="🇻🇳 Vietnam", callback_data="buy_country:Vietnam")
    kb.button(text="🇻🇳 Vietnam-Old", callback_data="buy_country:Vietnam-Old")
    kb.button(text="🇰🇪 Kenya-Old", callback_data="buy_country:Kenya-Old")
    kb.button(text="🇲🇦 Morocco", callback_data="buy_country:Morocco")
    kb.button(text="🇲🇦 Morocco-Old", callback_data="buy_country:Morocco-Old")
    kb.button(text="🇬🇭 Ghana-Old", callback_data="buy_country:Ghana-Old")
    kb.button(text="🇵🇭 Philippines-Old", callback_data="buy_country:Philippines-Old")
    kb.button(text="🇳🇬 Nigeria-Old", callback_data="buy_country:Nigeria-Old")
    kb.button(text="🇦🇷 Argentina", callback_data="buy_country:Argentina")
    kb.button(text="🇦🇷 Argentina-Old", callback_data="buy_country:Argentina-Old")
    kb.adjust(2)
    await cq.message.answer("🌍 Select a country:", reply_markup=kb.as_markup())
    
@dp.callback_query(F.data.startswith("buy_country:"))
async def on_choose_country(cq: CallbackQuery):
    await cq.answer()
    _, country = cq.data.split(":")
    kb = InlineKeyboardBuilder()
    kb.button(text="Telegram", callback_data=f"buy_service:{country}:Telegram")
    kb.button(text="WhatsApp", callback_data=f"buy_service:{country}:WhatsApp")
    kb.adjust(1)
    kb.button(text="🔙 Back", callback_data=f"buy")
    await cq.message.edit_text("💬 Select a service:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("buy_service:"))
async def on_buy_service(cq: CallbackQuery):
    await cq.answer()
    _, country, service = cq.data.split(":")
    kb = InlineKeyboardBuilder()
    operator_links = provider.get_operator_list(country, service)
    for op_id in operator_links.keys():
        price = provider.get_operator_price(country, service, op_id)
        kb.button(
            text=f"{op_id.upper()}-{DEFAULT_CURRENCY}{price} {country}-{service}",
            callback_data=f"confirm:{country}:{service}:{op_id}:{price}"
        )
    kb.adjust(1)
    kb.button(text="🔙 Back", callback_data=f"buy_country:{country}")
    kb.adjust(1)
    await cq.message.edit_text("🏢 Select an operator:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("confirm:"))
async def on_confirm(cq: CallbackQuery):
    await cq.answer()  # keeps Telegram happy (no timeout)
    
    _, country, service, op_id, price = cq.data.split(":")
    price = float(price)
    
    user = get_or_create_user(cq.from_user.id, cq.from_user.username)

    if user["balance"] < price or user["balance"] < MIN_BALANCE_REQUIRED:
        # Popup + proper message in chat
        await cq.answer("⚠️ Insufficient balance.", show_alert=True)
        await cq.message.answer("⚠️ You don’t have enough balance to complete this purchase.")
        return

    await cq.message.answer("⏳ Purchasing number...")
    try:
        url = provider.get_operator_url(country, service, op_id)
        resp = await provider.buy_number(url)
        if resp.get("status") != "success":
            return await cq.message.answer(f"❌ Purchase failed: {resp}")

        provider_order_id = str(resp["id"])
        number = str(resp["number"])
        users_col.update_one({"_id": user["_id"]}, {"$inc": {"balance": -price}})

        order_doc = {
            "user_id": user["_id"],
            "service": service,
            "country": country,
            "price": price,
            "provider_order_id": provider_order_id,
            "number": number,
            "status": "waiting_sms",
            "created_at": datetime.datetime.utcnow()
        }
        order_id = orders_col.insert_one(order_doc).inserted_id

        kb = InlineKeyboardBuilder()
        kb.button(text="❌ Cancel Order", callback_data=f"cancel:{str(order_id)}")
        await cq.message.answer(
            f"✅ Number purchased!\n\n<pre>👉 {country} - {service}</pre>\n📱 Number: <code>+{number}</code>\n💰 Price: ₹{price}\n\n"
            f"<blockquote><b>Note -</b><i>If there is already an account linked with this number, "
            f"wait 2 minutes and cancel the number, then try again 👍</i></blockquote>\n",
            reply_markup=kb.as_markup()
        )
        asyncio.create_task(poll_for_otp(order_id, provider_order_id, cq.message.chat.id))

    except ProviderError as e:
        await cq.message.answer(f"REQ FAILED: {e}")
    except Exception as e:
        await cq.message.answer(f"⚠️ Unexpected error: {e}")

# ===== Cancel =====
@dp.callback_query(F.data.startswith("cancel:"))
async def on_cancel(cq: CallbackQuery):
    order_id = ObjectId(cq.data.split(":")[1])
    order = orders_col.find_one({"_id": order_id})
    if not order:
        return await cq.answer("Order not found.", show_alert=True)
    if order["status"] == "received":
        return await cq.answer("❌ Cannot cancel. OTP already received.", show_alert=True)
    if (datetime.datetime.utcnow() - order["created_at"]).total_seconds() < 120:
        return await cq.answer("⏳ Cancel available after 2 minutes of purchase.", show_alert=True)

    provider_order_id = order.get("provider_order_id")
    if not provider_order_id:
        return await cq.answer("Activation ID not found. Cannot cancel.", show_alert=True)
    try:
        provider_cancelled = await cancel_number_on_provider(provider_order_id)
    except Exception as e:
        return await cq.answer(f"❌ Provider cancellation failed: {e}", show_alert=True)

    # Refund only if not already cancelled
    if order["status"] != "cancelled":
        if provider_cancelled:
            users_col.update_one({"_id": order["user_id"]}, {"$inc": {"balance": order["price"]}})
            orders_col.update_one({"_id": order_id}, {"$set": {"status": "cancelled"}})
            await cq.message.answer("❌ Order cancelled. Balance refunded and number released on provider.")
        else:
            # Check if provider already cancelled
            try:
                current_order = await provider.get_sms(provider_order_id)
                if current_order.get("status") == "cancelled":
                    users_col.update_one({"_id": order["user_id"]}, {"$inc": {"balance": order["price"]}})
                    orders_col.update_one({"_id": order_id}, {"$set": {"status": "cancelled"}})
                    await cq.message.answer("❌ Number was cancelled.\n\n✅ Balance refunded.")
                else:
                    await cq.answer("❌ Failed to cancel number on provider panel.", show_alert=True)
            except Exception:
                await cq.answer("❌ Failed to cancel number on provider panel.", show_alert=True)
    else:
        await cq.answer("❌ Order already cancelled.", show_alert=True)

# ===== Other Callbacks =====
@dp.callback_query(F.data == "howto")
async def callback_howto(cq: CallbackQuery):
    if not await check_join(bot, cq.message): return
    await cq.message.answer(
        "<b>📖 How to use QuickCodes Bot</b>\n1️⃣ Recharge\n2️⃣ Select Country + Operator\n3️⃣ Select App\n4️⃣ Click Purchase and 📩 Receive OTP\n\n"
        "✅ Done!\n🚀 Enjoy Fast OTP Services!\nNeed help? DM @Hehe_stalker"
    )
    await cq.answer()

# ===== Stats =====
@dp.message(Command("stats"))
async def cmd_stats(msg: Message):
    if not await check_join(bot, msg): return
    user = users_col.find_one({"_id": msg.from_user.id})
    if not user: return await msg.answer("❌ No data found for your account.")
    text = (
        f"📊 <b>Your Statistics</b>\n\n👤 Name: {msg.from_user.full_name}\n"
        f"🔹 Username: @{msg.from_user.username or '—'}\n🆔 User ID: <code>{msg.from_user.id}</code>\n"
        f"💰 Balance: ₹{user.get('balance', 0):.2f}\n"
    )
    await msg.answer(text, parse_mode="HTML")

@dp.callback_query(F.data == "stats")
async def callback_stats(cq: CallbackQuery):
    user = users_col.find_one({"_id": cq.from_user.id})
    if not user: return await cq.answer("❌ No data found for your account.", show_alert=True)
    text = (
        f"📊 <b>Your Statistics</b>\n\n👤 Name: {cq.from_user.full_name}\n"
        f"🔹 Username: @{cq.from_user.username or '—'}\n🆔 User ID: <code>{cq.from_user.id}</code>\n"
        f"💰 Balance: ₹{user.get('balance', 0):.2f}\n"
    )
    await cq.message.answer(text, parse_mode="HTML")
    await cq.answer()

# ===== Support =====
@dp.message(Command("support"))
async def cmd_support(msg: Message):
    if not await check_join(bot, msg): return
    text = f"👋 Hey {msg.from_user.full_name},\n\nIf you have any queries, feel free to contact our support."
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Contact Support", url="https://t.me/hehe_stalker")],
        [InlineKeyboardButton(text="📖 Terms of Use", url="https://telegra.ph/Terms-of-Use--Quick-Codes-Bot-08-31")]
    ])
    await msg.answer(text, reply_markup=kb)

# ===== Register external handlers =====
register_recharge_handlers(dp=dp, bot=bot, users_col=users_col, txns_col=txns_col, ADMIN_IDS=ADMIN_IDS)
register_admin_approval_handlers(dp=dp, bot=bot, users_col=users_col, txns_col=txns_col, ADMIN_IDS=ADMIN_IDS)
register_admin_command_handlers(dp=dp, bot=bot, users_col=users_col, ADMIN_IDS=ADMIN_IDS)
register_readymade_accounts_handlers(dp=dp, bot=bot, users_col=users_col)

# ===== Runner =====
async def main():
    print("Bot started.")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
























