from collections import deque, Counter
from datetime import datetime
import time
from strategies.digit_stats import calculate_cold_4_score

SEQVIX_JOKERJOE_MARKETS = [
    "R_10", "R_25", "R_50", "R_75", "R_100",
    "1HZ10V", "1HZ15V", "1HZ25V", "1HZ30V", "1HZ50V", "1HZ75V", "1HZ90V", "1HZ100V",
]
SEQVIX_JOKERJOE_SLOW_MARKETS = [
    "R_10", "R_25", "R_50", "R_75", "R_100",
]
SEQVIX_JOKERJOE_SAMPLE_SIZE = 20
SEQVIX_JOKERJOE_OVERPLAY_THRESHOLD = 4


def _seqvix_jokerjoe_mode_string(symbol, digit):
    return f"SEQVIX_JJ|{str(symbol or '').upper()}|{int(digit)}"


def _parse_seqvix_jokerjoe_mode(mode_value):
    raw = str(mode_value or "").strip()
    if not raw.startswith("SEQVIX_JJ|"):
        return None
    parts = raw.split("|", 2)
    if len(parts) != 3:
        return None
    sym = str(parts[1] or "").upper().strip()
    try:
        digit = int(parts[2])
    except Exception:
        return None
    if not sym or digit < 0 or digit > 9:
        return None
    return {"symbol": sym, "digit": digit}


def _seqvix_jokerjoe_make_market_state(trades_target):
    return {
        "buffer": [],
        "state": "scanning",
        "trades_done": 0,
        "trades_target": trades_target,
        "last_tick_marker": None,
        "last_played_digit": None,
        "watch_digits": [],
        "watch_percentage": None,
        "signal_digit": None,
        "signal_order": None,
        "signal_tick_marker": None,
        "signal_from_tie": False,
        "avoid_digit": None,
        "dominant_count": 0,
        "status_text": "Scanning 20 ticks",
        "open_contract_id": None,
    }


def _seqvix_jokerjoe_detect_overplayed_digit(sample):
    counts = {d: 0 for d in range(10)}
    for value in sample or []:
        try:
            digit = int(value)
        except Exception:
            continue
        if 0 <= digit <= 9:
            counts[digit] += 1
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    if not ordered:
        return None, 0
    top_digit, top_count = ordered[0]
    second_count = ordered[1][1] if len(ordered) > 1 else 0
    if top_count >= SEQVIX_JOKERJOE_OVERPLAY_THRESHOLD and top_count > second_count:
        return top_digit, top_count
    return None, top_count


def _seqvix_jokerjoe_digit_counts(sample):
    counts = {d: 0 for d in range(10)}
    for value in sample or []:
        try:
            digit = int(value)
        except Exception:
            continue
        if 0 <= digit <= 9:
            counts[digit] += 1
    return counts


def _seqvix_jokerjoe_refresh_market_analysis(market):
    sample = list(market.get("buffer") or [])[-SEQVIX_JOKERJOE_SAMPLE_SIZE:]
    counts = _seqvix_jokerjoe_digit_counts(sample)
    avoid_digit, dominant_count = _seqvix_jokerjoe_detect_overplayed_digit(sample)
    eligible_digits = [d for d in range(10) if d != avoid_digit]
    if not eligible_digits:
        eligible_digits = list(range(10))
    min_count = min(counts[d] for d in eligible_digits) if eligible_digits else 0
    lowest_digits = [d for d in eligible_digits if counts[d] == min_count]
    if len(lowest_digits) > 1:
        min_tie_count = min(counts[d] for d in lowest_digits)
        narrower = [d for d in lowest_digits if counts[d] == min_tie_count]
        if len(narrower) == 1:
            lowest_digits = narrower
    percentage = round((float(min_count) / float(SEQVIX_JOKERJOE_SAMPLE_SIZE)) * 100.0, 1) if SEQVIX_JOKERJOE_SAMPLE_SIZE else 0.0
    market["avoid_digit"] = avoid_digit
    market["dominant_count"] = dominant_count
    market["watch_digits"] = list(lowest_digits)
    market["watch_percentage"] = percentage
    return {
        "counts": counts,
        "watch_digits": list(lowest_digits),
        "watch_percentage": percentage,
        "avoid_digit": avoid_digit,
        "dominant_count": dominant_count,
    }


def _seqvix_jokerjoe_watch_label(market):
    digits = list(market.get("watch_digits") or [])
    pct = market.get("watch_percentage")
    if not digits:
        return "Waiting for low digit"
    digit_text = "/".join(str(int(d)) for d in digits)
    pct_text = f" ({float(pct):.1f}%)" if pct is not None else ""
    avoid_digit = market.get("avoid_digit")
    if avoid_digit is not None:
        return f"Watching {digit_text}{pct_text} • avoid {int(avoid_digit)}"
    return f"Watching {digit_text}{pct_text}"


def _seqvix_jokerjoe_is_busy(run):
    return bool(run.get("awaiting_buy") or run.get("active_contract_id"))


def _seqvix_jokerjoe_normalize_market_mode(mode):
    raw = str(mode or "").upper().strip()
    return raw if raw in ("5", "10", "ENDLESS") else "5"


def _seqvix_jokerjoe_normalize_trade_mode(mode):
    raw = str(mode or "").upper().strip()
    return raw if raw in ("1", "2") else "2"


def _seqvix_jokerjoe_normalize_scan_pool(mode):
    raw = str(mode or "").upper().strip()
    return raw if raw in ("ALL", "SLOW") else "ALL"


def _seqvix_jokerjoe_markets_for_pool(scan_pool):
    pool = _seqvix_jokerjoe_normalize_scan_pool(scan_pool)
    if pool == "SLOW":
        return list(SEQVIX_JOKERJOE_SLOW_MARKETS)
    return list(SEQVIX_JOKERJOE_MARKETS)


def _seqvix_jokerjoe_trade_target(trade_mode):
    trade_mode = _seqvix_jokerjoe_normalize_trade_mode(trade_mode)
    return 1 if trade_mode == "1" else 2


def _seqvix_jokerjoe_state_sort_key(run, symbol):
    try:
        return list(run.get("scan_markets") or []).index(symbol)
    except Exception:
        return 9999


def _seqvix_jokerjoe_rotation_candidates(run):
    markets = list(run.get("scan_markets") or [])
    if not markets:
        return []
    active = set(run.get("active_syms", set()) or set())
    try:
        cursor = int(run.get("rotation_cursor", 0) or 0)
    except Exception:
        cursor = 0
    if cursor < 0:
        cursor = 0
    if markets:
        cursor = cursor % len(markets)
    ordered = markets[cursor:] + markets[:cursor]
    return [sym for sym in ordered if sym not in active]


def _seqvix_jokerjoe_clear_signal(market, next_state="waiting_for_digit", status_text=None):
    market["state"] = next_state
    market["signal_digit"] = None
    market["signal_order"] = None
    market["signal_tick_marker"] = None
    market["signal_from_tie"] = False
    if status_text is not None:
        market["status_text"] = status_text


def _seqvix_jokerjoe_ready_queue(run):
    queued = []
    for sym, market in (run.get("market_states") or {}).items():
        if not isinstance(market, dict):
            continue
        if str(market.get("state") or "") != "ready_to_trade":
            continue
        order = market.get("signal_order")
        try:
            order_key = int(order)
        except Exception:
            order_key = 10**9
        queued.append((order_key, _seqvix_jokerjoe_state_sort_key(run, sym), sym))
    queued.sort()
    return [sym for _order, _idx, sym in queued]


def _seqvix_jokerjoe_status_payload(run):
    active_symbols = sorted(run.get("active_syms", set()), key=lambda sym: _seqvix_jokerjoe_state_sort_key(run, sym))
    active_markets = []
    for sym in active_symbols:
        market = (run.get("market_states") or {}).get(sym) or {}
        target = market.get("trades_target")
        active_markets.append({
            "symbol": sym,
            "state": market.get("state", "scanning"),
            "scan_count": len(market.get("buffer") or []),
            "last_digit": market.get("last_played_digit"),
            "watch_digits": list(market.get("watch_digits") or []),
            "watch_percentage": market.get("watch_percentage"),
            "signal_digit": market.get("signal_digit"),
            "overplayed_digit": market.get("avoid_digit"),
            "overplayed_count": int(market.get("dominant_count", 0) or 0),
            "trades_done": int(market.get("trades_done", 0) or 0),
            "trades_target": (None if target is None else int(target)),
            "status_text": market.get("status_text", ""),
        })
    return {
        "market_mode": run.get("market_mode", "5"),
        "trade_mode": run.get("trade_mode", "1"),
        "scan_pool": run.get("scan_pool", "ALL"),
        "queued_signals": len(_seqvix_jokerjoe_ready_queue(run)),
        "open_trade_status": run.get("open_trade_status", ""),
        "active_markets": active_markets,
    }


def _seqvix_jokerjoe_tick_marker(tick):
    try:
        epoch = int(float(tick.get("epoch") or tick.get("timestamp") or tick.get("time") or 0))
    except Exception:
        epoch = 0
    quote = tick.get("quote")
    return f"{epoch}|{quote}"


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

        # ---------------------------
        # ⚡kidGx / 🤖AI AUTO-TRADING (NEW)
        # ---------------------------
        self.kidgx_auto = False
        self.kidgx_barrier = 5
        self.kidgx_contract_type = "DIFFERS"
        self.kidgx_last_trade_time = 0.0
        self.kidgx_cooldown_seconds = 0.0

        self.ai_auto_trading = False
        self.ai_last_trade_time = 0.0
        self.ai_cooldown_seconds = 0.0

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
        if hasattr(self, "kidgx_auto"): self.kidgx_auto = False
        if hasattr(self, "ai_auto_trading"): self.ai_auto_trading = False

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
    # kidGx / AI toggles (NEW)
    # ---------------------------
    def toggle_kidgx_auto(self, barrier: int = None):
        self.kidgx_auto = not self.kidgx_auto
        if barrier is not None:
            self.set_kidgx_barrier(barrier)
        return self.kidgx_auto

    def set_kidgx_barrier(self, barrier: int = 5):
        try:
            b = int(barrier)
        except Exception:
            b = 5
        if b < 0:
            b = 0
        if b > 9:
            b = 9
        self.kidgx_barrier = b
        return self.kidgx_barrier

    def toggle_ai_auto_trading(self):
        self.ai_auto_trading = not self.ai_auto_trading
        return self.ai_auto_trading

    def _kidgx_can_trade(self):
        return (time.time() - float(getattr(self, "kidgx_last_trade_time", 0.0))) >= float(getattr(self, "kidgx_cooldown_seconds", 0.0))

    def _kidgx_mark_trade(self):
        self.kidgx_last_trade_time = time.time()

    def _ai_can_trade(self):
        return (time.time() - float(getattr(self, "ai_last_trade_time", 0.0))) >= float(getattr(self, "ai_cooldown_seconds", 0.0))

    def _ai_mark_trade(self):
        self.ai_last_trade_time = time.time()

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
        Combines independent fast modes (kidGx / AI) with existing master-auto logic.
        """
        signals = []

        # ⚡kidGx (independent, super fast, selected barrier)
        if getattr(self, "kidgx_auto", False) and self._kidgx_can_trade():
            signals.append({
                "mode": "KIDGX",
                "type": str(getattr(self, "kidgx_contract_type", "DIFFERS") or "DIFFERS").upper(),
                "barrier": int(5 if getattr(self, "kidgx_barrier", 5) is None else getattr(self, "kidgx_barrier", 5)),
            })
            self._kidgx_mark_trade()

        # 🤖AI AUTO-TRADING (JOKERJOE) -> trade all current golden digits as DIFFERS
        if getattr(self, "ai_auto_trading", False) and self._ai_can_trade():
            golden_digits = sorted(list(getattr(self, "golden_ttl", {}).keys()))
            if golden_digits:
                for d in golden_digits:
                    signals.append({"mode": "AI_AUTO_JOKERJOE", "type": "DIFFERS", "barrier": int(d)})
                self._ai_mark_trade()

        # Existing MASTER AUTO logic
        if self.auto_trade:
            # kidX first
            sig = self._kidx_check_signal()
            if sig:
                signals.append(sig)
            else:
                # sludgeX
                if self.sludgex_auto and self.tick_count >= 100:
                    if self.sludgex_pending_digit is not None and self.sludgex_pending_start_tick is not None:
                        if (self.tick_count - self.sludgex_pending_start_tick) > self.sludgex_pending_timeout_ticks:
                            self.sludgex_pending_digit = None
                            self.sludgex_pending_start_tick = None
                        elif self.tick_count > self.sludgex_pending_start_tick and self.last_tick_digit is not None:
                            if int(self.last_tick_digit) != int(self.sludgex_pending_digit):
                                sig = {
                                    "mode": "sludgeX",
                                    "type": "DIFFERS",
                                    "barrier": int(self.sludgex_pending_digit),
                                }
                                self.sludgex_pending_digit = None
                                self.sludgex_pending_start_tick = None
                                self.sludgex_last_trade_time = time.time()
                                signals.append(sig)

                # tripleX
                sig = self._check_triplex_signal()
                if sig:
                    signals.append(sig)

        if not signals:
            return None
        if len(signals) == 1:
            return signals[0]
        return signals

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
        cold4 = calculate_cold_4_score(list(self.tick_digits))

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
                "multig": self.multig_auto,
                "kidgx": self.kidgx_auto,
                "ai_auto_trading": self.ai_auto_trading,
            },

            "auto_settings": {
                "kidgx_barrier": int(5 if getattr(self, "kidgx_barrier", 5) is None else getattr(self, "kidgx_barrier", 5)),
            },

            "differs_analysis": {
                "green_digits": green_digits,
                "golden_digits": golden_digits
            },

            "cold4_score": cold4,

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

# ==================== ADVANCED NAMED AI MODES PATCH (non-destructive wrapper) ====================
def _jj_adv_mode_keys():
    return ("kidbrain", "edge_brain", "smart_flow", "meta_ai", "kidracks_ai")

def _jj_adv_init_state(self):
    self._adv_named_modes = {k: False for k in _jj_adv_mode_keys()}
    self._adv_mode_last_trade = {k: 0.0 for k in _jj_adv_mode_keys()}
    self._adv_loss_streak = 0
    self._adv_win_streak = 0
    self._adv_pause_until = 0.0
    self._adv_shadow = {"live_wins": 0, "live_losses": 0, "alt_wins": 0, "alt_losses": 0, "sample": 0}
    self._adv_shadow_live_pending = None
    self._adv_shadow_alt_pending = None
    self._adv_last_meta = {"regime": "WARMUP", "confidence_pct": 0.0, "edge_gap": 0.0, "market_score": 0.0, "consensus": 0}

def _jj_toggle_named_ai_mode(self, mode_key):
    mk = str(mode_key or "").strip().lower()
    if mk not in _jj_adv_mode_keys():
        raise ValueError(f"Invalid mode: {mode_key}")
    self._adv_named_modes[mk] = not bool(self._adv_named_modes.get(mk, False))
    if self._adv_named_modes[mk]:
        self._adv_mode_last_trade[mk] = 0.0
    return bool(self._adv_named_modes[mk])

def _jj_get_named_ai_modes_state(self):
    return dict(getattr(self, "_adv_named_modes", {}) or {})

def _jj_eval_contract_result(contract_type, barrier, digit):
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

def _jj_adv_resolve_pending_shadow(self, digit):
    for key in ("_adv_shadow_live_pending", "_adv_shadow_alt_pending"):
        pred = getattr(self, key, None)
        if not pred:
            continue
        res = _jj_eval_contract_result(pred.get("type"), pred.get("barrier"), digit)
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

def _jj_adv_snapshot(self):
    if int(getattr(self, "tick_count", 0) or 0) < 100:
        snap = {"regime":"WARMUP","confidence_pct":0.0,"edge_gap":0.0,"market_score":0.0,"consensus":0}
        self._adv_last_meta = dict(snap)
        return snap

    pcts = [float(getattr(self, "digit_percentages", {}).get(i, 0.0)) for i in range(10)]
    ranked_low = sorted([(pct, d) for d, pct in enumerate(pcts)], key=lambda x: (x[0], x[1]))
    ranked_high = sorted([(pct, d) for d, pct in enumerate(pcts)], key=lambda x: (-x[0], x[1]))
    lowest_pct, lowest_digit = ranked_low[0]
    second_low_pct = ranked_low[1][0] if len(ranked_low) > 1 else lowest_pct
    edge_gap = max(0.0, float(second_low_pct) - float(lowest_pct))  # for DIFFERS, larger gap on rare digit = stronger
    golden_count = len(getattr(self, "golden_ttl", {}) or {})

    seq_hint = False
    try:
        if getattr(self, "last_tick_digit", None) is not None and hasattr(self, "_current_triplex_step_digit"):
            seq_hint = int(self.last_tick_digit) == int(self._current_triplex_step_digit())
    except Exception:
        seq_hint = False

    confidence = min(95.0, (100.0 - float(lowest_pct)) * 0.65 + edge_gap * 4.0 + golden_count * 3.0)

    if golden_count >= 2 and edge_gap >= 2.0:
        regime = "BARRIER_DOMINANT"
    elif seq_hint:
        regime = "SEQUENCE"
    elif edge_gap <= 1.5:
        regime = "BALANCED"
    else:
        regime = "MIXED"

    score = confidence + (edge_gap * 1.8) + (golden_count * 2.0) - (int(getattr(self, "_adv_loss_streak", 0)) * 4)
    if regime == "SEQUENCE":
        score += 4
    if getattr(self, "_adv_pause_until", 0.0) > time.time():
        score -= 12

    snap = {
        "regime": regime,
        "confidence_pct": round(float(confidence), 1),
        "edge_gap": round(float(edge_gap), 1),
        "market_score": round(float(score), 1),
        "consensus": 0,
        "_lowest_digit": int(lowest_digit),
        "_lowest_pct": float(lowest_pct),
        "_golden_count": int(golden_count),
        "_seq_hint": bool(seq_hint),
    }
    self._adv_last_meta = dict({k:v for k,v in snap.items() if not k.startswith("_")})
    return snap

def _jj_adv_multig_like(self):
    # immediate rare-digit DIFFERS (faster variant than MultiG hold)
    try:
        ranked = sorted([(float(self.digit_percentages.get(d, 0.0)), d) for d in range(10)], key=lambda x: (x[0], x[1]))
        if not ranked:
            return None
        pct, d = ranked[0]
        if pct <= 12.0:
            return {"mode": "EDGE_BRAIN", "type": "DIFFERS", "barrier": int(d)}
    except Exception:
        pass
    return None

def _jj_adv_golden_signal(self):
    try:
        golden_digits = sorted(list((getattr(self, "golden_ttl", {}) or {}).keys()))
        if golden_digits:
            # pick most recent visible golden (highest digit tie-break is arbitrary)
            d = golden_digits[0]
            return {"mode": "META_AI", "type": "DIFFERS", "barrier": int(d)}
    except Exception:
        pass
    return None

def _jj_adv_sequence_signal(self):
    try:
        if hasattr(self, "_current_triplex_step_digit"):
            d = int(self._current_triplex_step_digit())
            # when sequence step digit is near, prepare DIFFERS on next opportunity (independent)
            return {"mode": "SMART_FLOW", "type": "DIFFERS", "barrier": d}
    except Exception:
        pass
    return None

def _jj_adv_consensus(self, snap, rare_sig, golden_sig, seq_sig):
    count = 0
    barrier = None
    for sig in (rare_sig, golden_sig, seq_sig):
        if sig and barrier is None:
            barrier = int(sig.get("barrier", 0))
    if rare_sig and snap.get("edge_gap", 0.0) >= 2.0:
        count += 1
    if golden_sig and int(snap.get("_golden_count", 0)) >= 1:
        count += 1
    if seq_sig and bool(snap.get("_seq_hint", False)):
        count += 1
    # extra vote if two or more sources point at same barrier
    barriers = [int(sig["barrier"]) for sig in (rare_sig, golden_sig, seq_sig) if sig]
    if barriers:
        if max(barriers.count(b) for b in set(barriers)) >= 2:
            count += 1
    return count

def _jj_adv_mode_cooldown(self, mode_key):
    base = 3.0 if mode_key == "meta_ai" else 5.0
    if mode_key == "smart_flow":
        base = 4.0
    if mode_key == "kidracks_ai":
        base = 6.0
    loss_streak = int(getattr(self, "_adv_loss_streak", 0) or 0)
    if loss_streak > 0:
        base += min(10.0, loss_streak * 2.0)
    return base

def _jj_adv_can_trade(self, mode_key):
    now = time.time()
    if now < float(getattr(self, "_adv_pause_until", 0.0) or 0.0):
        return False
    last_t = float((getattr(self, "_adv_mode_last_trade", {}) or {}).get(mode_key, 0.0))
    return (now - last_t) >= _jj_adv_mode_cooldown(self, mode_key)

def _jj_adv_mark_trade(self, mode_key, signal, alt_signal=None):
    self._adv_mode_last_trade[mode_key] = time.time()
    if signal:
        self._adv_shadow_live_pending = {"type": signal.get("type"), "barrier": signal.get("barrier")}
    if alt_signal:
        self._adv_shadow_alt_pending = {"type": alt_signal.get("type"), "barrier": alt_signal.get("barrier")}
    else:
        self._adv_shadow_alt_pending = None

def _jj_adv_build_signal_for_mode(self, mode_key):
    if not _jj_adv_can_trade(self, mode_key):
        return None
    snap = _jj_adv_snapshot(self)
    rare_sig = _jj_adv_multig_like(self)
    golden_sig = _jj_adv_golden_signal(self)
    seq_sig = _jj_adv_sequence_signal(self)

    def clone(sig, mode_name):
        if not sig:
            return None
        out = dict(sig)
        out["mode"] = mode_name
        return out

    if mode_key == "kidbrain":
        if snap["regime"] == "BARRIER_DOMINANT":
            chosen = clone(golden_sig or rare_sig, "KIDBRAIN")
            alt = clone(rare_sig if chosen and golden_sig else seq_sig, "KIDBRAIN_SHADOW")
        elif snap["regime"] == "SEQUENCE":
            chosen = clone(seq_sig or rare_sig, "KIDBRAIN")
            alt = clone(golden_sig, "KIDBRAIN_SHADOW")
        elif snap["regime"] == "BALANCED":
            chosen = clone(rare_sig, "KIDBRAIN")
            alt = clone(golden_sig, "KIDBRAIN_SHADOW")
        else:
            chosen = clone(golden_sig or rare_sig, "KIDBRAIN") if snap["confidence_pct"] >= 58 else None
            alt = clone(seq_sig, "KIDBRAIN_SHADOW")
        if chosen:
            _jj_adv_mark_trade(self, mode_key, chosen, alt)
        return chosen

    if mode_key == "edge_brain":
        if rare_sig and snap["edge_gap"] >= 2.0 and snap["confidence_pct"] >= 60:
            chosen = clone(rare_sig, "EDGE_BRAIN")
            _jj_adv_mark_trade(self, mode_key, chosen, clone(golden_sig, "EDGE_BRAIN_SHADOW"))
            return chosen
        return None

    if mode_key == "smart_flow":
        consensus = _jj_adv_consensus(self, snap, rare_sig, golden_sig, seq_sig)
        self._adv_last_meta["consensus"] = consensus
        primary = golden_sig or rare_sig or seq_sig
        if primary and consensus >= 2 and snap["confidence_pct"] >= 58:
            chosen = clone(primary, "SMART_FLOW")
            alt = clone(rare_sig if primary is not rare_sig else golden_sig, "SMART_FLOW_SHADOW")
            _jj_adv_mark_trade(self, mode_key, chosen, alt)
            return chosen
        return None

    if mode_key == "meta_ai":
        consensus = _jj_adv_consensus(self, snap, rare_sig, golden_sig, seq_sig)
        self._adv_last_meta["consensus"] = consensus
        if snap["confidence_pct"] < 60 or snap["edge_gap"] < 1.0:
            return None
        if snap["regime"] == "SEQUENCE" and seq_sig and consensus >= 2:
            chosen = clone(seq_sig, "META_AI")
        elif golden_sig and (consensus >= 2 or snap.get("_golden_count", 0) >= 2):
            chosen = clone(golden_sig, "META_AI")
        elif rare_sig and snap["edge_gap"] >= 2.5:
            chosen = clone(rare_sig, "META_AI")
        else:
            return None
        alt = clone(rare_sig if chosen.get("barrier") != (rare_sig or {}).get("barrier") else golden_sig, "META_AI_SHADOW")
        _jj_adv_mark_trade(self, mode_key, chosen, alt)
        return chosen

    if mode_key == "kidracks_ai":
        # "rack" here = strict rare-digit rack using stronger gap + touch filter
        try:
            if getattr(self, "last_tick_digit", None) is None:
                return None
            d = int(self.last_tick_digit)
            pct = float(getattr(self, "digit_percentages", {}).get(d, 0.0))
            if pct <= 10.0 and snap["edge_gap"] >= 1.5:
                chosen = {"mode": "KIDRACKS_AI", "type": "DIFFERS", "barrier": d}
                _jj_adv_mark_trade(self, mode_key, chosen, clone(golden_sig, "KIDRACKS_AI_SHADOW"))
                return chosen
        except Exception:
            return None
        return None

    return None

# wrappers
_JJ_ORIG_RESET = JokerJoeStrategy.reset
_JJ_ORIG_ON_TICK = JokerJoeStrategy.on_tick
_JJ_ORIG_ON_CONTRACT = JokerJoeStrategy.on_contract
_JJ_ORIG_CHECK_AUTO = JokerJoeStrategy.check_auto_trade_signal
_JJ_ORIG_GET_UI = JokerJoeStrategy.get_ui_payload
_JJ_ORIG_DISABLE_ALL = JokerJoeStrategy.disable_all_autos

def _jj_reset_wrapper(self, *args, **kwargs):
    res = _JJ_ORIG_RESET(self, *args, **kwargs)
    _jj_adv_init_state(self)
    return res

def _jj_on_tick_wrapper(self, tick, digit):
    try:
        _jj_adv_resolve_pending_shadow(self, int(digit))
    except Exception:
        pass
    res = _JJ_ORIG_ON_TICK(self, tick, digit)
    try:
        _jj_adv_snapshot(self)
    except Exception:
        pass
    return res

def _jj_on_contract_wrapper(self, contract, balance):
    res = _JJ_ORIG_ON_CONTRACT(self, contract, balance)
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

def _jj_disable_all_wrapper(self, *args, **kwargs):
    res = _JJ_ORIG_DISABLE_ALL(self, *args, **kwargs)
    try:
        if hasattr(self, "_adv_named_modes"):
            for k in list(self._adv_named_modes.keys()):
                self._adv_named_modes[k] = False
    except Exception:
        pass
    return res

def _jj_check_auto_wrapper(self):
    orig = _JJ_ORIG_CHECK_AUTO(self)
    adv_signals = []
    try:
        modes = getattr(self, "_adv_named_modes", {}) or {}
        for mk in _jj_adv_mode_keys():
            if modes.get(mk):
                sig = _jj_adv_build_signal_for_mode(self, mk)
                if sig:
                    adv_signals.append(sig)
    except Exception:
        pass

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

def _jj_get_ui_wrapper(self):
    payload = _JJ_ORIG_GET_UI(self)
    try:
        payload = dict(payload or {})
        payload.setdefault("auto_modes", {})
        payload["auto_modes"].update(_jj_get_named_ai_modes_state(self))
        snap = _jj_adv_snapshot(self)
        shadow = dict(getattr(self, "_adv_shadow", {}) or {})
        live_total = int(shadow.get("live_wins", 0)) + int(shadow.get("live_losses", 0))
        alt_total = int(shadow.get("alt_wins", 0)) + int(shadow.get("alt_losses", 0))
        shadow["live_winrate"] = round((shadow.get("live_wins", 0) / live_total) * 100.0, 1) if live_total else 0.0
        shadow["alt_winrate"] = round((shadow.get("alt_wins", 0) / alt_total) * 100.0, 1) if alt_total else 0.0
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

JokerJoeStrategy.reset = _jj_reset_wrapper
JokerJoeStrategy.on_tick = _jj_on_tick_wrapper
JokerJoeStrategy.on_contract = _jj_on_contract_wrapper
JokerJoeStrategy.disable_all_autos = _jj_disable_all_wrapper
JokerJoeStrategy.check_auto_trade_signal = _jj_check_auto_wrapper
JokerJoeStrategy.get_ui_payload = _jj_get_ui_wrapper
JokerJoeStrategy.toggle_named_ai_mode = _jj_toggle_named_ai_mode
JokerJoeStrategy.get_named_ai_modes_state = _jj_get_named_ai_modes_state
