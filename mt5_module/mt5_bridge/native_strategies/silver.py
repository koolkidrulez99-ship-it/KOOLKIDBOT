from __future__ import annotations

from typing import Any

from .common import Series, atr
from .models import NativeSignal
from .primordial import _finalize, _quote, _series, _signal


def _range(h1: Series) -> dict[str, float] | None:
    if not h1.has(24):
        return None
    high, low = h1.highest(1, 24), h1.lowest(1, 24)
    return {"high": high, "low": low, "mid": (high + low) * 0.5}


def _bias(h1: Series, rng: dict[str, float], point: float) -> int:
    if not h1.has(6):
        return 0
    last_close, prev_close = h1.close(1), h1.close(2)
    av = atr(h1, 14, 1) or point * 100.0
    bull = last_close > rng["mid"] and last_close > prev_close and h1.high(1) > h1.high(2)
    bear = last_close < rng["mid"] and last_close < prev_close and h1.low(1) < h1.low(2)
    if bull and not bear:
        return 1
    if bear and not bull:
        return -1
    if last_close > rng["high"] - 0.25 * av:
        return 1
    if last_close < rng["low"] + 0.25 * av:
        return -1
    return 0

def _setup(data: dict[str, Any]) -> dict[str, Any] | None:
    h1, m15 = _series(data, "H1"), _series(data, "M15")
    _, _, _, point = _quote(data)
    rng = _range(h1)
    if not rng or not m15.has(5):
        return None
    bias = _bias(h1, rng, point)
    av = atr(m15, 14, 1) or point * 120.0
    b0, b1, b2 = m15.bar(1), m15.bar(2), m15.bar(3)
    body_high = max(float(b0["open"]), float(b0["close"]))
    body_low = min(float(b0["open"]), float(b0["close"]))
    sweep_high = float(b1["high"]) > rng["high"] + av * 0.20
    sweep_low = float(b1["low"]) < rng["low"] - av * 0.20
    b1_body = abs(float(b1["close"]) - float(b1["open"]))
    bear_reject = float(b1["close"]) < float(b1["open"]) and float(b1["high"]) - max(float(b1["open"]), float(b1["close"])) > b1_body
    bull_reject = float(b1["close"]) > float(b1["open"]) and min(float(b1["open"]), float(b1["close"])) - float(b1["low"]) > b1_body
    b0_body = abs(float(b0["close"]) - float(b0["open"]))
    break_down = float(b0["close"]) < float(b1["low"]) and b0_body >= av * 0.35
    break_up = float(b0["close"]) > float(b1["high"]) and b0_body >= av * 0.35
    midpoint_sell = float(b0["close"]) < rng["mid"]
    midpoint_buy = float(b0["close"]) > rng["mid"]
    if bias <= 0 and sweep_high and bear_reject and break_down and midpoint_sell:
        return {
            "bullish": False, "route": "BREAK-RETEST SELL",
            "zone_high": body_high, "zone_low": body_low,
            "stop_ref": max(float(b1["high"]), float(b2["high"]), float(b0["high"])),
            "entry_ref": (body_high + body_low) * 0.5, "source_time": int(b0["time"]),
            "range": rng, "bias": bias,
        }
    if bias >= 0 and sweep_low and bull_reject and break_up and midpoint_buy:
        return {
            "bullish": True, "route": "BREAK-RETEST BUY",
            "zone_high": body_high, "zone_low": body_low,
            "stop_ref": min(float(b1["low"]), float(b2["low"]), float(b0["low"])),
            "entry_ref": (body_high + body_low) * 0.5, "source_time": int(b0["time"]),
            "range": rng, "bias": bias,
        }
    return None


def _close_location(bar: dict[str, Any]) -> float:
    rng = float(bar["high"]) - float(bar["low"])
    return 0.5 if rng <= 0 else (float(bar["close"]) - float(bar["low"])) / rng


def _body(bar: dict[str, Any]) -> float:
    return abs(float(bar["close"]) - float(bar["open"]))

def _retest(bar: dict[str, Any], setup: dict[str, Any], tolerance: float) -> bool:
    low, high = float(setup["zone_low"]), float(setup["zone_high"])
    if float(bar["high"]) < low - tolerance or float(bar["low"]) > high + tolerance:
        return False
    mid = (low + high) * 0.5
    body = _body(bar)
    if setup["bullish"]:
        lower = min(float(bar["open"]), float(bar["close"])) - float(bar["low"])
        return lower >= body * 0.70 and float(bar["close"]) >= mid - tolerance and _close_location(bar) > 0.25
    upper = float(bar["high"]) - max(float(bar["open"]), float(bar["close"]))
    return upper >= body * 0.70 and float(bar["close"]) <= mid + tolerance and _close_location(bar) < 0.75


def _confirm(bar: dict[str, Any], setup: dict[str, Any], av: float) -> bool:
    if setup["bullish"]:
        return (
            float(bar["close"]) > float(bar["open"]) and _body(bar) >= av * 0.30
            and float(bar["close"]) >= float(setup["zone_high"]) and _close_location(bar) >= 0.65
        )
    return (
        float(bar["close"]) < float(bar["open"]) and _body(bar) >= av * 0.30
        and float(bar["close"]) <= float(setup["zone_low"]) and _close_location(bar) <= 0.35
    )

def evaluate_silver(data: dict[str, Any]) -> NativeSignal:
    key = "primordial_silver"
    rules = {
        "native": True, "source": "Primordial_Silver.mq5", "completed_candles_only": True,
        "entry_timeframe": "M5", "ea_worker_used": False,
    }
    setup = _setup(data)
    if not setup:
        return _signal(key, stage="SCANNING", reason="No H1 range sweep + M15 break setup", rules=rules)
    m5 = _series(data, "M5")
    bid, ask, _, point = _quote(data)
    if not m5.has(6):
        return _signal(key, stage="WAITING_DATA", reason="M5 history unavailable", rules=rules, context=setup)
    av = atr(m5, 14, 1) or point * 80.0
    tolerance = av * 0.15
    max_lookback = min(3, len(m5.rows) - 2)
    retest_shift = -1
    for idx in range(1, max_lookback + 1):
        shift = idx + 1
        if _retest(m5.bar(shift), setup, tolerance):
            retest_shift = shift
            break
    rules["retest"] = retest_shift > 0
    context = {
        **setup, "symbol": data.get("symbol"), "account_login": data.get("account_login"),
        "management": {"partial_at_r": 1.0, "partial_close_percent": 50.0, "break_even_r": 1.0, "trail_start_r": 1.0, "trail_atr_mult": 1.20},
    }
    if retest_shift < 0:
        return _signal(key, stage="WAITING_RETEST", reason="Waiting for break-zone retest", rules=rules, context=context)
    latest = m5.bar(1)
    confirm = _confirm(latest, setup, av)
    if setup["bullish"]:
        mss = float(latest["close"]) > m5.high(retest_shift) and float(latest["high"]) > m5.high(2)
        chase_ok = ask - float(setup["zone_high"]) <= av * 0.35 * 1.5
    else:
        mss = float(latest["close"]) < m5.low(retest_shift) and float(latest["low"]) < m5.low(2)
        chase_ok = float(setup["zone_low"]) - bid <= av * 0.35 * 1.5
    rules.update({"confirmation": confirm, "mss": mss, "chase_filter": chase_ok})
    if not confirm:
        return _signal(key, stage="WAITING_CONFIRM", reason="Waiting for strong confirmation candle", rules=rules, context=context)
    if not mss:
        return _signal(key, stage="WAITING_MSS", reason="Waiting for entry-timeframe MSS", rules=rules, context=context)
    if not chase_ok:
        return _signal(key, stage="BLOCKED_CHASE", reason="Price moved too far from retest zone", rules=rules, context=context)
    bullish = bool(setup["bullish"])
    price = ask if bullish else bid
    sampled = [m5.bar(shift) for shift in range(1, retest_shift + 1)]
    if bullish:
        sl = min(float(setup["stop_ref"]), min(float(row["low"]) for row in sampled)) - tolerance
        risk = price - sl
        tp = price + risk * 2.50
    else:
        sl = max(float(setup["stop_ref"]), max(float(row["high"]) for row in sampled)) + tolerance
        risk = sl - price
        tp = price - risk * 2.50
    if risk <= max(point * 2.0, 0.0) or risk > av * 2.8:
        return _signal(key, stage="BLOCKED_RISK", reason="Stop distance outside Silver source limits", rules=rules, context=context)
    score = 100.0 if confirm and mss and chase_ok else 0.0
    return _finalize(_signal(
        key, decision="BUY" if bullish else "SELL", direction="BUY" if bullish else "SELL",
        stage="READY", score=score, reason=str(setup["route"]), entry=price, sl=sl, tp=tp,
        risk_percent=0.50, source_time=int(latest["time"]), rules=rules, context=context,
    ))
