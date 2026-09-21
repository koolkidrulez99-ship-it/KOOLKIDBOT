import mt5_module.mt5_bridge.main as main


def test_ui_position_row_normalizes_mt5_numeric_types():
    buy = main._ui_position_row({
        "ticket": 101,
        "type": 0,
        "symbol": "EURUSD",
        "price_open": 1.1,
        "price_current": 1.2,
        "time": 1790025393,
    }, [])
    sell = main._ui_position_row({
        "ticket": 102,
        "type": 1,
        "symbol": "XAUUSD",
        "price_open": 4300,
        "price_current": 4299,
        "time": 1790025393,
    }, [])

    assert buy["type"] == "buy"
    assert sell["type"] == "sell"
    assert buy["id"] == 101
    assert sell["id"] == 102
    assert buy["open_time"]
    assert sell["open_time"]


def test_ui_position_row_normalizes_string_side():
    row = main._ui_position_row({
        "ticket": 103,
        "side": "SELL",
        "type": 0,
        "symbol": "USDCAD",
    }, [])
    assert row["type"] == "sell"
