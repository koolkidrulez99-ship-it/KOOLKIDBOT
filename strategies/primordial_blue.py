"""Primordial Blue preset trade planner for UNCHAIN.

This module keeps the market-specific preset logic out of server.py so the
button can grow into a richer strategy layer later without bloating the route
and socket handlers.
"""

from __future__ import annotations

from typing import Dict, List

from strategies.preset_market_filters import analyze_uptrend_with_barriers


PRIMORDIAL_BLUE_MIN_STAKE = 0.35


PRIMORDIAL_BLUE_MARKETS: Dict[str, Dict[str, object]] = {
    "R_10": {
        "market_label": "V10",
        "duration": 10,
        "duration_unit": "t",
        "legs": (
            {"side": "HIGHER", "barrier": "-0.14", "ratio": 5.0, "label": "HIGHER -0.14"},
            {"side": "LOWER", "barrier": "-0.14", "ratio": 1.0, "label": "LOWER -0.14"},
        ),
    },
    "R_25": {
        "market_label": "V25",
        "duration": 10,
        "duration_unit": "t",
        "legs": (
            {"side": "HIGHER", "barrier": "-0.20", "ratio": 5.0, "label": "HIGHER -0.20"},
            {"side": "LOWER", "barrier": "-0.20", "ratio": 1.0, "label": "LOWER -0.20"},
        ),
    },
    "R_75": {
        "market_label": "V75",
        "duration": 10,
        "duration_unit": "t",
        "legs": (
            {"side": "HIGHER", "barrier": "-8.80", "ratio": 5.0, "label": "HIGHER -8.80"},
            {"side": "LOWER", "barrier": "-8.80", "ratio": 1.0, "label": "LOWER -8.80"},
        ),
    },
    "R_100": {
        "market_label": "V100",
        "duration": 10,
        "duration_unit": "t",
        "legs": (
            {"side": "HIGHER", "barrier": "-0.21", "ratio": 5.0, "label": "HIGHER -0.21"},
            {"side": "LOWER", "barrier": "-0.21", "ratio": 1.0, "label": "LOWER -0.21"},
        ),
    },
    "1HZ75V": {
        "market_label": "V75 1s",
        "duration": 15,
        "duration_unit": "s",
        "legs": (
            {"side": "HIGHER", "barrier": "+0.17", "ratio": 0.40, "label": "HIGHER +0.17"},
            {"side": "HIGHER", "barrier": "-0.17", "ratio": 0.10, "label": "HIGHER -0.17"},
            {"side": "LOWER", "barrier": "-0.17", "ratio": 0.25, "label": "LOWER -0.17"},
            {"side": "LOWER", "barrier": "+0.17", "ratio": 0.25, "label": "LOWER +0.17"},
        ),
    },
    "1HZ100V": {
        "market_label": "V100 1s",
        "duration": 10,
        "duration_unit": "t",
        "legs": (
            {"side": "HIGHER", "barrier": "-0.35", "ratio": 5.0, "label": "HIGHER -0.35"},
            {"side": "LOWER", "barrier": "-0.35", "ratio": 1.0, "label": "LOWER -0.35"},
        ),
    },
}


def get_primordial_blue_market(symbol: str | None) -> Dict[str, object] | None:
    return PRIMORDIAL_BLUE_MARKETS.get(str(symbol or "").strip().upper())


def split_primordial_blue_stakes(
    total_stake: float | int | str | None,
    ratios: List[float] | tuple[float, ...] | None = None,
) -> List[float]:
    """Return a stable ratio split that still sums to the total."""
    try:
        total = max(0.0, float(total_stake or 0.0))
    except Exception:
        total = 0.0
    safe_ratios = [float(v or 0.0) for v in list(ratios or [0.30, 0.30, 0.40])]
    if not safe_ratios:
        safe_ratios = [1.0]
    ratio_total = sum(max(0.0, value) for value in safe_ratios)
    if ratio_total <= 0.0:
        safe_ratios = [1.0]
        ratio_total = 1.0
    normalized = [max(0.0, value) / ratio_total for value in safe_ratios]
    stakes: List[float] = []
    running = 0.0
    for idx, ratio in enumerate(normalized):
        if idx == len(normalized) - 1:
            stake_value = round(max(0.0, total - running), 2)
        else:
            stake_value = round(total * ratio, 2)
            running += stake_value
        stakes.append(stake_value)
    return stakes


def build_primordial_blue_trade_plan(symbol: str | None, total_stake: float | int | str | None) -> Dict[str, object]:
    market = get_primordial_blue_market(symbol)
    if not market:
        return {
            "supported": False,
            "market_label": None,
            "reason": "Primordial Blue currently supports V10, V25, V75, V100, V75 1s, and V100 1s only.",
            "plan": [],
            "duration": 0,
            "duration_unit": "s",
            "total_stake": 0.0,
        }

    try:
        safe_total = max(0.0, float(total_stake or 0.0))
    except Exception:
        safe_total = 0.0
    if safe_total <= 0.0:
        return {
            "supported": True,
            "market_label": str(market.get("market_label") or "V75"),
            "reason": "Set the Higher stake first so Primordial Blue has a total cycle stake to split.",
            "plan": [],
            "duration": int(market.get("duration") or 5),
            "duration_unit": str(market.get("duration_unit") or "t"),
            "total_stake": 0.0,
        }

    leg_items = list(market.get("legs") or [])
    stakes = split_primordial_blue_stakes(
        safe_total,
        [float(item.get("ratio") or 0.0) for item in leg_items],
    )
    plan = []
    for idx, leg in enumerate(leg_items):
        plan.append({
            "side": str(leg.get("side") or "HIGHER").upper(),
            "barrier": str(leg.get("barrier") or "+0.00"),
            "stake": stakes[idx] if idx < len(stakes) else 0.0,
            "ratio": float(leg.get("ratio") or 0.0),
            "label": str(leg.get("label") or ""),
            "duration": int(market.get("duration") or 5),
            "duration_unit": str(market.get("duration_unit") or "t"),
        })

    min_leg_stake = min((float(item.get("stake") or 0.0) for item in plan), default=0.0)
    if min_leg_stake < PRIMORDIAL_BLUE_MIN_STAKE:
        market_label = str(market.get("market_label") or "V75")
        return {
            "supported": True,
            "market_label": market_label,
            "reason": (
                f"Primordial Blue skipped: total stake {_format_money_like(safe_total)} is too low for the "
                f"{market_label} split. Every leg must stay at or above {_format_money_like(PRIMORDIAL_BLUE_MIN_STAKE)}."
            ),
            "plan": [],
            "duration": int(market.get("duration") or 5),
            "duration_unit": str(market.get("duration_unit") or "t"),
            "total_stake": round(safe_total, 2),
        }

    return {
        "supported": True,
        "market_label": str(market.get("market_label") or "V75"),
        "reason": f"{str(market.get('market_label') or 'V75')} preset ready.",
        "plan": plan,
        "duration": int(market.get("duration") or 5),
        "duration_unit": str(market.get("duration_unit") or "t"),
        "total_stake": round(safe_total, 2),
    }


def analyze_primordial_blue_market_state(
    prices: List[float] | tuple[float, ...] | None,
    plan_info: Dict[str, object] | None,
) -> Dict[str, object]:
    safe_info = dict(plan_info or {})
    plan = list(safe_info.get("plan") or [])
    barriers = [item.get("barrier") for item in plan if isinstance(item, dict)]
    market_label = str(safe_info.get("market_label") or "V75")
    return analyze_uptrend_with_barriers(
        prices,
        barriers,
        strategy_name="Primordial Blue",
        market_label=market_label,
    )


def _format_money_like(value: float | int | str | None) -> str:
    try:
        amount = float(value or 0.0)
    except Exception:
        amount = 0.0
    return f"${amount:.2f}"
