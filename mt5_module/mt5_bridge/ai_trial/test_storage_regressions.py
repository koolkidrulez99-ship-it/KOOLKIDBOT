from ai_trial.storage import normalize_snapshot


def test_old_trial_snapshot_is_migrated_without_structure_fields():
    old = {
        "account_login": 202177726,
        "symbol": "Volatility 75 (1s) Index",
        "decision": "BUY",
        "confidence": 100,
        "proposed_trade": {"direction": "BUY", "entry": 5453.13, "sl": 5443.13, "tp": 5463.13},
    }

    migrated = normalize_snapshot(old)

    assert migrated is not None
    assert migrated["structure_shift"] == {"confirmed": False, "index": None, "time": None}
    assert migrated["retest"] == {"level": None, "touched": False, "same_candle_blocked": False}
    assert migrated["confidence_factors"] == []
    assert migrated["rules"]["completed_candles_only"] is True
    assert migrated["rules"]["take_profit_r"] == 2.0


def test_malformed_trial_snapshot_numbers_do_not_break_migration():
    migrated = normalize_snapshot({"confidence": "bad", "rules": {"swing_left": "x", "take_profit_r": "bad"}})

    assert migrated is not None
    assert migrated["confidence"] == 0.0
    assert migrated["rules"]["swing_left"] == 0
    assert migrated["rules"]["take_profit_r"] == 2.0
