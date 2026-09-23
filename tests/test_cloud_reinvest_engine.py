from cloud_reinvest_engine import CloudReinvestEngine
from cloud_session_manager import CloudSessionManager
import pytest


def _tick(symbol, digit, index=0):
    return {"symbol": symbol, "quote": float(f"100.{index % 10}{digit}")}


def _ready_under9(engine, *, start=1000.0):
    actions = []
    for index in range(99):
        digit = index % 8
        actions += engine.on_tick(_tick("R_10", digit, index), digit, balance=100, now_ts=start + index)
    actions += engine.on_tick(_tick("R_10", 9, 99), 9, balance=100, now_ts=start + 99)
    return actions


def test_percentage_stake_is_limited_and_uses_live_balance():
    low = CloudReinvestEngine("alice", "cid", {"stake_mode": "PERCENT", "balance_percent": 2})
    high = CloudReinvestEngine("alice", "cid", {"stake_mode": "PERCENT", "balance_percent": 80})
    valid = CloudReinvestEngine("alice", "cid", {"stake_mode": "PERCENT", "balance_percent": 15})

    assert low.settings["balance_percent"] == 10
    assert high.settings["balance_percent"] == 20
    assert valid._base_stake(200) == 30


def test_under9_scanner_emits_only_one_trade_and_locks():
    engine = CloudReinvestEngine("alice", "cid", {"cloud_trade_type": "under9", "allowed_markets": ["R_10"]})
    engine.start("cid")

    actions = _ready_under9(engine)

    assert len(actions) == 1
    assert actions[0]["intent"]["contract_type"] == "UNDER"
    assert actions[0]["intent"]["barrier"] == 9
    assert engine.trade_locked is True
    assert engine.on_tick(_tick("R_10", 9, 100), 9, balance=100, now_ts=1100) == []


def test_win_reinvests_full_profit_inside_session():
    engine = CloudReinvestEngine("alice", "cid", {"base_stake": 10, "trades_per_session": 3, "cloud_trade_type": "kidpairs"})
    engine.start("cid")
    engine.current_stake = 10
    engine.pending_signal = {"symbol": "R_10", "barrier": 1, "tick": 100}

    row = engine.on_contract_result({"contract_id": "1"}, {}, 7.5)

    assert row["result"] == "WIN"
    assert engine.current_stake == 17.5
    assert engine.session_wins == 1
    assert engine.state == "SCANNING_AGAIN"


def test_any_loss_ends_session_and_resets_next_session_stake():
    engine = CloudReinvestEngine(
        "alice",
        "cid",
        {"base_stake": 10, "trades_per_session": 5, "session_runs": 2, "session_delay": 1, "session_delay_unit": "seconds", "cloud_trade_type": "kidpairs"},
    )
    engine.start("cid")
    engine.current_stake = 17
    engine.session_wins = 3
    engine.pending_signal = {"symbol": "R_10", "barrier": 1, "tick": 100}

    row = engine.on_contract_result({"contract_id": "loss"}, {}, -17)

    assert row["session_result"] == "LOST"
    assert engine.state == "SESSION_WAIT"
    assert engine.current_stake == 10
    assert engine.session_wins == 3
    engine.on_tick(_tick("R_10", 1), 1, balance=100, now_ts=engine.wait_until + 0.1)
    assert engine.session_number == 2
    assert engine.session_wins == 0
    assert engine.current_stake == 10


@pytest.mark.parametrize("wins_before_loss", [0, 4])
def test_loss_at_any_point_marks_the_whole_session_lost(wins_before_loss):
    engine = CloudReinvestEngine(
        "alice",
        "cid",
        {"base_stake": 10, "trades_per_session": 5, "session_runs": 2, "cloud_trade_type": "kidpairs"},
    )
    engine.start("cid")
    engine.session_wins = wins_before_loss
    engine.current_stake = 15
    engine.pending_signal = {"symbol": "R_10", "barrier": 1, "tick": 100}

    row = engine.on_contract_result({"contract_id": f"loss-{wins_before_loss}"}, {}, -15)

    assert row["session_result"] == "LOST"
    assert engine.state == "SESSION_WAIT"
    assert engine.current_stake == 10
    assert engine.trade_locked is False
    assert engine.pending_signal is None


def test_optional_one_loss_daily_stop():
    engine = CloudReinvestEngine("alice", "cid", {"stop_after_one_loss": True})
    engine.start("cid")
    engine.pending_signal = {"symbol": "R_10", "barrier": 9, "tick": 100}

    engine.on_contract_result({"contract_id": "loss"}, {}, -1)

    assert engine.daily_stop is True
    assert engine.state == "DAILY_STOP_LOSS"
    assert engine.on_tick(_tick("R_10", 9), 9, balance=100) == []


def test_optional_one_win_daily_stop():
    engine = CloudReinvestEngine("alice", "cid", {"stop_after_one_win": True})
    engine.start("cid")
    engine.pending_signal = {"symbol": "R_10", "barrier": 9, "tick": 100}

    engine.on_contract_result({"contract_id": "win"}, {}, 0.8)

    assert engine.daily_stop is True
    assert engine.state == "DAILY_STOP_WIN"
    assert engine.current_stake == engine._base_stake(engine.last_balance)


def test_daily_stop_persists_in_runtime_state():
    original = CloudReinvestEngine("alice", "cid", {"stop_after_one_loss": True})
    original.start("cid")
    original.pending_signal = {"symbol": "R_10", "barrier": 9, "tick": 100}
    original.on_contract_result({"contract_id": "loss"}, {}, -1)
    settings = {**original.settings, "_runtime_state": original.runtime_state()}

    restored = CloudReinvestEngine("alice", "cid2", settings)

    assert restored.daily_stop is True
    assert restored.daily_stop_reason == "DAILY_STOP_LOSS"


def test_duplicate_settlement_does_not_advance_session_twice():
    engine = CloudReinvestEngine("alice", "cid", {"trades_per_session": 3, "cloud_trade_type": "kidpairs"})
    engine.start("cid")
    engine.pending_signal = {"symbol": "R_10", "barrier": 1, "tick": 100}

    engine.on_contract_result({"contract_id": "same"}, {}, 0.5)
    duplicate = engine.on_contract_result({"contract_id": "same"}, {}, 0.5)

    assert duplicate["duplicate"] is True
    assert engine.session_wins == 1


def test_signal_expires_before_purchase_after_too_many_ticks():
    engine = CloudReinvestEngine("alice", "cid", {"max_signal_age_ticks": 2})
    engine.start("cid")
    market = engine._market("R_10")
    market.update({"tick": 10, "last_at": __import__("time").time()})
    engine.trade_locked = True
    engine.pending_signal_id = "signal"
    engine.pending_signal = {"symbol": "R_10", "tick": 7}

    valid, reason = engine.pending_trade_valid("signal")

    assert valid is False
    assert "expired" in reason.lower()


def test_kid100_low_and_high_choose_opposite_frequency_targets():
    low = CloudReinvestEngine("alice", "cid", {"cloud_trade_type": "kid100wins", "kid100_mode": "LOW"})
    high = CloudReinvestEngine("bob", "cid", {"cloud_trade_type": "kid100wins", "kid100_mode": "HIGH"})
    for engine in (low, high):
        market = engine._market("R_10")
        market["digits"].extend(([0] * 30) + ([1] * 20) + ([2] * 15) + ([3] * 10) + ([4] * 8) + ([5] * 6) + ([6] * 5) + ([7] * 3) + ([8] * 3))
        market["tick"] = len(market["digits"]) + 10
    low.buffers["R_10"]["digits"].append(9)
    high.buffers["R_10"]["digits"].append(0)

    low_signal = low._analyze("R_10", low.buffers["R_10"])
    high_signal = high._analyze("R_10", high.buffers["R_10"])

    assert low_signal["barrier"] == 9
    assert high_signal["barrier"] == 0


@pytest.mark.parametrize(("mode", "target"), [("SAFE", 12), ("MODERATE", 20), ("AGGRESSIVE", 30)])
def test_mode_targets(mode, target):
    engine = CloudReinvestEngine("alice", "cid", {"cloud_trade_type": "digit_differs", "cloud_trade_mode": mode})
    assert engine.status()["mode_target"] == target


def test_winning_session_resets_before_next_session():
    engine = CloudReinvestEngine(
        "alice",
        "cid",
        {"base_stake": 10, "cloud_trade_type": "kidpairs", "trades_per_session": 1, "session_runs": 2, "session_delay": 1},
    )
    engine.start("cid")
    engine.pending_signal = {"symbol": "R_10", "barrier": 1, "tick": 100}
    engine.on_contract_result({"contract_id": "win"}, {}, 5)

    assert engine.state == "SESSION_WAIT"
    assert engine.session_result == "WON"
    assert engine.current_stake == 10


def test_user_engines_do_not_share_runtime_state():
    alice = CloudReinvestEngine("alice", "a", {"base_stake": 1})
    bob = CloudReinvestEngine("bob", "b", {"base_stake": 2})
    alice.start("a")
    bob.start("b")
    alice.pending_signal = {"symbol": "R_10", "barrier": 9, "tick": 100}
    alice.on_contract_result({"contract_id": "alice-contract"}, {}, -1)

    assert alice.session_result == "LOST"
    assert bob.session_result == ""
    assert bob.current_stake == 2


def test_session_manager_switches_only_requested_user_to_reinvest_engine():
    manager = CloudSessionManager()
    manager.start("alice", "a", {"strategy_name": "under9_reinvest"})
    manager.start("bob", "b", {"strategy_name": "under9_reinvest"})

    alice = manager.start("alice", "a", {"strategy_name": "reinvest_profits_100", "cloud_trade_type": "over0"})
    bob = manager.status("bob")

    assert alice["strategy_name"] == "reinvest_profits_100"
    assert bob["strategy_name"] == "under9_reinvest"


def test_reinvest_is_the_default_cloud_preset():
    manager = CloudSessionManager()

    status = manager.status("new-cloud-user")

    assert status["strategy_name"] == "reinvest_profits_100"


def test_cloud_history_restores_the_same_500_item_limit_as_profile_history():
    restored = [{"contract_id": str(index), "profit": 1, "result": "WIN"} for index in range(600)]

    engine = CloudReinvestEngine("alice", "cid", {}, restored={"history": restored})

    assert len(engine.history) == 500
    assert engine.history[0]["contract_id"] == "100"
    assert engine.history[-1]["contract_id"] == "599"


def test_cloud_budget_fields_remain_in_persisted_settings():
    engine = CloudReinvestEngine(
        "alice",
        "cid",
        {"profile_budget": 75.0, "profile_budget_realized_pnl": 4.25},
    )

    assert engine.status()["settings"]["profile_budget"] == 75.0
    assert engine.status()["settings"]["profile_budget_realized_pnl"] == 4.25


def test_clear_cloud_history_also_resets_net_pnl_totals():
    manager = CloudSessionManager()
    engine = manager.get_or_create("alice", "cid", {"strategy_name": "reinvest_profits_100"})
    engine.history = [{"contract_id": "one", "result": "WIN", "profit": 2.5}]
    engine.wins = 1
    engine.daily_profit = 2.5
    engine.session_profit = 2.5

    status = manager.clear_history("alice")

    assert manager.history("alice") == []
    assert status["wins"] == 0
    assert status["losses"] == 0
    assert status["daily_profit"] == 0.0
    assert status["session_profit"] == 0.0


def test_clear_cloud_history_resets_the_cloud_engine_runtime_but_keeps_settings():
    manager = CloudSessionManager()
    engine = manager.get_or_create("alice", "cid", {
        "strategy_name": "reinvest_profits_100",
        "base_stake": 3.0,
        "allowed_markets": ["R_25", "R_50"],
    })
    engine.start("cid")
    engine.current_market = "R_50"
    engine.current_stake = 8.0
    engine.session_profit = 5.0
    engine.daily_profit = 9.0
    engine.reinvest_step = 2
    engine.session_number = 3
    engine.session_wins = 2
    engine.daily_stop = True
    engine.buffers["R_50"] = {"tick": 100}

    status = manager.clear_history("alice")

    assert status["running"] is False
    assert status["current_market"] == "R_25"
    assert status["current_stake"] == 3.0
    assert status["session_profit"] == 0.0
    assert status["daily_profit"] == 0.0
    assert status["reinvest_step"] == 0
    assert status["session_number"] == 1
    assert status["session_wins"] == 0
    assert status["daily_stop"] is False
    assert status["settings"]["allowed_markets"] == ["R_25", "R_50"]


def test_completed_cloud_sessions_are_persisted_and_can_be_removed_individually():
    manager = CloudSessionManager()
    engine = manager.get_or_create("alice", "cid", {
        "strategy_name": "reinvest_profits_100",
        "cloud_trade_type": "kidpairs",
        "trades_per_session": 1,
        "session_runs": 2,
    })
    engine.start("cid")
    engine.pending_signal = {"symbol": "R_10", "barrier": 9, "tick": 100}

    manager.on_contract_result("alice", {"contract_id": "session-win"}, {}, 0.8)
    status = manager.status("alice")
    event = status["session_events"][0]

    assert event["result"] == "WON"
    assert event["label"] == "Target profit hit for session 1"
    remaining = manager.clear_session_event("alice", event["id"])
    assert remaining["session_events"] == []
