import json
import os
import sqlite3
from datetime import datetime

try:
    import psycopg2
except Exception:
    psycopg2 = None


def normalize_database_url(url):
    raw = str(url or "").strip()
    if raw.startswith("postgres://"):
        return "postgresql://" + raw[len("postgres://"):]
    return raw


def iter_sqlite_auth_db_candidates(*, explicit_path=None, default_name="users.db"):
    # Keep legacy SQLite filenames in the search list so older local auth DBs
    # can still be migrated even if the runtime fallback file name changed.
    seen = set()
    for raw in (
        explicit_path,
        os.environ.get("SQLITE_DB_PATH"),
        "user.db",
        default_name,
        "users.db",
    ):
        path = str(raw or "").strip()
        if not path:
            continue
        norm = os.path.normcase(os.path.abspath(path))
        if norm in seen:
            continue
        seen.add(norm)
        yield path


def find_existing_sqlite_auth_db(*, explicit_path=None, default_name="users.db"):
    for path in iter_sqlite_auth_db_candidates(explicit_path=explicit_path, default_name=default_name):
        if os.path.exists(path):
            return path
    return None


def utc_now_str():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def normalize_license_key(key):
    return str(key or "").strip().upper().replace(" ", "")


def _connect_postgres(database_url):
    db_url = normalize_database_url(database_url)
    if not db_url:
        raise RuntimeError("DATABASE_URL is required for Postgres auth storage.")
    if psycopg2 is None:
        raise RuntimeError("psycopg2 is not installed. Add psycopg2-binary to requirements.txt.")
    return psycopg2.connect(db_url)


def _ensure_postgres_user_columns(cursor):
    # Mirror the existing auth schema closely so the running bot keeps the same
    # login, admin, license, and reset behavior after the storage swap.
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'user'")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS grandfathered INTEGER DEFAULT 1")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS license_key TEXT")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS license_exempt INTEGER DEFAULT 0")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TEXT")


def ensure_postgres_auth_tables(database_url):
    conn = _connect_postgres(database_url)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
            """
        )
        _ensure_postgres_user_columns(cur)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS licenses (
                license_key TEXT PRIMARY KEY,
                license_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TIMESTAMP NOT NULL,
                activated_at TIMESTAMP NULL,
                expires_at TIMESTAMP NULL,
                used_by TEXT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS password_resets (
                id BIGSERIAL PRIMARY KEY,
                username TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used_at TIMESTAMP NULL
            )
            """
        )
        now_s = utc_now_str()
        cur.execute("UPDATE users SET role='user' WHERE role IS NULL OR TRIM(role)=''")
        cur.execute("UPDATE users SET grandfathered=1 WHERE grandfathered IS NULL")
        cur.execute("UPDATE users SET license_exempt=0 WHERE license_exempt IS NULL")
        cur.execute(
            "UPDATE users SET created_at=%s WHERE created_at IS NULL OR TRIM(created_at)=''",
            (now_s,),
        )
        conn.commit()
    finally:
        conn.close()


def _row_to_dict(description, row):
    columns = [col[0] for col in (description or [])]
    return {
        columns[index]: row[index]
        for index in range(min(len(columns), len(row)))
    }


def _json_safe_value(value):
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value


def export_postgres_auth_backup(*, database_url, backup_path):
    ensure_postgres_auth_tables(database_url)

    conn = _connect_postgres(database_url)
    try:
        cur = conn.cursor()
        payload = {
            "version": 1,
            "exported_at": utc_now_str(),
            "users": [],
            "licenses": [],
            "password_resets": [],
        }

        cur.execute(
            """
            SELECT username, password, email, role, grandfathered, license_key, license_exempt, created_at
            FROM users
            ORDER BY username ASC
            """
        )
        payload["users"] = [
            {key: _json_safe_value(value) for key, value in _row_to_dict(cur.description, row).items()}
            for row in (cur.fetchall() or [])
        ]

        cur.execute(
            """
            SELECT license_key, license_type, status, created_at, activated_at, expires_at, used_by
            FROM licenses
            ORDER BY license_key ASC
            """
        )
        payload["licenses"] = [
            {key: _json_safe_value(value) for key, value in _row_to_dict(cur.description, row).items()}
            for row in (cur.fetchall() or [])
        ]

        cur.execute(
            """
            SELECT username, token_hash, created_at, expires_at, used_at
            FROM password_resets
            ORDER BY username ASC, created_at ASC
            """
        )
        payload["password_resets"] = [
            {key: _json_safe_value(value) for key, value in _row_to_dict(cur.description, row).items()}
            for row in (cur.fetchall() or [])
        ]

        with open(backup_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        return payload
    finally:
        conn.close()


def restore_postgres_auth_backup(*, database_url, backup_path):
    if not backup_path or not os.path.exists(backup_path):
        raise FileNotFoundError(f"Backup file not found: {backup_path}")

    with open(backup_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    ensure_postgres_auth_tables(database_url)

    conn = _connect_postgres(database_url)
    counts = {"users": 0, "licenses": 0, "password_resets": 0, "backup_path": backup_path}
    try:
        cur = conn.cursor()

        for row in payload.get("users", []) or []:
            cur.execute(
                """
                INSERT INTO users (username, password, email, role, grandfathered, license_key, license_exempt, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (username) DO NOTHING
                """,
                (
                    row.get("username"),
                    row.get("password"),  # restore original password hashes as stored
                    row.get("email"),
                    row.get("role") or "user",
                    int(row.get("grandfathered") if row.get("grandfathered") is not None else 1),
                    row.get("license_key"),
                    int(row.get("license_exempt") if row.get("license_exempt") is not None else 0),
                    row.get("created_at") or utc_now_str(),
                ),
            )
            counts["users"] += max(int(getattr(cur, "rowcount", 0) or 0), 0)

        for row in payload.get("licenses", []) or []:
            license_key = normalize_license_key(row.get("license_key"))
            if not license_key:
                continue
            cur.execute(
                """
                INSERT INTO licenses (license_key, license_type, status, created_at, activated_at, expires_at, used_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (license_key) DO NOTHING
                """,
                (
                    license_key,
                    row.get("license_type") or "monthly",
                    row.get("status") or "active",
                    row.get("created_at") or utc_now_str(),
                    row.get("activated_at"),
                    row.get("expires_at"),
                    row.get("used_by"),
                ),
            )
            counts["licenses"] += max(int(getattr(cur, "rowcount", 0) or 0), 0)

        for row in payload.get("password_resets", []) or []:
            token_hash = str(row.get("token_hash") or "").strip()
            if not token_hash:
                continue
            cur.execute(
                """
                INSERT INTO password_resets (username, token_hash, created_at, expires_at, used_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (token_hash) DO NOTHING
                """,
                (
                    row.get("username"),
                    token_hash,
                    row.get("created_at") or utc_now_str(),
                    row.get("expires_at") or utc_now_str(),
                    row.get("used_at"),
                ),
            )
            counts["password_resets"] += max(int(getattr(cur, "rowcount", 0) or 0), 0)

        conn.commit()
        return counts
    except Exception:
        conn.rollback()
        raise


def migrate_sqlite_auth_to_postgres(*, sqlite_path, database_url):
    if not sqlite_path:
        raise FileNotFoundError("SQLite auth DB path is required.")
    if not os.path.exists(sqlite_path):
        raise FileNotFoundError(f"SQLite auth DB not found: {sqlite_path}")

    ensure_postgres_auth_tables(database_url)

    sconn = sqlite3.connect(sqlite_path)
    sconn.row_factory = sqlite3.Row
    pconn = _connect_postgres(database_url)
    counts = {"users": 0, "licenses": 0, "password_resets": 0, "sqlite_path": sqlite_path}
    try:
        scur = sconn.cursor()
        scur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row["name"] for row in scur.fetchall()}
        pcur = pconn.cursor()

        if "users" in tables:
            scur.execute("SELECT * FROM users")
            for row in scur.fetchall():
                data = dict(row)
                pcur.execute(
                    """
                    INSERT INTO users (username, password, email, role, grandfathered, license_key, license_exempt, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (username) DO NOTHING
                    """,
                    (
                        data.get("username"),
                        data.get("password"),  # keep existing password hashes exactly
                        data.get("email"),
                        data.get("role") or "user",
                        int(data.get("grandfathered") if data.get("grandfathered") is not None else 1),
                        data.get("license_key"),
                        int(data.get("license_exempt") if data.get("license_exempt") is not None else 0),
                        data.get("created_at") or utc_now_str(),
                    ),
                )
                counts["users"] += max(int(getattr(pcur, "rowcount", 0) or 0), 0)

        if "licenses" in tables:
            scur.execute("SELECT * FROM licenses")
            for row in scur.fetchall():
                data = dict(row)
                license_key = normalize_license_key(data.get("license_key"))
                if not license_key:
                    continue
                pcur.execute(
                    """
                    INSERT INTO licenses (license_key, license_type, status, created_at, activated_at, expires_at, used_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (license_key) DO NOTHING
                    """,
                    (
                        license_key,
                        data.get("license_type") or "monthly",
                        data.get("status") or "active",
                        data.get("created_at") or utc_now_str(),
                        data.get("activated_at"),
                        data.get("expires_at"),
                        data.get("used_by"),
                    ),
                )
                counts["licenses"] += max(int(getattr(pcur, "rowcount", 0) or 0), 0)

        if "password_resets" in tables:
            scur.execute("SELECT * FROM password_resets")
            for row in scur.fetchall():
                data = dict(row)
                token_hash = str(data.get("token_hash") or "").strip()
                if not token_hash:
                    continue
                pcur.execute(
                    """
                    INSERT INTO password_resets (username, token_hash, created_at, expires_at, used_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (token_hash) DO NOTHING
                    """,
                    (
                        data.get("username"),
                        token_hash,
                        data.get("created_at") or utc_now_str(),
                        data.get("expires_at") or utc_now_str(),
                        data.get("used_at"),
                    ),
                )
                counts["password_resets"] += max(int(getattr(pcur, "rowcount", 0) or 0), 0)

        pconn.commit()
        return counts
    except Exception:
        pconn.rollback()
        raise
    finally:
        try:
            sconn.close()
        except Exception:
            pass
        try:
            pconn.close()
        except Exception:
            pass
