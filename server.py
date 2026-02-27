import os, sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import json
import threading
import websocket
import time
import uuid
import sqlite3
import random  # PATCH 1A
import re
from collections import deque
from decimal import Decimal, InvalidOperation

from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_socketio import SocketIO, join_room
from datetime import datetime
import logging
from werkzeug.security import generate_password_hash, check_password_hash

# STRATEGIES
from strategies.koolkid import KoolKidStrategy
from strategies.jokerjoe import JokerJoeStrategy
from strategies.human import HumanStrategy

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
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading", manage_session=False)

DERIV_WS = "wss://ws.derivws.com/websockets/v3?app_id=1089"

# DATABASE FILE
DB_FILE = "users.db"

# ==========================
# MULTI-CLIENT STATE
# ==========================
clients = {}

# heartbeat timeout (10 minutes)
HEARTBEAT_TIMEOUT_SEC = 10 * 60

# ==========================
# EXECUTION HARDENING (FAST MODES)
# ==========================
TRADE_QUEUE_MIN_GAP_SEC = float(os.environ.get("TRADE_QUEUE_MIN_GAP_SEC", "0.12"))
TRADE_BACKOFF_SEC = float(os.environ.get("TRADE_BACKOFF_SEC", "1.0"))
TRADE_DUP_WINDOW_SEC = float(os.environ.get("TRADE_DUP_WINDOW_SEC", "0.10"))
MAX_TRADE_QUEUE_SIZE = int(os.environ.get("MAX_TRADE_QUEUE_SIZE", "300"))
MAX_INFLIGHT_PER_PROFILE = int(os.environ.get("MAX_INFLIGHT_PER_PROFILE", "8"))
MAX_INFLIGHT_PER_MARKET = int(os.environ.get("MAX_INFLIGHT_PER_MARKET", "3"))

# User requested instant burst execution (no server-side queue pacing/caps).
USE_TRADE_QUEUE = str(os.environ.get("USE_TRADE_QUEUE", "0")).strip().lower() in ("1", "true", "yes", "on")
ENFORCE_TRADE_INFLIGHT_LIMITS = str(os.environ.get("ENFORCE_TRADE_INFLIGHT_LIMITS", "0")).strip().lower() in ("1", "true", "yes", "on")


# ---------------- DATABASE SETUP ---------------- #
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


def ensure_admin_user():
    """
    Auto-create admin so you never get locked out.
    """
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("SELECT id FROM users WHERE username = ?", (ADMIN_USERNAME,))
    exists = c.fetchone()

    if not exists:
        hashed_pw = generate_password_hash(ADMIN_PASSWORD)
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (ADMIN_USERNAME, hashed_pw))
        conn.commit()
        print(f"✅ Admin account created automatically: {ADMIN_USERNAME}")

    conn.close()


def get_user_count():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    count = c.fetchone()[0]
    conn.close()
    return count


def create_user(username, password):
    if username.lower() == ADMIN_USERNAME.lower():
        return False, "Username is reserved"

    if get_user_count() >= MAX_USERS:
        return False, f"User limit reached ({MAX_USERS} max)"

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    hashed_pw = generate_password_hash(password)

    try:
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_pw))
        conn.commit()
        return True, "User created"
    except sqlite3.IntegrityError:
        return False, "Username already exists"
    finally:
        conn.close()


def verify_user(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("SELECT password FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()

    if not row:
        return False

    return check_password_hash(row[0], password)


# Initialize DB + Admin
init_db()
ensure_admin_user()


# ---------------- HELPERS ---------------- #
def now_time():
    return datetime.now().strftime("%H:%M:%S")


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _normalize_price_string(value):
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    return s.replace(",", "")


def _infer_pip_size_from_text(value):
    s = _normalize_price_string(value)
    if not s:
        return None
    if "." not in s:
        return 0
    dec = s.split(".", 1)[1]
    dec_digits = "".join(ch for ch in dec if ch.isdigit())
    return len(dec_digits)


def _cache_symbol_pip_from_active_symbols(state, items):
    """Cache symbol precision from active_symbols payload (best long-term source)."""
    try:
        if not state:
            return
        cache = state.setdefault("symbol_pip_sizes", {})
        if not isinstance(items, list):
            return
        for it in items:
            if not isinstance(it, dict):
                continue
            sym = it.get("symbol")
            if not sym:
                continue
            raw = it.get("pip_size")
            if raw in (None, ""):
                raw = it.get("pip")
            if raw in (None, ""):
                raw = it.get("display_precision")
            if raw in (None, ""):
                continue
            pip = _safe_int(raw, None)
            if pip is None or pip < 0:
                continue
            cache[str(sym)] = int(pip)
    except Exception:
        pass


def _enrich_tick_with_raw_quote_fields(raw_message, tick):
    """Preserve exact quote text from raw websocket JSON to avoid any float/parsing ambiguity."""
    try:
        if not isinstance(tick, dict) or not isinstance(raw_message, str):
            return
        # Only inspect the tick object portion to avoid matching other payload sections.
        m_tick = re.search(r'"tick"\s*:\s*\{(.*?)\}\s*(?:,|$)', raw_message, re.DOTALL)
        if not m_tick:
            return
        body = m_tick.group(1)

        m_quote = re.search(r'"quote"\s*:\s*([^,}]+)', body)
        if m_quote:
            qraw = m_quote.group(1).strip()
            # strip JSON string quotes if present
            if len(qraw) >= 2 and qraw[0] == '"' and qraw[-1] == '"':
                qraw = qraw[1:-1]
            tick["_quote_raw_text"] = qraw

        m_pip = re.search(r'"pip_size"\s*:\s*([^,}]+)', body)
        if m_pip:
            praw = m_pip.group(1).strip()
            if len(praw) >= 2 and praw[0] == '"' and praw[-1] == '"':
                praw = praw[1:-1]
            tick["_pip_size_raw_text"] = praw
    except Exception:
        pass


def resolve_tick_pip_size(state, tick, default=2):
    """Resolve pip_size robustly for a tick and cache it per symbol."""
    try:
        sym = (tick or {}).get("symbol")
    except Exception:
        sym = None

    cache = {}
    try:
        if state is not None:
            cache = state.setdefault("symbol_pip_sizes", {})
    except Exception:
        cache = {}

    # 1) Explicit pip_size from raw tick payload (preserves exact text if present)
    raw_pip = None
    try:
        raw_pip = (tick or {}).get("_pip_size_raw_text")
    except Exception:
        raw_pip = None
    if raw_pip in (None, ""):
        try:
            raw_pip = (tick or {}).get("pip_size")
        except Exception:
            raw_pip = None

    if raw_pip not in (None, ""):
        pip = _safe_int(raw_pip, default)
        if pip < 0:
            pip = _safe_int(default, 2)
        if sym:
            cache[sym] = pip
        return pip

    # 2) Trusted cached per-symbol precision (e.g., active_symbols metadata)
    if sym and sym in cache:
        return _safe_int(cache.get(sym), default)

    # 3) Infer from display/quote text if present (fallback only)
    inferred = None
    for key in ("quote_display_value", "_quote_raw_text", "quote"):
        try:
            inferred = _infer_pip_size_from_text((tick or {}).get(key))
        except Exception:
            inferred = None
        if inferred is not None:
            break

    if inferred is not None and inferred >= 0:
        if sym:
            prev = cache.get(sym)
            cache[sym] = max(int(prev), int(inferred)) if prev is not None else int(inferred)
            return cache[sym]
        return int(inferred)

    return _safe_int(default, 2)


def extract_last_decimal_digit(price, pip_size=2):
    try:
        pip = _safe_int(pip_size, 2)
        if pip < 0:
            pip = 2

        s = _normalize_price_string(price)
        if not s:
            return 0

        # Avoid float(...) so we don't lose/round the true last digit.
        d = Decimal(s)
        if pip > 0:
            q = Decimal("1").scaleb(-pip)  # 10^-pip
            s = format(d.quantize(q), f".{pip}f")
        else:
            s = format(d.quantize(Decimal("1")), "f")

        if "." not in s:
            digits = "".join(ch for ch in s if ch.isdigit())
            return int(digits[-1]) if digits else 0

        dec_digits = "".join(ch for ch in s.split(".", 1)[1] if ch.isdigit())

        if pip > 0:
            dec_digits = dec_digits.ljust(pip, "0")
            return int(dec_digits[pip - 1]) if len(dec_digits) >= pip else 0

        int_digits = "".join(ch for ch in s.split(".", 1)[0] if ch.isdigit())
        return int(int_digits[-1]) if int_digits else 0
    except (InvalidOperation, ValueError):
        return 0
    except Exception:
        return 0


def extract_last_digit_from_tick(state, tick, default_pip=2):
    """Return (digit, pip_size_used) from a Deriv tick payload."""
    try:
        pip = resolve_tick_pip_size(state, tick, default=default_pip)
        price_for_digit = None
        if isinstance(tick, dict):
            price_for_digit = tick.get("_quote_raw_text")
            if price_for_digit in (None, ""):
                price_for_digit = tick.get("quote_display_value")
            if price_for_digit in (None, ""):
                price_for_digit = tick.get("quote")
        digit = extract_last_decimal_digit(price_for_digit, pip)
        return digit, pip
    except Exception:
        return 0, _safe_int(default_pip, 2)


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
    return "user" in session


def is_admin():
    return session.get("user", "").lower() == ADMIN_USERNAME.lower()


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


def _ws_send_json(state, payload):
    """Thread-safe WebSocket send helper."""
    ws = state.get("ws") if state else None
    if not ws:
        return False
    lock = state.get("ws_send_lock")
    try:
        if lock:
            with lock:
                ws.send(json.dumps(payload))
        else:
            ws.send(json.dumps(payload))
        return True
    except Exception:
        return False


def _trade_slot_key_market(profile, symbol):
    return f"{str(profile).upper()}::{symbol}"


def _reserve_trade_slot(state, profile, symbol):
    profile = str(profile or "KOOLKID").upper()
    symbol = str(symbol or "")
    profile_counts = state.setdefault("trade_slots_profile", {})
    market_counts = state.setdefault("trade_slots_market", {})
    p_count = int(profile_counts.get(profile, 0))
    m_key = _trade_slot_key_market(profile, symbol)
    m_count = int(market_counts.get(m_key, 0))

    if ENFORCE_TRADE_INFLIGHT_LIMITS:
        if p_count >= MAX_INFLIGHT_PER_PROFILE:
            return False, f"{profile} in-flight limit reached"
        if m_count >= MAX_INFLIGHT_PER_MARKET:
            return False, f"{profile} {symbol} in-flight limit reached"

    profile_counts[profile] = p_count + 1
    market_counts[m_key] = m_count + 1
    return True, "reserved"


def _release_trade_slot(state, profile, symbol):
    try:
        profile = str(profile or "KOOLKID").upper()
        symbol = str(symbol or "")
        profile_counts = state.setdefault("trade_slots_profile", {})
        market_counts = state.setdefault("trade_slots_market", {})

        if profile in profile_counts:
            profile_counts[profile] = max(0, int(profile_counts.get(profile, 0)) - 1)
            if profile_counts[profile] <= 0:
                profile_counts.pop(profile, None)

        m_key = _trade_slot_key_market(profile, symbol)
        if m_key in market_counts:
            market_counts[m_key] = max(0, int(market_counts.get(m_key, 0)) - 1)
            if market_counts[m_key] <= 0:
                market_counts.pop(m_key, None)
    except Exception:
        pass


def _release_pending_req_slot(state, req_id, release_slot=True):
    pending = (state.get("pending_req_slots") or {}).pop(req_id, None)
    if pending and release_slot:
        _release_trade_slot(state, pending.get("profile"), pending.get("symbol"))
    return pending


def _move_pending_req_slot_to_contract(state, req_id, contract_id):
    if not req_id or not contract_id:
        return
    pending = _release_pending_req_slot(state, req_id, release_slot=False)
    if pending:
        state.setdefault("active_contract_slots", {})[contract_id] = pending


def _release_contract_slot(state, contract_id, fallback_profile=None, fallback_symbol=None):
    slot = (state.get("active_contract_slots") or {}).pop(contract_id, None)
    if slot:
        _release_trade_slot(state, slot.get("profile"), slot.get("symbol"))
    elif fallback_profile and fallback_symbol:
        _release_trade_slot(state, fallback_profile, fallback_symbol)


def _forget_contract_subscription(state, contract_id):
    try:
        sub_id = (state.get("contract_subs") or {}).pop(contract_id, None)
        if sub_id and state.get("ws_connected") and state.get("ws"):
            _ws_send_json(state, {"forget": sub_id})
    except Exception:
        pass


def _bump_trade_backoff(state, seconds=TRADE_BACKOFF_SEC):
    try:
        now = time.time()
        state["trade_backoff_until"] = max(float(state.get("trade_backoff_until", 0.0)), now + float(seconds))
    except Exception:
        pass


def _clear_trade_runtime_state(state, clear_queue=True):
    try:
        if clear_queue and state.get("trade_queue") is not None:
            lock = state.get("trade_queue_lock")
            if lock:
                with lock:
                    state["trade_queue"].clear()
            else:
                state["trade_queue"].clear()
        state.setdefault("pending_req_slots", {}).clear()
        state.setdefault("active_contract_slots", {}).clear()
        state.setdefault("contract_subs", {}).clear()
        state.setdefault("trade_slots_profile", {}).clear()
        state.setdefault("trade_slots_market", {}).clear()
        state.setdefault("last_trade_fingerprint_ts", {}).clear()
        state["trade_backoff_until"] = 0.0
        state["trade_last_send_ts"] = 0.0
        ev = state.get("trade_queue_event")
        if ev:
            ev.set()
    except Exception:
        pass


def _build_buy_queue_fingerprint(meta, params):
    try:
        profile = str((meta or {}).get("profile") or "")
        symbol = str((meta or {}).get("symbol") or "")
        ctype = str((meta or {}).get("type") or "")
        barrier = (meta or {}).get("barrier")
        d_contract = str((params or {}).get("contract_type") or "")
        return f"{profile}|{symbol}|{ctype}|{barrier}|{d_contract}"
    except Exception:
        return str(uuid.uuid4())


def _trade_worker_loop(client_id):
    while True:
        state = clients.get(client_id)
        if not state:
            return

        stop_ev = state.get("trade_worker_stop_event")
        if stop_ev and stop_ev.is_set():
            return

        ev = state.get("trade_queue_event")
        if ev:
            ev.wait(0.25)
            ev.clear()
        else:
            time.sleep(0.25)

        while True:
            state = clients.get(client_id)
            if not state:
                return
            stop_ev = state.get("trade_worker_stop_event")
            if stop_ev and stop_ev.is_set():
                return

            q_lock = state.get("trade_queue_lock")
            if q_lock:
                with q_lock:
                    item = state["trade_queue"][0] if state.get("trade_queue") else None
            else:
                item = state["trade_queue"][0] if state.get("trade_queue") else None

            if not item:
                break

            now = time.time()
            if now < float(state.get("trade_backoff_until", 0.0)):
                time.sleep(min(0.15, max(0.02, float(state.get("trade_backoff_until", 0.0)) - now)))
                continue

            min_gap = float(TRADE_QUEUE_MIN_GAP_SEC)
            last_send = float(state.get("trade_last_send_ts", 0.0))
            if now - last_send < min_gap:
                time.sleep(max(0.01, min_gap - (now - last_send)))
                continue

            if not state.get("ws_connected") or not state.get("ws"):
                time.sleep(0.10)
                break

            meta = dict(item.get("meta") or {})
            params = dict(item.get("parameters") or {})
            profile = str(meta.get("profile") or item.get("profile") or "KOOLKID").upper()
            symbol = meta.get("symbol") or params.get("symbol")
            fp = item.get("fingerprint") or _build_buy_queue_fingerprint(meta, params)

            last_fp_ts = float((state.get("last_trade_fingerprint_ts") or {}).get(fp, 0.0))
            if now - last_fp_ts < float(TRADE_DUP_WINDOW_SEC):
                logger.warning(f"[{client_id}] ⚠️ Duplicate trade request dropped ({profile} {symbol})")
                if q_lock:
                    with q_lock:
                        if state.get("trade_queue"):
                            state["trade_queue"].popleft()
                else:
                    if state.get("trade_queue"):
                        state["trade_queue"].popleft()
                continue

            ok_slot, slot_msg = _reserve_trade_slot(state, profile, symbol)
            if not ok_slot:
                time.sleep(0.05)
                continue

            # Pop only after slot reservation succeeds
            if q_lock:
                with q_lock:
                    if not state.get("trade_queue"):
                        _release_trade_slot(state, profile, symbol)
                        continue
                    item = state["trade_queue"].popleft()
            else:
                if not state.get("trade_queue"):
                    _release_trade_slot(state, profile, symbol)
                    continue
                item = state["trade_queue"].popleft()

            meta = dict(item.get("meta") or {})
            params = dict(item.get("parameters") or {})
            stake = float(item.get("stake", meta.get("stake", 1.0)))
            req_id = _new_req_id()
            meta["profile"] = profile
            meta["symbol"] = meta.get("symbol") or params.get("symbol")

            state.setdefault("req_meta", {})[req_id] = meta
            state.setdefault("pending_req_slots", {})[req_id] = {"profile": profile, "symbol": meta.get("symbol")}

            payload = {
                "req_id": req_id,
                "buy": 1,
                "price": stake,
                "parameters": params
            }

            sent = _ws_send_json(state, payload)
            if sent:
                state["trade_last_send_ts"] = time.time()
                state.setdefault("last_trade_fingerprint_ts", {})[item.get("fingerprint") or fp] = state["trade_last_send_ts"]
            else:
                state.get("req_meta", {}).pop(req_id, None)
                _release_pending_req_slot(state, req_id, release_slot=True)
                _bump_trade_backoff(state, seconds=max(0.5, TRADE_BACKOFF_SEC))
                logger.error(f"[{client_id}] ❌ Queue send failed ({profile} {meta.get('symbol')})")
                time.sleep(0.05)


def _ensure_trade_worker(client_id, state):
    t = state.get("trade_worker_thread")
    if t and t.is_alive():
        return
    try:
        stop_ev = state.get("trade_worker_stop_event")
        if stop_ev:
            stop_ev.clear()
    except Exception:
        pass
    t = threading.Thread(target=_trade_worker_loop, args=(client_id,), daemon=True)
    state["trade_worker_thread"] = t
    t.start()


def _send_buy_order_now(client_id, profile, meta, parameters):
    state = clients.get(client_id)
    if not state:
        return False, "No client state"
    if not state.get("ws_connected") or not state.get("ws"):
        return False, "Not connected"

    now_ts = time.time()
    if now_ts < float(state.get("trade_backoff_until", 0.0)):
        return False, "Execution layer cooling down after API error"

    try:
        stake = float((meta or {}).get("stake", 1.0))
    except Exception:
        stake = 1.0

    profile = str(profile or (meta or {}).get("profile") or "KOOLKID").upper()
    meta = dict(meta or {})
    params = dict(parameters or {})
    symbol = meta.get("symbol") or params.get("symbol")
    meta["profile"] = profile
    if symbol is not None:
        meta["symbol"] = symbol

    ok_slot, slot_msg = _reserve_trade_slot(state, profile, symbol)
    if not ok_slot:
        return False, slot_msg

    req_id = _new_req_id()
    state.setdefault("req_meta", {})[req_id] = meta
    state.setdefault("pending_req_slots", {})[req_id] = {"profile": profile, "symbol": symbol}

    payload = {
        "req_id": req_id,
        "buy": 1,
        "price": stake,
        "parameters": params
    }

    sent = _ws_send_json(state, payload)
    if sent:
        state["trade_last_send_ts"] = time.time()
        return True, "Trade sent"

    state.get("req_meta", {}).pop(req_id, None)
    _release_pending_req_slot(state, req_id, release_slot=True)
    _bump_trade_backoff(state, seconds=max(0.5, TRADE_BACKOFF_SEC))
    logger.error(f"[{client_id}] ❌ Direct send failed ({profile} {symbol})")
    return False, "Send failed"


def _queue_buy_order(client_id, profile, meta, parameters):
    if not USE_TRADE_QUEUE:
        return _send_buy_order_now(client_id, profile, meta, parameters)

    state = clients.get(client_id)
    if not state:
        return False, "No client state"
    if not state.get("ws_connected") or not state.get("ws"):
        return False, "Not connected"

    try:
        stake = float((meta or {}).get("stake", 1.0))
    except Exception:
        stake = 1.0

    item = {
        "profile": str(profile or (meta or {}).get("profile") or "KOOLKID").upper(),
        "stake": stake,
        "meta": dict(meta or {}),
        "parameters": dict(parameters or {}),
    }
    item["fingerprint"] = _build_buy_queue_fingerprint(item["meta"], item["parameters"])

    q_lock = state.get("trade_queue_lock")
    if q_lock:
        with q_lock:
            q = state.setdefault("trade_queue", deque())
            if len(q) >= MAX_TRADE_QUEUE_SIZE:
                return False, "Trade queue full"
            q.append(item)
    else:
        q = state.setdefault("trade_queue", deque())
        if len(q) >= MAX_TRADE_QUEUE_SIZE:
            return False, "Trade queue full"
        q.append(item)

    _ensure_trade_worker(client_id, state)
    ev = state.get("trade_queue_event")
    if ev:
        ev.set()

    return True, "Trade queued"


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
    _clear_trade_runtime_state(state, clear_queue=True)

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
        "current_symbol": "R_25",
        "human_symbol": "R_25",
        "tick_subs": {},
        "symbol_pip_sizes": {},
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
        "humanx_auto": False,
        "humanx_status_last": "Auto: OFF",
        "balance": 0.0,
        "session_start_balance": None,
        "auto_stake": 1.0,
        "req_meta": {},          # req_id -> meta
        "contract_meta": {},     # contract_id -> meta
        "contract_subs": {},     # contract_id -> subscription id (proposal_open_contract)
        "pending_req_slots": {}, # req_id -> {profile, symbol}
        "active_contract_slots": {}, # contract_id -> {profile, symbol}
        "trade_slots_profile": {},
        "trade_slots_market": {},
        "trade_last_send_ts": 0.0,
        "trade_backoff_until": 0.0,
        "last_trade_fingerprint_ts": {},
        "trade_queue": deque(),
        "trade_queue_lock": threading.Lock(),
        "trade_queue_event": threading.Event(),
        "trade_worker_thread": None,
        "trade_worker_stop_event": threading.Event(),
        "ws_send_lock": threading.Lock(),
        "last_seen": time.time(),  # heartbeat (page open)
        "strategies": {
            "KOOLKID": KoolKidStrategy(),
            "JOKERJOE": JokerJoeStrategy(),
            "HUMAN": HumanStrategy()
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

    # human chart
    try:
        if prof == "HUMAN" and strat and hasattr(strat, "get_chart_data"):
            socketio.emit("human_chart_data", strat.get_chart_data(), room=cid)
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
            session["user"] = username
            session["client_id"] = str(uuid.uuid4())
            init_client(session["client_id"])
            return redirect(url_for("index"))
        else:
            return render_template("login.html", error="Invalid username or password")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if len(password) < 8:
            return render_template("register.html", error="Password must be at least 8 characters")

        if password.isdigit() or password.isalpha():
            return render_template("register.html", error="Password must include letters and numbers")

        ok, msg = create_user(username, password)

        if ok:
            return redirect(url_for("login"))
        else:
            return render_template("register.html", error=msg)

    return render_template("register.html")


@app.route("/logout")
def logout():
    cid = session.pop("client_id", None)
    if cid and cid in clients:
        # full cleanup on logout
        disconnect_client(cid, reason="logout", emit=False)
        clients.pop(cid, None)

    session.pop("user", None)
    return redirect(url_for("login"))


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


# ---------------- BOT ROUTE (PROTECTED) ---------------- #
@app.route("/")
def index():
    if not login_required():
        return redirect(url_for("login"))
    return render_template("index.html", username=session.get("user"))


# ---------------- HEARTBEAT ROUTE ---------------- #
@app.route("/heartbeat", methods=["POST"])
def heartbeat():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403
    cid, _state = get_client_state()
    return jsonify({"status": "ok", "client_id": cid})


# ---------------- DERIV BUY FUNCTION (PER CLIENT) ---------------- #
def send_buy(client_id, contract_type, stake, symbol, barrier):
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
    meta = {
        "profile": profile,
        "type": contract_type,
        "barrier": int(barrier),
        "stake": float(stake),
        "symbol": symbol,
        "time": now_time()
    }

    parameters = {
        "amount": float(stake),
        "basis": "stake",
        "contract_type": deriv_contract,
        "currency": "USD",
        "duration": 1,
        "duration_unit": "t",
        "symbol": symbol,
        "barrier": int(barrier)
    }

    return _queue_buy_order(client_id, profile, meta, parameters)


# ==================== PATCH 1C: send_buy_with_profile ====================
def send_buy_with_profile(client_id, profile, contract_type, stake, symbol, barrier):
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
    meta = {
        "profile": profile,
        "type": contract_type,
        "barrier": int(barrier),
        "stake": float(stake),
        "symbol": symbol,
        "time": now_time()
    }

    parameters = {
        "amount": float(stake),
        "basis": "stake",
        "contract_type": deriv_contract,
        "currency": "USD",
        "duration": 1,
        "duration_unit": "t",
        "symbol": symbol,
        "barrier": int(barrier)
    }

    return _queue_buy_order(client_id, profile, meta, parameters)


# ---------------- MULTIPLIER ORDER (HUMANX) ---------------- #
def place_multiplier_order(client_id, signal):
    state = clients.get(client_id)
    if not state or not state.get("ws_connected"):
        return False, "Not connected"

    # PATCH E: Block HUMAN multiplier trades if HUMAN session is TP/SL blocked
    strategy = state.get("strategies", {}).get("HUMAN")

    if strategy and hasattr(strategy, "enforce_tp_sl"):
        strategy.enforce_tp_sl()
        if getattr(strategy, "risk_block_reason", None):
            return False, f"{strategy.risk_block_reason} (session limit reached)"

    ws = state["ws"]

    symbol_to_use = signal.get("symbol") or state.get("current_symbol")
    profile_to_use = signal.get("profile") or state.get("active_profile", "HUMAN")


    stake = float(signal.get("stake", state.get("auto_stake", 1.0)))
    multiplier = int(signal.get("multiplier", 50))
    direction = signal.get("direction", "BUY")
    sl = signal.get("sl")
    tp = signal.get("tp")

    # clamp multiplier to max 500
    if multiplier < 1:
        multiplier = 1
    if multiplier > 500:
        multiplier = 500
    meta = {
        "profile": "HUMAN",  # PATCH E: set profile hard to HUMAN
        "type": f"MULT {direction}",
        "barrier": None,
        "stake": stake,
        "symbol": symbol_to_use,
        "time": now_time()
    }

    parameters = {
        "amount": stake,
        "basis": "stake",
        "contract_type": "MULTIPLIER",
        "currency": "USD",
        "symbol": symbol_to_use,
        "multiplier": multiplier,
        "take_profit": tp,
        "stop_loss": sl,
    }

    return _queue_buy_order(client_id, profile_to_use, meta, parameters)


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
            symbol = state.get("current_symbol", "R_25")
            stake = float(state.get("auto_stake", 1.0))

            ok, msg = send_buy(client_id, ctype, stake, symbol, barrier)

            if ok:
                logger.info(f"[{client_id}] 🤖 AUTO TRADE SENT ({active_profile}): {ctype} barrier={barrier} stake={stake} mode={sig.get('mode')}")
            else:
                logger.error(f"[{client_id}] ❌ AUTO TRADE FAILED: {msg}")

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

    # digit from tick quote (robust precision + no float drift)
    try:
        d, _pip_size = extract_last_digit_from_tick(state, tick, default_pip=2)
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
            req_id = data.get("req_id")
            if req_id is not None and req_id in (state.get("pending_req_slots") or {}):
                _release_pending_req_slot(state, req_id, release_slot=True)
                state.get("req_meta", {}).pop(req_id, None)
            # Back off the execution layer briefly on API errors (helps fast-mode bursts recover).
            _bump_trade_backoff(state, seconds=TRADE_BACKOFF_SEC)
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
            # Prime per-symbol precision cache so live last-digit stays correct.
            ws.send(json.dumps({"active_symbols": "brief"}))

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

        if "active_symbols" in data:
            try:
                items = data.get("active_symbols") or []
                _cache_symbol_pip_from_active_symbols(state, items)
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
            _enrich_tick_with_raw_quote_fields(message, tick)
            try:
                sub = data.get("subscription") or {}
                sub_id = sub.get("id")
                sym = tick.get("symbol")
                if sub_id and sym:
                    state.setdefault("tick_subs", {})
                    state["tick_subs"][sym] = sub_id

                # Cache precision so later ticks without pip_size still extract the right digit.
                if sym:
                    resolve_tick_pip_size(state, tick, default=2)
            except Exception:
                pass
            # ==================== PATCH 1E: hook process_seqvix_tick ====================
            process_seqvix_tick(client_id, tick)
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
                _move_pending_req_slot_to_contract(state, req_id, contract_id)
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
                if req_id is not None:
                    _release_pending_req_slot(state, req_id, release_slot=True)
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
                _ws_send_json(state, {
                    "proposal_open_contract": 1,
                    "contract_id": contract_id,
                    "subscribe": 1
                })

        if "proposal_open_contract" in data:
            contract = data["proposal_open_contract"]
            try:
                sub = data.get("subscription") or {}
                sub_id = sub.get("id")
                c_id = contract.get("contract_id")
                if c_id and sub_id:
                    state.setdefault("contract_subs", {})[c_id] = sub_id
            except Exception:
                pass
            process_contract(client_id, contract)

    except Exception as e:
        logger.error(f"[{client_id}] on_message error: {e}")


# ---------------- HUMANX STATUS HELPERS ---------------- #
def _compute_humanx_status(strat):
    """Return a human-readable status string for HUMANX auto."""
    try:
        # Require TP/SL for true auto-close
        tp = float(getattr(strat, "tp", 0.0) or 0.0)
        sl = float(getattr(strat, "sl", 0.0) or 0.0)
        if tp <= 0 or sl <= 0:
            return "Auto: Set TP & SL"

        rh = getattr(strat, "range_high", None)
        rl = getattr(strat, "range_low", None)
        if not rh or not rl:
            return "Auto: Seeding Range"

        bias = getattr(strat, "breakout_bias", None)
        if not bias:
            return "Auto: Waiting Breakout"

        ob = getattr(strat, "order_block", None)
        if not ob:
            return "Auto: Waiting OB"

        retrace = bool(getattr(strat, "retrace_happened", False))
        if not retrace:
            return "Auto: Waiting Retest"

        fired = bool(getattr(strat, "signal_fired", False))
        if not fired:
            return "Auto: Waiting Confirmation"

        return "Auto: Entry Triggered"
    except Exception:
        return "Auto: Armed"


def _emit_humanx_status_if_changed(client_id, state, status):
    """Emit humanx_auto_status only when the text changes (to reduce spam)."""
    try:
        enabled = bool(state.get("humanx_auto"))
        if not enabled:
            status = "Auto: OFF"
        last = state.get("humanx_status_last")
        if status != last:
            state["humanx_status_last"] = status
            socketio.emit("humanx_auto_status", {"enabled": enabled, "status": status}, room=client_id)
    except Exception:
        pass



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

        pip_size = resolve_tick_pip_size(state, tick, default=2)
        digit = (extract_last_digit_from_tick(state, tick, default_pip=pip_size)[0]) if is_main else None

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

                    # ✅ HUMANX AUTO (independent of active profile)
                    if state.get("humanx_auto"):
                        try:
                            status = _compute_humanx_status(strat)
                            _emit_humanx_status_if_changed(client_id, state, status)

                            sig = strat.get_humanx_signal()
                            if sig:
                                # For Multipliers, TP/SL must be AMOUNTS, not price levels.
                                tp_amt = float(getattr(strat, "tp", 0.0) or 0.0)
                                sl_amt = float(getattr(strat, "sl", 0.0) or 0.0)

                                sig2 = dict(sig)
                                sig2["profile"] = "HUMAN"
                                sig2["symbol"] = human_symbol
                                if tp_amt > 0:
                                    sig2["tp"] = tp_amt
                                else:
                                    sig2["tp"] = None
                                if sl_amt > 0:
                                    sig2["sl"] = sl_amt
                                else:
                                    sig2["sl"] = None

                                if tp_amt <= 0 or sl_amt <= 0:
                                    _emit_humanx_status_if_changed(client_id, state, "Auto: Set TP & SL")
                                else:
                                    ok, msg = place_multiplier_order(client_id, sig2)
                                    if ok:
                                        _emit_humanx_status_if_changed(client_id, state, "Auto: Trade Placed")
                                    else:
                                        _emit_humanx_status_if_changed(client_id, state, f"Auto: Error ({msg})")
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

        if active_profile == "JOKERJOE":
            jj = strategies.get("JOKERJOE")
            if jj:
                emit_jokerjoe_modes(client_id, jj)

        if active_profile == "HUMAN":
            strat = strategies.get("HUMAN")
            if strat and hasattr(strat, "get_chart_data"):
                socketio.emit("human_chart_data", strat.get_chart_data(), room=client_id)

    except Exception as e:
        logger.error(f"[{client_id}] process_tick error: {e}")



def _is_contract_settled_fast(contract: dict) -> bool:
    try:
        if contract.get("is_sold") or contract.get("is_settled"):
            return True
        status = (contract.get("status") or "").lower()
        if status in ("sold", "won", "lost", "settled"):
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

        profit = float(contract.get("profit", 0))
        state["balance"] = float(state.get("balance", 0.0)) + profit

        contract_id = contract.get("contract_id")
        meta = state["contract_meta"].pop(contract_id, None) if contract_id else None
        if contract_id:
            _forget_contract_subscription(state, contract_id)
            _release_contract_slot(
                state,
                contract_id,
                fallback_profile=(meta or {}).get("profile"),
                fallback_symbol=(meta or {}).get("symbol"),
            )

        # PATCH F: Use the trade's real profile (not active_profile)
        profile_for_contract = (meta.get("profile") if meta else None) or state.get("active_profile", "KOOLKID")

        strategies = state.get("strategies", {})
        strategy = strategies.get(profile_for_contract)
        if not strategy:
            return

        # Remember previous block reason to detect changes
        prev_block = getattr(strategy, "risk_block_reason", None)

        # Update strategy with the contract result
        strategy.on_contract(contract, state.get("balance", 0))

        # If TP/SL just got hit, emit a risk block update
        new_block = getattr(strategy, "risk_block_reason", None)
        if new_block and new_block != prev_block:
            socketio.emit("risk_block_update", {
                "profile": profile_for_contract,
                "reason": new_block
            }, room=client_id)

        entry = {}
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
        send_stats_update(client_id)

    except Exception as e:
        logger.error(f"[{client_id}] process_contract error: {e}")


def send_stats_update(client_id):
    state = clients.get(client_id)
    if not state:
        return

    strategies = state.get("strategies", {})
    strategy = strategies.get(state.get("active_profile", "KOOLKID"))
    if not strategy or not hasattr(strategy, "get_stats_payload"):
        return

    payload = strategy.get_stats_payload(state.get("balance", 0.0), state.get("session_start_balance"))
    payload["profile"] = state.get("active_profile", "KOOLKID")

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
        _ws_send_json(state, {"authorize": api_token})


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
    _clear_trade_runtime_state(state, clear_queue=True)
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
        ws_app.run_forever(ping_interval=30, ping_timeout=10)
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

    # ✅ also sync stake into HUMAN strategy so humanX uses your stake input
    try:
        h = state["strategies"].get("HUMAN")
        if h and hasattr(h, "stake"):
            h.stake = float(stake)
    except Exception:
        pass

    return jsonify({"status": "success", "auto_stake": stake})


@app.route("/set_human_multiplier", methods=["POST"])
def set_human_multiplier():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    data = request.json or {}
    try:
        mult = int(data.get("multiplier", 50))
    except Exception:
        mult = 50

    if mult < 1:
        mult = 1
    if mult > 500:
        mult = 500

    try:
        h = state["strategies"].get("HUMAN")
        if h and hasattr(h, "multiplier"):
            h.multiplier = mult
    except Exception:
        pass

    return jsonify({"status": "success", "multiplier": mult})


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

    if profile == state.get("active_profile"):
        send_stats_update(cid)

    return jsonify({"status": "cleared", "profile": profile})


@app.route("/set_profile", methods=["POST"])
def set_profile():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    profile = (request.json or {}).get("profile", "KOOLKID")

    if profile not in state["strategies"]:
        return jsonify({"error": "Invalid profile"}), 400

    state["active_profile"] = profile
    socketio.emit("profile_update", {"profile": profile, "symbol": (state.get("human_symbol") if profile == "HUMAN" else state.get("current_symbol"))}, room=cid)
    if profile == "HUMAN":
        request_human_seed(cid)
        try:
            _emit_humanx_status_if_changed(cid, state, "Auto: OFF" if not state.get("humanx_auto") else state.get("humanx_status_last") or "Auto: Armed")
        except Exception:
            pass
    emit_profile_snapshot(cid)

    return jsonify({"status": "success", "profile": profile, "main_symbol": state.get("current_symbol"), "human_symbol": state.get("human_symbol") or state.get("current_symbol"), "symbol": (state.get("human_symbol") if profile == "HUMAN" else state.get("current_symbol")),
        "humanx_auto": bool(state.get("humanx_auto")),
        "humanx_status": state.get("humanx_status_last") or ("Auto: Armed" if state.get("humanx_auto") else "Auto: OFF")
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
        "humanx_auto": bool(state.get("humanx_auto")),
        "humanx_status": state.get("humanx_status_last") or ("Auto: Armed" if state.get("humanx_auto") else "Auto: OFF")
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
            old_id = (state.get("tick_subs") or {}).get(old_symbol)
            if old_id:
                ws.send(json.dumps({"forget": old_id}))
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

    old_symbol = state.get("human_symbol") or state.get("current_symbol")
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
            old_id = (state.get("tick_subs") or {}).get(old_symbol)
            if old_id:
                ws.send(json.dumps({"forget": old_id}))
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


@app.route("/toggle_humanx_auto", methods=["POST"])
def toggle_humanx_auto():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    enabled = not bool(state.get("humanx_auto"))
    state["humanx_auto"] = enabled

    strat = state.get("strategies", {}).get("HUMAN")
    if strat:
        try:
            strat.auto_trade = enabled
        except Exception:
            pass

    status = "Auto: Armed" if enabled else "Auto: OFF"
    state["humanx_status_last"] = status
    socketio.emit("humanx_auto_status", {"enabled": enabled, "status": status}, room=cid)

    return jsonify({
        "status": "success",
        "enabled": enabled,
        "main_symbol": state.get("current_symbol"),
        "human_symbol": state.get("human_symbol") or state.get("current_symbol")
    })


@app.route("/humanx_trade", methods=["POST"])
def humanx_trade():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    strat = state["strategies"].get("HUMAN")
    if not strat:
        return jsonify({"error": "Human strategy not loaded"}), 400

    signal = strat.get_humanx_signal()
    if not signal:
        return jsonify({"error": "No valid setup at the moment"}), 400

    ok, msg = place_multiplier_order(cid, signal)
    if ok:
        return jsonify({"status": "success", "signal": signal})
    else:
        return jsonify({"error": msg}), 500


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
        now = time.time()
        for cid, state in list(clients.items()):
            # PATCH C: Skip if keep-alive is enabled (HUMAN only)
            if state.get("human_keep_alive"):
                continue
            # only enforce timeout if a token/WS is active
            if state.get("api_token") or state.get("ws"):
                last_seen = state.get("last_seen", now)
                if (now - last_seen) > HEARTBEAT_TIMEOUT_SEC:
                    disconnect_client(cid, reason="heartbeat_timeout", emit=True)


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