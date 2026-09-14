from __future__ import annotations

import hashlib
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from dotenv import load_dotenv
from fastapi import Body, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

import engine
import ea_worker_client
import multi_account_client
from store import default_risk, read_state, remove_profile, update_state

app = FastAPI(title="KOOLKID Local MT5 Bridge", version="1.0.0")

EA_LIBRARY = ROOT / "data" / "ea_library"
EA_LIBRARY.mkdir(parents=True, exist_ok=True)
MAX_EA_FILE_BYTES = 25 * 1024 * 1024
_stats_history_lock = threading.Lock()
_stats_history_cache: dict[str, Any] = {"session_key": "", "loaded_at": 0.0, "rows": []}
_SECRET_INPUT = re.compile(r"(?:password|passwd|token|secret|license|licence|api.?key)", re.IGNORECASE)


def _safe_upload_name(name: str, extension: str) -> str:
    base = Path(name or "").name
    if not base.lower().endswith(extension):
        raise HTTPException(status_code=400, detail=f"Expected a {extension} file.")
    base = re.sub(r"[^A-Za-z0-9._() -]+", "_", base).strip(" .")
    if not base:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    return base


async def _save_upload(file: UploadFile, dest: Path, extension: str) -> dict[str, Any]:
    filename = _safe_upload_name(file.filename or "", extension)
    data = await file.read(MAX_EA_FILE_BYTES + 1)
    if len(data) > MAX_EA_FILE_BYTES:
        raise HTTPException(status_code=413, detail=f"{filename} exceeds the 25 MB upload limit.")
    if not data:
        raise HTTPException(status_code=400, detail=f"{filename} is empty.")
    if extension == ".ex5" and not data.startswith(b"EX5"):
        raise HTTPException(status_code=400, detail=f"{filename} is not a valid compiled MT5 EX5 file.")
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / filename
    path.write_bytes(data)
    result = {
        "filename": filename,
        "original_filename": Path(file.filename or "").name,
        "stored_filename": path.name,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "stored_path": str(path.relative_to(ROOT)),
    }
    if extension == ".ex5":
        result["analysis"] = {
            "format": "MT5 EX5", "compiled": True, "file_verified": True,
            "strategy_visibility": "Observed runtime behavior only; compiled source logic is not readable.",
        }
    elif extension == ".set":
        result["analysis"] = _analyze_set_data(data)
    return result


def _analyze_set_data(data: bytes) -> dict[str, Any]:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in data[:64]:
        text = data.decode("utf-16", errors="ignore")
    else:
        text = data.decode("utf-8", errors="ignore")
    inputs = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("\ufeff")
        if not line or line.startswith((";", "#")) or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()[:120]
        value = value.split("||", 1)[0].strip()[:200]
        if not name:
            continue
        inputs.append({"name": name, "value": "[redacted]" if _SECRET_INPUT.search(name) else value})
    return {"format": "MT5 SET", "input_count": len(inputs), "inputs": inputs[:100], "truncated": len(inputs) > 100}
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
)


class AccountPayload(BaseModel):
    login: int
    password: str | None = None
    server: str | None = None
    nickname: str | None = None
    broker: str | None = None
    account_type: str | None = None
    leverage: int | None = None
    balance: float | None = None


class TradePayload(BaseModel):
    account_login: int
    symbol: str = Field(min_length=1, max_length=64)
    type: str
    volume: float = Field(gt=0)
    sl: float | None = None
    tp: float | None = None
    source: str | None = None


def fail(exc: Exception, status: int = 400):
    raise HTTPException(status_code=status, detail=str(exc))


def normalize_http_errors(fn):
    try:
        return fn()
    except HTTPException:
        raise
    except RuntimeError as exc:
        fail(exc, 409)
    except Exception as exc:
        fail(exc, 500)


def session_error(exc: Exception):
    message = str(exc)
    lowered = message.lower()
    if "ipc timeout" in lowered or "worker timeout" in lowered or "timed out" in lowered:
        raise HTTPException(status_code=504, detail=message)
    if any(text in lowered for text in ("authorization", "wrong password", "invalid account", "auth failed")):
        raise HTTPException(status_code=401, detail=message)
    if "otp" in lowered or "certificate" in lowered:
        raise HTTPException(status_code=428, detail=message)
    if "disconnected" in lowered or "not connected" in lowered or "no mt5 account session" in lowered:
        raise HTTPException(status_code=503, detail=message)
    raise HTTPException(status_code=400, detail=message)


def session_snapshot() -> dict[str, Any]:
    try:
        return multi_account_client.accounts()
    except RuntimeError:
        return {"accounts": [], "master": None, "slaves": [], "offline": True}


@app.get("/")
def root():
    return {"name": "KOOLKID Local MT5 Bridge", "status": "ok", "docs": "/docs"}


@app.get("/health")
def health():
    copy_online = not bool(session_snapshot().get("offline"))
    return {"ok": True, "revision": "mt5-bridge-ea-v5", "time": datetime.now(timezone.utc).isoformat(), "copy_worker": "online" if copy_online else "offline", "ea_worker": ea_worker_client.status()}


@app.get("/api/mt5/bridge/status")
def bridge_status():
    worker = ea_worker_client.status()
    snapshot = session_snapshot()
    copy_online = not bool(snapshot.get("offline"))
    connected = [row for row in snapshot.get("accounts", []) if row.get("connected")]
    return {
        "status": "online", "mode": "bridge", "terminal": None, "terminal_path": None, "data_path": None,
        "endpoint": "http://127.0.0.1:8000", "protocol": "http",
        "trading_enabled": bool(connected), "account_login": None, "account_server": None,
        "last_heartbeat": datetime.now(timezone.utc).isoformat(),
        "message": f"MT5 coordinator online. {len(connected)} verified account session(s).",
        "services": {"bridge": "online", "ea_worker": worker["status"], "copy_worker": "online" if copy_online else "offline"},
        "capabilities": {"account_data": copy_online, "quotes": bool(connected), "candles": bool(connected), "manual_trading": bool(connected), "positions": copy_online, "history": bool(connected), "ea_launch": worker["status"] == "online"},
        "ea_worker": worker,
    }


@app.get("/api/mt5/accounts")
def accounts():
    rows = engine.list_accounts()
    snapshot = session_snapshot()
    try:
        known = {int(row.get("login") or 0) for row in rows}
        for saved in snapshot.get("accounts", []):
            login = int(saved.get("login") or 0)
            if not login or login in known:
                continue
            engine.upsert_profile({
                "login": login, "nickname": saved.get("nickname") or f"MT5 #{login}",
                "broker": "Deriv", "server": saved.get("server") or "", "balance": 0,
                "equity": 0, "margin": 0, "free_margin": 0, "floating_pl": 0,
                "leverage": 0, "currency": "USD", "status": "disconnected",
                "is_active": False, "account_type": "demo", "connection_status": "offline",
            }, make_active=False)
        rows = engine.list_accounts()
    except Exception:
        pass
    sessions = {int(item.get("login") or 0): item for item in snapshot.get("accounts", [])}
    for row in rows:
        session = sessions.get(int(row.get("login") or 0))
        if not session or not session.get("connected"):
            row.update({"status": "connecting" if session and session.get("connecting") else "disconnected", "connection_status": "offline", "worker_id": None, "cached": True})
            continue
        info = session.get("account_info") or {}
        row.update({
            "status": "connected", "connection_status": "online", "worker_id": session.get("account_id"), "cached": False,
            "balance": float(info.get("balance") or row.get("balance") or 0),
            "equity": float(info.get("equity") or row.get("equity") or 0),
            "margin": float(info.get("margin") or 0), "free_margin": float(info.get("margin_free") or 0),
            "floating_pl": float(info.get("profit") or 0), "leverage": int(info.get("leverage") or row.get("leverage") or 0),
            "currency": info.get("currency") or row.get("currency") or "USD",
            "last_heartbeat": datetime.now(timezone.utc).isoformat(),
        })
    return rows


@app.post("/api/mt5/accounts/test")
def test_account(payload: AccountPayload):
    if not payload.password:
        raise HTTPException(status_code=400, detail="MT5 password is required for a connection test.")
    profile = {"login": payload.login, "nickname": payload.nickname or f"MT5 #{payload.login}", "server": payload.server or "", "broker": payload.broker or "MetaTrader 5"}
    try:
        engine.shutdown_terminal()
        result = multi_account_client.connect(profile, payload.password)
        return {"ok": True, "mode": "bridge", "message": f"Connected to {payload.server or 'MT5'} as #{payload.login}.", "session": result}
    except RuntimeError as exc:
        session_error(exc)


@app.post("/api/mt5/accounts/connect")
def connect_account(payload: AccountPayload):
    if not payload.password:
        raise HTTPException(status_code=400, detail="MT5 password is required when adding a new account. KOOLKID does not persist it.")
    profile = {"login": payload.login, "nickname": payload.nickname or f"MT5 #{payload.login}", "server": payload.server or "", "broker": payload.broker or "MetaTrader 5"}
    try:
        engine.shutdown_terminal()
        session = multi_account_client.connect(profile, payload.password or "")
    except RuntimeError as exc:
        session_error(exc)
    info = session.get("account_info") or {}
    profile.update({"balance": float(info.get("balance") or 0), "equity": float(info.get("equity") or 0), "margin": float(info.get("margin") or 0), "free_margin": float(info.get("margin_free") or 0), "floating_pl": float(info.get("profit") or 0), "leverage": int(info.get("leverage") or 0), "currency": info.get("currency") or "USD", "status": "connected", "connection_status": "online", "account_type": "live" if int(info.get("trade_mode") or 0) == 2 else "demo"})
    engine.upsert_profile(profile)
    return next((row for row in accounts() if int(row.get("login", 0)) == payload.login), profile)


@app.post("/api/mt5/accounts/connect/cancel")
def cancel_account_connect(payload: dict[str, Any] = Body(...)):
    login = int(payload.get("login") or 0)
    if not login:
        raise HTTPException(status_code=400, detail="MT5 login is required to cancel a connection.")
    try:
        result = multi_account_client.request(f"/accounts/session-{login}/cancel", "POST", {}, timeout=5)
        return {"ok": bool(result.get("ok"))}
    except RuntimeError as exc:
        session_error(exc)


@app.delete("/api/mt5/accounts/{profile_id}")
def delete_account(profile_id: int):
    state = read_state()
    profile = next((x for x in state.get("profiles", []) if int(x.get("id", 0)) == profile_id), None)
    if not profile:
        raise HTTPException(status_code=404, detail="Account profile not found.")
    try:
        multi_account_client.remove(int(profile.get("login", 0)))
    except RuntimeError:
        pass
    return {"ok": remove_profile(profile_id)}


@app.put("/api/mt5/accounts/{profile_id}")
def account_action(profile_id: int, payload: dict[str, Any] = Body(default_factory=dict)):
    state = read_state()
    profile = next((x for x in state.get("profiles", []) if int(x.get("id", 0)) == profile_id), None)
    if not profile:
        raise HTTPException(status_code=404, detail="Account profile not found.")
    action = str(payload.get("action") or "")
    login = int(profile.get("login", 0))
    if action == "set_active":
        engine.set_active_login(login)
        return next((x for x in accounts() if int(x["id"]) == profile_id), profile)
    if action in {"toggle", "connect", "disconnect"}:
        live = {int(row.get("login") or 0): row for row in session_snapshot().get("accounts", []) if row.get("connected")}
        should_disconnect = action == "disconnect" or (action == "toggle" and login in live)
        if should_disconnect:
            try:
                multi_account_client.disconnect(login)
            except RuntimeError:
                pass
        elif login not in live:
            password = str(payload.get("password") or "") or None
            try:
                engine.shutdown_terminal()
                multi_account_client.connect(profile, password or "")
            except RuntimeError as exc:
                session_error(exc)
        return next((x for x in accounts() if int(x["id"]) == profile_id), profile)
    if action == "cancel_connect":
        try:
            result = multi_account_client.request(f"/accounts/session-{login}/cancel", "POST", {}, timeout=5)
            return {"ok": bool(result.get("ok"))}
        except RuntimeError as exc:
            session_error(exc)
    raise HTTPException(status_code=400, detail=f"Unsupported account action '{action}'.")


@app.get("/api/mt5/quotes")
def get_quotes(symbols: str = Query(default=""), account_login: int | None = None):
    requested = [x.strip() for x in symbols.split(",") if x.strip()]
    if not requested:
        return []
    if not account_login:
        raise HTTPException(status_code=422, detail="Select a connected MT5 account before requesting quotes.")
    try:
        return multi_account_client.account_request(account_login, f"/quotes?symbols={quote(','.join(requested))}", timeout=5)
    except RuntimeError as exc:
        message = str(exc)
        raise HTTPException(status_code=504 if "timeout" in message.lower() else 503, detail=message)


@app.get("/api/mt5/candles/{symbol}")
def get_candles(symbol: str, timeframe: str = "M15", count: int = 220, account_login: int | None = None):
    try:
        return multi_account_client.account_request(account_login, f"/candles/{quote(symbol)}?timeframe={quote(timeframe)}&count={count}", timeout=15)
    except RuntimeError as exc:
        session_error(exc)


@app.get("/api/mt5/symbols")
def get_symbols(visible_only: bool = True, limit: int = 1000, account_login: int | None = None):
    try:
        return multi_account_client.account_request(account_login, f"/symbols?visible_only={str(visible_only).lower()}&limit={limit}", timeout=15)
    except RuntimeError as exc:
        session_error(exc)


@app.get("/api/mt5/positions")
def positions():
    try:
        worker_rows = multi_account_client.request("/positions", timeout=10).get("positions", [])
        if worker_rows:
            return worker_rows
    except RuntimeError:
        pass
    return []


@app.post("/api/mt5/trade")
def trade(payload: TradePayload):
    workers = normalize_http_errors(multi_account_client.connected_by_login)
    worker = workers.get(payload.account_login)
    if worker:
        result = normalize_http_errors(lambda: multi_account_client.request("/manual-trade", "POST", {
            "target_account_ids": [worker["account_id"]], "symbol": payload.symbol,
            "side": payload.type.lower(), "volume": payload.volume, "sl": payload.sl or 0, "tp": payload.tp or 0,
        }, timeout=55))
        row = result.get("results", {}).get(worker["account_id"], {})
        if not row.get("ok"):
            raise HTTPException(status_code=409, detail=row.get("error") or "MT5 worker rejected the order.")
        return row.get("result")
    raise HTTPException(status_code=503, detail=f"MT5 account #{payload.account_login} is disconnected.")


@app.post("/api/mt5/positions/{ticket}/close")
def close_position(ticket: int):
    try:
        data = multi_account_client.request("/positions", timeout=10)
        match = next((row for row in data.get("positions", []) if int(row.get("ticket") or 0) == ticket), None)
        if match:
            return normalize_http_errors(lambda: multi_account_client.request("/positions/close", "POST", {"account_id": match["account_id"], "ticket": ticket}, timeout=55))
    except RuntimeError:
        pass
    raise HTTPException(status_code=404, detail=f"Open position #{ticket} was not found in a live account session.")


@app.post("/api/mt5/positions/close-all")
def close_all_positions():
    data = normalize_http_errors(lambda: multi_account_client.request("/positions", timeout=10))
    closed = 0
    errors = []
    for row in data.get("positions", []):
        try:
            multi_account_client.request("/positions/close", "POST", {"account_id": row["account_id"], "ticket": int(row["ticket"])}, timeout=20)
            closed += 1
        except RuntimeError as exc:
            errors.append(str(exc))
    return {"ok": not errors, "closed": closed, "realized": 0, "errors": errors}


@app.get("/api/mt5/history")
def history(days: int | None = None):
    rows = []
    for session in session_snapshot().get("accounts", []):
        if not session.get("connected"):
            continue
        try:
            rows.extend(multi_account_client.request(f"/accounts/{session['account_id']}/history?days={int(days or 30)}", timeout=15))
        except RuntimeError:
            continue
    rows.sort(key=lambda row: row.get("close_time", ""), reverse=True)
    return rows


def _history_for_stats(days: int = 30) -> list[dict[str, Any]]:
    sessions = [row for row in session_snapshot().get("accounts", []) if row.get("connected")]
    session_key = ",".join(sorted(str(row.get("account_id") or row.get("login") or "") for row in sessions))
    now = time.monotonic()
    with _stats_history_lock:
        if _stats_history_cache["session_key"] == session_key and now - float(_stats_history_cache["loaded_at"]) < 15:
            return list(_stats_history_cache["rows"])
    rows = history(days)
    with _stats_history_lock:
        _stats_history_cache.update({"session_key": session_key, "loaded_at": now, "rows": list(rows)})
    return rows


def _empty_stats():
    state = read_state()
    bots = state.get("bots", [])
    return {
        "kpis": {
            "total_balance": 0, "total_equity": 0, "floating": 0, "margin": 0, "free_margin": 0, "margin_level": None,
            "realized_today": 0, "today_pl": 0, "trades_today": 0, "latest_day": None, "connected_accounts": 0,
            "total_accounts": len(state.get("profiles", [])), "running_bots": 0, "paused_bots": 0, "total_bots": len(bots),
            "open_positions": 0, "win_rate_30d": 0, "trades_30d": 0, "profit_30d": 0, "drawdown_pct": 0, "peak_equity": 0,
        },
        "equity": [], "daily": [], "bots": bots, "symbolPnl": [], "exposure": [],
    }


@app.get("/api/mt5/stats")
def stats():
    base = _empty_stats()
    live_accounts = [row for row in accounts() if row.get("status") == "connected"]
    position_rows = positions()
    history_rows = _history_for_stats(30)
    today = datetime.now(timezone.utc).date().isoformat()
    today_rows = [row for row in history_rows if str(row.get("close_time", "")).startswith(today)]
    kpis = base["kpis"]
    kpis.update({
        "total_balance": sum(float(row.get("balance") or 0) for row in live_accounts),
        "total_equity": sum(float(row.get("equity") or 0) for row in live_accounts),
        "floating": sum(float(row.get("profit") or 0) for row in position_rows),
        "margin": sum(float(row.get("margin") or 0) for row in live_accounts),
        "free_margin": sum(float(row.get("free_margin") or 0) for row in live_accounts),
        "realized_today": sum(float(row.get("net_pl") or 0) for row in today_rows),
        "today_pl": sum(float(row.get("net_pl") or 0) for row in today_rows) + sum(float(row.get("profit") or 0) for row in position_rows),
        "trades_today": len(today_rows), "connected_accounts": len(live_accounts),
        "open_positions": len(position_rows), "trades_30d": len(history_rows),
        "profit_30d": sum(float(row.get("net_pl") or 0) for row in history_rows),
        "win_rate_30d": (100 * len([row for row in history_rows if float(row.get("net_pl") or 0) > 0]) / len(history_rows)) if history_rows else 0,
    })
    return base


@app.get("/api/mt5/risk")
def get_risk():
    state = read_state()
    return state.get("risk") or [default_risk()]


@app.put("/api/mt5/risk")
def put_risk(row: dict[str, Any] = Body(...)):
    required = {"id", "scope", "max_daily_loss", "max_daily_profit", "max_drawdown_pct", "max_lot_size", "max_open_positions", "max_trades_per_day", "max_risk_per_trade", "allowed_trading_hours", "allowed_symbols", "auto_stop"}
    missing = required - set(row)
    if missing:
        raise HTTPException(status_code=400, detail="Missing risk fields: " + ", ".join(sorted(missing)))
    def mut(state):
        rows = state.setdefault("risk", [])
        idx = next((i for i, item in enumerate(rows) if str(item.get("id")) == str(row.get("id"))), -1)
        if idx >= 0:
            rows[idx] = row
        else:
            rows.append(row)
        return row
    return update_state(mut)


@app.get("/api/mt5/copy")
def copy_state():
    state = read_state()
    return {
        "relationships": state.get("copy_relationships", []),
        "events": state.get("copy_events", [])[:500],
        "real_execution_available": False,
        "execution_message": "Copy rules are saved, but real multi-account copying is safety-locked until isolated MT5 terminal workers are installed. Simulation copy trading is fully testable in the frontend runtime.",
    }


@app.post("/api/mt5/copy")
def create_copy(payload: dict[str, Any] = Body(...)):
    master = int(payload.get("master_login") or 0)
    follower = int(payload.get("follower_login") or 0)
    if not master or not follower:
        raise HTTPException(status_code=400, detail="Master and follower accounts are required.")
    if master == follower:
        raise HTTPException(status_code=400, detail="Master and follower accounts must be different.")
    state = read_state()
    logins = {int(x.get("login", 0)) for x in state.get("profiles", [])}
    if master not in logins or follower not in logins:
        raise HTTPException(status_code=400, detail="Both MT5 account profiles must exist before creating a copy relationship.")
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "id": f"copy-{uuid.uuid4().hex[:12]}",
        "name": str(payload.get("name") or f"{master} → {follower}"),
        "master_login": master,
        "follower_login": follower,
        "enabled": bool(payload.get("enabled", False)),
        "status": "stopped",  # real execution remains locked in this bridge
        "copy_mode": str(payload.get("copy_mode") or "balance_ratio"),
        "fixed_lot": float(payload.get("fixed_lot") or 0.01),
        "multiplier": float(payload.get("multiplier") or 1.0),
        "max_lot": float(payload.get("max_lot") or 1.0),
        "max_daily_loss": float(payload.get("max_daily_loss") or 100.0),
        "max_drawdown_pct": float(payload.get("max_drawdown_pct") or 5.0),
        "max_open_positions": int(payload.get("max_open_positions") or 3),
        "copy_new_trades": bool(payload.get("copy_new_trades", True)),
        "copy_sl_tp": bool(payload.get("copy_sl_tp", True)),
        "copy_closes": bool(payload.get("copy_closes", True)),
        "created_at": now,
        "last_event": "Saved — real copy worker not installed",
    }
    def mut(st):
        st.setdefault("copy_relationships", []).insert(0, row)
        st.setdefault("copy_events", []).insert(0, {
            "id": f"evt-{uuid.uuid4().hex[:12]}", "relationship_id": row["id"], "time": now,
            "action": "status", "message": "Copy relationship saved. Real execution is locked until isolated workers are available."
        })
        return row
    return update_state(mut)


@app.put("/api/mt5/copy/{relationship_id}")
def update_copy(relationship_id: str, payload: dict[str, Any] = Body(...)):
    def mut(st):
        row = next((x for x in st.get("copy_relationships", []) if str(x.get("id")) == relationship_id), None)
        if row is None:
            raise KeyError
        safe = {k: v for k, v in payload.items() if k not in {"id", "created_at"}}
        row.update(safe)
        # Do not report 'armed' in real bridge mode until the multi-terminal copy executor exists.
        if row.get("enabled"):
            row["status"] = "blocked"
            row["last_event"] = "Real copy worker required"
        else:
            row["status"] = "stopped"
        st.setdefault("copy_events", []).insert(0, {
            "id": f"evt-{uuid.uuid4().hex[:12]}", "relationship_id": relationship_id,
            "time": datetime.now(timezone.utc).isoformat(), "action": "status",
            "message": "Copy settings updated. Real execution remains safety-locked." if row.get("enabled") else "Copy relationship stopped."
        })
        st["copy_events"] = st["copy_events"][:500]
        return row
    try:
        return update_state(mut)
    except KeyError:
        raise HTTPException(status_code=404, detail="Copy relationship not found.")


@app.delete("/api/mt5/copy/{relationship_id}")
def delete_copy(relationship_id: str):
    def mut(st):
        before = len(st.get("copy_relationships", []))
        st["copy_relationships"] = [x for x in st.get("copy_relationships", []) if str(x.get("id")) != relationship_id]
        return len(st["copy_relationships"]) != before
    return {"ok": bool(update_state(mut))}


@app.get("/api/mt5/bots")
def bots():
    state = read_state()
    worker_status = ea_worker_client.status()
    if worker_status["status"] == "online":
        try:
            assignments = {int(x["bot_id"]): x for x in ea_worker_client.request("/bots")}
            def sync(st):
                for bot in st.get("bots", []):
                    assignment = assignments.get(int(bot.get("id", 0)))
                    if assignment:
                        assignment_active = assignment.get("status") in {"starting", "running", "stopping"}
                        bot.update({
                            "status": assignment["status"], "started_at": assignment.get("started_at") if assignment_active else None,
                            "worker_id": assignment.get("worker_id"), "terminal_id": assignment.get("terminal_id"),
                            "process_id": assignment.get("process_id") if assignment_active else None, "terminal_status": assignment.get("terminal_status"),
                            "last_activity": assignment.get("last_activity"), "last_error": assignment.get("error"),
                            "account_verified": assignment.get("account_verified", False) if assignment_active else False,
                            "open_positions": assignment.get("open_positions", 0),
                            "current_pl": assignment.get("current_pl", 0), "today_pl": assignment.get("today_pl", 0),
                            "profit_today": assignment.get("today_pl", 0),
                            "account_open_positions": assignment.get("account_open_positions", 0),
                            "account_current_pl": assignment.get("account_current_pl", 0),
                            "metrics_scope": assignment.get("metrics_scope"),
                            "bot_trade_count": assignment.get("bot_trade_count", 0),
                            "bot_wins": assignment.get("bot_wins", 0), "bot_losses": assignment.get("bot_losses", 0),
                            "bot_win_rate": assignment.get("bot_win_rate", 0),
                            "detected_magic": assignment.get("detected_magic"),
                            "attribution_status": assignment.get("attribution_status", "pending"),
                            "last_trade": assignment.get("last_trade"), "metrics_error": assignment.get("metrics_error"),
                            "ea_verified": assignment.get("ea_verified", False) if assignment_active else False, "ea_status": assignment.get("ea_status"),
                            "verification_message": assignment.get("verification_message"),
                            "strategy_analysis": assignment.get("strategy_analysis"),
                            "background_mode": assignment.get("background_mode", False),
                        })
                    elif bot.get("status") in {"running", "connecting", "worker_offline"}:
                        bot["status"] = "stopped"
                        bot["started_at"] = None
                return st.get("bots", [])
            return update_state(sync)
        except RuntimeError:
            pass
    elif any(bot.get("status") in {"running", "connecting"} for bot in state.get("bots", [])):
        def offline(st):
            for bot in st.get("bots", []):
                if bot.get("status") in {"running", "connecting"}:
                    bot["status"] = "worker_offline"
            return st.get("bots", [])
        return update_state(offline)
    return state.get("bots", [])


@app.post("/api/mt5/bots")
def create_bot(payload: dict[str, Any] = Body(...)):
    def mut(state):
        bots = state.setdefault("bots", [])
        next_id = max([int(x.get("id", 0)) for x in bots] + [999]) + 1
        name = str(payload.get("name") or f"Custom EA {next_id}").strip()
        row = {
            "id": next_id, "name": name, "description": "Custom EA metadata.", "strategy": "Custom EA",
            "symbol": str(payload.get("symbol") or "EURUSD"), "timeframe": str(payload.get("timeframe") or "M15"),
            "recommended_timeframe": payload.get("recommended_timeframe"), "account_login": None, "status": "stopped",
            "lot_size": float(payload.get("lot_size") or 0.01), "win_rate": 0, "total_trades": 0, "net_profit": 0,
            "profit_today": 0, "version": str(payload.get("version") or "1.0.0"), "started_at": None,
            "ea_filename": payload.get("ea_filename"), "preset_filename": payload.get("preset_filename"),
            "file_status": "metadata-only", "upload_date": payload.get("upload_date"), "dll_required": bool(payload.get("dll_required", False)),
            "settings": payload.get("settings") or {"risk_percent": 1, "max_spread": 3.5, "trailing_stop": True, "magic_number": 510000 + next_id, "max_daily_loss": 250},
        }
        bots.append(row)
        return row
    return update_state(mut)




@app.post("/api/mt5/bots/{bot_id}/files")
async def upload_bot_files(
    bot_id: int,
    ea_file: UploadFile | None = File(default=None),
    preset_file: UploadFile | None = File(default=None),
):
    if ea_file is None and preset_file is None:
        raise HTTPException(status_code=400, detail="Choose an .ex5 EA file or .set preset to upload.")
    state = read_state()
    bot = next((b for b in state.get("bots", []) if int(b.get("id", 0)) == bot_id), None)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found.")

    bot_dir = EA_LIBRARY / str(bot_id)
    result: dict[str, Any] = {"bot_id": bot_id}
    if ea_file is not None:
        result["ea"] = await _save_upload(ea_file, bot_dir, ".ex5")
    if preset_file is not None:
        result["preset"] = await _save_upload(preset_file, bot_dir, ".set")

    now = datetime.now(timezone.utc).isoformat()
    def mut(st):
        row = next((b for b in st.get("bots", []) if int(b.get("id", 0)) == bot_id), None)
        if row is None:
            raise KeyError
        if "ea" in result:
            row["ea_filename"] = result["ea"]["filename"]
            row["ea_original_filename"] = result["ea"]["original_filename"]
            row["ea_stored_filename"] = result["ea"]["stored_filename"]
            row["ea_storage_path"] = result["ea"]["stored_path"]
            row["ea_size_bytes"] = result["ea"]["size_bytes"]
            row["ea_sha256"] = result["ea"]["sha256"]
            row["file_status"] = "ready"
            row["worker_compatibility"] = "ready"
            row["file_analysis"] = result["ea"].get("analysis")
        if "preset" in result:
            row["preset_filename"] = result["preset"]["filename"]
            row["preset_storage_path"] = result["preset"]["stored_path"]
            row["preset_size_bytes"] = result["preset"]["size_bytes"]
            row["preset_sha256"] = result["preset"]["sha256"]
            row["preset_analysis"] = result["preset"].get("analysis")
        row["upload_date"] = now
        return dict(row)
    try:
        result["bot"] = update_state(mut)
    except KeyError:
        raise HTTPException(status_code=404, detail="Bot not found.")
    return result


@app.put("/api/mt5/bots/{bot_id}")
def update_bot(bot_id: int, payload: dict[str, Any] = Body(...)):
    def mut(state):
        for i, bot in enumerate(state.get("bots", [])):
            if int(bot.get("id", 0)) == bot_id:
                safe = {k: v for k, v in payload.items() if k not in {"id", "status", "started_at"}}
                state["bots"][i] = {**bot, **safe}
                return state["bots"][i]
        raise KeyError
    try:
        return update_state(mut)
    except KeyError:
        raise HTTPException(status_code=404, detail="Bot not found.")


@app.delete("/api/mt5/bots/{bot_id}")
def delete_bot(bot_id: int):
    def mut(state):
        before = len(state.get("bots", []))
        state["bots"] = [b for b in state.get("bots", []) if int(b.get("id", 0)) != bot_id]
        return len(state["bots"]) != before
    return {"ok": bool(update_state(mut))}


@app.post("/api/mt5/bots/{bot_id}/start")
def start_bot(bot_id: int, payload: dict[str, Any] = Body(default_factory=dict)):
    state = read_state()
    bot = next((b for b in state.get("bots", []) if int(b.get("id", 0)) == bot_id), None)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found.")
    login = int(payload.get("account_login") or bot.get("account_login") or 0)
    profile = next((p for p in state.get("profiles", []) if int(p.get("login", 0)) == login), None)
    if not profile:
        raise HTTPException(status_code=409, detail="Selected MT5 account profile was not found.")
    try:
        session = multi_account_client.worker_for_login(login)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    info = session.get("account_info") or {}
    symbol = str(payload.get("symbol") or bot.get("symbol") or "")
    available = {row["symbol"] for row in normalize_http_errors(lambda: multi_account_client.account_request(login, "/symbols?visible_only=false&limit=5000", timeout=15))}
    if symbol not in available:
        raise HTTPException(status_code=400, detail=f"Symbol {symbol} is unavailable on the selected MT5 account.")
    ea_rel = bot.get("ea_storage_path")
    if not ea_rel or not (ROOT / ea_rel).is_file():
        raise HTTPException(status_code=409, detail="Uploaded .ex5 file was not found. Upload the EA before starting it.")
    preset_rel = bot.get("preset_storage_path")
    worker_payload = {
        "bot_id": bot_id, "account_login": login, "account_type": profile.get("account_type", "demo"),
        "server": profile.get("server"), "symbol": symbol, "timeframe": str(payload.get("timeframe") or bot.get("timeframe") or ""),
        "ea_path": str((ROOT / ea_rel).resolve()), "ea_filename": bot.get("ea_filename"),
        "preset_path": str((ROOT / preset_rel).resolve()) if preset_rel else None, "preset_filename": bot.get("preset_filename"),
        "terminal_path": payload.get("terminal_path"), "allow_live": bool(payload.get("confirm_live")),
        "bridge_terminal_path": info.get("terminal_path"), "bridge_data_path": info.get("data_path"),
        "allow_dll": bool(payload.get("allow_dll")), "dll_required": bool(bot.get("dll_required")),
        "configured_magic": int((bot.get("settings") or {}).get("magic_number") or 0) or None,
    }
    def mark_starting(st):
        row = next(b for b in st["bots"] if int(b["id"]) == bot_id)
        row.update({**{k: v for k, v in payload.items() if k in {"account_login", "symbol", "timeframe", "lot_size", "settings"}}, "status": "connecting"})
        return row
    update_state(mark_starting)
    try:
        assignment = ea_worker_client.request("/bots/start", "POST", worker_payload, timeout=120)
    except RuntimeError as exc:
        def mark_error(st):
            row = next(b for b in st["bots"] if int(b["id"]) == bot_id)
            row.update({"status": "error", "last_error": str(exc)})
            return row
        update_state(mark_error)
        raise HTTPException(status_code=409, detail=str(exc))
    def mark_running(st):
        row = next(b for b in st["bots"] if int(b["id"]) == bot_id)
        row.update({
            "status": assignment["status"], "started_at": assignment.get("started_at"),
            "worker_id": assignment.get("worker_id"), "terminal_id": assignment.get("terminal_id"),
            "process_id": assignment.get("process_id"), "terminal_status": assignment.get("terminal_status"),
            "last_activity": assignment.get("last_activity"), "last_error": assignment.get("error"),
            "account_verified": assignment.get("account_verified", False),
            "open_positions": assignment.get("open_positions", 0),
            "current_pl": assignment.get("current_pl", 0), "today_pl": assignment.get("today_pl", 0),
            "profit_today": assignment.get("today_pl", 0),
            "account_open_positions": assignment.get("account_open_positions", 0),
            "account_current_pl": assignment.get("account_current_pl", 0),
            "metrics_scope": assignment.get("metrics_scope"),
            "bot_trade_count": assignment.get("bot_trade_count", 0),
            "bot_wins": assignment.get("bot_wins", 0), "bot_losses": assignment.get("bot_losses", 0),
            "bot_win_rate": assignment.get("bot_win_rate", 0),
            "detected_magic": assignment.get("detected_magic"),
            "attribution_status": assignment.get("attribution_status", "pending"),
            "last_trade": assignment.get("last_trade"), "metrics_error": assignment.get("metrics_error"),
            "ea_verified": assignment.get("ea_verified", False), "ea_status": assignment.get("ea_status"),
            "verification_message": assignment.get("verification_message"),
            "strategy_analysis": assignment.get("strategy_analysis"),
            "background_mode": assignment.get("background_mode", False),
        })
        return row
    return update_state(mark_running)


@app.post("/api/mt5/bots/{bot_id}/pause")
def pause_bot(bot_id: int, payload: dict[str, Any] = Body(default_factory=dict)):
    raise HTTPException(status_code=409, detail="Pause is unavailable for arbitrary .ex5 EAs unless the EA exposes its own pause control.")


@app.post("/api/mt5/bots/{bot_id}/resume")
def resume_bot(bot_id: int, payload: dict[str, Any] = Body(default_factory=dict)):
    raise HTTPException(status_code=409, detail="Resume is unavailable for arbitrary .ex5 EAs. Start the bot again instead.")


@app.post("/api/mt5/bots/{bot_id}/stop")
def stop_bot(bot_id: int, payload: dict[str, Any] = Body(default_factory=dict)):
    try:
        assignment = ea_worker_client.request(f"/bots/{bot_id}/stop", "POST", {}, timeout=15)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    def mark_stopped(st):
        row = next((b for b in st.get("bots", []) if int(b.get("id", 0)) == bot_id), None)
        if not row:
            raise KeyError
        row.update({
            "status": assignment.get("status", "stopped"), "started_at": None, "process_id": None,
            "terminal_status": assignment.get("terminal_status", "offline"), "account_verified": False,
            "last_activity": assignment.get("last_activity"), "last_error": assignment.get("error"),
            "ea_verified": False, "ea_status": "stopped",
        })
        return row
    try:
        return update_state(mark_stopped)
    except KeyError:
        raise HTTPException(status_code=404, detail="Bot not found.")


@app.get("/api/mt5/bots/{bot_id}/performance")
def bot_performance(bot_id: int):
    state = read_state()
    bot = next((b for b in state.get("bots", []) if int(b.get("id", 0)) == bot_id), None)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found.")
    rows = history(30)
    tagged = [r for r in rows if str(r.get("source", "")).upper() == str(bot.get("name", "")).upper()]
    pnl = [float(r["profit"]) + float(r["swap"]) + float(r["commission"]) for r in tagged]
    wins = [x for x in pnl if x > 0]
    losses = [x for x in pnl if x < 0]
    curve = peak = max_dd = 0.0
    for value in reversed(pnl):
        curve += value
        peak = max(peak, curve)
        max_dd = max(max_dd, peak - curve)
    return {
        "bot_id": bot_id, "trades": len(pnl), "wins": len(wins), "losses": len(losses),
        "win_rate": round(len(wins) / len(pnl) * 100, 1) if pnl else 0,
        "gross_profit": round(sum(wins), 2), "gross_loss": round(sum(losses), 2), "net_pl": round(sum(pnl), 2),
        "average_win": round(sum(wins) / len(wins), 2) if wins else 0, "average_loss": round(sum(losses) / len(losses), 2) if losses else 0,
        "largest_win": max(wins) if wins else 0, "largest_loss": min(losses) if losses else 0,
        "current_drawdown": round(max(0, peak - curve), 2), "max_drawdown": round(max_dd, 2),
    }


@app.post("/api/mt5/emergency/stop-all-bots")
def emergency_stop_bots():
    try:
        for assignment in ea_worker_client.request("/bots/running", timeout=5):
            try:
                ea_worker_client.request(f"/bots/{int(assignment['bot_id'])}/stop", "POST", {}, timeout=15)
            except RuntimeError:
                pass
    except RuntimeError:
        pass
    def mut(state):
        stopped = 0
        for b in state.get("bots", []):
            if b.get("status") in {"running", "paused", "connecting"}:
                b["status"] = "stopped"
                b["started_at"] = None
                b["process_id"] = None
                b["terminal_status"] = "offline"
                b["account_verified"] = False
                stopped += 1
        return stopped
    return {"ok": True, "stopped": int(update_state(mut))}


@app.post("/api/mt5/emergency/stop-and-close-all")
def emergency_stop_close():
    stopped = emergency_stop_bots()["stopped"]
    result = close_all_positions()
    return {"ok": True, "stopped": stopped, "closed": result["closed"], "realized": result["realized"]}


@app.get("/api/mt5/ai")
def get_ai():
    state = read_state()
    settings = state.get("ai_settings", {})
    insights = []
    live_accounts = [row for row in accounts() if row.get("status") == "connected"]
    now = datetime.now(timezone.utc).isoformat()
    if live_accounts:
        try:
            k = stats()["kpis"]
            sentiment = "critical" if k["drawdown_pct"] >= 8 else "warning" if k["drawdown_pct"] >= 4 else "neutral"
            insights.append({"id": 1, "title": "Live MT5 bridge status", "body": f"Account data is live. Equity {k['total_equity']:.2f}, floating P/L {k['floating']:.2f}, open positions {k['open_positions']}.", "category": "performance", "sentiment": sentiment, "confidence": 100, "account_login": None, "bot_id": None, "created_at": now})
        except Exception:
            pass
    else:
        insights.append({"id": 1, "title": "MT5 bridge waiting", "body": "Connect an MT5 account.", "category": "market", "sentiment": "warning", "confidence": 100, "account_login": None, "bot_id": None, "created_at": now})
    return {"insights": insights, "settings": settings}


@app.post("/api/mt5/ai")
def generate_ai():
    return get_ai()


@app.delete("/api/mt5/ai")
def delete_ai(payload: dict[str, Any] = Body(default_factory=dict)):
    return {"ok": True}


@app.put("/api/mt5/ai")
def save_ai(payload: dict[str, Any] = Body(...)):
    settings = payload.get("settings") or {}
    def mut(state):
        state["ai_settings"] = settings
        return settings
    return update_state(mut)


# Deriv execution is deliberately not implemented by the MT5 bridge.
@app.get("/api/deriv/accounts")
def deriv_accounts():
    return []


@app.post("/api/deriv/accounts/{account_id}/active")
def deriv_active(account_id: int):
    raise HTTPException(status_code=501, detail="Deriv accounts remain in the separate Deriv integration path.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.getenv("MT5_BRIDGE_HOST", "127.0.0.1"), port=int(os.getenv("MT5_BRIDGE_PORT", "8000")))
