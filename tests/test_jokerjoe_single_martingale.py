from pathlib import Path

import pytest

import server


ROOT = Path(__file__).resolve().parents[1]
JOKER_JS = (ROOT / "static" / "js" / "profiles" / "jokerjoe.js").read_text(encoding="utf-8")
JOKER_HTML = (ROOT / "static" / "components" / "jokerjoe.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("contract", ["MATCHES", "DIFFERS"])
@pytest.mark.parametrize("digit", range(10))
def test_jokerjoe_single_martingale_routes_all_match_diff_digits(monkeypatch, contract, digit):
    calls = []
    monkeypatch.setattr(
        server,
        "send_buy_with_profile",
        lambda *args, **kwargs: (calls.append((args, kwargs)) or (True, "Trade sent")),
    )
    result = server._handle_fast_profile_trade_payload(
        "test-client",
        {"active_profile": "JOKERJOE", "current_symbol": "R_25"},
        {
            "profile": "JOKERJOE",
            "type": contract,
            "barrier": digit,
            "stake": 0.35,
            "duration": 1,
            "duration_unit": "t",
            "mode": "jokerjoe_single_martingale",
        },
    )
    assert result["status"] == "success"
    assert calls[0][0][1] == "JOKERJOE"
    assert calls[0][0][2] == contract
    assert calls[0][0][5] == digit


def test_ui_has_direction_and_digit_controls_without_step_mode():
    assert 'id="jokerjoeSingleMartingaleContract"' in JOKER_HTML
    assert '<option value="DIFFERS">DIFFERS</option>' in JOKER_HTML
    assert '<option value="MATCHES">MATCHES</option>' in JOKER_HTML
    assert 'id="jokerjoeSingleMartingaleDigit"' in JOKER_HTML
    for digit in range(10):
        assert f'value="{digit}">DIGIT {digit}</option>' in JOKER_HTML
    panel = JOKER_HTML[JOKER_HTML.index('id="jokerjoeSingleMartingalePanel"'):]
    panel = panel[:panel.index('id="jokerjoeBatchMartingalePanel"')]
    assert "0.05" not in panel
    assert "STEP_005" not in JOKER_JS


def test_recovery_and_switch_pickers_only_store_digits():
    assert "recoveryDigit" in JOKER_JS
    assert "switchAfterWinDigit" in JOKER_JS
    assert "switchEveryTradeDigit" in JOKER_JS
    assert 'openJokerjoeDigitPicker(\'recovery\')' in JOKER_HTML
    assert 'openJokerjoeDigitPicker(\'win\')' in JOKER_HTML
    assert 'openJokerjoeDigitPicker(\'every\')' in JOKER_HTML
    assert "type: settings.contract, barrier: digit" in JOKER_JS


def test_martingale_waits_for_settlement_and_deduplicates_results():
    assert 'mode: "jokerjoe_single_martingale"' in JOKER_JS
    assert "if (st.inProgress || st.sessionWaiting || st.waitingForTicks) return;" in JOKER_JS
    assert "if (!id || st.settledIds[id]" in JOKER_JS
    assert "st.settledIds[id] = true;" in JOKER_JS
    assert "st.pendingContractId = String(id)" in JOKER_JS


def test_recovery_keeps_multiplier_cycle_and_has_priority_on_win():
    assert "st.step = nextJokerjoeMartingaleStep(st, settings);" in JOKER_JS
    assert "if (st.cycleAttempt >= settings.recoveryAfter) st.recoveryActive = true;" in JOKER_JS
    assert "const wasRecovery = st.pendingWasRecovery;" in JOKER_JS
    assert "if (!wasRecovery)" in JOKER_JS
    assert "st.currentDigit = st.originalDigit;" in JOKER_JS


def test_tp_sl_session_and_run_limit_are_present():
    assert 'id="jokerjoeSingleMartingaleTP"' in JOKER_HTML
    assert 'id="jokerjoeSingleMartingaleSL"' in JOKER_HTML
    assert 'id="jokerjoeSessionRunLimit"' in JOKER_HTML
    for value in range(1, 11):
        assert f'<option value="{value}">{value}</option>' in JOKER_HTML
    assert "st.sessionRunsCompleted >= settings.sessionRunLimit" in JOKER_JS
    assert "settings.stopLoss > 0 && st.sessionProfit <= -Math.abs(settings.stopLoss)" in JOKER_JS


def test_profile_deactivation_stops_only_jokerjoe_single_runtime():
    deactivate = JOKER_JS[JOKER_JS.index("async function onDeactivate()") :]
    deactivate = deactivate[: deactivate.index("window.toggleTurboJokerjoe")]
    assert 'stopJokerjoeSingleMartingale("Stopped on profile change", false);' in deactivate
    assert "removeJokerjoeMartingalePopups();" in deactivate
