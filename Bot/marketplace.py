import os, json, uuid, time
from datetime import datetime

BASE_DIR = os.path.dirname(__file__)
SALES_FILE = os.path.join(BASE_DIR, "sales.json")

def load_sales():
    if not os.path.exists(SALES_FILE):
        with open(SALES_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)
    with open(SALES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_sales(data):
    with open(SALES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def make_listing_id():
    return f"L{int(time.time())}_{uuid.uuid4().hex[:6]}"

def make_token():
    return uuid.uuid4().hex[:8]
