import json
import threading
import time

import server


class _InlineThread:
    def __init__(self, target=None, args=None, kwargs=None, **_rest):
        self._target = target
        self._args = args or ()
        self._kwargs = kwargs or {}

    def start(self):
        if self._target:
            self._target(*self._args, **self._kwargs)


class _DummyWs:
    def __init__(self):
        self.messages = []
        self.closed = False

    def send(self, payload):
        self.messages.append(json.loads(payload))

    def close(self):
        self.closed = True


def test_schedule_contract_open_refresh_requests_one_shot_status(monkeypatch):
    ws = _DummyWs()
    state = {
        "ws_nonce": "nonce-1",
        "ws_connected": True,
        "ws": ws,
        "open_contract_subs": {},
    }
    monkeypatch.setattr(server, "clients", {"cid-fast": state})
    monkeypatch.setattr(server.threading, "Thread", _InlineThread)
    monkeypatch.setattr(server.time, "sleep", lambda *_args, **_kwargs: None)

    ok = server._schedule_contract_open_refresh("cid-fast", "nonce-1", "12345", delays=(0.01,))

    assert ok is True
    assert ws.messages == [{"proposal_open_contract": 1, "contract_id": 12345}]


def test_contract_open_refresh_delays_are_absolute_not_cumulative(monkeypatch):
    ws = _DummyWs()
    state = {
        "ws_nonce": "nonce-absolute",
        "ws_connected": True,
        "ws": ws,
        "open_contract_subs": {},
    }
    sleeps = []
    now = [100.0]
    monkeypatch.setattr(server, "clients", {"cid-absolute": state})
    monkeypatch.setattr(server.threading, "Thread", _InlineThread)
    monkeypatch.setattr(server, "_trade_latency_now", lambda: now[0])

    def fake_sleep(delay):
        sleeps.append(round(delay, 3))
        now[0] += delay

    monkeypatch.setattr(server.time, "sleep", fake_sleep)

    ok = server._schedule_contract_open_refresh("cid-absolute", "nonce-absolute", "12345", delays=(0.10, 0.30, 0.70))

    assert ok is True
    assert sleeps == [0.10, 0.20, 0.40]
    assert len(ws.messages) == 3


def test_fast_contract_refresh_delays_use_short_initial_lane():
    delays = server._contract_refresh_delays_for_meta({
        "profile": "KOOLKID",
        "type": "OVER",
        "duration": 1,
        "duration_unit": "t",
    })

    assert delays[0] <= 0.05
    assert delays == server.FAST_CONTRACT_REFRESH_DELAYS


def test_normal_contract_refresh_delays_keep_default_fallback():
    delays = server._contract_refresh_delays_for_meta({
        "profile": "UNCHAIN",
        "type": "HIGHER",
        "duration": 5,
        "duration_unit": "m",
    })

    assert delays == server.DEFAULT_CONTRACT_REFRESH_DELAYS


def test_schedule_contract_open_refresh_still_checks_when_subscription_already_exists(monkeypatch):
    ws = _DummyWs()
    state = {
        "ws_nonce": "nonce-1",
        "ws_connected": True,
        "ws": ws,
        "open_contract_subs": {"12345": "sub-1"},
    }
    monkeypatch.setattr(server, "clients", {"cid-fast": state})
    monkeypatch.setattr(server.threading, "Thread", _InlineThread)
    monkeypatch.setattr(server.time, "sleep", lambda *_args, **_kwargs: None)

    ok = server._schedule_contract_open_refresh("cid-fast", "nonce-1", "12345", delays=(0.01,))

    assert ok is True
    assert ws.messages == [{"proposal_open_contract": 1, "contract_id": 12345}]


def test_multi_tick_digit_contract_refresh_delays_extend_past_short_window():
    delays = server._contract_refresh_delays_for_meta({
        "profile": "KOOLKID",
        "type": "OVER",
        "duration": 5,
        "duration_unit": "t",
    })

    assert delays[: len(server.FAST_CONTRACT_REFRESH_DELAYS)] == server.FAST_CONTRACT_REFRESH_DELAYS
    assert max(delays) > max(server.FAST_CONTRACT_REFRESH_DELAYS)


def test_buy_confirm_emits_trade_placed_immediately_and_uses_fast_refresh(monkeypatch):
    emitted = []
    refresh_calls = []
    ws = _DummyWs()
    state = {
        "ws_nonce": "nonce-buy",
        "ws_connected": True,
        "ws": ws,
        "req_meta": {
            101: {
                "profile": "KOOLKID",
                "type": "OVER",
                "barrier": 1,
                "stake": 0.35,
                "symbol": "R_10",
                "time": "now",
                "duration": 1,
                "duration_unit": "t",
            }
        },
        "contract_meta": {},
        "active_profile": "KOOLKID",
        "strategies": {},
        "bot_auto_close_timers": {},
    }
    monkeypatch.setattr(server, "clients", {"cid-buy": state})
    monkeypatch.setattr(server.socketio, "emit", lambda event, payload=None, room=None: emitted.append((event, payload, room)))
    monkeypatch.setattr(server, "_schedule_contract_open_refresh", lambda cid, nonce, contract_id, delays=None: refresh_calls.append((cid, nonce, contract_id, delays)) or True)
    monkeypatch.setattr(server, "_schedule_bot_auto_close", lambda *_args, **_kwargs: None)

    server.handle_on_message("cid-buy", ws, json.dumps({
        "req_id": 101,
        "buy": {"contract_id": 555, "buy_price": 0.35},
    }), "nonce-buy")

    trade_events = [item for item in emitted if item[0] == "trade_placed"]
    assert len(trade_events) == 1
    assert trade_events[0][1]["contract_id"] == 555
    assert trade_events[0][1]["pending"] is True
    assert "_server_event_ms" in trade_events[0][1]
    assert refresh_calls == [("cid-buy", "nonce-buy", 555, server.FAST_CONTRACT_REFRESH_DELAYS)]
    assert ws.messages == [{"proposal_open_contract": 1, "contract_id": 555, "subscribe": 1}]


def test_human_pair_buy_confirm_emits_exact_pair_action(monkeypatch):
    emitted = []
    refresh_calls = []
    ws = _DummyWs()
    state = {
        "ws_nonce": "nonce-human-pair",
        "ws_connected": True,
        "ws": ws,
        "req_meta": {
            202: {
                "profile": "HUMAN",
                "type": "ASIANS DOWN",
                "stake": 0.35,
                "symbol": "R_10",
                "time": "now",
                "duration": 2,
                "duration_unit": "t",
                "mode": "human_manual_contract",
                "contract_type": "ASIAND",
                "pair_batch_id": 900,
                "pair_batch_size": 2,
                "pair_leg_index": 1,
                "pair_action": "ASIANS_DOWN",
            }
        },
        "contract_meta": {},
        "human_pending_contracts": {},
        "active_profile": "HUMAN",
        "strategies": {},
        "bot_auto_close_timers": {},
    }
    monkeypatch.setattr(server, "clients", {"cid-human-pair-buy": state})
    monkeypatch.setattr(server.socketio, "emit", lambda event, payload=None, room=None: emitted.append((event, payload, room)))
    monkeypatch.setattr(server, "_schedule_contract_open_refresh", lambda cid, nonce, contract_id, delays=None: refresh_calls.append((cid, nonce, contract_id, delays)) or True)
    monkeypatch.setattr(server, "_schedule_bot_auto_close", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_upsert_human_pending_contract", lambda *_args, **_kwargs: None)

    server.handle_on_message("cid-human-pair-buy", ws, json.dumps({
        "req_id": 202,
        "buy": {"contract_id": 9090, "buy_price": 0.35},
    }), "nonce-human-pair")

    trade_events = [item for item in emitted if item[0] == "trade_placed"]
    assert len(trade_events) == 1
    assert trade_events[0][1]["contract_id"] == 9090
    assert trade_events[0][1]["action"] == "ASIANS_DOWN"
    assert trade_events[0][1]["pair_action"] == "ASIANS_DOWN"


def test_settled_open_contract_emits_trade_result_immediately(monkeypatch):
    emitted = []

    class _Strategy:
        risk_block_reason = None

        def on_contract(self, contract, settled_balance):
            self.contract = contract
            self.balance = settled_balance

        def get_last_trade_entry(self):
            return {"result": "WIN", "profit": 0.12}

    state = {
        "active_profile": "KOOLKID",
        "strategies": {"KOOLKID": _Strategy()},
        "contract_meta": {
            "777": {
                "profile": "KOOLKID",
                "type": "OVER",
                "barrier": 1,
                "stake": 0.35,
                "symbol": "R_10",
                "time": "now",
                "duration": 1,
                "duration_unit": "t",
            }
        },
        "processed_contract_ids": set(),
        "balance": 100.0,
        "last_known_trade_balance": 100.0,
        "local_balance_adjustment": 0.0,
        "profile_budgets": server._new_profile_budget_map(),
        "bot_auto_close_timers": {},
    }
    monkeypatch.setattr(server, "clients", {"cid-result": state})
    monkeypatch.setattr(server.socketio, "emit", lambda event, payload=None, room=None: emitted.append((event, payload, room)))
    monkeypatch.setattr(server, "send_stats_update", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_emit_balance_payload", lambda *_args, **_kwargs: None)

    server.process_contract("cid-result", {
        "contract_id": 777,
        "is_sold": 1,
        "status": "won",
        "profit": 0.12,
        "sell_price": 0.47,
    })

    result_events = [item for item in emitted if item[0] == "trade_result"]
    assert len(result_events) == 1
    assert result_events[0][1]["contract_id"] == 777
    assert result_events[0][1]["result"] == "WIN"
    assert "_server_event_ms" in result_events[0][1]


def test_human_pair_result_emits_exact_pair_action(monkeypatch):
    emitted = []

    class _Strategy:
        risk_block_reason = None

        def on_contract(self, contract, settled_balance):
            self.contract = contract
            self.balance = settled_balance

        def get_last_trade_entry(self):
            return {"result": "LOSS", "profit": -0.35}

    state = {
        "active_profile": "HUMAN",
        "strategies": {"HUMAN": _Strategy()},
        "contract_meta": {
            "9191": {
                "profile": "HUMAN",
                "type": "ASIANS DOWN",
                "stake": 0.35,
                "symbol": "R_10",
                "time": "now",
                "duration": 2,
                "duration_unit": "t",
                "mode": "human_manual_contract",
                "contract_type": "ASIAND",
                "pair_batch_id": 901,
                "pair_batch_size": 2,
                "pair_leg_index": 1,
                "pair_action": "ASIANS_DOWN",
            }
        },
        "human_pending_contracts": {},
        "processed_contract_ids": set(),
        "balance": 100.0,
        "last_known_trade_balance": 100.0,
        "local_balance_adjustment": 0.0,
        "profile_budgets": server._new_profile_budget_map(),
        "bot_auto_close_timers": {},
    }
    monkeypatch.setattr(server, "clients", {"cid-human-pair-result": state})
    monkeypatch.setattr(server.socketio, "emit", lambda event, payload=None, room=None: emitted.append((event, payload, room)))
    monkeypatch.setattr(server, "send_stats_update", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_emit_balance_payload", lambda *_args, **_kwargs: None)

    server.process_contract("cid-human-pair-result", {
        "contract_id": 9191,
        "is_sold": 1,
        "status": "lost",
        "profit": -0.35,
        "sell_price": 0,
    })

    result_events = [item for item in emitted if item[0] == "trade_result"]
    assert len(result_events) == 1
    assert result_events[0][1]["contract_id"] == 9191
    assert result_events[0][1]["action"] == "ASIANS_DOWN"
    assert result_events[0][1]["pair_action"] == "ASIANS_DOWN"


def test_tick_ui_throttle_does_not_block_trade_result(monkeypatch):
    emitted = []

    class _Strategy:
        tick_count = 0
        risk_block_reason = None

        def on_tick(self, tick, digit):
            self.tick_count += 1

        def get_ui_payload(self):
            return {"tick_count": self.tick_count}

        def on_contract(self, contract, settled_balance):
            self.contract = contract
            self.balance = settled_balance

        def get_last_trade_entry(self):
            return {"result": "WIN", "profit": 0.21}

    state = {
        "current_symbol": "R_10",
        "human_symbol": "R_10",
        "active_profile": "KOOLKID",
        "ws_connected": True,
        "strategies": {"KOOLKID": _Strategy()},
        "contract_meta": {
            "888": {
                "profile": "KOOLKID",
                "type": "OVER",
                "barrier": 1,
                "stake": 0.35,
                "symbol": "R_10",
                "duration": 1,
                "duration_unit": "t",
            }
        },
        "processed_contract_ids": set(),
        "balance": 100.0,
        "last_known_trade_balance": 100.0,
        "local_balance_adjustment": 0.0,
        "profile_budgets": server._new_profile_budget_map(),
        "bot_auto_close_timers": {},
    }
    monkeypatch.setattr(server, "clients", {"cid-throttle": state})
    monkeypatch.setattr(server.socketio, "emit", lambda event, payload=None, room=None: emitted.append((event, payload, room)))
    monkeypatch.setattr(server, "run_auto_trade", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_maybe_refresh_koolkid_testtrial_quotes", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_run_unchain_hybrid", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_run_unchain_primordial_blue", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_run_unchain_ai_auto_trade", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_run_unchain_auto_both", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_run_unchain_directional_auto_trade", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_run_unchain_koolkid_hl", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_run_unchain_koolkid_both", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_run_ntt_auto_both", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_run_ntt_koolkid_hl", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_run_ntt_koolkid_both", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "send_stats_update", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_emit_balance_payload", lambda *_args, **_kwargs: None)

    server.process_tick("cid-throttle", {"symbol": "R_10", "quote": 123.45, "pip_size": 2})
    server.process_tick("cid-throttle", {"symbol": "R_10", "quote": 123.46, "pip_size": 2})
    server.process_contract("cid-throttle", {
        "contract_id": 888,
        "is_sold": 1,
        "status": "won",
        "profit": 0.21,
        "sell_price": 0.56,
    })

    assert len([item for item in emitted if item[0] == "tick"]) == 1
    assert len([item for item in emitted if item[0] == "digit_analysis"]) == 1
    assert len([item for item in emitted if item[0] == "trade_result"]) == 1


def test_send_buy_allows_authorized_stale_transport_and_sends_trade(monkeypatch):
    emitted = []
    reconnects = []
    ws = _DummyWs()
    state = {
        "ws_nonce": "nonce-1",
        "ws_connected": True,
        "ws_transport_connected": True,
        "ws_last_message_at": time.time() - (server.DERIV_WS_STALE_TIMEOUT_SEC + 5),
        "ws": ws,
        "api_token": "token",
        "ws_reconnect_pending": False,
        "ws_stop_event": threading.Event(),
        "req_meta": {},
        "balance": 100.0,
        "strategies": {"KOOLKID": None},
        "loginid": "CR123",
        "active_profile": "KOOLKID",
        "profile_budgets": server._new_profile_budget_map(),
        "contract_meta": {},
        "bot_auto_close_timers": {},
    }
    monkeypatch.setattr(server, "clients", {"cid-stale": state})
    monkeypatch.setattr(server.socketio, "emit", lambda event, payload=None, room=None: emitted.append((event, payload, room)))
    monkeypatch.setattr(server, "_schedule_ws_reconnect", lambda cid, nonce, delay_sec=0.25: reconnects.append((cid, nonce, delay_sec)) or True)

    ok, msg = server.send_buy("cid-stale", "OVER", 1.0, "R_10", 5)

    assert ok is True
    assert msg == "Trade sent"
    assert state["ws_connected"] is True
    assert ws.closed is False
    assert reconnects == []
    assert any(message.get("buy") == 1 for message in ws.messages)


def test_api_connection_status_keeps_authorized_stale_socket_trade_ready(monkeypatch):
    reconnects = []
    emitted = []
    ws = _DummyWs()
    state = {
        "ws_nonce": 2,
        "ws_connected": True,
        "ws_transport_connected": True,
        "ws_last_message_at": time.time() - (server.DERIV_WS_STALE_TIMEOUT_SEC + 5),
        "ws": ws,
        "api_token": "token",
        "ws_reconnect_pending": False,
        "ws_stop_event": threading.Event(),
        "balance": 55.0,
        "profile_budgets": server._new_profile_budget_map(),
        "active_profile": "KOOLKID",
        "session_start_balance": None,
        "loginid": "CR456",
    }
    monkeypatch.setattr(server, "login_required", lambda: True)
    monkeypatch.setattr(server, "get_client_state", lambda: ("cid-status", state))
    monkeypatch.setattr(server.socketio, "emit", lambda event, payload=None, room=None: emitted.append((event, payload, room)))
    monkeypatch.setattr(server, "_schedule_ws_reconnect", lambda cid, nonce, delay_sec=0.25: reconnects.append((cid, nonce, delay_sec)) or True)

    with server.app.test_request_context("/api_connection_status"):
        response = server.api_connection_status()

    data = response.get_json()
    assert data["connected"] is True
    assert data["can_trade"] is True
    assert data["authorized"] is True
    assert data["ws_stale"] is True
    assert state["ws_connected"] is True
    assert reconnects == []
    assert emitted == []


def test_api_connection_status_reconnects_when_authorize_stays_pending_too_long(monkeypatch):
    reconnects = []
    emitted = []
    ws = _DummyWs()
    state = {
        "ws_nonce": 3,
        "ws_connected": False,
        "ws_transport_connected": True,
        "ws_connect_started_at": time.time() - 10,
        "ws_authorize_deadline_at": time.time() - 1,
        "ws_last_message_at": time.time(),
        "ws": ws,
        "api_token": "token",
        "ws_reconnect_pending": False,
        "ws_stop_event": threading.Event(),
        "balance": 55.0,
        "profile_budgets": server._new_profile_budget_map(),
        "active_profile": "KOOLKID",
        "session_start_balance": None,
        "loginid": "UNKNOWN",
    }
    monkeypatch.setattr(server, "login_required", lambda: True)
    monkeypatch.setattr(server, "get_client_state", lambda: ("cid-auth", state))
    monkeypatch.setattr(server.socketio, "emit", lambda event, payload=None, room=None: emitted.append((event, payload, room)))
    monkeypatch.setattr(server, "_schedule_ws_reconnect", lambda cid, nonce, delay_sec=0.25: reconnects.append((cid, nonce, delay_sec)) or True)

    with server.app.test_request_context("/api_connection_status"):
        response = server.api_connection_status()

    data = response.get_json()
    assert data["connected"] is False
    assert state["ws_transport_connected"] is False
    assert ws.closed is True
    assert reconnects == [("cid-auth", 3, 0.25)]
    assert any(event == "connection_status" and payload.get("connected") is False for event, payload, _room in emitted)


def test_batch_trade_sleep_seconds_gives_turbo_a_much_faster_lane():
    normal = server._batch_trade_sleep_seconds({}, 0.04)
    turbo = server._batch_trade_sleep_seconds({"turbo": True}, 0.04)
    same_tick = server._batch_trade_sleep_seconds({"same_tick": True}, 0.04)

    assert normal == 0.04
    assert turbo == 0.002
    assert turbo < normal
    assert same_tick == 0.0


def test_ensure_trade_socket_ready_skips_reconnect_during_tick_warmup(monkeypatch):
    now = 1000.0
    marked = []
    ws = _DummyWs()
    state = {
        "ws_connected": True,
        "ws_transport_connected": True,
        "ws": ws,
        "api_token": "token",
        "current_symbol": "R_10",
        "human_symbol": "R_10",
        "ws_last_message_at": now - 200.0,
        "tick_stream_warmup_until": {"R_10": now + 6.0},
        "tick_stream_warmup_reason": {"R_10": "market_switch"},
        "tick_stream_recovering_symbols": {},
        "tick_subscribe_sent_at": {},
        "tick_resubscribe_attempted_at": {},
    }
    monkeypatch.setattr(server.time, "time", lambda: now)
    monkeypatch.setattr(server, "_mark_ws_unhealthy_and_reconnect", lambda *args, **kwargs: marked.append((args, kwargs)))

    ready, ready_msg = server._ensure_trade_socket_ready("cid-warmup", state, emit_error=False)

    assert ready is True
    assert ready_msg is None
    assert marked == []


def test_human_manual_contract_batch_does_not_force_reconnect_on_nonfatal_pair_send_error(monkeypatch):
    class _FlakyWs:
        def __init__(self):
            self.messages = []
            self.calls = 0

        def send(self, payload):
            self.calls += 1
            if self.calls >= 2:
                raise RuntimeError("temporary send rejected")
            self.messages.append(json.loads(payload))

    req_ids = iter([7000, 7001, 7002])
    marked = []
    released = []
    sleeps = []
    ws = _FlakyWs()
    state = {
        "ws_connected": True,
        "ws_transport_connected": True,
        "ws": ws,
        "req_meta": {},
        "strategies": {},
        "contract_meta": {},
    }
    info = {
        "ASIANS_UP": {
            "available": True,
            "label": "Asians Up",
            "contract_type": "ASIANU",
            "duration_unit": "t",
            "min_duration": 2,
            "max_duration": 10,
        },
        "ASIANS_DOWN": {
            "available": True,
            "label": "Asians Down",
            "contract_type": "ASIAND",
            "duration_unit": "t",
            "min_duration": 2,
            "max_duration": 10,
        },
    }
    monkeypatch.setattr(server, "clients", {"cid-pair": state})
    monkeypatch.setattr(server, "_ensure_trade_socket_ready", lambda *_args, **_kwargs: (True, None))
    monkeypatch.setattr(server, "_fetch_human_manual_contracts_for_state", lambda *_args, **_kwargs: (info, None, "R_10"))
    monkeypatch.setattr(
        server,
        "_request_human_manual_proposal_quote",
        lambda *_args, contract_type=None, stake=None, **_kwargs: (
            {"id": f"proposal-{contract_type}", "ask_price": float(stake or 0.35)},
            None,
        ),
    )
    monkeypatch.setattr(server, "_reserve_profile_budget", lambda *_args, **_kwargs: (True, "", {"reservation": 1}))
    monkeypatch.setattr(server, "_release_profile_budget_reservation", lambda _state, reservation: released.append(reservation))
    monkeypatch.setattr(server, "_emit_balance_payload", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_mark_ws_unhealthy_and_reconnect", lambda *args, **kwargs: marked.append((args, kwargs)))
    monkeypatch.setattr(server.time, "sleep", lambda delay: sleeps.append(delay))
    monkeypatch.setattr(server, "_new_req_id", lambda: next(req_ids))

    ok, msg, placed = server.place_human_manual_contract_batch(
        "cid-pair",
        actions=[
            {"action": "ASIANS_UP", "stake": 0.35, "duration_ticks": 2},
            {"action": "ASIANS_DOWN", "stake": 0.35, "duration_ticks": 2},
        ],
    )

    assert ok is False
    assert len(placed) == 2
    assert "temporary send rejected" in msg
    assert len(ws.messages) == 1
    assert ws.messages[0]["buy"] == "proposal-ASIANU"
    assert sleeps == []
    assert marked == []
    assert released == [{"reservation": 1}, {"reservation": 1}]
