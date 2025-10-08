import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGODB_URI

_client = AsyncIOMotorClient(MONGODB_URI)

# Try to get default database, fallback to manual db name
if _client.get_default_database():
    db = _client.get_default_database()
else:
    db = _client["telegramBot"]  # fallback default name

# Collections
users_col = db["users"]
stock_col = db["stock"]
tx_col = db["transactions"]

# convenience init
async def ensure_indexes():
    await users_col.create_index("telegram_id", unique=True)
    await stock_col.create_index([("country", 1)])
    await tx_col.create_index("user_id")

# utility to get or create user
async def get_or_create_user(telegram_id, username=None):
    user = await users_col.find_one({"telegram_id": telegram_id})
    if not user:
        user = {
            "telegram_id": telegram_id,
            "username": username,
            "balance": 0.0,
            "created_at": asyncio.get_event_loop().time()
        }
        await users_col.insert_one(user)
        user = await users_col.find_one({"telegram_id": telegram_id})
    return user
