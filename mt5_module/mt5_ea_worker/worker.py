from __future__ import annotations

import os
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil

try:
    from .config_builder import build_config
    from .ea_manager import install_files
    from .models import StartBotRequest
    from .state import ROOT, read_state, write_state
    from .terminal_manager import discover_terminals, prepare_dedicated_terminal, select_terminal, terminal_data_dir
except ImportError:  # direct `python main.py` execution
    from config_builder import build_config
    from ea_manager import install_files
    from models import StartBotRequest
    from state import ROOT, read_state, write_state
    from terminal_manager import discover_terminals, prepare_dedicated_terminal, select_terminal, terminal_data_dir

_LOCK = threading.RLock()
ASSIGNMENT_DIR = ROOT / "data" / "assignments"
DEFAULT_LIBRARY = ROOT.parent / "mt5_bridge" / "data" / "ea_library"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_bool(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _process_alive(pid: int, terminal_path: str) -> bool:
    try:
        process = psutil.Process(int(pid))
        return process.is_running() and Path(process.exe()).resolve() == Path(terminal_path).resolve()
    except (psutil.Error, OSError, ValueError):
        return False


def _safe_library_file(raw: str) -> Path:
    path = Path(raw).resolve()
    allowed = Path(os.getenv("MT5_EA_LIBRARY_ROOT", str(DEFAULT_LIBRARY))).resolve()
    if not path.is_relative_to(allowed):
        raise ValueError("EA files must come from the configured KOOLKID upload library.")
    return path


def _last_activity(data_dir: str) -> str | None:
    newest = 0.0
    for folder in (Path(data_dir) / "logs", Path(data_dir) / "MQL5" / "Logs"):
        if not folder.is_dir():
            continue
        for path in folder.glob("*.log"):
            try:
                newest = max(newest, path.stat().st_mtime)
            except OSError:
                pass
    return datetime.fromtimestamp(newest, timezone.utc).isoformat() if newest else None


def _terminal_metrics(row: dict[str, Any]) -> dict[str, Any]:
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return {"account_verified": False, "metrics_error": "MetaTrader5 is not installed in the EA worker environment."}
    try:
        if not mt5.initialize(path=str(row["terminal_path"]), portable=True, timeout=10000):
            return {"account_verified": False, "metrics_error": f"Could not inspect assigned terminal: {mt5.last_error()}"}
        info = mt5.account_info()
        actual_login = int(getattr(info, "login", 0) or 0) if info else 0
        if actual_login != int(row["account_login"]):
            return {"account_verified": False, "metrics_error": f"Assigned terminal opened account #{actual_login or 'none'} instead of #{row['account_login']}."}
        positions = list(mt5.positions_get() or [])
        start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        deals = list(mt5.history_deals_get(start, datetime.now(timezone.utc)) or [])
        trade_types = {int(mt5.DEAL_TYPE_BUY), int(mt5.DEAL_TYPE_SELL)}
        trade_deals = [deal for deal in deals if int(getattr(deal, "type", -1)) in trade_types]
        last = max(trade_deals, key=lambda deal: int(getattr(deal, "time_msc", 0) or 0), default=None)
        return {
            "account_verified": True,
            "open_positions": len(positions),
            "current_pl": sum(float(getattr(pos, "profit", 0) or 0) + float(getattr(pos, "swap", 0) or 0) for pos in positions),
            "today_pl": sum(float(getattr(deal, "profit", 0) or 0) + float(getattr(deal, "swap", 0) or 0) + float(getattr(deal, "commission", 0) or 0) + float(getattr(deal, "fee", 0) or 0) for deal in trade_deals),
            "last_trade": ({"ticket": int(last.ticket), "symbol": str(last.symbol), "time": datetime.fromtimestamp(int(last.time), timezone.utc).isoformat()} if last else None),
            "metrics_checked_at": _now(),
            "metrics_error": None,
        }
    finally:
        try:
            mt5.shutdown()
        except Exception:
            pass


def reconcile() -> list[dict[str, Any]]:
    with _LOCK:
        state = read_state()
        changed = False
        for row in state.get("assignments", []):
            if row.get("status") in {"starting", "running", "stopping"}:
                alive = _process_alive(int(row.get("process_id") or 0), str(row.get("terminal_path") or ""))
                next_status = "running" if alive else "stopped"
                row["terminal_status"] = "online" if alive else "offline"
                row["last_activity"] = _last_activity(str(row.get("data_path") or ""))
                if alive:
                    row.update(_terminal_metrics(row))
                if row.get("status") != next_status:
                    row["status"] = next_status
                    row["error"] = None if alive else "Terminal process is no longer running."
                    changed = True
        if changed:
            write_state(state)
        return state.get("assignments", [])


def start_bot(request: StartBotRequest) -> dict[str, Any]:
    with _LOCK:
        assignments = reconcile()
        existing = next((x for x in assignments if int(x.get("bot_id", 0)) == request.bot_id and x.get("status") in {"starting", "running"}), None)
        if existing:
            if (int(existing["account_login"]) == request.account_login and existing["symbol"] == request.symbol and existing["timeframe"] == request.timeframe):
                return existing
            raise ValueError("This bot already has a running assignment with different settings.")

        if request.account_type.lower() == "live" and (not request.allow_live or not _env_bool("MT5_ALLOW_LIVE_EA")):
            raise ValueError("LIVE EA execution is locked. Confirm LIVE execution and set MT5_ALLOW_LIVE_EA=1 in the worker environment.")
        if request.dll_required and (not request.allow_dll or not _env_bool("MT5_ALLOW_DLL_IMPORTS")):
            raise ValueError("This EA requires DLL imports. Explicit approval and MT5_ALLOW_DLL_IMPORTS=1 are required.")

        source_terminal = Path(request.bridge_terminal_path) if request.bridge_terminal_path else select_terminal(request.terminal_path)
        source_data = request.bridge_data_path
        if not source_data:
            try:
                source_data = str(terminal_data_dir(source_terminal if source_terminal.is_file() else source_terminal / "terminal64.exe"))
            except ValueError:
                source_data = None
        terminal, data_dir = prepare_dedicated_terminal(
            str(source_terminal), source_data, f"{request.account_login}-{request.bot_id}"
        )
        terminal_in_use = next((x for x in assignments if x.get("status") == "running" and Path(x["terminal_path"]).resolve() == terminal.resolve()), None)
        if terminal_in_use:
            raise ValueError("This MT5 terminal is already assigned to another EA. Select an isolated terminal installation.")

        ea_source = _safe_library_file(request.ea_path)
        preset_source = _safe_library_file(request.preset_path) if request.preset_path else None
        expert, preset = install_files(data_dir, request.bot_id, ea_source, preset_source)
        assignment_id = f"ea-{uuid.uuid4().hex[:12]}"
        config_path = ASSIGNMENT_DIR / assignment_id / "startup.ini"
        build_config(
            config_path, login=request.account_login, server=request.server, expert=expert, preset=preset,
            symbol=request.symbol, timeframe=request.timeframe,
            allow_trading=True, allow_dll=request.dll_required and request.allow_dll,
        )
        process = subprocess.Popen(
            [str(terminal), "/portable", f"/config:{config_path}"],
            cwd=str(terminal.parent),
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        time.sleep(5)
        if process.poll() is not None:
            raise RuntimeError(f"MetaTrader 5 exited during startup with code {process.returncode}.")
        row = {
            "id": assignment_id, "worker_id": "koolkid-ea-worker", "terminal_id": terminal.parent.name,
            "account_login": request.account_login, "bot_id": request.bot_id, "ea_file": request.ea_filename,
            "symbol": request.symbol, "timeframe": request.timeframe, "preset": request.preset_filename,
            "process_id": process.pid, "status": "running", "started_at": _now(), "error": None,
            "terminal_status": "online", "last_activity": _last_activity(str(data_dir)),
            "terminal_path": str(terminal), "data_path": str(data_dir), "config_path": str(config_path),
        }
        metrics = _terminal_metrics(row)
        if not metrics.get("account_verified"):
            try:
                psutil.Process(process.pid).terminate()
            except psutil.Error:
                pass
            raise RuntimeError(metrics.get("metrics_error") or "The assigned MT5 account could not be verified.")
        row.update(metrics)
        state = read_state()
        state["assignments"] = [x for x in state.get("assignments", []) if int(x.get("bot_id", 0)) != request.bot_id] + [row]
        write_state(state)
        return row


def get_bot(bot_id: int) -> dict[str, Any] | None:
    return next((x for x in reconcile() if int(x.get("bot_id", 0)) == int(bot_id)), None)


def stop_bot(bot_id: int) -> dict[str, Any]:
    with _LOCK:
        row = get_bot(bot_id)
        if not row:
            raise KeyError("Bot assignment not found.")
        pid = int(row.get("process_id") or 0)
        if _process_alive(pid, row.get("terminal_path", "")):
            process = psutil.Process(pid)
            for child in process.children(recursive=True):
                child.terminate()
            process.terminate()
            try:
                process.wait(timeout=10)
            except psutil.TimeoutExpired:
                process.kill()
        state = read_state()
        stored = next(x for x in state.get("assignments", []) if int(x.get("bot_id", 0)) == int(bot_id))
        stored["status"] = "stopped"
        stored["terminal_status"] = "offline"
        stored["stopped_at"] = _now()
        stored["error"] = None
        write_state(state)
        return stored


def terminals() -> list[dict[str, str]]:
    return discover_terminals()
