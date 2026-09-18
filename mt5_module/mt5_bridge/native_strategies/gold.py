from __future__ import annotations

from typing import Any

from .common import Series, atr, find_two_swing_highs, find_two_swing_lows
from .models import NativeSignal
from .primordial import _age_m5, _finalize, _quote, _series, _signal


def _bias(h4: Series, h1: Series) -> dict[str, Any]:
    bull = bear = 0
    for series in (h1, h4):
        highs = find_two_swing_highs(series, 120, 2)
        lows = find_two_swing_lows(series, 120, 2)
        if highs and lows:
            if highs[0] > highs[1] and lows[0] > lows[1]:
                bull += 2
            if highs[0] < highs[1] and lows[0] < lows[1]:
                bear += 2
    count = min(40, max(1, len(h1.rows) - 1))
    high, low = h1.highest(1, count), h1.lowest(1, count)
    mid = (high + low) * 0.5
    close = h1.close(1)
    if close > mid:
        bull += 1
    if close < mid:
        bear += 1
    direction = "bullish" if bull >= bear + 2 else "bearish" if bear >= bull + 2 else "neutral"
    return {"direction": direction, "score": max(bull, bear) * 10, "bull": bull, "bear": bear, "midpoint": mid}

def _compression(m15: Series) -> dict[str, Any] | None:
    if not m15.has(18):
        return None
    av = atr(m15, 14, 1)
    if av <= 0:
        return None
    count = 12
    box_high = m15.highest(2, count)
    box_low = m15.lowest(2, count)
    avg_body = m15.average_body(2, count)
    compressed = (box_high - box_low) <= av * 2.20 and avg_body <= av * 0.42
    return {
        "compressed": compressed, "box_high": box_high, "box_low": box_low,
        "avg_body": avg_body, "atr": av,
    }


def _setup(data: dict[str, Any]) -> dict[str, Any] | None:
    h4, h1, m15 = _series(data, "H4"), _series(data, "H1"), _series(data, "M15")
    bias = _bias(h4, h1)
    comp = _compression(m15)
    if bias["direction"] == "neutral" or not comp or not comp["compressed"]:
        return None
    av = float(comp["atr"])
    high1, low1, close1, open1 = m15.high(1), m15.low(1), m15.close(1), m15.open(1)
    body1 = abs(close1 - open1)
    buffer = av * 0.10
    bull_sweep = low1 < comp["box_low"] - buffer and close1 > comp["box_low"]
    bear_sweep = high1 > comp["box_high"] + buffer and close1 < comp["box_high"]
    if bias["direction"] == "bullish" and bull_sweep:
        bullish = True
        zone_low = min(comp["box_low"], close1) - av * (0.18 * 0.35)
        zone_high = comp["box_low"] + av * 0.18
        sweep_extreme, reclaim, structure = low1, comp["box_low"], high1
        score = 60 + (10 if body1 >= av * 0.70 else 0)
        score += 10 if close1 > comp["box_low"] + (comp["box_high"] - comp["box_low"]) * 0.25 else 0
        note = "Downside sweep reclaimed"
    elif bias["direction"] == "bearish" and bear_sweep:
        bullish = False
        zone_low = comp["box_high"] - av * 0.18
        zone_high = max(comp["box_high"], close1) + av * (0.18 * 0.35)
        sweep_extreme, reclaim, structure = high1, comp["box_high"], low1
        score = 60 + (10 if body1 >= av * 0.70 else 0)
        score += 10 if close1 < comp["box_high"] - (comp["box_high"] - comp["box_low"]) * 0.25 else 0
        note = "Upside sweep rejected"
    else:
        return None
    return {
        "bullish": bullish, "source_time": int(m15.bar(1)["time"]), "bias": bias, "compression": comp,
        "zone_low": float(zone_low), "zone_high": float(zone_high), "sweep_extreme": float(sweep_extreme),
        "reclaim_level": float(reclaim), "structure_level": float(structure), "setup_score": float(score), "note": note,
    }

def evaluate_gold(data: dict[str, Any]) -> NativeSignal:
    key = "primordial_gold"
    rules = {
        "native": True, "source": "Primordial_Gold.mq5", "completed_candles_only": True,
        "entry_timeframe": "M5", "ea_worker_used": False,
    }
    setup = _setup(data)
    if not setup:
        return _signal(key, stage="SCANNING", reason="No active compression + sweep setup", rules=rules)
    m5 = _series(data, "M5")
    if _age_m5(m5, int(setup["source_time"])) > 16:
        return _signal(key, stage="SCANNING", reason="Compression sweep setup expired", rules=rules, context=setup)
    bid, ask, spread, point = _quote(data)
    if spread > 250:
        return _signal(key, stage="BLOCKED_SPREAD", reason="Spread exceeds source limit", rules=rules, context=setup)
    bullish = bool(setup["bullish"])
    low, high = float(setup["zone_low"]), float(setup["zone_high"])
    touched = m5.low(1) <= high and m5.high(1) >= low
    reclaim = m5.close(1) > setup["reclaim_level"] if bullish else m5.close(1) < setup["reclaim_level"]
    op, cl, hi, lo = m5.open(1), m5.close(1), m5.high(1), m5.low(1)
    body = abs(cl - op)
    rejection = (cl > op and (min(op, cl) - lo) > body * 0.8) if bullish else (cl < op and (hi - max(op, cl)) > body * 0.8)
    lookback = min(8, max(1, len(m5.rows) - 2))
    bos_level = m5.highest(2, lookback) if bullish else m5.lowest(2, lookback)
    bos = cl > bos_level if bullish else cl < bos_level
    av = atr(m5, 14, 1)
    momentum = (
        body >= av * 0.35
        and (cl > m5.high(2) if bullish else cl < m5.low(2))
    )
    score = float(setup["setup_score"])
    score += 15 if touched else -15
    score += 10 if reclaim else -10
    score += 15 if rejection else 0
    score += 15 if bos else 0
    score += 15 if momentum else 0
    rules.update({"zone_touch": touched, "reclaim": reclaim, "rejection": rejection, "micro_bos": bos, "momentum": momentum})
    context = {
        **setup, "symbol": data.get("symbol"), "account_login": data.get("account_login"),
        "management": {"partial_at_r": 1.0, "partial_close_percent": 50.0, "break_even_r": 1.0, "trail_start_r": 1.8, "trail_atr_mult": 1.0},
    }
    checks = [(reclaim, "WAITING_RECLAIM", "No reclaim"), (rejection, "WAITING_REJECTION", "No rejection"),
              (bos, "WAITING_BOS", "No BOS"), (momentum, "WAITING_MOMENTUM", "No momentum")]
    for ok, stage, reason in checks:
        if not ok:
            return _signal(key, stage=stage, score=score, reason=reason, rules=rules, context=context)
    if score < 70.0:
        return _signal(key, stage="WAITING_SCORE", score=score, reason="Entry score below source threshold", rules=rules, context=context)
    price = ask if bullish else bid
    chase = max(0.0, price - high) if bullish else max(0.0, low - price)
    if av <= 0 or chase > av * 0.75:
        return _signal(key, stage="WAITING_RETEST", score=score, reason="Chasing away from zone", rules=rules, context=context)
    sl = min(setup["sweep_extreme"], low) - av * 0.25 if bullish else max(setup["sweep_extreme"], high) + av * 0.25
    risk = price - sl if bullish else sl - price
    if risk <= max(point * 2.0, 0.0) or risk > av * 4.0:
        return _signal(key, stage="BLOCKED_RISK", score=score, reason="Stop distance outside source limits", rules=rules, context=context)
    tp = price + risk * 2.5 if bullish else price - risk * 2.5
    return _finalize(_signal(
        key, decision="BUY" if bullish else "SELL", direction="BUY" if bullish else "SELL",
        stage="READY", score=score, reason="Compression sweep entry", entry=price, sl=sl, tp=tp,
        risk_percent=0.50, source_time=int(m5.bar(1)["time"]), rules=rules, context=context,
    ))
