from __future__ import annotations

from typing import Any

from .common import Series, atr, strong_bear_close, strong_bull_close
from .models import NativeSignal
from .primordial import _fib_bias, _finalize, _quote, _series, _signal


def _runtime(symbol: str) -> dict[str, float]:
    risk, be_r, trail_r, min_score = 0.50, 1.00, 1.80, 72.0
    text = symbol.upper()
    if "VOLATILITY 100" in text:
        risk, be_r, trail_r, min_score = min(risk, 0.35), 0.85, 1.50, max(min_score, 75.0)
    elif "VOLATILITY 75" in text:
        risk, be_r, trail_r, min_score = min(risk, 0.50), 0.95, 1.70, max(min_score, 72.0)
    elif "VOLATILITY 25" in text:
        risk, be_r, trail_r, min_score = min(risk, 0.60), 1.00, 1.90, max(min_score, 70.0)
    return {"risk": risk, "be_r": be_r, "trail_r": trail_r, "min_score": min_score}


def _opening_range(data: dict[str, Any]) -> dict[str, Any] | None:
    m15 = _series(data, "M15")
    if not m15.rows:
        return None
    latest = int(m15.bar(1)["time"])
    day_start = int(data.get("day_start") or (latest // 86400) * 86400)
    range_end = day_start + 4 * 3600
    bars = [row for row in m15.rows if day_start <= int(row["time"]) < range_end]
    if not bars:
        return None
    high = max(float(row["high"]) for row in bars)
    low = min(float(row["low"]) for row in bars)
    return {"day_start": day_start, "range_end": range_end, "ready": latest >= range_end,
            "high": high, "low": low, "midpoint": (high + low) * 0.5, "size": high - low}

def _setup(data: dict[str, Any], rng: dict[str, Any]) -> dict[str, Any] | None:
    if not rng.get("ready") or rng["high"] <= rng["low"]:
        return None
    m15, m5 = _series(data, "M15"), _series(data, "M5")
    bias = _fib_bias(data)
    av = atr(m15, 14, 1)
    if av <= 0:
        return None
    candidates: list[dict[str, Any]] = []
    for shift in range(1, min(60, len(m15.rows)) + 1):
        bar = m15.bar(shift)
        bt = int(bar["time"])
        if bt < int(rng["range_end"]):
            break
        age = max(0, int((int(m5.bar(1)["time"]) - bt) / 300))
        if age > 18:
            continue
        op, cl, hi, lo = map(float, (bar["open"], bar["close"], bar["high"], bar["low"]))
        body = abs(cl - op)
        if bias["direction"] in {"bullish", "neutral"} and lo < rng["low"] and cl > rng["low"]:
            score = 55 + (15 if body >= av * 1.05 else 0)
            score += 10 if cl > op and strong_bull_close(m15, shift) else 0
            score += 15 if bias["direction"] == "bullish" else 0
            score += 5 if cl > rng["midpoint"] else 0
            candidates.append({"bullish": True, "route": "BULL_SWEEP_RECLAIM", "source_time": bt,
                "zone_low": rng["low"] - av * 0.18, "zone_high": rng["low"] + av * 0.18,
                "raid_extreme": lo, "target2": max(rng["high"], rng["low"] + rng["size"]), "setup_score": score})
        if bias["direction"] in {"bearish", "neutral"} and hi > rng["high"] and cl < rng["high"]:
            score = 55 + (15 if body >= av * 1.05 else 0)
            score += 10 if cl < op and strong_bear_close(m15, shift) else 0
            score += 15 if bias["direction"] == "bearish" else 0
            score += 5 if cl < rng["midpoint"] else 0
            candidates.append({"bullish": False, "route": "BEAR_SWEEP_RECLAIM", "source_time": bt,
                "zone_low": rng["high"] - av * 0.18, "zone_high": rng["high"] + av * 0.18,
                "raid_extreme": hi, "target2": min(rng["low"], rng["high"] - rng["size"]), "setup_score": score})
        if bias["direction"] in {"bullish", "neutral"} and cl > rng["high"] and cl > op and strong_bull_close(m15, shift) and body >= av * 0.90:
            score = 52 + (15 if body >= av * 1.10 else 0)
            score += 15 if bias["direction"] == "bullish" else 0
            score += 8 if cl > rng["high"] + rng["size"] * 0.20 else 0
            candidates.append({"bullish": True, "route": "BULL_BREAKOUT_RETEST", "source_time": bt,
                "zone_low": rng["high"] - av * 0.18, "zone_high": rng["high"] + av * 0.18,
                "raid_extreme": hi, "target2": rng["high"] + rng["size"], "setup_score": score})
        if bias["direction"] in {"bearish", "neutral"} and cl < rng["low"] and cl < op and strong_bear_close(m15, shift) and body >= av * 0.90:
            score = 52 + (15 if body >= av * 1.10 else 0)
            score += 15 if bias["direction"] == "bearish" else 0
            score += 8 if cl < rng["low"] - rng["size"] * 0.20 else 0
            candidates.append({"bullish": False, "route": "BEAR_BREAKOUT_RETEST", "source_time": bt,
                "zone_low": rng["low"] - av * 0.18, "zone_high": rng["low"] + av * 0.18,
                "raid_extreme": lo, "target2": rng["low"] - rng["size"], "setup_score": score})
    if not candidates:
        return None
    candidates.sort(key=lambda row: (float(row["setup_score"]), int(row["source_time"])), reverse=True)
    return {**candidates[0], "range": rng, "bias": bias}


def _rejection(m5: Series, bullish: bool, low: float, high: float) -> bool:
    for shift in (1, 2):
        if shift > len(m5.rows) or m5.low(shift) > high or m5.high(shift) < low:
            continue
        op, cl = m5.open(shift), m5.close(shift)
        body = abs(cl - op)
        if bullish and cl > op and min(op, cl) - m5.low(shift) >= body * 0.60:
            return True
        if not bullish and cl < op and m5.high(shift) - max(op, cl) >= body * 0.60:
            return True
    return False

def evaluate_white(data: dict[str, Any]) -> NativeSignal:
    key = "primordial_white"
    rules = {"native": True, "source": "Primordial_White.mq5", "completed_candles_only": True,
             "entry_timeframe": "M5", "ea_worker_used": False}
    rng = _opening_range(data)
    if not rng:
        return _signal(key, stage="WAITING_RANGE", reason="Opening range data unavailable", rules=rules)
    if not rng["ready"]:
        return _signal(key, stage="BUILDING_RANGE", reason="First 4-hour opening range is still building", rules=rules, context={"range": rng})
    setup = _setup(data, rng)
    if not setup:
        return _signal(key, stage="SCANNING", reason="No opening-range sweep/reclaim or breakout/retest setup", rules=rules, context={"range": rng})
    m5 = _series(data, "M5")
    bid, ask, spread, point = _quote(data)
    if spread > 250:
        return _signal(key, stage="BLOCKED_SPREAD", reason="Spread exceeds source limit", rules=rules, context=setup)
    low, high = float(setup["zone_low"]), float(setup["zone_high"])
    touch_count, first_touch, wick_low, wick_high = 0, -1, float("inf"), float("-inf")
    touch_recent = False
    for shift in range(1, min(6, len(m5.rows)) + 1):
        if m5.low(shift) <= high and m5.high(shift) >= low:
            touch_count += 1
            if first_touch < 0:
                first_touch = shift
            wick_low, wick_high = min(wick_low, m5.low(shift)), max(wick_high, m5.high(shift))
            if shift <= 3:
                touch_recent = True
    bullish = bool(setup["bullish"])
    rejection = _rejection(m5, bullish, low, high)
    lookback = min(8, max(1, len(m5.rows) - 2))
    micro = m5.highest(2, lookback) if bullish else m5.lowest(2, lookback)
    bos = m5.close(1) > micro if bullish else m5.close(1) < micro
    av = atr(m5, 14, 1)
    momentum = ((m5.bullish(1) and strong_bull_close(m5, 1)) if bullish else (m5.bearish(1) and strong_bear_close(m5, 1)))
    momentum = momentum and m5.body(1) >= av * 0.35
    route = str(setup["route"])
    route_confirm = (
        m5.close(1) > rng["low"] if route == "BULL_SWEEP_RECLAIM" else
        m5.close(1) > rng["high"] if route == "BULL_BREAKOUT_RETEST" else
        m5.close(1) < rng["high"] if route == "BEAR_SWEEP_RECLAIM" else
        m5.close(1) < rng["low"]
    )
    score = (25 if touch_recent else 0) + (20 if rejection else 0) + (20 if bos else 0)
    score += (20 if momentum else 0) + (15 if route_confirm else 0) + min(15.0, float(setup["setup_score"]) * 0.10)
    runtime = _runtime(str(data.get("symbol") or ""))
    rules.update({"zone_touch": touch_recent, "first_retest_only": touch_count <= 2, "rejection": rejection,
                  "micro_bos": bos, "momentum": momentum, "route_confirm": route_confirm})
    context = {**setup, "symbol": data.get("symbol"), "account_login": data.get("account_login"),
               "management": {"partial_at_r": 1.0, "partial_close_percent": 50.0,
                              "break_even_r": runtime["be_r"], "trail_start_r": runtime["trail_r"], "trail_atr_mult": 1.0}}
    checks = [(touch_recent, "WAITING_RETEST", "No recent opening-range retest"),
              (touch_count <= 2, "WAITING_FIRST_RETEST", "First-retest-only source rule blocked this setup"),
              (rejection, "WAITING_REJECTION", "No rejection candle"), (bos, "WAITING_BOS", "No micro BOS"),
              (momentum, "WAITING_MOMENTUM", "No momentum confirmation"), (route_confirm, "WAITING_ROUTE_CONFIRM", "Opening-range route not reconfirmed")]
    for ok, stage, reason in checks:
        if not ok:
            return _signal(key, stage=stage, score=score, reason=reason, rules=rules, context=context)
    if score < runtime["min_score"]:
        return _signal(key, stage="WAITING_SCORE", score=score, reason="Entry score below source threshold", rules=rules, context=context)
    price = ask if bullish else bid
    chase = max(0.0, price - high) if bullish else max(0.0, low - price)
    if av <= 0 or chase > av * 0.70:
        return _signal(key, stage="WAITING_RETEST", score=score, reason="Price is chasing away from opening-range zone", rules=rules, context=context)
    if bullish:
        sl = min(low, setup["raid_extreme"], rng["low"]) - av * 0.25 if "SWEEP" in route else min(low, rng["high"], wick_low) - av * 0.25
        risk = price - sl
        tp = max(price + risk * 2.40, float(setup["target2"]))
    else:
        sl = max(high, setup["raid_extreme"], rng["high"]) + av * 0.25 if "SWEEP" in route else max(high, rng["low"], wick_high) + av * 0.25
        risk = sl - price
        tp = min(price - risk * 2.40, float(setup["target2"]))
    if risk <= max(point * 2.0, 0.0) or risk > av * 4.0:
        return _signal(key, stage="BLOCKED_RISK", score=score, reason="Stop distance outside source limits", rules=rules, context=context)
    return _finalize(_signal(key, decision="BUY" if bullish else "SELL", direction="BUY" if bullish else "SELL",
        stage="READY", score=score, reason="Opening range entry", entry=price, sl=sl, tp=tp,
        risk_percent=runtime["risk"], source_time=int(m5.bar(1)["time"]), rules=rules, context=context))
