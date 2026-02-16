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

        # AUTO SETTINGS (BARRIERS ONLY)
        self.kidracks_barrier = 5
        self.koolkidspeed_barrier = 5

        # Cooldowns (so modes don't spam)
        self.kidracks_last_trade_time = 0
        self.koolkidspeed_last_trade_time = 0
        self.koolluck_last_trade_time = 0

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

        self.kidracks_last_trade_time = 0
        self.koolkidspeed_last_trade_time = 0
        self.koolluck_last_trade_time = 0

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

    def mark_kidracks_trade(self):
        self.kidracks_last_trade_time = time.time()

    def mark_koolkidspeed_trade(self):
        self.koolkidspeed_last_trade_time = time.time()

    def mark_koolluck_trade(self):
        self.koolluck_last_trade_time = time.time()

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

    # ==============================
    # SERVER CALLS THIS EVERY TICK
    # ==============================
    def check_auto_trade_signal(self):
        """
        Called from server.py on every tick.

        Returns:
            - None (no trade), OR
            - dict, OR
            - list of dicts:
                {
                    "mode": "KIDRACKS"/"KOOLKIDSPEED"/"KOOLLUCK",
                    "type": "OVER"/"UNDER",
                    "barrier": int
                }
        """
        if self.tick_count < 100:
            # KOOLLuck doesn't depend on percentages; you can remove this
            # check for it if you want KOOLLuck from tick 1.
            # For now we keep all autos synced after 100 ticks.
            return None

        signals = []

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
            },
            "auto_settings": {
                "kidracks_barrier": self.kidracks_barrier,
                "koolkidspeed_barrier": self.koolkidspeed_barrier,
            },
        }
