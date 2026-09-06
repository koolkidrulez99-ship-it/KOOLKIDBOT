from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HUMAN_HTML = ROOT / "static" / "components" / "human.html"
HUMAN_JS = ROOT / "static" / "js" / "profiles" / "human.js"
SERVER = ROOT / "server.py"


def _function_block(source, name):
    start = source.index(f"function {name}")
    next_start = source.find("\n  function ", start + 1)
    return source[start:] if next_start == -1 else source[start:next_start]


def test_rise_fall_martingale_has_tp_sl_session_controls():
    html = HUMAN_HTML.read_text(encoding="utf-8")
    js = HUMAN_JS.read_text(encoding="utf-8")
    rf_settings = _function_block(js, "readHumanRfMartingaleSettings")

    assert 'id="humanRfMartingaleTp"' in html
    assert 'id="humanRfMartingaleSl"' in html
    assert 'id="humanRfMartingaleMaxSteps" type="number" min="1" step="1" value="80"' in html
    assert 'id="humanRfMartingaleDoBothTrades"' in html
    assert "applyHumanRfTpSlAfterResult" in js
    assert "isHumanRfTpSlEnabled" in js
    assert 'readHumanRfMartingaleNumber("humanRfMartingaleMaxSteps", 80' in js
    assert "doBothTrades" in js
    assert "sameSettingsPairMode" in js
    assert 'HUMAN_RF_MARTINGALE_STATE.riseBaseStake = sameSettingsPairMode ? settings.startStake' in js
    assert 'HUMAN_RF_MARTINGALE_STATE.fallBaseStake = sameSettingsPairMode ? settings.startStake' in js
    assert 'const maxDoubleCount = Math.max(0, Math.floor(Number(settings.maxSteps || 1) || 1) - 1)' in js
    assert "Session P/L" in js
    assert "waitForTpSl" in js
    assert "reconcileHumanRfPairPlacementResponse" in js
    assert "function scheduleHumanRfMartingaleRound()" in js
    assert "st.restartTimer = setTimeout" in js
    assert "batch_id: HUMAN_RF_MARTINGALE_STATE.batchId" in js
    assert "Partial pair sent" in js
    assert "next round will retry both" in js
    assert "Retrying next round" in js
    assert "Partial pair sent (${placed.length}/2). Settling placed leg, then stopped." not in js
    assert "rfBatchId === HUMAN_RF_MARTINGALE_STATE.batchId" in js
    assert '"batch_id": batch_id' in SERVER.read_text(encoding="utf-8")
    assert '"batch_size": 2' in SERVER.read_text(encoding="utf-8")
    assert '"leg_action": "RISE"' in SERVER.read_text(encoding="utf-8")
    assert '"leg_action": "FALL"' in SERVER.read_text(encoding="utf-8")
    assert 'tpEl && String(tpEl.value || "").trim() === "") tpEl.value = "0"' not in rf_settings
    assert 'slEl && String(slEl.value || "").trim() === "") slEl.value = "0"' not in rf_settings


def test_dual_market_allows_same_symbol_and_has_martingale_controls():
    html = HUMAN_HTML.read_text(encoding="utf-8")
    js = HUMAN_JS.read_text(encoding="utf-8")
    dual_settings = _function_block(js, "readHumanDualMartingaleSettings")

    assert 'id="humanDualMartingaleToggleBtn"' in html
    assert 'id="humanDualMartingaleMultiplier"' in html
    assert 'id="humanDualMartingaleTp"' in html
    assert 'id="humanDualMartingaleSl"' in html
    assert 'id="humanDualMarketQuickStopBtn"' in html
    assert "Choose two different markets for this mode" not in js
    assert "Choose two different markets for Dual Market Contracts" not in js
    assert 'if(multEl && String(multEl.value || "").trim() === "") multEl.value' not in dual_settings
    assert 'if(tpEl && String(tpEl.value || "").trim() === "") tpEl.value' not in dual_settings
    assert 'if(slEl && String(slEl.value || "").trim() === "") slEl.value' not in dual_settings


def test_dual_market_martingale_tracks_leg_metadata_for_same_market_results():
    js = HUMAN_JS.read_text(encoding="utf-8")
    server = SERVER.read_text(encoding="utf-8")

    assert "HUMAN_DUAL_MARTINGALE_STATE" in js
    assert "updateHumanDualMarketMartingaleFromResult" in js
    assert "matchHumanDualPendingSide" in js
    assert "dual_market_leg_index" in js
    assert "dual_market_batch_id" in js
    assert '"dual_market_leg_index": meta.get("dual_market_leg_index")' in server
    assert '"dual_market_batch_id": meta.get("dual_market_batch_id")' in server
