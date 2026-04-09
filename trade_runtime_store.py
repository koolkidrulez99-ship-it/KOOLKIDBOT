import json
import os
import sqlite3
import threading
from datetime import datetime

from auth_storage import find_existing_sqlite_auth_db, normalize_database_url

try:
    import psycopg2
except Exception:
    psycopg2 = None


_TABLE_READY = set()
_LOCK = threading.Lock()


def _normalize_sqlite_path(path):
    raw = str(path or "").strip()
    if raw:
        return raw
    existing = find_existing_sqlite_auth_db(default_name="users.db")
    if existing:
        return existing
    return "users.db"


def _backend_key(*, database_url=None, sqlite_path=None):
    db_url = normalize_database_url(database_url)
    if db_url:
        return f"postgres:{db_url}"
    return f"sqlite:{os.path.abspath(_normalize_sqlite_path(sqlite_path))}"


def _connect(*, database_url=None, sqlite_path=None, row_factory=False):
    db_url = normalize_database_url(database_url)
    if db_url:
        if psycopg2 is None:
            raise RuntimeError("psycopg2 is required for trade runtime Postgres storage.")
        return psycopg2.connect(db_url)
    db_path = _normalize_sqlite_path(sqlite_path)
    conn = sqlite3.connect(db_path)
    if row_factory:
        conn.row_factory = sqlite3.Row
    return conn


def _ensure_tables(*, database_url=None, sqlite_path=None):
    key = _backend_key(database_url=database_url, sqlite_path=sqlite_path)
    with _LOCK:
        if key in _TABLE_READY:
            return
        conn = _connect(database_url=database_url, sqlite_path=sqlite_path)
        try:
            cur = conn.cursor()
            if normalize_database_url(database_url):
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS trade_runtime_states (
                        client_id TEXT PRIMARY KEY,
                        username TEXT,
                        payload TEXT NOT NULL,
                        updated_at TIMESTAMP NOT NULL
                    )
                    """
                )
            else:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS trade_runtime_states (
                        client_id TEXT PRIMARY KEY,
                        username TEXT,
                        payload TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
            conn.commit()
            _TABLE_READY.add(key)
        finally:
            conn.close()


def save_trade_runtime(client_id, payload, *, username="", database_url=None, sqlite_path=None):
    safe_client_id = str(client_id or "").strip()
    if not safe_client_id or not isinstance(payload, dict):
        return False
    _ensure_tables(database_url=database_url, sqlite_path=sqlite_path)
    serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    updated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    conn = _connect(database_url=database_url, sqlite_path=sqlite_path)
    try:
        cur = conn.cursor()
        if normalize_database_url(database_url):
            cur.execute(
                """
                INSERT INTO trade_runtime_states (client_id, username, payload, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (client_id) DO UPDATE
                SET username = EXCLUDED.username,
                    payload = EXCLUDED.payload,
                    updated_at = EXCLUDED.updated_at
                """,
                (safe_client_id, str(username or "").strip().lower(), serialized, updated_at),
            )
        else:
            cur.execute(
                """
                INSERT INTO trade_runtime_states (client_id, username, payload, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(client_id) DO UPDATE SET
                    username=excluded.username,
                    payload=excluded.payload,
                    updated_at=excluded.updated_at
                """,
                (safe_client_id, str(username or "").strip().lower(), serialized, updated_at),
            )
        conn.commit()
        return True
    finally:
        conn.close()


def load_trade_runtime(client_id, *, database_url=None, sqlite_path=None):
    safe_client_id = str(client_id or "").strip()
    if not safe_client_id:
        return None
    _ensure_tables(database_url=database_url, sqlite_path=sqlite_path)
    conn = _connect(database_url=database_url, sqlite_path=sqlite_path, row_factory=True)
    try:
        cur = conn.cursor()
        if normalize_database_url(database_url):
            cur.execute(
                "SELECT client_id, username, payload, updated_at FROM trade_runtime_states WHERE client_id=%s",
                (safe_client_id,),
            )
        else:
            cur.execute(
                "SELECT client_id, username, payload, updated_at FROM trade_runtime_states WHERE client_id=?",
                (safe_client_id,),
            )
        row = cur.fetchone()
        if not row:
            return None
        raw_payload = row["payload"] if hasattr(row, "__getitem__") else row[2]
        try:
            payload = json.loads(raw_payload or "{}")
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        payload["_stored_client_id"] = safe_client_id
        payload["_stored_username"] = str((row["username"] if hasattr(row, "__getitem__") else row[1]) or "").strip().lower()
        payload["_stored_updated_at"] = str((row["updated_at"] if hasattr(row, "__getitem__") else row[3]) or "").strip()
        return payload
    finally:
        conn.close()


def clear_trade_runtime(client_id, *, database_url=None, sqlite_path=None):
    safe_client_id = str(client_id or "").strip()
    if not safe_client_id:
        return False
    _ensure_tables(database_url=database_url, sqlite_path=sqlite_path)
    conn = _connect(database_url=database_url, sqlite_path=sqlite_path)
    try:
        cur = conn.cursor()
        if normalize_database_url(database_url):
            cur.execute("DELETE FROM trade_runtime_states WHERE client_id=%s", (safe_client_id,))
        else:
            cur.execute("DELETE FROM trade_runtime_states WHERE client_id=?", (safe_client_id,))
        conn.commit()
        return True
    finally:
        conn.close()
