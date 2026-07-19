"""Generate BUY/SELL/HOLD signal with confidence, risk, and margin-stress score."""
from dataclasses import dataclass
from typing import Literal

import pandas as pd

from indicators import rsi, momentum, volatility, daily_change, drawdown

Signal = Literal["BUY", "SELL", "HOLD"]
Risk = Literal["LOW", "MEDIUM", "HIGH"]


@dataclass
class Result:
    ticker: str
    price: float
    daily_pct: float
    signal: Signal
    confidence: int       # 0-100
    risk: Risk
    margin_stress: int    # 0-100
    rsi_val: float
    mom5: float
    vol: float
    reasons: list[str]


def _margin_stress(daily_pct: float, vol: float, dd: float, peer_daily: float | None) -> int:
    score = 0
    if daily_pct < -3:
        score += 30
    elif daily_pct < -1.5:
        score += 15
    if vol > 40:
        score += 25
    elif vol > 25:
        score += 10
    if dd < -15:
        score += 25
    elif dd < -8:
        score += 10
    # simultaneous drop with peer (KOSPI or SK Hynix)
    if peer_daily is not None and peer_daily < -1.5 and daily_pct < -1.5:
        score += 20
    return min(score, 100)


def analyze(ticker: str, prices: pd.Series, peer_daily: float | None = None) -> Result:
    r = rsi(prices)
    mom = momentum(prices)
    vol = volatility(prices)
    dp = daily_change(prices)
    dd = drawdown(prices)
    price = float(prices.iloc[-1])

    reasons: list[str] = []
    bull = 0
    bear = 0

    if r < 30:
        bull += 2; reasons.append("RSI oversold")
    elif r > 70:
        bear += 2; reasons.append("RSI overbought")

    if mom > 3:
        bull += 2; reasons.append("Strong upside momentum")
    elif mom < -3:
        bear += 2; reasons.append("Strong downside momentum")

    if dp > 1.5:
        bull += 1
    elif dp < -1.5:
        bear += 1; reasons.append("Sharp daily drop")

    if vol > 35:
        bear += 1; reasons.append("High volatility")

    if peer_daily is not None and peer_daily < -1.5 and dp < -1.5:
        bear += 2; reasons.append("Market-wide weakness")

    total = bull + bear or 1
    if bull > bear:
        signal: Signal = "BUY"
        confidence = min(int(bull / total * 100) + 10, 95)
    elif bear > bull:
        signal = "SELL"
        confidence = min(int(bear / total * 100) + 10, 95)
    else:
        signal = "HOLD"
        confidence = 50

    stress = _margin_stress(dp, vol, dd, peer_daily)

    if stress >= 60 or vol > 40:
        risk: Risk = "HIGH"
    elif stress >= 30 or vol > 25:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    return Result(ticker, price, dp, signal, confidence, risk, stress, r, mom, vol, reasons)
