from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

import multi_account_client
import native_runtime
from hub_auth import current_workspace, reset_workspace, set_workspace
from native_strategies import NATIVE_PRESETS, evaluate
from store import read_state, update_state

_THREADS: dict[str, threading.Thread] = {}
_STOPS: dict[str, threading.Event] = {}
_LOCK = threading.RLock()
_EXECUTION_LOCKS: dict[str, threading.RLock] = {}
MODES = {"analysis", "alert", "manual", "auto"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event(event: str, **extra: Any) -> None:
    row = {"time": _now(), "event": event, **extra}
    def mut(state):
        rows = state.setdefault("ai_auto_select_events", [])
        rows.insert(0, row)
        del rows[100:]
        return row
    update_state(mut)
def _runtime(**updates: Any) -> dict[str, Any]:
    def mut(state):
        row = state.setdefault("ai_auto_select_runtime", {})
        row.update(updates)
        return dict(row)
    return update_state(mut)


def _bot_map() -> dict[int, dict[str, Any]]:
    return {int(row.get("id") or 0): dict(row) for row in read_state().get("bots", [])}


def _history_metrics(history: list[dict[str, Any]], bot_id: int) -> dict[str, Any]:
    prefix = f"KKN{int(bot_id)}"
    rows = [row for row in history if str(row.get("source") or "").startswith(prefix)]
    pnl = [float(row.get("net_pl") or 0) for row in rows]
    wins = sum(value > 0 for value in pnl)
    losses = sum(value < 0 for value in pnl)
    trades = len(pnl)
    win_rate = round(wins / trades * 100, 1) if trades else 0.0
    net_pl = round(sum(pnl), 2)
    bonus = 0.0
    if trades >= 3:
        bonus += max(-5.0, min(5.0, (win_rate - 50.0) * 0.10))
        bonus += 2.0 if net_pl > 0 else -2.0 if net_pl < 0 else 0.0
        bonus += min(2.0, trades / 10.0)
    return {"trades": trades, "wins": wins, "losses": losses, "win_rate": win_rate, "net_pl": net_pl, "selection_bonus": round(bonus, 2)}
def _account_mode(login: int) -> str:
    worker = multi_account_client.connected_by_login().get(int(login))
    if not worker:
        raise RuntimeError(f"MT5 account #{int(login)} is disconnected.")
    info = dict(worker.get("account_info") or {})
    trade_mode = info.get("trade_mode")
    if trade_mode is None:
        return "unknown"
    try:
        return {"0": "demo", "1": "demo", "2": "live"}.get(str(trade_mode), "unknown")
    except (TypeError, ValueError):
        return "unknown"


def _verify_execution_account(login: int, *, allow_live: bool = False) -> str:
    worker = multi_account_client.connected_by_login().get(int(login))
    if not worker:
        raise RuntimeError(f"MT5 account #{int(login)} is disconnected.")
    info = dict(worker.get("account_info") or {})
    if bool(info.get("read_only")) or str(info.get("access_mode") or "").lower() == "investor":
        raise PermissionError("AI execution is blocked on investor/read-only MT5 accounts.")
    mode = {"0": "demo", "1": "demo", "2": "live"}.get(str(info.get("trade_mode")), "unknown")
    if mode == "unknown":
        raise PermissionError("KOOLKID could not verify the MT5 account mode. AI execution remains locked.")
    if mode == "live" and not allow_live:
        raise PermissionError("LIVE AI execution requires explicit confirmation of the real-money risk warning.")
    return mode


def _positions(login: int) -> list[dict[str, Any]]:
    payload = multi_account_client.request("/positions", timeout=10)
    return [dict(row) for row in payload.get("positions", []) if int(row.get("account_login") or 0) == int(login)]


def _history(login: int) -> list[dict[str, Any]]:
    try:
        rows = multi_account_client.account_request(login, "/history?days=30", timeout=15)
        return [dict(row) for row in rows]
    except RuntimeError:
        return []
def _position_block(bot_id: int, symbol: str, positions: list[dict[str, Any]]) -> str | None:
    meta = NATIVE_PRESETS.get(int(bot_id)) or {}
    magic = int(meta.get("magic") or 0)
    same_symbol = [row for row in positions if str(row.get("symbol") or "") == symbol]
    native_magics = {int(row.get("magic") or 0) for row in NATIVE_PRESETS.values() if int(row.get("magic") or 0)}
    if any(str(row.get("comment") or "").startswith("KKN") or int(row.get("magic") or 0) in native_magics for row in same_symbol):
        return "Auto Select already has a KOOLKID native position on this symbol."
    if int(bot_id) == 1003 and same_symbol:
        return "Gold source rule allows only one open position on this symbol."
    if any(int(row.get("magic") or 0) == magic for row in same_symbol):
        return "This native strategy already has an open position on the symbol."
    return None


def _enabled_ids(config: dict[str, Any]) -> list[int]:
    requested = config.get("enabled_bot_ids")
    if isinstance(requested, list):
        values = []
        for item in requested:
            try:
                bot_id = int(item)
            except (TypeError, ValueError):
                continue
            if bot_id in NATIVE_PRESETS and bot_id not in values:
                values.append(bot_id)
        return values
    return [bot_id for bot_id, meta in NATIVE_PRESETS.items() if meta.get("ready")]


def scan_once(account_login: int, symbol: str, enabled_bot_ids: list[int] | None = None) -> dict[str, Any]:
    login = int(account_login)
    symbol = str(symbol).strip()
    if not login or not symbol:
        raise RuntimeError("Auto Select requires an account and symbol.")
    market, _ = native_runtime.fetch_market_snapshot(login, symbol)
    market.update({"symbol": symbol, "account_login": login})
    positions = _positions(login)
    history = _history(login)
    bots = _bot_map()
    ids = enabled_bot_ids if enabled_bot_ids is not None else [bot_id for bot_id, meta in NATIVE_PRESETS.items() if meta.get("ready")]
    results: list[dict[str, Any]] = []

    for bot_id in ids:
        meta = dict(NATIVE_PRESETS.get(int(bot_id)) or {})
        bot = bots.get(int(bot_id), {})
        if not meta:
            continue
        if not meta.get("ready") or not bot.get("native_ready", meta.get("ready")):
            results.append({
                "bot_id": int(bot_id), "name": meta.get("name"), "title": meta.get("title"),
                "decision": "REJECT", "stage": "SOURCE_REQUIRED", "score": 0.0,
                "selection_score": 0.0, "reason": "MQ5 source is required before this preset can be evaluated natively.",
                "history": _history_metrics(history, int(bot_id)), "signal": None,
            })
            continue
        signal = evaluate(str(meta["key"]), market).to_dict()
        perf = _history_metrics(history, int(bot_id))
        independent_running = bot.get("status") == "running" and bool((bot.get("native_config") or {}).get("enabled"))
        block = "This preset is already running independently in Bot Library." if independent_running else _position_block(int(bot_id), symbol, positions)
        valid = bool(signal.get("valid"))
        stage = str(signal.get("stage") or "SCANNING")
        if block:
            decision, reason = "REJECT", block
        elif valid:
            decision, reason = "APPROVE", str(signal.get("reason") or "Complete native setup.")
        elif stage.startswith("BLOCKED"):
            decision, reason = "REJECT", str(signal.get("reason") or "Source risk filter blocked this setup.")
        else:
            decision, reason = "WAIT", str(signal.get("reason") or "Native setup is incomplete.")
        raw_score = float(signal.get("score") or 0)
        selection_score = raw_score + (float(perf["selection_bonus"]) if decision == "APPROVE" else 0.0)
        results.append({
            "bot_id": int(bot_id), "name": meta.get("name"), "title": meta.get("title"),
            "subtitle": meta.get("subtitle"), "decision": decision, "stage": stage,
            "score": round(raw_score, 2), "selection_score": round(selection_score, 2),
            "reason": reason, "history": perf, "signal": signal,
        })

    approved = [row for row in results if row["decision"] == "APPROVE" and (row.get("signal") or {}).get("valid")]
    approved.sort(key=lambda row: (float(row["selection_score"]), float(row["score"])), reverse=True)
    selected = approved[0] if approved else None
    return {
        "generated_at": _now(), "account_login": login, "account_mode": _account_mode(login),
        "symbol": symbol, "decision": "APPROVE" if selected else "WAIT",
        "selected": selected, "results": sorted(results, key=lambda row: (row["decision"] == "APPROVE", float(row["selection_score"])), reverse=True),
        "rules": {
            "completed_candles_only": True,
            "confidence_cannot_complete_setup": True,
            "history_is_tiebreaker_only": True,
            "live_execution_requires_confirmation": True,
        },
    }
def scan_and_store(account_login: int, symbol: str, enabled_bot_ids: list[int] | None = None) -> dict[str, Any]:
    snapshot = scan_once(account_login, symbol, enabled_bot_ids)
    _save_snapshot(snapshot)
    return snapshot


def execute_selected(snapshot: dict[str, Any], *, allow_live: bool = False, expected_config: dict[str, Any] | None = None) -> dict[str, Any]:
    with _LOCK:
        lock = _EXECUTION_LOCKS.setdefault(current_workspace(), threading.RLock())
    with lock:
        return _execute_selected(snapshot, allow_live=allow_live, expected_config=expected_config)


def _execute_selected(snapshot: dict[str, Any], *, allow_live: bool, expected_config: dict[str, Any] | None) -> dict[str, Any]:
    selected = dict(snapshot.get("selected") or {})
    signal = dict(selected.get("signal") or {})
    if selected.get("decision") != "APPROVE" or not signal.get("valid"):
        raise RuntimeError("Auto Select has no fully confirmed native setup to execute.")
    login = int(snapshot.get("account_login") or 0)
    symbol = str(snapshot.get("symbol") or "")
    _verify_execution_account(login, allow_live=allow_live)
    bot_id = int(selected.get("bot_id") or 0)
    market, _ = native_runtime.fetch_market_snapshot(login, symbol)
    current = evaluate(str((NATIVE_PRESETS.get(bot_id) or {}).get("key") or ""), {**market, "symbol": symbol, "account_login": login}).to_dict()
    if not current.get("valid") or current.get("signal_key") != signal.get("signal_key"):
        raise RuntimeError("The selected setup changed before execution. Auto Select will rescan instead of chasing it.")
    bot = _bot_map().get(bot_id, {})
    if bot.get("status") == "running" and (bot.get("native_config") or {}).get("enabled"):
        raise RuntimeError("This preset is already running independently in Bot Library.")
    block = _position_block(bot_id, symbol, _positions(login))
    if block:
        raise RuntimeError(block)
    _verify_execution_account(login, allow_live=allow_live)
    if expected_config is not None:
        active = read_state().get("ai_auto_select_config") or {}
        if not active.get("enabled") or active != expected_config:
            raise RuntimeError("Auto Select stopped or settings changed during the scan.")
    return native_runtime.execute_signal_once(
        bot_id, login, symbol, current, market.get("symbol_info") or {}, demo_only=not allow_live,
    )


def _save_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    def mut(state):
        state["ai_auto_select_snapshot"] = snapshot
        return snapshot
    return update_state(mut)
def _cycle(config: dict[str, Any]) -> None:
    login = int(config.get("account_login") or 0)
    symbol = str(config.get("symbol") or "")
    mode = str(config.get("mode") or "analysis").lower()
    enabled_ids = _enabled_ids(config)
    bots = _bot_map()
    managed_ids = []
    for bot_id, bot in bots.items():
        managed = dict(bot.get("native_managed_position") or {})
        if not managed:
            continue
        managed_login = int(managed.get("account_login") or bot.get("account_login") or login)
        managed_symbol = str(managed.get("symbol") or bot.get("symbol") or symbol)
        if managed_login == login and managed_symbol == symbol:
            managed_ids.append(bot_id)
    if managed_ids:
        native_runtime.manage_positions_once(login, symbol, managed_ids)
    snapshot = scan_once(login, symbol, enabled_ids)
    _save_snapshot(snapshot)
    selected = dict(snapshot.get("selected") or {})
    _runtime(
        status="running", last_scan_at=snapshot["generated_at"], last_error=None,
        last_decision=snapshot.get("decision"), selected_bot_id=selected.get("bot_id"),
        selected_name=selected.get("name"), selected_title=selected.get("title"),
        selected_score=selected.get("selection_score"), selected_stage=selected.get("stage"),
    )
    if not selected:
        return
    signal_key = str((selected.get("signal") or {}).get("signal_key") or "")
    state = read_state()
    last_alert_key = str((state.get("ai_auto_select_runtime") or {}).get("last_alert_key") or "")
    if mode in {"alert", "manual", "auto"} and signal_key and signal_key != last_alert_key:
        _runtime(last_alert_key=signal_key, last_alert_at=_now())
        _event("native_setup_selected", bot_id=selected.get("bot_id"), name=selected.get("name"),
               symbol=symbol, score=selected.get("selection_score"), signal_key=signal_key, mode=mode)
    if mode != "auto" or not signal_key:
        return
    try:
        execution = execute_selected(snapshot, allow_live=bool(config.get("allow_live")), expected_config=config)
    except RuntimeError as exc:
        if "already submitted" in str(exc).lower() or "changed before execution" in str(exc).lower():
            return
        raise
    _runtime(last_execution_at=_now(), last_execution=execution, status="running")
    _event("native_auto_trade_executed", bot_id=selected.get("bot_id"), name=selected.get("name"),
           symbol=symbol, direction=execution.get("direction"), signal_key=signal_key)
def _runner(workspace_id: str, stop_event: threading.Event) -> None:
    token = set_workspace(workspace_id)
    try:
        _runtime(status="starting", started_at=_now(), last_error=None)
        while not stop_event.is_set():
            config = dict(read_state().get("ai_auto_select_config") or {})
            if not config.get("enabled"):
                _runtime(status="stopped", stopped_at=_now())
                return
            interval = max(15, min(int(config.get("scan_seconds") or 30), 300))
            try:
                _cycle(config)
            except PermissionError as exc:
                _runtime(status="blocked", last_error=str(exc), last_error_at=_now())
            except Exception as exc:
                _runtime(status="waiting", last_error=str(exc), last_error_at=_now())
            if stop_event.wait(interval):
                break
        _runtime(status="stopped", stopped_at=_now())
    finally:
        reset_workspace(token)
        with _LOCK:
            if _THREADS.get(workspace_id) is threading.current_thread():
                _THREADS.pop(workspace_id, None)
                _STOPS.pop(workspace_id, None)


def start(workspace_id: str) -> None:
    with _LOCK:
        existing = _THREADS.get(workspace_id)
        if existing and existing.is_alive():
            return
        stop_event = threading.Event()
        _STOPS[workspace_id] = stop_event
        thread = threading.Thread(target=_runner, args=(workspace_id, stop_event), daemon=True, name=f"KOOLKID-AutoSelect-{workspace_id[:8]}")
        _THREADS[workspace_id] = thread
        thread.start()


def stop(workspace_id: str) -> None:
    with _LOCK:
        event = _STOPS.get(workspace_id)
        if event:
            event.set()


def restore(workspace_id: str) -> bool:
    config = dict(read_state().get("ai_auto_select_config") or {})
    if not config.get("enabled"):
        return False
    start(workspace_id)
    return True


def configure(workspace_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    enabled = bool(payload.get("enabled"))
    mode = str(payload.get("mode") or "analysis").lower()
    if mode not in MODES:
        raise RuntimeError("Auto Select mode must be analysis, alert, manual, or auto.")
    if enabled:
        login = int(payload.get("account_login") or 0)
        symbol = str(payload.get("symbol") or "").strip()
        if not login or not symbol:
            raise RuntimeError("Choose a connected MT5 account and symbol before starting Auto Select.")
        enabled_ids = _enabled_ids(payload)
        if not enabled_ids:
            raise RuntimeError("Enable at least one native preset before starting Auto Select.")
        account_mode = _account_mode(login)
        allow_live = bool(payload.get("confirm_live"))
        if mode == "auto":
            _verify_execution_account(login, allow_live=allow_live)
        if mode == "auto" and bool((read_state().get("ai_auto_config") or {}).get("enabled")):
            raise RuntimeError("Stop Human Apostle Auto-Trading before enabling Auto Select automatic execution.")
        config = {
            "enabled": True, "mode": mode, "account_login": login, "symbol": symbol,
            "enabled_bot_ids": enabled_ids,
            "scan_seconds": max(15, min(int(payload.get("scan_seconds") or 30), 300)),
            "allow_live": allow_live if mode == "auto" else False,
            "account_mode": account_mode,
            "updated_at": _now(),
        }
        def mut(state):
            state["ai_auto_select_config"] = config
            state.setdefault("ai_auto_select_runtime", {}).update({"status": "starting", "last_error": None})
            return config
        update_state(mut)
        _event("auto_select_started", account_login=login, symbol=symbol, mode=mode, enabled_bot_ids=config["enabled_bot_ids"])
        start(workspace_id)
    else:
        def mut(state):
            config = dict(state.get("ai_auto_select_config") or {})
            config["enabled"] = False
            config["updated_at"] = _now()
            state["ai_auto_select_config"] = config
            state.setdefault("ai_auto_select_runtime", {})["status"] = "stopping"
            return config
        update_state(mut)
        _event("auto_select_stopped")
        stop(workspace_id)
    return status(workspace_id)


def manual_execute(*, confirm_live: bool = False) -> dict[str, Any]:
    snapshot = dict(read_state().get("ai_auto_select_snapshot") or {})
    execution = execute_selected(snapshot, allow_live=bool(confirm_live))
    _runtime(last_execution_at=_now(), last_execution=execution)
    selected = dict(snapshot.get("selected") or {})
    _event("native_manual_confirm_executed", bot_id=selected.get("bot_id"), name=selected.get("name"),
           symbol=snapshot.get("symbol"), direction=execution.get("direction"))
    return execution
def status(workspace_id: str) -> dict[str, Any]:
    state = read_state()
    config = dict(state.get("ai_auto_select_config") or {})
    runtime = dict(state.get("ai_auto_select_runtime") or {})
    with _LOCK:
        thread = _THREADS.get(workspace_id)
        alive = bool(thread and thread.is_alive())
    if not config.get("enabled") and not alive:
        runtime["status"] = "stopped"
    return {
        "enabled": bool(config.get("enabled")), "scanner_alive": alive,
        "config": config, "runtime": runtime,
        "snapshot": state.get("ai_auto_select_snapshot"),
        "events": list(state.get("ai_auto_select_events") or [])[:50],
        "available_presets": [
            {"bot_id": bot_id, "name": meta.get("name"), "title": meta.get("title"),
             "subtitle": meta.get("subtitle"), "ready": bool(meta.get("ready")),
             "source": meta.get("source"), "entry_tf": meta.get("entry_tf"), "bias_tf": meta.get("bias_tf")}
            for bot_id, meta in NATIVE_PRESETS.items()
        ],
        "execution_lock": "live_requires_explicit_confirmation",
    }
