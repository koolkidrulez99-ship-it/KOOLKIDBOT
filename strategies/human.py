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

        if profit > 0:
            self.total_wins += 1
            self.total_profit += profit
        else:
            self.total_losses += 1
            self.total_loss += abs(profit)

        self.session_profit += profit

        entry = {
            "time": self.now_time(),
            "result": result,
            "profit": round(profit, 2),
            "contract_type": contract_type,
            "buy_price": round(buy_price, 2),
            "balance": round(float(balance), 2),
            "symbol": contract.get("underlying", self.symbol or ""),
        }

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

    def enforce_tp_sl(self):
        if self.tp > 0 and self.session_profit >= self.tp:
            self.auto_trade = False
            return "TP HIT"
        if self.sl > 0 and self.session_profit <= -abs(self.sl):
            self.auto_trade = False
            return "SL HIT"
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