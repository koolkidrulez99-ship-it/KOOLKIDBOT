import os, sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import json
import threading
import websocket
import time
import uuid
import sqlite3
import random  # PATCH 1A
import secrets
import hashlib
import statistics
from collections import deque

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_file
from flask_socketio import SocketIO, join_room
from datetime import datetime, timedelta
import logging
from werkzeug.security import generate_password_hash, check_password_hash

# STRATEGIES
from strategies.koolkid import KoolKidStrategy
from strategies.jokerjoe import JokerJoeStrategy
from strategies.human import HumanStrategy
try:
    from strategies.unchain import UnchainStrategy
except Exception:
    import importlib.util
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    _UNCHAIN_FALLBACK = os.path.join(_BASE_DIR, "unchain_fix_round3_patch", "strategies", "unchain.py")
    if os.path.exists(_UNCHAIN_FALLBACK):
        _spec = importlib.util.spec_from_file_location("unchain_fallback_strategy", _UNCHAIN_FALLBACK)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        UnchainStrategy = _mod.UnchainStrategy
    else:
        raise

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder="templates")

# ===============================
# ENV VARIABLES (SAFE DEFAULTS)
# ===============================
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "koolkid-secret-key-2025")

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "koolkidrulez")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Koolkid@12345")

MAX_USERS = int(os.environ.get("MAX_USERS", "150"))

# NOTE: keep as you had it
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",
    manage_session=False,
    ping_interval=25,
    ping_timeout=60,
)

DERIV_WS = "wss://ws.derivws.com/websockets/v3?app_id=1089"

# DATABASE FILE (SQLite fallback for laptop/local testing)
DB_FILE = "users.db"

# Render / production Postgres (persistent users across deploys/restarts)
DATABASE_URL = (os.environ.get("DATABASE_URL") or "").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

try:
    import psycopg2
except Exception:
    psycopg2 = None

DB_BACKEND = "postgres" if DATABASE_URL else "sqlite"
if DB_BACKEND == "postgres" and psycopg2 is None:
    raise RuntimeError("DATABASE_URL is set but psycopg2 is not installed. Add psycopg2-binary to requirements.txt")

# ==========================
# MULTI-CLIENT STATE
# ==========================
clients = {}

# heartbeat timeout (effectively disabled to avoid disconnects)
HEARTBEAT_TIMEOUT_SEC = 10**12



# ---------------- DATABASE + LICENSE/AUTH SETUP ---------------- #
def _db_is_postgres():
    return DB_BACKEND == "postgres"


def _db_connect(row_factory=False):
    if _db_is_postgres():
        return psycopg2.connect(DATABASE_URL)
    conn = sqlite3.connect(DB_FILE)
    if row_factory:
        conn.row_factory = sqlite3.Row
    return conn


def _db_execute(cursor, sql, params=()):
    if _db_is_postgres():
        sql = sql.replace("?", "%s")
    return cursor.execute(sql, params)


def _db_fetchone(cursor):
    return cursor.fetchone()


def _db_commit(conn):
    try:
        conn.commit()
    except Exception:
        pass


def _table_has_column_sqlite(conn, table_name, column_name):
    c = conn.cursor()
    c.execute(f"PRAGMA table_info({table_name})")
    cols = {row[1] for row in c.fetchall()}
    return column_name in cols


def _db_row_to_dict(cursor, row):
    if row is None:
        return None
    try:
        if hasattr(row, "keys"):
            return {k: row[k] for k in row.keys()}
    except Exception:
        pass
    try:
        cols = [d[0] for d in (cursor.description or [])]
        return {cols[i]: row[i] for i in range(min(len(cols), len(row)))}
    except Exception:
        return None


def _db_fetchall_dicts(cursor):
    rows = cursor.fetchall()
    return [(_db_row_to_dict(cursor, r) or {}) for r in (rows or [])]


def _utc_now_str():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _parse_dt(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt)
        except Exception:
            pass
    return None


def normalize_license_key(key):
    return str(key or "").strip().upper().replace(" ", "")


def _db_add_user_column_if_missing(conn, column_name, column_def_sql):
    if _db_is_postgres():
        cur = conn.cursor()
        cur.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {column_name} {column_def_sql}")
        return
    if not _table_has_column_sqlite(conn, "users", column_name):
        cur = conn.cursor()
        cur.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_def_sql}")


def _db_create_auth_tables(conn):
    c = conn.cursor()
    if _db_is_postgres():
        c.execute("""
        CREATE TABLE IF NOT EXISTS licenses (
            license_key TEXT PRIMARY KEY,
            license_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMP NOT NULL,
            activated_at TIMESTAMP NULL,
            expires_at TIMESTAMP NULL,
            used_by TEXT NULL
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS password_resets (
            id BIGSERIAL PRIMARY KEY,
            username TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used_at TIMESTAMP NULL
        )
        """)
    else:
        c.execute("""
        CREATE TABLE IF NOT EXISTS licenses (
            license_key TEXT PRIMARY KEY,
            license_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            activated_at TEXT,
            expires_at TEXT,
            used_by TEXT
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT
        )
        """)


def init_db():
    conn = _db_connect()
    c = conn.cursor()

    if _db_is_postgres():
        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id BIGSERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
        """)
    else:
        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
        """)

    # Safe migrations for auth/license support
    _db_add_user_column_if_missing(conn, "email", "TEXT")
    _db_add_user_column_if_missing(conn, "role", "TEXT DEFAULT 'user'")
    _db_add_user_column_if_missing(conn, "grandfathered", "INTEGER DEFAULT 1")
    _db_add_user_column_if_missing(conn, "license_key", "TEXT")
    _db_add_user_column_if_missing(conn, "license_exempt", "INTEGER DEFAULT 0")
    _db_add_user_column_if_missing(conn, "created_at", "TEXT")

    _db_create_auth_tables(conn)

    now_s = _utc_now_str()
    _db_execute(c, "UPDATE users SET role='user' WHERE role IS NULL OR TRIM(role)=''", ())
    _db_execute(c, "UPDATE users SET grandfathered=1 WHERE grandfathered IS NULL", ())
    _db_execute(c, "UPDATE users SET license_exempt=0 WHERE license_exempt IS NULL", ())
    _db_execute(c, "UPDATE users SET created_at=? WHERE created_at IS NULL OR TRIM(created_at)=''", (now_s,))
    _db_commit(conn)
    conn.close()


def _maybe_migrate_sqlite_users_to_postgres():
    # One-time migration for Render deployment: import local SQLite rows if present
    if not _db_is_postgres():
        return
    if not os.path.exists(DB_FILE):
        return
    try:
        sconn = sqlite3.connect(DB_FILE)
        sconn.row_factory = sqlite3.Row
        scur = sconn.cursor()
        scur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {r["name"] for r in scur.fetchall()}
    except Exception as e:
        logger.warning(f"SQLite -> Postgres migration skipped (open/read error): {e}")
        try:
            sconn.close()
        except Exception:
            pass
        return

    pconn = None
    try:
        pconn = _db_connect()
        pcur = pconn.cursor()
        migrated_users = migrated_lic = migrated_resets = 0

        if "users" in tables:
            scur.execute("SELECT * FROM users")
            for r in scur.fetchall():
                rd = dict(r)
                try:
                    pcur.execute(
                        """
                        INSERT INTO users (username, password, email, role, grandfathered, license_key, license_exempt, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (username) DO NOTHING
                        """,
                        (
                            rd.get("username"),
                            rd.get("password"),
                            rd.get("email"),
                            rd.get("role") or "user",
                            int(rd.get("grandfathered") if rd.get("grandfathered") is not None else 1),
                            rd.get("license_key"),
                            int(rd.get("license_exempt") if rd.get("license_exempt") is not None else 0),
                            rd.get("created_at") or _utc_now_str(),
                        ),
                    )
                    migrated_users += max(int(getattr(pcur, "rowcount", 0) or 0), 0)
                except Exception as e_row:
                    logger.warning(f"SQLite->PG user migrate skip {rd.get('username')!r}: {e_row}")

        if "licenses" in tables:
            scur.execute("SELECT * FROM licenses")
            for r in scur.fetchall():
                rd = dict(r)
                key = normalize_license_key(rd.get("license_key"))
                if not key:
                    continue
                try:
                    pcur.execute(
                        """
                        INSERT INTO licenses (license_key, license_type, status, created_at, activated_at, expires_at, used_by)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (license_key) DO NOTHING
                        """,
                        (
                            key,
                            rd.get("license_type") or "monthly",
                            rd.get("status") or "active",
                            rd.get("created_at") or _utc_now_str(),
                            rd.get("activated_at"),
                            rd.get("expires_at"),
                            rd.get("used_by"),
                        ),
                    )
                    migrated_lic += max(int(getattr(pcur, "rowcount", 0) or 0), 0)
                except Exception as e_row:
                    logger.warning(f"SQLite->PG license migrate skip {key!r}: {e_row}")

        if "password_resets" in tables:
            scur.execute("SELECT * FROM password_resets")
            for r in scur.fetchall():
                rd = dict(r)
                if not rd.get("token_hash"):
                    continue
                try:
                    pcur.execute(
                        """
                        INSERT INTO password_resets (username, token_hash, created_at, expires_at, used_at)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (token_hash) DO NOTHING
                        """,
                        (
                            rd.get("username"),
                            rd.get("token_hash"),
                            rd.get("created_at") or _utc_now_str(),
                            rd.get("expires_at") or _utc_now_str(),
                            rd.get("used_at"),
                        ),
                    )
                    migrated_resets += max(int(getattr(pcur, "rowcount", 0) or 0), 0)
                except Exception as e_row:
                    logger.warning(f"SQLite->PG reset migrate skip: {e_row}")

        pconn.commit()
        logger.info(f"SQLite -> Postgres migration checked (users={migrated_users}, licenses={migrated_lic}, resets={migrated_resets})")
    except Exception as e:
        logger.error(f"SQLite -> Postgres migration failed: {e}")
    finally:
        try:
            sconn.close()
        except Exception:
            pass
        try:
            if pconn:
                pconn.close()
        except Exception:
            pass


def ensure_admin_user():
    conn = _db_connect()
    c = conn.cursor()
    _db_execute(c, "SELECT id FROM users WHERE lower(username)=lower(?)", (ADMIN_USERNAME,))
    exists = _db_fetchone(c)

    if not exists:
        hashed_pw = generate_password_hash(ADMIN_PASSWORD)
        _db_execute(
            c,
            """
            INSERT INTO users (username, password, role, grandfathered, license_exempt, created_at)
            VALUES (?, ?, 'admin', 1, 1, ?)
            """,
            (ADMIN_USERNAME, hashed_pw, _utc_now_str()),
        )
        _db_commit(conn)
        print(f"✅ Admin account created automatically: {ADMIN_USERNAME}")
    else:
        _db_execute(
            c,
            """
            UPDATE users SET role='admin', grandfathered=1, license_exempt=1,
                   created_at=COALESCE(created_at, ?)
             WHERE lower(username)=lower(?)
            """,
            (_utc_now_str(), ADMIN_USERNAME),
        )
        _db_commit(conn)
    conn.close()


def get_user_count():
    conn = _db_connect()
    c = conn.cursor()
    _db_execute(c, "SELECT COUNT(*) FROM users WHERE lower(username) != lower(?)", (ADMIN_USERNAME,))
    row = _db_fetchone(c)
    conn.close()
    return int((row[0] if row else 0) or 0)


def _get_user_row(username):
    conn = _db_connect(row_factory=not _db_is_postgres())
    c = conn.cursor()
    _db_execute(c, "SELECT * FROM users WHERE username = ?", (username,))
    row = _db_fetchone(c)
    out = _db_row_to_dict(c, row)
    conn.close()
    return out


def _get_license_row(license_key):
    key = normalize_license_key(license_key)
    if not key:
        return None
    conn = _db_connect(row_factory=not _db_is_postgres())
    c = conn.cursor()
    _db_execute(c, "SELECT * FROM licenses WHERE license_key = ?", (key,))
    row = _db_fetchone(c)
    out = _db_row_to_dict(c, row)
    conn.close()
    return out


def _license_is_expired(license_row):
    if not license_row:
        return True
    if str(license_row.get("license_type") or "").lower() == "lifetime":
        return False
    exp = _parse_dt(license_row.get("expires_at"))
    if exp is None:
        return False
    return datetime.utcnow() > exp


def check_user_license_access(user_row):
    if not user_row:
        return False, "User not found"
    role = str(user_row.get("role") or "user").lower()
    if role == "admin":
        return True, "admin"
    if int(user_row.get("license_exempt") or 0) == 1:
        return True, "license_exempt"
    if int(user_row.get("grandfathered") if user_row.get("grandfathered") is not None else 1) == 1:
        return True, "grandfathered"

    linked_key = normalize_license_key(user_row.get("license_key"))
    if not linked_key:
        return False, "No license linked to this account. Contact admin."
    lic = _get_license_row(linked_key)
    if not lic:
        return False, "Linked license key not found. Contact admin."
    if str(lic.get("status") or "").lower() == "revoked":
        return False, "Your license was revoked. Contact admin."
    if _license_is_expired(lic):
        return False, "Your license has expired. Please renew."
    return True, "active"


def _validate_license_for_registration(conn, license_key):
    key = normalize_license_key(license_key)
    if not key:
        return False, "License key is required"
    c = conn.cursor()
    _db_execute(c, "SELECT * FROM licenses WHERE license_key = ?", (key,))
    rowd = _db_row_to_dict(c, _db_fetchone(c))
    if not rowd:
        return False, "Invalid license key"
    if str(rowd.get("status") or "").lower() == "revoked":
        return False, "This license key has been revoked"
    if str(rowd.get("used_by") or "").strip():
        return False, "This license key has already been used"
    ltype = str(rowd.get("license_type") or "").lower()
    if ltype not in ("monthly", "lifetime"):
        return False, "Unsupported license key type"
    return True, rowd


def _consume_license_for_new_user(conn, license_key, username):
    ok, row_or_msg = _validate_license_for_registration(conn, license_key)
    if not ok:
        return False, row_or_msg
    rowd = row_or_msg
    now_s = _utc_now_str()
    expires_at = None
    if str(rowd.get("license_type") or "").lower() == "monthly":
        expires_at = (datetime.utcnow() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    c = conn.cursor()
    _db_execute(
        c,
        "UPDATE licenses SET used_by=?, activated_at=?, expires_at=? WHERE license_key=?",
        (username, now_s, expires_at, normalize_license_key(license_key)),
    )
    return True, normalize_license_key(license_key)


def create_user(username, password, email=None, license_key=None, *, role="user", grandfathered=0, license_exempt=0):
    username = (username or "").strip()
    if not username:
        return False, "Username is required"
    if username.lower() == ADMIN_USERNAME.lower() and str(role).lower() != "admin":
        return False, "Username is reserved"
    if str(role).lower() != "admin" and get_user_count() >= MAX_USERS:
        return False, f"User limit reached ({MAX_USERS} max)"

    conn = _db_connect()
    c = conn.cursor()
    hashed_pw = generate_password_hash(password)
    try:
        linked_license_key = None
        if str(role).lower() != "admin" and int(license_exempt or 0) != 1 and int(grandfathered or 0) != 1:
            lic_ok, lic_result = _consume_license_for_new_user(conn, license_key, username)
            if not lic_ok:
                try:
                    conn.rollback()
                except Exception:
                    pass
                return False, lic_result
            linked_license_key = lic_result

        _db_execute(
            c,
            """
            INSERT INTO users (username, password, email, role, grandfathered, license_key, license_exempt, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                username,
                hashed_pw,
                (email or None),
                str(role or "user").lower(),
                int(1 if grandfathered else 0),
                linked_license_key,
                int(1 if license_exempt else 0),
                _utc_now_str(),
            ),
        )
        _db_commit(conn)
        return True, "User created"
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        msg = str(e).lower()
        if "unique" in msg or "duplicate" in msg:
            return False, "Username already exists"
        logger.error(f"create_user DB error: {e}")
        return False, "Database error"
    finally:
        conn.close()


def verify_user(username, password):
    row = _get_user_row(username)
    if not row:
        return False
    try:
        return check_password_hash(row.get("password", ""), password)
    except Exception:
        return False


def _validate_password_strength(password):
    password = (password or "").strip()
    if len(password) < 8:
        return "Password must be at least 8 characters"
    if password.isdigit() or password.isalpha():
        return "Password must include letters and numbers"
    return None


def _find_user_for_reset(identifier):
    identifier = (identifier or "").strip()
    if not identifier:
        return None
    conn = _db_connect(row_factory=not _db_is_postgres())
    c = conn.cursor()
    _db_execute(c, "SELECT * FROM users WHERE lower(username)=lower(?) OR lower(COALESCE(email,''))=lower(?) LIMIT 1", (identifier, identifier))
    row = _db_fetchone(c)
    out = _db_row_to_dict(c, row)
    conn.close()
    return out


def _hash_reset_token(token):
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def _create_password_reset_token(username, minutes_valid=30):
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_reset_token(raw_token)
    now_dt = datetime.utcnow()
    exp_dt = now_dt + timedelta(minutes=minutes_valid)
    now_s = now_dt.strftime("%Y-%m-%d %H:%M:%S")
    exp_s = exp_dt.strftime("%Y-%m-%d %H:%M:%S")

    conn = _db_connect()
    c = conn.cursor()
    _db_execute(c, "UPDATE password_resets SET used_at=? WHERE username=? AND used_at IS NULL", (now_s, username))
    _db_execute(c, "INSERT INTO password_resets (username, token_hash, created_at, expires_at, used_at) VALUES (?, ?, ?, ?, NULL)",
                (username, token_hash, now_s, exp_s))
    _db_commit(conn)
    conn.close()
    return raw_token, exp_dt


def _get_reset_token_record(raw_token):
    token = (raw_token or "").strip()
    if not token:
        return None, "Missing reset token"

    conn = _db_connect(row_factory=not _db_is_postgres())
    c = conn.cursor()
    _db_execute(c, "SELECT id, username, created_at, expires_at, used_at FROM password_resets WHERE token_hash=?", (_hash_reset_token(token),))
    rec = _db_row_to_dict(c, _db_fetchone(c))
    conn.close()

    if not rec:
        return None, "Invalid reset token"
    if rec.get("used_at"):
        return None, "This reset link has already been used"

    exp_dt = _parse_dt(rec.get("expires_at"))
    if exp_dt is None:
        return None, "Reset token is invalid"
    if datetime.utcnow() > exp_dt:
        return None, "This reset link has expired"
    return rec, None


def _mark_reset_token_used(token_id):
    conn = _db_connect()
    c = conn.cursor()
    _db_execute(c, "UPDATE password_resets SET used_at=? WHERE id=?", (_utc_now_str(), token_id))
    _db_commit(conn)
    conn.close()


def _update_user_password(username, new_password):
    conn = _db_connect()
    c = conn.cursor()
    _db_execute(c, "UPDATE users SET password=? WHERE username=?", (generate_password_hash(new_password), username))
    ok = (getattr(c, "rowcount", 0) or 0) > 0
    _db_commit(conn)
    conn.close()
    return bool(ok)


def _validate_reset_license_for_user(user_row, provided_license_key):
    if not user_row:
        return False, "User not found"
    role = str(user_row.get("role") or "user").lower()
    if role == "admin" or int(user_row.get("license_exempt") or 0) == 1:
        return True, None
    linked_key = normalize_license_key(user_row.get("license_key"))
    if not linked_key:
        return False, "This account has no linked license key. Contact admin to reset password."
    entered_key = normalize_license_key(provided_license_key)
    if not entered_key:
        return False, "License key is required for password reset"
    if entered_key != linked_key:
        return False, "License key does not match this account"
    return True, None


def _generate_license_key(license_type):
    prefix = "KK-MTH" if str(license_type).lower() == "monthly" else "KK-LIFE"
    chunk = lambda: uuid.uuid4().hex[:4].upper()
    return f"{prefix}-{chunk()}-{chunk()}-{chunk()}"


def create_license_record(license_type):
    ltype = str(license_type or "").strip().lower()
    if ltype not in ("monthly", "lifetime"):
        return False, "Invalid license type", None
    conn = _db_connect()
    c = conn.cursor()
    try:
        for _ in range(20):
            key = _generate_license_key(ltype)
            try:
                _db_execute(c, "INSERT INTO licenses (license_key, license_type, status, created_at) VALUES (?, ?, 'active', ?)", (key, ltype, _utc_now_str()))
                _db_commit(conn)
                return True, "License created", key
            except Exception as e:
                msg = str(e).lower()
                if "unique" in msg or "duplicate" in msg:
                    continue
                raise
        return False, "Failed to generate unique key", None
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return False, str(e), None
    finally:
        conn.close()


def revoke_license_record(license_key):
    key = normalize_license_key(license_key)
    if not key:
        return False, "License key is required"
    conn = _db_connect()
    c = conn.cursor()
    _db_execute(c, "UPDATE licenses SET status='revoked' WHERE license_key = ?", (key,))
    changed = (getattr(c, "rowcount", 0) or 0)
    _db_commit(conn)
    conn.close()
    if changed <= 0:
        return False, "License key not found"
    return True, "License revoked"


def _reset_license_binding_for_user(conn, username):
    c = conn.cursor()
    _db_execute(c, "UPDATE licenses SET used_by=NULL, activated_at=NULL, expires_at=CASE WHEN lower(license_type)='monthly' THEN NULL ELSE expires_at END WHERE used_by=?", (username,))


def admin_reset_user_license(username):
    username = (username or "").strip()
    if not username:
        return False, "Username is required"
    if username.lower() == ADMIN_USERNAME.lower():
        return False, "Admin account is protected"
    conn = _db_connect()
    c = conn.cursor()
    _db_execute(c, "SELECT username FROM users WHERE username = ?", (username,))
    if not _db_fetchone(c):
        conn.close()
        return False, "User not found"
    try:
        _reset_license_binding_for_user(conn, username)
        _db_execute(c, "UPDATE users SET license_key=NULL WHERE username=?", (username,))
        _db_commit(conn)
        return True, "User license key reset"
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return False, str(e)
    finally:
        conn.close()


def admin_reassign_user_license(username, license_key):
    username = (username or "").strip()
    key = normalize_license_key(license_key)
    if not username or not key:
        return False, "Username and license key are required"
    if username.lower() == ADMIN_USERNAME.lower():
        return False, "Admin account is protected"

    conn = _db_connect(row_factory=not _db_is_postgres())
    c = conn.cursor()
    try:
        _db_execute(c, "SELECT * FROM users WHERE username=?", (username,))
        user_row = _db_row_to_dict(c, _db_fetchone(c))
        if not user_row:
            return False, "User not found"

        _db_execute(c, "SELECT * FROM licenses WHERE license_key=?", (key,))
        lic_row = _db_row_to_dict(c, _db_fetchone(c))
        if not lic_row:
            return False, "License key not found"
        if str(lic_row.get("status") or "").lower() == "revoked":
            return False, "License key is revoked"

        used_by = str(lic_row.get("used_by") or "").strip()
        if used_by and used_by.lower() != username.lower():
            return False, "License key is already assigned to another user"

        _reset_license_binding_for_user(conn, username)

        now_s = _utc_now_str()
        expires_at = lic_row.get("expires_at")
        if str(lic_row.get("license_type") or "").lower() == "monthly":
            expires_at = (datetime.utcnow() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")

        _db_execute(c, "UPDATE licenses SET used_by=?, activated_at=?, expires_at=? WHERE license_key=?", (username, now_s, expires_at, key))
        _db_execute(c, "UPDATE users SET license_key=?, grandfathered=0, license_exempt=0 WHERE username=?", (key, username))
        _db_commit(conn)
        return True, "License key reassigned"
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return False, str(e)
    finally:
        conn.close()


def delete_user_admin(user_id):
    try:
        uid = int(user_id)
    except Exception:
        return False, "Invalid user ID"

    conn = _db_connect(row_factory=not _db_is_postgres())
    c = conn.cursor()
    _db_execute(c, "SELECT * FROM users WHERE id=?", (uid,))
    user_row = _db_row_to_dict(c, _db_fetchone(c))
    if not user_row:
        conn.close()
        return False, "User not found"
    if str(user_row.get("username") or "").lower() == ADMIN_USERNAME.lower():
        conn.close()
        return False, "Admin account is protected"

    try:
        _reset_license_binding_for_user(conn, user_row.get("username"))
        _db_execute(c, "DELETE FROM password_resets WHERE username=?", (user_row.get("username"),))
        _db_execute(c, "DELETE FROM users WHERE id=?", (uid,))
        _db_commit(conn)
        return True, "User deleted"
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return False, str(e)
    finally:
        conn.close()


def get_admin_users_view():
    conn = _db_connect(row_factory=not _db_is_postgres())
    c = conn.cursor()
    _db_execute(c, "SELECT * FROM users ORDER BY id ASC")
    rows = _db_fetchall_dicts(c)
    conn.close()
    out = []
    for r in rows:
        out.append({
            "id": r.get("id"),
            "username": r.get("username"),
            "email": r.get("email") or "",
            "role": (r.get("role") or "user"),
            "grandfathered": int(r.get("grandfathered") if r.get("grandfathered") is not None else 1),
            "license_key": r.get("license_key") or "",
            "license_exempt": int(r.get("license_exempt") or 0),
            "created_at": r.get("created_at") or "",
            "access": check_user_license_access(r)[1],
        })
    return out


def get_admin_users_view_legacy_tuples():
    return [(u["id"], u["username"], u["email"], 1 if str(u["role"]).lower()=="admin" else 0) for u in get_admin_users_view()]


def get_admin_licenses_view():
    conn = _db_connect(row_factory=not _db_is_postgres())
    c = conn.cursor()
    _db_execute(c, "SELECT license_key, license_type, status, used_by, created_at, activated_at, expires_at FROM licenses ORDER BY created_at DESC, license_key DESC")
    rows = _db_fetchall_dicts(c)
    conn.close()
    return rows


# Initialize DB + Admin
init_db()
if _db_is_postgres():
    logger.info("🗄️ Storage mode: postgres (Render persistent)")
    _maybe_migrate_sqlite_users_to_postgres()
else:
    logger.info(f"🗄️ Storage mode: sqlite fallback ({DB_FILE})")
ensure_admin_user()


# ---------------- HELPERS ---------------- #
def now_time():
    return datetime.now().strftime("%H:%M:%S")


def extract_last_decimal_digit(price, pip_size=2):
    try:
        fmt = "{:0." + str(int(pip_size)) + "f}"
        price_str = fmt.format(float(price))

        if "." not in price_str:
            return int(price_str[-1])

        decimal_part = price_str.split(".")[1]
        return int(decimal_part[-1])
    except Exception:
        return 0


def extract_exit_digit_from_contract(contract: dict):
    """
    Deriv digit contracts often include:
      - exit_tick_display_value (string)
      - exit_tick (float)
      - sell_spot / exit_spot (fallback)
    We want the LAST decimal digit.
    """
    try:
        val = contract.get("exit_tick_display_value")
        if val is None or val == "":
            val = contract.get("exit_tick")
        if val is None or val == "":
            val = contract.get("sell_spot") or contract.get("exit_spot")

        if val is None or val == "":
            return None

        s = str(val)

        if "." in s:
            dec = s.split(".", 1)[1]
            dec_digits = "".join(ch for ch in dec if ch.isdigit())
            if not dec_digits:
                return None
            return int(dec_digits[-1])

        digits = "".join(ch for ch in s if ch.isdigit())
        if not digits:
            return None
        return int(digits[-1])
    except Exception:
        return None


def login_required():
    username = session.get("user")
    if not username:
        return False
    user_row = _get_user_row(username)
    if not user_row:
        return False
    ok, _msg = check_user_license_access(user_row)
    return bool(ok)


def is_admin():
    if str(session.get("role") or "").lower() == "admin":
        return True
    user_row = _get_user_row(session.get("user"))
    return bool(user_row and str(user_row.get("role") or "").lower() == "admin")


def get_client_id():
    """
    Each browser / device gets its own client_id in the Flask session.
    Same username on 2 devices => 2 different client_ids => 2 independent bots.
    """
    cid = session.get("client_id")
    if not cid:
        cid = str(uuid.uuid4())
        session["client_id"] = cid
    return cid


def _new_req_id():
    return int(uuid.uuid4().int % 1000000000)


def _touch_client(client_id):
    st = clients.get(client_id)
    if st:
        st["last_seen"] = time.time()


def _hard_stop_all_strategies(state):
    """
    Your rule: when API disconnected -> everything stops (auto + memory).
    We reset strategies and force all auto flags OFF safely.
    """
    for strat in state.get("strategies", {}).values():
        try:
            strat.reset()
        except Exception:
            pass

        # force common auto flags off
        if hasattr(strat, "auto_trade"):
            try:
                strat.auto_trade = False
            except Exception:
                pass

        # JokerJoe extra autos (safe)
        for k in ("sludgex_auto", "triplex_auto", "kidx_auto", "multig_auto"):
            if hasattr(strat, k):
                try:
                    setattr(strat, k, False)
                except Exception:
                    pass


def disconnect_client(client_id, reason="manual", emit=True):
    state = clients.get(client_id)
    if not state:
        return

    logger.info(f"[{client_id}] 🔻 disconnect_client: reason={reason}")

    # stop websocket
    try:
        state["ws_stop_event"].set()
    except Exception:
        pass

    ws = state.get("ws")
    if ws:
        try:
            ws.close()
        except Exception:
            pass

    state["ws"] = None
    state["ws_connected"] = False
    state["ws_transport_connected"] = False
    state["api_token"] = ""
    state["balance"] = 0.0
    state["session_start_balance"] = None
    state["req_meta"].clear()
    state["contract_meta"].clear()

    _hard_stop_all_strategies(state)

    if emit:
        socketio.emit("connection_status", {"connected": False, "loginid": "UNKNOWN", "balance": 0.0}, room=client_id)
        socketio.emit("reset_ui", room=client_id)

        # keep stats consistent for current profile (will show zeros)
        send_stats_update(client_id)


def init_client(client_id):
    """
    Initialize a fresh client state.
    """
    if client_id in clients:
        return

    clients[client_id] = {
        "api_token": "",
        "ws": None,
        "ws_thread": None,
        "ws_stop_event": threading.Event(),
        "ws_nonce": 0,  # prevents stale WS callbacks = "2 instances" bug
        "ws_connected": False,  # AUTHORIZED
        "ws_transport_connected": False,  # underlying transport open
        "active_profile": "KOOLKID",
        # Keep backend default market in sync with the frontend selector default.
        "current_symbol": "R_10",
        "human_symbol": "R_10",
        "tick_subs": {},
        # ==================== PATCH 1B: seqvix state ====================
        "seqvix": {
            "KOOLKID": {
                "running": False, "total": 0, "endless": False, "done": 0,
                "batch_size": 6, "sample_size": 30,
                "remaining": [], "active_syms": set(),
                "samples": {}, "ready_syms": set(),
                "last_exec_ts": 0.0,
                "config": {},
                # ==================== PATCH 1A: new fields ====================
                "owned_syms": set(),
                "cooldown_until": 0.0,
                "trades_per_market": 2,
                "cooldown_sec": 5.0,
            },
            "JOKERJOE": {
                "running": False, "total": 0, "endless": False, "done": 0,
                "batch_size": 6, "sample_size": 30,
                "remaining": [], "active_syms": set(),
                "samples": {}, "ready_syms": set(),
                "last_exec_ts": 0.0,
                "config": {},
                # ==================== PATCH 1A: new fields ====================
                "owned_syms": set(),
                "cooldown_until": 0.0,
                "trades_per_market": 2,
                "cooldown_sec": 5.0,
            }
        },
        "human_rf_status_last": "WAIT",
        "unchain_hl": {
            "higher_stake": 1.0,
            "lower_stake": 1.0,
            "higher_barrier": "0.12",
            "lower_barrier": "-0.12",
            "duration": 5,
            "duration_unit": "t",
            "tp": 0.0,
            "sl": 0.0,
            "auto_sl": True,
            "active_contracts": {},
            "last_action": "Ready",
            "last_result": None,
            "stats": {"wins": 0, "losses": 0, "net_pnl": 0.0},
            "risk_block_reason": None,
        },
        "unchain_scanner": {
            "running": False,
            "symbols": [],
            "buffers": {},
            "analyses": {},
            "owned_syms": set(),
            "sample_size": 30,
            "max_symbols": 10,
            "last_emit": 0.0,
        },
        "balance": 0.0,
        "session_start_balance": None,
        "auto_stake": 1.0,
        "req_meta": {},          # req_id -> meta
        "contract_meta": {},     # contract_id -> meta
        "last_seen": time.time(),  # heartbeat (page open)
        "strategies": {
            "KOOLKID": KoolKidStrategy(),
            "JOKERJOE": JokerJoeStrategy(),
            "HUMAN": HumanStrategy(),
            "UNCHAIN": UnchainStrategy()
        },
        # PATCH A: human_keep_alive flag
        "human_keep_alive": False,
    }


def get_client_state():
    cid = get_client_id()
    if cid not in clients:
        init_client(cid)
    _touch_client(cid)
    return cid, clients[cid]


def emit_jokerjoe_modes(cid, strat: JokerJoeStrategy):
    try:
        socketio.emit("auto_mode_update", {
            "sludgex": bool(getattr(strat, "sludgex_auto", False)),
            "triplex": bool(getattr(strat, "triplex_auto", False)),
            "kidx": bool(getattr(strat, "kidx_auto", False)),
            "multig": bool(getattr(strat, "multig_auto", False)),
            "kidgx": bool(getattr(strat, "kidgx_auto", False)),
            "ai_auto_trading": bool(getattr(strat, "ai_auto_trading", False)),
        }, room=cid)
    except Exception:
        pass


def emit_profile_snapshot(cid):
    """
    When user switches profile, immediately push that profile’s latest UI payload.
    """
    state = clients.get(cid)
    if not state:
        return
    prof = state.get("active_profile", "KOOLKID")
    strat = state.get("strategies", {}).get(prof)

    # digit analysis payload (KOOLKID/JOKERJOE)
    try:
        if strat and hasattr(strat, "get_ui_payload"):
            socketio.emit("digit_analysis", strat.get_ui_payload(), room=cid)
    except Exception:
        pass

    # UNCHAIN status snapshot
    try:
        if prof == "UNCHAIN":
            socketio.emit("unchain_status", _unchain_payload_response(state), room=cid)
    except Exception:
        pass

    # human chart + rise/fall status
    try:
        if prof == "HUMAN" and strat and hasattr(strat, "get_chart_data"):
            socketio.emit("human_chart_data", strat.get_chart_data(), room=cid)
        if prof == "HUMAN" and strat and hasattr(strat, "get_human_rf_payload"):
            socketio.emit("human_rf_status", strat.get_human_rf_payload(), room=cid)
    except Exception:
        pass

    send_stats_update(cid)

    # JokerJoe modes
    try:
        if prof == "JOKERJOE" and strat:
            emit_jokerjoe_modes(cid, strat)
    except Exception:
        pass



def request_human_seed(client_id):
    """
    Fetch recent candles from Deriv so HUMAN chart renders immediately:
      - 5M: last 2 hours (24 candles)
      - 1H: last 24 hours (24 candles)
    """
    state = clients.get(client_id)
    if not state:
        return

    ws = state.get("ws")
    if not ws or not state.get("ws_connected"):
        return

    try:
        state.setdefault("req_meta", {})
        symbol = state.get("human_symbol") or state.get("current_symbol")

        # 5M seed (2 hours)
        req_id_5m = _new_req_id()
        state["req_meta"][req_id_5m] = {
            "kind": "human_5m_seed",
            "time": now_time(),
            "symbol": symbol
        }
        ws.send(json.dumps({
            "ticks_history": symbol,
            "style": "candles",
            "count": 24,
            "granularity": 300,
            "end": "latest",
            "start": 1,
            "adjust_start_time": 1,
            "req_id": req_id_5m
        }))

        # 1H seed (24 hours)
        req_id_1h = _new_req_id()
        state["req_meta"][req_id_1h] = {
            "kind": "human_1h_seed",
            "time": now_time(),
            "symbol": symbol
        }
        ws.send(json.dumps({
            "ticks_history": symbol,
            "style": "candles",
            "count": 24,
            "granularity": 3600,
            "end": "latest",
            "start": 1,
            "adjust_start_time": 1,
            "req_id": req_id_1h
        }))
    except Exception:
        pass


# ---------------- ROUTES (LOGIN SYSTEM) ---------------- #
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if verify_user(username, password):
            user_row = _get_user_row(username)
            ok, reason = check_user_license_access(user_row)
            if not ok:
                session.pop("user", None)
                session.pop("role", None)
                return render_template("login.html", error=reason)

            role = str((user_row or {}).get("role") or "user").lower()
            session["user"] = username
            session["role"] = role
            session["client_id"] = str(uuid.uuid4())
            init_client(session["client_id"])

            if role == "admin":
                return redirect(url_for("admin_panel"))
            return redirect(url_for("index"))
        else:
            return render_template("login.html", error="Invalid username or password")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        email = request.form.get("email", "").strip()
        license_key = request.form.get("license_key", "").strip()

        pw_err = _validate_password_strength(password)
        if pw_err:
            return render_template("register.html", error=pw_err)

        if not license_key:
            return render_template("register.html", error="License key is required for new registrations")

        ok, msg = create_user(
            username,
            password,
            email=email,
            license_key=license_key,
            role="user",
            grandfathered=0,
            license_exempt=0
        )

        if ok:
            return redirect(url_for("login"))
        else:
            return render_template("register.html", error=msg)

    return render_template("register.html")


@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        identifier = (request.form.get("email") or "").strip()  # template compatibility
        license_key = (request.form.get("license_key") or "").strip()

        if not identifier:
            return render_template("forgot_password.html", error="Enter your email or username", entered_email=identifier)

        user_row = _find_user_for_reset(identifier)
        if not user_row:
            return render_template("forgot_password.html", error="No account found with that email/username", entered_email=identifier)

        lic_ok, lic_err = _validate_reset_license_for_user(user_row, license_key)
        if not lic_ok:
            return render_template("forgot_password.html", error=lic_err, entered_email=identifier, entered_license_key=license_key)

        username = user_row.get("username")
        raw_token, _exp_dt = _create_password_reset_token(username, minutes_valid=30)
        reset_link = url_for("reset_password", token=raw_token, _external=True)

        return render_template(
            "forgot_password.html",
            success=f"Reset link created for {username}. It expires in 30 minutes.",
            reset_link=reset_link,
            entered_email=identifier,
            entered_license_key=license_key
        )

    return render_template("forgot_password.html")


@app.route("/reset_password", methods=["GET", "POST"])
@app.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password(token=None):
    token = (token or request.args.get("token") or request.form.get("token") or "").strip()

    if request.method == "POST":
        password = (request.form.get("password") or "").strip()
        confirm_password = (request.form.get("confirm_password") or "").strip()
        license_key = (request.form.get("license_key") or "").strip()

        if not token:
            return render_template("reset_password.html", error="Missing reset token", token="", entered_license_key=license_key)
        if password != confirm_password:
            return render_template("reset_password.html", error="Passwords do not match", token=token, entered_license_key=license_key)

        pw_err = _validate_password_strength(password)
        if pw_err:
            return render_template("reset_password.html", error=pw_err, token=token, entered_license_key=license_key)

        rec, err = _get_reset_token_record(token)
        if err:
            return render_template("reset_password.html", error=err, token="", entered_license_key=license_key)

        user_row = _get_user_row(rec["username"])
        lic_ok, lic_err = _validate_reset_license_for_user(user_row, license_key)
        if not lic_ok:
            return render_template("reset_password.html", error=lic_err, token=token, entered_license_key=license_key)

        if not _update_user_password(rec["username"], password):
            return render_template("reset_password.html", error="Could not update password. Try again.", token=token, entered_license_key=license_key)

        _mark_reset_token_used(rec["id"])
        return render_template("reset_password.html", success="Password reset successful. You can now log in with your new password.", token="")

    if token:
        _rec, err = _get_reset_token_record(token)
        if err:
            return render_template("reset_password.html", error=err, token="")
        return render_template("reset_password.html", token=token)

    return render_template("reset_password.html", token="")


@app.route("/logout")
def logout():
    cid = session.pop("client_id", None)
    if cid and cid in clients:
        disconnect_client(cid, reason="logout", emit=False)
        clients.pop(cid, None)

    session.pop("user", None)
    session.pop("role", None)
    return redirect(url_for("login"))


@app.route("/admin")
def admin_panel():
    if not login_required():
        return redirect(url_for("login"))
    if not is_admin():
        return redirect(url_for("index"))

    return render_template(
        "admin.html",
        admin=session.get("user"),
        admin_username=ADMIN_USERNAME,
        users=get_admin_users_view_legacy_tuples(),  # current template compatibility
        users_full=get_admin_users_view(),
        licenses=get_admin_licenses_view()
    )


@app.route("/admin/delete_user", methods=["POST"])
def admin_delete_user():
    if not login_required() or not is_admin():
        return jsonify({"status": "error", "error": "Unauthorized"}), 403

    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    if user_id is None:
        user_id = request.form.get("user_id")

    ok, msg = delete_user_admin(user_id)
    if ok:
        return jsonify({"status": "deleted"})
    return jsonify({"status": "error", "error": msg}), 400


@app.route("/admin/license/create", methods=["POST"])
def admin_create_license():
    if not login_required() or not is_admin():
        return jsonify({"status": "error", "error": "Unauthorized"}), 403

    data = request.get_json(silent=True) or {}
    license_type = (data.get("license_type") or request.form.get("license_type") or "").strip().lower()
    ok, msg, key = create_license_record(license_type)
    if not ok:
        return jsonify({"status": "error", "error": msg}), 400
    return jsonify({"status": "ok", "license_key": key, "license_type": license_type})


@app.route("/admin/license/revoke", methods=["POST"])
def admin_revoke_license():
    if not login_required() or not is_admin():
        return jsonify({"status": "error", "error": "Unauthorized"}), 403

    data = request.get_json(silent=True) or {}
    license_key = (data.get("license_key") or request.form.get("license_key") or "").strip()
    ok, msg = revoke_license_record(license_key)
    if not ok:
        return jsonify({"status": "error", "error": msg}), 400
    return jsonify({"status": "ok", "message": msg})


@app.route("/admin/user/reset_key", methods=["POST"])
def admin_user_reset_key():
    if not login_required() or not is_admin():
        return jsonify({"status": "error", "error": "Unauthorized"}), 403

    data = request.get_json(silent=True) or {}
    username = (data.get("username") or request.form.get("username") or "").strip()
    ok, msg = admin_reset_user_license(username)
    if not ok:
        return jsonify({"status": "error", "error": msg}), 400
    return jsonify({"status": "ok", "message": msg})


@app.route("/admin/user/reassign_key", methods=["POST"])
def admin_user_reassign_key():
    if not login_required() or not is_admin():
        return jsonify({"status": "error", "error": "Unauthorized"}), 403

    data = request.get_json(silent=True) or {}
    username = (data.get("username") or request.form.get("username") or "").strip()
    license_key = (data.get("license_key") or request.form.get("license_key") or "").strip()
    ok, msg = admin_reassign_user_license(username, license_key)
    if not ok:
        return jsonify({"status": "error", "error": msg}), 400
    return jsonify({"status": "ok", "message": msg})


# ---------------- SOCKET.IO CONNECT ---------------- #
@socketio.on("connect")
def handle_connect():
    if not login_required():
        return False

    cid, state = get_client_state()
    join_room(cid)

    socketio.emit("connection_status", {
        "connected": state["ws_connected"],
        "loginid": "UNKNOWN",
        "balance": state["balance"]
    }, room=cid)

    emit_profile_snapshot(cid)


@socketio.on("client_heartbeat")
def client_heartbeat():
    if not login_required():
        return
    cid, _state = get_client_state()
    # get_client_state already touches last_seen
    return


@app.route("/static/components/unchain.html")
def unchain_component_alias():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base_dir, "unchain.html"),
        os.path.join(base_dir, "static", "components", "unchain.html"),
        os.path.join(base_dir, "unchain_fix_round3_patch", "static", "components", "unchain.html"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return send_file(p)
    return ("UNCHAIN component not found", 404)


@app.route("/static/js/profiles/unchain.js")
def unchain_js_alias():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base_dir, "unchain.js"),
        os.path.join(base_dir, "static", "js", "profiles", "unchain.js"),
        os.path.join(base_dir, "unchain_fix_round3_patch", "static", "js", "profiles", "unchain.js"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return send_file(p)
    return ("UNCHAIN profile JS not found", 404)



# ---------------- BOT ROUTE (PROTECTED) ---------------- #
@app.route("/")
def index():
    if not login_required():
        return redirect(url_for("login"))
    if is_admin():
        return redirect(url_for("admin_panel"))
    return render_template("index.html", username=session.get("user"))


# ---------------- HEARTBEAT ROUTE ---------------- #
@app.route("/heartbeat", methods=["POST"])
def heartbeat():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403
    cid, _state = get_client_state()
    return jsonify({"status": "ok", "client_id": cid})


# ---------------- DERIV BUY FUNCTION (PER CLIENT) ---------------- #
def send_buy(client_id, contract_type, stake, symbol, barrier, duration=1, duration_unit="t", mode=None):
    state = clients.get(client_id)
    if not state:
        return False, "No client state"

    ws = state.get("ws")
    ws_connected = state.get("ws_connected", False)

    if not ws_connected or not ws:
        return False, "Not connected"

    # PATCH D: Block digit trades if profile session is TP/SL blocked
    profile = state.get("active_profile", "KOOLKID")
    strategy = state.get("strategies", {}).get(profile)

    if strategy and hasattr(strategy, "enforce_tp_sl"):
        strategy.enforce_tp_sl()
        if getattr(strategy, "risk_block_reason", None):
            return False, f"{strategy.risk_block_reason} (session limit reached)"

    contract_map = {
        "OVER": "DIGITOVER",
        "UNDER": "DIGITUNDER",
        "MATCHES": "DIGITMATCH",
        "DIFFERS": "DIGITDIFF"
    }

    if contract_type not in contract_map:
        return False, "Invalid contract type"

    deriv_contract = contract_map[contract_type]
    try:
        duration = int(duration or 1)
    except Exception:
        duration = 1
    duration = max(1, min(20, duration))
    duration_unit = str(duration_unit or "t").strip().lower()
    if duration_unit not in ("t", "s", "m", "h"):
        duration_unit = "t"

    req_id = _new_req_id()
    state["req_meta"][req_id] = {
        "profile": profile,  # PATCH D: use the same profile variable
        "type": contract_type,
        "barrier": int(barrier),
        "stake": float(stake),
        "symbol": symbol,
        "time": now_time(),
        "mode": mode,
        "duration": duration,
        "duration_unit": duration_unit,
    }

    payload = {
        "req_id": req_id,
        "buy": 1,
        "price": float(stake),
        "parameters": {
            "amount": float(stake),
            "basis": "stake",
            "contract_type": deriv_contract,
            "currency": "USD",
            "duration": duration,
            "duration_unit": duration_unit,
            "symbol": symbol,
            "barrier": int(barrier)
        }
    }

    try:
        ws.send(json.dumps(payload))
        return True, "Trade sent"
    except Exception as e:
        return False, str(e)


# ==================== PATCH 1C: send_buy_with_profile ====================
def send_buy_with_profile(client_id, profile, contract_type, stake, symbol, barrier, duration=1, duration_unit="t", mode=None):
    state = clients.get(client_id)
    if not state:
        return False, "No client state"

    ws = state.get("ws")
    ws_connected = state.get("ws_connected", False)
    if not ws_connected or not ws:
        return False, "Not connected"

    # Enforce TP/SL for that profile (if your strategy supports it)
    strat = (state.get("strategies") or {}).get(profile)
    if strat and hasattr(strat, "enforce_tp_sl"):
        try:
            strat.enforce_tp_sl()
            if getattr(strat, "risk_block_reason", None):
                return False, f"{strat.risk_block_reason} (session limit reached)"
        except Exception:
            pass

    contract_map = {
        "OVER": "DIGITOVER",
        "UNDER": "DIGITUNDER",
        "MATCHES": "DIGITMATCH",
        "DIFFERS": "DIGITDIFF"
    }
    if contract_type not in contract_map:
        return False, "Invalid contract type"

    deriv_contract = contract_map[contract_type]
    try:
        duration = int(duration or 1)
    except Exception:
        duration = 1
    duration = max(1, min(20, duration))
    duration_unit = str(duration_unit or "t").strip().lower()
    if duration_unit not in ("t", "s", "m", "h"):
        duration_unit = "t"

    req_id = _new_req_id()
    state["req_meta"][req_id] = {
        "profile": profile,
        "type": contract_type,
        "barrier": int(barrier),
        "stake": float(stake),
        "symbol": symbol,
        "time": now_time(),
        "mode": mode,
        "duration": duration,
        "duration_unit": duration_unit,
    }

    payload = {
        "req_id": req_id,
        "buy": 1,
        "price": float(stake),
        "parameters": {
            "amount": float(stake),
            "basis": "stake",
            "contract_type": deriv_contract,
            "currency": "USD",
            "duration": duration,
            "duration_unit": duration_unit,
            "symbol": symbol,
            "barrier": int(barrier)
        }
    }

    try:
        ws.send(json.dumps(payload))
        return True, "Trade sent"
    except Exception as e:
        return False, str(e)


# ---------------- RISE/FALL ORDER (HUMAN Smart Assist) ---------------- #
def place_risefall_order(client_id, signal):
    state = clients.get(client_id)
    if not state or not state.get("ws_connected"):
        return False, "Not connected"

    strategy = state.get("strategies", {}).get("HUMAN")
    if strategy and hasattr(strategy, "enforce_tp_sl"):
        try:
            strategy.enforce_tp_sl()
            if getattr(strategy, "risk_block_reason", None):
                return False, f"{strategy.risk_block_reason} (session limit reached)"
        except Exception:
            pass

    ws = state.get("ws")
    if not ws:
        return False, "Not connected"

    direction = str(signal.get("direction") or "").upper()
    contract_map = {"RISE": "CALL", "FALL": "PUT"}
    deriv_contract = contract_map.get(direction)
    if not deriv_contract:
        return False, "Invalid rise/fall direction"

    stake = float(signal.get("stake", state.get("auto_stake", 1.0)))
    duration = int(signal.get("duration", 5) or 5)
    duration = max(1, min(20, duration))
    duration_unit = signal.get("duration_unit", "t") or "t"
    symbol_to_use = signal.get("symbol") or state.get("human_symbol") or state.get("current_symbol")

    req_id = _new_req_id()
    state["req_meta"][req_id] = {
        "profile": "HUMAN",
        "type": direction,
        "barrier": None,
        "stake": stake,
        "symbol": symbol_to_use,
        "time": now_time(),
        "mode": "human_rf",
        "duration": duration,
    }

    payload = {
        "req_id": req_id,
        "buy": 1,
        "price": float(stake),
        "parameters": {
            "amount": float(stake),
            "basis": "stake",
            "contract_type": deriv_contract,
            "currency": "USD",
            "duration": duration,
            "duration_unit": duration_unit,
            "symbol": symbol_to_use,
        }
    }

    try:
        ws.send(json.dumps(payload))
        return True, "Trade sent"
    except Exception as e:
        return False, str(e)


def _default_unchain_hl_state():
    return {
        "higher_stake": 1.0,
        "lower_stake": 1.0,
        "higher_barrier": "0.12",
        "lower_barrier": "-0.12",
        "duration": 5,
        "duration_unit": "t",
        "tp": 0.0,
        "sl": 0.0,
        "auto_sl": True,
        "auto_both_enabled": False,
        "auto_both_cooldown": 3,
        "auto_start_threshold": 60.0,
        "auto_min_movement": 0.12,
        "auto_min_tick_speed": 1.5,
        "auto_min_range": 0.2,
        "auto_pair_active": False,
        "auto_next_fire_at": 0.0,
        "auto_last_cycle_closed_at": 0.0,
        "auto_wait_for_reset": False,
        "active_contracts": {},
        "last_action": "Ready",
        "last_result": None,
        "stats": {"wins": 0, "losses": 0, "net_pnl": 0.0},
        "risk_block_reason": None,
    }


def _ensure_unchain_hl_state(state):
    base = _default_unchain_hl_state()
    cur = state.setdefault("unchain_hl", {}) or {}
    for k, v in base.items():
        if k not in cur:
            cur[k] = v.copy() if isinstance(v, dict) else v
    if not isinstance(cur.get("active_contracts"), dict):
        cur["active_contracts"] = {}
    if not isinstance(cur.get("stats"), dict):
        cur["stats"] = {"wins": 0, "losses": 0, "net_pnl": 0.0}
    cur.setdefault("risk_block_reason", None)
    try:
        cur["auto_start_threshold"] = max(55.0, min(80.0, float(cur.get("auto_start_threshold", 60.0) or 60.0)))
    except Exception:
        cur["auto_start_threshold"] = 60.0
    try:
        cur["auto_min_movement"] = max(0.00001, float(cur.get("auto_min_movement", 0.12) or 0.12))
    except Exception:
        cur["auto_min_movement"] = 0.12
    try:
        cur["auto_min_tick_speed"] = max(0.05, min(10.0, float(cur.get("auto_min_tick_speed", 1.5) or 1.5)))
    except Exception:
        cur["auto_min_tick_speed"] = 1.5
    try:
        cur["auto_min_range"] = max(0.00001, float(cur.get("auto_min_range", 0.2) or 0.2))
    except Exception:
        cur["auto_min_range"] = 0.2
    try:
        symbol = str(state.get("current_symbol") or "").upper()
        is_v75 = symbol in {
            "V75", "V_75", "R_75", "VOL75", "1HZ75V",
            "VOLATILITY 75 INDEX", "VOLATILITY 75 (1S) INDEX",
        }

        def _as_float(val):
            try:
                return float(val)
            except Exception:
                return None

        if is_v75:
            hb = cur.get("higher_barrier")
            lb = cur.get("lower_barrier")
            base_hb = base.get("higher_barrier")
            base_lb = base.get("lower_barrier")
            hb_is_default = _as_float(hb) == _as_float(base_hb) or hb in (None, "")
            lb_is_default = _as_float(lb) == _as_float(base_lb) or lb in (None, "")
            if hb_is_default:
                cur["higher_barrier"] = "+3.88"
            if lb_is_default:
                cur["lower_barrier"] = "-3.88"
    except Exception:
        pass
    state["unchain_hl"] = cur
    return cur


def _clean_unchain_duration_unit(value):
    unit = str(value or "t").strip().lower()
    return unit if unit in ("t", "s", "m", "h") else "t"


def _format_unchain_barrier(raw_value, side, duration_unit):
    raw = str(raw_value if raw_value is not None else "").strip()
    if not raw:
        raise ValueError("Barrier is required")

    # Higher/Lower uses the contract side to decide the direction.
    # If the user does not type a sign, keep the barrier as a positive offset
    # for BOTH sides (same behavior users see in the Deriv UI).
    user_typed_sign = raw.startswith(("+", "-"))
    numeric = float(raw) if user_typed_sign else abs(float(raw))

    unit = _clean_unchain_duration_unit(duration_unit)
    if not user_typed_sign and unit in ("t", "s", "m"):
        out = f"+{numeric:.10f}".rstrip("0").rstrip(".")
    else:
        out = f"{numeric:.10f}".rstrip("0").rstrip(".")
    return out or "0"


def _normalize_contract_id(contract_id):
    if contract_id is None:
        return None
    try:
        s = str(contract_id).strip()
    except Exception:
        return None
    if not s:
        return None
    try:
        f = float(s)
        if f.is_integer():
            s = str(int(f))
    except Exception:
        pass
    return s


def _peek_contract_meta(state, contract_id):
    meta_map = state.get("contract_meta") or {}
    norm = _normalize_contract_id(contract_id)
    candidates = [contract_id, norm, str(contract_id) if contract_id is not None else None]
    if norm and norm.isdigit():
        try:
            candidates.append(int(norm))
        except Exception:
            pass
    for key in candidates:
        if key is None:
            continue
        if key in meta_map:
            return meta_map.get(key)
    return None


def _get_unchain_active_entry(state, contract_id):
    u = _ensure_unchain_hl_state(state)
    active = u.get("active_contracts") or {}
    norm = _normalize_contract_id(contract_id)
    for key in (norm, str(contract_id) if contract_id is not None else None, contract_id):
        if key is None:
            continue
        key = str(key)
        if key in active:
            return active.get(key)
    return None


def _remove_unchain_active_contract(state, contract_id):
    u = _ensure_unchain_hl_state(state)
    active = u.setdefault("active_contracts", {})
    removed = None
    norm = _normalize_contract_id(contract_id)
    for key in (norm, str(contract_id) if contract_id is not None else None, contract_id):
        if key is None:
            continue
        key = str(key)
        if key in active:
            removed = active.pop(key, None) or removed
    return removed


def _get_processed_unchain_contracts(state):
    seen = state.setdefault("_processed_unchain_contracts", set())
    if not isinstance(seen, set):
        try:
            seen = set(seen)
        except Exception:
            seen = set()
        state["_processed_unchain_contracts"] = seen
    return seen


def _mark_unchain_contract_processed(state, contract_id):
    norm = _normalize_contract_id(contract_id)
    if not norm:
        return
    seen = _get_processed_unchain_contracts(state)
    seen.add(norm)
    if len(seen) > 2000:
        while len(seen) > 1500:
            try:
                seen.pop()
            except Exception:
                break


def _is_unchain_contract_processed(state, contract_id):
    norm = _normalize_contract_id(contract_id)
    return bool(norm and norm in _get_processed_unchain_contracts(state))


def _pull_contract_meta(state, contract_id):
    meta_map = state.get("contract_meta") or {}
    if contract_id is None:
        return None
    found = None
    norm = _normalize_contract_id(contract_id)
    candidates = [contract_id, norm, str(contract_id) if contract_id is not None else None]
    if norm and norm.isdigit():
        try:
            candidates.append(int(norm))
        except Exception:
            pass
    for key in candidates:
        if key is None:
            continue
        if key in meta_map:
            value = meta_map.pop(key, None)
            if value is not None and found is None:
                found = value
    return found


def _is_unchain_contract_known(state, contract_id, meta=None):
    try:
        if meta and str((meta.get("profile") or "")).upper() == "UNCHAIN":
            return True
    except Exception:
        pass
    norm = _normalize_contract_id(contract_id)
    if norm and _is_unchain_contract_processed(state, norm):
        return True
    u = _ensure_unchain_hl_state(state)
    active = u.get("active_contracts") or {}
    return (str(contract_id) in active or (norm in active if norm else False)) if contract_id is not None else False


def _entry_is_open_for_ui(entry):
    if not isinstance(entry, dict):
        return False
    try:
        if entry.get("is_sold"):
            return False
        for key in ("status", "contract_status"):
            status = str(entry.get(key) or "").strip().lower()
            if status in ("sold", "won", "lost", "settled", "closed", "expired"):
                return False
        if entry.get("sell_price") not in (None, ""):
            return False
    except Exception:
        return True
    return True


def _check_unchain_hl_risk_block(state):
    u = _ensure_unchain_hl_state(state)
    net_pnl = float(((u.get("stats") or {}).get("net_pnl", 0.0)) or 0.0)
    auto_sl = bool(u.get("auto_sl", True))
    if not auto_sl:
        u["risk_block_reason"] = None
        return None
    try:
        tp = float(u.get("tp", 0) or 0)
    except Exception:
        tp = 0.0
    try:
        sl = float(u.get("sl", 0) or 0)
    except Exception:
        sl = 0.0
    reason = None
    if tp > 0 and net_pnl >= tp:
        reason = f"UNCHAIN TP reached (+${net_pnl:.2f})"
    elif sl > 0 and net_pnl <= -abs(sl):
        reason = f"UNCHAIN SL reached (${net_pnl:.2f})"
    u["risk_block_reason"] = reason
    return reason


def _upsert_unchain_active_contract(state, contract_id, meta=None, contract=None, status=None):
    u = _ensure_unchain_hl_state(state)
    cid_key = _normalize_contract_id(contract_id) or str(contract_id)
    active = u.setdefault("active_contracts", {})
    entry = active.get(cid_key, {})
    meta = meta or _peek_contract_meta(state, contract_id) or {}
    contract = contract or {}
    entry["contract_id"] = contract_id
    entry["profile"] = "UNCHAIN"
    entry["type"] = (meta.get("type") or entry.get("type") or "TRADE").upper()
    entry["side"] = entry["type"]
    entry["symbol"] = meta.get("symbol") or contract.get("underlying") or contract.get("symbol") or state.get("current_symbol")
    entry["barrier"] = meta.get("barrier", entry.get("barrier"))
    try:
        entry["stake"] = float(meta.get("stake", entry.get("stake", contract.get("buy_price") or 0)) or 0)
    except Exception:
        entry["stake"] = entry.get("stake", 0)
    entry["duration"] = meta.get("duration", entry.get("duration"))
    entry["duration_unit"] = meta.get("duration_unit", entry.get("duration_unit"))
    entry["time"] = meta.get("time") or entry.get("time") or now_time()
    entry_status = status or contract.get("status") or entry.get("status") or "OPEN"
    if contract.get("is_sold"):
        entry_status = "SOLD"
    entry["status"] = entry_status
    try:
        if contract.get("profit") is not None:
            entry["open_profit"] = float(contract.get("profit") or 0)
    except Exception:
        pass
    if contract:
        entry["contract_status"] = contract.get("status") or entry.get("contract_status")
        entry["is_sold"] = bool(contract.get("is_sold"))
        if contract.get("entry_spot") not in (None, ""):
            try:
                spot = float(contract.get("entry_spot"))
                if spot > 0:
                    entry["entry_spot"] = spot
            except Exception:
                pass
        if contract.get("current_spot") not in (None, ""):
            try:
                spot_now = float(contract.get("current_spot"))
                if spot_now > 0:
                    entry["current_spot"] = spot_now
            except Exception:
                pass
        if contract.get("sell_price") not in (None, ""):
            entry["sell_price"] = contract.get("sell_price")
        if contract.get("buy_price") not in (None, ""):
            entry["buy_price"] = contract.get("buy_price")
        if contract.get("is_valid_to_sell") is not None:
            entry["is_valid_to_sell"] = bool(contract.get("is_valid_to_sell"))
    # Fallback base for charting when Deriv has not populated entry_spot yet.
    if entry.get("entry_spot") in (None, "", 0, 0.0):
        current_spot = entry.get("current_spot")
        try:
            current_spot = float(current_spot)
        except Exception:
            current_spot = None
        if current_spot and current_spot > 0:
            entry["entry_spot"] = current_spot
        else:
            try:
                un_strat = (state.get("strategies") or {}).get("UNCHAIN")
                last_price = float(getattr(un_strat, "last_price", 0) or 0)
                if last_price > 0:
                    entry["entry_spot"] = last_price
            except Exception:
                pass
    entry["updated_at"] = now_time()
    active[cid_key] = entry
    u["last_action"] = f"{entry['type']} active on {entry['symbol']}"
    return entry


def _finalize_unchain_contract(state, contract, meta=None):
    u = _ensure_unchain_hl_state(state)
    contract_id = contract.get("contract_id")
    active_entry = _remove_unchain_active_contract(state, contract_id) or {}
    meta = meta or {}
    profit = float(contract.get("profit", 0) or 0)
    result = "WIN" if profit > 0 else "LOSS"
    entry = {
        "profile": "UNCHAIN",
        "type": (meta.get("type") or active_entry.get("type") or "TRADE").upper(),
        "barrier": meta.get("barrier", active_entry.get("barrier")),
        "stake": meta.get("stake", active_entry.get("stake")),
        "symbol": meta.get("symbol") or active_entry.get("symbol") or state.get("current_symbol"),
        "time": meta.get("time") or active_entry.get("time") or now_time(),
        "profit": profit,
        "profit_value": profit,
        "result": result,
        "contract_id": contract_id,
        "duration": meta.get("duration", active_entry.get("duration")),
        "duration_unit": meta.get("duration_unit", active_entry.get("duration_unit")),
    }
    stats = u.setdefault("stats", {"wins": 0, "losses": 0, "net_pnl": 0.0})
    if profit > 0:
        stats["wins"] = int(stats.get("wins", 0) or 0) + 1
    else:
        stats["losses"] = int(stats.get("losses", 0) or 0) + 1
    stats["net_pnl"] = float(stats.get("net_pnl", 0.0) or 0.0) + profit
    u["last_result"] = entry
    u["last_action"] = f"{entry['type']} {result} on {entry['symbol']} ({profit:+.2f})"
    _check_unchain_hl_risk_block(state)
    return entry


def _get_open_unchain_active_entries(state):
    u = _ensure_unchain_hl_state(state)
    active_map = u.get("active_contracts") or {}
    return [entry for entry in active_map.values() if _entry_is_open_for_ui(entry)]


def _get_unchain_bias_payload(state, u=None):
    u = u or _ensure_unchain_hl_state(state)
    bias_payload = {
        "status": "LOADING ANALYZER…",
        "higher_pct": 50.0,
        "lower_pct": 50.0,
        "strength": "Building",
        "reasons": ["Waiting for data"],
        "lookback": 0,
        "summary": "Gathering enough recent ticks to score Higher vs Lower.",
    }
    try:
        strat = (state.get("strategies") or {}).get("UNCHAIN")
        if strat and hasattr(strat, "get_bias_payload"):
            bias_payload = strat.get_bias_payload({
                "higher_barrier": u.get("higher_barrier", "0.12"),
                "lower_barrier": u.get("lower_barrier", "-0.12"),
                "duration": int(u.get("duration", 5) or 5),
                "duration_unit": _clean_unchain_duration_unit(u.get("duration_unit", "t")),
            }) or bias_payload
    except Exception:
        pass
    return bias_payload


def _compute_unchain_auto_metrics(state, u=None):
    """
    Auto Both market-quality scoring:
    movement (30) + volatility/tick-speed (25) + range (25) + trap-zone safety (20).
    """
    u = u or _ensure_unchain_hl_state(state)
    sample_size = 10
    strat = (state.get("strategies") or {}).get("UNCHAIN")
    prices = []
    tick_times = []
    if strat is not None:
        try:
            prices = list(getattr(strat, "price_history", []) or [])
        except Exception:
            prices = []
        try:
            tick_times = list(getattr(strat, "tick_time_history", []) or [])
        except Exception:
            tick_times = []

    safe_prices = []
    for v in prices:
        try:
            if v is None:
                continue
            safe_prices.append(float(v))
        except Exception:
            continue
    prices = safe_prices
    recent_prices = prices[-sample_size:]
    recent_times = [float(v) for v in tick_times[-sample_size:] if v is not None]

    try:
        min_movement = float(u.get("auto_min_movement", 0.12) or 0.12)
    except Exception:
        min_movement = 0.12
    try:
        min_tick_speed = float(u.get("auto_min_tick_speed", 1.5) or 1.5)
    except Exception:
        min_tick_speed = 1.5
    try:
        min_range = float(u.get("auto_min_range", 0.2) or 0.2)
    except Exception:
        min_range = 0.2

    if len(recent_prices) < sample_size:
        return {
            "ready": False,
            "sample_size": sample_size,
            "ticks_used": len(recent_prices),
            "movement": 0.0,
            "average_tick_interval": None,
            "recent_range": 0.0,
            "middle_price": None,
            "center_hits": 0,
            "direction_changes": 0,
            "movement_score": 0,
            "volatility_score": 0,
            "range_score": 0,
            "trap_zone_score": 0,
            "market_confidence": 0.0,
            "min_movement": min_movement,
            "min_tick_speed": min_tick_speed,
            "min_range": min_range,
            "movement_pass": False,
            "volatility_pass": False,
            "range_pass": False,
            "trap_zone_pass": False,
            "reasons": [f"Need {sample_size} ticks ({len(recent_prices)}/{sample_size})"],
        }

    first_price = float(recent_prices[0])
    last_price = float(recent_prices[-1])
    movement = abs(last_price - first_price)
    movement_pass = movement >= min_movement
    movement_score = 30 if movement_pass else 0

    intervals = []
    for idx in range(1, len(recent_times)):
        diff = recent_times[idx] - recent_times[idx - 1]
        if diff > 0:
            intervals.append(diff)
    average_tick_interval = (sum(intervals) / len(intervals)) if intervals else None
    volatility_pass = bool(average_tick_interval is not None and average_tick_interval <= min_tick_speed)
    volatility_score = 25 if volatility_pass else 0

    highest_price = max(recent_prices)
    lowest_price = min(recent_prices)
    recent_range = highest_price - lowest_price
    range_pass = recent_range >= min_range
    range_score = 25 if range_pass else 0

    middle_price = (sum(recent_prices) / len(recent_prices)) if recent_prices else None
    center_band = max(0.00001, recent_range * 0.12, min_range * 0.10)
    center_hits = 0
    if middle_price is not None:
        center_hits = sum(1 for p in recent_prices if abs(p - middle_price) <= center_band)

    deltas = [recent_prices[i] - recent_prices[i - 1] for i in range(1, len(recent_prices))]
    direction_changes = 0
    prev_sign = 0
    for d in deltas:
        sign = 1 if d > 0 else (-1 if d < 0 else 0)
        if sign == 0:
            continue
        if prev_sign and sign != prev_sign:
            direction_changes += 1
        prev_sign = sign

    center_hit_limit = max(2, int(round(sample_size * 0.45)))
    direction_change_limit = max(2, int(round((sample_size - 1) * 0.35)))
    trap_zone_pass = (center_hits <= center_hit_limit) and (direction_changes <= direction_change_limit)
    trap_zone_score = 20 if trap_zone_pass else 0

    market_confidence = float(movement_score + volatility_score + range_score + trap_zone_score)

    reasons = []
    if not movement_pass:
        reasons.append(f"Movement {movement:.5f} < min {min_movement:.5f}")
    if not volatility_pass:
        if average_tick_interval is None:
            reasons.append("Tick speed unavailable")
        else:
            reasons.append(f"Avg tick {average_tick_interval:.3f}s > max {min_tick_speed:.3f}s")
    if not range_pass:
        reasons.append(f"Range {recent_range:.5f} < min {min_range:.5f}")
    if not trap_zone_pass:
        reasons.append(f"Trap-zone noisy (center hits {center_hits}, flips {direction_changes})")
    if not reasons:
        reasons.append("All filters passed")

    return {
        "ready": True,
        "sample_size": sample_size,
        "ticks_used": sample_size,
        "movement": float(movement),
        "average_tick_interval": (None if average_tick_interval is None else float(average_tick_interval)),
        "recent_range": float(recent_range),
        "middle_price": (None if middle_price is None else float(middle_price)),
        "center_hits": int(center_hits),
        "direction_changes": int(direction_changes),
        "movement_score": int(movement_score),
        "volatility_score": int(volatility_score),
        "range_score": int(range_score),
        "trap_zone_score": int(trap_zone_score),
        "market_confidence": float(market_confidence),
        "min_movement": float(min_movement),
        "min_tick_speed": float(min_tick_speed),
        "min_range": float(min_range),
        "movement_pass": bool(movement_pass),
        "volatility_pass": bool(volatility_pass),
        "range_pass": bool(range_pass),
        "trap_zone_pass": bool(trap_zone_pass),
        "reasons": reasons,
    }


def _get_unchain_auto_gate(state, u=None):
    u = u or _ensure_unchain_hl_state(state)
    threshold = float(u.get("auto_start_threshold", 60.0) or 60.0)
    metrics = _compute_unchain_auto_metrics(state, u)
    market_confidence = float(metrics.get("market_confidence", 0.0) or 0.0)
    ready = bool(metrics.get("ready")) and market_confidence >= threshold

    return {
        "ready": bool(ready),
        "threshold": threshold,
        "market_confidence": market_confidence,
        "movement_score": int(metrics.get("movement_score", 0) or 0),
        "volatility_score": int(metrics.get("volatility_score", 0) or 0),
        "range_score": int(metrics.get("range_score", 0) or 0),
        "trap_zone_score": int(metrics.get("trap_zone_score", 0) or 0),
        "metrics": metrics,
    }


def _get_unchain_auto_status(state, u=None, active_count=None, gate=None):
    u = u or _ensure_unchain_hl_state(state)
    if not u:
        return {"label": "OFF", "cooldown_remaining": 0.0}
    enabled = bool(u.get("auto_both_enabled"))
    if active_count is None:
        active_count = len([v for v in (u.get("active_contracts") or {}).values() if _entry_is_open_for_ui(v)])
    if not enabled:
        return {"label": "OFF", "cooldown_remaining": 0.0}
    if active_count > 0 or bool(u.get("auto_pair_active")):
        return {"label": "RUNNING", "cooldown_remaining": 0.0}
    now_ts = time.time()
    next_fire_at = float(u.get("auto_next_fire_at") or 0.0)
    cooldown_remaining = max(0.0, next_fire_at - now_ts)
    if cooldown_remaining > 0:
        return {"label": "COOLDOWN", "cooldown_remaining": cooldown_remaining}
    gate = gate or _get_unchain_auto_gate(state, u)
    if bool(u.get("auto_wait_for_reset")):
        return {
            "label": "WAITING RESET",
            "cooldown_remaining": 0.0,
            "threshold": float(gate.get("threshold", 60.0) or 60.0),
            "market_confidence": float(gate.get("market_confidence", 0.0) or 0.0),
        }
    if not gate.get("ready"):
        threshold = gate.get("threshold", 60.0)
        market_confidence = float(gate.get("market_confidence", 0.0) or 0.0)
        return {
            "label": f"WAITING {int(threshold)}%",
            "cooldown_remaining": 0.0,
            "threshold": threshold,
            "market_confidence": market_confidence,
        }
    return {"label": "ARMED", "cooldown_remaining": 0.0}


def _run_unchain_auto_both(client_id, state):
    u = _ensure_unchain_hl_state(state)
    if not bool(u.get("auto_both_enabled")):
        return False
    if not state.get("ws_connected") or not state.get("ws"):
        return False

    cooldown = max(0, int(u.get("auto_both_cooldown", 3) or 3))
    open_entries = _get_open_unchain_active_entries(state)
    active_count = len(open_entries)
    now_ts = time.time()

    if active_count > 0:
        u["auto_pair_active"] = True
        return False

    if bool(u.get("auto_pair_active")):
        u["auto_pair_active"] = False
        u["auto_last_cycle_closed_at"] = now_ts
        u["auto_next_fire_at"] = now_ts + cooldown
        u["auto_wait_for_reset"] = True
        u["last_action"] = f"AUTO BOTH cooldown {cooldown}s"
        return False

    next_fire_at = float(u.get("auto_next_fire_at") or 0.0)
    if next_fire_at and now_ts < next_fire_at:
        return False

    gate = _get_unchain_auto_gate(state, u)
    if bool(u.get("auto_wait_for_reset")):
        if gate.get("ready"):
            threshold = float(gate.get("threshold", 60.0) or 60.0)
            market_confidence = float(gate.get("market_confidence", 0.0) or 0.0)
            u["last_action"] = f"AUTO BOTH waiting for fresh setup reset • confidence {market_confidence:.0f}%/{threshold:.0f}%"
            if state.get("active_profile") == "UNCHAIN":
                socketio.emit("unchain_status", _unchain_payload_response(state), room=client_id)
            return False
        # Gate dropped below threshold once -> allow next cycle when confidence rebuilds.
        u["auto_wait_for_reset"] = False
        return False

    if not gate.get("ready"):
        threshold = float(gate.get("threshold", 60.0) or 60.0)
        market_confidence = float(gate.get("market_confidence", 0.0) or 0.0)
        metrics = gate.get("metrics") or {}
        u["last_action"] = (
            f"AUTO BOTH waiting • confidence {market_confidence:.0f}%/{threshold:.0f}% • "
            f"M{int(metrics.get('movement_score', 0) or 0)} V{int(metrics.get('volatility_score', 0) or 0)} "
            f"R{int(metrics.get('range_score', 0) or 0)} T{int(metrics.get('trap_zone_score', 0) or 0)}"
        )
        if state.get("active_profile") == "UNCHAIN":
            socketio.emit("unchain_status", _unchain_payload_response(state), room=client_id)
        return False

    symbol = state.get("current_symbol", "R_25")
    plan = [
        ("HIGHER", u.get("higher_stake", 1.0), u.get("higher_barrier", "0.12")),
        ("LOWER", u.get("lower_stake", 1.0), u.get("lower_barrier", "-0.12")),
    ]
    placed = []
    errors = []
    for side, stake, barrier in plan:
        ok, msg = _send_unchain_hl_trade(
            client_id,
            side=side,
            stake=stake,
            symbol=symbol,
            barrier=barrier,
            duration=u.get("duration", 5),
            duration_unit=u.get("duration_unit", "t"),
        )
        if ok:
            placed.append(side)
        else:
            errors.append(f"{side}: {msg}")

    if placed:
        u["auto_pair_active"] = True
        u["auto_wait_for_reset"] = False
        u["auto_next_fire_at"] = 0.0
        if len(placed) == 2:
            u["last_action"] = f"AUTO BOTH pair sent on {symbol}"
        else:
            u["last_action"] = f"AUTO BOTH partial send ({' + '.join(placed)})"
    else:
        u["auto_pair_active"] = False
        u["auto_next_fire_at"] = now_ts + cooldown
        if errors:
            u["last_action"] = f"AUTO BOTH retry in {cooldown}s • {errors[0]}"

    if state.get("active_profile") == "UNCHAIN":
        socketio.emit("unchain_status", _unchain_payload_response(state), room=client_id)
    return bool(placed)


def _unchain_payload_response(state):
    u = _ensure_unchain_hl_state(state)
    _check_unchain_hl_risk_block(state)
    un_strat = (state.get("strategies") or {}).get("UNCHAIN")
    live_price = None
    try:
        live_price = float(getattr(un_strat, "last_price", None))
    except Exception:
        live_price = None
    active_map = u.get("active_contracts") or {}
    cleaned_active = {}
    for key, entry in list(active_map.items()):
        if _entry_is_open_for_ui(entry):
            cleaned_active[str(key)] = entry
    if len(cleaned_active) != len(active_map):
        u["active_contracts"] = cleaned_active
        active_map = cleaned_active
    active_contracts = list(active_map.values())
    active_contracts.sort(key=lambda x: str(x.get("contract_id") or ""))
    stats = u.get("stats") or {"wins": 0, "losses": 0, "net_pnl": 0.0}

    bias_payload = _get_unchain_bias_payload(state, u)
    auto_gate = _get_unchain_auto_gate(state, u)
    auto_meta = _get_unchain_auto_status(state, u, active_count=len(active_contracts), gate=auto_gate)

    return {
        "profile": "UNCHAIN",
        "unchain": {
            "higher_stake": float(u.get("higher_stake", 1.0) or 1.0),
            "lower_stake": float(u.get("lower_stake", 1.0) or 1.0),
            "higher_barrier": u.get("higher_barrier", "0.12"),
            "lower_barrier": u.get("lower_barrier", "-0.12"),
            "duration": int(u.get("duration", 5) or 5),
            "duration_unit": _clean_unchain_duration_unit(u.get("duration_unit", "t")),
            "tp": float(u.get("tp", 0) or 0),
            "sl": float(u.get("sl", 0) or 0),
            "auto_sl": bool(u.get("auto_sl", True)),
            "auto_both_enabled": bool(u.get("auto_both_enabled", False)),
            "auto_both_cooldown": max(0, int(u.get("auto_both_cooldown", 3) or 3)),
            "auto_status": auto_meta.get("label", "OFF"),
            "auto_cooldown_remaining": float(auto_meta.get("cooldown_remaining", 0.0) or 0.0),
            "auto_start_threshold": float(u.get("auto_start_threshold", 60.0) or 60.0),
            "auto_min_movement": float(u.get("auto_min_movement", 0.12) or 0.12),
            "auto_min_tick_speed": float(u.get("auto_min_tick_speed", 1.5) or 1.5),
            "auto_min_range": float(u.get("auto_min_range", 0.2) or 0.2),
            "auto_gate": auto_gate,
            "risk_block_reason": u.get("risk_block_reason"),
            "active_contracts": active_contracts,
            "active_count": len(active_contracts),
            "last_action": u.get("last_action") or "Ready",
            "last_result": u.get("last_result"),
            "bias": bias_payload,
            "stats": {
                "wins": int(stats.get("wins", 0) or 0),
                "losses": int(stats.get("losses", 0) or 0),
                "net_pnl": float(stats.get("net_pnl", 0.0) or 0.0),
            },
        },
        "auto_stake": float(state.get("auto_stake", 1.0) or 1.0),
        "symbol": state.get("current_symbol", "R_25"),
        "main_symbol": state.get("current_symbol", "R_25"),
        "human_symbol": state.get("human_symbol") or state.get("current_symbol", "R_25"),
        "active_profile": state.get("active_profile", "KOOLKID"),
        "ws_connected": bool(state.get("ws_connected")),
        "price": live_price,
        "scanner": _get_unchain_scanner_payload(state),
    }


def _send_unchain_hl_trade(client_id, *, side, stake, symbol, barrier, duration, duration_unit):
    state = clients.get(client_id)
    if not state:
        return False, "No client state"
    ws = state.get("ws")
    if not state.get("ws_connected") or not ws:
        return False, "Not connected"
    risk_block = _check_unchain_hl_risk_block(state)
    if risk_block:
        return False, risk_block
    side = str(side or "").upper()
    if side not in ("HIGHER", "LOWER"):
        return False, "Invalid UNCHAIN side"
    try:
        stake = float(stake)
    except Exception:
        return False, "Invalid stake"
    if stake <= 0:
        return False, "Stake must be greater than 0"
    try:
        duration = int(duration)
    except Exception:
        return False, "Invalid duration"
    duration = max(1, min(999, duration))
    duration_unit = _clean_unchain_duration_unit(duration_unit)
    try:
        barrier_value = _format_unchain_barrier(barrier, side, duration_unit)
    except Exception as e:
        return False, str(e)
    req_id = _new_req_id()
    req_meta = {
        "profile": "UNCHAIN",
        "type": side,
        "barrier": barrier_value,
        "stake": float(stake),
        "symbol": symbol,
        "time": now_time(),
        "duration": int(duration),
        "duration_unit": duration_unit,
        "deriv_contract_type": {"HIGHER": "CALL", "LOWER": "PUT"}[side],
    }
    state.setdefault("req_meta", {})[req_id] = req_meta
    deriv_contract = {"HIGHER": "CALL", "LOWER": "PUT"}[side]
    payload = {
        "req_id": req_id,
        "buy": 1,
        "price": float(stake),
        "parameters": {
            "amount": float(stake),
            "basis": "stake",
            "contract_type": deriv_contract,
            "currency": "USD",
            "duration": int(duration),
            "duration_unit": duration_unit,
            "symbol": symbol,
            "barrier": barrier_value,
        }
    }
    try:
        ws.send(json.dumps(payload))
        u = _ensure_unchain_hl_state(state)
        u["last_action"] = f"{side} request sent on {symbol}"
        return True, f"{side} trade sent"
    except Exception as e:
        try:
            state.get("req_meta", {}).pop(req_id, None)
        except Exception:
            pass
        return False, str(e)


def _send_unchain_buy(client_id, *, stake, symbol, growth_rate, mode="AUTO", exit_ticks=5):
    state = clients.get(client_id)
    if not state:
        return False, "No client state"

    ws = state.get("ws")
    if not state.get("ws_connected") or not ws:
        return False, "Not connected"

    strat = (state.get("strategies") or {}).get("UNCHAIN")
    if not strat:
        return False, "UNCHAIN strategy not loaded"

    if hasattr(strat, "enforce_tp_sl"):
        try:
            strat.enforce_tp_sl()
            if getattr(strat, "risk_block_reason", None):
                return False, f"{strat.risk_block_reason} (session limit reached)"
        except Exception:
            pass

    try:
        stake = float(stake)
    except Exception:
        stake = float(state.get("auto_stake", 1.0) or 1.0)
    if stake <= 0:
        stake = 1.0

    try:
        growth_rate = float(growth_rate)
    except Exception:
        growth_rate = float(getattr(strat, "growth_rate", 0.02) or 0.02)
    # strategy stores growth in decimal (0.01 - 0.05)
    growth_rate = max(0.01, min(0.05, growth_rate))

    try:
        exit_ticks = int(exit_ticks or 5)
    except Exception:
        exit_ticks = 5
    exit_ticks = max(1, min(50, exit_ticks))

    req_id = _new_req_id()
    req_meta = {
        "profile": "UNCHAIN",
        "type": "ACCU",
        "barrier": None,
        "stake": float(stake),
        "symbol": symbol,
        "time": now_time(),
        "mode": str(mode).upper(),
        "exit_ticks": int(exit_ticks),
        "growth_rate": float(growth_rate),
    }
    state.setdefault("req_meta", {})[req_id] = req_meta

    # mark pending in strategy immediately to prevent duplicate entries before buy ack
    try:
        if hasattr(strat, "on_trade_request_sent"):
            strat.on_trade_request_sent(mode=req_meta["mode"], exit_ticks=exit_ticks, manual=(req_meta["mode"] == "MANUAL"), stake=stake)
    except Exception:
        pass

    payload = {
        "req_id": req_id,
        "buy": 1,
        "price": float(stake),
        "parameters": {
            "amount": float(stake),
            "basis": "stake",
            "contract_type": "ACCU",
            "currency": "USD",
            "growth_rate": float(growth_rate),
            "symbol": symbol,
        }
    }

    try:
        ws.send(json.dumps(payload))
        return True, "UNCHAIN trade sent"
    except Exception as e:
        # best effort rollback pending flag if send failed before Deriv receives it
        try:
            if getattr(strat, "pending_trade_request", False):
                strat.pending_trade_request = False
        except Exception:
            pass
        try:
            state.get("req_meta", {}).pop(req_id, None)
        except Exception:
            pass
        return False, str(e)


def _request_sell_contract(client_id, contract_id):
    state = clients.get(client_id)
    if not state:
        return False, "No client state"
    ws = state.get("ws")
    if not state.get("ws_connected") or not ws:
        return False, "Not connected"
    try:
        active_entry = _get_unchain_active_entry(state, contract_id)
        if active_entry is not None:
            active_entry["status"] = "CLOSE REQUESTED"
            active_entry["updated_at"] = now_time()
        ws.send(json.dumps({"sell": int(contract_id), "price": 0}))
        # Keep an open-contract subscription alive so settlement always arrives.
        try:
            ws.send(json.dumps({
                "proposal_open_contract": 1,
                "contract_id": int(float(contract_id)),
                "subscribe": 1,
            }))
        except Exception:
            pass
        return True, "Sell request sent"
    except Exception as e:
        return False, str(e)


def _maybe_unchain_exit_on_tick(client_id, state):
    try:
        strat = (state.get("strategies") or {}).get("UNCHAIN")
        if not strat or not hasattr(strat, "should_request_exit"):
            return
        exit_req = strat.should_request_exit(getattr(strat, "tick_count", 0))
        if not exit_req:
            return
        cid = exit_req.get("contract_id")
        if not cid:
            return
        reason = exit_req.get("reason") or "tick_exit"
        # mark first to avoid duplicate requests on fast ticks
        try:
            if hasattr(strat, "mark_exit_requested"):
                strat.mark_exit_requested(reason)
        except Exception:
            pass
        ok, msg = _request_sell_contract(client_id, cid)
        if not ok:
            try:
                # clear only if send failed
                strat.exit_requested = False
                strat.exit_requested_reason = None
            except Exception:
                pass
            logger.warning(f"[{client_id}] UNCHAIN sell request failed: {msg}")
        else:
            if state.get("active_profile") == "UNCHAIN":
                socketio.emit("unchain_status", _unchain_payload_response(state), room=client_id)
    except Exception as e:
        logger.error(f"[{client_id}] UNCHAIN exit-on-tick error: {e}")


# ---------------- AUTO TRADE ENGINE (PER CLIENT) ---------------- #
def run_auto_trade(client_id, state):
    active_profile = state.get("active_profile", "KOOLKID")

    strategies = state.get("strategies", {})
    strategy = strategies.get(active_profile)
    if not strategy:
        return

    signals = None

    if active_profile == "JOKERJOE" and hasattr(strategy, "check_multig_signal"):
        try:
            multig_sig = strategy.check_multig_signal()
            if multig_sig:
                signals = multig_sig
        except Exception:
            pass

    if hasattr(strategy, "check_auto_trade_signal"):
        try:
            auto_sig = strategy.check_auto_trade_signal()
            if auto_sig:
                if not signals:
                    signals = auto_sig
        except Exception:
            pass

    if not signals:
        return

    if isinstance(signals, dict):
        signals = [signals]

    for sig in signals:
        try:
            ctype = sig.get("type")
            barrier = sig.get("barrier")
            symbol = sig.get("symbol") or state.get("current_symbol", "R_25")
            stake = float(sig.get("stake", state.get("auto_stake", 1.0)) or state.get("auto_stake", 1.0))
            duration = sig.get("duration", 1)
            duration_unit = sig.get("duration_unit", "t")
            mode = sig.get("mode")

            if active_profile == "UNCHAIN" or str(ctype).upper() == "ACCU":
                un = (state.get("strategies") or {}).get("UNCHAIN")
                growth_rate = sig.get("growth_rate", getattr(un, "growth_rate", 0.02) if un else 0.02)
                exit_ticks = sig.get("exit_ticks", getattr(un, "auto_exit_ticks", 5) if un else 5)
                mode = sig.get("mode", "AUTO")
                ok, msg = _send_unchain_buy(
                    client_id,
                    stake=stake,
                    symbol=symbol,
                    growth_rate=growth_rate,
                    mode=mode,
                    exit_ticks=exit_ticks,
                )
            else:
                ok, msg = send_buy(
                    client_id,
                    ctype,
                    stake,
                    symbol,
                    barrier,
                    duration=duration,
                    duration_unit=duration_unit,
                    mode=mode,
                )

            if ok:
                logger.info(f"[{client_id}] 🤖 AUTO TRADE SENT ({active_profile}): {ctype} barrier={barrier} stake={stake} mode={sig.get('mode')}")
                if hasattr(strategy, "on_auto_trade_sent"):
                    try:
                        strategy.on_auto_trade_sent(sig)
                    except Exception:
                        pass
            else:
                logger.error(f"[{client_id}] ❌ AUTO TRADE FAILED: {msg}")
                if hasattr(strategy, "on_auto_trade_failed"):
                    try:
                        strategy.on_auto_trade_failed(sig, msg)
                    except Exception:
                        pass

        except Exception as e:
            logger.error(f"[{client_id}] Auto trade error: {e}")


# ==================== PATCH 1D: Sequential VIX engine helpers ====================
SEQVIX_MARKETS = [
    "R_10", "R_25", "R_50", "R_75", "R_100",
    "1HZ10V", "1HZ15V", "1HZ25V", "1HZ30V", "1HZ50V", "1HZ75V", "1HZ90V", "1HZ100V",
    "RDBULL", "RDBEAR",
]

def _seqvix_emit_progress(client_id, state, profile, reason=None):
    run = state["seqvix"][profile]
    payload = {
        "profile": profile,
        "running": bool(run.get("running")),
        "done": int(run.get("done", 0)),
        "total": (None if run.get("endless") else int(run.get("total", 0))),
    }
    if reason:
        payload["reason"] = reason
    socketio.emit("seqvix_progress", payload, room=client_id)

def _seqvix_forget_symbol(state, profile, sym):
    """Only forget if this seqvix runner owns the symbol."""
    run = state["seqvix"][profile]
    if sym not in run.get("owned_syms", set()):
        return  # not ours, don't touch
    ws = state.get("ws")
    if not ws or not state.get("ws_connected"):
        return
    sub_id = (state.get("tick_subs") or {}).get(sym)
    if sub_id:
        try:
            ws.send(json.dumps({"forget": sub_id}))
        except Exception:
            pass
        try:
            state.setdefault("tick_subs", {}).pop(sym, None)
        except Exception:
            pass
    run["owned_syms"].discard(sym)

def _seqvix_fill_batch(state, profile):
    run = state["seqvix"][profile]
    ws = state.get("ws")
    if not ws or not state.get("ws_connected"):
        return

    while len(run["active_syms"]) < run["batch_size"]:
        if not run["remaining"]:
            if run.get("endless"):
                run["remaining"] = SEQVIX_MARKETS.copy()
                random.shuffle(run["remaining"])
            else:
                break

        sym = run["remaining"].pop()
        if sym in run["active_syms"]:
            continue

        # ==================== PATCH 1B: avoid duplicate subscriptions ====================
        existing_sub_id = (state.get("tick_subs") or {}).get(sym)
        if existing_sub_id:
            # already subscribed elsewhere (main market or previous stream)
            run["active_syms"].add(sym)
            run["samples"][sym] = []
            # do NOT add to owned_syms, do NOT subscribe again
            continue

        # otherwise subscribe and mark as owned by seqvix
        run["active_syms"].add(sym)
        run["samples"][sym] = []
        run["owned_syms"].add(sym)
        try:
            ws.send(json.dumps({"ticks": sym, "subscribe": 1}))
        except Exception:
            pass

def _pick_two_rarest_digits(sample):
    counts = {d: 0 for d in range(10)}
    for d in sample:
        if d in counts:
            counts[d] += 1
    ordered = sorted(counts.items(), key=lambda kv: (kv[1], kv[0]))
    return ordered[0][0], ordered[1][0]

def stop_seqvix(state, client_id, profile, reason="stopped"):
    run = state["seqvix"][profile]
    if not run.get("running"):
        return

    # ==================== PATCH 1C: only forget owned symbols ====================
    for sym in list(run.get("owned_syms", set())):
        _seqvix_forget_symbol(state, profile, sym)

    run["running"] = False
    run["endless"] = False
    run["total"] = 0
    run["active_syms"] = set()
    run["samples"] = {}
    run["ready_syms"] = set()
    run["remaining"] = []
    run["last_exec_ts"] = 0.0
    run["config"] = {}
    run["owned_syms"] = set()
    run["cooldown_until"] = 0.0

    _seqvix_emit_progress(client_id, state, profile, reason=reason)

def start_seqvix_jokerjoe(state, client_id, mode, trades_per_market=2):
    run = state["seqvix"]["JOKERJOE"]
    if run.get("running"):
        stop_seqvix(state, client_id, "JOKERJOE", reason="restart")

    # ==================== PATCH 1E: sanitize trades_per_market ====================
    try:
        tpm = int(trades_per_market)
    except Exception:
        tpm = 2
    if tpm not in (1, 2):
        tpm = 2

    mode_str = str(mode).upper().strip()
    endless = (mode_str == "ENDLESS")
    total = 0
    if not endless:
        try:
            total = int(mode_str)
        except Exception:
            total = 5
        if total not in (5, 10):
            total = 5

    run.update({
        "running": True, "endless": endless, "total": total, "done": 0,
        "batch_size": 6, "sample_size": 30,
        "remaining": SEQVIX_MARKETS.copy(),
        "active_syms": set(), "samples": {}, "ready_syms": set(),
        "last_exec_ts": 0.0, "config": {},
        "owned_syms": set(), "cooldown_until": 0.0, "trades_per_market": tpm, "cooldown_sec": 5.0,
    })
    random.shuffle(run["remaining"])

    _seqvix_fill_batch(state, "JOKERJOE")
    _seqvix_emit_progress(client_id, state, "JOKERJOE")

def start_seqvix_koolkid(state, client_id, contract_type, barrier, trades_per_market=2):
    run = state["seqvix"]["KOOLKID"]
    if run.get("running"):
        stop_seqvix(state, client_id, "KOOLKID", reason="restart")

    # ==================== PATCH 1E: sanitize trades_per_market ====================
    try:
        tpm = int(trades_per_market)
    except Exception:
        tpm = 2
    if tpm not in (1, 2):
        tpm = 2

    ct = str(contract_type).upper().strip()
    if ct not in ("OVER", "UNDER"):
        ct = "OVER"
    try:
        b = int(barrier)
    except Exception:
        b = 1

    run.update({
        "running": True, "endless": False, "total": 10, "done": 0,
        "batch_size": 6, "sample_size": 30,
        "remaining": SEQVIX_MARKETS.copy(),
        "active_syms": set(), "samples": {}, "ready_syms": set(),
        "last_exec_ts": 0.0,
        "config": {"contract_type": ct, "barrier": b},
        "owned_syms": set(), "cooldown_until": 0.0, "trades_per_market": tpm, "cooldown_sec": 5.0,
    })
    random.shuffle(run["remaining"])

    _seqvix_fill_batch(state, "KOOLKID")
    _seqvix_emit_progress(client_id, state, "KOOLKID")

def _seqvix_execute_one_market(client_id, state, profile, sym):
    run = state["seqvix"][profile]
    sample = run["samples"].get(sym, [])
    if len(sample) < run["sample_size"]:
        return False

    stake = float(state.get("auto_stake", 1.0))
    trade_count = int(run.get("trades_per_market", 2))

    if profile == "JOKERJOE":
        d1, d2 = _pick_two_rarest_digits(sample)
        if trade_count == 1:
            # only the rarest digit
            ok1, _ = send_buy_with_profile(client_id, "JOKERJOE", "DIFFERS", stake, sym, d1)
            return ok1
        else:
            ok1, _ = send_buy_with_profile(client_id, "JOKERJOE", "DIFFERS", stake, sym, d1)
            ok2, _ = send_buy_with_profile(client_id, "JOKERJOE", "DIFFERS", stake, sym, d2)
            return ok1 and ok2
    else:
        ct = run["config"].get("contract_type", "OVER")
        barrier = int(run["config"].get("barrier", 1))
        if trade_count == 1:
            ok1, _ = send_buy_with_profile(client_id, "KOOLKID", ct, stake, sym, barrier)
            return ok1
        else:
            ok1, _ = send_buy_with_profile(client_id, "KOOLKID", ct, stake, sym, barrier)
            ok2, _ = send_buy_with_profile(client_id, "KOOLKID", ct, stake, sym, barrier)
            return ok1 and ok2

def process_seqvix_tick(client_id, tick):
    state = clients.get(client_id)
    if not state:
        return

    seqvix = state.get("seqvix") or {}
    sym = tick.get("symbol")
    if not sym:
        return

    active_profiles = [p for p in ("KOOLKID", "JOKERJOE") if seqvix.get(p, {}).get("running")]
    if not active_profiles:
        return

    # digit from tick quote
    try:
        price = tick.get("quote")
        pip_size = tick.get("pip_size", 2)
        d = extract_last_decimal_digit(price, pip_size)
    except Exception:
        d = None
    if d is None:
        return

    # update buffers
    for profile in active_profiles:
        run = seqvix[profile]
        if sym not in run.get("active_syms", set()):
            continue

        buf = run["samples"].setdefault(sym, [])
        if len(buf) < run["sample_size"]:
            buf.append(int(d))

        if len(buf) >= run["sample_size"]:
            run["ready_syms"].add(sym)

    # execute at most 1 market per tick per profile (rate limit) + cooldown
    now = time.time()
    for profile in active_profiles:
        run = seqvix[profile]
        if not run.get("running"):
            continue

        _seqvix_fill_batch(state, profile)

        if (not run.get("endless")) and run.get("total", 0) and run.get("done", 0) >= run["total"]:
            stop_seqvix(state, client_id, profile, reason="done")
            continue

        # ==================== PATCH 1D: cooldown check ====================
        if now < float(run.get("cooldown_until", 0.0)):
            continue

        if now - float(run.get("last_exec_ts", 0.0)) < 0.15:
            continue

        ready = list(run.get("ready_syms", set()))
        if not ready:
            continue

        chosen = random.choice(ready)
        ok = _seqvix_execute_one_market(client_id, state, profile, chosen)
        if not ok:
            continue

        # success => increment + cleanup that market
        run["done"] += 1
        run["last_exec_ts"] = now
        # ==================== PATCH 1D: set cooldown ====================
        run["cooldown_until"] = now + float(run.get("cooldown_sec", 5.0))

        _seqvix_forget_symbol(state, profile, chosen)
        run["ready_syms"].discard(chosen)
        run["active_syms"].discard(chosen)
        run["samples"].pop(chosen, None)

        _seqvix_fill_batch(state, profile)
        _seqvix_emit_progress(client_id, state, profile)

        if (not run.get("endless")) and run.get("total", 0) and run.get("done", 0) >= run["total"]:
            stop_seqvix(state, client_id, profile, reason="done")


# ==================== UNCHAIN MULTI-MARKET SCANNER (UP TO 10) ====================
UNCHAIN_SCANNER_DEFAULTS = [
    "R_10", "R_25", "R_50", "R_75", "R_100",
    "1HZ25V", "1HZ50V", "1HZ75V", "1HZ90V", "1HZ100V",
]
UNCHAIN_SCANNER_SAMPLE_SIZE = 30


def _ensure_unchain_scanner(state):
    scan = state.setdefault("unchain_scanner", {}) or {}
    scan.setdefault("running", False)
    scan.setdefault("symbols", [])
    scan.setdefault("buffers", {})
    scan.setdefault("analyses", {})
    scan.setdefault("owned_syms", set())
    try:
        sample_size = int(scan.get("sample_size", UNCHAIN_SCANNER_SAMPLE_SIZE) or UNCHAIN_SCANNER_SAMPLE_SIZE)
    except Exception:
        sample_size = UNCHAIN_SCANNER_SAMPLE_SIZE
    # Keep scanner behavior fixed: analyze 10 markets over 30 ticks.
    scan["sample_size"] = UNCHAIN_SCANNER_SAMPLE_SIZE if sample_size != UNCHAIN_SCANNER_SAMPLE_SIZE else sample_size
    scan.setdefault("max_symbols", 10)
    scan.setdefault("last_emit", 0.0)
    return scan


def _normalize_scanner_symbols(raw, max_symbols=10):
    if raw is None:
        raw = []
    if isinstance(raw, str):
        raw = raw.replace(";", ",").replace("|", ",").replace("\n", ",")
        raw = [s.strip() for s in raw.split(",")]
    symbols = []
    for s in raw:
        if not s:
            continue
        sym = str(s).strip().upper()
        if sym and sym not in symbols:
            symbols.append(sym)
        if len(symbols) >= max_symbols:
            break
    return symbols[:max_symbols]


def _build_unchain_scanner_analysis(buffer, sample_size=UNCHAIN_SCANNER_SAMPLE_SIZE, symbol=None):
    window = list(buffer)[-sample_size:]
    if len(window) < 6:
        return None

    last_price = window[-1]
    high = max(window)
    low = min(window)
    rng = high - low

    deltas = [window[i] - window[i - 1] for i in range(1, len(window))]
    avg_abs = sum(abs(d) for d in deltas) / max(1, len(deltas))
    trend = window[-1] - window[0]
    trend_norm = max(-1.0, min(1.0, trend / max((rng if rng > 0 else avg_abs * max(2.0, len(window) / 3.0)), 1e-9)))

    flips = 0
    prev_sign = 0
    for d in deltas:
        s = 1 if d > 0 else (-1 if d < 0 else 0)
        if prev_sign and s and s != prev_sign:
            flips += 1
        if s:
            prev_sign = s
    noise = min(1.0, flips / max(1, len(deltas)))
    cleanliness = max(0.0, 1.0 - noise)

    range_norm = min(1.0, rng / max(1e-9, (abs(last_price) * 0.015 if last_price else avg_abs * 8.0)))

    higher_confidence = max(5.0, min(99.0, 50.0 + (trend_norm * 45.0) + (range_norm * 20.0) + (cleanliness * 10.0)))
    lower_confidence = max(5.0, min(99.0, 100.0 - higher_confidence))
    direction = "HIGHER" if higher_confidence >= lower_confidence else "LOWER"
    confidence_dir = higher_confidence if direction == "HIGHER" else lower_confidence

    target_profit_mult = 1.5  # aim for ~150% profit style barriers
    base_barrier = (rng * 0.6) + (avg_abs * target_profit_mult * 0.5)
    if base_barrier <= 0:
        base_barrier = avg_abs * (target_profit_mult + 0.5)
    barrier_mag = max(0.01, min(1.5, base_barrier))
    barrier_mag = round(barrier_mag, 2)
    barrier_high = f"+{barrier_mag:.2f}"
    barrier_low = f"-{barrier_mag:.2f}"

    range_pct = (rng / max(1e-9, abs(last_price))) * 100.0
    score = max(higher_confidence, lower_confidence) + (range_norm * 10.0) + (cleanliness * 8.0)

    return {
        "symbol": symbol,
        "range": round(rng, 6),
        "range_pct": round(range_pct, 3),
        "trend": round(trend, 6),
        "direction": direction,
        "barrier_high": barrier_high,
        "barrier_low": barrier_low,
        "barrier_mag": barrier_mag,
        "confidence": round(confidence_dir, 1),
        "higher_confidence": round(higher_confidence, 1),
        "lower_confidence": round(lower_confidence, 1),
        "ticks_ready": len(window),
        "last_price": last_price,
        "score": score,
        "updated_at": now_time(),
        "range_high": round(high, 6),
        "range_low": round(low, 6),
    }


def _get_top_unchain_scanner_recs(scanner, limit=4):
    analyses = list((scanner.get("analyses") or {}).values())
    analyses = [a for a in analyses if a and a.get("ticks_ready", 0) >= scanner.get("sample_size", UNCHAIN_SCANNER_SAMPLE_SIZE)]
    analyses.sort(key=lambda a: max(a.get("higher_confidence", 0), a.get("lower_confidence", 0)), reverse=True)
    return analyses[:limit]


def _get_unchain_scanner_payload(state):
    scan = _ensure_unchain_scanner(state)
    top = _get_top_unchain_scanner_recs(scan)
    ready = sum(1 for a in (scan.get("analyses") or {}).values() if a and a.get("ticks_ready", 0) >= scan.get("sample_size", UNCHAIN_SCANNER_SAMPLE_SIZE))
    progress = []
    for sym in scan.get("symbols") or []:
        buf = (scan.get("buffers") or {}).get(sym)
        ticks_ready = len(buf) if isinstance(buf, deque) else 0
        analysis = (scan.get("analyses") or {}).get(sym) or {}
        progress.append({
            "symbol": sym,
            "ticks_ready": int(ticks_ready),
            "sample_size": int(scan.get("sample_size", UNCHAIN_SCANNER_SAMPLE_SIZE) or UNCHAIN_SCANNER_SAMPLE_SIZE),
            "barrier_high": analysis.get("barrier_high"),
            "barrier_low": analysis.get("barrier_low"),
            "higher_confidence": analysis.get("higher_confidence"),
            "lower_confidence": analysis.get("lower_confidence"),
            "range": analysis.get("range"),
            "range_pct": analysis.get("range_pct"),
        })
    return {
        "running": bool(scan.get("running")),
        "symbols": list(scan.get("symbols") or []),
        "max_symbols": int(scan.get("max_symbols", 10) or 10),
        "sample_size": int(scan.get("sample_size", UNCHAIN_SCANNER_SAMPLE_SIZE) or UNCHAIN_SCANNER_SAMPLE_SIZE),
        "recommendations": top,
        "total_tracked": len(scan.get("symbols") or []),
        "ready": int(ready),
        "last_emit": float(scan.get("last_emit", 0.0) or 0.0),
        "progress": progress,
    }


def _emit_unchain_scanner(client_id, state):
    payload = _get_unchain_scanner_payload(state)
    socketio.emit("unchain_scanner", payload, room=client_id)
    return payload


def _ensure_tick_subscription(state, symbol):
    """
    Best-effort self-heal for tick streams. Some UI flows can leave a symbol
    unsubscribed; this re-requests ticks if no active subscription id is known.
    """
    sym = str(symbol or "").strip().upper()
    if not sym:
        return
    ws = state.get("ws")
    if not state.get("ws_connected") or not ws:
        return
    tick_subs = state.setdefault("tick_subs", {})
    if tick_subs.get(sym):
        return
    try:
        ws.send(json.dumps({"ticks": sym, "subscribe": 1}))
    except Exception:
        pass


def _start_unchain_scanner(client_id, state, symbols=None):
    scan = _ensure_unchain_scanner(state)
    ws = state.get("ws")
    if not state.get("ws_connected") or not ws:
        return False, "Not connected", _get_unchain_scanner_payload(state)

    symbols = _normalize_scanner_symbols(symbols, max_symbols=int(scan.get("max_symbols", 10) or 10))
    if not symbols:
        symbols = UNCHAIN_SCANNER_DEFAULTS[: scan.get("max_symbols", 10)]

    scan["running"] = True
    scan["symbols"] = symbols
    scan["analyses"] = {}
    scan["last_emit"] = 0.0
    prev_owned = set(scan.get("owned_syms", set()) or set())
    scan["owned_syms"] = set()

    # keep existing buffers but reset lengths
    for sym in symbols:
        buf = scan["buffers"].get(sym)
        if not isinstance(buf, deque):
            buf = deque(maxlen=max(120, scan.get("sample_size", UNCHAIN_SCANNER_SAMPLE_SIZE) * 3))
        buf.maxlen = max(120, scan.get("sample_size", UNCHAIN_SCANNER_SAMPLE_SIZE) * 3)
        scan["buffers"][sym] = buf

    tick_subs = state.setdefault("tick_subs", {})
    main_symbol = state.get("current_symbol")
    human_symbol = state.get("human_symbol") or main_symbol

    # Clear stale subscriptions from a previous scanner run.
    for stale_sym in list(prev_owned):
        if stale_sym in symbols or stale_sym in (main_symbol, human_symbol):
            continue
        stale_id = tick_subs.get(stale_sym)
        if stale_id:
            try:
                ws.send(json.dumps({"forget": stale_id}))
            except Exception:
                pass
            tick_subs.pop(stale_sym, None)

    # Subscribe scanner symbols, self-healing stale/non-live sub ids.
    for sym in symbols:
        existing_sub_id = tick_subs.get(sym)
        if existing_sub_id and sym not in (main_symbol, human_symbol):
            try:
                ws.send(json.dumps({"forget": existing_sub_id}))
            except Exception:
                pass
            tick_subs.pop(sym, None)
            existing_sub_id = None
        if existing_sub_id:
            continue
        try:
            ws.send(json.dumps({"ticks": sym, "subscribe": 1}))
            # Never mark current main/human streams as scanner-owned.
            if sym not in (main_symbol, human_symbol):
                scan.setdefault("owned_syms", set()).add(sym)
        except Exception:
            pass

    return True, "Scanner started", _emit_unchain_scanner(client_id, state)


def _stop_unchain_scanner(client_id, state):
    scan = _ensure_unchain_scanner(state)
    ws = state.get("ws")
    tick_subs = state.setdefault("tick_subs", {})
    main_symbol = state.get("current_symbol")
    human_symbol = state.get("human_symbol") or main_symbol
    keep_owned = set()
    if state.get("ws_connected") and ws:
        for sym in list(scan.get("owned_syms", set())):
            if sym in (main_symbol, human_symbol):
                keep_owned.add(sym)
                continue
            sub_id = tick_subs.get(sym)
            if sub_id:
                try:
                    ws.send(json.dumps({"forget": sub_id}))
                except Exception:
                    pass
                tick_subs.pop(sym, None)
        scan["owned_syms"] = keep_owned
    scan["running"] = False
    scan["symbols"] = []
    scan["last_emit"] = time.time()
    return _emit_unchain_scanner(client_id, state)


def _process_unchain_scanner_tick(client_id, tick):
    state = clients.get(client_id)
    if not state:
        return
    scan = _ensure_unchain_scanner(state)
    if not scan.get("running"):
        return
    sym = tick.get("symbol")
    if not sym or sym not in (scan.get("symbols") or []):
        return
    try:
        price = float(tick.get("quote"))
    except Exception:
        return

    buf = scan["buffers"].setdefault(sym, deque(maxlen=max(120, scan.get("sample_size", UNCHAIN_SCANNER_SAMPLE_SIZE) * 3)))
    buf.append(price)

    sample_size = int(scan.get("sample_size", UNCHAIN_SCANNER_SAMPLE_SIZE) or UNCHAIN_SCANNER_SAMPLE_SIZE)
    if len(buf) >= max(6, sample_size):
        analysis = _build_unchain_scanner_analysis(buf, sample_size=sample_size, symbol=sym)
        if analysis:
            scan.setdefault("analyses", {})[sym] = analysis

    now = time.time()
    if now - float(scan.get("last_emit", 0.0) or 0.0) >= 0.45:
        scan["last_emit"] = now
        _emit_unchain_scanner(client_id, state)


def _apply_scanner_recommendation(client_id, state, symbol, switch_symbol=True):
    scan = _ensure_unchain_scanner(state)
    sym = str(symbol or "").upper().strip()
    if not sym:
        return False, "No symbol provided", _get_unchain_scanner_payload(state)
    analysis = (scan.get("analyses") or {}).get(sym)
    if not analysis:
        return False, f"No analysis ready for {sym}", _get_unchain_scanner_payload(state)

    try:
        mag = abs(float(analysis.get("barrier_mag") or 0.0))
    except Exception:
        mag = 0.0
    if mag <= 0:
        return False, "No barrier recommendation available", _get_unchain_scanner_payload(state)

    hb = f"{mag:.2f}"
    lb = f"-{mag:.2f}"
    u = _ensure_unchain_hl_state(state)
    u["higher_barrier"] = hb
    u["lower_barrier"] = lb
    u["last_action"] = f"Scanner set {hb} / {lb} on {sym}"

    if switch_symbol:
        old_symbol = state.get("current_symbol")
        human_symbol = state.get("human_symbol") or old_symbol
        state["current_symbol"] = sym
        # This symbol becomes MAIN, so scanner should not own it.
        scan.setdefault("owned_syms", set()).discard(sym)
        # reset non-HUMAN profile analysis
        for name, strat in state.get("strategies", {}).items():
            if name == "HUMAN":
                continue
            try:
                if hasattr(strat, "reset_tick_analysis"):
                    strat.reset_tick_analysis()
            except Exception:
                pass
        ws = state.get("ws")
        if state.get("ws_connected") and ws:
            try:
                tick_subs = state.setdefault("tick_subs", {})
                old_id = tick_subs.get(old_symbol)
                # Keep old symbol stream if HUMAN still depends on it.
                if old_id and old_symbol != human_symbol:
                    ws.send(json.dumps({"forget": old_id}))
                    tick_subs.pop(old_symbol, None)
                ws.send(json.dumps({"ticks": state["current_symbol"], "subscribe": 1}))
                # Keep scanner coverage intact if old symbol is still part of scanner markets.
                if scan.get("running") and old_symbol and old_symbol in (scan.get("symbols") or []) and old_symbol != sym:
                    ws.send(json.dumps({"ticks": old_symbol, "subscribe": 1}))
                    if old_symbol not in (state.get("current_symbol"), human_symbol):
                        scan.setdefault("owned_syms", set()).add(old_symbol)
            except Exception:
                pass
        socketio.emit("market_change", {"symbol": state["current_symbol"]}, room=client_id)

    payload = _unchain_payload_response(state)
    return True, f"Applied scanner pick for {sym}", payload

# ---------------- WEBSOCKET HANDLERS (PER CLIENT) ---------------- #
def handle_on_message(client_id, ws, message, expected_nonce):
    state = clients.get(client_id)
    if not state:
        return
    if state.get("ws_nonce") != expected_nonce:
        return  # stale WS callback

    try:
        data = json.loads(message)

        if "error" in data:
            msg = data["error"].get("message", "Unknown API Error")
            logger.error(f"[{client_id}] API Error: {msg}")
            socketio.emit("api_error", {"message": msg}, room=client_id)
            return

        if "authorize" in data:
            # AUTHORIZED
            state["ws_connected"] = True
            loginid = data["authorize"].get("loginid", "UNKNOWN")
            balance = float(data["authorize"].get("balance", 0))

            state["balance"] = balance

            if state["session_start_balance"] is None:
                state["session_start_balance"] = balance

            logger.info(f"[{client_id}] ✅ Authorized: {loginid} Balance={balance}")

            socketio.emit("connection_status", {
                "connected": True,
                "loginid": loginid,
                "balance": balance
            }, room=client_id)

            socketio.emit("balance_update", {"balance": balance}, room=client_id)
            emit_profile_snapshot(client_id)

            ws.send(json.dumps({"ticks": state["current_symbol"], "subscribe": 1}))

            # ✅ HUMAN runs its own market stream (independent)
            human_sym = state.get("human_symbol") or state["current_symbol"]
            if human_sym != state["current_symbol"]:
                ws.send(json.dumps({"ticks": human_sym, "subscribe": 1}))

            ws.send(json.dumps({"balance": 1, "subscribe": 1}))

            # seed HUMAN candles early so chart is ready instantly
            request_human_seed(client_id)

        if "balance" in data:
            try:
                balance = float(data["balance"]["balance"])
                state["balance"] = balance
                socketio.emit("balance_update", {"balance": balance}, room=client_id)
                send_stats_update(client_id)
            except Exception:
                pass


        if "candles" in data:
            try:
                raw = data.get("candles")
                candles = raw.get("candles") if isinstance(raw, dict) else raw
                if not isinstance(candles, list):
                    candles = []

                req_id = data.get("req_id")
                meta = None
                if req_id and req_id in state.get("req_meta", {}):
                    meta = state["req_meta"].pop(req_id, None)

                if meta and meta.get("kind") in ("human_5m_seed", "human_1h_seed"):
                    strat = state.get("strategies", {}).get("HUMAN")

                    if strat:
                        if meta.get("kind") == "human_5m_seed" and hasattr(strat, "seed_5m_history"):
                            strat.seed_5m_history(candles)
                        if meta.get("kind") == "human_1h_seed" and hasattr(strat, "seed_1h_history"):
                            strat.seed_1h_history(candles)

                    # Push chart update immediately if user is on HUMAN profile
                    if state.get("active_profile") == "HUMAN" and strat and hasattr(strat, "get_chart_data"):
                        socketio.emit("human_chart_data", strat.get_chart_data(), room=client_id)
            except Exception:
                pass


        if "tick" in data:
            tick = data["tick"]
            try:
                sub = data.get("subscription") or {}
                sub_id = sub.get("id")
                sym = tick.get("symbol")
                if sub_id and sym:
                    state.setdefault("tick_subs", {})
                    state["tick_subs"][sym] = sub_id
            except Exception:
                pass
            # ==================== PATCH 1E: hook process_seqvix_tick ====================
            process_seqvix_tick(client_id, tick)
            _process_unchain_scanner_tick(client_id, tick)
            process_tick(client_id, tick)

        if "buy" in data:
            buy = data["buy"]
            contract_id = buy.get("contract_id")
            req_id = data.get("req_id")

            meta = None
            if req_id and req_id in state["req_meta"]:
                meta = state["req_meta"].pop(req_id, None)

            if contract_id and meta:
                state["contract_meta"][contract_id] = meta
                state["contract_meta"][str(contract_id)] = meta
                norm_contract_id = _normalize_contract_id(contract_id)
                if norm_contract_id:
                    state["contract_meta"][norm_contract_id] = meta
                try:
                    if (meta.get("profile") or "").upper() == "UNCHAIN":
                        _upsert_unchain_active_contract(state, contract_id, meta=meta, status="OPEN")
                        us = (state.get("strategies") or {}).get("UNCHAIN")
                        if us and hasattr(us, "on_contract_opened") and str(meta.get("type") or "").upper() == "ACCU":
                            us.on_contract_opened(
                                contract_id=contract_id,
                                entry_tick_seq=getattr(us, "tick_count", 0),
                                mode=meta.get("mode", "AUTO"),
                                target_exit_ticks=meta.get("exit_ticks"),
                                symbol=meta.get("symbol") or state.get("current_symbol"),
                                stake=meta.get("stake"),
                            )
                except Exception:
                    pass
                socketio.emit("trade_placed", {
                    "profile": meta.get("profile"),
                    "type": meta.get("type"),
                    "barrier": meta.get("barrier"),
                    "stake": meta.get("stake"),
                    "symbol": meta.get("symbol"),
                    "time": meta.get("time"),
                    "contract_id": contract_id
                }, room=client_id)
            else:
                socketio.emit("trade_placed", {
                    "profile": state.get("active_profile", "KOOLKID"),
                    "type": "TRADE",
                    "barrier": None,
                    "stake": None,
                    "symbol": state.get("current_symbol"),
                    "time": now_time(),
                    "contract_id": contract_id
                }, room=client_id)

            if contract_id:
                ws.send(json.dumps({
                    "proposal_open_contract": 1,
                    "contract_id": contract_id,
                    "subscribe": 1
                }))

        if "sell" in data:
            try:
                sell_info = data.get("sell") or {}
                echo_req = data.get("echo_req") or {}
                cid_val = sell_info.get("contract_id") or echo_req.get("sell")
                meta_for_contract = _peek_contract_meta(state, cid_val)
                if _is_unchain_contract_known(state, cid_val, meta=meta_for_contract):
                    active_entry = _get_unchain_active_entry(state, cid_val) or {}
                    sold_for_raw = sell_info.get("sold_for")
                    if sold_for_raw in (None, ""):
                        sold_for_raw = sell_info.get("sell_price")
                    profit_raw = sell_info.get("profit")
                    buy_price_raw = sell_info.get("buy_price")
                    if buy_price_raw in (None, ""):
                        buy_price_raw = active_entry.get("stake")

                    if sold_for_raw not in (None, "") or profit_raw not in (None, ""):
                        try:
                            sold_for = float(sold_for_raw or 0)
                        except Exception:
                            sold_for = 0.0
                        try:
                            buy_price = float(buy_price_raw or 0)
                        except Exception:
                            buy_price = 0.0
                        try:
                            profit_value = float(profit_raw) if profit_raw not in (None, "") else (sold_for - buy_price)
                        except Exception:
                            profit_value = sold_for - buy_price

                        synthetic_contract = {
                            "contract_id": cid_val,
                            "status": "sold",
                            "is_sold": True,
                            "sell_price": sold_for,
                            "buy_price": buy_price,
                            "profit": profit_value,
                        }
                        process_contract(client_id, synthetic_contract)
                    else:
                        _upsert_unchain_active_contract(
                            state,
                            cid_val,
                            meta=meta_for_contract,
                            contract={"contract_id": cid_val, "status": "CLOSE REQUESTED"},
                            status="CLOSE REQUESTED",
                        )
                        try:
                            ws.send(json.dumps({
                                "proposal_open_contract": 1,
                                "contract_id": int(float(cid_val)),
                                "subscribe": 1,
                            }))
                        except Exception:
                            pass
                    if state.get("active_profile") == "UNCHAIN":
                        socketio.emit("unchain_status", _unchain_payload_response(state), room=client_id)
            except Exception:
                pass

        if "proposal_open_contract" in data:
            contract = data["proposal_open_contract"]

            # UNCHAIN live open-contract updates
            try:
                cid_val = contract.get("contract_id")
                meta_for_contract = _peek_contract_meta(state, cid_val)
                unchain_known = _is_unchain_contract_known(state, cid_val, meta=meta_for_contract)
                if unchain_known and not _is_contract_settled_fast(contract):
                    _upsert_unchain_active_contract(state, cid_val, meta=meta_for_contract, contract=contract, status="OPEN")
                un = (state.get("strategies") or {}).get("UNCHAIN")
                if un and hasattr(un, "on_open_contract"):
                    if ((meta_for_contract and (meta_for_contract.get("profile") or "").upper() == "UNCHAIN" and str(meta_for_contract.get("type") or "").upper() == "ACCU")
                        or (getattr(un, "active_contract_id", None) and cid_val and int(getattr(un, "active_contract_id")) == int(cid_val))):
                        un.on_open_contract(contract)
                if state.get("active_profile") == "UNCHAIN":
                    socketio.emit("unchain_status", _unchain_payload_response(state), room=client_id)
            except Exception:
                pass

            process_contract(client_id, contract)

    except Exception as e:
        logger.error(f"[{client_id}] on_message error: {e}")



def process_tick(client_id, tick):
    state = clients.get(client_id)
    if not state:
        return

    try:
        symbol = tick.get("symbol")
        price = tick.get("quote")

        main_symbol = state.get("current_symbol")
        human_symbol = state.get("human_symbol") or main_symbol

        is_main = (symbol == main_symbol)
        is_human = (symbol == human_symbol)

        # ignore ticks we don't care about
        if not (is_main or is_human):
            return

        pip_size = tick.get("pip_size", 2)
        digit = extract_last_decimal_digit(price, pip_size) if is_main else None

        # epoch for HUMAN candles
        try:
            ts = int(tick.get("epoch") or tick.get("timestamp") or tick.get("time") or 0)
        except Exception:
            ts = 0

        strategies = state.get("strategies", {})

        # ✅ Collect data for ALL profiles (background)
        for name, strat in strategies.items():
            try:
                if name == "HUMAN":
                    if not is_human:
                        continue
                    # HUMAN expects PRICE candles/OB logic
                    strat.on_tick(tick, price, ts=ts if ts else None)

                    # ✅ HUMAN Rise/Fall Smart Assist AUTO (HUMAN profile active only)
                    try:
                        rf_enabled = bool(getattr(strat, "rf_auto_assist", False))
                        if rf_enabled and state.get("active_profile") == "HUMAN":
                            rf_sig = strat.build_human_rf_trade_signal(force_direction=None, require_threshold=True)
                            if rf_sig:
                                rf_sig["symbol"] = human_symbol
                                ok, _msg = place_risefall_order(client_id, rf_sig)
                                if not ok:
                                    logger.warning(f"[{client_id}] HUMAN RF auto trade blocked: {_msg}")
                    except Exception:
                        pass
                else:
                    if not is_main:
                        continue
                    strat.on_tick(tick, digit)
            except TypeError:
                # fallback safety
                try:
                    if is_main:
                        strat.on_tick(tick, digit)
                except Exception:
                    pass
            except Exception:
                pass

        # UNCHAIN precise exit-by-ticks / early-exit checks run in background on main market ticks
        if is_main:
            _maybe_unchain_exit_on_tick(client_id, state)

        # Active strategy for UI only
        active_profile = state.get("active_profile", "KOOLKID")
        active_strategy = strategies.get(active_profile)

        want_symbol = human_symbol if active_profile == "HUMAN" else main_symbol
        if symbol != want_symbol:
            return

        socketio.emit("tick", {
            "symbol": symbol,
            "digit": digit if digit is not None else extract_last_decimal_digit(price, pip_size),
            "price": price,
            "tick_count": getattr(active_strategy, "tick_count", 0) if active_strategy else 0,
            "timestamp": now_time()
        }, room=client_id)

        # Digit analysis only for KOOLKID/JOKERJOE style payloads
        if active_strategy and hasattr(active_strategy, "get_ui_payload"):
            socketio.emit("digit_analysis", active_strategy.get_ui_payload(), room=client_id)

        run_auto_trade(client_id, state)
        if is_main:
            _run_unchain_auto_both(client_id, state)

        if active_profile == "UNCHAIN":
            socketio.emit("unchain_status", _unchain_payload_response(state), room=client_id)

        if active_profile == "JOKERJOE":
            jj = strategies.get("JOKERJOE")
            if jj:
                emit_jokerjoe_modes(client_id, jj)

        if active_profile == "HUMAN":
            strat = strategies.get("HUMAN")
            if strat and hasattr(strat, "get_chart_data"):
                socketio.emit("human_chart_data", strat.get_chart_data(), room=client_id)
            if strat and hasattr(strat, "get_human_rf_payload"):
                socketio.emit("human_rf_status", strat.get_human_rf_payload(), room=client_id)

    except Exception as e:
        logger.error(f"[{client_id}] process_tick error: {e}")



def _is_contract_settled_fast(contract: dict) -> bool:
    try:
        if contract.get("is_sold") or contract.get("is_settled"):
            return True
        status = (contract.get("status") or "").lower()
        # Deriv can report settled contracts under several terminal states.
        if status in ("sold", "won", "lost", "settled", "closed", "expired", "cancelled", "canceled"):
            return True
        if contract.get("sell_price") is not None and contract.get("sell_price") != "":
            return True
    except Exception:
        pass
    return False


def process_contract(client_id, contract):
    state = clients.get(client_id)
    if not state:
        return

    try:
        if not _is_contract_settled_fast(contract):
            return

        profit = float(contract.get("profit", 0) or 0)
        state["balance"] = float(state.get("balance", 0.0)) + profit

        contract_id = contract.get("contract_id")
        if _is_unchain_contract_processed(state, contract_id):
            _remove_unchain_active_contract(state, contract_id)
            _pull_contract_meta(state, contract_id)
            if state.get("active_profile") == "UNCHAIN":
                socketio.emit("unchain_status", _unchain_payload_response(state), room=client_id)
            return

        meta = _pull_contract_meta(state, contract_id) if contract_id is not None else None
        if _is_unchain_contract_known(state, contract_id, meta=meta):
            profile_for_contract = "UNCHAIN"
        else:
            profile_for_contract = (meta.get("profile") if meta else None) or state.get("active_profile", "KOOLKID")
        entry = {}

        if profile_for_contract == "UNCHAIN":
            entry = _finalize_unchain_contract(state, contract, meta=meta)
            _mark_unchain_contract_processed(state, contract_id)
        else:
            strategies = state.get("strategies", {})
            strategy = strategies.get(profile_for_contract)
            if not strategy:
                return
            prev_block = getattr(strategy, "risk_block_reason", None)
            strategy.on_contract(contract, state.get("balance", 0))
            if hasattr(strategy, "on_contract_settled"):
                try:
                    strategy.on_contract_settled(contract, meta=meta)
                except Exception:
                    pass
            new_block = getattr(strategy, "risk_block_reason", None)
            if new_block and new_block != prev_block:
                socketio.emit("risk_block_update", {
                    "profile": profile_for_contract,
                    "reason": new_block
                }, room=client_id)
            if strategy and hasattr(strategy, "get_last_trade_entry"):
                entry = strategy.get_last_trade_entry() or {}
            if meta:
                entry.setdefault("profile", meta.get("profile"))
                entry.setdefault("type", meta.get("type"))
                entry.setdefault("barrier", meta.get("barrier"))
                entry.setdefault("stake", meta.get("stake"))
                entry.setdefault("symbol", meta.get("symbol"))
                entry.setdefault("time", meta.get("time"))
            else:
                entry.setdefault("profile", profile_for_contract)
            exit_digit = extract_exit_digit_from_contract(contract)
            if exit_digit is not None:
                entry["exit_digit"] = exit_digit

        socketio.emit("trade_result", entry, room=client_id)
        if profile_for_contract == "UNCHAIN":
            _run_unchain_auto_both(client_id, state)
        if state.get("active_profile") == "UNCHAIN":
            socketio.emit("unchain_status", _unchain_payload_response(state), room=client_id)
        send_stats_update(client_id)

    except Exception as e:
        logger.error(f"[{client_id}] process_contract error: {e}")


def send_stats_update(client_id):
    state = clients.get(client_id)
    if not state:
        return

    active_profile = state.get("active_profile", "KOOLKID")
    if active_profile == "UNCHAIN":
        u = _ensure_unchain_hl_state(state)
        stats = u.get("stats") or {}
        wins = int(stats.get("wins", 0) or 0)
        losses = int(stats.get("losses", 0) or 0)
        total = wins + losses
        winrate = round((wins / total) * 100, 1) if total else 0.0
        payload = {
            "profile": "UNCHAIN",
            "wins": wins,
            "losses": losses,
            "winrate": winrate,
            "net_pnl": float(stats.get("net_pnl", 0.0) or 0.0),
            "auto_trade": bool(u.get("auto_both_enabled", False)),
        }
        socketio.emit("stats_update", payload, room=client_id)
        return

    strategies = state.get("strategies", {})
    strategy = strategies.get(active_profile)
    if not strategy or not hasattr(strategy, "get_stats_payload"):
        return

    payload = strategy.get_stats_payload(state.get("balance", 0.0), state.get("session_start_balance"))
    payload["profile"] = active_profile
    socketio.emit("stats_update", payload, room=client_id)


def handle_on_open(client_id, ws, expected_nonce):
    state = clients.get(client_id)
    if not state:
        return
    if state.get("ws_nonce") != expected_nonce:
        return

    logger.info(f"[{client_id}] 🔌 WebSocket transport connected")
    state["ws_transport_connected"] = True
    state["ws_connected"] = False  # IMPORTANT: not authorized yet

    api_token = state.get("api_token")
    if api_token:
        ws.send(json.dumps({"authorize": api_token}))


def handle_on_error(client_id, ws, error, expected_nonce):
    state = clients.get(client_id)
    if not state:
        return
    if state.get("ws_nonce") != expected_nonce:
        return
    logger.error(f"[{client_id}] WebSocket Error: {error}")
    socketio.emit("api_error", {"message": str(error)}, room=client_id)


def handle_on_close(client_id, ws, code, msg, expected_nonce):
    state = clients.get(client_id)
    if not state:
        return
    if state.get("ws_nonce") != expected_nonce:
        return

    state["ws_connected"] = False
    state["ws_transport_connected"] = False
    logger.warning(f"[{client_id}] 🔌 WebSocket Disconnected")
    socketio.emit("connection_status", {"connected": False, "loginid": "UNKNOWN", "balance": state.get("balance", 0.0)}, room=client_id)


def start_ws_for_client(client_id):
    state = clients.get(client_id)
    if not state:
        return

    # bump nonce -> invalidates older WS callbacks
    state["ws_nonce"] = state.get("ws_nonce", 0) + 1
    expected_nonce = state["ws_nonce"]

    # stop old ws/thread
    try:
        state["ws_stop_event"].set()
    except Exception:
        pass

    old_ws = state.get("ws")
    if old_ws:
        try:
            old_ws.close()
        except Exception:
            pass

    # new stop event for this run
    state["ws_stop_event"] = threading.Event()

    def _on_message(ws, message, cid=client_id, nonce=expected_nonce):
        if state["ws_stop_event"].is_set():
            return
        handle_on_message(cid, ws, message, nonce)

    def _on_open(ws, cid=client_id, nonce=expected_nonce):
        if state["ws_stop_event"].is_set():
            return
        handle_on_open(cid, ws, nonce)

    def _on_error(ws, error, cid=client_id, nonce=expected_nonce):
        if state["ws_stop_event"].is_set():
            return
        handle_on_error(cid, ws, error, nonce)

    def _on_close(ws, code, msg, cid=client_id, nonce=expected_nonce):
        handle_on_close(cid, ws, code, msg, nonce)

    ws_app = websocket.WebSocketApp(
        DERIV_WS,
        on_message=_on_message,
        on_open=_on_open,
        on_error=_on_error,
        on_close=_on_close
    )

    state["ws"] = ws_app

    # run until closed
    try:
        ws_app.run_forever(ping_interval=0, ping_timeout=None)
    except Exception:
        pass


# ---------------- BOT API ROUTES ---------------- #
@app.route("/set_token", methods=["POST"])
def set_token():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    token = (request.json or {}).get("token", "")

    state["api_token"] = token
    state["session_start_balance"] = None

    # start WS but avoid "2 instances" per browser session
    t = state.get("ws_thread")
    if t and t.is_alive():
        try:
            state["ws_stop_event"].set()
        except Exception:
            pass
        try:
            if state.get("ws"):
                state["ws"].close()
        except Exception:
            pass

    t = threading.Thread(target=start_ws_for_client, args=(cid,), daemon=True)
    state["ws_thread"] = t
    t.start()

    return jsonify({"status": "connecting"})


@app.route("/set_auto_stake", methods=["POST"])
def set_auto_stake():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()

    try:
        stake = float((request.json or {}).get("stake", 1))
        if stake <= 0:
            stake = 1.0
    except Exception:
        stake = 1.0

    state["auto_stake"] = stake
    logger.info(f"[{cid}] 💰 AUTO STAKE UPDATED: {stake}")

    # ✅ also sync stake into HUMAN strategy so manual/Rise-Fall uses your stake input
    try:
        h = state["strategies"].get("HUMAN")
        if h and hasattr(h, "stake"):
            h.stake = float(stake)
    except Exception:
        pass

    return jsonify({"status": "success", "auto_stake": stake})


@app.route("/disconnect", methods=["POST"])
def disconnect():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, _state = get_client_state()
    disconnect_client(cid, reason="client_disconnect", emit=True)
    return jsonify({"status": "disconnected"})


@app.route("/clear_profile_history", methods=["POST"])
def clear_profile_history():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    data = request.json or {}
    profile = (data.get("profile") or state.get("active_profile") or "KOOLKID").upper()

    strat = state["strategies"].get(profile)
    if strat and hasattr(strat, "clear_history"):
        strat.clear_history()

    if profile == "UNCHAIN":
        u = _ensure_unchain_hl_state(state)
        u["stats"] = {"wins": 0, "losses": 0, "net_pnl": 0.0}
        u["last_result"] = None
        u["last_action"] = "Ready"
        u["risk_block_reason"] = None

    if profile == state.get("active_profile"):
        send_stats_update(cid)
        if profile == "UNCHAIN":
            socketio.emit("unchain_status", _unchain_payload_response(state), room=cid)

    return jsonify({"status": "cleared", "profile": profile, "payload": (_unchain_payload_response(state) if profile == "UNCHAIN" else None)})


@app.route("/set_profile", methods=["POST"])
def set_profile():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    profile = (request.json or {}).get("profile", "KOOLKID")

    if profile not in state["strategies"]:
        return jsonify({"error": "Invalid profile"}), 400

    state["active_profile"] = profile
    if profile == "HUMAN":
        _ensure_tick_subscription(state, state.get("human_symbol") or state.get("current_symbol"))
    else:
        _ensure_tick_subscription(state, state.get("current_symbol"))
    socketio.emit("profile_update", {"profile": profile, "symbol": (state.get("human_symbol") if profile == "HUMAN" else state.get("current_symbol"))}, room=cid)
    if profile == "HUMAN":
        request_human_seed(cid)
    emit_profile_snapshot(cid)

    return jsonify({"status": "success", "profile": profile, "main_symbol": state.get("current_symbol"), "human_symbol": state.get("human_symbol") or state.get("current_symbol"), "symbol": (state.get("human_symbol") if profile == "HUMAN" else state.get("current_symbol")),
    })


@app.route("/market_state", methods=["GET"])
def market_state():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    prof = state.get("active_profile", "KOOLKID")
    return jsonify({
        "status": "success",
        "profile": prof,
        "main_symbol": state.get("current_symbol"),
        "human_symbol": state.get("human_symbol") or state.get("current_symbol"),
        "symbol": (state.get("human_symbol") if prof == "HUMAN" else state.get("current_symbol")),
    })


@app.route("/change_market", methods=["POST"])
def change_market():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    symbol = (request.json or {}).get("symbol")

    if not symbol:
        return jsonify({"error": "No symbol provided"}), 400

    old_symbol = state.get("current_symbol")
    human_symbol = state.get("human_symbol") or old_symbol
    state["current_symbol"] = symbol

    # ✅ reset analysis for MAIN profiles only (HUMAN is independent)
    for name, strat in state.get("strategies", {}).items():
        if name == "HUMAN":
            continue
        try:
            if hasattr(strat, "reset_tick_analysis"):
                strat.reset_tick_analysis()
        except Exception:
            pass

    ws = state.get("ws")
    if state.get("ws_connected") and ws:
        try:
            # best-effort unsubscribe old MAIN ticks (do not touch HUMAN)
            tick_subs = state.setdefault("tick_subs", {})
            old_id = tick_subs.get(old_symbol)
            # Do not forget if HUMAN still streams the old symbol.
            if old_id and old_symbol != human_symbol:
                ws.send(json.dumps({"forget": old_id}))
                tick_subs.pop(old_symbol, None)
            ws.send(json.dumps({"ticks": state["current_symbol"], "subscribe": 1}))
        except Exception:
            pass

    socketio.emit("market_change", {"symbol": state["current_symbol"]}, room=cid)
    return jsonify({
        "status": "success",
        "symbol": state["current_symbol"],
        "main_symbol": state.get("current_symbol"),
        "human_symbol": state.get("human_symbol") or state.get("current_symbol")
    })


@app.route("/change_human_market", methods=["POST"])
def change_human_market():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    symbol = (request.json or {}).get("symbol")

    if not symbol:
        return jsonify({"error": "No symbol provided"}), 400

    main_symbol = state.get("current_symbol")
    old_symbol = state.get("human_symbol") or main_symbol
    state["human_symbol"] = symbol

    # reset HUMAN analysis only
    strat = state.get("strategies", {}).get("HUMAN")
    if strat:
        try:
            if hasattr(strat, "reset_tick_analysis"):
                strat.reset_tick_analysis()
            if hasattr(strat, "symbol"):
                strat.symbol = symbol
        except Exception:
            pass

    ws = state.get("ws")
    if state.get("ws_connected") and ws:
        try:
            tick_subs = state.setdefault("tick_subs", {})
            old_id = tick_subs.get(old_symbol)
            # If HUMAN previously shared MAIN symbol, keep that stream alive.
            if old_id and old_symbol != main_symbol:
                ws.send(json.dumps({"forget": old_id}))
                tick_subs.pop(old_symbol, None)
            ws.send(json.dumps({"ticks": symbol, "subscribe": 1}))
        except Exception:
            pass

    # refresh HUMAN chart candles on HUMAN market change
    request_human_seed(cid)

    socketio.emit("human_market_change", {"symbol": symbol}, room=cid)
    return jsonify({
        "status": "success",
        "symbol": symbol,
        "main_symbol": state.get("current_symbol"),
        "human_symbol": state.get("human_symbol") or state.get("current_symbol")
    })


@app.route("/set_risk_controls", methods=["POST"])
def set_risk_controls():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    data = request.json or {}
    tp = float(data.get("tp", 0))
    sl = float(data.get("sl", 0))
    auto_sl = bool(data.get("auto_sl", True))

    strategy = state["strategies"].get(state["active_profile"])
    if strategy and hasattr(strategy, "set_risk_controls"):
        strategy.set_risk_controls(tp=tp, sl=sl, auto_sl=auto_sl)

    return jsonify({"status": "success"})


@app.route("/toggle_auto", methods=["POST"])
def toggle_auto():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()

    strategy = state["strategies"].get(state["active_profile"])
    if not strategy or not hasattr(strategy, "toggle_auto"):
        return jsonify({"status": "error", "message": "No strategy loaded"}), 400

    new_state = strategy.toggle_auto()
    send_stats_update(cid)

    if state.get("active_profile") == "JOKERJOE":
        jj = state["strategies"].get("JOKERJOE")
        if jj:
            emit_jokerjoe_modes(cid, jj)

    return jsonify({"status": "success", "auto_trade": new_state})


# ---------------- AUTO MODE ROUTES (KOOLKID) ---------------- #
@app.route("/toggle_kidracks_auto", methods=["POST"])
def toggle_kidracks_auto_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    strat = state["strategies"].get("KOOLKID")
    state_val = strat.toggle_kidracks_auto()

    socketio.emit("auto_mode_update", strat.get_ui_payload().get("auto_modes", {}), room=cid)
    return jsonify({"status": "success", "kidracks_auto": state_val})


@app.route("/toggle_koolkidspeed_auto", methods=["POST"])
def toggle_koolkidspeed_auto_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    strat = state["strategies"].get("KOOLKID")
    state_val = strat.toggle_koolkidspeed_auto()

    socketio.emit("auto_mode_update", strat.get_ui_payload().get("auto_modes", {}), room=cid)
    return jsonify({"status": "success", "koolkidspeed_auto": state_val})


@app.route("/toggle_koolluck_auto", methods=["POST"])
def toggle_koolluck_auto_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    strat = state["strategies"].get("KOOLKID")
    state_val = strat.toggle_koolluck_auto()

    socketio.emit("auto_mode_update", strat.get_ui_payload().get("auto_modes", {}), room=cid)
    return jsonify({"status": "success", "koolluck_auto": state_val})


# ==================== EXISTING kidbagz AND mpull ROUTES ====================
@app.route("/toggle_kidbagz_auto", methods=["POST"])
def toggle_kidbagz_auto_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    strat = state["strategies"].get("KOOLKID")
    state_val = strat.toggle_kidbagz_auto()

    socketio.emit("auto_mode_update", strat.get_ui_payload().get("auto_modes", {}), room=cid)
    return jsonify({"status": "success", "kidbagz_auto": state_val})


@app.route("/toggle_mpull_auto", methods=["POST"])
def toggle_mpull_auto_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    strat = state["strategies"].get("KOOLKID")
    state_val = strat.toggle_mpull_auto()

    socketio.emit("auto_mode_update", strat.get_ui_payload().get("auto_modes", {}), room=cid)
    return jsonify({"status": "success", "mpull_auto": state_val})


# ==================== NEW ROUTES (kidPairs, MPull mode, kidPairs trades) ====================
@app.route("/toggle_kidpairs_auto", methods=["POST"])
def toggle_kidpairs_auto_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    strat = state["strategies"].get("KOOLKID")
    state_val = strat.toggle_kidpairs_auto()

    socketio.emit("auto_mode_update", strat.get_ui_payload().get("auto_modes", {}), room=cid)
    return jsonify({"status": "success", "kidpairs_auto": state_val})


@app.route("/toggle_over3_analysis_koolkid", methods=["POST"])
def toggle_over3_analysis_koolkid_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    strat = state["strategies"].get("KOOLKID")
    if not strat or not hasattr(strat, "toggle_over3_analysis_auto"):
        return jsonify({"status": "error", "message": "KOOLKID strategy not available"}), 400

    enabled = bool(strat.toggle_over3_analysis_auto())
    payload = {}
    try:
        payload = strat.get_ui_payload() or {}
    except Exception:
        payload = {}

    try:
        socketio.emit("auto_mode_update", (payload.get("auto_modes") or {}), room=cid)
        socketio.emit("digit_analysis", payload, room=cid)
    except Exception:
        pass

    return jsonify({
        "status": "success",
        "over3_analysis": enabled,
        "auto_modes": payload.get("auto_modes", {}),
        "over3_analysis_data": payload.get("over3_analysis_data", {}),
        "payload": payload,
    })


@app.route("/set_mpull_mode", methods=["POST"])
def set_mpull_mode_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    data = request.json or {}
    mode = (data.get("mode") or "BOTH")
    strat = state["strategies"].get("KOOLKID")
    mode_val = strat.set_mpull_mode(mode)

    return jsonify({"status": "success", "mpull_mode": mode_val})


@app.route("/set_kidpairs_trades", methods=["POST"])
def set_kidpairs_trades_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    data = request.json or {}
    trades = data.get("trades", 1)
    strat = state["strategies"].get("KOOLKID")
    trades_val = strat.set_kidpairs_trades_per_signal(trades)

    return jsonify({"status": "success", "kidpairs_trades_per_signal": trades_val})


@app.route("/set_kidracks_settings", methods=["POST"])
def set_kidracks_settings():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    data = request.json or {}
    barrier = int(data.get("barrier", 5))

    strat = state["strategies"].get("KOOLKID")
    strat.kidracks_barrier = barrier

    return jsonify({"status": "success"})


@app.route("/set_koolkidspeed_settings", methods=["POST"])
def set_koolkidspeed_settings():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    data = request.json or {}
    barrier = int(data.get("barrier", 5))

    strat = state["strategies"].get("KOOLKID")
    strat.koolkidspeed_barrier = barrier

    return jsonify({"status": "success"})


# ---------------- ADVANCED AI MODE ALIAS ROUTES (UI compatibility) ---------------- #
# These are lightweight aliases that map the "Advanced AI Modes" UI buttons
# (Kid Brain / Edge Brain / Smart Flow / Metral / Kidricks AI) to the existing KOOLKID
# auto-mode routes and strategy toggles.

def _toggle_koolkid_advanced_alias(cid, state, *, method_name, base_key, alias_key):
    """
    Robust alias toggle:
    1) Use the real KOOLKID strategy toggle method if it exists.
    2) Fallback to directly toggling the boolean attr if the method is missing.
    3) Never hard-fail the UI just because an older/newer strategy build renamed a helper.
    """
    strat = state.get("strategies", {}).get("KOOLKID")
    if not strat:
        return jsonify({"status": "error", "message": "KOOLKID strategy not available"}), 400

    state_val = None
    try:
        fn = getattr(strat, method_name, None)
        if callable(fn):
            state_val = fn()
        else:
            # Fallback for strategy builds where route exists but helper method name is missing.
            current = bool(getattr(strat, base_key, False))
            state_val = (not current)
            try:
                setattr(strat, base_key, bool(state_val))
            except Exception:
                # last-resort UI-only fallback (keeps button from failing even if strategy uses slots)
                alias_state = state.setdefault("advanced_ai_alias_modes", {})
                alias_state[base_key] = bool(state_val)
    except Exception as e:
        return jsonify({"status": "error", "message": f"Failed to toggle {alias_key}: {e}"}), 500

    # Build payload for auto_mode_update safely and include alias key(s) for UI compatibility
    emit_payload = {}
    try:
        if hasattr(strat, "get_ui_payload"):
            emit_payload = (strat.get_ui_payload() or {}).get("auto_modes", {}) or {}
    except Exception:
        emit_payload = {}

    # Ensure the base and alias keys are both present in emitted payload
    emit_payload = dict(emit_payload)
    if state_val is None:
        state_val = bool(emit_payload.get(base_key, False))
    emit_payload[base_key] = bool(state_val)
    emit_payload[alias_key] = bool(state_val)

    try:
        socketio.emit("auto_mode_update", emit_payload, room=cid)
    except Exception:
        pass

    return jsonify({"status": "success", alias_key: bool(state_val), base_key: bool(state_val)})


@app.route("/toggle_kidbrain_auto", methods=["GET", "POST"])
def toggle_kidbrain_auto_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    return _toggle_koolkid_advanced_alias(
        cid, state,
        method_name="toggle_kidracks_auto",
        base_key="kidracks_auto",
        alias_key="kidbrain_auto",
    )


@app.route("/toggle_edgebrain_auto", methods=["GET", "POST"])
def toggle_edgebrain_auto_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    return _toggle_koolkid_advanced_alias(
        cid, state,
        method_name="toggle_koolkidspeed_auto",
        base_key="koolkidspeed_auto",
        alias_key="edgebrain_auto",
    )


@app.route("/toggle_smartflow_auto", methods=["GET", "POST"])
def toggle_smartflow_auto_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    return _toggle_koolkid_advanced_alias(
        cid, state,
        method_name="toggle_koolluck_auto",
        base_key="koolluck_auto",
        alias_key="smartflow_auto",
    )


@app.route("/toggle_metral_auto", methods=["GET", "POST"])
def toggle_metral_auto_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    return _toggle_koolkid_advanced_alias(
        cid, state,
        method_name="toggle_kidbagz_auto",
        base_key="kidbagz_auto",
        alias_key="metral_auto",
    )


@app.route("/toggle_kidricks_ai_auto", methods=["GET", "POST"])
def toggle_kidricks_ai_auto_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    return _toggle_koolkid_advanced_alias(
        cid, state,
        method_name="toggle_mpull_auto",
        base_key="mpull_auto",
        alias_key="kidricks_ai_auto",
    )


@app.route("/set_kidbrain_settings", methods=["GET", "POST"])
def set_kidbrain_settings():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    data = request.get_json(silent=True) or request.form or {}
    barrier = int(data.get("barrier", 5))

    strat = state["strategies"].get("KOOLKID")
    if not strat:
        return jsonify({"status": "error", "message": "KOOLKID strategy not available"}), 400

    strat.kidracks_barrier = barrier
    return jsonify({"status": "success"})


@app.route("/set_edgebrain_settings", methods=["GET", "POST"])
def set_edgebrain_settings():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    data = request.get_json(silent=True) or request.form or {}
    barrier = int(data.get("barrier", 5))

    strat = state["strategies"].get("KOOLKID")
    if not strat:
        return jsonify({"status": "error", "message": "KOOLKID strategy not available"}), 400

    strat.koolkidspeed_barrier = barrier
    return jsonify({"status": "success"})


# ---------------- JOKERJOE toggles ---------------- #
@app.route("/toggle_sludgex_auto", methods=["POST"])
def toggle_sludgex_auto_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    strat = state["strategies"].get("JOKERJOE")
    if not strat or not hasattr(strat, "toggle_sludgex_auto"):
        return jsonify({"status": "error", "message": "JOKERJOE strategy not available"}), 400

    new_val = strat.toggle_sludgex_auto()
    send_stats_update(cid)

    emit_jokerjoe_modes(cid, strat)
    return jsonify({"status": "success", "sludgex_auto": new_val})


@app.route("/toggle_triplex_auto", methods=["POST"])
def toggle_triplex_auto_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    strat = state["strategies"].get("JOKERJOE")
    if not strat or not hasattr(strat, "toggle_triplex_auto"):
        return jsonify({"status": "error", "message": "JOKERJOE strategy not available"}), 400

    new_val = strat.toggle_triplex_auto()
    send_stats_update(cid)

    emit_jokerjoe_modes(cid, strat)
    return jsonify({"status": "success", "triplex_auto": new_val})


@app.route("/toggle_kidx_auto", methods=["POST"])
def toggle_kidx_auto_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    strat = state["strategies"].get("JOKERJOE")
    if not strat or not hasattr(strat, "toggle_kidx_auto"):
        return jsonify({"status": "error", "message": "JOKERJOE strategy not available"}), 400

    data = request.json or {}
    barrier = int(data.get("barrier", 5))

    new_val = strat.toggle_kidx_auto(barrier=barrier)
    send_stats_update(cid)

    emit_jokerjoe_modes(cid, strat)
    return jsonify({"status": "success", "kidx_auto": bool(new_val), "barrier": barrier})


@app.route("/toggle_multig_auto", methods=["POST"])
def toggle_multig_auto_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    strat = state["strategies"].get("JOKERJOE")
    if not strat or not hasattr(strat, "toggle_multig_auto"):
        return jsonify({"status": "error", "message": "JOKERJOE strategy not available"}), 400

    new_val = strat.toggle_multig_auto()
    send_stats_update(cid)

    emit_jokerjoe_modes(cid, strat)
    return jsonify({"status": "success", "multig_auto": bool(new_val)})


@app.route("/kidgamblex", methods=["POST"])
def kidgamblex_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    data = request.json or {}

    try:
        stake = float(data.get("stake", state.get("auto_stake", 1.0)))
        if stake <= 0:
            stake = 1.0
    except Exception:
        stake = 1.0

    symbol = data.get("symbol", state.get("current_symbol", "R_25"))

    strat = state["strategies"].get("JOKERJOE")
    if not strat or not hasattr(strat, "get_top_digits"):
        return jsonify({"status": "error", "message": "JOKERJOE strategy not available"}), 400

    digits = strat.get_top_digits(n=3)
    if not digits:
        return jsonify({"status": "error", "message": "Need 100 ticks before kidgambleX can select top digits."}), 400

    placed = 0
    for d in digits:
        ok, _msg = send_buy(cid, "MATCHES", stake, symbol, int(d))
        if ok:
            placed += 1
        time.sleep(0.12)

    return jsonify({"status": "success", "digits": digits, "placed": placed})




# ---------------- NEW FAST MODES / ANALYSIS ROUTES ---------------- #
@app.route("/toggle_kidgx_auto", methods=["POST"])
def toggle_kidgx_auto_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    data = request.json or {}
    profile = (data.get("profile") or state.get("active_profile") or "KOOLKID").upper().strip()
    if profile not in ("KOOLKID", "JOKERJOE"):
        return jsonify({"status": "error", "message": "Invalid profile"}), 400

    strat = state["strategies"].get(profile)
    if not strat or not hasattr(strat, "toggle_kidgx_auto"):
        return jsonify({"status": "error", "message": f"{profile} strategy not available"}), 400

    barrier = data.get("barrier", None)
    try:
        if profile == "JOKERJOE":
            new_val = strat.toggle_kidgx_auto(barrier=barrier)
            if barrier is not None and hasattr(strat, "set_kidgx_barrier"):
                strat.set_kidgx_barrier(barrier)
        else:
            new_val = strat.toggle_kidgx_auto()
    except TypeError:
        new_val = strat.toggle_kidgx_auto()

    try:
        socketio.emit("auto_mode_update", strat.get_ui_payload().get("auto_modes", {}), room=cid)
        socketio.emit("digit_analysis", strat.get_ui_payload(), room=cid)
    except Exception:
        pass
    if profile == "JOKERJOE":
        try:
            emit_jokerjoe_modes(cid, strat)
        except Exception:
            pass

    payload = {"status": "success", "profile": profile, "kidgx_auto": bool(new_val)}
    if profile == "JOKERJOE":
        payload["barrier"] = int(5 if getattr(strat, "kidgx_barrier", 5) is None else getattr(strat, "kidgx_barrier", 5))
    return jsonify(payload)


@app.route("/set_kidgx_barrier", methods=["POST"])
def set_kidgx_barrier_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    data = request.json or {}
    strat = state["strategies"].get("JOKERJOE")
    if not strat or not hasattr(strat, "set_kidgx_barrier"):
        return jsonify({"status": "error", "message": "JOKERJOE strategy not available"}), 400

    barrier = int(data.get("barrier", 5))
    b = strat.set_kidgx_barrier(barrier)
    try:
        socketio.emit("digit_analysis", strat.get_ui_payload(), room=cid)
        emit_jokerjoe_modes(cid, strat)
    except Exception:
        pass
    return jsonify({"status": "success", "barrier": int(b)})


@app.route("/toggle_barrier_analysis", methods=["POST"])
def toggle_barrier_analysis_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    strat = state["strategies"].get("KOOLKID")
    if not strat or not hasattr(strat, "toggle_barrier_analysis"):
        return jsonify({"status": "error", "message": "KOOLKID strategy not available"}), 400

    new_val = strat.toggle_barrier_analysis()
    payload = strat.get_ui_payload()
    socketio.emit("auto_mode_update", payload.get("auto_modes", {}), room=cid)
    socketio.emit("digit_analysis", payload, room=cid)
    return jsonify({"status": "success", "barrier_analysis": bool(new_val)})


@app.route("/select_barrier_analysis_barrier", methods=["POST"])
def select_barrier_analysis_barrier_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    data = request.json or {}
    key = data.get("key") or "UNDER 9"
    strat = state["strategies"].get("KOOLKID")
    if not strat or not hasattr(strat, "select_barrier_analysis_barrier"):
        return jsonify({"status": "error", "message": "KOOLKID strategy not available"}), 400

    selected = strat.select_barrier_analysis_barrier(key)
    payload = strat.get_ui_payload()
    socketio.emit("digit_analysis", payload, room=cid)
    return jsonify({"status": "success", "selected": selected})


@app.route("/toggle_ai_auto_trading", methods=["POST"])
def toggle_ai_auto_trading_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    data = request.json or {}
    profile = (data.get("profile") or state.get("active_profile") or "KOOLKID").upper().strip()
    if profile not in ("KOOLKID", "JOKERJOE"):
        return jsonify({"status": "error", "message": "Invalid profile"}), 400

    strat = state["strategies"].get(profile)
    if not strat or not hasattr(strat, "toggle_ai_auto_trading"):
        return jsonify({"status": "error", "message": f"{profile} strategy not available"}), 400

    new_val = strat.toggle_ai_auto_trading()
    try:
        socketio.emit("auto_mode_update", strat.get_ui_payload().get("auto_modes", {}), room=cid)
        socketio.emit("digit_analysis", strat.get_ui_payload(), room=cid)
        if profile == "JOKERJOE":
            emit_jokerjoe_modes(cid, strat)
    except Exception:
        pass
    return jsonify({"status": "success", "profile": profile, "ai_auto_trading": bool(new_val)})


@app.route("/toggle_mpull_all_digits_auto", methods=["POST"])
def toggle_mpull_all_digits_auto_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    strat = state["strategies"].get("KOOLKID")
    if not strat or not hasattr(strat, "toggle_mpull_all_digits_auto"):
        return jsonify({"status": "error", "message": "KOOLKID strategy not available"}), 400

    new_val = strat.toggle_mpull_all_digits_auto()
    payload = strat.get_ui_payload()
    socketio.emit("auto_mode_update", payload.get("auto_modes", {}), room=cid)
    socketio.emit("digit_analysis", payload, room=cid)
    return jsonify({"status": "success", "mpull_all_digits_auto": bool(new_val)})


@app.route("/set_mpull_all_digits_selection", methods=["POST"])
def set_mpull_all_digits_selection_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    data = request.json or {}
    digits = data.get("digits") or []
    strat = state["strategies"].get("KOOLKID")
    if not strat or not hasattr(strat, "set_mpull_all_digits_selected_digits"):
        return jsonify({"status": "error", "message": "KOOLKID strategy not available"}), 400

    vals = strat.set_mpull_all_digits_selected_digits(digits)
    payload = strat.get_ui_payload()
    socketio.emit("digit_analysis", payload, room=cid)
    return jsonify({"status": "success", "digits": vals})

@app.route("/insta5", methods=["POST"])
def insta5_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    data = request.json or {}

    contract_type = "DIFFERS"
    try:
        stake = float(data.get("stake", state.get("auto_stake", 1.0)))
        if stake <= 0:
            stake = 1.0
    except Exception:
        stake = 1.0

    symbol = data.get("symbol", state.get("current_symbol", "R_25"))
    barrier = int(data.get("barrier", 5))

    placed = 0
    for _ in range(5):
        ok, _msg = send_buy(cid, contract_type, stake, symbol, barrier)
        if ok:
            placed += 1
        time.sleep(0.06)

    return jsonify({"status": "success", "placed": placed, "barrier": barrier})


@app.route("/manual_trade", methods=["POST"])
def manual_trade():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    data = request.json or {}

    contract_type = data.get("type")
    stake = float(data.get("stake", 1))
    symbol = data.get("symbol", state.get("current_symbol", "R_25"))
    barrier = int(data.get("barrier", 5))

    ok, msg = send_buy(cid, contract_type, stake, symbol, barrier)
    return jsonify({"status": "success" if ok else "error", "message": msg})


@app.route("/manual_3_trades", methods=["POST"])
def manual_3_trades():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    data = request.json or {}

    contract_type = data.get("type")
    stake = float(data.get("stake", 1))
    symbol = data.get("symbol", state.get("current_symbol", "R_25"))
    barrier = int(data.get("barrier", 5))

    placed = 0
    for _ in range(3):
        ok, _msg = send_buy(cid, contract_type, stake, symbol, barrier)
        if ok:
            placed += 1
        time.sleep(0.15)

    return jsonify({"status": "success", "placed": placed})


@app.route("/burst_4", methods=["POST"])
def burst_4():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    data = request.json or {}

    contract_type = data.get("type")
    stake = float(data.get("stake", 1))
    symbol = data.get("symbol", state.get("current_symbol", "R_25"))
    barrier = int(data.get("barrier", 5))

    placed = 0
    for _ in range(4):
        ok, _msg = send_buy(cid, contract_type, stake, symbol, barrier)
        if ok:
            placed += 1
        time.sleep(0.10)

    return jsonify({"status": "success", "placed": placed})



@app.route("/unchain_status", methods=["GET"])
def unchain_status_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403
    _cid, state = get_client_state()
    _ensure_tick_subscription(state, state.get("current_symbol"))
    return jsonify(_unchain_payload_response(state))


@app.route("/unchain_scanner", methods=["GET"])
def unchain_scanner_status_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403
    _cid, state = get_client_state()
    return jsonify(_get_unchain_scanner_payload(state))


@app.route("/unchain_scanner/start", methods=["POST"])
def unchain_scanner_start_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403
    cid, state = get_client_state()
    data = request.json or {}
    symbols = data.get("symbols")
    ok, msg, payload = _start_unchain_scanner(cid, state, symbols)
    status = "success" if ok else "error"
    if state.get("active_profile") == "UNCHAIN":
        socketio.emit("unchain_scanner", payload, room=cid)
        socketio.emit("unchain_status", _unchain_payload_response(state), room=cid)
    return jsonify({"status": status, "message": msg, "scanner": payload})


@app.route("/unchain_scanner/stop", methods=["POST"])
def unchain_scanner_stop_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403
    cid, state = get_client_state()
    payload = _stop_unchain_scanner(cid, state)
    if state.get("active_profile") == "UNCHAIN":
        socketio.emit("unchain_scanner", payload, room=cid)
        socketio.emit("unchain_status", _unchain_payload_response(state), room=cid)
    return jsonify({"status": "success", "scanner": payload})


@app.route("/unchain_scanner/apply", methods=["POST"])
def unchain_scanner_apply_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403
    cid, state = get_client_state()
    data = request.json or {}
    symbol = data.get("symbol")
    switch_symbol = bool(data.get("switch_symbol", True))
    ok, msg, payload = _apply_scanner_recommendation(cid, state, symbol, switch_symbol=switch_symbol)
    if state.get("active_profile") == "UNCHAIN":
        socketio.emit("unchain_status", payload, room=cid)
    return jsonify({"status": "success" if ok else "error", "message": msg, "payload": payload}), (200 if ok else 400)


@app.route("/unchain_settings", methods=["POST"])
def unchain_settings_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403
    cid, state = get_client_state()
    u = _ensure_unchain_hl_state(state)
    data = request.json or {}
    try:
        if "higher_stake" in data:
            u["higher_stake"] = max(0.35, float(data.get("higher_stake") or 0.35))
            if "lower_stake" not in data:
                u["lower_stake"] = u["higher_stake"]
        if "lower_stake" in data:
            u["lower_stake"] = max(0.35, float(data.get("lower_stake") or 0.35))
        if "higher_barrier" in data:
            u["higher_barrier"] = str(data.get("higher_barrier") or "0.12").strip()
        if "lower_barrier" in data:
            u["lower_barrier"] = str(data.get("lower_barrier") or "-0.12").strip()
        if "duration" in data:
            u["duration"] = max(1, min(999, int(data.get("duration") or 1)))
        if "duration_unit" in data:
            u["duration_unit"] = _clean_unchain_duration_unit(data.get("duration_unit"))
        if "tp" in data:
            u["tp"] = max(0.0, float(data.get("tp") or 0))
        if "sl" in data:
            u["sl"] = max(0.0, float(data.get("sl") or 0))
        if "auto_sl" in data:
            u["auto_sl"] = bool(data.get("auto_sl"))
        if "auto_start_threshold" in data:
            u["auto_start_threshold"] = max(55.0, min(80.0, float(data.get("auto_start_threshold") or 60.0)))
        if "auto_min_movement" in data:
            u["auto_min_movement"] = max(0.00001, float(data.get("auto_min_movement") or 0.12))
        if "auto_min_tick_speed" in data:
            u["auto_min_tick_speed"] = max(0.05, min(10.0, float(data.get("auto_min_tick_speed") or 1.5)))
        if "auto_min_range" in data:
            u["auto_min_range"] = max(0.00001, float(data.get("auto_min_range") or 0.2))
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    u["last_action"] = "UNCHAIN settings saved"
    _check_unchain_hl_risk_block(state)
    payload = _unchain_payload_response(state)
    if state.get("active_profile") == "UNCHAIN":
        socketio.emit("unchain_status", payload, room=cid)
        socketio.emit("digit_analysis", payload, room=cid)
        send_stats_update(cid)
    return jsonify(payload)


@app.route("/unchain_trade", methods=["POST"])
def unchain_trade_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403
    cid, state = get_client_state()
    u = _ensure_unchain_hl_state(state)
    data = request.json or {}
    side = str(data.get("side") or "").upper()
    symbol = data.get("symbol") or state.get("current_symbol", "R_25")
    duration = data.get("duration", u.get("duration", 5))
    duration_unit = data.get("duration_unit", u.get("duration_unit", "t"))
    plan = []
    if side == "HIGHER":
        plan.append(("HIGHER", data.get("higher_stake", u.get("higher_stake", 1.0)), data.get("higher_barrier", u.get("higher_barrier", "0.12"))))
    elif side == "LOWER":
        plan.append(("LOWER", data.get("lower_stake", u.get("lower_stake", 1.0)), data.get("lower_barrier", u.get("lower_barrier", "-0.12"))))
    elif side == "BOTH":
        plan.append(("HIGHER", data.get("higher_stake", u.get("higher_stake", 1.0)), data.get("higher_barrier", u.get("higher_barrier", "0.12"))))
        plan.append(("LOWER", data.get("lower_stake", u.get("lower_stake", 1.0)), data.get("lower_barrier", u.get("lower_barrier", "-0.12"))))
    else:
        return jsonify({"status": "error", "message": "Invalid side. Use HIGHER, LOWER, or BOTH.", "payload": _unchain_payload_response(state)}), 400
    placed = []
    for trade_side, stake, barrier in plan:
        ok, msg = _send_unchain_hl_trade(
            cid,
            side=trade_side,
            stake=stake,
            symbol=symbol,
            barrier=barrier,
            duration=duration,
            duration_unit=duration_unit,
        )
        if not ok:
            payload = _unchain_payload_response(state)
            if state.get("active_profile") == "UNCHAIN":
                socketio.emit("unchain_status", payload, room=cid)
            return jsonify({"status": "error", "message": msg, "payload": payload, "placed": placed}), 400
        placed.append(trade_side)
    u["last_action"] = f"Sent {' + '.join(placed)} on {symbol}"
    payload = _unchain_payload_response(state)
    if state.get("active_profile") == "UNCHAIN":
        socketio.emit("unchain_status", payload, room=cid)
    return jsonify({"status": "success", "message": f"Sent {' + '.join(placed)}", "payload": payload, "placed": placed})


@app.route("/toggle_unchain_auto", methods=["POST"])
def toggle_unchain_auto_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403
    cid, state = get_client_state()
    u = _ensure_unchain_hl_state(state)
    data = request.json or {}
    requested = data.get("enabled")
    if requested is None:
        u["auto_both_enabled"] = not bool(u.get("auto_both_enabled"))
    else:
        u["auto_both_enabled"] = bool(requested)

    u["auto_both_cooldown"] = 3
    active_count = len(_get_open_unchain_active_entries(state))
    if u["auto_both_enabled"]:
        u["auto_wait_for_reset"] = False
        if active_count > 0:
            u["auto_pair_active"] = True
            u["auto_next_fire_at"] = 0.0
            u["last_action"] = "AUTO BOTH armed • waiting for current auto trade to finish"
        else:
            u["auto_pair_active"] = False
            u["auto_next_fire_at"] = time.time()
            gate = _get_unchain_auto_gate(state, u)
            if gate.get("ready"):
                u["last_action"] = "AUTO BOTH armed"
            else:
                threshold = float(gate.get("threshold", 60.0) or 60.0)
                market_confidence = float(gate.get("market_confidence", 0.0) or 0.0)
                u["last_action"] = f"AUTO BOTH armed • waiting for {threshold:.0f}% confidence (now {market_confidence:.0f}%)"
        _run_unchain_auto_both(cid, state)
        message = "UNCHAIN AUTO BOTH ON"
    else:
        u["auto_pair_active"] = False
        u["auto_wait_for_reset"] = False
        u["auto_next_fire_at"] = 0.0
        u["last_action"] = "AUTO BOTH OFF"
        message = "UNCHAIN AUTO BOTH OFF"

    payload = _unchain_payload_response(state)
    if state.get("active_profile") == "UNCHAIN":
        socketio.emit("unchain_status", payload, room=cid)
    return jsonify({
        "status": "success",
        "message": message,
        "auto_enabled": bool(u.get("auto_both_enabled")),
        "payload": payload,
    })


@app.route("/unchain_stop", methods=["POST"])
def unchain_stop_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403
    cid, state = get_client_state()
    u = _ensure_unchain_hl_state(state)
    u["auto_both_enabled"] = False
    u["auto_pair_active"] = False
    u["auto_next_fire_at"] = 0.0
    active_ids = list((u.get("active_contracts") or {}).keys())
    closed = []
    failed = []
    for contract_id in active_ids:
        ok, msg = _request_sell_contract(cid, contract_id)
        if ok:
            closed.append(str(contract_id))
        else:
            failed.append({"contract_id": str(contract_id), "error": msg})
    if closed:
        u["last_action"] = f"Close requested for {len(closed)} UNCHAIN trade(s)"
    elif failed:
        u["last_action"] = "Close request failed"
    else:
        u["last_action"] = "No active UNCHAIN trades"
    payload = _unchain_payload_response(state)
    if state.get("active_profile") == "UNCHAIN":
        socketio.emit("unchain_status", payload, room=cid)
        socketio.emit("digit_analysis", payload, room=cid)
    send_stats_update(cid)
    return jsonify({
        "status": "success" if closed or not failed else "error",
        "message": f"Close requested for {len(closed)} trade(s)" if closed else ("No active UNCHAIN trades" if not failed else "Some close requests failed"),
        "closed": closed,
        "failed": failed,
        "payload": payload,
    })


@app.route("/unchain_manual_enter", methods=["POST"])
def unchain_manual_enter_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403
    cid, state = get_client_state()
    data = request.json or {}
    side = str(data.get("side") or "HIGHER").upper()
    u = _ensure_unchain_hl_state(state)
    if side not in ("HIGHER", "LOWER"):
        side = "HIGHER"
    ok, msg = _send_unchain_hl_trade(
        cid,
        side=side,
        stake=data.get("stake", u.get("higher_stake" if side == "HIGHER" else "lower_stake", 1.0)),
        symbol=state.get("current_symbol", "R_25"),
        barrier=data.get("barrier", u.get("higher_barrier" if side == "HIGHER" else "lower_barrier", "0.12" if side == "HIGHER" else "-0.12")),
        duration=data.get("duration", u.get("duration", 5)),
        duration_unit=data.get("duration_unit", u.get("duration_unit", "t")),
    )
    payload = _unchain_payload_response(state)
    if state.get("active_profile") == "UNCHAIN":
        socketio.emit("unchain_status", payload, room=cid)
    if ok:
        return jsonify({"status": "success", "message": f"UNCHAIN {side} entry sent", "payload": payload})
    return jsonify({"status": "error", "message": msg, "payload": payload}), 400


@app.route("/unchain_close_now", methods=["POST"])
def unchain_close_now_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403
    cid, state = get_client_state()
    u = _ensure_unchain_hl_state(state)
    active_ids = list((u.get("active_contracts") or {}).keys())
    if not active_ids:
        return jsonify({"status": "error", "message": "No active UNCHAIN trade", "payload": _unchain_payload_response(state)}), 400
    closed = []
    failed = []
    for contract_id in active_ids:
        ok, msg = _request_sell_contract(cid, contract_id)
        if ok:
            closed.append(str(contract_id))
        else:
            failed.append({"contract_id": str(contract_id), "error": msg})
    if closed:
        u["last_action"] = f"Sell requested for {len(closed)} UNCHAIN trade(s)"
    payload = _unchain_payload_response(state)
    if state.get("active_profile") == "UNCHAIN":
        socketio.emit("unchain_status", payload, room=cid)
        socketio.emit("digit_analysis", payload, room=cid)
    return jsonify({
        "status": "success" if closed else "error",
        "message": f"Sell request sent for {len(closed)} trade(s)" if closed else (failed[0]["error"] if failed else "No active UNCHAIN trade"),
        "closed": closed,
        "failed": failed,
        "payload": payload,
    }), (200 if closed else 500)


@app.route("/unchain_clear_active", methods=["POST"])
def unchain_clear_active_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403
    cid, state = get_client_state()
    u = _ensure_unchain_hl_state(state)
    active_ids = list((u.get("active_contracts") or {}).keys())
    cleared = []
    if active_ids:
        for contract_id in active_ids:
            cleared.append(str(contract_id))
            try:
                _mark_unchain_contract_processed(state, contract_id)
            except Exception:
                pass
            try:
                _pull_contract_meta(state, contract_id)
            except Exception:
                pass
        u["active_contracts"] = {}
        u["auto_pair_active"] = False
        u["last_action"] = f"Manually cleared {len(cleared)} UNCHAIN trade(s)"
    else:
        u["last_action"] = "No active UNCHAIN trades to clear"
    payload = _unchain_payload_response(state)
    if state.get("active_profile") == "UNCHAIN":
        socketio.emit("unchain_status", payload, room=cid)
        socketio.emit("digit_analysis", payload, room=cid)
    return jsonify({
        "status": "success",
        "message": u.get("last_action"),
        "cleared": cleared,
        "payload": payload,
    })


@app.route("/human_rf_status", methods=["GET"])
def human_rf_status_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    strat = state.get("strategies", {}).get("HUMAN")
    if not strat or not hasattr(strat, "get_human_rf_payload"):
        return jsonify({"error": "Human strategy not loaded"}), 400

    payload = strat.get_human_rf_payload()
    payload["human_symbol"] = state.get("human_symbol") or state.get("current_symbol")
    payload["main_symbol"] = state.get("current_symbol")
    payload["active_profile"] = state.get("active_profile")
    payload["ws_connected"] = bool(state.get("ws_connected"))
    return jsonify(payload)


@app.route("/human_rf_settings", methods=["POST"])
def human_rf_settings_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    _cid, state = get_client_state()
    strat = state.get("strategies", {}).get("HUMAN")
    if not strat or not hasattr(strat, "set_human_rf_settings"):
        return jsonify({"error": "Human strategy not loaded"}), 400

    data = request.json or {}
    # Accept partial updates
    kwargs = {
        "smart_assist": data.get("smart_assist"),
        "auto_assist": data.get("auto_assist"),
        "bias_lock": data.get("bias_lock"),
        "no_trade_filter": data.get("no_trade_filter"),
        "adaptive_cooldown": data.get("adaptive_cooldown"),
        "duration_ticks": data.get("duration_ticks"),
        "conf_threshold": data.get("conf_threshold"),
    }
    payload = strat.set_human_rf_settings(**kwargs)
    return jsonify({"status": "success", "rise_fall": payload})


@app.route("/human_rf_trade", methods=["POST"])
def human_rf_trade():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    strat = state.get("strategies", {}).get("HUMAN")
    if not strat or not hasattr(strat, "build_human_rf_trade_signal"):
        return jsonify({"error": "Human strategy not loaded"}), 400

    data = request.json or {}
    direction = (data.get("direction") or "AUTO").upper().strip()

    # sync stake from request if provided (optional)
    try:
        if data.get("stake") is not None:
            strat.stake = float(data.get("stake"))
    except Exception:
        pass
    try:
        if data.get("duration_ticks") is not None and hasattr(strat, "set_human_rf_settings"):
            strat.set_human_rf_settings(duration_ticks=int(data.get("duration_ticks")))
    except Exception:
        pass

    if direction == "AUTO":
        sig = strat.build_human_rf_trade_signal(force_direction=None, require_threshold=True)
    elif direction in ("RISE", "FALL"):
        sig = strat.build_human_rf_trade_signal(force_direction=direction, require_threshold=False)
    else:
        return jsonify({"error": "Invalid direction"}), 400

    if not sig:
        return jsonify({"error": "No valid setup / cooldown active"}), 400

    sig["symbol"] = state.get("human_symbol") or state.get("current_symbol")
    ok, msg = place_risefall_order(cid, sig)
    if ok:
        return jsonify({"status": "success", "signal": sig})
    return jsonify({"error": msg}), 500


@app.route("/human_formula_x", methods=["POST"])
def human_formula_x_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    strat = state.get("strategies", {}).get("HUMAN")
    if not strat:
        return jsonify({"error": "Human strategy not loaded"}), 400

    data = request.json or {}
    rise_stake = max(0.35, float(data.get("rise_stake") or 0))
    fall_stake = max(0.35, float(data.get("fall_stake") or 0))
    duration_ticks = int(data.get("duration_ticks") or getattr(strat, "rf_duration_ticks", 5) or 5)

    symbol = state.get("human_symbol") or state.get("current_symbol")
    signals = [
        {"direction": "RISE", "stake": rise_stake, "duration": duration_ticks, "symbol": symbol},
        {"direction": "FALL", "stake": fall_stake, "duration": duration_ticks, "symbol": symbol},
    ]

    results = []
    for sig in signals:
        ok, msg = place_risefall_order(cid, sig)
        results.append((ok, msg))

    payload = strat.get_human_rf_payload()
    if state.get("active_profile") == "HUMAN":
        socketio.emit("human_rf_status", payload, room=cid)

    rise_ok, rise_msg = results[0]
    fall_ok, fall_msg = results[1]
    status = "success" if (rise_ok and fall_ok) else ("partial" if (rise_ok or fall_ok) else "error")
    message = "FormulaX sent both trades" if status == "success" else (rise_msg or fall_msg or "FormulaX failed")
    return jsonify({
        "status": status,
        "message": message,
        "payload": payload,
        "rise_ok": rise_ok,
        "fall_ok": fall_ok,
    }), (200 if status in ("success", "partial") else 500)


# ==================== PATCH 1F: SeqVIX endpoints ====================
@app.route("/start_seqvix_jokerjoe", methods=["POST"])
def start_seqvix_jokerjoe_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    if not state.get("ws_connected") or not state.get("ws"):
        return jsonify({"error": "Not connected"}), 400

    data = request.json or {}
    mode = data.get("mode", "5")
    trade_count = data.get("trade_count", 2)   # ==================== PATCH 1G ====================
    start_seqvix_jokerjoe(state, cid, mode, trades_per_market=trade_count)
    return jsonify({"status": "success"})

@app.route("/stop_seqvix_jokerjoe", methods=["POST"])
def stop_seqvix_jokerjoe_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    stop_seqvix(state, cid, "JOKERJOE", reason="stopped")
    return jsonify({"status": "success"})

@app.route("/start_seqvix_koolkid", methods=["POST"])
def start_seqvix_koolkid_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    if not state.get("ws_connected") or not state.get("ws"):
        return jsonify({"error": "Not connected"}), 400

    data = request.json or {}
    contract_type = data.get("contract_type", "OVER")
    barrier = data.get("barrier", 1)
    trade_count = data.get("trade_count", 2)   # ==================== PATCH 1G ====================
    start_seqvix_koolkid(state, cid, contract_type, barrier, trades_per_market=trade_count)
    return jsonify({"status": "success"})

@app.route("/stop_seqvix_koolkid", methods=["POST"])
def stop_seqvix_koolkid_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    stop_seqvix(state, cid, "KOOLKID", reason="stopped")
    return jsonify({"status": "success"})

@app.route("/seqvix_status", methods=["GET"])
def seqvix_status_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    out = {}
    for p in ("KOOLKID", "JOKERJOE"):
        run = (state.get("seqvix") or {}).get(p) or {}
        out[p] = {
            "running": bool(run.get("running")),
            "done": int(run.get("done", 0)),
            "total": (None if run.get("endless") else int(run.get("total", 0))),
        }
    return jsonify(out)


# ---------------- KEEP-ALIVE ENDPOINTS (HUMAN ONLY) ---------------- #
@app.route("/human_keep_alive_status", methods=["GET"])
def human_keep_alive_status():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    _cid, state = get_client_state()
    return jsonify({"enabled": bool(state.get("human_keep_alive", False))})


@app.route("/toggle_human_keep_alive", methods=["POST"])
def toggle_human_keep_alive():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    _cid, state = get_client_state()
    state["human_keep_alive"] = not bool(state.get("human_keep_alive", False))
    return jsonify({"enabled": bool(state["human_keep_alive"])})


# ---------------- HEARTBEAT SWEEPER ---------------- #
def heartbeat_sweeper():
    while True:
        time.sleep(30)
        # Heartbeat checks disabled to prevent unintended disconnects.
        continue


@app.route("/toggle_named_ai_mode", methods=["POST"])
def toggle_named_ai_mode_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    data = request.json or {}
    profile = (data.get("profile") or state.get("active_profile") or "KOOLKID").upper().strip()
    mode_key = str(data.get("mode_key") or "").strip().lower()

    if profile not in ("KOOLKID", "JOKERJOE"):
        return jsonify({"status": "error", "message": "Invalid profile"}), 400

    strat = state["strategies"].get(profile)
    if not strat or not hasattr(strat, "toggle_named_ai_mode"):
        return jsonify({"status": "error", "message": f"{profile} strategy not available"}), 400

    try:
        enabled = bool(strat.toggle_named_ai_mode(mode_key))
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

    try:
        payload = strat.get_ui_payload()
    except Exception:
        payload = {}
    auto_modes = {}
    try:
        auto_modes = (payload or {}).get("auto_modes", {}) or {}
    except Exception:
        auto_modes = {}

    try:
        socketio.emit("auto_mode_update", auto_modes, room=cid)
        socketio.emit("digit_analysis", payload, room=cid)
        if profile == "JOKERJOE":
            emit_jokerjoe_modes(cid, strat)
    except Exception:
        pass

    return jsonify({
        "status": "success",
        "profile": profile,
        "mode_key": mode_key,
        "enabled": enabled,
        "auto_modes": auto_modes,
        "payload": payload,
    })

threading.Thread(target=heartbeat_sweeper, daemon=True).start()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    print("""
╔══════════════════════════════════════════════════════════════╗
║     🚀 KOOLKID AI BOT SERVER (TRUE MULTI-USER MODE)          ║
║     - Per-session client_id                                  ║
║     - Separate WS + state per browser/device                 ║
║     - KOOLKID / JOKERJOE / HUMAN                             ║
║     - ✅ HUMAN price feed fixed                              ║
║     - ✅ all profiles collect data in background              ║
║     - ✅ refresh/close forced disconnect + 10min timeout      ║
╚══════════════════════════════════════════════════════════════╝
    """)

    socketio.run(app, host="0.0.0.0", port=port, debug=True, allow_unsafe_werkzeug=True)
