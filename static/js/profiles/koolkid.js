(function () {
  const PROFILE = "KOOLKID";
  const FAST_INTERVAL_MS_NORMAL = 400; // 0.4s as requested
  const FAST_INTERVAL_MS_TURBO = 120;  // faster Turbo lane for KOOLKID
  const FAST_MAX_BUY_QUEUE = 12;       // safety limit
  const state = {
    lastSocket: null,
    socketBound: false,
    barrierAnalysis: null,
    over3Analysis: null,
    goldenCard: null,
    kid2vix: null,
    goldenCardTradeBusy: false,
    autoModes: {},
    turboMode: loadTurboModeKoolkid(),
    dual2xOpen: false,
    dual2xBusy: false,
    dual2xAnalysis: { tickCount: 0, pctByDigit: null, ready: false },
  };
  const fastBuyQueueKoolkid = { items: [], running: false, lastRunAt: 0 };

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

  function nextPaintFrame() {
    return new Promise((resolve) => {
      try {
        requestAnimationFrame(() => resolve());
      } catch (e) {
        setTimeout(resolve, 0);
      }
    });
  }

  function showCenteredPopupKoolkid(id) {
    const popup = document.getElementById(id);
    if (!popup) return null;
    popup.style.visibility = "hidden";
    popup.style.display = "block";
    popup.style.left = "50%";
    popup.style.top = "50%";
    popup.style.transform = "translate(-50%, -50%)";
    popup.style.visibility = "visible";
    return popup;
  }

  function hideCenteredPopupKoolkid(id) {
    const popup = document.getElementById(id);
    if (!popup) return;
    popup.style.display = "none";
    popup.style.visibility = "";
    popup.style.left = "";
    popup.style.top = "";
    popup.style.transform = "";
  }

  function getFastIntervalMsKoolkid() {
    return currentTurboModeKoolkid() ? FAST_INTERVAL_MS_TURBO : FAST_INTERVAL_MS_NORMAL;
  }

  function delayFastBuyMsKoolkid(ms) {
    const waitMs = Math.max(0, Number(ms) || 0);
    if (waitMs <= 0) return Promise.resolve();
    return new Promise((resolve) => setTimeout(resolve, waitMs));
  }

  async function runFastBuyQueueKoolkid() {
    if (fastBuyQueueKoolkid.running) return;
    fastBuyQueueKoolkid.running = true;
    try {
      while ((fastBuyQueueKoolkid.items || []).length) {
        const item = fastBuyQueueKoolkid.items.shift();
        if (!item || typeof item.task !== "function") continue;
        const intervalMs = getFastIntervalMsKoolkid();
        const elapsedMs = Date.now() - Number(fastBuyQueueKoolkid.lastRunAt || 0);
        if (fastBuyQueueKoolkid.lastRunAt) {
          if (elapsedMs < intervalMs) await delayFastBuyMsKoolkid(intervalMs - elapsedMs);
        }
        try {
          const result = await item.task();
          item.resolve(result);
        } catch (err) {
          item.reject(err);
        } finally {
          fastBuyQueueKoolkid.lastRunAt = Date.now();
        }
      }
    } finally {
      fastBuyQueueKoolkid.running = false;
    }
  }

  function enqueueFastBuyKoolkid(task) {
    if (typeof task !== "function") return Promise.resolve();
    const queuedCount = Number((fastBuyQueueKoolkid.items || []).length || 0);
    const inFlightCount = fastBuyQueueKoolkid.running ? 1 : 0;
    if ((queuedCount + inFlightCount) >= FAST_MAX_BUY_QUEUE) {
      return Promise.reject(new Error(`Fast buy queue is full (${FAST_MAX_BUY_QUEUE})`));
    }
    return new Promise((resolve, reject) => {
      fastBuyQueueKoolkid.items.push({ task, resolve, reject });
      runFastBuyQueueKoolkid();
    });
  }

  function turboStorageKeyKoolkid() {
    return "profileTurbo:KOOLKID";
  }

  function loadTurboModeKoolkid() {
    const app = App();
    if (app && typeof app.getProfileTurboEnabled === "function") {
      return !!app.getProfileTurboEnabled(PROFILE);
    }
    try {
      return localStorage.getItem(turboStorageKeyKoolkid()) === "1";
    } catch (e) {
      return false;
    }
  }

  function persistTurboModeKoolkid(enabled) {
    const app = App();
    if (app && typeof app.setProfileTurboEnabled === "function") {
      app.setProfileTurboEnabled(PROFILE, !!enabled);
      return;
    }
    try {
      localStorage.setItem(turboStorageKeyKoolkid(), enabled ? "1" : "0");
    } catch (e) {}
  }

  function currentTurboModeKoolkid() {
    const enabled = !!loadTurboModeKoolkid();
    state.turboMode = enabled;
    return enabled;
  }

  function renderTurboToggleKoolkid() {
    const btn = document.getElementById("turboToggleBtnKoolkid");
    if (!btn) return;
    state.turboMode = currentTurboModeKoolkid();
    btn.classList.toggle("is-on", !!state.turboMode);
    btn.setAttribute("aria-pressed", state.turboMode ? "true" : "false");
    btn.setAttribute("aria-label", state.turboMode ? "Turbo on" : "Turbo off");
  }

  function currencyPayload(payload) {
    return payload || {};
  }

  function money(value, payload) {
    const num = Number(value || 0);
    try { if (typeof formatCurrencyAmount === "function") return formatCurrencyAmount(num, currencyPayload(payload)); } catch (e) {}
    return Number.isFinite(num) ? `$${Math.abs(num).toFixed(2)}` : "—";
  }

  function setInputValueIfIdle(id, value) {
    const el = document.getElementById(id);
    if (!el) return;
    if (document.activeElement === el) return;
    const next = value === null || value === undefined ? "" : String(value);
    if (el.value !== next) el.value = next;
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

  async function sendFastManualTradeKoolkid(payload, options) {
    const app = App();
    const requestPayload = Object.assign({}, payload || {});
    const turbo = !!(options && Object.prototype.hasOwnProperty.call(options, "turbo")
      ? options.turbo
      : currentTurboModeKoolkid());
    requestPayload.turbo = turbo;
    const shouldQueue = !!(options && options.queue);
    const sendNow = () => {
      if (app && typeof app.sendFastProfileTrade === "function") {
        return app.sendFastProfileTrade(PROFILE, requestPayload, Object.assign({
          turbo,
          queue: false,
          fireAndForget: turbo,
        }, options || {}, {
          turbo,
          queue: false,
          fireAndForget: turbo,
        }));
      }
      return postJSON("/manual_trade", requestPayload);
    };
    if (shouldQueue) {
      return enqueueFastBuyKoolkid(sendNow);
    }
    return sendNow();
  }


  function getStakeValueKoolkid() {
    const el = document.getElementById("stake");
    let v = Number(el && el.value);
    if (!isFinite(v) || v <= 0) v = 1;
    return v;
  }

  function kid2vixColor(label) {
    const key = String(label || "").toUpperCase();
    if (key === "SAFE") return "#22c55e";
    if (key === "RISKY") return "#f59e0b";
    return "#ef4444";
  }

  function normalizeOverAnalysisBarrier(value) {
    const n = Number(value);
    return [1, 2, 3].includes(n) ? n : 3;
  }

  function overAnalysisLabel(barrier) {
    return `Over ${normalizeOverAnalysisBarrier(barrier)} Analysis`;
  }

  function syncOverAnalysisSelectKoolkid(barrier) {
    const select = document.getElementById("overAnalysisBarrierSelectKoolkid");
    if (!select) return;
    const next = String(normalizeOverAnalysisBarrier(barrier));
    if (select.value !== next) select.value = next;
  }

  function renderKid2vixKoolkid(data) {
    if (data && typeof data === "object") state.kid2vix = data;
    const d = state.kid2vix || {};
    const btn = document.getElementById("kid2vixBtnKoolkid");
    const info = document.getElementById("kid2vixInfoKoolkid");
    const labelEl = document.getElementById("kid2vixLabelKoolkid");
    const pressureEl = document.getElementById("kid2vixPressureKoolkid");
    const count20El = document.getElementById("kid2vixCount20Koolkid");
    const count5El = document.getElementById("kid2vixCount5Koolkid");
    const readinessEl = document.getElementById("kid2vixReadinessKoolkid");
    const splitEl = document.getElementById("kid2vixSplitKoolkid");
    const enabled = !!(state.autoModes && state.autoModes.kid2vix);
    const label = String(d.label || "SKIP").toUpperCase();
    const labelColor = kid2vixColor(label);
    const pressure = Number(d.repeat_pressure_score);
    const pressureThreshold = Number(d.repeat_pressure_threshold);
    const count20 = Number(d.last20_count);
    const count5 = Number(d.last5_count);
    const cooldown = Number(d.cooldown_remaining || 0);
    const ready = !!d.trade_ready;
    const ratioPct = d.ratio_pct || {};
    const overPct = Number(ratioPct.over3);
    const underPct = Number(ratioPct.under2);
    const stake = getStakeValueKoolkid();
    const overStake = Number((stake * ((isFinite(overPct) ? overPct : 70) / 100)).toFixed(2));
    const underStake = Number((stake - overStake).toFixed(2));

    if (btn) {
      btn.innerText = enabled ? `Kid2vix: ON • ${label}` : "Kid2vix: OFF";
      btn.style.background = enabled ? labelColor : "#1e293b";
      btn.style.color = enabled ? "#04130b" : "#e2e8f0";
    }
    if (info) {
      info.style.color = enabled ? "#cbd5e1" : "#94a3b8";
      info.innerText = String(d.reason_summary || "Scanning 2/3 pressure for a safe UNDER 2 + OVER 3 entry...");
    }
    if (labelEl) {
      labelEl.innerText = label;
      labelEl.style.color = labelColor;
    }
    if (pressureEl) {
      pressureEl.innerText = isFinite(pressure) && isFinite(pressureThreshold)
        ? `${pressure.toFixed(1)} / ${pressureThreshold.toFixed(1)}`
        : "-";
      pressureEl.style.color = isFinite(pressure) && isFinite(pressureThreshold) && pressure <= pressureThreshold ? "#22c55e" : "#f59e0b";
    }
    if (count20El) {
      count20El.innerText = isFinite(count20) ? `${count20}` : "-";
      count20El.style.color = isFinite(count20) && count20 <= Number((d.settings || {}).last20_threshold || 0) ? "#22c55e" : "#f59e0b";
    }
    if (count5El) {
      count5El.innerText = isFinite(count5) ? `${count5}` : "-";
      count5El.style.color = isFinite(count5) && count5 <= Number((d.settings || {}).last5_threshold || 0) ? "#22c55e" : "#f59e0b";
    }
    if (readinessEl) {
      if (!enabled) readinessEl.innerText = "Trade readiness: auto mode is OFF.";
      else if (!d.ready) readinessEl.innerText = "Trade readiness: warming up the 20-tick and 5-tick windows.";
      else if (d.cycle_active) readinessEl.innerText = `Trade readiness: waiting for current cycle (${Number(d.open_contracts || 0)} leg${Number(d.open_contracts || 0) === 1 ? "" : "s"}) to finish.`;
      else if (cooldown > 0) readinessEl.innerText = `Trade readiness: cooldown after loss • ${cooldown.toFixed(1)}s left.`;
      else readinessEl.innerText = `Trade readiness: ${ready ? "SAFE to send UNDER 2 + OVER 3" : "not ready yet"}.`;
      readinessEl.style.color = ready ? "#22c55e" : "#cbd5e1";
    }
    if (splitEl) {
      splitEl.innerText = `Split: OVER 3 ${isFinite(overPct) ? overPct.toFixed(1) : "70.0"}% (${money(overStake, d)}) • UNDER 2 ${isFinite(underPct) ? underPct.toFixed(1) : "30.0"}% (${money(underStake, d)})`;
    }

    const settings = d.settings || {};
  }

  function updateDual2xUIKoolkid() {
    const btn = document.getElementById("dual2xBtnKoolkid");
    const wrap = document.getElementById("dual2xOptionsKoolkid");
    const optionA = document.getElementById("dual2xOver6Under4BtnKoolkid");
    const optionB = document.getElementById("dual2xOver5Under4BtnKoolkid");
    const optionC = document.getElementById("dual2xOver2Under1BtnKoolkid");
    const optionD = document.getElementById("dual2xOver8Under7BtnKoolkid");
    const under3SplitBtn = document.getElementById("under3SplitBtnKoolkid");
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
    if (under3SplitBtn) {
      under3SplitBtn.disabled = !!state.dual2xBusy;
      under3SplitBtn.style.opacity = state.dual2xBusy ? "0.7" : "1";
      under3SplitBtn.style.cursor = state.dual2xBusy ? "not-allowed" : "pointer";
      under3SplitBtn.innerText = state.dual2xBusy
        ? "UNDER 3 (RUNNING...)"
        : "UNDER 3 (OVER 3 + UNDER 3 SAME TICK)";
    }
    renderDual2xAnalysisKoolkid();
  }

  async function placeDual2xLegsSameTickKoolkid(legs) {
    const stake = getStakeValueKoolkid();
    const totalWeight = legs.reduce((sum, leg) => sum + Math.max(0, Number(leg.weight || 1)), 0) || 1;
    const plannedLegs = legs.map((leg) => {
      const fixedStake = Number(leg.fixedStake);
      const weight = Math.max(0, Number(leg.weight || 1));
      const legStake = (Number.isFinite(fixedStake) && fixedStake > 0)
        ? Number(fixedStake.toFixed(2))
        : Number((stake * weight / totalWeight).toFixed(2));
      return Object.assign({}, leg, { legStake });
    });
    const jobs = plannedLegs.map((leg) => {
      const turboOn = currentTurboModeKoolkid();
      const payload = {
        stake: leg.legStake,
        amount: leg.legStake,
        type: String(leg.type || "OVER").toUpperCase(),
        barrier: Number(leg.barrier),
      };
      return sendFastManualTradeKoolkid(payload, {
        turbo: turboOn,
        queue: !turboOn,
        useSocket: turboOn,
      });
    });
    const rs = await Promise.allSettled(jobs);
    let placed = 0;
    const failures = [];
    const stakes = [];
    rs.forEach((r, idx) => {
      const leg = plannedLegs[idx] || legs[idx] || {};
      const ok = r.status === "fulfilled" && r.value && r.value.data && r.value.data.status === "success";
      if (ok) placed += 1;
      else failures.push(leg.label || `${leg.type} ${leg.barrier}`);
      const defaultStake = Number.isFinite(Number(leg.legStake))
        ? Number(leg.legStake)
        : Number((stake * Math.max(0, Number(leg.weight || 1)) / totalWeight).toFixed(2));
      stakes.push({
        label: leg.label || `${leg.type} ${leg.barrier}`,
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
    const selectedBarrier = normalizeOverAnalysisBarrier(d.selected_barrier || 3);
    const label = overAnalysisLabel(selectedBarrier);
    if (btn) {
      btn.innerText = `${label}: ${enabled ? "ON" : "OFF"}`;
      btn.style.background = enabled ? "#22c55e" : "#1e293b";
    }
    syncOverAnalysisSelectKoolkid(selectedBarrier);
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
    const marketLabel = symbol || "selected market";
    const counts = `H100 ${high100}/58 • H10 ${high10}/6 • Streak ${streak}/<6`;
    const session = `Losses ${losses}/2 • Trades ${total}/5 • Duration ${duration}T`;

    if (!enabled) {
      info.style.color = "#94a3b8";
      info.innerText = `${label} off • Over 3 analysis idle • ${counts}`;
      return;
    }
    if (!symbolOk) {
      info.style.color = "#f59e0b";
      info.innerText = "Waiting for market ticks to start Over 3 analysis...";
      return;
    }
    if (stopped) {
      info.style.color = "#ef4444";
      info.innerText = `Session stopped (${session}). Toggle OFF/ON to restart.`;
      return;
    }
    if (active) {
      info.style.color = "#38bdf8";
      info.innerText = `Trade active on ${marketLabel}, waiting result • ${session}`;
      return;
    }
    if (waitFresh) {
      info.style.color = "#f59e0b";
      info.innerText = `Waiting fresh setup reset • ${counts} • ${session}`;
      return;
    }
    if (setupReady) {
      info.style.color = "#22c55e";
      info.innerText = `Setup ready on ${marketLabel}: ${label.replace(" Analysis", "")} entry armed • using Over 3 analysis • ${counts} • ${session}`;
      return;
    }
    info.style.color = "#94a3b8";
    info.innerText = `Scanning ${marketLabel} ticks with Over 3 analysis • ${counts} • ${session}`;
  }

  function renderGoldenCardKoolkid(data) {
    if (data && typeof data === "object") state.goldenCard = data;
    const d = state.goldenCard || {};
    const btn = document.getElementById("goldenCardBtnKoolkid");
    const info = document.getElementById("goldenCardInfoKoolkid");
    const statusEl = document.getElementById("goldenCardStatusKoolkid");
    const progressEl = document.getElementById("goldenCardProgressKoolkid");
    const resultsEl = document.getElementById("goldenCardResultsKoolkid");
    const running = !!d.running;
    const historyTarget = Number(d.history_target || 20) || 20;
    const symbols = Array.isArray(d.symbols) ? d.symbols : [];
    const warmed = Number(d.completed_markets || 0) || 0;
    const statusText = String(d.status || "Golden Card is waiting to scan markets.");
    const results = Array.isArray(d.results) ? d.results : [];

    if (btn) {
      btn.innerText = running ? "🂠 GOLDEN CARD • SCANNING" : "🂠 GOLDEN CARD";
      btn.style.background = running
        ? "linear-gradient(135deg,#f59e0b,#fde047)"
        : "linear-gradient(135deg,#ca8a04,#facc15)";
      btn.style.color = "#111827";
    }
    if (info) {
      info.style.color = running ? "#facc15" : "#94a3b8";
      info.innerText = statusText;
    }
    if (statusEl) statusEl.innerText = statusText;
    if (progressEl) progressEl.innerText = `${warmed} / ${symbols.length || 10} warmed • rolling ${historyTarget} ticks`;
    if (!resultsEl) return;
    if (!results.length) {
      resultsEl.innerHTML = `<div style="grid-column:1 / -1; text-align:center; color:#64748b; padding:20px;">${running ? "Scanning market ticks live..." : "Golden Card results will show here after the scan starts."}</div>`;
      return;
    }
    resultsEl.innerHTML = results.map((row) => {
      const tier = String(row.tier || "danger");
      const marketLabel = String(row.market_label || row.symbol || "Market");
      const confidence = Number(row.confidence_pct || 0);
      const setupDigit = Number(row.setup_digit || 3);
      const ticksReady = Number(row.ticks_ready || 0);
      const canTrade = ticksReady >= historyTarget;
      const readyText = row.entry_ready ? "READY" : (canTrade ? "LIVE" : `${ticksReady}/${historyTarget}`);
      return `
        <div class="golden-card-market ${tier}" data-golden-card-symbol="${String(row.symbol || "").replace(/"/g, "&quot;")}">
          <div style="min-width:0;">
            <div style="display:flex; align-items:center; justify-content:space-between; gap:10px;">
              <div style="font-size:17px; font-weight:800; color:#f8fafc; line-height:1.1;">${marketLabel}</div>
              <div style="font-size:12px; color:#e2e8f0; font-weight:700; white-space:nowrap;">${confidence.toFixed(1)}%</div>
            </div>
            <div style="margin-top:6px; font-size:11px; color:${row.entry_ready ? "#86efac" : "#cbd5e1"}; font-weight:700; letter-spacing:.02em;">${readyText}</div>
          </div>
          <div class="golden-card-digit">${setupDigit}</div>
        </div>
      `;
    }).join("");
    Array.from(resultsEl.querySelectorAll("[data-golden-card-symbol]")).forEach((node) => {
      const symbol = String(node.getAttribute("data-golden-card-symbol") || "").toUpperCase();
      const row = results.find((item) => String(item.symbol || "").toUpperCase() === symbol);
      const canTrade = !!row && Number(row.ticks_ready || 0) >= historyTarget;
      if (canTrade) {
        node.addEventListener("click", () => {
          if (!symbol || !window.placeGoldenCardTradeKoolkid) return;
          window.placeGoldenCardTradeKoolkid(symbol);
        });
        node.style.cursor = "pointer";
        node.style.opacity = "1";
      } else {
        node.style.cursor = "wait";
        node.style.opacity = "0.78";
      }
    });
  }


  function updateAdvancedAIModeButtons(modes, payload) {
  const map = [
    ["kidbrain", "kidbrainBtnKoolkid", "🤖 KIDBRAIN"],
    ["edge_brain", "edgeBrainBtnKoolkid", "🧠 EDGE BRAIN"],
    ["smart_flow", "smartFlowBtnKoolkid", "🎯 SMART FLOW"],
    ["meta_ai", "metaAiBtnKoolkid", "⚡ META AI"],
    ["kidracks_ai", "kidracksAiBtnKoolkid", "🤓 KIDRACKS AI"],
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
    if (payload && payload.golden_card_data) renderGoldenCardKoolkid(payload.golden_card_data);
    else renderGoldenCardKoolkid();
    if (payload && payload.kid2vix_data) renderKid2vixKoolkid(payload.kid2vix_data);
    else renderKid2vixKoolkid();
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
        if (data && data.golden_card_data) renderGoldenCardKoolkid(data.golden_card_data);
        if (data && data.kid2vix_data) renderKid2vixKoolkid(data.kid2vix_data);
        if (data && data.auto_modes) updateModeButtonsFromPayload(data.auto_modes, data);
      });

      socket.on("golden_card_update", (data) => {
        renderGoldenCardKoolkid(data || {});
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

    document.addEventListener("input", (event) => {
      const target = event && event.target;
      if (target && target.id === "stake") {
        renderKid2vixKoolkid();
      }
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
    renderGoldenCardKoolkid();
    renderKid2vixKoolkid();
    currentTurboModeKoolkid();
    renderTurboToggleKoolkid();
    setTimeout(syncSelectedDigitsToServer, 200);
  }

  async function onActivate() {
    try { App().applyDigitSelectionUI && App().applyDigitSelectionUI(); } catch (e) {}
    bindSocketListeners();
    updateDual2xUIKoolkid();
    renderDual2xAnalysisKoolkid();
    renderOver3AnalysisKoolkid();
    renderGoldenCardKoolkid();
    renderKid2vixKoolkid();
    currentTurboModeKoolkid();
    renderTurboToggleKoolkid();
    setTimeout(syncSelectedDigitsToServer, 150);
  }

  async function afterLoadProfileUI() {
    try { App().applyDigitSelectionUI && App().applyDigitSelectionUI(); } catch (e) {}
    bindSocketListeners();
    updateDual2xUIKoolkid();
    renderDual2xAnalysisKoolkid();
    renderOver3AnalysisKoolkid();
    renderGoldenCardKoolkid();
    renderKid2vixKoolkid();
    currentTurboModeKoolkid();
    renderTurboToggleKoolkid();
  }

  window.toggleTurboKoolkid = function () {
    const next = !currentTurboModeKoolkid();
    state.turboMode = next;
    persistTurboModeKoolkid(next);
    renderTurboToggleKoolkid();
  };

  if (!window.__koolkidTurboSyncBound) {
    window.__koolkidTurboSyncBound = true;
    window.addEventListener("bot-profile-turbo-change", (event) => {
      const detail = (event && event.detail) || {};
      if (String(detail.profile || "").toUpperCase() !== PROFILE) return;
      state.turboMode = !!detail.enabled;
      renderTurboToggleKoolkid();
    });
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
        const stakeMsg = r.stakes && r.stakes.length ? r.stakes.map((s) => `${s.label}: ${money(Number(s.stake), s)}`).join(" / ") : "";
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

  window.runUnder3SplitKoolkid = async function () {
    if (state.dual2xBusy) return;
    const stake = getStakeValueKoolkid();
    const overStake = Number((stake * 0.65).toFixed(2)); // Match requested split behavior (example: $10 -> $6.50).
    const underStake = Number((stake - overStake).toFixed(2));
    if (overStake < 0.35 || underStake < 0.35) {
      safeToast(`Stake too low for Under 3 split. Use at least ${money(1)}.`, "error");
      return;
    }

    state.dual2xBusy = true;
    updateDual2xUIKoolkid();
    try {
      const r = await placeDual2xLegsSameTickKoolkid([
        { type: "OVER", barrier: 3, fixedStake: overStake, label: "OVER 3" },
        { type: "UNDER", barrier: 3, fixedStake: underStake, label: "UNDER 3" },
      ]);
      if (r.placed === 2) {
        safeToast(`UNDER 3 sent • OVER 3 ${money(overStake)} / UNDER 3 ${money(underStake)} (same tick)`, "success");
      } else if (r.placed === 1) {
        safeToast(`UNDER 3 partial (1/2) • OVER 3 ${money(overStake)} / UNDER 3 ${money(underStake)}`, "error");
      } else {
        safeToast("UNDER 3 failed", "error");
      }
    } catch (e) {
      safeToast("UNDER 3 failed", "error");
    } finally {
      state.dual2xBusy = false;
      updateDual2xUIKoolkid();
    }
  };

  window.openGoldenCardPopupKoolkid = function () {
    showCenteredPopupKoolkid("goldenCardPopupKoolkid");
  };

  window.hideGoldenCardPopupKoolkid = function () {
    hideCenteredPopupKoolkid("goldenCardPopupKoolkid");
  };

  window.handleGoldenCardBtnKoolkid = async function () {
    const current = state.goldenCard || {};
    if (current.running) {
      window.openGoldenCardPopupKoolkid();
      return;
    }
    renderGoldenCardKoolkid(Object.assign({}, current, {
      running: true,
      completed: false,
      status: "Starting live Golden Card scan across 10 markets...",
    }));
    window.openGoldenCardPopupKoolkid();
    await nextPaintFrame();
    const r = await postJSON("/start_golden_card_koolkid", {});
    if (r.data && r.data.status === "success") {
      if (r.data.golden_card_data) renderGoldenCardKoolkid(r.data.golden_card_data);
      safeToast("Golden Card scan started", "success");
    } else {
      window.hideGoldenCardPopupKoolkid();
      renderGoldenCardKoolkid(Object.assign({}, current, {
        running: false,
        completed: false,
      }));
      safeToast((r.data && r.data.message) || "Golden Card scan failed", "error");
    }
  };

  window.turnOffGoldenCardKoolkid = async function () {
    const current = state.goldenCard || {};
    if (!current.running) {
      safeToast("Golden Card is already off", "info");
      return;
    }
    const r = await postJSON("/stop_golden_card_koolkid", {});
    if (r.data && r.data.golden_card_data) renderGoldenCardKoolkid(r.data.golden_card_data);
    window.hideGoldenCardPopupKoolkid();
    safeToast("Golden Card turned off", "info");
  };

  window.placeGoldenCardTradeKoolkid = async function (symbol) {
    if (state.goldenCardTradeBusy) return;
    const market = String(symbol || "").toUpperCase().trim();
    if (!market) {
      safeToast("Golden Card market missing", "error");
      return;
    }
    state.goldenCardTradeBusy = true;
    try {
      const stake = getStakeValueKoolkid();
      const duration = Number(document.getElementById("durationTicks")?.value || 1) || 1;
      const turboOn = currentTurboModeKoolkid();
      const payload = {
        stake,
        amount: stake,
        type: "OVER",
        barrier: 1,
        symbol: market,
        duration,
      };
      const r = await sendFastManualTradeKoolkid(payload, {
        turbo: turboOn,
        queue: !turboOn,
        useSocket: turboOn,
      });
      const ok = !!(r && r.data && r.data.status === "success");
      if (ok) safeToast(`Golden Card sent OVER 1 on ${market}`, "success");
      else safeToast((r && r.data && r.data.message) || `Golden Card trade failed on ${market}`, "error");
    } catch (e) {
      safeToast(`Golden Card trade failed on ${market}`, "error");
    } finally {
      state.goldenCardTradeBusy = false;
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

  window.setOverAnalysisBarrierKoolkid = async function (barrier) {
    const selected = normalizeOverAnalysisBarrier(barrier);
    const r = await postJSON("/set_over_analysis_barrier_koolkid", { barrier: selected, enable: false });
    if (r.data && r.data.status === "success") {
      if (r.data.auto_modes) state.autoModes = Object.assign({}, state.autoModes || {}, r.data.auto_modes);
      if (r.data.over3_analysis_data) renderOver3AnalysisKoolkid(r.data.over3_analysis_data);
      updateModeButtonsFromPayload(r.data.auto_modes || { over3_analysis: !!r.data.over3_analysis }, r.data.payload || null);
      safeToast(`${overAnalysisLabel(selected)} selected`, "success");
    } else {
      safeToast((r.data && r.data.message) || `${overAnalysisLabel(selected)} failed`, "error");
    }
  };

  window.toggleOver3AnalysisKoolkid = async function () {
    const r = await postJSON("/toggle_over3_analysis_koolkid", {});
    if (r.data && r.data.status === "success") {
      if (r.data.auto_modes) state.autoModes = Object.assign({}, state.autoModes || {}, r.data.auto_modes);
      updateModeButtonsFromPayload(r.data.auto_modes || { over3_analysis: !!r.data.over3_analysis }, r.data.payload || null);
      if (r.data.over3_analysis_data) renderOver3AnalysisKoolkid(r.data.over3_analysis_data);
      safeToast(`${overAnalysisLabel((r.data.over3_analysis_data || {}).selected_barrier || 3)}: ${r.data.over3_analysis ? "ON" : "OFF"}`, r.data.over3_analysis ? "success" : "error");
    } else {
      safeToast((r.data && r.data.message) || "Over Analysis failed", "error");
    }
  };

  window.toggleKid2vixKoolkid = async function () {
    const r = await postJSON("/toggle_kid2vix_koolkid", {});
    if (r.data && r.data.status === "success") {
      if (r.data.auto_modes) state.autoModes = Object.assign({}, state.autoModes || {}, r.data.auto_modes);
      updateModeButtonsFromPayload(r.data.auto_modes || { kid2vix: !!r.data.kid2vix_auto }, r.data.payload || null);
      if (r.data.kid2vix_data) renderKid2vixKoolkid(r.data.kid2vix_data);
      safeToast(`Kid2vix: ${r.data.kid2vix_auto ? "ON" : "OFF"}`, r.data.kid2vix_auto ? "success" : "error");
    } else {
      safeToast((r.data && r.data.message) || "Kid2vix failed", "error");
    }
  };

  window.saveKid2vixSettingsKoolkid = async function () {
    const last20 = Number(document.getElementById("kid2vixLast20ThresholdKoolkid")?.value);
    const last5 = Number(document.getElementById("kid2vixLast5ThresholdKoolkid")?.value);
    const pressure = Number(document.getElementById("kid2vixPressureThresholdKoolkid")?.value);
    const ratio = Number(document.getElementById("kid2vixOver3RatioKoolkid")?.value);
    const cooldown = Number(document.getElementById("kid2vixCooldownKoolkid")?.value);
    const r = await postJSON("/set_kid2vix_settings_koolkid", {
      last20_threshold: last20,
      last5_threshold: last5,
      repeat_pressure_threshold: pressure,
      over3_ratio: ratio,
      cooldown_after_loss: cooldown,
    });
    if (r.data && r.data.status === "success") {
      if (r.data.payload && r.data.payload.auto_modes) state.autoModes = Object.assign({}, state.autoModes || {}, r.data.payload.auto_modes);
      if (r.data.kid2vix_data) renderKid2vixKoolkid(r.data.kid2vix_data);
      safeToast("Kid2vix settings saved", "success");
    } else {
      safeToast((r.data && r.data.message) || "Kid2vix settings failed", "error");
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
