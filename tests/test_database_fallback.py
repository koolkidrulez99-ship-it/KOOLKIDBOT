import sqlite3
from types import SimpleNamespace

import server
import mutant_auto_store
import storage_fallback
import trade_runtime_store


def _broken_pg_connect(*args, **kwargs):
    raise RuntimeError("postgres unavailable")


def test_server_db_connect_falls_back_to_sqlite_when_postgres_is_down(monkeypatch, tmp_path):
    db_path = tmp_path / "auth_fallback.db"
    monkeypatch.setattr(server, "DATABASE_URL", "postgresql://broken/render")
    monkeypatch.setattr(server, "DB_BACKEND", "postgres")
    monkeypatch.setattr(server, "DB_FILE", str(db_path))
    monkeypatch.setattr(server, "AUTH_SQLITE_TARGET", str(db_path))
    monkeypatch.setattr(server, "AUTH_SQLITE_STORAGE", "sqlite")
    monkeypatch.setattr(server, "psycopg2", SimpleNamespace(connect=_broken_pg_connect))

    conn = server._db_connect(row_factory=True)
    try:
        assert isinstance(conn, sqlite3.Connection)
        conn.execute("CREATE TABLE IF NOT EXISTS probe (id INTEGER PRIMARY KEY)")
    finally:
        conn.close()

    assert server.DB_BACKEND == "sqlite"


def test_trade_runtime_store_falls_back_to_sqlite_when_postgres_is_down(monkeypatch, tmp_path):
    sqlite_path = tmp_path / "runtime_store.db"
    trade_runtime_store._TABLE_READY.clear()
    trade_runtime_store._POSTGRES_DISABLED.clear()
    monkeypatch.setattr(trade_runtime_store, "psycopg2", SimpleNamespace(connect=_broken_pg_connect))

    saved = trade_runtime_store.save_trade_runtime(
        "client-1",
        {"active": True, "symbol": "R_25"},
        username="alice",
        database_url="postgresql://broken/render",
        sqlite_path=str(sqlite_path),
    )
    restored = trade_runtime_store.load_trade_runtime(
        "client-1",
        database_url="postgresql://broken/render",
        sqlite_path=str(sqlite_path),
    )

    assert saved is True
    assert isinstance(restored, dict)
    assert restored["active"] is True
    assert restored["symbol"] == "R_25"


def test_sqlite_helper_uses_shared_memory_when_file_storage_fails(monkeypatch, tmp_path):
    real_connect = storage_fallback.sqlite3.connect
    blocked_path = str(tmp_path / "blocked.db")

    def flaky_connect(target, *args, **kwargs):
        if kwargs.get("uri") and str(target).startswith("file:"):
            return real_connect(target, *args, **kwargs)
        raise sqlite3.OperationalError("disk is unavailable")

    monkeypatch.setattr(storage_fallback.sqlite3, "connect", flaky_connect)

    info = storage_fallback.open_sqlite_with_fallback(
        preferred_path=blocked_path,
        default_name=blocked_path,
        row_factory=True,
        memory_namespace="test-db-fallback",
    )

    conn = info["connection"]
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS sample (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO sample (name) VALUES (?)", ("ok",))
        row = conn.execute("SELECT name FROM sample").fetchone()
    finally:
        conn.close()

    assert info["storage"] == "memory"
    assert row["name"] == "ok"


def test_mutant_auto_store_falls_back_to_sqlite_when_postgres_is_down(monkeypatch, tmp_path):
    sqlite_path = tmp_path / "mutant_auto_store.db"
    mutant_auto_store._TABLE_READY.clear()
    mutant_auto_store._POSTGRES_DISABLED.clear()
    monkeypatch.setattr(mutant_auto_store, "psycopg2", SimpleNamespace(connect=_broken_pg_connect))

    saved = mutant_auto_store.save_mutant_auto_runtime(
        "client-2",
        {"auto": {"enabled": True, "current_stake": 0.35}},
        username="alice",
        database_url="postgresql://broken/render",
        sqlite_path=str(sqlite_path),
    )
    restored = mutant_auto_store.load_mutant_auto_runtime(
        "client-2",
        database_url="postgresql://broken/render",
        sqlite_path=str(sqlite_path),
    )

    assert saved is True
    assert isinstance(restored, dict)
    assert restored["auto"]["enabled"] is True


def test_trade_runtime_store_load_handles_postgres_tuple_rows(monkeypatch):
    tuple_row = ("client-3", "alice", '{"active": true}', "2026-04-10 10:00:00")

    class FakeCursor:
        def execute(self, *_args, **_kwargs):
            return None

        def fetchone(self):
            return tuple_row

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def close(self):
            return None

    monkeypatch.setattr(trade_runtime_store, "_ensure_tables", lambda **_kwargs: None)
    monkeypatch.setattr(
        trade_runtime_store,
        "_resolve_backend",
        lambda **_kwargs: {"kind": "postgres", "connection": FakeConn(), "key": "postgres:test"},
    )

    payload = trade_runtime_store.load_trade_runtime("client-3", database_url="postgresql://example/render")

    assert payload["active"] is True
    assert payload["_stored_username"] == "alice"


def test_mutant_auto_store_load_handles_postgres_tuple_rows(monkeypatch):
    tuple_row = ("client-4", "alice", '{"auto": {"enabled": true}}', "2026-04-10 10:00:00")

    class FakeCursor:
        def execute(self, *_args, **_kwargs):
            return None

        def fetchone(self):
            return tuple_row

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def close(self):
            return None

    monkeypatch.setattr(mutant_auto_store, "_ensure_tables", lambda **_kwargs: None)
    monkeypatch.setattr(
        mutant_auto_store,
        "_resolve_backend",
        lambda **_kwargs: {"kind": "postgres", "connection": FakeConn(), "key": "postgres:test"},
    )

    payload = mutant_auto_store.load_mutant_auto_runtime("client-4", database_url="postgresql://example/render")

    assert payload["auto"]["enabled"] is True
    assert payload["_stored_username"] == "alice"
