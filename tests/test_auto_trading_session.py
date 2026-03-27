import server
from strategies import auto_session


class DummyWS:
    def __init__(self):
        self.sent = []

    def send(self, payload):
        self.sent.append(payload)


def test_start_auto_session_clamps_budget_and_builds_profile_button_pool():
    state = {"strategies": {}}
    session = auto_session.start_auto_session(
        state,
        "KOOLKID",
        budget=5000,
        sl=25,
        tp=50,
    )

    assert session["running"] is True
    assert session["selected_strategy_ids"] == ["KOOLKID"]
    assert session["budget"] == 2000.0
    assert session["remaining_budget"] == 2000.0
    assert session["current_stake"] == 0.35
    assert "KOOLKID_MPULL" in session["allowed_strategy_ids"]
    assert "KOOLKID_SEQVIX" in session["allowed_strategy_ids"]
    assert len(session["markets"]) == len(auto_session.AUTO_SESSION_MARKETS)
    assert "KOOLKID_MPULL" in session["markets"]["R_10"]["candidates"]


def test_auto_session_catalog_returns_profiles():
    catalog = auto_session.get_auto_session_catalog()
    catalog_ids = {item["id"] for item in catalog}

    assert {"KOOLKID", "JOKERJOE", "HUMAN", "UNCHAIN"}.issubset(catalog_ids)
    assert all(int(item.get("button_count", 0) or 0) >= 1 for item in catalog)


def test_start_auto_session_can_build_unchain_profile_pool():
    state = {"strategies": {}}
    session = auto_session.start_auto_session(state, "UNCHAIN", budget=50, sl=10, tp=15)

    assert session["selected_strategy_ids"] == ["UNCHAIN"]
    assert "UNCHAIN_HIGHER" in session["allowed_strategy_ids"]
    assert "UNCHAIN_LOWER" in session["allowed_strategy_ids"]


def test_compute_session_stake_uses_ramp_and_confidence_sizing():
    session = auto_session.start_auto_session({"strategies": {}}, "KOOLKID", budget=100, sl=0, tp=0)

    assert auto_session.compute_session_stake(session, live_balance=100.0, leg_count=1) == 0.35

    session["trade_index"] = 1
    assert auto_session.compute_session_stake(session, live_balance=100.0, leg_count=1) == 10.0

    session["trade_index"] = 2
    assert auto_session.compute_session_stake(session, live_balance=100.0, leg_count=1) == 20.0

    session["trade_index"] = 3
    assert auto_session.compute_session_stake(session, live_balance=100.0, leg_count=1, confidence=65.0) == 10.0
    assert auto_session.compute_session_stake(session, live_balance=100.0, leg_count=1, confidence=85.0) == 35.0
    assert auto_session.compute_session_stake(session, live_balance=100.0, leg_count=1, confidence=95.0) == 100.0


def test_compute_session_stake_recovery_mode_stays_smaller():
    session = auto_session.start_auto_session({"strategies": {}}, "KOOLKID", budget=100, sl=0, tp=0)
    session["trade_index"] = 3
    session["recovery_mode"] = True

    assert auto_session.compute_session_stake(session, live_balance=100.0, leg_count=1, confidence=72.0) == 10.0
    assert auto_session.compute_session_stake(session, live_balance=100.0, leg_count=1, confidence=85.0) == 18.0


def test_feed_history_marks_market_ready():
    state = {"strategies": {}}
    session = auto_session.start_auto_session(state, "JOKERJOE", budget=100, sl=10, tp=20)
    session["allowed_strategy_ids"] = ["JOKERJOE_KIDGX"]
    session["markets"] = {sym: auto_session._make_market_runtime(sym, ["JOKERJOE_KIDGX"]) for sym in auto_session.AUTO_SESSION_MARKETS}
    prices = [100.00 + (idx % 10) / 100.0 for idx in range(120)]

    auto_session.feed_auto_session_history(state, "R_10", prices, lambda price: server.extract_last_decimal_digit(price, 2))

    market = session["markets"]["R_10"]
    assert market["ready"] is True
    assert "R_10" in session["seeded_markets"]
    assert len(market["digits"]) >= 100


def test_jokerjoe_seqvix_candidate_can_arm_and_build_plan():
    state = {"strategies": {}, "balance": 100.0}
    session = auto_session.start_auto_session(state, "JOKERJOE", budget=100, sl=10, tp=20)
    session["allowed_strategy_ids"] = ["JOKERJOE_SEQVIX"]
    session["markets"] = {sym: auto_session._make_market_runtime(sym, ["JOKERJOE_SEQVIX"]) for sym in auto_session.AUTO_SESSION_MARKETS}

    digits = ([0, 1, 2, 3, 4, 5, 6, 7, 8, 0] * 10)[:100]
    digits[-20:] = [0, 1, 2, 3, 4, 5, 6, 7, 8, 0, 1, 2, 3, 4, 5, 6, 7, 8, 0, 1]
    prices = [100.0 + (digit / 100.0) for digit in digits]

    auto_session.feed_auto_session_history(state, "R_10", prices, lambda price: server.extract_last_decimal_digit(price, 2))

    armed_plan = auto_session.process_auto_session_tick(
        state,
        {"symbol": "R_10", "quote": 100.09, "epoch": 1001, "pip_size": 2},
        9,
    )
    assert armed_plan is None

    plan = auto_session.process_auto_session_tick(
        state,
        {"symbol": "R_10", "quote": 100.03, "epoch": 1002, "pip_size": 2},
        3,
    )

    assert plan is not None
    assert plan["strategy_ids"] == ["JOKERJOE_SEQVIX"]
    assert plan["market"] == "R_10"
    assert len(plan["actions"]) == 1
    assert plan["actions"][0]["contract_type"] == "DIFFERS"
    assert plan["actions"][0]["barrier"] == 9


def test_session_stops_when_take_profit_is_hit():
    state = {"strategies": {}}
    session = auto_session.start_auto_session(state, "KOOLKID", budget=100, sl=10, tp=5)
    token = session["token"]
    mode = f"AUTO_SESSION|{token}|B1|KOOLKID_KIDRACKS|1|R_10"
    session["open_contracts"] = {"123": {"mode": mode}}

    auto_session.handle_auto_session_contract_settled(
        state,
        {"contract_id": "123", "profit": 6.0},
        {"mode": mode},
    )

    assert session["running"] is False
    assert session["status"] == "STOPPED"
    assert session["stop_reason"] == "Take profit reached"


def test_auto_session_dashboard_tracks_settled_trades_separately():
    state = {"strategies": {}}
    session = auto_session.start_auto_session(state, "KOOLKID", budget=100, sl=10, tp=20)
    token = session["token"]
    mode = f"AUTO_SESSION|{token}|B1|KOOLKID_MPULL|1|R_10"
    session["open_contracts"] = {"123": {"mode": mode}}

    auto_session.handle_auto_session_contract_settled(
        state,
        {"contract_id": "123", "profit": 2.5, "sell_price": 4.8},
        {
            "mode": mode,
            "profile": "KOOLKID",
            "type": "OVER",
            "barrier": 2,
            "stake": 2.3,
            "symbol": "R_10",
            "duration": 1,
            "duration_unit": "t",
        },
    )

    dashboard = auto_session.get_auto_session_dashboard_payload(state)

    assert dashboard["stats"]["total_trades"] == 1
    assert dashboard["stats"]["wins"] == 1
    assert dashboard["stats"]["net_pnl"] == 2.5
    assert dashboard["history"][0]["symbol"] == "R_10"
    assert dashboard["history"][0]["button_label"] == auto_session._CANDIDATE_DEFS["KOOLKID_MPULL"]["label"]
    assert dashboard["history"][0]["type"] == "OVER"
    assert dashboard["history"][0]["barrier"] == 2


def test_auto_session_plan_uses_one_trade_at_a_time_and_session_stake_only():
    state = {"strategies": {}, "balance": 100.0}
    session = auto_session.start_auto_session(state, "KOOLKID", budget=100, sl=0, tp=0)
    session["trade_index"] = 3
    result = {
        "profile": "KOOLKID",
        "strategy_id": "KOOLKID_AUTO_DOLLAR",
        "label": auto_session._CANDIDATE_DEFS["KOOLKID_AUTO_DOLLAR"]["label"],
        "market": "R_10",
        "confidence": 91.0,
        "signal": [
            {"type": "OVER", "barrier": 4, "duration": 1, "duration_unit": "t", "stake": 1.0},
            {"type": "UNDER", "barrier": 5, "duration": 1, "duration_unit": "t", "stake": 1.0},
        ],
    }

    plan = auto_session._build_plan_from_result(session, result, live_balance=100.0)

    assert plan is not None
    assert len(plan["actions"]) == 1
    assert plan["actions"][0]["stake"] == 100.0


def test_auto_session_clear_history_route_only_clears_session_dashboard(monkeypatch):
    cid = "auto-session-clear"
    server.clients.pop(cid, None)
    server.init_client(cid)
    state = server.clients[cid]
    auto_session.ensure_auto_session_dashboard(state)["history"] = [{"contract_id": "1", "profit": 1.0}]
    auto_session.ensure_auto_session_dashboard(state)["stats"] = {
        "wins": 1,
        "losses": 0,
        "total_trades": 1,
        "winrate": 100.0,
        "net_pnl": 1.0,
    }
    monkeypatch.setattr(server, "login_required", lambda: True)

    with server.app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = "tester"
            sess["role"] = "user"
            sess["client_id"] = cid
        response = client.post("/auto-session/clear-history")

    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["dashboard"]["stats"]["total_trades"] == 0
    assert payload["dashboard"]["history"] == []

    server.clients.pop(cid, None)


def test_auto_session_start_route_requires_connection(monkeypatch):
    cid = "auto-session-route"
    server.clients.pop(cid, None)
    server.init_client(cid)
    state = server.clients[cid]
    state["ws_connected"] = False
    state["ws"] = DummyWS()
    monkeypatch.setattr(server, "login_required", lambda: True)
    monkeypatch.setattr(server, "is_admin", lambda: False)

    with server.app.test_request_context(
        "/auto-session/start",
        method="POST",
        json={"strategy_1": "KOOLKID", "budget": 100, "sl": 10, "tp": 20},
    ):
        server.session["user"] = "tester"
        server.session["role"] = "user"
        server.session["client_id"] = cid
        response, status = server.auto_session_start()
        payload = response.get_json()

    assert status == 400
    assert payload["ok"] is False
    assert "Connect your API first" in payload["error"]

    server.clients.pop(cid, None)


def test_auto_session_start_route_rejects_budget_above_balance(monkeypatch):
    cid = "auto-session-balance-cap"
    server.clients.pop(cid, None)
    server.init_client(cid)
    state = server.clients[cid]
    state["ws_connected"] = True
    state["ws"] = DummyWS()
    state["balance"] = 12.5
    monkeypatch.setattr(server, "login_required", lambda: True)

    with server.app.test_request_context(
        "/auto-session/start",
        method="POST",
        json={"strategy_1": "KOOLKID", "budget": 20, "sl": 5, "tp": 10},
    ):
        server.session["user"] = "tester"
        server.session["role"] = "user"
        server.session["client_id"] = cid
        response, status = server.auto_session_start()
        payload = response.get_json()

    assert status == 400
    assert payload["ok"] is False
    assert "cannot be above your current balance" in payload["error"]

    server.clients.pop(cid, None)


def test_unchain_refresh_barriers_route_resets_current_market_defaults(monkeypatch):
    cid = "unchain-refresh"
    server.clients.pop(cid, None)
    server.init_client(cid)
    state = server.clients[cid]
    state["current_symbol"] = "R_75"
    u = server._ensure_unchain_hl_state(state)
    u["higher_barrier"] = "+0.01"
    u["lower_barrier"] = "-0.01"
    monkeypatch.setattr(server, "login_required", lambda: True)

    def fake_apply(target_state, symbol):
      un = server._ensure_unchain_hl_state(target_state)
      un["higher_barrier"] = "+0.17"
      un["lower_barrier"] = "-0.17"
      un["koolkid_higher_barrier"] = "+0.17"
      un["koolkid_lower_barrier"] = "-0.17"
      return True, "+0.17 / -0.17"

    monkeypatch.setattr(server, "_apply_unchain_market_default_barriers", fake_apply)

    with server.app.test_request_context("/unchain_refresh_barriers", method="POST"):
        server.session["user"] = "tester"
        server.session["role"] = "user"
        server.session["client_id"] = cid
        response = server.unchain_refresh_barriers_route()
        payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["payload"]["unchain"]["higher_barrier"] == "+0.17"
    assert payload["payload"]["unchain"]["lower_barrier"] == "-0.17"

    server.clients.pop(cid, None)
