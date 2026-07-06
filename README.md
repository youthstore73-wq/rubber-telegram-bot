# Daily Rubber Price Telegram Bot

Fetches SGX SICOM RSS3 and TSR20 FOB official settlement prices from RTAS and posts them to a Telegram channel/group.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python bot.py
```

Required environment variables:

```env
BOT_TOKEN=your_telegram_bot_token
CHAT_ID=@your_public_channel_or_numeric_chat_id
```

## Schedule with GitHub Actions

Add repository secrets:

- `BOT_TOKEN`
- `CHAT_ID`

The workflow in `.github/workflows/daily.yml` runs on weekdays at 02:30 UTC, approximately 09:00 Myanmar time.

## Notes

This is not live pricing. It posts daily official settlement / delayed data from RTAS/SGX and includes source credit.
