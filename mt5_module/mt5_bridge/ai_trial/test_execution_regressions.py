import copy
import sys
from pathlib import Path

import pytest

BRIDGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BRIDGE))
sys.path.insert(0, str(BRIDGE.parent))

import hub_auth
import store
import ai_auto_select
from ai_trial import storage
from mt5_module.mt5_bridge import main


@pytest.fixture
def execution(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "state")
    monkeypatch.setattr(storage, "ROOT", tmp_path / "trial")
    token = hub_auth.set_workspace("ws_ai_regression")
    snapshot = {"account_login": 1001, "symbol": "XAUUSD", "decision": "BUY",
                "proposed_trade": {"direction": "BUY", "time": 123456, "entry": 2000, "sl": 1990, "tp": 2020}}
    monkeypatch.setattr(main, "_run_ai_trial_scan", lambda payload: copy.deepcopy(snapshot))
    monkeypatch.setattr(main, "_connected_ai_account", lambda *args, **kwargs: {"account_type": "demo"})
    fills = []

    def trade(payload):
        fills.append(payload)
        return {"retcode": 10009, "ticket": 42}

    monkeypatch.setattr(main, "trade", trade)
    yield snapshot, fills
    hub_auth.reset_workspace(token)


def test_stopped_apostle_scan_cannot_submit(execution):
    snapshot, fills = execution
    config = {"enabled": True, "account_login": 1001}
    store.update_state(lambda state: state.update(ai_auto_config={**config, "enabled": False}))
    with pytest.raises(main.HTTPException, match="automation stopped"):
        main._execute_apostle_snapshot(snapshot, .01, source="ai_auto_human_apostle", expected_config=config)
    assert fills == []


def test_apostle_revalidates_stored_signal(execution, monkeypatch):
    snapshot, fills = execution
    monkeypatch.setattr(main, "_run_ai_trial_scan", lambda payload: {**snapshot, "decision": "SCANNING", "proposed_trade": None})
    with pytest.raises(main.HTTPException, match="changed before execution"):
        main._execute_apostle_snapshot(snapshot, .01, source="ai_manual_human_apostle")
    assert fills == []


def test_unconfirmed_result_is_not_reported_as_fill_or_retried(execution, monkeypatch):
    snapshot, _ = execution
    monkeypatch.setattr(main, "trade", lambda payload: {"retcode": 10008, "order": 123})
    with pytest.raises(main.HTTPException, match="did not confirm"):
        main._execute_apostle_snapshot(snapshot, .01, source="ai_manual_human_apostle")
    with pytest.raises(main.HTTPException, match="already submitted"):
        main._execute_apostle_snapshot(snapshot, .01, source="ai_manual_human_apostle")


def test_same_signal_is_scoped_by_workspace(execution):
    snapshot, fills = execution
    main._execute_apostle_snapshot(snapshot, .01, source="ai_manual_human_apostle")
    token = hub_auth.set_workspace("ws_another_ai_user")
    try:
        assert not store.read_state().get("ai_signal_attempts")
        main._execute_apostle_snapshot(snapshot, .01, source="ai_manual_human_apostle")
    finally:
        hub_auth.reset_workspace(token)
    assert len(fills) == 2


@pytest.mark.parametrize("mode", [None, "garbage", -1, 3, 2.5, True])
def test_unknown_account_modes_fail_closed(mode, monkeypatch):
    monkeypatch.setattr(main.multi_account_client, "connected_by_login", lambda: {1: {"account_info": {"trade_mode": mode}}})
    for verify in (main._connected_ai_account, ai_auto_select._verify_execution_account):
        with pytest.raises(PermissionError, match="could not verify"):
            verify(1, allow_live=True)


@pytest.mark.parametrize("mode", [0, 2])
def test_readonly_account_cannot_execute_even_with_confirmation(mode, monkeypatch):
    monkeypatch.setattr(main.multi_account_client, "connected_by_login", lambda: {1: {"account_info": {"trade_mode": mode, "read_only": True}}})
    for verify in (main._connected_ai_account, ai_auto_select._verify_execution_account):
        with pytest.raises(PermissionError, match="read-only"):
            verify(1, allow_live=True)


@pytest.mark.parametrize("conflict", ["independent_bot", "position", "stopped"])
def test_auto_select_rechecks_conflicts_after_market_fetch(execution, monkeypatch, conflict):
    _, fills = execution
    config = {"enabled": True, "mode": "auto", "account_login": 1001}
    signal = {"valid": True, "signal_key": "signal-1"}
    snapshot = {"account_login": 1001, "symbol": "XAUUSD", "selected": {"bot_id": 1000, "decision": "APPROVE", "signal": signal}}
    monkeypatch.setattr(ai_auto_select, "_verify_execution_account", lambda *a, **kw: "demo")
    monkeypatch.setattr(ai_auto_select.native_runtime, "fetch_market_snapshot", lambda *a: ({"symbol_info": {}}, {}))
    class Signal:
        def to_dict(self): return signal
    monkeypatch.setattr(ai_auto_select, "evaluate", lambda *a: Signal())
    monkeypatch.setattr(ai_auto_select, "_bot_map", lambda: {1000: {"status": "running" if conflict == "independent_bot" else "stopped", "native_config": {"enabled": True}}})
    monkeypatch.setattr(ai_auto_select, "_positions", lambda login: [{"symbol": "XAUUSD", "comment": "KKN1001"}] if conflict == "position" else [])
    monkeypatch.setattr(ai_auto_select.native_runtime, "execute_signal_once", lambda *a, **kw: fills.append("unexpected"))
    store.update_state(lambda state: state.update(ai_auto_select_config={**config, "enabled": conflict != "stopped"}))
    with pytest.raises(RuntimeError):
        ai_auto_select.execute_selected(snapshot, expected_config=config)
    assert fills == []


def test_live_trade_requires_confirmation_and_forwards_confirm(monkeypatch):
    worker = {"account_id": "live-1", "account_info": {"trade_mode": 2, "read_only": False, "access_mode": "trading"}}
    monkeypatch.setattr(main.multi_account_client, "connected_by_login", lambda: {555: worker})
    calls = []

    def request(path, method="GET", payload=None, timeout=None):
        calls.append((path, method, payload))
        return {"results": {"live-1": {"ok": True, "result": {"retcode": 10009, "ticket": 42}}}}

    monkeypatch.setattr(main.multi_account_client, "request", request)
    with pytest.raises(main.HTTPException, match="explicit confirmation"):
        main.trade(main.TradePayload(account_login=555, symbol="XAUUSD", type="buy", volume=0.01))
    assert calls == []

    result = main.trade(main.TradePayload(account_login=555, symbol="XAUUSD", type="buy", volume=0.01, confirm_live=True))
    assert result["ticket"] == 42
    assert calls[-1][2]["confirm_live"] is True


def test_demo_trade_does_not_require_live_confirmation(monkeypatch):
    worker = {"account_id": "demo-1", "account_info": {"trade_mode": 0, "read_only": False, "access_mode": "trading"}}
    monkeypatch.setattr(main.multi_account_client, "connected_by_login", lambda: {556: worker})
    monkeypatch.setattr(main.multi_account_client, "request", lambda *a, **k: {"results": {"demo-1": {"ok": True, "result": {"retcode": 10009, "ticket": 43}}}})
    result = main.trade(main.TradePayload(account_login=556, symbol="XAUUSD", type="buy", volume=0.01))
    assert result["ticket"] == 43


def test_ai_trial_status_restores_saved_market_selection(monkeypatch):
    monkeypatch.setattr(main, "load_ai_trial_snapshot", lambda: None)
    monkeypatch.setattr(main, "read_state", lambda: {
        "ai_scan_config": {"account_login": 77123, "symbol": "FXVol40"}
    })
    status = main.get_ai_trial()
    assert status["scan_config"] == {"account_login": 77123, "symbol": "FXVol40"}


def test_trial_scan_persists_selected_market(monkeypatch):
    state = {}
    monkeypatch.setattr(main, "_run_ai_trial_scan", lambda payload: {"decision": "SCANNING"})
    monkeypatch.setattr(main, "update_state", lambda mutator: mutator(state))
    result = main.scan_ai_trial(main.AiTrialScanPayload(account_login=77123, symbol="SFXVol40"))
    assert result["decision"] == "SCANNING"
    assert state["ai_scan_config"] == {
        "account_login": 77123,
        "symbol": "SFXVol40",
        "execution_timeframe": "M15",
        "bias_timeframe": "H4",
    }


def test_ai_scan_requests_selected_execution_and_bias_timeframes(monkeypatch):
    requested = []
    monkeypatch.setattr(
        main.multi_account_client,
        "account_request",
        lambda login, path, timeout=20: requested.append(path) or [{"time": 1, "open": 1, "high": 2, "low": .5, "close": 1.5, "volume": 1}],
    )
    monkeypatch.setattr(main, "load_ai_trial_snapshot", lambda: None)
    monkeypatch.setattr(main, "save_ai_trial_snapshot", lambda snapshot: snapshot)
    monkeypatch.setattr(
        main,
        "run_human_apostle_trial",
        lambda execution, bias, **kwargs: {
            "decision": "WAIT",
            "execution_timeframe": kwargs["execution_timeframe"],
            "bias_timeframe": kwargs["bias_timeframe"],
        },
    )

    result = main._run_ai_trial_scan(main.AiTrialScanPayload(
        account_login=77123,
        symbol="FXV40",
        execution_timeframe="M30",
        bias_timeframe="D1",
    ))

    assert any("timeframe=M30" in path for path in requested)
    assert any("timeframe=D1" in path for path in requested)
    assert result["execution_timeframe"] == "M30"
    assert result["bias_timeframe"] == "D1"
