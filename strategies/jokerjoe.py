from collections import deque, Counter
from datetime import datetime
import time


class JokerJoeStrategy:
    """
    JokerJoe profile strategy.

    Existing:
      - kidgambleX
      - sludgeX auto mode
      - tripleX auto mode

    NEW:
      - kidX (MASTER AUTO REQUIRED)
          * DIFFERS only
          * uses selected barrier
          * requires 100 ticks
          * barrier digit percentage must be <= 10%
          * waits until market touches barrier while still <= 10%
          * then places 3 trades over 5 ticks (spaced)
          * then cooldown 10 seconds
      - MultiG (MASTER AUTO NOT REQUIRED)
          * DIFFERS only
          * digits with percentage <= 9%
          * queues ONE digit at a time
          * holds 30 seconds before placing
          * countdown exposed to UI (shown in trade history)
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

        # Master auto toggle
        self.auto_trade = False

        # ---------------------------
        # sludgeX auto mode state
        # ---------------------------
        self.sludgex_auto = False
        self.sludgex_targets = {8, 1, 7, 2}

        self.sludgex_pending_digit = None
        self.sludgex_pending_start_tick = None
        self.sludgex_pending_timeout_ticks = 12

        self.sludgex_last_trade_time = 0.0
        self.sludgex_cooldown_seconds = 5.0

        # ---------------------------
        # Differs analysis / golden logic
        # ---------------------------
        self.last_seen_tick = {i: None for i in range(10)}
        self.golden_ttl = {}
        self.golden_show_ticks = 5

        self.analysis_interval = 5

        # ---------------------------
        # tripleX auto mode
        # ---------------------------
        self.triplex_auto = False
        self.triplex_sequences = [
            [8, 1, 7, 2],
            [9, 9, 8, 1],
            [7, 8, 9, 1],
            [1, 3, 5, 7],
            [1, 2, 4, 6],
        ]
        self.triplex_sequence_index = 0
        self.triplex_step_index = 0
        self.triplex_armed_digit = None

        # ---------------------------
        # kidX auto mode (NEW)
        # ---------------------------
        self.kidx_auto = False
        self.kidx_barrier = 5

        self.kidx_pct_threshold = 10.0
        self.kidx_trades_total = 3
        self.kidx_window_ticks = 5
        self.kidx_cooldown_seconds = 10.0
        self.kidx_last_trade_time = 0.0

        # state machine
        self.kidx_wait_for_touch = True
        self.kidx_sequence_active = False
        self.kidx_window_start_tick = None
        self.kidx_window_pos = 0
        self.kidx_trades_remaining = 0

        # spaced placements across 5 ticks -> positions 1,3,5
        self.kidx_place_positions = {1, 3, 5}

        # ---------------------------
        # MultiG auto mode (NEW)
        # ---------------------------
        self.multig_auto = False
        self.multig_pct_threshold = 9.0
        self.multig_hold_seconds = 30

        self.multig_pending_active = False
        self.multig_pending_barrier = None
        self.multig_pending_start_time = None
        self.multig_pending_due_time = None

        self.multig_last_cycle_time = 0.0
        self.multig_cycle_cooldown_seconds = 3.0  # small pause between cycles

        # Patch A: Risk Controls (Session)
        self.tp = 0.0
        self.sl = 0.0
        self.auto_sl = True
        self.session_profit = 0.0
        self.risk_block_reason = None

    def reset_tick_analysis(self):
        self.tick_count = 0
        self.tick_digits.clear()
        self.digit_percentages = {i: 0 for i in range(10)}
        self.last_tick_digit = None

        self.last_seen_tick = {i: None for i in range(10)}
        self.golden_ttl = {}

        self.sludgex_pending_digit = None
        self.sludgex_pending_start_tick = None

        self.triplex_armed_digit = None
        self.triplex_sequence_index = 0
        self.triplex_step_index = 0

        # kidX safe reset (toggle remains)
        self.kidx_sequence_active = False
        self.kidx_wait_for_touch = True
        self.kidx_window_start_tick = None
        self.kidx_window_pos = 0
        self.kidx_trades_remaining = 0

        # MultiG safe reset (toggle remains)
        self.multig_pending_active = False
        self.multig_pending_barrier = None
        self.multig_pending_start_time = None
        self.multig_pending_due_time = None

    def now_time(self):
        return datetime.now().strftime("%H:%M:%S")

    def toggle_auto(self):
        self.auto_trade = not self.auto_trade
        return self.auto_trade

    # Patch B: Add risk control methods
    def set_risk_controls(self, tp=0.0, sl=0.0, auto_sl=True):
        self.tp = float(tp)
        self.sl = float(sl)
        self.auto_sl = bool(auto_sl)

    def disable_all_autos(self):
        self.auto_trade = False
        if hasattr(self, "sludgex_auto"): self.sludgex_auto = False
        if hasattr(self, "triplex_auto"): self.triplex_auto = False
        if hasattr(self, "kidx_auto"): self.kidx_auto = False
        if hasattr(self, "multig_auto"): self.multig_auto = False

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

    def toggle_sludgex_auto(self):
        self.sludgex_auto = not self.sludgex_auto
        if self.sludgex_auto:
            self.sludgex_pending_digit = None
            self.sludgex_pending_start_tick = None
        return self.sludgex_auto

    def toggle_triplex_auto(self):
        self.triplex_auto = not self.triplex_auto
        self.triplex_armed_digit = None
        self.triplex_sequence_index = 0
        self.triplex_step_index = 0
        return self.triplex_auto

    # ---------------------------
    # kidX toggle (NEW)
    # ---------------------------
    def toggle_kidx_auto(self, barrier: int = 5):
        self.kidx_auto = not self.kidx_auto
        self.kidx_barrier = int(barrier)

        # reset state machine each toggle
        self.kidx_wait_for_touch = True
        self.kidx_sequence_active = False
        self.kidx_window_start_tick = None
        self.kidx_window_pos = 0
        self.kidx_trades_remaining = 0

        return self.kidx_auto

    # ---------------------------
    # MultiG toggle (NEW)
    # ---------------------------
    def toggle_multig_auto(self):
        self.multig_auto = not self.multig_auto

        # clear pending each toggle to avoid stale countdown
        self.multig_pending_active = False
        self.multig_pending_barrier = None
        self.multig_pending_start_time = None
        self.multig_pending_due_time = None

        return self.multig_auto

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
        if self.tick_count < 100:
            return []

        items = [(d, float(self.digit_percentages.get(d, 0.0))) for d in range(10)]
        items.sort(key=lambda x: (-x[1], x[0]))
        return [d for d, _pct in items[:n]]

    # ---------------------------
    # Golden logic (existing)
    # ---------------------------
    def _decay_golden(self):
        to_del = []
        for d in list(self.golden_ttl.keys()):
            self.golden_ttl[d] -= 1
            if self.golden_ttl[d] <= 0:
                to_del.append(d)
        for d in to_del:
            self.golden_ttl.pop(d, None)

    def _check_make_golden(self, digit):
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
    # sludgeX helpers (existing)
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
    # tripleX helpers (existing)
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
        if not self.triplex_auto:
            return None

        if self.triplex_armed_digit is not None:
            armed = self.triplex_armed_digit
            if self.last_tick_digit != armed:
                self.triplex_armed_digit = None
                sig = {
                    "mode": "tripleX",
                    "type": "DIFFERS",
                    "barrier": int(armed),
                }
                self._advance_triplex_step()
                return sig
            return None

        step_digit = self._current_triplex_step_digit()
        if int(self.last_tick_digit) == step_digit:
            self.triplex_armed_digit = step_digit
            return None

        return None

    # ---------------------------
    # kidX logic (NEW)
    # ---------------------------
    def _kidx_in_cooldown(self):
        return (time.time() - self.kidx_last_trade_time) < self.kidx_cooldown_seconds

    def _kidx_barrier_pct_ok(self):
        pct = float(self.digit_percentages.get(int(self.kidx_barrier), 0.0))
        return pct <= self.kidx_pct_threshold

    def _kidx_start_sequence(self):
        self.kidx_sequence_active = True
        self.kidx_window_start_tick = int(self.tick_count)
        self.kidx_window_pos = 0
        self.kidx_trades_remaining = int(self.kidx_trades_total)

    def _kidx_cancel_sequence(self):
        self.kidx_sequence_active = False
        self.kidx_window_start_tick = None
        self.kidx_window_pos = 0
        self.kidx_trades_remaining = 0
        self.kidx_wait_for_touch = True

    def _kidx_check_signal(self):
        """
        MASTER AUTO REQUIRED
        - after 100 ticks
        - barrier pct must stay <= 10%
        - wait for touch, then 3 trades over 5 ticks, then cooldown
        """
        if not self.auto_trade:
            return None
        if not self.kidx_auto:
            return None
        if self.tick_count < 100:
            return None
        if self._kidx_in_cooldown():
            return None

        # If pct is not ok, do nothing and reset any active sequence
        if not self._kidx_barrier_pct_ok():
            if self.kidx_sequence_active:
                self._kidx_cancel_sequence()
            return None

        # Waiting for touch
        if self.kidx_wait_for_touch and not self.kidx_sequence_active:
            if int(self.last_tick_digit) == int(self.kidx_barrier):
                # touch happened WHILE pct ok -> start sequence (no trade on same tick)
                self.kidx_wait_for_touch = False
                self._kidx_start_sequence()
            return None

        # Sequence active
        if not self.kidx_sequence_active:
            return None

        self.kidx_window_pos += 1

        # If window exceeded -> cancel (no cooldown)
        if self.kidx_window_pos > self.kidx_window_ticks:
            self._kidx_cancel_sequence()
            return None

        # If pct goes above threshold mid-sequence -> cancel immediately
        if not self._kidx_barrier_pct_ok():
            self._kidx_cancel_sequence()
            return None

        # Place trades on positions 1,3,5 (within 5 ticks)
        if self.kidx_window_pos in self.kidx_place_positions and self.kidx_trades_remaining > 0:
            self.kidx_trades_remaining -= 1

            sig = {
                "mode": "kidX",
                "type": "DIFFERS",
                "barrier": int(self.kidx_barrier),
            }

            # If finished all 3 trades -> cooldown + reset
            if self.kidx_trades_remaining <= 0:
                self.kidx_last_trade_time = time.time()
                self._kidx_cancel_sequence()

            return sig

        return None

    # ---------------------------
    # MultiG logic (NEW) - independent of master auto
    # ---------------------------
    def _multig_seconds_remaining(self):
        if not self.multig_pending_active or not self.multig_pending_due_time:
            return 0
        return max(0, int(round(self.multig_pending_due_time - time.time())))

    def _multig_pick_digit(self):
        """
        Pick one digit with pct <= 9.
        Prefer lowest pct, tie -> smaller digit.
        """
        candidates = []
        for d in range(10):
            pct = float(self.digit_percentages.get(d, 0.0))
            if pct <= self.multig_pct_threshold:
                candidates.append((pct, d))
        if not candidates:
            return None
        candidates.sort(key=lambda x: (x[0], x[1]))
        return int(candidates[0][1])

    def _multig_can_cycle(self):
        return (time.time() - self.multig_last_cycle_time) >= self.multig_cycle_cooldown_seconds

    def check_multig_signal(self):
        """
        MultiG independent of master auto.
        - requires 100 ticks (needs percentages)
        - queues one digit with pct <= 9%
        - holds 30 seconds before placing
        - re-check pct still <= 9% at execution time
        """
        if not self.multig_auto:
            return None
        if self.tick_count < 100:
            return None

        # If pending, see if due
        if self.multig_pending_active:
            if time.time() >= (self.multig_pending_due_time or 0):
                # due -> re-check digit still eligible
                d = int(self.multig_pending_barrier)
                pct = float(self.digit_percentages.get(d, 0.0))
                self.multig_pending_active = False
                self.multig_pending_barrier = None
                self.multig_pending_start_time = None
                self.multig_pending_due_time = None
                self.multig_last_cycle_time = time.time()

                if pct <= self.multig_pct_threshold:
                    return {
                        "mode": "MultiG",
                        "type": "DIFFERS",
                        "barrier": int(d)
                    }
                return None

            return None

        # Not pending: start new pending if allowed
        if not self._multig_can_cycle():
            return None

        pick = self._multig_pick_digit()
        if pick is None:
            return None

        self.multig_pending_active = True
        self.multig_pending_barrier = int(pick)
        self.multig_pending_start_time = time.time()
        self.multig_pending_due_time = self.multig_pending_start_time + float(self.multig_hold_seconds)

        return None

    # ---------------------------
    # Auto trade signals (master auto based)
    # ---------------------------
    def check_auto_trade_signal(self):
        """
        Master-auto based.
        Priority:
          1) kidX
          2) sludgeX
          3) tripleX
        """
        if not self.auto_trade:
            return None

        # kidX first
        sig = self._kidx_check_signal()
        if sig:
            return sig

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

        # tripleX
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

        self._decay_golden()

        if self.tick_count == 100 or (self.tick_count > 100 and self.tick_count % self.analysis_interval == 0):
            self.digit_percentages = self.calculate_digit_percentages()

        made_golden = self._check_make_golden(digit)
        self.last_seen_tick[digit] = self.tick_count

        if made_golden:
            self._sludgex_arm_if_needed(digit)

    def on_contract(self, contract, balance):
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

        # Patch C: track session profit and enforce TP/SL
        self.session_profit += profit
        self.enforce_tp_sl()

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
        # Patch D: reset session profit and risk_block_reason
        self.session_profit = 0.0
        self.risk_block_reason = None

    # ---------------------------
    # UI payloads
    # ---------------------------
    def get_ui_payload(self):
        green_digits = []
        if self.tick_count >= 100:
            for d in range(10):
                if float(self.digit_percentages.get(d, 0.0)) <= 10.0:
                    green_digits.append(d)

        golden_digits = sorted(list(self.golden_ttl.keys()))

        # MultiG countdown payload
        multig_payload = {"active": False}
        if self.multig_auto and self.multig_pending_active and self.multig_pending_barrier is not None:
            multig_payload = {
                "active": True,
                "barrier": int(self.multig_pending_barrier),
                "seconds_remaining": self._multig_seconds_remaining()
            }

        return {
            "tick_count": self.tick_count,
            "last_digit": self.last_tick_digit,
            "percentages": self.digit_percentages,

            "confidence": {},

            "auto_modes": {
                "sludgex": self.sludgex_auto,
                "triplex": self.triplex_auto,
                "kidx": self.kidx_auto,
                "multig": self.multig_auto
            },

            "differs_analysis": {
                "green_digits": green_digits,
                "golden_digits": golden_digits
            },

            "multig_pending": multig_payload
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
            "sludgex_auto": self.sludgex_auto,
            "triplex_auto": self.triplex_auto,
            "kidx_auto": self.kidx_auto,
            "multig_auto": self.multig_auto
        }