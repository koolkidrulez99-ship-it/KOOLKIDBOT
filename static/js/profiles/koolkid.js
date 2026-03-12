(function () {
  const PROFILE = "KOOLKID";
  const state = {
    lastSocket: null,
    socketBound: false,
    barrierAnalysis: null,
    over3Analysis: null,
    autoModes: {},
    dual2xOpen: false,
    dual2xBusy: false,
    dual2xAnalysis: { tickCount: 0, pctByDigit: null, ready: false },
  };

  function App() { return window.BotApp || {}; }
  function isActive() { try { return typeof activeProfile !== "undefined" && activeProfile === PROFILE; } catch (e) { return false; } }

  function getRoot() { return document.getElementById("profileContainer"); }

  function fmtPct(v) {
    if (v === null || v === undefined || v === "") return "-";
    const n = Number(v);
    if (!isFinite(n)) return "-";
    return `${n.toFixed(1)}%`;
  }

  function safeToast(msg, type) {
    try {
      if (typeof showToast === "function") showToast(msg, type || "info");
    } catch (e) {}
  }

  async function postJSON(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    let data = {};
    try { data = await res.json(); } catch (e) {}
    return { ok: res.ok, data };
  }


  function getStakeValueKoolkid() {
    const el = document.getElementById("stake");
    let v = Number(el && el.value);
    if (!isFinite(v) || v <= 0) v = 1;
    return v;
  }

  function updateDual2xUIKoolkid() {
    const btn = document.getElementById("dual2xBtnKoolkid");
    const wrap = document.getElementById("dual2xOptionsKoolkid");
    const optionA = document.getElementById("dual2xOver6Under4BtnKoolkid");
    const optionB = document.getElementById("dual2xOver5Under4BtnKoolkid");
    const optionC = document.getElementById("dual2xOver2Under1BtnKoolkid");
    const optionD = document.getElementById("dual2xOver8Under7BtnKoolkid");
    if (btn) {
      btn.innerText = state.dual2xBusy ? "DUAL 2x (RUNNING...)" : (state.dual2xOpen ? "DUAL 2x ▼" : "DUAL 2x");
      btn.style.background = state.dual2xBusy ? "#0ea5e9" : (state.dual2xOpen ? "#22c55e" : "#1e293b");
    }
    if (wrap) wrap.style.display = state.dual2xOpen ? "block" : "none";
    [optionA, optionB, optionC, optionD].forEach((b) => {
      if (!b) return;
      b.disabled = !!state.dual2xBusy;
      b.style.opacity = state.dual2xBusy ? "0.7" : "1";
      b.style.cursor = state.dual2xBusy ? "not-allowed" : "pointer";
    });
    renderDual2xAnalysisKoolkid();
  }

  async function placeDual2xLegsSameTickKoolkid(legs) {
    const stake = getStakeValueKoolkid();
    const totalWeight = legs.reduce((sum, leg) => sum + Math.max(0, Number(leg.weight || 1)), 0) || 1;
    const jobs = legs.map((leg) => {
      const weight = Math.max(0, Number(leg.weight || 1));
      const legStake = Number((stake * weight / totalWeight).toFixed(2));
      const payload = {
        stake: legStake,
        amount: legStake,
        type: String(leg.type || "OVER").toUpperCase(),
        barrier: Number(leg.barrier),
      };
      return postJSON("/manual_trade", payload);
    });
    const rs = await Promise.allSettled(jobs);
    let placed = 0;
    const failures = [];
    const stakes = [];
    rs.forEach((r, idx) => {
      const ok = r.status === "fulfilled" && r.value && r.value.data && r.value.data.status === "success";
      if (ok) placed += 1;
      else failures.push(legs[idx].label || `${legs[idx].type} ${legs[idx].barrier}`);
      const defaultStake = Number((stake * Math.max(0, Number(legs[idx].weight || 1)) / totalWeight).toFixed(2));
      stakes.push({
        label: legs[idx].label || `${legs[idx].type} ${legs[idx].barrier}`,
        stake: (r.status === "fulfilled" && r.value && r.value.stake) ? r.value.stake : defaultStake,
      });
    });
    return { placed, failures, stake, stakes };
  }

  async function placeDual2xSameTickKoolkid(overBarrier, underBarrier) {
    return placeDual2xLegsSameTickKoolkid([
      { type: "OVER", barrier: Number(overBarrier), weight: 1, label: `OVER ${overBarrier}` },
      { type: "UNDER", barrier: Number(underBarrier), weight: 1, label: `UNDER ${underBarrier}` },
    ]);
  }


  function parseDigitPercentagesForDual2xKoolkid(data) {
    if (!data) return null;
    const sources = [data.digit_percentages, data.percentages, data.digitPercents, data.digit_percent];
    for (const src of sources) {
      if (!src) continue;
      const out = {};
      if (Array.isArray(src)) {
        src.forEach((v, i) => {
          let pct = null;
          if (typeof v === "number") pct = Number(v);
          else if (v && typeof v === "object") pct = Number(v.pct ?? v.percent ?? v.percentage ?? v.value);
          if (Number.isFinite(pct)) out[i] = pct;
        });
      } else if (typeof src === "object") {
        Object.keys(src).forEach((k) => {
          const item = src[k];
          let pct = null;
          if (typeof item === "number") pct = Number(item);
          else if (item && typeof item === "object") pct = Number(item.pct ?? item.percent ?? item.percentage ?? item.value);
          const d = Number((item && typeof item === "object" && item.digit !== undefined) ? item.digit : k);
          if (Number.isInteger(d) && d >= 0 && d <= 9 && Number.isFinite(pct)) out[d] = pct;
        });
      }
      if (Object.keys(out).length) return out;
    }
    return null;
  }

  function dual2xSumPctDigitsKoolkid(pctByDigit, digits) {
    if (!pctByDigit) return null;
    let sum = 0;
    let count = 0;
    (digits || []).forEach((d) => {
      const v = Number(pctByDigit[d]);
      if (Number.isFinite(v)) {
        sum += v;
        count += 1;
      }
    });
    return count ? sum : null;
  }

  function dual2xAnalyzeCombosKoolkid(pctByDigit) {
    const d4 = Number(pctByDigit && pctByDigit[4]);
    const d5 = Number(pctByDigit && pctByDigit[5]);
    const d6 = Number(pctByDigit && pctByDigit[6]);

    const over6Under4Dead = dual2xSumPctDigitsKoolkid(pctByDigit, [4, 5, 6]);
    const over5Under4Dead = dual2xSumPctDigitsKoolkid(pctByDigit, [4, 5]);

    const over6Under4Safe = Number.isFinite(over6Under4Dead) ? Math.max(0, 100 - over6Under4Dead) : null;
    const over5Under4Safe = Number.isFinite(over5Under4Dead) ? Math.max(0, 100 - over5Under4Dead) : null;

    let best = null;
    if (Number.isFinite(over6Under4Dead) && Number.isFinite(over5Under4Dead)) {
      if (Math.abs(over6Under4Dead - over5Under4Dead) < 0.05) best = "TIE";
      else best = over6Under4Dead < over5Under4Dead ? "OVER6_UNDER4" : "OVER5_UNDER4";
    }

    return {
      d4: Number.isFinite(d4) ? d4 : null,
      d5: Number.isFinite(d5) ? d5 : null,
      d6: Number.isFinite(d6) ? d6 : null,
      over6Under4Dead,
      over6Under4Safe,
      over5Under4Dead,
      over5Under4Safe,
      best,
    };
  }

  function dual2xRiskColorKoolkid(deadPct) {
    const v = Number(deadPct);
    if (!Number.isFinite(v)) return "#94a3b8";
    if (v <= 18) return "#22c55e";
    if (v <= 28) return "#facc15";
    return "#fb7185";
  }

  function renderDual2xAnalysisKoolkid(data) {
    const statusEl = document.getElementById("dual2xAnalysisStatusKoolkid");
    const recEl = document.getElementById("dual2xRecommendationKoolkid");
    const d4El = document.getElementById("dual2xDigit4PctKoolkid");
    const d5El = document.getElementById("dual2xDigit5PctKoolkid");
    const d6El = document.getElementById("dual2xDigit6PctKoolkid");
    const aDeadEl = document.getElementById("dual2xDeadRiskA");
    const aSafeEl = document.getElementById("dual2xSafeA");
    const bDeadEl = document.getElementById("dual2xDeadRiskB");
    const bSafeEl = document.getElementById("dual2xSafeB");
    const optionA = document.getElementById("dual2xOver6Under4BtnKoolkid");
    const optionB = document.getElementById("dual2xOver5Under4BtnKoolkid");
    if (!statusEl && !recEl) return;

    const pctByDigit = parseDigitPercentagesForDual2xKoolkid(data);
    if (pctByDigit) {
      state.dual2xAnalysis = {
        pctByDigit,
        tickCount: Number(data && data.tick_count) || state.dual2xAnalysis.tickCount || 0,
        ready: true,
      };
    }

    const current = state.dual2xAnalysis || {};
    const pct = current.pctByDigit || null;
    const ready = !!current.ready && !!pct;
    const stats = dual2xAnalyzeCombosKoolkid(pct || {});

    if (d4El) d4El.innerText = fmtPct(stats.d4);
    if (d5El) d5El.innerText = fmtPct(stats.d5);
    if (d6El) d6El.innerText = fmtPct(stats.d6);

    if (aDeadEl) { aDeadEl.innerText = fmtPct(stats.over6Under4Dead); aDeadEl.style.color = dual2xRiskColorKoolkid(stats.over6Under4Dead); }
    if (aSafeEl) aSafeEl.innerText = fmtPct(stats.over6Under4Safe);
    if (bDeadEl) { bDeadEl.innerText = fmtPct(stats.over5Under4Dead); bDeadEl.style.color = dual2xRiskColorKoolkid(stats.over5Under4Dead); }
    if (bSafeEl) bSafeEl.innerText = fmtPct(stats.over5Under4Safe);

    if (statusEl) {
      if (!ready) {
        statusEl.style.color = "#94a3b8";
        statusEl.innerText = "Waiting for digit % data…";
      } else {
        statusEl.style.color = "#38bdf8";
        statusEl.innerText = `Live digit % • Dead zones: (4,5,6) vs (4,5)`;
      }
    }

    if (recEl) {
      if (!ready) {
        recEl.style.color = "#94a3b8";
        recEl.innerText = "Risk-only recommendation: waiting for data";
      } else if (stats.best === "OVER6_UNDER4") {
        recEl.style.color = "#22c55e";
        recEl.innerText = "Risk-only pick: OVER 6 & UNDER 4 (4,5,6 dead zone currently lower)";
      } else if (stats.best === "OVER5_UNDER4") {
        recEl.style.color = "#22c55e";
        recEl.innerText = "Risk-only pick: OVER 5 & UNDER 4 (4,5 dead zone currently lower)";
      } else {
        recEl.style.color = "#facc15";
        recEl.innerText = "Risk-only pick: Tie / very close";
      }
    }

    if (optionA && !state.dual2xBusy) {
      optionA.style.boxShadow = (stats.best === "OVER6_UNDER4") ? "0 0 0 1px #22c55e inset, 0 0 10px rgba(34,197,94,0.25)" : "none";
    }
    if (optionB && !state.dual2xBusy) {
      optionB.style.boxShadow = (stats.best === "OVER5_UNDER4") ? "0 0 0 1px #22c55e inset, 0 0 10px rgba(34,197,94,0.25)" : "none";
    }
  }

  function selectedDigits() {
    const a = App();
    return Array.isArray(a.koolkidSelectedDigits) ? a.koolkidSelectedDigits.slice() : [];
  }

  async function syncSelectedDigitsToServer() {
    if (!isActive()) return;
    try {
      await postJSON("/set_mpull_all_digits_selection", { digits: selectedDigits() });
    } catch (e) {}
  }

  function renderBarrierAnalysis(data) {
    state.barrierAnalysis = data || state.barrierAnalysis || null;
    const panelBtn = document.getElementById("barrierAnalysisBtn");
    const prog = document.getElementById("barrierAnalysisProgress");
    const detailsWrap = document.getElementById("barrierAnalysisDetails");
    const rowsWrap = document.getElementById("barrierAnalysisRows");
    const rec = document.getElementById("barrierAnalysisRecommended");
    const kidGxBtn = document.getElementById("kidGxBtnKoolkid");
    if (!panelBtn || !prog || !rowsWrap || !rec) return;

    const ba = state.barrierAnalysis || {};
    const running = !!ba.running;
    const progress = Number(ba.progress || 0);
    const target = Number(ba.target || 30);
    const ready = !!ba.ready;
    const selected = (ba.selected || "UNDER 9").toString().toUpperCase();

    panelBtn.innerText = `Barrier Analysis: ${running ? "ON" : "OFF"}`;
    panelBtn.style.background = running ? "#22c55e" : "#1e293b";
    if (detailsWrap) detailsWrap.style.display = running ? "block" : "none";

    if (!running) {
      prog.innerText = "Press Barrier Analysis to start";
    } else if (!ready) {
      prog.innerText = `${Math.min(progress, target)}/${target}`;
    } else {
      prog.innerText = `Live rolling ${target}/${target}`;
    }

    const rows = Array.isArray(ba.rows) ? ba.rows.slice() : [];
    rows.sort((a, b) => {
      const av = Number(a && (a.wins_pct ?? a.confidence_pct));
      const bv = Number(b && (b.wins_pct ?? b.confidence_pct));
      const aOk = isFinite(av);
      const bOk = isFinite(bv);
      if (aOk && bOk && av !== bv) return bv - av;
      if (aOk && !bOk) return -1;
      if (!aOk && bOk) return 1;
      const ak = ((a && (a.key || `${a.type} ${a.barrier}`)) || "").toString();
      const bk = ((b && (b.key || `${b.type} ${b.barrier}`)) || "").toString();
      return ak.localeCompare(bk);
    });
    rowsWrap.innerHTML = "";
    rows.forEach((row) => {
      const key = (row.key || `${row.type} ${row.barrier}`).toString().toUpperCase();
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "barrier-analysis-row";
      btn.style.width = "100%";
      btn.style.display = "flex";
      btn.style.justifyContent = "space-between";
      btn.style.alignItems = "center";
      btn.style.gap = "8px";
      btn.style.height = "38px";
      btn.style.background = key === selected ? "#1d4ed8" : "#111827";
      btn.style.border = key === selected ? "1px solid #60a5fa" : "1px solid #334155";
      btn.style.borderRadius = "10px";
      btn.style.color = "#e2e8f0";
      btn.style.padding = "0 10px";
      btn.onclick = function () { window.selectBarrierAnalysisOption && window.selectBarrierAnalysisOption(key); };
      btn.innerHTML = `
        <span style="font-weight:700;">${key}</span>
        <span style="font-size:12px; color:#cbd5e1;">${ready ? fmtPct(row.wins_pct) : `${Math.min(progress, target)}/${target}`}</span>
      `;
      rowsWrap.appendChild(btn);
    });

    const r = ba.recommended;
    if (!ready || !r) {
      rec.innerText = `Recommended: ${ready ? "-" : `Loading ${Math.min(progress, target)}/${target}`}`;
    } else {
      const rKey = (r.key || `${r.type} ${r.barrier}`).toString().toUpperCase();
      rec.innerText = `Recommended: ${rKey} (${fmtPct(r.wins_pct)}) • Confidence ${fmtPct(r.confidence_pct)}`;
    }

    if (kidGxBtn) {
      const on = !!state.autoModes.kidgx;
      kidGxBtn.innerText = on ? `⚡kidGx ${selected}: ON` : `⚡kidGx ${selected}`;
      kidGxBtn.style.background = on ? "#22c55e" : "#1e293b";
    }
  }

  function renderOver3AnalysisKoolkid(data) {
    if (data && typeof data === "object") state.over3Analysis = data;
    const d = state.over3Analysis || {};
    const info = document.getElementById("over3AnalysisInfoKoolkid");
    const btn = document.getElementById("over3AnalysisBtnKoolkid");
    const enabled = !!(state.autoModes && state.autoModes.over3_analysis);
    if (btn) {
      btn.innerText = `Over 3 Analysis: ${enabled ? "ON" : "OFF"}`;
      btn.style.background = enabled ? "#22c55e" : "#1e293b";
    }
    if (!info) return;

    const symbol = String(d.symbol || "");
    const symbolOk = !!d.symbol_ok;
    const high100 = Number(d.high_count_100 || 0);
    const high10 = Number(d.high_count_10 || 0);
    const streak = Number(d.current_high_streak || 0);
    const losses = Number(d.consecutive_losses || 0);
    const total = Number(d.total_trades || 0);
    const duration = Number(d.duration_ticks || 1);
    const active = !!d.trade_active;
    const stopped = !!d.session_stopped;
    const waitFresh = !!d.wait_fresh_setup;
    const setupReady = !!d.entry_conditions_ready;
    const counts = `H100 ${high100}/58 • H10 ${high10}/6 • Streak ${streak}/<6`;
    const session = `Losses ${losses}/2 • Trades ${total}/5 • Duration ${duration}T`;

    if (!enabled) {
      info.style.color = "#94a3b8";
      info.innerText = `Over 3 off • ${counts}`;
      return;
    }
    if (!symbolOk) {
      info.style.color = "#f59e0b";
      info.innerText = `Switch to Volatility 50 (R_50) to run Over 3 • Current ${symbol || "-"}`;
      return;
    }
    if (stopped) {
      info.style.color = "#ef4444";
      info.innerText = `Session stopped (${session}). Toggle OFF/ON to restart.`;
      return;
    }
    if (active) {
      info.style.color = "#38bdf8";
      info.innerText = `Trade active on R_50, waiting result • ${session}`;
      return;
    }
    if (waitFresh) {
      info.style.color = "#f59e0b";
      info.innerText = `Waiting fresh setup reset • ${counts} • ${session}`;
      return;
    }
    if (setupReady) {
      info.style.color = "#22c55e";
      info.innerText = `Setup ready: Over 3 entry armed • ${counts} • ${session}`;
      return;
    }
    info.style.color = "#94a3b8";
    info.innerText = `Scanning R_50 ticks • ${counts} • ${session}`;
  }


function updateAdvancedAIModeButtons(modes, payload) {
  const map = [
    ["kidbrain", "kidbrainBtnKoolkid", "🤖 KIDBRAIN"],
    ["edge_brain", "edgeBrainBtnKoolkid", "🧠 EDGE BRAIN"],
    ["smart_flow", "smartFlowBtnKoolkid", "🎯 SMART FLOW"],
    ["meta_ai", "metaAiBtnKoolkid", "⚡ META AI"],
    ["kidracks_ai", "kidracksAiBtnKoolkid", "🤓 KIDRACKS AI"],
    ["over3_analysis", "over3AnalysisBtnKoolkid", "Over 3 Analysis"],
  ];
  map.forEach(([key, id, label]) => {
    const btn = document.getElementById(id);
    if (!btn || !(key in (state.autoModes || {}))) return;
    const on = !!state.autoModes[key];
    btn.innerText = `${label}: ${on ? "ON" : "OFF"}`;
    btn.style.background = on ? "#22c55e" : "#1e293b";
  });
  const info = document.getElementById("metaBrainInfoKoolkid");
  const meta = (payload && payload.meta_brain) || state.metaBrain;
  if (payload && payload.meta_brain) state.metaBrain = payload.meta_brain;
  if (info && meta) {
    const conf = meta.confidence_pct !== undefined ? `${Number(meta.confidence_pct).toFixed(1)}%` : "-";
    const gap = meta.edge_gap !== undefined ? Number(meta.edge_gap).toFixed(1) : "-";
    const score = meta.market_score !== undefined ? Number(meta.market_score).toFixed(1) : "-";
    const shadow = meta.shadow && typeof meta.shadow.live_winrate === "number"
      ? ` • Shadow ${meta.shadow.live_winrate.toFixed(1)}%/${meta.shadow.alt_winrate.toFixed(1)}%`
      : "";
    info.innerText = `Regime: ${meta.regime || "-"} • Conf: ${conf} • Gap: ${gap} • Score: ${score}${shadow}`;
  }
}

  function updateModeButtonsFromPayload(modes, payload) {
    state.autoModes = Object.assign({}, state.autoModes || {}, modes || {});
    const kidGxBtn = document.getElementById("kidGxBtnKoolkid");
    const aiBtn = document.getElementById("aiAutoTradingBtnKoolkid");
    const mpullAllBtn = document.getElementById("mpullAllDigitsBtn");
    if (aiBtn && state.autoModes.ai_auto_trading !== undefined) {
      aiBtn.innerText = `🤖AI AUTO-TRADING: ${state.autoModes.ai_auto_trading ? "ON" : "OFF"}`;
      aiBtn.style.background = state.autoModes.ai_auto_trading ? "#22c55e" : "#1e293b";
    }
    if (mpullAllBtn && state.autoModes.mpull_all_digits !== undefined) {
      mpullAllBtn.innerText = `MPull💰🤓 ALL DIGITS: ${state.autoModes.mpull_all_digits ? "ON" : "OFF"}`;
      mpullAllBtn.style.background = state.autoModes.mpull_all_digits ? "#22c55e" : "#1e293b";
    }
    if (payload && payload.barrier_analysis) renderBarrierAnalysis(payload.barrier_analysis);
    else if (kidGxBtn) renderBarrierAnalysis(state.barrierAnalysis || { selected: "UNDER 9" });
    if (payload && payload.over3_analysis_data) renderOver3AnalysisKoolkid(payload.over3_analysis_data);
    else renderOver3AnalysisKoolkid();
    updateDual2xUIKoolkid();
    renderDual2xAnalysisKoolkid();
    updateAdvancedAIModeButtons(modes || {}, payload || null);
  }

  function bindSocketListeners() {
    try {
      if (typeof socket === "undefined" || !socket) return;
      if (state.lastSocket === socket && state.socketBound) return;
      state.lastSocket = socket;
      state.socketBound = true;

      socket.on("digit_analysis", (data) => {
        if (!isActive()) return;
        renderDual2xAnalysisKoolkid(data || {});
        if (data && data.barrier_analysis) renderBarrierAnalysis(data.barrier_analysis);
        if (data && data.over3_analysis_data) renderOver3AnalysisKoolkid(data.over3_analysis_data);
        if (data && data.auto_modes) updateModeButtonsFromPayload(data.auto_modes, data);
      });

      socket.on("auto_mode_update", (modes) => {
        if (!isActive()) return;
        updateModeButtonsFromPayload(modes || {});
      });
    } catch (e) {}
  }

  function bindWindowEvents() {
    if (window.__koolkidFeatureEventsBound) return;
    window.__koolkidFeatureEventsBound = true;

    window.addEventListener("botapp:koolkidSelectedDigitsChanged", () => {
      syncSelectedDigitsToServer();
      try { App().applyDigitSelectionUI && App().applyDigitSelectionUI(); } catch (e) {}
    });
  }

  async function onMount() {
    try { App().ensureDigitClickPatchSoon && App().ensureDigitClickPatchSoon(); } catch (e) {}
    try { App().applyDigitSelectionUI && App().applyDigitSelectionUI(); } catch (e) {}
    bindSocketListeners();
    bindWindowEvents();
    updateDual2xUIKoolkid();
    renderDual2xAnalysisKoolkid();
    renderOver3AnalysisKoolkid();
    setTimeout(syncSelectedDigitsToServer, 200);
  }

  async function onActivate() {
    try { App().applyDigitSelectionUI && App().applyDigitSelectionUI(); } catch (e) {}
    bindSocketListeners();
    updateDual2xUIKoolkid();
    renderDual2xAnalysisKoolkid();
    renderOver3AnalysisKoolkid();
    setTimeout(syncSelectedDigitsToServer, 150);
  }

  async function afterLoadProfileUI() {
    try { App().applyDigitSelectionUI && App().applyDigitSelectionUI(); } catch (e) {}
    bindSocketListeners();
    updateDual2xUIKoolkid();
    renderDual2xAnalysisKoolkid();
    renderOver3AnalysisKoolkid();
  }

  window.toggleDual2xKoolkid = function () {
    state.dual2xOpen = !state.dual2xOpen;
    updateDual2xUIKoolkid();
  };

  window.runDual2xKoolkid = async function (mode) {
    if (state.dual2xBusy) return;
    const key = String(mode || "").toUpperCase();
    const configs = {
      OVER6_UNDER4: {
        label: "OVER 6 & UNDER 4",
        legs: [
          { type: "OVER", barrier: 6, weight: 1, label: "OVER 6" },
          { type: "UNDER", barrier: 4, weight: 1, label: "UNDER 4" },
        ],
        deadKey: "over6Under4Dead",
      },
      OVER5_UNDER4: {
        label: "OVER 5 & UNDER 4",
        legs: [
          { type: "OVER", barrier: 5, weight: 1, label: "OVER 5" },
          { type: "UNDER", barrier: 4, weight: 1, label: "UNDER 4" },
        ],
        deadKey: "over5Under4Dead",
      },
      OVER2_UNDER1: {
        label: "OVER 2 & UNDER 1 (5:1 split)",
        legs: [
          { type: "OVER", barrier: 2, weight: 5, label: "OVER 2" },
          { type: "UNDER", barrier: 1, weight: 1, label: "UNDER 1" },
        ],
        deadKey: null,
      },
      OVER8_UNDER7: {
        label: "OVER 8 & UNDER 7 (5:1 split)",
        legs: [
          { type: "OVER", barrier: 8, weight: 1, label: "OVER 8" },
          { type: "UNDER", barrier: 7, weight: 5, label: "UNDER 7" },
        ],
        deadKey: null,
      },
    };
    const config = configs[key] || configs.OVER6_UNDER4;

    state.dual2xBusy = true;
    updateDual2xUIKoolkid();
    try {
      const liveStats = dual2xAnalyzeCombosKoolkid((state.dual2xAnalysis && state.dual2xAnalysis.pctByDigit) || {});
      const deadRisk = config.deadKey ? liveStats[config.deadKey] : null;
      const r = await placeDual2xLegsSameTickKoolkid(config.legs);
      if (r.placed === config.legs.length) {
        const stakeMsg = r.stakes && r.stakes.length ? r.stakes.map((s) => `${s.label}: $${Number(s.stake).toFixed(2)}`).join(" / ") : "";
        safeToast(`DUAL 2x sent: ${config.label} • ${stakeMsg}${Number.isFinite(deadRisk) ? ` • dead risk ${deadRisk.toFixed(1)}%` : ""}`, "success");
      } else if (r.placed === 1) {
        safeToast(`DUAL 2x partial (1/2): ${config.label}`, "error");
      } else {
        safeToast(`DUAL 2x failed: ${config.label}`, "error");
      }
    } catch (e) {
      safeToast(`DUAL 2x failed: ${config.label}`, "error");
    } finally {
      state.dual2xBusy = false;
      updateDual2xUIKoolkid();
    }
  };

  window.toggleBarrierAnalysis = async function () {
    const r = await postJSON("/toggle_barrier_analysis", {});
    if (r.data && r.data.status === "success") {
      if (!state.barrierAnalysis || typeof state.barrierAnalysis !== "object") state.barrierAnalysis = {};
      state.barrierAnalysis.running = !!r.data.barrier_analysis;
      renderBarrierAnalysis(state.barrierAnalysis);
      safeToast(`Barrier Analysis: ${r.data.barrier_analysis ? "ON" : "OFF"}`, r.data.barrier_analysis ? "success" : "error");
    } else {
      safeToast((r.data && r.data.message) || "Barrier Analysis failed", "error");
    }
  };

  window.selectBarrierAnalysisOption = async function (key) {
    const r = await postJSON("/select_barrier_analysis_barrier", { key });
    if (r.data && r.data.status === "success") {
      if (!state.barrierAnalysis) state.barrierAnalysis = {};
      state.barrierAnalysis.selected = r.data.selected;
      renderBarrierAnalysis(state.barrierAnalysis);
      safeToast(`Selected ${r.data.selected}`, "success");
    }
  };

  window.toggleKidGxKoolkid = async function () {
    const r = await postJSON("/toggle_kidgx_auto", { profile: "KOOLKID" });
    if (r.data && r.data.status === "success") {
      state.autoModes.kidgx = !!r.data.kidgx_auto;
      updateModeButtonsFromPayload({ kidgx: state.autoModes.kidgx });
      safeToast(`⚡kidGx ${r.data.kidgx_auto ? "ON" : "OFF"}`, r.data.kidgx_auto ? "success" : "error");
    } else {
      safeToast((r.data && r.data.message) || "⚡kidGx failed", "error");
    }
  };

  window.toggleAIAutoTradingKoolkid = async function () {
    const r = await postJSON("/toggle_ai_auto_trading", { profile: "KOOLKID" });
    if (r.data && r.data.status === "success") {
      state.autoModes.ai_auto_trading = !!r.data.ai_auto_trading;
      updateModeButtonsFromPayload({ ai_auto_trading: state.autoModes.ai_auto_trading });
      safeToast(`🤖AI AUTO-TRADING: ${r.data.ai_auto_trading ? "ON" : "OFF"}`, r.data.ai_auto_trading ? "success" : "error");
    } else {
      safeToast((r.data && r.data.message) || "AI auto failed", "error");
    }
  };

  window.toggleMPullAllDigitsAuto = async function () {
    await syncSelectedDigitsToServer();
    const r = await postJSON("/toggle_mpull_all_digits_auto", {});
    if (r.data && r.data.status === "success") {
      state.autoModes.mpull_all_digits = !!r.data.mpull_all_digits_auto;
      updateModeButtonsFromPayload({ mpull_all_digits: state.autoModes.mpull_all_digits });
      safeToast(`MPull💰🤓 ALL DIGITS: ${r.data.mpull_all_digits_auto ? "ON" : "OFF"}`, r.data.mpull_all_digits_auto ? "success" : "error");
    } else {
      safeToast((r.data && r.data.message) || "MPull ALL DIGITS failed", "error");
    }
  };

  window.toggleOver3AnalysisKoolkid = async function () {
    const r = await postJSON("/toggle_over3_analysis_koolkid", {});
    if (r.data && r.data.status === "success") {
      if (r.data.auto_modes) state.autoModes = Object.assign({}, state.autoModes || {}, r.data.auto_modes);
      updateModeButtonsFromPayload(r.data.auto_modes || { over3_analysis: !!r.data.over3_analysis }, r.data.payload || null);
      if (r.data.over3_analysis_data) renderOver3AnalysisKoolkid(r.data.over3_analysis_data);
      safeToast(`Over 3 Analysis: ${r.data.over3_analysis ? "ON" : "OFF"}`, r.data.over3_analysis ? "success" : "error");
    } else {
      safeToast((r.data && r.data.message) || "Over 3 Analysis failed", "error");
    }
  };


async function toggleAdvancedModeKoolkid(modeKey, label) {
  const r = await postJSON("/toggle_named_ai_mode", { profile: "KOOLKID", mode_key: modeKey });
  if (r.data && r.data.status === "success") {
    if (r.data.auto_modes) state.autoModes = Object.assign({}, state.autoModes || {}, r.data.auto_modes);
    updateModeButtonsFromPayload(r.data.auto_modes || { [modeKey]: !!r.data.enabled }, r.data.payload || null);
    safeToast(`${label}: ${r.data.enabled ? "ON" : "OFF"}`, r.data.enabled ? "success" : "error");
  } else {
    safeToast((r.data && r.data.message) || `${label} failed`, "error");
  }
}

window.toggleKidbrainKoolkid = function () { return toggleAdvancedModeKoolkid("kidbrain", "🤖 KIDBRAIN"); };
window.toggleEdgeBrainKoolkid = function () { return toggleAdvancedModeKoolkid("edge_brain", "🧠 EDGE BRAIN"); };
window.toggleSmartFlowKoolkid = function () { return toggleAdvancedModeKoolkid("smart_flow", "🎯 SMART FLOW"); };
window.toggleMetaAIKoolkid = function () { return toggleAdvancedModeKoolkid("meta_ai", "⚡ META AI"); };
window.toggleKidracksAIKoolkid = function () { return toggleAdvancedModeKoolkid("kidracks_ai", "🤓 KIDRACKS AI"); };

  if (typeof window.registerProfileModule === "function") {
    window.registerProfileModule(PROFILE, { onMount, afterLoadProfileUI, onActivate });
  } else {
    window.ProfileModules = window.ProfileModules || {};
    window.ProfileModules[PROFILE] = { onMount, afterLoadProfileUI, onActivate };
  }

  // Fallback bootstrap for index versions without Phase 2 hooks
  function fallbackBootstrap() {
    try {
      if (typeof window.registerProfileModule !== "function") {
        if (typeof onMount === "function") onMount();
        if (typeof afterLoadProfileUI === "function") afterLoadProfileUI();
        if (isActive() && typeof onActivate === "function") onActivate();
      }
    } catch (e) {}
  }
  setInterval(fallbackBootstrap, 900);
  setTimeout(fallbackBootstrap, 200);

})();
