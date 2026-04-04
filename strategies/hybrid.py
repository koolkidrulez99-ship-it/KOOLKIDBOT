"""Hybrid preset trade planner for UNCHAIN.

This keeps the market-specific Hybrid button logic modular, similar to
Primordial Blue, so preset growth stays out of server.py.
"""

from __future__ import annotations

from typing import Dict, List

from strategies.preset_market_filters import analyze_clear_direction_with_barriers


HYBRID_MIN_STAKE = 0.35


HYBRID_MARKETS: Dict[str, Dict[str, object]] = {
    "R_10": {
        "market_label": "V10",
        "duration": 15,
        "duration_unit": "s",
        "legs": (
            {"side": "HIGHER", "barrier": "+0.09", "ratio": 0.50, "label": "HIGHER +0.09"},
            {"side": "LOWER", "barrier": "-0.09", "ratio": 0.50, "label": "LOWER -0.09"},
        ),
    },
    "R_25": {
        "market_label": "V25",
        "duration": 15,
        "duration_unit": "s",
        "legs": (
            {"side": "HIGHER", "barrier": "+0.15", "ratio": 0.50, "label": "HIGHER +0.15"},
            {"side": "LOWER", "barrier": "-0.15", "ratio": 0.50, "label": "LOWER -0.15"},
        ),
    },
    "R_75": {
        "market_label": "V75",
        "duration": 15,
        "duration_unit": "s",
        "legs": (
            {"side": "HIGHER", "barrier": "+3.88", "ratio": 0.50, "label": "HIGHER +3.88"},
            {"side": "LOWER", "barrier": "-3.88", "ratio": 0.50, "label": "LOWER -3.88"},
        ),
    },
    "R_100": {
        "market_label": "V100",
        "duration": 15,
        "duration_unit": "s",
        "legs": (
            {"side": "HIGHER", "barrier": "+0.10", "ratio": 0.50, "label": "HIGHER +0.10"},
            {"side": "LOWER", "barrier": "-0.10", "ratio": 0.50, "label": "LOWER -0.10"},
        ),
    },
    "1HZ75V": {
        "market_label": "V75 1s",
        "duration": 15,
        "duration_unit": "s",
        "legs": (
            {"side": "HIGHER", "barrier": "+0.50", "ratio": 0.50, "label": "HIGHER +0.50"},
            {"side": "LOWER", "barrier": "-0.50", "ratio": 0.50, "label": "LOWER -0.50"},
        ),
    },
    "1HZ100V": {
        "market_label": "V100 1s",
        "duration": 15,
        "duration_unit": "s",
        "legs": (
            {"side": "HIGHER", "barrier": "+0.20", "ratio": 0.50, "label": "HIGHER +0.20"},
            {"side": "LOWER", "barrier": "-0.20", "ratio": 0.50, "label": "LOWER -0.20"},
        ),
    },
    "1HZ25V": {
        "market_label": "V25 1s",
        "duration": 15,
        "duration_unit": "s",
        "legs": (
            {"side": "HIGHER", "barrier": "+40.2", "ratio": 0.50, "label": "HIGHER +40.2"},
            {"side": "LOWER", "barrier": "-40.2", "ratio": 0.50, "label": "LOWER -40.2"},
        ),
    },
}


def get_hybrid_market(symbol: str | None) -> Dict[str, object] | None:
    return HYBRID_MARKETS.get(str(symbol or "").strip().upper())


def split_hybrid_stakes(
    total_stake: float | int | str | None,
    ratios: List[float] | tuple[float, ...] | None = None,
) -> List[float]:
    try:
        total = max(0.0, float(total_stake or 0.0))
    except Exception:
        total = 0.0
    safe_ratios = [float(v or 0.0) for v in list(ratios or [0.5, 0.5])]
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


def build_hybrid_trade_plan(symbol: str | None, total_stake: float | int | str | None) -> Dict[str, object]:
    market = get_hybrid_market(symbol)
    if not market:
        return {
            "supported": False,
            "market_label": None,
            "reason": "Hybrid currently supports V10, V25, V75, V100, V75 1s, V100 1s, and V25 1s only.",
            "plan": [],
            "duration": 0,
            "duration_unit": "t",
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
            "reason": "Set the Higher stake first so Hybrid has a total cycle stake to split.",
            "plan": [],
            "duration": int(market.get("duration") or 10),
            "duration_unit": str(market.get("duration_unit") or "t"),
            "total_stake": 0.0,
        }

    leg_items = list(market.get("legs") or [])
    stakes = split_hybrid_stakes(safe_total, [float(item.get("ratio") or 0.0) for item in leg_items])
    plan = []
    for idx, leg in enumerate(leg_items):
        plan.append({
            "side": str(leg.get("side") or "HIGHER").upper(),
            "barrier": str(leg.get("barrier") or "+0.00"),
            "stake": stakes[idx] if idx < len(stakes) else 0.0,
            "ratio": float(leg.get("ratio") or 0.0),
            "label": str(leg.get("label") or ""),
            "duration": int(market.get("duration") or 10),
            "duration_unit": str(market.get("duration_unit") or "t"),
        })

    min_leg_stake = min((float(item.get("stake") or 0.0) for item in plan), default=0.0)
    if min_leg_stake < HYBRID_MIN_STAKE:
        market_label = str(market.get("market_label") or "V75")
        return {
            "supported": True,
            "market_label": market_label,
            "reason": (
                f"Hybrid skipped: total stake {_format_money_like(safe_total)} is too low for the "
                f"{market_label} split. Every leg must stay at or above {_format_money_like(HYBRID_MIN_STAKE)}."
            ),
            "plan": [],
            "duration": int(market.get("duration") or 10),
            "duration_unit": str(market.get("duration_unit") or "t"),
            "total_stake": round(safe_total, 2),
        }

    return {
        "supported": True,
        "market_label": str(market.get("market_label") or "V75"),
        "reason": f"{str(market.get('market_label') or 'V75')} preset ready.",
        "plan": plan,
        "duration": int(market.get("duration") or 10),
        "duration_unit": str(market.get("duration_unit") or "t"),
        "total_stake": round(safe_total, 2),
    }


def analyze_hybrid_market_state(
    prices: List[float] | tuple[float, ...] | None,
    plan_info: Dict[str, object] | None,
) -> Dict[str, object]:
    safe_info = dict(plan_info or {})
    plan = list(safe_info.get("plan") or [])
    barriers = [item.get("barrier") for item in plan if isinstance(item, dict)]
    market_label = str(safe_info.get("market_label") or "V75")
    return analyze_clear_direction_with_barriers(
        prices,
        barriers,
        strategy_name="Hybrid",
        market_label=market_label,
    )


def _format_money_like(value: float | int | str | None) -> str:
    try:
        amount = float(value or 0.0)
    except Exception:
        amount = 0.0
    return f"${amount:.2f}"
