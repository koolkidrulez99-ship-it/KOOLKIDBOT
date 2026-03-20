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
