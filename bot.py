# bot.py
import logging
import os
import asyncio
from typing import Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler

from config import BOT_TOKEN, ADMIN_IDS, CURRENCY_SYMBOL, DEFAULT_PRICE
from db import db, users_col, stock_col, tx_col, get_or_create_user, ensure_indexes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# States for conversation handlers
ASK_QUANTITY = 1
ADMIN_AWAITING_NUMBER = 2

COUNTRIES = [
    ("USA", "🇺🇸"),
    ("India", "🇮🇳"),
    ("China", "🇨🇳"),
    ("Indonesia", "🇮🇩"),
    ("Chile", "🇨🇱"),
    # add others as needed
]

def country_keyboard():
    kb = []
    for c, emoji in COUNTRIES:
        kb.append([InlineKeyboardButton(f"{c} {emoji}", callback_data=f"country:{c}")])
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

async def send_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await get_or_create_user(user.id, user.username)
    text = (
        "👋 Welcome!\n\n"
        "We sell Telegram virtual numbers. Use the buttons below.\n\n"
        "Important: This bot does NOT automate OTP retrieval. You must request the OTP in your Telegram X app after copying the number. "
        "If you want to integrate an SMS provider, please do so with explicit consent and a legal provider. See /help."
    )
    await update.message.reply_photo(photo="https://telegra.ph/file/placeholder-start-image.png", caption=text, reply_markup=start_keyboard())

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await send_welcome(update, context)
    else:
        # cases when invoked via callback query
        await update.callback_query.answer()
        await send_welcome(update, context)

async def button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    await query.answer()
    data = query.data

    if data == "balance":
        u = await get_or_create_user(user.id, user.username)
        bal = u.get("balance", 0.0)
        await query.edit_message_text(f"💳 Your balance: {CURRENCY_SYMBOL}{bal:.2f}", reply_markup=start_keyboard())

    elif data == "accdetails":
        u = await get_or_create_user(user.id, user.username)
        text = f"Account details:\n\nUsername: @{u.get('username')}\nBalance: {CURRENCY_SYMBOL}{u.get('balance',0):.2f}"
        await query.edit_message_text(text, reply_markup=start_keyboard())

    elif data == "recharge":
        await query.edit_message_text("🔄 To recharge, send money to our payment gateway. (Recharge logic placeholder)\n\nAfter payment, contact admin with TXN ID or use /recharge command.", reply_markup=start_keyboard())

    elif data == "support":
        await query.edit_message_text("🆘 Support:\nContact @YourSupportHandle or reply here and an admin will assist.", reply_markup=start_keyboard())

    elif data == "buy_account":
        await query.edit_message_text("Select country:", reply_markup=country_keyboard())

    elif data.startswith("country:"):
        country = data.split(":",1)[1]
        # show the template message for the selected country with buy inline
        price = DEFAULT_PRICE
        available = await stock_col.count_documents({"country": country})
        text = (
            f"⚡ Telegram Account Info\n\n"
            f"🌍 Country : {country}\n"
            f"💸 Price : {CURRENCY_SYMBOL}{price:.2f}\n"
            f"📦 Available : {available}\n"
            f"🔍 Reliable | Affordable | Good Quality\n\n"
            "⚠️ Important: Please use Telegram X only to login.\n"
            "🚫 We are not responsible for freeze/ban if logged in with other apps."
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛒 Buy Now", callback_data=f"buynow:{country}")],
            [InlineKeyboardButton("🔙 Go back", callback_data="buy_account")]
        ])
        await query.edit_message_text(text, reply_markup=kb)

    elif data == "buy_account":
        await query.edit_message_text("Select country:", reply_markup=country_keyboard())

    elif data.startswith("buynow:"):
        country = data.split(":",1)[1]
        # ask quantity
        context.user_data["pending_country"] = country
        await query.edit_message_text(f"How many accounts do you want to buy from {country}? Please reply with a number.")
        return

    elif data == "copy_number":
        # this callback will be created dynamically in buy flow; handle generically
        await query.answer(text="Number copied (use your Telegram client to copy).")

    elif data == "i_requested_otp":
        # user indicates they requested OTP in their Telegram X app
        await query.edit_message_text("✅ Please paste the OTP you received here (if you want us to assist). Note: do NOT share OTPs for accounts you do not own.", reply_markup=None)

    else:
        await query.edit_message_text("Unknown action.", reply_markup=start_keyboard())

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()

    # Admin addstock flow
    if user.id in ADMIN_IDS and context.user_data.get("awaiting_stock_country"):
        country = context.user_data.pop("awaiting_stock_country")
        # Expectation: Admin sends the phone number in plain text
        number = text.split()[0]
        # Store number in stock with available flag
        await stock_col.insert_one({
            "country": country,
            "number": number,
            "meta": {"added_by": user.id, "status": "available"}
        })
        await update.message.reply_text(f"✅ Number {number} added to stock for {country}.")
        return

    # If user replying with quantity after buynow
    if context.user_data.get("pending_country") and text.isdigit():
        qty = int(text)
        country = context.user_data.pop("pending_country")
        # check stock count
        available_count = await stock_col.count_documents({"country": country, "meta.status": {"$ne": "sold"}})
        price_per = DEFAULT_PRICE
        total = price_per * qty
        user_doc = await get_or_create_user(user.id, user.username)
        balance = user_doc.get("balance", 0.0)

        if available_count < qty:
            await update.message.reply_text(f"❌ Only {available_count} accounts available in {country}. Please reduce quantity or choose another country.")
            return

        if balance < total:
            # insufficient funds
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Recharge", callback_data="recharge")]])
            await update.message.reply_text(
                f"💳 Your balance is {CURRENCY_SYMBOL}{balance:.2f}.\n💸 Price is {CURRENCY_SYMBOL}{total:.2f}.\n\n⚠️ Please deposit more funds to continue.",
                reply_markup=kb
            )
            return

        # proceed: allocate `qty` entries and mark sold
        cursor = stock_col.find({"country": country, "meta.status": {"$ne": "sold"}}).limit(qty)
        items = await cursor.to_list(length=qty)
        numbers = [it["number"] for it in items]

        # update stock as sold (atomic-ish)
        for it in items:
            await stock_col.update_one({"_id": it["_id"]}, {"$set": {"meta.status": "sold", "meta.sold_to": user.id, "meta.sold_at": asyncio.get_event_loop().time()}})

        # deduct balance and create tx
        await users_col.update_one({"telegram_id": user.id}, {"$inc": {"balance": -total}})
        await tx_col.insert_one({
            "user_id": user.id,
            "type": "purchase",
            "amount": total,
            "currency": CURRENCY_SYMBOL,
            "country": country,
            "numbers": numbers,
            "created_at": asyncio.get_event_loop().time()
        })

        new_bal_doc = await users_col.find_one({"telegram_id": user.id})
        new_balance = new_bal_doc.get("balance", 0.0)

        # Send success message including copy number and next steps
        # If qty==1, show number inline. If multiple, list them and instruct user.
        if qty == 1:
            number = numbers[0]
            text = (
                "✅ Purchase Successful!\n\n"
                f"🌍 Country: {country}\n"
                f"📱 Number: {number}\n\n"
                f"💸 Deducted: {CURRENCY_SYMBOL}{total:.2f}\n"
                f"💰 Balance Left: {CURRENCY_SYMBOL}{new_balance:.2f}\n\n"
                "👉 Copy the number and open Telegram X, paste the number, request login.\n\n"
                "After requesting the login code in your Telegram X, come back here and press 'I requested OTP'.\n\n"
                "⚠️ This bot will NOT attempt to fetch the OTP automatically."
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Copy Number (tap)", callback_data="copy_number")],
                [InlineKeyboardButton("🔐 I requested OTP", callback_data="i_requested_otp")]
            ])
            await update.message.reply_text(text, reply_markup=kb)
        else:
            # multiple numbers
            lines = "\n".join(f"{i+1}. {n}" for i,n in enumerate(numbers))
            text = (
                "✅ Purchase Successful!\n\n"
                f"🌍 Country: {country}\n"
                f"📱 Numbers:\n{lines}\n\n"
                f"💸 Deducted: {CURRENCY_SYMBOL}{total:.2f}\n"
                f"💰 Balance Left: {CURRENCY_SYMBOL}{new_balance:.2f}\n\n"
                "👉 Copy the numbers and open Telegram X, paste the number(s), request login.\n\n"
                "After requesting the login code(s), come back here and press 'I requested OTP'.\n\n"
                "⚠️ This bot will NOT attempt to fetch the OTP automatically."
            )
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔐 I requested OTP", callback_data="i_requested_otp")]])
            await update.message.reply_text(text, reply_markup=kb)

        return

    # default fallback
    await update.message.reply_text("I didn't understand that. Use /start to open the menu.")

# Admin command: /addstock
async def cmd_addstock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("Unauthorized.")
        return
    # show country keyboard; admin selects one -> then we ask them to send number
    kb = country_keyboard()
    await update.message.reply_text("Select country to add stock:", reply_markup=kb)
    # we put a marker so when callback arrives we set awaiting_country flag
    context.user_data["admin_adding_stock"] = True

async def admin_country_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if not (data.startswith("country:") and context.user_data.get("admin_adding_stock")):
        # normal user flow handled elsewhere
        return await button_router(update, context)
    country = data.split(":",1)[1]
    context.user_data.pop("admin_adding_stock", None)
    context.user_data["awaiting_stock_country"] = country
    await query.edit_message_text(f"Send the phone number (one per message) to add to {country}. Admin: just send the number now.")

async def cmd_balance_topup_simulate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # helper for testing: admins can topup user balance
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("Unauthorized.")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /topup <telegram_id> <amount>")
        return
    target = int(args[0])
    amount = float(args[1])
    await users_col.update_one({"telegram_id": target}, {"$inc": {"balance": amount}})
    await update.message.reply_text(f"Done: topped up {target} by {CURRENCY_SYMBOL}{amount:.2f}")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Help:\n"
        "/start - show menu\n"
        "/addstock - admin: add a number to stock\n"
        "Buy flow is via inline menus. IMPORTANT: This bot does NOT automate fetching Telegram login codes or create sessions.\n"
        "If you need integration with a legal SMS provider, implement it server-side and ensure you have consent and a proper contract."
    )

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # startup ensure indexes
    async def on_startup(app):
        await ensure_indexes()
        logger.info("Indexes ensured")

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("addstock", cmd_addstock))
    app.add_handler(CommandHandler("topup", cmd_balance_topup_simulate))  # admin helper for testing

    # callback query routing
    app.add_handler(CallbackQueryHandler(admin_country_selected, pattern=r"^country:.*"))
    app.add_handler(CallbackQueryHandler(button_router, pattern=".*"))

    # text handler
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), text_handler))

    # run
    app.run_polling()

if __name__ == "__main__":
    main()
