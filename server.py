import os, sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import json
import threading
import websocket
import time
import uuid
import sqlite3

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

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading", manage_session=False)

DERIV_WS = "wss://ws.derivws.com/websockets/v3?app_id=1089"

# DATABASE FILE
DB_FILE = "users.db"

# ==========================
# MULTI-CLIENT STATE
# ==========================
clients = {}


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


# ✅ NEW: extract exit digit reliably from contract fields
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


def _force_autos_off(strategy_obj):
    """
    Bulletproof: if strategies store auto flags, force them OFF.
    This is safe because we only set attrs that already exist.
    """
    if not strategy_obj:
        return
    try:
        # Common "main auto" flag
        if hasattr(strategy_obj, "auto_trade"):
            setattr(strategy_obj, "auto_trade", False)

        # KOOLKID modes (if present)
        for attr in ("kidracks_auto", "koolkidspeed_auto", "koolluck_auto"):
            if hasattr(strategy_obj, attr):
                setattr(strategy_obj, attr, False)

        # JOKERJOE modes (if present)
        for attr in ("sludgex_auto", "triplex_auto", "kidx_auto", "multig_auto"):
            if hasattr(strategy_obj, attr):
                setattr(strategy_obj, attr, False)
    except Exception:
        pass


def stop_client_everything(client_id, *, clear_token=True):
    """
    HARD STOP:
    - kill deriv WS (and invalidate any old thread callbacks)
    - disable all trading
    - clear request/contract meta
    - reset strategies + force autos off
    - emit UI reset + disconnected
    """
    state = clients.get(client_id)
    if not state:
        return

    # Invalidate any existing WS thread callbacks immediately
    try:
        state["ws_generation"] = int(state.get("ws_generation", 0)) + 1
    except Exception:
        state["ws_generation"] = 1

    # Stop-event for any currently running WS thread
    try:
        ev = state.get("ws_stop_event")
        if ev:
            ev.set()
    except Exception:
        pass

    # Disable trading right away
    state["trading_enabled"] = False
    state["ws_connected"] = False

    if clear_token:
        state["api_token"] = ""

    # Close the websocket-client app if exists
    ws = state.get("ws")
    if ws:
        try:
            # websocket-client uses keep_running; setting false helps stop run_forever()
            ws.keep_running = False
        except Exception:
            pass
        try:
            ws.close()
        except Exception:
            pass

    state["ws"] = None
    state["balance"] = 0.0
    state["session_start_balance"] = None
    state["req_meta"].clear()
    state["contract_meta"].clear()

    # Reset strategies + hard force autos off
    try:
        for strat in state["strategies"].values():
            try:
                strat.reset()
            except Exception:
                pass
            _force_autos_off(strat)
    except Exception:
        pass

    # Tell UI to reset + disconnected
    try:
        socketio.emit("connection_status", {"connected": False}, room=client_id)
        socketio.emit("reset_ui", room=client_id)
        send_stats_update(client_id)
    except Exception:
        pass


def init_client(client_id):
    """
    Initialize a fresh client state.
    """
    if client_id in clients:
        return

    clients[client_id] = {
        "api_token": "",
        "ws": None,
        "ws_connected": False,
        "trading_enabled": False,      # ✅ hard gate
        "ws_generation": 0,            # ✅ anti double-instance guard
        "ws_stop_event": threading.Event(),
        "active_profile": "KOOLKID",
        "current_symbol": "R_25",
        "balance": 0.0,
        "session_start_balance": None,
        "auto_stake": 1.0,
        "req_meta": {},          # req_id -> meta
        "contract_meta": {},     # contract_id -> meta
        "strategies": {
            "KOOLKID": KoolKidStrategy(),
            "JOKERJOE": JokerJoeStrategy(),
            "HUMAN": HumanStrategy()
        }
    }


def get_client_state():
    cid = get_client_id()
    if cid not in clients:
        init_client(cid)
    return cid, clients[cid]


def emit_jokerjoe_modes(cid, strat: JokerJoeStrategy):
    try:
        socketio.emit("auto_mode_update", {
            "sludgex": bool(getattr(strat, "sludgex_auto", False)),
            "triplex": bool(getattr(strat, "triplex_auto", False)),
            "kidx": bool(getattr(strat, "kidx_auto", False)),
            "multig": bool(getattr(strat, "multig_auto", False)),
        }, room=cid)
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
        stop_client_everything(cid, clear_token=True)
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

    try:
        jj = state["strategies"].get("JOKERJOE")
        if jj:
            emit_jokerjoe_modes(cid, jj)
    except Exception:
        pass

    send_stats_update(cid)


# ---------------- BOT ROUTE (PROTECTED) ---------------- #
@app.route("/")
def index():
    if not login_required():
        return redirect(url_for("login"))
    return render_template("index.html", username=session.get("user"))


# ---------------- DERIV BUY FUNCTION (PER CLIENT) ---------------- #
def send_buy(client_id, contract_type, stake, symbol, barrier):
    state = clients.get(client_id)
    if not state:
        return False, "No client state"

    ws = state.get("ws")
    ws_connected = state.get("ws_connected", False)
    trading_enabled = state.get("trading_enabled", False)

    # ✅ HARD GATE
    if not trading_enabled:
        return False, "Trading disabled"
    if not ws_connected or not ws:
        return False, "Not connected"

    contract_map = {
        "OVER": "DIGITOVER",
        "UNDER": "DIGITUNDER",
        "MATCHES": "DIGITMATCH",
        "DIFFERS": "DIGITDIFF"
    }

    if contract_type not in contract_map:
        return False, "Invalid contract type"

    deriv_contract = contract_map[contract_type]

    req_id = _new_req_id()
    state["req_meta"][req_id] = {
        "profile": state.get("active_profile", "KOOLKID"),
        "type": contract_type,
        "barrier": int(barrier),
        "stake": float(stake),
        "symbol": symbol,
        "time": now_time()
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
            "duration": 1,
            "duration_unit": "t",
            "symbol": symbol,
            "barrier": int(barrier)
        }
    }

    try:
        ws.send(json.dumps(payload))
        return True, "Trade sent"
    except Exception as e:
        return False, str(e)


# ---------------- MULTIPLIER ORDER (HUMANX) ---------------- #
def place_multiplier_order(client_id, signal):
    state = clients.get(client_id)
    if not state:
        return False, "No client state"

    # ✅ HARD GATE
    if not state.get("trading_enabled", False):
        return False, "Trading disabled"
    if not state.get("ws_connected", False):
        return False, "Not connected"

    ws = state["ws"]
    if not ws:
        return False, "Not connected"

    stake = float(signal.get("stake", state.get("auto_stake", 1.0)))
    multiplier = signal.get("multiplier", 50)
    direction = signal.get("direction", "BUY")
    sl = signal.get("sl")
    tp = signal.get("tp")

    req_id = _new_req_id()
    state["req_meta"][req_id] = {
        "profile": state.get("active_profile", "HUMAN"),
        "type": f"MULT {direction}",
        "barrier": None,
        "stake": stake,
        "symbol": state["current_symbol"],
        "time": now_time()
    }

    payload = {
        "req_id": req_id,
        "buy": 1,
        "price": stake,
        "parameters": {
            "amount": stake,
            "basis": "stake",
            "contract_type": "MULTIPLIER",
            "currency": "USD",
            "symbol": state["current_symbol"],
            "multiplier": multiplier,
            "take_profit": tp,
            "stop_loss": sl,
        }
    }
    try:
        ws.send(json.dumps(payload))
        return True, "Trade sent"
    except Exception as e:
        return False, str(e)


# ---------------- AUTO TRADE ENGINE (PER CLIENT) ---------------- #
def run_auto_trade(client_id, state):
    # ✅ HARD GATE
    if not state.get("trading_enabled", False):
        return
    if not state.get("ws_connected", False):
        return

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


# ---------------- WEBSOCKET HANDLERS (PER CLIENT) ---------------- #
def handle_on_message(client_id, ws, message):
    state = clients.get(client_id)
    if not state:
        return

    try:
        data = json.loads(message)

        if "error" in data:
            msg = data["error"].get("message", "Unknown API Error")
            logger.error(f"[{client_id}] API Error: {msg}")
            socketio.emit("api_error", {"message": msg}, room=client_id)
            return

        if "authorize" in data:
            # ✅ Only mark connected + enable trading AFTER authorize confirms
            state["ws_connected"] = True
            state["trading_enabled"] = True

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
            send_stats_update(client_id)

            ws.send(json.dumps({"ticks": state["current_symbol"], "subscribe": 1}))
            ws.send(json.dumps({"balance": 1, "subscribe": 1}))

        if "balance" in data:
            try:
                balance = float(data["balance"]["balance"])
                state["balance"] = balance
                socketio.emit("balance_update", {"balance": balance}, room=client_id)
                send_stats_update(client_id)
            except Exception:
                pass

        if "tick" in data:
            tick = data["tick"]
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

        if "proposal_open_contract" in data:
            contract = data["proposal_open_contract"]
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

        if symbol != state.get("current_symbol"):
            return

        pip_size = tick.get("pip_size", 2)
        digit = extract_last_decimal_digit(price, pip_size)

        strategies = state.get("strategies", {})
        strategy = strategies.get(state.get("active_profile", "KOOLKID"))

        if strategy:
            strategy.on_tick(tick, digit)

        socketio.emit("tick", {
            "symbol": symbol,
            "digit": digit,
            "price": price,
            "tick_count": strategy.tick_count if strategy else 0,
            "timestamp": now_time()
        }, room=client_id)

        if strategy:
            socketio.emit("digit_analysis", strategy.get_ui_payload(), room=client_id)

        # ✅ HARD GATE inside run_auto_trade (and checks above)
        run_auto_trade(client_id, state)

        if state.get("active_profile") == "JOKERJOE":
            jj = state["strategies"].get("JOKERJOE")
            if jj:
                emit_jokerjoe_modes(client_id, jj)

        if state.get("active_profile") == "HUMAN":
            strat = state["strategies"]["HUMAN"]
            chart_data = strat.get_chart_data()
            socketio.emit("human_chart_data", chart_data, room=client_id)

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

        strategies = state.get("strategies", {})
        strategy = strategies.get(state.get("active_profile", "KOOLKID"))

        if strategy:
            strategy.on_contract(contract, state["balance"])

        contract_id = contract.get("contract_id")
        meta = state["contract_meta"].pop(contract_id, None) if contract_id else None

        entry = strategy.get_last_trade_entry() if strategy else {}
        if meta:
            entry.setdefault("profile", meta.get("profile"))
            entry.setdefault("type", meta.get("type"))
            entry.setdefault("barrier", meta.get("barrier"))
            entry.setdefault("stake", meta.get("stake"))
            entry.setdefault("symbol", meta.get("symbol"))
            entry.setdefault("time", meta.get("time"))
        else:
            entry.setdefault("profile", state.get("active_profile", "KOOLKID"))

        # ✅ EXIT DIGIT FIX: inject exit digit for history UI
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
    if not strategy:
        return

    payload = strategy.get_stats_payload(state.get("balance", 0.0), state.get("session_start_balance"))
    payload["profile"] = state.get("active_profile", "KOOLKID")

    socketio.emit("stats_update", payload, room=client_id)


def handle_on_open(client_id, ws):
    state = clients.get(client_id)
    if not state:
        return

    # ✅ DO NOT set ws_connected/trading_enabled here
    logger.info(f"[{client_id}] 🔌 WebSocket Connected (socket open)")

    api_token = state.get("api_token")
    if api_token:
        ws.send(json.dumps({"authorize": api_token}))


def handle_on_error(client_id, ws, error):
    logger.error(f"[{client_id}] WebSocket Error: {error}")
    socketio.emit("api_error", {"message": str(error)}, room=client_id)


def handle_on_close(client_id, ws, code, msg):
    state = clients.get(client_id)
    if not state:
        return

    state["ws_connected"] = False
    state["trading_enabled"] = False
    logger.warning(f"[{client_id}] 🔌 WebSocket Disconnected")
    socketio.emit("connection_status", {"connected": False}, room=client_id)


def start_ws_for_client(client_id):
    state = clients.get(client_id)
    if not state:
        return

    # ✅ New generation every time we start
    try:
        state["ws_generation"] = int(state.get("ws_generation", 0)) + 1
    except Exception:
        state["ws_generation"] = 1

    my_gen = state["ws_generation"]

    # ✅ fresh stop event per run
    ev = threading.Event()
    state["ws_stop_event"] = ev

    # close old ws if any
    old_ws = state.get("ws")
    if old_ws:
        try:
            old_ws.keep_running = False
        except Exception:
            pass
        try:
            old_ws.close()
        except Exception:
            pass

    def _stale_or_stopped():
        # Ignore callbacks from old threads or after stop
        cur = clients.get(client_id)
        if not cur:
            return True
        if cur.get("ws_generation") != my_gen:
            return True
        if ev.is_set():
            return True
        return False

    def _on_message(ws, message, cid=client_id):
        if _stale_or_stopped():
            return
        handle_on_message(cid, ws, message)

    def _on_open(ws, cid=client_id):
        if _stale_or_stopped():
            return
        handle_on_open(cid, ws)

    def _on_error(ws, error, cid=client_id):
        if _stale_or_stopped():
            return
        handle_on_error(cid, ws, error)

    def _on_close(ws, code, msg, cid=client_id):
        # even if stale, it's fine to ignore
        if _stale_or_stopped():
            return
        handle_on_close(cid, ws, code, msg)

    ws_app = websocket.WebSocketApp(
        DERIV_WS,
        on_message=_on_message,
        on_open=_on_open,
        on_error=_on_error,
        on_close=_on_close
    )

    state["ws"] = ws_app

    try:
        ws_app.run_forever(ping_interval=30)
    except Exception as e:
        logger.error(f"[{client_id}] run_forever error: {e}")


# ---------------- BOT API ROUTES ---------------- #
@app.route("/set_token", methods=["POST"])
def set_token():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    token = (request.json or {}).get("token", "")

    # ✅ bulletproof: always hard-stop before starting a new WS
    stop_client_everything(cid, clear_token=True)

    # re-fetch state after stop (still exists)
    state = clients.get(cid)
    if not state:
        init_client(cid)
        state = clients[cid]

    state["api_token"] = token
    state["session_start_balance"] = None
    state["ws_connected"] = False
    state["trading_enabled"] = False  # will flip True after authorize

    t = threading.Thread(target=start_ws_for_client, args=(cid,), daemon=True)
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

    return jsonify({"status": "success", "auto_stake": stake})


@app.route("/disconnect", methods=["POST"])
def disconnect():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, _state = get_client_state()
    stop_client_everything(cid, clear_token=True)
    return jsonify({"status": "disconnected"})


@app.route("/clear_profile_history", methods=["POST"])
def clear_profile_history():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    data = request.json or {}
    profile = (data.get("profile") or state.get("active_profile") or "KOOLKID").upper()

    strat = state["strategies"].get(profile)
    if strat:
        strat.clear_history()

    if profile == state.get("active_profile"):
        send_stats_update(cid)

    return jsonify({"status": "cleared", "profile": profile})


@app.route("/set_profile", methods=["POST"])
def set_profile():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    profile = request.json.get("profile", "KOOLKID")

    if profile not in state["strategies"]:
        return jsonify({"error": "Invalid profile"}), 400

    state["active_profile"] = profile
    socketio.emit("profile_update", {"profile": profile}, room=cid)
    send_stats_update(cid)

    if profile == "JOKERJOE":
        jj = state["strategies"].get("JOKERJOE")
        if jj:
            emit_jokerjoe_modes(cid, jj)

    return jsonify({"status": "success", "profile": profile})


@app.route("/change_market", methods=["POST"])
def change_market():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    symbol = request.json.get("symbol")

    if not symbol:
        return jsonify({"error": "No symbol provided"}), 400

    state["current_symbol"] = symbol

    strategy = state["strategies"].get(state["active_profile"])
    if strategy:
        strategy.reset_tick_analysis()

    ws = state.get("ws")
    if state.get("ws_connected") and ws:
        try:
            ws.send(json.dumps({"forget_all": "ticks"}))
            ws.send(json.dumps({"ticks": state["current_symbol"], "subscribe": 1}))
        except Exception:
            pass

    socketio.emit("market_change", {"symbol": state["current_symbol"]}, room=cid)
    return jsonify({"status": "success", "symbol": state["current_symbol"]})


@app.route("/set_risk_controls", methods=["POST"])
def set_risk_controls():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()

    data = request.json
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
    if not strategy:
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


@app.route("/set_kidracks_settings", methods=["POST"])
def set_kidracks_settings():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    data = request.json
    barrier = int(data.get("barrier", 5))

    strat = state["strategies"].get("KOOLKID")
    strat.kidracks_barrier = barrier

    return jsonify({"status": "success"})


@app.route("/set_koolkidspeed_settings", methods=["POST"])
def set_koolkidspeed_settings():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    cid, state = get_client_state()
    data = request.json
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
    data = request.json

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
    data = request.json

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
    data = request.json

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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    print("""
╔══════════════════════════════════════════════════════════════╗
║     🚀 KOOLKID AI BOT SERVER (TRUE MULTI-USER MODE)          ║
║     - Per-session client_id                                  ║
║     - Separate WS + state per browser/device                 ║
║     - KOOLKID / JOKERJOE / HUMAN                             ║
║     - ✅ Fixed toaster payloads                               ║
║     - ✅ Per-profile clear history route                      ║
╚══════════════════════════════════════════════════════════════╝
    """)

    socketio.run(app, host="0.0.0.0", port=port, debug=True, allow_unsafe_werkzeug=True)