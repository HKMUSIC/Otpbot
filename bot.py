# bot.py
import logging
import asyncio
from typing import Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from config import BOT_TOKEN, ADMIN_IDS, CURRENCY_SYMBOL, DEFAULT_PRICE
from db import db, users_col, stock_col, tx_col, get_or_create_user, ensure_indexes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# States for conversation handlers
ASK_QUANTITY = 1

COUNTRIES = [
    ("USA", "🇺🇸"),
    ("India", "🇮🇳"),
    ("China", "🇨🇳"),
    ("Indonesia", "🇮🇩"),
    ("Chile", "🇨🇱"),
]

# ----------------- Keyboards -----------------
def country_keyboard():
    kb = [[InlineKeyboardButton(f"{c} {emoji}", callback_data=f"country:{c}")] for c, emoji in COUNTRIES]
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="back:main")])
    return InlineKeyboardMarkup(kb)

def start_keyboard():
    kb = [
        [InlineKeyboardButton("💳 Balance", callback_data="balance")],
        [InlineKeyboardButton("📦 Account Details", callback_data="accdetails")],
        [InlineKeyboardButton("🔄 Recharge", callback_data="recharge")],
        [InlineKeyboardButton("🆘 Support", callback_data="support")],
        [InlineKeyboardButton("🛒 Buy Account", callback_data="buy_account")]
    ]
    return InlineKeyboardMarkup(kb)

# ----------------- Commands -----------------
async def send_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await get_or_create_user(user.id, user.username)
    text = (
        "👋 Welcome!\n\n"
        "We sell Telegram virtual numbers. Use the buttons below.\n\n"
        "⚠️ This bot does NOT automate OTP retrieval. Copy the number and use Telegram X."
    )
    await update.message.reply_photo(
        photo="https://telegra.ph/file/placeholder-start-image.png",
        caption=text,
        reply_markup=start_keyboard()
    )

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await send_welcome(update, context)
    else:
        await update.callback_query.answer()
        await send_welcome(update, context)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Help:\n"
        "/start - show menu\n"
        "/addstock - admin only\n"
        "Buy flow is via inline buttons.\n"
        "This bot does NOT fetch Telegram login codes automatically."
    )

# ----------------- Button Routing -----------------
async def button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    await query.answer()
    data = query.data

    if data == "balance":
        u = await get_or_create_user(user.id, user.username)
        await query.edit_message_text(f"💳 Balance: {CURRENCY_SYMBOL}{u.get('balance', 0.0):.2f}", reply_markup=start_keyboard())

    elif data == "accdetails":
        u = await get_or_create_user(user.id, user.username)
        text = f"Account details:\nUsername: @{u.get('username')}\nBalance: {CURRENCY_SYMBOL}{u.get('balance',0):.2f}"
        await query.edit_message_text(text, reply_markup=start_keyboard())

    elif data == "recharge":
        await query.edit_message_text("🔄 Recharge placeholder. Contact admin or use payment gateway.", reply_markup=start_keyboard())

    elif data == "support":
        await query.edit_message_text("🆘 Support: Contact @YourSupportHandle", reply_markup=start_keyboard())

    elif data == "buy_account":
        await query.edit_message_text("Select country:", reply_markup=country_keyboard())

    elif data.startswith("country:"):
        country = data.split(":",1)[1]
        available = await stock_col.count_documents({"country": country, "meta.status": {"$ne": "sold"}})
        text = (
            f"⚡ Telegram Account Info\n"
            f"🌍 Country : {country}\n"
            f"💸 Price : {CURRENCY_SYMBOL}{DEFAULT_PRICE:.2f}\n"
            f"📦 Available : {available}\n"
            f"🔍 Reliable | Affordable | Good Quality\n\n"
            "⚠️ Use Telegram X only. Not responsible for freeze/ban."
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛒 Buy Now", callback_data=f"buynow:{country}")],
            [InlineKeyboardButton("🔙 Go back", callback_data="buy_account")]
        ])
        await query.edit_message_text(text, reply_markup=kb)

    elif data.startswith("buynow:"):
        country = data.split(":",1)[1]
        context.user_data["pending_country"] = country
        await query.edit_message_text(f"How many accounts do you want from {country}? Reply with a number.")

# ----------------- Text Handler -----------------
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()

    # Admin adding stock
    if user.id in ADMIN_IDS and context.user_data.get("awaiting_stock_country"):
        country = context.user_data.pop("awaiting_stock_country")
        number = text.split()[0]
        await stock_col.insert_one({"country": country, "number": number, "meta": {"added_by": user.id, "status": "available"}})
        await update.message.reply_text(f"✅ Number {number} added to stock for {country}.")
        return

    # User buys accounts
    if context.user_data.get("pending_country") and text.isdigit():
        qty = int(text)
        country = context.user_data.pop("pending_country")
        available_count = await stock_col.count_documents({"country": country, "meta.status": {"$ne": "sold"}})
        total = DEFAULT_PRICE * qty
        user_doc = await get_or_create_user(user.id, user.username)
        balance = user_doc.get("balance", 0.0)

        if available_count < qty:
            await update.message.reply_text(f"❌ Only {available_count} accounts available in {country}.")
            return

        if balance < total:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Recharge", callback_data="recharge")]])
            await update.message.reply_text(f"💳 Balance: {CURRENCY_SYMBOL}{balance:.2f}\n💸 Price: {CURRENCY_SYMBOL}{total:.2f}\nDeposit more funds.", reply_markup=kb)
            return

        # Allocate numbers
        cursor = stock_col.find({"country": country, "meta.status": {"$ne": "sold"}}).limit(qty)
        items = await cursor.to_list(length=qty)
        numbers = [it["number"] for it in items]
        for it in items:
            await stock_col.update_one({"_id": it["_id"]}, {"$set": {"meta.status": "sold", "meta.sold_to": user.id, "meta.sold_at": asyncio.get_event_loop().time()}})

        # Deduct balance & record transaction
        await users_col.update_one({"telegram_id": user.id}, {"$inc": {"balance": -total}})
        await tx_col.insert_one({"user_id": user.id, "type": "purchase", "amount": total, "currency": CURRENCY_SYMBOL, "country": country, "numbers": numbers, "created_at": asyncio.get_event_loop().time()})
        new_balance = (await users_col.find_one({"telegram_id": user.id})).get("balance",0.0)

        # Reply success
        if qty == 1:
            num = numbers[0]
            text = (
                f"✅ Purchase Successful!\n\n"
                f"🌍 Country: {country}\n📱 Number: {num}\n💸 Deducted: {CURRENCY_SYMBOL}{total:.2f}\n💰 Balance Left: {CURRENCY_SYMBOL}{new_balance:.2f}\n\n"
                "👉 Copy the number and login via Telegram X."
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Copy Number", callback_data="copy_number")],
                [InlineKeyboardButton("🔐 I requested OTP", callback_data="i_requested_otp")]
            ])
            await update.message.reply_text(text, reply_markup=kb)
        else:
            lines = "\n".join(f"{i+1}. {n}" for i,n in enumerate(numbers))
            text = (
                f"✅ Purchase Successful!\n\n🌍 Country: {country}\n📱 Numbers:\n{lines}\n💸 Deducted: {CURRENCY_SYMBOL}{total:.2f}\n💰 Balance Left: {CURRENCY_SYMBOL}{new_balance:.2f}\n\n"
                "👉 Copy numbers and login via Telegram X."
            )
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔐 I requested OTP", callback_data="i_requested_otp")]])
            await update.message.reply_text(text, reply_markup=kb)
        return

    await update.message.reply_text("I didn't understand that. Use /start to open menu.")

# ----------------- Admin Commands -----------------
async def cmd_addstock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("Unauthorized.")
        return
    await update.message.reply_text("Select country to add stock:", reply_markup=country_keyboard())
    context.user_data["admin_adding_stock"] = True

async def admin_country_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if not (data.startswith("country:") and context.user_data.get("admin_adding_stock")):
        return await button_router(update, context)
    country = data.split(":",1)[1]
    context.user_data.pop("admin_adding_stock", None)
    context.user_data["awaiting_stock_country"] = country
    await query.edit_message_text(f"Send the phone number to add to {country}.")

# ----------------- Main -----------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    async def on_startup(app):
        await ensure_indexes()
        logger.info("Indexes ensured")

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("addstock", cmd_addstock))
    app.add_handler(CallbackQueryHandler(admin_country_selected, pattern=r"^country:.*"))
    app.add_handler(CallbackQueryHandler(button_router, pattern=".*"))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), text_handler))

    app.run_polling()

if __name__ == "__main__":
    main()
