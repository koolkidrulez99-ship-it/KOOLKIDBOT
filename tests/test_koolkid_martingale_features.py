from pathlib import Path

import pytest

import server


ROOT = Path(__file__).resolve().parents[1]
KOOLKID_JS = (ROOT / "static" / "js" / "profiles" / "koolkid.js").read_text(encoding="utf-8")
KOOLKID_HTML = (ROOT / "static" / "components" / "koolkid.html").read_text(encoding="utf-8")


@pytest.fixture
def manual_trade_client(monkeypatch):
    calls = []
    monkeypatch.setattr(server, "login_required", lambda: True)
    monkeypatch.setattr(server, "get_client_state", lambda: ("test", {"current_symbol": "R_25"}))
    monkeypatch.setattr(server, "send_buy", lambda *args, **kwargs: (calls.append((args, kwargs)) or (True, "ok")))
    return server.app.test_client(), calls


@pytest.mark.parametrize(
    ("trade_type", "barrier"),
    [("UNDER", 0), ("DIGITUNDER", 0), ("OVER", 9), ("DIGITOVER", 9)],
)
def test_koolkid_martingale_rejects_unwinnable_digit_contracts(manual_trade_client, trade_type, barrier):
    client, calls = manual_trade_client
    response = client.post("/manual_trade", json={
        "type": trade_type,
        "barrier": barrier,
        "stake": 0.35,
        "mode": "koolkid_single_martingale",
    })
    assert response.status_code == 400
    assert response.get_json()["status"] == "error"
    assert calls == []


@pytest.mark.parametrize(("trade_type", "barrier"), [("OVER", 0), ("UNDER", 9), ("UNDER", 2), ("OVER", 7)])
def test_koolkid_martingale_accepts_valid_digit_contracts(manual_trade_client, trade_type, barrier):
    client, calls = manual_trade_client
    response = client.post("/manual_trade", json={
        "type": trade_type,
        "barrier": barrier,
        "stake": 0.35,
        "mode": "koolkid_single_martingale",
    })
    assert response.status_code == 200
    assert response.get_json()["status"] == "success"
    assert len(calls) == 1


@pytest.mark.parametrize(("trade_type", "barrier"), [("UNDER", 0), ("OVER", 9)])
def test_fast_koolkid_path_rejects_unwinnable_contract_before_buy(monkeypatch, trade_type, barrier):
    calls = []
    monkeypatch.setattr(server, "send_buy_with_profile", lambda *args, **kwargs: (calls.append((args, kwargs)) or (True, "ok")))
    result = server._handle_fast_profile_trade_payload("test", {"current_symbol": "R_25"}, {
        "profile": "KOOLKID",
        "type": trade_type,
        "barrier": barrier,
        "stake": 0.35,
        "mode": "koolkid_single_martingale_pair",
    })
    assert result["status"] == "error"
    assert calls == []


def test_koolkid_runtime_metadata_is_isolated_per_client_state():
    state_a = {}
    state_b = {}
    server._capture_koolkid_martingale_runtime(state_a, {
        "mode": "koolkid_single_martingale",
        "main_trade_action": "OVER_6",
        "action": "OVER_4",
        "recovery_trade_action": "OVER_4",
        "recovery_active": True,
        "cycle_attempt": 4,
        "logical_round_id": "round-a",
    })
    server._capture_koolkid_martingale_runtime(state_b, {
        "mode": "koolkid_single_martingale",
        "main_trade_action": "UNDER_3",
        "action": "UNDER_3",
        "logical_round_id": "round-b",
    })
    assert state_a["koolkid_martingale_runtime"]["recovery_active"] is True
    assert state_a["koolkid_martingale_runtime"]["main_trade_action"] == "OVER_6"
    assert state_b["koolkid_martingale_runtime"]["recovery_active"] is False
    assert state_b["koolkid_martingale_runtime"]["logical_round_id"] == "round-b"


def test_combined_round_is_declared_as_two_correlated_legs():
    assert '<option value="UNDER_2_OVER_7">UNDER 2 + OVER 7</option>' in KOOLKID_HTML
    block = KOOLKID_JS[KOOLKID_JS.index('if (compact === "UNDER_2_OVER_7")'):]
    block = block[:block.index('if (compact === "OVER_4_UNDER_5")')]
    assert 'combinedRound: true' in block
    assert block.count('{ action: "UNDER_2", type: "UNDER", barrier: 2') == 1
    assert block.count('{ action: "OVER_7", type: "OVER", barrier: 7') == 1


def test_over3_under6_pair_has_two_valid_correlated_legs():
    assert '<option value="OVER_3_UNDER_6">OVER 3 + UNDER 6</option>' in KOOLKID_HTML
    block = KOOLKID_JS[KOOLKID_JS.index('if (compact === "OVER_3_UNDER_6")'):]
    block = block[:block.index('if (compact === "OVER_3_OVER_6"')]
    assert block.count('{ action: "OVER_3", type: "OVER", barrier: 3') == 1
    assert block.count('{ action: "UNDER_6", type: "UNDER", barrier: 6') == 1
    assert 'settleTogether: true' in block


def test_pair_double_after_loss_waits_for_both_and_updates_each_leg_once():
    assert 'settings.independentPair || settings.pairDoubleAfterLoss' in KOOLKID_JS
    assert 'st.pendingSettled < Math.max(2, Number(st.pendingExpected) || 2)' in KOOLKID_JS
    assert 'st.pairSteps[legAction] = nextKoolkidLimitedMartingaleStep' in KOOLKID_JS
    assert 'st.pairSteps[legAction] = 1' in KOOLKID_JS


def test_new_pair_controls_are_persisted_and_available_to_everyone():
    assert 'pairDoubleAfterLoss: saved.pairDoubleAfterLoss === true' in KOOLKID_JS
    assert 'function canUseKoolkidSingleMartingale() {\n    return true;' in KOOLKID_JS
    assert 'id="koolkidPairDoubleAfterLossToggle"' in KOOLKID_HTML
    assert 'id="koolkidOver3PairMultiplier"' in KOOLKID_HTML
    assert 'id="koolkidUnder6PairMultiplier"' in KOOLKID_HTML


def test_combined_round_waits_for_both_and_uses_combined_profit_once():
    assert 'if (st.pendingSettled < expected)' in KOOLKID_JS
    assert 'const roundProfit = resolveKoolkidPairRoundProfit(pendingItems, settings);' in KOOLKID_JS
    assert 'const roundOutcome = roundProfit > 0 ? "WIN" : roundProfit < 0 ? "LOSS" : "BREAKEVEN";' in KOOLKID_JS
    combined = KOOLKID_JS[KOOLKID_JS.index('if (settings.combinedRound)'):]
    combined = combined[:combined.index('const pairRiskSettings')]
    assert combined.count('st.step = nextKoolkidLimitedMartingaleStep') == 1


def test_recovery_and_switch_configuration_is_persisted_but_runtime_is_not():
    assert 'koolkid.martingale.features.v1' in KOOLKID_JS
    saved = KOOLKID_JS[KOOLKID_JS.index('function saveKoolkidMartingaleFeatureConfig'):]
    saved = saved[:saved.index('function selectedKoolkidFeatureTrade')]
    assert 'recoveryActive' not in saved
    assert 'cycleAttempt' not in saved
    assert 'recoveryEnabled' in KOOLKID_JS
    assert 'switchAfterWinEnabled' in KOOLKID_JS


def test_recovery_priority_and_switch_after_win_guards_are_explicit():
    assert 'if (!wasRecoveryTrade) applyKoolkidSwitchAfterNormalWin(st);' in KOOLKID_JS
    assert 'st.cycleAttempt >= koolkidMartingaleConfig.recoveryAfter' in KOOLKID_JS
    assert 'if (!koolkidMartingaleConfig.recoveryEnabled || !st.recoveryActive) return settings;' in KOOLKID_JS


def test_switch_after_win_alternates_between_original_and_selected_trade():
    assert 'switchOriginalAction: "UNDER_3"' in KOOLKID_JS
    assert 'switchAlternateActive: false' in KOOLKID_JS
    assert 'const next = st.switchAlternateActive ? original : alternate;' in KOOLKID_JS
    assert 'st.switchAlternateActive = !st.switchAlternateActive;' in KOOLKID_JS
    assert 'resetKoolkidSwitchRotation(st, st.action);' in KOOLKID_JS


def test_switch_every_trade_reuses_digit_picker_and_persists_selection():
    assert 'id="koolkidSwitchEveryTradeToggle"' in KOOLKID_HTML
    assert 'id="koolkidSwitchEveryTradeControls"' in KOOLKID_HTML
    assert "openKoolkidDigitTradePicker('everyTrade')" in KOOLKID_HTML
    assert 'switchEveryTradeEnabled: saved.switchEveryTradeEnabled === true' in KOOLKID_JS
    assert 'everyTradeType: everyTrade ? everyTrade.contractType : defaults.everyTradeType' in KOOLKID_JS
    assert 'everyTradeBarrier: everyTrade ? everyTrade.barrier : defaults.everyTradeBarrier' in KOOLKID_JS


def test_switch_every_trade_alternates_after_results_without_resetting_loss_step():
    assert 'function applyKoolkidSwitchEveryTrade(st)' in KOOLKID_JS
    assert 'const alternate = selectedKoolkidFeatureTrade("everyTrade");' in KOOLKID_JS
    assert 'if (!wasRecoveryTrade && !koolkidMartingaleConfig.switchEveryTradeEnabled) applyKoolkidSwitchAfterNormalWin(st);' in KOOLKID_JS
    loss_start = KOOLKID_JS.index('} else if (outcome === "LOSS")', KOOLKID_JS.index('if (st.pendingContractId'))
    loss_block = KOOLKID_JS[loss_start:KOOLKID_JS.index('updateKoolkidSingleMartingalePanel();', loss_start)]
    assert 'applyKoolkidSwitchEveryTrade(st);' in loss_block
    assert loss_block.index('applyKoolkidSwitchEveryTrade(st);') < loss_block.index('st.step = nextKoolkidLimitedMartingaleStep')
    assert 'riskSettings.active || koolkidMartingaleConfig.switchEveryTradeEnabled' in KOOLKID_JS


def test_switch_every_trade_respects_recovery_and_conflicting_switch_mode():
    assert 'if (!koolkidMartingaleConfig.switchEveryTradeEnabled || st.recoveryActive) return false;' in KOOLKID_JS
    assert 'if (koolkidMartingaleConfig.switchAfterWinEnabled) koolkidMartingaleConfig.switchEveryTradeEnabled = false;' in KOOLKID_JS
    assert 'koolkidMartingaleConfig.switchAfterWinEnabled = false;' in KOOLKID_JS


def test_picker_has_all_digits_and_disables_under_zero_and_over_nine():
    assert 'for (let digit = 0; digit <= 9; digit += 1)' in KOOLKID_JS
    assert 'disabled: digit === 0' in KOOLKID_JS
    assert 'disabled: digit === 9' in KOOLKID_JS
    assert 'contractType === "DIGITOVER" && digit <= 8' in KOOLKID_JS
    assert 'contractType === "DIGITUNDER" && digit >= 1' in KOOLKID_JS


def test_stop_and_profile_deactivation_invalidate_pending_requests():
    assert KOOLKID_JS.count('st.requestGeneration = Number(st.requestGeneration || 0) + 1;') >= 3
    assert 'if (st.requestGeneration !== requestGeneration || st.stopRequested) return;' in KOOLKID_JS
    assert 'clearKoolkidSingleMartingalePending();\n    resetKoolkidRecoveryRuntime(mgState, mgState.action);' in KOOLKID_JS
