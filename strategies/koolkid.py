from collections import deque
import random
import time

from strategies.base import BaseStrategy


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
        self.koolluck_auto = False  # 🍀 KOOL LUCK

        # AUTO SETTINGS (BARRIERS ONLY)
        self.kidracks_barrier = 5
        self.koolkidspeed_barrier = 5
        # KoolLuck sequences have their own barriers

        # Cooldowns
        self.kidracks_last_trade_time = 0
        self.koolkidspeed_last_trade_time = 0
        self.koolluck_last_trade_time = 0

        # 5 second delay
        self.cooldown_seconds = 5.0

        # minimum dominance difference for KoolKidspeed
        self.koolkidspeed_min_diff = 3.0

        # =======================
        # KOOLLUCK SEQUENCES
        # =======================
        # 1.) over 1, over 2, under 8, under 9
        # 2.) over 2, over 1, over 3, under 9
        # 3.) over 0, over 2, under 9, over 1
        # 4.) under 8, under 7, over 2, under 9
        # 5.) under 8, over 2, under 7, over 5
        self.koolluck_sequences = [
            [
                {"type": "OVER", "barrier": 1},
                {"type": "OVER", "barrier": 2},
                {"type": "UNDER", "barrier": 8},
                {"type": "UNDER", "barrier": 9},
            ],
            [
                {"type": "OVER", "barrier": 2},
                {"type": "OVER", "barrier": 1},
                {"type": "OVER", "barrier": 3},
                {"type": "UNDER", "barrier": 9},
            ],
            [
                {"type": "OVER", "barrier": 0},
                {"type": "OVER", "barrier": 2},
                {"type": "UNDER", "barrier": 9},
                {"type": "OVER", "barrier": 1},
            ],
            [
                {"type": "UNDER", "barrier": 8},
                {"type": "UNDER", "barrier": 7},
                {"type": "OVER", "barrier": 2},
                {"type": "UNDER", "barrier": 9},
            ],
            [
                {"type": "UNDER", "barrier": 8},
                {"type": "OVER", "barrier": 2},
                {"type": "UNDER", "barrier": 7},
                {"type": "OVER", "barrier": 5},
            ],
        ]
        self.koolluck_current_sequence = None
        self.koolluck_index = 0

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
        self.koolluck_index = 0

    # ========= TOGGLES =========
    def toggle_kidracks_auto(self):
        self.kidracks_auto = not self.kidracks_auto
        return self.kidracks_auto

    def toggle_koolkidspeed_auto(self):
        self.koolkidspeed_auto = not self.koolkidspeed_auto
        return self.koolkidspeed_auto

    def toggle_koolluck_auto(self):
        self.koolluck_auto = not self.koolluck_auto
        # when turning OFF, reset the sequence so a new one is random next time
        if not self.koolluck_auto:
            self.koolluck_current_sequence = None
            self.koolluck_index = 0
        return self.koolluck_auto

    # ========= CONFIDENCE BARS =========
    def update_confidence_bars(self):
        if len(self.pattern_buffer) < 3:
            return

        last = list(self.pattern_buffer)

        if 0 in last[-4:] and 1 in last[-4:]:
            self.confidence_over1 = min(100, self.confidence_over1 + 8)
        else:
            self.confidence_over1 = max(0, self.confidence_over1 - 2)

        if 2 in last[-4:]:
            self.confidence_over2 = min(100, self.confidence_over2 + 6)
        else:
            self.confidence_over2 = max(0, self.confidence_over2 - 2)

        if 9 in last[-3:]:
            self.confidence_under9 = min(100, self.confidence_under9 + 10)
        else:
            self.confidence_under9 = max(0, self.confidence_under9 - 3)

        if 9 in last[-4:] and 8 in last[-4:]:
            self.confidence_under8 = min(100, self.confidence_under8 + 10)
        else:
            self.confidence_under8 = max(0, self.confidence_under8 - 3)

    def on_tick(self, tick, digit):
        super().on_tick(tick, digit)

        self.pattern_buffer.append(digit)
        self.update_confidence_bars()

    # ==============================
    # HELPER FUNCTIONS
    # ==============================
    def sum_pct(self, start, end):
        total = 0
        for i in range(start, end + 1):
            total += float(self.digit_percentages.get(i, 0))
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
        if self.tick_count < 100:
            return None

        barrier = int(self.kidracks_barrier)

        barrier_pct = float(self.digit_percentages.get(barrier, 0))

        # MUST BE UNDER 10%
        if barrier_pct >= 10:
            return None

        # We now use the live percentage directly (no need to wait for the digit to play first)

        pct_0_4 = self.sum_pct(0, 4)
        pct_5_9 = self.sum_pct(5, 9)

        pct_0_1 = self.sum_pct(0, 1)
        pct_0_2 = self.sum_pct(0, 2)

        pct_8_9 = self.sum_pct(8, 9)

        # 0-4 = OVER
        if barrier in [0, 1, 2, 3, 4]:

            if barrier == 1 and pct_0_1 >= 20:
                return None

            if barrier == 2 and pct_0_2 >= 25:
                return None

            if barrier in [3, 4]:
                if pct_0_4 <= pct_5_9:
                    return None

            return {
                "mode": "KIDRACKS",
                "type": "OVER",
                "barrier": barrier,
            }

        # 6-9 = UNDER
        if barrier in [6, 7, 8, 9]:

            if barrier == 8 and pct_8_9 >= 20:
                return None

            if barrier in [6, 7]:
                pct_6_9 = self.sum_pct(6, 9)
                pct_0_4_check = self.sum_pct(0, 4)
                if pct_6_9 <= pct_0_4_check:
                    return None

            return {
                "mode": "KIDRACKS",
                "type": "UNDER",
                "barrier": barrier,
            }

        # Barrier 5 logic
        if barrier == 5:
            pct_0_4 = self.sum_pct(0, 4)
            pct_6_9 = self.sum_pct(6, 9)

            if pct_0_4 < pct_6_9:
                return {"mode": "KIDRACKS", "type": "UNDER", "barrier": 5}

            if pct_6_9 < pct_0_4:
                return {"mode": "KIDRACKS", "type": "OVER", "barrier": 5}

        return None

    # ==============================
    # KOOLKIDSPEED AUTO SIGNAL
    # ==============================
    def check_koolkidspeed_signal(self):
        if self.tick_count < 100:
            return None

        barrier = int(self.koolkidspeed_barrier)

        pct_0_5 = self.sum_pct(0, 5)
        pct_6_9 = self.sum_pct(6, 9)

        diff = abs(pct_0_5 - pct_6_9)

        # must have dominance difference
        if diff < self.koolkidspeed_min_diff:
            return None

        # 🔹 YOUR EXTRA RULE:
        # If barrier is from 0-5 do OVER when 0-5 is dominant
        # If barrier is from 6-9 do UNDER when 6-9 is dominant

        if 0 <= barrier <= 5:
            if pct_0_5 > pct_6_9:
                return {
                    "mode": "KOOLKIDSPEED",
                    "type": "OVER",
                    "barrier": barrier,
                }
            return None

        if 6 <= barrier <= 9:
            if pct_6_9 > pct_0_5:
                return {
                    "mode": "KOOLKIDSPEED",
                    "type": "UNDER",
                    "barrier": barrier,
                }
            return None

        return None

    # ==============================
    # KOOLLUCK AUTO SIGNAL (SEQUENCE)
    # ==============================
    def _ensure_koolluck_sequence(self):
        """
        Pick a random sequence if we don't have one or if we finished the last one.
        This is what keeps KOOL🍀LUCK always random.
        """
        if (
            self.koolluck_current_sequence is None
            or self.koolluck_index >= len(self.koolluck_current_sequence)
        ):
            self.koolluck_current_sequence = random.choice(self.koolluck_sequences)
            self.koolluck_index = 0

    def check_koolluck_signal(self):
        if self.tick_count < 100:
            return None

        self._ensure_koolluck_sequence()

        if not self.koolluck_current_sequence:
            return None

        step = self.koolluck_current_sequence[self.koolluck_index]
        self.koolluck_index += 1

        # step already has type + barrier
        return {
            "mode": "KOOLLUCK",
            "type": step["type"],
            "barrier": step["barrier"],
        }

    # ==============================
    # SERVER CALLS THIS EVERY TICK
    # ==============================
    def check_auto_trade_signal(self):
        """
        Returns list of signals because all 3 modes can trade independently.
        KIDRACKS, KOOLKIDSPEED, KOOLLUCK.
        """
        if self.tick_count < 100:
            return None

        signals = []

        if self.kidracks_auto and self.can_trade_kidracks():
            sig = self.check_kidracks_signal()
            if sig:
                signals.append(sig)
                self.mark_kidracks_trade()

        if self.koolkidspeed_auto and self.can_trade_koolkidspeed():
            sig = self.check_koolkidspeed_signal()
            if sig:
                signals.append(sig)
                self.mark_koolkidspeed_trade()

        if self.koolluck_auto and self.can_trade_koolluck():
            sig = self.check_koolluck_signal()
            if sig:
                signals.append(sig)
                self.mark_koolluck_trade()

        if len(signals) == 0:
            return None

        return signals

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
