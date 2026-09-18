from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable
import math

Bar = dict[str, Any]


def clean_rows(rows: Iterable[Bar], *, drop_forming: bool = True) -> list[Bar]:
    by_time: dict[int, Bar] = {}
    for raw in rows or []:
        try:
            t = int(raw.get("time") or 0)
        except (TypeError, ValueError):
            continue
        if not t:
            continue
        by_time[t] = {
            "time": t,
            "open": float(raw.get("open") or 0),
            "high": float(raw.get("high") or 0),
            "low": float(raw.get("low") or 0),
            "close": float(raw.get("close") or 0),
            "volume": int(raw.get("volume") or 0),
        }
    out = [by_time[key] for key in sorted(by_time)]
    return out[:-1] if drop_forming and len(out) > 1 else out


@dataclass(frozen=True)
class Series:
    rows: list[Bar]

    @classmethod
    def from_rows(cls, rows: Iterable[Bar]) -> "Series":
        return cls(clean_rows(rows))

    def bar(self, shift: int = 1) -> Bar:
        if shift < 1 or shift > len(self.rows):
            raise IndexError(f"bar shift {shift} unavailable; have {len(self.rows)} completed candles")
        return self.rows[-shift]

    def has(self, count: int) -> bool:
        return len(self.rows) >= count

    def high(self, shift: int = 1) -> float:
        return float(self.bar(shift)["high"])

    def low(self, shift: int = 1) -> float:
        return float(self.bar(shift)["low"])

    def open(self, shift: int = 1) -> float:
        return float(self.bar(shift)["open"])

    def close(self, shift: int = 1) -> float:
        return float(self.bar(shift)["close"])

    def body(self, shift: int = 1) -> float:
        return abs(self.close(shift) - self.open(shift))

    def bullish(self, shift: int = 1) -> bool:
        return self.close(shift) > self.open(shift)

    def bearish(self, shift: int = 1) -> bool:
        return self.close(shift) < self.open(shift)

    def highest(self, start_shift: int, count: int) -> float:
        return max(self.high(start_shift + i) for i in range(count))

    def lowest(self, start_shift: int, count: int) -> float:
        return min(self.low(start_shift + i) for i in range(count))

    def average_body(self, start_shift: int, count: int) -> float:
        vals = [self.body(start_shift + i) for i in range(count) if start_shift + i <= len(self.rows)]
        vals = [value for value in vals if value > 0]
        return sum(vals) / len(vals) if vals else 0.0


def true_range(current: Bar, previous: Bar | None) -> float:
    high, low = float(current["high"]), float(current["low"])
    if previous is None:
        return high - low
    pc = float(previous["close"])
    return max(high - low, abs(high - pc), abs(low - pc))


def atr(series: Series, period: int = 14, shift: int = 1) -> float:
    end = len(series.rows) - shift
    if end < 0:
        return 0.0
    trs: list[float] = []
    for i in range(0, end + 1):
        trs.append(true_range(series.rows[i], series.rows[i - 1] if i else None))
    if len(trs) < period:
        return sum(trs) / len(trs) if trs else 0.0
    value = sum(trs[:period]) / period
    for tr in trs[period:]:
        value = ((value * (period - 1)) + tr) / period
    return value


def strong_bull_close(s: Series, shift: int) -> bool:
    hi, lo, op, cl = s.high(shift), s.low(shift), s.open(shift), s.close(shift)
    rng = hi - lo
    return rng > 0 and cl > op and cl >= lo + rng * 0.60


def strong_bear_close(s: Series, shift: int) -> bool:
    hi, lo, op, cl = s.high(shift), s.low(shift), s.open(shift), s.close(shift)
    rng = hi - lo
    return rng > 0 and cl < op and cl <= lo + rng * 0.40


def touches(s: Series, shift: int, zone_low: float, zone_high: float) -> bool:
    return s.low(shift) <= zone_high and s.high(shift) >= zone_low


def bull_rejection(s: Series, shift: int, zone_low: float, zone_high: float, wick_ratio: float = 0.50) -> bool:
    if not touches(s, shift, zone_low, zone_high):
        return False
    hi, lo, op, cl = s.high(shift), s.low(shift), s.open(shift), s.close(shift)
    body = abs(cl - op)
    lower = min(op, cl) - lo
    upper = hi - max(op, cl)
    return cl > op and strong_bull_close(s, shift) and lower >= body * wick_ratio and lower >= upper


def bear_rejection(s: Series, shift: int, zone_low: float, zone_high: float, wick_ratio: float = 0.50) -> bool:
    if not touches(s, shift, zone_low, zone_high):
        return False
    hi, lo, op, cl = s.high(shift), s.low(shift), s.open(shift), s.close(shift)
    body = abs(cl - op)
    lower = min(op, cl) - lo
    upper = hi - max(op, cl)
    return cl < op and strong_bear_close(s, shift) and upper >= body * wick_ratio and upper >= lower


def momentum(s: Series, shift: int, bullish: bool, atr_frac: float, period: int = 14) -> bool:
    av = atr(s, period, shift)
    avg_body = s.average_body(shift + 1, 5)
    body = s.body(shift)
    direction = s.bullish(shift) if bullish else s.bearish(shift)
    return direction and body >= max(av * atr_frac, avg_body * 1.10)


def find_two_swing_highs(s: Series, lookback: int, wing: int) -> tuple[float, float] | None:
    found: list[float] = []
    upper = min(lookback, len(s.rows) - wing)
    for shift in range(2 + wing, upper + 1):
        center = s.high(shift)
        ok = True
        for k in range(1, wing + 1):
            if s.high(shift - k) >= center or s.high(shift + k) > center:
                ok = False
                break
        if ok:
            found.append(center)
            if len(found) == 2:
                return found[0], found[1]
    return None


def find_two_swing_lows(s: Series, lookback: int, wing: int) -> tuple[float, float] | None:
    found: list[float] = []
    upper = min(lookback, len(s.rows) - wing)
    for shift in range(2 + wing, upper + 1):
        center = s.low(shift)
        ok = True
        for k in range(1, wing + 1):
            if s.low(shift - k) <= center or s.low(shift + k) < center:
                ok = False
                break
        if ok:
            found.append(center)
            if len(found) == 2:
                return found[0], found[1]
    return None


def recent_swing_high(s: Series, lookback: int, wing: int) -> float:
    pair = find_two_swing_highs(s, lookback, wing)
    if pair:
        return pair[0]
    return s.highest(2, min(lookback, max(1, len(s.rows) - 2)))


def recent_swing_low(s: Series, lookback: int, wing: int) -> float:
    pair = find_two_swing_lows(s, lookback, wing)
    if pair:
        return pair[0]
    return s.lowest(2, min(lookback, max(1, len(s.rows) - 2)))


def trend_bias(s: Series, lookback: int, wing: int) -> str:
    highs = find_two_swing_highs(s, lookback, wing)
    lows = find_two_swing_lows(s, lookback, wing)
    if not highs or not lows:
        return "neutral"
    h1, h2 = highs
    l1, l2 = lows
    if h1 > h2 and l1 > l2:
        return "bullish"
    if h1 < h2 and l1 < l2:
        return "bearish"
    return "neutral"


def sweep(s: Series, bullish: bool, lookback: int, wing: int) -> tuple[bool, float]:
    ref = recent_swing_low(s, lookback, wing) if bullish else recent_swing_high(s, lookback, wing)
    for shift in range(1, min(4, len(s.rows)) + 1):
        if bullish and s.low(shift) < ref and s.close(shift) > ref:
            return True, s.low(shift)
        if not bullish and s.high(shift) > ref and s.close(shift) < ref:
            return True, s.high(shift)
    return False, 0.0


def displacement(s: Series, shift: int, bullish: bool, atr_mult: float, period: int = 14) -> bool:
    av = atr(s, period, shift)
    if av <= 0:
        return False
    direction = s.bullish(shift) if bullish else s.bearish(shift)
    return direction and s.body(shift) >= av * atr_mult


def premium_discount_bias(h4: Series, bid: float, lookback: int) -> int:
    count = min(lookback, max(1, len(h4.rows) - 2))
    high = h4.highest(2, count)
    low = h4.lowest(2, count)
    if high <= low:
        return 0
    mid = (high + low) * 0.5
    if bid <= mid:
        return 10
    if bid >= mid:
        return -10
    return 0


def build_bias(h4: Series, h1: Series, bid: float, lookback: int = 100, wing: int = 2) -> dict[str, Any]:
    h4_dir, h1_dir = trend_bias(h4, lookback, wing), trend_bias(h1, lookback, wing)
    trend = (20 if h4_dir == "bullish" else -20 if h4_dir == "bearish" else 0)
    trend += (20 if h1_dir == "bullish" else -20 if h1_dir == "bearish" else 0)
    bull_sweep, _ = sweep(h1, True, lookback, wing)
    bear_sweep, _ = sweep(h1, False, lookback, wing)
    sweep_score = (20 if bull_sweep else 0) + (-20 if bear_sweep else 0)
    pd = premium_discount_bias(h4, bid, lookback)
    total = trend + sweep_score + pd
    direction = "bullish" if total >= 30 else "bearish" if total <= -30 else "neutral"
    return {"direction": direction, "score": total, "trend_score": trend, "sweep_score": sweep_score, "pd_score": pd}
