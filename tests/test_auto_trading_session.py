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


def test_start_auto_session_uses_profile_market_allowlist():
    state = {"strategies": {}}
    session = auto_session.start_auto_session(
        state,
        "JOKERJOE",
        budget=100,
        sl=10,
        tp=20,
    )

    assert session["market_order"] == list(auto_session.SEQVIX_JOKERJOE_SLOW_MARKETS)
    assert set(session["markets"].keys()) == set(auto_session.SEQVIX_JOKERJOE_SLOW_MARKETS)


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
    assert "UNCHAIN_DIRECTIONAL_AUTO" in session["allowed_strategy_ids"]


def test_compute_session_stake_uses_ramp_and_confidence_sizing():
    session = auto_session.start_auto_session({"strategies": {}}, "KOOLKID", budget=100, sl=0, tp=0)

    assert auto_session.compute_session_stake(session, live_balance=100.0, leg_count=1) == 0.35

    session["trade_index"] = 1
    assert auto_session.compute_session_stake(session, live_balance=100.0, leg_count=1) == 10.0

    session["trade_index"] = 2
    assert auto_session.compute_session_stake(session, live_balance=100.0, leg_count=1) == 20.0

    session["trade_index"] = 3
    assert auto_session.compute_session_stake(session, live_balance=100.0, leg_count=1, confidence=65.0) == 10.0
    assert auto_session.compute_session_stake(session, live_balance=100.0, leg_count=1, confidence=75.0) == 15.0
    assert auto_session.compute_session_stake(session, live_balance=100.0, leg_count=1, confidence=85.0) == 25.0
    assert auto_session.compute_session_stake(session, live_balance=100.0, leg_count=1, confidence=95.0) == 40.0


def test_compute_session_stake_budget_states_scale_down_risk():
    session = auto_session.start_auto_session({"strategies": {}}, "KOOLKID", budget=100, sl=0, tp=0)
    session["trade_index"] = 3
    session["budget_used"] = 21.0
    auto_session._sync_session_totals(session)
    assert session["health_state"] == "CAUTION"
    assert auto_session.compute_session_stake(session, live_balance=100.0, leg_count=1, confidence=85.0) == 16.79

    session["budget_used"] = 41.0
    auto_session._sync_session_totals(session)
    assert session["health_state"] == "BUDGET_RECOVERY"
    assert auto_session.compute_session_stake(session, live_balance=100.0, leg_count=1, confidence=85.0) == 8.85

    session["budget_used"] = 61.0
    auto_session._sync_session_totals(session)
    assert session["health_state"] == "CRITICAL"
    assert auto_session.compute_session_stake(session, live_balance=100.0, leg_count=1, confidence=85.0) == 3.9


def test_required_confidence_matches_budget_health_states_and_loss_response():
    session = auto_session.start_auto_session({"strategies": {}}, "KOOLKID", budget=100, sl=0, tp=0)

    assert auto_session._required_confidence(session) == 60.0

    session["budget_used"] = 21.0
    auto_session._sync_session_totals(session)
    assert auto_session._required_confidence(session) == 68.0

    session["budget_used"] = 41.0
    auto_session._sync_session_totals(session)
    assert auto_session._required_confidence(session) == 75.0

    session["budget_used"] = 61.0
    auto_session._sync_session_totals(session)
    assert auto_session._required_confidence(session) == 82.0

    session["budget_used"] = 0.0
    session["loss_streak"] = 1
    auto_session._sync_session_totals(session)
    assert auto_session._required_confidence(session) == 63.0

    session["loss_streak"] = 2
    auto_session._sync_session_totals(session)
    assert auto_session._required_confidence(session) == 75.0


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
    assert len(market["digits"]) >= auto_session.AUTO_SESSION_MIN_HISTORY


def test_budget_and_profit_stay_separate_after_wins_and_losses():
    state = {"strategies": {}}
    session = auto_session.start_auto_session(state, "KOOLKID", budget=100, sl=20, tp=40)
    token = session["token"]

    win_mode = f"AUTO_SESSION|{token}|B1|KOOLKID_MPULL|1|R_10"
    session["open_contracts"] = {"101": {"mode": win_mode}}
    auto_session.handle_auto_session_contract_settled(
        state,
        {"contract_id": "101", "profit": 30.0, "sell_price": 60.0},
        {"mode": win_mode, "profile": "KOOLKID", "stake": 30.0, "symbol": "R_10", "type": "OVER"},
    )

    loss_mode = f"AUTO_SESSION|{token}|B2|KOOLKID_MPULL|1|R_10"
    session["running"] = True
    session["open_contracts"] = {"102": {"mode": loss_mode}}
    auto_session.handle_auto_session_contract_settled(
        state,
        {"contract_id": "102", "profit": -10.0, "sell_price": 0.0},
        {"mode": loss_mode, "profile": "KOOLKID", "stake": 10.0, "symbol": "R_10", "type": "OVER"},
    )

    assert session["protected_profit"] == 30.0
    assert session["budget_used"] == 10.0
    assert session["remaining_budget"] == 90.0
    assert session["session_profit"] == 20.0


def test_jokerjoe_candidates_are_blocked_on_1s_markets():
    assert auto_session._candidate_allowed_on_market("JOKERJOE_MULTIG", "1HZ10V") is False
    assert auto_session._candidate_allowed_on_market("JOKERJOE_MULTIG", "R_75") is True
    assert auto_session._candidate_allowed_on_market("KOOLKID_MPULL", "1HZ10V") is True


def test_market_scan_batch_rotates_in_groups_of_five():
    state = {"strategies": {}}
    session = auto_session.start_auto_session(state, "KOOLKID", budget=100, sl=0, tp=0)
    first_batch = auto_session._scan_batch_symbols(session)
    auto_session._maybe_rotate_scan_batch(
        session,
        now_ts=float(session.get("last_scan_rotate_at", 0.0) or 0.0) + auto_session.AUTO_SESSION_SCAN_ROTATE_SEC + 0.5,
    )
    second_batch = auto_session._scan_batch_symbols(session)

    assert len(first_batch) == min(auto_session.AUTO_SESSION_SCAN_BATCH_SIZE, len(auto_session.AUTO_SESSION_MARKETS))
    assert len(second_batch) == len(first_batch)
    assert first_batch != second_batch


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


def test_auto_session_resume_keeps_profit_history_until_clear():
    state = {"strategies": {}}
    auto_session.ensure_auto_session_dashboard(state)["stats"] = {
        "wins": 3,
        "losses": 1,
        "total_trades": 4,
        "winrate": 75.0,
        "net_pnl": 9.0,
    }

    session = auto_session.start_auto_session(state, "KOOLKID", budget=15, sl=15, tp=10)

    assert session["running"] is True
    assert session["session_profit"] == 9.0
    assert session["wins"] == 3
    assert session["losses"] == 1
    assert session["trade_index"] == 4

    token = session["token"]
    mode = f"AUTO_SESSION|{token}|B1|KOOLKID_MPULL|1|R_10"
    session["open_contracts"] = {"123": {"mode": mode}}

    auto_session.handle_auto_session_contract_settled(
        state,
        {"contract_id": "123", "profit": 1.0, "sell_price": 2.0},
        {"mode": mode, "profile": "KOOLKID", "stake": 1.0, "symbol": "R_10", "type": "OVER"},
    )

    assert session["running"] is False
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
    assert plan["actions"][0]["stake"] == 40.0


def test_process_auto_session_tick_recovers_from_stale_pending_request(monkeypatch):
    state = {"strategies": {}, "balance": 100.0}
    session = auto_session.start_auto_session(state, "KOOLKID", budget=100, sl=0, tp=0)
    session["market_order"] = ["R_10"]
    session["markets"] = {"R_10": auto_session._make_market_runtime("R_10", ["KOOLKID_MPULL"])}

    stale_mode = f"AUTO_SESSION|{session['token']}|B1|KOOLKID_MPULL|1|R_10"
    session["busy"] = True
    session["pending_modes"] = {stale_mode}
    session["pending_batches"] = {
        "B1": {
            "batch_id": "B1",
            "market": "R_10",
            "label": "KOOLKID - MPull",
            "confidence": 82.0,
            "expected": 1,
            "failed": 0,
            "created_at": 1.0,
            "updated_at": 1.0,
            "modes": [stale_mode],
        }
    }
    session["last_action_at"] = 1.0

    def fake_select_best_execution_plan(_state, preview_only=False):
        if preview_only:
            return {
                "market": "R_10",
                "label": "KOOLKID - MPull",
                "confidence": 82.0,
                "actions": [{"profile": "KOOLKID", "strategy_id": "KOOLKID_MPULL", "kind": "digit", "contract_type": "OVER", "barrier": 4, "symbol": "R_10", "duration": 1, "duration_unit": "t", "stake": 10.0}],
            }
        return {
            "market": "R_10",
            "label": "KOOLKID - MPull",
            "confidence": 82.0,
            "actions": [{"profile": "KOOLKID", "strategy_id": "KOOLKID_MPULL", "kind": "digit", "contract_type": "OVER", "barrier": 4, "symbol": "R_10", "duration": 1, "duration_unit": "t", "stake": 10.0}],
            "strategy_ids": ["KOOLKID_MPULL"],
        }

    monkeypatch.setattr(auto_session, "_select_best_execution_plan", fake_select_best_execution_plan)
    monkeypatch.setattr(auto_session.time, "time", lambda: auto_session.AUTO_SESSION_PENDING_TIMEOUT_SEC + 50.0)

    plan = auto_session.process_auto_session_tick(
        state,
        {"symbol": "R_10", "quote": 100.04, "epoch": 1004},
        4,
    )

    assert plan is not None
    assert session["pending_modes"]
    assert session["busy"] is True
    assert "resumed scanning" in session["events"][-2]["text"].lower()


def test_three_losses_trigger_cooldown_and_recovery_rules(monkeypatch):
    state = {"strategies": {}}
    session = auto_session.start_auto_session(state, "KOOLKID", budget=100, sl=0, tp=0)
    token = session["token"]
    base_ts = 500.0
    monkeypatch.setattr(auto_session.time, "time", lambda: base_ts)

    for idx in range(1, 4):
        mode = f"AUTO_SESSION|{token}|B{idx}|KOOLKID_MPULL|1|R_10"
        session["running"] = True
        session["open_contracts"] = {str(100 + idx): {"mode": mode}}
        auto_session.handle_auto_session_contract_settled(
            state,
            {"contract_id": str(100 + idx), "profit": -5.0, "sell_price": 0.0},
            {"mode": mode, "profile": "KOOLKID", "stake": 5.0, "symbol": "R_10", "type": "OVER"},
        )

    assert session["loss_streak"] == 3
    assert session["recovery_mode"] is True
    assert session["cooldown_until"] == base_ts + auto_session.AUTO_SESSION_THREE_LOSS_COOLDOWN_SEC


def test_final_confidence_score_uses_45_45_10_weighting():
    assert auto_session._final_confidence_score(70.0, 80.0, 50.0) == 72.5


def test_unchain_expected_profit_preview_uses_single_net_expected_for_both(monkeypatch):
    quotes = {
        "HIGHER": ({"ask_price": 20.0, "payout": 42.0, "barrier": "+0.12"}, None),
        "LOWER": ({"ask_price": 20.0, "payout": 38.0, "barrier": "-0.12"}, None),
    }

    def fake_quote(state, side, stake, symbol, barrier, duration, duration_unit):
        return quotes[side]

    monkeypatch.setattr(server, "_request_unchain_proposal_quote", fake_quote)

    preview = server._build_unchain_expected_profit_preview(
        {},
        symbol="R_10",
        higher_stake=20,
        lower_stake=20,
        higher_barrier="+0.12",
        lower_barrier="-0.12",
        duration=5,
        duration_unit="t",
    )

    assert preview["both"]["higher_profit"] == 22.0
    assert preview["both"]["lower_profit"] == 18.0
    assert preview["both"]["net_profit"] == 2.0


def test_dual_profile_mode_can_trade_from_shared_market_consensus(monkeypatch):
    state = {"strategies": {}, "balance": 100.0}
    session = auto_session.start_auto_session(state, "KOOLKID", "JOKERJOE", budget=100, sl=0, tp=0)
    session["market_order"] = ["R_10"]
    session["allowed_strategy_ids"] = ["KOOLKID_MPULL", "JOKERJOE_MULTIG"]
    session["markets"] = {"R_10": auto_session._make_market_runtime("R_10", session["allowed_strategy_ids"])}
    session["markets"]["R_10"]["ready"] = True

    def fake_eval(strategy_id, runtime, market, state_obj, per_trade_stake, preview_only=False):
        if strategy_id == "KOOLKID_MPULL":
            return {
                "profile": "KOOLKID",
                "strategy_id": strategy_id,
                "label": auto_session._CANDIDATE_DEFS[strategy_id]["label"],
                "market": market["symbol"],
                "confidence": 58.0,
                "signal": {"type": "OVER", "barrier": 4, "duration": 1, "duration_unit": "t", "confidence": 58.0},
            }
        if strategy_id == "JOKERJOE_MULTIG":
            return {
                "profile": "JOKERJOE",
                "strategy_id": strategy_id,
                "label": auto_session._CANDIDATE_DEFS[strategy_id]["label"],
                "market": market["symbol"],
                "confidence": 59.0,
                "signal": {"type": "DIFFERS", "barrier": 4, "duration": 1, "duration_unit": "t", "confidence": 59.0},
            }
        return None

    monkeypatch.setattr(auto_session, "_evaluate_candidate", fake_eval)

    plan = auto_session._select_best_execution_plan(state)

    assert plan is not None
    assert len(plan["actions"]) == 1
    assert len(plan["strategy_ids"]) == 2
    assert plan["confidence"] >= 60.0
    assert "dual confirm" in plan["label"].lower()


def test_dual_profile_mode_rotates_away_from_last_profile_when_close(monkeypatch):
    state = {"strategies": {}, "balance": 100.0}
    session = auto_session.start_auto_session(state, "KOOLKID", "JOKERJOE", budget=100, sl=0, tp=0)
    session["market_order"] = ["R_10"]
    session["allowed_strategy_ids"] = ["KOOLKID_MPULL", "JOKERJOE_MULTIG"]
    session["markets"] = {"R_10": auto_session._make_market_runtime("R_10", session["allowed_strategy_ids"])}
    session["markets"]["R_10"]["ready"] = True
    session["last_dual_profile"] = "KOOLKID"

    def fake_eval(strategy_id, runtime, market, state_obj, per_trade_stake, preview_only=False):
        if strategy_id == "KOOLKID_MPULL":
            return {
                "profile": "KOOLKID",
                "strategy_id": strategy_id,
                "label": auto_session._CANDIDATE_DEFS[strategy_id]["label"],
                "market": market["symbol"],
                "confidence": 61.0,
                "signal": {"type": "OVER", "barrier": 4, "duration": 1, "duration_unit": "t", "confidence": 61.0},
            }
        if strategy_id == "JOKERJOE_MULTIG":
            return {
                "profile": "JOKERJOE",
                "strategy_id": strategy_id,
                "label": auto_session._CANDIDATE_DEFS[strategy_id]["label"],
                "market": market["symbol"],
                "confidence": 60.0,
                "signal": {"type": "DIFFERS", "barrier": 4, "duration": 1, "duration_unit": "t", "confidence": 60.0},
            }
        return None

    monkeypatch.setattr(auto_session, "_evaluate_candidate", fake_eval)

    plan = auto_session._select_best_execution_plan(state)

    assert plan is not None
    assert plan["actions"][0]["profile"] == "JOKERJOE"
    assert "dual confirm" in plan["label"].lower()


def test_human_profile_candidate_can_build_session_plan_without_consuming_preview(monkeypatch):
    state = {"strategies": {}, "balance": 100.0}
    session = auto_session.start_auto_session(state, "HUMAN", budget=100, sl=0, tp=0)
    session["market_order"] = ["R_10"]
    session["allowed_strategy_ids"] = ["HUMAN_RF"]
    session["markets"] = {"R_10": auto_session._make_market_runtime("R_10", ["HUMAN_RF"])}
    session["markets"]["R_10"]["ready"] = True

    class DummyHuman:
        rf_duration_ticks = 5
        stake = 1.0
        rf_conf_threshold = 70.0

        def get_human_rf_payload(self):
            return {
                "signal": "TAKE NOW",
                "trade_direction": "RISE",
                "confidence": 82.0,
                "cooldown_sec": 0.0,
                "reason": "Clean trend",
            }

        def build_human_rf_trade_signal(self, force_direction=None, require_threshold=True):
            return {
                "direction": "RISE",
                "contract_type": "CALL",
                "stake": 1.0,
                "duration": 5,
                "duration_unit": "t",
                "mode": "human_rf",
                "profile": "HUMAN",
            }

    runtime = session["markets"]["R_10"]["candidates"]["HUMAN_RF"]
    runtime["strategy"] = DummyHuman()

    preview_plan = auto_session._select_best_execution_plan(state, preview_only=True)
    live_plan = auto_session._select_best_execution_plan(state, preview_only=False)

    assert preview_plan is not None
    assert live_plan is not None
    assert live_plan["actions"][0]["profile"] == "HUMAN"
    assert live_plan["confidence"] >= 60.0


def test_unchain_profile_candidate_accepts_text_barrier_and_builds_plan(monkeypatch):
    state = {"strategies": {}, "balance": 100.0}
    session = auto_session.start_auto_session(state, "UNCHAIN", budget=100, sl=0, tp=0)
    session["market_order"] = ["R_10"]
    session["allowed_strategy_ids"] = ["UNCHAIN_HIGHER"]
    session["markets"] = {"R_10": auto_session._make_market_runtime("R_10", ["UNCHAIN_HIGHER"])}
    session["markets"]["R_10"]["ready"] = True

    def fake_eval(strategy_id, runtime, market, state_obj, per_trade_stake, preview_only=False):
        return {
            "profile": "UNCHAIN",
            "strategy_id": strategy_id,
            "label": auto_session._CANDIDATE_DEFS[strategy_id]["label"],
            "market": market["symbol"],
            "confidence": 72.0,
            "signal": {
                "type": "HIGHER",
                "barrier": "+0.17",
                "duration": 5,
                "duration_unit": "t",
                "confidence": 72.0,
            },
        }

    monkeypatch.setattr(auto_session, "_evaluate_candidate", fake_eval)

    plan = auto_session._select_best_execution_plan(state)

    assert plan is not None
    assert plan["actions"][0]["profile"] == "UNCHAIN"
    assert plan["actions"][0]["barrier"] == "+0.17"


def test_unchain_directional_auto_candidate_uses_saved_side_and_barrier():
    state = {
        "unchain_hl": {
            "directional_auto_side": "HIGHER",
            "directional_auto_barrier": "-0.12",
            "duration": 4,
            "duration_unit": "t",
        }
    }
    market = {
        "prices": [100.00, 100.02, 100.05, 100.09, 100.14, 100.20, 100.27, 100.35, 100.44, 100.54],
        "epochs": list(range(10)),
    }

    signal = auto_session._build_unchain_directional_signal(state, market)

    assert signal is not None
    assert signal["type"] == "HIGHER"
    assert signal["barrier"] == "+0.12"
    assert signal["duration"] == 4
    assert signal["duration_unit"] == "t"
    assert signal["confidence"] >= 60.0


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
    session_state = auto_session.ensure_auto_session_state(state)
    session_state["running"] = False
    session_state["session_profit"] = 1.0
    session_state["wins"] = 1
    session_state["losses"] = 0
    session_state["trade_index"] = 1
    session_state["button_stats"] = {"KOOLKID_MPULL": {"wins": 1}}
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
    assert state["auto_session"]["session_profit"] == 0.0
    assert state["auto_session"]["wins"] == 0
    assert state["auto_session"]["trade_index"] == 0
    assert state["auto_session"]["button_stats"] == {}

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
