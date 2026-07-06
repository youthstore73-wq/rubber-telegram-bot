"""Daily Telegram bot for rubber, gold, and oil prices.

Required environment variables:
  BOT_TOKEN - Telegram BotFather token
  CHAT_ID   - Telegram chat id / group id / @channel_username
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable
from urllib.parse import quote
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
    "Live မဟုတ်ပါ။ Free/delayed daily market data update ဖြစ်ပါသည်။",
)

USER_AGENT = (
    "Mozilla/5.0 (compatible; DailyCommodityTelegramBot/2.0; "
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


@dataclass
class MarketQuote:
    name: str
    symbol: str
    price: float | None
    previous_close: float | None
    currency: str
    unit: str
    source: str

    @property
    def change(self) -> float | None:
        if self.price is None or self.previous_close is None:
            return None
        return self.price - self.previous_close

    @property
    def change_pct(self) -> float | None:
        if self.change is None or not self.previous_close:
            return None
        return (self.change / self.previous_close) * 100


def fetch_html(url: str = RTAS_URL) -> str:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()
    return response.text


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def extract_rtas_price_date(page_html: str) -> str | None:
    soup = BeautifulSoup(page_html, "lxml")
    text = soup.get_text("\n", strip=True)
    match = re.search(r"Daily Price\s*-\s*([^\n]+)", text, flags=re.I)
    return _clean(match.group(1)) if match else None


def _parse_section(lines: list[str], start_index: int, product: str) -> list[RubberContract]:
    rows: list[RubberContract] = []
    in_prices = False

    for line in lines[start_index + 1 :]:
        if any(stop in line for stop in [
            "SICOM RSS 3 Rubber Futures",
            "SICOM TSR 20 FOB Rubber Futures",
            "Reference Prices for Physical Rubber",
            "Archives",
            "Download Daily Price PDF",
        ]):
            break

        if "Month Settlement Price" in line:
            in_prices = True
            continue
        if not in_prices:
            continue

        match = re.match(r"^([A-Z][a-z]{2}(?:\s+\d{4})?)\s+(\d+(?:[-.]\d+)?)$", line)
        if match:
            month, price = match.groups()
            rows.append(RubberContract(product=product, month=month, raw_price=price))

    return rows


def parse_rtas_prices(page_html: str) -> list[RubberContract]:
    """Parse only SGX RSS3 and TSR20 settlement tables from RTAS."""
    soup = BeautifulSoup(page_html, "lxml")
    lines = [_clean(line) for line in soup.get_text("\n", strip=True).splitlines()]
    lines = [line for line in lines if line]

    contracts: list[RubberContract] = []
    product_markers = {
        "SICOM RSS 3 Rubber Futures": "SGX SICOM RSS3",
        "SICOM TSR 20 FOB Rubber Futures": "SGX SICOM TSR20 FOB",
    }

    for i, line in enumerate(lines):
        for marker, product in product_markers.items():
            if marker.lower() == line.lower():
                contracts.extend(_parse_section(lines, i, product))

    return contracts


def fetch_yahoo_quote(symbol: str, name: str, unit: str) -> MarketQuote | None:
    """Fetch delayed/free quote-like data from Yahoo Finance chart endpoint.

    This is suitable for a private informational bot, not for trading or redistribution.
    """
    encoded = quote(symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?range=5d&interval=1d"

    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        response.raise_for_status()
        data = response.json()
        result = data.get("chart", {}).get("result", [None])[0]
        if not result:
            raise RuntimeError(data.get("chart", {}).get("error") or "No Yahoo result")

        meta = result.get("meta", {})
        price = meta.get("regularMarketPrice")
        previous_close = meta.get("chartPreviousClose") or meta.get("previousClose")
        currency = meta.get("currency") or "USD"

        # If the meta price is missing, use the latest close value from the chart.
        quote_data = (result.get("indicators", {}).get("quote") or [{}])[0]
        closes = [v for v in quote_data.get("close", []) if isinstance(v, (int, float))]
        if price is None and closes:
            price = closes[-1]
        if previous_close is None and len(closes) >= 2:
            previous_close = closes[-2]

        if price is None:
            raise RuntimeError("Price not found")

        return MarketQuote(
            name=name,
            symbol=symbol,
            price=float(price),
            previous_close=float(previous_close) if previous_close is not None else None,
            currency=currency,
            unit=unit,
            source="Yahoo Finance",
        )
    except Exception as exc:
        logging.warning("Could not fetch %s (%s): %s", name, symbol, exc)
        return None


def fetch_gold_oil_quotes() -> list[MarketQuote]:
    # GC=F: COMEX Gold futures, CL=F: NYMEX WTI crude futures, BZ=F: Brent crude futures.
    targets = [
        ("GC=F", "Gold Futures", "USD/troy oz"),
        ("CL=F", "WTI Crude Oil Futures", "USD/barrel"),
        ("BZ=F", "Brent Crude Oil Futures", "USD/barrel"),
    ]
    quotes: list[MarketQuote] = []
    for symbol, name, unit in targets:
        quote_data = fetch_yahoo_quote(symbol, name, unit)
        if quote_data:
            quotes.append(quote_data)
    return quotes


def group_contracts(contracts: Iterable[RubberContract]) -> dict[str, list[RubberContract]]:
    grouped: dict[str, list[RubberContract]] = {}
    for contract in contracts:
        grouped.setdefault(contract.product, []).append(contract)
    return grouped


def _format_market_quote(q: MarketQuote) -> str:
    if q.price is None:
        return f"• {q.name}: မရရှိပါ"

    change_text = ""
    if q.change is not None and q.change_pct is not None:
        sign = "+" if q.change >= 0 else ""
        change_text = f" ({sign}{q.change:.2f}, {sign}{q.change_pct:.2f}%)"

    return f"• {q.name}: {q.price:,.2f} {q.unit}{change_text}"



def _to_float(value: str) -> float | None:
    try:
        return float(re.sub(r"^(\d+)-(\d+)$", r"\1.\2", value.strip()))
    except Exception:
        return None


def _direction_from_change_pct(change_pct: float | None, up_threshold: float = 0.35, down_threshold: float = -0.35) -> tuple[str, str]:
    """Return short Myanmar direction label and reason from a daily % change."""
    if change_pct is None:
        return "ဘက်မသေချာ", "နေ့စဉ်ပြောင်းလဲမှု data မပြည့်စုံ"
    if change_pct >= up_threshold:
        return "တက်ဘက်အားသာ", f"နေ့စဉ်ပြောင်းလဲမှု +{change_pct:.2f}% ဖြစ်နေ"
    if change_pct <= down_threshold:
        return "ကျဘက်အားသာ", f"နေ့စဉ်ပြောင်းလဲမှု {change_pct:.2f}% ဖြစ်နေ"
    return "ဘက်မရှင်း", f"နေ့စဉ်ပြောင်းလဲမှု {change_pct:+.2f}% သာရှိပြီး momentum မပြင်း"


def analyze_rubber_contracts(contracts: list[RubberContract], product: str) -> list[str]:
    rows = group_contracts(contracts).get(product, [])
    prices: list[tuple[str, float]] = []
    for row in rows[:6]:
        value = _to_float(row.normalized_price)
        if value is not None:
            prices.append((row.month, value))

    if len(prices) < 2:
        return [f"• {product}: data မလုံလောက်လို့ ခန့်မှန်းချက်မပေးနိုင်ပါ"]

    near_month, near_price = prices[0]
    far_month, far_price = prices[-1]
    curve_pct = ((far_price - near_price) / near_price) * 100 if near_price else 0.0

    if curve_pct >= 0.8:
        direction = "အနည်းငယ်တက်ဘက်"
        reason = f"{near_month} မှ {far_month} အထိ futures curve +{curve_pct:.2f}% မြင့်နေ"
    elif curve_pct <= -0.8:
        direction = "အနည်းငယ်ကျဘက်"
        reason = f"{near_month} မှ {far_month} အထိ futures curve {curve_pct:.2f}% နိမ့်နေ"
    else:
        direction = "ဘက်မရှင်း"
        reason = f"{near_month} မှ {far_month} အထိ futures curve {curve_pct:+.2f}% ပဲကွာ"

    return [
        f"• {product}: {direction}",
        f"  အကြောင်းပြချက်: {reason}",
    ]


def build_market_report(contracts: list[RubberContract], market_quotes: list[MarketQuote]) -> list[str]:
    """Build a short rule-based market comment for the Telegram message.

    This is not a prediction model. It only summarizes futures curve shape and delayed
    daily momentum from the available free data.
    """
    lines: list[str] = [
        "📊 စျေးသုံးသပ်ချက် / အတက်အကျ အလားအလာ",
        "မှတ်ချက်: ခန့်မှန်းချက်မဟုတ်ပါ။ Free/delayed data ကို rule-based နဲ့ဖတ်ထားခြင်းသာဖြစ်ပါတယ်။",
        "",
    ]

    if contracts:
        lines.append("🛞 Rubber")
        lines.extend(analyze_rubber_contracts(contracts, "SGX SICOM RSS3"))
        lines.extend(analyze_rubber_contracts(contracts, "SGX SICOM TSR20 FOB"))
        lines.append("")

    if market_quotes:
        lines.append("🟡 ရွှေ / 🛢 ရေနံ")
        for quote_data in market_quotes:
            direction, reason = _direction_from_change_pct(quote_data.change_pct)
            lines.append(f"• {quote_data.name}: {direction}")
            lines.append(f"  အကြောင်းပြချက်: {reason}")
        lines.append("")

    lines.extend([
        "ဖတ်နည်း:",
        "• တက်ဘက်အားသာ = ဒီနေ့ data အရ buyer momentum ပိုကောင်းတဲ့ပုံစံ",
        "• ကျဘက်အားသာ = ဒီနေ့ data အရ seller pressure ပိုများတဲ့ပုံစံ",
        "• ဘက်မရှင်း = စောင့်ကြည့်သင့်တဲ့အခြေအနေ",
    ])
    return lines


def build_message(
    contracts: list[RubberContract],
    market_quotes: list[MarketQuote],
    rtas_price_date: str | None = None,
) -> str:
    tz = ZoneInfo(TZ_NAME)
    today = datetime.now(tz).strftime("%d %b %Y")
    grouped = group_contracts(contracts)

    lines: list[str] = [
        "🌏 နိုင်ငံတကာ စျေးနှုန်း Update",
        f"📅 Bot Date: {today}",
    ]
    if rtas_price_date:
        lines.append(f"📌 SGX/RTAS Rubber Daily Price: {rtas_price_date}")
    lines.append("")

    product_icons = {
        "SGX SICOM RSS3": "🇸🇬 SGX SICOM RSS3",
        "SGX SICOM TSR20 FOB": "🇸🇬 SGX SICOM TSR20 FOB",
    }

    if contracts:
        lines.extend(["🛞 Rubber Futures", "Unit: US cents/kg", ""])
        for product in ["SGX SICOM RSS3", "SGX SICOM TSR20 FOB"]:
            rows = grouped.get(product, [])
            if not rows:
                continue
            lines.append(product_icons[product])
            lines.append("Contract / Delivery Month")
            for row in rows[:6]:
                lines.append(f"• {row.month}: {row.normalized_price}")
            lines.append("")
    else:
        lines.extend(["🛞 Rubber Futures", "• RTAS data မရရှိပါ", ""])

    if market_quotes:
        lines.append("🟡 ရွှေ / 🛢 ရေနံ Futures")
        for quote_data in market_quotes:
            lines.append(_format_market_quote(quote_data))
        lines.append("")

    lines.extend(build_market_report(contracts, market_quotes))
    lines.append("")

    if FOOTER:
        lines.append("မှတ်ချက်: " + FOOTER)
    lines.append("Sources: RTAS/SGX, Yahoo Finance")

    return "\n".join(lines).strip()


def send_telegram_message(text: str) -> dict:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Add it to GitHub Secrets or .env")
    if not CHAT_ID:
        raise RuntimeError("CHAT_ID is missing. Add it to GitHub Secrets or .env")

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
        page_html = fetch_html()
        contracts = parse_rtas_prices(page_html)
        rtas_price_date = extract_rtas_price_date(page_html)
        market_quotes = fetch_gold_oil_quotes()
        message = build_message(contracts, market_quotes, rtas_price_date)
        logging.info("Prepared message:\n%s", message)
        result = send_telegram_message(message)
        logging.info("Telegram message sent: %s", result.get("ok"))
        return 0
    except Exception as exc:
        logging.exception("Bot failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
