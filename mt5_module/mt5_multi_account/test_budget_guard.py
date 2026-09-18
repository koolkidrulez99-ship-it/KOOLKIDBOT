from __future__ import annotations

import tempfile
from pathlib import Path

from .copy_engine import CopyEngine
from .state import State


class FakePool:
    def __init__(self):
        self._ids = ["a1", "master", "slave"]

    def ids(self):
        return list(self._ids)

    def call(self, account_id, op, payload=None, timeout=15):
        if op == "account_info":
            if account_id == "master":
                return {"balance": 1000.0, "equity": 1000.0, "margin": 0.0}
            if account_id == "slave":
                return {"balance": 500.0, "equity": 500.0, "margin": 0.0}
            return {"balance": 1000.0, "equity": 1000.0, "margin": 20.0}
        if op == "margin_required":
            return {"margin": float((payload or {}).get("volume") or 0) * 100.0}
        raise AssertionError((account_id, op, payload))
def run():
    with tempfile.TemporaryDirectory() as tmp:
        state = State(Path(tmp) / "state.json")
        state.save({
            "accounts": {
                "a1": {"account_id": "a1", "budget": 100.0},
                "master": {"account_id": "master", "budget": 100.0},
                "slave": {"account_id": "slave", "budget": 50.0},
            },
            "master": None, "slaves": [], "copy_map": {},
        })
        engine = CopyEngine(FakePool(), state)

        status = engine.budget_status("a1")
        assert status["budget_enabled"] is True
        assert status["virtual_balance"] == 100.0
        assert status["virtual_free_margin"] == 80.0

        allowed = engine.enforce_budget("a1", {"symbol": "XAUUSD", "side": "buy", "volume": 0.50})
        assert allowed["required_margin"] == 50.0
        try:
            engine.enforce_budget("a1", {"symbol": "XAUUSD", "side": "buy", "volume": 0.90})
            raise AssertionError("Budget guard accepted an over-budget order")
        except RuntimeError as exc:
            assert "Budget guard blocked" in str(exc)
        engine.config = {
            "lot_mode": "equity_proportional",
            "fixed_lot": 0.01, "multiplier": 1.0,
        }
        volume = engine.target_volume(
            {"volume": 1.0},
            {"equity": 1000.0},
            {"equity": 500.0},
            master_id="master", slave_id="slave",
        )
        assert abs(volume - 0.5) < 1e-9


if __name__ == "__main__":
    run()
    print("budget guard checks passed")
