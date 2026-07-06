"""Daily Telegram bot for SGX/RTAS rubber settlement prices.

Usage:
  python bot.py

Required environment variables:
  BOT_TOKEN - Telegram BotFather token
  CHAT_ID   - Telegram channel/group id or public @channel_username
"""
from __future__ import annotations

import os
import re
import sys
import html
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

RTAS_URL = os.getenv("RTAS_URL", "https://www.rtas.sg/rubber-prices/")
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()
TZ_NAME = os.getenv("TZ", "Asia/Yangon")
FOOTER = os.getenv(
    "FOOTER",
    "Live မဟုတ်ပါ။ RTAS/SGX official settlement price update ဖြစ်ပါသည်။",
)

USER_AGENT = (
    "Mozilla/5.0 (compatible; RubberDailyTelegramBot/1.0; "
    "+https://telegram.org/)"
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)


@dataclass
class RubberContract:
    product: str
    month: str
    raw_price: str

    @property
    def normalized_price(self) -> str:
        # RTAS/SGX often displays 280-4 style notation for 280.4.
        return re.sub(r"^(\d+)-(\d+)$", r"\1.\2", self.raw_price.strip())


def fetch_html(url: str = RTAS_URL) -> str:
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    return response.text


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _detect_product(context: str) -> str | None:
    lowered = context.lower()
    # Check TSR first because some page containers may include both product names.
    if "tsr" in lowered and "rubber" in lowered:
        return "SGX SICOM TSR20 FOB"
    if "rss" in lowered and "rubber" in lowered:
        return "SGX SICOM RSS3"
    return None


def _parse_table_rows(soup: BeautifulSoup) -> list[RubberContract]:
    contracts: list[RubberContract] = []
    seen: set[tuple[str, str, str]] = set()

    for table in soup.find_all("table"):
        # Find the closest heading/paragraph before the table that tells us RSS3 or TSR20.
        product = None
        for tag in table.find_all_previous(["h1", "h2", "h3", "h4", "h5", "p", "strong", "caption"], limit=50):
            text = _clean(tag.get_text(" ", strip=True))
            # Avoid giant wrapper nodes that can contain both RSS and TSR tables.
            if not text or len(text) > 180:
                continue
            product = _detect_product(text)
            if product:
                break
        if not product:
            continue

        for row in table.find_all("tr"):
            cells = [_clean(cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"])]
            if len(cells) < 2:
                continue
            month, price = cells[0], cells[1]
            if month.lower() == "month" or "settlement" in price.lower():
                continue
            if not re.search(r"\d", price):
                continue
            key = (product, month, price)
            if key not in seen:
                contracts.append(RubberContract(product, month, price))
                seen.add(key)

    return contracts


def _parse_text_fallback(soup: BeautifulSoup) -> list[RubberContract]:
    """Fallback parser for pages where tables are not standard HTML tables."""
    text = soup.get_text("\n", strip=True)
    products = [
        ("SGX SICOM RSS3", r"SICOM\s+RSS\s*3\s+Rubber\s+Futures"),
        ("SGX SICOM TSR20 FOB", r"SICOM\s+TSR\s*20\s+FOB\s+Rubber\s+Futures"),
    ]
    starts: list[tuple[int, str]] = []
    for product, pattern in products:
        match = re.search(pattern, text, flags=re.I)
        if match:
            starts.append((match.start(), product))
    starts.sort()

    contracts: list[RubberContract] = []
    for index, (start, product) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else len(text)
        section = text[start:end]
        pattern = re.compile(
            r"\b([A-Z][a-z]{2}(?:\s+\d{4})?)\b\s*\n\s*([0-9]+(?:[-.][0-9]+)?)",
            re.M,
        )
        for month, price in pattern.findall(section):
            contracts.append(RubberContract(product, month, price))
    return contracts


def parse_rtas_prices(page_html: str) -> list[RubberContract]:
    soup = BeautifulSoup(page_html, "lxml")
    contracts = _parse_table_rows(soup)
    if not contracts:
        contracts = _parse_text_fallback(soup)

    # Keep only the two products we want, and a sane number of rows per product.
    filtered: list[RubberContract] = []
    counts: dict[str, int] = {}
    for contract in contracts:
        if contract.product not in {"SGX SICOM RSS3", "SGX SICOM TSR20 FOB"}:
            continue
        counts.setdefault(contract.product, 0)
        if counts[contract.product] < 12:
            filtered.append(contract)
            counts[contract.product] += 1
    return filtered


def group_contracts(contracts: Iterable[RubberContract]) -> dict[str, list[RubberContract]]:
    grouped: dict[str, list[RubberContract]] = {}
    for contract in contracts:
        grouped.setdefault(contract.product, []).append(contract)
    return grouped


def build_message(contracts: list[RubberContract]) -> str:
    if not contracts:
        raise RuntimeError("No rubber price rows found from RTAS page.")

    tz = ZoneInfo(TZ_NAME)
    today = datetime.now(tz).strftime("%d %b %Y")
    grouped = group_contracts(contracts)

    lines: list[str] = [
        "🌏 နိုင်ငံတကာ ရော်ဘာစျေးနှုန်း Update",
        f"📅 {today}",
        "",
        "Unit: US cents/kg",
        "",
    ]

    product_icons = {
        "SGX SICOM RSS3": "🇸🇬 SGX SICOM RSS3",
        "SGX SICOM TSR20 FOB": "🇸🇬 SGX SICOM TSR20 FOB",
    }

    for product in ["SGX SICOM RSS3", "SGX SICOM TSR20 FOB"]:
        rows = grouped.get(product, [])
        if not rows:
            continue
        lines.append(product_icons[product])
        for row in rows[:6]:
            lines.append(f"• {row.month}: {row.normalized_price}")
        lines.append("")

    if FOOTER:
        lines.extend(["မှတ်ချက်: " + FOOTER, "Source: RTAS / SGX"])
    else:
        lines.append("Source: RTAS / SGX")

    return "\n".join(lines).strip()


def send_telegram_message(text: str) -> dict:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Add it to environment variables or .env")
    if not CHAT_ID:
        raise RuntimeError("CHAT_ID is missing. Add @channel_username or numeric id to environment variables or .env")

    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "disable_web_page_preview": True,
    }
    response = requests.post(api_url, data=payload, timeout=30)
    try:
        data = response.json()
    except Exception:
        response.raise_for_status()
        raise
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")
    return data


def main() -> int:
    try:
        html_text = fetch_html()
        contracts = parse_rtas_prices(html_text)
        message = build_message(contracts)
        logging.info("Prepared message:\n%s", message)
        result = send_telegram_message(message)
        logging.info("Telegram message sent: %s", result.get("ok"))
        return 0
    except Exception as exc:
        logging.exception("Bot failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
