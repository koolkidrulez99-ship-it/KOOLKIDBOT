from collections import deque, Counter
from strategies.base import BaseStrategy
import time
import random


class KoolKidStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()

        # Confidence bars
        self.confidence_over1 = 0
        self.confidence_over2 = 0
        self.confidence_under8 = 0
        self.confidence_under9 = 0

        self.pattern_buffer = deque(maxlen=6)

        # AUTO MODES (INDEPENDENT)
        self.kidracks_auto = False
        self.koolkidspeed_auto = False
        self.koolluck_auto = False
        self.auto_dollar_auto = False

        # ==================== PATCH A: add new flags and settings ====================
        self.kidbagz_auto = False
        self.mpull_auto = False
        self.kidpairs_auto = False

        # MPull direction filter: BOTH (default) / OVER / UNDER
        self.mpull_mode = "BOTH"

        # kidPairs trades per signal (1 or 2)
        self.kidpairs_trades_per_signal = 1

        # AUTO SETTINGS (BARRIERS ONLY)
        self.kidracks_barrier = 5
        self.koolkidspeed_barrier = 5

        # Cooldowns (so modes don't spam)
        self.kidracks_last_trade_time = 0
        self.koolkidspeed_last_trade_time = 0
        self.koolluck_last_trade_time = 0
        self.auto_dollar_last_trade_time = 0

        # ==================== PATCH B: add state variables ====================
        self.kidbagz_last_trade_time = 0
        self.mpull_last_trade_time = 0
        self.kidpairs_cooldown_until = 0.0
        self.kidpairs_seq_active = False
        self.kidpairs_seq_tick = 0
        self.kidpairs_forced_signal = None

        # kidBagz💰🤑 state
        self.kidbagz_cluster_len = 6  # uses last 6 digits in 0–4 zone
        self.kidbagz_armed = False
        self.kidbagz_break_streak = 0

        # MPull💰🤫 state
        self.mpull_waiting_pullback = False
        self.mpull_dir = None  # "UP" or "DOWN"

        # ==================== NEW: kidGx / Barrier Analysis / AI / MPull ALL DIGITS ====================
        self.kidgx_auto = False
        self.kidgx_last_trade_time = 0.0
        self.kidgx_cooldown_seconds = 0.0
        self.ai_auto_trading = False
        self.ai_last_trade_time = 0.0
        self.ai_cooldown_seconds = 0.0

        self.barrier_analysis_running = False
        self.barrier_analysis_warm_target = 30
        self.barrier_analysis_warm_count = 0
        self.barrier_analysis_selected = "UNDER 9"

        self.barrier_analysis_defs = [
            ("OVER", 0), ("OVER", 1), ("OVER", 2), ("UNDER", 8), ("UNDER", 9)
        ]
        self.ai_extra_barrier_defs = [
            ("OVER", 3), ("OVER", 4), ("OVER", 5), ("UNDER", 6), ("UNDER", 7)
        ]
        self.barrier_analysis_windows = {}

        self.mpull_all_digits_auto = False
        self.mpull_all_digits_selected_digits = set()
        self.mpull_all_digits_last_trade_time = 0.0
        self.last_symbol = None

        # Over 3 Analysis bot state
        self.over3_analysis_auto = False
        self.over3_execution_barrier = 3
        self.over3_duration_ticks = 1
        self.over3_trade_active = False
        self.over3_consecutive_losses = 0
        self.over3_total_trades = 0
        self.over3_session_stopped = False
        self.over3_wait_fresh_setup = False
        self.over3_ticks_by_symbol = {}

        # Kid2vix auto: UNDER 2 + OVER 3 pair when digits 2/3 look cold
        self.kid2vix_auto = False
        self.kid2vix_last20_threshold = 4
        self.kid2vix_last5_threshold = 1
        self.kid2vix_repeat_pressure_threshold = 34.0
        self.kid2vix_over3_ratio = 0.70
        self.kid2vix_cooldown_after_loss = 5.0
        self.kid2vix_cycle_active = False
        self.kid2vix_open_contracts = 0
        self.kid2vix_cycle_profit = 0.0
        self.kid2vix_last_trade_time = 0.0
        self.kid2vix_cooldown_until = 0.0
        self.kid2vix_last_result = ""
        self.kid2vix_analysis = {
            "ready": False,
            "label": "SKIP",
            "reason_summary": "Waiting for live tick data...",
            "last20_count": 0,
            "last5_count": 0,
            "repeat_pressure_score": 0.0,
            "repeat_pressure_threshold": 34.0,
            "trade_ready": False,
            "cycle_active": False,
            "cooldown_remaining": 0.0,
            "ratio": {"over3": 0.70, "under2": 0.30},
        }

        # 5 second delay between trades (your request)
        self.cooldown_seconds = 5.0

        # minimum dominance difference for KoolKidspeed
        self.koolkidspeed_min_diff = 3.0

        # KOOLLuck sequences
        # Each sequence is a list of steps in order
        # type = OVER/UNDER, barrier = digit
        self.koolluck_sequences = [
            [  # 1) over 1, over 2, under 8, under 9
                {"type": "OVER", "barrier": 1},
                {"type": "OVER", "barrier": 2},
                {"type": "UNDER", "barrier": 8},
                {"type": "UNDER", "barrier": 9},
            ],
            [  # 2) over 2, over 1, over 3, under 9
                {"type": "OVER", "barrier": 2},
                {"type": "OVER", "barrier": 1},
                {"type": "OVER", "barrier": 3},
                {"type": "UNDER", "barrier": 9},
            ],
            [  # 3) over 0, over 2, under 9, over 1
                {"type": "OVER", "barrier": 0},
                {"type": "OVER", "barrier": 2},
                {"type": "UNDER", "barrier": 9},
                {"type": "OVER", "barrier": 1},
            ],
            [  # 4) under 8, under 7, over 2, under 9
                {"type": "UNDER", "barrier": 8},
                {"type": "UNDER", "barrier": 7},
                {"type": "OVER", "barrier": 2},
                {"type": "UNDER", "barrier": 9},
            ],
            [  # 5) under 8, over 2, under 7, over 5
                {"type": "UNDER", "barrier": 8},
                {"type": "OVER", "barrier": 2},
                {"type": "UNDER", "barrier": 7},
                {"type": "OVER", "barrier": 5},
            ],
        ]
        self.koolluck_current_sequence = None
        self.koolluck_step_index = 0
        self.koolluck_probability_threshold = 60.0
        self.koolluck_background_analysis = {
            "ready": False,
            "best_signal": None,
            "best_probability": 0.0,
            "candidates": [],
        }
        self.auto_dollar_analysis = {
            "ready": False,
            "sample_size": 0,
            "over4_wins": 0,
            "under5_wins": 0,
            "over4_win_rate": 0.0,
            "under5_win_rate": 0.0,
            "leading_side": None,
            "split": {"over4": 0.5, "under5": 0.5},
        }

    def reset(self):
        super().reset()

        self.confidence_over1 = 0
        self.confidence_over2 = 0
        self.confidence_under8 = 0
        self.confidence_under9 = 0

        self.pattern_buffer.clear()

        self.kidracks_auto = False
        self.koolkidspeed_auto = False
        self.koolluck_auto = False
        self.auto_dollar_auto = False
        self.kidbagz_auto = False
        self.mpull_auto = False
        self.kidpairs_auto = False

        self.kidracks_last_trade_time = 0
        self.koolkidspeed_last_trade_time = 0
        self.koolluck_last_trade_time = 0
        self.auto_dollar_last_trade_time = 0
        self.kidbagz_last_trade_time = 0
        self.mpull_last_trade_time = 0
        self.kidpairs_cooldown_until = 0.0
        self.kidpairs_seq_active = False
        self.kidpairs_seq_tick = 0
        self.kidpairs_forced_signal = None

        self.kidbagz_armed = False
        self.kidbagz_break_streak = 0
        self.mpull_waiting_pullback = False
        self.mpull_dir = None

        self.kidgx_auto = False
        self.kidgx_last_trade_time = 0.0
        self.ai_auto_trading = False
        self.ai_last_trade_time = 0.0

        self.barrier_analysis_running = False
        self.barrier_analysis_warm_count = 0
        self.barrier_analysis_selected = "UNDER 9"
        self.barrier_analysis_windows = {}

        self.mpull_all_digits_auto = False
        self.mpull_all_digits_selected_digits = set()
        self.mpull_all_digits_last_trade_time = 0.0
        self.last_symbol = None

        self.over3_analysis_auto = False
        self.over3_execution_barrier = 3
        self.over3_duration_ticks = 1
        self.over3_trade_active = False
        self.over3_consecutive_losses = 0
        self.over3_total_trades = 0
        self.over3_session_stopped = False
        self.over3_wait_fresh_setup = False
        self.over3_ticks_by_symbol = {}

        self.kid2vix_auto = False
        self.kid2vix_last20_threshold = 4
        self.kid2vix_last5_threshold = 1
        self.kid2vix_repeat_pressure_threshold = 34.0
        self.kid2vix_over3_ratio = 0.70
        self.kid2vix_cooldown_after_loss = 5.0
        self.kid2vix_cycle_active = False
        self.kid2vix_open_contracts = 0
        self.kid2vix_cycle_profit = 0.0
        self.kid2vix_last_trade_time = 0.0
        self.kid2vix_cooldown_until = 0.0
        self.kid2vix_last_result = ""
        self.kid2vix_analysis = {
            "ready": False,
            "label": "SKIP",
            "reason_summary": "Waiting for live tick data...",
            "last20_count": 0,
            "last5_count": 0,
            "repeat_pressure_score": 0.0,
            "repeat_pressure_threshold": 34.0,
            "trade_ready": False,
            "cycle_active": False,
            "cooldown_remaining": 0.0,
            "ratio": {"over3": 0.70, "under2": 0.30},
        }

        self.koolluck_current_sequence = None
        self.koolluck_step_index = 0
        self.koolluck_background_analysis = {
            "ready": False,
            "best_signal": None,
            "best_probability": 0.0,
            "candidates": [],
        }
        self.auto_dollar_analysis = {
            "ready": False,
            "sample_size": 0,
            "over4_wins": 0,
            "under5_wins": 0,
            "over4_win_rate": 0.0,
            "under5_win_rate": 0.0,
            "leading_side": None,
            "split": {"over4": 0.5, "under5": 0.5},
        }

    # ==============================
    # TOGGLES
    # ==============================
    def toggle_kidracks_auto(self):
        self.kidracks_auto = not self.kidracks_auto
        return self.kidracks_auto

    def toggle_koolkidspeed_auto(self):
        self.koolkidspeed_auto = not self.koolkidspeed_auto
        return self.koolkidspeed_auto

    def toggle_koolluck_auto(self):
        self.koolluck_auto = not self.koolluck_auto
        # reset sequence on toggle ON
        if self.koolluck_auto:
            self.koolluck_current_sequence = None
            self.koolluck_step_index = 0
        return self.koolluck_auto

    def toggle_auto_dollar_auto(self):
        self.auto_dollar_auto = not self.auto_dollar_auto
        return self.auto_dollar_auto

    # ==================== PATCH C: add toggles and setters ====================
    def toggle_kidbagz_auto(self):
        self.kidbagz_auto = not self.kidbagz_auto
        if self.kidbagz_auto:
            self.kidbagz_armed = False
            self.kidbagz_break_streak = 0
        return self.kidbagz_auto

    def toggle_mpull_auto(self):
        self.mpull_auto = not self.mpull_auto
        if self.mpull_auto:
            self.mpull_waiting_pullback = False
            self.mpull_dir = None
        return self.mpull_auto

    def toggle_kidpairs_auto(self):
        self.kidpairs_auto = not self.kidpairs_auto
        if self.kidpairs_auto:
            self.kidpairs_seq_active = False
            self.kidpairs_seq_tick = 0
            self.kidpairs_forced_signal = None
            self.kidpairs_cooldown_until = 0.0
        return self.kidpairs_auto

    def set_mpull_mode(self, mode: str):
        mode = (mode or "").upper().strip()
        if mode not in ("BOTH", "OVER", "UNDER"):
            mode = "BOTH"
        self.mpull_mode = mode
        return self.mpull_mode

    def set_kidpairs_trades_per_signal(self, n: int):
        try:
            n = int(n)
        except Exception:
            n = 1
        if n not in (1, 2):
            n = 1
        self.kidpairs_trades_per_signal = n
        return self.kidpairs_trades_per_signal


    def disable_all_autos(self):
        try:
            super().disable_all_autos()
        except Exception:
            pass
        self.kidgx_auto = False
        self.ai_auto_trading = False
        self.mpull_all_digits_auto = False
        self.over3_analysis_auto = False
        self.over3_trade_active = False
        self.auto_dollar_auto = False
        self.kid2vix_auto = False
        self.kid2vix_cycle_active = False
        self.kid2vix_open_contracts = 0

    # ==============================
    # NEW FEATURE TOGGLES / SETTINGS
    # ==============================
    def toggle_kidgx_auto(self):
        self.kidgx_auto = not self.kidgx_auto
        return self.kidgx_auto

    def toggle_ai_auto_trading(self):
        self.ai_auto_trading = not self.ai_auto_trading
        return self.ai_auto_trading

    def toggle_barrier_analysis(self):
        self.barrier_analysis_running = not self.barrier_analysis_running
        if self.barrier_analysis_running:
            self.barrier_analysis_warm_count = 0
            self.barrier_analysis_windows = {}
        return self.barrier_analysis_running

    def toggle_mpull_all_digits_auto(self):
        self.mpull_all_digits_auto = not self.mpull_all_digits_auto
        if self.mpull_all_digits_auto:
            self.mpull_auto = False
        return self.mpull_all_digits_auto

    def _reset_over3_analysis_session(self):
        self.over3_trade_active = False
        self.over3_consecutive_losses = 0
        self.over3_total_trades = 0
        self.over3_session_stopped = False
        self.over3_wait_fresh_setup = False

    def _normalize_over3_execution_barrier(self, barrier):
        try:
            value = int(barrier)
        except Exception:
            value = 3
        if value not in (1, 2, 3):
            value = 3
        return value

    def set_over3_analysis_barrier(self, barrier):
        self.over3_execution_barrier = self._normalize_over3_execution_barrier(barrier)
        return int(self.over3_execution_barrier)

    def toggle_over3_analysis_auto(self):
        self.over3_analysis_auto = not self.over3_analysis_auto
        if self.over3_analysis_auto:
            self._reset_over3_analysis_session()
        else:
            self.over3_trade_active = False
        return self.over3_analysis_auto

    def toggle_kid2vix_auto(self):
        self.kid2vix_auto = not self.kid2vix_auto
        if self.kid2vix_auto:
            self.kid2vix_cycle_active = False
            self.kid2vix_open_contracts = 0
            self.kid2vix_cycle_profit = 0.0
            self.kid2vix_cooldown_until = 0.0
            self.kid2vix_last_result = ""
        return self.kid2vix_auto

    def set_kid2vix_settings(
        self,
        *,
        last20_threshold=None,
        last5_threshold=None,
        repeat_pressure_threshold=None,
        over3_ratio=None,
        cooldown_after_loss=None,
    ):
        if last20_threshold is not None:
            try:
                self.kid2vix_last20_threshold = max(0, min(20, int(last20_threshold)))
            except Exception:
                pass
        if last5_threshold is not None:
            try:
                self.kid2vix_last5_threshold = max(0, min(5, int(last5_threshold)))
            except Exception:
                pass
        if repeat_pressure_threshold is not None:
            try:
                self.kid2vix_repeat_pressure_threshold = max(0.0, min(100.0, float(repeat_pressure_threshold)))
            except Exception:
                pass
        if over3_ratio is not None:
            try:
                ratio = float(over3_ratio)
                if ratio > 1.0:
                    ratio = ratio / 100.0
                self.kid2vix_over3_ratio = max(0.05, min(0.95, ratio))
            except Exception:
                pass
        if cooldown_after_loss is not None:
            try:
                self.kid2vix_cooldown_after_loss = max(0.0, min(120.0, float(cooldown_after_loss)))
            except Exception:
                pass
        return {
            "last20_threshold": int(self.kid2vix_last20_threshold),
            "last5_threshold": int(self.kid2vix_last5_threshold),
            "repeat_pressure_threshold": float(self.kid2vix_repeat_pressure_threshold),
            "over3_ratio": float(self.kid2vix_over3_ratio),
            "cooldown_after_loss": float(self.kid2vix_cooldown_after_loss),
        }

    def _is_high_digit(self, digit):
        try:
            return int(digit) >= 4
        except Exception:
            return False

    def _over3_symbol_key(self, symbol):
        sym = str(symbol or "").upper().strip()
        return sym or ""

    def _over3_counts(self, symbol=None):
        sym = self._over3_symbol_key(symbol or getattr(self, "last_symbol", ""))
        if sym:
            ticks = list((self.over3_ticks_by_symbol or {}).get(sym) or [])
        else:
            ticks = list(self.tick_digits or [])
        last100 = ticks[-100:]
        last10 = ticks[-10:]
        high100 = sum(1 for d in last100 if self._is_high_digit(d))
        high10 = sum(1 for d in last10 if self._is_high_digit(d))
        streak = 0
        for d in reversed(last100):
            if self._is_high_digit(d):
                streak += 1
            else:
                break
        return {
            "sample100": len(last100),
            "sample10": len(last10),
            "high_count_100": int(high100),
            "high_count_10": int(high10),
            "current_high_streak": int(streak),
        }

    def get_over3_analysis_state(self):
        symbol = self._over3_symbol_key(getattr(self, "last_symbol", ""))
        counts = self._over3_counts(symbol=symbol)
        entry_conditions = bool(
            counts["sample100"] >= 100
            and counts["sample10"] >= 10
            and counts["high_count_100"] >= 58
            and counts["high_count_10"] >= 6
            and counts["current_high_streak"] < 6
        )
        symbol_ok = bool(symbol)
        duration_ticks = 2 if int(counts["high_count_100"]) >= 64 else int(getattr(self, "over3_duration_ticks", 1) or 1)
        duration_ticks = 1 if duration_ticks not in (1, 2) else duration_ticks
        return {
            "symbol_ok": bool(symbol_ok),
            "symbol": symbol,
            "analysis_barrier": 3,
            "selected_barrier": int(self._normalize_over3_execution_barrier(getattr(self, "over3_execution_barrier", 3))),
            "duration_ticks": int(duration_ticks),
            "trade_active": bool(self.over3_trade_active),
            "consecutive_losses": int(self.over3_consecutive_losses),
            "total_trades": int(self.over3_total_trades),
            "session_stopped": bool(self.over3_session_stopped),
            "wait_fresh_setup": bool(self.over3_wait_fresh_setup),
            "entry_conditions_ready": bool(entry_conditions),
            **counts,
        }

    def check_over3_analysis_signal(self):
        if not bool(getattr(self, "over3_analysis_auto", False)):
            return None

        s = self.get_over3_analysis_state()
        if not s["symbol_ok"] or s["session_stopped"] or s["trade_active"]:
            return None

        if s["consecutive_losses"] >= 2 or s["total_trades"] >= 5:
            self.over3_session_stopped = True
            return None

        setup_ready = bool(s["entry_conditions_ready"])
        if self.over3_wait_fresh_setup:
            if not setup_ready:
                self.over3_wait_fresh_setup = False
            return None

        if not setup_ready:
            return None

        duration_ticks = int(s.get("duration_ticks", 1) or 1)
        if duration_ticks not in (1, 2):
            duration_ticks = 1
        symbol = self._over3_symbol_key(s.get("symbol") or getattr(self, "last_symbol", ""))
        if not symbol:
            return None
        return {
            "mode": "OVER3_ANALYSIS",
            "type": "OVER",
            "barrier": int(self._normalize_over3_execution_barrier(getattr(self, "over3_execution_barrier", 3))),
            "duration": duration_ticks,
            "duration_unit": "t",
            "symbol": symbol,
        }

    def set_mpull_all_digits_selected_digits(self, digits):
        cleaned = set()
        for d in (digits or []):
            try:
                di = int(d)
            except Exception:
                continue
            if 0 <= di <= 9:
                cleaned.add(di)
        self.mpull_all_digits_selected_digits = cleaned
        return sorted(cleaned)

    def select_barrier_analysis_barrier(self, key: str):
        k = str(key or '').upper().strip()
        valid = {self._barrier_key(t, b) for (t, b) in self.barrier_analysis_defs}
        if k in valid:
            self.barrier_analysis_selected = k
        return self.barrier_analysis_selected

    def _barrier_key(self, t, b):
        return f"{str(t).upper()} {int(b)}"

    def _ensure_barrier_analysis_windows(self):
        if self.barrier_analysis_windows:
            return
        for t, b in list(self.barrier_analysis_defs) + list(self.ai_extra_barrier_defs):
            self.barrier_analysis_windows[self._barrier_key(t, b)] = deque(maxlen=int(self.barrier_analysis_warm_target or 30))

    def _eval_sim_win(self, t, barrier, digit):
        try:
            d = int(digit); b = int(barrier)
        except Exception:
            return 0
        t = str(t).upper()
        if t == 'OVER':
            return 1 if d > b else 0
        if t == 'UNDER':
            return 1 if d < b else 0
        return 0

    def _record_barrier_analysis_tick(self, digit):
        if not getattr(self, 'barrier_analysis_running', False):
            return
        self._ensure_barrier_analysis_windows()
        if self.barrier_analysis_warm_count < int(self.barrier_analysis_warm_target or 30):
            self.barrier_analysis_warm_count += 1
        for key, winq in self.barrier_analysis_windows.items():
            try:
                t, btxt = key.split(); b = int(btxt)
            except Exception:
                continue
            winq.append(self._eval_sim_win(t, b, digit))

    def _analysis_pct(self, key):
        q = (self.barrier_analysis_windows or {}).get(key)
        if not q:
            return 0.0
        return round((sum(q) / max(1, len(q))) * 100.0, 1)

    def _barrier_analysis_ready(self):
        return bool(getattr(self, 'barrier_analysis_running', False) and int(getattr(self, 'barrier_analysis_warm_count', 0)) >= int(getattr(self, 'barrier_analysis_warm_target', 30)))

    def _get_barrier_analysis_rows(self):
        rows = []
        for t, b in self.barrier_analysis_defs:
            key = self._barrier_key(t, b)
            pct = self._analysis_pct(key) if self._barrier_analysis_ready() else None
            rows.append({
                'key': key,
                'type': t,
                'barrier': int(b),
                'wins_pct': pct,
                'confidence_pct': pct,
                'sample': len((self.barrier_analysis_windows or {}).get(key, []))
            })
        return rows

    def _get_barrier_analysis_recommended(self):
        if not self._barrier_analysis_ready():
            return None
        best = None
        for row in self._get_barrier_analysis_rows():
            pct = row.get('wins_pct')
            if pct is None:
                continue
            if best is None or float(pct) > float(best.get('wins_pct', -1)):
                best = row
        return best

    def _get_ai_candidate_defs(self):
        return list(self.barrier_analysis_defs) + list(self.ai_extra_barrier_defs)

    def _pick_best_ai_candidate(self):
        if not self._barrier_analysis_ready():
            return None
        self._ensure_barrier_analysis_windows()
        best = None
        for t, b in self._get_ai_candidate_defs():
            key = self._barrier_key(t, b)
            pct = self._analysis_pct(key)
            item = {'key': key, 'type': t, 'barrier': int(b), 'wins_pct': pct}
            if best is None or float(item['wins_pct']) > float(best['wins_pct']):
                best = item
        return best

    def can_trade_kidgx(self):
        return (time.time() - float(getattr(self, 'kidgx_last_trade_time', 0.0))) >= float(getattr(self, 'kidgx_cooldown_seconds', 0.0))

    def mark_kidgx_trade(self):
        self.kidgx_last_trade_time = time.time()

    def can_trade_ai_auto(self):
        return (time.time() - float(getattr(self, 'ai_last_trade_time', 0.0))) >= float(getattr(self, 'ai_cooldown_seconds', 0.0))

    def mark_ai_auto_trade(self):
        self.ai_last_trade_time = time.time()

    def can_trade_mpull_all_digits(self):
        return (time.time() - float(getattr(self, 'mpull_all_digits_last_trade_time', 0.0))) >= float(getattr(self, 'cooldown_seconds', 5.0))

    def mark_mpull_all_digits_trade(self):
        self.mpull_all_digits_last_trade_time = time.time()

    # ==============================
    # CONFIDENCE BARS
    # ==============================
    def update_confidence_bars(self):
        if len(self.pattern_buffer) < 3:
            return

        last = list(self.pattern_buffer)

        # OVER 1 confidence
        if 0 in last[-4:] and 1 in last[-4:]:
            self.confidence_over1 = min(100, self.confidence_over1 + 8)
        else:
            self.confidence_over1 = max(0, self.confidence_over1 - 2)

        # OVER 2 confidence
        if 2 in last[-4:]:
            self.confidence_over2 = min(100, self.confidence_over2 + 6)
        else:
            self.confidence_over2 = max(0, self.confidence_over2 - 2)

        # UNDER 9 confidence
        if 9 in last[-3:]:
            self.confidence_under9 = min(100, self.confidence_under9 + 10)
        else:
            self.confidence_under9 = max(0, self.confidence_under9 - 3)

        # UNDER 8 confidence
        if 9 in last[-4:] and 8 in last[-4:]:
            self.confidence_under8 = min(100, self.confidence_under8 + 10)
        else:
            self.confidence_under8 = max(0, self.confidence_under8 - 3)

    def on_tick(self, tick, digit):
        super().on_tick(tick, digit)
        try:
            self.last_symbol = tick.get("symbol")
        except Exception:
            pass
        try:
            symbol = self._over3_symbol_key(getattr(self, "last_symbol", ""))
            if symbol and digit is not None:
                buf = self.over3_ticks_by_symbol.get(symbol)
                if buf is None:
                    buf = deque(maxlen=100)
                    self.over3_ticks_by_symbol[symbol] = buf
                buf.append(int(digit))
        except Exception:
            pass

        self.pattern_buffer.append(digit)
        self.update_confidence_bars()
        self._record_barrier_analysis_tick(digit)
        self._refresh_koolluck_background_analysis()
        self._refresh_auto_dollar_analysis()
        self._refresh_kid2vix_analysis()

    def on_auto_trade_sent(self, signal):
        mode = str((signal or {}).get("mode") or "").upper().strip()
        if mode == "OVER3_ANALYSIS":
            self.over3_trade_active = True
            return
        if mode == "KID2VIX":
            self.kid2vix_cycle_active = True
            self.kid2vix_open_contracts = int(self.kid2vix_open_contracts or 0) + 1
            self.kid2vix_last_trade_time = time.time()

    def on_auto_trade_failed(self, signal, _reason=None):
        mode = str((signal or {}).get("mode") or "").upper().strip()
        if mode == "OVER3_ANALYSIS":
            self.over3_trade_active = False
            return

    def on_contract_settled(self, contract, meta=None):
        mode = str(((meta or {}).get("mode") or "").upper().strip())
        if mode == "KID2VIX":
            try:
                profit = float((contract or {}).get("profit", 0) or 0)
            except Exception:
                profit = 0.0
            self.kid2vix_cycle_profit = float(self.kid2vix_cycle_profit or 0.0) + profit
            self.kid2vix_open_contracts = max(0, int(self.kid2vix_open_contracts or 0) - 1)
            if self.kid2vix_open_contracts <= 0:
                self.kid2vix_cycle_active = False
                cycle_profit = float(self.kid2vix_cycle_profit or 0.0)
                if cycle_profit > 0:
                    self.kid2vix_last_result = "WIN"
                    self.kid2vix_cooldown_until = 0.0
                elif cycle_profit < 0:
                    self.kid2vix_last_result = "LOSS"
                    self.kid2vix_cooldown_until = time.time() + float(self.kid2vix_cooldown_after_loss or 0.0)
                else:
                    self.kid2vix_last_result = "FLAT"
                    self.kid2vix_cooldown_until = 0.0
                self.kid2vix_cycle_profit = 0.0
            self._refresh_kid2vix_analysis()
            return
        if mode != "OVER3_ANALYSIS":
            return
        try:
            profit = float((contract or {}).get("profit", 0) or 0)
        except Exception:
            profit = 0.0
        self.over3_trade_active = False
        self.over3_total_trades = int(self.over3_total_trades) + 1
        if profit > 0:
            self.over3_consecutive_losses = 0
        else:
            self.over3_consecutive_losses = int(self.over3_consecutive_losses) + 1
        self.over3_wait_fresh_setup = True
        if int(self.over3_consecutive_losses) >= 2 or int(self.over3_total_trades) >= 5:
            self.over3_session_stopped = True

    def _kid2vix_stake_split(self, total_stake):
        try:
            total = float(total_stake or 0.0)
        except Exception:
            total = 0.0
        total = max(0.0, total)
        over_ratio = max(0.05, min(0.95, float(getattr(self, "kid2vix_over3_ratio", 0.70) or 0.70)))
        over_stake = round(total * over_ratio, 2)
        under_stake = round(max(0.0, total - over_stake), 2)
        return {
            "total": round(total, 2),
            "over3_ratio": over_ratio,
            "under2_ratio": round(max(0.0, 1.0 - over_ratio), 4),
            "over3_stake": over_stake,
            "under2_stake": under_stake,
        }

    def _kid2vix_max_cluster_len(self, digits):
        best = 0
        run = 0
        for digit in digits or []:
            if int(digit) in (2, 3):
                run += 1
                if run > best:
                    best = run
            else:
                run = 0
        return int(best)

    def _refresh_kid2vix_analysis(self):
        digits = [int(d) for d in list(getattr(self, "tick_digits", [])) if d is not None]
        last20 = digits[-20:]
        last5 = digits[-5:]
        prev5 = digits[-10:-5]
        count20 = sum(1 for d in last20 if d in (2, 3))
        count5 = sum(1 for d in last5 if d in (2, 3))
        prev5_count = sum(1 for d in prev5 if d in (2, 3))
        last_hit = bool(digits and digits[-1] in (2, 3))
        second_hit = bool(len(digits) >= 2 and digits[-2] in (2, 3))
        back_to_back = bool(last_hit and second_hit)
        repeated_same = bool(len(digits) >= 2 and digits[-1] == digits[-2] and digits[-1] in (2, 3))
        cluster_len = self._kid2vix_max_cluster_len(last5)
        unique_other_digits = len({d for d in last5 if d not in (2, 3)})
        spread_support = unique_other_digits >= 3
        heating_up = bool(
            count5 > max(int(getattr(self, "kid2vix_last5_threshold", 1) or 1), prev5_count)
            or (cluster_len >= 2 and count5 >= 2)
        )

        pressure = 0.0
        if last_hit:
            pressure += 16.0
        if second_hit:
            pressure += 6.0
        if back_to_back:
            pressure += 10.0
        if repeated_same:
            pressure += 8.0
        pressure += float(count5 * 7.0)
        pressure += float(max(0, count20 - int(getattr(self, "kid2vix_last20_threshold", 4) or 4)) * 6.0)
        pressure += float(max(0, count5 - int(getattr(self, "kid2vix_last5_threshold", 1) or 1)) * 12.0)
        if heating_up:
            pressure += 8.0
        if count5 == 0:
            pressure -= 8.0
        if count20 <= max(0, int(getattr(self, "kid2vix_last20_threshold", 4) or 4) - 2):
            pressure -= 6.0
        pressure -= min(10.0, float(unique_other_digits) * 2.0)
        pressure = max(0.0, min(100.0, pressure))

        ready = len(last20) >= 20 and len(last5) >= 5
        threshold20 = int(getattr(self, "kid2vix_last20_threshold", 4) or 4)
        threshold5 = int(getattr(self, "kid2vix_last5_threshold", 1) or 1)
        pressure_threshold = float(getattr(self, "kid2vix_repeat_pressure_threshold", 34.0) or 34.0)
        cooldown_remaining = max(0.0, float(getattr(self, "kid2vix_cooldown_until", 0.0) or 0.0) - time.time())

        differ_support = bool(
            spread_support
            or count5 == 0
            or (last_hit and count5 == 1 and prev5_count == 0 and not repeated_same)
        )

        if not ready:
            label = "SKIP"
            reason = "Waiting for a full 20-tick digit sample."
        elif (
            count20 <= threshold20
            and count5 <= threshold5
            and pressure <= pressure_threshold
            and not heating_up
            and differ_support
        ):
            label = "SAFE"
            reason = "2/3 quiet • repeat pressure low • differ flow looks clean"
        elif (
            count20 > (threshold20 + 1)
            or count5 > (threshold5 + 1)
            or pressure > (pressure_threshold + 8.0)
            or (heating_up and count5 >= 2)
        ):
            label = "SKIP"
            reason = "2/3 too active or clustering is building."
        else:
            label = "RISKY"
            reason = "Mixed 2/3 pressure. Wait for a cleaner differ setup."

        split = self._kid2vix_stake_split(getattr(self, "current_auto_stake", 0.0))
        trade_ready = bool(
            ready
            and label == "SAFE"
            and not bool(getattr(self, "kid2vix_cycle_active", False))
            and cooldown_remaining <= 0.0
            and float(split["total"]) > 0.0
        )
        if bool(getattr(self, "kid2vix_cycle_active", False)):
            reason = "Trade cycle active • waiting for UNDER 2 + OVER 3 to settle"
        elif cooldown_remaining > 0.0:
            reason = f"Loss cooldown active • {cooldown_remaining:.1f}s left"

        self.kid2vix_analysis = {
            "ready": bool(ready),
            "label": str(label),
            "reason_summary": str(reason),
            "last20_count": int(count20),
            "last5_count": int(count5),
            "prev5_count": int(prev5_count),
            "repeat_pressure_score": round(float(pressure), 1),
            "repeat_pressure_threshold": round(float(pressure_threshold), 1),
            "trade_ready": bool(trade_ready),
            "cycle_active": bool(getattr(self, "kid2vix_cycle_active", False)),
            "open_contracts": int(getattr(self, "kid2vix_open_contracts", 0) or 0),
            "cooldown_remaining": round(float(cooldown_remaining), 1),
            "ratio": {
                "over3": round(float(split["over3_ratio"]), 4),
                "under2": round(float(split["under2_ratio"]), 4),
            },
            "ratio_pct": {
                "over3": round(float(split["over3_ratio"]) * 100.0, 1),
                "under2": round(float(split["under2_ratio"]) * 100.0, 1),
            },
            "stake_preview": {
                "total": round(float(split["total"]), 2),
                "over3": round(float(split["over3_stake"]), 2),
                "under2": round(float(split["under2_stake"]), 2),
            },
            "last_result": str(getattr(self, "kid2vix_last_result", "") or ""),
            "heating_up": bool(heating_up),
            "differ_support": bool(differ_support),
            "cluster_len": int(cluster_len),
            "last_hit_23": bool(last_hit),
            "back_to_back_23": bool(back_to_back),
            "repeated_same_digit": bool(repeated_same),
            "unique_other_digits": int(unique_other_digits),
            "settings": {
                "last20_threshold": int(threshold20),
                "last5_threshold": int(threshold5),
                "repeat_pressure_threshold": round(float(pressure_threshold), 1),
                "over3_ratio_pct": round(float(split["over3_ratio"]) * 100.0, 1),
                "cooldown_after_loss": round(float(getattr(self, "kid2vix_cooldown_after_loss", 5.0) or 5.0), 1),
            },
        }
        return self.kid2vix_analysis

    def check_kid2vix_signal(self):
        if not bool(getattr(self, "kid2vix_auto", False)):
            return None
        analysis = self._refresh_kid2vix_analysis()
        if not analysis or not bool(analysis.get("trade_ready")):
            return None
        split = self._kid2vix_stake_split(getattr(self, "current_auto_stake", 0.0))
        self.kid2vix_cycle_profit = 0.0
        return [
            {
                "mode": "KID2VIX",
                "type": "OVER",
                "barrier": 3,
                "stake": float(split["over3_stake"]),
                "duration": 1,
                "duration_unit": "t",
            },
            {
                "mode": "KID2VIX",
                "type": "UNDER",
                "barrier": 2,
                "stake": float(split["under2_stake"]),
                "duration": 1,
                "duration_unit": "t",
            },
        ]

    # ==============================
    # HELPERS
    # ==============================
    def sum_pct(self, start, end):
        """
        Sums digit percentages from start to end inclusive.
        Uses the 100-tick percentage map.
        """
        total = 0.0
        for i in range(start, end + 1):
            total += float(self.digit_percentages.get(i, 0.0))
        return total

    def can_trade_kidracks(self):
        return (time.time() - self.kidracks_last_trade_time) >= self.cooldown_seconds

    def can_trade_koolkidspeed(self):
        return (time.time() - self.koolkidspeed_last_trade_time) >= self.cooldown_seconds

    def can_trade_koolluck(self):
        return (time.time() - self.koolluck_last_trade_time) >= self.cooldown_seconds

    def can_trade_auto_dollar(self):
        return (time.time() - self.auto_dollar_last_trade_time) >= self.cooldown_seconds

    # ==================== PATCH D: add helpers ====================
    def can_trade_kidbagz(self):
        return (time.time() - self.kidbagz_last_trade_time) >= self.cooldown_seconds

    def can_trade_mpull(self):
        return (time.time() - self.mpull_last_trade_time) >= self.cooldown_seconds

    def kidpairs_in_cooldown(self):
        return time.time() < float(self.kidpairs_cooldown_until or 0.0)

    def mark_kidracks_trade(self):
        self.kidracks_last_trade_time = time.time()

    def mark_koolkidspeed_trade(self):
        self.koolkidspeed_last_trade_time = time.time()

    def mark_koolluck_trade(self):
        self.koolluck_last_trade_time = time.time()

    def mark_auto_dollar_trade(self):
        self.auto_dollar_last_trade_time = time.time()

    def mark_kidbagz_trade(self):
        self.kidbagz_last_trade_time = time.time()

    def mark_mpull_trade(self):
        self.mpull_last_trade_time = time.time()

    def _koolluck_candidate_defs(self):
        seen = set()
        ordered = []
        for seq in getattr(self, "koolluck_sequences", []) or []:
            for step in seq or []:
                try:
                    key = (str(step.get("type") or "").upper().strip(), int(step.get("barrier")))
                except Exception:
                    continue
                if key in seen:
                    continue
                seen.add(key)
                ordered.append({"type": key[0], "barrier": key[1]})
        return ordered

    def _get_live_tick_percentages(self):
        digits = [int(d) for d in list(getattr(self, "tick_digits", [])) if d is not None]
        if len(digits) < 100:
            return None, None
        counter = Counter(digits[-100:])
        counts = {digit: int(counter.get(digit, 0)) for digit in range(10)}
        percentages = {digit: (counts[digit] / 100.0) * 100.0 for digit in range(10)}
        return counts, percentages

    def _koolluck_strength_bands(self, contract_type, barrier):
        kind = str(contract_type or "").upper().strip()
        barrier = int(barrier)
        if kind == "OVER":
            bands = {
                0: (list(range(0, 2)), list(range(2, 10))),
                1: (list(range(0, 3)), list(range(3, 10))),
                2: (list(range(0, 4)), list(range(4, 10))),
                3: (list(range(0, 5)), list(range(5, 10))),
                5: (list(range(1, 7)), list(range(7, 10))),
            }
            return bands.get(
                barrier,
                (list(range(0, min(9, barrier + 1) + 1)), list(range(min(9, barrier + 2), 10))),
            )

        bands = {
            9: (list(range(8, 10)), list(range(0, 8))),
            8: (list(range(7, 10)), list(range(0, 7))),
            7: (list(range(6, 10)), list(range(0, 6))),
        }
        return bands.get(barrier, (list(range(max(0, barrier - 1), 10)), list(range(0, max(0, barrier - 1)))))

    def _score_koolluck_candidate(self, contract_type, barrier, counts, percentages):
        kind = str(contract_type or "").upper().strip()
        barrier = int(barrier)
        if kind == "OVER":
            losing_digits = list(range(0, barrier + 1))
            winning_digits = list(range(barrier + 1, 10))
        else:
            losing_digits = list(range(barrier, 10))
            winning_digits = list(range(0, barrier))

        if not losing_digits or not winning_digits:
            return None

        losing_pct = sum(float(percentages.get(d, 0.0)) for d in losing_digits)
        winning_pct = sum(float(percentages.get(d, 0.0)) for d in winning_digits)
        losing_avg_pct = losing_pct / max(1, len(losing_digits))
        losing_max_pct = max(float(percentages.get(d, 0.0)) for d in losing_digits)

        opposing_band, favorable_band = self._koolluck_strength_bands(kind, barrier)
        opposing_pct = sum(float(percentages.get(d, 0.0)) for d in opposing_band)
        favorable_pct = sum(float(percentages.get(d, 0.0)) for d in favorable_band)
        strength_diff = favorable_pct - opposing_pct
        if strength_diff <= 0:
            return {
                "type": kind,
                "barrier": barrier,
                "probability": 0.0,
                "qualified": False,
                "reason": "favorable side is not stronger",
            }

        rarity_score = max(0.0, min(100.0, 82.0 - (losing_avg_pct * 5.0) - (losing_max_pct * 1.5)))
        strength_score = max(0.0, min(100.0, 50.0 + (strength_diff * 2.8)))
        probability = (winning_pct * 0.68) + (rarity_score * 0.17) + (strength_score * 0.15)
        qualified = probability >= float(getattr(self, "koolluck_probability_threshold", 60.0))

        return {
            "type": kind,
            "barrier": barrier,
            "probability": round(probability, 2),
            "qualified": bool(qualified),
            "reason": "ok" if qualified else "probability below threshold",
            "winning_pct": round(winning_pct, 2),
            "losing_pct": round(losing_pct, 2),
            "losing_avg_pct": round(losing_avg_pct, 2),
            "favorable_pct": round(favorable_pct, 2),
            "opposing_pct": round(opposing_pct, 2),
            "strength_diff": round(strength_diff, 2),
        }

    def _refresh_koolluck_background_analysis(self):
        counts, percentages = self._get_live_tick_percentages()
        if not counts or not percentages:
            self.koolluck_background_analysis = {
                "ready": False,
                "best_signal": None,
                "best_probability": 0.0,
                "candidates": [],
            }
            return self.koolluck_background_analysis

        scored = []
        for candidate in self._koolluck_candidate_defs():
            row = self._score_koolluck_candidate(candidate.get("type"), candidate.get("barrier"), counts, percentages)
            if row:
                scored.append(row)

        scored.sort(
            key=lambda row: (
                float(row.get("probability", 0.0)),
                float(row.get("winning_pct", 0.0)),
                -float(row.get("losing_avg_pct", 100.0)),
                -int(row.get("barrier", 0)),
            ),
            reverse=True,
        )

        best = scored[0] if scored else None
        self.koolluck_background_analysis = {
            "ready": True,
            "best_signal": (
                {
                    "mode": "KOOLLUCK",
                    "type": str(best.get("type") or "").upper(),
                    "barrier": int(best.get("barrier", 0)),
                }
                if best and best.get("qualified")
                else None
            ),
            "best_probability": float(best.get("probability", 0.0)) if best else 0.0,
            "candidates": scored,
        }
        return self.koolluck_background_analysis

    def _refresh_auto_dollar_analysis(self):
        digits = list(getattr(self, "tick_digits", []) or [])
        sample = digits[-100:]
        sample_size = len(sample)
        if sample_size < 100:
            self.auto_dollar_analysis = {
                "ready": False,
                "sample_size": sample_size,
                "over4_wins": 0,
                "under5_wins": 0,
                "over4_win_rate": 0.0,
                "under5_win_rate": 0.0,
                "leading_side": None,
                "split": {"over4": 0.5, "under5": 0.5},
            }
            return self.auto_dollar_analysis

        over4_wins = sum(1 for digit in sample if int(digit) > 4)
        under5_wins = sum(1 for digit in sample if int(digit) < 5)
        over4_rate = (over4_wins / sample_size) * 100.0
        under5_rate = (under5_wins / sample_size) * 100.0

        if over4_wins > under5_wins:
            leading_side = "OVER4"
            split = {"over4": 0.6, "under5": 0.4}
        elif under5_wins > over4_wins:
            leading_side = "UNDER5"
            split = {"over4": 0.4, "under5": 0.6}
        else:
            leading_side = "TIE"
            split = {"over4": 0.5, "under5": 0.5}

        self.auto_dollar_analysis = {
            "ready": True,
            "sample_size": sample_size,
            "over4_wins": int(over4_wins),
            "under5_wins": int(under5_wins),
            "over4_win_rate": round(over4_rate, 2),
            "under5_win_rate": round(under5_rate, 2),
            "leading_side": leading_side,
            "split": {
                "over4": round(float(split["over4"]), 2),
                "under5": round(float(split["under5"]), 2),
            },
        }
        return self.auto_dollar_analysis

    def _resolve_auto_dollar_stakes(self, total_stake):
        try:
            total = round(float(total_stake or 0.0), 2)
        except Exception:
            total = 0.0
        if total < 0.70:
            return None

        split = (getattr(self, "auto_dollar_analysis", {}) or {}).get("split") or {"over4": 0.5, "under5": 0.5}
        over_ratio = float(split.get("over4", 0.5) or 0.5)
        under_ratio = float(split.get("under5", 0.5) or 0.5)

        over_stake = round(total * over_ratio, 2)
        under_stake = round(total * under_ratio, 2)
        min_side = 0.35

        if over_stake < min_side:
            over_stake = min_side
            under_stake = round(total - over_stake, 2)
        if under_stake < min_side:
            under_stake = min_side
            over_stake = round(total - under_stake, 2)
        if over_stake < min_side or under_stake < min_side:
            return None

        return {
            "over4": round(over_stake, 2),
            "under5": round(under_stake, 2),
        }

    def check_auto_dollar_signal(self):
        analysis = self._refresh_auto_dollar_analysis()
        if not self.auto_dollar_auto:
            return None
        if not analysis.get("ready"):
            return None

        stakes = self._resolve_auto_dollar_stakes(getattr(self, "current_auto_stake", 1.0))
        if not stakes:
            return None

        return [
            {"mode": "AUTO$", "type": "OVER", "barrier": 4, "stake": float(stakes["over4"])},
            {"mode": "AUTO$", "type": "UNDER", "barrier": 5, "stake": float(stakes["under5"])},
        ]

    # ==============================
    # KIDRACKS AUTO SIGNAL
    # ==============================
    def check_kidracks_signal(self):
        """
        KidRacks rules:

        - Wait until 100 ticks (percentages valid).
        - Uses self.kidracks_barrier selected from UI.
        - Barrier digit % must be < 10%.
        - Must wait until THAT digit prints (last_tick_digit == barrier).

        For barrier:
          0–4  → OVER
            * barrier 1: (0+1)% < 20%
            * barrier 2: (0+1+2)% < 25%
            * barrier 3,4: total(0–4) > total(5–9)
          6–9  → UNDER
            * barrier 8: (8+9)% < 20%
            * barrier 6,7: total(6–9) > total(0–4)
          5:
            * if total(0–4) < total(6–9) → UNDER 5
            * if total(6–9) < total(0–4) → OVER 5
        """
        if self.tick_count < 100:
            return None

        barrier = int(self.kidracks_barrier)

        # 1) barrier digit must be under 10%
        barrier_pct = float(self.digit_percentages.get(barrier, 0.0))
        if barrier_pct >= 10.0:
            return None

        # 2) only trade AFTER that digit actually prints
        if self.last_tick_digit != barrier:
            return None

        # Group percentages
        pct_0_1 = self.sum_pct(0, 1)
        pct_0_2 = self.sum_pct(0, 2)
        pct_0_4 = self.sum_pct(0, 4)
        pct_5_9 = self.sum_pct(5, 9)
        pct_6_9 = self.sum_pct(6, 9)
        pct_8_9 = self.sum_pct(8, 9)

        # ─────────────────────────────
        # 0–4  → OVER
        # ─────────────────────────────
        if barrier in [0, 1, 2, 3, 4]:

            # Over 1 → only if 0+1 combined < 20%
            if barrier == 1 and pct_0_1 >= 20.0:
                return None

            # Over 2 → only if 0+1+2 combined < 25%
            if barrier == 2 and pct_0_2 >= 25.0:
                return None

            # Over 3 / Over 4 → only if 0–4 has more % than 5–9
            if barrier in [3, 4] and pct_0_4 <= pct_5_9:
                return None

            return {
                "mode": "KIDRACKS",
                "type": "OVER",
                "barrier": barrier,
            }

        # ─────────────────────────────
        # 6–9  → UNDER
        # ─────────────────────────────
        if barrier in [6, 7, 8, 9]:

            # Under 8 → extra condition: 8+9 combined < 20%
            if barrier == 8 and pct_8_9 >= 20.0:
                return None

            # Under 6 / Under 7 → only if 6–9 > 0–4
            if barrier in [6, 7] and pct_6_9 <= pct_0_4:
                return None

            return {
                "mode": "KIDRACKS",
                "type": "UNDER",
                "barrier": barrier,
            }

        # ─────────────────────────────
        # Barrier 5 → OVER or UNDER
        # based on which side has LOWER %
        # ─────────────────────────────
        if barrier == 5:
            pct_0_4 = self.sum_pct(0, 4)
            pct_6_9 = self.sum_pct(6, 9)

            # Example you gave:
            # 0–4 = 30, 6–9 = 40 → 0–4 lower → UNDER 5
            if pct_0_4 < pct_6_9:
                return {
                    "mode": "KIDRACKS",
                    "type": "UNDER",
                    "barrier": 5,
                }

            # If 6–9 is lower → OVER 5
            if pct_6_9 < pct_0_4:
                return {
                    "mode": "KIDRACKS",
                    "type": "OVER",
                    "barrier": 5,
                }

        return None

    # ==============================
    # KOOLKIDSPEED AUTO SIGNAL
    # ==============================
    def check_koolkidspeed_signal(self):
        """
        KOOLKIDSPEED rules:

        - Only active after 100 ticks.
        - Uses self.koolkidspeed_barrier.
        - Compare total % of 0–5 vs 6–9.
        - Need a minimum difference (koolkidspeed_min_diff).
        - If barrier is 0–5 → OVER only if 0–5 dominates.
        - If barrier is 6–9 → UNDER only if 6–9 dominates.
        """
        if self.tick_count < 100:
            return None

        barrier = int(self.koolkidspeed_barrier)

        pct_0_5 = self.sum_pct(0, 5)
        pct_6_9 = self.sum_pct(6, 9)

        diff = abs(pct_0_5 - pct_6_9)
        min_diff = float(getattr(self, "koolkidspeed_min_diff", 3.0))

        if diff < min_diff:
            return None

        # Barrier in 0–5 → OVER ONLY when 0–5 dominates
        if 0 <= barrier <= 5:
            if pct_0_5 > pct_6_9:
                return {
                    "mode": "KOOLKIDSPEED",
                    "type": "OVER",
                    "barrier": barrier,
                }
            else:
                return None

        # Barrier in 6–9 → UNDER ONLY when 6–9 dominates
        if 6 <= barrier <= 9:
            if pct_6_9 > pct_0_5:
                return {
                    "mode": "KOOLKIDSPEED",
                    "type": "UNDER",
                    "barrier": barrier,
                }
            else:
                return None

        return None

    # ==============================
    # KOOLLUCK AUTO SIGNAL
    # ==============================
    def check_koolluck_signal(self):
        """
        KOOL🍀LUCK:

        - Always analyzes the latest 100 ticks in the background.
        - Scores every KOOLLUCK contract candidate from the KOOLLUCK set.
        - For UNDER setups, the losing digits must stay weak.
        - For OVER setups, the losing digits must stay weak and the upper side must stay stronger.
        - Uses a softer probability model and only trades the best setup above threshold.
        - Background analysis keeps running even while the button is OFF.
        """
        analysis = self._refresh_koolluck_background_analysis()
        if not self.koolluck_auto:
            return None
        if not analysis.get("ready"):
            return None
        best_signal = analysis.get("best_signal")
        if not best_signal:
            return None
        return dict(best_signal)

    # ==================== PATCH E: add the three signal functions ====================
    # (These replace any existing ones with the same name; the ones below are the exact versions requested)

    # ==============================
    # kidBagz💰🤑 AUTO SIGNAL
    # ==============================
    def check_kidbagz_signal(self):
        """
        STRATEGY 3 – 📊 Clustering (Over/Under Zone Break)

        Cluster: last 6 digits are all in 0–4 zone (example: 2-3-1-4-3-2)
        Confirm: two consecutive breaks above 5 (digits 6–9), example: 6-7
        Entry: OVER 5
        """
        # Safety: need the rolling buffer
        buf = list(self.pattern_buffer)
        if len(buf) < 6:
            return None

        # cluster detected
        if all(0 <= d <= 4 for d in buf[-6:]):
            self.kidbagz_armed = True
            self.kidbagz_break_streak = 0
            return None

        if not getattr(self, "kidbagz_armed", False):
            return None

        d = self.last_tick_digit
        if d is None:
            return None

        # Breaks must be strictly > 5 (6–9)
        if d >= 6:
            self.kidbagz_break_streak += 1
        else:
            # Any non-break resets the streak
            self.kidbagz_break_streak = 0

        # Two breaks = confirmed breakout
        if self.kidbagz_break_streak >= 2:
            self.kidbagz_armed = False
            self.kidbagz_break_streak = 0
            return {"mode": "KIDBAGZ", "type": "OVER", "barrier": 5}

        return None


    # ==============================
    # MPull💰🤫 AUTO SIGNAL (Momentum Confirmation) — NEW OVERALL TREND VERSION
    # ==============================
    def check_mpull_signal(self):
        """
        MPull💰🤫 — Momentum Confirmation (overall trend, not exact sequence)

        Trend detection (last 5 digits):
          - UP trend: mostly rising overall (3+ upward steps out of 4) AND last > first
          - DOWN trend: mostly falling overall (3+ downward steps out of 4) AND last < first

        Pullback (next tick only):
          - After UP trend: next tick must be 4 -> trade OVER 5
          - After DOWN trend: next tick must be 5 -> trade UNDER 5

        Mode filter:
          self.mpull_mode in {"BOTH","OVER","UNDER"} controls allowed direction.
        """

        d = getattr(self, "last_tick_digit", None)
        if d is None:
            return None

        # 1) If we are waiting for pullback, it MUST be on this tick (next-tick rule)
        if getattr(self, "mpull_waiting_pullback", False):
            self.mpull_waiting_pullback = False  # next-tick window closes now

            direction = getattr(self, "mpull_dir", None)
            mode = (getattr(self, "mpull_mode", "BOTH") or "BOTH").upper()

            # UP trend pullback: 4 -> OVER 5
            if direction == "UP" and d == 4:
                if mode in ("BOTH", "OVER"):
                    self.mpull_dir = None
                    return {"mode": "MPULL", "type": "OVER", "barrier": 5}
                # mode blocks it
                self.mpull_dir = None
                return None

            # DOWN trend pullback: 5 -> UNDER 5
            if direction == "DOWN" and d == 5:
                if mode in ("BOTH", "UNDER"):
                    self.mpull_dir = None
                    return {"mode": "MPULL", "type": "UNDER", "barrier": 5}
                # mode blocks it
                self.mpull_dir = None
                return None

            # Pullback didn't match -> reset
            self.mpull_dir = None
            return None

        # 2) Not waiting: detect overall momentum from last 5 digits
        buf = list(getattr(self, "pattern_buffer", []))
        if len(buf) < 5:
            return None

        last5 = buf[-5:]  # oldest -> newest
        ups = 0
        downs = 0
        for i in range(1, 5):
            if last5[i] > last5[i - 1]:
                ups += 1
            elif last5[i] < last5[i - 1]:
                downs += 1

        # Require majority trend + net direction
        if ups >= 3 and last5[-1] > last5[0]:
            self.mpull_dir = "UP"
            self.mpull_waiting_pullback = True
            return None

        if downs >= 3 and last5[-1] < last5[0]:
            self.mpull_dir = "DOWN"
            self.mpull_waiting_pullback = True
            return None

        return None


    # ==============================
    # kidPairs🤓💯 AUTO SIGNAL (Exact Logic)
    # ==============================
    def check_kidpairs_signal(self):
        """
        KidPairs 🤓💯 — Exact Logic

        - Rolling window: last 5 digits
        - Over 1 signal: window contains 0 AND 1
        - Under 8 signal: window contains 8 AND 9
        - Random mode selection each eligible tick:
            randomly choose Over 1 or Under 8
            only trade if chosen mode condition is true now
        - Trade count per signal: 1 or 2 (self.kidpairs_trades_per_signal)
            1 Trade: execute immediately, start 5s cooldown
            2 Trades: trade #1 now, skip next tick, trade #2 on tick 3 no matter what, then 5s cooldown
        """
        now = time.time()

        # Cooldown check (global for KidPairs)
        cooldown_until = float(getattr(self, "kidpairs_cooldown_until", 0.0) or 0.0)
        if now < cooldown_until:
            return None

        # If a 2-trade sequence is active, we control tick spacing here
        if getattr(self, "kidpairs_seq_active", False):
            self.kidpairs_seq_tick = int(getattr(self, "kidpairs_seq_tick", 1)) + 1

            # Tick 2: skip
            if self.kidpairs_seq_tick == 2:
                return None

            # Tick 3: force trade #2 regardless of signal validity
            if self.kidpairs_seq_tick >= 3:
                sig2 = getattr(self, "kidpairs_forced_signal", None)
                # end sequence
                self.kidpairs_seq_active = False
                self.kidpairs_seq_tick = 0
                self.kidpairs_forced_signal = None
                # start 5s cooldown AFTER trade #2
                self.kidpairs_cooldown_until = now + 5.0
                return sig2

            return None

        # Not in a sequence: evaluate last 5 digits window
        buf = list(self.pattern_buffer)
        if len(buf) < 5:
            return None
        last5 = buf[-5:]

        over1_ok = (0 in last5 and 1 in last5)
        under8_ok = (8 in last5 and 9 in last5)

        # Randomly choose which mode to attempt this tick
        choice = random.choice(["OVER1", "UNDER8"])

        # If chosen mode isn't valid, do nothing this tick
        if choice == "OVER1" and not over1_ok:
            return None
        if choice == "UNDER8" and not under8_ok:
            return None

        # Build the chosen signal
        if choice == "OVER1":
            sig = {"mode": "KIDPAIRS", "type": "OVER", "barrier": 1}
        else:
            sig = {"mode": "KIDPAIRS", "type": "UNDER", "barrier": 8}

        trades = int(getattr(self, "kidpairs_trades_per_signal", 1) or 1)
        if trades not in (1, 2):
            trades = 1

        # 1 Trade mode
        if trades == 1:
            # Start cooldown immediately after trade #1
            self.kidpairs_cooldown_until = now + 5.0
            return sig

        # 2 Trades mode
        # Trade #1 now, Trade #2 forced on tick 3 (skip one tick in between)
        self.kidpairs_seq_active = True
        self.kidpairs_seq_tick = 1
        self.kidpairs_forced_signal = sig
        return sig


    # ==============================
    # SERVER CALLS THIS EVERY TICK
    # ==============================
    # ==================== PATCH F: replace check_auto_trade_signal entirely ====================
    def check_auto_trade_signal(self):
        """
        Called from server.py on every tick.

        Returns:
            - None (no trade), OR
            - dict, OR
            - list of dicts:
                {
                    "mode": "...",
                    "type": "OVER"/"UNDER",
                    "barrier": int
                }
        """

        signals = []

        now = time.time()

        over3_sig = self.check_over3_analysis_signal()
        if over3_sig:
            signals.append(over3_sig)

        kid2vix_sig = self.check_kid2vix_signal()
        if kid2vix_sig:
            signals.extend(kid2vix_sig)

        # ------------------------------
        # NEW MODES (can run immediately)
        # ------------------------------

        # kidBagz💰🤑 (uses cooldown_seconds)
        if getattr(self, "kidbagz_auto", False):
            if self.can_trade_kidbagz():
                sig = self.check_kidbagz_signal()
                if sig:
                    signals.append(sig)
                    self.mark_kidbagz_trade()

        # MPull💰🤫 (uses cooldown_seconds)
        if getattr(self, "mpull_auto", False):
            if self.can_trade_mpull():
                sig = self.check_mpull_signal()
                if sig:
                    signals.append(sig)
                    self.mark_mpull_trade()

        # kidPairs🤓💯 (its own strict 5s cooldown + 2-trade sequence)
        if getattr(self, "kidpairs_auto", False):
            sig = self.check_kidpairs_signal()
            if sig:
                signals.append(sig)

        # ⚡kidGx (super fast endless, linked to selected Barrier Analysis option)
        if getattr(self, "kidgx_auto", False):
            if self._barrier_analysis_ready() and self.can_trade_kidgx():
                key = str(getattr(self, "barrier_analysis_selected", "UNDER 9"))
                try:
                    t, b = key.split()
                    signals.append({"mode": "KIDGX", "type": str(t).upper(), "barrier": int(b)})
                    self.mark_kidgx_trade()
                except Exception:
                    pass

        # 🤖AI AUTO-TRADING (KOOLKID)
        if getattr(self, "ai_auto_trading", False):
            if self._barrier_analysis_ready() and self.can_trade_ai_auto():
                best = self._pick_best_ai_candidate()
                if best:
                    signals.append({"mode": "AI_AUTO_KOOLKID", "type": best["type"], "barrier": int(best["barrier"])})
                    self.mark_ai_auto_trade()

        # MPull💰🤓 ALL DIGITS (uses MPull trigger, only fires on selected digits)
        if getattr(self, "mpull_all_digits_auto", False):
            if self.can_trade_mpull_all_digits():
                selected = set(getattr(self, "mpull_all_digits_selected_digits", set()) or set())
                base_sig = self.check_mpull_signal()
                if base_sig and selected:
                    d = int(getattr(self, "last_tick_digit", -1) or -1)
                    mapped_sig = None
                    if d in selected:
                        if 1 <= d <= 5:
                            mapped_sig = {"mode": "MPULL_ALL_DIGITS", "type": "OVER", "barrier": d}
                        elif 6 <= d <= 9:
                            mapped_sig = {"mode": "MPULL_ALL_DIGITS", "type": "UNDER", "barrier": d}
                    if mapped_sig:
                        signals.append(mapped_sig)
                        self.mark_mpull_all_digits_trade()

        # -----------------------------------------
        # EXISTING MODES (keep your 100-tick gating)
        # -----------------------------------------
        if self.tick_count >= 100:

            # KidRacks
            if self.kidracks_auto and self.can_trade_kidracks():
                sig = self.check_kidracks_signal()
                if sig:
                    signals.append(sig)
                    self.mark_kidracks_trade()

            # KoolKidspeed
            if self.koolkidspeed_auto and self.can_trade_koolkidspeed():
                sig = self.check_koolkidspeed_signal()
                if sig:
                    signals.append(sig)
                    self.mark_koolkidspeed_trade()

            # KOOLLuck
            if self.koolluck_auto and self.can_trade_koolluck():
                sig = self.check_koolluck_signal()
                if sig:
                    signals.append(sig)
                    self.mark_koolluck_trade()

            # AUTO$
            if self.auto_dollar_auto and self.can_trade_auto_dollar():
                sig = self.check_auto_dollar_signal()
                if sig:
                    signals.extend(sig)
                    self.mark_auto_dollar_trade()

        if not signals:
            return None

        if len(signals) == 1:
            return signals[0]

        return signals

    # ==============================
    # UI PAYLOAD
    # ==============================
    # ==================== PATCH G: update get_ui_payload ====================
    def get_ui_payload(self):
        return {
            "tick_count": self.tick_count,
            "last_digit": self.last_tick_digit,
            "percentages": self.digit_percentages,
            "confidence": {
                "over1": self.confidence_over1,
                "over2": self.confidence_over2,
                "under8": self.confidence_under8,
                "under9": self.confidence_under9,
            },
            "auto_modes": {
                "kidracks": self.kidracks_auto,
                "koolkidspeed": self.koolkidspeed_auto,
                "koolluck": self.koolluck_auto,
                "auto_dollar": self.auto_dollar_auto,
                "kidbagz": self.kidbagz_auto,
                "mpull": self.mpull_auto,
                "kidpairs": self.kidpairs_auto,
                "kidgx": self.kidgx_auto,
                "barrier_analysis": self.barrier_analysis_running,
                "ai_auto_trading": self.ai_auto_trading,
                "mpull_all_digits": self.mpull_all_digits_auto,
                "over3_analysis": self.over3_analysis_auto,
                "kid2vix": self.kid2vix_auto,
            },
            "auto_settings": {
                "kidracks_barrier": self.kidracks_barrier,
                "koolkidspeed_barrier": self.koolkidspeed_barrier,
                "mpull_mode": self.mpull_mode,
                "kidpairs_trades_per_signal": self.kidpairs_trades_per_signal,
                "barrier_analysis_selected": self.barrier_analysis_selected,
                "mpull_all_digits_selected_digits": sorted(list(self.mpull_all_digits_selected_digits)),
                "over3_execution_barrier": int(self._normalize_over3_execution_barrier(getattr(self, "over3_execution_barrier", 3))),
                "kid2vix_last20_threshold": int(self.kid2vix_last20_threshold),
                "kid2vix_last5_threshold": int(self.kid2vix_last5_threshold),
                "kid2vix_repeat_pressure_threshold": float(self.kid2vix_repeat_pressure_threshold),
                "kid2vix_over3_ratio": float(self.kid2vix_over3_ratio),
                "kid2vix_cooldown_after_loss": float(self.kid2vix_cooldown_after_loss),
            },
            "over3_analysis_data": self.get_over3_analysis_state(),
            "kid2vix_data": dict(self.kid2vix_analysis or self._refresh_kid2vix_analysis() or {}),
            "auto_dollar_analysis": dict(self.auto_dollar_analysis or {}),
            "barrier_analysis": {
                "running": bool(self.barrier_analysis_running),
                "progress": int(min(self.barrier_analysis_warm_count, self.barrier_analysis_warm_target)),
                "target": int(self.barrier_analysis_warm_target),
                "ready": bool(self._barrier_analysis_ready()),
                "rows": self._get_barrier_analysis_rows(),
                "recommended": self._get_barrier_analysis_recommended(),
                "selected": self.barrier_analysis_selected,
                "ai_recommended": self._pick_best_ai_candidate() if self._barrier_analysis_ready() else None,
            },
        }

# ==================== ADVANCED NAMED AI MODES PATCH (non-destructive wrapper) ====================
def _kk_adv_mode_keys():
    return ("kidbrain", "edge_brain", "smart_flow", "meta_ai", "kidracks_ai")

def _kk_adv_init_state(self):
    self._adv_named_modes = {k: False for k in _kk_adv_mode_keys()}
    self._adv_mode_last_trade = {k: 0.0 for k in _kk_adv_mode_keys()}
    self._adv_loss_streak = 0
    self._adv_win_streak = 0
    self._adv_pause_until = 0.0
    self._adv_last_regime = "WARMUP"
    self._adv_shadow = {"live_wins": 0, "live_losses": 0, "alt_wins": 0, "alt_losses": 0, "sample": 0}
    self._adv_shadow_live_pending = None
    self._adv_shadow_alt_pending = None
    self._adv_last_meta = {"regime": "WARMUP", "confidence_pct": 0.0, "edge_gap": 0.0, "market_score": 0.0, "consensus": 0}

def _kk_toggle_named_ai_mode(self, mode_key):
    mk = str(mode_key or "").strip().lower()
    if mk not in _kk_adv_mode_keys():
        raise ValueError(f"Invalid mode: {mode_key}")
    self._adv_named_modes[mk] = not bool(self._adv_named_modes.get(mk, False))
    # If META AI is turned on, keep independent but reset pause/shadow comparators for clean start
    if self._adv_named_modes[mk]:
        self._adv_mode_last_trade[mk] = 0.0
    return bool(self._adv_named_modes[mk])

def _kk_get_named_ai_modes_state(self):
    return dict(getattr(self, "_adv_named_modes", {}) or {})

def _kk_any_named_ai_mode_on(self):
    modes = getattr(self, "_adv_named_modes", {}) or {}
    return any(bool(v) for v in modes.values())

def _kk_eval_contract_result(contract_type, barrier, digit):
    try:
        d = int(digit)
        b = int(barrier)
        ct = str(contract_type or "").upper()
        if ct == "OVER":
            return d > b
        if ct == "UNDER":
            return d < b
        if ct == "DIFFERS":
            return d != b
        if ct == "MATCHES":
            return d == b
    except Exception:
        return None
    return None

def _kk_adv_resolve_pending_shadow(self, digit):
    for key in ("_adv_shadow_live_pending", "_adv_shadow_alt_pending"):
        pred = getattr(self, key, None)
        if not pred:
            continue
        res = _kk_eval_contract_result(pred.get("type"), pred.get("barrier"), digit)
        if res is None:
            setattr(self, key, None)
            continue
        shadow = getattr(self, "_adv_shadow", None) or {"live_wins":0,"live_losses":0,"alt_wins":0,"alt_losses":0,"sample":0}
        if key.endswith("live_pending"):
            if res: shadow["live_wins"] += 1
            else: shadow["live_losses"] += 1
        else:
            if res: shadow["alt_wins"] += 1
            else: shadow["alt_losses"] += 1
        shadow["sample"] = int(shadow.get("sample", 0)) + 1
        self._adv_shadow = shadow
        setattr(self, key, None)

def _kk_adv_snapshot(self):
    tick_count = int(getattr(self, "tick_count", 0) or 0)
    if tick_count < 100:
        snap = {"regime":"WARMUP","confidence_pct":0.0,"edge_gap":0.0,"market_score":0.0,"consensus":0}
        self._adv_last_meta = dict(snap)
        return snap

    # digit rarity and edge
    pcts = [float(getattr(self, "digit_percentages", {}).get(i, 0.0)) for i in range(10)]
    sorted_desc = sorted(pcts, reverse=True)
    sorted_asc = sorted(pcts)
    dominant_gap = (sorted_desc[0] - sorted_desc[1]) if len(sorted_desc) >= 2 else 0.0
    rare_gap = (sorted_asc[1] - sorted_asc[0]) if len(sorted_asc) >= 2 else 0.0

    conf = 0.0
    edge_gap = 0.0
    best_ai = None
    second_ai_pct = None

    try:
        if hasattr(self, "_barrier_analysis_ready") and self._barrier_analysis_ready():
            defs = list(self._get_ai_candidate_defs()) if hasattr(self, "_get_ai_candidate_defs") else []
            rows = []
            for t, b in defs:
                key = self._barrier_key(t, b)
                pct = float(self._analysis_pct(key))
                rows.append((pct, str(t).upper(), int(b), key))
            rows.sort(key=lambda x: (-x[0], x[2]))
            if rows:
                conf = float(rows[0][0])
                best_ai = {"wins_pct": rows[0][0], "type": rows[0][1], "barrier": rows[0][2], "key": rows[0][3]}
                if len(rows) > 1:
                    second_ai_pct = float(rows[1][0])
            edge_gap = conf - (second_ai_pct if second_ai_pct is not None else conf)
        else:
            conf = float(max(
                getattr(self, "confidence_over1", 0),
                getattr(self, "confidence_over2", 0),
                getattr(self, "confidence_under8", 0),
                getattr(self, "confidence_under9", 0)
            ))
            edge_gap = max(dominant_gap, rare_gap)
    except Exception:
        conf = float(max(
            getattr(self, "confidence_over1", 0),
            getattr(self, "confidence_over2", 0),
            getattr(self, "confidence_under8", 0),
            getattr(self, "confidence_under9", 0)
        ))
        edge_gap = max(dominant_gap, rare_gap)

    # Sequence detector from last 5 digits
    buf = list(getattr(self, "pattern_buffer", []) or [])
    last5 = buf[-5:] if len(buf) >= 5 else []
    has_over1_seq = (0 in last5 and 1 in last5)
    has_under8_seq = (8 in last5 and 9 in last5)
    sequence_bias = has_over1_seq or has_under8_seq

    if conf >= 68 and edge_gap >= 4:
        regime = "BARRIER_DOMINANT"
    elif sequence_bias:
        regime = "SEQUENCE"
    elif max(dominant_gap, rare_gap) <= 2.0:
        regime = "BALANCED"
    else:
        regime = "MIXED"

    score = float(conf) + float(edge_gap * 1.5) - float(getattr(self, "_adv_loss_streak", 0) * 4)
    if regime == "SEQUENCE":
        score += 4.0
    elif regime == "BARRIER_DOMINANT":
        score += 6.0
    if getattr(self, "_adv_pause_until", 0.0) > time.time():
        score -= 12.0

    snap = {
        "regime": regime,
        "confidence_pct": round(float(conf), 1),
        "edge_gap": round(float(edge_gap), 1),
        "market_score": round(float(score), 1),
        "consensus": 0,
        "_best_ai": best_ai,
        "_has_over1_seq": bool(has_over1_seq),
        "_has_under8_seq": bool(has_under8_seq),
    }
    self._adv_last_meta = dict({k:v for k,v in snap.items() if not k.startswith("_")})
    self._adv_last_regime = regime
    return snap

def _kk_adv_pick_ai_signal(self):
    try:
        best = self._pick_best_ai_candidate() if hasattr(self, "_pick_best_ai_candidate") else None
    except Exception:
        best = None
    if not best:
        return None
    return {"mode": "META_AI", "type": str(best["type"]).upper(), "barrier": int(best["barrier"])}

def _kk_adv_pick_kidpairs_signal(self):
    if not hasattr(self, "pattern_buffer"):
        return None
    buf = list(self.pattern_buffer)
    if len(buf) < 5:
        return None
    last5 = buf[-5:]
    over_ok = (0 in last5 and 1 in last5)
    under_ok = (8 in last5 and 9 in last5)
    if not over_ok and not under_ok:
        return None
    # choose stronger confidence side
    over_score = float(getattr(self, "confidence_over1", 0)) + float(getattr(self, "confidence_over2", 0)) * 0.35
    under_score = float(getattr(self, "confidence_under8", 0)) + float(getattr(self, "confidence_under9", 0)) * 0.35
    if over_ok and (not under_ok or over_score >= under_score):
        return {"mode": "SMART_FLOW", "type": "OVER", "barrier": 1}
    return {"mode": "SMART_FLOW", "type": "UNDER", "barrier": 8}

def _kk_adv_pick_kidracks_signal(self):
    try:
        if hasattr(self, "check_kidracks_signal"):
            sig = self.check_kidracks_signal()
            if sig:
                sig = dict(sig)
                sig["mode"] = "KIDRACKS_AI"
                return sig
    except Exception:
        pass
    # fallback: use selected kidracks barrier with family inference when barrier printed
    try:
        b = int(getattr(self, "kidracks_barrier", 5))
        d = int(getattr(self, "last_tick_digit", -1))
        if d != b:
            return None
        if b <= 4:
            t = "OVER"
        elif b >= 6:
            t = "UNDER"
        else:
            low = sum(float(self.digit_percentages.get(i,0.0)) for i in range(0,5))
            high = sum(float(self.digit_percentages.get(i,0.0)) for i in range(6,10))
            t = "UNDER" if low < high else "OVER"
        return {"mode":"KIDRACKS_AI","type":t,"barrier":b}
    except Exception:
        return None

def _kk_adv_consensus(self, snap, ai_sig, seq_sig):
    count = 0
    if ai_sig and snap.get("confidence_pct", 0.0) >= 58.0:
        count += 1
    if seq_sig:
        count += 1
    # third vote from percentages side bias
    try:
        low = sum(float(self.digit_percentages.get(i, 0.0)) for i in range(0, 5))
        high = sum(float(self.digit_percentages.get(i, 0.0)) for i in range(5, 10))
        if ai_sig:
            if ai_sig["type"] == "OVER" and low <= high + 3:
                count += 1
            elif ai_sig["type"] == "UNDER" and high <= low + 3:
                count += 1
        elif seq_sig:
            if seq_sig["type"] == "OVER" and low <= high + 3:
                count += 1
            elif seq_sig["type"] == "UNDER" and high <= low + 3:
                count += 1
    except Exception:
        pass
    return count

def _kk_adv_mode_cooldown(self, mode_key):
    base = 5.0
    if mode_key == "meta_ai":
        base = 3.0
    elif mode_key == "smart_flow":
        base = 4.0
    elif mode_key == "edge_brain":
        base = 5.0
    elif mode_key == "kidracks_ai":
        base = float(getattr(self, "cooldown_seconds", 5.0))
    # adaptive loss-based extension
    loss_streak = int(getattr(self, "_adv_loss_streak", 0) or 0)
    if loss_streak > 0:
        base += min(10.0, loss_streak * 2.5)
    return base

def _kk_adv_can_trade(self, mode_key):
    now = time.time()
    if now < float(getattr(self, "_adv_pause_until", 0.0) or 0.0):
        return False
    last_t = float((getattr(self, "_adv_mode_last_trade", {}) or {}).get(mode_key, 0.0))
    return (now - last_t) >= _kk_adv_mode_cooldown(self, mode_key)

def _kk_adv_mark_trade(self, mode_key, signal, alt_signal=None):
    now = time.time()
    self._adv_mode_last_trade[mode_key] = now
    if signal and isinstance(signal, dict):
        self._adv_shadow_live_pending = {"type": signal.get("type"), "barrier": signal.get("barrier")}
    if alt_signal and isinstance(alt_signal, dict):
        self._adv_shadow_alt_pending = {"type": alt_signal.get("type"), "barrier": alt_signal.get("barrier")}
    else:
        self._adv_shadow_alt_pending = None

def _kk_adv_build_signal_for_mode(self, mode_key):
    if not _kk_adv_can_trade(self, mode_key):
        return None

    snap = _kk_adv_snapshot(self)
    ai_sig = _kk_adv_pick_ai_signal(self)
    seq_sig = _kk_adv_pick_kidpairs_signal(self)
    racks_sig = _kk_adv_pick_kidracks_signal(self)

    # normalize mode labels
    def clone(sig, mode_name):
        if not sig:
            return None
        out = dict(sig)
        out["mode"] = mode_name
        return out

    if mode_key == "kidbrain":
        chosen = None
        if snap["regime"] == "SEQUENCE":
            chosen = clone(seq_sig, "KIDBRAIN")
            alt = clone(ai_sig, "KIDBRAIN_SHADOW")
        elif snap["regime"] == "BARRIER_DOMINANT":
            chosen = clone(ai_sig, "KIDBRAIN")
            alt = clone(seq_sig or racks_sig, "KIDBRAIN_SHADOW")
        elif snap["regime"] == "BALANCED":
            chosen = clone(racks_sig or ai_sig, "KIDBRAIN")
            alt = clone(seq_sig, "KIDBRAIN_SHADOW")
        else:
            chosen = clone(ai_sig if snap["confidence_pct"] >= 60 else None, "KIDBRAIN")
            alt = clone(seq_sig, "KIDBRAIN_SHADOW")
        if chosen:
            _kk_adv_mark_trade(self, mode_key, chosen, alt)
        return chosen

    if mode_key == "edge_brain":
        if ai_sig and snap["confidence_pct"] >= 63 and snap["edge_gap"] >= 4:
            chosen = clone(ai_sig, "EDGE_BRAIN")
            _kk_adv_mark_trade(self, mode_key, chosen, clone(seq_sig, "EDGE_BRAIN_SHADOW"))
            return chosen
        return None

    if mode_key == "smart_flow":
        consensus = _kk_adv_consensus(self, snap, ai_sig, seq_sig)
        self._adv_last_meta["consensus"] = consensus
        primary = ai_sig or seq_sig
        if primary and consensus >= 2 and snap["confidence_pct"] >= 58:
            chosen = clone(primary, "SMART_FLOW")
            alt = clone(seq_sig if primary is ai_sig else ai_sig, "SMART_FLOW_SHADOW")
            _kk_adv_mark_trade(self, mode_key, chosen, alt)
            return chosen
        return None

    if mode_key == "meta_ai":
        consensus = _kk_adv_consensus(self, snap, ai_sig, seq_sig)
        self._adv_last_meta["consensus"] = consensus
        if snap["confidence_pct"] < 60 or snap["edge_gap"] < 2:
            return None
        if snap["regime"] == "SEQUENCE" and seq_sig and consensus >= 2:
            chosen = clone(seq_sig, "META_AI")
        elif ai_sig and (consensus >= 2 or snap["confidence_pct"] >= 70):
            chosen = clone(ai_sig, "META_AI")
        elif racks_sig and snap["regime"] in ("BALANCED", "MIXED") and consensus >= 2:
            chosen = clone(racks_sig, "META_AI")
        else:
            return None
        alt = clone(ai_sig if chosen.get("type") != (ai_sig or {}).get("type") else seq_sig, "META_AI_SHADOW")
        _kk_adv_mark_trade(self, mode_key, chosen, alt)
        return chosen

    if mode_key == "kidracks_ai":
        if racks_sig and snap["confidence_pct"] >= 52:
            chosen = clone(racks_sig, "KIDRACKS_AI")
            _kk_adv_mark_trade(self, mode_key, chosen, clone(ai_sig, "KIDRACKS_AI_SHADOW"))
            return chosen
        return None

    return None

# --- wrappers ---
_KK_ORIG_INIT = KoolKidStrategy.__init__
_KK_ORIG_RESET = KoolKidStrategy.reset
_KK_ORIG_ON_TICK = KoolKidStrategy.on_tick
_KK_ORIG_ON_CONTRACT = KoolKidStrategy.on_contract
_KK_ORIG_CHECK_AUTO = KoolKidStrategy.check_auto_trade_signal
_KK_ORIG_GET_UI = KoolKidStrategy.get_ui_payload

def _kk_init_wrapper(self, *args, **kwargs):
    _KK_ORIG_INIT(self, *args, **kwargs)
    _kk_adv_init_state(self)

def _kk_reset_wrapper(self, *args, **kwargs):
    res = _KK_ORIG_RESET(self, *args, **kwargs)
    _kk_adv_init_state(self)
    return res

def _kk_on_tick_wrapper(self, tick, digit):
    try:
        _kk_adv_resolve_pending_shadow(self, int(digit))
    except Exception:
        pass
    res = _KK_ORIG_ON_TICK(self, tick, digit)
    try:
        _kk_adv_snapshot(self)
    except Exception:
        pass
    return res

def _kk_on_contract_wrapper(self, contract, balance):
    res = _KK_ORIG_ON_CONTRACT(self, contract, balance)
    try:
        profit = float(contract.get("profit", 0) or 0)
        if profit > 0:
            self._adv_win_streak = int(getattr(self, "_adv_win_streak", 0)) + 1
            self._adv_loss_streak = 0
        else:
            self._adv_loss_streak = int(getattr(self, "_adv_loss_streak", 0)) + 1
            self._adv_win_streak = 0
            if self._adv_loss_streak >= 2:
                self._adv_pause_until = max(float(getattr(self, "_adv_pause_until", 0.0) or 0.0), time.time() + min(20.0, 6.0 + self._adv_loss_streak * 2.0))
    except Exception:
        pass
    return res

def _kk_check_auto_wrapper(self):
    orig = _KK_ORIG_CHECK_AUTO(self)
    adv_signals = []
    try:
        modes = getattr(self, "_adv_named_modes", {}) or {}
        for mk in _kk_adv_mode_keys():
            if modes.get(mk):
                sig = _kk_adv_build_signal_for_mode(self, mk)
                if sig:
                    adv_signals.append(sig)
    except Exception:
        pass

    # merge with original result non-destructively
    combined = []
    if orig is None:
        combined = []
    elif isinstance(orig, list):
        combined.extend(orig)
    else:
        combined.append(orig)
    combined.extend(adv_signals)

    if not combined:
        return None
    if len(combined) == 1:
        return combined[0]
    return combined

def _kk_get_ui_wrapper(self):
    payload = _KK_ORIG_GET_UI(self)
    try:
        payload = dict(payload or {})
        payload.setdefault("auto_modes", {})
        payload["auto_modes"].update(_kk_get_named_ai_modes_state(self))
        snap = _kk_adv_snapshot(self)
        shadow = dict(getattr(self, "_adv_shadow", {}) or {})
        live_total = int(shadow.get("live_wins", 0)) + int(shadow.get("live_losses", 0))
        alt_total = int(shadow.get("alt_wins", 0)) + int(shadow.get("alt_losses", 0))
        if live_total > 0:
            shadow["live_winrate"] = round((shadow.get("live_wins", 0) / live_total) * 100.0, 1)
        else:
            shadow["live_winrate"] = 0.0
        if alt_total > 0:
            shadow["alt_winrate"] = round((shadow.get("alt_wins", 0) / alt_total) * 100.0, 1)
        else:
            shadow["alt_winrate"] = 0.0
        shadow["sample"] = int(shadow.get("sample", 0))
        payload["meta_brain"] = {
            "regime": snap.get("regime", "WARMUP"),
            "confidence_pct": float(snap.get("confidence_pct", 0.0)),
            "edge_gap": float(snap.get("edge_gap", 0.0)),
            "market_score": float(snap.get("market_score", 0.0)),
            "consensus": int(getattr(self, "_adv_last_meta", {}).get("consensus", 0)),
            "loss_streak": int(getattr(self, "_adv_loss_streak", 0)),
            "pause_until": float(getattr(self, "_adv_pause_until", 0.0)),
            "shadow": shadow,
        }
    except Exception:
        return payload
    return payload

# bind methods
KoolKidStrategy.__init__ = _kk_init_wrapper
KoolKidStrategy.reset = _kk_reset_wrapper
KoolKidStrategy.on_tick = _kk_on_tick_wrapper
KoolKidStrategy.on_contract = _kk_on_contract_wrapper
KoolKidStrategy.check_auto_trade_signal = _kk_check_auto_wrapper
KoolKidStrategy.get_ui_payload = _kk_get_ui_wrapper
KoolKidStrategy.toggle_named_ai_mode = _kk_toggle_named_ai_mode
KoolKidStrategy.get_named_ai_modes_state = _kk_get_named_ai_modes_state
