from __future__ import annotations

import os
import re
import subprocess
import threading
import time
import uuid
import ctypes
import sys
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hub_auth import current_workspace

try:
    from .config_builder import build_config
    from .ea_observer import capture_log_offsets, inspect_ea_logs
    from .ea_manager import install_files
    from .models import StartBotRequest
    from .state import ROOT, read_state, write_state
    from .terminal_manager import discover_terminals, prepare_dedicated_terminal, select_terminal, terminal_data_dir
except ImportError:  # direct `python main.py` execution
    from config_builder import build_config
    from ea_observer import capture_log_offsets, inspect_ea_logs
    from ea_manager import install_files
    from models import StartBotRequest
    from state import ROOT, read_state, write_state
    from terminal_manager import discover_terminals, prepare_dedicated_terminal, select_terminal, terminal_data_dir

_LOCK = threading.RLock()
DEFAULT_LIBRARY = ROOT.parent / "mt5_bridge" / "data" / "ea_library"
COPY_MAGIC = 987654
HUB_COMMENTS = ("kkm:", "kkcopy:", "koolkid hub", "koolkid close")


def _assignment_dir() -> Path:
    return ROOT / "data" / "workspaces" / current_workspace() / "assignments"


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


def _hidden_process_options() -> dict[str, Any]:
    if os.name != "nt":
        return {}
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    return {
        "startupinfo": startup,
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    }


def _keep_process_windows_hidden(pid: int, terminal_path: str) -> None:
    if os.name != "nt":
        return
    user32 = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def hide_window(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == int(pid) and user32.IsWindowVisible(hwnd):
            user32.ShowWindow(hwnd, 0)
        return True

    while _process_alive(pid, terminal_path):
        user32.EnumWindows(hide_window, 0)
        time.sleep(0.25)


def _terminate_process(pid: int) -> None:
    try:
        process = psutil.Process(int(pid))
        for child in process.children(recursive=True):
            child.terminate()
        process.terminate()
        try:
            process.wait(timeout=10)
        except psutil.TimeoutExpired:
            process.kill()
    except (psutil.Error, ValueError):
        pass


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


def _bot_trade_candidate(item: Any, row: dict[str, Any], baseline: set[int], expert_reason: int | None) -> bool:
    ticket = int(getattr(item, "ticket", 0) or 0)
    if ticket in baseline or str(getattr(item, "symbol", "")) != str(row.get("symbol") or ""):
        return False
    magic = int(getattr(item, "magic", 0) or 0)
    comment = str(getattr(item, "comment", "") or "").strip().lower()
    if magic in {0, COPY_MAGIC} or comment.startswith(HUB_COMMENTS):
        return False
    reason = getattr(item, "reason", None)
    return expert_reason is not None and reason is not None and int(reason) == int(expert_reason)


def _resolve_bot_magic(candidates: list[Any], row: dict[str, Any]) -> tuple[int | None, str]:
    detected = int(row.get("detected_magic") or 0)
    if detected:
        return detected, "verified"
    configured = int(row.get("configured_magic") or 0)
    available = {int(getattr(item, "magic", 0) or 0) for item in candidates}
    if configured and configured in available:
        row["detected_magic"] = configured
        return configured, "verified"
    if len(available) == 1:
        detected = available.pop()
        row["detected_magic"] = detected
        return detected, "verified"
    return None, "ambiguous" if len(available) > 1 else "pending"


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
        baseline_positions = {int(ticket) for ticket in row.get("baseline_position_tickets", [])}
        baseline_deals = {int(ticket) for ticket in row.get("baseline_deal_tickets", [])}
        instance_symbol = str(row.get("symbol") or "")
        position_candidates = [
            position for position in positions
            if str(getattr(position, "symbol", "") or "") == instance_symbol
            and _bot_trade_candidate(position, row, baseline_positions, getattr(mt5, "POSITION_REASON_EXPERT", None))
        ]
        deal_candidates = [
            deal for deal in trade_deals
            if str(getattr(deal, "symbol", "") or "") == instance_symbol
            and _bot_trade_candidate(deal, row, baseline_deals, getattr(mt5, "DEAL_REASON_EXPERT", None))
        ]
        detected_magic, attribution_status = _resolve_bot_magic(position_candidates + deal_candidates, row)
        observed_positions = [position for position in position_candidates if detected_magic and int(getattr(position, "magic", 0) or 0) == detected_magic]
        observed_deals = [deal for deal in deal_candidates if detected_magic and int(getattr(deal, "magic", 0) or 0) == detected_magic]
        close_entries = {
            int(value) for value in (
                getattr(mt5, "DEAL_ENTRY_OUT", None), getattr(mt5, "DEAL_ENTRY_OUT_BY", None),
                getattr(mt5, "DEAL_ENTRY_INOUT", None),
            ) if value is not None
        }
        settled_deals = [deal for deal in observed_deals if int(getattr(deal, "entry", -1)) in close_entries]
        settled_pl = [
            float(getattr(deal, "profit", 0) or 0) + float(getattr(deal, "swap", 0) or 0)
            + float(getattr(deal, "commission", 0) or 0) + float(getattr(deal, "fee", 0) or 0)
            for deal in settled_deals
        ]
        last = max(observed_deals, key=lambda deal: int(getattr(deal, "time_msc", 0) or 0), default=None)
        if attribution_status == "verified":
            scope = f"Bot-only MT5 activity matched to magic number {detected_magic}."
        elif attribution_status == "ambiguous":
            scope = "Bot-only totals unavailable because multiple unclaimed EA magic numbers were observed."
        else:
            scope = "Waiting for this EA to place a trade with a unique MT5 magic number."
        return {
            "account_verified": True,
            "open_positions": len(observed_positions),
            "current_pl": sum(float(getattr(pos, "profit", 0) or 0) + float(getattr(pos, "swap", 0) or 0) for pos in observed_positions),
            "today_pl": sum(float(getattr(deal, "profit", 0) or 0) + float(getattr(deal, "swap", 0) or 0) + float(getattr(deal, "commission", 0) or 0) + float(getattr(deal, "fee", 0) or 0) for deal in observed_deals),
            "last_trade": ({"ticket": int(last.ticket), "symbol": str(last.symbol), "time": datetime.fromtimestamp(int(last.time), timezone.utc).isoformat()} if last else None),
            "bot_trade_count": len(settled_deals),
            "bot_wins": len([value for value in settled_pl if value > 0]),
            "bot_losses": len([value for value in settled_pl if value < 0]),
            "bot_win_rate": round(len([value for value in settled_pl if value > 0]) / len(settled_pl) * 100, 1) if settled_pl else 0.0,
            "detected_magic": detected_magic,
            "attribution_status": attribution_status,
            "metrics_scope": scope,
            "_position_tickets": [int(getattr(pos, "ticket", 0) or 0) for pos in positions],
            "_deal_tickets": [int(getattr(deal, "ticket", 0) or 0) for deal in trade_deals],
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
                before = dict(row)
                alive = _process_alive(int(row.get("process_id") or 0), str(row.get("terminal_path") or ""))
                row["terminal_status"] = "online" if alive else "offline"
                if alive:
                    observed = inspect_ea_logs(
                        Path(str(row.get("data_path") or "")),
                        str(row.get("ea_file") or ""),
                        offsets=row.get("log_offsets") or None,
                    )
                    row["strategy_analysis"] = observed
                    row["ea_verified"] = bool(row.get("ea_verified") or observed.get("ea_verified"))
                    row["ea_status"] = "active" if row["ea_verified"] else "verifying"
                    row["last_activity"] = observed.get("last_ea_activity") or _last_activity(str(row.get("data_path") or ""))
                    row.update(_terminal_metrics(row))
                    next_status = "running" if row["ea_verified"] and row.get("account_verified") else "starting"
                    row["error"] = None if next_status == "running" else row.get("metrics_error") or observed.get("verification_error")
                else:
                    next_status = "stopped"
                    row["ea_status"] = "stopped"
                if row.get("status") != next_status:
                    row["status"] = next_status
                    row["error"] = None if alive else "Terminal process is no longer running."
                changed = changed or row != before
        if changed:
            write_state(state)
        return state.get("assignments", [])


def _safe_instance_key(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "default")).strip("._")[:80] or "default"


def start_bot(request: StartBotRequest) -> dict[str, Any]:
    with _LOCK:
        assignments = reconcile()
        instance_key = _safe_instance_key(request.instance_key)
        existing = next((
            x for x in assignments
            if int(x.get("bot_id", 0)) == request.bot_id
            and str(x.get("instance_key") or "default") == instance_key
            and x.get("status") in {"starting", "running"}
        ), None)
        if existing:
            if (int(existing["account_login"]) == request.account_login and existing["symbol"] == request.symbol and existing["timeframe"] == request.timeframe):
                return existing
            raise ValueError("This bot market instance already has a running assignment with different settings.")

        if request.account_type.lower() == "live" and not request.allow_live:
            raise ValueError("LIVE EA execution requires explicit confirmation of the testing-phase risk warning.")
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
            str(source_terminal), source_data, f"{request.account_login}-{request.bot_id}-{instance_key}"
        )
        terminal_in_use = next((x for x in assignments if x.get("status") == "running" and Path(x["terminal_path"]).resolve() == terminal.resolve()), None)
        if terminal_in_use:
            raise ValueError("This MT5 terminal is already assigned to another EA. Select an isolated terminal installation.")

        ea_source = _safe_library_file(request.ea_path)
        preset_source = _safe_library_file(request.preset_path) if request.preset_path else None
        expert, preset = install_files(data_dir, request.bot_id, ea_source, preset_source)
        assignment_id = f"ea-{uuid.uuid4().hex[:12]}"
        config_path = _assignment_dir() / assignment_id / "startup.ini"
        build_config(
            config_path, login=request.account_login, server=request.server, expert=expert, preset=preset,
            symbol=request.symbol, timeframe=request.timeframe,
            allow_trading=True, allow_dll=request.dll_required and request.allow_dll,
        )
        log_offsets = capture_log_offsets(data_dir)
        process = subprocess.Popen(
            [str(terminal), "/portable", f"/config:{config_path}"],
            cwd=str(terminal.parent),
            **_hidden_process_options(),
        )
        threading.Thread(
            target=_keep_process_windows_hidden,
            args=(process.pid, str(terminal)),
            daemon=True,
            name=f"KOOLKID-EA-Hide-{request.bot_id}",
        ).start()
        observed: dict[str, Any] = {}
        metrics: dict[str, Any] = {}
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"MetaTrader 5 exited during startup with code {process.returncode}.")
            observed = inspect_ea_logs(data_dir, request.ea_filename, offsets=log_offsets)
            if observed.get("verification_error") and not observed.get("ea_verified"):
                _terminate_process(process.pid)
                raise RuntimeError(f"MT5 could not load {request.ea_filename}: {observed['verification_error']}")
            if observed.get("ea_verified"):
                metrics = _terminal_metrics({"terminal_path": str(terminal), "account_login": request.account_login})
                if metrics.get("account_verified"):
                    break
            time.sleep(0.5)
        if not observed.get("ea_verified"):
            _terminate_process(process.pid)
            raise RuntimeError(f"MT5 did not confirm that {request.ea_filename} loaded on {request.symbol} {request.timeframe}.")
        if not metrics.get("account_verified"):
            _terminate_process(process.pid)
            raise RuntimeError(metrics.get("metrics_error") or "The assigned MT5 account could not be verified.")
        row = {
            "id": assignment_id, "worker_id": "koolkid-ea-worker", "terminal_id": terminal.parent.name,
            "account_login": request.account_login, "bot_id": request.bot_id, "instance_key": instance_key, "ea_file": request.ea_filename,
            "symbol": request.symbol, "timeframe": request.timeframe, "preset": request.preset_filename,
            "process_id": process.pid, "status": "running", "started_at": _now(), "error": None,
            "terminal_status": "online", "last_activity": observed.get("last_ea_activity") or _last_activity(str(data_dir)),
            "terminal_path": str(terminal), "data_path": str(data_dir), "config_path": str(config_path),
            "background_mode": True, "ea_verified": True, "ea_status": "active",
            "verification_message": f"MT5 confirmed {request.ea_filename} loaded on {request.symbol} {request.timeframe}.",
            "strategy_analysis": observed, "log_offsets": log_offsets,
            "configured_magic": request.configured_magic,
            "baseline_position_tickets": metrics.get("_position_tickets", []),
            "baseline_deal_tickets": metrics.get("_deal_tickets", []),
            "restart_request": request.model_dump(),
        }
        row.update(metrics)
        row.update({"open_positions": 0, "current_pl": 0.0, "today_pl": 0.0, "last_trade": None})
        state = read_state()
        state["assignments"] = [
            x for x in state.get("assignments", [])
            if not (
                int(x.get("bot_id", 0)) == request.bot_id
                and str(x.get("instance_key") or "default") == instance_key
            )
        ] + [row]
        write_state(state)
        return row


def get_bots(bot_id: int) -> list[dict[str, Any]]:
    return [x for x in reconcile() if int(x.get("bot_id", 0)) == int(bot_id)]


def get_bot(bot_id: int) -> dict[str, Any] | None:
    rows = get_bots(bot_id)
    return next((x for x in rows if x.get("status") in {"starting", "running"}), rows[0] if rows else None)


def _stop_assignment(stored: dict[str, Any]) -> dict[str, Any]:
    pid = int(stored.get("process_id") or 0)
    if _process_alive(pid, stored.get("terminal_path", "")):
        _terminate_process(pid)
    stored["status"] = "stopped"
    stored["terminal_status"] = "offline"
    stored["ea_status"] = "stopped"
    stored["ea_verified"] = False
    stored["account_verified"] = False
    stored["process_id"] = None
    stored["stopped_at"] = _now()
    stored["error"] = None
    return stored


def stop_bot_instance(bot_id: int, instance_key: str) -> dict[str, Any]:
    target_key = _safe_instance_key(instance_key)
    with _LOCK:
        state = read_state()
        stored = next((
            x for x in state.get("assignments", [])
            if int(x.get("bot_id", 0)) == int(bot_id)
            and str(x.get("instance_key") or "default") == target_key
        ), None)
        if not stored:
            raise KeyError("Bot market assignment not found.")
        result = dict(_stop_assignment(stored))
        write_state(state)
        return result


def stop_bot(bot_id: int) -> dict[str, Any]:
    with _LOCK:
        state = read_state()
        rows = [x for x in state.get("assignments", []) if int(x.get("bot_id", 0)) == int(bot_id)]
        if not rows:
            raise KeyError("Bot assignment not found.")
        stopped = [dict(_stop_assignment(row)) for row in rows]
        write_state(state)
        primary = dict(stopped[0])
        primary.update({
            "status": "stopped",
            "terminal_status": "offline",
            "process_id": None,
            "instances": stopped,
            "symbols": [str(row.get("symbol") or "") for row in stopped if row.get("symbol")],
        })
        return primary


def terminals() -> list[dict[str, str]]:
    return discover_terminals()


def restore_running_assignments() -> None:
    """Restart saved assignments independently after a service restart."""
    for row in list(read_state().get("assignments", [])):
        request = row.get("restart_request")
        if row.get("status") not in {"running", "starting"} or not isinstance(request, dict):
            continue
        try:
            start_bot(StartBotRequest(**request))
        except Exception:
            continue
