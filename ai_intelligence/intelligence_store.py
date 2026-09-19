"""Per-user persistence for AI Intelligence strategy state and learning records."""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone


class IntelligenceStore:
    def __init__(self, bridge):
        self.bridge = bridge
        self._ready = False

    def ensure(self):
        statements = [
            "CREATE TABLE IF NOT EXISTS ai_intelligence_setups (id TEXT PRIMARY KEY, username TEXT NOT NULL, account TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL, strategy TEXT NOT NULL, state_json TEXT NOT NULL, updated_at TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS ai_intelligence_evaluations (id TEXT PRIMARY KEY, username TEXT NOT NULL, account TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL, strategy TEXT NOT NULL, decision TEXT NOT NULL, score INTEGER NOT NULL, record TEXT NOT NULL, created_at TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS ai_intelligence_knowledge (id TEXT PRIMARY KEY, username TEXT NOT NULL, strategy TEXT NOT NULL, rule_text TEXT NOT NULL, structured_rule TEXT NOT NULL, priority INTEGER NOT NULL, version INTEGER NOT NULL, enabled INTEGER NOT NULL, created_at TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS ai_intelligence_profiles (id TEXT PRIMARY KEY, username TEXT NOT NULL, name TEXT NOT NULL, config TEXT NOT NULL, updated_at TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS ai_intelligence_backtests (id TEXT PRIMARY KEY, username TEXT NOT NULL, strategy TEXT NOT NULL, result TEXT NOT NULL, created_at TEXT NOT NULL)",
        ]
        for statement in statements:
            self.bridge.db(statement)
        self._ready = True

    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat()

    def save_setup(self, username, setup):
        self.ensure()
        key = f"{username}|{setup.account}|{setup.symbol}|{setup.timeframe}|{setup.strategy}"
        setup_id = secrets.token_hex(16)
        row = self.bridge.db("SELECT id FROM ai_intelligence_setups WHERE username=? AND account=? AND symbol=? AND timeframe=? AND strategy=?", (username, setup.account, setup.symbol, setup.timeframe, setup.strategy), True)
        if row:
            setup_id = row[0]
            self.bridge.db("UPDATE ai_intelligence_setups SET state_json=?, updated_at=? WHERE id=? AND username=?", (json.dumps(setup.__dict__), self.now(), setup_id, username))
        else:
            self.bridge.db("INSERT INTO ai_intelligence_setups (id,username,account,symbol,timeframe,strategy,state_json,updated_at) VALUES (?,?,?,?,?,?,?,?)", (setup_id, username, setup.account, setup.symbol, setup.timeframe, setup.strategy, json.dumps(setup.__dict__), self.now()))
        return key

    def load_setup(self, username, account, symbol, timeframe, strategy):
        self.ensure()
        row = self.bridge.db("SELECT state_json FROM ai_intelligence_setups WHERE username=? AND account=? AND symbol=? AND timeframe=? AND strategy=?", (username, account, symbol, timeframe, strategy), True)
        return json.loads(row[0]) if row else None

    def record_evaluation(self, username, setup, result):
        self.ensure()
        safe = {k: result.get(k) for k in ("decision", "reason", "score", "entry", "sl", "tp", "r", "volume", "threshold", "risk_validated", "executed", "confidence_factors") if k in result}
        safe["state"] = result.get("state", {})
        self.bridge.db("INSERT INTO ai_intelligence_evaluations (id,username,account,symbol,timeframe,strategy,decision,score,record,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)", (secrets.token_hex(16), username, setup.account, setup.symbol, setup.timeframe, setup.strategy, result["decision"], int(result.get("score", 0)), json.dumps(safe), self.now()))

    def recent(self, username, limit=30):
        self.ensure()
        with self.bridge.schema_lock:
            conn = self.bridge.s._db_connect()
            try:
                cur = conn.cursor()
                self.bridge.s._db_execute(cur, "SELECT record,created_at FROM ai_intelligence_evaluations WHERE username=? ORDER BY created_at DESC LIMIT ?", (username, int(limit)))
                return [{**json.loads(row[0]), "created_at": row[1]} for row in cur.fetchall()]
            finally:
                conn.close()

    def latest_evaluation(self, username, account, symbol, timeframe, strategy):
        self.ensure()
        row = self.bridge.db("SELECT record FROM ai_intelligence_evaluations WHERE username=? AND account=? AND symbol=? AND timeframe=? AND strategy=? ORDER BY created_at DESC LIMIT 1", (username, account, symbol, timeframe, strategy), True)
        return json.loads(row[0]) if row else None

    def teach(self, username, strategy, text, structured, priority=50):
        self.ensure()
        record_id = secrets.token_hex(16)
        self.bridge.db("INSERT INTO ai_intelligence_knowledge (id,username,strategy,rule_text,structured_rule,priority,version,enabled,created_at) VALUES (?,?,?,?,?,?,?,?,?)", (record_id, username, strategy, text, json.dumps(structured), int(priority), 1, 1, self.now()))
        return record_id

    def knowledge(self, username):
        self.ensure()
        with self.bridge.schema_lock:
            conn = self.bridge.s._db_connect()
            try:
                cur = conn.cursor()
                self.bridge.s._db_execute(cur, "SELECT id,strategy,rule_text,structured_rule,priority,version,enabled,created_at FROM ai_intelligence_knowledge WHERE username=? ORDER BY created_at DESC", (username,))
                return [{"id": r[0], "strategy": r[1], "rule": r[2], "structured": json.loads(r[3]), "priority": r[4], "version": r[5], "enabled": bool(r[6]), "created_at": r[7]} for r in cur.fetchall()]
            finally:
                conn.close()

    def toggle_knowledge(self, username, record_id, enabled):
        self.ensure()
        self.bridge.db("UPDATE ai_intelligence_knowledge SET enabled=? WHERE id=? AND username=?", (int(bool(enabled)), record_id, username))

    def save_backtest(self, username, strategy, result):
        self.ensure()
        self.bridge.db("INSERT INTO ai_intelligence_backtests (id,username,strategy,result,created_at) VALUES (?,?,?,?,?)", (secrets.token_hex(16), username, strategy, json.dumps(result), self.now()))
