# strategies/unchain.py
from collections import deque
from datetime import datetime
import time
import math
import statistics


class UnchainStrategy:
    """
    UNCHAIN — dedicated Accumulators profile (signal + risk-managed exits)
    Two modes:
      - AUTO: exits at 5 ticks, but can early-exit before 5 if market turns choppy
      - MANUAL: user sets exit ticks; optional early safety exit
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.tick_count = 0
        self.last_price = None
        self.last_digit = None
        self.last_symbol = None
        self.last_tick_ts = 0
        self.price_history = deque(maxlen=240)
        self.delta_history = deque(maxlen=120)
        self.abs_delta_history = deque(maxlen=120)
        self.sign_history = deque(maxlen=120)

        # Crash / spike detection stats
        self.market_tick_counter = 0
        self.last_crash_tick = None  # absolute tick index
        self.last_crash_cycle_ticks = None  # ticks count at the last crash event
        self.last_crash_at_ts = None
        self.crash_intervals = deque(maxlen=20)
        self.recent_crash_points = deque(maxlen=10)  # tuples (tick_index, delta, price)
        self.ticks_since_last_crash = None

        # Signal / regime state
        self.warmup_ticks_required = 35
        self.bias = "NEUTRAL"
        self.signal_state = "WAIT"   # WAIT / READY / TAKE NOW / LATE
        self.signal_side = None      # "RISE" / "FALL"
        self.market_state = "WARMING UP"
        self.no_trade_reason = "Warming up"
        self.confidence = 0.0
        self.edge_gap = 0.0
        self.chop_score = 100.0
        self.crash_risk = "UNKNOWN"
        self.signal_components = {
            "trend": 0,
            "momentum": 0,
            "pullback": 0,
            "trigger": 0,
            "cleanliness": 0,
        }

        # Signal cycle control (one-trade-per-signal)
        self.signal_cycle_id = 0
        self._last_signal_signature = None
        self._consumed_signal_cycle_id = None
        self._take_now_started_at_tick = None
        self._late_until_tick = None
        self._ready_tick = None

        # Trade/cooldown
        self.auto_enabled = False
        self.mode = "AUTO"  # AUTO / MANUAL
        self.cooldown_sec = 10
        self.cooldown_until = 0.0
        self.adaptive_cooldown = True
        self.loss_streak = 0
        self.win_streak = 0
        self.last_result = None
        self.last_result_time = None

        # Entry/exit settings
        self.confidence_threshold = 70.0
        self.manual_exit_ticks = 10
        self.auto_exit_ticks = 5
        self.growth_rate = 0.02
        self.auto_early_exit = True
        self.manual_allow_early_exit = True
        self.signal_strength = "BALANCED"  # WEAK / MEDIUM / STRONG / BALANCED
        self.no_trade_filter = True

        # Active contract tracking
        self.active_contract_id = None
        self.active_contract_open = False
        self.active_entry_tick_seq = None
        self.active_entry_market_tick_counter = None
        self.active_entry_symbol = None
        self.active_mode = None
        self.active_target_exit_ticks = None
        self.active_stake_amount = None
        self.pending_trade_stake = None
        self.exit_requested = False
        self.exit_requested_reason = None
        self.open_contract_profit = None
        self.open_contract_sell_price = None
        self.open_contract_entry_spot = None
        self.open_contract_current_spot = None

        # Pending request lock (prevents duplicate buys while waiting for buy response)
        self.pending_trade_request = False
        self.pending_trade_mode = None
        self.pending_trade_exit_ticks = None

        # Stats + risk controls
        self.trade_history = []
        self.total_wins = 0
        self.total_losses = 0
        self.total_profit = 0.0
        self.total_loss = 0.0
        self.last_trade_entry = None
        self.session_profit = 0.0
        self.risk_block_reason = None
        self.tp = 0.0
        self.sl = 0.0
        self.auto_sl = True

    # -----------------------------
    # Utility / time
    # -----------------------------
    def now_time(self):
        return datetime.now().strftime("%H:%M:%S")

    def _to_float(self, v, default=0.0):
        try:
            return float(v)
        except Exception:
            return float(default)

    # -----------------------------
    # Settings / risk controls
    # -----------------------------
    def set_settings(self, **kwargs):
        mode = kwargs.get("mode")
        if mode is not None:
            m = str(mode).upper().strip()
            if m in ("AUTO", "MANUAL"):
                self.mode = m

        if kwargs.get("confidence_threshold") is not None:
            try:
                x = float(kwargs.get("confidence_threshold"))
                self.confidence_threshold = max(50.0, min(99.0, x))
            except Exception:
                pass

        if kwargs.get("manual_exit_ticks") is not None:
            try:
                x = int(kwargs.get("manual_exit_ticks"))
                self.manual_exit_ticks = max(1, min(50, x))
            except Exception:
                pass

        if kwargs.get("growth_rate") is not None:
            try:
                x = float(kwargs.get("growth_rate"))
                self.growth_rate = max(0.01, min(0.05, x))
            except Exception:
                pass

        if kwargs.get("auto_early_exit") is not None:
            self.auto_early_exit = bool(kwargs.get("auto_early_exit"))
        if kwargs.get("manual_allow_early_exit") is not None:
            self.manual_allow_early_exit = bool(kwargs.get("manual_allow_early_exit"))
        if kwargs.get("signal_strength") is not None:
            s = str(kwargs.get("signal_strength")).upper().strip()
            if s in ("WEAK", "MEDIUM", "STRONG", "BALANCED"):
                self.signal_strength = s
        if kwargs.get("cooldown_sec") is not None:
            try:
                cd = int(kwargs.get("cooldown_sec"))
                self.cooldown_sec = max(3, min(60, cd))
            except Exception:
                pass

    def set_risk_controls(self, tp=0.0, sl=0.0, auto_sl=True):
        self.tp = self._to_float(tp, 0.0)
        self.sl = self._to_float(sl, 0.0)
        self.auto_sl = bool(auto_sl)

    def enforce_tp_sl(self):
        self.risk_block_reason = None
        # session TP/SL in net profit units
        try:
            if self.tp and self.tp > 0 and self.session_profit >= self.tp:
                self.risk_block_reason = f"TP hit (+{self.session_profit:.2f})"
                return
            if self.sl and self.sl > 0 and self.session_profit <= -abs(self.sl):
                self.risk_block_reason = f"SL hit ({self.session_profit:.2f})"
                return
        except Exception:
            self.risk_block_reason = None

    def toggle_auto(self):
        self.auto_enabled = not self.auto_enabled
        return self.auto_enabled

    def stop_auto(self):
        self.auto_enabled = False
        return self.auto_enabled

    # -----------------------------
    # Tick processing + analysis
    # -----------------------------
    def on_tick(self, tick, digit=None):
        try:
            price = tick.get("quote") if isinstance(tick, dict) else None
            price = self._to_float(price, None)
            if price is None:
                return
        except Exception:
            return

        self.tick_count += 1
        self.market_tick_counter += 1
        self.last_symbol = (tick or {}).get("symbol") or self.last_symbol
        self.last_tick_ts = int((tick or {}).get("epoch") or time.time())
        self.last_digit = digit

        prev_price = self.last_price
        self.last_price = price
        self.price_history.append(price)

        if prev_price is not None:
            delta = price - prev_price
            self.delta_history.append(delta)
            self.abs_delta_history.append(abs(delta))
            if delta > 0:
                self.sign_history.append(1)
            elif delta < 0:
                self.sign_history.append(-1)
            else:
                self.sign_history.append(0)
            self._update_crash_stats(delta, price)

        self._analyze_signal()

    def _update_crash_stats(self, delta, price):
        if len(self.abs_delta_history) < 12:
            self.ticks_since_last_crash = None if self.last_crash_tick is None else (self.market_tick_counter - self.last_crash_tick)
            return

        absd = list(self.abs_delta_history)
        med = statistics.median(absd) if absd else 0.0
        mean = (sum(absd) / len(absd)) if absd else 0.0
        base_thr = max(med * 6.0, mean * 4.5, 1e-9)

        # Crash/Boom directional tuning if symbol name hints exist
        sym = (self.last_symbol or "").upper()
        directional_ok = True
        if "CRASH" in sym:
            directional_ok = (delta < 0)  # downward spikes
            base_thr = max(base_thr, med * 4.5)
        elif "BOOM" in sym:
            directional_ok = (delta > 0)  # upward spikes
            base_thr = max(base_thr, med * 4.5)

        is_crash = directional_ok and abs(delta) >= base_thr
        if is_crash:
            if self.last_crash_tick is not None:
                interval = self.market_tick_counter - self.last_crash_tick
                if interval > 0:
                    self.crash_intervals.append(interval)
                    self.last_crash_cycle_ticks = int(interval)
            else:
                self.last_crash_cycle_ticks = int(self.market_tick_counter)
            self.last_crash_tick = self.market_tick_counter
            self.last_crash_at_ts = self.last_tick_ts
            self.recent_crash_points.append((self.market_tick_counter, float(delta), float(price)))

        self.ticks_since_last_crash = None if self.last_crash_tick is None else (self.market_tick_counter - self.last_crash_tick)

    def _rolling(self, n):
        vals = list(self.price_history)
        if len(vals) < n:
            return None
        return vals[-n:]

    def _mean(self, vals):
        if not vals:
            return None
        return sum(vals) / len(vals)

    def _analyze_signal(self):
        # Defaults
        self.no_trade_reason = ""
        self.bias = "NEUTRAL"
        self.market_state = "WARMING UP"
        self.crash_risk = "UNKNOWN"
        self.signal_components = {"trend": 0, "momentum": 0, "pullback": 0, "trigger": 0, "cleanliness": 0}
        self.edge_gap = 0.0

        # Warm-up
        if len(self.price_history) < self.warmup_ticks_required or len(self.delta_history) < 18:
            self.confidence = 0.0
            self.signal_state = "WAIT"
            self.signal_side = None
            self.no_trade_reason = f"Warming up {len(self.price_history)}/{self.warmup_ticks_required}"
            return

        p5 = self._rolling(5)
        p10 = self._rolling(10)
        p15 = self._rolling(15)
        p20 = self._rolling(20)
        if not all([p5, p10, p15, p20]):
            self.confidence = 0.0
            self.signal_state = "WAIT"
            self.signal_side = None
            self.no_trade_reason = "Waiting data"
            return

        fast = self._mean(p5)
        slow = self._mean(p15)
        very_slow = self._mean(p20)
        current = self.price_history[-1]
        prev2 = self.price_history[-3] if len(self.price_history) >= 3 else current

        momentum5 = current - self.price_history[-6]
        momentum10 = current - self.price_history[-11]

        recent_d = list(self.delta_history)[-20:]
        flips = 0
        prev_sign = 0
        for d in recent_d:
            s = 1 if d > 0 else (-1 if d < 0 else 0)
            if prev_sign and s and s != prev_sign:
                flips += 1
            if s:
                prev_sign = s
        flip_ratio = flips / max(1, len(recent_d) - 1)

        absd = list(self.abs_delta_history)[-30:]
        med = statistics.median(absd) if absd else 0.0
        mean_abs = (sum(absd) / len(absd)) if absd else 0.0
        max_abs = max(absd) if absd else 0.0

        # trend / bias
        bullish = fast > slow and slow >= very_slow
        bearish = fast < slow and slow <= very_slow
        if bullish:
            self.bias = "BULLISH"
        elif bearish:
            self.bias = "BEARISH"
        else:
            self.bias = "NEUTRAL"

        # pullback quality (distance to fast while respecting slow)
        pullback_ok_rise = bullish and current >= slow and current <= fast
        pullback_ok_fall = bearish and current <= slow and current >= fast

        # trigger (micro resumption)
        last2 = list(self.delta_history)[-3:]
        trigger_rise = (current > max(self.price_history[-3:-1])) or (len(last2) >= 2 and last2[-1] > 0 and last2[-2] > 0)
        trigger_fall = (current < min(self.price_history[-3:-1])) or (len(last2) >= 2 and last2[-1] < 0 and last2[-2] < 0)

        # chop / cleanliness
        noise_ratio = 0.0
        net_move = abs(current - self.price_history[-16])
        gross_move = sum(abs(x) for x in list(self.delta_history)[-15:])
        if gross_move > 0:
            noise_ratio = 1.0 - min(1.0, net_move / gross_move)
        self.chop_score = round(min(100.0, max(0.0, (flip_ratio * 60.0) + (noise_ratio * 40.0))), 1)

        if max_abs > max(med * 6 if med else 0, mean_abs * 5 if mean_abs else 0):
            self.crash_risk = "HIGH"
        elif max_abs > max(med * 4 if med else 0, mean_abs * 3 if mean_abs else 0):
            self.crash_risk = "MEDIUM"
        else:
            self.crash_risk = "LOW"

        # Scoring
        trend_pts = 30 if (bullish or bearish) else 8
        momentum_ok = ((momentum5 > 0 and momentum10 > 0 and bullish) or (momentum5 < 0 and momentum10 < 0 and bearish))
        momentum_pts = 25 if momentum_ok else (10 if (bullish or bearish) else 4)
        pullback_pts = 20 if (pullback_ok_rise or pullback_ok_fall) else 6
        trigger_pts = 15 if ((trigger_rise and bullish) or (trigger_fall and bearish)) else (6 if (bullish or bearish) else 2)

        clean_pts = 10
        if self.chop_score >= 75:
            clean_pts = 0
        elif self.chop_score >= 60:
            clean_pts = 2
        elif self.chop_score >= 45:
            clean_pts = 5
        elif self.chop_score >= 30:
            clean_pts = 8

        self.signal_components = {
            "trend": int(trend_pts),
            "momentum": int(momentum_pts),
            "pullback": int(pullback_pts),
            "trigger": int(trigger_pts),
            "cleanliness": int(clean_pts),
        }
        confidence = trend_pts + momentum_pts + pullback_pts + trigger_pts + clean_pts

        # Strength profile modifies thresholds
        threshold = self.confidence_threshold
        if self.signal_strength in ("STRONG",):
            threshold = max(threshold, 78.0)
        elif self.signal_strength in ("WEAK",):
            threshold = min(threshold, 62.0)
        elif self.signal_strength in ("MEDIUM", "BALANCED"):
            pass

        # Edge gap as difference between directional scores (rise vs fall)
        rise_score = 0
        fall_score = 0
        if bullish:
            rise_score += 35
        if bearish:
            fall_score += 35
        if momentum5 > 0 and momentum10 > 0:
            rise_score += 25
        if momentum5 < 0 and momentum10 < 0:
            fall_score += 25
        if pullback_ok_rise:
            rise_score += 20
        if pullback_ok_fall:
            fall_score += 20
        if trigger_rise and bullish:
            rise_score += 20
        if trigger_fall and bearish:
            fall_score += 20
        rise_score += max(0, 10 - int(self.chop_score // 10))
        fall_score += max(0, 10 - int(self.chop_score // 10))
        self.edge_gap = round(abs(rise_score - fall_score) / 100.0 * 100.0, 1)
        if rise_score > fall_score:
            side = "RISE"
        elif fall_score > rise_score:
            side = "FALL"
        else:
            side = None

        # no-trade filtering
        if self.no_trade_filter:
            if self.chop_score >= 72:
                self.market_state = "CHOPPY"
                self.no_trade_reason = "Choppy market"
                confidence = min(confidence, threshold - 5)
                side = None
            elif self.chop_score >= 58:
                self.market_state = "MIXED"
                self.no_trade_reason = "Mixed flow"
            else:
                self.market_state = "CLEAN"

            if self.crash_risk == "HIGH":
                self.market_state = "VOLATILE"
                # keep signal possible in manual mode, but lower confidence
                confidence -= 8
                if confidence < threshold:
                    self.no_trade_reason = "Spike / crash risk high"

        self.confidence = round(max(0.0, min(99.9, confidence)), 1)

        # Decide signal state with Option-B style states
        prev_state = self.signal_state
        prev_side = self.signal_side

        # If no clear side, WAIT
        if not side:
            self.signal_state = "WAIT"
            self.signal_side = None
            if not self.no_trade_reason:
                self.no_trade_reason = "No clear edge"
            self._ready_tick = None
            self._take_now_started_at_tick = None
            self._late_until_tick = None
        else:
            self.signal_side = side
            # READY when trend+momentum align but below threshold OR trigger missing
            ready_cond = (self.confidence >= max(55.0, threshold - 10))
            take_cond = (self.confidence >= threshold)
            if take_cond:
                # On fresh TAKE NOW signal cycle
                sig = (side, round(self.confidence, 1), round(self.edge_gap, 1))
                fresh_take = (prev_state != "TAKE NOW" or prev_side != side)
                if fresh_take:
                    self.signal_cycle_id += 1
                    self._last_signal_signature = sig
                    self._take_now_started_at_tick = self.tick_count
                    self._late_until_tick = self.tick_count + 4  # small reaction window
                # TAKE NOW first 2 ticks of window, then LATE
                if self._take_now_started_at_tick is not None and self.tick_count <= self._take_now_started_at_tick + 2:
                    self.signal_state = "TAKE NOW"
                    self.no_trade_reason = ""
                    self.market_state = "ENTRY WINDOW" if self.market_state == "CLEAN" else self.market_state
                elif self._late_until_tick is not None and self.tick_count <= self._late_until_tick:
                    self.signal_state = "LATE"
                    self.no_trade_reason = "Late entry window"
                    if self.market_state == "CLEAN":
                        self.market_state = "LATE WINDOW"
                else:
                    # signal aged out but still directional
                    self.signal_state = "READY"
                    self.no_trade_reason = "Setup still valid (waiting refresh)"
                    self._ready_tick = self.tick_count
            elif ready_cond:
                self.signal_state = "READY"
                self.no_trade_reason = "Setup forming"
                if self._ready_tick is None:
                    self._ready_tick = self.tick_count
                if self.market_state == "CLEAN":
                    self.market_state = "SETUP FORMING"
                self._take_now_started_at_tick = None
                self._late_until_tick = None
            else:
                self.signal_state = "WAIT"
                self.no_trade_reason = self.no_trade_reason or "Weak confidence"
                self._ready_tick = None
                self._take_now_started_at_tick = None
                self._late_until_tick = None

        # If signal fully resets, allow next cycle consumption
        if self.signal_state == "WAIT":
            # do not clear consumed cycle id here (signal_cycle_id increments on new TAKE)
            pass

    # -----------------------------
    # Auto/manual entry controls
    # -----------------------------
    def _cooldown_remaining(self):
        return max(0.0, float(self.cooldown_until or 0) - time.time())

    def _trade_block_reason(self):
        self.enforce_tp_sl()
        if self.risk_block_reason:
            return self.risk_block_reason
        if self.pending_trade_request:
            return "Trade request pending"
        if self.active_contract_id:
            return "Active trade running"
        if self._cooldown_remaining() > 0:
            return f"Cooldown {self._cooldown_remaining():.1f}s"
        return None

    def can_manual_enter(self):
        reason = self._trade_block_reason()
        if reason:
            return False, reason
        return True, "OK"

    def check_auto_trade_signal(self):
        if not self.auto_enabled:
            return None
        if self.mode != "AUTO":
            return None
        reason = self._trade_block_reason()
        if reason:
            return None
        # Only one trade per strong TAKE NOW signal cycle
        if self.signal_state != "TAKE NOW":
            return None
        if (self._consumed_signal_cycle_id is not None) and (self._consumed_signal_cycle_id == self.signal_cycle_id):
            return None
        if self.confidence < self.confidence_threshold:
            return None
        return {
            "profile": "UNCHAIN",
            "type": "ACCU",
            "mode": "AUTO",
            "exit_ticks": int(self.auto_exit_ticks),
            "confidence": float(self.confidence),
            "growth_rate": float(self.growth_rate),
        }

    def on_trade_request_sent(self, mode="AUTO", exit_ticks=5, manual=False, stake=None):
        self.pending_trade_request = True
        self.pending_trade_mode = str(mode).upper()
        self.pending_trade_exit_ticks = int(exit_ticks or (self.auto_exit_ticks if str(mode).upper() == "AUTO" else self.manual_exit_ticks))
        try:
            self.pending_trade_stake = float(stake) if stake is not None else self.pending_trade_stake
        except Exception:
            pass
        # Consume current TAKE NOW cycle (anti-spam)
        if self.signal_state == "TAKE NOW":
            self._consumed_signal_cycle_id = self.signal_cycle_id

    def on_contract_opened(self, contract_id, entry_tick_seq, mode, target_exit_ticks, symbol, stake=None):
        self.pending_trade_request = False
        self.active_contract_id = contract_id
        self.active_contract_open = True
        self.active_entry_tick_seq = int(entry_tick_seq or 0)
        self.active_entry_market_tick_counter = int(self.market_tick_counter or 0)
        self.active_entry_symbol = symbol
        self.active_mode = str(mode).upper()
        self.active_target_exit_ticks = int(target_exit_ticks or (self.auto_exit_ticks if self.active_mode == "AUTO" else self.manual_exit_ticks))
        try:
            self.active_stake_amount = float(stake) if stake is not None else self.pending_trade_stake
        except Exception:
            self.active_stake_amount = self.pending_trade_stake
        self.pending_trade_stake = None
        self.exit_requested = False
        self.exit_requested_reason = None
        self.open_contract_profit = None
        self.open_contract_sell_price = None
        self.open_contract_entry_spot = None
        self.open_contract_current_spot = None

    def on_open_contract(self, contract):
        try:
            cid = contract.get("contract_id")
            if self.active_contract_id and cid and int(cid) != int(self.active_contract_id):
                return
        except Exception:
            return
        try:
            self.open_contract_profit = self._to_float(contract.get("profit", 0.0), 0.0)
        except Exception:
            pass
        try:
            self.open_contract_sell_price = self._to_float(contract.get("sell_price", 0.0), 0.0)
        except Exception:
            pass
        try:
            self.open_contract_entry_spot = self._to_float(contract.get("entry_spot"), 0.0)
        except Exception:
            pass
        try:
            buy_price = contract.get("buy_price")
            if buy_price not in (None, ""):
                self.active_stake_amount = self._to_float(buy_price, self.active_stake_amount or 0.0)
        except Exception:
            pass
        try:
            self.open_contract_current_spot = self._to_float(contract.get("current_spot"), 0.0)
        except Exception:
            pass
        # If contract already sold/settled, final cleanup will happen in on_contract

    def current_trade_ticks_elapsed(self, current_tick_seq=None):
        if not self.active_contract_id:
            return 0
        # Prefer market tick counter (profile-local, exact for UNCHAIN stream)
        try:
            if self.active_entry_market_tick_counter is not None:
                return max(0, int(self.market_tick_counter) - int(self.active_entry_market_tick_counter))
        except Exception:
            pass
        if self.active_entry_tick_seq is None:
            return 0
        try:
            if current_tick_seq is None:
                current_tick_seq = self.tick_count
            return max(0, int(current_tick_seq) - int(self.active_entry_tick_seq))
        except Exception:
            return 0

    def _is_choppy_now(self):
        return self.chop_score >= 65 or self.market_state in ("CHOPPY", "VOLATILE", "MIXED")

    def should_request_exit(self, current_tick_seq):
        """Called from server on each main tick to decide if active UNCHAIN contract should be sold."""
        if not self.active_contract_id or not self.active_contract_open:
            return None
        if self.exit_requested:
            return None

        elapsed = self.current_trade_ticks_elapsed(current_tick_seq)
        target = int(self.active_target_exit_ticks or (self.auto_exit_ticks if self.active_mode == "AUTO" else self.manual_exit_ticks))
        mode = (self.active_mode or "AUTO").upper()

        # Auto mode: target 5 ticks, but early-exit before target if choppy
        if mode == "AUTO":
            if self.auto_early_exit and elapsed < target and self._is_choppy_now():
                return {"contract_id": self.active_contract_id, "reason": "choppy_early_exit", "elapsed": elapsed}
            if elapsed >= target:
                return {"contract_id": self.active_contract_id, "reason": "target_ticks_reached", "elapsed": elapsed}

        # Manual mode: exit at user ticks; optional early safety exit
        if mode == "MANUAL":
            if self.manual_allow_early_exit and elapsed < target and self.crash_risk == "HIGH" and self._is_choppy_now():
                return {"contract_id": self.active_contract_id, "reason": "manual_safety_early_exit", "elapsed": elapsed}
            if elapsed >= target:
                return {"contract_id": self.active_contract_id, "reason": "manual_target_ticks_reached", "elapsed": elapsed}

        return None

    def mark_exit_requested(self, reason="exit"):
        self.exit_requested = True
        self.exit_requested_reason = reason

    def on_contract(self, contract, balance):
        # Finalized contract result
        profit = self._to_float(contract.get("profit", 0.0), 0.0)
        sold = self._to_float(contract.get("sell_price", 0.0), 0.0)
        buy_price = self._to_float(contract.get("buy_price", 0.0), 0.0)
        is_win = profit >= 0

        if is_win:
            self.total_wins += 1
            self.total_profit += max(0.0, profit)
            self.win_streak += 1
            self.loss_streak = 0
        else:
            self.total_losses += 1
            self.total_loss += abs(profit)
            self.loss_streak += 1
            self.win_streak = 0

        self.session_profit += profit
        self.last_result = "WIN" if is_win else "LOSS"
        self.last_result_time = self.now_time()

        # adaptive cooldown
        cd = float(self.cooldown_sec)
        if self.adaptive_cooldown:
            if is_win:
                cd = max(6.0, cd - 2.0)
            else:
                cd = min(25.0, cd + (4.0 if self.loss_streak <= 1 else 7.0))
        self.cooldown_until = time.time() + cd

        ticks_elapsed_final = self.current_trade_ticks_elapsed()
        self.last_trade_entry = {
            "profile": "UNCHAIN",
            "type": f"ACCU {self.active_mode or 'AUTO'}",
            "stake": (buy_price if buy_price else self.active_stake_amount),
            "symbol": self.active_entry_symbol or self.last_symbol,
            "time": self.now_time(),
            "profit": round(profit, 2),
            "result": "WIN" if is_win else "LOSS",
            "contract_id": contract.get("contract_id"),
            "exit_reason": self.exit_requested_reason or ("auto" if (self.active_mode or "AUTO") == "AUTO" else "manual"),
            "ticks_elapsed": ticks_elapsed_final,
        }
        self.trade_history.append(self.last_trade_entry)

        # Clear active trade
        self.pending_trade_request = False
        self.pending_trade_mode = None
        self.pending_trade_exit_ticks = None
        self.active_contract_id = None
        self.active_contract_open = False
        self.active_entry_tick_seq = None
        self.active_entry_market_tick_counter = None
        self.active_entry_symbol = None
        self.active_mode = None
        self.active_target_exit_ticks = None
        self.active_stake_amount = None
        self.pending_trade_stake = None
        self.exit_requested = False
        self.exit_requested_reason = None
        self.open_contract_profit = None
        self.open_contract_sell_price = None
        self.open_contract_entry_spot = None
        self.open_contract_current_spot = None

    def get_last_trade_entry(self):
        return self.last_trade_entry

    def reset_tick_analysis(self):
        # preserve settings and session/risk controls
        keep = {
            "auto_enabled": self.auto_enabled,
            "mode": self.mode,
            "confidence_threshold": self.confidence_threshold,
            "manual_exit_ticks": self.manual_exit_ticks,
            "auto_exit_ticks": self.auto_exit_ticks,
            "growth_rate": self.growth_rate,
            "cooldown_sec": self.cooldown_sec,
            "adaptive_cooldown": self.adaptive_cooldown,
            "tp": self.tp,
            "sl": self.sl,
            "auto_sl": self.auto_sl,
            "session_profit": self.session_profit,
            "trade_history": list(self.trade_history),
            "total_wins": self.total_wins,
            "total_losses": self.total_losses,
            "total_profit": self.total_profit,
            "total_loss": self.total_loss,
            "last_trade_entry": self.last_trade_entry,
            "cooldown_until": self.cooldown_until,
            "loss_streak": self.loss_streak,
            "win_streak": self.win_streak,
            "last_result": self.last_result,
            "last_result_time": self.last_result_time,
            "signal_strength": self.signal_strength,
            "auto_early_exit": self.auto_early_exit,
            "manual_allow_early_exit": self.manual_allow_early_exit,
            "pending_trade_request": self.pending_trade_request,
            "pending_trade_mode": self.pending_trade_mode,
            "pending_trade_exit_ticks": self.pending_trade_exit_ticks,
            "pending_trade_stake": self.pending_trade_stake,
            "active_contract_id": self.active_contract_id,
            "active_contract_open": self.active_contract_open,
            "active_entry_tick_seq": self.active_entry_tick_seq,
            "active_entry_market_tick_counter": self.active_entry_market_tick_counter,
            "active_entry_symbol": self.active_entry_symbol,
            "active_mode": self.active_mode,
            "active_target_exit_ticks": self.active_target_exit_ticks,
            "active_stake_amount": self.active_stake_amount,
            "exit_requested": self.exit_requested,
            "exit_requested_reason": self.exit_requested_reason,
        }
        self.reset()
        for k, v in keep.items():
            setattr(self, k, v)


    def _duration_lookback(self, duration=5, duration_unit="t"):
        try:
            duration = int(duration or 5)
        except Exception:
            duration = 5
        unit = str(duration_unit or "t").lower().strip()
        if unit == "m":
            return max(18, min(60, duration * 6))
        if unit == "s":
            return max(10, min(40, (duration // 2) + 8))
        return max(8, min(32, duration * 2))

    def get_bias_payload(self, config=None):
        """
        Display-only Higher/Lower analyzer.

        This leaves the main UNCHAIN strategy intact and simply scores recent
        movement plus the user's current Higher/Lower setup so the UI can show:
        - FAVORS HIGHER / FAVORS LOWER / NEUTRAL
        - Higher %
        - Lower %
        - Strength
        - Reason chips
        """
        config = config or {}
        duration = config.get("duration", getattr(self, "manual_exit_ticks", 5))
        duration_unit = config.get("duration_unit", "t")
        lookback = self._duration_lookback(duration, duration_unit)

        prices = list(self.price_history)
        if len(prices) < max(8, min(lookback, 10)):
            need = max(8, min(lookback, 10))
            return {
                "status": "LOADING ANALYZER…",
                "higher_pct": 50.0,
                "lower_pct": 50.0,
                "strength": "Building",
                "reasons": [
                    f"Need more ticks ({len(prices)}/{need})",
                    "Waiting for clearer flow",
                ],
                "lookback": min(len(prices), lookback),
                "summary": "Gathering enough recent ticks to score Higher vs Lower.",
                "updated_at": self.now_time(),
            }

        window = prices[-lookback:]
        deltas = [window[i] - window[i - 1] for i in range(1, len(window))]
        if not deltas:
            deltas = [0.0]

        up_count = sum(1 for d in deltas if d > 0)
        down_count = sum(1 for d in deltas if d < 0)
        flat_count = max(0, len(deltas) - up_count - down_count)

        recent_span = min(4, len(window) - 1)
        recent_move = window[-1] - window[-1 - recent_span] if recent_span > 0 else 0.0
        net_move = window[-1] - window[0]
        avg_abs = sum(abs(d) for d in deltas) / max(1, len(deltas))
        gross_move = sum(abs(d) for d in deltas)
        scale = max(avg_abs, 1e-9)

        trend_norm = max(-1.0, min(1.0, net_move / (scale * max(2.0, len(deltas) / 3.0))))
        flow_norm = max(-1.0, min(1.0, (up_count - down_count) / max(1.0, len(deltas))))
        recent_norm = max(-1.0, min(1.0, recent_move / (scale * max(1.5, recent_span or 1))))

        higher_barrier = self._to_float(config.get("higher_barrier", 0.0), 0.0)
        lower_barrier = self._to_float(config.get("lower_barrier", 0.0), 0.0)
        barrier_scale = max(scale * max(2.0, len(deltas) / 4.0), 1e-9)

        # Easier HIGHER = barrier lower/negative. Easier LOWER = barrier higher/positive.
        higher_ease = max(-1.0, min(1.0, -higher_barrier / barrier_scale))
        lower_ease = max(-1.0, min(1.0, lower_barrier / barrier_scale))
        barrier_norm = max(-1.0, min(1.0, (higher_ease - lower_ease) / 2.0))

        # Reuse the existing UNCHAIN analysis gently, without letting it override the new tool.
        structural_norm = 0.0
        if str(self.bias).upper() == "BULLISH":
            structural_norm += 0.35
        elif str(self.bias).upper() == "BEARISH":
            structural_norm -= 0.35

        if str(self.signal_side).upper() == "RISE":
            structural_norm += max(0.10, min(0.35, (float(self.confidence or 0.0) - 50.0) / 100.0))
        elif str(self.signal_side).upper() == "FALL":
            structural_norm -= max(0.10, min(0.35, (float(self.confidence or 0.0) - 50.0) / 100.0))
        structural_norm = max(-1.0, min(1.0, structural_norm))

        combined = (
            0.34 * trend_norm
            + 0.22 * flow_norm
            + 0.16 * recent_norm
            + 0.12 * barrier_norm
            + 0.16 * structural_norm
        )
        combined = max(-1.0, min(1.0, combined))

        # Penalize noisy / choppy conditions so the analyzer can go neutral more often.
        chop_penalty = min(0.18, max(0.0, (float(self.chop_score or 0.0) - 45.0) / 250.0))
        combined = max(-1.0, min(1.0, combined * (1.0 - chop_penalty)))

        higher_pct = round(max(5.0, min(95.0, 50.0 + combined * 35.0)), 1)
        lower_pct = round(100.0 - higher_pct, 1)
        edge = abs(higher_pct - 50.0)

        if edge >= 18:
            strength = "Strong"
        elif edge >= 10:
            strength = "Medium"
        else:
            strength = "Weak"

        if edge < 4:
            status = "NEUTRAL / WAIT"
        elif higher_pct > lower_pct:
            status = "FAVORS HIGHER"
        else:
            status = "FAVORS LOWER"

        reasons = []
        if abs(net_move) <= scale * 1.15 and abs(recent_move) <= scale * 1.0:
            reasons.append("market flat")
        else:
            if trend_norm > 0.22:
                reasons.append("short trend up")
            elif trend_norm < -0.22:
                reasons.append("short trend down")

            if flow_norm > 0.12:
                reasons.append("more upticks")
            elif flow_norm < -0.12:
                reasons.append("more downticks")

            if recent_norm > 0.22:
                reasons.append("recent push up")
            elif recent_norm < -0.22:
                reasons.append("recent push down")

        if str(self.market_state).upper() in ("CHOPPY", "VOLATILE", "MIXED"):
            reasons.append(str(self.market_state).lower())

        if str(self.signal_side).upper() == "RISE" and float(self.confidence or 0.0) >= 60:
            reasons.append("unchain rise signal")
        elif str(self.signal_side).upper() == "FALL" and float(self.confidence or 0.0) >= 60:
            reasons.append("unchain fall signal")

        if barrier_norm > 0.18:
            reasons.append("higher setup easier")
        elif barrier_norm < -0.18:
            reasons.append("lower setup easier")

        if flat_count >= max(2, len(deltas) // 3):
            reasons.append("slow tape")

        if not reasons:
            reasons = ["balanced flow", "wait for cleaner move"]

        return {
            "status": status,
            "higher_pct": higher_pct,
            "lower_pct": lower_pct,
            "strength": strength,
            "reasons": reasons[:4],
            "lookback": len(window),
            "summary": f"Based on the latest {len(window)} ticks and your current UNCHAIN duration/barriers.",
            "updated_at": self.now_time(),
        }

    # -----------------------------
    # UI / stats payloads
    # -----------------------------
    def _avg_crash_interval(self):
        if not self.crash_intervals:
            return None
        return round(sum(self.crash_intervals) / len(self.crash_intervals), 1)

    def _status_label(self):
        if self.active_contract_id:
            if self.exit_requested:
                return "BREAK / EXITING"
            if (self.active_mode or "").upper() == "AUTO":
                return "CHAIN ACTIVE"
            return "CHAIN ACTIVE (MANUAL EXIT)"
        if self._cooldown_remaining() > 0:
            return "BREAK / COOLING"
        if self.signal_state == "TAKE NOW":
            return "UNCHAIN READY"
        if self.signal_state == "READY":
            return "CHAIN FORMING"
        if self.market_state in ("CHOPPY", "VOLATILE"):
            return "SAFE MODE"
        return "IDLE"

    def get_ui_payload(self):
        active_ticks_elapsed = None
        if self.active_contract_id:
            try:
                active_ticks_elapsed = int(self.current_trade_ticks_elapsed())
            except Exception:
                active_ticks_elapsed = None
        progress_ticks_display = active_ticks_elapsed
        try:
            if progress_ticks_display is not None and self.active_target_exit_ticks and self.exit_requested:
                if int(progress_ticks_display) < int(self.active_target_exit_ticks):
                    progress_ticks_display = int(self.active_target_exit_ticks)
        except Exception:
            pass
        market_ticks_display = int(self.market_tick_counter)
        ticks_since_crash_display = None
        try:
            if self.ticks_since_last_crash is not None:
                ticks_since_crash_display = int(self.ticks_since_last_crash)
        except Exception:
            ticks_since_crash_display = None

        active_ticks_remaining = None
        try:
            if active_ticks_elapsed is not None and self.active_target_exit_ticks:
                active_ticks_remaining = max(0, int(self.active_target_exit_ticks) - int(active_ticks_elapsed))
        except Exception:
            active_ticks_remaining = None

        active_growth_value_per_tick = None
        try:
            if self.active_stake_amount is not None:
                active_growth_value_per_tick = round(float(self.active_stake_amount) * float(self.growth_rate), 4)
        except Exception:
            active_growth_value_per_tick = None

        top_crashes = []
        for t_idx, dlt, px in list(self.recent_crash_points)[-5:][::-1]:
            top_crashes.append({
                "tick_index": int(t_idx),
                "delta": round(float(dlt), 8),
                "price": round(float(px), 6),
            })

        return {
            "profile": "UNCHAIN",
            "tick_count": int(self.tick_count),
            "unchain": {
                "status": self._status_label(),
                "mode": self.mode,
                "auto_enabled": bool(self.auto_enabled),
                "confidence": float(self.confidence),
                "confidence_threshold": float(self.confidence_threshold),
                "signal_state": self.signal_state,
                "signal_side": self.signal_side,
                "bias": self.bias,
                "higher_lower_bias": self.get_bias_payload({}),
                "hl_bias": self.get_bias_payload({}),
                "market_state": self.market_state,
                "no_trade_reason": self.no_trade_reason,
                "edge_gap": float(self.edge_gap),
                "chop_score": float(self.chop_score),
                "crash_risk": self.crash_risk,
                "cooldown_remaining_sec": round(self._cooldown_remaining(), 1),
                "growth_rate": float(self.growth_rate),
                "manual_exit_ticks": int(self.manual_exit_ticks),
                "auto_exit_ticks": int(self.auto_exit_ticks),
                "active_contract_id": self.active_contract_id,
                "active_mode": self.active_mode,
                "active_target_exit_ticks": self.active_target_exit_ticks,
                "active_ticks_elapsed": active_ticks_elapsed,
                "active_ticks_remaining": active_ticks_remaining,
                "active_tick_progress": (f"{progress_ticks_display}/{int(self.active_target_exit_ticks or 0)}" if (progress_ticks_display is not None and self.active_target_exit_ticks) else None),
                "active_symbol": self.active_entry_symbol or self.last_symbol,
                "active_stake": (None if self.active_stake_amount is None else float(self.active_stake_amount)),
                "pending_stake": (None if self.pending_trade_stake is None else float(self.pending_trade_stake)),
                "exit_requested": bool(self.exit_requested),
                "exit_requested_reason": self.exit_requested_reason,
                "open_profit": None if self.open_contract_profit is None else float(self.open_contract_profit),
                "projected_open_profit": (None if (active_ticks_elapsed is None or self.active_stake_amount is None) else round(float(self.active_stake_amount) * float(self.growth_rate) * max(0, int(active_ticks_elapsed)), 2)),
                "active_growth_value_per_tick": active_growth_value_per_tick,
                "open_current_spot": None if self.open_contract_current_spot is None else float(self.open_contract_current_spot),
                "open_entry_spot": None if self.open_contract_entry_spot is None else float(self.open_contract_entry_spot),
                "pending_trade_request": bool(self.pending_trade_request),
                "last_result": self.last_result,
                "last_result_time": self.last_result_time,
                "wins": int(self.total_wins),
                "losses": int(self.total_losses),
                "session_profit": round(float(self.session_profit), 2),
                "risk_block_reason": self.risk_block_reason,
                "signal_components": dict(self.signal_components),
                "tick_crash_stats": {
                    "market_ticks": int(market_ticks_display),
                    "market_ticks_total": int(market_ticks_display),
                    "ticks_since_last_crash": ticks_since_crash_display,
                    "crash_detected_recent": (False if ticks_since_crash_display is None else bool(ticks_since_crash_display <= 1)),
                    "last_crash_tick": (None if self.last_crash_cycle_ticks is None else int(self.last_crash_cycle_ticks)),
                    "avg_crash_interval": self._avg_crash_interval(),
                    "recent_crashes": top_crashes,
                },
            }
        }

    def get_stats_payload(self, balance, session_start_balance):
        net_pnl = None
        try:
            if session_start_balance is not None:
                net_pnl = round(float(balance) - float(session_start_balance), 2)
        except Exception:
            net_pnl = None
        return {
            "balance": float(balance or 0.0),
            "net_pnl": net_pnl,
            "wins": int(self.total_wins),
            "losses": int(self.total_losses),
            "session_profit": round(float(self.session_profit), 2),
            "profile_stats_label": "UNCHAIN",
            "auto_trade": bool(self.auto_enabled),
        }
