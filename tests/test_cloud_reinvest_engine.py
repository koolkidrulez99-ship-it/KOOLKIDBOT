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


@pytest.mark.parametrize("requested,expected", [(10, 10), (12, 10), (14, 15), (18, 20), (20, 20)])
def test_percentage_stake_uses_only_supported_dropdown_values(requested, expected):
    engine = CloudReinvestEngine("alice", "cid", {"stake_mode": "PERCENT", "balance_percent": requested})

    assert engine.settings["balance_percent"] == expected


def test_one_market_scope_limits_scanner_to_selected_market():
    engine = CloudReinvestEngine("alice", "cid", {
        "market_scan_scope": "ONE",
        "selected_market": "R_50",
        "allowed_markets": ["R_10", "R_25", "R_50"],
    })
    engine.start("cid")

    assert engine.settings["allowed_markets"] == ["R_50"]
    assert engine.needed_symbols() == ["R_50"]


def test_under9_scanner_emits_only_one_trade_and_locks():
    engine = CloudReinvestEngine("alice", "cid", {"cloud_trade_type": "under9", "allowed_markets": ["R_10"]})
    engine.start("cid")

    actions = _ready_under9(engine)

    assert len(actions) == 1
    assert actions[0]["intent"]["contract_type"] == "UNDER"
    assert actions[0]["intent"]["barrier"] == 9
    assert engine.trade_locked is True
    assert engine.on_tick(_tick("R_10", 9, 100), 9, balance=100, now_ts=1100) == []


def test_under9_requires_ten_ticks_without_nine_before_fresh_nine():
    engine = CloudReinvestEngine("alice", "cid", {"cloud_trade_type": "under9"})
    market = engine._market("R_10")
    market["digits"].extend(([1] * 89) + [9] + ([2] * 9) + [9])
    market["tick"] = 100

    assert engine._analyze("R_10", market) is None

    market["digits"].extend([2] * 10)
    market["tick"] += 10
    market["digits"].append(9)
    market["tick"] += 1
    signal = engine._analyze("R_10", market)

    assert signal["contract_type"] == "UNDER"
    assert signal["barrier"] == 9


def test_over0_requires_ten_ticks_without_zero_before_fresh_zero():
    engine = CloudReinvestEngine("alice", "cid", {"cloud_trade_type": "over0"})
    market = engine._market("R_10")
    market["digits"].extend(([1] * 89) + [0] + ([2] * 9) + [0])
    market["tick"] = 100

    assert engine._analyze("R_10", market) is None

    market["digits"].extend([2] * 10)
    market["tick"] += 10
    market["digits"].append(0)
    market["tick"] += 1
    signal = engine._analyze("R_10", market)

    assert signal["contract_type"] == "OVER"
    assert signal["barrier"] == 0


def test_ai_auto_strategy_setting_is_user_selected_and_validated():
    golden = CloudReinvestEngine("alice", "cid", {"cloud_trade_type": "ai_auto_trading", "ai_auto_strategy": "GOLDEN_CARD"})
    lowest = CloudReinvestEngine("bob", "cid", {"cloud_trade_type": "ai_auto_trading", "ai_auto_strategy": "LOWEST_PERCENT"})
    invalid = CloudReinvestEngine("eve", "cid", {"cloud_trade_type": "ai_auto_trading", "ai_auto_strategy": "UNKNOWN"})

    assert golden.settings["ai_auto_strategy"] == "GOLDEN_CARD"
    assert lowest.settings["ai_auto_strategy"] == "LOWEST_PERCENT"
    assert invalid.settings["ai_auto_strategy"] == "GOLDEN_CARD"


def test_ai_auto_lowest_percent_reuses_touch_move_away_next_tick_sequence():
    engine = CloudReinvestEngine("alice", "cid", {"cloud_trade_type": "ai_auto_trading", "ai_auto_strategy": "LOWEST_PERCENT"})
    market = engine._market("R_10")
    market["digits"].extend(([0] * 12) + ([1] * 11) + ([2] * 11) + ([3] * 11) + ([4] * 11) + ([5] * 11) + ([6] * 11) + ([7] * 11) + ([8] * 11))
    market["tick"] = len(market["digits"])

    market["digits"].append(9)
    market["tick"] += 1
    assert engine._analyze("R_10", market) is None

    market["digits"].append(1)
    market["tick"] += 1
    assert engine._analyze("R_10", market) is None

    market["digits"].append(2)
    market["tick"] += 1
    signal = engine._analyze("R_10", market)

    assert signal["contract_type"] == "DIFFERS"
    assert signal["barrier"] == 9
    assert signal["source_signal"] == "LOWEST_PERCENT"


def test_ai_auto_golden_card_reuses_existing_koolkid_recommendation():
    engine = CloudReinvestEngine("alice", "cid", {"cloud_trade_type": "ai_auto_trading", "ai_auto_strategy": "GOLDEN_CARD"})
    market = engine._market("R_10")
    market["digits"].extend((([9] * 9) + [0]) * 10)
    market["tick"] = 100

    signal = engine._analyze("R_10", market)

    assert signal["contract_type"] == "OVER"
    assert signal["barrier"] == 0
    assert signal["source_signal"] == "GOLDEN_CARD"


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


def test_reinvest_history_persists_duration_and_exit_digit():
    engine = CloudReinvestEngine("alice", "cid", {
        "base_stake": 1,
        "trades_per_session": 3,
        "cloud_trade_type": "kidpairs",
        "duration": 2,
    })
    engine.start("cid")
    engine.pending_signal = {"symbol": "R_25", "barrier": 1, "tick": 100}

    row = engine.on_contract_result(
        {"contract_id": "duration-exit", "buy_price": 1},
        {"duration": 2, "duration_unit": "t", "exit_digit": 7},
        0.8,
    )

    assert row["duration"] == 2
    assert row["duration_unit"] == "t"
    assert row["exit_digit"] == 7
    assert engine.history[-1]["exit_digit"] == 7


@pytest.mark.parametrize("trade_type", sorted({
    "kidpairs", "over3_analysis", "mpull_over5", "under9", "over0", "digit_differs", "odd", "rise", "higher", "kid100wins", "ai_auto_trading",
}))
def test_every_reinvest_trade_type_compounds_the_actual_settled_buy_price(trade_type):
    settings = {
        "base_stake": 10,
        "trades_per_session": 3,
        "cloud_trade_type": trade_type,
        "cloud_trade_mode": "SAFE",
    }
    engine = CloudReinvestEngine("alice", "cid", settings)
    engine.start("cid")
    engine.current_stake = 10
    engine.pending_signal = {"symbol": "R_10", "barrier": 1, "tick": 100}

    row = engine.on_contract_result(
        {"contract_id": f"{trade_type}-win", "buy_price": 9.5},
        {"proposal_ask_price": 9.75},
        7.5,
    )

    assert row["buy_price"] == 9.5
    assert row["requested_stake"] == 10
    assert row["next_stake"] == 17.0
    assert engine.current_stake == 17.0
    assert engine.state == "SCANNING_AGAIN"


def test_budget_or_market_settings_update_does_not_reset_compounded_stake():
    engine = CloudReinvestEngine("alice", "cid", {
        "base_stake": 10,
        "trades_per_session": 3,
        "cloud_trade_type": "kidpairs",
        "allowed_markets": ["R_10", "R_25"],
    })
    engine.start("cid")
    engine.pending_signal = {"symbol": "R_10", "barrier": 1, "tick": 100}
    engine.on_contract_result({"contract_id": "win", "buy_price": 10}, {}, 7.5)

    engine.update_settings({"profile_budget_realized_pnl": 7.5})
    engine.update_settings({"allowed_markets": ["R_25"]})

    assert engine.current_market == "R_25"
    assert engine.current_stake == 17.5
    assert engine.reinvest_step == 1


def test_history_profit_is_the_authoritative_sum_of_persisted_cloud_rows():
    engine = CloudReinvestEngine("alice", "cid", {})
    engine.history = [
        {"contract_id": "one", "profit": 0.8, "result": "WIN"},
        {"contract_id": "two", "profit": -1.0, "result": "LOSS"},
    ]
    engine.daily_profit = 99.0

    assert engine.status()["history_profit"] == -0.2


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
    assert event["profit"] == 0.8
    remaining = manager.clear_session_event("alice", event["id"])
    assert remaining["session_events"] == []


def test_new_cloud_trade_types_use_fixed_market_scopes():
    odd = CloudReinvestEngine("odd-user", "cid", {"cloud_trade_type": "odd"})
    rise = CloudReinvestEngine("rise-user", "cid", {"cloud_trade_type": "rise"})
    higher = CloudReinvestEngine("higher-user", "cid", {"cloud_trade_type": "higher"})

    assert odd.settings["allowed_markets"] == ["JD10", "JD25", "JD50", "JD75", "JD100"]
    assert rise.settings["allowed_markets"] == ["STPRNG", "STPRNG2", "STPRNG3", "STPRNG4", "STPRNG5"]
    assert higher.settings["allowed_markets"] == ["R_75"]


def test_cloud_odd_waits_for_four_consecutive_even_digits_on_jump_markets():
    engine = CloudReinvestEngine("alice", "cid", {"cloud_trade_type": "odd"})
    engine.start("cid")
    actions = []
    for index, digit in enumerate([2, 4, 6]):
        actions += engine.on_tick({"symbol": "JD10", "quote": 100.0 + index}, digit, balance=100, now_ts=1000 + index)
    assert actions == []

    actions = engine.on_tick({"symbol": "JD10", "quote": 104.0}, 8, balance=100, now_ts=1004)

    assert len(actions) == 1
    intent = actions[0]["intent"]
    assert intent["contract_type"] == "ODD"
    assert intent["deriv_contract_type"] == "DIGITODD"
    assert intent["barrier"] is None
    assert intent["duration"] == 1


def test_cloud_odd_does_not_scan_non_jump_markets():
    engine = CloudReinvestEngine("alice", "cid", {"cloud_trade_type": "odd"})
    engine.start("cid")

    for index, digit in enumerate([2, 4, 6, 8]):
        actions = engine.on_tick({"symbol": "R_75", "quote": 100.0 + index}, digit, balance=100, now_ts=1000 + index)

    assert actions == []


def test_cloud_rise_uses_step_market_and_five_consecutive_up_moves():
    engine = CloudReinvestEngine("alice", "cid", {"cloud_trade_type": "rise"})
    engine.start("cid")
    actions = []
    for index, price in enumerate([100.0, 101.0, 102.0, 103.0, 104.0, 105.0]):
        actions = engine.on_tick({"symbol": "stpRNG", "quote": price}, index % 10, balance=100, now_ts=2000 + index)

    assert len(actions) == 1
    intent = actions[0]["intent"]
    assert intent["contract_type"] == "RISE"
    assert intent["deriv_contract_type"] == "CALL"
    assert intent["barrier"] is None
    assert intent["duration"] == 1


def test_cloud_rise_rejects_mixed_trend():
    engine = CloudReinvestEngine("alice", "cid", {"cloud_trade_type": "rise"})
    market = engine._market("STPRNG")
    market["prices"].extend([100.0, 101.0, 102.0, 101.5, 103.0, 104.0])
    market["digits"].extend([0, 1, 2, 3, 4, 5])
    market["tick"] = 6

    assert engine._analyze("STPRNG", market) is None


def test_cloud_higher_arms_below_minus_7_5_level_then_enters_after_full_recovery():
    engine = CloudReinvestEngine("alice", "cid", {"cloud_trade_type": "higher"})
    engine.start("cid")
    # Nineteen V75 prices build a reference high of 110.
    base = [108.0] * 18 + [110.0]
    for index, price in enumerate(base):
        assert engine.on_tick({"symbol": "R_75", "quote": price}, index % 10, balance=100, now_ts=3000 + index) == []

    # Price goes below the reference barrier price: 110 - 7.5 = 102.5.
    assert engine.on_tick({"symbol": "R_75", "quote": 102.0}, 2, balance=100, now_ts=3020) == []
    assert engine.buffers["R_75"]["higher_recovery"]["barrier_price"] == 102.5

    # Recovery is not enough yet.
    assert engine.on_tick({"symbol": "R_75", "quote": 108.0}, 8, balance=100, now_ts=3021) == []

    # Going past the original 110 reference triggers the 5-tick Higher.
    actions = engine.on_tick({"symbol": "R_75", "quote": 110.5}, 5, balance=100, now_ts=3022)

    assert len(actions) == 1
    intent = actions[0]["intent"]
    assert intent["contract_type"] == "HIGHER"
    assert intent["deriv_contract_type"] == "HIGHER"
    assert intent["barrier"] == -7.5
    assert intent["duration"] == 5


def test_cloud_digit_differs_requires_highest_then_lowest_transition():
    engine = CloudReinvestEngine("alice", "cid", {"cloud_trade_type": "digit_differs"})
    market = engine._market("R_10")

    first = ([7] * 20)
    for digit in [0, 1, 2, 3, 4, 5, 6, 8, 9]:
        first.extend([digit] * 8)
    first.extend([0, 1, 2, 3, 4, 5, 6, 8])
    assert len(first) == 100
    market["digits"].extend(first)
    market["tick"] = 100

    assert engine._differ_candidate(market) is None
    assert 7 in market["differs_peak_tracker"]

    second = []
    for digit in [0, 1, 2, 3, 4, 5, 6, 8, 9]:
        second.extend([digit] * 11)
    second.append(0)
    assert len(second) == 100
    market["digits"].clear()
    market["digits"].extend(second)
    market["tick"] = 200

    signal = engine._differ_candidate(market)

    assert signal is not None
    assert signal["digit"] == 7
    assert signal["source_signal"] == "HIGHEST_TO_LOWEST"
    assert signal["peak_pct"] > signal["lowest_pct"]


def test_cloud_digit_differs_does_not_trade_a_low_digit_that_was_never_highest():
    engine = CloudReinvestEngine("alice", "cid", {"cloud_trade_type": "digit_differs"})
    market = engine._market("R_10")
    digits = ([0] * 20) + ([1] * 10) + ([2] * 10) + ([3] * 10) + ([4] * 10) + ([5] * 10) + ([6] * 10) + ([8] * 10) + ([9] * 9) + [7]
    market["digits"].extend(digits)
    market["tick"] = 100

    signal = engine._differ_candidate(market)

    assert signal is None
    assert 0 in market["differs_peak_tracker"]
    assert 7 not in market["differs_peak_tracker"]


def test_cloud_rise_needed_symbols_use_deriv_step_symbol_casing():
    engine = CloudReinvestEngine("alice", "cid", {"cloud_trade_type": "rise"})
    engine.start("cid")

    assert engine.needed_symbols() == ["stpRNG", "stpRNG2", "stpRNG3", "stpRNG4", "stpRNG5"]
