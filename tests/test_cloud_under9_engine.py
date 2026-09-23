from datetime import datetime, timezone

from cloud_under9_engine import CloudUnder9Engine


def _tick(symbol, digit):
    return {"symbol": symbol, "quote": float(f"100.{digit}")}


def _price_tick(symbol, price):
    return {"symbol": symbol, "quote": float(price)}


def test_cloud_under9_places_one_trade_when_single_9_prints_at_9_percent_or_lower():
    engine = CloudUnder9Engine("alice", "cid", {"base_stake": 10, "allowed_markets": ["R_10"]})
    engine.start("cid")

    actions = []
    for i in range(99):
        actions.extend(engine.on_tick(_tick("R_10", i % 8), i % 8, balance=100))
    assert actions == []

    actions = engine.on_tick(_tick("R_10", 9), 9, balance=100)

    assert len(actions) == 1
    assert actions[0]["type"] == "trade"
    assert actions[0]["intent"]["contract_type"] == "UNDER"
    assert actions[0]["intent"]["barrier"] == 9
    assert actions[0]["intent"]["stake"] == 10

    # A repeated 9 cannot spam another trade while this signal is locked.
    assert engine.on_tick(_tick("R_10", 9), 9, balance=100) == []


def test_cloud_under9_blocks_single_9_when_digit9_percentage_is_above_9():
    engine = CloudUnder9Engine("alice", "cid", {"base_stake": 10, "allowed_markets": ["R_10"]})
    engine.start("cid")

    for _ in range(10):
        engine.on_tick(_tick("R_10", 9), 9, balance=100)
    for i in range(89):
        engine.on_tick(_tick("R_10", i % 8), i % 8, balance=100)

    actions = engine.on_tick(_tick("R_10", 9), 9, balance=100)

    assert actions == []
    assert engine.digit9_percentage() == 11.0


def test_cloud_under9_reinvests_full_profit_then_resets_on_loss():
    engine = CloudUnder9Engine("alice", "cid", {"base_stake": 10, "take_profit_target": 50})
    engine.start("cid")
    engine.current_stake = 10
    win_row = engine.on_contract_result({"contract_id": "1"}, {"stake": 10}, 7.5)

    assert win_row["result"] == "WIN"
    assert engine.current_stake == 17.5
    assert engine.reinvest_step == 1

    loss_row = engine.on_contract_result({"contract_id": "2"}, {"stake": 17.5}, -17.5)

    assert loss_row["result"] == "LOSS"
    assert engine.current_stake == 10
    assert engine.reinvest_step == 0


def test_cloud_under9_history_persists_duration_and_exit_digit():
    engine = CloudUnder9Engine("alice", "cid", {"base_stake": 1, "duration": 2, "duration_unit": "t"})
    engine.start("cid")

    row = engine.on_contract_result(
        {"contract_id": "duration-exit"},
        {"duration": 2, "duration_unit": "t", "exit_digit": 6},
        0.8,
    )

    assert row["duration"] == 2
    assert row["duration_unit"] == "t"
    assert row["exit_digit"] == 6
    assert engine.history[-1]["exit_digit"] == 6


def test_cloud_under9_capital_build_resets_at_double_base():
    engine = CloudUnder9Engine("alice", "cid", {"base_stake": 10, "capital_build_mode": True})
    engine.start("cid")
    engine.current_stake = 18

    row = engine.on_contract_result({"contract_id": "3"}, {"stake": 18}, 20)

    assert row["tp_hit"] is True
    assert engine.current_stake == 10
    assert engine.reinvest_step == 0
    assert engine.session_profit == 0


def test_cloud_base_stake_save_updates_current_trade_stake_when_idle():
    engine = CloudUnder9Engine("alice", "cid", {"base_stake": 10})
    engine.start("cid")
    engine.current_stake = 17.5
    engine.reinvest_step = 1

    engine.update_settings({"base_stake": 12})

    assert engine.settings["base_stake"] == 12
    assert engine.current_stake == 12
    assert engine.reinvest_step == 0


def test_cloud_base_stake_save_waits_for_open_trade_then_applies():
    engine = CloudUnder9Engine("alice", "cid", {"base_stake": 10})
    engine.start("cid")
    engine.current_stake = 17.5
    engine.trade_locked = True
    engine.open_contract_id = "abc"

    engine.update_settings({"base_stake": 12})

    assert engine.current_stake == 17.5
    assert engine.base_stake_reset_pending is True

    row = engine.on_contract_result({"contract_id": "abc"}, {"stake": 17.5}, 8)

    assert row["result"] == "WIN"
    assert engine.current_stake == 12
    assert engine.reinvest_step == 0


def test_cloud_market_settings_remove_current_market_from_rotation():
    engine = CloudUnder9Engine("alice", "cid", {"allowed_markets": ["R_10", "JD10", "JD25"]})
    engine.start("cid")
    engine.current_market = "R_10"
    engine.tick_digits.extend([1, 2, 3])

    engine.update_settings({"allowed_markets": ["JD10", "JD25"]})

    assert engine.current_market == "JD10"
    assert engine.settings["allowed_markets"] == ["JD10", "JD25"]
    assert list(engine.tick_digits) == []


def test_cloud_morning_window_blocks_valid_signal_outside_jamaica_window():
    engine = CloudUnder9Engine(
        "alice",
        "cid",
        {
            "base_stake": 10,
            "allowed_markets": ["R_10"],
            "trade_time_mode": "PRESET_9_13",
        },
    )
    engine.start("cid")
    for i in range(99):
        engine.on_tick(_tick("R_10", i % 8), i % 8, balance=100)

    outside_window = datetime(2026, 5, 24, 13, 59, tzinfo=timezone.utc).timestamp()
    actions = engine.on_tick(_tick("R_10", 9), 9, balance=100, now_ts=outside_window)

    assert actions == []
    assert "Waiting for Jamaica EST trade window" in engine.last_signal


def test_cloud_morning_window_allows_valid_signal_inside_jamaica_window():
    engine = CloudUnder9Engine(
        "alice",
        "cid",
        {
            "base_stake": 10,
            "allowed_markets": ["R_10"],
            "trade_time_mode": "PRESET_9_13",
        },
    )
    engine.start("cid")
    for i in range(99):
        engine.on_tick(_tick("R_10", i % 8), i % 8, balance=100)

    inside_window = datetime(2026, 5, 24, 14, 30, tzinfo=timezone.utc).timestamp()
    actions = engine.on_tick(_tick("R_10", 9), 9, balance=100, now_ts=inside_window)

    assert len(actions) == 1
    assert actions[0]["type"] == "trade"


def test_cloud_overnight_window_allows_after_midnight_jamaica_time():
    engine = CloudUnder9Engine(
        "alice",
        "cid",
        {
            "base_stake": 10,
            "allowed_markets": ["R_10"],
            "trade_time_mode": "PRESET_17_01",
        },
    )
    engine.start("cid")
    for i in range(99):
        engine.on_tick(_tick("R_10", i % 8), i % 8, balance=100)

    after_midnight = datetime(2026, 5, 24, 5, 30, tzinfo=timezone.utc).timestamp()
    actions = engine.on_tick(_tick("R_10", 9), 9, balance=100, now_ts=after_midnight)

    assert len(actions) == 1
    assert actions[0]["type"] == "trade"


def test_cloud_custom_window_blocks_outside_custom_start_end():
    engine = CloudUnder9Engine(
        "alice",
        "cid",
        {
            "base_stake": 10,
            "allowed_markets": ["R_10"],
            "trade_time_mode": "CUSTOM",
            "custom_trade_start_time": "10:00",
            "custom_trade_end_time": "11:00",
        },
    )
    engine.start("cid")
    for i in range(99):
        engine.on_tick(_tick("R_10", i % 8), i % 8, balance=100)

    outside_custom = datetime(2026, 5, 24, 16, 30, tzinfo=timezone.utc).timestamp()
    actions = engine.on_tick(_tick("R_10", 9), 9, balance=100, now_ts=outside_custom)

    assert actions == []
    assert "10:00 - 11:00" in engine.last_signal


def test_koolkid_profit_waits_for_crash_and_five_later_confirmation_ticks():
    engine = CloudUnder9Engine(
        "alice",
        "cid",
        {"strategy_name": "koolkid_profit", "base_stake": 2, "allowed_markets": ["R_10"]},
    )
    engine.start("cid")
    for index in range(31):
        assert engine.on_tick(_price_tick("R_10", 100 + (index * 0.1)), index % 10, balance=100) == []

    assert engine.on_tick(_price_tick("R_10", 95), 0, balance=100) == []
    for index in range(4):
        assert engine.on_tick(_price_tick("R_10", 95 + ((index + 1) * 0.02)), index, balance=100) == []

    actions = engine.on_tick(_price_tick("R_10", 95.10), 1, balance=100)

    assert len(actions) == 1
    assert actions[0]["intent"]["deriv_contract_type"] == "ACCU"
    assert actions[0]["intent"]["growth_rate"] == 0.05
    assert actions[0]["intent"]["hold_ticks"] == 2
    assert actions[0]["intent"]["stake"] == 2


def test_koolkid_profit_requests_close_after_two_ticks_only_once():
    engine = CloudUnder9Engine("alice", "cid", {"strategy_name": "koolkid_profit", "allowed_markets": ["R_10"]})
    engine.start("cid")
    engine.total_ticks = 40
    engine.trade_locked = True
    engine.mark_trade_open("123")

    assert engine.on_tick(_price_tick("R_10", 100.1), 1, balance=100) == []
    actions = engine.on_tick(_price_tick("R_10", 100.2), 2, balance=100)
    assert actions == [{"type": "close_trade", "contract_id": "123"}]
    assert engine.on_tick(_price_tick("R_10", 100.3), 3, balance=100) == []


def test_koolkid_profit_compounds_selected_profit_share_and_resets_after_loss():
    engine = CloudUnder9Engine(
        "alice",
        "cid",
        {"strategy_name": "koolkid_profit", "base_stake": 10, "compound_percent": 50},
    )
    engine.start("cid")
    engine.current_stake = 10

    win = engine.on_contract_result({"contract_id": "1"}, {"stake": 10}, 4)
    assert win["result"] == "WIN"
    assert engine.current_stake == 12

    loss = engine.on_contract_result({"contract_id": "2"}, {"stake": 12}, -3)
    assert loss["result"] == "LOSS"
    assert engine.current_stake == 10


def test_koolkid_profit_stops_new_setups_after_two_opened_trades_for_day():
    engine = CloudUnder9Engine("alice", "cid", {"strategy_name": "koolkid_profit", "allowed_markets": ["R_10"]})
    engine.start("cid")
    engine.daily_trade_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    engine.daily_trade_count = 2
    engine.price_ticks.extend([100 + (index * 0.01) for index in range(31)])
    engine.ticks_since_crash = 31

    actions = engine.on_tick(_price_tick("R_10", 90), 0, balance=100)

    assert actions == []
    assert "Daily target complete" in engine.last_signal
