# Korea Market Alert

Monitors SK Hynix (`000660.KS`) and KOSPI (`^KS11`) during Korean market hours and sends Telegram alerts when signals change.

## Setup

1. **Fork / clone** this repo.
2. Add two GitHub Secrets:
   - `TELEGRAM_BOT_TOKEN` — from [@BotFather](https://t.me/BotFather)
   - `TELEGRAM_CHAT_ID` — your chat or channel ID
3. GitHub Actions runs every 5 minutes on weekdays during KST market hours.

## Run locally

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...
python src/main.py
```

## Test

```bash
pytest -q
```

## Signals

| Signal | Meaning |
|--------|---------|
| BUY | RSI oversold + positive momentum |
| SELL | RSI overbought + negative momentum / sharp drop |
| HOLD | No clear edge |

**Margin Stress** (0–100): detects large drops, high volatility, deep drawdowns, and simultaneous SK Hynix + KOSPI weakness.

Alerts only fire on: signal change, risk becoming HIGH, stress jump ≥20 pts, or daily drop > 3%.

> ⚠️ Research tool only. No order execution.
