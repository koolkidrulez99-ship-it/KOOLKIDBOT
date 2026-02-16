import os, sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import json
import threading
import websocket
import time
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

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

DERIV_WS = "wss://ws.derivws.com/websockets/v3?app_id=1089"

# DATABASE FILE
DB_FILE = "users.db"

# ===================================
# PER-USER STATE (TRUE MULTI-USER)
# ===================================
user_sessions = {}
sessions_lock = threading.Lock()


def get_user_state(username: str):
    """
    Get or create state bucket for a given username.
    This is where we keep that user's:
      - Deriv WS connection
      - api_token
      - active_profile
      - strategies
      - balance, symbol, etc.
    """
    if not username:
        return None

    with sessions_lock:
        if username not in user_sessions:
            user_sessions[username] = {
                "api_token": "",
                "ws": None,
                "ws_connected": False,
                "active_profile": "KOOLKID",
                "current_symbol": "R_25",
                "balance": 0.0,
                "session_start_balance": None,
                "auto_stake": 1.0,
                "strategies": {
                    "KOOLKID": KoolKidStrategy(),
                    "JOKERJOE": JokerJoeStrategy(),
                    "HUMAN": HumanStrategy()
                },
            }
        return user_sessions[username]


# ---------------- DATABASE SETUP ---------------- #
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute(
        """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )
    """
    )

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


# Initialize DB
init_db()
ensure_admin_user()


# ---------------- HELPERS ---------------- #
def now_time():
    return datetime.now().strftime("%H:%M:%S")


def extract_last_decimal_digit(price, pip_size=2):
    try:
        # NOTE: fixed format string
        fmt = "{:0." + str(int(pip_size)) + "f}"
        price_str = fmt.format(float(price))

        if "." not in price_str:
            return int(price_str[-1])

        decimal_part = price_str.split(".")[1]
        return int(decimal_part[-1])
    except Exception:
        return 0


# ---------------- LOGIN REQUIRED CHECK ---------------- #
def login_required():
    return "user" in session


def is_admin():
    return session.get("user", "").lower() == ADMIN_USERNAME.lower()


# ---------------- SOCKET.IO CONNECTION ---------------- #
@socketio.on("connect")
def handle_socket_connect():
    """
    When a browser connects via Socket.IO, drop them
    into a room named by their username so we can emit
    per-user events from the WS threads.
    """
    username = session.get("user")
    if not username:
        # reject unauthorized socket connections
        return False

    join_room(username)
    logger.info(f"🔌 Socket.IO connected for user {username}")


# ---------------- ROUTES (LOGIN SYSTEM) ---------------- #
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if verify_user(username, password):
            session["user"] = username
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
    username = session.get("user")
    session.pop("user", None)

    # Optionally, also close that user's WS here
    if username:
        state = get_user_state(username)
        ws = state.get("ws")
        if ws:
            try:
                ws.close()
            except Exception:
                pass
            state["ws"] = None
            state["ws_connected"] = False

    return redirect(url_for("login"))


# ---------------- BOT ROUTE (PROTECTED) ---------------- #
@app.route("/")
def index():
    if not login_required():
        return redirect(url_for("login"))

    return render_template("index.html", username=session.get("user"))


# ---------------- PER-USER DERIV BUY FUNCTION ---------------- #
def send_buy(username, contract_type, stake, symbol, barrier):
    state = get_user_state(username)
    if not state:
        return False, "No user session"

    ws = state.get("ws")
    ws_connected = state.get("ws_connected", False)

    if not ws or not ws_connected:
        return False, "Not connected"

    contract_map = {
        "OVER": "DIGITOVER",
        "UNDER": "DIGITUNDER",
        "MATCHES": "DIGITMATCH",
        "DIFFERS": "DIGITDIFF",
    }

    if contract_type not in contract_map:
        return False, "Invalid contract type"

    deriv_contract = contract_map[contract_type]

    payload = {
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
            "barrier": int(barrier),
        },
    }

    try:
        ws.send(json.dumps(payload))
        return True, "Trade sent"
    except Exception as e:
        return False, str(e)


# ---------------- AUTO TRADE ENGINE (PER USER) ---------------- #
def run_auto_trade(username, strategy):
    """
    Run all KoolKid auto engines for ONE USER.
    Uses that user's auto_stake + active profile.
    Requires master AUTO to be ON.
    """
    if not strategy or not getattr(strategy, "auto_trade", False):
        return

    state = get_user_state(username)
    if not state:
        return

    if state.get("active_profile") != "KOOLKID":
        return

    if not hasattr(strategy, "check_auto_trade_signal"):
        return

    signals = strategy.check_auto_trade_signal()
    if not signals:
        return

    if isinstance(signals, dict):
        signals = [signals]

    auto_stake = float(state.get("auto_stake", 1.0))
    symbol = state.get("current_symbol", "R_25")

    for sig in signals:
        try:
            ctype = sig.get("type")
            barrier = sig.get("barrier")

            # Force using per-user auto_stake
            ok, msg = send_buy(username, ctype, auto_stake, symbol, barrier)

            if ok:
                socketio.emit(
                    "trade_placed",
                    {
                        "type": ctype,
                        "barrier": barrier,
                        "stake": auto_stake,
                        "symbol": symbol,
                        "mode": sig.get("mode", "AUTO"),
                    },
                    room=username,
                )
                logger.info(f"🤖 [{username}] AUTO TRADE SENT: {ctype} barrier={barrier} stake={auto_stake}")
            else:
                logger.error(f"❌ [{username}] AUTO TRADE FAILED: {msg}")
        except Exception as e:
            logger.error(f"Auto trade error for {username}: {e}")


# ---------------- WEBSOCKET HANDLERS (PER USER WRAPPERS) ---------------- #
def handle_on_message(username, ws, message):
    state = get_user_state(username)
    if not state:
        return

    try:
        data = json.loads(message)

        if "error" in data:
            msg = data["error"].get("message", "Unknown API Error")
            logger.error(f"[{username}] API Error: {msg}")
            socketio.emit("api_error", {"message": msg}, room=username)
            return

        # AUTH SUCCESS
        if "authorize" in data:
            state["ws_connected"] = True
            loginid = data["authorize"].get("loginid", "UNKNOWN")
            balance = float(data["authorize"].get("balance", 0.0))
            state["balance"] = balance

            if state["session_start_balance"] is None:
                state["session_start_balance"] = balance

            logger.info(f"✅ [{username}] Authorized: {loginid} Balance={balance}")

            socketio.emit(
                "connection_status",
                {
                    "connected": True,
                    "loginid": loginid,
                    "balance": balance,
                },
                room=username,
            )

            socketio.emit("balance_update", {"balance": balance}, room=username)
            send_stats_update(username)

            # Subscribe tick + balance
            ws.send(json.dumps({"ticks": state["current_symbol"], "subscribe": 1}))
            ws.send(json.dumps({"balance": 1, "subscribe": 1}))

        # BALANCE STREAM
        if "balance" in data:
            try:
                bal = float(data["balance"]["balance"])
                state["balance"] = bal
                socketio.emit("balance_update", {"balance": bal}, room=username)
                send_stats_update(username)
            except Exception:
                pass

        # TICK STREAM
        if "tick" in data:
            tick = data["tick"]
            process_tick(username, tick)

        # BUY CONFIRMATION
        if "buy" in data:
            socketio.emit("trade_placed", data["buy"], room=username)

            contract_id = data["buy"].get("contract_id")
            if contract_id:
                ws.send(
                    json.dumps(
                        {
                            "proposal_open_contract": 1,
                            "contract_id": contract_id,
                            "subscribe": 1,
                        }
                    )
                )

        # CONTRACT UPDATES
        if "proposal_open_contract" in data:
            contract = data["proposal_open_contract"]
            process_contract(username, contract)

    except Exception as e:
        logger.error(f"[{username}] on_message error: {e}")


def process_tick(username, tick):
    try:
        state = get_user_state(username)
        if not state:
            return

        symbol = tick.get("symbol")
        price = tick.get("quote")

        if symbol != state.get("current_symbol"):
            return

        pip_size = tick.get("pip_size", 2)
        digit = extract_last_decimal_digit(price, pip_size)

        strategies = state["strategies"]
        active_profile = state["active_profile"]
        strategy = strategies.get(active_profile)

        if strategy:
            strategy.on_tick(tick, digit)

        socketio.emit(
            "tick",
            {
                "symbol": symbol,
                "digit": digit,
                "price": price,
                "tick_count": strategy.tick_count if strategy else 0,
                "timestamp": now_time(),
            },
            room=username,
        )

        if strategy:
            socketio.emit("digit_analysis", strategy.get_ui_payload(), room=username)

        # AUTO trade engine (only KoolKid, only if AUTO is ON)
        if active_profile == "KOOLKID":
            run_auto_trade(username, strategy)

    except Exception as e:
        logger.error(f"[{username}] process_tick error: {e}")


def process_contract(username, contract):
    try:
        state = get_user_state(username)
        if not state:
            return

        if not (contract.get("is_sold") or contract.get("is_settled")):
            return

        profit = float(contract.get("profit", 0))
        state["balance"] = float(state.get("balance", 0.0)) + profit

        strategies = state["strategies"]
        strategy = strategies.get(state["active_profile"])

        if strategy:
            strategy.on_contract(contract, state["balance"])

        socketio.emit(
            "trade_result",
            strategy.get_last_trade_entry() if strategy else {},
            room=username,
        )
        send_stats_update(username)

    except Exception as e:
        logger.error(f"[{username}] process_contract error: {e}")


def send_stats_update(username):
    state = get_user_state(username)
    if not state:
        return

    strategies = state["strategies"]
    active_profile = state["active_profile"]
    strategy = strategies.get(active_profile)

    if not strategy:
        return

    payload = strategy.get_stats_payload(state.get("balance", 0.0), state.get("session_start_balance"))
    payload["profile"] = active_profile

    socketio.emit("stats_update", payload, room=username)


def handle_on_open(username, ws):
    logger.info(f"🔌 [{username}] WebSocket Connected")
    state = get_user_state(username)
    if not state:
        return
    state["ws_connected"] = True

    token = state.get("api_token")
    if token:
        ws.send(json.dumps({"authorize": token}))


def handle_on_error(username, ws, error):
    logger.error(f"[{username}] WebSocket Error: {error}")
    socketio.emit("api_error", {"message": str(error)}, room=username)


def handle_on_close(username, ws, code, msg):
    logger.warning(f"🔌 [{username}] WebSocket Disconnected ({code}) {msg}")
    state = get_user_state(username)
    if not state:
        return
    state["ws_connected"] = False
    state["ws"] = None
    socketio.emit("connection_status", {"connected": False}, room=username)


def start_ws_for_user(username):
    """
    Start a dedicated Deriv WebSocket for ONE user.
    """
    state = get_user_state(username)
    if not state:
        return

    def _on_message(ws, message):
        handle_on_message(username, ws, message)

    def _on_open(ws):
        handle_on_open(username, ws)

    def _on_error(ws, error):
        handle_on_error(username, ws, error)

    def _on_close(ws, code, msg):
        handle_on_close(username, ws, code, msg)

    ws_app = websocket.WebSocketApp(
        DERIV_WS,
        on_message=_on_message,
        on_open=_on_open,
        on_error=_on_error,
        on_close=_on_close,
    )

    state["ws"] = ws_app
    ws_app.run_forever(ping_interval=30)


# ---------------- BOT API ROUTES ---------------- #
@app.route("/set_token", methods=["POST"])
def set_token():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    username = session.get("user")
    state = get_user_state(username)
    if not state:
        return jsonify({"error": "No user session"}), 400

    token = request.json.get("token", "")
    state["api_token"] = token
    state["session_start_balance"] = None

    # Close old WS if any
    old_ws = state.get("ws")
    if old_ws:
        try:
            old_ws.close()
        except Exception:
            pass
        state["ws"] = None
        state["ws_connected"] = False

    threading.Thread(target=start_ws_for_user, args=(username,), daemon=True).start()
    return jsonify({"status": "connecting"})


@app.route("/set_auto_stake", methods=["POST"])
def set_auto_stake():
    """
    Per-user AUTO stake (used by ALL auto modes).
    """
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    username = session.get("user")
    state = get_user_state(username)
    if not state:
        return jsonify({"error": "No user session"}), 400

    try:
        stake = float(request.json.get("stake", 1))
        if stake <= 0:
            stake = 1.0
    except Exception:
        stake = 1.0

    state["auto_stake"] = stake
    logger.info(f"💰 [{username}] AUTO STAKE UPDATED: {stake}")

    return jsonify({"status": "success", "auto_stake": stake})


@app.route("/disconnect", methods=["POST"])
def disconnect():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    username = session.get("user")
    state = get_user_state(username)
    if not state:
        return jsonify({"error": "No user session"}), 400

    ws = state.get("ws")
    if ws:
        try:
            ws.close()
        except Exception:
            pass

    # Reset this user's state (but keep strategies objects so history clears via reset)
    state["ws"] = None
    state["ws_connected"] = False
    state["api_token"] = ""
    state["balance"] = 0.0
    state["session_start_balance"] = None

    for strat in state["strategies"].values():
        strat.reset()

    socketio.emit("connection_status", {"connected": False}, room=username)
    socketio.emit("reset_ui", room=username)
    send_stats_update(username)

    return jsonify({"status": "disconnected"})


@app.route("/clear_history", methods=["POST"])
def clear_history():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    username = session.get("user")
    state = get_user_state(username)
    if not state:
        return jsonify({"error": "No user session"}), 400

    strategies = state["strategies"]
    strat = strategies.get(state["active_profile"])
    if strat:
        strat.clear_history()

    socketio.emit("history_cleared", room=username)
    send_stats_update(username)
    return jsonify({"status": "cleared"})


@app.route("/set_profile", methods=["POST"])
def set_profile():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    username = session.get("user")
    state = get_user_state(username)
    if not state:
        return jsonify({"error": "No user session"}), 400

    profile = request.json.get("profile", "KOOLKID")

    if profile not in state["strategies"]:
        return jsonify({"error": "Invalid profile"}), 400

    state["active_profile"] = profile
    socketio.emit("profile_update", {"profile": profile}, room=username)
    send_stats_update(username)

    return jsonify({"status": "success", "profile": profile})


@app.route("/change_market", methods=["POST"])
def change_market():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    username = session.get("user")
    state = get_user_state(username)
    if not state:
        return jsonify({"error": "No user session"}), 400

    symbol = request.json.get("symbol")

    if not symbol:
        return jsonify({"error": "No symbol provided"}), 400

    state["current_symbol"] = symbol

    strat = state["strategies"].get(state["active_profile"])
    if strat:
        strat.reset_tick_analysis()

    ws = state.get("ws")
    if state.get("ws_connected") and ws:
        try:
            ws.send(json.dumps({"forget_all": "ticks"}))
            ws.send(json.dumps({"ticks": state["current_symbol"], "subscribe": 1}))
        except Exception:
            pass

    socketio.emit("market_change", {"symbol": state["current_symbol"]}, room=username)
    return jsonify({"status": "success", "symbol": state["current_symbol"]})


# ---------------- RISK CONTROL ROUTE ---------------- #
@app.route("/set_risk_controls", methods=["POST"])
def set_risk_controls():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    username = session.get("user")
    state = get_user_state(username)
    if not state:
        return jsonify({"error": "No user session"}), 400

    data = request.json
    tp = float(data.get("tp", 0))
    sl = float(data.get("sl", 0))
    auto_sl = bool(data.get("auto_sl", True))

    strat = state["strategies"].get(state["active_profile"])
    if strat:
        strat.set_risk_controls(tp=tp, sl=sl, auto_sl=auto_sl)

    return jsonify({"status": "success"})


# ---------------- MASTER AUTO TOGGLE ---------------- #
@app.route("/toggle_auto", methods=["POST"])
def toggle_auto():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    username = session.get("user")
    state = get_user_state(username)
    if not state:
        return jsonify({"error": "No user session"}), 400

    strat = state["strategies"].get(state["active_profile"])
    if not strat:
        return jsonify({"status": "error", "message": "No strategy loaded"}), 400

    new_state = strat.toggle_auto()
    send_stats_update(username)

    return jsonify({"status": "success", "auto_trade": new_state})


# ---------------- AUTO MODE ROUTES ---------------- #
@app.route("/toggle_kidracks_auto", methods=["POST"])
def toggle_kidracks_auto_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    username = session.get("user")
    state = get_user_state(username)
    if not state:
        return jsonify({"error": "No user session"}), 400

    strat = state["strategies"].get("KOOLKID")
    state_flag = strat.toggle_kidracks_auto()

    socketio.emit("auto_mode_update", strat.get_ui_payload().get("auto_modes", {}), room=username)

    return jsonify({"status": "success", "kidracks_auto": state_flag})


@app.route("/toggle_koolkidspeed_auto", methods=["POST"])
def toggle_koolkidspeed_auto_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    username = session.get("user")
    state = get_user_state(username)
    if not state:
        return jsonify({"error": "No user session"}), 400

    strat = state["strategies"].get("KOOLKID")
    state_flag = strat.toggle_koolkidspeed_auto()

    socketio.emit("auto_mode_update", strat.get_ui_payload().get("auto_modes", {}), room=username)

    return jsonify({"status": "success", "koolkidspeed_auto": state_flag})


@app.route("/toggle_koolluck_auto", methods=["POST"])
def toggle_koolluck_auto_route():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    username = session.get("user")
    state = get_user_state(username)
    if not state:
        return jsonify({"error": "No user session"}), 400

    strat = state["strategies"].get("KOOLKID")
    state_flag = strat.toggle_koolluck_auto()

    socketio.emit("auto_mode_update", strat.get_ui_payload().get("auto_modes", {}), room=username)

    return jsonify({"status": "success", "koolluck_auto": state_flag})


@app.route("/set_kidracks_settings", methods=["POST"])
def set_kidracks_settings():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    username = session.get("user")
    state = get_user_state(username)
    if not state:
        return jsonify({"error": "No user session"}), 400

    data = request.json
    barrier = int(data.get("barrier", 5))

    strat = state["strategies"].get("KOOLKID")
    strat.kidracks_barrier = barrier

    return jsonify({"status": "success"})


@app.route("/set_koolkidspeed_settings", methods=["POST"])
def set_koolkidspeed_settings():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    username = session.get("user")
    state = get_user_state(username)
    if not state:
        return jsonify({"error": "No user session"}), 400

    data = request.json
    barrier = int(data.get("barrier", 5))

    strat = state["strategies"].get("KOOLKID")
    strat.koolkidspeed_barrier = barrier

    return jsonify({"status": "success"})


# ---------------- MANUAL TRADING ROUTES ---------------- #
@app.route("/manual_trade", methods=["POST"])
def manual_trade():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    username = session.get("user")
    state = get_user_state(username)
    if not state:
        return jsonify({"error": "No user session"}), 400

    data = request.json

    contract_type = data.get("type")
    stake = float(data.get("stake", 1))
    symbol = data.get("symbol", state.get("current_symbol", "R_25"))
    barrier = int(data.get("barrier", 5))

    ok, msg = send_buy(username, contract_type, stake, symbol, barrier)
    return jsonify({"status": "success" if ok else "error", "message": msg})


@app.route("/manual_3_trades", methods=["POST"])
def manual_3_trades():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    username = session.get("user")
    state = get_user_state(username)
    if not state:
        return jsonify({"error": "No user session"}), 400

    data = request.json

    contract_type = data.get("type")
    stake = float(data.get("stake", 1))
    symbol = data.get("symbol", state.get("current_symbol", "R_25"))
    barrier = int(data.get("barrier", 5))

    placed = 0
    for _ in range(3):
        ok, _msg = send_buy(username, contract_type, stake, symbol, barrier)
        if ok:
            placed += 1
        time.sleep(0.15)

    return jsonify({"status": "success", "placed": placed})


@app.route("/burst_4", methods=["POST"])
def burst_4():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    username = session.get("user")
    state = get_user_state(username)
    if not state:
        return jsonify({"error": "No user session"}), 400

    data = request.json

    contract_type = data.get("type")
    stake = float(data.get("stake", 1))
    symbol = data.get("symbol", state.get("current_symbol", "R_25"))
    barrier = int(data.get("barrier", 5))

    placed = 0
    for _ in range(4):
        ok, _msg = send_buy(username, contract_type, stake, symbol, barrier)
        if ok:
            placed += 1
        time.sleep(0.10)

    return jsonify({"status": "success", "placed": placed})


# ---------------- MAIN ENTRY ---------------- #
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    print(
        """
╔══════════════════════════════════════════════════════════════╗
║     🚀 KOOLKID AI BOT SERVER (TRUE MULTI-USER MODE)          ║
║     - Each user has their own Deriv WS & strategies          ║
║     - Admin + Users + Max Users Limit                        ║
║     - KidRacks / KoolKidspeed / KOOL🍀KID LUCK auto modes    ║
╚══════════════════════════════════════════════════════════════╝
    """
    )

    socketio.run(app, host="0.0.0.0", port=port, debug=True, allow_unsafe_werkzeug=True)
