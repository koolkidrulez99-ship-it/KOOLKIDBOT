from __future__ import annotations
import atexit
import configparser
import os
import re
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import uuid
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from .models import ConnectRequest, CopyRequest, CopyDecisionRequest, ManualTradeRequest, CloseRequest, MultiCloseRequest
from .state import State
from .pool import Pool
from .credential_store import CredentialStore
from .copy_engine import CopyEngine, COPY_MAGIC

import sys
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent))
from hub_auth import current_workspace, internal_workspace_signature, reset_workspace, set_workspace, verify_internal_workspace, workspace_from_authorization, workspace_ids

TERMINALS = BASE / "data" / "terminals"
TERMINAL_LOCK = threading.RLock()
_CORE_POOL = Pool()
_SESSION_STOP = threading.Event()
_RUNTIMES: dict[str, "WorkspaceRuntime"] = {}
_RUNTIMES_LOCK = threading.RLock()


class ScopedPool:
    def __init__(self, workspace_id: str):
        self.workspace_id = workspace_id

    def _key(self, account_id: str) -> str:
        return f"{self.workspace_id}--{account_id}"

    def _external(self, account_id: str) -> str:
        prefix = f"{self.workspace_id}--"
        return account_id[len(prefix):] if account_id.startswith(prefix) else account_id

    @property
    def items(self):
        return {self._external(aid): runtime for aid, runtime in _CORE_POOL.items.items() if str(runtime.config.get("_workspace") or "") == self.workspace_id}

    @property
    def pending(self):
        return {self._external(aid): value for aid, value in _CORE_POOL.pending.items() if aid.startswith(f"{self.workspace_id}--")}

    def connect(self, cfg, password=""):
        external = str(cfg["account_id"])
        return self.status_from_internal(_CORE_POOL.connect({**cfg, "account_id": self._key(external), "_workspace": self.workspace_id}, password), external)

    def status_from_internal(self, row, external: str):
        result = dict(row)
        result["account_id"] = external
        return result

    def disconnect(self, aid, preserve_recovery=False):
        return _CORE_POOL.disconnect(self._key(str(aid)), preserve_recovery=preserve_recovery)

    def cancel_connect(self, aid):
        return _CORE_POOL.cancel_connect(self._key(str(aid)))

    def call(self, aid, op, payload=None, timeout=15):
        return _CORE_POOL.call(self._key(str(aid)), op, payload, timeout)

    def cached(self, aid, op, default=None):
        return _CORE_POOL.cached(self._key(str(aid)), op, default)

    def ids(self):
        return [self._external(aid) for aid in _CORE_POOL.ids() if aid.startswith(f"{self.workspace_id}--")]

    def status(self, aid):
        return self.status_from_internal(_CORE_POOL.status(self._key(str(aid))), str(aid))


class WorkspaceRuntime:
    def __init__(self, workspace_id: str):
        root = BASE / "data" / "workspaces" / workspace_id
        self.workspace_id = workspace_id
        self.state = State(root / "state.json")
        self.credentials = CredentialStore(root / "credentials")
        self.pool = ScopedPool(workspace_id)
        self.copy = CopyEngine(self.pool, self.state)
        self.session_backoff: dict[str, dict[str, object]] = {}
        self.started = False


def _runtime() -> WorkspaceRuntime:
    workspace_id = current_workspace()
    with _RUNTIMES_LOCK:
        runtime = _RUNTIMES.get(workspace_id)
        if runtime is None:
            runtime = WorkspaceRuntime(workspace_id)
            _RUNTIMES[workspace_id] = runtime
        return runtime


class _RuntimeProxy:
    def __init__(self, attr: str): self.attr = attr
    def __getattr__(self, name): return getattr(getattr(_runtime(), self.attr), name)


STATE = _RuntimeProxy("state")
CREDENTIALS = _RuntimeProxy("credentials")
POOL = _RuntimeProxy("pool")
COPY = _RuntimeProxy("copy")
app = FastAPI(title="KOOLKID MT5 Multi-Account", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5055", "http://localhost:5055"],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def require_workspace(request: Request, call_next):
    # Public health check used by START_KOOLKID.bat/service monitoring.
    # Keep this workspace-neutral and do not expose user/account state.
    if request.method == "OPTIONS" or request.url.path == "/health":
        return await call_next(request)

    workspace_id = workspace_from_authorization(request.headers.get("Authorization"))
    if not workspace_id:
        candidate = request.headers.get("X-MT5-Workspace", "")
        if verify_internal_workspace(candidate, request.headers.get("X-MT5-Internal-Signature")):
            workspace_id = candidate
    if not workspace_id:
        return JSONResponse(status_code=401, content={"detail": "Sign in to your MT5 Hub workspace."})
    token = set_workspace(workspace_id)
    try:
        _start_workspace(workspace_id)
        return await call_next(request)
    finally:
        reset_workspace(token)

def _saved_real_accounts():
    state = STATE.load()
    rows = []
    for cfg in list(state.get("accounts", {}).values())[:10]:
        if str(cfg.get("mode") or "real") != "real":
            continue
        if cfg.get("auto_reconnect", True) is False:
            continue
        rows.append(dict(cfg))
    return rows


def _saved_password(cfg: dict) -> str:
    if cfg.get("remember_session", True) is False:
        return ""
    return CREDENTIALS.load(str(cfg.get("account_id") or ""))


def _connect_saved(cfg: dict) -> None:
    aid = str(cfg.get("account_id") or "")
    if not aid or aid in POOL.ids() or aid in POOL.pending:
        return
    POOL.connect(dict(cfg), _saved_password(cfg))


def restore_saved_sessions():
    # Startup is intentionally sequential. MT5 portable terminals are much more
    # reliable when restored one at a time instead of all racing for IPC at boot.
    for cfg in _saved_real_accounts():
        aid = str(cfg.get("account_id") or "")
        for attempt in range(3):
            try:
                _connect_saved(cfg)
                _runtime().session_backoff.pop(aid, None)
                break
            except Exception as exc:
                if attempt < 2:
                    time.sleep(min(8, 2 ** (attempt + 1)))
                else:
                    _runtime().session_backoff[aid] = {"attempt": 1, "next_at": time.time() + 5, "error": str(exc)}


def keep_saved_sessions_connected():
    # If the broker/network/terminal is unavailable during startup, do not give up
    # after three attempts. Keep trying with bounded backoff until the saved account
    # is back online or the user explicitly disconnects/removes it.
    while not _SESSION_STOP.wait(5):
        now = time.time()
        saved = {str(cfg.get("account_id") or ""): cfg for cfg in _saved_real_accounts()}
        backoff = _runtime().session_backoff
        for aid in list(backoff):
            if aid not in saved:
                backoff.pop(aid, None)
        for aid, cfg in saved.items():
            if not aid or aid in POOL.ids() or aid in POOL.pending:
                backoff.pop(aid, None)
                continue
            state = backoff.setdefault(aid, {"attempt": 0, "next_at": 0.0, "error": ""})
            if now < float(state.get("next_at") or 0):
                continue
            try:
                _connect_saved(cfg)
                backoff.pop(aid, None)
            except Exception as exc:
                attempt = int(state.get("attempt") or 0) + 1
                delay = min(120, 2 ** min(attempt, 7))
                state.update({"attempt": attempt, "next_at": time.time() + delay, "error": str(exc)})


@app.on_event("startup")
def startup_restore():
    users_file = BASE.parent / "mt5_bridge" / "data" / "mt5_hub_users.json"
    for workspace_id in workspace_ids(users_file):
        _start_workspace(workspace_id)


def _start_workspace(workspace_id: str) -> None:
    with _RUNTIMES_LOCK:
        runtime = _RUNTIMES.get(workspace_id)
        if runtime is None:
            runtime = WorkspaceRuntime(workspace_id)
            _RUNTIMES[workspace_id] = runtime
        if runtime.started:
            return
        runtime.started = True

    def run_in_workspace(fn, name):
        def runner():
            token = set_workspace(workspace_id)
            try:
                fn()
                if fn is restore_saved_sessions:
                    saved = STATE.load()
                    cfg = saved.get("copy_config")
                    if cfg and saved.get("copy_enabled"):
                        COPY.start(cfg)
            finally:
                reset_workspace(token)
        threading.Thread(target=runner, daemon=True, name=name).start()

    run_in_workspace(restore_saved_sessions, f"KOOLKID-MT5-Session-Restore-{workspace_id[:8]}")
    run_in_workspace(keep_saved_sessions_connected, f"KOOLKID-MT5-Persistent-Sessions-{workspace_id[:8]}")

def bad(exc):
    message = str(exc)
    lowered = message.lower()
    if "ipc timeout" in lowered or "worker timeout" in lowered:
        raise HTTPException(504, message)
    if any(text in lowered for text in ("authorization", "wrong password", "invalid account", "auth failed")):
        raise HTTPException(401, message)
    if "otp" in lowered or "certificate" in lowered:
        raise HTTPException(428, message)
    raise HTTPException(400, message)


def source_data_dir(terminal: Path) -> Path | None:
    configured = os.getenv("MT5_ACCOUNT_DATA_PATH", "").strip().strip('"')
    if configured:
        path = Path(configured).expanduser().resolve()
        if not path.is_dir():
            raise RuntimeError("MT5_ACCOUNT_DATA_PATH does not exist.")
        return path
    appdata = os.getenv("APPDATA")
    root = Path(appdata) / "MetaQuotes" / "Terminal" if appdata else None
    if root and root.is_dir():
        expected = str(terminal.parent.resolve()).lower()
        for origin in root.glob("*/origin.txt"):
            try:
                raw = origin.read_bytes()
                encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
                value = raw.decode(encoding, errors="ignore").lstrip("\ufeff").strip("\x00\r\n ").lower()
                if value == expected and (origin.parent / "config" / "accounts.dat").is_file():
                    return origin.parent
            except OSError:
                continue
    if (terminal.parent / "config" / "accounts.dat").is_file():
        return terminal.parent
    return None

def isolated_terminal(account_id: str, requested: str) -> str:
    source = Path(requested).expanduser().resolve() if requested else Path(os.getenv("ProgramFiles", "C:/Program Files")) / "MetaTrader 5" / "terminal64.exe"
    source = source.resolve()
    if source.name.lower() != "terminal64.exe" or not source.is_file():
        raise RuntimeError("The MT5 terminal64.exe installation was not found.")
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", account_id).strip("._") or "account"
    target_dir = TERMINALS / safe_id
    terminal = target_dir / "terminal64.exe"
    marker = target_dir / ".koolkid-account-session-v2"
    with TERMINAL_LOCK:
        if source != terminal and not terminal.is_file():
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source.parent, target_dir, dirs_exist_ok=True)
        if not marker.is_file():
            POOL._stop_terminal(str(terminal))
            source_data = source_data_dir(source)
            if source_data and source_data.resolve() != target_dir.resolve():
                source_config = source_data / "config"
                if source_config.is_dir():
                    shutil.copytree(source_config, target_dir / "config", dirs_exist_ok=True)
            marker.write_text("Account terminal seeded from the original MT5 profile.\n", encoding="ascii")
    if not terminal.is_file():
        raise RuntimeError("Could not prepare the isolated MT5 account terminal.")
    # Current MT5 builds copy the desktop MCP listener into portable clones.
    # Every clone otherwise competes for the same localhost ports (22345/22346),
    # which prevents additional account workers from completing startup.
    assistant_ini = target_dir / "config" / "assistant.ini"
    if assistant_ini.is_file():
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        raw = assistant_ini.read_bytes()
        encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        parser.read_string(raw.decode(encoding))
        changed = False
        for section in ("MCP.MetaEditor", "MCP.MetaTrader"):
            if parser.has_section(section) and parser.get(section, "Enable", fallback="0") != "0":
                parser.set(section, "Enable", "0")
                changed = True
        if changed:
            with assistant_ini.open("w", encoding=encoding) as handle:
                parser.write(handle, space_around_delimiters=False)
    return str(terminal)

@app.get("/")
def root():
    return FileResponse(BASE / "static" / "index.html")

@app.get("/health")
def health():
    # Public, workspace-neutral health endpoint for launcher/service checks.
    return {
        "ok": True,
        "service": "mt5-multi-account-worker",
        "revision": "mt5-routing-v4",
    }

@app.post("/demo/bootstrap")
def demo_bootstrap():
    made = []
    for i in range(1,4):
        aid = f"sim{i}"
        cfg = {
            "account_id": aid, "nickname": f"SIM Account {i}", "login": 900000+i,
            "server": "KOOLKID-SIM", "terminal_path": "", "mode": "simulation", "symbol_aliases": {}
        }
        if aid not in POOL.ids():
            POOL.connect(cfg)
        s = STATE.load()
        s["accounts"][aid] = cfg
        STATE.save(s)
        made.append(aid)
    s = STATE.load()
    s["master"], s["slaves"] = "sim1", ["sim2","sim3"]
    STATE.save(s)
    return {"ok": True, "accounts": made, "master": "sim1", "slaves": ["sim2","sim3"]}

@app.post("/accounts/connect")
def connect(req: ConnectRequest):
    try:
        saved = STATE.load()
        if req.account_id not in saved.get("accounts", {}) and len(saved.get("accounts", {})) >= 10:
            raise RuntimeError("Maximum of 10 MT5 accounts per workspace reached")
        cfg = req.model_dump(exclude={"password"})
        cfg["auto_reconnect"] = True
        if req.mode == "real":
            cfg["terminal_path"] = isolated_terminal(f"{current_workspace()}--{req.account_id}", req.terminal_path)
            cfg["portable"] = True
        if req.account_id in POOL.ids():
            info = POOL.call(req.account_id, "account_info", timeout=5)
            if int(info.get("login") or 0) == int(req.login):
                if req.mode == "real" and req.remember_session and req.password:
                    CREDENTIALS.save(req.account_id, req.password)
                return {**POOL.status(req.account_id), "account_info": info, "remembered": CREDENTIALS.has(req.account_id)}
            POOL.disconnect(req.account_id)
        POOL.connect(cfg, req.password)
        if req.mode == "real":
            if req.remember_session and req.password:
                CREDENTIALS.save(req.account_id, req.password)
            elif not req.remember_session:
                CREDENTIALS.delete(req.account_id)
        s = STATE.load()
        s["accounts"][req.account_id] = cfg
        STATE.save(s)
        _runtime().session_backoff.pop(req.account_id, None)
        return {**POOL.status(req.account_id), "account_info": POOL.call(req.account_id, "account_info", timeout=5), "remembered": CREDENTIALS.has(req.account_id)}
    except Exception as exc:
        bad(exc)

@app.post("/accounts/{account_id}/disconnect")
def disconnect(account_id: str):
    POOL.disconnect(account_id)
    s = STATE.load()
    if account_id in s.get("accounts", {}):
        s["accounts"][account_id]["auto_reconnect"] = False
        STATE.save(s)
    _runtime().session_backoff.pop(account_id, None)
    if s.get("master") == account_id:
        COPY.stop()
    return {"ok": True}

@app.post("/accounts/{account_id}/cancel")
def cancel_connect(account_id: str):
    return {"ok": POOL.cancel_connect(account_id)}

@app.delete("/accounts/{account_id}")
def remove_account(account_id: str):
    POOL.disconnect(account_id)
    CREDENTIALS.delete(account_id)
    _runtime().session_backoff.pop(account_id, None)
    s = STATE.load()
    s.get("accounts", {}).pop(account_id, None)
    if s.get("master") == account_id:
        COPY.stop()
        s["master"] = None
    s["slaves"] = [item for item in s.get("slaves", []) if item != account_id]
    STATE.save(s)
    return {"ok": True}

@app.get("/accounts")
def accounts():
    s = STATE.load()
    def snapshot(item):
        aid, cfg = item
        row = dict(cfg)
        row.update(POOL.status(aid))
        row["is_master"] = s.get("master") == aid
        row["is_slave"] = aid in s.get("slaves", [])
        row["remembered"] = CREDENTIALS.has(aid)
        row["auto_reconnect"] = cfg.get("auto_reconnect", True) is not False
        if row.get("connected"):
            try:
                row["account_info"] = POOL.call(aid, "account_info", timeout=2)
                row["last_heartbeat"] = time.time()
            except Exception as exc:
                status = POOL.status(aid)
                cached = POOL.cached(aid, "account_info", {})
                if cached:
                    row["account_info"] = cached
                row.update({"connected": bool(status.get("connected")), "connecting": bool(status.get("connecting")), "recovering": bool(status.get("recovering")), "busy": bool(status.get("connected")), "error": str(exc)})
        return row
    items = list(s.get("accounts", {}).items())[:10]
    with ThreadPoolExecutor(max_workers=len(items) or 1) as executor:
        rows = list(executor.map(snapshot, items))
    return {"accounts": rows, "master": s.get("master"), "slaves": s.get("slaves", [])}

@app.get("/accounts/{account_id}/quotes")
def account_quotes(account_id: str, symbols: str = Query(default="")):
    try:
        requested = [item.strip() for item in symbols.split(",") if item.strip()]
        return POOL.call(account_id, "quotes", {"symbols": requested}, timeout=8)
    except Exception as exc:
        bad(exc)

@app.get("/accounts/{account_id}/symbols")
def account_symbols(account_id: str, visible_only: bool = True, limit: int = 1000):
    try:
        return POOL.call(account_id, "symbols", {"visible_only": visible_only, "limit": limit}, timeout=12)
    except Exception as exc:
        bad(exc)

@app.get("/accounts/{account_id}/candles/{symbol}")
def account_candles(account_id: str, symbol: str, timeframe: str = "M15", count: int = 220):
    try:
        return POOL.call(account_id, "candles", {"symbol": symbol, "timeframe": timeframe, "count": count}, timeout=12)
    except Exception as exc:
        bad(exc)

@app.get("/accounts/{account_id}/history")
def account_history(account_id: str, days: int = 30):
    try:
        return POOL.call(account_id, "history", {"days": days}, timeout=15)
    except Exception as exc:
        bad(exc)

@app.post("/copy/start")
def start_copy(req: CopyRequest):
    try:
        if req.master_account_id not in POOL.ids():
            raise RuntimeError("Master is not connected")
        if req.master_account_id in req.slave_account_ids:
            raise RuntimeError("Master cannot also be a slave")
        for aid in req.slave_account_ids:
            if aid not in POOL.ids():
                raise RuntimeError(f"Slave not connected: {aid}")
        cfg = req.model_dump()
        COPY.start(cfg)
        s = STATE.load()
        s["master"], s["slaves"] = req.master_account_id, req.slave_account_ids
        s["copy_enabled"] = True
        STATE.save(s)
        return COPY.snapshot()
    except Exception as exc:
        bad(exc)

@app.post("/copy/stop")
def stop_copy():
    COPY.stop()
    s = STATE.load()
    s["copy_enabled"] = False
    STATE.save(s)
    return COPY.snapshot()

@app.get("/copy/status")
def copy_status():
    return COPY.snapshot()

@app.get("/copy/pending")
def copy_pending():
    return {"pending": COPY.pending_items()}

@app.post("/copy/decision")
def copy_decision(req: CopyDecisionRequest):
    try:
        return COPY.decide(req.master_ticket, req.should_copy, req.slave_account_ids)
    except Exception as exc:
        bad(exc)

@app.post("/manual-trade")
def manual_trade(req: ManualTradeRequest):
    backend_received_at = time.time()
    COPY.pause_for_execution(20)
    copy_config = COPY.config if COPY.status == "running" else None
    master_id = str((copy_config or {}).get("master_account_id") or "")
    def submit(aid):
        tag = f"KKM:{uuid.uuid4().hex[:12]}"
        try:
            volume = req.volume
            if aid != master_id:
                if req.lot_mode == "fixed": volume = req.fixed_lot
                elif req.lot_mode == "multiplier": volume = req.volume * req.multiplier
            result = POOL.call(aid, "open_trade", {
                "symbol": req.symbol, "side": req.side, "volume": volume,
                "sl": req.sl, "tp": req.tp, "magic": 0, "comment": tag,
            }, timeout=12)
            return aid, {"ok": True, "result": result, "timing": {"ui_clicked_at": req.ui_clicked_at, "backend_received_at": backend_received_at, **result.get("timing", {}), "backend_result_at": time.time()}}
        except TimeoutError:
            try:
                positions = POOL.call(aid, "positions", timeout=3)
                match = next((row for row in positions if str(row.get("comment") or "").startswith(tag)), None)
                if match:
                    return aid, {"ok": True, "result": {"retcode": 10009, "ticket": int(match.get("ticket") or 0), "reconciled_after_timeout": True}}
                return aid, {"ok": False, "error": "MT5 did not confirm the order before the safety timeout."}
            except Exception as exc:
                return aid, {"ok": False, "error": f"MT5 order confirmation timed out: {exc}"}
        except Exception as exc:
            return aid, {"ok": False, "error": str(exc)}
    out = {}
    targets = list(dict.fromkeys(req.target_account_ids))[:10]
    try:
        with ThreadPoolExecutor(max_workers=len(targets) or 1) as executor:
            for future in as_completed([executor.submit(submit, aid) for aid in targets]):
                aid, result = future.result()
                out[aid] = result
        master_row = out.get(master_id) if master_id else None
        master_result = (master_row or {}).get("result") or {}
        master_ticket = int(master_result.get("ticket") or master_result.get("order") or 0)
        if master_ticket:
            COPY.register_concurrent_open(master_ticket, {"symbol": req.symbol, "side": req.side, "volume": req.volume, "sl": req.sl, "tp": req.tp}, {aid: row for aid, row in out.items() if aid != master_id})
    finally:
        COPY.resume_after_execution()
    return {"results": out, "backend_received_at": backend_received_at, "backend_result_at": time.time()}

@app.post("/positions/close-many")
def close_many(req: MultiCloseRequest):
    received = time.time()
    def submit(target):
        aid, ticket = str(target.get("account_id") or ""), int(target.get("ticket") or 0)
        try:
            result = POOL.call(aid, "close_position", {"ticket": ticket}, timeout=12)
            return aid, {"ok": True, "ticket": ticket, "result": result, "timing": {"ui_clicked_at": req.ui_clicked_at, "backend_received_at": received, **result.get("timing", {}), "backend_result_at": time.time()}}
        except Exception as exc:
            return aid, {"ok": False, "ticket": ticket, "error": str(exc)}
    out = {}
    targets = req.targets[:10]
    with ThreadPoolExecutor(max_workers=len(targets) or 1) as executor:
        for future in as_completed([executor.submit(submit, target) for target in targets]):
            aid, result = future.result()
            out[aid] = result
    return {"results": out, "backend_received_at": received, "backend_result_at": time.time()}

@app.get("/positions")
def positions():
    rows, errors = [], {}
    for aid in POOL.ids():
        try:
            for p in POOL.call(aid, "positions"):
                p = dict(p)
                p["account_id"] = aid
                p["account_login"] = int(POOL.items[aid].config.get("login") or 0)
                p["account_nickname"] = str(POOL.items[aid].config.get("nickname") or aid)
                magic = int(p.get("magic") or 0)
                p["source"] = "manual" if magic == 0 else ("copy" if magic == COPY_MAGIC else "ea")
                rows.append(p)
        except Exception as exc:
            errors[aid] = str(exc)
    return {"positions": rows, "errors": errors}

@app.post("/positions/close")
def close(req: CloseRequest):
    try:
        return POOL.call(req.account_id, "close_position", {"ticket": req.ticket}, timeout=35)
    except TimeoutError:
        try:
            positions = POOL.call(req.account_id, "positions", timeout=15)
            if not any(int(row.get("ticket") or 0) == int(req.ticket) for row in positions):
                return {"ticket": req.ticket, "closed": True, "reconciled_after_timeout": True}
            raise RuntimeError("MT5 did not confirm the close before the safety timeout; the position is still open.")
        except RuntimeError as exc:
            bad(exc)
        except Exception as exc:
            raise RuntimeError(f"MT5 close confirmation timed out: {exc}") from exc
    except Exception as exc:
        bad(exc)

@atexit.register
def cleanup():
    try:
        _SESSION_STOP.set()
        for runtime in list(_RUNTIMES.values()):
            runtime.copy.stop()
        _CORE_POOL.close_all()
    except Exception:
        pass
