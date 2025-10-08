import os
from dotenv import load_dotenv

load_dotenv()

def _getenv(name: str, default: str | None = None, required: bool = False) -> str:
    val = os.getenv(name, default)
    if required and (val is None or val == ""):
        raise RuntimeError(f"Missing required env var: {name}")
    return val
    
MUST_JOIN_CHANNEL = "@QuickCodesGc"
BOT_TOKEN = _getenv("BOT_TOKEN", required=True)
ADMIN_IDS = [int(i) for i in _getenv("ADMIN_IDS", "", required=True).replace(" ", "").split(",") if i]
API_ID = "21377358"
API_HASH = "e05bc1f4f03839db7864a99dbf72d1cd"

DATABASE_URL = _getenv("DATABASE_URL", "mongodb+srv://quickcodes:Stalker123@quickcodes.dm6vjhj.mongodb.net/?retryWrites=true&w=majority&appName=QuickCodes")

# Temporasms API
API_KEY = "f6ba51d5bfa7ae4861968713433255134984"
PROVIDER_API_KEY = "f6ba51d5bfa7ae4861968713433255134984"
PROVIDER_BASE_URL = "https://api.temporasms.com/stubs/handler_api.php"
PROVIDER_ENDPOINT_GET_NUMBER = _getenv("PROVIDER_ENDPOINT_GET_NUMBER", required=True)
PROVIDER_ENDPOINT_GET_SMS = _getenv("PROVIDER_ENDPOINT_GET_SMS", required=True)

PROVIDER_PARAM_APIKEY = _getenv("PROVIDER_PARAM_APIKEY", "api_key")
PROVIDER_PARAM_SERVICE = _getenv("PROVIDER_PARAM_SERVICE", "service")
PROVIDER_PARAM_COUNTRY = _getenv("PROVIDER_PARAM_COUNTRY", "country")
PROVIDER_PARAM_ORDER_ID = _getenv("PROVIDER_PARAM_ORDER_ID", "id")

DEFAULT_CURRENCY = _getenv("DEFAULT_CURRENCY", "₹")
MIN_BALANCE_REQUIRED = float(_getenv("MIN_BALANCE_REQUIRED", "0"))
