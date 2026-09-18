from __future__ import annotations

from typing import Any
import math

from .catalog import NATIVE_PRESETS
from .common import (
    Series, atr, bear_rejection, build_bias, bull_rejection, displacement,
    momentum, recent_swing_high, recent_swing_low, find_two_swing_highs, find_two_swing_lows, strong_bear_close,
    strong_bull_close, sweep, touches,
)
from .models import NativeSignal


def _meta(key: str) -> dict[str, Any]:
    return next(value for value in NATIVE_PRESETS.values() if value["key"] == key)


def _signal(key: str, **updates: Any) -> NativeSignal:
    meta = _meta(key)
    row = NativeSignal(strategy_key=key, strategy_name=meta["name"], title=meta["title"])
    for name, value in updates.items():
        setattr(row, name, value)
    return row


def _series(data: dict[str, Any], tf: str) -> Series:
    value = data.get(tf)
    if not isinstance(value, Series):
        raise ValueError(f"{tf} candle series is required")
    return value


def _quote(data: dict[str, Any]) -> tuple[float, float, float, float]:
    q = data.get("quote") or {}
    return float(q.get("bid") or 0), float(q.get("ask") or 0), float(q.get("spread_points") or 0), float(q.get("point") or 0)


def _symbol_risk(symbol: str, default: float, disp: float, be_r: float, trail_r: float) -> tuple[float, float, float, float]:
    text = symbol.upper()
    if "VOLATILITY 25" in text or "V25" in text:
        return 0.60, 1.00, 1.00, 2.00
    if "VOLATILITY 75" in text or "V75" in text:
        return 0.50, 1.15, 0.95, 1.80
    if "VOLATILITY 100" in text or "V100" in text:
        return 0.35, 1.25, 0.80, 1.50
    return default, disp, be_r, trail_r


def _fvg(s: Series, bullish: bool) -> tuple[bool, float, float]:
    if not s.has(3):
        return False, 0.0, 0.0
    if bullish and s.low(1) > s.high(3):
        return True, s.high(3), s.low(1)
    if not bullish and s.high(1) < s.low(3):
        return True, s.high(1), s.low(3)
    return False, 0.0, 0.0


def _ob(s: Series, bullish: bool, disp_mult: float) -> tuple[bool, float, float]:
    if not displacement(s, 1, bullish, disp_mult):
        return False, 0.0, 0.0
    for shift in range(2, min(8, len(s.rows)) + 1):
        if bullish and s.bearish(shift):
            return True, min(s.open(shift), s.close(shift)), s.high(shift)
        if not bullish and s.bullish(shift):
            return True, s.low(shift), max(s.open(shift), s.close(shift))
    return False, 0.0, 0.0


def _through_shift(s: Series, shift: int) -> Series:
    end = len(s.rows) - shift + 1
    return Series(s.rows[:max(0, end)])


def _asof(s: Series, epoch: int) -> Series:
    return Series([row for row in s.rows if int(row["time"]) <= int(epoch)])


def _age_m5(entry: Series, source_time: int) -> int:
    if not entry.rows or not source_time:
        return 10**9
    return max(0, int((int(entry.bar(1)["time"]) - int(source_time)) / 300))


def _micro_level(s: Series, bullish: bool, lookback: int = 8) -> float:
    count = min(lookback, max(1, len(s.rows) - 2))
    return s.highest(2, count) if bullish else s.lowest(2, count)


def _base_rules(key: str, tf: str = "M5") -> dict[str, Any]:
    return {
        "source": _meta(key).get("source"),
        "native": True,
        "completed_candles_only": True,
        "entry_timeframe": tf,
        "ea_worker_used": False,
    }


def _finalize(sig: NativeSignal) -> NativeSignal:
    if sig.valid and sig.source_time:
        sig.signal_key = f"{sig.strategy_key}:{sig.context.get('account_login', 0)}:{sig.context.get('symbol', '')}:{sig.source_time}:{sig.decision}"
    return sig


def _obfvg_setup(data: dict[str, Any], key: str, setup_shift: int, *,
                 lookback_htf: int, lookback_ltf: int, wing: int,
                 risk: float, disp_mult: float, ob_mult: float) -> dict[str, Any] | None:
    m15, h4, h1 = _through_shift(_series(data, "M15"), setup_shift), _series(data, "H4"), _series(data, "H1")
    if not m15.has(max(32, wing * 2 + 8)):
        return None
    source_time = int(m15.bar(1)["time"])
    h4a, h1a = _asof(h4, source_time), _asof(h1, source_time)
    if not h4a.has(20) or not h1a.has(20):
        return None
    bid, _, spread, _ = _quote(data)
    bias = build_bias(h4a, h1a, bid, lookback_htf, wing)
    if bias["direction"] == "neutral" or spread > 250:
        return None
    bullish = bias["direction"] == "bullish"
    symbol = str(data.get("symbol") or "")
    risk_pct, runtime_disp, be_r, trail_r = _symbol_risk(symbol, risk, disp_mult, 1.0, 1.8)
    sweep_ok, sweep_extreme = sweep(m15, bullish, lookback_ltf, wing)
    disp_ok = displacement(m15, 1, bullish, runtime_disp)
    mom_ok = momentum(m15, 1, bullish, 0.30)
    fvg_ok, fvg_low, fvg_high = _fvg(m15, bullish)
    ob_ok, ob_low, ob_high = _ob(m15, bullish, min(runtime_disp, ob_mult))
    score = (25 if sweep_ok else 0) + (20 if disp_ok else 0) + (15 if mom_ok else 0) + (20 if fvg_ok else 0) + (20 if ob_ok else 0)
    if not (sweep_ok and disp_ok) or not (fvg_ok or ob_ok):
        return None
    if fvg_ok and ob_ok:
        zone_low, zone_high, zone_type, route = min(fvg_low, ob_low), max(fvg_high, ob_high), "HYBRID", "FVG + OB"
        score += 10
    elif fvg_ok:
        zone_low, zone_high, zone_type, route = fvg_low, fvg_high, "FVG", "FVG"
    else:
        zone_low, zone_high, zone_type, route = ob_low, ob_high, "OB", "OB"
    structure = _micro_level(m15, bullish, 8)
    return {
        "direction": "BUY" if bullish else "SELL",
        "bullish": bullish,
        "source_time": source_time,
        "zone_low": float(zone_low), "zone_high": float(zone_high),
        "zone_type": zone_type, "route": route,
        "sweep_extreme": float(sweep_extreme), "structure": float(structure),
        "setup_score": float(score), "bias": bias,
        "risk_percent": risk_pct, "break_even_r": be_r, "trail_start_r": trail_r,
    }


def _obfvg_entry(data: dict[str, Any], key: str, setup: dict[str, Any], *,
                 lookback_ltf: int, entry_score: float, body_atr: float,
                 max_chase_atr: float, max_stop_atr: float, stop_buffer: float,
                 rr: float) -> NativeSignal:
    m5 = _series(data, "M5")
    bid, ask, _, point = _quote(data)
    bullish = bool(setup["bullish"])
    zone_low, zone_high = float(setup["zone_low"]), float(setup["zone_high"])
    av = atr(m5, 14, 1)
    rules = _base_rules(key)
    rules.update({"zone_touch": False, "rejection": False, "micro_bos": False, "momentum": False})
    if av <= 0 or not m5.has(max(20, lookback_ltf + 4)):
        return _signal(key, stage="WAITING_DATA", reason="ATR or M5 history unavailable", rules=rules)
    touch = touches(m5, 1, zone_low, zone_high) or touches(m5, 2, zone_low, zone_high)
    reject = (bull_rejection(m5, 1, zone_low, zone_high) or bull_rejection(m5, 2, zone_low, zone_high)) if bullish else (bear_rejection(m5, 1, zone_low, zone_high) or bear_rejection(m5, 2, zone_low, zone_high))
    ref = _micro_level(m5, bullish, 8)
    bos = m5.close(1) > ref if bullish else m5.close(1) < ref
    mom = momentum(m5, 1, bullish, body_atr)
    score = (25 if touch else 0) + (25 if reject else 0) + (20 if bos else 0) + (15 if mom else 0)
    if setup["zone_type"] == "HYBRID":
        score += 10
    score += min(10.0, float(setup["setup_score"]) * 0.10)
    rules.update({"zone_touch": touch, "rejection": reject, "micro_bos": bos, "momentum": mom})
    context = {**setup, "symbol": data.get("symbol"), "account_login": data.get("account_login"), "management": {"partial_at_r": 1.0, "partial_close_percent": 50.0, "break_even_r": setup["break_even_r"], "trail_start_r": setup["trail_start_r"], "trail_atr_mult": 1.0}}
    if not touch:
        return _signal(key, stage="WAITING_RETEST", score=score, reason="No zone touch", rules=rules, context=context)
    if not reject:
        return _signal(key, stage="WAITING_REJECTION", score=score, reason="No rejection", rules=rules, context=context)
    if not bos:
        return _signal(key, stage="WAITING_BOS", score=score, reason="No micro BOS", rules=rules, context=context)
    if not mom:
        return _signal(key, stage="WAITING_MOMENTUM", score=score, reason="No momentum follow-through", rules=rules, context=context)
    if score < entry_score:
        return _signal(key, stage="WAITING_SCORE", score=score, reason="Entry score too low", rules=rules, context=context)
    price = ask if bullish else bid
    chase = max(0.0, price - zone_high) if bullish else max(0.0, zone_low - price)
    if chase > av * max_chase_atr:
        return _signal(key, stage="WAITING_RETEST", score=score, reason="Price is chasing away from the zone", rules=rules, context=context)
    if bullish:
        recent = recent_swing_low(m5, lookback_ltf, 1)
        sl = min(recent, float(setup["sweep_extreme"]), zone_low) - av * stop_buffer
        risk_dist = price - sl
        tp = price + risk_dist * rr
    else:
        recent = recent_swing_high(m5, lookback_ltf, 1)
        sl = max(recent, float(setup["sweep_extreme"]), zone_high) + av * stop_buffer
        risk_dist = sl - price
        tp = price - risk_dist * rr
    if risk_dist <= max(point * 2.0, 0.0):
        return _signal(key, stage="BLOCKED_RISK", score=score, reason="Risk distance too small", rules=rules, context=context)
    if risk_dist > av * max_stop_atr:
        return _signal(key, stage="BLOCKED_RISK", score=score, reason="Stop is wider than source limit", rules=rules, context=context)
    sig = _signal(key, decision="BUY" if bullish else "SELL", direction="BUY" if bullish else "SELL",
                  stage="READY", score=score, reason=f"{setup['route']} entry confirmed",
                  entry=price, sl=sl, tp=tp, risk_percent=float(setup["risk_percent"]),
                  source_time=int(m5.bar(1)["time"]), rules=rules, context=context)
    return _finalize(sig)


def evaluate_black(data: dict[str, Any], *, purple: bool = False) -> NativeSignal:
    key = "primordial_purple" if purple else "primordial_black"
    expiry = 10 if purple else 14
    params = dict(lookback_htf=100, lookback_ltf=28, wing=2,
                  risk=0.45 if purple else 0.50, disp_mult=1.20 if purple else 1.10,
                  ob_mult=1.05 if purple else 0.95)
    m15, m5 = _series(data, "M15"), _series(data, "M5")
    max_setup_shifts = min(8, max(1, math.ceil(expiry / 3) + 2))
    candidates = []
    for shift in range(1, max_setup_shifts + 1):
        setup = _obfvg_setup(data, key, shift, **params)
        if setup and _age_m5(m5, int(setup["source_time"])) <= expiry:
            candidates.append(setup)
    if not candidates:
        return _signal(key, stage="SCANNING", reason="No active liquidity + displacement confluence", rules=_base_rules(key))
    setup = max(candidates, key=lambda row: int(row["source_time"]))
    return _obfvg_entry(data, key, setup, lookback_ltf=28,
                        entry_score=76.0 if purple else 70.0, body_atr=0.40 if purple else 0.35,
                        max_chase_atr=0.70, max_stop_atr=4.0, stop_buffer=0.25, rr=2.50)


def _swing_shifts(s: Series, bullish_break: bool, lookback: int = 80, wing: int = 2) -> tuple[tuple[int, float], tuple[int, float]] | None:
    found: list[tuple[int, float]] = []
    upper = min(lookback, len(s.rows) - wing)
    for shift in range(2 + wing, upper + 1):
        center = s.high(shift) if bullish_break else s.low(shift)
        ok = True
        for k in range(1, wing + 1):
            if bullish_break:
                if s.high(shift - k) >= center or s.high(shift + k) > center:
                    ok = False; break
            else:
                if s.low(shift - k) <= center or s.low(shift + k) < center:
                    ok = False; break
        if ok:
            found.append((shift, center))
            if len(found) == 2:
                return found[0], found[1]
    return None


def _project_line(t1: int, p1: float, t2: int, p2: float, t: int) -> float:
    dt = t2 - t1
    return p2 if dt == 0 else p1 + (p2 - p1) / dt * (t - t1)


def _trendline_retest(data: dict[str, Any], bullish: bool) -> dict[str, Any] | None:
    m5, m15 = _series(data, "M5"), _series(data, "M15")
    swings = _swing_shifts(m15, bullish, 80, 2)
    if not swings or not m5.has(20):
        return None
    (newer_shift, newer), (older_shift, older) = swings
    if bullish and newer >= older:
        return None
    if not bullish and newer <= older:
        return None
    t1, p1 = int(m15.bar(older_shift)["time"]), older
    t2, p2 = int(m15.bar(newer_shift)["time"]), newer
    av = atr(m5, 14, 1)
    _, _, _, point = _quote(data)
    min_body = max(av * 0.35, point * 10.0)
    break_shift = -1
    for shift in range(2, min(8, len(m5.rows)) + 1):
        bar = m5.bar(shift)
        line = _project_line(t1, p1, t2, p2, int(bar["time"]))
        op, cl, hi, lo = m5.open(shift), m5.close(shift), m5.high(shift), m5.low(shift)
        body = abs(cl - op)
        if bullish:
            crossed = (op <= line and cl > line) or (lo <= line and cl > line)
            accepted = cl > line and cl >= (hi + lo) * 0.5
        else:
            crossed = (op >= line and cl < line) or (hi >= line and cl < line)
            accepted = cl < line and cl <= (hi + lo) * 0.5
        if crossed and accepted and body >= min_body:
            break_shift = shift
            break
    if break_shift < 0:
        return None
    zone_low, zone_high = m5.low(break_shift), m5.high(break_shift)
    cluster_end = break_shift
    for shift in range(break_shift - 1, 0, -1):
        if break_shift - shift >= 3:
            break
        bar = m5.bar(shift)
        line = _project_line(t1, p1, t2, p2, int(bar["time"]))
        op, cl = m5.open(shift), m5.close(shift)
        accepted = cl > line and cl >= op if bullish else cl < line and cl <= op
        if not accepted:
            break
        cluster_end = shift
        zone_low, zone_high = min(zone_low, m5.low(shift)), max(zone_high, m5.high(shift))
    buffer = max(av * 0.20, point * 15.0)
    low, high = zone_low - buffer, zone_high + buffer
    mid = (low + high) * 0.5
    for shift in range(cluster_end - 1, 0, -1):
        touched = touches(m5, shift, low, high)
        held = m5.close(shift) >= mid if bullish else m5.close(shift) <= mid
        response = (bull_rejection(m5, shift, low, high) or strong_bull_close(m5, shift)) if bullish else (bear_rejection(m5, shift, low, high) or strong_bear_close(m5, shift))
        if touched and held and response:
            return {"ok": True, "break_zone_low": low, "break_zone_high": high, "break_shift": break_shift, "retest_shift": shift, "retest_time": int(m5.bar(shift)["time"])}
    return None


def evaluate_blue(data: dict[str, Any]) -> NativeSignal:
    key, expiry = "primordial_blue", 14
    m5 = _series(data, "M5")
    candidates = []
    for shift in range(1, min(8, math.ceil(expiry / 3) + 3)):
        setup = _obfvg_setup(data, key, shift, lookback_htf=100, lookback_ltf=28, wing=2,
                             risk=0.50, disp_mult=1.10, ob_mult=0.95)
        if setup and _age_m5(m5, int(setup["source_time"])) <= expiry:
            candidates.append(setup)
    if not candidates:
        return _signal(key, stage="SCANNING", reason="No active liquidity + displacement confluence", rules=_base_rules(key))
    setup = max(candidates, key=lambda row: int(row["source_time"]))
    bullish = bool(setup["bullish"])
    tl = _trendline_retest(data, bullish)
    zone_low, zone_high = float(setup["zone_low"]), float(setup["zone_high"])
    touch = touches(m5, 1, zone_low, zone_high) or touches(m5, 2, zone_low, zone_high)
    rejection = (bull_rejection(m5, 1, zone_low, zone_high) or bull_rejection(m5, 2, zone_low, zone_high)) if bullish else (bear_rejection(m5, 1, zone_low, zone_high) or bear_rejection(m5, 2, zone_low, zone_high))
    ref = _micro_level(m5, bullish, 8)
    bos = m5.close(1) > ref if bullish else m5.close(1) < ref
    mom = momentum(m5, 1, bullish, 0.35)
    tl_touch = bool(tl and (touches(m5, 1, tl["break_zone_low"], tl["break_zone_high"]) or touches(m5, 2, tl["break_zone_low"], tl["break_zone_high"])))
    score = (20 if touch else 0) + (20 if rejection else 0) + (15 if bos else 0) + (10 if mom else 0) + (25 if tl else 0) + (10 if tl_touch else 0)
    if setup["zone_type"] == "HYBRID": score += 10
    score += min(10.0, float(setup["setup_score"]) * 0.10)
    rules = _base_rules(key)
    rules.update({"zone_touch": touch, "trendline_break_retest": bool(tl), "trendline_zone_touch": tl_touch, "rejection": rejection, "micro_bos": bos, "momentum": mom})
    context = {**setup, "trendline": tl, "symbol": data.get("symbol"), "account_login": data.get("account_login"), "management": {"partial_at_r": 1.0, "partial_close_percent": 50.0, "break_even_r": setup["break_even_r"], "trail_start_r": setup["trail_start_r"], "trail_atr_mult": 1.0}}
    for ok, stage, reason in [(touch, "WAITING_RETEST", "No zone touch"), (bool(tl), "WAITING_TRENDLINE_RETEST", "No trendline break/retest"), (rejection, "WAITING_REJECTION", "No rejection"), (bos, "WAITING_BOS", "No micro BOS"), (mom, "WAITING_MOMENTUM", "No momentum follow-through")]:
        if not ok:
            return _signal(key, stage=stage, score=score, reason=reason, rules=rules, context=context)
    if score < 70:
        return _signal(key, stage="WAITING_SCORE", score=score, reason="Entry score too low", rules=rules, context=context)
    bid, ask, _, point = _quote(data)
    av = atr(m5, 14, 1)
    chase_upper = max(zone_high, float(tl["break_zone_high"]))
    chase_lower = min(zone_low, float(tl["break_zone_low"]))
    price = ask if bullish else bid
    chase = max(0.0, price - chase_upper) if bullish else max(0.0, chase_lower - price)
    if chase > av * 0.70:
        return _signal(key, stage="WAITING_RETEST", score=score, reason="Chasing away from break/retest zone", rules=rules, context=context)
    if bullish:
        sl = min(recent_swing_low(m5, 28, 1), float(setup["sweep_extreme"]), zone_low) - av * 0.25
        risk_dist, tp = price - sl, None
        tp = price + risk_dist * 2.5
    else:
        sl = max(recent_swing_high(m5, 28, 1), float(setup["sweep_extreme"]), zone_high) + av * 0.25
        risk_dist = sl - price
        tp = price - risk_dist * 2.5
    if risk_dist <= max(point * 2.0, 0.0) or risk_dist > av * 4.0:
        return _signal(key, stage="BLOCKED_RISK", score=score, reason="Stop distance outside source limits", rules=rules, context=context)
    return _finalize(_signal(key, decision="BUY" if bullish else "SELL", direction="BUY" if bullish else "SELL", stage="READY", score=score, reason="Trendline break/retest + confluence entry confirmed", entry=price, sl=sl, tp=tp, risk_percent=float(setup["risk_percent"]), source_time=int(m5.bar(1)["time"]), rules=rules, context=context))



def _fib_bias(data: dict[str, Any], asof_time: int | None = None) -> dict[str, Any]:
    h4, h1 = _series(data, "H4"), _series(data, "H1")
    if asof_time:
        h4, h1 = _asof(h4, asof_time), _asof(h1, asof_time)
    bid, _, _, _ = _quote(data)
    lookback, wing = 120, 2
    count = min(max(30, lookback // 2), max(1, len(h1.rows) - 2))
    high, low = h1.highest(2, count), h1.lowest(2, count)
    mid = (high + low) * 0.5
    bull = bear = 0
    for series in (h1, h4):
        highs, lows = find_two_swing_highs(series, lookback, wing), find_two_swing_lows(series, lookback, wing)
        if highs:
            bull += 2 if highs[0] > highs[1] else 0
            bear += 2 if highs[0] < highs[1] else 0
        if lows:
            bull += 2 if lows[0] > lows[1] else 0
            bear += 2 if lows[0] < lows[1] else 0
    if bid <= mid: bull += 1
    if bid >= mid: bear += 1
    direction = "bullish" if bull >= bear + 2 else "bearish" if bear >= bull + 2 else "neutral"
    return {"direction": direction, "score": bull if direction == "bullish" else bear if direction == "bearish" else max(bull, bear), "bull": bull, "bear": bear, "range_high": high, "range_low": low, "midpoint": mid}


def _recent_swing_with_shift(s: Series, want_low: bool, lookback: int = 60, wing: int = 2) -> tuple[int, float] | None:
    upper = min(lookback, len(s.rows) - wing)
    for shift in range(2 + wing, upper + 1):
        center = s.low(shift) if want_low else s.high(shift)
        ok = True
        for k in range(1, wing + 1):
            if want_low and (s.low(shift - k) <= center or s.low(shift + k) < center): ok = False; break
            if not want_low and (s.high(shift - k) >= center or s.high(shift + k) > center): ok = False; break
        if ok: return shift, center
    return None
