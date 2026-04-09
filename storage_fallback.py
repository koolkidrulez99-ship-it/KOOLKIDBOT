import os
import sqlite3
import tempfile
import threading


_MEMORY_KEEPERS = {}
_MEMORY_KEEPERS_LOCK = threading.Lock()


def _iter_sqlite_candidates(preferred_path=None, default_name="users.db"):
    seen = set()
    for raw in (preferred_path, default_name):
        path = str(raw or "").strip()
        if not path:
            continue
        norm = os.path.normcase(os.path.abspath(path))
        if norm in seen:
            continue
        seen.add(norm)
        yield path
    fallback_name = os.path.basename(str(preferred_path or default_name or "users.db").strip() or "users.db")
    temp_path = os.path.join(tempfile.gettempdir(), fallback_name or "users.db")
    norm_temp = os.path.normcase(os.path.abspath(temp_path))
    if norm_temp not in seen:
        yield temp_path


def connect_postgres_with_timeout(psycopg2_module, database_url, *, connect_timeout=3):
    if psycopg2_module is None:
        raise RuntimeError("psycopg2 is not installed.")
    try:
        return psycopg2_module.connect(database_url, connect_timeout=connect_timeout)
    except TypeError:
        return psycopg2_module.connect(database_url)


def open_sqlite_with_fallback(*, preferred_path=None, default_name="users.db", row_factory=False, memory_namespace="app-storage"):
    errors = []
    for candidate in _iter_sqlite_candidates(preferred_path=preferred_path, default_name=default_name):
        try:
            conn = sqlite3.connect(candidate)
            if row_factory:
                conn.row_factory = sqlite3.Row
            return {
                "connection": conn,
                "target": candidate,
                "storage": "sqlite",
                "errors": errors,
            }
        except Exception as exc:
            errors.append((candidate, exc))

    memory_uri = f"file:{memory_namespace}?mode=memory&cache=shared"
    with _MEMORY_KEEPERS_LOCK:
        keeper = _MEMORY_KEEPERS.get(memory_uri)
        if keeper is None:
            keeper = sqlite3.connect(memory_uri, uri=True, check_same_thread=False)
            _MEMORY_KEEPERS[memory_uri] = keeper
    conn = sqlite3.connect(memory_uri, uri=True)
    if row_factory:
        conn.row_factory = sqlite3.Row
    return {
        "connection": conn,
        "target": memory_uri,
        "storage": "memory",
        "errors": errors,
    }
