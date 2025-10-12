import os
import json
from datetime import datetime
import pycountry
import phonenumbers

# --- Config ---
BASE_DIR = os.path.dirname(__file__)
PRICING_FILE = os.path.join(BASE_DIR, "pricing.json")
ADMIN_IDS = [8488180191]   # <- replace with your admin Telegram ID(s)

# Simple in-memory state for interactive command (replace with FSM if you prefer)
admin_state = {}  # key: admin_user_id -> {"step": "...", "country_input": "..."}

# ---------- JSON helpers ----------
def load_json(path, default):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2, ensure_ascii=False)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_pricing():
    return load_json(PRICING_FILE, {"default_price": 30.0, "prices": {}})

def save_pricing(data):
    save_json(PRICING_FILE, data)

# ---------- helpers to normalize country ----------
def country_name_to_iso(country_input: str):
    """
    Try to convert a country name like "India" or "india" or "IN" to ISO alpha-2 (IN).
    If unable, return uppercased input (so it still can be used as key).
    """
    if not country_input:
        return None
    s = country_input.strip()
    if len(s) == 2:
        return s.upper()
    # try exact match via pycountry
    try:
        # try by common name
        country = pycountry.countries.get(name=s)
        if country:
            return country.alpha_2
        # try by official_name
        country = next((c for c in pycountry.countries if getattr(c, 'official_name', '').lower() == s.lower()), None)
        if country:
            return country.alpha_2
        # try lookup by common name case-insensitive
        country = next((c for c in pycountry.countries if c.name.lower() == s.lower()), None)
        if country:
            return country.alpha_2
        # try partial matching (e.g., "United States")
        country = next((c for c in pycountry.countries if s.lower() in c.name.lower()), None)
        if country:
            return country.alpha_2
    except Exception:
        pass
    # fallback to None to indicate we couldn't map
    return None

# ---------- Bot handlers (aiogram style) ----------
# Note: Replace decorator usage to match your bot instance (dp) and imports
# Example assumes: from aiogram import Bot, Dispatcher, types
# and dp is your Dispatcher object and bot is your Bot object.

@dp.message_handler(commands=['setprice'])
async def cmd_setprice_start(message: types.Message):
    uid = message.from_user.id
    if uid not in ADMIN_IDS:
        return await message.reply("❌ Aap admin nahi ho. /setprice sirf admin ke liye hai.")
    admin_state[uid] = {"step": "await_country"}
    await message.reply("🔧 Enter the country name or ISO code for which you want to set price.\nExample: `India` or `IN`")

@dp.message_handler(func=lambda m: admin_state.get(m.from_user.id, {}).get("step") == "await_country")
async def cmd_setprice_country(message: types.Message):
    uid = message.from_user.id
    if uid not in ADMIN_IDS:
        admin_state.pop(uid, None)
        return await message.reply("❌ Unauthorized.")
    country_input = message.text.strip()
    iso = country_name_to_iso(country_input)
    if iso is None:
        # ask for confirmation: we couldn't map to ISO; we'll store by given name
        admin_state[uid] = {"step": "confirm_freeform_country", "country_input": country_input}
        return await message.reply(
            f"⚠️ Maine '{country_input}' ko standard ISO country code me map nahi kar paya.\n"
            "Agar aap same text (like 'India') ko key ke roop mein rakhna chahte hain, type `YES` to continue, otherwise resend country name."
        )

    # proceed to ask price
    admin_state[uid] = {"step": "await_price", "country_input": iso}
    await message.reply(f"Enter the selling price for {iso} (in INR). Example: `30`")

@dp.message_handler(func=lambda m: admin_state.get(m.from_user.id, {}).get("step") == "confirm_freeform_country")
async def cmd_setprice_confirm_freeform(message: types.Message):
    uid = message.from_user.id
    if uid not in ADMIN_IDS:
        admin_state.pop(uid, None)
        return await message.reply("❌ Unauthorized.")
    txt = message.text.strip().lower()
    if txt != "yes":
        admin_state.pop(uid, None)
        return await message.reply("Okay, cancelled. Send `/setprice` again to start over and give a different country name.")
    country_input = admin_state[uid]["country_input"]
    # accept freeform name as key
    admin_state[uid] = {"step": "await_price", "country_input": country_input}
    await message.reply(f"Enter the selling price for '{country_input}'. Example: `30`")

@dp.message_handler(func=lambda m: admin_state.get(m.from_user.id, {}).get("step") == "await_price")
async def cmd_setprice_price(message: types.Message):
    uid = message.from_user.id
    if uid not in ADMIN_IDS:
        admin_state.pop(uid, None)
        return await message.reply("❌ Unauthorized.")
    txt = message.text.strip()
    try:
        price = float(txt)
        if price < 0:
            raise ValueError()
    except:
        return await message.reply("❌ Price invalid. Send a positive number like `30`")

    country_key = admin_state[uid]["country_input"]
    # normalize country_key: if it's a 2-letter ISO stored earlier, keep it; else keep the text
    pricing = load_pricing()
    pricing.setdefault("prices", {})

    # If country_key is ISO (2 letters), store key as ISO. Otherwise store raw text.
    key_to_store = country_key if (isinstance(country_key, str) and len(country_key) == 2 and country_key.isalpha()) else country_key

    pricing["prices"][key_to_store] = price
    save_pricing(pricing)

    admin_state.pop(uid, None)
    await message.reply(f"✅ Saved successfully 🎉\nPrice for {key_to_store} set to ₹{price}")

# Optional: admin quick set via single message (fallback)
@dp.message_handler(commands=['setprice_quick'])
async def cmd_setprice_quick(message: types.Message):
    """
    Alternative quick usage: /setprice_quick IN 30
    """
    uid = message.from_user.id
    if uid not in ADMIN_IDS:
        return await message.reply("❌ Not authorized.")
    parts = message.text.strip().split(maxsplit=2)
    if len(parts) < 3:
        return await message.reply("Usage: /setprice_quick <COUNTRY_OR_ISO> <PRICE>\nExample: /setprice_quick IN 30")
    country_input = parts[1].strip()
    try:
        price = float(parts[2].strip())
    except:
        return await message.reply("Price must be a number.")
    iso = country_name_to_iso(country_input)
    key_to_store = iso if iso else country_input
    pricing = load_pricing()
    pricing.setdefault("prices", {})[key_to_store] = price
    save_pricing(pricing)
    await message.reply(f"✅ Saved successfully 🎉\nPrice for {key_to_store} set to ₹{price}")

# ---------- show pricing ----------
@dp.message_handler(commands=['show_pricing'])
async def cmd_show_pricing(message: types.Message):
    pricing = load_pricing()
    lines = [f"Default: ₹{pricing.get('default_price', 30.0)}"]
    for c, p in pricing.get("prices", {}).items():
        lines.append(f"{c}: ₹{p}")
    await message.reply("Current pricing:\n" + "\n".join(lines))
