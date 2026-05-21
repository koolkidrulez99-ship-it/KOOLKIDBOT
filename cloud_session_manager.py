from __future__ import annotations

import json
import threading
from typing import Any

from cloud_alerts import CloudAlertDispatcher
from cloud_under9_engine import CloudUnder9Engine


def ensure_cloud_tables(conn, is_postgres=False):
    cur = conn.cursor()
    if is_postgres:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS cloud_under9_sessions (
                username TEXT PRIMARY KEY,
                cloud_enabled INTEGER NOT NULL DEFAULT 0,
                strategy_name TEXT NOT NULL DEFAULT 'under9_reinvest',
                base_stake DOUBLE PRECISION NOT NULL DEFAULT 1,
                current_stake DOUBLE PRECISION NOT NULL DEFAULT 1,
                session_profit DOUBLE PRECISION NOT NULL DEFAULT 0,
                tp_target DOUBLE PRECISION NOT NULL DEFAULT 50,
                reinvest_step INTEGER NOT NULL DEFAULT 0,
                max_reinvest_steps INTEGER NOT NULL DEFAULT 5,
                capital_build_mode INTEGER NOT NULL DEFAULT 0,
                current_market TEXT NOT NULL DEFAULT 'R_10',
                allowed_markets TEXT NOT NULL DEFAULT '["R_10","R_25","R_50","R_75","R_100"]',
                last_trade_result TEXT NOT NULL DEFAULT '',
                cloud_status TEXT NOT NULL DEFAULT 'Stopped',
                settings_json TEXT NOT NULL DEFAULT '{}',
                history_json TEXT NOT NULL DEFAULT '[]',
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            )
            """
        )
    else:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS cloud_under9_sessions (
                username TEXT PRIMARY KEY,
                cloud_enabled INTEGER NOT NULL DEFAULT 0,
                strategy_name TEXT NOT NULL DEFAULT 'under9_reinvest',
                base_stake REAL NOT NULL DEFAULT 1,
                current_stake REAL NOT NULL DEFAULT 1,
                session_profit REAL NOT NULL DEFAULT 0,
                tp_target REAL NOT NULL DEFAULT 50,
                reinvest_step INTEGER NOT NULL DEFAULT 0,
                max_reinvest_steps INTEGER NOT NULL DEFAULT 5,
                capital_build_mode INTEGER NOT NULL DEFAULT 0,
                current_market TEXT NOT NULL DEFAULT 'R_10',
                allowed_markets TEXT NOT NULL DEFAULT '["R_10","R_25","R_50","R_75","R_100"]',
                last_trade_result TEXT NOT NULL DEFAULT '',
                cloud_status TEXT NOT NULL DEFAULT 'Stopped',
                settings_json TEXT NOT NULL DEFAULT '{}',
                history_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


class CloudPersistence:
    def __init__(self, *, db_connect, db_execute, db_fetchone, db_row_to_dict, db_commit, utc_now_str):
        self.db_connect = db_connect
        self.db_execute = db_execute
        self.db_fetchone = db_fetchone
        self.db_row_to_dict = db_row_to_dict
        self.db_commit = db_commit
        self.utc_now_str = utc_now_str

    def load(self, username: str) -> dict:
        user = str(username or "").strip().lower()
        if not user:
            return {}
        conn = self.db_connect(row_factory=True)
        cur = conn.cursor()
        self.db_execute(cur, "SELECT * FROM cloud_under9_sessions WHERE lower(username)=lower(?)", (user,))
        row = self.db_fetchone(cur)
        out = self.db_row_to_dict(cur, row)
        conn.close()
        if not out:
            return {}
        for key in ("settings_json", "history_json", "allowed_markets"):
            try:
                out[key] = json.loads(out.get(key) or ("[]" if key in ("history_json", "allowed_markets") else "{}"))
            except Exception:
                out[key] = [] if key in ("history_json", "allowed_markets") else {}
        return out

    def save(self, username: str, status: dict, settings: dict, history: list[dict]):
        user = str(username or "").strip().lower()
        if not user:
            return False
        now_s = self.utc_now_str()
        allowed = json.dumps(settings.get("allowed_markets") or [])
        settings_json = json.dumps(settings or {}, sort_keys=True)
        history_json = json.dumps(list(history or [])[-200:])
        conn = self.db_connect()
        cur = conn.cursor()
        self.db_execute(
            cur,
            """
            INSERT INTO cloud_under9_sessions (
                username, cloud_enabled, strategy_name, base_stake, current_stake,
                session_profit, tp_target, reinvest_step, max_reinvest_steps,
                capital_build_mode, current_market, allowed_markets,
                last_trade_result, cloud_status, settings_json, history_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                cloud_enabled=excluded.cloud_enabled,
                strategy_name=excluded.strategy_name,
                base_stake=excluded.base_stake,
                current_stake=excluded.current_stake,
                session_profit=excluded.session_profit,
                tp_target=excluded.tp_target,
                reinvest_step=excluded.reinvest_step,
                max_reinvest_steps=excluded.max_reinvest_steps,
                capital_build_mode=excluded.capital_build_mode,
                current_market=excluded.current_market,
                allowed_markets=excluded.allowed_markets,
                last_trade_result=excluded.last_trade_result,
                cloud_status=excluded.cloud_status,
                settings_json=excluded.settings_json,
                history_json=excluded.history_json,
                updated_at=excluded.updated_at
            """,
            (
                user,
                1 if status.get("cloud_enabled") or status.get("running") else 0,
                "under9_reinvest",
                float(settings.get("base_stake") or 1),
                float(status.get("current_stake") or settings.get("base_stake") or 1),
                float(status.get("session_profit") or 0),
                float(settings.get("take_profit_target") or status.get("configured_tp_target") or 50),
                int(status.get("reinvest_step") or 0),
                int(settings.get("max_reinvest_steps") or 5),
                1 if settings.get("capital_build_mode") else 0,
                str(status.get("current_market") or "R_10"),
                allowed,
                str(status.get("last_trade_result") or ""),
                str(status.get("cloud_status") or "Stopped"),
                settings_json,
                history_json,
                now_s,
                now_s,
            ),
        )
        self.db_commit(conn)
        conn.close()
        return True


class CloudSessionManager:
    def __init__(self, *, persistence: CloudPersistence | None = None, alerts: CloudAlertDispatcher | None = None, logger=None):
        self.persistence = persistence
        self.alerts = alerts or CloudAlertDispatcher(logger=logger)
        self.logger = logger
        self._lock = threading.RLock()
        self._sessions: dict[str, CloudUnder9Engine] = {}

    def _key(self, username: str) -> str:
        return str(username or "").strip().lower()

    def _persist(self, session: CloudUnder9Engine):
        if not self.persistence or not session:
            return
        try:
            self.persistence.save(session.username, session.status(), session.settings, session.history)
        except Exception as exc:
            if self.logger:
                self.logger.warning("cloud persistence save failed user=%s error=%s", getattr(session, "username", ""), exc)

    def get_or_create(self, username: str, client_id: str | None = None, settings: dict | None = None) -> CloudUnder9Engine:
        key = self._key(username)
        with self._lock:
            if key in self._sessions:
                engine = self._sessions[key]
                if client_id:
                    engine.client_id = client_id
                if settings:
                    engine.update_settings(settings)
                return engine
            restored = self.persistence.load(key) if self.persistence else {}
            restored_settings = {}
            if isinstance(restored.get("settings_json"), dict):
                restored_settings.update(restored.get("settings_json") or {})
            if settings:
                restored_settings.update(settings)
            engine = CloudUnder9Engine(
                key,
                client_id or "",
                restored_settings,
                restored={
                    "current_market": restored.get("current_market"),
                    "current_stake": restored.get("current_stake"),
                    "session_profit": restored.get("session_profit"),
                    "reinvest_step": restored.get("reinvest_step"),
                    "last_trade_result": restored.get("last_trade_result"),
                    "history": restored.get("history_json") or [],
                },
                logger=self.logger,
            )
            engine.enabled = bool(restored.get("cloud_enabled")) and bool(engine.settings.get("allow_auto_resume"))
            engine.running = False
            if not engine.enabled:
                engine.cloud_status = restored.get("cloud_status") or "Stopped"
            self._sessions[key] = engine
            return engine

    def start(self, username: str, client_id: str, settings: dict | None = None) -> dict:
        with self._lock:
            engine = self.get_or_create(username, client_id, settings)
            if settings:
                engine.update_settings(settings)
            engine.start(client_id)
            self._persist(engine)
            self.alerts.send("cloud_started", f"Cloud Under 9 started on {engine.current_market}.", engine.settings)
            return engine.status()

    def stop(self, username: str, reason: str = "Stopped") -> dict:
        with self._lock:
            engine = self.get_or_create(username)
            engine.stop(reason)
            self._persist(engine)
            self.alerts.send("cloud_stopped", f"Cloud Under 9 stopped: {engine.cloud_status}", engine.settings)
            return engine.status()

    def update_settings(self, username: str, settings: dict) -> dict:
        with self._lock:
            engine = self.get_or_create(username, settings=settings)
            engine.update_settings(settings)
            self._persist(engine)
            return engine.status()

    def status(self, username: str) -> dict:
        with self._lock:
            engine = self.get_or_create(username)
            return engine.status()

    def has_session(self, username: str) -> bool:
        key = self._key(username)
        if not key:
            return False
        with self._lock:
            if key in self._sessions:
                return True
        if not self.persistence:
            return False
        try:
            return bool(self.persistence.load(key))
        except Exception:
            return False

    def session_keys(self) -> list[str]:
        with self._lock:
            return list(self._sessions.keys())

    def history(self, username: str) -> list[dict]:
        with self._lock:
            engine = self.get_or_create(username)
            return list(engine.history[-200:])

    def clear_history(self, username: str) -> dict:
        with self._lock:
            engine = self.get_or_create(username)
            engine.history = []
            engine.wins = 0
            engine.losses = 0
            engine.last_trade_result = ""
            self._persist(engine)
            return engine.status()

    def is_symbol_needed(self, username: str, symbol: str) -> bool:
        key = self._key(username)
        sym = str(symbol or "").upper().strip()
        with self._lock:
            engine = self._sessions.get(key)
            return bool(engine and engine.running and str(engine.current_market).upper() == sym)

    def all_needed_symbols(self) -> set[str]:
        with self._lock:
            return {
                str(engine.current_market).upper()
                for engine in self._sessions.values()
                if engine and engine.running and engine.current_market
            }

    def on_tick(self, username: str, client_id: str, tick: dict, digit: int, *, balance: float | None = None) -> list[dict]:
        key = self._key(username)
        if not key:
            return []
        with self._lock:
            engine = self.get_or_create(key, client_id)
            actions = engine.on_tick(tick, digit, balance=balance)
            self._persist(engine)
            return actions

    def mark_trade_sent(self, username: str, signal_id: str):
        with self._lock:
            engine = self.get_or_create(username)
            engine.mark_trade_sent(signal_id)
            self._persist(engine)

    def mark_trade_open(self, username: str, contract_id: Any, meta: dict | None = None):
        with self._lock:
            engine = self.get_or_create(username)
            engine.mark_trade_open(contract_id, meta=meta)
            self._persist(engine)

    def mark_trade_failed(self, username: str, reason: str):
        with self._lock:
            engine = self.get_or_create(username)
            engine.mark_trade_failed(reason)
            self._persist(engine)
            self.alerts.send("cloud_trade_failed", f"Cloud Under 9 trade failed: {reason}", engine.settings)

    def on_contract_result(self, username: str, contract: dict, meta: dict | None, profit: float) -> dict:
        with self._lock:
            engine = self.get_or_create(username)
            row = engine.on_contract_result(contract, meta, profit)
            self._persist(engine)
            event = "cloud_trade_win" if profit > 0 else "cloud_trade_loss"
            self.alerts.send(event, f"Cloud Under 9 {row.get('result')}: {row.get('profit')} on {row.get('market')}.", engine.settings)
            if row.get("tp_hit"):
                self.alerts.send("cloud_tp_reached", "Cloud Under 9 TP reached. Reinvest chain reset.", engine.settings)
            return row
