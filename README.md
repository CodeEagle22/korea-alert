# MU Alert System — Automated Setup (GitHub Actions + Telegram)

## Files
- `mu_alert_system.py` — deterministic rule engine + honest explainer (no invented numbers)
- `mu_data_fetch.py` — pulls real OHLCV from Yahoo Finance, computes EMA20/50, RSI14, ATR14, relative volume
- `telegram_notify.py` — formats result and sends it to Telegram
- `.github/workflows/mu-alert.yml` — runs the check daily and notifies you

## One-time setup

1. **Create a repo** on GitHub and push these files into its root (keep the
   `.github/workflows/mu-alert.yml` path exactly as-is).

2. **Create a Telegram bot**
   - Message `@BotFather` on Telegram → `/newbot` → follow prompts → copy the **bot token**.

3. **Get your chat ID**
   - Message your new bot anything (e.g. "hi").
   - Visit: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
   - Find `"chat":{"id": ...}` in the JSON response → that number is your **chat ID**.

4. **Add GitHub secrets**
   - Repo → Settings → Secrets and variables → Actions → New repository secret
   - Add `TELEGRAM_BOT_TOKEN` = your bot token
   - Add `TELEGRAM_CHAT_ID` = your chat ID

5. **Test it manually**
   - Repo → Actions → "MU Alert Check" → Run workflow (button)
   - Check the run logs and your Telegram chat for the message.

## Schedule
Default: weekdays at 21:30 UTC (after US market close). Edit the `cron` line
in `mu-alert.yml` to change timing. GitHub cron times can lag a few minutes;
this is normal for free-tier Actions.

## What it does NOT do
- Does not place trades or give buy/sell instructions — output uses phrases
  like "bullish confirmation", "bearish risk", "watch only" only.
- Does not invent any price/indicator — every number in the Telegram message
  traces back to Yahoo Finance data fetched that run.
- If Yahoo Finance data is insufficient, the run fails loudly (exit code 1)
  rather than sending a fabricated signal — check the Actions log if you get
  no Telegram message.

## Local test (before pushing to GitHub)
```bash
pip install yfinance pandas --break-system-packages
export TELEGRAM_BOT_TOKEN=xxx
export TELEGRAM_CHAT_ID=xxx
python3 telegram_notify.py MU
```
