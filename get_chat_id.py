"""Helper to inspect Telegram updates and find numeric chat IDs.

Usage:
  BOT_TOKEN=123:ABC python get_chat_id.py

For private channels/groups: add your bot, send a test message/post, then run this script.
"""
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN missing. Add it to .env or environment.")

url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
res = requests.get(url, timeout=30)
res.raise_for_status()
print(json.dumps(res.json(), indent=2, ensure_ascii=False))
