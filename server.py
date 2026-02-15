import os, sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import json
import threading
import websocket
import time
import sqlite3
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_socketio import SocketIO, join_room, leave_room
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
app.config["SECRET_KEY"] = "koolkid-secret-key-2025"

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

DERIV_WS = "wss://ws.derivws.com/websockets/v3?app_id=1089"

# DATABASE FILE
DB_FILE = "users.db"


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


def create_user(username, password):
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
    except:
        return 0


def login_required():
    return "user" in session


def get_username():
    return session.get("user")


def get_room(username):
    return f"user_{username}"


# ---------------- MULTI USER BOT STORAGE ---------------- #
user_bots = {}
user_lock = threading.Lock()


def create_user_bot(username):
    """
    Creates bot state for a user if not existing.
    """
    with user_lock:
        if username not in user_bots:
            user_bots[username] = {
                "api_token": "",
                "ws": None,
                "ws_connected": False,
                "active_profile": "KOOLKID",
                "current_symbol": "R_25",
                "balance": 0.0,
                "session_start_balance": None,
                "strategies": {
                    "KOOLKID": KoolKidStrategy(),
                    "JOKERJOE": JokerJoeStrategy(),
                    "HUMAN": HumanStrategy()
                }
            }


def reset_user_bot(username):
    with user_lock:
        if username in user_bots:
            bot = user_bots[username]

            try:
                if bot["ws"]:
                    bot["ws"].close()
            except:
                pass

            bot["api_token"] = ""
            bot["ws"] = None
            bot["ws_connected"] = False
            bot["balance"] = 0.0
            bot["session_start_balance"] = None
            bot["active_profile"] = "KOOLKID"
            bot["current_symbol"] = "R_25"

            for strat in bot["strategies"].values():
                strat.reset()


# ---------------- SOCKET.IO ROOM JOIN ---------------- #
@socketio.on("connect")
def on_socket_connect():
    if login_required():
        username = get_username()
        join_room(get_room(username))
        logger.info(f"🟢 Socket joined room: {get_room(username)}")


@socketio.on("disconnect")
def on_socket_disconnect():
    if login_required():
        username = get_username()
        leave_room(get_room(username))
        logger.info(f"🔴 Socket left room: {get_room(username)}")


# ---------------- ROUTES (LOGIN SYSTEM) ---------------- #
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if verify_user(username, password):
            session["user"] = username
            create_user_bot(username)
            return redirect(url_for("index"))
        else:
            return render_template("login.html", error="Invalid username or password")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        ok, msg = create_user(username, password)

        if ok:
            return redirect(url_for("login"))
        else:
            return render_template("register.html", error=msg)

    return render_template("register.html")


@app.route("/logout")
def logout():
    username = session.get("user")
    if username:
        reset_user_bot(username)

    session.pop("user", None)
    return redirect(url_for("login"))


# ---------------- BOT ROUTE (PROTECTED) ---------------- #
@app.route("/")
def index():
    if not login_required():
        return redirect(url_for("login"))

    return render_template("index.html", username=session.get("user"))


# ---------------- DERIV BUY FUNCTION ---------------- #
def send_buy(username, contract_type, stake, symbol, barrier):
    bot = user_bots.get(username)

    if not bot:
        return False, "Bot not found"

    ws = bot["ws"]

    if not bot["ws_connected"] or not ws:
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
            "barrier": int(barrier)
        }
    }

    try:
        ws.send(json.dumps(payload))
        return True, "Trade sent"
    except Exception as e:
        return False, str(e)


# ---------------- WEBSOCKET HANDLERS ---------------- #
def on_message(username, ws, message):
    bot = user_bots.get(username)
    if not bot:
        return

    try:
        data = json.loads(message)
        room = get_room(username)

        if "error" in data:
            msg = data["error"].get("message", "Unknown API Error")
            logger.error(f"API Error [{username}]: {msg}")
            socketio.emit("api_error", {"message": msg}, room=room)
            return

        # AUTH SUCCESS
        if "authorize" in data:
            bot["ws_connected"] = True
            loginid = data["authorize"].get("loginid", "UNKNOWN")
            bot["balance"] = float(data["authorize"].get("balance", 0))

            if bot["session_start_balance"] is None:
                bot["session_start_balance"] = bot["balance"]

            logger.info(f"✅ Authorized [{username}]: {loginid} Balance={bot['balance']}")

            socketio.emit("connection_status", {
                "connected": True,
                "loginid": loginid,
                "balance": bot["balance"]
            }, room=room)

            socketio.emit("balance_update", {"balance": bot["balance"]}, room=room)

            send_stats_update(username)

            # Subscribe tick + balance
            ws.send(json.dumps({"ticks": bot["current_symbol"], "subscribe": 1}))
            ws.send(json.dumps({"balance": 1, "subscribe": 1}))

        # BALANCE STREAM
        if "balance" in data:
            try:
                bot["balance"] = float(data["balance"]["balance"])
                socketio.emit("balance_update", {"balance": bot["balance"]}, room=room)
                send_stats_update(username)
            except:
                pass

        # TICK STREAM
        if "tick" in data:
            tick = data["tick"]
            process_tick(username, tick)

        # BUY CONFIRMATION
        if "buy" in data:
            socketio.emit("trade_placed", data["buy"], room=room)

            contract_id = data["buy"].get("contract_id")
            if contract_id:
                ws.send(json.dumps({
                    "proposal_open_contract": 1,
                    "contract_id": contract_id,
                    "subscribe": 1
                }))

        # CONTRACT UPDATES
        if "proposal_open_contract" in data:
            contract = data["proposal_open_contract"]
            process_contract(username, contract)

    except Exception as e:
        logger.error(f"on_message error [{username}]: {e}")


def process_tick(username, tick):
    bot = user_bots.get(username)
    if not bot:
        return

    try:
        symbol = tick.get("symbol")
        price = tick.get("quote")

        if symbol != bot["current_symbol"]:
            return

        pip_size = tick.get("pip_size", 2)
        digit = extract_last_decimal_digit(price, pip_size)

        strategy = bot["strategies"].get(bot["active_profile"])
        if strategy:
            strategy.on_tick(tick, digit)

        socketio.emit("tick", {
            "symbol": symbol,
            "digit": digit,
            "price": price,
            "tick_count": strategy.tick_count if strategy else 0,
            "timestamp": now_time()
        }, room=get_room(username))

        if strategy:
            socketio.emit("digit_analysis", strategy.get_ui_payload(), room=get_room(username))

    except Exception as e:
        logger.error(f"process_tick error [{username}]: {e}")


def process_contract(username, contract):
    bot = user_bots.get(username)
    if not bot:
        return

    try:
        if not (contract.get("is_sold") or contract.get("is_settled")):
            return

        profit = float(contract.get("profit", 0))
        bot["balance"] = float(bot["balance"]) + profit

        strategy = bot["strategies"].get(bot["active_profile"])
        if strategy:
            strategy.on_contract(contract, bot["balance"])

        socketio.emit("trade_result", strategy.get_last_trade_entry() if strategy else {}, room=get_room(username))
        send_stats_update(username)

    except Exception as e:
        logger.error(f"process_contract error [{username}]: {e}")


def send_stats_update(username):
    bot = user_bots.get(username)
    if not bot:
        return

    strategy = bot["strategies"].get(bot["active_profile"])
    if not strategy:
        return

    payload = strategy.get_stats_payload(bot["balance"], bot["session_start_balance"])
    payload["profile"] = bot["active_profile"]

    socketio.emit("stats_update", payload, room=get_room(username))


def on_open(username, ws):
    bot = user_bots.get(username)
    if not bot:
        return

    logger.info(f"🔌 WebSocket Connected [{username}]")
    bot["ws_connected"] = True

    if bot["api_token"]:
        ws.send(json.dumps({"authorize": bot["api_token"]}))


def on_error(username, ws, error):
    logger.error(f"WebSocket Error [{username}]: {error}")
    socketio.emit("api_error", {"message": str(error)}, room=get_room(username))


def on_close(username, ws, code, msg):
    bot = user_bots.get(username)
    if not bot:
        return

    bot["ws_connected"] = False
    logger.warning(f"🔌 WebSocket Disconnected [{username}]")
    socketio.emit("connection_status", {"connected": False}, room=get_room(username))


def start_ws(username):
    bot = user_bots.get(username)
    if not bot:
        return

    def _on_message(ws, message):
        on_message(username, ws, message)

    def _on_open(ws):
        on_open(username, ws)

    def _on_error(ws, error):
        on_error(username, ws, error)

    def _on_close(ws, code, msg):
        on_close(username, ws, code, msg)

    bot["ws"] = websocket.WebSocketApp(
        DERIV_WS,
        on_message=_on_message,
        on_open=_on_open,
        on_error=_on_error,
        on_close=_on_close
    )

    bot["ws"].run_forever(ping_interval=30)


# ---------------- BOT API ROUTES (PROTECTED) ---------------- #
@app.route("/set_token", methods=["POST"])
def set_token():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    username = get_username()
    create_user_bot(username)

    bot = user_bots[username]

    bot["api_token"] = request.json.get("token", "")
    bot["session_start_balance"] = None

    threading.Thread(target=start_ws, args=(username,), daemon=True).start()
    return jsonify({"status": "connecting"})


@app.route("/disconnect", methods=["POST"])
def disconnect():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    username = get_username()
    reset_user_bot(username)

    socketio.emit("connection_status", {"connected": False}, room=get_room(username))
    socketio.emit("reset_ui", room=get_room(username))
    send_stats_update(username)

    return jsonify({"status": "disconnected"})


@app.route("/clear_history", methods=["POST"])
def clear_history():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    username = get_username()
    bot = user_bots.get(username)

    if bot:
        strategy = bot["strategies"].get(bot["active_profile"])
        if strategy:
            strategy.clear_history()

    socketio.emit("history_cleared", room=get_room(username))
    send_stats_update(username)
    return jsonify({"status": "cleared"})


@app.route("/set_profile", methods=["POST"])
def set_profile():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    username = get_username()
    bot = user_bots.get(username)

    profile = request.json.get("profile", "KOOLKID")

    if profile not in ["KOOLKID", "JOKERJOE", "HUMAN"]:
        return jsonify({"error": "Invalid profile"}), 400

    bot["active_profile"] = profile

    socketio.emit("profile_update", {"profile": profile}, room=get_room(username))
    send_stats_update(username)

    return jsonify({"status": "success", "profile": profile})


@app.route("/change_market", methods=["POST"])
def change_market():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    username = get_username()
    bot = user_bots.get(username)

    symbol = request.json.get("symbol")

    if not symbol:
        return jsonify({"error": "No symbol provided"}), 400

    bot["current_symbol"] = symbol

    strategy = bot["strategies"].get(bot["active_profile"])
    if strategy:
        strategy.reset_tick_analysis()

    if bot["ws_connected"] and bot["ws"]:
        try:
            bot["ws"].send(json.dumps({"forget_all": "ticks"}))
            bot["ws"].send(json.dumps({"ticks": bot["current_symbol"], "subscribe": 1}))
        except:
            pass

    socketio.emit("market_change", {"symbol": bot["current_symbol"]}, room=get_room(username))
    return jsonify({"status": "success", "symbol": bot["current_symbol"]})


@app.route("/toggle_auto", methods=["POST"])
def toggle_auto():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    username = get_username()
    bot = user_bots.get(username)

    strategy = bot["strategies"].get(bot["active_profile"])
    if not strategy:
        return jsonify({"status": "error", "message": "No strategy loaded"}), 400

    new_state = strategy.toggle_auto()
    send_stats_update(username)

    return jsonify({"status": "success", "auto_trade": new_state})


@app.route("/manual_trade", methods=["POST"])
def manual_trade():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    username = get_username()
    bot = user_bots.get(username)

    data = request.json

    contract_type = data.get("type")
    stake = float(data.get("stake", 1))
    symbol = data.get("symbol", bot["current_symbol"])
    barrier = int(data.get("barrier", 5))

    ok, msg = send_buy(username, contract_type, stake, symbol, barrier)
    return jsonify({"status": "success" if ok else "error", "message": msg})


@app.route("/manual_3_trades", methods=["POST"])
def manual_3_trades():
    if not login_required():
        return jsonify({"error": "Unauthorized"}), 403

    username = get_username()
    bot = user_bots.get(username)

    data = request.json

    contract_type = data.get("type")
    stake = float(data.get("stake", 1))
    symbol = data.get("symbol", bot["current_symbol"])
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

    username = get_username()
    bot = user_bots.get(username)

    data = request.json

    contract_type = data.get("type")
    stake = float(data.get("stake", 1))
    symbol = data.get("symbol", bot["current_symbol"])
    barrier = int(data.get("barrier", 5))

    placed = 0
    for _ in range(4):
        ok, _msg = send_buy(username, contract_type, stake, symbol, barrier)
        if ok:
            placed += 1
        time.sleep(0.10)

    return jsonify({"status": "success", "placed": placed})


# ---------------- MAIN ENTRY (RENDER SAFE) ---------------- #
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    print("""
╔══════════════════════════════════════════════════════════════╗
║     🚀 KOOLKID AI BOT SERVER (MULTI USER BUILD)              ║
║     - SQLite Users Database                                 ║
║     - Each user has own Deriv WS + Token                     ║
║     - Multi-user safe (rooms + isolated strategies)          ║
╚══════════════════════════════════════════════════════════════╝
    """)

    socketio.run(app, host="0.0.0.0", port=port, debug=True, allow_unsafe_werkzeug=True)
