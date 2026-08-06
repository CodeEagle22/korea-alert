"""
MU Alert System
================
A deterministic, rule-based alert engine for MU (Micron) plus a strict
explanation generator. No prices/indicators/targets are ever invented —
everything printed is derived from the input JSON fields.

Two independent stages:
  1. RuleEngine   -> computes rule_result from raw numeric inputs (pure math,
                     no LLM, fully deterministic, unit-testable).
  2. Explainer    -> takes a signal (raw fields + rule_result) and produces
                     the fixed JSON explanation contract. Never contradicts
                     rule_result; never adds new numeric levels.

Run this file directly to see it work against the sample signal.
"""

from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any


# ---------------------------------------------------------------------------
# 1. Data model
# ---------------------------------------------------------------------------

@dataclass
class MUSignal:
    symbol: str
    timestamp: str
    last_price: float
    daily_close_confirmed: bool
    ema20: float
    ema50: float
    atr14: float
    rsi14: float
    relative_volume: float
    previous_5_day_low: float
    previous_20_day_high: float
    rule_result: Optional[str] = None  # filled in by RuleEngine if not supplied


# ---------------------------------------------------------------------------
# 2. Rule Engine (deterministic — no LLM, no external data)
# ---------------------------------------------------------------------------
#
# Thresholds are explicit and fixed. Adjust constants below to tune the
# strategy; do not embed magic numbers elsewhere in the codebase.

RSI_BULL = 50
RSI_BEAR = 40
REL_VOL_CONFIRM = 1.20


class RuleEngine:
    """Computes rule_result purely from numeric fields on MUSignal."""

    @staticmethod
    def evaluate(s: MUSignal) -> str:
        price = s.last_price

        long_confirmation = (
            s.daily_close_confirmed
            and price > s.ema20
            and s.ema20 > s.ema50
            and s.rsi14 > RSI_BULL
            and s.relative_volume >= REL_VOL_CONFIRM
            and price >= s.previous_20_day_high
        )
        if long_confirmation:
            return "LONG_CONFIRMATION"

        breakdown_risk = (
            s.daily_close_confirmed
            and price < s.ema50
            and price < s.previous_5_day_low
            and s.rsi14 < RSI_BEAR
        )
        if breakdown_risk:
            return "BREAKDOWN_RISK"

        reclaim_watch = (
            s.ema50 <= price <= s.ema20
            and RSI_BEAR <= s.rsi14 <= RSI_BULL + 5
            and not s.daily_close_confirmed
        )
        if reclaim_watch:
            return "RECLAIM_WATCH"

        return "NO_ACTION"


# ---------------------------------------------------------------------------
# 3. Explainer — strict, honest, no invented numbers
# ---------------------------------------------------------------------------

class Explainer:
    """Builds the fixed-shape explanation JSON. Never contradicts rule_result."""

    @staticmethod
    def explain(s: MUSignal) -> Dict[str, Any]:
        rr = s.rule_result

        if rr == "NO_ACTION":
            return {
                "alert_type": "NO_ACTION",
                "evidence": ["No rule condition met per rule_result field"],
                "invalidation": "N/A",
                "risk_note": Explainer._risk_note(s),
                "monitoring_levels": {
                    "key_support": [s.ema50, s.previous_5_day_low],
                    "key_resistance": [s.ema20, s.previous_20_day_high],
                    "entry_reference": None,
                    "stop_reference": None,
                },
            }

        if rr == "LONG_CONFIRMATION":
            return {
                "alert_type": "LONG_CONFIRMATION",
                "evidence": [
                    f"Confirmed daily close above EMA20 ({s.ema20})",
                    f"EMA20 ({s.ema20}) above EMA50 ({s.ema50}) — bullish trend structure",
                    f"RSI14 ({s.rsi14}) above {RSI_BULL} — bullish momentum",
                    f"Relative volume ({s.relative_volume}) at/above {REL_VOL_CONFIRM} — participation confirms move",
                    f"Price ({s.last_price}) at/above previous 20-day high ({s.previous_20_day_high})",
                ],
                "invalidation": (
                    f"A confirmed daily close back below EMA20 ({s.ema20}), "
                    f"or a break below the previous 5-day low ({s.previous_5_day_low}), "
                    "would invalidate the bullish confirmation."
                ),
                "risk_note": Explainer._risk_note(s),
                "monitoring_levels": {
                    "key_support": [s.ema20, s.previous_5_day_low],
                    "key_resistance": [s.previous_20_day_high],
                    "entry_reference": s.last_price,
                    "stop_reference": s.previous_5_day_low,
                },
            }

        if rr == "BREAKDOWN_RISK":
            return {
                "alert_type": "BREAKDOWN_RISK",
                "evidence": [
                    f"Confirmed daily close below EMA50 ({s.ema50})",
                    f"Price ({s.last_price}) below previous 5-day low ({s.previous_5_day_low})",
                    f"RSI14 ({s.rsi14}) below {RSI_BEAR} — bearish momentum, correction may continue",
                ],
                "invalidation": (
                    f"A confirmed daily close back above EMA50 ({s.ema50}) "
                    "would suggest a potential recovery and invalidate the breakdown risk view."
                ),
                "risk_note": Explainer._risk_note(s),
                "monitoring_levels": {
                    "key_support": [s.previous_5_day_low],
                    "key_resistance": [s.ema50, s.ema20],
                    "entry_reference": None,
                    "stop_reference": None,
                },
            }

        if rr == "RECLAIM_WATCH":
            return {
                "alert_type": "RECLAIM_WATCH",
                "evidence": [
                    f"Price ({s.last_price}) between EMA50 ({s.ema50}) and EMA20 ({s.ema20}) — watch only, no confirmed close",
                    f"RSI14 ({s.rsi14}) in neutral range — insufficient data for a clear directional view",
                ],
                "invalidation": (
                    f"Loss of EMA50 ({s.ema50}) on a confirmed close shifts risk bearish; "
                    f"confirmed close above EMA20 ({s.ema20}) shifts toward bullish confirmation."
                ),
                "risk_note": Explainer._risk_note(s),
                "monitoring_levels": {
                    "key_support": [s.ema50, s.previous_5_day_low],
                    "key_resistance": [s.ema20, s.previous_20_day_high],
                    "entry_reference": None,
                    "stop_reference": None,
                },
            }

        raise ValueError(f"Unknown rule_result: {rr}")

    @staticmethod
    def _risk_note(s: MUSignal) -> str:
        vol_flag = "elevated" if s.atr14 / s.last_price > 0.06 else "normal"
        return (
            f"Volatility: ATR14 of {s.atr14} implies {vol_flag} daily range "
            f"relative to price ({s.last_price}). Semiconductor sector carries "
            "cyclical and macro/export-policy risk. No earnings-date field "
            "provided — earnings proximity risk cannot be assessed from this data."
        )


# ---------------------------------------------------------------------------
# 4. Orchestration helper
# ---------------------------------------------------------------------------

def process_signal(raw: Dict[str, Any]) -> Dict[str, Any]:
    """raw -> MUSignal -> (rule_result filled if missing) -> explanation JSON."""
    s = MUSignal(**{k: raw[k] for k in MUSignal.__dataclass_fields__ if k in raw})
    if not s.rule_result:
        s.rule_result = RuleEngine.evaluate(s)
    else:
        # Trust-but-verify: recompute and flag mismatch instead of silently
        # overriding an externally supplied rule_result.
        computed = RuleEngine.evaluate(s)
        if computed != s.rule_result:
            raise ValueError(
                f"Supplied rule_result '{s.rule_result}' does not match "
                f"engine-computed '{computed}'. Refusing to explain a "
                "mismatched signal."
            )
    return Explainer.explain(s)


# ---------------------------------------------------------------------------
# 5. Demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    sample = {
        "symbol": "MU",
        "timestamp": "2026-08-06T10:18:00+02:00",
        "last_price": 893.19,
        "daily_close_confirmed": False,
        "ema20": 1043.0,
        "ema50": 862.0,
        "atr14": 93.0,
        "rsi14": 42,
        "relative_volume": 1.15,
        "previous_5_day_low": 820.0,
        "previous_20_day_high": 975.0,
        # rule_result intentionally omitted -> RuleEngine computes it below.
    }

    print(json.dumps(process_signal(sample), indent=2))
