from __future__ import annotations

from typing import Any

from .common import Series, atr, strong_bear_close, strong_bull_close
from .models import NativeSignal
from .primordial import (
    _age_m5, _fib_bias, _finalize, _quote, _recent_swing_with_shift,
    _series, _signal, _through_shift,
)


def _runtime(symbol: str, *, emerald: bool) -> dict[str, float]:
    risk, be_r, trail_r = 0.50, 1.00, 1.80
    min_score = 75.0 if emerald else 70.0
    text = symbol.upper()
    if "VOLATILITY 100" in text:
        risk, be_r, trail_r = min(risk, 0.35), 0.85, 1.50
        min_score = max(min_score, 74.0)
    elif "VOLATILITY 75" in text:
        risk, be_r, trail_r = min(risk, 0.50), 0.95, 1.70
        min_score = max(min_score, 72.0)
    elif "VOLATILITY 25" in text:
        risk, be_r, trail_r = min(risk, 0.60), 1.00, 1.90
        min_score = max(min_score, 68.0)
    return {"risk": risk, "be_r": be_r, "trail_r": trail_r, "min_score": min_score}

def _setup_from_series(data: dict[str, Any], m15: Series, *, bullish: bool) -> dict[str, Any] | None:
    if not m15.has(30):
        return None
    av = atr(m15, 14, 1)
    if av <= 0:
        return None
    swing = _recent_swing_with_shift(m15, want_low=bullish, lookback=60, wing=2)
    if not swing:
        return None
    swing_shift, swing_price = swing
    raid_shift = -1
    for shift in range(swing_shift - 1, 0, -1):
        if bullish and m15.low(shift) < swing_price and m15.close(shift) > swing_price:
            raid_shift = shift
            break
        if not bullish and m15.high(shift) > swing_price and m15.close(shift) < swing_price:
            raid_shift = shift
            break
    if raid_shift < 0:
        return None
    displacement_shift = -1
    for shift in range(raid_shift - 1, max(0, raid_shift - 3), -1):
        if shift < 1:
            break
        body_ok = m15.body(shift) >= av * 1.10
        direction_ok = m15.bullish(shift) if bullish else m15.bearish(shift)
        close_ok = strong_bull_close(m15, shift) if bullish else strong_bear_close(m15, shift)
        if direction_ok and body_ok and close_ok:
            displacement_shift = shift
            break
    if displacement_shift < 0:
        return None

    count = raid_shift - displacement_shift + 1
    if bullish:
        raid_low = min(m15.low(raid_shift), swing_price)
        raid_high = max(m15.open(raid_shift), m15.close(raid_shift))
        impulse_start = raid_low
        impulse_end = m15.highest(displacement_shift, count)
        if impulse_end <= impulse_start:
            return None
        fib = lambda ratio: impulse_end - (impulse_end - impulse_start) * ratio
        structure = m15.high(raid_shift)
    else:
        raid_high = max(m15.high(raid_shift), swing_price)
        raid_low = min(m15.open(raid_shift), m15.close(raid_shift))
        impulse_start = raid_high
        impulse_end = m15.lowest(displacement_shift, count)
        if impulse_start <= impulse_end:
            return None
        fib = lambda ratio: impulse_end + (impulse_start - impulse_end) * ratio
        structure = m15.low(raid_shift)
    fib50, fib618, fib705, fib786 = fib(0.500), fib(0.618), fib(0.705), fib(0.786)
    zone_low, zone_high = min(fib618, fib786), max(fib618, fib786)
    source_time = int(m15.bar(displacement_shift)["time"])
    bias = _fib_bias(data, source_time)
    score = 50
    score += 15 if m15.body(displacement_shift) >= av * 1.25 else 0
    if bullish and bias["direction"] == "bullish":
        score += 20
    if not bullish and bias["direction"] == "bearish":
        score += 20
    return {
        "bullish": bullish, "source_time": source_time,
        "raid_low": float(raid_low), "raid_high": float(raid_high),
        "raid_level": float(swing_price), "zone_low": float(zone_low), "zone_high": float(zone_high),
        "fib50": float(fib50), "fib618": float(fib618), "fib705": float(fib705), "fib786": float(fib786),
        "structure": float(structure), "setup_score": float(score), "bias": bias,
    }


def _find_setup(data: dict[str, Any], *, emerald: bool) -> dict[str, Any] | None:
    m15, m5 = _series(data, "M15"), _series(data, "M5")
    candidates: list[dict[str, Any]] = []
    for shift in range(1, 8):
        view = _through_shift(m15, shift)
        for bullish in (True, False):
            setup = _setup_from_series(data, view, bullish=bullish)
            if setup and _age_m5(m5, int(setup["source_time"])) <= 18:
                candidates.append(setup)
    if not candidates:
        return None
    candidates.sort(key=lambda row: (int(row["source_time"]), float(row["setup_score"])), reverse=True)
    return candidates[0]


def _recent_touch(m5: Series, low: float, high: float, bars: int) -> tuple[bool, int, float, float]:
    first = -1
    wick_low, wick_high = float("inf"), float("-inf")
    touched = False
    for shift in range(1, min(bars, len(m5.rows)) + 1):
        if m5.low(shift) <= high and m5.high(shift) >= low:
            touched = True
            if first < 0:
                first = shift
            wick_low = min(wick_low, m5.low(shift))
            wick_high = max(wick_high, m5.high(shift))
    return touched, first, wick_low, wick_high


def _wick_rejection(m5: Series, bullish: bool, low: float, high: float) -> bool:
    for shift in (1, 2):
        if shift > len(m5.rows):
            continue
        if m5.low(shift) > high or m5.high(shift) < low:
            continue
        op, cl = m5.open(shift), m5.close(shift)
        body = abs(cl - op)
        if bullish:
            lower = min(op, cl) - m5.low(shift)
            if cl > op and lower >= body * 0.60:
                return True
        else:
            upper = m5.high(shift) - max(op, cl)
            if cl < op and upper >= body * 0.60:
                return True
    return False


def evaluate_fib(data: dict[str, Any], *, emerald: bool) -> NativeSignal:
    key = "primordial_emerald" if emerald else "primordial_red"
    setup = _find_setup(data, emerald=emerald)
    rules = {
        "native": True, "source": "Primordial_Emerald.mq5" if emerald else "Primordial_Red.mq5",
        "completed_candles_only": True, "entry_timeframe": "M5", "ea_worker_used": False,
    }
    if not setup:
        return _signal(key, stage="SCANNING", reason="No active liquidity raid + Fibonacci pullback setup", rules=rules)

    m15, m5 = _series(data, "M15"), _series(data, "M5")
    bid, ask, spread, point = _quote(data)
    if spread > 250:
        return _signal(key, stage="BLOCKED_SPREAD", reason="Spread exceeds source limit", rules=rules, context=setup)
    bullish = bool(setup["bullish"])
    zone_low, zone_high = float(setup["zone_low"]), float(setup["zone_high"])
    touch, first_touch, wick_low, wick_high = _recent_touch(m5, zone_low, zone_high, 4 if not emerald else 3)
    sweet_low, sweet_high = min(setup["fib618"], setup["fib705"]), max(setup["fib618"], setup["fib705"])
    sweet_touch, _, _, _ = _recent_touch(m5, sweet_low, sweet_high, 3)
    fib50_reclaim = m5.close(1) > setup["fib50"] if bullish else m5.close(1) < setup["fib50"]
    rejection = _wick_rejection(m5, bullish, zone_low, zone_high)
    lookback = min(8, max(1, len(m5.rows) - 2))
    micro = m5.highest(2, lookback) if bullish else m5.lowest(2, lookback)
    bos = m5.close(1) > micro if bullish else m5.close(1) < micro
    av = atr(m5, 14, 1)
    momentum = (
        (m5.bullish(1) if bullish else m5.bearish(1))
        and (strong_bull_close(m5, 1) if bullish else strong_bear_close(m5, 1))
        and m5.body(1) >= av * (0.40 if emerald else 0.35)
    )
    runtime = _runtime(str(data.get("symbol") or ""), emerald=emerald)
    if emerald:
        score = (20 if touch else 0) + (20 if sweet_touch else 0) + (20 if rejection else 0)
        score += (20 if bos else 0) + (10 if momentum else 0) + (10 if fib50_reclaim else 0)
        score += min(10.0, float(setup["setup_score"]) * 0.10)
    else:
        score = (25 if touch else 0) + (25 if rejection else 0) + (25 if bos else 0) + (25 if momentum else 0)
        score += min(15.0, float(setup["setup_score"]) * 0.10)

    rules.update({
        "zone_touch": touch, "fresh_touch": first_touch in (1, 2), "fib_sweet_spot": sweet_touch,
        "fib50_reclaim": fib50_reclaim, "rejection": rejection, "micro_bos": bos, "momentum": momentum,
    })
    context = {
        **setup, "symbol": data.get("symbol"), "account_login": data.get("account_login"),
        "management": {"partial_at_r": 1.0, "partial_close_percent": 50.0,
                       "break_even_r": runtime["be_r"], "trail_start_r": runtime["trail_r"], "trail_atr_mult": 1.0},
    }
    checks = [(touch, "WAITING_RETEST", "No Fibonacci zone touch"),
              (first_touch in (1, 2), "WAITING_FRESH_TOUCH", "Fibonacci touch is no longer fresh")]
    if emerald:
        checks.append((sweet_touch, "WAITING_SWEET_SPOT", "61.8%-70.5% Fibonacci sweet spot not touched"))
    checks += [(rejection, "WAITING_REJECTION", "No rejection candle"),
               (bos, "WAITING_BOS", "No micro BOS"),
               (momentum, "WAITING_MOMENTUM", "No momentum confirmation")]
    for ok, stage, reason in checks:
        if not ok:
            return _signal(key, stage=stage, score=score, reason=reason, rules=rules, context=context)
    if score < runtime["min_score"]:
        return _signal(key, stage="WAITING_SCORE", score=score, reason="Entry score below source threshold", rules=rules, context=context)
    price = ask if bullish else bid
    chase = max(0.0, price - zone_high) if bullish else max(0.0, zone_low - price)
    if av <= 0 or chase > av * (0.65 if emerald else 0.70):
        return _signal(key, stage="WAITING_RETEST", score=score, reason="Price is chasing away from Fibonacci zone", rules=rules, context=context)
    if bullish:
        sl = min(zone_low, setup["raid_low"], setup["fib786"], wick_low) - av * 0.25
        risk = price - sl
        target_rr = price + risk * 2.60
        opposite = m15.highest(2, min(30, max(1, len(m15.rows) - 2)))
        tp = max(target_rr, opposite)
    else:
        sl = max(zone_high, setup["raid_high"], setup["fib786"], wick_high) + av * 0.25
        risk = sl - price
        target_rr = price - risk * 2.60
        opposite = m15.lowest(2, min(30, max(1, len(m15.rows) - 2)))
        tp = min(target_rr, opposite)
    if risk <= max(point * 2.0, 0.0) or risk > av * 4.0:
        return _signal(key, stage="BLOCKED_RISK", score=score, reason="Stop distance outside source limits", rules=rules, context=context)
    reason = "Fib + price action entry" if emerald else "Liquidity + Fib entry"
    return _finalize(_signal(key, decision="BUY" if bullish else "SELL", direction="BUY" if bullish else "SELL",
        stage="READY", score=score, reason=reason, entry=price, sl=sl, tp=tp,
        risk_percent=runtime["risk"], source_time=int(m5.bar(1)["time"]), rules=rules, context=context))


def evaluate_emerald(data: dict[str, Any]) -> NativeSignal:
    return evaluate_fib(data, emerald=True)


def evaluate_red(data: dict[str, Any]) -> NativeSignal:
    return evaluate_fib(data, emerald=False)
