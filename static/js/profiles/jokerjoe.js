(function () {
  const PROFILE = "JOKERJOE";
  const state = { lastSocket: null, socketBound: false, autoModes: {}, kidgxBarrier: 5, matchesAnalysisOn: false, matchesLastKey: "", matchesObserverBound: false, matchSniperOn: false, matchSniperCooldownUntil: 0, matchSniperActiveDigit: null, matchSniperConsumed: false, matchSniperBusy: false, matchesSnapshot: null, matchesSorted: [], matchSniper5xOn: false, matchSniper5xCooldownUntil: 0, matchSniper5xBusy: false, matchSniper5xLastTopKey: "", aiAutoModeChoice: "golden_digits", aiAutoLowestLocalOn: false, aiAutoModalOpen: false, aiLowestLastTickCount: 0, aiLowestTouches: {}, aiLowestArmed: null, aiLowestBatchActive: false, aiLowestBatchPending: 0, aiLowestBatchBarrier: null, aiLowestBatchProfit: 0, aiLowestCooldownUntil: 0, aiLowestSubmitting: false, aiLowestRecoveryDeficit: 0, aiLowestRecoveryOnly: false };

  function App() { return window.BotApp || {}; }
  function isActive() { try { return typeof activeProfile !== "undefined" && activeProfile === PROFILE; } catch (e) { return false; } }
  function safeToast(msg, type) { try { if (typeof showToast === "function") showToast(msg, type || "info"); } catch (e) {} }

  function getEl(id) { return document.getElementById(id); }

  function setText(id, value) {
    const el = getEl(id);
    if (el) el.innerText = value;
  }


  function normalizeAIAutoModeJokerjoe(mode) {
    return String(mode || "golden_digits").toLowerCase() === "lowest_pct" ? "lowest_pct" : "golden_digits";
  }

  function isAIAutoOnJokerjoe() {
    return !!(state.autoModes && state.autoModes.ai_auto_trading) || !!state.aiAutoLowestLocalOn;
  }

  function resetAIAutoLowestStateJokerjoe(opts) {
    const keepRecovery = !!(opts && opts.keepRecovery);
    state.aiLowestLastTickCount = 0;
    state.aiLowestTouches = {};
    state.aiLowestArmed = null;
    state.aiLowestBatchActive = false;
    state.aiLowestBatchPending = 0;
    state.aiLowestBatchBarrier = null;
    state.aiLowestBatchProfit = 0;
    state.aiLowestSubmitting = false;
    state.aiLowestCooldownUntil = 0;
    if (!keepRecovery) {
      state.aiLowestRecoveryDeficit = 0;
      state.aiLowestRecoveryOnly = false;
    }
  }

  function openAIAutoModeModalJokerjoe() {
    const modal = getEl("aiAutoModeModalJokerjoe");
    if (!modal) return;
    state.aiAutoModalOpen = true;
    modal.style.display = "flex";
    updateAIAutoModeModalUiJokerjoe();
  }

  function closeAIAutoModeModalJokerjoe() {
    const modal = getEl("aiAutoModeModalJokerjoe");
    if (!modal) return;
    state.aiAutoModalOpen = false;
    modal.style.display = "none";
  }

  function updateAIAutoModeModalUiJokerjoe() {
    const mode = normalizeAIAutoModeJokerjoe(state.aiAutoModeChoice);
    const goldenBtn = getEl("aiAutoGoldenBtnJokerjoe");
    const lowestBtn = getEl("aiAutoLowestBtnJokerjoe");
    const status = getEl("aiAutoModeModalStatusJokerjoe");
    if (goldenBtn) goldenBtn.style.background = mode === "golden_digits" ? "#22c55e" : "#1e293b";
    if (lowestBtn) lowestBtn.style.background = mode === "lowest_pct" ? "#22c55e" : "#1e293b";
    if (status) {
      if (mode === "lowest_pct") {
        const rec = state.aiLowestRecoveryOnly ? ` • Recovery ON ($${Number(state.aiLowestRecoveryDeficit || 0).toFixed(2)} left)` : "";
        status.innerText = `Lowest % mode (DIFFERS): touch → move-away → next tick • exact 5 trades • 10s cooldown${rec}`;
      } else {
        status.innerText = "Golden Digits mode: existing backend AI AUTO logic";
      }
    }
  }

  function getEligibleLowPctDigitsJokerjoe(percentages) {
    const out = [];
    if (!percentages) return out;
    for (let d = 0; d <= 9; d++) {
      const raw = Array.isArray(percentages) ? percentages[d] : percentages[d];
      const pct = Number(raw);
      if (!Number.isNaN(pct) && pct < 10) out.push({ digit: d, pct });
    }
    return out.sort((a, b) => a.pct - b.pct || a.digit - b.digit);
  }

  async function placeBatchManualTradesJokerjoe(contractType, digits) {
    const stakeEl = document.getElementById("stake");
    let stake = Number(stakeEl && stakeEl.value);
    if (!Number.isFinite(stake) || stake <= 0) stake = 1;

    // Send stake with each manual trade so batch actions (MatchSniper 5x) respect the UI stake.
    // Include both `stake` and `amount` for compatibility with different backend parsers.
    const base = { type: contractType, stake, amount: stake };

    const jobs = (digits || []).map((d) => postJSON("/manual_trade", Object.assign({}, base, { barrier: Number(d) })));
    const results = await Promise.allSettled(jobs);
    let placed = 0;
    const failed = [];
    for (let i = 0; i < results.length; i++) {
      const r = results[i];
      if (r.status === "fulfilled" && r.value && r.value.data && r.value.data.status === "success") placed += 1;
      else failed.push(Number(digits[i]));
    }
    return { placed, failed };
  }

  async function placeExactFiveDiffersBatchJokerjoe(digit) {
    let totalPlaced = 0;
    let attempts = 0;
    try {
      const r = await postJSON("/insta5", { barrier: Number(digit) });
      totalPlaced = Math.max(0, Number(r && r.data && r.data.placed) || 0);
    } catch (e) {}

    while (totalPlaced < 5 && attempts < 20) {
      attempts += 1;
      const missing = 5 - totalPlaced;
      const jobs = [];
      for (let i = 0; i < missing; i++) jobs.push(postJSON("/manual_trade", { type: "DIFFERS", barrier: Number(digit) }));
      const rs = await Promise.allSettled(jobs);
      let add = 0;
      rs.forEach((x) => {
        if (x.status === "fulfilled" && x.value && x.value.data && x.value.data.status === "success") add += 1;
      });
      totalPlaced += add;
      if (totalPlaced < 5) await new Promise((resolve) => setTimeout(resolve, 40));
    }
    return { placed: totalPlaced, exact: totalPlaced === 5 };
  }

  async function fireAIAutoLowestBatchJokerjoe(digit, pct) {
    if (state.aiLowestSubmitting || state.aiLowestBatchActive) return;
    state.aiLowestSubmitting = true;
    const d = Number(digit);
    try {
      const r = await placeExactFiveDiffersBatchJokerjoe(d);
      if (r && r.exact) {
        state.aiLowestBatchActive = true;
        state.aiLowestBatchPending = 5;
        state.aiLowestBatchBarrier = d;
        state.aiLowestBatchProfit = 0;
        safeToast(`🤖AI Lowest % batch: 5/5 DIFFERS on ${d}${Number.isFinite(Number(pct)) ? ` (${Number(pct).toFixed(1)}%)` : ""}`, "success");
      } else {
        state.aiLowestBatchActive = false;
        state.aiLowestBatchPending = 0;
        state.aiLowestBatchBarrier = null;
        safeToast(`🤖AI Lowest % exact batch failed (${r && r.placed ? r.placed : 0}/5)`, "error");
      }
    } catch (e) {
      safeToast("🤖AI Lowest % batch failed", "error");
    } finally {
      state.aiLowestSubmitting = false;
      updateAIAutoModeModalUiJokerjoe();
    }
  }

  function processAIAutoLowestTickJokerjoe(data) {
    if (!data || !state.aiAutoLowestLocalOn) return;
    const tickCount = Number(data.tick_count);
    const lastDigit = Number(data.last_digit);
    const percentages = data.percentages || data.digit_percentages || data.digitPercents;
    if (!Number.isFinite(tickCount) || !Number.isInteger(lastDigit) || lastDigit < 0 || lastDigit > 9 || !percentages) return;
    if (tickCount <= (state.aiLowestLastTickCount || 0)) return;
    state.aiLowestLastTickCount = tickCount;

    const now = Date.now();
    const eligible = getEligibleLowPctDigitsJokerjoe(percentages);
    const eligibleMap = new Map(eligible.map((x) => [x.digit, x.pct]));

    // Resolve armed condition on the required NEXT tick before creating new ones.
    if (state.aiLowestArmed && !state.aiLowestBatchActive && !state.aiLowestSubmitting && now >= (state.aiLowestCooldownUntil || 0)) {
      const armed = state.aiLowestArmed;
      if (tickCount >= Number(armed.tradeOnTick || Infinity)) {
        const pct = eligibleMap.has(armed.digit) ? eligibleMap.get(armed.digit) : armed.pctAtArm;
        const armDigit = Number(armed.digit);
        state.aiLowestArmed = null;
        fireAIAutoLowestBatchJokerjoe(armDigit, pct);
        return;
      }
    }

    const nextTouches = {};
    const prevTouches = state.aiLowestTouches || {};
    Object.keys(prevTouches).forEach((k) => {
      const d = Number(k);
      if (eligibleMap.has(d)) nextTouches[d] = Object.assign({}, prevTouches[k]);
    });
    state.aiLowestTouches = nextTouches;

    if (!state.aiLowestBatchActive && !state.aiLowestSubmitting && !state.aiLowestArmed && now >= (state.aiLowestCooldownUntil || 0)) {
      if (eligibleMap.has(lastDigit)) {
        const t = state.aiLowestTouches[lastDigit] || {};
        t.touchedTick = tickCount;
        if (t.validSinceTick == null) t.validSinceTick = null;
        state.aiLowestTouches[lastDigit] = t;
      }

      const valid = [];
      Object.keys(state.aiLowestTouches).forEach((k) => {
        const d = Number(k);
        const t = state.aiLowestTouches[d] || {};
        if (!eligibleMap.has(d)) return;
        if (d === lastDigit) return;
        if (t.touchedTick == null) return;
        if (t.validSinceTick == null) t.validSinceTick = tickCount;
        valid.push({ digit: d, pct: Number(eligibleMap.get(d)), validSinceTick: Number(t.validSinceTick) || tickCount });
      });

      let chosen = null;
      if (valid.length) {
        if (state.aiLowestRecoveryOnly) {
          const lowest = eligible[0];
          if (lowest) {
            chosen = valid.filter((x) => x.digit === lowest.digit).sort((a, b) => a.validSinceTick - b.validSinceTick)[0] || null;
          }
        } else {
          valid.sort((a, b) => (a.validSinceTick - b.validSinceTick) || (a.pct - b.pct) || (a.digit - b.digit));
          chosen = valid[0] || null;
        }
      }

      if (chosen) {
        state.aiLowestArmed = { digit: Number(chosen.digit), pctAtArm: Number(chosen.pct), armedAtTick: tickCount, tradeOnTick: tickCount + 1 };
        state.aiLowestTouches = {};
      }
    } else if (eligibleMap.has(lastDigit)) {
      const t = state.aiLowestTouches[lastDigit] || {};
      t.touchedTick = tickCount;
      state.aiLowestTouches[lastDigit] = t;
    }

    updateAIAutoModeModalUiJokerjoe();
  }

  function onJokerjoeTradeResultForLowestAI(entry) {
    if (!entry || !state.aiLowestBatchActive || !state.aiAutoLowestLocalOn) return;
    if (String(entry.profile || "") !== PROFILE) return;
    const type = String(entry.type || entry.contract_type || "").toUpperCase();
    if (type !== "DIFFERS" && type !== "DIGITDIFF") return;
    const barrier = Number(entry.barrier);
    if (!Number.isInteger(barrier) || barrier !== Number(state.aiLowestBatchBarrier)) return;
    if ((state.aiLowestBatchPending || 0) <= 0) return;

    state.aiLowestBatchPending -= 1;
    const p = Number(entry.profit);
    if (!Number.isNaN(p)) state.aiLowestBatchProfit += p;

    if (state.aiLowestBatchPending <= 0) {
      const batchProfit = Number(state.aiLowestBatchProfit || 0);
      state.aiLowestBatchActive = false;
      state.aiLowestBatchBarrier = null;
      state.aiLowestBatchPending = 0;
      state.aiLowestCooldownUntil = Date.now() + 10000;

      if (batchProfit < 0) {
        state.aiLowestRecoveryDeficit = Number((state.aiLowestRecoveryDeficit || 0) + Math.abs(batchProfit));
        state.aiLowestRecoveryOnly = true;
      } else if (batchProfit > 0 && state.aiLowestRecoveryOnly) {
        state.aiLowestRecoveryDeficit = Number((state.aiLowestRecoveryDeficit || 0) - batchProfit);
        if (state.aiLowestRecoveryDeficit <= 0) {
          state.aiLowestRecoveryDeficit = 0;
          state.aiLowestRecoveryOnly = false;
        }
      }

      safeToast(`🤖AI Lowest % batch done: ${batchProfit >= 0 ? "+" : ""}${batchProfit.toFixed(2)}${state.aiLowestRecoveryOnly ? ` • Recovery $${Number(state.aiLowestRecoveryDeficit || 0).toFixed(2)} left` : ""}`, batchProfit >= 0 ? "success" : "error");
      updateAIAutoModeModalUiJokerjoe();
    }
  }

  function updateMatchSniper5xButtonJokerjoe() {
    const btn = getEl("matchSniper5xBtnJokerjoe");
    if (!btn) return;
    btn.innerText = `🎯 MatchSniper 5x: ${state.matchSniper5xOn ? "ON" : "OFF"}`;
    btn.style.background = state.matchSniper5xOn ? "#22c55e" : "#1e293b";
  }

  function updateMatchSniper5xStatusJokerjoe(sorted) {
    const el = getEl("matchSniper5xStatusJokerjoe");
    if (!el) return;
    const now = Date.now();
    const cdMs = Math.max(0, (state.matchSniper5xCooldownUntil || 0) - now);
    const data = Array.isArray(sorted) ? sorted : (Array.isArray(state.matchesSorted) ? state.matchesSorted : []);
    if (!state.matchSniper5xOn) {
      el.style.color = "#94a3b8";
      el.innerText = "OFF • Top 5 MATCHES digits • same-tick batch • 10s cooldown";
      return;
    }
    if (state.matchSniper5xBusy) {
      el.style.color = "#38bdf8";
      el.innerText = "Placing 5 MATCHES trades (same tick request)…";
      return;
    }
    if (cdMs > 0) {
      el.style.color = "#facc15";
      el.innerText = `Cooldown: ${(cdMs/1000).toFixed(1)}s • waiting for next top-5 set`;
      return;
    }
    if (!data || data.length < 5) {
      el.style.color = "#94a3b8";
      el.innerText = "Armed • waiting for top 5 MATCHES digits";
      return;
    }
    const top5 = data.slice(0,5).map(x => `${x.digit} (${Number(x.pct).toFixed(1)}%)`).join(", ");
    el.style.color = "#22c55e";
    el.innerText = `ARMED • Top 5 = ${top5}`;
  }

  async function tryMatchSniper5xTradeJokerjoe(sorted) {
    if (!state.matchSniper5xOn || state.matchSniper5xBusy) return;
    const now = Date.now();
    if ((state.matchSniper5xCooldownUntil || 0) > now) return;
    if (!Array.isArray(sorted) || sorted.length < 5) return;
    const top5 = sorted.slice(0, 5).map((x) => ({ digit: Number(x.digit), pct: Number(x.pct) }));
    const uniq = Array.from(new Set(top5.map(x => x.digit)));
    if (uniq.length < 5) return;
    const key = top5.map(x => `${x.digit}:${x.pct.toFixed(1)}`).join("|");
    if (state.matchSniper5xLastTopKey === key) return;

    state.matchSniper5xBusy = true;
    updateMatchSniper5xStatusJokerjoe(sorted);
    try {
      const r = await placeBatchManualTradesJokerjoe("MATCHES", top5.map(x => x.digit));
      if (r.placed === 5) {
        state.matchSniper5xLastTopKey = key;
        state.matchSniper5xCooldownUntil = Date.now() + 10000;
        safeToast(`🎯 MatchSniper 5x: MATCHES ${top5.map(x => x.digit).join(', ')} (same-tick request)`, "success");
      } else {
        safeToast(`🎯 MatchSniper 5x partial (${r.placed}/5)`, "error");
      }
    } catch (e) {
      safeToast("🎯 MatchSniper 5x failed", "error");
    } finally {
      state.matchSniper5xBusy = false;
      updateMatchSniper5xStatusJokerjoe(sorted);
    }
  }

  function updateMatchesAnalysisButtonJokerjoe() {
    const btn = getEl("matchesAnalysisBtnJokerjoe");
    const panel = getEl("matchesAnalysisPanelJokerjoe");
    if (btn) {
      btn.innerText = `🎯 MATCHES ANALYSIS: ${state.matchesAnalysisOn ? "ON" : "OFF"}`;
      btn.style.background = state.matchesAnalysisOn ? "#22c55e" : "#1e293b";
    }
    if (panel) panel.style.display = state.matchesAnalysisOn ? "block" : "none";
  }

  function updateMatchSniperButtonJokerjoe() {
    const btn = getEl("matchSniperBtnJokerjoe");
    if (!btn) return;
    btn.innerText = `🎯 MatchSniper 1x: ${state.matchSniperOn ? "ON" : "OFF"}`;
    btn.style.background = state.matchSniperOn ? "#22c55e" : "#1e293b";
  }

  function updateMatchSniperStatusJokerjoe(snapshot) {
    const el = getEl("matchSniperStatusJokerjoe");
    if (!el) return;
    const now = Date.now();
    const cdMs = Math.max(0, (state.matchSniperCooldownUntil || 0) - now);
    const cd = (cdMs / 1000).toFixed(1);
    const s = snapshot || state.matchesSnapshot;
    if (!state.matchSniperOn) {
      el.style.color = "#94a3b8";
      el.innerText = "OFF • Strong signal only • 10s cooldown • 1 trade per signal";
      return;
    }
    if (state.matchSniperBusy) {
      el.style.color = "#38bdf8";
      el.innerText = "Placing 1 MATCHES trade…";
      return;
    }
    if (cdMs > 0) {
      el.style.color = "#facc15";
      el.innerText = `Cooldown: ${cd}s • waiting for next strong signal`;
      return;
    }
    if (!s || !s.hasData) {
      el.style.color = "#94a3b8";
      el.innerText = "Armed • waiting for data / warm-up";
      return;
    }
    if (!s.strong) {
      el.style.color = "#fb7185";
      el.innerText = `Armed • waiting for strong signal (need top% ≥ 12 and gap ≥ 2)`;
      return;
    }
    if (state.matchSniperConsumed && String(state.matchSniperActiveDigit) === String(s.topDigit)) {
      el.style.color = "#38bdf8";
      el.innerText = `Signal used on digit ${s.topDigit} • waiting for a new strong signal`;
      return;
    }
    el.style.color = "#22c55e";
    el.innerText = `ARMED • Strong signal ${s.topDigit} (${s.topPct.toFixed(1)}%, gap ${s.gap.toFixed(1)}%)`;
  }

  function setBarrierForMatchDigitJokerjoe(digit) {
    const d = Number(digit);
    if (!Number.isInteger(d) || d < 0 || d > 9) return;
    const barrier = getEl("barrier");
    if (barrier) {
      barrier.value = String(d);
      try { barrier.dispatchEvent(new Event("change", { bubbles: true })); } catch (e) {}
      try { barrier.dispatchEvent(new Event("blur", { bubbles: true })); } catch (e) {}
    }
  }

  function tryMatchSniperTradeJokerjoe(snapshot) {
    try {
      if (!state.matchSniperOn || !snapshot || !snapshot.strong) { updateMatchSniperStatusJokerjoe(snapshot); return; }
      const now = Date.now();
      if ((state.matchSniperCooldownUntil || 0) > now) { updateMatchSniperStatusJokerjoe(snapshot); return; }
      const topDigit = String(snapshot.topDigit);
      if (state.matchSniperActiveDigit === null || state.matchSniperActiveDigit !== topDigit) {
        state.matchSniperActiveDigit = topDigit;
        state.matchSniperConsumed = false;
      }
      if (state.matchSniperConsumed || state.matchSniperBusy) { updateMatchSniperStatusJokerjoe(snapshot); return; }
      if (typeof window.trade !== "function") { updateMatchSniperStatusJokerjoe(snapshot); return; }

      state.matchSniperBusy = true;
      updateMatchSniperStatusJokerjoe(snapshot);
      setBarrierForMatchDigitJokerjoe(snapshot.topDigit);
      try { window.trade("MATCHES"); } catch (e) { safeToast("MatchSniper trade failed", "error"); }
      state.matchSniperConsumed = true;
      state.matchSniperCooldownUntil = now + 10000;
      safeToast(`🎯 MatchSniper 1x took MATCHES ${snapshot.topDigit} (${snapshot.topPct.toFixed(1)}%, gap ${snapshot.gap.toFixed(1)}%)`, "success");
      setTimeout(() => { state.matchSniperBusy = false; updateMatchSniperStatusJokerjoe(); }, 700);
      updateMatchSniperStatusJokerjoe(snapshot);
    } catch (e) {
      state.matchSniperBusy = false;
      updateMatchSniperStatusJokerjoe(snapshot);
    }
  }

  function evaluateMatchSniperSignalJokerjoe(sorted) {
    if (!Array.isArray(sorted) || !sorted.length) {
      state.matchesSnapshot = { hasData: false, strong: false };
      // Reset signal cycle if no data
      state.matchSniperActiveDigit = null;
      state.matchSniperConsumed = false;
      updateMatchSniperStatusJokerjoe();
    updateMatchSniper5xButtonJokerjoe();
    updateMatchSniper5xStatusJokerjoe();
    updateAIAutoModeModalUiJokerjoe();
    updateMatchSniper5xButtonJokerjoe();
    updateMatchSniper5xStatusJokerjoe();
    updateAIAutoModeModalUiJokerjoe();
    updateMatchSniper5xButtonJokerjoe();
    updateMatchSniper5xStatusJokerjoe();
    updateAIAutoModeModalUiJokerjoe();
      return;
    }
    const top = sorted[0];
    const second = sorted[1] || { pct: 0 };
    const gap = Math.max(0, Number(top.pct || 0) - Number(second.pct || 0));
    const topPct = Number(top.pct || 0);
    const strong = topPct >= 12 && gap >= 2;
    state.matchesSnapshot = { hasData: true, strong, topDigit: Number(top.digit), topPct, gap };

    if (!strong) {
      // New cycle can start only after strong signal disappears
      state.matchSniperActiveDigit = null;
      state.matchSniperConsumed = false;
      updateMatchSniperStatusJokerjoe(state.matchesSnapshot);
      return;
    }

    // Strong signal present; only one trade per strong signal cycle / top digit
    tryMatchSniperTradeJokerjoe(state.matchesSnapshot);
    updateMatchSniperStatusJokerjoe(state.matchesSnapshot);
  }

  function classifyMatchesEdge(gap) {
    const g = Number(gap) || 0;
    if (g >= 3) return { label: "Strong Edge", color: "#22c55e" };
    if (g >= 1.5) return { label: "Medium Edge", color: "#facc15" };
    return { label: "Weak Edge / WAIT", color: "#fb7185" };
  }

  function renderMatchesAnalysisJokerjoe(entries, opts) {
    const statusEl = getEl("matchesAnalysisStatusJokerjoe");
    const top3Wrap = getEl("matchesTop3Jokerjoe");
    const edgeLabelEl = getEl("matchesEdgeLabelJokerjoe");

    if (!state.matchesAnalysisOn) return;

    if (!entries || !entries.length) {
      setText("matchesBestDigitJokerjoe", "-");
      setText("matchesBestPctJokerjoe", "--%");
      setText("matchesEdgeGapJokerjoe", "--%");
      if (edgeLabelEl) { edgeLabelEl.innerText = "Waiting"; edgeLabelEl.style.color = "#94a3b8"; }
      if (statusEl) statusEl.innerText = (opts && opts.status) || "Warm-up / waiting for digit %";
      if (top3Wrap) top3Wrap.innerHTML = '<div style="color:#64748b; font-size:12px;">Warm-up…</div>';
      state.matchesSorted = [];
      evaluateMatchSniperSignalJokerjoe([]);
      updateMatchSniper5xStatusJokerjoe([]);
      return;
    }

    const sorted = entries
      .filter(x => x && x.digit !== undefined && x.pct !== undefined && !Number.isNaN(Number(x.pct)))
      .map(x => ({ digit: Number(x.digit), pct: Number(x.pct) }))
      .sort((a, b) => b.pct - a.pct);

    if (!sorted.length) {
      return renderMatchesAnalysisJokerjoe([], { status: "Warm-up / waiting for digit %" });
    }

    const top = sorted[0];
    const second = sorted[1] || { pct: 0 };
    const gap = Math.max(0, (top.pct || 0) - (second.pct || 0));
    const edge = classifyMatchesEdge(gap);

    setText("matchesBestDigitJokerjoe", String(top.digit));
    setText("matchesBestPctJokerjoe", `${top.pct.toFixed(1)}%`);
    setText("matchesEdgeGapJokerjoe", `${gap.toFixed(1)}%`);
    if (edgeLabelEl) {
      edgeLabelEl.innerText = edge.label;
      edgeLabelEl.style.color = edge.color;
    }
    if (statusEl) statusEl.innerText = (opts && opts.status) || "Live";

    if (top3Wrap) {
      const top3 = sorted.slice(0, 3);
      top3Wrap.innerHTML = top3.map((row, idx) => {
        const rankColor = idx === 0 ? "#22c55e" : idx === 1 ? "#38bdf8" : "#a78bfa";
        return `
          <div style="display:flex; align-items:center; gap:8px; background:#111827; border:1px solid #334155; border-radius:999px; padding:6px 10px;">
            <span style="display:inline-flex; align-items:center; justify-content:center; width:18px; height:18px; border-radius:999px; background:${rankColor}; color:#020617; font-weight:800; font-size:11px;">${idx + 1}</span>
            <span style="font-weight:700;">${row.digit}</span>
            <span style="color:#94a3b8; font-size:12px;">${row.pct.toFixed(1)}%</span>
          </div>
        `;
      }).join("");
    }

    state.matchesLastKey = sorted.map(x => `${x.digit}:${x.pct.toFixed(1)}`).join("|");
    state.matchesSorted = sorted.slice();
    evaluateMatchSniperSignalJokerjoe(sorted);
    tryMatchSniper5xTradeJokerjoe(sorted);
    updateMatchSniper5xStatusJokerjoe(sorted);
  }

  function parseMatchesEntriesFromDigitAnalysisPayloadJokerjoe(data) {
    if (!data) return null;

    // Common formats: {digit_percentages:{0:..}}, {digit_percentages:[..]}, {percentages:[..]}
    const candidates = [data.digit_percentages, data.percentages, data.digitPercents, data.digit_percent];
    for (const src of candidates) {
      if (!src) continue;
      if (Array.isArray(src)) {
        const arr = [];
        src.forEach((item, idx) => {
          if (typeof item === "number") arr.push({ digit: idx, pct: Number(item) });
          else if (item && typeof item === "object") {
            const d = item.digit ?? item.number ?? item.n ?? idx;
            const p = item.pct ?? item.percent ?? item.percentage ?? item.value;
            if (d !== undefined && p !== undefined) arr.push({ digit: d, pct: Number(p) });
          }
        });
        if (arr.length) return arr;
      } else if (typeof src === "object") {
        const arr = [];
        Object.keys(src).forEach((k) => {
          const v = src[k];
          if (v && typeof v === "object") {
            const p = v.pct ?? v.percent ?? v.percentage ?? v.value;
            const d = v.digit ?? v.number ?? k;
            if (p !== undefined) arr.push({ digit: d, pct: Number(p) });
          } else if (!Number.isNaN(Number(v))) {
            arr.push({ digit: Number(k), pct: Number(v) });
          }
        });
        if (arr.length) return arr;
      }
    }
    return null;
  }

  function parseMatchesEntriesFromDiffersDomJokerjoe() {
    const row = getEl("differsDigitsRow");
    if (!row) return [];
    const cards = Array.from(row.children || []);
    const out = [];
    const seen = new Set();

    for (const card of cards) {
      const text = (card.innerText || card.textContent || "").replace(/\s+/g, " ").trim();
      if (!text) continue;

      // Try explicit data attrs first
      let digit = card.dataset && (card.dataset.digit ?? card.getAttribute("data-digit"));
      let pct = card.dataset && (card.dataset.pct ?? card.getAttribute("data-pct") ?? card.getAttribute("data-percent"));

      if (digit == null || pct == null) {
        const digitMatch = text.match(/(?:^|\D)([0-9])(?:\D|$)/);
        const pctMatch = text.match(/(\d+(?:\.\d+)?)\s*%/);
        if (digit == null && digitMatch) digit = digitMatch[1];
        if (pct == null && pctMatch) pct = pctMatch[1];
      }

      const d = Number(digit);
      const p = Number(pct);
      if (Number.isInteger(d) && d >= 0 && d <= 9 && !Number.isNaN(p)) {
        if (!seen.has(d)) {
          out.push({ digit: d, pct: p });
          seen.add(d);
        }
      }
    }
    return out;
  }

  function refreshMatchesAnalysisJokerjoe(data) {
    if (!state.matchesAnalysisOn) return;
    const fromPayload = parseMatchesEntriesFromDigitAnalysisPayloadJokerjoe(data);
    if (fromPayload && fromPayload.length) {
      return renderMatchesAnalysisJokerjoe(fromPayload, { status: "Live" });
    }
    const fromDom = parseMatchesEntriesFromDiffersDomJokerjoe();
    renderMatchesAnalysisJokerjoe(fromDom, { status: fromDom && fromDom.length ? "Live" : "Warm-up / waiting for digit %" });
  }

  function bindMatchesAnalysisObserverJokerjoe() {
    if (state.matchesObserverBound) return;
    const row = getEl("differsDigitsRow");
    if (!row || typeof MutationObserver === "undefined") return;
    const obs = new MutationObserver(() => {
      if (state.matchesAnalysisOn) refreshMatchesAnalysisJokerjoe();
    });
    obs.observe(row, { childList: true, subtree: true, characterData: true });
    state.matchesObserverBound = true;
  }

  window.toggleMatchesAnalysisJokerjoe = function () {
    state.matchesAnalysisOn = !state.matchesAnalysisOn;
    updateMatchesAnalysisButtonJokerjoe();
    updateMatchSniperButtonJokerjoe();
    updateMatchSniperStatusJokerjoe();
    updateMatchSniper5xButtonJokerjoe();
    updateMatchSniper5xStatusJokerjoe();
    bindMatchesAnalysisObserverJokerjoe();
    if (state.matchesAnalysisOn) refreshMatchesAnalysisJokerjoe();
  };


  window.toggleMatchSniperJokerjoe = function () {
    state.matchSniperOn = !state.matchSniperOn;
    if (state.matchSniperOn && !state.matchesAnalysisOn) {
      state.matchesAnalysisOn = true;
      updateMatchesAnalysisButtonJokerjoe();
    }
    updateMatchSniperButtonJokerjoe();
    bindMatchesAnalysisObserverJokerjoe();
    refreshMatchesAnalysisJokerjoe();
    updateMatchSniperStatusJokerjoe();
    updateMatchSniper5xStatusJokerjoe();
    safeToast(`🎯 MatchSniper 1x: ${state.matchSniperOn ? "ON" : "OFF"}`, state.matchSniperOn ? "success" : "error");
  };

  window.toggleMatchSniper5xJokerjoe = function () {
    state.matchSniper5xOn = !state.matchSniper5xOn;
    if (state.matchSniper5xOn && !state.matchesAnalysisOn) {
      state.matchesAnalysisOn = true;
      updateMatchesAnalysisButtonJokerjoe();
    }
    if (!state.matchSniper5xOn) {
      state.matchSniper5xBusy = false;
    }
    updateMatchSniper5xButtonJokerjoe();
    bindMatchesAnalysisObserverJokerjoe();
    refreshMatchesAnalysisJokerjoe();
    updateMatchSniper5xStatusJokerjoe();
    safeToast(`🎯 MatchSniper 5x: ${state.matchSniper5xOn ? "ON" : "OFF"}`, state.matchSniper5xOn ? "success" : "error");
  };



  async function postJSON(url, body) {
    const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
    let data = {};
    try { data = await res.json(); } catch (e) {}
    return { ok: res.ok, data };
  }

  function currentBarrier() {
    const el = document.getElementById("barrier");
    let b = parseInt((el && el.value) || "5", 10);
    if (isNaN(b)) b = 5;
    if (b < 0) b = 0;
    if (b > 9) b = 9;
    return b;
  }

  function updateButtons() {
    const kidGxBtn = document.getElementById("kidGxBtnJokerjoe");
    const aiBtn = document.getElementById("aiAutoTradingBtnJokerjoe");
    if (kidGxBtn) {
      const on = !!state.autoModes.kidgx;
      kidGxBtn.innerText = on ? `⚡kidGx ${state.kidgxBarrier}: ON` : `⚡kidGx ${state.kidgxBarrier}`;
      kidGxBtn.style.background = on ? "#22c55e" : "#1e293b";
    }
    if (aiBtn) {
      const on = isAIAutoOnJokerjoe();
      aiBtn.innerText = `🤖AI AUTO-TRADING: ${on ? "ON" : "OFF"}`;
      aiBtn.style.background = on ? "#22c55e" : "#1e293b";
    }
    updateAdvancedAIModeButtonsJokerjoe();
  }


function updateAdvancedAIModeButtonsJokerjoe(payload) {
  const map = [
    ["kidbrain", "kidbrainBtnJokerjoe", "🤖 KIDBRAIN"],
    ["edge_brain", "edgeBrainBtnJokerjoe", "🧠 EDGE BRAIN"],
    ["smart_flow", "smartFlowBtnJokerjoe", "🎯 SMART FLOW"],
    ["meta_ai", "metaAiBtnJokerjoe", "⚡ META AI"],
    ["kidracks_ai", "kidracksAiBtnJokerjoe", "🤓 KIDRACKS AI"],
  ];
  map.forEach(([key, id, label]) => {
    const btn = document.getElementById(id);
    if (!btn || !(key in (state.autoModes || {}))) return;
    const on = !!state.autoModes[key];
    btn.innerText = `${label}: ${on ? "ON" : "OFF"}`;
    btn.style.background = on ? "#22c55e" : "#1e293b";
  });
  const info = document.getElementById("metaBrainInfoJokerjoe");
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

  function bindSocketListeners() {
    try {
      if (typeof socket === "undefined" || !socket) return;
      if (state.lastSocket === socket && state.socketBound) return;
      state.lastSocket = socket;
      state.socketBound = true;

      socket.on("digit_analysis", (data) => {
        if (!isActive() || !data) return;
        if (data.auto_modes) state.autoModes = Object.assign({}, state.autoModes, data.auto_modes);
        if (data.auto_settings && data.auto_settings.kidgx_barrier !== undefined) state.kidgxBarrier = Number(data.auto_settings.kidgx_barrier);
        if (data.meta_brain) state.metaBrain = data.meta_brain;
        updateButtons();
        updateAdvancedAIModeButtonsJokerjoe(data);
        processAIAutoLowestTickJokerjoe(data);
        refreshMatchesAnalysisJokerjoe(data);
      });

      socket.on("auto_mode_update", (modes) => {
        if (!isActive()) return;
        state.autoModes = Object.assign({}, state.autoModes, modes || {});
        updateButtons();
        updateAdvancedAIModeButtonsJokerjoe();
      });

      socket.on("trade_result", (entry) => {
        if (!isActive()) return;
        onJokerjoeTradeResultForLowestAI(entry || {});
      });
    } catch (e) {}
  }

  function bindBarrierSync() {
    const input = document.getElementById("barrier");
    if (!input || input.dataset.kidgxSyncBound === "1") return;
    input.dataset.kidgxSyncBound = "1";
    const sync = async () => {
      state.kidgxBarrier = currentBarrier();
      updateButtons();
      try { await postJSON("/set_kidgx_barrier", { barrier: state.kidgxBarrier }); } catch (e) {}
    };
    input.addEventListener("change", sync);
    input.addEventListener("blur", sync);
    setTimeout(sync, 150);
  }

  function patchKidgambleConfirm() {
    if (window.__kidgambleXConfirmPatched) return;
    if (typeof window.kidgambleX !== "function") return;
    const original = window.kidgambleX;
    window.kidgambleX = async function () {
      const ok = window.confirm("This button places 3 matches trades. Do you want to confirm?\n\nYes = continue\nNo = cancel");
      if (!ok) return;
      return original.apply(this, arguments);
    };
    window.__kidgambleXConfirmPatched = true;
  }

  async function onMount() {
    try { App().ensureDigitClickPatchSoon && App().ensureDigitClickPatchSoon(); } catch (e) {}
    try { App().applyDigitSelectionUI && App().applyDigitSelectionUI(); } catch (e) {}
    patchKidgambleConfirm();
    try { const m = getEl("aiAutoModeModalJokerjoe"); if (m && m.dataset.bound !== "1") { m.dataset.bound = "1"; m.addEventListener("click", (ev) => { if (ev.target === m) closeAIAutoModeModalJokerjoe(); }); } } catch (e) {}
    bindSocketListeners();
    bindBarrierSync();
    bindMatchesAnalysisObserverJokerjoe();
    updateButtons();
    updateMatchesAnalysisButtonJokerjoe();
    updateMatchSniperButtonJokerjoe();
    updateMatchSniperStatusJokerjoe();
    updateMatchSniper5xButtonJokerjoe();
    updateMatchSniper5xStatusJokerjoe();
    updateAIAutoModeModalUiJokerjoe();
  }

  async function afterLoadProfileUI() {
    try { App().applyDigitSelectionUI && App().applyDigitSelectionUI(); } catch (e) {}
    patchKidgambleConfirm();
    bindSocketListeners();
    bindBarrierSync();
    bindMatchesAnalysisObserverJokerjoe();
    updateButtons();
    updateMatchesAnalysisButtonJokerjoe();
    updateMatchSniperButtonJokerjoe();
    updateMatchSniperStatusJokerjoe();
    updateMatchSniper5xButtonJokerjoe();
    updateMatchSniper5xStatusJokerjoe();
    updateAIAutoModeModalUiJokerjoe();
  }

  async function onActivate() {
    try { App().applyDigitSelectionUI && App().applyDigitSelectionUI(); } catch (e) {}
    patchKidgambleConfirm();
    bindSocketListeners();
    bindBarrierSync();
    bindMatchesAnalysisObserverJokerjoe();
    state.kidgxBarrier = currentBarrier();
    updateButtons();
    updateMatchesAnalysisButtonJokerjoe();
    updateMatchSniperButtonJokerjoe();
    updateMatchSniperStatusJokerjoe();
    updateMatchSniper5xButtonJokerjoe();
    updateMatchSniper5xStatusJokerjoe();
    updateAIAutoModeModalUiJokerjoe();
    refreshMatchesAnalysisJokerjoe();
  }

  window.toggleKidGxJokerjoe = async function () {
    state.kidgxBarrier = currentBarrier();
    const r = await postJSON("/toggle_kidgx_auto", { profile: "JOKERJOE", barrier: state.kidgxBarrier });
    if (r.data && r.data.status === "success") {
      state.autoModes.kidgx = !!r.data.kidgx_auto;
      if (r.data.barrier !== undefined) state.kidgxBarrier = Number(r.data.barrier);
      updateButtons();
      safeToast(`⚡kidGx ${state.autoModes.kidgx ? "ON" : "OFF"} @ ${state.kidgxBarrier}`, state.autoModes.kidgx ? "success" : "error");
    } else {
      safeToast((r.data && r.data.message) || "⚡kidGx failed", "error");
    }
  };

  window.toggleAIAutoTradingJokerjoe = async function () {
    const currentlyOn = isAIAutoOnJokerjoe();

    // If currently ON, turn off whichever mode is active
    if (currentlyOn) {
      if (state.aiAutoLowestLocalOn) {
        state.aiAutoLowestLocalOn = false;
        resetAIAutoLowestStateJokerjoe();
        closeAIAutoModeModalJokerjoe();
        updateButtons();
        safeToast("🤖AI AUTO-TRADING: OFF", "error");
        return;
      }

      const rOff = await postJSON("/toggle_ai_auto_trading", { profile: "JOKERJOE" });
      if (rOff.data && rOff.data.status === "success") {
        state.autoModes.ai_auto_trading = !!rOff.data.ai_auto_trading;
        updateButtons();
        safeToast(`🤖AI AUTO-TRADING: ${state.autoModes.ai_auto_trading ? "ON" : "OFF"}`, state.autoModes.ai_auto_trading ? "success" : "error");
      } else {
        safeToast((rOff.data && rOff.data.message) || "AI auto failed", "error");
      }
      return;
    }

    openAIAutoModeModalJokerjoe();
  };

  window.selectAIAutoModeJokerjoe = async function (mode) {
    const chosen = normalizeAIAutoModeJokerjoe(mode);
    state.aiAutoModeChoice = chosen;
    updateAIAutoModeModalUiJokerjoe();

    if (chosen === "lowest_pct") {
      // Ensure backend AI AUTO is off before local lowest mode starts
      if (state.autoModes.ai_auto_trading) {
        const rOff = await postJSON("/toggle_ai_auto_trading", { profile: "JOKERJOE" });
        if (rOff.data && rOff.data.status === "success") state.autoModes.ai_auto_trading = !!rOff.data.ai_auto_trading;
      }
      resetAIAutoLowestStateJokerjoe();
      state.aiAutoLowestLocalOn = true;
      closeAIAutoModeModalJokerjoe();
      updateButtons();
      safeToast("🤖AI AUTO-TRADING: ON (Lowest % mode)", "success");
      return;
    }

    // Golden Digits mode (existing backend AI AUTO)
    state.aiAutoLowestLocalOn = false;
    resetAIAutoLowestStateJokerjoe();
    if (!state.autoModes.ai_auto_trading) {
      const rOn = await postJSON("/toggle_ai_auto_trading", { profile: "JOKERJOE" });
      if (rOn.data && rOn.data.status === "success") {
        state.autoModes.ai_auto_trading = !!rOn.data.ai_auto_trading;
      } else {
        safeToast((rOn.data && rOn.data.message) || "AI auto failed", "error");
        return;
      }
    }
    closeAIAutoModeModalJokerjoe();
    updateButtons();
    safeToast("🤖AI AUTO-TRADING: ON (Golden Digits)", "success");
  };

  window.closeAIAutoModeModalJokerjoe = function () {
    closeAIAutoModeModalJokerjoe();
  };


async function toggleAdvancedModeJokerjoe(modeKey, label) {
  const r = await postJSON("/toggle_named_ai_mode", { profile: "JOKERJOE", mode_key: modeKey });
  if (r.data && r.data.status === "success") {
    if (r.data.auto_modes) state.autoModes = Object.assign({}, state.autoModes || {}, r.data.auto_modes);
    if (r.data.payload && r.data.payload.meta_brain) state.metaBrain = r.data.payload.meta_brain;
    updateButtons();
    updateAdvancedAIModeButtonsJokerjoe(r.data.payload || null);
    safeToast(`${label}: ${r.data.enabled ? "ON" : "OFF"}`, r.data.enabled ? "success" : "error");
  } else {
    safeToast((r.data && r.data.message) || `${label} failed`, "error");
  }
}

window.toggleKidbrainJokerjoe = function () { return toggleAdvancedModeJokerjoe("kidbrain", "🤖 KIDBRAIN"); };
window.toggleEdgeBrainJokerjoe = function () { return toggleAdvancedModeJokerjoe("edge_brain", "🧠 EDGE BRAIN"); };
window.toggleSmartFlowJokerjoe = function () { return toggleAdvancedModeJokerjoe("smart_flow", "🎯 SMART FLOW"); };
window.toggleMetaAIJokerjoe = function () { return toggleAdvancedModeJokerjoe("meta_ai", "⚡ META AI"); };
window.toggleKidracksAIJokerjoe = function () { return toggleAdvancedModeJokerjoe("kidracks_ai", "🤓 KIDRACKS AI"); };

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
  setInterval(() => { try { if (isActive() && (state.matchesAnalysisOn || state.matchSniperOn || state.matchSniper5xOn)) { refreshMatchesAnalysisJokerjoe(); updateMatchSniperStatusJokerjoe(); updateMatchSniper5xStatusJokerjoe(); updateAIAutoModeModalUiJokerjoe(); } } catch (e) {} }, 1000);

})();