import sys
sys.path.insert(0, "src")

import pandas as pd
import pytest
from indicators import rsi, momentum, volatility, daily_change, drawdown
from signals import analyze, _margin_stress
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def _prices(vals):
    return pd.Series(vals, dtype=float)


def test_rsi_overbought():
    # Rising prices → high RSI
    p = _prices([100 + i * 2 for i in range(20)])
    assert rsi(p) > 70


def test_rsi_oversold():
    p = _prices([100 - i * 2 for i in range(20)])
    assert rsi(p) < 30


def test_momentum():
    p = _prices([100, 100, 100, 100, 100, 110])
    assert abs(momentum(p) - 10.0) < 0.01


def test_daily_change():
    p = _prices([100, 95])
    assert abs(daily_change(p) - (-5.0)) < 0.01


def test_drawdown_flat():
    p = _prices([100] * 10)
    assert drawdown(p) == 0.0


def test_margin_stress_spike():
    score = _margin_stress(-4.0, 45.0, -20.0, -3.0)
    assert score >= 60


def test_margin_stress_calm():
    score = _margin_stress(0.5, 10.0, -2.0, 0.5)
    assert score == 0


def test_analyze_sell_signal():
    # Falling prices should produce SELL
    p = _prices([110 - i * 2 for i in range(20)])
    r = analyze("TEST", p)
    assert r.signal == "SELL"
    assert 0 <= r.confidence <= 100
    assert r.risk in ("LOW", "MEDIUM", "HIGH")
    assert 0 <= r.margin_stress <= 100


def test_analyze_buy_signal():
    p = _prices([80 + i * 2 for i in range(20)])
    r = analyze("TEST", p)
    assert r.signal == "BUY"
