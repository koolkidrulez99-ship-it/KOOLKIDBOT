from __future__ import annotations

import math
import time
import uuid
from collections import Counter, deque
from datetime import datetime, timedelta, timezone

from strategies.koolkid import KoolKidStrategy


JAMAICA_TZ = timezone(timedelta(hours=-5), "EST")
MODE_TARGETS = {"SAFE": 12, "MODERATE": 20, "AGGRESSIVE": 30}
MODE_THRESHOLDS = {
    "SAFE": (72.0, 70.0),
    "MODERATE": (64.0, 60.0),
    "AGGRESSIVE": (56.0, 50.0),
}
MODE_TRADE_TYPES = {"digit_differs", "under9", "over0"}
SUPPORTED_TRADE_TYPES = {
    "kidpairs",
    "over3_analysis",
    "mpull_over5",
    "under9",
    "over0",
    "digit_differs",
    "kid100wins",
}


def _float(value, fallback=0.0):
    try:
        number = float(value)
        return number if math.isfinite(number) else float(fallback)
    except Exception:
        return float(fallback)


def _int(value, fallback=0):
    try:
        return int(float(value))
    except Exception:
        return int(fallback)


def _bool(value, fallback=False):
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return bool(fallback)
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _day_key(now_ts=None):
    return datetime.fromtimestamp(float(now_ts or time.time()), JAMAICA_TZ).strftime("%Y-%m-%d")


def _normalize_markets(value):
    if isinstance(value, str):
        value = value.replace("\n", ",").replace(";", ",").split(",")
    out = []
    for item in value or []:
        symbol = str(item or "").strip().upper()
        if symbol and symbol not in out:
            out.append(symbol)
    return out or ["R_10", "R_25", "R_50", "R_75", "R_100"]


class CloudReinvestEngine:
    """Server-side scanner/session engine for the Reinvest Profits 100% preset."""

    strategy_name = "reinvest_profits_100"

    def __init__(self, username, client_id, settings=None, restored=None, logger=None):
        self.username = str(username or "").strip().lower()
        self.client_id = client_id or ""
        self.logger = logger
        self.settings = self.normalize_settings(settings or {})
        self.enabled = False
        self.running = False
        self.cloud_status = "Stopped"
        self.current_market = self.settings["allowed_markets"][0]
        self.current_stake = round(_float((restored or {}).get("current_stake"), self.settings["base_stake"]), 2)
        self.session_profit = round(_float((restored or {}).get("session_profit"), 0.0), 2)
        self.daily_profit = round(_float((restored or {}).get("daily_profit"), 0.0), 2)
        self.reinvest_step = max(0, _int((restored or {}).get("reinvest_step"), 0))
        self.last_trade_result = str((restored or {}).get("last_trade_result") or "")
        self.history = list((restored or {}).get("history") or [])[-500:]
        self.wins = _int((restored or {}).get("wins"), 0)
        self.losses = _int((restored or {}).get("losses"), 0)
        runtime = self.settings.get("_runtime_state") if isinstance(self.settings.get("_runtime_state"), dict) else {}
        self.trading_date = str(runtime.get("trading_date") or _day_key())
        self.daily_stop = bool(runtime.get("daily_stop"))
        self.daily_stop_reason = str(runtime.get("daily_stop_reason") or "")
        self.cycle_complete = bool(runtime.get("cycle_complete"))
        self.completed_wins = max(0, _int(runtime.get("completed_wins"), 0))
        self.session_number = max(1, _int(runtime.get("session_number"), 1))
        self.session_wins = max(0, _int(runtime.get("session_wins"), 0))
        self.session_result = str(runtime.get("session_result") or "")
        self.session_events = list(runtime.get("session_events") or [])[-100:]
        self.wait_until = max(0.0, _float(runtime.get("wait_until"), 0.0))
        self.wait_ticks_remaining = max(0, _int(runtime.get("wait_ticks_remaining"), 0))
        self.state = str(runtime.get("state") or "STOPPED")
        self.trade_locked = False
        self.open_contract_id = None
        self.pending_signal_id = ""
        self.pending_signal = None
        self.last_signal = "Ready"
        self.last_balance = 0.0
        self.last_rank_at = 0.0
        self.total_tick_count = 0
        self.buffers = {}
        self.shadow = {}
        self.market_scores = {}
        self.deep_markets = []
        self.market_cooldowns = {}
        self.last_target = runtime.get("last_target")
        self.last_target_tick = max(0, _int(runtime.get("last_target_tick"), 0))
        self._processed_contracts = set()

    def _log(self, event, **details):
        if not self.logger:
            return
        try:
            values = " ".join(f"{key}={value}" for key, value in sorted(details.items()))
            self.logger.info("cloud_reinvest user=%s event=%s %s", self.username, event, values)
        except Exception:
            pass

    @staticmethod
    def normalize_settings(settings):
        raw = dict(settings or {})
        trade_type = str(raw.get("cloud_trade_type") or "under9").strip().lower()
        mode = str(raw.get("cloud_trade_mode") or "SAFE").strip().upper()
        stake_mode = str(raw.get("stake_mode") or "FIXED").strip().upper()
        delay_unit = str(raw.get("session_delay_unit") or "seconds").strip().lower()
        kid100_mode = str(raw.get("kid100_mode") or "LOW").strip().upper()
        return {
            **raw,
            "strategy_name": "reinvest_profits_100",
            "cloud_trade_type": trade_type if trade_type in SUPPORTED_TRADE_TYPES else "under9",
            "cloud_trade_mode": mode if mode in MODE_TARGETS else "SAFE",
            "kid100_mode": kid100_mode if kid100_mode in {"LOW", "HIGH"} else "LOW",
            "stake_mode": stake_mode if stake_mode in {"FIXED", "PERCENT"} else "FIXED",
            "base_stake": max(0.35, round(_float(raw.get("base_stake"), 1.0), 2)),
            "balance_percent": max(10.0, min(20.0, _float(raw.get("balance_percent"), 10.0))),
            "allowed_markets": _normalize_markets(raw.get("allowed_markets")),
            "duration": max(1, min(10, _int(raw.get("duration"), 1))),
            "duration_unit": "t",
            "trades_per_session": max(1, min(100, _int(raw.get("trades_per_session"), 1))),
            "session_runs": max(1, min(10, _int(raw.get("session_runs"), 1))),
            "session_delay": max(1, _int(raw.get("session_delay"), 30)),
            "session_delay_unit": delay_unit if delay_unit in {"ticks", "seconds", "minutes"} else "seconds",
            "stop_after_one_win": _bool(raw.get("stop_after_one_win"), False),
            "stop_after_one_loss": _bool(raw.get("stop_after_one_loss"), False),
            "scanner_rank_interval": max(1.0, min(3.0, _float(raw.get("scanner_rank_interval"), 2.0))),
            "scanner_top_count": max(3, min(5, _int(raw.get("scanner_top_count"), 5))),
            "scanner_cooldown_seconds": max(5.0, min(15.0, _float(raw.get("scanner_cooldown_seconds"), 8.0))),
            "minimum_history": max(100, min(500, _int(raw.get("minimum_history"), 100))),
            "min_profit_percent": max(0.0, _float(raw.get("min_profit_percent"), 0.0)),
            "max_signal_age_ticks": max(2, min(5, _int(raw.get("max_signal_age_ticks"), 3))),
            "target_cooldown_ticks": max(1, _int(raw.get("target_cooldown_ticks"), 10)),
            "allow_auto_resume": _bool(raw.get("allow_auto_resume"), True),
            "compound_percent": 100.0,
        }

    def update_settings(self, settings=None):
        previous = self.settings
        self.settings = self.normalize_settings({**previous, **(settings or {})})
        if previous.get("cloud_trade_type") != self.settings["cloud_trade_type"]:
            self._clear_scanner("trade type changed")
        if self.current_market not in self.settings["allowed_markets"]:
            self.current_market = self.settings["allowed_markets"][0]
        if not self.trade_locked and not self.open_contract_id and self.state not in {"SESSION_WAIT", "DAILY_STOP_LOSS", "DAILY_STOP_WIN"}:
            self.current_stake = self._base_stake(self.last_balance)

    def _clear_scanner(self, reason=""):
        self.buffers.clear()
        self.shadow.clear()
        self.market_scores.clear()
        self.deep_markets = []
        self.pending_signal = None
        self.pending_signal_id = ""
        self.last_signal = reason or "Collecting market data"

    def _base_stake(self, balance=None):
        if self.settings["stake_mode"] == "PERCENT":
            available = max(0.0, _float(balance, self.last_balance))
            if available <= 0:
                return round(float(self.settings["base_stake"]), 2)
            return round(max(0.35, available * (float(self.settings["balance_percent"]) / 100.0)), 2)
        return round(float(self.settings["base_stake"]), 2)

    def _reset_daily_if_needed(self, now_ts):
        today = _day_key(now_ts)
        if today == self.trading_date:
            return
        self.trading_date = today
        self.daily_stop = False
        self.daily_stop_reason = ""
        self.cycle_complete = False
        self.completed_wins = 0
        self.session_number = 1
        self.session_wins = 0
        self.session_result = ""
        self.daily_profit = 0.0
        self.current_stake = self._base_stake(self.last_balance)
        self.state = "SCANNING" if self.running else "STOPPED"

    def start(self, client_id=None):
        if client_id:
            self.client_id = client_id
        self.enabled = True
        self.running = True
        self._reset_daily_if_needed(time.time())
        if self.daily_stop:
            self.state = self.daily_stop_reason or "DAILY_STOP_LOSS"
            self.cloud_status = self.state
            self.last_signal = "Daily stop remains active until the next trading day."
            return
        self.state = "COLLECTING_DATA"
        self.cloud_status = "Running"
        self.current_stake = self._base_stake(self.last_balance)
        self.last_signal = "Collecting market data"
        self._log("started", trade_type=self.settings["cloud_trade_type"], markets=len(self.settings["allowed_markets"]), stake_mode=self.settings["stake_mode"])

    def stop(self, reason="Stopped"):
        self.enabled = False
        self.running = False
        self.trade_locked = False
        self.pending_signal = None
        self.pending_signal_id = ""
        self.state = "STOPPED"
        self.cloud_status = reason or "Stopped"
        self.last_signal = self.cloud_status
        self._log("stopped", reason=self.cloud_status)

    def needed_symbols(self):
        return list(self.settings["allowed_markets"]) if self.running else []

    def _market(self, symbol):
        symbol = str(symbol or "").upper()
        if symbol not in self.buffers:
            self.buffers[symbol] = {
                "digits": deque(maxlen=120),
                "prices": deque(maxlen=120),
                "tick": 0,
                "last_at": 0.0,
            }
            self.shadow[symbol] = KoolKidStrategy()
        return self.buffers[symbol]

    def _cheap_score(self, market, now_ts):
        digits = list(market["digits"])
        if len(digits) < 25:
            return 0.0
        counts = Counter(digits[-50:])
        spread = max(counts.values() or [0]) - min([counts.get(d, 0) for d in range(10)] or [0])
        freshness = max(0.0, 10.0 - max(0.0, now_ts - market["last_at"]))
        movement = len(set(digits[-20:]))
        return round((spread * 2.0) + movement + freshness, 2)

    def _rerank(self, now_ts):
        if now_ts - self.last_rank_at < float(self.settings["scanner_rank_interval"]):
            return
        self.last_rank_at = now_ts
        rows = []
        for symbol, market in self.buffers.items():
            score = self._cheap_score(market, now_ts)
            self.market_scores[symbol] = score
            if len(market["digits"]) >= self.settings["minimum_history"] and now_ts - market["last_at"] <= 10:
                rows.append((score, symbol))
        rows.sort(reverse=True)
        previous = tuple(self.deep_markets)
        self.deep_markets = [symbol for _score, symbol in rows[: self.settings["scanner_top_count"]]]
        if tuple(self.deep_markets) != previous:
            self._log("ranked", top=",".join(self.deep_markets))

    def _frequency_snapshot(self, digits):
        snapshots = {}
        for size in (25, 50, 100):
            window = list(digits)[-size:]
            counts = Counter(window)
            snapshots[size] = {d: (counts.get(d, 0) * 100.0 / len(window)) if window else 0.0 for d in range(10)}
        return snapshots

    def _differ_candidate(self, market):
        digits = list(market["digits"])
        if len(digits) < self.settings["minimum_history"]:
            return None
        frequencies = self._frequency_snapshot(digits)
        mode = self.settings["cloud_trade_mode"]
        min_signal, min_quality = MODE_THRESHOLDS[mode]
        long_values = list(frequencies[100].values())
        concentration = max(long_values) - min(long_values)
        disagreement = sum(abs(frequencies[25][d] - frequencies[100][d]) for d in range(10)) / 10.0
        quality = max(0.0, min(100.0, 82.0 - disagreement * 2.0 - max(0.0, concentration - 12.0)))
        best = None
        for digit in range(10):
            long_pct = frequencies[100][digit]
            medium_pct = frequencies[50][digit]
            short_pct = frequencies[25][digit]
            anomaly = max(0.0, short_pct - long_pct)
            distance = next((idx for idx, value in enumerate(reversed(digits)) if value == digit), len(digits))
            score = 100.0 - (long_pct * 3.0 + medium_pct * 2.0 + short_pct) + min(12.0, distance * 0.6) - anomaly * 2.5
            row = {"digit": digit, "score": round(score, 2), "quality": round(quality, 2), "frequencies": frequencies}
            if best is None or row["score"] > best["score"]:
                best = row
        if not best or best["score"] < min_signal or best["quality"] < min_quality:
            return None
        if self.last_target == best["digit"] and market["tick"] - self.last_target_tick < self.settings["target_cooldown_ticks"]:
            return None
        return best

    def _existing_strategy_signal(self, symbol, market):
        trade_type = self.settings["cloud_trade_type"]
        strat = self.shadow[symbol]
        signal = None
        if trade_type == "kidpairs":
            strat.kidpairs_trades_per_signal = 1
            signal = strat.check_kidpairs_signal()
        elif trade_type == "over3_analysis":
            signal = strat.check_over3_analysis_signal()
        elif trade_type == "mpull_over5":
            signal = strat.check_mpull_signal()
        if not signal:
            return None
        return {"contract_type": "OVER", "barrier": 1, "score": self.market_scores.get(symbol, 0.0), "source_signal": signal}

    def _analyze(self, symbol, market):
        trade_type = self.settings["cloud_trade_type"]
        digits = list(market["digits"])
        if len(digits) < self.settings["minimum_history"]:
            return None
        if trade_type in {"kidpairs", "over3_analysis", "mpull_over5"}:
            return self._existing_strategy_signal(symbol, market)
        if trade_type == "digit_differs":
            row = self._differ_candidate(market)
            return ({"contract_type": "DIFFERS", "barrier": row["digit"], **row} if row else None)
        frequencies = self._frequency_snapshot(digits)
        if trade_type == "under9" and digits[-1] == 9 and frequencies[100][9] <= 9.0:
            return {"contract_type": "UNDER", "barrier": 9, "score": 100.0 - frequencies[100][9]}
        if trade_type == "over0" and digits[-1] == 0 and frequencies[100][0] <= 9.0:
            return {"contract_type": "OVER", "barrier": 0, "score": 100.0 - frequencies[100][0]}
        if trade_type == "kid100wins":
            counts = Counter(digits[-100:])
            reverse = self.settings["kid100_mode"] == "HIGH"
            target = sorted(range(10), key=lambda d: (counts.get(d, 0), d), reverse=reverse)[0]
            if digits[-1] == target and market["tick"] - self.last_target_tick >= 5:
                return {"contract_type": "DIFFERS", "barrier": target, "score": float(counts.get(target, 0))}
        return None

    def _waiting(self, now_ts):
        if self.state != "SESSION_WAIT":
            return False
        if self.settings["session_delay_unit"] == "ticks":
            return self.wait_ticks_remaining > 0
        return now_ts < self.wait_until

    def _start_next_session(self):
        if self.session_number >= self.settings["session_runs"]:
            self.running = False
            self.enabled = False
            self.cycle_complete = True
            self.state = "CYCLE_COMPLETE"
            self.cloud_status = "Cycle complete"
            self.last_signal = "All configured sessions are complete."
            return
        self.session_number += 1
        self.session_wins = 0
        self.session_result = ""
        self.current_stake = self._base_stake(self.last_balance)
        self.reinvest_step = 0
        self.state = "SCANNING"
        self.cloud_status = "Running"
        self.last_signal = f"Session {self.session_number} scanning"

    def _finish_session(self, result, now_ts):
        self.session_result = result
        self._record_session_event(result, now_ts)
        self.current_stake = self._base_stake(self.last_balance)
        self.reinvest_step = 0
        delay = self.settings["session_delay"]
        unit = self.settings["session_delay_unit"]
        self.state = "SESSION_WAIT"
        self.wait_ticks_remaining = delay if unit == "ticks" else 0
        self.wait_until = now_ts + (delay * 60.0 if unit == "minutes" else delay) if unit != "ticks" else 0.0
        self.last_signal = f"Session {self.session_number} {result}. Waiting before next session."

    def _record_session_event(self, result, now_ts):
        outcome = str(result or "").upper()
        if outcome not in {"WON", "LOST"}:
            return
        label = "Target profit hit" if outcome == "WON" else "Session loss"
        self.session_events.append({
            "id": uuid.uuid4().hex,
            "session_number": int(self.session_number),
            "result": outcome,
            "label": f"{label} for session {self.session_number}",
            "time": datetime.fromtimestamp(float(now_ts), timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        })
        self.session_events = self.session_events[-100:]

    def clear_session_event(self, event_id):
        key = str(event_id or "").strip()
        before = len(self.session_events)
        self.session_events = [item for item in self.session_events if str((item or {}).get("id") or "") != key]
        return len(self.session_events) != before

    def reset_after_history_clear(self):
        self.stop("Stopped")
        self.history = []
        self.wins = 0
        self.losses = 0
        self.daily_profit = 0.0
        self.session_profit = 0.0
        self.current_stake = self._base_stake(self.last_balance)
        self.current_market = self.settings["allowed_markets"][0]
        self.reinvest_step = 0
        self.completed_wins = 0
        self.session_number = 1
        self.session_wins = 0
        self.session_result = ""
        self.daily_stop = False
        self.daily_stop_reason = ""
        self.cycle_complete = False
        self.wait_until = 0.0
        self.wait_ticks_remaining = 0
        self.open_contract_id = None
        self.pending_signal = None
        self.pending_signal_id = ""
        self.last_target = None
        self.last_target_tick = 0
        self.buffers.clear()
        self.shadow.clear()
        self.market_scores.clear()
        self.deep_markets = []
        self.market_cooldowns.clear()
        self.total_tick_count = 0
        self.last_trade_result = ""
        self.last_signal = "History and Cloud engine cleared"

    def on_tick(self, tick, digit, *, balance=None, now_ts=None):
        if not self.running:
            return []
        now_ts = float(now_ts or time.time())
        self.last_balance = max(0.0, _float(balance, self.last_balance))
        if self.settings["stake_mode"] == "PERCENT" and self.session_wins == 0 and self.reinvest_step == 0 and not self.trade_locked:
            self.current_stake = self._base_stake(self.last_balance)
        self._reset_daily_if_needed(now_ts)
        if self.daily_stop or self.cycle_complete:
            return []
        symbol = str((tick or {}).get("symbol") or "").upper()
        if self.state == "SESSION_WAIT":
            if self.settings["session_delay_unit"] == "ticks" and symbol == str(self.current_market).upper() and self.wait_ticks_remaining > 0:
                self.wait_ticks_remaining -= 1
            if not self._waiting(now_ts):
                self._start_next_session()
            return []
        if symbol not in self.settings["allowed_markets"]:
            return []
        try:
            digit = int(digit)
            quote = float((tick or {}).get("quote"))
        except Exception:
            return []
        if digit < 0 or digit > 9:
            return []
        market = self._market(symbol)
        market["digits"].append(digit)
        market["prices"].append(quote)
        market["tick"] += 1
        market["last_at"] = now_ts
        self.total_tick_count += 1
        try:
            self.shadow[symbol].on_tick(tick, digit)
        except TypeError:
            self.shadow[symbol].on_tick(tick, digit)
        if len(market["digits"]) == self.settings["minimum_history"]:
            self.last_rank_at = 0.0
        self._rerank(now_ts)
        if self.trade_locked or self.open_contract_id:
            return []
        if len(market["digits"]) < self.settings["minimum_history"]:
            self.state = "COLLECTING_DATA"
            self.last_signal = "Collecting at least 100 ticks per eligible market"
            return []
        self.state = "SCANNING"
        if symbol not in self.deep_markets or now_ts < self.market_cooldowns.get(symbol, 0.0):
            return []
        candidate = self._analyze(symbol, market)
        if not candidate:
            self.market_cooldowns[symbol] = now_ts + self.settings["scanner_cooldown_seconds"]
            self._log("setup_rejected", symbol=symbol, reason="STRATEGY_CONDITIONS_NOT_MET", cooldown=self.settings["scanner_cooldown_seconds"])
            return []
        self.current_market = symbol
        self.pending_signal_id = f"cloud-reinvest:{symbol}:{market['tick']}:{int(now_ts * 1000)}"
        self.pending_signal = {**candidate, "symbol": symbol, "tick": market["tick"]}
        self.trade_locked = True
        self.state = "SETUP_FOUND"
        self.last_signal = f"{self.settings['cloud_trade_type']} setup found on {symbol}"
        self._log("setup_accepted", symbol=symbol, trade_type=self.settings["cloud_trade_type"], contract=candidate["contract_type"], barrier=candidate["barrier"], score=candidate.get("score"))
        return [{
            "type": "trade",
            "intent": {
                "signal_id": self.pending_signal_id,
                "symbol": symbol,
                "stake": round(float(self.current_stake), 2),
                "duration": self.settings["duration"],
                "duration_unit": "t",
                "contract_type": candidate["contract_type"],
                "deriv_contract_type": f"DIGIT{candidate['contract_type']}",
                "barrier": int(candidate["barrier"]),
                "cloud_trade_type": self.settings["cloud_trade_type"],
                "signal_tick": market["tick"],
                "max_signal_age_ticks": self.settings["max_signal_age_ticks"],
                "min_profit_percent": self.settings["min_profit_percent"],
            },
            "analysis": candidate,
        }]

    def mark_trade_sent(self, signal_id):
        if signal_id != self.pending_signal_id:
            return
        self.state = "BUYING"
        self.cloud_status = "Buying"

    def pending_trade_valid(self, signal_id):
        if not self.running or self.daily_stop or self.cycle_complete:
            return False, "Cloud session is no longer accepting entries."
        if not self.trade_locked or signal_id != self.pending_signal_id or not self.pending_signal:
            return False, "Cloud signal is no longer active."
        symbol = str(self.pending_signal.get("symbol") or "").upper()
        market = self.buffers.get(symbol) or {}
        age = _int(market.get("tick"), 0) - _int(self.pending_signal.get("tick"), 0)
        if age > self.settings["max_signal_age_ticks"]:
            return False, "Cloud signal expired before purchase."
        if time.time() - _float(market.get("last_at"), 0.0) > 10.0:
            return False, "Cloud market ticks are stale."
        return True, ""

    def mark_trade_open(self, contract_id, meta=None):
        self.open_contract_id = str(contract_id or "")
        self.state = "TRADE_OPEN"
        self.cloud_status = "Trade open"

    def mark_trade_failed(self, reason):
        failed_symbol = str((self.pending_signal or {}).get("symbol") or self.current_market).upper()
        if failed_symbol:
            self.market_cooldowns[failed_symbol] = time.time() + self.settings["scanner_cooldown_seconds"]
        self.trade_locked = False
        self.open_contract_id = None
        self.pending_signal_id = ""
        self.pending_signal = None
        self.state = "SCANNING" if self.running else "STOPPED"
        self.cloud_status = "Running" if self.running else "Stopped"
        self.last_trade_result = "FAILED"
        self.last_signal = str(reason or "Trade failed")
        self._log("trade_failed", symbol=failed_symbol, reason=self.last_signal)

    def mark_close_failed(self, reason):
        self.last_signal = str(reason or "Close failed")

    def on_contract_result(self, contract, meta, profit):
        contract_id = str((contract or {}).get("contract_id") or self.open_contract_id or "")
        if contract_id and contract_id in self._processed_contracts:
            return {"duplicate": True, "result": self.last_trade_result, "profit": 0.0}
        if contract_id:
            self._processed_contracts.add(contract_id)
        now_ts = time.time()
        profit = round(_float(profit), 2)
        won = profit > 0
        result = "WIN" if won else ("BREAKEVEN" if profit == 0 else "LOSS")
        previous_stake = round(float(self.current_stake), 2)
        self.session_profit = round(self.session_profit + profit, 2)
        self.daily_profit = round(self.daily_profit + profit, 2)
        self.last_trade_result = result
        if won:
            self.wins += 1
            self.completed_wins += 1
            self.session_wins += 1
            self.reinvest_step += 1
            self.current_stake = round(max(0.35, previous_stake + profit), 2)
        elif result == "LOSS":
            self.losses += 1
        signal = dict(self.pending_signal or {})
        self.last_target = signal.get("barrier")
        self.last_target_tick = _int(signal.get("tick"), self.total_tick_count)
        self.trade_locked = False
        self.open_contract_id = None
        self.pending_signal_id = ""
        self.pending_signal = None
        action = "Reinvested 100% of settled profit" if won else "Session lost; remaining session trades cancelled"
        if won and self.settings["stop_after_one_win"]:
            self.daily_stop = True
            self.daily_stop_reason = "DAILY_STOP_WIN"
        elif result == "LOSS" and self.settings["stop_after_one_loss"]:
            self.daily_stop = True
            self.daily_stop_reason = "DAILY_STOP_LOSS"
        if self.daily_stop:
            self.state = self.daily_stop_reason
            self.cloud_status = self.daily_stop_reason
            self.current_stake = self._base_stake(self.last_balance)
            action = "Daily stop activated"
        else:
            required = MODE_TARGETS[self.settings["cloud_trade_mode"]] if self.settings["cloud_trade_type"] in MODE_TRADE_TYPES else self.settings["trades_per_session"]
            if result == "LOSS":
                self._finish_session("LOST", now_ts)
            elif self.session_wins >= required:
                self._finish_session("WON", now_ts)
            else:
                self.state = "SCANNING_AGAIN"
                self.cloud_status = "Running"
        row = {
            "strategy": "REINVEST PROFITS 100%",
            "trade_type": self.settings["cloud_trade_type"],
            "market": signal.get("symbol") or self.current_market,
            "contract_id": contract_id,
            "stake": previous_stake,
            "profit": profit,
            "result": result,
            "action": action,
            "next_stake": self.current_stake,
            "reinvest_step": self.reinvest_step,
            "session_number": self.session_number,
            "session_result": self.session_result,
            "proposal_id": (meta or {}).get("proposal_id"),
            "buy_price": (meta or {}).get("proposal_ask_price", previous_stake),
            "payout": (meta or {}).get("proposal_payout"),
            "proposal_profit_percent": (meta or {}).get("proposal_profit_percent"),
        }
        self.history.append({"time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), **row})
        self.history = self.history[-500:]
        self._log("trade_settled", contract_id=contract_id, result=result, profit=profit, session=self.session_number, next_stake=self.current_stake)
        return row

    def status(self):
        required = MODE_TARGETS[self.settings["cloud_trade_mode"]] if self.settings["cloud_trade_type"] in MODE_TRADE_TYPES else self.settings["trades_per_session"]
        return {
            "status": "success",
            "strategy_name": self.strategy_name,
            "cloud_enabled": self.enabled,
            "running": self.running,
            "cloud_status": self.cloud_status,
            "state": self.state,
            "current_market": self.current_market,
            "allowed_markets": list(self.settings["allowed_markets"]),
            "current_stake": self.current_stake,
            "base_stake": self.settings["base_stake"],
            "session_profit": self.session_profit,
            "daily_profit": self.daily_profit,
            "reinvest_step": self.reinvest_step,
            "last_trade_result": self.last_trade_result,
            "last_signal": self.last_signal,
            "trade_locked": self.trade_locked,
            "open_contract_id": self.open_contract_id,
            "wins": self.wins,
            "losses": self.losses,
            "completed_wins": self.completed_wins,
            "mode_target": required,
            "session_wins": self.session_wins,
            "session_number": self.session_number,
            "session_runs": self.settings["session_runs"],
            "session_result": self.session_result,
            "session_events": list(self.session_events),
            "daily_stop": self.daily_stop,
            "daily_stop_reason": self.daily_stop_reason,
            "deep_markets": list(self.deep_markets),
            "market_scores": dict(self.market_scores),
            "wait_until": self.wait_until,
            "wait_ticks_remaining": self.wait_ticks_remaining,
            "settings": dict(self.settings),
            "compound_percent": 100.0,
        }

    def runtime_state(self):
        return {
            "trading_date": self.trading_date,
            "daily_stop": self.daily_stop,
            "daily_stop_reason": self.daily_stop_reason,
            "cycle_complete": self.cycle_complete,
            "completed_wins": self.completed_wins,
            "session_number": self.session_number,
            "session_wins": self.session_wins,
            "session_result": self.session_result,
            "session_events": list(self.session_events),
            "wait_until": self.wait_until,
            "wait_ticks_remaining": self.wait_ticks_remaining,
            "state": self.state,
            "last_target": self.last_target,
            "last_target_tick": self.last_target_tick,
            "daily_profit": self.daily_profit,
            "wins": self.wins,
            "losses": self.losses,
        }

    def export_state(self):
        return {**self.status(), "history": list(self.history)}
