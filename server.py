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
        "current_symbol": "R_25",
        "human_symbol": "R_25",
        "tick_subs": {},
        "humanx_auto": False,
        "humanx_status_last": "Auto: OFF",
        "balance": 0.0,
        "session_start_balance": None,
        "auto_stake": 1.0,
        "req_meta": {},          # req_id -> meta
        "contract_meta": {},     # contract_id -> meta
        "last_seen": time.time(),  # heartbeat (page open)
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
    _touch_client(cid)
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
    if not state or not state.get("ws_connected"):
        return False, "Not connected"

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

    req_id = _new_req_id()
    state["req_meta"][req_id] = {
        "profile": profile_to_use,
        "type": f"MULT {direction}",
        "barrier": None,
        "stake": stake,
        "symbol": symbol_to_use,
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
            "symbol": symbol_to_use,
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

        strategies = state.get("strategies", {})
        strategy = strategies.get(state.get("active_profile", "KOOLKID"))

        if strategy:
            try:
                strategy.on_contract(contract, state["balance"])
            except Exception:
                pass

        contract_id = contract.get("contract_id")
        meta = state["contract_meta"].pop(contract_id, None) if contract_id else None

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
            entry.setdefault("profile", state.get("active_profile", "KOOLKID"))

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


# ---------------- HEARTBEAT SWEEPER ---------------- #
def heartbeat_sweeper():
    while True:
        time.sleep(30)
        now = time.time()
        for cid, state in list(clients.items()):
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