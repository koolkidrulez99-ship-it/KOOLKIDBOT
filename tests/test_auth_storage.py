import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import auth_storage


def _make_sqlite_auth_db(path: Path):
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT,
            role TEXT DEFAULT 'user',
            grandfathered INTEGER DEFAULT 1,
            license_key TEXT,
            license_exempt INTEGER DEFAULT 0,
            created_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE licenses (
            license_key TEXT PRIMARY KEY,
            license_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            activated_at TEXT,
            expires_at TEXT,
            used_by TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT
        )
        """
    )
    cur.execute(
        """
        INSERT INTO users (username, password, email, role, grandfathered, license_key, license_exempt, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("alice", "pbkdf2:sha256:hash", "alice@example.com", "user", 1, "LIC-123", 0, "2026-03-30 10:00:00"),
    )
    cur.execute(
        """
        INSERT INTO licenses (license_key, license_type, status, created_at, activated_at, expires_at, used_by)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("LIC-123", "monthly", "active", "2026-03-01 00:00:00", "2026-03-02 00:00:00", "2026-04-01 00:00:00", "alice"),
    )
    cur.execute(
        """
        INSERT INTO password_resets (username, token_hash, created_at, expires_at, used_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("alice", "tokenhash-1", "2026-03-10 00:00:00", "2026-03-10 00:30:00", None),
    )
    conn.commit()
    conn.close()


def _make_fake_pg_driver(store):
    user_cols = ("username", "password", "email", "role", "grandfathered", "license_key", "license_exempt", "created_at")
    license_cols = ("license_key", "license_type", "status", "created_at", "activated_at", "expires_at", "used_by")
    reset_cols = ("username", "token_hash", "created_at", "expires_at", "used_at")

    class FakeCursor:
        def __init__(self, backing):
            self.backing = backing
            self.rowcount = 0
            self.description = []
            self._rows = []

        def execute(self, sql, params=None):
            text = " ".join(str(sql).split()).upper()
            params = params or ()
            self.rowcount = 0
            self.description = []
            self._rows = []

            if text.startswith("SELECT USERNAME, PASSWORD, EMAIL, ROLE, GRANDFATHERED, LICENSE_KEY, LICENSE_EXEMPT, CREATED_AT FROM USERS"):
                self.description = [(col,) for col in user_cols]
                rows = [self.backing["users"][key] for key in sorted(self.backing["users"].keys())]
                self._rows = [tuple(row.get(col) for col in user_cols) for row in rows]
                return

            if text.startswith("SELECT LICENSE_KEY, LICENSE_TYPE, STATUS, CREATED_AT, ACTIVATED_AT, EXPIRES_AT, USED_BY FROM LICENSES"):
                self.description = [(col,) for col in license_cols]
                rows = [self.backing["licenses"][key] for key in sorted(self.backing["licenses"].keys())]
                self._rows = [tuple(row.get(col) for col in license_cols) for row in rows]
                return

            if text.startswith("SELECT USERNAME, TOKEN_HASH, CREATED_AT, EXPIRES_AT, USED_AT FROM PASSWORD_RESETS"):
                self.description = [(col,) for col in reset_cols]
                rows = [self.backing["password_resets"][key] for key in sorted(self.backing["password_resets"].keys())]
                self._rows = [tuple(row.get(col) for col in reset_cols) for row in rows]
                return

            if text.startswith("INSERT INTO USERS"):
                username = params[0]
                if username not in self.backing["users"]:
                    self.backing["users"][username] = dict(zip(user_cols, params))
                    self.rowcount = 1
                return

            if text.startswith("INSERT INTO LICENSES"):
                license_key = params[0]
                if license_key not in self.backing["licenses"]:
                    self.backing["licenses"][license_key] = dict(zip(license_cols, params))
                    self.rowcount = 1
                return

            if text.startswith("INSERT INTO PASSWORD_RESETS"):
                token_hash = params[1]
                if token_hash not in self.backing["password_resets"]:
                    self.backing["password_resets"][token_hash] = dict(zip(reset_cols, params))
                    self.rowcount = 1
                return

        def fetchall(self):
            return list(self._rows)

    class FakeConn:
        def __init__(self, backing):
            self.backing = backing

        def cursor(self):
            return FakeCursor(self.backing)

        def commit(self):
            return None

        def rollback(self):
            return None

        def close(self):
            return None

    return SimpleNamespace(connect=lambda url: FakeConn(store))


def test_find_existing_sqlite_auth_db_finds_legacy_user_db(tmp_path):
    legacy = tmp_path / "user.db"
    legacy.write_bytes(b"sqlite")
    previous_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        found = auth_storage.find_existing_sqlite_auth_db(
            explicit_path=None,
            default_name=str(tmp_path / "users.db"),
        )
        assert Path(found).resolve() == legacy.resolve()
    finally:
        os.chdir(previous_cwd)

    found = auth_storage.find_existing_sqlite_auth_db(
        explicit_path=str(legacy),
        default_name=str(tmp_path / "users.db"),
    )
    assert Path(found).resolve() == legacy.resolve()


def test_migrate_sqlite_auth_to_postgres_is_idempotent(tmp_path, monkeypatch):
    sqlite_path = tmp_path / "user.db"
    _make_sqlite_auth_db(sqlite_path)

    store = {
        "users": {},
        "licenses": set(),
        "password_resets": set(),
    }

    class FakeCursor:
        def __init__(self, backing):
            self.backing = backing
            self.rowcount = 0

        def execute(self, sql, params=None):
            text = " ".join(str(sql).split()).upper()
            self.rowcount = 0
            params = params or ()
            if text.startswith("INSERT INTO USERS"):
                key = params[0]
                if key not in self.backing["users"]:
                    self.backing["users"][key] = params[1]
                    self.rowcount = 1
            elif text.startswith("INSERT INTO LICENSES"):
                key = params[0]
                if key not in self.backing["licenses"]:
                    self.backing["licenses"].add(key)
                    self.rowcount = 1
            elif text.startswith("INSERT INTO PASSWORD_RESETS"):
                key = params[1]
                if key not in self.backing["password_resets"]:
                    self.backing["password_resets"].add(key)
                    self.rowcount = 1

    class FakeConn:
        def __init__(self, backing):
            self.backing = backing
            self.commits = 0

        def cursor(self):
            return FakeCursor(self.backing)

        def commit(self):
            self.commits += 1

        def rollback(self):
            return None

        def close(self):
            return None

    fake_driver = SimpleNamespace(connect=lambda url: FakeConn(store))
    monkeypatch.setattr(auth_storage, "psycopg2", fake_driver)

    first = auth_storage.migrate_sqlite_auth_to_postgres(
        sqlite_path=str(sqlite_path),
        database_url="postgresql://example/render",
    )
    second = auth_storage.migrate_sqlite_auth_to_postgres(
        sqlite_path=str(sqlite_path),
        database_url="postgresql://example/render",
    )

    assert first["users"] == 1
    assert first["licenses"] == 1
    assert first["password_resets"] == 1
    assert second["users"] == 0
    assert second["licenses"] == 0
    assert second["password_resets"] == 0
    assert store["users"]["alice"] == "pbkdf2:sha256:hash"


def test_export_and_restore_postgres_auth_backup_preserves_hashes(tmp_path, monkeypatch):
    source_store = {
        "users": {
            "alice": {
                "username": "alice",
                "password": "pbkdf2:sha256:exported-hash",
                "email": "alice@example.com",
                "role": "user",
                "grandfathered": 1,
                "license_key": "LIC-123",
                "license_exempt": 0,
                "created_at": "2026-03-30 10:00:00",
            }
        },
        "licenses": {
            "LIC-123": {
                "license_key": "LIC-123",
                "license_type": "monthly",
                "status": "active",
                "created_at": "2026-03-01 00:00:00",
                "activated_at": "2026-03-02 00:00:00",
                "expires_at": "2026-04-01 00:00:00",
                "used_by": "alice",
            }
        },
        "password_resets": {
            "tokenhash-1": {
                "username": "alice",
                "token_hash": "tokenhash-1",
                "created_at": "2026-03-10 00:00:00",
                "expires_at": "2026-03-10 00:30:00",
                "used_at": None,
            }
        },
    }
    backup_path = tmp_path / "auth-backup.json"
    monkeypatch.setattr(auth_storage, "psycopg2", _make_fake_pg_driver(source_store))

    exported = auth_storage.export_postgres_auth_backup(
        database_url="postgresql://example/source",
        backup_path=str(backup_path),
    )

    target_store = {"users": {}, "licenses": {}, "password_resets": {}}
    monkeypatch.setattr(auth_storage, "psycopg2", _make_fake_pg_driver(target_store))

    first = auth_storage.restore_postgres_auth_backup(
        database_url="postgresql://example/target",
        backup_path=str(backup_path),
    )
    second = auth_storage.restore_postgres_auth_backup(
        database_url="postgresql://example/target",
        backup_path=str(backup_path),
    )

    assert exported["users"][0]["password"] == "pbkdf2:sha256:exported-hash"
    assert first["users"] == 1
    assert first["licenses"] == 1
    assert first["password_resets"] == 1
    assert second["users"] == 0
    assert second["licenses"] == 0
    assert second["password_resets"] == 0
    assert target_store["users"]["alice"]["password"] == "pbkdf2:sha256:exported-hash"
