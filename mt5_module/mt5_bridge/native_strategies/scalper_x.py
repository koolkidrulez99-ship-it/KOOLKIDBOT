from __future__ import annotations

from typing import Any

from .catalog import NATIVE_PRESETS
from .common import Series, atr
from .models import NativeSignal


def _meta() -> dict[str, Any]:
    return next(value for value in NATIVE_PRESETS.values() if value["key"] == "koolkid_scalper_x")


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    seed_count = min(period, len(values))
    value = sum(values[:seed_count]) / seed_count
    alpha = 2.0 / (period + 1.0)
    for close in values[seed_count:]:
        value = (close * alpha) + (value * (1.0 - alpha))
    return value


def _signal(**updates: Any) -> NativeSignal:
    meta = _meta()
    row = NativeSignal(
        strategy_key=meta["key"],
        strategy_name=meta["name"],
        title=meta["title"],
    )
    for name, value in updates.items():
        setattr(row, name, value)
    return row


def evaluate_scalper_x(data: dict[str, Any]) -> NativeSignal:
    """KOOLKID-native completed-candle momentum scalper.

    No external website, key, API, WebRequest, signal feed or third-party
    command channel is used by this strategy.
    """
    m5 = data.get("M5")
    h1 = data.get("H1")
    if not isinstance(m5, Series) or not isinstance(h1, Series):
        return _signal(stage="WAITING_DATA", reason="M5 and H1 candle history is required.")
    if not m5.has(40) or not h1.has(60):
        return _signal(stage="WAITING_DATA", reason="Completed M5/H1 candle history is still loading.")

    info = dict(data.get("symbol_info") or {})
    quote = dict(data.get("quote") or {})
    point = max(float(info.get("point") or quote.get("point") or 0), 1e-10)
    ask = float(quote.get("ask") or 0)
    bid = float(quote.get("bid") or 0)
    spread_points = float(
        quote.get("spread_points")
        or ((ask - bid) / point if ask > 0 and bid > 0 else 0)
    )

    h1_closes = [float(row["close"]) for row in h1.rows[-60:]]
    ema20 = _ema(h1_closes, 20)
    ema50 = _ema(h1_closes, 50)
    bias = "bullish" if ema20 > ema50 else "bearish" if ema20 < ema50 else "neutral"

    av = atr(m5, 14, 1)
    if av <= 0:
        return _signal(stage="WAITING_DATA", reason="M5 volatility data is not ready yet.")

    last = m5.bar(1)
    body = abs(float(last["close"]) - float(last["open"]))
    prior_high = m5.highest(2, 8)
    prior_low = m5.lowest(2, 8)
    bull_break = (
        float(last["close"]) > prior_high
        and float(last["close"]) > float(last["open"])
        and body >= av * 0.55
    )
    bear_break = (
        float(last["close"]) < prior_low
        and float(last["close"]) < float(last["open"])
        and body >= av * 0.55
    )

    atr_points = av / point
    max_spread = max(8.0, atr_points * 0.12)
    rules = {
        "native": True,
        "completed_candles_only": True,
        "external_signal_service": False,
        "webrequest": False,
        "execution_timeframe": "M5",
        "bias_timeframe": "H1",
        "h1_ema20": ema20,
        "h1_ema50": ema50,
        "bias": bias,
        "breakout_lookback": 8,
        "atr14": av,
        "spread_points": spread_points,
        "max_dynamic_spread_points": max_spread,
    }

    if spread_points > max_spread:
        return _signal(
            stage="BLOCKED_SPREAD",
            score=15,
            reason="Spread is too large relative to current M5 volatility.",
            rules=rules,
        )

    direction = None
    if bias == "bullish" and bull_break:
        direction = "BUY"
    elif bias == "bearish" and bear_break:
        direction = "SELL"

    if not direction:
        score = 30.0 if bias != "neutral" else 10.0
        if bull_break or bear_break:
            score += 25.0
        return _signal(
            stage="SCANNING",
            score=min(70.0, score),
            reason=f"H1 bias is {bias}; waiting for a matching completed M5 momentum breakout.",
            rules=rules,
            context={"bias": bias, "prior_high": prior_high, "prior_low": prior_low},
        )

    entry = ask if direction == "BUY" else bid
    if entry <= 0:
        entry = float(last["close"])

    candle_low = float(last["low"])
    candle_high = float(last["high"])
    buffer = av * 0.20
    if direction == "BUY":
        sl = min(candle_low - buffer, entry - av * 0.85)
    else:
        sl = max(candle_high + buffer, entry + av * 0.85)

    minimum = float(info.get("trade_stops_level") or 0) * point
    if minimum > 0:
        if direction == "BUY" and entry - sl < minimum:
            sl = entry - minimum - (2 * point)
        if direction == "SELL" and sl - entry < minimum:
            sl = entry + minimum + (2 * point)

    risk = abs(entry - sl)
    if risk <= point:
        return _signal(
            stage="BLOCKED_RISK",
            reason="Calculated stop distance is too small for this broker.",
            rules=rules,
        )

    target_rr = 1.6
    tp = entry + risk * target_rr if direction == "BUY" else entry - risk * target_rr
    source_time = int(last["time"])
    signal_key = (
        f"koolkid_scalper_x:{data.get('account_login', 0)}:"
        f"{data.get('symbol', '')}:{source_time}:{direction}"
    )

    return _signal(
        decision=direction,
        direction=direction,
        stage="READY",
        score=92.0,
        reason=f"H1 {bias} trend and completed M5 momentum breakout are aligned.",
        entry=entry,
        sl=sl,
        tp=tp,
        risk_percent=0.5,
        source_time=source_time,
        signal_key=signal_key,
        rules=rules,
        context={
            "symbol": data.get("symbol"),
            "account_login": data.get("account_login"),
            "bias": bias,
            "prior_high": prior_high,
            "prior_low": prior_low,
            "management": {
                "break_even_r": 0.8,
                "partial_at_r": 0.0,
                "partial_close_percent": 0.0,
                "trail_start_r": 1.2,
                "trail_distance_r": 0.5,
            },
        },
    )
