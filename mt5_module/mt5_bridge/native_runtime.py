from __future__ import annotations

import math
import threading
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import multi_account_client
from hub_auth import reset_workspace, set_workspace
from store import read_state, update_state
from native_strategies import NATIVE_PRESETS, evaluate
from native_strategies.common import Series, atr

_THREADS: dict[tuple[str, int], threading.Thread] = {}
_STOPS: dict[tuple[str, int], threading.Event] = {}
_LOCK = threading.RLock()
_TIMEFRAME_COUNTS = {"M1": 700, "M5": 500, "M15": 500, "M30": 450, "H1": 360, "H4": 260, "D1": 180}
_BASE_TIMEFRAME_COUNTS = {"M5": 500, "M15": 500, "H1": 360, "H4": 260, "D1": 10}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _key(workspace_id: str, bot_id: int) -> tuple[str, int]:
    return workspace_id, int(bot_id)


def _preset(bot_id: int) -> dict[str, Any] | None:
    row = NATIVE_PRESETS.get(int(bot_id))
    return dict(row) if row else None


def _primary_bias_timeframe(preset: dict[str, Any]) -> str:
    raw = str(preset.get("bias_tf") or "").upper().replace("+", " ")
    for token in raw.split():
        if token in _TIMEFRAME_COUNTS:
            return token
    return "H1"


def configured_timeframes(
    bot_id: int,
    bot: dict[str, Any] | None = None,
    *,
    execution_timeframe: str | None = None,
    bias_timeframe: str | None = None,
) -> tuple[str, str]:
    preset = _preset(bot_id) or {}
    row = bot or _bot(bot_id) or {}
    config = dict(row.get("native_config") or {})
    exec_tf = str(execution_timeframe or config.get("execution_timeframe") or row.get("timeframe") or preset.get("entry_tf") or "M5").upper()
    bias_tf = str(bias_timeframe or config.get("bias_timeframe") or row.get("bias_timeframe") or _primary_bias_timeframe(preset)).upper()
    if exec_tf not in _TIMEFRAME_COUNTS or bias_tf not in _TIMEFRAME_COUNTS:
        raise RuntimeError("Unsupported native execution or bias timeframe.")
    return exec_tf, bias_tf


def prepare_strategy_market(
    bot_id: int,
    market: dict[str, Any],
    bot: dict[str, Any] | None = None,
    *,
    execution_timeframe: str | None = None,
    bias_timeframe: str | None = None,
) -> tuple[dict[str, Any], str, str]:
    preset = _preset(bot_id) or {}
    exec_tf, bias_tf = configured_timeframes(
        bot_id, bot, execution_timeframe=execution_timeframe, bias_timeframe=bias_timeframe,
    )
    if not isinstance(market.get(exec_tf), Series) or not isinstance(market.get(bias_tf), Series):
        raise RuntimeError(f"Required {exec_tf}/{bias_tf} candle history is unavailable.")
    prepared = dict(market)
    canonical_exec = str(preset.get("entry_tf") or exec_tf).upper()
    canonical_bias = _primary_bias_timeframe(preset)
    if canonical_exec in _TIMEFRAME_COUNTS:
        prepared[canonical_exec] = market[exec_tf]
    if canonical_bias in _TIMEFRAME_COUNTS:
        prepared[canonical_bias] = market[bias_tf]
    prepared["_configured_execution_timeframe"] = exec_tf
    prepared["_configured_bias_timeframe"] = bias_tf
    return prepared, exec_tf, bias_tf


def _bot(bot_id: int) -> dict[str, Any] | None:
    return next((dict(row) for row in read_state().get("bots", []) if int(row.get("id") or 0) == int(bot_id)), None)

def _patch_bot(bot_id: int, **updates: Any) -> dict[str, Any]:
    def mut(state):
        row = next((b for b in state.get("bots", []) if int(b.get("id") or 0) == int(bot_id)), None)
        if row is None:
            raise KeyError(bot_id)
        row.update(updates)
        return dict(row)
    return update_state(mut)


def _runtime(bot_id: int, **updates: Any) -> dict[str, Any]:
    bot = _bot(bot_id) or {}
    current = dict(bot.get("native_runtime") or {})
    current.update(updates)
    _patch_bot(bot_id, native_runtime=current)
    return current


def _connected_worker(login: int) -> dict[str, Any]:
    worker = multi_account_client.connected_by_login().get(int(login))
    if not worker:
        raise RuntimeError(f"MT5 account #{int(login)} is disconnected.")
    return worker


def _verify_account(login: int, allow_live: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    worker = _connected_worker(login)
    info = dict(worker.get("account_info") or {})
    if bool(info.get("read_only")) or str(info.get("access_mode") or "").lower() == "investor":
        raise PermissionError("Native preset execution is blocked on investor/read-only MT5 accounts.")
    trade_mode = info.get("trade_mode")
    if trade_mode is None:
        raise RuntimeError("KOOLKID could not verify the MT5 account mode.")
    live = int(trade_mode) == 2
    if live and not allow_live:
        raise PermissionError("LIVE native preset execution requires explicit LIVE confirmation.")
    return worker, info

def _fetch_market(
    login: int,
    symbol: str,
    extra_timeframes: set[str] | list[str] | tuple[str, ...] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    quote_rows = multi_account_client.account_request(login, f"/quotes?symbols={quote(symbol)}", timeout=8)
    if not quote_rows:
        raise RuntimeError(f"No live quote is available for {symbol}.")
    q = dict(quote_rows[0])
    symbol_info = multi_account_client.account_request(login, f"/symbol-info/{quote(symbol)}", timeout=8)
    data: dict[str, Any] = {"quote": q, "symbol_info": dict(symbol_info or {})}
    counts = dict(_BASE_TIMEFRAME_COUNTS)
    for tf in {str(item).upper() for item in (extra_timeframes or [])}:
        if tf in _TIMEFRAME_COUNTS:
            counts[tf] = max(counts.get(tf, 0), _TIMEFRAME_COUNTS[tf])
    for tf, count in counts.items():
        rows = multi_account_client.account_request(login, f"/candles/{quote(symbol)}?timeframe={tf}&count={count}", timeout=15)
        data[tf] = Series.from_rows(rows)
        if tf == "D1" and rows:
            data["day_start"] = int(rows[-1].get("time") or 0)
    return data, q


def _positions(login: int) -> list[dict[str, Any]]:
    rows = multi_account_client.request("/positions", timeout=10).get("positions", [])
    return [dict(row) for row in rows if int(row.get("account_login") or 0) == int(login)]


def _history(login: int, days: int = 2) -> list[dict[str, Any]]:
    try:
        rows = multi_account_client.account_request(login, f"/history?days={int(days)}", timeout=12)
        return [dict(row) for row in rows]
    except RuntimeError:
        return []

def _signal_registry_key(bot_id: int, signal_key: str) -> str:
    return f"{int(bot_id)}:{signal_key}"


def _already_attempted(bot_id: int, signal_key: str) -> bool:
    return _signal_registry_key(bot_id, signal_key) in (read_state().get("native_signal_attempts") or {})


def _record_attempt(bot_id: int, signal_key: str, status: str, **extra: Any) -> None:
    key = _signal_registry_key(bot_id, signal_key)
    row = {"bot_id": int(bot_id), "signal_key": signal_key, "status": status, "updated_at": _now(), **extra}
    def mut(state):
        registry = state.setdefault("native_signal_attempts", {})
        registry[key] = {**dict(registry.get(key) or {}), **row}
        if len(registry) > 500:
            oldest = sorted(registry.items(), key=lambda item: str((item[1] or {}).get("updated_at") or ""))[:len(registry)-500]
            for old_key, _ in oldest:
                registry.pop(old_key, None)
        return registry[key]
    update_state(mut)


def _source_prefix(bot_id: int) -> str:
    # Legacy comment prefix kept only for recovering positions opened before
    # KOOLKID switched to human-readable MT5 comments.
    return f"KKN{int(bot_id)}"


def _mt5_bot_comment(bot: dict[str, Any]) -> str:
    name = " ".join(str(bot.get("name") or f"BOT {int(bot.get('id') or 0)}").split())
    # MT5 order comments are broker-limited (commonly 31 chars). Keep the
    # requested KKBOT(NAME) format and trim only the name when necessary.
    max_name = 31 - len("KKBOT()")
    return f"KKBOT({name[:max_name].rstrip()})"


def _has_position_conflict(bot_id: int, symbol: str, positions: list[dict[str, Any]]) -> bool:
    preset = _preset(bot_id) or {}
    magic = int(preset.get("magic") or 0)
    same_symbol = [row for row in positions if str(row.get("symbol") or "") == symbol]
    if int(bot_id) == 1003:
        return bool(same_symbol)
    return any(int(row.get("magic") or 0) == magic for row in same_symbol)

def _budget_for_login(login: int) -> float | None:
    profile = next((row for row in read_state().get("profiles", []) if int(row.get("login") or 0) == int(login)), None)
    if not profile or not profile.get("budget_enabled"):
        return None
    try:
        value = float(profile.get("budget") or 0)
        return value if value > 0 else None
    except (TypeError, ValueError):
        return None


def _effective_equity(login: int, info: dict[str, Any]) -> float:
    equity = float(info.get("equity") or 0)
    budget = _budget_for_login(login)
    return min(equity, budget) if budget is not None and equity > 0 else (budget if budget is not None else equity)


def _daily_guard(bot: dict[str, Any], info: dict[str, Any], positions: list[dict[str, Any]]) -> tuple[bool, str]:
    today = datetime.now(timezone.utc).date().isoformat()
    day = dict(bot.get("native_day_state") or {})
    equity = _effective_equity(int(bot.get("account_login") or 0), info)
    if day.get("date") != today or float(day.get("start_equity") or 0) <= 0:
        day = {"date": today, "start_equity": equity, "updated_at": _now()}
        _patch_bot(int(bot["id"]), native_day_state=day)
    preset = _preset(int(bot["id"])) or {}
    start_equity = float(day.get("start_equity") or equity or 0)
    source_daily_loss = float(preset.get("max_daily_loss_percent") or 4.0)
    if start_equity > 0 and equity > 0:
        dd = max(0.0, (start_equity - equity) / start_equity * 100.0)
        if dd >= source_daily_loss:
            return False, f"Daily drawdown guard active ({dd:.2f}% / {source_daily_loss:.2f}% limit)."
    prefix = _source_prefix(int(bot["id"]))
    losses = 0
    trades = 0
    for row in _history(int(bot.get("account_login") or 0), 2):
        if not str(row.get("close_time") or "").startswith(today):
            continue
        if not str(row.get("source") or "").startswith(prefix):
            continue
        trades += 1
        if float(row.get("net_pl") or 0) < 0:
            losses += 1
    max_trades = int(preset.get("max_trades_per_day") or 0)
    if max_trades > 0 and trades >= max_trades:
        return False, f"Source max-trades-per-day cap reached ({trades}/{max_trades})."
    if losses >= 2:
        return False, "KOOLKID native daily loss-streak cap reached."
    if _has_position_conflict(int(bot["id"]), str(bot.get("symbol") or ""), positions):
        managed = dict(bot.get("native_managed_position") or {})
        ticket = int(managed.get("ticket") or 0)
        if not ticket or not any(int(row.get("ticket") or 0) == ticket for row in positions):
            return False, "Source one-trade-per-symbol guard is active."
    return True, ""

def _normalize_volume(value: float, info: dict[str, Any]) -> float:
    minimum = float(info.get("volume_min") or 0.01)
    maximum = float(info.get("volume_max") or max(value, minimum))
    step = float(info.get("volume_step") or 0.01)
    value = max(minimum, min(float(value), maximum))
    steps = math.floor((value + 1e-12) / step)
    return round(max(minimum, min(steps * step, maximum)), 8)


def _risk_volume(signal: dict[str, Any], account: dict[str, Any], symbol_info: dict[str, Any], bot: dict[str, Any]) -> float:
    equity = _effective_equity(int(bot.get("account_login") or 0), account)
    entry, sl = float(signal["entry"]), float(signal["sl"])
    source_risk = float(signal.get("risk_percent") or 0)
    configured_risk = float((bot.get("settings") or {}).get("risk_percent") or source_risk or 0)
    risk_pct = min(configured_risk, source_risk) if source_risk > 0 and configured_risk > 0 else max(configured_risk, source_risk)
    tick_size = float(symbol_info.get("trade_tick_size") or symbol_info.get("point") or 0)
    tick_value = float(symbol_info.get("trade_tick_value_loss") or symbol_info.get("trade_tick_value") or 0)
    if equity <= 0 or risk_pct <= 0 or tick_size <= 0 or tick_value <= 0 or entry == sl:
        raise RuntimeError("Broker risk metadata is incomplete; native order sizing is safety-blocked.")
    cost_per_lot = abs(entry - sl) / tick_size * tick_value
    if cost_per_lot <= 0:
        raise RuntimeError("Native risk-per-lot calculation failed.")
    volume = _normalize_volume(equity * (risk_pct / 100.0) / cost_per_lot, symbol_info)
    global_risk = next((row for row in read_state().get("risk", []) if row.get("scope") == "global"), {})
    max_lot = float(global_risk.get("max_lot_size") or 0)
    if max_lot > 0:
        volume = min(volume, _normalize_volume(max_lot, symbol_info))
    return volume

def _managed_position(bot: dict[str, Any], positions: list[dict[str, Any]]) -> dict[str, Any] | None:
    managed = dict(bot.get("native_managed_position") or {})
    ticket = int(managed.get("ticket") or 0)
    if ticket:
        row = next((p for p in positions if int(p.get("ticket") or 0) == ticket), None)
        if row:
            return row
    bot_id = int(bot["id"])
    symbol = str(bot.get("symbol") or "")
    magic = int((_preset(bot_id) or {}).get("magic") or 0)
    row = next((
        p for p in positions
        if (not symbol or str(p.get("symbol") or "") == symbol)
        and magic
        and int(p.get("magic") or 0) == magic
    ), None)
    if not row:
        legacy_prefix = _source_prefix(bot_id)
        row = next((p for p in positions if str(p.get("comment") or "").startswith(legacy_prefix)), None)
    if not row:
        expected_comment = _mt5_bot_comment(bot)
        row = next((p for p in positions if str(p.get("comment") or "") == expected_comment), None)
    if row:
        managed["ticket"] = int(row.get("ticket") or 0)
        _patch_bot(bot_id, native_managed_position=managed)
    return row


def _manage_open_position(bot: dict[str, Any], positions: list[dict[str, Any]], m5: Series, symbol_info: dict[str, Any]) -> None:
    pos = _managed_position(bot, positions)
    managed = dict(bot.get("native_managed_position") or {})
    if not pos:
        if managed.get("ticket"):
            _patch_bot(int(bot["id"]), native_managed_position=None)
        return
    ticket = int(pos.get("ticket") or 0)
    account_id = str(pos.get("account_id") or "")
    if not ticket or not account_id:
        return
    open_price = float(pos.get("price_open") or pos.get("open_price") or managed.get("entry") or 0)
    current = float(pos.get("price_current") or pos.get("current_price") or open_price)
    current_sl = float(pos.get("sl") or 0)
    current_tp = float(pos.get("tp") or 0)
    initial_risk = float(managed.get("initial_risk") or 0)
    if initial_risk <= 0:
        return
    side = str(pos.get("side") or "").lower()
    if not side:
        side = "buy" if str(pos.get("type") or "0").lower() in {"0", "buy"} else "sell"
    progress_r = ((current - open_price) if side == "buy" else (open_price - current)) / initial_risk
    management = dict(managed.get("management") or {})
    changed = False
    partial_at = float(management.get("partial_at_r") or 0)
    partial_pct = float(management.get("partial_close_percent") or 0)
    if not managed.get("partial_taken") and partial_at > 0 and 0 < partial_pct < 100 and progress_r >= partial_at:
        volume = float(pos.get("volume") or 0)
        close_volume = _normalize_volume(volume * partial_pct / 100.0, symbol_info)
        if 0 < close_volume < volume:
            multi_account_client.request("/positions/close-partial", "POST", {"account_id": account_id, "ticket": ticket, "volume": close_volume}, timeout=20)
        managed["partial_taken"] = True
        changed = True

    be_r = float(management.get("break_even_r") or 0)
    if not managed.get("moved_to_be") and be_r > 0 and progress_r >= be_r:
        favorable = (side == "buy" and (current_sl == 0 or current_sl < open_price)) or (side == "sell" and (current_sl == 0 or current_sl > open_price))
        if favorable:
            multi_account_client.request("/positions/modify", "POST", {"account_id": account_id, "ticket": ticket, "sl": open_price, "tp": current_tp}, timeout=15)
            current_sl = open_price
        managed["moved_to_be"] = True
        changed = True

    trail_start = float(management.get("trail_start_r") or 0)
    trail_distance_r = float(management.get("trail_distance_r") or 0)
    trail_mult = float(management.get("trail_atr_mult") or 0)
    av = atr(m5, 14, 1)
    if trail_start > 0 and progress_r >= trail_start:
        candidate = None
        if trail_distance_r > 0:
            candidate = current - initial_risk * trail_distance_r if side == "buy" else current + initial_risk * trail_distance_r
        elif trail_mult > 0 and av > 0:
            candidate = current - av * trail_mult if side == "buy" else current + av * trail_mult
        if candidate is not None:
            favorable = (side == "buy" and candidate > current_sl and candidate < current) or (side == "sell" and (current_sl == 0 or candidate < current_sl) and candidate > current)
            if favorable:
                multi_account_client.request("/positions/modify", "POST", {"account_id": account_id, "ticket": ticket, "sl": candidate, "tp": current_tp}, timeout=15)
                managed["last_trail_sl"] = candidate
                changed = True
    if changed:
        managed["last_managed_at"] = _now()
        _patch_bot(int(bot["id"]), native_managed_position=managed)

def _execute(
    bot: dict[str, Any],
    signal: dict[str, Any],
    account: dict[str, Any],
    symbol_info: dict[str, Any],
    *,
    allow_live: bool = False,
) -> dict[str, Any]:
    signal_key = str(signal.get("signal_key") or "")
    if not signal_key:
        raise RuntimeError("Native signal has no stable signal key.")
    if _already_attempted(int(bot["id"]), signal_key):
        raise RuntimeError("This completed-candle native signal was already submitted.")
    volume = _risk_volume(signal, account, symbol_info, bot)
    mt5_comment = _mt5_bot_comment(bot)
    _record_attempt(int(bot["id"]), signal_key, "submitting", volume=volume)
    worker = _connected_worker(int(bot["account_login"]))
    account_id = str(worker["account_id"])
    payload = {
        "target_account_ids": [account_id], "symbol": str(bot["symbol"]),
        "side": str(signal["direction"]).lower(), "volume": volume,
        "sl": float(signal["sl"]), "tp": float(signal["tp"]),
        "magic": int((_preset(int(bot["id"])) or {}).get("magic") or 0),
        "comment": mt5_comment,
        "confirm_live": bool(allow_live),
    }
    try:
        result = multi_account_client.request("/manual-trade", "POST", payload, timeout=25)
        row = (result.get("results") or {}).get(account_id) or {}
        if not row.get("ok"):
            raise RuntimeError(str(row.get("error") or "8002 rejected native order."))
        order = dict(row.get("result") or {})
        ticket = int(order.get("ticket") or order.get("order") or order.get("deal") or 0)
        management = dict((signal.get("context") or {}).get("management") or {})
        managed = {
            "ticket": ticket, "signal_key": signal_key, "entry": float(signal["entry"]),
            "initial_risk": abs(float(signal["entry"]) - float(signal["sl"])),
            "original_volume": volume, "partial_taken": False, "moved_to_be": False,
            "management": management, "opened_at": _now(),
            "account_login": int(bot["account_login"]), "account_id": account_id, "symbol": str(bot["symbol"]),
        }
        execution = {
            "ticket": ticket, "signal_key": signal_key, "direction": signal["direction"],
            "symbol": bot["symbol"], "volume": volume, "sl": signal["sl"], "tp": signal["tp"],
            "executed_at": _now(), "result": order, "engine": "native",
        }
        _record_attempt(int(bot["id"]), signal_key, "executed", ticket=ticket, volume=volume)
        _patch_bot(int(bot["id"]), native_last_execution=execution, native_managed_position=managed)
        return execution
    except Exception as exc:
        _record_attempt(int(bot["id"]), signal_key, "failed", error=str(exc), volume=volume)
        raise


def _selected_symbols(bot: dict[str, Any], config: dict[str, Any]) -> list[str]:
    raw = config.get("symbols") or bot.get("symbols") or [config.get("symbol") or bot.get("symbol")]
    if isinstance(raw, str):
        raw = [raw]
    symbols: list[str] = []
    for item in raw or []:
        symbol = str(item or "").strip()
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    if not symbols:
        raise RuntimeError("Native preset requires at least one market.")
    if len(symbols) > 10:
        raise RuntimeError("A native bot can scan a maximum of 10 markets.")
    return symbols


def _cycle(bot_id: int, symbol_override: str | None = None, *, execute_allowed: bool = True) -> dict[str, Any]:
    bot = _bot(bot_id)
    if not bot:
        raise RuntimeError("Native bot state was not found.")
    config = dict(bot.get("native_config") or {})
    login = int(config.get("account_login") or bot.get("account_login") or 0)
    symbol = str(symbol_override or config.get("symbol") or bot.get("symbol") or "")
    if not login or not symbol:
        raise RuntimeError("Native preset requires an account and symbol.")
    _, account = _verify_account(login, bool(config.get("allow_live")))
    exec_tf, bias_tf = configured_timeframes(bot_id, bot)
    market, _ = _fetch_market(login, symbol, {exec_tf, bias_tf})
    market.update({"symbol": symbol, "account_login": login})
    strategy_market, exec_tf, bias_tf = prepare_strategy_market(bot_id, market, bot)
    signal = evaluate(str(bot.get("native_key") or ""), strategy_market).to_dict()
    rules = dict(signal.get("rules") or {})
    rules.update({
        "configured_execution_timeframe": exec_tf,
        "configured_bias_timeframe": bias_tf,
        "scanned_symbol": symbol,
    })
    signal["rules"] = rules
    original_signal_key = str(signal.get("signal_key") or "")
    if original_signal_key:
        signal["signal_key"] = f"{symbol}:{original_signal_key}"
    positions = _positions(login)
    managed = _managed_position(bot, positions)
    canonical_exec = str((_preset(bot_id) or {}).get("entry_tf") or "M5").upper()
    if managed and str(managed.get("symbol") or "") == symbol:
        _manage_open_position(
            {**bot, "symbol": symbol},
            positions,
            strategy_market.get(canonical_exec) or market["M5"],
            market["symbol_info"],
        )
    previous_runtime = dict(bot.get("native_runtime") or {})
    market_scans = dict(previous_runtime.get("market_scans") or {})
    market_scans[symbol] = {
        "symbol": symbol,
        "valid": bool(signal.get("valid")),
        "stage": signal.get("stage"),
        "score": float(signal.get("score") or signal.get("confidence") or 0),
        "direction": signal.get("direction"),
        "reason": signal.get("reason"),
        "error": None,
    }
    runtime = {
        **previous_runtime, "status": "managing" if managed else "running", "last_scan_at": _now(),
        "last_signal": signal, "last_stage": signal.get("stage"), "last_score": signal.get("score"),
        "last_error": None, "account_login": login, "symbol": symbol,
        "symbols": _selected_symbols(bot, config), "market_scans": market_scans,
    }
    _patch_bot(bot_id, native_signal=signal, native_runtime=runtime)
    result = {
        "symbol": symbol,
        "signal": signal,
        "score": float(signal.get("score") or signal.get("confidence") or 0),
        "valid": bool(signal.get("valid")),
        "market": market,
    }
    if not execute_allowed or not signal.get("valid"):
        return result
    runtime_bot = {**(_bot(bot_id) or bot), "account_login": login, "symbol": symbol}
    ok, reason = _daily_guard(runtime_bot, account, positions)
    if not ok:
        _runtime(bot_id, status="guarded", last_error=reason)
        return result
    managed = _managed_position(runtime_bot, positions)
    if managed:
        _runtime(bot_id, status="managing", last_error=None)
        return result
    signal_key = str(signal.get("signal_key") or "")
    if signal_key and not _already_attempted(bot_id, signal_key):
        execution = _execute(
            runtime_bot,
            signal,
            account,
            market["symbol_info"],
            allow_live=bool(config.get("allow_live")),
        )
        result["execution"] = execution
        _runtime(bot_id, status="running", last_execution=execution, last_execution_at=_now(), last_error=None)
    return result


def _runner(workspace_id: str, bot_id: int, stop_event: threading.Event) -> None:
    token = set_workspace(workspace_id)
    try:
        _runtime(bot_id, status="starting", started_at=_now(), last_error=None)
        while not stop_event.is_set():
            bot = _bot(bot_id)
            if not bot or bot.get("status") not in {"running", "paused"} or not (bot.get("native_config") or {}).get("enabled"):
                break
            try:
                config = dict(bot.get("native_config") or {})
                symbols = _selected_symbols(bot, config)
                results: list[dict[str, Any]] = []
                for symbol in symbols:
                    try:
                        results.append(_cycle(bot_id, symbol, execute_allowed=False))
                    except Exception as scan_exc:
                        latest_scan = _bot(bot_id) or bot
                        scan_runtime = dict(latest_scan.get("native_runtime") or {})
                        market_scans = dict(scan_runtime.get("market_scans") or {})
                        market_scans[symbol] = {
                            "symbol": symbol, "valid": False, "stage": "ERROR",
                            "score": 0, "direction": None, "reason": None, "error": str(scan_exc),
                        }
                        _runtime(bot_id, market_scans=market_scans, symbols=symbols)
                latest = _bot(bot_id) or bot
                login = int(config.get("account_login") or latest.get("account_login") or 0)
                managed = _managed_position(latest, _positions(login)) if login else None
                candidates = [row for row in results if row.get("valid")]
                if bot.get("status") == "paused":
                    _runtime(bot_id, status="paused", last_error=None)
                elif not managed and candidates:
                    winner = max(candidates, key=lambda row: float(row.get("score") or 0))
                    _cycle(bot_id, str(winner["symbol"]), execute_allowed=True)
            except Exception as exc:
                _runtime(bot_id, status="waiting", last_error=str(exc), last_error_at=_now())
            bot = _bot(bot_id) or {}
            seconds = max(10, min(int((bot.get("native_config") or {}).get("scan_seconds") or 20), 300))
            stop_event.wait(seconds)
    finally:
        try:
            bot = _bot(bot_id)
            if bot and bot.get("status") not in {"running", "paused"}:
                _runtime(bot_id, status="stopped", stopped_at=_now())
        finally:
            reset_workspace(token)
            with _LOCK:
                _THREADS.pop(_key(workspace_id, bot_id), None)
                _STOPS.pop(_key(workspace_id, bot_id), None)


def fetch_market_snapshot(
    account_login: int,
    symbol: str,
    timeframes: set[str] | list[str] | tuple[str, ...] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    return _fetch_market(int(account_login), str(symbol), timeframes)


def manage_positions_once(
    account_login: int,
    symbol: str,
    bot_ids: list[int],
    market: dict[str, Any] | None = None,
) -> None:
    market = market or _fetch_market(int(account_login), str(symbol))[0]
    positions = _positions(int(account_login))
    m5 = market.get("M5")
    symbol_info = dict(market.get("symbol_info") or {})
    if not isinstance(m5, Series):
        return
    for bot_id in bot_ids:
        bot = _bot(int(bot_id))
        if not bot:
            continue
        runtime_bot = {**bot, "account_login": int(account_login), "symbol": str(symbol)}
        _manage_open_position(runtime_bot, positions, m5, symbol_info)


def execute_signal_once(
    bot_id: int,
    account_login: int,
    symbol: str,
    signal: dict[str, Any],
    symbol_info: dict[str, Any] | None = None,
    *,
    demo_only: bool = True,
) -> dict[str, Any]:
    preset = _preset(bot_id)
    if not preset or not preset.get("ready"):
        raise RuntimeError("This native preset is not ready for execution.")
    _, account = _verify_account(int(account_login), allow_live=not demo_only)
    bot = _bot(bot_id)
    if not bot:
        raise RuntimeError("Native bot state was not found.")
    runtime_bot = {**bot, "account_login": int(account_login), "symbol": str(symbol)}
    positions = _positions(int(account_login))
    ok, reason = _daily_guard(runtime_bot, account, positions)
    if not ok:
        raise RuntimeError(reason)
    if _has_position_conflict(int(bot_id), str(symbol), positions):
        raise RuntimeError("Native one-position safety rule blocked a duplicate strategy position.")
    if not signal.get("valid"):
        raise RuntimeError("The native setup is incomplete and cannot be executed.")
    if symbol_info is None:
        symbol_info = multi_account_client.account_request(
            int(account_login), f"/symbol-info/{str(symbol)}", timeout=8,
        )
    return _execute(runtime_bot, signal, account, dict(symbol_info or {}), allow_live=not demo_only)


def start(
    workspace_id: str,
    bot_id: int,
    account_login: int,
    symbol: str,
    *,
    symbols: list[str] | None = None,
    allow_live: bool = False,
    scan_seconds: int = 20,
    execution_timeframe: str | None = None,
    bias_timeframe: str | None = None,
) -> dict[str, Any]:
    preset = _preset(bot_id)
    if not preset:
        raise RuntimeError("This bot is not a KOOLKID native preset.")
    if not preset.get("ready"):
        raise RuntimeError(f"{preset['name']} requires its MQ5 source before native execution can be enabled.")
    _verify_account(account_login, allow_live)
    selected: list[str] = []
    for item in (symbols or [symbol]):
        value = str(item or "").strip()
        if value and value not in selected:
            selected.append(value)
    if not selected:
        raise RuntimeError("Choose at least one market.")
    if len(selected) > 10:
        raise RuntimeError("Choose no more than 10 markets for one bot.")
    symbol = selected[0]
    exec_tf = str(execution_timeframe or preset.get("entry_tf") or "M5").upper()
    bias_tf = str(bias_timeframe or _primary_bias_timeframe(preset)).upper()
    if exec_tf not in _TIMEFRAME_COUNTS or bias_tf not in _TIMEFRAME_COUNTS:
        raise RuntimeError("Choose a supported execution and bias timeframe.")
    config = {
        "enabled": True, "account_login": int(account_login), "symbol": str(symbol), "symbols": selected,
        "market_mode": "multi" if len(selected) > 1 else "single",
        "allow_live": bool(allow_live), "scan_seconds": max(10, min(int(scan_seconds), 300)),
        "strategy_key": preset["key"], "execution_timeframe": exec_tf, "bias_timeframe": bias_tf,
        "updated_at": _now(),
    }
    session_started_at = _now()
    _patch_bot(bot_id, status="running", account_login=int(account_login), symbol=str(symbol), symbols=selected,
               market_mode="multi" if len(selected) > 1 else "single",
               timeframe=exec_tf, bias_timeframe=bias_tf, native_config=config,
               started_at=session_started_at, session_started_at=session_started_at,
               bot_trade_count=0, bot_wins=0, bot_losses=0, bot_win_rate=0.0,
               today_pl=0.0, profit_today=0.0, last_trade=None,
               native_signal=None, native_last_execution=None, last_error=None)
    key = _key(workspace_id, bot_id)
    with _LOCK:
        thread = _THREADS.get(key)
        if thread and thread.is_alive():
            return _bot(bot_id) or {}
        stop_event = threading.Event()
        _STOPS[key] = stop_event
        thread = threading.Thread(target=_runner, args=(workspace_id, int(bot_id), stop_event), daemon=True, name=f"koolkid-native-{bot_id}")
        _THREADS[key] = thread
        thread.start()
    return _bot(bot_id) or {}

def pause(workspace_id: str, bot_id: int) -> dict[str, Any]:
    bot = _bot(bot_id)
    if not bot:
        raise RuntimeError("Bot not found.")
    if bot.get("status") == "paused":
        return bot
    if bot.get("status") != "running":
        raise RuntimeError("Only a running native bot can be paused.")
    config = dict(bot.get("native_config") or {})
    config["enabled"] = True
    config["updated_at"] = _now()
    return _patch_bot(
        bot_id,
        status="paused",
        native_config=config,
        native_runtime={**dict(bot.get("native_runtime") or {}), "status": "paused", "paused_at": _now(), "last_error": None},
    )


def resume(workspace_id: str, bot_id: int) -> dict[str, Any]:
    bot = _bot(bot_id)
    if not bot:
        raise RuntimeError("Bot not found.")
    if bot.get("status") == "running":
        return bot
    if bot.get("status") != "paused":
        raise RuntimeError("Only a paused native bot can be resumed.")
    config = dict(bot.get("native_config") or {})
    config["enabled"] = True
    config["updated_at"] = _now()
    _patch_bot(
        bot_id,
        status="running",
        native_config=config,
        native_runtime={**dict(bot.get("native_runtime") or {}), "status": "running", "resumed_at": _now(), "last_error": None},
    )
    key = _key(workspace_id, bot_id)
    with _LOCK:
        thread = _THREADS.get(key)
        if not thread or not thread.is_alive():
            stop_event = threading.Event()
            _STOPS[key] = stop_event
            thread = threading.Thread(
                target=_runner,
                args=(workspace_id, int(bot_id), stop_event),
                daemon=True,
                name=f"koolkid-native-{bot_id}",
            )
            _THREADS[key] = thread
            thread.start()
    return _bot(bot_id) or {}


def stop(workspace_id: str, bot_id: int) -> dict[str, Any]:
    key = _key(workspace_id, bot_id)
    with _LOCK:
        event = _STOPS.get(key)
        if event:
            event.set()
    bot = _bot(bot_id)
    if not bot:
        raise RuntimeError("Bot not found.")
    config = dict(bot.get("native_config") or {})
    config["enabled"] = False
    config["updated_at"] = _now()
    return _patch_bot(bot_id, status="stopped", started_at=None, session_started_at=None, native_config=config,
                      native_runtime={**dict(bot.get("native_runtime") or {}), "status": "stopped", "stopped_at": _now()})


def restore(workspace_id: str) -> int:
    restored = 0
    for bot in read_state().get("bots", []):
        if not bot.get("native_engine") or bot.get("status") not in {"running", "paused"}:
            continue
        config = dict(bot.get("native_config") or {})
        if not config.get("enabled") or not bot.get("native_ready"):
            continue
        bot_id = int(bot["id"])
        key = _key(workspace_id, bot_id)
        with _LOCK:
            thread = _THREADS.get(key)
            if thread and thread.is_alive():
                continue
            stop_event = threading.Event()
            _STOPS[key] = stop_event
            thread = threading.Thread(target=_runner, args=(workspace_id, bot_id, stop_event), daemon=True, name=f"koolkid-native-{bot_id}")
            _THREADS[key] = thread
            thread.start()
        restored += 1
    return restored


def status(workspace_id: str, bot_id: int) -> dict[str, Any]:
    key = _key(workspace_id, bot_id)
    with _LOCK:
        thread = _THREADS.get(key)
        alive = bool(thread and thread.is_alive())
    bot = _bot(bot_id) or {}
    return {"alive": alive, "runtime": dict(bot.get("native_runtime") or {}),
            "signal": bot.get("native_signal"), "last_execution": bot.get("native_last_execution")}
