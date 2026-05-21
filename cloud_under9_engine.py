from __future__ import annotations

import time
from collections import Counter, deque
from dataclasses import dataclass

from cloud_market_rotation import DEFAULT_CLOUD_MARKETS, next_market, normalize_allowed_markets, normalize_cloud_symbol
from cloud_risk import evaluate_under9_backup, merge_risk_settings


def _float_value(value, fallback):
    try:
        number = float(value)
        return number if number == number else float(fallback)
    except Exception:
        return float(fallback)


def _int_value(value, fallback):
    try:
        return int(float(value))
    except Exception:
        return int(fallback)


def _bool_value(value, fallback=False):
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return bool(fallback)
    return str(value).strip().lower() in ("1", "true", "yes", "on", "enabled")


DEFAULT_CLOUD_SETTINGS = {
    "base_stake": 1.0,
    "take_profit_target": 50.0,
    "max_reinvest_steps": 5,
    "capital_build_mode": False,
    "market_switch_minutes": 10,
    "allowed_markets": list(DEFAULT_CLOUD_MARKETS),
    "duration": 1,
    "duration_unit": "t",
    "enable_telegram_alerts": False,
    "enable_whatsapp_alerts": False,
    "allow_auto_resume": False,
    "cooldown_seconds": 2.0,
    "max_daily_loss": 0.0,
    "max_trades_per_session": 0,
    "low_balance_stop": 0.0,
    **merge_risk_settings({}),
}


@dataclass(frozen=True)
class CloudTradeIntent:
    signal_id: str
    symbol: str
    stake: float
    duration: int
    duration_unit: str
    contract_type: str = "UNDER"
    deriv_contract_type: str = "DIGITUNDER"
    barrier: int = 9

    def to_payload(self) -> dict:
        return {
            "signal_id": self.signal_id,
            "symbol": self.symbol,
            "stake": self.stake,
            "duration": self.duration,
            "duration_unit": self.duration_unit,
            "contract_type": self.contract_type,
            "deriv_contract_type": self.deriv_contract_type,
            "barrier": self.barrier,
        }


class CloudProfileStrategy:
    def __init__(self):
        self.tick_count = 0
        self.total_wins = 0
        self.total_losses = 0
        self.session_profit = 0.0
        self.last_trade_entry = {}

    def reset_tick_analysis(self):
        self.tick_count = 0

    def clear_history(self):
        self.tick_count = 0
        self.total_wins = 0
        self.total_losses = 0
        self.session_profit = 0.0
        self.last_trade_entry = {}

    def on_tick(self, _tick, _digit):
        self.tick_count += 1

    def on_contract(self, contract, balance):
        profit = _float_value((contract or {}).get("profit"), 0.0)
        result = "WIN" if profit > 0 else "LOSS"
        if result == "WIN":
            self.total_wins += 1
        else:
            self.total_losses += 1
        self.session_profit = round(float(self.session_profit or 0.0) + profit, 2)
        self.last_trade_entry = {
            "profile": "CLOUD",
            "result": result,
            "profit": round(profit, 2),
            "balance": round(_float_value(balance, 0.0), 2),
            "symbol": (contract or {}).get("underlying", ""),
        }

    def get_last_trade_entry(self):
        return dict(self.last_trade_entry)

    def get_ui_payload(self):
        return {"profile": "CLOUD", "tick_count": self.tick_count}

    def get_stats_payload(self, _balance, _session_start_balance):
        total = self.total_wins + self.total_losses
        winrate = round((self.total_wins / total) * 100, 1) if total else 0
        return {
            "balance": 0,
            "wins": self.total_wins,
            "losses": self.total_losses,
            "winrate": winrate,
            "loserate": round(100 - winrate, 1) if total else 0,
            "total_profit": max(0.0, self.session_profit),
            "total_loss": abs(min(0.0, self.session_profit)),
            "net_pnl": self.session_profit,
            "session_pnl": self.session_profit,
            "auto_trade": False,
        }


class CloudUnder9Engine:
    strategy_name = "under9_reinvest"

    def __init__(self, username: str, client_id: str, settings: dict | None = None, restored: dict | None = None, logger=None):
        self.username = str(username or "").strip().lower()
        self.client_id = client_id
        self.logger = logger
        self.settings = self.normalize_settings(settings or {})
        self.enabled = False
        self.running = False
        self.cloud_status = "Stopped"
        self.current_market = normalize_cloud_symbol(restored.get("current_market") if restored else None) or self.settings["allowed_markets"][0]
        self.current_stake = round(_float_value((restored or {}).get("current_stake"), self.settings["base_stake"]), 2)
        self.session_profit = round(_float_value((restored or {}).get("session_profit"), 0.0), 2)
        self.daily_profit = round(_float_value((restored or {}).get("daily_profit"), 0.0), 2)
        self.reinvest_step = max(0, _int_value((restored or {}).get("reinvest_step"), 0))
        self.last_trade_result = str((restored or {}).get("last_trade_result") or "")
        self.tick_digits = deque(maxlen=100)
        self.total_ticks = 0
        self.trade_locked = False
        self.open_contract_id = None
        self.pending_signal_id = ""
        self.base_stake_reset_pending = False
        self.signal_armed = True
        self.last_signal = "Waiting for 100 ticks"
        self.last_log_reason = ""
        self.last_99_streak_ts = 0.0
        self.last_trade_at = 0.0
        self.market_started_at = time.time()
        self.last_valid_setup_at = 0.0
        self.session_trade_count = 0
        self.wins = int((restored or {}).get("wins") or 0)
        self.losses = int((restored or {}).get("losses") or 0)
        self.history = list((restored or {}).get("history") or [])[-200:]

    @staticmethod
    def normalize_settings(settings: dict | None) -> dict:
        raw = dict(DEFAULT_CLOUD_SETTINGS)
        raw.update(settings or {})
        raw["base_stake"] = max(0.35, round(_float_value(raw.get("base_stake"), 1.0), 2))
        raw["take_profit_target"] = max(0.01, round(_float_value(raw.get("take_profit_target"), 50.0), 2))
        raw["max_reinvest_steps"] = max(1, _int_value(raw.get("max_reinvest_steps"), 5))
        raw["capital_build_mode"] = _bool_value(raw.get("capital_build_mode"), False)
        raw["market_switch_minutes"] = max(1, _int_value(raw.get("market_switch_minutes"), 10))
        raw["allowed_markets"] = normalize_allowed_markets(raw.get("allowed_markets"))
        raw["duration"] = max(1, min(10, _int_value(raw.get("duration"), 1)))
        raw["duration_unit"] = str(raw.get("duration_unit") or "t").strip().lower() or "t"
        if raw["duration_unit"] not in ("t", "s", "m", "h"):
            raw["duration_unit"] = "t"
        raw["enable_telegram_alerts"] = _bool_value(raw.get("enable_telegram_alerts"), False)
        raw["enable_whatsapp_alerts"] = _bool_value(raw.get("enable_whatsapp_alerts"), False)
        raw["allow_auto_resume"] = _bool_value(raw.get("allow_auto_resume"), False)
        raw["cooldown_seconds"] = max(0.0, _float_value(raw.get("cooldown_seconds"), 2.0))
        raw["max_daily_loss"] = max(0.0, _float_value(raw.get("max_daily_loss"), 0.0))
        raw["max_trades_per_session"] = max(0, _int_value(raw.get("max_trades_per_session"), 0))
        raw["low_balance_stop"] = max(0.0, _float_value(raw.get("low_balance_stop"), 0.0))
        raw.update(merge_risk_settings(raw))
        return raw

    def update_settings(self, settings: dict | None):
        previous_base_stake = round(float(self.settings.get("base_stake") or 0.0), 2)
        previous_markets = self.settings.get("allowed_markets") or []
        self.settings = self.normalize_settings({**self.settings, **(settings or {})})
        new_base_stake = round(float(self.settings["base_stake"]), 2)
        if new_base_stake != previous_base_stake:
            if not self.trade_locked and not self.open_contract_id:
                self.current_stake = new_base_stake
                self.reinvest_step = 0
                self.base_stake_reset_pending = False
                self.last_signal = f"Base stake updated to {new_base_stake:.2f}"
                self.log("base stake updated current_stake_reset=%s previous_base=%s", new_base_stake, previous_base_stake)
            else:
                self.base_stake_reset_pending = True
                self.last_signal = f"Base stake updated to {new_base_stake:.2f}. It will apply after the open trade settles."
                self.log("base stake updated pending open_trade current_stake=%s new_base=%s", self.current_stake, new_base_stake)
        if self.current_market not in self.settings["allowed_markets"]:
            self.current_market = self.settings["allowed_markets"][0]
            self.reset_market_buffer("settings market change")
        if previous_markets != self.settings["allowed_markets"]:
            self.log("allowed markets updated: %s", ",".join(self.settings["allowed_markets"]))

    def start(self, client_id: str | None = None):
        if client_id:
            self.client_id = client_id
        self.enabled = True
        self.running = True
        self.cloud_status = "Running"
        self.last_signal = "Waiting for 100 ticks"
        self.market_started_at = time.time()
        self.current_market = self.current_market or self.settings["allowed_markets"][0]
        if self.current_stake <= 0:
            self.current_stake = self.settings["base_stake"]
        self.log("cloud started market=%s stake=%s", self.current_market, self.current_stake)

    def stop(self, reason: str = "Stopped"):
        self.enabled = False
        self.running = False
        self.trade_locked = False
        self.open_contract_id = None
        self.pending_signal_id = ""
        self.cloud_status = reason or "Stopped"
        self.last_signal = self.cloud_status
        self.log("cloud stopped reason=%s", self.cloud_status)

    def reset_market_buffer(self, reason: str = ""):
        self.tick_digits.clear()
        self.total_ticks = 0
        self.signal_armed = True
        self.last_99_streak_ts = 0.0
        self.market_started_at = time.time()
        self.last_signal = "Waiting for 100 ticks"
        self.log("market buffer reset market=%s reason=%s", self.current_market, reason)

    def log(self, message, *args):
        if self.logger:
            try:
                self.logger.info("cloud_under9 user=%s " + message, self.username, *args)
            except Exception:
                pass

    def digit9_percentage(self) -> float:
        if len(self.tick_digits) < 100:
            return 0.0
        return round((Counter(self.tick_digits).get(9, 0) / 100) * 100.0, 1)

    def tp_target_for_cycle(self) -> float:
        if self.settings.get("capital_build_mode"):
            return round(float(self.settings["base_stake"]) * 2.0, 2)
        return float(self.settings["take_profit_target"])

    def _append_history(self, entry: dict):
        row = dict(entry or {})
        row.setdefault("time", time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()))
        self.history.append(row)
        self.history = self.history[-200:]

    def _should_stop_for_limits(self, balance: float | None) -> str:
        if balance is not None and self.settings["low_balance_stop"] > 0 and balance <= self.settings["low_balance_stop"]:
            return "Stopped: low balance protection."
        if balance is not None and self.settings.get("capital_build_mode") and balance <= (self.settings["base_stake"] * 1.15):
            if self.reinvest_step >= 5:
                return "Stopped: capital build max steps reached for low balance."
        if self.settings["max_daily_loss"] > 0 and self.daily_profit <= -abs(float(self.settings["max_daily_loss"])):
            return "Stopped: max daily loss reached."
        if self.settings["max_trades_per_session"] > 0 and self.session_trade_count >= int(self.settings["max_trades_per_session"]):
            return "Stopped: max trades per session reached."
        return ""

    def _market_rotation_action(self, now_ts: float):
        if self.trade_locked:
            return None
        switch_after = max(60.0, float(self.settings["market_switch_minutes"]) * 60.0)
        if (now_ts - float(self.market_started_at or now_ts)) < switch_after:
            return None
        new_market = next_market(self.settings["allowed_markets"], self.current_market)
        old_market = self.current_market
        self.current_market = new_market
        self.reset_market_buffer("rotation no setup")
        self.cloud_status = f"Rotated to {new_market}"
        return {"type": "switch_market", "old_symbol": old_market, "new_symbol": new_market, "reason": "No valid Under 9 setup"}

    def on_tick(self, tick: dict, digit: int, *, balance: float | None = None, now_ts: float | None = None) -> list[dict]:
        if not self.running:
            return []
        now_ts = float(now_ts or time.time())
        symbol = normalize_cloud_symbol((tick or {}).get("symbol"))
        if symbol != normalize_cloud_symbol(self.current_market):
            return []

        stop_reason = self._should_stop_for_limits(balance)
        if stop_reason:
            self.stop(stop_reason)
            return [{"type": "stopped", "reason": stop_reason}]

        try:
            safe_digit = int(digit)
        except Exception:
            return []
        if safe_digit < 0 or safe_digit > 9:
            return []

        self.total_ticks += 1
        self.tick_digits.append(safe_digit)
        actions = []
        history = list(self.tick_digits)
        if len(history) < 2 or history[-2:] != [9, 9]:
            self.signal_armed = True

        if len(history) < 100:
            self.last_signal = f"Waiting for 100 ticks ({len(history)}/100)"
            if len(history) in (1, 25, 50, 75, 99):
                self.log("waiting for 100 ticks market=%s ready=%s/100", self.current_market, len(history))
            rotation = self._market_rotation_action(now_ts)
            return [rotation] if rotation else actions

        pct9 = self.digit9_percentage()
        self.last_signal = f"Digit 9 at {pct9:.1f}%"
        self.log("digit 9 percentage market=%s pct=%s", self.current_market, pct9)
        if pct9 > 11.0:
            rotation = self._market_rotation_action(now_ts)
            return [rotation] if rotation else actions

        if len(history) < 2 or history[-2:] != [9, 9]:
            rotation = self._market_rotation_action(now_ts)
            return [rotation] if rotation else actions

        if not self.signal_armed:
            self.last_signal = "9,9 already consumed. Waiting for a fresh setup."
            return actions
        if self.trade_locked or self.open_contract_id:
            self.last_signal = "9,9 detected but trade is already open."
            return actions
        if self.last_trade_at and (now_ts - self.last_trade_at) < float(self.settings["cooldown_seconds"]):
            self.last_signal = "Cooldown active after previous trade."
            return actions

        risk = evaluate_under9_backup(
            history,
            settings=self.settings,
            now_ts=now_ts,
            last_99_streak_ts=self.last_99_streak_ts,
        )
        self.last_99_streak_ts = now_ts
        if not risk.passed:
            self.signal_armed = False
            self.last_signal = risk.reason
            self.log("backup thinking failed market=%s reason=%s details=%s", self.current_market, risk.reason, risk.details)
            return actions

        self.signal_armed = False
        self.trade_locked = True
        self.pending_signal_id = f"cloud99:{self.current_market}:{self.total_ticks}:{int(now_ts * 1000)}"
        self.last_valid_setup_at = now_ts
        self.last_signal = "9,9 detected. Under 9 trade locked and sending."
        self.log("9,9 detected backup passed market=%s signal_id=%s stake=%s", self.current_market, self.pending_signal_id, self.current_stake)
        intent = CloudTradeIntent(
            signal_id=self.pending_signal_id,
            symbol=self.current_market,
            stake=round(float(self.current_stake), 2),
            duration=int(self.settings["duration"]),
            duration_unit=str(self.settings["duration_unit"]),
        )
        return [{"type": "trade", "intent": intent.to_payload(), "risk": risk.details}]

    def mark_trade_sent(self, signal_id: str):
        if signal_id and signal_id == self.pending_signal_id:
            self.last_trade_at = time.time()
            self.session_trade_count += 1
            self.cloud_status = "Trade open"
            self.last_signal = "Under 9 sent. Waiting for result."
            self.log("trade placed signal_id=%s stake=%s", signal_id, self.current_stake)

    def mark_trade_open(self, contract_id, meta: dict | None = None):
        self.open_contract_id = str(contract_id or "")
        self.trade_locked = True
        self.cloud_status = "Trade open"
        self.log("trade open contract_id=%s signal_id=%s", self.open_contract_id, (meta or {}).get("cloud_signal_id"))

    def mark_trade_failed(self, reason: str):
        self.trade_locked = False
        self.open_contract_id = None
        self.pending_signal_id = ""
        self.last_trade_result = "FAILED"
        self.last_signal = reason or "Trade failed"
        self.cloud_status = "Running" if self.running else self.cloud_status
        self._append_history({"result": "FAILED", "profit": 0, "reason": self.last_signal, "market": self.current_market})
        self.log("trade failed reason=%s", self.last_signal)

    def on_contract_result(self, contract: dict, meta: dict | None, profit: float) -> dict:
        won = float(profit or 0.0) > 0
        result = "WIN" if won else "LOSS"
        previous_stake = round(float(self.current_stake or self.settings["base_stake"]), 2)
        self.session_profit = round(float(self.session_profit or 0.0) + float(profit or 0.0), 2)
        self.daily_profit = round(float(self.daily_profit or 0.0) + float(profit or 0.0), 2)
        self.last_trade_result = result
        if won:
            self.wins += 1
            self.reinvest_step += 1
            self.current_stake = round(max(0.35, previous_stake + max(0.0, float(profit or 0.0))), 2)
        else:
            self.losses += 1
            self.current_stake = round(float(self.settings["base_stake"]), 2)
            self.reinvest_step = 0

        action = "Reinvest stake updated" if won else "Stake reset after loss"
        tp_hit = False
        target = self.tp_target_for_cycle()
        if self.session_profit >= target:
            tp_hit = True
            action = "TP reached. Chain reset."
            self.current_stake = round(float(self.settings["base_stake"]), 2)
            self.reinvest_step = 0
            self.session_profit = 0.0
        elif self.reinvest_step >= int(self.settings["max_reinvest_steps"]):
            action = "Max reinvest steps reached. Chain reset."
            self.current_stake = round(float(self.settings["base_stake"]), 2)
            self.reinvest_step = 0
        elif self.base_stake_reset_pending:
            action = "Base stake update applied after settlement."
            self.current_stake = round(float(self.settings["base_stake"]), 2)
            self.reinvest_step = 0
        self.base_stake_reset_pending = False

        self.trade_locked = False
        self.open_contract_id = None
        self.pending_signal_id = ""
        self.cloud_status = "Running" if self.running else "Stopped"
        self.last_signal = f"{result}: {action}"
        row = {
            "strategy": "Cloud Under 9",
            "market": self.current_market,
            "contract_id": (contract or {}).get("contract_id"),
            "stake": previous_stake,
            "profit": round(float(profit or 0.0), 2),
            "result": result,
            "action": action,
            "tp_hit": tp_hit,
            "next_stake": self.current_stake,
            "reinvest_step": self.reinvest_step,
        }
        self._append_history(row)
        self.log("trade %s profit=%s next_stake=%s action=%s", result.lower(), profit, self.current_stake, action)
        return row

    def status(self) -> dict:
        pct = self.digit9_percentage()
        return {
            "status": "success",
            "cloud_enabled": bool(self.enabled),
            "running": bool(self.running),
            "strategy_name": self.strategy_name,
            "cloud_status": self.cloud_status,
            "current_market": self.current_market,
            "allowed_markets": list(self.settings["allowed_markets"]),
            "base_stake": round(float(self.settings["base_stake"]), 2),
            "current_stake": round(float(self.current_stake), 2),
            "session_profit": round(float(self.session_profit), 2),
            "daily_profit": round(float(self.daily_profit), 2),
            "tp_target": self.tp_target_for_cycle(),
            "configured_tp_target": round(float(self.settings["take_profit_target"]), 2),
            "reinvest_step": int(self.reinvest_step),
            "max_reinvest_steps": int(self.settings["max_reinvest_steps"]),
            "capital_build_mode": bool(self.settings["capital_build_mode"]),
            "market_switch_minutes": int(self.settings["market_switch_minutes"]),
            "duration": int(self.settings["duration"]),
            "duration_unit": self.settings["duration_unit"],
            "enable_telegram_alerts": bool(self.settings["enable_telegram_alerts"]),
            "enable_whatsapp_alerts": bool(self.settings["enable_whatsapp_alerts"]),
            "last_trade_result": self.last_trade_result,
            "last_signal": self.last_signal,
            "tick_count": len(self.tick_digits),
            "digit9_percentage": pct,
            "trade_locked": bool(self.trade_locked),
            "open_contract_id": self.open_contract_id,
            "wins": int(self.wins),
            "losses": int(self.losses),
            "session_trade_count": int(self.session_trade_count),
            "settings": dict(self.settings),
        }

    def export_state(self) -> dict:
        return {
            **self.status(),
            "current_stake": self.current_stake,
            "session_profit": self.session_profit,
            "daily_profit": self.daily_profit,
            "reinvest_step": self.reinvest_step,
            "history": list(self.history[-200:]),
        }
