import datetime
from bson import ObjectId
from aiogram import F
from aiogram.types import CallbackQuery, Message, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import StateFilter, Command
from mustjoin import check_join


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
            "• Automatic payments have been stopped for security reasons.\n\n"
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
    async def recharge_auto(cq: CallbackQuery):
        await cq.answer(
            "⚠️ Automatic payment feature is currently unavailable. Please choose manual payment.",
            show_alert=True
        )

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
            "• Automatic payments have been stopped for security reasons.\n\n"
            "Please choose a method below:"
        )

        await bot.edit_message_text(
            text=text,
            chat_id=cq.from_user.id,
            message_id=msg_id,
            reply_markup=kb.as_markup()
        )
        await cq.answer()

    @dp.callback_query(F.data == "deposit_now", StateFilter(RechargeState.choose_method))
    async def deposit_now(cq: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        msg_id = data.get("recharge_msg_id")

        kb = InlineKeyboardBuilder()
        kb.button(text="UPI", callback_data="upi_qr")
        kb.button(text="Go Back", callback_data="go_back")
        kb.adjust(2)

        text = "Select the UPI method below to deposit your funds.\n\n1 INR = 1 INR"

        await bot.edit_message_text(
            text=text,
            chat_id=cq.from_user.id,
            message_id=msg_id,
            reply_markup=kb.as_markup()
        )
        await cq.answer()

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

    # ===== Amount Input Calculator =====
    @dp.callback_query(F.data == "send_deposit", StateFilter(RechargeState.choose_method))
    async def send_deposit(cq: CallbackQuery, state: FSMContext):
        try:
            await cq.message.delete()
        except:
            pass
        await cq.message.answer("📸 Please send a screenshot of your payment.")
        await state.set_state(RechargeState.waiting_deposit_screenshot)
        await cq.answer()

    @dp.message(StateFilter(RechargeState.waiting_deposit_screenshot), F.photo)
    async def screenshot_received(message: Message, state: FSMContext):
        await state.update_data(screenshot=message.photo[-1].file_id)

        kb = InlineKeyboardBuilder()
        for row in ["123", "456", "789", "0"]:
            for ch in row:
                kb.button(text=ch, callback_data=f"amount_{ch}")
            kb.adjust(len(row))
        kb.button(text="❌", callback_data="amount_del")
        kb.button(text="✅", callback_data="amount_send")
        kb.adjust(3)

        msg = await message.answer("💰 Enter the amount you sent:\n0", reply_markup=kb.as_markup())
        await state.update_data(amount_msg_id=msg.message_id, amount_value="")
        await state.set_state(RechargeState.waiting_deposit_amount)

    @dp.callback_query(StateFilter(RechargeState.waiting_deposit_amount))
    async def amount_button_pressed(cq: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        value = data.get("amount_value", "")
        kb = cq.message.reply_markup

        if cq.data.startswith("amount_"):
            key = cq.data.split("_")[1]
            if key == "del":
                value = value[:-1]
            elif key == "send":
                if not value:
                    await cq.answer("❌ Please enter a valid amount.", show_alert=True)
                    return

                # Save transaction
                screenshot = data.get("screenshot")
                user = cq.from_user
                txn_doc = {
                    "user_id": user.id,
                    "username": user.username,
                    "full_name": user.full_name,
                    "amount": float(value),
                    "screenshot": screenshot,
                    "status": "pending",
                    "created_at": datetime.datetime.utcnow()
                }
                txn_id = txns_col.insert_one(txn_doc).inserted_id

                await cq.message.edit_text(
                    f"✅ Your payment request of ₹{value} has been sent to the admin.\n"
                    "Please wait for approval or DM @valriking for faster approvals."
                )
                await state.clear()

                # Admin buttons
                kb_admin = InlineKeyboardBuilder()
                kb_admin.button(text="✅ Approve", callback_data=f"approve_txn:{txn_id}")
                kb_admin.button(text="❌ Decline", callback_data=f"decline_txn:{txn_id}")
                kb_admin.adjust(2)

                # Send to admins
                for admin_id in ADMIN_IDS:
                    try:
                        await bot.send_photo(
                            chat_id=admin_id,
                            photo=screenshot,
                            caption=(
                                f"<b>Payment Approval Request</b>\n\n"
                                f"Name: {user.full_name}\n"
                                f"Username: @{user.username}\n"
                                f"ID: {user.id}\n"
                                f"Amount: {value}"
                            ),
                            parse_mode="HTML",
                            reply_markup=kb_admin.as_markup()
                        )
                    except Exception:
                        pass
                await cq.answer()
                return
            else:
                value += key

        display_value = value if value else "0"
        await cq.message.edit_text(f"💰 Enter the amount you sent:\n{display_value}", reply_markup=kb)
        await state.update_data(amount_value=value)
        await cq.answer()

    # ===== Admin Approval Handlers =====
    @dp.callback_query(F.data.startswith("approve_txn"))
    async def approve_txn(cq: CallbackQuery):
        txn_id = cq.data.split(":")[1]
        txn = txns_col.find_one({"_id": ObjectId(txn_id)})

        if not txn:
            await cq.answer("Transaction not found!", show_alert=True)
            return

        if txn.get("status") == "approved":
            await cq.answer("Already approved!", show_alert=True)
            return

        # Update transaction status
        txns_col.update_one({"_id": ObjectId(txn_id)}, {"$set": {"status": "approved"}})

        # Add balance to user
        user = users_col.find_one({"_id": txn["user_id"]})
        if user:
            new_balance = user.get("balance", 0.0) + txn["amount"]
            users_col.update_one({"_id": txn["user_id"]}, {"$set": {"balance": new_balance}})

            # Send message to user that payment approved
            try:
                await bot.send_message(
                    chat_id=txn["user_id"],
                    text=f"✅ Your payment of ₹{txn['amount']} has been approved and your new balance is ₹{new_balance:.2f}."
                )
            except Exception:
                pass

        await cq.message.edit_caption(cq.message.caption + "\n✅ Approved and balance credited")
        await cq.answer("Transaction approved and balance updated!")

    @dp.callback_query(F.data.startswith("decline_txn"))
    async def decline_txn(cq: CallbackQuery):
        txn_id = cq.data.split(":")[1]
        txn = txns_col.find_one({"_id": ObjectId(txn_id)})

        if not txn:
            await cq.answer("Transaction not found!", show_alert=True)
            return

        if txn.get("status") == "declined":
            await cq.answer("Already declined!", show_alert=True)
            return

        txns_col.update_one({"_id": ObjectId(txn_id)}, {"$set": {"status": "declined"}})
        await cq.message.edit_caption(cq.message.caption + "\n❌ Declined")
        await cq.answer("Transaction declined!")
