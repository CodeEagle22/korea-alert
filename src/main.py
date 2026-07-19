"""Main entry point — run from GitHub Actions or locally."""
import os
import sys
from datetime import datetime, timezone, timedelta

from data import fetch
from signals import analyze
from telegram import send

KST = timezone(timedelta(hours=9))
MARKET_OPEN = 9    # 09:00 KST
MARKET_CLOSE = 15  # 15:30 KST (use 15 for simplicity)

TICKERS = {
    "SK Hynix": "000660.KS",
    "KOSPI":    "^KS11",
}


def in_market_hours() -> bool:
    now = datetime.now(KST)
    # ponytail: skip holiday check, yfinance returns stale data on holidays anyway
    return now.weekday() < 5 and MARKET_OPEN <= now.hour < MARKET_CLOSE


def main() -> None:
    if not in_market_hours():
        print("Outside Korean market hours — exiting")
        sys.exit(0)

    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    prices = {name: fetch(ticker) for name, ticker in TICKERS.items()}

    kospi_daily = float((prices["KOSPI"].iloc[-1] / prices["KOSPI"].iloc[-2] - 1) * 100)

    results = [
        analyze("SK Hynix", prices["SK Hynix"], peer_daily=kospi_daily),
        analyze("KOSPI",    prices["KOSPI"],    peer_daily=None),
    ]

    for r in results:
        print(f"{r.ticker}: {r.signal} (conf={r.confidence}%, stress={r.margin_stress})")

    send(results, bot_token, chat_id)


if __name__ == "__main__":
    main()
