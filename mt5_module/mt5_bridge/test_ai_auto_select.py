from __future__ import annotations

import copy
import sys
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mt5_module"))
sys.path.insert(0, str(ROOT / "mt5_module" / "mt5_bridge"))

import ai_auto_select as mod  # noqa: E402


class FakeSignal:
    def __init__(self, row):
        self.row = row

    def to_dict(self):
        return copy.deepcopy(self.row)


def base_signal(key: str, score: float, valid: bool):
    return {
        "strategy_key": key, "decision": "BUY" if valid else "WAIT",
        "direction": "BUY" if valid else None, "stage": "READY" if valid else "WAITING_RETEST",
        "score": score, "reason": "ready" if valid else "setup incomplete",
        "entry": 100.0 if valid else None, "sl": 99.0 if valid else None,
        "tp": 102.0 if valid else None, "valid": valid,
        "signal_key": key + ":1:XAUUSD:1000:BUY" if valid else None,
    }
def with_scan_fakes(evaluator, history=None):
    originals = {
        "evaluate": mod.evaluate,
        "fetch": mod.native_runtime.fetch_market_snapshot,
        "positions": mod._positions,
        "history": mod._history,
        "mode": mod._account_mode,
        "bots": mod._bot_map,
        "prepare": mod.native_runtime.prepare_strategy_market,
    }
    mod.evaluate = evaluator
    mod.native_runtime.fetch_market_snapshot = lambda login, symbol, timeframes=None: ({"symbol_info": {}}, {})
    mod.native_runtime.prepare_strategy_market = lambda bot_id, market, bot=None, **kwargs: (market, "M5", "H4")
    mod._positions = lambda login: []
    mod._history = lambda login: list(history or [])
    mod._account_mode = lambda login: "demo"
    mod._bot_map = lambda: {bot_id: {"native_ready": meta.get("ready")} for bot_id, meta in mod.NATIVE_PRESETS.items()}
    return originals


def restore_scan_fakes(originals):
    mod.evaluate = originals["evaluate"]
    mod.native_runtime.fetch_market_snapshot = originals["fetch"]
    mod._positions = originals["positions"]
    mod._history = originals["history"]
    mod._account_mode = originals["mode"]
    mod._bot_map = originals["bots"]
    mod.native_runtime.prepare_strategy_market = originals["prepare"]


def test_incomplete_high_score_never_selected():
    def evaluator(key, market):
        return FakeSignal(base_signal(key, 99.0, False))
    originals = with_scan_fakes(evaluator)
    try:
        result = mod.scan_once(1, "XAUUSD", [1000])
        assert result["selected"] is None
        assert result["results"][0]["decision"] == "WAIT"
        assert result["results"][0]["score"] == 99.0
    finally:
        restore_scan_fakes(originals)
def test_history_only_breaks_tie_between_valid_setups():
    def evaluator(key, market):
        score = 80.0 if key == "primordial_black" else 79.0
        return FakeSignal(base_signal(key, score, True))
    history = [
        {"source": "KKN1001:test", "net_pl": 5.0},
        {"source": "KKN1001:test", "net_pl": 4.0},
        {"source": "KKN1001:test", "net_pl": 3.0},
        {"source": "KKN1000:test", "net_pl": -2.0},
        {"source": "KKN1000:test", "net_pl": -1.0},
        {"source": "KKN1000:test", "net_pl": 1.0},
    ]
    originals = with_scan_fakes(evaluator, history)
    try:
        result = mod.scan_once(1, "XAUUSD", [1000, 1001])
        assert result["selected"]["bot_id"] == 1001
        assert all(row["decision"] == "APPROVE" for row in result["results"])
        assert result["rules"]["history_is_tiebreaker_only"] is True
    finally:
        restore_scan_fakes(originals)


def test_source_required_is_rejected():
    originals = with_scan_fakes(lambda key, market: FakeSignal(base_signal(key, 100, True)))
    original_ready = mod.NATIVE_PRESETS[1000].get("ready")
    mod.NATIVE_PRESETS[1000]["ready"] = False
    try:
        result = mod.scan_once(1, "XAUUSD", [1000])
        row = result["results"][0]
        assert row["decision"] == "REJECT"
        assert row["stage"] == "SOURCE_REQUIRED"
        assert result["selected"] is None
    finally:
        mod.NATIVE_PRESETS[1000]["ready"] = original_ready
        restore_scan_fakes(originals)
def test_live_execution_is_blocked():
    original_mode = mod._account_mode
    mod._account_mode = lambda login: "live"
    try:
        snapshot = {
            "account_login": 1, "symbol": "XAUUSD",
            "selected": {"bot_id": 1000, "decision": "APPROVE", "signal": base_signal("primordial_black", 80, True)},
        }
        try:
            with patch.object(mod, "current_workspace", return_value="ws_test"), patch.object(mod.multi_account_client, "connected_by_login", return_value={1: {"account_info": {"trade_mode": 2}}}):
                mod.execute_selected(snapshot)
            raise AssertionError("Live Auto Select execution was accepted")
        except PermissionError:
            pass
    finally:
        mod._account_mode = original_mode


def test_config_guards():
    state = {"ai_auto_config": {"enabled": True}}
    original_read, original_update = mod.read_state, mod.update_state
    original_mode, original_start = mod._account_mode, mod.start

    def read_state():
        return copy.deepcopy(state)

    def update_state(mutator):
        result = mutator(state)
        return copy.deepcopy(result)

    mod.read_state, mod.update_state = read_state, update_state
    mod._account_mode = lambda login: "demo"
    mod.start = lambda workspace_id: None
    try:
        try:
            with patch.object(mod.multi_account_client, "connected_by_login", return_value={1: {"account_info": {"trade_mode": 0}}}):
                mod.configure("ws_test", {"enabled": True, "mode": "auto", "account_login": 1, "symbol": "XAUUSD", "enabled_bot_ids": [1000]})
            raise AssertionError("Auto Select auto mode overlapped Human Apostle auto")
        except RuntimeError as exc:
            assert "Human Apostle" in str(exc)

        state["ai_auto_config"]["enabled"] = False
        try:
            mod.configure("ws_test", {"enabled": True, "mode": "analysis", "account_login": 1, "symbol": "XAUUSD", "enabled_bot_ids": []})
            raise AssertionError("Auto Select accepted zero enabled presets")
        except RuntimeError as exc:
            assert "at least one" in str(exc).lower()
    finally:
        mod.read_state, mod.update_state = original_read, original_update
        mod._account_mode, mod.start = original_mode, original_start
def run():
    test_incomplete_high_score_never_selected()
    test_history_only_breaks_tie_between_valid_setups()
    test_source_required_is_rejected()
    test_live_execution_is_blocked()
    test_config_guards()


if __name__ == "__main__":
    run()
    print("AI Auto Select checks passed")


def test_live_analysis_and_alert_modes_do_not_require_trade_confirmation():
    state = {"ai_auto_config": {"enabled": False}}
    original_read, original_update = mod.read_state, mod.update_state
    original_mode, original_start = mod._account_mode, mod.start

    def read_state():
        return copy.deepcopy(state)

    def update_state(mutator):
        result = mutator(state)
        return copy.deepcopy(result)

    mod.read_state, mod.update_state = read_state, update_state
    mod._account_mode = lambda login: "live"
    mod.start = lambda workspace_id: None
    try:
        for mode in ("analysis", "alert"):
            result = mod.configure("ws_live_nonexec", {
                "enabled": True, "mode": mode, "account_login": 1,
                "symbol": "XAUUSD", "enabled_bot_ids": [1000],
            })
            assert result["config"]["mode"] == mode
            assert result["config"]["allow_live"] is False
    finally:
        mod.read_state, mod.update_state = original_read, original_update
        mod._account_mode, mod.start = original_mode, original_start


def test_human_apostle_is_not_an_auto_select_preset():
    assert mod._enabled_ids({"enabled_bot_ids": [1008, 1009]}) == [1009]
    original_read = mod.read_state
    mod.read_state = lambda: {"ai_auto_select_config": {"enabled": False, "enabled_bot_ids": [1008, 1009]}}
    try:
        status = mod.status("ws_ai_filter")
        ids = [row["bot_id"] for row in status["available_presets"]]
        assert 1008 not in ids
        assert 1009 in ids
        assert status["config"]["enabled_bot_ids"] == [1009]
    finally:
        mod.read_state = original_read


def test_auto_select_reconfirms_selected_bot_logic_before_execution():
    snapshot = {
        "account_login": 1,
        "symbol": "FXVol40",
        "selected": {
            "bot_id": 1009,
            "decision": "APPROVE",
            "signal": {"valid": True, "signal_key": "old-signal"},
        },
    }
    original_verify = mod._verify_execution_account
    original_fetch = mod.native_runtime.fetch_market_snapshot
    original_evaluate = mod.evaluate
    original_bot_map = mod._bot_map
    original_positions = mod._positions
    original_execute = mod.native_runtime.execute_signal_once
    original_prepare = mod.native_runtime.prepare_strategy_market
    try:
        mod._verify_execution_account = lambda *a, **kw: "demo"
        mod.native_runtime.fetch_market_snapshot = lambda *a: ({"symbol_info": {}}, {})
        mod.native_runtime.prepare_strategy_market = lambda bot_id, market, bot=None, **kwargs: (market, "M5", "H4")
        mod.evaluate = lambda *a: FakeSignal({"valid": True, "signal_key": "new-signal"})
        mod._bot_map = lambda: {1009: {"status": "stopped", "native_config": {"enabled": False}}}
        mod._positions = lambda login: []
        mod.native_runtime.execute_signal_once = lambda *a, **kw: (_ for _ in ()).throw(AssertionError("execution should not run"))
        try:
            with patch.object(mod, "current_workspace", return_value="ws_reconfirm"):
                mod.execute_selected(snapshot)
            raise AssertionError("Changed bot setup was executed")
        except RuntimeError as exc:
            assert "changed before execution" in str(exc)
    finally:
        mod._verify_execution_account = original_verify
        mod.native_runtime.fetch_market_snapshot = original_fetch
        mod.evaluate = original_evaluate
        mod._bot_map = original_bot_map
        mod._positions = original_positions
        mod.native_runtime.execute_signal_once = original_execute
        mod.native_runtime.prepare_strategy_market = original_prepare
