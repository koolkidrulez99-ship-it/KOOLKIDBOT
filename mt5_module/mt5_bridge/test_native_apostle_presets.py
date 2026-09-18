from __future__ import annotations

import copy

import native_runtime
from native_strategies import evaluate, ready_keys
from native_strategies.catalog import NATIVE_PRESETS
from native_strategies.common import Series
from store import SYSTEM_BOT_PRESETS, _merge_system_bots


def _rows(step: int, count: int, start: float, delta: float):
    rows = []
    price = start
    for index in range(count):
        opened = price
        closed = price + delta
        rows.append({
            "time": index * step,
            "open": opened,
            "high": max(opened, closed) + 0.2,
            "low": min(opened, closed) - 0.2,
            "close": closed,
            "volume": 100,
        })
        price = closed
    return rows


def _market():
    return {
        "M5": Series(_rows(300, 500, 100.0, 0.01)),
        "M15": Series(_rows(900, 500, 100.0, 0.02)),
        "H1": Series(_rows(3600, 360, 100.0, 0.05)),
        "H4": Series(_rows(14400, 260, 100.0, 0.10)),
        "quote": {"bid": 110.0, "ask": 110.02, "spread_points": 2},
        "symbol_info": {"point": 0.01, "trade_stops_level": 0},
        "symbol": "XAUUSD",
        "account_login": 123,
    }


def test_catalog_replaces_black_rock():
    assert NATIVE_PRESETS[1008]["name"] == "HUMAN APOSTLE"
    assert NATIVE_PRESETS[1008]["key"] == "human_apostle"
    assert NATIVE_PRESETS[1008]["ready"] is True
    assert NATIVE_PRESETS[1008]["version"] == "1.00"
    assert NATIVE_PRESETS[1008]["magic"] == 4152026
    assert NATIVE_PRESETS[1009]["name"] == "DEAR BRUCE"
    assert NATIVE_PRESETS[1009]["key"] == "dear_bruce"
    assert NATIVE_PRESETS[1009]["ready"] is True
    assert NATIVE_PRESETS[1009]["version"] == "2.20"
    assert NATIVE_PRESETS[1009]["magic"] == 22082605
    assert "human_apostle" in ready_keys()
    assert "dear_bruce" in ready_keys()
    assert all(row["name"] != "BLACK ROCK" for row in SYSTEM_BOT_PRESETS)


def test_native_rows_are_locked_and_described():
    rows = {int(row["id"]): row for row in _merge_system_bots([])}
    human = rows[1008]
    bruce = rows[1009]
    for row in (human, bruce):
        assert row["system_preset"] is True
        assert row["locked"] is True
        assert row["native_engine"] is True
        assert row["native_ready"] is True
        assert row["engine_type"] == "native"
        assert row["description"]
        assert row["settings"]["risk_percent"] == 1.0
    assert human["timeframe"] == "M15"
    assert human["bias_timeframe"] == "H4"
    assert bruce["timeframe"] == "M5"
    assert bruce["bias_timeframe"] == "H4"


def test_evaluators_are_native_and_do_not_require_ea_worker():
    market = _market()
    human = evaluate("human_apostle", copy.deepcopy(market))
    bruce = evaluate("dear_bruce", copy.deepcopy(market))
    assert human.rules["ea_worker_used"] is False
    assert bruce.rules["ea_worker_used"] is False
    assert human.rules["execution_timeframe"] == "M15"
    assert bruce.rules["execution_timeframe"] == "M5"
    assert human.stage in {"SCANNING", "WAITING_STRUCTURE_SHIFT", "WAITING_RETEST", "READY"}
    assert bruce.stage in {"SCANNING", "WAITING_STRUCTURE_SHIFT", "WAITING_RETEST", "READY"}


def test_investor_account_is_rejected_before_native_execution():
    original = native_runtime.multi_account_client.connected_by_login
    native_runtime.multi_account_client.connected_by_login = lambda: {
        123: {
            "account_id": "session-123",
            "account_info": {
                "login": 123,
                "trade_mode": 0,
                "read_only": True,
                "access_mode": "investor",
            },
        }
    }
    try:
        try:
            native_runtime._verify_account(123, allow_live=False)
            raise AssertionError("Investor account was accepted for native preset execution.")
        except PermissionError as exc:
            assert "investor/read-only" in str(exc)
    finally:
        native_runtime.multi_account_client.connected_by_login = original


def run():
    test_catalog_replaces_black_rock()
    test_native_rows_are_locked_and_described()
    test_evaluators_are_native_and_do_not_require_ea_worker()
    test_investor_account_is_rejected_before_native_execution()
    print("native apostle preset tests: 4 passed")


if __name__ == "__main__":
    run()
