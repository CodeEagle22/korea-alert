"""Send Telegram alerts; skip duplicates unless something changed."""
import json
import os
from pathlib import Path

import requests

STATE_FILE = Path("/tmp/korea_alert_state.json")


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state))


def _key(r) -> str:
    return f"{r.signal}:{r.risk}:{r.margin_stress // 20}"  # bucket stress in 20-pt bands


def should_send(results: list) -> tuple[bool, str]:
    state = _load_state()
    reasons = []
    for r in results:
        prev = state.get(r.ticker, {})
        if prev.get("signal") != r.signal:
            reasons.append(f"{r.ticker} signal changed → {r.signal}")
        if r.risk == "HIGH" and prev.get("risk") != "HIGH":
            reasons.append(f"{r.ticker} risk became HIGH")
        prev_stress = prev.get("stress", 0)
        if r.margin_stress - prev_stress >= 20:
            reasons.append(f"{r.ticker} margin stress +{r.margin_stress - prev_stress}")
        if r.daily_pct < -3:
            reasons.append(f"{r.ticker} major drop {r.daily_pct:.1f}%")
    return bool(reasons), "; ".join(reasons)


def send(results: list, bot_token: str, chat_id: str) -> None:
    ok, why = should_send(results)
    if not ok:
        print("No change — skipping alert")
        return

    lines = ["🇰🇷 *Korea Market Alert*\n"]
    for r in results:
        stress_label = "HIGH" if r.margin_stress >= 60 else "MEDIUM" if r.margin_stress >= 30 else "LOW"
        lines += [
            f"*{r.ticker}*: {r.signal}",
            f"Confidence: {r.confidence}%",
            f"Price: {r.price:,.0f}",
            f"Daily Change: {r.daily_pct:+.1f}%",
            f"RSI: {r.rsi_val:.0f} | Mom5: {r.mom5:+.1f}% | Vol: {r.vol:.0f}%",
            f"Risk: {r.risk} | Margin Stress: {stress_label} ({r.margin_stress})",
            "",
        ]
    if any(r.reasons for r in results):
        lines.append("*Reasons:*")
        for r in results:
            for reason in r.reasons:
                lines.append(f"• {reason}")

    text = "\n".join(lines)
    resp = requests.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
        timeout=10,
    )
    resp.raise_for_status()
    print(f"Alert sent: {why}")

    # persist state
    state = _load_state()
    for r in results:
        state[r.ticker] = {"signal": r.signal, "risk": r.risk, "stress": r.margin_stress}
    _save_state(state)
