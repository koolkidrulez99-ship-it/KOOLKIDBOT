# strategies/human.py
from collections import deque
from dataclasses import dataclass
from datetime import datetime
import time


@dataclass
class Candle:
    start_ts: int          # epoch seconds at candle start
    tf_sec: int
    open: float
    high: float
    low: float
    close: float

    def update(self, price: float):
        self.close = price
        if price > self.high:
            self.high = price
        if price < self.low:
            self.low = price


class HumanStrategy:
    """
    HUMAN (Multipliers) Strategy Engine with Order Block logic.

    IMPORTANT:
    Your server calls strategy.on_tick(tick, digit).
    This strategy needs real PRICE for candles/OB logic, so we read it from tick["quote"].
    """

    def __init__(self):
        self.reset()

    def reset(self):
        # Tick tracking
        self.tick_count = 0
        self.last_price = None
        self.last_ts = None

        # Candle building
        self.tf_1m = 60
        self.tf_5m = 300
        self.tf_1h = 3600

        self.cur_1m = None
        self.cur_5m = None
        self.cur_1h = None

        self.hist_1m = deque(maxlen=600)   # last 10 hours of 1m candles
        self.hist_5m = deque(maxlen=300)   # last ~25 hours of 5m candles
        self.hist_1h = deque(maxlen=48)    # last 48 hours of 1h candles

        # Range (previous 1H candle)
        self.range_high = None
        self.range_low = None
        self.range_start_ts = None
        self.range_size = None

        # Breakout / OB state
        self.breakout_bias = None
        self.breakout_ts = None
        self.breakout_price = None

        self.order_block = None   # dict with 'high', 'low', 'start_ts'

        self.retrace_happened = False
        self.retrace_ts = None
        self.retrace_price = None

        self.signal_fired = False
        self.last_signal_time = 0
        self.humanx_cooldown = 300  # 5 minutes between signals

        # Settings (safe defaults)
        self.auto_trade = False
        self.symbol = ""
        self.stake = 1.0
        self.multiplier = 50

        # HUMAN Rise/Fall Smart Assist (new)
        self.rf_prices = deque(maxlen=120)
        self.rf_signal = {
            "bias": "NEUTRAL",
            "signal": "WAIT",
            "trade_direction": None,
            "confidence": 0.0,
            "reason": "Collecting data",
            "cooldown_sec": 0.0,
            "components": {},
            "flags": {}
        }
        self.rf_last_direction = None
        self.rf_smart_assist = True
        self.rf_auto_assist = False
        self.rf_bias_lock = False
        self.rf_locked_bias = None
        self.rf_no_trade_filter = True
        self.rf_adaptive_cooldown = True
        self.rf_duration_ticks = 5
        self.rf_conf_threshold = 70.0
        self.rf_manual_threshold = 60.0
        self.rf_cooldown_until = 0.0
        self.rf_last_trade_ts = 0.0
        self.rf_win_streak = 0
        self.rf_loss_streak = 0
        self.rf_last_result = None
        self.rf_shadow = {
            "enabled": False,
            "sample": 30,
            "live_wins": 0,
            "live_total": 0,
            "alt_wins": 0,
            "alt_total": 0,
            "last_alt": None,
        }
        self.rf_last_take_tick = -999999
        self.rf_last_take_direction = None
        self.rf_late_window_ticks = 3
        # One-trade-per-signal (prevents auto spam on the same TAKE NOW window)
        self.rf_signal_cycle_id = 0
        self.rf_last_take_signal_key = None
        self.rf_consumed_take_signal_key = None

        # Trade stats/history
        self.trade_history = []
        self.total_wins = 0
        self.total_losses = 0
        self.total_profit = 0.0
        self.total_loss = 0.0
        self.last_trade_entry = None

        # Manual plan
        self.manual_plan = {}

        # Risk controls
        self.tp = 0.0
        self.sl = 0.0
        self.auto_sl = True
        self.session_profit = 0.0

        # Patch A: add risk_block_reason
        self.risk_block_reason = None

    def reset_tick_analysis(self):
        keep_auto = self.auto_trade
        keep_symbol = self.symbol
        keep_stake = self.stake
        keep_mult = self.multiplier

        self.reset()

        self.auto_trade = keep_auto
        self.symbol = keep_symbol
        self.stake = keep_stake
        self.multiplier = keep_mult

    def now_time(self):
        return datetime.now().strftime("%H:%M:%S")

    # ----------------------------
    # Utilities
    # ----------------------------
    def _floor_ts(self, ts: int, tf: int) -> int:
        return (ts // tf) * tf

    def _new_candle(self, ts: int, tf: int, price: float) -> Candle:
        start = self._floor_ts(ts, tf)
        return Candle(start_ts=start, tf_sec=tf, open=price, high=price, low=price, close=price)

    def _roll_candle(self, cur: Candle, ts: int, tf: int, price: float):
        if cur is None:
            return self._new_candle(ts, tf, price), None

        cur_start = cur.start_ts
        new_start = self._floor_ts(ts, tf)

        if new_start == cur_start:
            cur.update(price)
            return cur, None

        closed = cur
        new_cur = Candle(start_ts=new_start, tf_sec=tf, open=price, high=price, low=price, close=price)
        return new_cur, closed

    # ----------------------------
    # Auto toggle
    # ----------------------------
    def toggle_auto(self):
        self.auto_trade = not self.auto_trade
        return self.auto_trade

    # ----------------------------
    # HUMAN Rise/Fall Smart Assist
    # ----------------------------
    def _rf_avg(self, n: int):
        if len(self.rf_prices) < n or n <= 0:
            return None
        vals = list(self.rf_prices)[-n:]
        return sum(vals) / float(len(vals))

    def _rf_update_locked_bias(self, fast_avg, slow_avg):
        if not self.rf_bias_lock:
            self.rf_locked_bias = None
            return
        if fast_avg is None or slow_avg is None:
            return
        diff = fast_avg - slow_avg
        if abs(diff) < 1e-12:
            return
        new_bias = "BULLISH" if diff > 0 else "BEARISH"
        # Keep lock until signal degrades heavily; otherwise refresh to current trend
        self.rf_locked_bias = new_bias

    def _rf_compute_signal(self):
        prices = list(self.rf_prices)
        now_ts = time.time()
        if len(prices) < 20:
            self.rf_signal = {
                "bias": "NEUTRAL",
                "signal": "WAIT",
                "trade_direction": None,
                "confidence": 0.0,
                "reason": f"Collecting ticks ({len(prices)}/20)",
                "cooldown_sec": max(0.0, self.rf_cooldown_until - now_ts),
                "components": {"trend": 0, "momentum": 0, "pullback": 0, "trigger": 0, "cleanliness": 0},
                "flags": {"choppy": False, "pullback_ready": False, "trigger_ready": False}
            }
            return self.rf_signal

        cur = prices[-1]
        fast_avg = self._rf_avg(5)
        slow_avg = self._rf_avg(15)
        if fast_avg is None or slow_avg is None:
            return self.rf_signal

        self._rf_update_locked_bias(fast_avg, slow_avg)

        m5 = cur - prices[-6]
        m10 = cur - prices[-11]
        recent5 = prices[-5:]
        recent8 = prices[-8:]
        recent10 = prices[-10:]
        recent15 = prices[-15:]

        diffs = [prices[i] - prices[i-1] for i in range(max(1, len(prices)-15), len(prices))]
        abs_diffs = [abs(d) for d in diffs if d is not None]
        avg_abs_move = (sum(abs_diffs) / len(abs_diffs)) if abs_diffs else 0.0
        range10 = (max(recent10) - min(recent10)) if recent10 else 0.0
        range15 = (max(recent15) - min(recent15)) if recent15 else 0.0

        # Choppiness / no-trade detection
        sign_changes = 0
        prev_sign = 0
        for d in diffs[-10:]:
            s = 1 if d > 0 else (-1 if d < 0 else 0)
            if s and prev_sign and s != prev_sign:
                sign_changes += 1
            if s:
                prev_sign = s

        ma_gap = abs(fast_avg - slow_avg)
        tiny_move = avg_abs_move <= max(abs(cur) * 1e-8, 1e-9)
        flat_ma = ma_gap <= max(avg_abs_move * 0.75, range15 * 0.015 if range15 > 0 else 0.0)
        whip = sign_changes >= 6
        dead = range10 <= max(avg_abs_move * 2.0, abs(cur) * 5e-8)
        choppy = bool((flat_ma and whip) or dead or tiny_move)

        bullish_trend = fast_avg > slow_avg
        bearish_trend = fast_avg < slow_avg
        bias = "BULLISH" if bullish_trend else ("BEARISH" if bearish_trend else "NEUTRAL")

        # Bias lock (optional)
        if self.rf_bias_lock and self.rf_locked_bias in ("BULLISH", "BEARISH"):
            bias = self.rf_locked_bias

        momentum_rise = (m5 > 0 and m10 > 0)
        momentum_fall = (m5 < 0 and m10 < 0)

        # Pullback definitions
        prev_window = prices[-7:-1]
        prev_min = min(prev_window) if prev_window else cur
        prev_max = max(prev_window) if prev_window else cur
        pullback_rise = bool(bias == "BULLISH" and min(recent8) <= fast_avg and min(recent8) >= slow_avg)
        pullback_fall = bool(bias == "BEARISH" and max(recent8) >= fast_avg and max(recent8) <= slow_avg)

        # Trigger (resume in trend direction after pullback)
        trigger_rise = bool((cur > prev_max and prices[-1] > prices[-2]) or (prices[-1] > prices[-2] > prices[-3]))
        trigger_fall = bool((cur < prev_min and prices[-1] < prices[-2]) or (prices[-1] < prices[-2] < prices[-3]))

        # Choose directional candidate / signal state
        signal = "WAIT"            # WAIT / READY / TAKE NOW / LATE
        trade_direction = None     # RISE / FALL when directional context exists
        reason = "No clear setup"
        direction_ok = False
        pullback_ok = False
        trigger_ok = False

        if bias == "BULLISH":
            direction_ok = momentum_rise
            pullback_ok = pullback_rise
            trigger_ok = trigger_rise
            if direction_ok and pullback_ok and trigger_ok:
                signal = "TAKE NOW"
                trade_direction = "RISE"
                reason = "Bullish pullback + momentum confirmation"
            elif direction_ok and pullback_ok:
                signal = "READY"
                trade_direction = "RISE"
                reason = "Bullish setup forming (waiting trigger)"
            elif direction_ok:
                trade_direction = "RISE"
        elif bias == "BEARISH":
            direction_ok = momentum_fall
            pullback_ok = pullback_fall
            trigger_ok = trigger_fall
            if direction_ok and pullback_ok and trigger_ok:
                signal = "TAKE NOW"
                trade_direction = "FALL"
                reason = "Bearish pullback + momentum confirmation"
            elif direction_ok and pullback_ok:
                signal = "READY"
                trade_direction = "FALL"
                reason = "Bearish setup forming (waiting trigger)"
            elif direction_ok:
                trade_direction = "FALL"

        # Confidence score (0-100)
        trend_score = 30 if bias in ("BULLISH", "BEARISH") and ma_gap > 0 else 0
        if trend_score and range15 > 0:
            trend_score = min(30, max(8, int(30 * min(1.0, ma_gap / max(range15 * 0.20, 1e-12)))))

        momentum_score = 0
        if bias == "BULLISH":
            if m5 > 0 and m10 > 0:
                momentum_score = 25
            elif m5 > 0 or m10 > 0:
                momentum_score = 12
        elif bias == "BEARISH":
            if m5 < 0 and m10 < 0:
                momentum_score = 25
            elif m5 < 0 or m10 < 0:
                momentum_score = 12

        pullback_score = 20 if pullback_ok else 0
        if pullback_ok and range15 > 0 and fast_avg is not None:
            dist_to_fast = abs(cur - fast_avg)
            # smaller distance after pullback recovery is better
            pullback_score = max(8, min(20, int(20 * (1.0 - min(1.0, dist_to_fast / max(range15 * 0.25, 1e-12))))))

        trigger_score = 15 if trigger_ok else 0
        cleanliness_score = 10 if not choppy else 0

        confidence = float(trend_score + momentum_score + pullback_score + trigger_score + cleanliness_score)

        # Edge gap proxy: compare confidence to minimum actionable threshold and momentum/trend disagreement
        edge_gap = max(0.0, confidence - (self.rf_conf_threshold - 8.0))

        # No-trade filtering and cooldown
        cooldown_left = max(0.0, self.rf_cooldown_until - now_ts)
        hard_blocked = False
        if cooldown_left > 0:
            signal = "WAIT"
            trade_direction = None
            reason = f"Cooldown active ({cooldown_left:.1f}s)"
            hard_blocked = True

        if self.rf_no_trade_filter and choppy and signal != "WAIT":
            signal = "WAIT"
            trade_direction = None
            reason = "No-Trade Zone: choppy ticks"
            hard_blocked = True

        if signal == "TAKE NOW" and confidence < self.rf_manual_threshold:
            signal = "WAIT"
            trade_direction = None
            reason = "Setup too weak"
            hard_blocked = True

        # If smart assist is off, still report analytics but don't output directional signal
        if not self.rf_smart_assist:
            signal = "WAIT"
            trade_direction = None
            reason = "Smart Assist OFF"
            hard_blocked = True

        # Bias lock mismatch guard
        if self.rf_bias_lock and self.rf_locked_bias and bias in ("BULLISH", "BEARISH"):
            if bias != self.rf_locked_bias:
                signal = "WAIT"
                trade_direction = None
                reason = "Bias Lock holding previous trend"
                hard_blocked = True

        # Track fresh trigger windows and create a short "LATE" state for human reaction time
        if signal == "TAKE NOW" and trade_direction in ("RISE", "FALL"):
            self.rf_last_take_tick = int(self.tick_count)
            self.rf_last_take_direction = trade_direction

        if signal == "WAIT" and not hard_blocked:
            recent_take = (int(self.tick_count) - int(self.rf_last_take_tick)) <= int(self.rf_late_window_ticks or 0)
            late_dir = self.rf_last_take_direction
            late_conf_min = max(45.0, float(self.rf_manual_threshold) - 12.0)
            late_supported = (
                (late_dir == "RISE" and bias == "BULLISH" and momentum_rise) or
                (late_dir == "FALL" and bias == "BEARISH" and momentum_fall)
            )
            if recent_take and late_dir in ("RISE", "FALL") and late_supported and confidence >= late_conf_min:
                signal = "LATE"
                trade_direction = late_dir
                reason = f"{late_dir} setup aging (weaker entry than TAKE NOW)"

        # Track TAKE NOW cycles so auto/trade can consume only one trade per signal window
        prev_sig = self.rf_signal if isinstance(getattr(self, "rf_signal", None), dict) else {}
        prev_state = str(prev_sig.get("signal") or "WAIT").upper()
        prev_dir = str(prev_sig.get("trade_direction") or "").upper()
        signal_key = None
        signal_consumed = False
        if signal == "TAKE NOW" and trade_direction in ("RISE", "FALL"):
            if not (prev_state == "TAKE NOW" and prev_dir == str(trade_direction).upper()):
                self.rf_signal_cycle_id = int(getattr(self, "rf_signal_cycle_id", 0)) + 1
            signal_key = f"{str(trade_direction).upper()}:{int(self.rf_signal_cycle_id)}"
            self.rf_last_take_signal_key = signal_key
            signal_consumed = bool(signal_key and signal_key == getattr(self, "rf_consumed_take_signal_key", None))
        else:
            # Once setup leaves TAKE NOW, next TAKE NOW becomes a new cycle and can trade again
            self.rf_last_take_signal_key = None

        self.rf_signal = {
            "bias": bias,
            "signal": signal,
            "trade_direction": trade_direction,
            "signal_key": signal_key,
            "signal_consumed": bool(signal_consumed),
            "confidence": round(confidence, 1),
            "reason": reason,
            "cooldown_sec": round(cooldown_left, 1),
            "edge_gap": round(edge_gap, 1),
            "components": {
                "trend": int(trend_score),
                "momentum": int(momentum_score),
                "pullback": int(pullback_score),
                "trigger": int(trigger_score),
                "cleanliness": int(cleanliness_score),
            },
            "flags": {
                "choppy": bool(choppy),
                "pullback_ready": bool(pullback_ok),
                "trigger_ready": bool(trigger_ok),
                "momentum_ok": bool(direction_ok),
                "auto_ready": bool(signal == "TAKE NOW" and trade_direction in ("RISE", "FALL") and confidence >= self.rf_conf_threshold and cooldown_left <= 0 and not signal_consumed),
                "signal_consumed": bool(signal_consumed),
            },
            "metrics": {
                "fast_avg": fast_avg,
                "slow_avg": slow_avg,
                "m5": m5,
                "m10": m10,
                "range10": range10,
                "range15": range15,
                "sign_changes": sign_changes,
            },
            "settings": {
                "smart_assist": bool(self.rf_smart_assist),
                "auto_assist": bool(self.rf_auto_assist),
                "bias_lock": bool(self.rf_bias_lock),
                "no_trade_filter": bool(self.rf_no_trade_filter),
                "adaptive_cooldown": bool(self.rf_adaptive_cooldown),
                "duration_ticks": int(self.rf_duration_ticks),
                "conf_threshold": float(self.rf_conf_threshold),
            },
            "streaks": {
                "wins": int(self.rf_win_streak),
                "losses": int(self.rf_loss_streak),
                "last_result": self.rf_last_result,
            }
        }
        return self.rf_signal

    def set_human_rf_settings(self, **kwargs):
        bool_fields = ["smart_assist", "auto_assist", "bias_lock", "no_trade_filter", "adaptive_cooldown"]
        for k in bool_fields:
            if k in kwargs and kwargs[k] is not None:
                setattr(self, f"rf_{k}", bool(kwargs[k]))
        if kwargs.get("duration_ticks") is not None:
            try:
                dur = int(kwargs.get("duration_ticks"))
                if dur < 1:
                    dur = 1
                if dur > 10:
                    dur = 10
                self.rf_duration_ticks = dur
            except Exception:
                pass
        if kwargs.get("conf_threshold") is not None:
            try:
                t = float(kwargs.get("conf_threshold"))
                self.rf_conf_threshold = max(1.0, min(100.0, t))
            except Exception:
                pass
        self._rf_compute_signal()
        return self.get_human_rf_payload()

    def get_human_rf_payload(self):
        if not self.rf_signal:
            self._rf_compute_signal()
        payload = dict(self.rf_signal or {})
        payload.setdefault("settings", {})
        payload["settings"] = {
            **payload.get("settings", {}),
            "smart_assist": bool(self.rf_smart_assist),
            "auto_assist": bool(self.rf_auto_assist),
            "bias_lock": bool(self.rf_bias_lock),
            "no_trade_filter": bool(self.rf_no_trade_filter),
            "adaptive_cooldown": bool(self.rf_adaptive_cooldown),
            "duration_ticks": int(self.rf_duration_ticks),
            "conf_threshold": float(self.rf_conf_threshold),
        }
        return payload

    def _rf_consume_current_take_signal(self):
        """Lock current TAKE NOW cycle so auto only takes one trade per signal."""
        try:
            sig = self._rf_compute_signal()
        except Exception:
            sig = self.rf_signal if isinstance(getattr(self, "rf_signal", None), dict) else {}
        state = str((sig or {}).get("signal") or "WAIT").upper()
        key = (sig or {}).get("signal_key")
        if state == "TAKE NOW" and key:
            self.rf_consumed_take_signal_key = str(key)
            # refresh payload flags so UI shows consumed/not auto-ready immediately
            self._rf_compute_signal()
            return self.rf_consumed_take_signal_key
        return None

    def _rf_apply_trade_result(self, result: str):
        self.rf_last_result = result
        if result == "WIN":
            self.rf_win_streak += 1
            self.rf_loss_streak = 0
            cooldown = 2.0
        else:
            self.rf_loss_streak += 1
            self.rf_win_streak = 0
            cooldown = 6.0
            if self.rf_loss_streak >= 2:
                cooldown = 10.0
            if self.rf_loss_streak >= 3:
                cooldown = 15.0
        if not self.rf_adaptive_cooldown:
            cooldown = 2.0
        self.rf_cooldown_until = max(self.rf_cooldown_until, time.time() + cooldown)
        self._rf_compute_signal()

    def build_human_rf_trade_signal(self, force_direction=None, require_threshold=True):
        sig = self._rf_compute_signal()
        if not sig:
            return None

        state = str(sig.get("signal") or "WAIT").upper()
        sig_direction = str(sig.get("trade_direction") or "").upper()
        direction = None
        if force_direction:
            fd = str(force_direction).upper().strip()
            if fd in ("RISE", "FALL"):
                direction = fd
        else:
            if sig_direction in ("RISE", "FALL"):
                # STRICT (auto) => TAKE NOW only. Manual/relaxed => TAKE NOW or LATE.
                if require_threshold and state != "TAKE NOW":
                    return None
                if (not require_threshold) and state not in ("TAKE NOW", "LATE"):
                    return None
                direction = sig_direction

        if not direction:
            return None

        if require_threshold and not force_direction:
            if float(sig.get("confidence", 0.0) or 0.0) < float(self.rf_conf_threshold):
                return None
            if sig.get("cooldown_sec", 0) and float(sig.get("cooldown_sec", 0)) > 0:
                return None
            # One trade per TAKE NOW signal cycle (prevents spam while same signal stays active)
            if state == "TAKE NOW":
                sig_key = sig.get("signal_key")
                consumed_key = getattr(self, "rf_consumed_take_signal_key", None)
                if sig_key and consumed_key and str(sig_key) == str(consumed_key):
                    return None

        # manual forced trades still respect cooldown only when adaptive cooldown is enabled strongly
        if force_direction and self.rf_adaptive_cooldown:
            if time.time() < float(self.rf_cooldown_until or 0.0):
                return None

        # Consume the current TAKE NOW signal cycle for strict signal-based trades (auto / TAKE SIGNAL)
        if require_threshold and not force_direction and state == "TAKE NOW":
            self.rf_consumed_take_signal_key = str(sig.get("signal_key")) if sig.get("signal_key") else self.rf_consumed_take_signal_key

        self.rf_last_direction = direction
        self.rf_last_trade_ts = time.time()
        # brief baseline cooldown to avoid accidental duplicate same tick entries
        self.rf_cooldown_until = max(self.rf_cooldown_until, self.rf_last_trade_ts + 1.5)
        self._rf_compute_signal()
        return {
            "direction": direction,
            "contract_type": "CALL" if direction == "RISE" else "PUT",
            "stake": float(self.stake or 1.0),
            "duration": int(self.rf_duration_ticks),
            "duration_unit": "t",
            "mode": "human_rf",
            "profile": "HUMAN"
        }

    # ----------------------------
    # Order Block logic
    # ----------------------------
    def _update_range_from_prev_1h(self):
        if not self.hist_1h:
            return
        prev = self.hist_1h[-1]
        self.range_high = prev.high
        self.range_low = prev.low
        self.range_start_ts = prev.start_ts
        self.range_size = max(0.0, self.range_high - self.range_low)

        # Reset state for new range
        self.breakout_bias = None
        self.breakout_ts = None
        self.breakout_price = None
        self.order_block = None
        self.retrace_happened = False
        self.signal_fired = False

    def _check_breakout(self, price):
        if self.range_high is None or self.range_low is None:
            return
        if self.breakout_bias is not None:
            return
        if price > self.range_high:
            self.breakout_bias = "BUY"
            self.breakout_ts = self.last_ts
            self.breakout_price = price
            self._identify_order_block(direction="BUY")
        elif price < self.range_low:
            self.breakout_bias = "SELL"
            self.breakout_ts = self.last_ts
            self.breakout_price = price
            self._identify_order_block(direction="SELL")

    def _identify_order_block(self, direction):
        if not self.breakout_ts:
            return

        # Find the last opposite 1h candle before breakout hour
        breakout_hour_start = self._floor_ts(self.breakout_ts, self.tf_1h)

        for candle in reversed(self.hist_1h):
            if candle.start_ts >= breakout_hour_start:
                continue

            if direction == "BUY" and candle.close < candle.open:
                self.order_block = {"high": candle.high, "low": candle.low, "start_ts": candle.start_ts}
                break

            if direction == "SELL" and candle.close > candle.open:
                self.order_block = {"high": candle.high, "low": candle.low, "start_ts": candle.start_ts}
                break

    def _check_retrace(self, price):
        if not self.order_block or self.retrace_happened or self.signal_fired:
            return
        if self.order_block["low"] <= price <= self.order_block["high"]:
            self.retrace_happened = True
            self.retrace_ts = self.last_ts
            self.retrace_price = price

    def _check_confirmation(self, price):
        if not self.retrace_happened or self.signal_fired or not self.order_block:
            return None

        # Confirmation: price moves a tiny amount beyond the OB in breakout direction
        buffer = 0.0002  # small buffer (adjust for forex/indices)

        if self.breakout_bias == "BUY" and price > self.order_block["high"] + buffer:
            self.signal_fired = True
            return self._build_signal("BUY")

        if self.breakout_bias == "SELL" and price < self.order_block["low"] - buffer:
            self.signal_fired = True
            return self._build_signal("SELL")

        return None

    def _build_signal(self, direction):
        entry = self.last_price
        range_size = self.range_size if self.range_size else 0.001  # fallback

        if direction == "BUY":
            sl = self.order_block["low"] - 0.0002  # below OB
            tp = entry + range_size * 0.75
        else:
            sl = self.order_block["high"] + 0.0002  # above OB
            tp = entry - range_size * 0.75

        return {
            "direction": direction,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "stake": self.stake,
            "multiplier": self.multiplier,
            "mode": "humanX"
        }

    def get_humanx_signal(self):
        # Safety gate: if risk controls already hit, don't allow new signals
        _hit = self.enforce_tp_sl()
        if _hit:
            return None

        if time.time() - self.last_signal_time < self.humanx_cooldown:
            return None
        if self.last_price is None:
            return None

        # Trigger checks using last known price
        self._check_breakout(self.last_price)
        self._check_retrace(self.last_price)
        signal = self._check_confirmation(self.last_price)

        if signal:
            self.last_signal_time = time.time()

        return signal

    # ----------------------------
    # Tick handling
    # ----------------------------
    def on_tick(self, tick, digit=None, ts: int = None):
        """
        Server calls: on_tick(tick, digit)
        We ignore 'digit' and use tick['quote'] as PRICE for candles/OB logic.
        """
        # timestamp
        if ts is None:
            try:
                ts = int(tick.get("epoch") or tick.get("timestamp") or tick.get("time"))
            except Exception:
                ts = int(time.time())

        # price (Deriv tick uses "quote")
        try:
            price = float(tick.get("quote"))
        except Exception:
            # fallback: if quote missing, do nothing
            return

        self.tick_count += 1
        self.last_price = price
        self.last_ts = ts

        # HUMAN Rise/Fall Smart Assist rolling prices
        self.rf_prices.append(price)
        self._rf_compute_signal()

        # Build candles
        self.cur_1m, closed_1m = self._roll_candle(self.cur_1m, ts, self.tf_1m, price)
        if closed_1m:
            self.hist_1m.append(closed_1m)

        self.cur_5m, closed_5m = self._roll_candle(self.cur_5m, ts, self.tf_5m, price)
        if closed_5m:
            self.hist_5m.append(closed_5m)

        self.cur_1h, closed_1h = self._roll_candle(self.cur_1h, ts, self.tf_1h, price)
        if closed_1h:
            self.hist_1h.append(closed_1h)
            self._update_range_from_prev_1h()

        # OB checks are triggered by get_humanx_signal() (button-driven)

    # ----------------------------
    # Contract handling
    # ----------------------------
    def on_contract(self, contract, balance):
        status = (contract.get("status") or "").lower()

        if not (contract.get("is_sold") or contract.get("is_settled") or status in ("sold", "settled", "closed", "won", "lost")):
            return

        profit = float(contract.get("profit", 0))
        buy_price = float(contract.get("buy_price", 0))
        contract_type = contract.get("contract_type", "MULTIPLIER")

        result = "WIN" if profit > 0 else "LOSS"

        # Apply HUMAN Rise/Fall adaptive cooldown only for CALL/PUT contracts
        try:
            ctype = str(contract.get("contract_type") or "").upper()
            if ctype in ("CALL", "PUT"):
                self._rf_apply_trade_result(result)
        except Exception:
            pass

        if profit > 0:
            self.total_wins += 1
            self.total_profit += profit
        else:
            self.total_losses += 1
            self.total_loss += abs(profit)

        self.session_profit += profit

        # Patch D: enforce TP/SL after updating session_profit
        self.enforce_tp_sl()

        entry = {
            "time": self.now_time(),
            "result": result,
            "profit": round(profit, 2),
            "contract_type": contract_type,
            "buy_price": round(buy_price, 2),
            "balance": round(float(balance), 2),
            "symbol": contract.get("underlying", self.symbol or ""),
        }
        contract_id = contract.get("contract_id") or contract.get("id")
        if contract_id not in (None, ""):
            entry["contract_id"] = str(contract_id)

        self.trade_history.append(entry)
        if len(self.trade_history) > 200:
            self.trade_history.pop(0)

        self.last_trade_entry = entry

        # After trade, reset OB state (allow new setup)
        self.breakout_bias = None
        self.order_block = None
        self.retrace_happened = False
        self.signal_fired = False

    def get_last_trade_entry(self):
        return self.last_trade_entry or {}

    def clear_history(self):
        self.trade_history = []
        self.total_wins = 0
        self.total_losses = 0
        self.total_profit = 0.0
        self.total_loss = 0.0
        self.last_trade_entry = None
        # Patch B: reset session profit and block reason
        self.session_profit = 0.0
        self.risk_block_reason = None

    # ----------------------------
    # Chart data
    # ----------------------------
    def _parse_seed_candle(self, item: dict, tf_sec: int):
        """Parse a Deriv candle dict into a Candle object (best-effort)."""
        try:
            ts = int(item.get("epoch") or item.get("timestamp") or item.get("time") or 0)
            o = float(item.get("open"))
            h = float(item.get("high"))
            l = float(item.get("low"))
            c = float(item.get("close"))
            if not ts:
                return None
            return Candle(start_ts=ts, tf_sec=tf_sec, open=o, high=h, low=l, close=c)
        except Exception:
            return None

    def seed_5m_history(self, candles: list):
        """Seed recent 5M candles so the chart can render immediately."""
        try:
            self.hist_5m.clear()
            self.cur_5m = None
            if not isinstance(candles, list):
                return
            for item in candles:
                c = self._parse_seed_candle(item, self.tf_5m)
                if c:
                    self.hist_5m.append(c)
        except Exception:
            pass

    def seed_1h_history(self, candles: list):
        """Seed recent 1H candles so we can compute Prev 1H range immediately."""
        try:
            self.hist_1h.clear()
            self.cur_1h = None
            if not isinstance(candles, list):
                return
            for item in candles:
                c = self._parse_seed_candle(item, self.tf_1h)
                if c:
                    self.hist_1h.append(c)

            # update Prev 1H range from last CLOSED 1H candle
            self._update_range_from_prev_1h()
        except Exception:
            pass

    def get_chart_data(self):
        """Return payload for the frontend chart (5M + 1H) without touching trade logic."""
        def to_dict(c: Candle):
            return {
                "time": int(c.start_ts),
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
            }

        # 5M candles (need at least last 2 hours for the "new vs previous hour" blocks)
        all_5m = list(self.hist_5m)
        if self.cur_5m:
            all_5m.append(self.cur_5m)
        all_5m = sorted(all_5m, key=lambda x: x.start_ts)

        candles_5m = [to_dict(c) for c in all_5m[-24:]]  # 24 x 5m = 2 hours

        # 1H candles for TF switch
        all_1h = list(self.hist_1h)
        if self.cur_1h:
            all_1h.append(self.cur_1h)
        all_1h = sorted(all_1h, key=lambda x: x.start_ts)
        candles_1h = [to_dict(c) for c in all_1h[-24:]]  # last 24 hours (max)

        # previous CLOSED 1H candle
        prev_h1 = self.hist_1h[-1] if len(self.hist_1h) > 0 else None

        return {
            # keep backward-compat keys
            "tf_sec": self.tf_5m,
            "candles": candles_5m,
            "current_price": self.last_price or 0,

            # new keys
            "candles_5m": candles_5m,
            "candles_1h": candles_1h,
            "prev_h1": to_dict(prev_h1) if prev_h1 else None,

            # prev 1H range lines
            "range_high": self.range_high or 0,
            "range_low": self.range_low or 0,
            "range_start_ts": self.range_start_ts or 0,

            # OB + bias (OB = current as per your instruction)
            "breakout_bias": self.breakout_bias,
            "order_block": self.order_block,
            "retrace_happened": self.retrace_happened,
        }

    # ----------------------------
    # Risk controls
    # ----------------------------
    def set_risk_controls(self, tp=0.0, sl=0.0, auto_sl=True):
        self.tp = float(tp)
        self.sl = float(sl)
        self.auto_sl = bool(auto_sl)

    # Patch C: add disable_all_autos
    def disable_all_autos(self):
        self.auto_trade = False

    # Patch C: replace enforce_tp_sl with new version
    def enforce_tp_sl(self):
        if getattr(self, "risk_block_reason", None):
            return self.risk_block_reason

        if self.tp > 0 and self.session_profit >= self.tp:
            self.risk_block_reason = "TP HIT"
            self.disable_all_autos()
            return self.risk_block_reason

        if self.sl > 0 and self.session_profit <= -abs(self.sl):
            self.risk_block_reason = "SL HIT"
            self.disable_all_autos()
            return self.risk_block_reason

        return None

    # ----------------------------
    # UI payloads
    # ----------------------------
    def get_ui_payload(self):
        return {
            "tick_count": self.tick_count,
            "last_price": self.last_price,
            "mode": "HUMAN",
            "range": {
                "high": self.range_high,
                "low": self.range_low,
                "size": self.range_size,
            },
            "breakout": {
                "bias": self.breakout_bias,
                "price": self.breakout_price,
            },
            "order_block": self.order_block,
            "retrace_happened": self.retrace_happened,
            "signal_fired": self.signal_fired,
            "auto_trade": self.auto_trade,
            "rise_fall": self.get_human_rf_payload(),
        }

    def get_stats_payload(self, balance, session_start_balance):
        total_trades = self.total_wins + self.total_losses
        winrate = (self.total_wins / total_trades * 100) if total_trades > 0 else 0
        loserate = (self.total_losses / total_trades * 100) if total_trades > 0 else 0
        net_pnl = self.total_profit - self.total_loss

        session_pnl = 0
        if session_start_balance is not None:
            session_pnl = balance - session_start_balance

        return {
            "balance": round(balance, 2),
            "wins": self.total_wins,
            "losses": self.total_losses,
            "winrate": round(winrate, 1),
            "loserate": round(loserate, 1),
            "total_profit": round(self.total_profit, 2),
            "total_loss": round(self.total_loss, 2),
            "net_pnl": round(net_pnl, 2),
            "session_pnl": round(session_pnl, 2),
            "auto_trade": self.auto_trade,
        }
