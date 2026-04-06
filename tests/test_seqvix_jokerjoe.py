import pytest

import server


class DummyWS:
    def __init__(self):
        self.sent = []

    def send(self, payload):
        self.sent.append(payload)


@pytest.fixture()
def jokerjoe_client():
    cid = "test-seqvix-jokerjoe"
    server.clients.pop(cid, None)
    server.init_client(cid)
    state = server.clients[cid]
    state["ws_connected"] = True
    state["ws"] = DummyWS()
    state["strategies"] = {}
    try:
        yield cid, state
    finally:
        server.clients.pop(cid, None)


def _make_tick(symbol, digit, epoch):
    return {
        "symbol": symbol,
        "quote": 100.0 + (int(digit) / 100.0),
        "pip_size": 2,
        "epoch": epoch,
    }


def test_start_seqvix_jokerjoe_uses_selected_market_count_and_trade_total(jokerjoe_client):
    cid, state = jokerjoe_client

    server.start_seqvix_jokerjoe(state, cid, "5", trade_mode="2")

    run = state["seqvix"]["JOKERJOE"]
    assert run["running"] is True
    assert run["market_mode"] == "5"
    assert run["trade_mode"] == "2"
    assert run["scan_pool"] == "ALL"
    assert run["market_limit"] == 5
    assert run["sample_size"] == 20
    assert run["total"] == 10
    assert set(run["active_syms"]) == set(server.SEQVIX_JOKERJOE_MARKETS[:5])
    assert run["remaining_markets"] == []
    assert len(run["market_states"]) == 5
    assert len(state["ws"].sent) == 4
    assert all('"R_10"' not in payload for payload in state["ws"].sent)


def test_start_seqvix_jokerjoe_slow_pool_only_uses_non_1s_markets(jokerjoe_client):
    cid, state = jokerjoe_client

    server.start_seqvix_jokerjoe(state, cid, "10", trade_mode="2", scan_pool="SLOW")

    run = state["seqvix"]["JOKERJOE"]
    assert run["running"] is True
    assert run["market_mode"] == "10"
    assert run["trade_mode"] == "2"
    assert run["scan_pool"] == "SLOW"
    assert run["market_limit"] == len(server.SEQVIX_JOKERJOE_SLOW_MARKETS)
    assert run["scan_markets"] == server.SEQVIX_JOKERJOE_SLOW_MARKETS
    assert run["requested_market_limit"] == 10
    assert run["total"] == 20
    assert set(run["active_syms"]) == set(server.SEQVIX_JOKERJOE_SLOW_MARKETS)
    assert run["remaining_markets"] == server.SEQVIX_JOKERJOE_SLOW_MARKETS
    assert len(state["ws"].sent) == len(server.SEQVIX_JOKERJOE_SLOW_MARKETS) - 1


def test_endless_market_mode_has_infinite_total_with_selected_trade_mode(jokerjoe_client):
    cid, state = jokerjoe_client

    server.start_seqvix_jokerjoe(state, cid, "ENDLESS", trade_mode="2")

    run = state["seqvix"]["JOKERJOE"]
    assert run["running"] is True
    assert run["endless"] is True
    assert run["market_mode"] == "ENDLESS"
    assert run["trade_mode"] == "2"
    assert run["total"] == 0
    assert len(run["active_syms"]) == 10
    assert len(state["ws"].sent) == 9


def test_endless_slow_pool_stays_within_slow_markets(jokerjoe_client):
    cid, state = jokerjoe_client

    server.start_seqvix_jokerjoe(state, cid, "ENDLESS", trade_mode="1", scan_pool="SLOW")

    run = state["seqvix"]["JOKERJOE"]
    assert run["running"] is True
    assert run["endless"] is True
    assert run["scan_pool"] == "SLOW"
    assert run["market_limit"] == len(server.SEQVIX_JOKERJOE_SLOW_MARKETS)
    assert set(run["active_syms"]) == set(server.SEQVIX_JOKERJOE_SLOW_MARKETS)
    assert run["remaining_markets"] == []
    assert len(state["ws"].sent) == len(server.SEQVIX_JOKERJOE_SLOW_MARKETS) - 1


def test_slow_pool_non_endless_refills_from_rotation_queue_after_completion(jokerjoe_client):
    cid, state = jokerjoe_client

    server.start_seqvix_jokerjoe(state, cid, "10", trade_mode="1", scan_pool="SLOW")

    run = state["seqvix"]["JOKERJOE"]
    symbol = server.SEQVIX_JOKERJOE_SLOW_MARKETS[0]
    assert symbol in run["active_syms"]
    run["active_contract_id"] = "cid-slow-1"
    run["active_symbol"] = symbol

    meta = {"mode": server._seqvix_jokerjoe_mode_string(symbol, 4)}
    assert server._seqvix_jokerjoe_on_contract_settled(state, cid, "cid-slow-1", meta) is True

    assert run["done"] == 1
    assert len(run["active_syms"]) == len(server.SEQVIX_JOKERJOE_SLOW_MARKETS)
    assert symbol in run["active_syms"]


def test_endless_market_mode_replaces_finished_market_with_next_unused(jokerjoe_client):
    cid, state = jokerjoe_client

    server.start_seqvix_jokerjoe(state, cid, "ENDLESS", trade_mode="1")

    run = state["seqvix"]["JOKERJOE"]
    first_ten = server.SEQVIX_JOKERJOE_MARKETS[:10]
    untouched = server.SEQVIX_JOKERJOE_MARKETS[10:]
    assert set(run["active_syms"]) == set(first_ten)
    assert run["remaining_markets"] == untouched

    finished_symbol = first_ten[0]
    run["active_contract_id"] = "cid-1"
    run["active_symbol"] = finished_symbol

    meta = {"mode": server._seqvix_jokerjoe_mode_string(finished_symbol, 7)}
    assert server._seqvix_jokerjoe_on_contract_settled(state, cid, "cid-1", meta) is True

    assert finished_symbol not in run["active_syms"]
    assert untouched[0] in run["active_syms"]
    assert len(run["active_syms"]) == 10
    assert run["done"] == 1


def test_endless_market_mode_keeps_market_in_rotation_after_settlement(jokerjoe_client):
    cid, state = jokerjoe_client

    server.start_seqvix_jokerjoe(state, cid, "ENDLESS", trade_mode="2")
    run = state["seqvix"]["JOKERJOE"]
    symbol = server.SEQVIX_JOKERJOE_MARKETS[0]
    market = run["market_states"][symbol]
    market["state"] = "trade_open"
    run["active_contract_id"] = "cid-2"
    run["active_symbol"] = symbol

    meta = {"mode": server._seqvix_jokerjoe_mode_string(symbol, 3)}
    assert server._seqvix_jokerjoe_on_contract_settled(state, cid, "cid-2", meta) is True

    assert symbol in run["active_syms"]
    assert run["market_states"][symbol]["state"] == "waiting_for_digit"
    assert run["market_states"][symbol]["trades_done"] == 1
    assert len(run["active_syms"]) == 10


def test_process_seqvix_tick_trades_unique_lowest_digit_after_it_prints(jokerjoe_client, monkeypatch):
    cid, state = jokerjoe_client
    symbol = "R_10"
    run = state["seqvix"]["JOKERJOE"]
    run.update({
        "running": True,
        "market_mode": "5",
        "trade_mode": "1",
        "active_syms": {symbol},
        "market_states": {symbol: server._seqvix_jokerjoe_make_market_state(1)},
        "awaiting_buy": False,
        "active_contract_id": None,
        "scan_markets": [symbol],
    })

    placed = []

    def fake_try_trade(client_id, current_state, sym, digit):
        placed.append((client_id, sym, digit))
        return True, "ok"

    monkeypatch.setattr(server, "_seqvix_jokerjoe_try_trade", fake_try_trade)

    sample = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 8, 0]
    for idx, digit in enumerate(sample):
        server.process_seqvix_tick(cid, _make_tick(symbol, digit, idx + 1))

    market = run["market_states"][symbol]
    assert market["state"] == "waiting_for_digit"
    assert market["watch_digits"] == [9]

    server.process_seqvix_tick(cid, _make_tick(symbol, 9, 101))
    assert placed == []
    assert market["state"] == "ready_to_trade"
    assert market["signal_digit"] == 9

    server.process_seqvix_tick(cid, _make_tick(symbol, 0, 102))
    assert placed == [(cid, symbol, 9)]
    assert market["state"] == "trade_open"


def test_process_seqvix_tick_queues_tied_low_digits_and_trades_first_to_print(jokerjoe_client, monkeypatch):
    cid, state = jokerjoe_client
    symbol = "R_25"
    run = state["seqvix"]["JOKERJOE"]
    run.update({
        "running": True,
        "market_mode": "5",
        "trade_mode": "2",
        "active_syms": {symbol},
        "market_states": {symbol: server._seqvix_jokerjoe_make_market_state(2)},
        "awaiting_buy": False,
        "active_contract_id": None,
        "scan_markets": [symbol],
    })

    placed = []

    def fake_try_trade(client_id, current_state, sym, digit):
        placed.append((client_id, sym, digit))
        return True, "ok"

    monkeypatch.setattr(server, "_seqvix_jokerjoe_try_trade", fake_try_trade)

    sample = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 0, 1, 2, 3]
    for idx, digit in enumerate(sample):
        server.process_seqvix_tick(cid, _make_tick(symbol, digit, idx + 1))

    market = run["market_states"][symbol]
    assert market["state"] == "waiting_for_digit"
    assert market["watch_digits"] == [8, 9]

    server.process_seqvix_tick(cid, _make_tick(symbol, 9, 101))
    assert placed == []
    assert market["state"] == "ready_to_trade"
    assert market["signal_digit"] == 9

    server.process_seqvix_tick(cid, _make_tick(symbol, 0, 102))
    assert placed == [(cid, symbol, 9)]
    assert market["state"] == "trade_open"


def test_process_seqvix_tick_skips_overplayed_digit_until_next_fresh_low_digit(jokerjoe_client, monkeypatch):
    cid, state = jokerjoe_client
    symbol = "R_25"
    run = state["seqvix"]["JOKERJOE"]
    run.update({
        "running": True,
        "market_mode": "5",
        "trade_mode": "2",
        "active_syms": {symbol},
        "market_states": {symbol: server._seqvix_jokerjoe_make_market_state(2)},
        "awaiting_buy": False,
        "active_contract_id": None,
        "scan_markets": [symbol],
    })

    placed = []

    def fake_try_trade(client_id, current_state, sym, digit):
        placed.append((client_id, sym, digit))
        return True, "ok"

    monkeypatch.setattr(server, "_seqvix_jokerjoe_try_trade", fake_try_trade)

    sample = [9, 9, 9, 9, 0, 1, 2, 3, 4, 5, 6, 7, 8, 0, 1, 2, 3, 4, 5, 6]
    for idx, digit in enumerate(sample):
        server.process_seqvix_tick(cid, _make_tick(symbol, digit, idx + 1))

    market = run["market_states"][symbol]
    assert market["state"] == "waiting_for_digit"
    assert market["avoid_digit"] == 9

    server.process_seqvix_tick(cid, _make_tick(symbol, 9, 101))
    assert placed == []
    assert market["state"] == "waiting_for_digit"

    server.process_seqvix_tick(cid, _make_tick(symbol, 8, 102))
    assert market["state"] == "ready_to_trade"
    assert market["signal_digit"] == 8

    server.process_seqvix_tick(cid, _make_tick(symbol, 0, 103))
    assert placed == [(cid, symbol, 8)]
    assert market["state"] == "trade_open"


def test_process_seqvix_tick_expires_signal_if_next_tick_is_missed_due_to_busy_market(jokerjoe_client, monkeypatch):
    cid, state = jokerjoe_client
    symbol = "R_50"
    run = state["seqvix"]["JOKERJOE"]
    run.update({
        "running": True,
        "market_mode": "5",
        "trade_mode": "1",
        "active_syms": {symbol},
        "market_states": {symbol: server._seqvix_jokerjoe_make_market_state(1)},
        "awaiting_buy": False,
        "active_contract_id": None,
        "scan_markets": [symbol],
    })

    monkeypatch.setattr(server, "_seqvix_jokerjoe_try_trade", lambda *args, **kwargs: (True, "ok"))

    sample = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 8, 0]
    for idx, digit in enumerate(sample):
        server.process_seqvix_tick(cid, _make_tick(symbol, digit, idx + 1))

    market = run["market_states"][symbol]
    server.process_seqvix_tick(cid, _make_tick(symbol, 9, 101))
    assert market["state"] == "ready_to_trade"
    assert market["signal_digit"] == 9

    run["active_contract_id"] = "other-contract"
    server.process_seqvix_tick(cid, _make_tick(symbol, 4, 102))

    assert market["state"] == "waiting_for_digit"
    assert market["signal_digit"] is None
    assert "Signal expired" in str(market.get("status_text") or "")


def test_send_buy_with_profile_emits_insufficient_funds_error(jokerjoe_client, monkeypatch):
    cid, state = jokerjoe_client
    state["balance"] = 0.25
    emitted = []

    monkeypatch.setattr(server.socketio, "emit", lambda event, payload, room=None: emitted.append((event, payload, room)))

    ok, msg = server.send_buy_with_profile(cid, "JOKERJOE", "DIFFERS", 1.0, "R_10", 5)

    assert ok is False
    assert "Insufficient" in msg
    assert any(event == "api_error" and "Insufficient funds" in str(payload.get("message", "")) for event, payload, _room in emitted)


def test_send_buy_with_profile_allows_stake_equal_to_rounded_balance(jokerjoe_client):
    cid, state = jokerjoe_client
    state["balance"] = 99.995

    ok, msg = server.send_buy_with_profile(cid, "JOKERJOE", "DIFFERS", 100.0, "R_10", 5)

    assert ok is True
    assert msg == "Trade sent"
    assert len(state["ws"].sent) == 1


def test_send_buy_with_profile_can_skip_local_balance_gate(jokerjoe_client):
    cid, state = jokerjoe_client
    state["balance"] = 0.25

    ok, msg = server.send_buy_with_profile(
        cid,
        "JOKERJOE",
        "DIFFERS",
        1.0,
        "R_10",
        5,
        skip_local_balance_check=True,
    )

    assert ok is True
    assert msg == "Trade sent"


def test_blackcard_socket_trade_uses_jokerjoe_profile_and_selected_digit(jokerjoe_client, monkeypatch):
    cid, state = jokerjoe_client
    captured = {}

    monkeypatch.setattr(server, "login_required", lambda: True)
    monkeypatch.setattr(server, "get_client_state", lambda: (cid, state))

    def fake_send_buy_with_profile(client_id, profile, contract_type, stake, symbol, barrier, duration=1, duration_unit="t", mode=None, skip_local_balance_check=False):
        captured.update(
            {
                "client_id": client_id,
                "profile": profile,
                "contract_type": contract_type,
                "stake": stake,
                "symbol": symbol,
                "barrier": barrier,
                "duration": duration,
                "duration_unit": duration_unit,
            }
        )
        return True, "Trade sent"

    monkeypatch.setattr(server, "send_buy_with_profile", fake_send_buy_with_profile)

    result = server.handle_jokerjoe_blackcard_trade({"digit": 9, "stake": 2.5, "duration": 4, "symbol": "R_25"})

    assert result["status"] == "success"
    assert result["digit"] == 9
    assert captured == {
        "client_id": cid,
        "profile": "JOKERJOE",
        "contract_type": "DIFFERS",
        "stake": 2.5,
        "symbol": "R_25",
        "barrier": 9,
        "duration": 4,
        "duration_unit": "t",
    }


def test_seqvix_jokerjoe_try_trade_bypasses_local_balance_gate(jokerjoe_client):
    cid, state = jokerjoe_client
    state["balance"] = 0.25
    state["auto_stake"] = 1.0
    run = state["seqvix"]["JOKERJOE"]
    run["awaiting_buy"] = False
    run["active_contract_id"] = None

    ok, msg = server._seqvix_jokerjoe_try_trade(cid, state, "R_10", 7)

    assert ok is True
    assert msg == "Trade sent"
    assert run["awaiting_buy"] is True
    assert run["awaiting_symbol"] == "R_10"
    assert run["awaiting_digit"] == 7
    assert len(state["ws"].sent) == 1
