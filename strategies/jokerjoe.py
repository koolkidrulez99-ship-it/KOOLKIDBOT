from collections import deque, Counter
from datetime import datetime
import time


class JokerJoeStrategy:
    """
    JokerJoe profile strategy.

    Adds:
      - kidgambleX support: get_top_digits(n=3) based on 100-tick percentages.
      - sludgeX auto mode:
          * ONLY trades DIFFERS
          * ONLY for digits {8, 1, 7, 2}
          * ONLY when the digit is GOLDEN:
                - digit percentage <= 10%
                - digit was absent for >= 20 ticks
                - then digit prints again (that print creates the GOLDEN state)
          * entry timing rule:
                - do NOT enter on the same tick that digit prints
                - wait until a later tick where last digit is different
                - then place DIFFERS on the original digit barrier
      - Differs analysis payload for UI:
          * green_digits: digits with pct <= 10
          * golden_digits: digits that recently became golden

    + tripleX auto mode (added back):
          * DIFFERS only
          * sequences (step-by-step)
          * do NOT trade on the same tick digit prints
          * wait for next tick to be different, then DIFFERS that step digit
          * sequence order loops
    """

    def __init__(self):
        self.reset()

    def reset(self):
        # Tick analysis
        self.tick_count = 0
        self.tick_digits = deque(maxlen=100)
        self.digit_percentages = {i: 0 for i in range(10)}
        self.last_tick_digit = None

        # Trade stats/history
        self.trade_history = []
        self.total_wins = 0
        self.total_losses = 0
        self.total_profit = 0.0
        self.total_loss = 0.0
        self.last_trade_entry = None

        # Master auto toggle (shared concept)
        self.auto_trade = False

        # ---------------------------
        # sludgeX auto mode state
        # ---------------------------
        self.sludgex_auto = False
        self.sludgex_targets = {8, 1, 7, 2}

        # Pending “wait for different digit” trigger
        self.sludgex_pending_digit = None
        self.sludgex_pending_start_tick = None

        # Safety: if no confirmation after N ticks, cancel pending
        self.sludgex_pending_timeout_ticks = 12

        # Cooldown so sludgeX doesn't spam
        self.sludgex_last_trade_time = 0.0
        self.sludgex_cooldown_seconds = 5.0

        # ---------------------------
        # Differs analysis / golden logic
        # ---------------------------
        self.last_seen_tick = {i: None for i in range(10)}  # when each digit last printed
        self.golden_ttl = {}  # digit -> ticks remaining to display as golden
        self.golden_show_ticks = 5  # Option B: show for 5 ticks

        # Analysis recalculation interval after 100 ticks
        self.analysis_interval = 5  # Option B: every 5 ticks after 100

        # ---------------------------
        # tripleX auto mode state (ADDED BACK)
        # ---------------------------
        self.triplex_auto = False

        self.triplex_sequences = [
            [8, 1, 7, 2],
            [9, 9, 8, 1],
            [7, 8, 9, 1],
            [1, 3, 5, 7],
            [1, 2, 4, 6],
        ]
        self.triplex_sequence_index = 0  # loops
        self.triplex_step_index = 0
        self.triplex_armed_digit = None

    def reset_tick_analysis(self):
        self.tick_count = 0
        self.tick_digits.clear()
        self.digit_percentages = {i: 0 for i in range(10)}
        self.last_tick_digit = None

        self.last_seen_tick = {i: None for i in range(10)}
        self.golden_ttl = {}

        # Clear sludgeX pending (safer)
        self.sludgex_pending_digit = None
        self.sludgex_pending_start_tick = None

        # Reset tripleX internal state (toggle stays as user set)
        self.triplex_armed_digit = None
        self.triplex_sequence_index = 0
        self.triplex_step_index = 0

    def now_time(self):
        return datetime.now().strftime("%H:%M:%S")

    def toggle_auto(self):
        self.auto_trade = not self.auto_trade
        return self.auto_trade

    def toggle_sludgex_auto(self):
        self.sludgex_auto = not self.sludgex_auto

        # When turning ON, clear any stale pending state
        if self.sludgex_auto:
            self.sludgex_pending_digit = None
            self.sludgex_pending_start_tick = None

        return self.sludgex_auto

    # ---------------------------
    # tripleX toggle (ADDED BACK)
    # ---------------------------
    def toggle_triplex_auto(self):
        self.triplex_auto = not self.triplex_auto
        # reset arming state and restart sequence when toggling
        self.triplex_armed_digit = None
        self.triplex_sequence_index = 0
        self.triplex_step_index = 0
        return self.triplex_auto

    # ---------------------------
    # Percentages
    # ---------------------------
    def calculate_digit_percentages(self):
        if len(self.tick_digits) < 100:
            return {i: 0 for i in range(10)}

        counter = Counter(self.tick_digits)
        result = {}

        for digit in range(10):
            count = counter.get(digit, 0)
            pct = (count / 100) * 100
            result[digit] = round(pct, 1)

        return result

    def get_top_digits(self, n=3):
        """
        Returns the top N digits by percentage (descending).
        Only valid once we have 100 ticks.
        """
        if self.tick_count < 100:
            return []

        items = [(d, float(self.digit_percentages.get(d, 0.0))) for d in range(10)]
        items.sort(key=lambda x: (-x[1], x[0]))  # higher pct first; tie -> smaller digit
        return [d for d, _pct in items[:n]]

    # ---------------------------
    # Golden logic
    # ---------------------------
    def _decay_golden(self):
        # Decrease golden TTL each tick
        to_del = []
        for d in list(self.golden_ttl.keys()):
            self.golden_ttl[d] -= 1
            if self.golden_ttl[d] <= 0:
                to_del.append(d)
        for d in to_del:
            self.golden_ttl.pop(d, None)

    def _check_make_golden(self, digit):
        """
        A digit becomes GOLDEN when:
          - digit percentage <= 10%
          - it has NOT appeared for >= 20 ticks
          - then it appears now (this tick)
        """
        if self.tick_count < 100:
            return False

        pct = float(self.digit_percentages.get(digit, 0.0))
        if pct > 10.0:
            return False

        last_seen = self.last_seen_tick.get(digit)
        if last_seen is None:
            return False

        gap = self.tick_count - last_seen
        if gap >= 20:
            self.golden_ttl[digit] = self.golden_show_ticks
            return True

        return False

    def is_digit_golden_now(self, digit):
        return self.golden_ttl.get(int(digit), 0) > 0

    # ---------------------------
    # sludgeX signal generation
    # ---------------------------
    def _sludgex_can_trade(self):
        return (time.time() - self.sludgex_last_trade_time) >= self.sludgex_cooldown_seconds

    def _sludgex_arm_if_needed(self, digit):
        if not self.auto_trade or not self.sludgex_auto:
            return

        if not self._sludgex_can_trade():
            return

        if self.sludgex_pending_digit is not None:
            return

        if digit not in self.sludgex_targets:
            return

        if not self.is_digit_golden_now(digit):
            return

        self.sludgex_pending_digit = int(digit)
        self.sludgex_pending_start_tick = int(self.tick_count)

    # ---------------------------
    # tripleX helpers (ADDED BACK)
    # ---------------------------
    def _current_triplex_step_digit(self):
        seq = self.triplex_sequences[self.triplex_sequence_index]
        return int(seq[self.triplex_step_index])

    def _advance_triplex_step(self):
        seq = self.triplex_sequences[self.triplex_sequence_index]
        self.triplex_step_index += 1
        if self.triplex_step_index >= len(seq):
            self.triplex_step_index = 0
            self.triplex_sequence_index = (self.triplex_sequence_index + 1) % len(self.triplex_sequences)

    def _check_triplex_signal(self):
        """
        tripleX:
        - DIFFERS only
        - sequences (step-by-step)
        - do NOT trade on the same tick digit prints
        - wait for next tick to be different, then DIFFERS step digit
        - sequence order loops
        """
        if not self.triplex_auto:
            return None

        # If armed, wait for different digit to fire
        if self.triplex_armed_digit is not None:
            armed = self.triplex_armed_digit
            if self.last_tick_digit != armed:
                self.triplex_armed_digit = None

                sig = {
                    "mode": "tripleX",
                    "type": "DIFFERS",
                    "barrier": int(armed),
                }

                # advance to next step AFTER firing
                self._advance_triplex_step()
                return sig

            return None

        # Not armed: check if current digit matches step digit
        step_digit = self._current_triplex_step_digit()
        if int(self.last_tick_digit) == step_digit:
            # arm (do not trade on this tick)
            self.triplex_armed_digit = step_digit
            return None

        return None

    def check_auto_trade_signal(self):
        """
        Called by server auto engine every tick.

        Priority:
          1) sludgeX
          2) tripleX
        """
        if not self.auto_trade:
            return None

        # sludgeX
        if self.sludgex_auto and self.tick_count >= 100:
            if self.sludgex_pending_digit is not None and self.sludgex_pending_start_tick is not None:
                if (self.tick_count - self.sludgex_pending_start_tick) > self.sludgex_pending_timeout_ticks:
                    self.sludgex_pending_digit = None
                    self.sludgex_pending_start_tick = None
                    return None

                if self.tick_count <= self.sludgex_pending_start_tick:
                    return None

                if self.last_tick_digit is None:
                    return None

                if int(self.last_tick_digit) != int(self.sludgex_pending_digit):
                    sig = {
                        "mode": "sludgeX",
                        "type": "DIFFERS",
                        "barrier": int(self.sludgex_pending_digit),
                    }

                    self.sludgex_pending_digit = None
                    self.sludgex_pending_start_tick = None
                    self.sludgex_last_trade_time = time.time()
                    return sig

        # tripleX (ADDED BACK)
        sig = self._check_triplex_signal()
        if sig:
            return sig

        return None

    # ---------------------------
    # Tick & contract events
    # ---------------------------
    def on_tick(self, tick, digit):
        digit = int(digit)
        self.last_tick_digit = digit
        self.tick_count += 1
        self.tick_digits.append(digit)

        # Golden TTL decay
        self._decay_golden()

        # Update percentages every 5 ticks after 100 (Option B), and at tick 100
        if self.tick_count == 100 or (self.tick_count > 100 and self.tick_count % self.analysis_interval == 0):
            self.digit_percentages = self.calculate_digit_percentages()

        # Determine golden status BEFORE updating last_seen_tick (so gap is correct)
        made_golden = self._check_make_golden(digit)

        # Update last seen
        self.last_seen_tick[digit] = self.tick_count

        # Arm sludgeX only if digit became golden
        if made_golden:
            self._sludgex_arm_if_needed(digit)

    def on_contract(self, contract, balance):
        if not (contract.get("is_sold") or contract.get("is_settled")):
            return

        profit = float(contract.get("profit", 0))
        buy_price = float(contract.get("buy_price", 0))
        contract_type = contract.get("contract_type", "UNKNOWN")

        result = "WIN" if profit > 0 else "LOSS"

        if profit > 0:
            self.total_wins += 1
            self.total_profit += profit
        else:
            self.total_losses += 1
            self.total_loss += abs(profit)

        entry = {
            "time": self.now_time(),
            "result": result,
            "profit": round(profit, 2),
            "contract_type": contract_type,
            "buy_price": round(buy_price, 2),
            "balance": round(balance, 2),
            "symbol": contract.get("underlying", "")
        }

        self.trade_history.append(entry)
        if len(self.trade_history) > 200:
            self.trade_history.pop(0)

        self.last_trade_entry = entry

    def get_last_trade_entry(self):
        return self.last_trade_entry or {}

    def clear_history(self):
        self.trade_history = []
        self.total_wins = 0
        self.total_losses = 0
        self.total_profit = 0.0
        self.total_loss = 0.0

    # ---------------------------
    # UI payloads
    # ---------------------------
    def get_ui_payload(self):
        # Green digits: <=10%
        green_digits = []
        if self.tick_count >= 100:
            for d in range(10):
                if float(self.digit_percentages.get(d, 0.0)) <= 10.0:
                    green_digits.append(d)

        golden_digits = sorted(list(self.golden_ttl.keys()))

        return {
            "tick_count": self.tick_count,
            "last_digit": self.last_tick_digit,
            "percentages": self.digit_percentages,

            "confidence": {},

            "auto_modes": {
                "sludgex": self.sludgex_auto,
                "triplex": self.triplex_auto
            },

            "differs_analysis": {
                "green_digits": green_digits,
                "golden_digits": golden_digits
            }
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
            # expose autos
            "sludgex_auto": self.sludgex_auto,
            "triplex_auto": self.triplex_auto
        }
