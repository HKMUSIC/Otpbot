import datetime
import asyncio
import re
from bson import ObjectId
from aiogram import F
from aiogram.types import CallbackQuery, Message, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import StateFilter, Command
from mustjoin import check_join
import requests
from aiogram import Bot
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from requests.auth import HTTPBasicAuth

# Import your Fampay checker function
from fampaymodule import check_fampay_emails  # should return (found: bool, sender: str)

# --- Initialize bot and dispatcher ---
bot = Bot(token="8240394115:AAHoBxLr30amA7X4SfvAuEGI2pcGoYQkHP4")
dp = Dispatcher(storage=MemoryStorage())
# Recharge FSM
class RechargeState(StatesGroup):
    choose_method = State()
    waiting_deposit_screenshot = State()
    waiting_deposit_amount = State()


def register_recharge_handlers(dp, bot, users_col, txns_col, ADMIN_IDS):
    # ========= Helper =========
    async def start_recharge_flow(message: Message, state: FSMContext):
        kb = InlineKeyboardBuilder()
        kb.button(text="Pay Manually", callback_data="recharge_manual")
        kb.button(text="Automatic", callback_data="recharge_auto")
        kb.adjust(2)

        text = (
            "💰 Add Funds to Your Account\n\n"
            "We only accept payments via UPI.\n"
            "• Automatic payments are now available via Fampay.\n\n"
            "Please choose a method below:"
        )

        msg = await message.answer(text, reply_markup=kb.as_markup())
        await state.update_data(recharge_msg_id=msg.message_id)
        await state.set_state(RechargeState.choose_method)

    # ========= Entry Points =========
    @dp.callback_query(F.data == "recharge")
    async def recharge_start_button(cq: CallbackQuery, state: FSMContext):
        await start_recharge_flow(cq.message, state)
        await cq.answer()

    @dp.message(Command("recharge"))
    async def recharge_start_command(message: Message, state: FSMContext):
        if not await check_join(bot, message):
            return
        await start_recharge_flow(message, state)

    # ========= Flow Handlers =========
    @dp.callback_query(F.data == "recharge_auto", StateFilter(RechargeState.choose_method))
    async def recharge_auto(cq: CallbackQuery, state: FSMContext):
        # Follow manual flow until deposit button
        data = await state.get_data()
        msg_id = data.get("recharge_msg_id")

        kb = InlineKeyboardBuilder()
        kb.button(text="Deposit Now", callback_data="deposit_now")
        kb.button(text="Go Back", callback_data="go_back")
        kb.adjust(2)

        text = (
            f"Hello {cq.from_user.full_name},\n\n"
            "You have chosen the automatic payment method via Fampay.\n\n"
            "Please proceed to deposit using the options below:"
        )

        await bot.edit_message_text(
            text=text,
            chat_id=cq.from_user.id,
            message_id=msg_id,
            reply_markup=kb.as_markup()
        )
        await cq.answer()

    @dp.callback_query(F.data == "recharge_manual", StateFilter(RechargeState.choose_method))
    async def recharge_manual(cq: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        msg_id = data.get("recharge_msg_id")

        kb = InlineKeyboardBuilder()
        kb.button(text="Deposit Now", callback_data="deposit_now")
        kb.button(text="Go Back", callback_data="go_back")
        kb.adjust(2)

        text = (
            f"Hello {cq.from_user.full_name},\n\n"
            "You have chosen the manual method to add balance to your account.\n"
            "Thanks for trusting us.\n\n"
            "In Manual Method, your payment will be processed via admin approval."
        )

        await bot.edit_message_text(
            text=text,
            chat_id=cq.from_user.id,
            message_id=msg_id,
            reply_markup=kb.as_markup()
        )
        await cq.answer()

    @dp.callback_query(F.data == "go_back", StateFilter(RechargeState.choose_method))
    async def recharge_go_back(cq: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        msg_id = data.get("recharge_msg_id")

        kb = InlineKeyboardBuilder()
        kb.button(text="Pay Manually", callback_data="recharge_manual")
        kb.button(text="Automatic", callback_data="recharge_auto")
        kb.adjust(2)

        text = (
            "💰 Add Funds to Your Account\n\n"
            "We only accept payments via UPI.\n"
            "• Automatic payments are now available via Fampay.\n\n"
            "Please choose a method below:"
        )

        await bot.edit_message_text(
            text=text,
            chat_id=cq.from_user.id,
            message_id=msg_id,
            reply_markup=kb.as_markup()
        )
        await cq.answer()

    # ========= Deposit Options =========
    @dp.callback_query(F.data == "deposit_now", StateFilter(RechargeState.choose_method))
    async def deposit_now(cq: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        msg_id = data.get("recharge_msg_id")

        kb = InlineKeyboardBuilder()
        kb.button(text="UPI", callback_data="upi_qr")
        kb.button(text="Crypto", callback_data="crypto_pay")
        kb.button(text="Razorpay", callback_data="razorpay_qr")
        kb.button(text="Go Back", callback_data="go_back")
        kb.adjust(2, 1)

        text = "Select your preferred payment method:\n\n1 INR = 1 INR\n1 USDT = ₹88"

        await bot.edit_message_text(
            text=text,
            chat_id=cq.from_user.id,
            message_id=msg_id,
            reply_markup=kb.as_markup()
        )
        await cq.answer()

    # ===== Crypto Payment Flow =====
    @dp.callback_query(F.data == "crypto_pay", StateFilter(RechargeState.choose_method))
    async def crypto_pay(cq: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        msg_id = data.get("recharge_msg_id")

        kb = InlineKeyboardBuilder()
        kb.button(text="Submit Payment", callback_data="crypto_submit")
        kb.button(text="Go Back", callback_data="deposit_now")
        kb.adjust(2)

        text = (
            "🪙 <b>Make Payment via Crypto</b>\n\n"
            "Send your payment to the USDT wallet addresses below:\n\n"
            "📥 <b>TRC20 Address:</b>\n<code>TW4oPVrKNYsaht3MyHiDbxt9gDM9LbRUy6</code>\n\n"
            "🌐 <b>BEP20 Address:</b>\n<code>0xdc714CDA825542C0c223a340d3D1e75BB93F6d7c</code>\n\n"
            "💜 <b>POLYGON Address:</b>\n<code>0xdc714CDA825542C0c223a340d3D1e75BB93F6d7c</code>\n\n"
            "💰 <b>Minimum Payment:</b> 0.01 USDT\n"
            "💱 <b>Exchange Rate:</b> 1 USDT = ₹88\n\n"
            "📸 After completing the payment, take a screenshot.\n\n"
            "🔘 Tap <b>'Submit Payment'</b> below to continue."
        )

        await bot.edit_message_text(
            text=text,
            chat_id=cq.from_user.id,
            message_id=msg_id,
            parse_mode="HTML",
            reply_markup=kb.as_markup()
        )
        await cq.answer()

    @dp.callback_query(F.data == "crypto_submit", StateFilter(RechargeState.choose_method))
    async def crypto_submit(cq: CallbackQuery, state: FSMContext):
        try:
            await cq.message.delete()
        except:
            pass
        await cq.message.answer("📸 Please send a screenshot of your Crypto payment.")
        await state.update_data(is_crypto=True)
        await state.set_state(RechargeState.waiting_deposit_screenshot)
        await cq.answer()

    # ===== UPI QR Flow =====
    @dp.callback_query(F.data == "upi_qr", StateFilter(RechargeState.choose_method))
    async def upi_qr(cq: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        msg_id = data.get("recharge_msg_id")
        try:
            await bot.delete_message(chat_id=cq.from_user.id, message_id=msg_id)
        except:
            pass

        qr_image = FSInputFile("IMG_20251011_222812_469.jpg")

        kb = InlineKeyboardBuilder()
        kb.button(text="Deposit", callback_data="send_deposit")
        kb.button(text="Go Back", callback_data="go_back")
        kb.adjust(2)

        text = (
            "🔝 Send INR on this QR Code.\n"
            "💳 Or Pay To:\n\n<code>prabhat896@ptaxis</code>\n"
            "✅ After Payment, Click Deposit Button."
        )

        msg = await cq.message.answer_photo(
            photo=qr_image,
            caption=text,
            parse_mode="HTML",
            reply_markup=kb.as_markup()
        )
        await state.update_data(recharge_msg_id=msg.message_id)
        await cq.answer()

    # ===== Fampay Automatic QR Flow =====
    @dp.callback_query(F.data == "fampay_auto", StateFilter(RechargeState.choose_method))
    async def fampay_auto(cq: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        msg_id = data.get("recharge_msg_id")
        qr_image = FSInputFile("Screenshot_2025-09-06-09-31-25-25_ba41e9a642e6e0e2b03656bfbbffd6e4.jpg")  # same QR as manual

        kb = InlineKeyboardBuilder()
        kb.button(text="Deposit", callback_data="fampay_deposit")
        kb.button(text="Go Back", callback_data="deposit_now")
        kb.adjust(2)

        text = (
            "🔝 Send INR on this QR Code via Fampay.\n"
            "💳 Or Pay To:\n\n<code>iybhathstalker@fam</code>\n"
            "✅ After Payment, Click Deposit Button.\n\n"
            "📌 Automatic payments will be verified via Fampay transaction ID."
        )

        msg = await cq.message.answer_photo(
            photo=qr_image,
            caption=text,
            parse_mode="HTML",
            reply_markup=kb.as_markup()
        )
        await state.update_data(recharge_msg_id=msg.message_id)
        await cq.answer()
        
# =====razor atomatic QR Flow =====
    @dp.callback_query(F.data == "razorpay_qr", StateFilter(RechargeState.choose_method))
    async def fampay_auto(cq: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        msg_id = data.get("recharge_msg_id")
        
        try:
            await bot.delete_message(chat_id=cq.from_user.id, message_id=msg_id)
            
        except:
            pass
            qr_image = FSInputFile("QrCode.jpeg.png")  # your saved QR image
            kb = InlineKeyboardBuilder()
            kb.button(text="✅ Done", callback_data="razorpay_done")
            kb.button(text="Go Back", callback_data="deposit_now")
            kb.adjust(2)
            text = (
                "💳 <b>Razorpay Payment</b>\n\n"
                "📲 Scan this QR and make payment via any UPI app.\n\n"
                "✅ Once payment is done, tap 'Done' and send your UTR (Transaction ID) when asked."
            )
            msg = await cq.message.answer_photo(
                photo=qr_image,
                caption=text,
                parse_mode="HTML",
                reply_markup=kb.as_markup()
            )
            await state.update_data(recharge_msg_id=msg.message_id)
            await cq.answer()


@dp.callback_query(F.data == "razorpay_done", StateFilter(RechargeState.choose_method))
async def razorpay_done(cq: CallbackQuery, state: FSMContext):
    await cq.message.answer("💬 Please send your UTR / Transaction ID to verify your payment.")
    await state.update_data(is_razorpay=True)
    await state.set_state(RechargeState.waiting_deposit_amount)
    await cq.answer()
  
    is_razorpay = data.get("is_razorpay", False)
    if is_razorpay:
        utr = message.text.strip()
        await message.answer("⏳ Verifying your payment with Razorpay...")
        url = f"https://api.razorpay.com/v1/payments?qr_id={RAZORPAY_QR_ID}"
        res = requests.get(url, auth=HTTPBasicAuth(RAZORPAY_KEY, RAZORPAY_SECRET))
        data_rz = res.json()
        
        verified = False
        payment_found = None
        for p in data_rz.get("items", []):
            txn_id = p.get("acquirer_data", {}).get("bank_transaction_id")
            if txn_id and utr in txn_id and p["status"] == "captured":
                verified = True
                payment_found = p
                break
                
                user = message.from_user
                
                if verified:
                    amount = payment_found["amount"] / 100  # Razorpay gives paise
                    users_col.update_one({"_id": user.id}, {"$inc": {"balance": amount}})
                    await message.answer(f"✅ Payment verified! ₹{amount} credited successfully.")
                    await state.clear()
                
                else:
                    await message.answer(
                        "❌ Could not verify your payment automatically.\n"
                        "Your payment has been sent for manual review."
                    )
                    
                    txn_doc = {
                        "user_id": user.id,
                        "username": user.username,
                        "full_name": user.full_name,
                        "is_razorpay": True,
                        "utr": utr,
                        "status": "pending",
                        "created_at": datetime.datetime.utcnow()
                    
                    }
                    txn_id = txns_col.insert_one(txn_doc).inserted_ikb_admin = InlineKeyboardBuilder()
                    kb_admin.button(text="✅ Approve", callback_data=f"approve_txn:{txn_id}")
                    kb_admin.button(text="❌ Decline", callback_data=f"decline_txn:{txn_id}")
                    kb_admin.adjust(2)
                    
                    for admin_id in ADMIN_IDS:
                        try:
                            await bot.send_message(
                                
                                chat_id=admin_id,
                                
                                text=(
                                    f"<b>Manual Razorpay Verification Required</b>\n\n"
                                    f"Name: {user.full_name}\n"
                                    f"Username: @{user.username}\n"
                                    f"UTR: {utr}"
                                ),
                                parse_mode="HTML",
                                reply_markup=kb_admin.as_markup()
                            )
                        except Exception:
                            pass
                            await state.clear()
                            return

    # ===== Fampay Deposit Handling =====
    @dp.callback_query(F.data == "fampay_deposit", StateFilter(RechargeState.choose_method))
    async def fampay_deposit(cq: CallbackQuery, state: FSMContext):
        try:
            await cq.message.delete()
        except:
            pass
        await cq.message.answer(
            "📸 Please send a screenshot of your Fampay payment.\n"
            "💰 Also enter the amount and your Fampay Transaction ID in the format:\n"
            "`Amount | TransactionID`"
        )
        await state.update_data(is_fampay=True)
        await state.set_state(RechargeState.waiting_deposit_screenshot)
        await cq.answer()

    # ===== Screenshot & Amount Input =====
    @dp.message(StateFilter(RechargeState.waiting_deposit_screenshot))
    async def screenshot_fampay(message: Message, state: FSMContext):
        data = await state.get_data()
        is_fampay = data.get("is_fampay", False)

        if message.photo:
            await state.update_data(screenshot=message.photo[-1].file_id)
            await message.answer("✅ Screenshot received.\nNow, send `Amount | TransactionID`.")
            return

        if is_fampay and "|" in message.text:
            try:
                amount_str, txnid = map(str.strip, message.text.split("|"))
                amount = float(amount_str)
            except:
                await message.answer("❌ Invalid format. Please use `Amount | TransactionID`.")
                return

            # Check Fampay IMAP for the txn id (up to 10 sec)
            found = False
            for _ in range(2):  # check 5 times, 2 sec interval
                found, sender = check_fampay_emails(txnid)
                if found:
                    break
                await asyncio.sleep(1)

            user = message.from_user
            screenshot = data.get("screenshot")

            if found:
                # Directly credit balance
                users_col.update_one({"_id": user.id}, {"$inc": {"balance": amount}})
                await message.answer(f"✅ Payment confirmed! ₹{amount} has been credited to your account.")
                await state.clear()
            else:
                # Send to admin for manual approval
                txn_doc = {
                    "user_id": user.id,
                    "username": user.username,
                    "full_name": user.full_name,
                    "is_crypto": False,
                    "is_fampay": True,
                    "amount": amount,
                    "original_amount": amount,
                    "screenshot": screenshot,
                    "fampay_txn_id": txnid,
                    "status": "pending",
                    "created_at": datetime.datetime.utcnow()
                }
                txn_id = txns_col.insert_one(txn_doc).inserted_id

                kb_admin = InlineKeyboardBuilder()
                kb_admin.button(text="✅ Approve", callback_data=f"approve_txn:{txn_id}")
                kb_admin.button(text="❌ Decline", callback_data=f"decline_txn:{txn_id}")
                kb_admin.adjust(2)

                for admin_id in ADMIN_IDS:
                    try:
                        await bot.send_photo(
                            chat_id=admin_id,
                            photo=screenshot,
                            caption=(
                                f"<b>Fampay Payment Approval Request</b>\n\n"
                                f"Name: {user.full_name}\n"
                                f"Username: @{user.username}\n"
                                f"ID: {user.id}\n"
                                f"Amount: {amount}\n"
                                f"Txn ID: {txnid}"
                            ),
                            parse_mode="HTML",
                            reply_markup=kb_admin.as_markup()
                        )
                    except Exception:
                        pass

                await message.answer(
                    f"❌ Transaction ID not found in Fampay.\n"
                    "Your payment has been sent for manual admin approval."
                )
                await state.clear()
        else:
            # Manual / Crypto flow handled separately
            # Trigger original amount entry logic
            await message.answer("📸 Screenshot received. Please proceed to enter the amount using buttons.")
            await screenshot_received(message, state)  # reuse existing handler
