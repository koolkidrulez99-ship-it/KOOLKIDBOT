"""Shared recent-tick filters for preset auto trade modes."""

from __future__ import annotations

import math
import statistics
from typing import Iterable, Sequence


def analyze_uptrend_with_barriers(
    prices: Sequence[float] | Iterable[float] | None,
    barriers: Sequence[object] | Iterable[object] | None,
    *,
    strategy_name: str,
    market_label: str,
) -> dict:
    context = _build_context(prices, barriers)
    if not context["ready"]:
        return _result(
            False,
            "SCANNING",
            f"{strategy_name} waiting: collecting ticks ({context['tick_count']}/12).",
            context,
        )

    short = context["short"]
    medium = context["medium"]
    long = context["long"]
    direction_floor = context["direction_floor"]
    flat_floor = context["flat_floor"]
    meaningful_floor = context["meaningful_floor"]

    if long["range"] < flat_floor or abs(long["net"]) < direction_floor * 0.45:
        return _result(
            False,
            "FLAT",
            f"{strategy_name} waiting: market is too flat for the {market_label} preset barriers.",
            context,
        )

    if long["net"] <= -direction_floor * 0.35 or medium["net"] < -meaningful_floor:
        return _result(
            False,
            "DOWN",
            f"{strategy_name} waiting: market is drifting down, not in a solid upward move yet.",
            context,
        )

    clean_up = (
        long["net"] >= direction_floor
        and medium["net"] >= direction_floor * 0.55
        and short["net"] >= -meaningful_floor * 0.5
        and long["up_ratio"] >= 0.58
        and medium["up_ratio"] >= 0.60
        and long["range"] >= flat_floor
    )
    if clean_up:
        return _result(
            True,
            "UPTREND",
            f"{strategy_name} ready: solid upward movement confirmed for the {market_label} preset.",
            context,
        )

    return _result(
        False,
        "BUILDING",
        f"{strategy_name} waiting: the up move is not clean enough yet for the {market_label} preset.",
        context,
    )


def analyze_clear_direction_with_barriers(
    prices: Sequence[float] | Iterable[float] | None,
    barriers: Sequence[object] | Iterable[object] | None,
    *,
    strategy_name: str,
    market_label: str,
) -> dict:
    context = _build_context(prices, barriers)
    if not context["ready"]:
        return _result(
            False,
            "SCANNING",
            f"{strategy_name} waiting: collecting ticks ({context['tick_count']}/12).",
            context,
        )

    short = context["short"]
    medium = context["medium"]
    long = context["long"]
    direction_floor = context["direction_floor"]
    flat_floor = context["flat_floor"]

    if long["range"] < flat_floor:
        return _result(
            False,
            "FLAT",
            f"{strategy_name} waiting: market is too flat for the {market_label} preset barriers.",
            context,
        )

    clear_up = (
        long["net"] >= direction_floor
        and medium["net"] >= direction_floor * 0.45
        and long["up_ratio"] >= 0.56
        and medium["up_ratio"] >= 0.56
        and short["net"] >= -context["meaningful_floor"]
    )
    if clear_up:
        return _result(
            True,
            "UP",
            f"{strategy_name} ready: clear upward movement is away from the middle zone for {market_label}.",
            context,
        )

    clear_down = (
        long["net"] <= -direction_floor
        and medium["net"] <= -direction_floor * 0.45
        and long["down_ratio"] >= 0.56
        and medium["down_ratio"] >= 0.56
        and short["net"] <= context["meaningful_floor"]
    )
    if clear_down:
        return _result(
            True,
            "DOWN",
            f"{strategy_name} ready: clear downward movement is away from the middle zone for {market_label}.",
            context,
        )

    if abs(long["net"]) < direction_floor or abs(medium["net"]) < direction_floor * 0.45:
        return _result(
            False,
            "MIDDLE",
            f"{strategy_name} waiting: market is stuck in the middle zone for the {market_label} preset.",
            context,
        )

    return _result(
        False,
        "MIXED",
        f"{strategy_name} waiting: direction is too mixed to escape the middle zone cleanly.",
        context,
    )


def _build_context(
    prices: Sequence[float] | Iterable[float] | None,
    barriers: Sequence[object] | Iterable[object] | None,
) -> dict:
    cleaned_prices = _clean_prices(prices)
    tick_count = max(0, len(cleaned_prices) - 1)
    if len(cleaned_prices) < 12:
        return {
            "ready": False,
            "tick_count": tick_count,
            "prices": cleaned_prices,
            "barrier_scale": _derive_barrier_scale(barriers),
            "meaningful_floor": 0.0,
            "direction_floor": 0.0,
            "flat_floor": 0.0,
            "short": _empty_window(),
            "medium": _empty_window(),
            "long": _empty_window(),
        }

    deltas = [cleaned_prices[idx] - cleaned_prices[idx - 1] for idx in range(1, len(cleaned_prices))]
    abs_deltas = [abs(delta) for delta in deltas]
    avg_abs_move = statistics.fmean(abs_deltas) if abs_deltas else 0.0
    barrier_scale = _derive_barrier_scale(barriers)
    meaningful_floor = max(avg_abs_move * 0.45, barrier_scale * 0.015, 0.00001)
    direction_floor = max(barrier_scale * 0.08, avg_abs_move * 2.0, meaningful_floor * 3.0)
    flat_floor = max(barrier_scale * 0.10, avg_abs_move * 3.0, meaningful_floor * 5.0)

    return {
        "ready": True,
        "tick_count": tick_count,
        "prices": cleaned_prices,
        "barrier_scale": barrier_scale,
        "meaningful_floor": meaningful_floor,
        "direction_floor": direction_floor,
        "flat_floor": flat_floor,
        "short": _window_snapshot(cleaned_prices, 5, meaningful_floor),
        "medium": _window_snapshot(cleaned_prices, 10, meaningful_floor),
        "long": _window_snapshot(cleaned_prices, 20, meaningful_floor),
    }


def _window_snapshot(prices: Sequence[float], tick_window: int, meaningful_floor: float) -> dict:
    sample_size = min(len(prices), max(2, int(tick_window) + 1))
    window = list(prices[-sample_size:])
    deltas = [window[idx] - window[idx - 1] for idx in range(1, len(window))]
    meaningful = [delta for delta in deltas if abs(delta) >= meaningful_floor]
    meaningful_count = len(meaningful)
    up_count = sum(1 for delta in meaningful if delta > 0.0)
    down_count = sum(1 for delta in meaningful if delta < 0.0)
    base_count = meaningful_count or 1
    return {
        "tick_count": len(deltas),
        "net": float(window[-1] - window[0]) if len(window) >= 2 else 0.0,
        "range": float(max(window) - min(window)) if window else 0.0,
        "meaningful_count": meaningful_count,
        "up_count": up_count,
        "down_count": down_count,
        "up_ratio": float(up_count / base_count),
        "down_ratio": float(down_count / base_count),
    }


def _derive_barrier_scale(barriers: Sequence[object] | Iterable[object] | None) -> float:
    values = []
    for raw in list(barriers or []):
        try:
            number = float(str(raw or "").replace(",", "."))
        except Exception:
            continue
        if math.isfinite(number):
            values.append(abs(number))
    return max(values) if values else 0.0


def _clean_prices(prices: Sequence[float] | Iterable[float] | None) -> list[float]:
    cleaned = []
    for raw in list(prices or []):
        try:
            number = float(raw)
        except Exception:
            continue
        if math.isfinite(number):
            cleaned.append(number)
    return cleaned


def _empty_window() -> dict:
    return {
        "tick_count": 0,
        "net": 0.0,
        "range": 0.0,
        "meaningful_count": 0,
        "up_count": 0,
        "down_count": 0,
        "up_ratio": 0.0,
        "down_ratio": 0.0,
    }


def _result(ready: bool, label: str, reason: str, context: dict) -> dict:
    return {
        "ready": bool(ready),
        "label": str(label or "UNKNOWN"),
        "reason": str(reason or ""),
        "tick_count": int(context.get("tick_count") or 0),
        "barrier_scale": float(context.get("barrier_scale") or 0.0),
        "meaningful_floor": float(context.get("meaningful_floor") or 0.0),
        "direction_floor": float(context.get("direction_floor") or 0.0),
        "flat_floor": float(context.get("flat_floor") or 0.0),
        "short": dict(context.get("short") or _empty_window()),
        "medium": dict(context.get("medium") or _empty_window()),
        "long": dict(context.get("long") or _empty_window()),
    }
