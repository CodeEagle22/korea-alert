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


def _json_safe(obj):
    """Recursively convert numpy/pandas scalar types to native Python types."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if hasattr(obj, "item"):  # numpy scalar (bool_, float64, int64, ...)
        return obj.item()
    return obj


def save_state(state):
    with open(STATE_PATH, "w") as f:
        json.dump(_json_safe(state), f, indent=2)


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
    pos_state = state.setdefault(key, {})

    if hist is None or hist.empty:
        # Only alert on missing data occasionally, not every run
        # (avoids permanent spam if a ticker symbol is wrong).
        miss_count = pos_state.get("missing_count", 0) + 1
        pos_state["missing_count"] = miss_count
        if miss_count in (1, 5, 20):
            alerts.append(f"⚠️ {key}: no data returned for ticker '{ticker}' ({miss_count}x). Check ticker symbol in config.yml.")
        return
    pos_state["missing_count"] = 0

    last_price = float(hist["Close"].iloc[-1])
    rolling_high = float(hist["Close"].tail(cfg["lookback_days"]).max())
    trailing_stop = rolling_high * (1 - cfg["trailing_stop_pct"] / 100)
    effective_stop = max(trailing_stop, cfg["hard_floor"])

    pos_state["rolling_high"] = rolling_high
    pos_state["last_price"] = last_price
    pos_state["effective_stop"] = effective_stop
    pos_state["last_checked"] = datetime.utcnow().isoformat()

    breached = bool(last_price < effective_stop)
    near = bool(last_price < effective_stop * 1.03)  # within 3% of stop

    current_status = "breached" if breached else ("watch" if near else "ok")
    prev_status = pos_state.get("alert_status", "ok")
    pos_state["alert_status"] = current_status

    # Only notify when status CHANGES (ok->watch, watch->breached, etc.),
    # not every run while it stays the same. Re-remind once/day if still breached.
    should_notify = current_status != prev_status
    if current_status == "breached" and not should_notify:
        last_notified = pos_state.get("breach_last_notified", "")
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if last_notified != today:
            should_notify = True
            pos_state["breach_last_notified"] = today

    if not should_notify:
        return

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
    elif prev_status != "ok":
        alerts.append(
            f"🟢 CLEARED — {cfg['name']} ({ticker}): "
            f"price {last_price:.2f} {cfg['currency']} back above stop {effective_stop:.2f}."
        )


def _notify_once_per_day(state, key, condition_met, message, alerts):
    """Fire an alert on new trigger, then at most once/day while it persists."""
    condition_met = bool(condition_met)  # numpy.bool_ -> Python bool (JSON-safe)
    cs = state.setdefault("correlation", {})
    prev = cs.get(key, {}).get("active", False)
    cs.setdefault(key, {})["active"] = condition_met

    if not condition_met:
        return  # no alert when condition isn't met; state already cleared above

    today = datetime.utcnow().strftime("%Y-%m-%d")
    last_notified = cs[key].get("last_notified", "")
    newly_triggered = not prev
    if newly_triggered or last_notified != today:
        alerts.append(message)
        cs[key]["last_notified"] = today


def check_correlation_triggers(cfg, state, alerts):
    trig = cfg.get("correlation_triggers", {})

    # SOX below 50-day MA
    sox = trig.get("sox_index")
    if sox:
        hist = get_history(sox["ticker"], 60)
        if hist is not None and len(hist) >= 50:
            ma50 = hist["Close"].tail(50).mean()
            last = hist["Close"].iloc[-1]
            condition = last < ma50
            _notify_once_per_day(
                state, "sox_below_50dma", condition,
                f"🔴 CORRELATION TRIGGER — SOX ({last:.1f}) below 50-day MA ({ma50:.1f}). Sector-wide confirmation signal.",
                alerts,
            )

    # Daily-drop-pct triggers (DRAM ETF, Kospi)
    for name, label in [("dram_etf", "DRAM ETF"), ("kospi", "Kospi")]:
        t = trig.get(name)
        if not t:
            continue
        hist = get_history(t["ticker"], 5)
        if hist is not None and len(hist) >= 2:
            change_pct = (hist["Close"].iloc[-1] / hist["Close"].iloc[-2] - 1) * 100
            condition = change_pct <= -t["threshold"]
            _notify_once_per_day(
                state, f"{name}_drop", condition,
                f"🔴 CORRELATION TRIGGER — {label} dropped {change_pct:.1f}% today (threshold {t['threshold']}%).",
                alerts,
            )

    # FX move
    fx = trig.get("fx_krw_eur")
    if fx:
        hist = get_history(fx["pair"], 5)
        if hist is not None and len(hist) >= 2:
            change_pct = abs(hist["Close"].iloc[-1] / hist["Close"].iloc[-2] - 1) * 100
            condition = change_pct >= fx["threshold"]
            _notify_once_per_day(
                state, "fx_krw_eur", condition,
                f"🟡 FX TRIGGER — KRW/EUR moved {change_pct:.1f}% (threshold {fx['threshold']}%). Affects SKH GDR value.",
                alerts,
            )


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

    check_correlation_triggers(cfg, state, alerts)
    send_alerts(cfg, alerts)
    save_state(state)


if __name__ == "__main__":
    main()
