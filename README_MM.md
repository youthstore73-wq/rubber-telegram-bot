# နေ့စဉ် Rubber Price Telegram Bot

ဒီ project က RTAS page ပေါ်က SGX SICOM RSS3 / TSR20 FOB official settlement prices ကိုနေ့စဉ် Telegram channel/group ထဲ auto post လုပ်ဖို့ပါ။

## ၁။ Telegram Bot Token ယူရန်

1. Telegram မှာ `@BotFather` ကိုဖွင့်ပါ။
2. `/newbot` လို့ပို့ပါ။
3. Bot name နဲ့ username ပေးပါ။
4. BotFather ပေးတဲ့ token ကို copy လုပ်ပါ။

## ၂။ Channel ထဲ Bot ထည့်ရန်

1. ကိုယ့် Telegram Channel ကိုဖွင့်ပါ။
2. Administrators ထဲမှာ Bot ကို add ပါ။
3. Bot ကို **Post Messages** permission ပေးပါ။
4. Channel က public ဖြစ်ရင် `CHAT_ID=@your_channel_username` လို့သုံးနိုင်ပါတယ်။
5. Private channel/group ဖြစ်ရင် numeric chat id `-100...` လိုအပ်နိုင်ပါတယ်။

## ၃။ Local မှာ Run စမ်းရန်

```bash
python -m venv .venv
source .venv/bin/activate   # Windows ဆို .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

`.env` file ထဲမှာ ဒီနှစ်ခုကိုဖြည့်ပါ။

```env
BOT_TOKEN=BotFather ကပေးတဲ့ token
CHAT_ID=@your_channel_username
```

Run စမ်းရန် —

```bash
python bot.py
```

အောင်မြင်ရင် Telegram channel ထဲ message တက်လာပါမယ်။

## ၄။ GitHub Actions နဲ့နေ့စဉ် Auto Post လုပ်ရန်

1. ဒီ folder ကို GitHub repository တစ်ခုတင်ပါ။
2. Repository > Settings > Secrets and variables > Actions > New repository secret မှာ ထည့်ပါ။
   - `BOT_TOKEN`
   - `CHAT_ID`
3. `.github/workflows/daily.yml` ထဲက cron time ကိုလိုချင်သလိုပြင်ပါ။

Cron example:

```yaml
- cron: "30 2 * * 1-5"
```

ဒါက UTC 02:30 ဖြစ်ပြီး Myanmar time 09:00 AM ဝန်းကျင်ပါ။

## ၅။ Message ပုံစံ

```text
🌏 နိုင်ငံတကာ ရော်ဘာစျေးနှုန်း Update
📅 06 Jul 2026

Unit: US cents/kg

🇸🇬 SGX SICOM RSS3
• Aug 2026: xxx.x
• Sep: xxx.x

🇸🇬 SGX SICOM TSR20 FOB
• Aug 2026: xxx.x
• Sep: xxx.x

မှတ်ချက်: Live မဟုတ်ပါ။ RTAS/SGX official settlement price update ဖြစ်ပါသည်။
Source: RTAS / SGX
```

## သတိပြုရန်

- ဒီ bot က live price မဟုတ်ပါ။ RTAS/SGX official settlement price ကိုနေ့စဉ် update လုပ်တာပါ။
- Website structure ပြောင်းသွားရင် parser ကိုပြင်ဖို့လိုနိုင်ပါတယ်။
- Public channel မှာတင်တဲ့အခါ source credit ထည့်ထားတာကောင်းပါတယ်။
