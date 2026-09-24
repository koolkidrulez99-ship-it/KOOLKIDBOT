from __future__ import annotations

from copy import deepcopy

import pytest

import main
import native_runtime
from hub_auth import reset_workspace, set_workspace


def _state(bot: dict) -> dict:
    return {
        "bots": [bot],
        "profiles": [{"login": 123, "server": "Broker-Demo"}],
        "risk": [],
    }


def _state_mocks(monkeypatch, state: dict) -> None:
    monkeypatch.setattr(main, "read_state", lambda: state)

    def update_state(mutator):
        return mutator(state)

    monkeypatch.setattr(main, "update_state", update_state)
    monkeypatch.setattr(
        main.multi_account_client,
        "worker_for_login",
        lambda login: {
            "account_info": {
                "login": login,
                "trade_mode": 0,
                "terminal_path": "bridge-terminal",
                "data_path": "bridge-data",
            }
        },
    )
    monkeypatch.setattr(
        main.multi_account_client,
        "account_request",
        lambda login, path, timeout=0: [
            {"symbol": "EURUSD"},
            {"symbol": "GBPUSD"},
            {"symbol": "USDJPY"},
        ] if path.startswith("/symbols") else {},
    )


def test_native_start_receives_all_selected_markets(monkeypatch):
    bot = {
        "id": 1010,
        "name": "KOOLKID SCALPER X",
        "symbol": "EURUSD",
        "symbols": ["EURUSD"],
        "timeframe": "M5",
        "bias_timeframe": "H1",
        "account_login": 123,
        "native_engine": True,
        "native_ready": True,
        "native_key": "koolkid_scalper_x",
        "settings": {"risk_percent": 0.5},
        "status": "stopped",
        "lot_size": 0.01,
    }
    state = _state(bot)
    _state_mocks(monkeypatch, state)
    monkeypatch.setitem(main.NATIVE_PRESETS, 1010, {
        "entry_tf": "M5",
        "bias_tf": "H1",
        "key": "koolkid_scalper_x",
        "ready": True,
    })
    captured = {}

    def fake_start(workspace, bot_id, login, symbol, **kwargs):
        captured.update({
            "workspace": workspace,
            "bot_id": bot_id,
            "login": login,
            "symbol": symbol,
            **kwargs,
        })
        return {"status": "running"}

    monkeypatch.setattr(main.native_runtime, "start", fake_start)
    monkeypatch.setattr(main, "_mark_library_revision_running", lambda *args, **kwargs: None)

    token = set_workspace("multi-market-native")
    try:
        result = main.start_bot(1010, {
            "account_login": 123,
            "symbols": ["EURUSD", "GBPUSD", "USDJPY"],
            "timeframe": "M5",
            "bias_timeframe": "H1",
        })
    finally:
        reset_workspace(token)

    assert result["status"] == "running"
    assert captured["symbol"] == "EURUSD"
    assert captured["symbols"] == ["EURUSD", "GBPUSD", "USDJPY"]
    assert state["bots"][0]["symbols"] == ["EURUSD", "GBPUSD", "USDJPY"]
    assert state["bots"][0]["market_mode"] == "multi"


def test_uploaded_ea_starts_one_worker_instance_per_market(monkeypatch, tmp_path):
    (tmp_path / "Demo.ex5").write_bytes(b"compiled-ea")
    bot = {
        "id": 2000,
        "name": "Uploaded Demo",
        "symbol": "EURUSD",
        "symbols": ["EURUSD"],
        "timeframe": "M15",
        "account_login": 123,
        "native_engine": False,
        "ea_storage_path": "Demo.ex5",
        "ea_filename": "Demo.ex5",
        "preset_storage_path": None,
        "preset_filename": None,
        "dll_required": False,
        "settings": {"magic_number": 712000},
        "status": "stopped",
        "lot_size": 0.01,
        "version": "1.0.0",
    }
    state = _state(bot)
    _state_mocks(monkeypatch, state)
    monkeypatch.setattr(main, "ROOT", tmp_path)
    calls = []

    def worker_request(path, method="GET", payload=None, timeout=0):
        if path == "/bots/start":
            calls.append(deepcopy(payload))
            return {
                "id": f"ea-{len(calls)}",
                "bot_id": 2000,
                "instance_key": payload["instance_key"],
                "symbol": payload["symbol"],
                "status": "running",
                "started_at": "now",
                "worker_id": "worker",
                "terminal_id": payload["instance_key"],
                "process_id": 100 + len(calls),
                "terminal_status": "online",
                "account_verified": True,
                "ea_verified": True,
                "ea_status": "active",
                "open_positions": 0,
                "current_pl": 0,
                "today_pl": 0,
                "bot_trade_count": 0,
                "bot_wins": 0,
                "bot_losses": 0,
                "restart_request": deepcopy(payload),
            }
        raise AssertionError(path)

    monkeypatch.setattr(main.ea_worker_client, "request", worker_request)

    token = set_workspace("multi-market-ea")
    try:
        result = main.start_bot(2000, {
            "account_login": 123,
            "symbols": ["EURUSD", "GBPUSD"],
            "timeframe": "M15",
        })
    finally:
        reset_workspace(token)

    assert [call["symbol"] for call in calls] == ["EURUSD", "GBPUSD"]
    assert [call["instance_key"] for call in calls] == ["market-1", "market-2"]
    assert result["market_mode"] == "multi"
    assert result["instance_count"] == 2
    assert state["bots"][0]["symbols"] == ["EURUSD", "GBPUSD"]


def test_native_symbol_selection_deduplicates_and_caps():
    bot = {"symbol": "EURUSD", "symbols": ["EURUSD", "GBPUSD", "EURUSD"]}
    assert native_runtime._selected_symbols(bot, {}) == ["EURUSD", "GBPUSD"]
    with pytest.raises(RuntimeError, match="maximum of 10"):
        native_runtime._selected_symbols(
            {"symbols": [f"SYM{i}" for i in range(11)]},
            {},
        )


def test_dear_bruce_market_fetch_skips_unrelated_timeframes(monkeypatch):
    calls = []

    def account_request(login, path, timeout=0):
        calls.append(path)
        if path.startswith("/quotes"):
            return [{"bid": 1.1, "ask": 1.2}]
        if path.startswith("/symbol-info"):
            return {"name": "Jump 10 Index", "point": 0.01}
        if "timeframe=M15" in path or "timeframe=H4" in path:
            return [
                {"time": 1_700_000_000 + i * 60, "open": 100 + i, "high": 101 + i, "low": 99 + i, "close": 100.5 + i, "volume": 10}
                for i in range(60)
            ]
        raise RuntimeError(f"Unexpected optional timeframe request: {path}")

    monkeypatch.setattr(native_runtime.multi_account_client, "account_request", account_request)
    market, _ = native_runtime._fetch_market(
        123,
        "Jump 10 Index",
        {"M15", "H4"},
        required_timeframes_only=True,
    )

    assert market["M15"].rows
    assert market["H4"].rows
    assert not any("timeframe=M5" in path for path in calls)
    assert not any("timeframe=H1" in path for path in calls)
    assert not any("timeframe=D1" in path for path in calls)


def test_bot_trade_attribution_does_not_rewrite_display_source():
    bots = [
        {
            "id": 1010,
            "name": "KOOLKID SCALPER X",
            "account_login": 123,
            "settings": {"magic_number": 26101001},
        },
        {
            "id": 2000,
            "name": "My Uploaded EA",
            "account_login": 123,
            "ea_filename": "My_Uploaded_EA.ex5",
            "detected_magic": 812345,
            "settings": {"magic_number": 512000},
        },
    ]

    native = main._enrich_bot_trade_row(
        {"account_login": 123, "source": "KKN1010:abc123", "magic": 26101001},
        bots,
    )
    uploaded = main._enrich_bot_trade_row(
        {"account_login": 123, "source": "MT5", "comment": "anything", "magic": 812345},
        bots,
    )
    mt5_comment = main._enrich_bot_trade_row(
        {"account_login": 123, "source": "KKBOT(KOOLKID SCALPER X)", "comment": "KKBOT(KOOLKID SCALPER X)", "magic": 26101001},
        bots,
    )

    assert native["source"] == "KKN1010:abc123"
    assert native["bot_id"] == 1010
    assert uploaded["source"] == "MT5"
    assert uploaded["bot_id"] == 2000
    assert mt5_comment["source"] == "KKBOT(KOOLKID SCALPER X)"
    assert mt5_comment["bot_id"] == 1010


def test_native_mt5_comment_uses_bot_name_and_mt5_length_limit():
    assert native_runtime._mt5_bot_comment({"id": 1010, "name": "DEAR BRUCE"}) == "KKBOT(DEAR BRUCE)"
    comment = native_runtime._mt5_bot_comment({"id": 1010, "name": "THIS IS A VERY LONG BOT NAME THAT EXCEEDS MT5"})
    assert comment.startswith("KKBOT(")
    assert comment.endswith(")")
    assert len(comment) <= 31


class _ValidSignal:
    def to_dict(self):
        return {
            "valid": True, "stage": "READY", "score": 90.0,
            "confidence": 90.0, "signal_key": "sig-1",
            "direction": "BUY", "entry": 1.1, "sl": 1.0, "tp": 1.3,
            "rules": {}, "context": {},
        }


def _cycle_slot_mocks(monkeypatch, bot, active_positions):
    monkeypatch.setattr(native_runtime, "_bot", lambda bot_id: bot)
    monkeypatch.setattr(native_runtime, "_verify_account", lambda *args, **kwargs: ({}, {"equity": 1000.0}))
    monkeypatch.setattr(native_runtime, "configured_timeframes", lambda *args, **kwargs: ("M5", "H1"))
    market = {"symbol_info": {}, "M5": object(), "H1": object()}
    monkeypatch.setattr(native_runtime, "_fetch_market", lambda *args, **kwargs: (dict(market), {}))
    monkeypatch.setattr(native_runtime, "prepare_strategy_market", lambda *args, **kwargs: (args[1], "M5", "H1"))
    monkeypatch.setattr(native_runtime, "evaluate", lambda *args, **kwargs: _ValidSignal())
    monkeypatch.setattr(native_runtime, "_positions", lambda login: list(active_positions))
    monkeypatch.setattr(
        native_runtime,
        "_managed_position",
        lambda runtime_bot, positions: next(
            (row for row in positions if row.get("symbol") == runtime_bot.get("symbol")), None
        ),
    )
    monkeypatch.setattr(native_runtime, "_active_managed_positions", lambda *args, **kwargs: list(active_positions))
    monkeypatch.setattr(native_runtime, "_daily_guard", lambda *args, **kwargs: (True, ""))
    monkeypatch.setattr(native_runtime, "_already_attempted", lambda *args, **kwargs: False)
    monkeypatch.setattr(native_runtime, "_patch_bot", lambda *args, **kwargs: bot)
    monkeypatch.setattr(native_runtime, "_runtime", lambda *args, **kwargs: {})


def test_native_multi_market_can_fill_an_open_slot_on_another_market(monkeypatch):
    bot = {
        "id": 1010, "native_key": "koolkid_scalper_x",
        "account_login": 123, "symbol": "EURUSD",
        "symbols": ["EURUSD", "GBPUSD", "USDJPY"],
        "settings": {"multi_trade_enabled": True, "max_concurrent_trades": 2},
        "native_config": {
            "enabled": True, "account_login": 123,
            "symbols": ["EURUSD", "GBPUSD", "USDJPY"],
            "execution_timeframe": "M5", "bias_timeframe": "H1",
        },
    }
    active = [{"ticket": 1, "symbol": "EURUSD"}]
    _cycle_slot_mocks(monkeypatch, bot, active)
    monkeypatch.setattr(native_runtime, "_execute", lambda *args, **kwargs: {"ticket": 2, "symbol": "GBPUSD"})

    result = native_runtime._cycle(1010, "GBPUSD", execute_allowed=True)

    assert result["active_trade_count"] == 1
    assert result["max_concurrent_trades"] == 2
    assert result["execution"]["ticket"] == 2


def test_native_one_trade_mode_keeps_other_market_scanning_but_blocks_entry(monkeypatch):
    bot = {
        "id": 1010, "native_key": "koolkid_scalper_x",
        "account_login": 123, "symbol": "EURUSD",
        "symbols": ["EURUSD", "GBPUSD"],
        "settings": {"multi_trade_enabled": False, "max_concurrent_trades": 2},
        "native_config": {
            "enabled": True, "account_login": 123,
            "symbols": ["EURUSD", "GBPUSD"],
            "execution_timeframe": "M5", "bias_timeframe": "H1",
        },
    }
    active = [{"ticket": 1, "symbol": "EURUSD"}]
    _cycle_slot_mocks(monkeypatch, bot, active)
    executed = []
    monkeypatch.setattr(native_runtime, "_execute", lambda *args, **kwargs: executed.append(True) or {"ticket": 2})

    result = native_runtime._cycle(1010, "GBPUSD", execute_allowed=True)

    assert result["valid"] is True
    assert result["active_trade_count"] == 1
    assert result["max_concurrent_trades"] == 1
    assert "scanner remains active" in result["execution_blocked"]
    assert executed == []
