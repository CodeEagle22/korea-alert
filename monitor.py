#!/usr/bin/env python3
"""
Portfolio Alert Monitor
Checks positions against trailing stops and correlation-based triggers,
sends an alert (webhook/Telegram/console) when action may be warranted.

Run manually:      python monitor.py
Run in background:  see README.md (cron or GitHub Actions)
"""

import os
import sys
import json
import yaml
import requests
import yfinance as yf
from datetime import datetime, timedelta

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yml")
STATE_PATH = os.path.join(os.path.dirname(__file__), "state.json")


def load_config():
    with open(CONFIG_PATH, "r") as f:
        raw = f.read()
    # expand ${ENV_VAR} placeholders
    for key, val in os.environ.items():
        raw = raw.replace(f"${{{key}}}", val)
    return yaml.safe_load(raw)


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def get_history(ticker, days=10):
    try:
        data = yf.Ticker(ticker).history(period=f"{days}d")
        return data
    except Exception as e:
        print(f"[WARN] Could not fetch {ticker}: {e}")
        return None


def check_position(key, cfg, state, alerts):
    ticker = cfg["ticker"]
    hist = get_history(ticker, cfg["lookback_days"] + 2)
    if hist is None or hist.empty:
        alerts.append(f"⚠️ {key}: no data returned for {ticker}")
        return

    last_price = float(hist["Close"].iloc[-1])
    rolling_high = float(hist["Close"].tail(cfg["lookback_days"]).max())
    trailing_stop = rolling_high * (1 - cfg["trailing_stop_pct"] / 100)
    effective_stop = max(trailing_stop, cfg["hard_floor"])

    prev_high = state.get(key, {}).get("rolling_high", 0)
    state.setdefault(key, {})["rolling_high"] = rolling_high
    state[key]["last_price"] = last_price
    state[key]["effective_stop"] = effective_stop
    state[key]["last_checked"] = datetime.utcnow().isoformat()

    breached = last_price < effective_stop
    near = last_price < effective_stop * 1.03  # within 3% of stop

    if breached:
        alerts.append(
            f"🔴 STOP BREACHED — {cfg['name']} ({ticker}): "
            f"price {last_price:.2f} {cfg['currency']} < stop {effective_stop:.2f}. "
            f"Review execute-vs-override decision."
        )
    elif near:
        alerts.append(
            f"🟡 WATCH — {cfg['name']} ({ticker}): "
            f"price {last_price:.2f} {cfg['currency']} approaching stop {effective_stop:.2f}."
        )


def check_correlation_triggers(cfg, alerts):
    trig = cfg.get("correlation_triggers", {})

    # SOX below 50-day MA
    sox = trig.get("sox_index")
    if sox:
        hist = get_history(sox["ticker"], 60)
        if hist is not None and len(hist) >= 50:
            ma50 = hist["Close"].tail(50).mean()
            last = hist["Close"].iloc[-1]
            if last < ma50:
                alerts.append(f"🔴 CORRELATION TRIGGER — SOX ({last:.1f}) below 50-day MA ({ma50:.1f}). Sector-wide confirmation signal.")

    # Daily-drop-pct triggers (DRAM ETF, Kospi)
    for name, key in [("dram_etf", "DRAM ETF"), ("kospi", "Kospi")]:
        t = trig.get(name)
        if not t:
            continue
        hist = get_history(t["ticker"], 5)
        if hist is not None and len(hist) >= 2:
            change_pct = (hist["Close"].iloc[-1] / hist["Close"].iloc[-2] - 1) * 100
            if change_pct <= -t["threshold"]:
                alerts.append(f"🔴 CORRELATION TRIGGER — {key} dropped {change_pct:.1f}% today (threshold {t['threshold']}%).")

    # FX move
    fx = trig.get("fx_krw_eur")
    if fx:
        hist = get_history(fx["pair"], 5)
        if hist is not None and len(hist) >= 2:
            change_pct = abs(hist["Close"].iloc[-1] / hist["Close"].iloc[-2] - 1) * 100
            if change_pct >= fx["threshold"]:
                alerts.append(f"🟡 FX TRIGGER — KRW/EUR moved {change_pct:.1f}% (threshold {fx['threshold']}%). Affects SKH GDR value.")


def send_alerts(cfg, alerts):
    if not alerts:
        print(f"[{datetime.utcnow().isoformat()}] No alerts. All positions within normal range.")
        return

    message = "📊 *Portfolio Alert* — " + datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC") + "\n\n"
    message += "\n".join(alerts)

    method = cfg["notifications"]["method"]

    if method == "console":
        print(message)

    elif method == "webhook":
        url = cfg["notifications"]["webhook_url"]
        if url and not url.startswith("${"):
            try:
                requests.post(url, json={"text": message}, timeout=10)
            except Exception as e:
                print(f"[WARN] Webhook send failed: {e}")
        print(message)  # also print for GitHub Actions logs

    elif method == "telegram":
        token = cfg["notifications"]["telegram_bot_token"]
        chat_id = cfg["notifications"]["telegram_chat_id"]
        if token and chat_id and not token.startswith("${"):
            try:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
                    timeout=10,
                )
            except Exception as e:
                print(f"[WARN] Telegram send failed: {e}")
        print(message)


def main():
    cfg = load_config()
    state = load_state()
    alerts = []

    for key, pos_cfg in cfg["positions"].items():
        check_position(key, pos_cfg, state, alerts)

    check_correlation_triggers(cfg, alerts)
    send_alerts(cfg, alerts)
    save_state(state)


if __name__ == "__main__":
    main()
