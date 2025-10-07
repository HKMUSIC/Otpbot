# config.py
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")  # Telegram bot token
MONGODB_URI = os.getenv("MONGODB_URI")  # MongoDB connection string
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()}
CURRENCY_SYMBOL = os.getenv("CURRENCY_SYMBOL", "₹")
DEFAULT_PRICE = float(os.getenv("DEFAULT_PRICE", "140.0"))
