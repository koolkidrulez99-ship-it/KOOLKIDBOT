from collections import deque
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
        self.kidbagz_auto = False
        self.mpull_auto = False
        self.kidpairs_auto = False

        self.kidracks_last_trade_time = 0
        self.koolkidspeed_last_trade_time = 0
        self.koolluck_last_trade_time = 0
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

        self.koolluck_current_sequence = None
        self.koolluck_step_index = 0

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

        self.pattern_buffer.append(digit)
        self.update_confidence_bars()
        self._record_barrier_analysis_tick(digit)

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

    def mark_kidbagz_trade(self):
        self.kidbagz_last_trade_time = time.time()

    def mark_mpull_trade(self):
        self.mpull_last_trade_time = time.time()

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

        - Uses your 5 given sequences.
        - Always random sequence choice.
        - Walks the sequence step by step.
        - Each step: wait until that digit prints, then send that trade.
        - Then move to next step; when sequence ends, pick a new random one.
        """
        if not self.koolluck_auto:
            return None

        # If no current sequence or finished → pick new random one
        if self.koolluck_current_sequence is None or \
           self.koolluck_step_index >= len(self.koolluck_current_sequence):

            self.koolluck_current_sequence = random.choice(self.koolluck_sequences)
            self.koolluck_step_index = 0

        step = self.koolluck_current_sequence[self.koolluck_step_index]

        # Only trade when that digit just printed
        if self.last_tick_digit != step["barrier"]:
            return None

        # Build signal
        sig = {
            "mode": "KOOLLUCK",
            "type": step["type"],
            "barrier": step["barrier"],
        }

        # Move to next step for next time
        self.koolluck_step_index += 1

        return sig

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
                "kidbagz": self.kidbagz_auto,
                "mpull": self.mpull_auto,
                "kidpairs": self.kidpairs_auto,
                "kidgx": self.kidgx_auto,
                "barrier_analysis": self.barrier_analysis_running,
                "ai_auto_trading": self.ai_auto_trading,
                "mpull_all_digits": self.mpull_all_digits_auto,
            },
            "auto_settings": {
                "kidracks_barrier": self.kidracks_barrier,
                "koolkidspeed_barrier": self.koolkidspeed_barrier,
                "mpull_mode": self.mpull_mode,
                "kidpairs_trades_per_signal": self.kidpairs_trades_per_signal,
                "barrier_analysis_selected": self.barrier_analysis_selected,
                "mpull_all_digits_selected_digits": sorted(list(self.mpull_all_digits_selected_digits)),
            },
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