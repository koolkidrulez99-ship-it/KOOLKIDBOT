from collections import deque
from strategies.base import BaseStrategy

class KoolKidStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()

        self.confidence_over1 = 0
        self.confidence_over2 = 0
        self.confidence_under8 = 0
        self.confidence_under9 = 0

        self.pattern_buffer = deque(maxlen=6)

    def reset(self):
        super().reset()
        self.confidence_over1 = 0
        self.confidence_over2 = 0
        self.confidence_under8 = 0
        self.confidence_under9 = 0
        self.pattern_buffer.clear()

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

    def get_ui_payload(self):
        return {
            "tick_count": self.tick_count,
            "last_digit": self.last_tick_digit,
            "percentages": self.digit_percentages,
            "confidence": {
                "over1": self.confidence_over1,
                "over2": self.confidence_over2,
                "under8": self.confidence_under8,
                "under9": self.confidence_under9
            }
        }
