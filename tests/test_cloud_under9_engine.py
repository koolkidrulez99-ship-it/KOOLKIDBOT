from cloud_under9_engine import CloudUnder9Engine


def _tick(symbol, digit):
    return {"symbol": symbol, "quote": float(f"100.{digit}")}


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
