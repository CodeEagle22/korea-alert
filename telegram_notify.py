"""
telegram_notify.py
===================
Sends the MU signal explanation to a Telegram chat via Bot API.
Reads secrets from environment variables (set as GitHub Actions secrets):
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID

No prices/values are invented here — it only formats what mu_data_fetch.py
already computed from real market data.
"""

import os
import sys
import json
import urllib.request


def format_message(signal: dict, result: dict) -> str:
    lvl = result["monitoring_levels"]
    lines = [
        f"MU Alert: {result['alert_type']}  ({signal['timestamp']})",
        f"Price: {signal['last_price']}  RSI14: {signal['rsi14']}  RelVol: {signal['relative_volume']}",
        "",
        "Evidence:",
    ]
    for e in result["evidence"]:
        lines.append(f"- {e}")
    lines += [
        "",
        f"Invalidation: {result['invalidation']}",
        f"Risk note: {result['risk_note']}",
        "",
        f"Support: {lvl['key_support']}",
        f"Resistance: {lvl['key_resistance']}",
    ]
    if lvl["entry_reference"] is not None:
        lines.append(f"Entry ref: {lvl['entry_reference']}  Stop ref: {lvl['stop_reference']}")
    return "\n".join(lines)


def send_telegram(text: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"].strip()
    chat_id = os.environ["TELEGRAM_CHAT_ID"].strip()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Telegram send failed: HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Telegram API rejected the request: HTTP {e.code}\n"
            f"Response body: {body}\n"
            "Common causes: TELEGRAM_BOT_TOKEN wrong/malformed (404), "
            "or TELEGRAM_CHAT_ID wrong / bot never messaged first (400)."
        ) from e


if __name__ == "__main__":
    from mu_data_fetch import run

    symbol = sys.argv[1] if len(sys.argv) > 1 else "MU"
    signal, result = run(symbol)
    msg = format_message(signal.__dict__, result)
    print(msg)  # visible in GitHub Actions logs too
    send_telegram(msg)
