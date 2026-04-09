import json
import logging
import os
import sqlite3
import threading
from datetime import datetime

from auth_storage import find_existing_sqlite_auth_db, normalize_database_url
from storage_fallback import connect_postgres_with_timeout, open_sqlite_with_fallback

try:
    import psycopg2
except Exception:
    psycopg2 = None


_TABLE_READY = set()
_LOCK = threading.Lock()
_POSTGRES_DISABLED = {}
logger = logging.getLogger(__name__)


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
    if db_url and db_url not in _POSTGRES_DISABLED:
        return f"postgres:{db_url}"
    return f"sqlite:{os.path.abspath(_normalize_sqlite_path(sqlite_path))}"


def _log_postgres_fallback(db_url, exc):
    reason = str(exc or "unknown error").strip() or "unknown error"
    previous = _POSTGRES_DISABLED.get(db_url)
    if previous == reason:
        return
    _POSTGRES_DISABLED[db_url] = reason
    logger.warning("Mutant AUTO storage falling back to SQLite because Postgres is unavailable: %s", reason)


def _resolve_backend(*, database_url=None, sqlite_path=None, row_factory=False):
    db_url = normalize_database_url(database_url)
    if db_url and db_url not in _POSTGRES_DISABLED:
        if psycopg2 is None:
            _log_postgres_fallback(db_url, RuntimeError("psycopg2 is not installed."))
        else:
            try:
                conn = connect_postgres_with_timeout(psycopg2, db_url, connect_timeout=3)
                return {
                    "kind": "postgres",
                    "key": f"postgres:{db_url}",
                    "connection": conn,
                }
            except Exception as exc:
                _log_postgres_fallback(db_url, exc)
    sqlite_info = open_sqlite_with_fallback(
        preferred_path=_normalize_sqlite_path(sqlite_path),
        default_name=_normalize_sqlite_path(sqlite_path),
        row_factory=row_factory,
        memory_namespace="mutant-auto-store",
    )
    return {
        "kind": "sqlite",
        "key": f"{sqlite_info['storage']}:{sqlite_info['target']}",
        "connection": sqlite_info["connection"],
    }


def _ensure_tables(*, database_url=None, sqlite_path=None):
    with _LOCK:
        backend = _resolve_backend(database_url=database_url, sqlite_path=sqlite_path)
        key = backend["key"]
        if key in _TABLE_READY:
            backend["connection"].close()
            return
        conn = backend["connection"]
        try:
            cur = conn.cursor()
            if backend["kind"] == "postgres":
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS mutant_auto_states (
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
                    CREATE TABLE IF NOT EXISTS mutant_auto_states (
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


def save_mutant_auto_runtime(client_id, payload, *, username="", database_url=None, sqlite_path=None):
    safe_client_id = str(client_id or "").strip()
    if not safe_client_id or not isinstance(payload, dict):
        return False
    _ensure_tables(database_url=database_url, sqlite_path=sqlite_path)
    serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    updated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    backend = _resolve_backend(database_url=database_url, sqlite_path=sqlite_path)
    conn = backend["connection"]
    try:
        cur = conn.cursor()
        if backend["kind"] == "postgres":
            cur.execute(
                """
                INSERT INTO mutant_auto_states (client_id, username, payload, updated_at)
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
                INSERT INTO mutant_auto_states (client_id, username, payload, updated_at)
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


def load_mutant_auto_runtime(client_id, *, database_url=None, sqlite_path=None):
    safe_client_id = str(client_id or "").strip()
    if not safe_client_id:
        return None
    _ensure_tables(database_url=database_url, sqlite_path=sqlite_path)
    backend = _resolve_backend(database_url=database_url, sqlite_path=sqlite_path, row_factory=True)
    conn = backend["connection"]
    try:
        cur = conn.cursor()
        if backend["kind"] == "postgres":
            cur.execute(
                "SELECT client_id, username, payload, updated_at FROM mutant_auto_states WHERE client_id=%s",
                (safe_client_id,),
            )
        else:
            cur.execute(
                "SELECT client_id, username, payload, updated_at FROM mutant_auto_states WHERE client_id=?",
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


def clear_mutant_auto_runtime(client_id, *, database_url=None, sqlite_path=None):
    safe_client_id = str(client_id or "").strip()
    if not safe_client_id:
        return False
    _ensure_tables(database_url=database_url, sqlite_path=sqlite_path)
    backend = _resolve_backend(database_url=database_url, sqlite_path=sqlite_path)
    conn = backend["connection"]
    try:
        cur = conn.cursor()
        if backend["kind"] == "postgres":
            cur.execute("DELETE FROM mutant_auto_states WHERE client_id=%s", (safe_client_id,))
        else:
            cur.execute("DELETE FROM mutant_auto_states WHERE client_id=?", (safe_client_id,))
        conn.commit()
        return True
    finally:
        conn.close()
