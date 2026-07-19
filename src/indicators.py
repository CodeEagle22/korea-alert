"""Technical indicators — all return plain floats."""
import pandas as pd


def rsi(prices: pd.Series, period: int = 14) -> float:
    delta = prices.diff().dropna()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    loss_val = float(loss.iloc[-1])
    if loss_val == 0:
        return 100.0
    return float(100 - 100 / (1 + float(gain.iloc[-1]) / loss_val))


def momentum(prices: pd.Series, days: int = 5) -> float:
    """% change over last N days."""
    return float((prices.iloc[-1] / prices.iloc[-days - 1] - 1) * 100)


def volatility(prices: pd.Series, days: int = 10) -> float:
    """Annualised std of daily returns (last N days)."""
    returns = prices.pct_change().dropna().iloc[-days:]
    return float(returns.std() * (252 ** 0.5) * 100)


def daily_change(prices: pd.Series) -> float:
    return float((prices.iloc[-1] / prices.iloc[-2] - 1) * 100)


def drawdown(prices: pd.Series) -> float:
    """Max drawdown over the series (negative %)."""
    roll_max = prices.cummax()
    dd = (prices - roll_max) / roll_max
    return float(dd.min() * 100)
