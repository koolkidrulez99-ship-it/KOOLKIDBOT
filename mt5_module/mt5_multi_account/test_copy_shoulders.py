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


def _bar(t, low, high, close=None):
    return {
        "time": t,
        "open": (low + high) / 2,
        "low": low,
        "high": high,
        "close": (low + high) / 2 if close is None else close,
    }


def test_market_structure_buy_shoulder_requires_higher_low_and_continuation():
    candles = [
        _bar(0, 100, 102), _bar(1, 99, 103), _bar(2, 95, 101),
        _bar(3, 98, 102), _bar(4, 100, 104), _bar(5, 100, 106),
        _bar(6, 99, 105), _bar(7, 97, 103), _bar(8, 100, 104),
        _bar(9, 101, 105), _bar(10, 102, 108, 107),
        _bar(11, 103, 109, 108),
    ]
    result = CopyEngine.structure_shoulder_stop(
        candles, "buy", 0.01, current_sl=94.0, current_price=108.0,
        strength=2, buffer_points=5,
    )
    assert result is not None
    assert result["shoulder_time"] == 7
    assert round(result["sl"], 2) == 96.95

    no_loosen = CopyEngine.structure_shoulder_stop(
        candles, "buy", 0.01, current_sl=98.0, current_price=108.0,
        strength=2, buffer_points=5,
    )
    assert no_loosen is None


def test_market_structure_sell_shoulder_requires_lower_high_and_continuation():
    candles = [
        _bar(0, 98, 100), _bar(1, 97, 101), _bar(2, 99, 105),
        _bar(3, 98, 102), _bar(4, 96, 100), _bar(5, 94, 100),
        _bar(6, 95, 101), _bar(7, 97, 103), _bar(8, 95, 100),
        _bar(9, 94, 99), _bar(10, 91, 98, 92),
        _bar(11, 90, 97, 91),
    ]
    result = CopyEngine.structure_shoulder_stop(
        candles, "sell", 0.01, current_sl=106.0, current_price=92.0,
        strength=2, buffer_points=5,
    )
    assert result is not None
    assert result["shoulder_time"] == 7
    assert round(result["sl"], 2) == 103.05


def test_copy_preferences_survive_new_engine_instance():
    tmp, state, pool, engine = _engine()
    try:
        saved = engine.update_preferences({
            "trail_by_shoulders": True,
            "limit_copied_trades": True,
            "max_copied_trades_per_slave": 2,
            "fixed_lot": 0.42,
        })
        assert saved["trail_by_shoulders"] is True
        assert saved["max_copied_trades_per_slave"] == 2

        restored = CopyEngine(pool, state)
        assert restored.preferences["trail_by_shoulders"] is True
        assert restored.preferences["limit_copied_trades"] is True
        assert restored.preferences["max_copied_trades_per_slave"] == 2
        assert restored.preferences["fixed_lot"] == 0.42
    finally:
        tmp.cleanup()


def test_copy_limit_is_independent_per_slave_and_off_means_unlimited():
    tmp, _, pool, engine = _engine()
    try:
        pool.items["slave2"] = _Runtime()
        original_call = pool.call

        def call(account_id, op, payload=None, timeout=15):
            if op == "positions":
                if account_id == "slave":
                    return [
                        {"ticket": 1, "magic": 987654, "comment": "KKCOPY:11"},
                        {"ticket": 2, "magic": 987654, "comment": "KKCOPY:12"},
                    ]
                if account_id == "slave2":
                    return [{"ticket": 3, "magic": 987654, "comment": "KKCOPY:13"}]
            return original_call(account_id, op, payload, timeout)

        pool.call = call
        engine.config.update({
            "limit_copied_trades": True,
            "max_copied_trades_per_slave": 2,
        })
        assert engine._copy_slot_available("slave")[0] is False
        assert engine._copy_slot_available("slave2")[0] is True
        engine.config["limit_copied_trades"] = False
        assert engine._copy_slot_available("slave")[0] is True
    finally:
        tmp.cleanup()


def test_master_close_keeps_mapping_until_slave_close_is_confirmed():
    tmp, _, pool, engine = _engine()
    try:
        engine.config["approval_required"] = False  # Copy Trades From Anywhere uses the same close path.
        engine.copy_map = {"master-77": {"slave": {"ticket": 777}}}
        slave_still_open = {"value": True}
        original_call = pool.call

        def call(account_id, op, payload=None, timeout=15):
            if op == "close_position":
                raise TimeoutError("broker response timed out")
            if op == "positions":
                return [{"ticket": 777, "magic": 987654, "comment": "KKCOPY:master-77"}] if slave_still_open["value"] else []
            return original_call(account_id, op, payload, timeout)

        pool.call = call
        closed = engine._close_master_mappings("master-77", engine.config)
        assert closed is False
        assert engine.copy_map["master-77"]["slave"]["ticket"] == 777
        assert engine.copy_map["master-77"]["slave"]["close_retry_count"] == 1
        assert any(row["event"] == "copied_close_retry" for row in engine.activity)

        # Next engine cycle: MT5 now confirms the slave ticket is gone.
        slave_still_open["value"] = False
        closed = engine._close_master_mappings("master-77", engine.config)
        assert closed is True
        assert "master-77" not in engine.copy_map
        assert any(row["event"] == "copied_close_confirmed" for row in engine.activity)
    finally:
        tmp.cleanup()
