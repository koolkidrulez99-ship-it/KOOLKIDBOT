from __future__ import annotations

import tempfile
from pathlib import Path

from .copy_engine import CopyEngine
from .state import State


class _Runtime:
    config = {"symbol_aliases": {}}


class FakePool:
    def __init__(self):
        self.items = {"slave": _Runtime()}
        self.calls = []
        self.position = {"ticket": 999, "symbol": "EURUSD", "price_open": 101.0}

    def ids(self):
        return ["master", "slave"]

    def call(self, account_id, op, payload=None, timeout=15):
        self.calls.append((account_id, op, payload))
        if op == "account_info":
            return {"balance": 1000.0, "equity": 1000.0, "margin": 0.0}
        if op == "open_trade":
            return {"retcode": 10009, "ticket": 999, "price": 101.0}
        if op == "positions":
            return [dict(self.position)]
        if op == "modify_position":
            self.position.update({"sl": payload["sl"], "tp": payload["tp"]})
            return {"ok": True}
        raise AssertionError((account_id, op, payload))


def _engine():
    tmp = tempfile.TemporaryDirectory()
    state = State(Path(tmp.name) / "state.json")
    state.save({
        "accounts": {
            "master": {"account_id": "master"},
            "slave": {"account_id": "slave"},
        },
        "copy_map": {},
    })
    pool = FakePool()
    engine = CopyEngine(pool, state)
    engine.config = {
        "master_account_id": "master",
        "slave_account_ids": ["slave"],
        "lot_mode": "fixed",
        "fixed_lot": 0.37,
        "multiplier": 1.0,
        "trail_by_shoulders": True,
        "risk_reward_ratio": 2.0,
        "source_filter": "all",
        "poll_ms": 300,
    }
    return tmp, state, pool, engine


def test_fixed_lot_keeps_user_value():
    tmp, _, _, engine = _engine()
    try:
        assert engine.target_volume(
            {"volume": 1.0}, {"equity": 1000}, {"equity": 500},
            master_id="master", slave_id="slave",
        ) == 0.37
    finally:
        tmp.cleanup()


def test_shoulder_target_is_two_r_for_buy_and_sell():
    tmp, _, _, engine = _engine()
    try:
        assert engine.shoulder_target(100.0, 95.0, "buy") == 110.0
        assert engine.shoulder_target(100.0, 105.0, "sell") == 90.0
    finally:
        tmp.cleanup()


def test_copied_trade_uses_slave_fill_for_exact_two_r_target():
    tmp, _, pool, engine = _engine()
    try:
        result = engine._copy_to_slave(
            "12345",
            {
                "ticket": 12345,
                "symbol": "EURUSD",
                "side": "buy",
                "volume": 1.0,
                "price_open": 100.0,
                "sl": 95.0,
                "tp": 120.0,
            },
            {"equity": 1000.0},
            "slave",
        )
        assert result == {"ok": True, "ticket": 999}
        open_payload = next(payload for aid, op, payload in pool.calls if op == "open_trade")
        assert open_payload["volume"] == 0.37
        assert open_payload["sl"] == 95.0
        assert open_payload["tp"] == 110.0
        modify_payload = [payload for aid, op, payload in pool.calls if op == "modify_position"][-1]
        assert modify_payload == {"ticket": 999, "sl": 95.0, "tp": 113.0}
        assert engine.copy_map["12345"]["slave"]["last_tp"] == 113.0
        assert engine.copy_map["12345"]["slave"]["trail_by_shoulders"] is True
    finally:
        tmp.cleanup()
