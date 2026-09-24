from strategies.unchain import UnchainStrategy


def test_unchain_on_tick_dedupes_duplicate_epoch_and_price():
    strat = UnchainStrategy()
    tick = {"symbol": "1HZ30V", "quote": 7215.6, "epoch": 1000}
    strat.on_tick(tick, digit=6)
    strat.on_tick(dict(tick), digit=6)

    assert strat.tick_count == 1
    assert strat.market_tick_counter == 1


def test_unchain_on_tick_counts_new_tick_when_price_changes_same_epoch():
    strat = UnchainStrategy()
    first = {"symbol": "1HZ30V", "quote": 7215.6, "epoch": 1000}
    second = {"symbol": "1HZ30V", "quote": 7215.7, "epoch": 1000}
    strat.on_tick(first, digit=6)
    strat.on_tick(second, digit=7)

    assert strat.tick_count == 2
    assert strat.market_tick_counter == 2


def test_unchain_warmed_tick_analysis_does_not_raise_on_deque_history():
    strat = UnchainStrategy()
    base = 7215.6
    for i in range(300):
        tick = {"symbol": "1HZ30V", "quote": base + (i * 0.01), "epoch": 2000 + i}
        strat.on_tick(tick, digit=i % 10)

    assert strat.tick_count == 300
    assert strat.market_tick_counter == 300
    assert strat.signal_state in {"WAIT", "READY", "TAKE NOW"}
