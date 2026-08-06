"""
mu_data_fetch.py
=================
Fetches REAL market data from Yahoo Finance (yfinance) and builds a
MUSignal with genuine, computed numbers — no invented values anywhere.

Run locally (this sandbox cannot reach finance.yahoo.com):

    pip install yfinance pandas --break-system-packages
    python3 mu_data_fetch.py

It fetches daily OHLCV, computes EMA20/EMA50/RSI14/ATR14, relative
volume vs 20-day avg volume, previous 5-day low, previous 20-day high,
then hands the result to RuleEngine + Explainer from mu_alert_system.py.
"""

import sys
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

from mu_alert_system import MUSignal, RuleEngine, Explainer


def compute_rsi(closes: pd.Series, period: int = 14) -> float:
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])


def compute_atr(df: pd.DataFrame, period: int = 14) -> float:
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


def fetch_mu_signal(symbol: str = "MU") -> MUSignal:
    df = yf.download(symbol, period="4mo", interval="1d", progress=False, auto_adjust=True)
    if df.empty or len(df) < 25:
        raise RuntimeError(f"Insufficient data returned for {symbol} — cannot build a genuine signal.")

    df = df.dropna()
    close = df["Close"]

    last_price = float(close.iloc[-1])
    ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
    ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
    rsi14 = compute_rsi(close, 14)
    atr14 = compute_atr(df, 14)

    avg_vol_20 = float(df["Volume"].iloc[-21:-1].mean())
    last_vol = float(df["Volume"].iloc[-1])
    relative_volume = round(last_vol / avg_vol_20, 3) if avg_vol_20 else 0.0

    previous_5_day_low = float(df["Low"].iloc[-6:-1].min())
    previous_20_day_high = float(df["High"].iloc[-21:-1].max())

    # A daily close is "confirmed" only once the session has closed.
    # yfinance daily bars only contain fully closed sessions except possibly
    # the most recent partial day; treat the last row as confirmed only if
    # it is not today's still-open session (UTC date check, conservative).
    last_bar_date = df.index[-1].date()
    today_utc = datetime.now(timezone.utc).date()
    daily_close_confirmed = last_bar_date < today_utc

    return MUSignal(
        symbol=symbol,
        timestamp=datetime.now(timezone.utc).isoformat(),
        last_price=round(last_price, 2),
        daily_close_confirmed=daily_close_confirmed,
        ema20=round(ema20, 2),
        ema50=round(ema50, 2),
        atr14=round(atr14, 2),
        rsi14=round(rsi14, 2),
        relative_volume=relative_volume,
        previous_5_day_low=round(previous_5_day_low, 2),
        previous_20_day_high=round(previous_20_day_high, 2),
        rule_result=None,  # computed by RuleEngine
    )


def run(symbol: str = "MU"):
    signal = fetch_mu_signal(symbol)
    signal.rule_result = RuleEngine.evaluate(signal)
    result = Explainer.explain(signal)
    return signal, result


if __name__ == "__main__":
    import json

    sym = sys.argv[1] if len(sys.argv) > 1 else "MU"
    try:
        signal, result = run(sym)
        print("=== Fetched signal (real data) ===")
        print(json.dumps(signal.__dict__, indent=2))
        print("\n=== Explanation ===")
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"FAILED to build a genuine signal: {e}", file=sys.stderr)
        sys.exit(1)
