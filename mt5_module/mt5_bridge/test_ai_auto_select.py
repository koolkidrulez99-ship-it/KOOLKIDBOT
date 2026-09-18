from __future__ import annotations

import copy
import sys
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
    }
    mod.evaluate = evaluator
    mod.native_runtime.fetch_market_snapshot = lambda login, symbol: ({"symbol_info": {}}, {})
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
    original_ready = mod.NATIVE_PRESETS[1008].get("ready")
    mod.NATIVE_PRESETS[1008]["ready"] = False
    try:
        result = mod.scan_once(1, "XAUUSD", [1008])
        row = result["results"][0]
        assert row["decision"] == "REJECT"
        assert row["stage"] == "SOURCE_REQUIRED"
        assert result["selected"] is None
    finally:
        mod.NATIVE_PRESETS[1008]["ready"] = original_ready
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
