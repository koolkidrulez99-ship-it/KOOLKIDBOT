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
from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from .models import ConnectRequest, CopyRequest, CopyDecisionRequest, ManualTradeRequest, CloseRequest, MultiCloseRequest, ModifyPositionRequest, PartialCloseRequest
from .state import State
from .pool import Pool
from .credential_store import CredentialStore
from .copy_engine import CopyEngine, COPY_MAGIC

import sys
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent))
from hub_auth import current_workspace, internal_workspace_signature, reset_workspace, set_workspace, verify_internal_workspace, workspace_from_authorization, workspace_ids

TERMINALS = BASE / "data" / "terminals"
TEMPLATE_MQL5 = TERMINALS / "_worker_template" / "MQL5"
BROKER_SEEDS = BASE / "broker_seeds"
TERMINAL_LOCK = threading.RLock()
_CORE_POOL = Pool()
_SESSION_STOP = threading.Event()
_RUNTIMES: dict[str, "WorkspaceRuntime"] = {}
_RUNTIMES_LOCK = threading.RLock()
_REAPER_STARTED = False
WORKSPACE_IDLE_SECONDS = max(60, int(os.getenv("MT5_WORKSPACE_IDLE_SECONDS", "300")))


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
        with _CORE_POOL.lock:
            items = list(_CORE_POOL.items.items())
        return {self._external(aid): runtime for aid, runtime in items if str(runtime.config.get("_workspace") or "") == self.workspace_id}

    @property
    def pending(self):
        with _CORE_POOL.lock:
            pending = list(_CORE_POOL.pending.items())
        return {self._external(aid): value for aid, value in pending if aid.startswith(f"{self.workspace_id}--")}

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
        self.copy_groups = {
            "1": CopyEngine(self.pool, self.state, "1"),
            "2": CopyEngine(self.pool, self.state, "2"),
        }
        self.copy = self.copy_groups["1"]
        self.copy_restore_lock = threading.Lock()
        self.session_backoff: dict[str, dict[str, object]] = {}
        self.session_stop = threading.Event()
        self.last_activity = time.time()
        self.read_cache: dict[str, tuple[float, object]] = {}
        self.read_cache_lock = threading.RLock()
        self.accounts_snapshot_lock = threading.Lock()
        self.positions_snapshot_lock = threading.Lock()
        self.started = False

    def touch(self) -> None:
        self.last_activity = time.time()


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


def _snapshot_cache_get(runtime: WorkspaceRuntime, key: str, ttl: float):
    now = time.monotonic()
    with runtime.read_cache_lock:
        item = runtime.read_cache.get(key)
        if not item:
            return None
        created_at, value = item
        if now - created_at > ttl:
            runtime.read_cache.pop(key, None)
            return None
        return value


def _snapshot_cache_set(runtime: WorkspaceRuntime, key: str, value):
    with runtime.read_cache_lock:
        runtime.read_cache[key] = (time.monotonic(), value)
    return value


def _snapshot_cache_clear(runtime: WorkspaceRuntime, *keys: str) -> None:
    with runtime.read_cache_lock:
        for key in keys:
            runtime.read_cache.pop(key, None)


def _copy_group(group_id: str = "1") -> CopyEngine:
    key = "2" if str(group_id) == "2" else "1"
    return _runtime().copy_groups[key]

def _copy_state_key(base: str, group_id: str) -> str:
    return base if str(group_id) == "1" else f"{base}_2"

def _copy_status_payload():
    runtime = _runtime()
    groups = {gid: engine.snapshot() for gid, engine in runtime.copy_groups.items()}
    combined_activity = sorted(
        [row for snapshot in groups.values() for row in snapshot.get("activity", [])],
        key=lambda row: float(row.get("time") or 0),
        reverse=True,
    )[:200]
    primary = groups["1"]
    return {
        **primary,
        "status": "running" if any(item["status"] == "running" for item in groups.values()) else "stopped",
        "pending_count": sum(int(item.get("pending_count") or 0) for item in groups.values()),
        "activity": combined_activity,
        "groups": groups,
        "copy_anywhere_groups": [
            gid for gid, item in groups.items()
            if item.get("status") == "running"
            and isinstance(item.get("config"), dict)
            and item["config"].get("approval_required") is False
        ],
    }

app = FastAPI(title="KOOLKID MT5 Multi-Account", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5055",
        "http://localhost:5055",
        "https://koolkidbot.org",
        "https://www.koolkidbot.org",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=False,
    allow_private_network=True,
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
        runtime = _runtime()
        runtime.touch()
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

    preferred: list[str] = []
    for group_id in ("1", "2"):
        if not state.get(_copy_state_key("copy_enabled", group_id)):
            continue
        cfg = state.get(_copy_state_key("copy_config", group_id))
        if not isinstance(cfg, dict):
            continue
        for aid in [cfg.get("master_account_id"), *(cfg.get("slave_account_ids") or [])]:
            key = str(aid or "")
            if key and key not in preferred:
                preferred.append(key)
    order = {aid: index for index, aid in enumerate(preferred)}
    rows.sort(key=lambda cfg: (order.get(str(cfg.get("account_id") or ""), len(order)), str(cfg.get("account_id") or "")))
    return rows


def _saved_password(cfg: dict) -> str:
    if cfg.get("remember_session", True) is False:
        return ""
    return CREDENTIALS.load(str(cfg.get("account_id") or ""))


def _connect_saved(cfg: dict) -> None:
    aid = str(cfg.get("account_id") or "")
    if not aid or aid in POOL.ids() or aid in POOL.pending:
        return
    prepared = dict(cfg)
    prepared["server"] = normalize_mt5_server(prepared.get("server") or "")
    if str(prepared.get("mode") or "real") == "real":
        broker = str(prepared.get("broker") or "")
        terminal_source = broker_terminal_source(broker, prepared.get("terminal_path") or "")
        prepared["terminal_path"] = isolated_terminal(f"{current_workspace()}--{aid}", terminal_source, broker)
        prepared["portable"] = True
        prepared["broker_seeded"] = broker_seed_dir(broker) is not None
    POOL.connect(prepared, _saved_password(cfg))


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


def _restore_copy_groups_if_ready():
    runtime = _runtime()
    with runtime.copy_restore_lock:
        saved = STATE.load()
        connected = set(POOL.ids())
        for group_id in ("1", "2"):
            cfg = saved.get(_copy_state_key("copy_config", group_id))
            enabled = bool(saved.get(_copy_state_key("copy_enabled", group_id)))
            engine = _copy_group(group_id)
            if not cfg or not enabled or engine.status == "running":
                continue
            master_id = str(cfg.get("master_account_id") or "")
            slave_ids = [str(item) for item in cfg.get("slave_account_ids", [])]
            required = {master_id, *slave_ids} - {""}
            if required and required.issubset(connected):
                try:
                    engine.start(cfg)
                    engine.log("copy_restored_after_reconnect", accounts=sorted(required))
                except Exception as exc:
                    engine.log("restore_error", error=str(exc))


def _runtime_requires_persistence(runtime: WorkspaceRuntime) -> bool:
    state = runtime.state.load()
    return bool(
        state.get("copy_enabled")
        or state.get("copy_enabled_2")
        or any(engine.status == "running" for engine in runtime.copy_groups.values())
    )


def keep_saved_sessions_connected():
    # If the broker/network/terminal is unavailable during startup, do not give up
    # after three attempts. Keep trying with bounded backoff until the saved account
    # is back online or the user explicitly disconnects/removes it.
    runtime = _runtime()
    while not _SESSION_STOP.is_set() and not runtime.session_stop.wait(5):
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
        _restore_copy_groups_if_ready()


def _workspace_saved_copy_enabled(workspace_id: str) -> bool:
    state = State(BASE / "data" / "workspaces" / workspace_id / "state.json").load()
    return bool(state.get("copy_enabled") or state.get("copy_enabled_2"))


def _release_idle_workspace(runtime: WorkspaceRuntime) -> bool:
    if not runtime.started or _runtime_requires_persistence(runtime):
        return False
    if time.time() - float(runtime.last_activity or 0) < WORKSPACE_IDLE_SECONDS:
        return False

    runtime.session_stop.set()
    for aid in list(runtime.pool.ids()):
        try:
            runtime.pool.disconnect(aid)
        except Exception:
            pass
    runtime.session_backoff.clear()
    runtime.started = False
    return True


def _workspace_reaper():
    while not _SESSION_STOP.wait(30):
        with _RUNTIMES_LOCK:
            runtimes = list(_RUNTIMES.values())
        for runtime in runtimes:
            try:
                _release_idle_workspace(runtime)
            except Exception:
                pass


@app.on_event("startup")
def startup_restore():
    global _REAPER_STARTED
    if not _REAPER_STARTED:
        _REAPER_STARTED = True
        threading.Thread(target=_workspace_reaper, daemon=True, name="KOOLKID-MT5-Workspace-Reaper").start()
    if os.getenv("MT5_SKIP_SESSION_RESTORE", "").strip().lower() in {"1", "true", "yes", "on"}:
        return
    users_file = BASE.parent / "mt5_bridge" / "data" / "mt5_hub_users.json"
    for workspace_id in workspace_ids(users_file):
        if _workspace_saved_copy_enabled(workspace_id):
            _start_workspace(workspace_id)


def _start_workspace(workspace_id: str) -> None:
    with _RUNTIMES_LOCK:
        runtime = _RUNTIMES.get(workspace_id)
        if runtime is None:
            runtime = WorkspaceRuntime(workspace_id)
            _RUNTIMES[workspace_id] = runtime
        if runtime.started:
            return
        runtime.session_stop.clear()
        runtime.touch()
        runtime.started = True

    def session_manager():
        token = set_workspace(workspace_id)
        try:
            restore_saved_sessions()
            _restore_copy_groups_if_ready()
            if not runtime.session_stop.is_set() and not _SESSION_STOP.is_set():
                keep_saved_sessions_connected()
        finally:
            reset_workspace(token)

    threading.Thread(
        target=session_manager,
        daemon=True,
        name=f"KOOLKID-MT5-Session-Manager-{workspace_id[:8]}",
    ).start()

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


def normalize_mt5_server(value: str) -> str:
    server = str(value or "").strip()
    compact = re.sub(r"\s+", "", server).lower()
    if compact == "deriv-demo":
        return "Deriv-Demo"
    if compact == "deriv-real":
        return "Deriv-Real"
    if compact in {"qberxcapital-server", "qberxcaptial-server"}:
        return "QberxCapital-Server"
    if compact in {"weltrade", "weltrade-demo", "weltradedemo", "weltrade-live", "weltradelive"}:
        return "Weltrade"
    return server


def broker_terminal_source(broker: str, requested: str = "") -> str:
    """Resolve the MT5 installation/template for the selected broker."""
    explicit = str(requested or "").strip().strip('"')
    if explicit:
        return explicit

    broker_name = str(broker or "").strip()
    slug = re.sub(r"[^A-Za-z0-9]+", "_", broker_name).strip("_").upper()
    if slug:
        broker_specific = os.getenv(f"MT5_TERMINAL_{slug}", "").strip().strip('"')
        if broker_specific:
            return broker_specific

    aliases = {
        "hfm": ("hfm", "hf markets", "hfmarkets", "hotforex"),
        "xm global": ("xm global", "xmglobal", "xm mt5"),
        "qberx capital": ("qberx", "qberx capital", "qb capital"),
        "weltrade": ("weltrade",),
        "exness": ("exness",),
        "ic markets": ("ic markets", "icmarkets"),
        "pepperstone": ("pepperstone",),
        "fxtm": ("fxtm",),
        "fbs": ("fbs",),
        "eightcap": ("eightcap",),
        "admiral markets": ("admiral",),
        "ftmo": ("ftmo",),
    }
    hints = aliases.get(broker_name.lower(), ())
    if hints and os.name == "nt":
        for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
            root = os.getenv(env_name)
            if not root or not Path(root).is_dir():
                continue
            for folder in Path(root).iterdir():
                label = folder.name.lower()
                if any(hint in label for hint in hints):
                    candidate = folder / "terminal64.exe"
                    if candidate.is_file():
                        return str(candidate)

    return os.getenv("MT5_TERMINAL_PATH", "").strip().strip('"')


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

def broker_seed_dir(broker: str) -> Path | None:
    slug = re.sub(r"[^a-z0-9]+", "_", str(broker or "").strip().lower()).strip("_")
    if not slug:
        return None
    seed = BROKER_SEEDS / slug
    return seed if seed.is_dir() else None


def apply_broker_seed(target_dir: Path, broker: str) -> None:
    seed = broker_seed_dir(broker)
    if not seed:
        return
    seed_config = seed / "config"
    if seed_config.is_dir():
        target_config = target_dir / "config"
        target_config.mkdir(parents=True, exist_ok=True)
        for candidate in seed_config.iterdir():
            if candidate.is_file():
                shutil.copy2(candidate, target_config / candidate.name)
    seed_bases = seed / "Bases"
    if seed_bases.is_dir():
        shutil.copytree(seed_bases, target_dir / "Bases", dirs_exist_ok=True)


def isolated_terminal(account_id: str, requested: str, broker: str = "") -> str:
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
            if TEMPLATE_MQL5.is_dir():
                shutil.copytree(TEMPLATE_MQL5, target_dir / "MQL5", dirs_exist_ok=True)
        if not marker.is_file():
            _CORE_POOL._stop_terminal(str(terminal))
            source_data = source_data_dir(source)
            if source_data and source_data.resolve() != target_dir.resolve():
                source_config = source_data / "config"
                target_config = target_dir / "config"
                target_config.mkdir(parents=True, exist_ok=True)
                for name in ("servers.dat", "terminal.lic", "dnsperf.dat"):
                    candidate = source_config / name
                    if candidate.is_file():
                        shutil.copy2(candidate, target_config / name)
            marker.write_text("Account terminal seeded without account credentials.\n", encoding="ascii")
        apply_broker_seed(target_dir, broker)
        if broker_seed_dir(broker):
            try:
                (target_dir / ".koolkid-broker-bootstrap-required").unlink()
            except FileNotFoundError:
                pass
    if not terminal.is_file():
        raise RuntimeError("Could not prepare the isolated MT5 account terminal.")
    # Current MT5 builds copy the desktop MCP listener into portable clones.
    # Every clone otherwise competes for the same localhost ports (22345/22346),
    # which prevents additional account workers from completing startup.
    # Disable MetaTrader/MetaEditor MCP before the very first terminal start.
    # Fresh portable clones do not have assistant.ini yet; waiting for the file to
    # appear is too late because MT5 may already bind 22345/22346 and break IPC.
    config_dir = target_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    assistant_ini = config_dir / "assistant.ini"
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    encoding = "utf-8"
    if assistant_ini.is_file():
        raw = assistant_ini.read_bytes()
        encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        parser.read_string(raw.decode(encoding))
    for section in ("MCP.MetaEditor", "MCP.MetaTrader"):
        if not parser.has_section(section):
            parser.add_section(section)
        parser.set(section, "Enable", "0")
    if not parser.has_section("MCP.Custom"):
        parser.add_section("MCP.Custom")
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
        "revision": "mt5-routing-v8",
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
        prior_cfg = dict((saved.get("accounts") or {}).get(req.account_id) or {})
        cfg = req.model_dump(exclude={"password"})
        cfg["server"] = normalize_mt5_server(cfg.get("server") or "")
        cfg["auto_reconnect"] = True
        for key in ("budget", "budget_updated_at"):
            if key in prior_cfg:
                cfg[key] = prior_cfg[key]
        if req.mode == "real":
            terminal_source = broker_terminal_source(req.broker, req.terminal_path)
            cfg["terminal_path"] = isolated_terminal(f"{current_workspace()}--{req.account_id}", terminal_source, req.broker)
            cfg["portable"] = True
            cfg["broker_seeded"] = broker_seed_dir(req.broker) is not None
        if req.account_id in POOL.ids():
            info = POOL.call(req.account_id, "account_info", timeout=5)
            actual_server = str(info.get("server") or "").strip()
            requested_server = str(cfg.get("server") or "").strip()
            requested_key = requested_server.replace(" ", "").lower()
            actual_key = actual_server.replace(" ", "").lower()
            weltrade_alias = (
                str(req.broker or "").strip().lower() == "weltrade"
                and requested_key == "weltrade"
                and actual_key in {"weltrade-demo", "weltradedemo", "weltrade-live", "weltradelive"}
            )
            named_server_matches = (
                not requested_server
                or "." in requested_server
                or ":" in requested_server
                or requested_key == actual_key
                or weltrade_alias
            )
            existing_access_mode = str(POOL.items[req.account_id].config.get("access_mode") or "trading")
            requested_access_mode = str(cfg.get("access_mode") or "trading")
            if int(info.get("login") or 0) == int(req.login) and named_server_matches and existing_access_mode == requested_access_mode:
                if req.mode == "real" and req.remember_session and req.password:
                    CREDENTIALS.save(req.account_id, req.password)
                saved["accounts"][req.account_id] = cfg
                STATE.save(saved)
                return {**POOL.status(req.account_id), "broker": req.broker, "server": cfg.get("server"), "account_info": info, "remembered": CREDENTIALS.has(req.account_id)}
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

@app.put("/accounts/{account_id}/budget")
def set_account_budget(account_id: str, payload: dict = None):
    payload = payload or {}
    s = STATE.load()
    cfg = (s.get("accounts") or {}).get(account_id)
    if cfg is None:
        raise HTTPException(404, "MT5 account is not registered in this workspace.")
    reset = bool(payload.get("reset"))
    raw = payload.get("budget")
    if reset or raw is None:
        cfg.pop("budget", None)
        cfg.pop("budget_updated_at", None)
    else:
        try:
            budget = float(raw)
        except (TypeError, ValueError):
            raise HTTPException(422, "Budget must be a positive number.")
        if budget <= 0:
            raise HTTPException(422, "Budget must be greater than zero.")
        if account_id in POOL.ids():
            info = POOL.call(account_id, "account_info", timeout=5)
            balance = float(info.get("balance") or 0)
            if balance > 0 and budget > balance + 1e-9:
                raise HTTPException(422, f"Budget cannot exceed the current MT5 balance ({balance:.2f}).")
        cfg["budget"] = round(budget, 2)
        cfg["budget_updated_at"] = time.time()
    s["accounts"][account_id] = cfg
    STATE.save(s)
    try:
        return COPY.budget_status(account_id)
    except Exception:
        budget = cfg.get("budget")
        return {"budget_enabled": budget is not None, "budget": budget, "virtual_balance": budget}


@app.post("/accounts/{account_id}/disconnect")
def disconnect(account_id: str):
    POOL.disconnect(account_id)
    s = STATE.load()
    if account_id in s.get("accounts", {}):
        s["accounts"][account_id]["auto_reconnect"] = False
        STATE.save(s)
    _runtime().session_backoff.pop(account_id, None)
    for group_id in ("1", "2"):
        if s.get(_copy_state_key("master", group_id)) == account_id:
            _copy_group(group_id).stop()
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
    for group_id in ("1", "2"):
        master_key = _copy_state_key("master", group_id)
        slaves_key = _copy_state_key("slaves", group_id)
        enabled_key = _copy_state_key("copy_enabled", group_id)
        config_key = _copy_state_key("copy_config", group_id)
        map_key = _copy_state_key("copy_map", group_id)
        if s.get(master_key) == account_id:
            _copy_group(group_id).stop()
            s[master_key] = None
            s[enabled_key] = False
            s[config_key] = None
            s[map_key] = {}
        s[slaves_key] = [item for item in s.get(slaves_key, []) if item != account_id]
        cfg = s.get(config_key)
        if isinstance(cfg, dict):
            cfg["slave_account_ids"] = [item for item in cfg.get("slave_account_ids", []) if item != account_id]
    STATE.save(s)
    return {"ok": True}

@app.get("/accounts")
def accounts():
    runtime = _runtime()
    cached = _snapshot_cache_get(runtime, "accounts", 0.8)
    if cached is not None:
        return cached

    with runtime.accounts_snapshot_lock:
        cached = _snapshot_cache_get(runtime, "accounts", 0.8)
        if cached is not None:
            return cached

        pool = runtime.pool
        credentials = runtime.credentials
        s = runtime.state.load()

        def snapshot(item):
            aid, cfg = item
            row = dict(cfg)
            row.update(pool.status(aid))
            masters = [s.get(_copy_state_key("master", gid)) for gid in ("1", "2")]
            slave_lists = [s.get(_copy_state_key("slaves", gid), []) for gid in ("1", "2")]
            row["is_master"] = aid in masters
            row["is_slave"] = any(aid in values for values in slave_lists)
            row["remembered"] = credentials.has(aid)
            row["access_mode"] = str(cfg.get("access_mode") or "trading")
            row["read_only"] = row["access_mode"] == "investor"
            row["auto_reconnect"] = cfg.get("auto_reconnect", True) is not False
            row["budget"] = cfg.get("budget")
            row["budget_enabled"] = cfg.get("budget") is not None
            if row.get("connected"):
                try:
                    row["account_info"] = pool.call(aid, "account_info", timeout=2)
                    row["last_heartbeat"] = time.time()
                except Exception as exc:
                    status = pool.status(aid)
                    account_info = pool.cached(aid, "account_info", {})
                    if account_info:
                        row["account_info"] = account_info
                    row.update({"connected": bool(status.get("connected")), "connecting": bool(status.get("connecting")), "recovering": bool(status.get("recovering")), "busy": bool(status.get("connected")), "error": str(exc)})
            return row

        items = list(s.get("accounts", {}).items())[:10]
        with ThreadPoolExecutor(max_workers=len(items) or 1) as executor:
            rows = list(executor.map(snapshot, items))
        groups = {
            gid: {
                "group_id": gid,
                "master": s.get(_copy_state_key("master", gid)),
                "slaves": s.get(_copy_state_key("slaves", gid), []),
                "enabled": bool(s.get(_copy_state_key("copy_enabled", gid))),
            }
            for gid in ("1", "2")
        }
        result = {
            "accounts": rows,
            "master": groups["1"]["master"],
            "slaves": groups["1"]["slaves"],
            "groups": groups,
        }
        return _snapshot_cache_set(runtime, "accounts", result)

@app.get("/accounts/{account_id}/quotes")
def account_quotes(account_id: str, symbols: str = Query(default="")):
    try:
        runtime = _runtime()
        requested = [item.strip() for item in symbols.split(",") if item.strip()]
        key = f"quotes:{account_id}:{','.join(requested)}"
        cached = _snapshot_cache_get(runtime, key, 0.25)
        if cached is not None:
            return cached
        return _snapshot_cache_set(runtime, key, runtime.pool.call(account_id, "quotes", {"symbols": requested}, timeout=8))
    except Exception as exc:
        bad(exc)

@app.get("/accounts/{account_id}/symbols")
def account_symbols(account_id: str, visible_only: bool = True, limit: int = 1000):
    try:
        return POOL.call(account_id, "symbols", {"visible_only": visible_only, "limit": limit}, timeout=12)
    except Exception as exc:
        bad(exc)

@app.get("/accounts/{account_id}/symbol-info/{symbol}")
def account_symbol_info(account_id: str, symbol: str):
    try:
        runtime = _runtime()
        key = f"symbol-info:{account_id}:{symbol}"
        cached = _snapshot_cache_get(runtime, key, 15.0)
        if cached is not None:
            return cached
        return _snapshot_cache_set(runtime, key, runtime.pool.call(account_id, "symbol_info", {"symbol": symbol}, timeout=8))
    except Exception as exc:
        bad(exc)

@app.get("/accounts/{account_id}/candles/{symbol}")
def account_candles(account_id: str, symbol: str, timeframe: str = "M15", count: int = 220):
    try:
        runtime = _runtime()
        key = f"candles:{account_id}:{symbol}:{timeframe}:{int(count)}"
        cached = _snapshot_cache_get(runtime, key, 1.0)
        if cached is not None:
            return cached
        value = runtime.pool.call(account_id, "candles", {"symbol": symbol, "timeframe": timeframe, "count": count}, timeout=12)
        return _snapshot_cache_set(runtime, key, value)
    except Exception as exc:
        bad(exc)

@app.get("/accounts/{account_id}/history")
def account_history(account_id: str, days: int = 30):
    try:
        runtime = _runtime()
        key = f"history:{account_id}:{int(days)}"
        cached = _snapshot_cache_get(runtime, key, 5.0)
        if cached is not None:
            return cached
        value = runtime.pool.call(account_id, "history", {"days": days}, timeout=15)
        return _snapshot_cache_set(runtime, key, value)
    except Exception as exc:
        bad(exc)

@app.post("/copy/start")
def start_copy(req: CopyRequest):
    try:
        group_id = str(req.group_id)
        engine = _copy_group(group_id)
        if req.master_account_id not in POOL.ids():
            raise RuntimeError("Master is not connected")
        if req.master_account_id in req.slave_account_ids:
            raise RuntimeError("Master cannot also be a slave in the same group")
        other_group = "2" if group_id == "1" else "1"
        other_engine = _copy_group(other_group)
        other_master = str((other_engine.config or {}).get("master_account_id") or "")
        if other_master and other_master == req.master_account_id:
            raise RuntimeError("The same account cannot be used as Master in both Copy Trader groups.")
        for aid in req.slave_account_ids:
            if aid not in POOL.ids():
                raise RuntimeError(f"Slave not connected: {aid}")
            slave_cfg = POOL.items[aid].config
            if str(slave_cfg.get("access_mode") or "trading").lower() == "investor":
                raise RuntimeError(f"Investor/read-only account cannot be used as a Copy Trader slave: {aid}")
        cfg = req.model_dump()
        cfg.pop("group_id", None)
        engine.start(cfg)
        s = STATE.load()
        s[_copy_state_key("master", group_id)] = req.master_account_id
        s[_copy_state_key("slaves", group_id)] = req.slave_account_ids
        s[_copy_state_key("copy_enabled", group_id)] = True
        STATE.save(s)
        return _copy_status_payload()
    except Exception as exc:
        bad(exc)

@app.post("/copy/stop")
def stop_copy(group_id: str = Query(default="1")):
    group_id = "2" if str(group_id) == "2" else "1"
    runtime = _runtime()
    engine = runtime.copy_groups[group_id]
    engine.stop()
    engine.config = None
    with engine.lock:
        engine.copy_map.clear()
        engine.pending.clear()
        engine.ignored.clear()
    s = runtime.state.load()
    s[_copy_state_key("copy_enabled", group_id)] = False
    s[_copy_state_key("copy_config", group_id)] = None
    s[_copy_state_key("copy_map", group_id)] = {}
    s[_copy_state_key("master", group_id)] = None
    s[_copy_state_key("slaves", group_id)] = []
    runtime.state.save(s)
    return _copy_status_payload()

@app.get("/copy/status")
def copy_status():
    return _copy_status_payload()

@app.put("/copy/preferences")
def copy_preferences(payload: dict = Body(default_factory=dict), group_id: str = Query(default="1")):
    try:
        engine = _copy_group(group_id)
        preferences = engine.update_preferences(payload)
        return {"ok": True, "group_id": engine.group_id, "preferences": preferences, "status": engine.status}
    except Exception as exc:
        bad(exc)

@app.get("/copy/pending")
def copy_pending():
    pending = []
    for group_id in ("1", "2"):
        pending.extend(_copy_group(group_id).pending_items())
    return {"pending": pending}

@app.post("/copy/decision")
def copy_decision(req: CopyDecisionRequest):
    try:
        return _copy_group(req.group_id).decide(req.master_ticket, req.should_copy, req.slave_account_ids)
    except Exception as exc:
        bad(exc)

@app.post("/manual-trade")
def manual_trade(req: ManualTradeRequest):
    backend_received_at = time.time()
    runtime = _runtime()
    pool = runtime.pool
    copy_engine = runtime.copy
    copy_engines = list(runtime.copy_groups.values())
    active_copy_engines = [
        engine for engine in copy_engines
        if engine.status == "running" and isinstance(engine.config, dict)
    ]
    master_ids = {
        str(engine.config.get("master_account_id") or "")
        for engine in active_copy_engines
    } - {""}
    master_id = next(iter(master_ids), "")
    targets = list(dict.fromkeys(req.target_account_ids))[:10]
    for aid in targets:
        try:
            info = dict(pool.call(aid, "account_info", timeout=5) or {})
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Could not verify MT5 account {aid}: {exc}")
        if bool(info.get("read_only")) or str(info.get("access_mode") or "").lower() == "investor":
            raise HTTPException(status_code=403, detail=f"Trading is blocked on investor/read-only MT5 account {aid}.")
        trade_mode = info.get("trade_mode")
        account_mode = str(getattr(pool.items.get(aid), "config", {}).get("mode") or "real").lower()
        if trade_mode is None and account_mode != "simulation":
            raise HTTPException(status_code=403, detail=f"KOOLKID could not verify the MT5 account mode for {aid}.")
        if trade_mode is not None:
            try:
                is_live = int(trade_mode) == 2
            except (TypeError, ValueError):
                raise HTTPException(status_code=403, detail=f"KOOLKID could not verify the MT5 account mode for {aid}.")
            if is_live and not req.confirm_live:
                raise HTTPException(status_code=403, detail="LIVE trading requires explicit confirmation of the testing-phase risk warning.")

    def submit(aid):
        requested_comment = str(req.comment or "KOOLKID")
        prefix = "KKM" if int(req.magic or 0) == 0 and requested_comment == "KOOLKID" else re.sub(r"[^A-Za-z0-9:_-]+", "", requested_comment)[:18] or "KOOLKID"
        tag = f"{prefix}:{uuid.uuid4().hex[:8]}"[:31]
        try:
            volume = req.volume
            if aid not in master_ids:
                if req.lot_mode == "fixed": volume = req.fixed_lot
                elif req.lot_mode == "multiplier": volume = req.volume * req.multiplier
            order_payload = {
                "symbol": req.symbol, "side": req.side, "volume": volume,
                "sl": req.sl, "tp": req.tp, "magic": int(req.magic or 0), "comment": tag,
            }
            copy_engine.enforce_budget(aid, order_payload)
            result = pool.call(aid, "open_trade", order_payload, timeout=12)
            return aid, {"ok": True, "result": result, "timing": {"ui_clicked_at": req.ui_clicked_at, "backend_received_at": backend_received_at, **result.get("timing", {}), "backend_result_at": time.time()}}
        except TimeoutError:
            try:
                positions = pool.call(aid, "positions", timeout=3)
                match = next((row for row in positions if str(row.get("comment") or "").startswith(tag)), None)
                if match:
                    return aid, {"ok": True, "result": {"retcode": 10009, "ticket": int(match.get("ticket") or 0), "reconciled_after_timeout": True}}
                return aid, {"ok": False, "error": "MT5 did not confirm the order before the safety timeout."}
            except Exception as exc:
                return aid, {"ok": False, "error": f"MT5 order confirmation timed out: {exc}"}
        except Exception as exc:
            return aid, {"ok": False, "error": str(exc)}
    out = {}
    for engine in copy_engines:
        engine.pause_for_execution(20)
    try:
        with ThreadPoolExecutor(max_workers=len(targets) or 1) as executor:
            for future in as_completed([executor.submit(submit, aid) for aid in targets]):
                aid, result = future.result()
                out[aid] = result
        for engine in active_copy_engines:
            cfg = engine.config or {}
            group_master_id = str(cfg.get("master_account_id") or "")
            master_row = out.get(group_master_id) if group_master_id else None
            master_result = (master_row or {}).get("result") or {}
            master_ticket = int(master_result.get("ticket") or master_result.get("order") or 0)
            if not master_ticket:
                continue
            group_slaves = set(str(item) for item in cfg.get("slave_account_ids", []))
            already_submitted_slaves = {
                aid: row for aid, row in out.items()
                if aid in group_slaves and aid != group_master_id
            }
            engine.register_concurrent_open(
                master_ticket,
                {"symbol": req.symbol, "side": req.side, "volume": req.volume, "sl": req.sl, "tp": req.tp},
                already_submitted_slaves,
            )
    finally:
        for engine in copy_engines:
            engine.resume_after_execution()
    _snapshot_cache_clear(runtime, "positions", "accounts")
    return {"results": out, "backend_received_at": backend_received_at, "backend_result_at": time.time()}

@app.post("/positions/modify")
def modify_position(req: ModifyPositionRequest):
    try:
        result = POOL.call(req.account_id, "modify_position", {"ticket": req.ticket, "sl": req.sl, "tp": req.tp}, timeout=15)
        _snapshot_cache_clear(_runtime(), "positions")
        return result
    except Exception as exc:
        bad(exc)

@app.post("/positions/close-partial")
def close_partial(req: PartialCloseRequest):
    try:
        result = POOL.call(req.account_id, "close_partial", {"ticket": req.ticket, "volume": req.volume}, timeout=20)
        _snapshot_cache_clear(_runtime(), "positions", "accounts")
        return result
    except Exception as exc:
        bad(exc)

@app.post("/positions/close-many")
def close_many(req: MultiCloseRequest):
    received = time.time()
    pool = _runtime().pool
    def submit(target):
        aid, ticket = str(target.get("account_id") or ""), int(target.get("ticket") or 0)
        try:
            result = pool.call(aid, "close_position", {"ticket": ticket}, timeout=12)
            return aid, {"ok": True, "ticket": ticket, "result": result, "timing": {"ui_clicked_at": req.ui_clicked_at, "backend_received_at": received, **result.get("timing", {}), "backend_result_at": time.time()}}
        except Exception as exc:
            return aid, {"ok": False, "ticket": ticket, "error": str(exc)}
    out = {}
    targets = req.targets[:10]
    with ThreadPoolExecutor(max_workers=len(targets) or 1) as executor:
        for future in as_completed([executor.submit(submit, target) for target in targets]):
            aid, result = future.result()
            out[aid] = result
    _snapshot_cache_clear(_runtime(), "positions", "accounts")
    return {"results": out, "backend_received_at": received, "backend_result_at": time.time()}

@app.get("/positions")
def positions():
    runtime = _runtime()
    cached = _snapshot_cache_get(runtime, "positions", 0.5)
    if cached is not None:
        return cached

    with runtime.positions_snapshot_lock:
        cached = _snapshot_cache_get(runtime, "positions", 0.5)
        if cached is not None:
            return cached

        rows, errors = [], {}
        pool = runtime.pool
        pool_items = pool.items
        for aid in pool.ids():
            try:
                for position in pool.call(aid, "positions"):
                    position = dict(position)
                    position["account_id"] = aid
                    runtime_row = pool_items.get(aid)
                    config = runtime_row.config if runtime_row else {}
                    position["account_login"] = int(config.get("login") or 0)
                    position["account_nickname"] = str(config.get("nickname") or aid)
                    magic = int(position.get("magic") or 0)
                    comment = str(position.get("comment") or "")
                    position["source"] = "native" if comment.startswith("KKN") else ("manual" if magic == 0 else ("copy" if magic == COPY_MAGIC else "ea"))
                    rows.append(position)
            except Exception as exc:
                errors[aid] = str(exc)
        return _snapshot_cache_set(runtime, "positions", {"positions": rows, "errors": errors})

@app.post("/positions/close")
def close(req: CloseRequest):
    try:
        result = POOL.call(req.account_id, "close_position", {"ticket": req.ticket}, timeout=35)
        _snapshot_cache_clear(_runtime(), "positions", "accounts")
        return result
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
            for engine in runtime.copy_groups.values():
                engine.stop()
        _CORE_POOL.close_all()
    except Exception:
        pass
