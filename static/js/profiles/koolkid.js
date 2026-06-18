(function () {
  const PROFILE = "KOOLKID";
  const FAST_INTERVAL_MS_NORMAL = 400; // 0.4s as requested
  const FAST_INTERVAL_MS_TURBO = 120;  // faster Turbo lane for KOOLKID
  const FAST_MAX_BUY_QUEUE = 12;       // safety limit
  const DIGIT_RENDER_THROTTLE_MS = 350;
  const GOLDEN_RENDER_THROTTLE_MS = 180;
  const state = {
    lastSocket: null,
    socketBound: false,
    barrierAnalysis: null,
    over3Analysis: null,
    goldenCard: null,
    predictionRecentDigits: [],
    predictionResultMarker: { digit: null, type: "", until: 0 },
    predictionLastTickCount: null,
    over6Analyzer: {
      useForEntry: false,
      lastReadyAt: 0,
      lastSignature: "",
    },
    goldenCardSettingsBusy: false,
    testtrial: null,
    kid2vix: null,
    goldenCardTradeBusy: false,
    goldenCardAutoOn: false,
    goldenCardAutoLastSignalKey: "",
    goldenCardAutoWaitingReset: false,
    goldenCardPopupDismissedAt: 0,
    goldenCardReinvestProfitsOn: false,
    goldenCardReinvestProfitPct: 25,
    goldenCardReinvestBaseStake: null,
    goldenCardReinvestCycleStake: null,
    goldenCardReinvestLastProfit: 0,
    goldenCardReinvestContracts: {},
    g1AutoOn: false,
    g1AutoBusy: false,
    g1AutoLastTick: null,
    g1LastDigit: null,
    profileReinvestOn: false,
    profileReinvestPct: 25,
    profileReinvestBaseStake: null,
    profileReinvestProfitBank: 0,
    singleMartingale: {
      action: "UNDER_3",
      enabled: false,
      step: 1,
      over3Step: 1,
      pairSteps: {},
      doubleLimit: 0,
      running: false,
      inProgress: false,
      pendingAction: "",
      pendingContractId: "",
      pendingContracts: {},
      pendingExpected: 0,
      pendingSettled: 0,
      pendingPair: false,
      pendingHasWin: false,
      pendingStake: 0,
      pendingMartingale: false,
      stopRequested: false,
      restartTimer: null,
      waitingForTicks: false,
      waitTicksRemaining: 0,
      tickSpacing: 1,
      sessionProfit: 0,
      status: "Ready",
      lastResult: "none",
      targetProfit: {
        OVER_2_TARGET: { currentStake: 0.35, lossBank: 0, step: 1, sessionProfit: 0, lastResult: "none" },
        OVER_3_TARGET: { currentStake: 0.35, lossBank: 0, step: 1, sessionProfit: 0, lastResult: "none" },
      },
      over3Under6Pair: {
        running: false,
        enabled: false,
        inProgress: false,
        round: 1,
        pendingContracts: {},
        pendingExpected: 0,
        pendingSettled: 0,
        lastDigit: null,
        status: "Ready",
        availabilityError: "",
        over3_state: { current_stake: 0.35, loss_bank: 0, step: 1, last_result: "none" },
        under6_state: { current_stake: 0.35, loss_bank: 0, step: 1, last_result: "none" },
      },
    },
    over6ScanMartingale: {
      running: false,
      inProgress: false,
      step: 1,
      maxSteps: 4,
      cooldownUntil: 0,
      cooldownTimer: null,
      pendingContractId: "",
      lastResult: "none",
      status: "Scanning",
      reason: "Scanning for Over 6 opening...",
      digits: [],
      lastSymbol: "",
      lastTickCount: null,
      lastUiAt: 0,
    },
    balancedRecovery: {
      enabled: false,
      running: false,
      inProgress: false,
      round: 1,
      lossAccumulated: 0,
      underStake: 0,
      overStake: 0,
      batchId: "",
      pending: {},
      settled: 0,
      hasWin: false,
      totalProfit: 0,
      sessionProfit: 0,
      lastResult: "none",
      status: "Ready",
      stopRequested: false,
      thinkingLogic: false,
      thinkingScanning: false,
      thinkingOpportunityActive: false,
      thinkingLastSignalKey: "",
      thinkingAnalysisRequested: false,
    },
    koolkidPairRecovery: {
      enabled: false,
      running: false,
      inProgress: false,
      round: 1,
      lossAccumulated: 0,
      underStake: 0,
      overStake: 0,
      batchId: "",
      pending: {},
      settled: 0,
      hasWin: false,
      totalProfit: 0,
      lastResult: "none",
      status: "Ready",
      stopRequested: false,
      underMultiplier: 0,
      overMultiplier: 0,
    },
    autoModes: {},
    turboMode: loadTurboModeKoolkid(),
    dual2xOpen: false,
    dual2xBusy: false,
    dual2xAnalysis: { tickCount: 0, pctByDigit: null, ready: false },
    dual2xReinvestBatches: {},
  };
  const fastBuyQueueKoolkid = { items: [], running: false, lastRunAt: 0 };
  let pendingDigitAnalysisRender = null;
  let digitAnalysisRenderTimer = null;
  let lastDigitAnalysisRenderAt = 0;
  let pendingGoldenCardRender = null;
  let goldenCardRenderTimer = null;
  let lastGoldenCardRenderAt = 0;

  function App() { return window.BotApp || {}; }
  function isActive() { try { return typeof activeProfile !== "undefined" && activeProfile === PROFILE; } catch (e) { return false; } }

  function getRoot() { return document.getElementById("profileContainer"); }

  function isLifetimeUserKoolkid() {
    try {
      const ctx = window.LICENSE_CONTEXT || {};
      return !!(ctx.is_lifetime || String(ctx.license_type || "").toLowerCase() === "lifetime");
    } catch (e) {
      return false;
    }
  }

  function isPaidMonthlyUserKoolkid() {
    try {
      const ctx = window.LICENSE_CONTEXT || {};
      return !!(ctx.is_paid_monthly || String(ctx.license_type || "").toLowerCase() === "paid_monthly");
    } catch (e) {
      return false;
    }
  }

  function isRegularMonthlyUserKoolkid() {
    try {
      const ctx = window.LICENSE_CONTEXT || {};
      return !!(ctx.is_monthly || String(ctx.license_type || "").toLowerCase() === "monthly") && !isPaidMonthlyUserKoolkid();
    } catch (e) {
      return false;
    }
  }

  function isMonthlyKidGxReplacementUserKoolkid() {
    try {
      const ctx = window.LICENSE_CONTEXT || {};
      const type = String(ctx.license_type || "").toLowerCase();
      const lifetime = !!(ctx.is_lifetime || ctx.is_full_access || type === "lifetime" || type === "testers" || type === "beta_testers");
      return !!(!lifetime && (ctx.is_monthly || type === "monthly" || type === "paid_monthly" || type === "fifteen_day"));
    } catch (e) {
      return false;
    }
  }

  function canUseKoolkidSingleMartingale() {
    return isLifetimeUserKoolkid() || isRegularMonthlyUserKoolkid();
  }

  function isKoolkidSingleMartingaleMonthlyLimited() {
    return isRegularMonthlyUserKoolkid() && !isLifetimeUserKoolkid();
  }

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
    if (id === "goldenCardPopupKoolkid") {
      popup.style.top = "18px";
      popup.style.transform = "translateX(-50%)";
    } else {
      popup.style.top = "50%";
      popup.style.transform = "translate(-50%, -50%)";
    }
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

  function normalizeGoldenCardFilterModeKoolkid(value) {
    const raw = String(value || "BOTH").toUpperCase().replace(/\s+/g, "");
    if (raw === "OVER0" || raw === "OVER_0") return "OVER0";
    if (raw === "OVER1" || raw === "OVER_1") return "OVER1";
    if (raw === "OVER2" || raw === "OVER_2") return "OVER2";
    if (raw === "UNDER8" || raw === "UNDER_8") return "UNDER8";
    if (raw === "UNDER9" || raw === "UNDER_9") return "UNDER9";
    if (raw === "ALL" || raw === "ALL4" || raw === "ALL_4") return "ALL4";
    return "BOTH";
  }

  function syncGoldenCardControlsKoolkid(data) {
    const safe = data || state.goldenCard || {};
    const modeNode = document.getElementById("goldenCardTradeModeKoolkid");
    const jumpNode = document.getElementById("goldenCardAddJumpPairsKoolkid");
    const autoNode = document.getElementById("goldenCardAutoTraderKoolkid");
    const filterMode = normalizeGoldenCardFilterModeKoolkid(safe.filter_mode || "BOTH");
    if (modeNode) modeNode.value = filterMode;
    if (jumpNode) jumpNode.checked = !!safe.add_jump_pairs;
    if (autoNode) autoNode.checked = !!state.goldenCardAutoOn;
    applyGoldenCardPcScrollKoolkid();
    renderGoldenCardReinvestControlsKoolkid();
  }

  function readGoldenCardOptionsKoolkid() {
    const modeNode = document.getElementById("goldenCardTradeModeKoolkid");
    const jumpNode = document.getElementById("goldenCardAddJumpPairsKoolkid");
    return {
      filter_mode: normalizeGoldenCardFilterModeKoolkid(modeNode ? modeNode.value : "BOTH"),
      add_jump_pairs: !!(jumpNode && jumpNode.checked),
    };
  }

  function getGoldenCardReinvestPctKoolkid() {
    const pct = Number(state.goldenCardReinvestProfitPct);
    return [25, 50, 75, 100].includes(pct) ? pct : 25;
  }

  function resetGoldenCardReinvestCycleKoolkid() {
    state.goldenCardReinvestBaseStake = null;
    state.goldenCardReinvestCycleStake = null;
    state.goldenCardReinvestLastProfit = 0;
    state.goldenCardReinvestContracts = {};
  }

  function getGoldenCardReinvestAdjustedStakeKoolkid(baseStake) {
    const base = Number(baseStake);
    if (!Number.isFinite(base) || base <= 0) return 0;
    if (!state.goldenCardReinvestProfitsOn) {
      state.goldenCardReinvestBaseStake = Number(base.toFixed(2));
      state.goldenCardReinvestCycleStake = null;
      return Number(base.toFixed(2));
    }
    const knownBase = Number(state.goldenCardReinvestBaseStake);
    if (!Number.isFinite(knownBase) || knownBase <= 0 || Math.abs(knownBase - base) >= 0.01) {
      state.goldenCardReinvestBaseStake = Number(base.toFixed(2));
      state.goldenCardReinvestCycleStake = Number(base.toFixed(2));
    }
    const cycle = Number(state.goldenCardReinvestCycleStake);
    return Number((Number.isFinite(cycle) && cycle > 0 ? cycle : base).toFixed(2));
  }

  function setGoldenCardReinvestCycleStakeFromTradeKoolkid(stake) {
    const value = Number(stake);
    if (!Number.isFinite(value) || value <= 0) return;
    state.goldenCardReinvestCycleStake = Number(value.toFixed(2));
    if (!Number.isFinite(Number(state.goldenCardReinvestBaseStake))) {
      state.goldenCardReinvestBaseStake = Number(value.toFixed(2));
    }
  }

  function isGoldenCardTradeEventKoolkid(trade) {
    if (!trade || typeof trade !== "object") return false;
    const profile = String(trade.profile || "").toUpperCase();
    const mode = String(trade.mode || "").toLowerCase();
    const id = String(trade.contract_id || trade.id || "").trim();
    return profile === PROFILE && (mode === "golden_card" || (id && !!state.goldenCardReinvestContracts[id]));
  }

  function trackGoldenCardReinvestPlacementKoolkid(trade) {
    if (!state.goldenCardReinvestProfitsOn || !isGoldenCardTradeEventKoolkid(trade)) return;
    const id = String(trade.contract_id || trade.id || "").trim();
    if (id) state.goldenCardReinvestContracts[id] = true;
    setGoldenCardReinvestCycleStakeFromTradeKoolkid(Number(trade.stake || trade.amount || state.goldenCardReinvestCycleStake));
    renderGoldenCardReinvestControlsKoolkid();
  }

  function armGoldenCardReinvestProfitKoolkid(profit) {
    if (!state.goldenCardReinvestProfitsOn) return;
    const amount = Number(profit) || 0;
    if (!Number.isFinite(amount) || amount <= 0) return;
    state.goldenCardReinvestLastProfit = amount;
    const currentStake = Number(state.goldenCardReinvestCycleStake);
    const fallbackStake = Number(state.goldenCardReinvestBaseStake || getStakeValueKoolkid());
    const baseStake = Number.isFinite(currentStake) && currentStake > 0 ? currentStake : fallbackStake;
    if (!Number.isFinite(baseStake) || baseStake <= 0) return;
    const add = amount * (getGoldenCardReinvestPctKoolkid() / 100);
    state.goldenCardReinvestCycleStake = Number((baseStake + add).toFixed(2));
    renderGoldenCardReinvestControlsKoolkid();
  }

  function handleGoldenCardReinvestResultKoolkid(trade) {
    if (!state.goldenCardReinvestProfitsOn || !isGoldenCardTradeEventKoolkid(trade)) return;
    const id = String(trade.contract_id || trade.id || "").trim();
    if (id && state.goldenCardReinvestContracts[id]) delete state.goldenCardReinvestContracts[id];
    const profit = Number(
      trade.profit != null ? trade.profit
        : (trade.profit_loss != null ? trade.profit_loss : trade.pnl)
    ) || 0;
    const result = String(trade.result || trade.status || "").toUpperCase();
    if (profit > 0 || result === "WIN" || result === "WON") armGoldenCardReinvestProfitKoolkid(Math.max(profit, 0));
    else renderGoldenCardReinvestControlsKoolkid();
  }

  function renderGoldenCardReinvestControlsKoolkid() {
    const toggle = document.getElementById("goldenCardReinvestProfitsKoolkid");
    const panel = document.getElementById("goldenCardReinvestPanelKoolkid");
    const preview = document.getElementById("goldenCardReinvestPreviewKoolkid");
    const on = !!state.goldenCardReinvestProfitsOn;
    const pct = getGoldenCardReinvestPctKoolkid();
    if (toggle) toggle.checked = on;
    if (panel) panel.style.display = on ? "block" : "none";
    document.querySelectorAll("[data-golden-card-reinvest-pct]").forEach((btn) => {
      const active = Number(btn.getAttribute("data-golden-card-reinvest-pct")) === pct;
      btn.style.background = active ? "#facc15" : "#334155";
      btn.style.color = active ? "#111827" : "#e2e8f0";
      btn.style.fontWeight = active ? "900" : "700";
    });
    if (preview) {
      const manual = getStakeValueKoolkid();
      const next = getGoldenCardReinvestAdjustedStakeKoolkid(manual);
      const profit = Math.max(0, Number(state.goldenCardReinvestLastProfit) || 0);
      preview.innerText = on
        ? `Next stake: ${money(next)} • using ${pct}% of profit${profit > 0 ? ` (${money(profit)} last win)` : ""}`
        : "Next Golden Card stake uses the selected share of confirmed profit.";
    }
  }

  function applyGoldenCardPcScrollKoolkid() {
    const popup = document.getElementById("goldenCardPopupKoolkid");
    if (!popup) return;
    popup.classList.add("is-pc-scroll-enabled");
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
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || {}),
      });
      let data = {};
      try { data = await res.json(); } catch (e) {}
      if (!res.ok && !data.message) data.message = `Request failed (${res.status})`;
      return { ok: res.ok, data };
    } catch (e) {
      return { ok: false, data: { status: "error", message: "Connection interrupted. Please try again." } };
    }
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
      if (window.MarthaAI && typeof window.MarthaAI.guardAction === "function") {
        return window.MarthaAI.guardAction({
          profile: PROFILE,
          source: "manual_trade",
          type: requestPayload.type || "TRADE",
          label: `KOOLKID ${requestPayload.type || "TRADE"}`,
          barrier: requestPayload.barrier,
          symbol: requestPayload.symbol,
          stake: requestPayload.stake,
          duration: requestPayload.duration,
          duration_unit: requestPayload.duration_unit || "t",
        }, () => postJSON("/manual_trade", requestPayload));
      }
      return postJSON("/manual_trade", requestPayload);
    };
    if (shouldQueue) {
      return enqueueFastBuyKoolkid(sendNow);
    }
    return sendNow();
  }


  function getRawStakeValueKoolkid() {
    const el = document.getElementById("stake");
    let v = Number(el && el.value);
    if (!isFinite(v) || v <= 0) v = 1;
    return v;
  }

  function getProfileReinvestPctKoolkid() {
    const pct = Number(state.profileReinvestPct);
    return [25, 50, 75, 100].includes(pct) ? pct : 25;
  }

  function getProfileReinvestStakeKoolkid(baseStake) {
    const base = Number(baseStake);
    if (!Number.isFinite(base) || base <= 0) return 1;
    if (!state.profileReinvestOn) return Number(base.toFixed(2));
    if (!Number.isFinite(Number(state.profileReinvestBaseStake)) || state.profileReinvestBaseStake <= 0) {
      state.profileReinvestBaseStake = Number(base.toFixed(2));
      state.profileReinvestProfitBank = 0;
    }
    const bank = Math.max(0, Number(state.profileReinvestProfitBank) || 0);
    const add = bank * (getProfileReinvestPctKoolkid() / 100);
    return Number((Number(state.profileReinvestBaseStake) + add).toFixed(2));
  }

  function getStakeValueKoolkid() {
    return getProfileReinvestStakeKoolkid(getRawStakeValueKoolkid());
  }

  function getDurationTicksKoolkid() {
    try {
      if (typeof window.getManualDurationTicks === "function") {
        return window.getManualDurationTicks();
      }
    } catch (e) {}
    const node = document.getElementById("durationTicks");
    const raw = parseInt((node && node.value) || "1", 10);
    if (!Number.isFinite(raw) || raw < 1) return 1;
    return Math.min(10, raw);
  }

  function syncProfileReinvestAutoStakeKoolkid() {
    try {
      fetch("/set_auto_stake", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stake: getStakeValueKoolkid() }),
      }).catch(() => {});
    } catch (e) {}
  }

  function resetProfileReinvestKoolkid() {
    state.profileReinvestBaseStake = null;
    state.profileReinvestProfitBank = 0;
  }

  function handleDual2xProfileReinvestResultKoolkid(trade) {
    const mode = String(trade.mode || "").toLowerCase();
    const batchId = String(trade.batch_id || trade.batchId || "");
    if (mode !== "koolkid_dual2x" && !batchId.startsWith("koolkid_dual2x_")) return false;
    if (!batchId) return true;
    const profit = Number(trade.profit != null ? trade.profit : (trade.profit_value != null ? trade.profit_value : trade.pnl));
    if (!Number.isFinite(profit)) return true;
    const batches = state.dual2xReinvestBatches || (state.dual2xReinvestBatches = {});
    const batch = batches[batchId] || {
      expected: Math.max(2, Math.floor(Number(trade.batch_size || trade.batchSize || 2)) || 2),
      settled: {},
      totalProfit: 0,
    };
    const settledKey = String(trade.contract_id || trade.buy_contract_id || trade.id || `${trade.type || trade.action || "leg"}_${Object.keys(batch.settled).length}`);
    if (batch.settled[settledKey]) {
      batches[batchId] = batch;
      return true;
    }
    batch.settled[settledKey] = true;
    batch.totalProfit = Number((Number(batch.totalProfit || 0) + profit).toFixed(2));
    batches[batchId] = batch;
    if (Object.keys(batch.settled).length < batch.expected) return true;

    delete batches[batchId];
    if (batch.totalProfit > 0) {
      if (!Number.isFinite(Number(state.profileReinvestBaseStake))) {
        state.profileReinvestBaseStake = Number(getRawStakeValueKoolkid().toFixed(2));
      }
      state.profileReinvestProfitBank = Number((Math.max(0, Number(state.profileReinvestProfitBank) || 0) + batch.totalProfit).toFixed(2));
      renderProfileReinvestControlsKoolkid();
      syncProfileReinvestAutoStakeKoolkid();
    } else if (batch.totalProfit < 0) {
      resetProfileReinvestKoolkid();
      renderProfileReinvestControlsKoolkid();
      syncProfileReinvestAutoStakeKoolkid();
    }
    return true;
  }

  function renderProfileReinvestControlsKoolkid() {
    const toggle = document.getElementById("profileReinvestToggleKoolkid");
    const row = document.getElementById("profileReinvestPctRowKoolkid");
    const preview = document.getElementById("profileReinvestPreviewKoolkid");
    const on = !!state.profileReinvestOn;
    const pct = getProfileReinvestPctKoolkid();
    if (toggle) {
      toggle.innerText = on ? "ON" : "OFF";
      toggle.style.background = on ? "#22c55e" : "#334155";
      toggle.style.color = on ? "#052e16" : "#f8fafc";
    }
    if (row) row.style.display = on ? "grid" : "none";
    document.querySelectorAll("[data-profile-reinvest-pct]").forEach((btn) => {
      const active = on && Number(btn.getAttribute("data-profile-reinvest-pct")) === pct;
      btn.style.background = active ? "#facc15" : "#334155";
      btn.style.color = active ? "#111827" : "#e2e8f0";
      btn.style.fontWeight = active ? "900" : "700";
    });
    if (preview) {
      const base = Number(state.profileReinvestBaseStake || getRawStakeValueKoolkid());
      const bank = Math.max(0, Number(state.profileReinvestProfitBank) || 0);
      const next = getProfileReinvestStakeKoolkid(base);
      preview.innerText = on
        ? `ON - ${pct}% profit - next stake ${money(next)}${bank > 0 ? ` - profit bank ${money(bank)}` : ""}`
        : "OFF - fixed stake";
      preview.style.color = on ? "#fde68a" : "#94a3b8";
    }
  }

  function relocateKoolkidTradeHistoryForLifetime() {
    const card = document.getElementById("koolkidTradeHistoryCard");
    const lifetimeSlot = document.getElementById("koolkidLifetimeHistorySlot");
    const originalSlot = document.getElementById("koolkidTradeHistoryOriginalSlot");
    if (!card || !lifetimeSlot || !originalSlot) return;
    if (isLifetimeUserKoolkid()) {
      if (card.parentNode !== lifetimeSlot) lifetimeSlot.appendChild(card);
      card.classList.add("koolkid-history-dock");
    } else {
      if (card.previousElementSibling !== originalSlot) originalSlot.insertAdjacentElement("afterend", card);
      card.classList.remove("koolkid-history-dock");
    }
  }

  function handleProfileReinvestResultKoolkid(trade) {
    if (!state.profileReinvestOn || !trade || typeof trade !== "object") return;
    const profile = String(trade.profile || "").toUpperCase();
    if (profile && profile !== PROFILE) return;
    if (handleDual2xProfileReinvestResultKoolkid(trade)) return;
    const result = String(trade.result || trade.status || "").toUpperCase();
    const profit = Number(trade.profit != null ? trade.profit : (trade.profit_value != null ? trade.profit_value : trade.pnl));
    if ((result === "WIN" || result === "WON" || profit > 0) && Number.isFinite(profit) && profit > 0) {
      if (!Number.isFinite(Number(state.profileReinvestBaseStake))) {
        state.profileReinvestBaseStake = Number(getRawStakeValueKoolkid().toFixed(2));
      }
      state.profileReinvestProfitBank = Number((Math.max(0, Number(state.profileReinvestProfitBank) || 0) + profit).toFixed(2));
      renderProfileReinvestControlsKoolkid();
      syncProfileReinvestAutoStakeKoolkid();
      return;
    }
    if (result === "LOSS" || result === "LOST" || (Number.isFinite(profit) && profit < 0)) {
      resetProfileReinvestKoolkid();
      renderProfileReinvestControlsKoolkid();
      syncProfileReinvestAutoStakeKoolkid();
    }
  }

  function getKoolkidSingleMartingaleState() {
    return state.singleMartingale || {};
  }

  function getKoolkidOver6ScanState() {
    return state.over6ScanMartingale || {};
  }

  function readKoolkidOver6ScanSettings() {
    const duration = Math.max(1, Math.min(10, Math.floor(readKoolkidMartingaleNumber("koolkidOver6ScanDuration", 1, 1, 10))));
    const maxSteps = Math.max(1, Math.min(50, Math.floor(readKoolkidMartingaleNumber("koolkidOver6ScanMaxSteps", 4, 1, 50))));
    const cooldownSeconds = Math.max(30, Math.min(60, Math.floor(readKoolkidMartingaleNumber("koolkidOver6ScanCooldown", 45, 30, 60))));
    const baseStake = Number(Math.max(0.35, getRawStakeValueKoolkid()).toFixed(2));
    return { duration, maxSteps, cooldownSeconds, baseStake };
  }

  function getKoolkidOver6ScanSymbol() {
    const symbolEl = document.getElementById("symbol");
    const value = symbolEl && symbolEl.value ? String(symbolEl.value).trim() : "";
    return value || "R_25";
  }

  function extractKoolkidDigitFromTickPayload(payload) {
    const direct = extractPredictionLastDigitKoolkid(payload || {});
    if (Number.isInteger(direct)) return direct;
    const quoteCandidates = [
      payload && payload.quote,
      payload && payload.tick && payload.tick.quote,
      payload && payload.price,
      payload && payload.value,
    ];
    for (const candidate of quoteCandidates) {
      const text = String(candidate ?? "");
      const match = text.match(/(\d)(?!.*\d)/);
      if (match) return Number(match[1]);
    }
    return null;
  }

  function rememberKoolkidOver6ScanDigit(digit, symbol) {
    const value = Number(digit);
    if (!Number.isInteger(value) || value < 0 || value > 9) return;
    const st = getKoolkidOver6ScanState();
    const safeSymbol = String(symbol || getKoolkidOver6ScanSymbol() || "");
    if (safeSymbol && st.lastSymbol && st.lastSymbol !== safeSymbol) {
      st.digits = [];
      st.lastTickCount = null;
      st.pendingContractId = "";
      st.inProgress = false;
      st.reason = "Market changed. Collecting fresh Over 6 scan data...";
    }
    if (safeSymbol) st.lastSymbol = safeSymbol;
    st.digits = (st.digits || []).concat(value).slice(-10);
  }

  function syncKoolkidOver6ScanDigitsFromData(data) {
    const symbol = String((data && (data.symbol || data.market || data.current_symbol)) || getKoolkidOver6ScanSymbol() || "");
    const digits = extractPredictionDigitsKoolkid(data || {});
    const tickCount = extractPredictionTickCountKoolkid(data || {});
    const st = getKoolkidOver6ScanState();
    if (Number.isFinite(tickCount) && st.lastTickCount === tickCount) return;
    if (digits && digits.length) {
      if (symbol && st.lastSymbol && st.lastSymbol !== symbol) {
        st.digits = [];
        st.lastTickCount = null;
      }
      if (symbol) st.lastSymbol = symbol;
      if (digits.length >= 10) {
        st.digits = digits.map(Number).filter((d) => Number.isInteger(d) && d >= 0 && d <= 9).slice(-10);
      } else if (!(st.digits || []).length) {
        st.digits = digits.map(Number).filter((d) => Number.isInteger(d) && d >= 0 && d <= 9).slice(-10);
      } else {
        const latest = Number(digits[digits.length - 1]);
        if (Number.isInteger(latest) && latest >= 0 && latest <= 9) st.digits = (st.digits || []).concat(latest).slice(-10);
      }
      if (Number.isFinite(tickCount)) st.lastTickCount = tickCount;
      return;
    }
    const digit = extractKoolkidDigitFromTickPayload(data || {});
    rememberKoolkidOver6ScanDigit(digit, symbol);
    if (Number.isFinite(tickCount)) st.lastTickCount = tickCount;
  }

  function analyzeKoolkidOver6Scan() {
    const st = getKoolkidOver6ScanState();
    const digits = (st.digits || []).slice(-10);
    const low10 = digits.filter((digit) => digit >= 0 && digit <= 6).length;
    const high10 = digits.filter((digit) => digit >= 7 && digit <= 9).length;
    const highPercentages = [7, 8, 9].map((digit) => {
      const pct = Number((state.digitPercentages && state.digitPercentages[digit]) || 0);
      return { digit, pct: Number.isFinite(pct) ? pct : 0 };
    });
    const strongestHigh = highPercentages.reduce((best, item) => (item.pct > best.pct ? item : best), { digit: 7, pct: 0 });
    const highQuality = highPercentages.some((item) => item.pct > 10);
    const latest = digits.length ? digits[digits.length - 1] : null;
    const lowMajority = low10 > high10;
    const strength = strongestHigh.pct;
    const ready = digits.length >= 10 && lowMajority && highQuality;
    let reason = "Scanning for Over 6 opening...";
    if (digits.length < 10) reason = `Collecting 10 ticks... ${digits.length}/10`;
    else if (!lowMajority) reason = `Scanning for 0-6 majority... low digits ${low10}/10.`;
    else if (!highQuality) reason = `0-6 pattern found. Waiting for 7-9 strength over 10% (best ${strongestHigh.digit}: ${strongestHigh.pct.toFixed(1)}%).`;
    else reason = `Signal found. Low digits ${low10}/10 and digit ${strongestHigh.digit} is ${strongestHigh.pct.toFixed(1)}%.`;
    return { ready, digits, low10, high10, highPercentages, strongestHigh, latest, strength, reason };
  }

  function koolkidOver6ScanStakeForStep(stepValue) {
    const settings = readKoolkidOver6ScanSettings();
    const step = Math.max(1, Math.min(settings.maxSteps, Math.floor(Number(stepValue || getKoolkidOver6ScanState().step) || 1)));
    return Number((settings.baseStake * Math.pow(2, step - 1)).toFixed(2));
  }

  function updateKoolkidOver6ScanMartingalePanel() {
    const st = getKoolkidOver6ScanState();
    const settings = readKoolkidOver6ScanSettings();
    st.maxSteps = settings.maxSteps;
    const signal = analyzeKoolkidOver6Scan();
    const now = Date.now();
    const inCooldown = now < Number(st.cooldownUntil || 0);
    let status = st.status || "Scanning";
    if (inCooldown) status = "Cooldown";
    else if (st.inProgress) status = "Trade placed";
    else if (st.running && signal.ready) status = "Signal found";
    else if (st.running) status = "Scanning";
    const statusNode = document.getElementById("koolkidOver6ScanStatus");
    const strengthNode = document.getElementById("koolkidOver6ScanStrength");
    const stepNode = document.getElementById("koolkidOver6ScanStep");
    const stakeNode = document.getElementById("koolkidOver6ScanStake");
    const reasonNode = document.getElementById("koolkidOver6ScanReason");
    const startBtn = document.getElementById("koolkidOver6ScanStartBtn");
    const stopBtn = document.getElementById("koolkidOver6ScanStopBtn");
    if (statusNode) statusNode.textContent = status;
    if (strengthNode) strengthNode.textContent = `${signal.strength.toFixed(0)}%`;
    if (stepNode) stepNode.textContent = `Martingale step ${Math.max(1, st.step || 1)}/${settings.maxSteps}`;
    if (stakeNode) stakeNode.textContent = money(koolkidOver6ScanStakeForStep(), { stake: settings.baseStake });
    if (reasonNode) {
      const cooldownLeft = inCooldown ? Math.ceil((Number(st.cooldownUntil || 0) - now) / 1000) : 0;
      reasonNode.textContent = inCooldown ? `Cooldown ${cooldownLeft}s after failed cycle.` : (st.reason || signal.reason);
      reasonNode.style.color = signal.ready && !inCooldown ? "#86efac" : "#94a3b8";
    }
    if (startBtn) {
      startBtn.disabled = !!st.running;
      startBtn.style.opacity = st.running ? "0.55" : "1";
    }
    if (stopBtn) {
      stopBtn.disabled = !st.running && !st.inProgress && !inCooldown;
      stopBtn.style.opacity = stopBtn.disabled ? "0.55" : "1";
    }
  }

  function clearKoolkidOver6ScanCooldownTimer() {
    const st = getKoolkidOver6ScanState();
    if (st.cooldownTimer) {
      clearTimeout(st.cooldownTimer);
      st.cooldownTimer = null;
    }
  }

  function scheduleKoolkidOver6ScanCooldown(seconds) {
    const st = getKoolkidOver6ScanState();
    clearKoolkidOver6ScanCooldownTimer();
    st.cooldownUntil = Date.now() + (Math.max(30, Math.min(60, Number(seconds || 45))) * 1000);
    st.status = "Cooldown";
    st.reason = "Cooldown";
    updateKoolkidOver6ScanMartingalePanel();
    st.cooldownTimer = setTimeout(() => {
      st.cooldownTimer = null;
      st.cooldownUntil = 0;
      if (st.running) {
        st.status = "Scanning";
        st.reason = "Scanning for Over 6 opening...";
        maybeRunKoolkidOver6ScanMartingale();
      }
      updateKoolkidOver6ScanMartingalePanel();
    }, Math.max(30, Math.min(60, Number(seconds || 45))) * 1000);
  }

  async function maybeRunKoolkidOver6ScanMartingale(data) {
    if (data) syncKoolkidOver6ScanDigitsFromData(data);
    const st = getKoolkidOver6ScanState();
    if (!st.running || st.inProgress) {
      const now = Date.now();
      if (st.running || now - Number(st.lastUiAt || 0) > 500) {
        st.lastUiAt = now;
        updateKoolkidOver6ScanMartingalePanel();
      }
      return;
    }
    if (Date.now() < Number(st.cooldownUntil || 0)) {
      st.status = "Cooldown";
      updateKoolkidOver6ScanMartingalePanel();
      return;
    }
    const signal = analyzeKoolkidOver6Scan();
    if (!signal.ready) {
      st.status = "Scanning";
      st.reason = signal.reason || "Scanning for Over 6 opening...";
      updateKoolkidOver6ScanMartingalePanel();
      return;
    }
    const settings = readKoolkidOver6ScanSettings();
    const stake = koolkidOver6ScanStakeForStep();
    st.inProgress = true;
    st.pendingContractId = "";
    st.status = "Trade placed";
    st.reason = `Signal found. Sending OVER 6 at ${money(stake)}.`;
    updateKoolkidOver6ScanMartingalePanel();
    try {
      const result = await sendFastManualTradeKoolkid({
        stake,
        amount: stake,
        type: "OVER",
        barrier: 6,
        symbol: getKoolkidOver6ScanSymbol(),
        duration: settings.duration,
        duration_unit: "t",
        mode: "koolkid_over6_scan_martingale",
        action: "OVER_6_SCAN_MARTINGALE",
        label: `Over 6 Scan Martingale step ${st.step}/${settings.maxSteps}`,
      }, { turbo: false, queue: false, fireAndForget: false });
      if (!(result && result.data && result.data.status === "success")) {
        throw new Error((result && result.data && result.data.message) || "Over 6 scan martingale trade failed");
      }
      st.status = "Trade placed";
      st.reason = `Trade placed. Martingale step ${st.step}/${settings.maxSteps}.`;
    } catch (e) {
      st.inProgress = false;
      st.status = "Scanning";
      st.reason = (e && e.message) || "Trade failed. Scanning for Over 6 opening...";
      safeToast(st.reason, "error");
    } finally {
      updateKoolkidOver6ScanMartingalePanel();
    }
  }

  function rememberKoolkidOver6ScanTrade(payload) {
    if (!payload || String(payload.profile || "").toUpperCase() !== PROFILE) return;
    const st = getKoolkidOver6ScanState();
    if (!st.inProgress) return;
    const mode = String(payload.mode || "").toLowerCase();
    const action = String(payload.action || "").toUpperCase();
    if (mode !== "koolkid_over6_scan_martingale" && action !== "OVER_6_SCAN_MARTINGALE") return;
    const contractId = payload.contract_id || payload.buy_contract_id || payload.id;
    if (contractId) st.pendingContractId = String(contractId);
    st.status = "Trade placed";
    st.reason = "Trade placed";
    updateKoolkidOver6ScanMartingalePanel();
  }

  function updateKoolkidOver6ScanFromResult(payload) {
    if (!payload || String(payload.profile || "").toUpperCase() !== PROFILE) return;
    const st = getKoolkidOver6ScanState();
    if (!st.inProgress && !st.pendingContractId) return;
    const contractId = payload.contract_id || payload.buy_contract_id || payload.id;
    const mode = String(payload.mode || "").toLowerCase();
    const action = String(payload.action || "").toUpperCase();
    if (st.pendingContractId) {
      if (contractId && String(contractId) !== String(st.pendingContractId)) return;
      if (!contractId && mode !== "koolkid_over6_scan_martingale" && action !== "OVER_6_SCAN_MARTINGALE") return;
    } else if (mode !== "koolkid_over6_scan_martingale" && action !== "OVER_6_SCAN_MARTINGALE") {
      return;
    }
    const outcome = resolveKoolkidTradeOutcome(payload);
    if (!outcome) return;
    const settings = readKoolkidOver6ScanSettings();
    st.inProgress = false;
    st.pendingContractId = "";
    st.lastResult = outcome;
    if (outcome === "WIN") {
      st.step = 1;
      st.status = "Scanning";
      st.reason = "Win. Reset to base stake. Scanning for Over 6 opening...";
      updateKoolkidOver6ScanMartingalePanel();
      setTimeout(() => maybeRunKoolkidOver6ScanMartingale(), 120);
      return;
    }
    if (Math.max(1, Number(st.step || 1)) >= settings.maxSteps) {
      st.step = 1;
      st.reason = "Max martingale step lost. Resetting stake and entering cooldown.";
      scheduleKoolkidOver6ScanCooldown(settings.cooldownSeconds);
      return;
    }
    st.step = Math.min(settings.maxSteps, Math.max(1, Number(st.step || 1)) + 1);
    st.status = "Scanning";
    st.reason = `Loss. Martingale step ${st.step}/${settings.maxSteps}. Rescanning before recovery.`;
    updateKoolkidOver6ScanMartingalePanel();
    setTimeout(() => maybeRunKoolkidOver6ScanMartingale(), 120);
  }

  function startKoolkidOver6ScanMartingale() {
    const st = getKoolkidOver6ScanState();
    const selectedSymbol = getKoolkidOver6ScanSymbol();
    if (selectedSymbol && st.lastSymbol && st.lastSymbol !== selectedSymbol) {
      st.digits = [];
      st.lastTickCount = null;
    }
    st.lastSymbol = selectedSymbol || st.lastSymbol;
    clearKoolkidOver6ScanCooldownTimer();
    st.running = true;
    st.inProgress = false;
    st.step = 1;
    st.cooldownUntil = 0;
    st.pendingContractId = "";
    st.lastResult = "none";
    st.status = "Scanning";
    st.reason = "Scanning for Over 6 opening...";
    updateKoolkidOver6ScanMartingalePanel();
    maybeRunKoolkidOver6ScanMartingale();
  }

  function stopKoolkidOver6ScanMartingale() {
    const st = getKoolkidOver6ScanState();
    clearKoolkidOver6ScanCooldownTimer();
    st.running = false;
    st.inProgress = false;
    st.step = 1;
    st.cooldownUntil = 0;
    st.pendingContractId = "";
    st.status = "Stopped";
    st.reason = "Stopped.";
    updateKoolkidOver6ScanMartingalePanel();
  }

  function isKoolkidMonthlySingleMartingaleActionAllowed(action) {
    return ["UNDER_3", "UNDER_4", "OVER_5", "OVER_6", "OVER_7"].includes(String(action || "").toUpperCase());
  }

  function syncKoolkidMonthlySingleMartingaleUi() {
    const limited = isKoolkidSingleMartingaleMonthlyLimited();
    const actionEl = document.getElementById("koolkidMartingaleAction");
    if (actionEl) {
      Array.from(actionEl.options || []).forEach((opt) => {
        const action = normalizeKoolkidMartingaleAction(opt.value).action;
        const allowed = !limited || isKoolkidMonthlySingleMartingaleActionAllowed(action);
        opt.hidden = !allowed;
        opt.disabled = !allowed;
      });
      const selected = normalizeKoolkidMartingaleAction(actionEl.value).action;
      if (limited && !isKoolkidMonthlySingleMartingaleActionAllowed(selected)) {
        actionEl.value = "UNDER_3";
      }
    }
    const modeEl = document.getElementById("koolkidMartingaleMode");
    if (modeEl) {
      Array.from(modeEl.options || []).forEach((opt) => {
        const isStep = String(opt.value || "").toUpperCase() === "STEP_005";
        opt.hidden = limited && isStep;
        opt.disabled = limited && isStep;
      });
      if (limited) modeEl.value = "MULTIPLIER";
    }
    const stepWrap = document.getElementById("koolkidMartingaleStepAmountWrap");
    if (stepWrap) stepWrap.style.display = limited ? "none" : "grid";
    const badge = document.getElementById("koolkidMartingaleAccessBadge");
    if (badge) {
      badge.textContent = limited ? "MONTHLY" : "LIFETIME";
      badge.style.color = limited ? "#38bdf8" : "#facc15";
    }
    const note = document.getElementById("koolkidMartingaleLifetimeNote");
    if (note) {
      note.textContent = limited
        ? "Monthly users: UNDER 3, UNDER 4, OVER 5, OVER 6, and OVER 7 only. Multiplier martingale only."
        : "Lifetime users only.";
    }
  }

  function normalizeKoolkidMartingaleAction(value) {
    const text = String(value || "").toUpperCase();
    const compact = text.replace(/\s+/g, "_").replace(/\+/g, "_").replace(/__+/g, "_");
    if (compact === "UNDER_3_OVER_6") {
      return {
        action: "UNDER_3_OVER_6",
        type: "PAIR",
        barrier: null,
        label: "UNDER 3 + OVER 6",
        isPair: true,
        legs: [
          { action: "UNDER_3", type: "UNDER", barrier: 3, label: "UNDER 3" },
          { action: "OVER_6", type: "OVER", barrier: 6, label: "OVER 6" },
        ],
      };
    }
    if (compact === "OVER_4_UNDER_5") {
      return {
        action: "OVER_4_UNDER_5",
        type: "PAIR",
        barrier: null,
        label: "OVER 4 + UNDER 5",
        isPair: true,
        independentPair: true,
        legs: [
          { action: "OVER_4", type: "OVER", barrier: 4, label: "OVER 4" },
          { action: "UNDER_5", type: "UNDER", barrier: 5, label: "UNDER 5" },
        ],
      };
    }
    if (compact === "OVER_3_OVER_6" || compact === "UNDER_3_OVER_3_OVER_6") {
      return {
        action: "OVER_3_OVER_6",
        type: "BATCH",
        barrier: null,
        label: "OVER 3 + OVER 6",
        isPair: true,
        isTriple: true,
        legs: [
          { action: "OVER_3", type: "OVER", barrier: 3, label: "OVER 3", fixedCycle: true, controlsStop: false },
          { action: "OVER_6", type: "OVER", barrier: 6, label: "OVER 6", controlsStop: true },
        ],
      };
    }
    const parsed = text.match(/\b(UNDER|OVER)\s*_?\s*([0-9])\b/);
    const key = parsed ? `${parsed[1]}_${parsed[2]}` : compact;
    if (compact === "OVER_2_TARGET" || compact === "OVER_2_TP") {
      return { action: "OVER_2_TARGET", type: "OVER", barrier: 2, label: "OVER 2 Target Profit", targetProfitMode: true };
    }
    if (compact === "OVER_3_TARGET" || compact === "OVER_3_TP") {
      return { action: "OVER_3_TARGET", type: "OVER", barrier: 3, label: "OVER 3 Target Profit", targetProfitMode: true };
    }
    const map = {
      UNDER_3: { action: "UNDER_3", type: "UNDER", barrier: 3, label: "UNDER 3" },
      UNDER_4: { action: "UNDER_4", type: "UNDER", barrier: 4, label: "UNDER 4" },
      UNDER_5: { action: "UNDER_5", type: "UNDER", barrier: 5, label: "UNDER 5" },
      OVER_4: { action: "OVER_4", type: "OVER", barrier: 4, label: "OVER 4" },
      OVER_5: { action: "OVER_5", type: "OVER", barrier: 5, label: "OVER 5" },
      OVER_6: { action: "OVER_6", type: "OVER", barrier: 6, label: "OVER 6" },
      OVER_7: { action: "OVER_7", type: "OVER", barrier: 7, label: "OVER 7" },
      OVER_8: { action: "OVER_8", type: "OVER", barrier: 8, label: "OVER 8" },
    };
    return map[key] || map.UNDER_3;
  }

  function readKoolkidMartingaleNumber(id, fallback, min, max) {
    const el = document.getElementById(id);
    const raw = el ? Number(el.value) : Number(fallback);
    let value = Number.isFinite(raw) ? raw : Number(fallback);
    if (Number.isFinite(Number(min))) value = Math.max(Number(min), value);
    if (Number.isFinite(Number(max))) value = Math.min(Number(max), value);
    return value;
  }

  function isOver3Under6PairModeKoolkid() {
    return false;
  }

  function getOver3Under6PairStateKoolkid() {
    const st = getKoolkidSingleMartingaleState();
    if (!st.over3Under6Pair) {
      st.over3Under6Pair = {
        running: false,
        enabled: false,
        inProgress: false,
        round: 1,
        pendingContracts: {},
        pendingExpected: 0,
        pendingSettled: 0,
        lastDigit: null,
        status: "Ready",
        availabilityError: "",
        over3_state: { current_stake: 0.35, loss_bank: 0, step: 1, last_result: "none" },
        under6_state: { current_stake: 0.35, loss_bank: 0, step: 1, last_result: "none" },
      };
    }
    return st.over3Under6Pair;
  }

  function readOver3Under6PairSettingsKoolkid() {
    return {
      duration: Math.max(1, Math.min(10, Math.floor(readKoolkidMartingaleNumber("koolkidMartingaleDuration", 1, 1, 10)))),
      over3BaseStake: Number(readKoolkidMartingaleNumber("koolkidPairOver3BaseStake", 0.35, 0.35, 1000000).toFixed(2)),
      under6BaseStake: Number(readKoolkidMartingaleNumber("koolkidPairUnder6BaseStake", 0.35, 0.35, 1000000).toFixed(2)),
      targetProfit: Number(readKoolkidMartingaleNumber("koolkidPairTargetProfit", 0.05, 0.01, 1000000).toFixed(2)),
      payoutMultiplier: Math.max(0.01, Number(readKoolkidMartingaleNumber("koolkidPairPayoutMultiplier", 0.63, 0.01, 100).toFixed(4))),
    };
  }

  function calculateNextOver3Under6SideStakeKoolkid(lossBank, targetProfit, payoutMultiplier) {
    const next = (Number(lossBank || 0) + Number(targetProfit || 0.05)) / Math.max(0.01, Number(payoutMultiplier || 0.63));
    return Number(Math.max(0.35, Math.ceil((next - 1e-9) * 100) / 100).toFixed(2));
  }

  function isKoolkidTargetProfitMartingaleAction(action) {
    return ["OVER_2_TARGET", "OVER_3_TARGET"].includes(String(action || "").toUpperCase());
  }

  function getKoolkidTargetProfitMartingaleState(action) {
    const st = getKoolkidSingleMartingaleState();
    st.targetProfit = st.targetProfit || {};
    const key = isKoolkidTargetProfitMartingaleAction(action) ? String(action).toUpperCase() : "OVER_2_TARGET";
    if (!st.targetProfit[key]) {
      st.targetProfit[key] = { currentStake: 0.35, lossBank: 0, step: 1, sessionProfit: 0, lastResult: "none" };
    }
    return st.targetProfit[key];
  }

  function readKoolkidTargetProfitMartingaleSettings() {
    return {
      targetProfit: Number(readKoolkidMartingaleNumber("koolkidTargetMartingaleProfit", 0.35, 0.01, 1000000).toFixed(2)),
      payoutMultiplier: Math.max(0.01, Number(readKoolkidMartingaleNumber("koolkidTargetMartingalePayout", 0.63, 0.01, 100).toFixed(4))),
      takeProfit: Number(readKoolkidMartingaleNumber("koolkidTargetMartingaleTP", 0, 0, 1000000).toFixed(2)),
      stopLoss: Number(readKoolkidMartingaleNumber("koolkidTargetMartingaleSL", 0, 0, 1000000).toFixed(2)),
    };
  }

  function readKoolkidSingleMartingaleRiskSettings() {
    const takeProfit = Number(readKoolkidMartingaleNumber("koolkidMartingaleTP", 0, 0, 1000000).toFixed(2));
    const stopLoss = Number(readKoolkidMartingaleNumber("koolkidMartingaleSL", 0, 0, 1000000).toFixed(2));
    return {
      takeProfit,
      stopLoss,
      active: takeProfit > 0 || stopLoss > 0,
    };
  }

  function calculateNextKoolkidTargetProfitStake(lossBank, targetProfit, payoutMultiplier) {
    const next = (Number(lossBank || 0) + Number(targetProfit || 0.35)) / Math.max(0.01, Number(payoutMultiplier || 0.63));
    return Number(Math.max(0.35, Math.ceil((next - 1e-9) * 100) / 100).toFixed(2));
  }

  function resetKoolkidTargetProfitMartingaleAction(action, baseStake) {
    const target = getKoolkidTargetProfitMartingaleState(action);
    target.currentStake = Number(Math.max(0.35, Number(baseStake || 0.35)).toFixed(2));
    target.lossBank = 0;
    target.step = 1;
    target.lastResult = "none";
  }

  function resetOver3Under6SideStateKoolkid(sideState, baseStake) {
    sideState.current_stake = Number(Math.max(0.35, Number(baseStake || 0.35)).toFixed(2));
    sideState.loss_bank = 0;
    sideState.step = 1;
    sideState.last_result = "none";
  }

  function resetOver3Under6PairStateKoolkid(status) {
    const pair = getOver3Under6PairStateKoolkid();
    const settings = readOver3Under6PairSettingsKoolkid();
    pair.inProgress = false;
    pair.pendingContracts = {};
    pair.pendingExpected = 0;
    pair.pendingSettled = 0;
    pair.lastDigit = null;
    pair.round = 1;
    pair.status = status || "Ready";
    resetOver3Under6SideStateKoolkid(pair.over3_state, settings.over3BaseStake);
    resetOver3Under6SideStateKoolkid(pair.under6_state, settings.under6BaseStake);
    updateKoolkidSingleMartingalePanel();
  }

  function updateOver3Under6SideAfterWinKoolkid(sideState, baseStake) {
    resetOver3Under6SideStateKoolkid(sideState, baseStake);
    sideState.last_result = "WIN";
  }

  function updateOver3Under6SideAfterLossKoolkid(sideState, settings) {
    const stake = Number(sideState.current_stake || 0.35);
    sideState.loss_bank = Number((Number(sideState.loss_bank || 0) + stake).toFixed(2));
    sideState.step = Math.max(1, Math.floor(Number(sideState.step || 1))) + 1;
    sideState.current_stake = calculateNextOver3Under6SideStakeKoolkid(sideState.loss_bank, settings.targetProfit, settings.payoutMultiplier);
    sideState.last_result = "LOSS";
  }

  function readKoolkidSingleMartingaleSettings() {
    const st = getKoolkidSingleMartingaleState();
    syncKoolkidMonthlySingleMartingaleUi();
    const actionEl = document.getElementById("koolkidMartingaleAction");
    let action = normalizeKoolkidMartingaleAction(actionEl ? actionEl.value : st.action);
    if (isKoolkidSingleMartingaleMonthlyLimited() && !isKoolkidMonthlySingleMartingaleActionAllowed(action.action)) {
      if (actionEl) actionEl.value = "UNDER_3";
      action = normalizeKoolkidMartingaleAction("UNDER_3");
    }
    const duration = Math.max(1, Math.min(10, Math.floor(readKoolkidMartingaleNumber("koolkidMartingaleDuration", 1, 1, 10))));
    const startStake = Number(readKoolkidMartingaleNumber("koolkidMartingaleStartStake", 0.35, 0.35, 1000000).toFixed(2));
    const tickSpacing = Math.max(1, Math.min(10, Math.floor(readKoolkidMartingaleNumber("koolkidMartingaleTickSpacing", 1, 1, 10))));
    const modeEl = document.getElementById("koolkidMartingaleMode");
    const mode = isKoolkidSingleMartingaleMonthlyLimited()
      ? "MULTIPLIER"
      : (String((modeEl && modeEl.value) || "STEP_005").toUpperCase() === "MULTIPLIER" ? "MULTIPLIER" : "STEP_005");
    const stepAmount = Number(readKoolkidMartingaleNumber("koolkidMartingaleStepAmount", 0.05, 0.01, 1000000).toFixed(2));
    const multiplier = Math.max(1, readKoolkidMartingaleNumber("koolkidMartingaleMultiplier", 2, 1, 100));
    const maxSteps = Math.max(1, Math.floor(readKoolkidMartingaleNumber("koolkidMartingaleMaxSteps", 1000, 1, 1000000)));
    const doubleLimit = Math.max(0, Math.floor(readKoolkidMartingaleNumber("koolkidMartingaleDoubleLimit", 0, 0, 1000000)));
    const capEl = document.getElementById("koolkidMartingaleMaxStake");
    const maxStake = capEl && String(capEl.value || "").trim() !== ""
      ? Number(readKoolkidMartingaleNumber("koolkidMartingaleMaxStake", 0, 0, 1000000).toFixed(2))
      : null;
    return {
      action: action.action,
      type: action.type,
      barrier: action.barrier,
      label: action.label,
      isPair: !!action.isPair,
      isTriple: !!action.isTriple,
      independentPair: !!action.independentPair,
      targetProfitMode: !!action.targetProfitMode,
      legs: action.legs || null,
      duration,
      startStake,
      tickSpacing,
      mode,
      stepAmount,
      multiplier,
      maxSteps,
      maxStake,
      doubleLimit
    };
  }

  function nextKoolkidLimitedMartingaleStep(currentStep, settings) {
    const step = Math.max(1, Math.min(settings.maxSteps || 1000000, Math.floor(Number(currentStep || 1) || 1)));
    const limit = Math.max(0, Math.floor(Number(settings.doubleLimit || 0) || 0));
    if (limit > 0 && (step - 1) >= limit) return 1;
    return Math.min(settings.maxSteps || 1000000, step + 1);
  }

  function koolkidSingleMartingaleStakeForLeg(leg, stepValue) {
    const settings = readKoolkidSingleMartingaleSettings();
    const step = Math.max(1, Math.min(settings.maxSteps, Math.floor(Number(stepValue || getKoolkidSingleMartingaleState().step) || 1)));
    if (settings.independentPair && leg && leg.action) {
      const st = getKoolkidSingleMartingaleState();
      const pairSteps = st.pairSteps || {};
      const legStep = Math.max(1, Math.min(settings.maxSteps, Math.floor(Number(pairSteps[leg.action] || 1) || 1)));
      let stake = settings.startStake * Math.pow(settings.multiplier, legStep - 1);
      if (settings.maxStake !== null) stake = Math.min(stake, settings.maxStake);
      return Number(Math.max(0.35, stake).toFixed(2));
    }
    if (leg && leg.fixedCycle) {
      const st = getKoolkidSingleMartingaleState();
      const fixedStep = Math.max(1, Math.min(3, Math.floor(Number(st.over3Step || 1) || 1)));
      const cycleIndex = (fixedStep - 1) % 3;
      return Number((1 * Math.pow(2, cycleIndex)).toFixed(2));
    }
    return koolkidSingleMartingaleStakeForStep(step);
  }

  function koolkidSingleMartingaleNextOver3StakeAfterLoss() {
    const st = getKoolkidSingleMartingaleState();
    const currentStep = Math.max(1, Math.min(3, Math.floor(Number(st.over3Step || 1) || 1)));
    const nextStep = currentStep >= 3 ? 1 : currentStep + 1;
    return Number((1 * Math.pow(2, nextStep - 1)).toFixed(2));
  }

  function koolkidSingleMartingaleStakeForStep(stepValue) {
    const settings = readKoolkidSingleMartingaleSettings();
    const st = getKoolkidSingleMartingaleState();
    const step = Math.max(1, Math.min(settings.maxSteps, Math.floor(Number(stepValue || st.step) || 1)));
    let stake = settings.isPair
      ? settings.startStake * Math.pow(settings.multiplier, step - 1)
      : settings.mode === "STEP_005"
      ? settings.startStake + ((step - 1) * settings.stepAmount)
      : settings.startStake * Math.pow(settings.multiplier, step - 1);
    if (settings.maxStake !== null) stake = Math.min(stake, settings.maxStake);
    return Number(Math.max(0.35, stake).toFixed(2));
  }

  function formatKoolkidMartingaleCalculatorMoney(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) return "$0.00";
    const sign = num < 0 ? "-" : "";
    return `${sign}$${Math.abs(num).toFixed(2)}`;
  }

  function readKoolkidDisplayedBalance() {
    const node = document.getElementById("balance");
    const text = node ? String(node.textContent || "") : "";
    const matches = text.replace(/,/g, "").match(/-?\d+(?:\.\d+)?/g);
    const value = matches && matches.length ? Number(matches[matches.length - 1]) : 0;
    return Number.isFinite(value) ? Math.max(0, value) : 0;
  }

  function estimateKoolkidDigitProfitMultiplier(type, barrier) {
    const key = `${String(type || "").toUpperCase()}_${Math.max(0, Math.min(9, Math.floor(Number(barrier) || 0)))}`;
    const table = {
      UNDER_1: 8,
      UNDER_2: 3.33,
      UNDER_3: 2.14,
      UNDER_4: 1.43,
      UNDER_5: 0.95,
      UNDER_6: 0.63,
      UNDER_7: 0.43,
      UNDER_8: 0.24,
      UNDER_9: 0.1,
      OVER_0: 0.1,
      OVER_1: 0.24,
      OVER_2: 0.43,
      OVER_3: 0.63,
      OVER_4: 0.95,
      OVER_5: 1.43,
      OVER_6: 2.14,
      OVER_7: 3.33,
      OVER_8: 8,
    };
    if (table[key]) return table[key];
    const wins = String(type || "").toUpperCase() === "UNDER" ? Number(barrier) : 9 - Number(barrier);
    if (!Number.isFinite(wins) || wins <= 0) return 0.63;
    return Number(Math.max(0.01, (((10 / wins) - 1) * 0.94)).toFixed(2));
  }

  function estimateKoolkidMartingaleLegProfitMultiplier(leg, settings) {
    if (settings && settings.targetProfitMode) {
      return readKoolkidTargetProfitMartingaleSettings().payoutMultiplier;
    }
    const normalized = normalizeKoolkidMartingaleAction((leg && leg.action) || (settings && settings.action));
    return estimateKoolkidDigitProfitMultiplier((leg && leg.type) || normalized.type, (leg && leg.barrier) ?? normalized.barrier);
  }

  function resolveKoolkidMartingaleProfit(payload, outcome, stake, settings, leg) {
    const direct = Number(payload && (payload.profit ?? payload.pnl ?? payload.net_profit));
    if (Number.isFinite(direct)) return Number(direct.toFixed(2));
    const safeStake = Math.max(0, Number(stake || 0));
    if (outcome === "LOSS") return Number((-safeStake).toFixed(2));
    if (outcome === "WIN") {
      const multiplier = estimateKoolkidMartingaleLegProfitMultiplier(leg || null, settings || readKoolkidSingleMartingaleSettings());
      return Number((safeStake * Number(multiplier || 0)).toFixed(2));
    }
    return 0;
  }

  function resetKoolkidSingleMartingaleSteps() {
    const st = getKoolkidSingleMartingaleState();
    st.step = 1;
    st.over3Step = 1;
    st.pairSteps = {};
  }

  function scheduleKoolkidSingleMartingaleContinuation(st, settings, reason) {
    if (!st || !settings || !st.enabled || !st.running || st.stopRequested) return false;
    if (st.restartTimer) clearTimeout(st.restartTimer);
    st.restartTimer = null;
    st.tickSpacing = settings.tickSpacing;
    st.waitTicksRemaining = settings.tickSpacing;
    st.waitingForTicks = true;
    st.status = reason || `Waiting ${settings.tickSpacing} tick${settings.tickSpacing === 1 ? "" : "s"}`;
    return true;
  }

  function stopKoolkidSingleMartingaleOnRiskLimit(st, hitTp, sessionProfit) {
    if (!st) return;
    resetKoolkidSingleMartingaleSteps();
    st.running = false;
    st.enabled = false;
    st.stopRequested = true;
    st.waitingForTicks = false;
    st.waitTicksRemaining = 0;
    st.status = hitTp ? "TP reached" : "SL reached";
    safeToast(
      hitTp
        ? `KOOLKID martingale TP reached. Session profit $${Number(sessionProfit || 0).toFixed(2)}.`
        : `KOOLKID martingale SL reached. Session P/L $${Number(sessionProfit || 0).toFixed(2)}.`,
      hitTp ? "success" : "error"
    );
  }

  function koolkidMartingaleCalculatorStakeForStep(settings, step) {
    const safeStep = Math.max(1, Math.floor(Number(step || 1) || 1));
    let stake = settings.isPair || settings.mode === "MULTIPLIER"
      ? settings.startStake * Math.pow(settings.multiplier, safeStep - 1)
      : settings.startStake + ((safeStep - 1) * settings.stepAmount);
    if (settings.maxStake !== null) stake = Math.min(stake, settings.maxStake);
    return Number(Math.max(0.35, stake).toFixed(2));
  }

  function koolkidMartingaleCalculatorLegRows(settings, step) {
    if (settings.targetProfitMode || !settings.legs || !settings.legs.length) {
      const stake = koolkidMartingaleCalculatorStakeForStep(settings, step);
      return [{
        label: settings.label,
        stake,
        multiplier: estimateKoolkidMartingaleLegProfitMultiplier(null, settings),
      }];
    }
    return settings.legs.map((leg) => {
      let stake;
      if (leg.fixedCycle) {
        const cycleStep = ((Math.max(1, Math.floor(Number(step || 1) || 1)) - 1) % 3) + 1;
        stake = Number((1 * Math.pow(2, cycleStep - 1)).toFixed(2));
      } else {
        stake = koolkidMartingaleCalculatorStakeForStep(settings, step);
      }
      return {
        label: leg.label || settings.label,
        stake,
        multiplier: estimateKoolkidMartingaleLegProfitMultiplier(leg, settings),
      };
    });
  }

  function buildKoolkidMartingaleCalculatorRows(settings, amount) {
    const available = Math.max(0, Number(amount || 0));
    const maxConfiguredSteps = Math.max(1, Math.floor(Number(settings.maxSteps || 1) || 1));
    const cappedSteps = settings.doubleLimit > 0 ? Math.min(maxConfiguredSteps, Number(settings.doubleLimit) + 1) : maxConfiguredSteps;
    const hardLimit = Math.min(Math.max(1, cappedSteps), 5000);
    const rows = [];
    let cumulative = 0;
    let affordableTrades = 0;
    let affordableContracts = 0;

    if (settings.targetProfitMode) {
      const targetSettings = readKoolkidTargetProfitMartingaleSettings();
      const targetState = getKoolkidTargetProfitMartingaleState(settings.action);
      let stake = Number(targetState.currentStake || settings.startStake);
      let lossBank = Number(targetState.lossBank || 0);
      for (let step = 1; step <= hardLimit; step += 1) {
        stake = Number(Math.max(0.35, stake).toFixed(2));
        cumulative = Number((cumulative + stake).toFixed(2));
        const previousLosses = Number(Math.max(0, lossBank).toFixed(2));
        const profit = Number((stake * targetSettings.payoutMultiplier).toFixed(2));
        const netProfit = Number((profit - previousLosses).toFixed(2));
        const affordable = cumulative <= available + 1e-9;
        if (affordable) {
          affordableTrades += 1;
          affordableContracts += 1;
        }
        if (rows.length < 12 || !affordable) {
          rows.push({
            step,
            stake,
            contracts: 1,
            profit,
            previousLosses,
            netProfit,
            cumulative,
            affordable,
            details: `${settings.label}: ${formatKoolkidMartingaleCalculatorMoney(stake)}`,
          });
        }
        if (!affordable) break;
        lossBank = Number((lossBank + stake).toFixed(2));
        stake = calculateNextKoolkidTargetProfitStake(lossBank, targetSettings.targetProfit, targetSettings.payoutMultiplier);
      }
      return { rows, affordableTrades, affordableContracts, cumulative, capped: cappedSteps > 5000 };
    }

    for (let step = 1; step <= hardLimit; step += 1) {
      const legs = koolkidMartingaleCalculatorLegRows(settings, step);
      const roundStake = Number(legs.reduce((sum, leg) => sum + Number(leg.stake || 0), 0).toFixed(2));
      const profit = Number(legs.reduce((sum, leg) => sum + (Number(leg.stake || 0) * Number(leg.multiplier || 0)), 0).toFixed(2));
      const previousLosses = Number(cumulative.toFixed(2));
      const netProfit = Number((profit - previousLosses).toFixed(2));
      cumulative = Number((cumulative + roundStake).toFixed(2));
      const affordable = cumulative <= available + 1e-9;
      if (affordable) {
        affordableTrades += 1;
        affordableContracts += legs.length;
      }
      if (rows.length < 12 || !affordable) {
        rows.push({
          step,
          stake: roundStake,
          contracts: legs.length,
          profit,
          previousLosses,
          netProfit,
          cumulative,
          affordable,
          details: legs.map((leg) => `${leg.label}: ${formatKoolkidMartingaleCalculatorMoney(leg.stake)}`).join(" + "),
        });
      }
      if (!affordable) break;
    }
    return { rows, affordableTrades, affordableContracts, cumulative, capped: cappedSteps > 5000 };
  }

  function updateKoolkidMartingaleCalculator() {
    const popup = document.getElementById("koolkidMartingaleCalculatorPopup");
    const results = document.getElementById("koolkidMartingaleCalculatorResults");
    if (!popup || !results) return;
    const settings = readKoolkidSingleMartingaleSettings();
    const balance = readKoolkidDisplayedBalance();
    const amountEl = document.getElementById("koolkidMartingaleCalculatorAmount");
    const customAmount = amountEl && String(amountEl.value || "").trim() !== "" ? Number(amountEl.value) : NaN;
    const amount = Number.isFinite(customAmount) && customAmount > 0 ? customAmount : balance;
    const balanceEl = document.getElementById("koolkidMartingaleCalculatorBalance");
    const contractEl = document.getElementById("koolkidMartingaleCalculatorContract");
    const startStakeEl = document.getElementById("koolkidMartingaleCalculatorStartStake");
    if (balanceEl) balanceEl.textContent = formatKoolkidMartingaleCalculatorMoney(balance);
    if (contractEl) contractEl.textContent = settings.label;
    if (startStakeEl) startStakeEl.textContent = formatKoolkidMartingaleCalculatorMoney(settings.startStake);

    const calc = buildKoolkidMartingaleCalculatorRows(settings, amount);
    const noun = settings.isPair ? "rounds" : "trades";
    const doubleUps = Math.max(0, calc.affordableTrades - 1);
    const rows = calc.rows || [];
    const rowHtml = rows.length
      ? rows.map((row) => `
        <div style="display:grid; grid-template-columns:54px 1fr 88px; gap:8px; align-items:center; padding:8px; border:1px solid ${row.affordable ? "#334155" : "#7f1d1d"}; border-radius:10px; margin-top:6px; background:${row.affordable ? "#111827" : "rgba(127,29,29,0.18)"};">
          <div style="font-weight:900; color:${row.affordable ? "#f8fafc" : "#fca5a5"};">#${row.step}</div>
          <div style="min-width:0;">
            <div style="color:#e2e8f0; font-weight:800;">${escapeHtmlKoolkid(row.details || settings.label)}</div>
            <div style="color:#94a3b8; font-size:11px;">Need ${formatKoolkidMartingaleCalculatorMoney(row.cumulative)} total - ${row.contracts} contract${row.contracts === 1 ? "" : "s"}</div>
            <div style="color:${Number(row.netProfit || 0) >= 0 ? "#86efac" : "#fca5a5"}; font-size:11px;">Net after previous losses: ${formatKoolkidMartingaleCalculatorMoney(row.netProfit || 0)}</div>
          </div>
          <div style="text-align:right; color:#86efac; font-weight:900;">+${formatKoolkidMartingaleCalculatorMoney(row.profit)}</div>
        </div>
      `).join("")
      : `<div style="padding:8px; border:1px solid #334155; border-radius:10px;">Enter an amount to preview this setup.</div>`;

    results.innerHTML = `
      <div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); gap:8px;">
        <div style="padding:8px; border:1px solid #334155; border-radius:10px; background:#111827;">
          <div style="color:#94a3b8; font-size:11px; font-weight:800;">Amount Checked</div>
          <div style="font-weight:900; color:#f8fafc;">${formatKoolkidMartingaleCalculatorMoney(amount)}</div>
        </div>
        <div style="padding:8px; border:1px solid #334155; border-radius:10px; background:#111827;">
          <div style="color:#94a3b8; font-size:11px; font-weight:800;">Can Cover</div>
          <div style="font-weight:900; color:#f8fafc;">${calc.affordableTrades} ${noun}</div>
        </div>
        <div style="padding:8px; border:1px solid #334155; border-radius:10px; background:#111827;">
          <div style="color:#94a3b8; font-size:11px; font-weight:800;">Double-Ups</div>
          <div style="font-weight:900; color:#f8fafc;">${doubleUps}</div>
        </div>
        <div style="padding:8px; border:1px solid #334155; border-radius:10px; background:#111827;">
          <div style="color:#94a3b8; font-size:11px; font-weight:800;">Contracts</div>
          <div style="font-weight:900; color:#f8fafc;">${calc.affordableContracts}</div>
        </div>
      </div>
      <div style="margin-top:8px; color:#94a3b8; font-size:11px;">Profit is an estimate from the selected digit contract payout. Live Deriv proposals can vary slightly by market.</div>
      ${rowHtml}
      ${calc.capped ? `<div style="margin-top:8px; color:#facc15; font-size:11px;">Preview capped at 5000 steps for performance.</div>` : ""}
    `;
  }

  function openKoolkidMartingaleCalculator() {
    const popup = document.getElementById("koolkidMartingaleCalculatorPopup");
    const amountEl = document.getElementById("koolkidMartingaleCalculatorAmount");
    if (amountEl && String(amountEl.value || "").trim() === "") {
      amountEl.value = String(readKoolkidDisplayedBalance() || "");
    }
    updateKoolkidMartingaleCalculator();
    if (popup) popup.style.display = "flex";
  }

  function closeKoolkidMartingaleCalculator() {
    const popup = document.getElementById("koolkidMartingaleCalculatorPopup");
    if (popup) popup.style.display = "none";
  }

  function updateKoolkidMartingaleCalculatorIfOpen() {
    const popup = document.getElementById("koolkidMartingaleCalculatorPopup");
    if (popup && popup.style.display !== "none") updateKoolkidMartingaleCalculator();
  }

  function clearKoolkidSingleMartingalePending() {
    const st = getKoolkidSingleMartingaleState();
    st.inProgress = false;
    st.pendingAction = "";
    st.pendingContractId = "";
    st.pendingContracts = {};
    st.pendingExpected = 0;
    st.pendingSettled = 0;
    st.pendingPair = false;
    st.pendingHasWin = false;
    st.pendingStake = 0;
    st.pendingMartingale = false;
  }

  function updateKoolkidSingleMartingalePanel() {
    const st = getKoolkidSingleMartingaleState();
    const allowed = canUseKoolkidSingleMartingale();
    const panel = document.getElementById("koolkidSingleMartingalePanel");
    if (panel) panel.style.display = allowed ? "" : "none";
    if (!allowed) return;
    syncKoolkidMonthlySingleMartingaleUi();

    const settings = readKoolkidSingleMartingaleSettings();
    const pairMode = isOver3Under6PairModeKoolkid();
    const targetMode = !pairMode && !!settings.targetProfitMode;
    const pairSettingsWrap = document.getElementById("koolkidOver3Under6PairSettings");
    if (pairSettingsWrap) pairSettingsWrap.style.display = pairMode ? "" : "none";
    const targetSettingsWrap = document.getElementById("koolkidTargetProfitMartingaleSettings");
    if (targetSettingsWrap) targetSettingsWrap.style.display = targetMode ? "" : "none";
    const riskSettingsWrap = document.getElementById("koolkidMartingaleRiskSettings");
    if (riskSettingsWrap) riskSettingsWrap.style.display = (!pairMode && !targetMode) ? "grid" : "none";
    ["koolkidMartingaleAction", "koolkidMartingaleMode", "koolkidMartingaleStepAmount", "koolkidMartingaleMultiplier", "koolkidMartingaleMaxSteps", "koolkidMartingaleMaxStake", "koolkidMartingaleDoubleLimit", "koolkidMartingaleTickSpacing", "koolkidMartingaleStartStake"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.disabled = pairMode;
    });
    ["koolkidMartingaleMode", "koolkidMartingaleStepAmount", "koolkidMartingaleMultiplier", "koolkidMartingaleMaxSteps", "koolkidMartingaleMaxStake", "koolkidMartingaleDoubleLimit"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.disabled = pairMode || targetMode;
    });
    const pair = getOver3Under6PairStateKoolkid();
    const pairSettings = readOver3Under6PairSettingsKoolkid();
    const pairStatus = document.getElementById("koolkidPairStatus");
    if (pairStatus) {
      const over = pair.over3_state || {};
      const under = pair.under6_state || {};
      const errorText = pair.availabilityError ? ` - ${pair.availabilityError}` : "";
      pairStatus.textContent = `${pair.status || "Ready"}${errorText} - Round ${pair.round || 1} - Over 3 stake $${Number(over.current_stake || pairSettings.over3BaseStake).toFixed(2)} / bank $${Number(over.loss_bank || 0).toFixed(2)} / step ${over.step || 1} - Under 6 stake $${Number(under.current_stake || pairSettings.under6BaseStake).toFixed(2)} / bank $${Number(under.loss_bank || 0).toFixed(2)} / step ${under.step || 1} - Last digit ${pair.lastDigit === null || pair.lastDigit === undefined ? "-" : pair.lastDigit}`;
      pairStatus.style.color = pair.inProgress ? "#fbbf24" : pair.status === "Error" ? "#fca5a5" : "#94a3b8";
    }
    const pairStart = document.getElementById("koolkidPairStartBtn");
    if (pairStart) pairStart.disabled = !!(pair.running || pair.inProgress);
    const pairStop = document.getElementById("koolkidPairStopBtn");
    if (pairStop) pairStop.disabled = !(pair.running || pair.inProgress);
    st.action = settings.action;
    const toggleBtn = document.getElementById("koolkidMartingaleToggleBtn");
    if (toggleBtn) {
      toggleBtn.textContent = pairMode ? `PAIR: ${pair.running ? "ON" : "OFF"}` : `MARTINGALE: ${st.enabled ? "ON" : "OFF"}`;
      toggleBtn.style.background = (pairMode ? pair.running : st.enabled) ? "#f59e0b" : "#334155";
      toggleBtn.style.color = (pairMode ? pair.running : st.enabled) ? "#111827" : "#f8fafc";
    }
    const placeBtn = document.getElementById("koolkidMartingalePlaceBtn");
    if (placeBtn) {
      placeBtn.textContent = pairMode ? "START PAIR" : "PLACE SELECTED CONTRACT";
      placeBtn.disabled = pairMode ? !!(pair.running || pair.inProgress) : !!(st.inProgress || st.running);
      placeBtn.style.opacity = placeBtn.disabled ? "0.55" : "1";
      placeBtn.style.cursor = placeBtn.disabled ? "not-allowed" : "pointer";
    }
    const stopBtn = document.getElementById("koolkidMartingaleQuickStopBtn");
    if (stopBtn) {
      stopBtn.textContent = pairMode ? "STOP PAIR" : "QUICK STOP";
      const canStop = pairMode ? !!(pair.running || pair.inProgress) : !!(st.running || st.inProgress || st.waitingForTicks);
      stopBtn.disabled = !canStop;
      stopBtn.style.opacity = canStop ? "1" : "0.55";
      stopBtn.style.cursor = canStop ? "pointer" : "not-allowed";
    }
    const status = document.getElementById("koolkidMartingaleStatus");
    if (status) {
      status.style.display = pairMode ? "none" : "";
      if (pairMode) {
        updateKoolkidMartingaleCalculatorIfOpen();
        return;
      }
      const currentStake = koolkidSingleMartingaleStakeForStep();
      const nextStep = nextKoolkidLimitedMartingaleStep(st.step, settings);
      const nextStake = st.enabled ? koolkidSingleMartingaleStakeForStep(nextStep) : settings.startStake;
      if (targetMode) {
        const targetSettings = readKoolkidTargetProfitMartingaleSettings();
        const targetState = getKoolkidTargetProfitMartingaleState(settings.action);
        const current = Number(targetState.currentStake || settings.startStake);
        const nextLoss = calculateNextKoolkidTargetProfitStake(Number(targetState.lossBank || 0) + current, targetSettings.targetProfit, targetSettings.payoutMultiplier);
        const tpText = targetSettings.takeProfit > 0 ? `TP $${targetSettings.takeProfit.toFixed(2)}` : "TP off";
        const slText = targetSettings.stopLoss > 0 ? `SL $${targetSettings.stopLoss.toFixed(2)}` : "SL off";
        status.textContent = `${st.status}. ${settings.label} - Target $${targetSettings.targetProfit.toFixed(2)} - Current stake $${current.toFixed(2)} - If loss next $${nextLoss.toFixed(2)} - Bank $${Number(targetState.lossBank || 0).toFixed(2)} - Step ${targetState.step || 1} - Session P/L $${Number(targetState.sessionProfit || 0).toFixed(2)} - ${tpText} / ${slText} - Last result: ${targetState.lastResult || st.lastResult}`;
        status.style.color = st.inProgress ? "#fbbf24" : "#94a3b8";
        updateKoolkidMartingaleCalculatorIfOpen();
        return;
      }
      const modeLabel = settings.isPair ? `paired ${settings.multiplier}x` : (settings.mode === "STEP_005" ? `$${settings.stepAmount.toFixed(2)} step` : `${settings.multiplier}x`);
      const limitLabel = settings.doubleLimit > 0 ? ` - Limit ${settings.doubleLimit} double-up${settings.doubleLimit === 1 ? "" : "s"}` : "";
      const riskSettings = readKoolkidSingleMartingaleRiskSettings();
      const tpText = riskSettings.takeProfit > 0 ? `TP $${riskSettings.takeProfit.toFixed(2)}` : "TP off";
      const slText = riskSettings.stopLoss > 0 ? `SL $${riskSettings.stopLoss.toFixed(2)}` : "SL off";
      const waitTotal = Math.max(1, Math.floor(Number(st.tickSpacing || settings.tickSpacing) || settings.tickSpacing));
      const waitText = st.waitingForTicks
        ? `Waiting ${st.waitTicksRemaining}/${waitTotal} tick${waitTotal === 1 ? "" : "s"}`
        : `Tick spacing ${settings.tickSpacing}`;
      const over3Current = settings.isTriple ? koolkidSingleMartingaleStakeForLeg({ fixedCycle: true }, st.step) : null;
      const over3Next = settings.isTriple ? koolkidSingleMartingaleNextOver3StakeAfterLoss() : null;
      const over4Current = settings.independentPair ? koolkidSingleMartingaleStakeForLeg({ action: "OVER_4" }, st.step) : null;
      const under5Current = settings.independentPair ? koolkidSingleMartingaleStakeForLeg({ action: "UNDER_5" }, st.step) : null;
      const over4Next = settings.independentPair
        ? Number(Math.max(0.35, Math.min(settings.maxStake ?? Number.POSITIVE_INFINITY, settings.startStake * Math.pow(settings.multiplier, Math.max(0, ((st.pairSteps && st.pairSteps.OVER_4) || 1))))).toFixed(2))
        : null;
      const under5Next = settings.independentPair
        ? Number(Math.max(0.35, Math.min(settings.maxStake ?? Number.POSITIVE_INFINITY, settings.startStake * Math.pow(settings.multiplier, Math.max(0, ((st.pairSteps && st.pairSteps.UNDER_5) || 1))))).toFixed(2))
        : null;
      const stakeLabel = settings.isTriple
        ? `Main stakes $${currentStake.toFixed(2)} each / OVER 3 $${over3Current.toFixed(2)} - Next main $${nextStake.toFixed(2)} each / OVER 3 if loss $${over3Next.toFixed(2)}`
        : settings.independentPair
        ? `OVER 4 $${over4Current.toFixed(2)} / UNDER 5 $${under5Current.toFixed(2)} - Next OVER 4 if loss $${over4Next.toFixed(2)} / UNDER 5 if loss $${under5Next.toFixed(2)}`
        : settings.isPair
        ? `Current stakes $${currentStake.toFixed(2)} each - Next stakes $${nextStake.toFixed(2)} each`
        : `Current stake $${currentStake.toFixed(2)} - Next stake $${nextStake.toFixed(2)}`;
      status.textContent = `${st.status}. ${modeLabel}${limitLabel} - ${settings.label} - ${waitText} - Step ${st.step} - ${stakeLabel} - Session P/L $${Number(st.sessionProfit || 0).toFixed(2)} - ${tpText} / ${slText} - Last result: ${st.lastResult}`;
      status.style.color = st.inProgress ? "#fbbf24" : "#94a3b8";
    }
    updateKoolkidMartingaleCalculatorIfOpen();
  }

  function setKoolkidSingleMartingaleAction(action) {
    const st = getKoolkidSingleMartingaleState();
    st.action = normalizeKoolkidMartingaleAction(action).action;
    st.pairSteps = {};
    st.sessionProfit = 0;
    if (isKoolkidTargetProfitMartingaleAction(st.action)) {
      resetKoolkidTargetProfitMartingaleAction(st.action, readKoolkidSingleMartingaleSettings().startStake);
    }
    st.status = "Ready";
    updateKoolkidSingleMartingalePanel();
  }

  function quickStopKoolkidSingleMartingale(reason) {
    if (isOver3Under6PairModeKoolkid()) {
      stopOver3Under6PairMartingaleKoolkid(reason || "Stopped");
      return;
    }
    const st = getKoolkidSingleMartingaleState();
    if (st.restartTimer) {
      clearTimeout(st.restartTimer);
      st.restartTimer = null;
    }
    st.running = false;
    st.stopRequested = true;
    st.enabled = false;
    st.over3Step = 1;
    st.pairSteps = {};
    st.sessionProfit = 0;
    if (isKoolkidTargetProfitMartingaleAction(st.action)) {
      resetKoolkidTargetProfitMartingaleAction(st.action, readKoolkidSingleMartingaleSettings().startStake);
      getKoolkidTargetProfitMartingaleState(st.action).sessionProfit = 0;
    }
    st.waitingForTicks = false;
    st.waitTicksRemaining = 0;
    clearKoolkidSingleMartingalePending();
    st.status = reason || "Stopped";
    updateKoolkidSingleMartingalePanel();
  }

  function toggleKoolkidSingleMartingale() {
    if (isOver3Under6PairModeKoolkid()) {
      const pair = getOver3Under6PairStateKoolkid();
      if (pair.running || pair.inProgress) stopOver3Under6PairMartingaleKoolkid("Stopped");
      else startOver3Under6PairMartingaleKoolkid();
      return;
    }
    if (!canUseKoolkidSingleMartingale()) {
      safeToast(isPaidMonthlyUserKoolkid() ? "This Koolkid martingale is not included for Paid Monthly users." : "This Koolkid martingale is for monthly and lifetime users only.", "error");
      return;
    }
    if (isKoolkidSingleMartingaleMonthlyLimited()) {
      const settings = readKoolkidSingleMartingaleSettings();
      if (!isKoolkidMonthlySingleMartingaleActionAllowed(settings.action)) {
        safeToast("Monthly users can only use UNDER 3, UNDER 4, OVER 5, OVER 6, or OVER 7 here.", "error");
        return;
      }
    }
    const st = getKoolkidSingleMartingaleState();
    st.enabled = !st.enabled;
    if (st.enabled) {
      st.step = 1;
      st.over3Step = 1;
      st.pairSteps = {};
      st.sessionProfit = 0;
      if (isKoolkidTargetProfitMartingaleAction(readKoolkidSingleMartingaleSettings().action)) {
        const settings = readKoolkidSingleMartingaleSettings();
        resetKoolkidTargetProfitMartingaleAction(settings.action, settings.startStake);
        getKoolkidTargetProfitMartingaleState(settings.action).sessionProfit = 0;
      }
      st.status = "Ready";
      st.lastResult = "none";
      st.stopRequested = false;
      st.waitingForTicks = false;
      st.waitTicksRemaining = 0;
    } else {
      quickStopKoolkidSingleMartingale("Martingale stopped.");
      return;
    }
    updateKoolkidSingleMartingalePanel();
  }

  async function checkOver3Under6AvailabilityKoolkid() {
    const symbolEl = document.getElementById("symbol");
    const symbol = symbolEl ? symbolEl.value : undefined;
    const r = await postJSON("/koolkid/over3-under6-availability", { symbol });
    if (!(r && r.data && r.data.status === "success")) {
      throw new Error((r && r.data && r.data.message) || "Over/Under digit contracts are not available on this market.");
    }
    return r.data;
  }

  async function placeOver3Under6PairRoundKoolkid(options) {
    const pair = getOver3Under6PairStateKoolkid();
    const settings = readOver3Under6PairSettingsKoolkid();
    if (pair.inProgress) return;
    pair.inProgress = true;
    pair.pendingContracts = {};
    pair.pendingExpected = 2;
    pair.pendingSettled = 0;
    pair.status = "Running";
    updateKoolkidSingleMartingalePanel();
    const round = Math.max(1, Number(pair.round || 1));
    const overStake = Number(pair.over3_state.current_stake || settings.over3BaseStake);
    const underStake = Number(pair.under6_state.current_stake || settings.under6BaseStake);
    const legs = [
      { key: "over3", action: "OVER_3", type: "OVER", barrier: 3, label: "Over 3", stake: Number(overStake.toFixed(2)) },
      { key: "under6", action: "UNDER_6", type: "UNDER", barrier: 6, label: "Under 6", stake: Number(underStake.toFixed(2)) },
    ];
    try {
      const results = await Promise.all(legs.map((leg) => {
        const payload = {
          stake: leg.stake,
          amount: leg.stake,
          type: leg.type,
          barrier: leg.barrier,
          duration: settings.duration,
          duration_unit: "t",
          mode: "koolkid_over3_under6_pair_martingale",
          action: "OVER3_UNDER6_PAIR",
          leg_action: leg.action,
          label: `Over 3 + Under 6 Pair Martingale ${leg.label}`,
          batch_label: "Over 3 + Under 6 Pair Martingale",
          strategy_name: "Over 3 + Under 6 Pair Martingale",
          round_number: round,
          over3_stake: Number(overStake.toFixed(2)),
          under6_stake: Number(underStake.toFixed(2)),
          hide_from_history: false,
        };
        return sendFastManualTradeKoolkid(payload, { turbo: false, queue: false, fireAndForget: false })
          .then((result) => ({ result, leg }));
      }));
      const failed = results.find((row) => !(row && row.result && row.result.data && row.result.data.status === "success"));
      results.forEach((row) => {
        const data = row && row.result && row.result.data;
        const contractId = data && (data.contract_id || data.buy_contract_id || data.id);
        if (contractId) {
          pair.pendingContracts[String(contractId)] = {
            key: row.leg.key,
            action: row.leg.action,
            label: row.leg.label,
            stake: row.leg.stake,
            outcome: "",
            exit_digit: null,
          };
        }
      });
      if (failed) throw new Error((failed.result && failed.result.data && failed.result.data.message) || "Over 3 + Under 6 pair trade failed");
      pair.status = "Running";
      safeToast(`Over 3 + Under 6 round ${round} sent`, "success");
    } catch (e) {
      pair.inProgress = false;
      pair.running = false;
      pair.enabled = false;
      pair.pendingContracts = {};
      pair.pendingExpected = 0;
      pair.pendingSettled = 0;
      pair.status = "Error";
      pair.availabilityError = (e && e.message) || "Over 3 + Under 6 pair trade failed";
      safeToast(pair.availabilityError, "error");
    } finally {
      updateKoolkidSingleMartingalePanel();
    }
  }

  async function startOver3Under6PairMartingaleKoolkid(options) {
    if (!canUseKoolkidSingleMartingale()) {
      safeToast(isPaidMonthlyUserKoolkid() ? "This Koolkid martingale is not included for Paid Monthly users." : "This Koolkid martingale is for monthly and lifetime users only.", "error");
      return;
    }
    const pair = getOver3Under6PairStateKoolkid();
    if (pair.inProgress) return;
    try {
      await checkOver3Under6AvailabilityKoolkid();
      pair.availabilityError = "";
    } catch (e) {
      pair.running = false;
      pair.enabled = false;
      pair.status = "Error";
      pair.availabilityError = (e && e.message) || "Over/Under digit contracts are not available on this market.";
      updateKoolkidSingleMartingalePanel();
      safeToast(pair.availabilityError, "error");
      return;
    }
    const opts = options || {};
    pair.running = true;
    pair.enabled = true;
    pair.status = "Running";
    if (!opts.continuation) {
      pair.round = Math.max(1, Number(pair.round || 1));
      pair.lastDigit = null;
    }
    updateKoolkidSingleMartingalePanel();
    await placeOver3Under6PairRoundKoolkid(opts);
  }

  function stopOver3Under6PairMartingaleKoolkid(reason) {
    const pair = getOver3Under6PairStateKoolkid();
    pair.running = false;
    pair.enabled = false;
    pair.inProgress = false;
    pair.pendingContracts = {};
    pair.pendingExpected = 0;
    pair.pendingSettled = 0;
    pair.status = reason || "Stopped";
    updateKoolkidSingleMartingalePanel();
  }

  async function placeKoolkidSingleMartingaleTrade(options) {
    if (isOver3Under6PairModeKoolkid()) {
      return startOver3Under6PairMartingaleKoolkid(options || {});
    }
    if (!canUseKoolkidSingleMartingale()) {
      safeToast(isPaidMonthlyUserKoolkid() ? "This Koolkid martingale is not included for Paid Monthly users." : "This Koolkid martingale is for monthly and lifetime users only.", "error");
      return;
    }
    const st = getKoolkidSingleMartingaleState();
    const opts = options || {};
    if (st.inProgress) return;
    const settings = readKoolkidSingleMartingaleSettings();
    if (isKoolkidSingleMartingaleMonthlyLimited() && !isKoolkidMonthlySingleMartingaleActionAllowed(settings.action)) {
      safeToast("Monthly users can only use UNDER 3, UNDER 4, OVER 5, OVER 6, or OVER 7 here.", "error");
      updateKoolkidSingleMartingalePanel();
      return;
    }
    const targetState = settings.targetProfitMode ? getKoolkidTargetProfitMartingaleState(settings.action) : null;
    if (settings.targetProfitMode && (!Number.isFinite(Number(targetState.currentStake)) || Number(targetState.currentStake) < 0.35)) {
      resetKoolkidTargetProfitMartingaleAction(settings.action, settings.startStake);
    }
    const stake = settings.targetProfitMode
      ? Number(Math.max(0.35, Number(targetState.currentStake || settings.startStake)).toFixed(2))
      : (st.enabled ? koolkidSingleMartingaleStakeForStep() : settings.startStake);
    if (st.enabled && !opts.continuation) {
      if (!st.running) st.sessionProfit = 0;
      st.running = true;
      st.stopRequested = false;
    }
    st.waitingForTicks = false;
    st.waitTicksRemaining = 0;
    st.inProgress = true;
    st.pendingAction = settings.action;
    st.pendingContractId = "";
    st.pendingContracts = {};
    st.pendingExpected = settings.isPair ? (settings.legs || []).length : 1;
    st.pendingSettled = 0;
    st.pendingPair = !!settings.isPair;
    st.pendingHasWin = false;
    st.pendingStake = stake;
    st.pendingMartingale = !!st.enabled;
    st.status = "Running";
    updateKoolkidSingleMartingalePanel();
    try {
      if (settings.isPair) {
        const jobs = (settings.legs || []).map((leg) => {
          const legStake = koolkidSingleMartingaleStakeForLeg(leg, st.step);
          const payload = {
            stake: legStake,
            amount: legStake,
            type: leg.type,
            barrier: leg.barrier,
            duration: settings.duration,
            duration_unit: "t",
            mode: "koolkid_single_martingale_pair",
            action: settings.action,
            leg_action: leg.action,
            label: `${settings.label} ${leg.label}`,
          };
          return sendFastManualTradeKoolkid(payload, { turbo: false, queue: false, fireAndForget: false })
            .then((result) => ({ result, leg, legStake }));
        });
        const results = await Promise.all(jobs);
        const failed = results.find((row) => !(row && row.result && row.result.data && row.result.data.status === "success"));
        results.forEach((row) => {
          const data = row && row.result && row.result.data;
          const contractId = data && (data.contract_id || data.buy_contract_id || data.id);
          if (contractId) {
            st.pendingContracts[String(contractId)] = {
              action: row.leg.action,
              label: row.leg.label,
              stake: row.legStake,
              controlsStop: row.leg.controlsStop !== false,
              outcome: "",
            };
          }
        });
        if (failed) {
          throw new Error((failed.result && failed.result.data && failed.result.data.message) || "Koolkid paired martingale trade failed");
        }
        safeToast(`KOOLKID ${settings.label} sent`, "success");
        return;
      }
      const payload = {
        stake,
        amount: stake,
        type: settings.type,
        barrier: settings.barrier,
        duration: settings.duration,
        duration_unit: "t",
        mode: settings.targetProfitMode ? "koolkid_target_profit_martingale" : "koolkid_single_martingale",
        action: settings.action,
        label: settings.label,
      };
      const r = await sendFastManualTradeKoolkid(payload, { turbo: false, queue: false, fireAndForget: false });
      if (!(r && r.data && r.data.status === "success")) {
        throw new Error((r && r.data && r.data.message) || "Koolkid martingale trade failed");
      }
      const contractId = r.data.contract_id || r.data.buy_contract_id || r.data.id;
      if (contractId) st.pendingContractId = String(contractId);
      safeToast(`KOOLKID ${settings.label} sent at $${stake.toFixed(2)}`, "success");
    } catch (e) {
      st.running = false;
      st.stopRequested = true;
      clearKoolkidSingleMartingalePending();
      st.status = "Stopped";
      safeToast((e && e.message) || "Koolkid martingale trade failed", "error");
    } finally {
      updateKoolkidSingleMartingalePanel();
    }
  }

  function rememberKoolkidSingleMartingaleTrade(payload) {
    if (!payload || String(payload.profile || "").toUpperCase() !== PROFILE) return;
    const pairMode = String(payload.mode || "").toLowerCase() === "koolkid_over3_under6_pair_martingale";
    if (pairMode) {
      const pair = getOver3Under6PairStateKoolkid();
      const contractId = payload.contract_id || payload.buy_contract_id || payload.id;
      if (!contractId || pair.pendingContracts[String(contractId)]) return;
      const legAction = String(payload.leg_action || "").toUpperCase();
      const isUnder = legAction === "UNDER_6" || String(payload.type || "").toUpperCase() === "UNDER";
      pair.pendingContracts[String(contractId)] = {
        key: isUnder ? "under6" : "over3",
        action: isUnder ? "UNDER_6" : "OVER_3",
        label: isUnder ? "Under 6" : "Over 3",
        stake: Number(payload.stake || payload.amount || 0),
        outcome: "",
        exit_digit: null,
      };
      pair.pendingExpected = 2;
      pair.status = "Running";
      updateKoolkidSingleMartingalePanel();
      return;
    }
    const st = getKoolkidSingleMartingaleState();
    if (!st.inProgress) return;
    const mode = String(payload.mode || "").toLowerCase();
    const action = normalizeKoolkidMartingaleAction(payload.action || [payload.type, payload.contract_type, payload.label].filter(Boolean).join(" ")).action;
    const contractId = payload.contract_id || payload.buy_contract_id || payload.id;
    if (st.pendingPair) {
      if (!contractId || st.pendingContracts[String(contractId)]) return;
      if (mode !== "koolkid_single_martingale_pair" && action !== st.pendingAction) return;
      const legAction = String(payload.leg_action || "").toUpperCase();
      const settings = readKoolkidSingleMartingaleSettings();
      const leg = (settings.legs || []).find((candidate) => candidate.action === legAction) || null;
      st.pendingContracts[String(contractId)] = {
        action: legAction || action,
        label: leg ? leg.label : (legAction ? legAction.replace("_", " ") : String(payload.label || st.pendingAction)),
        stake: Number(payload.stake || payload.amount || st.pendingStake || 0),
        controlsStop: !leg || leg.controlsStop !== false,
        outcome: "",
      };
      st.status = "Running";
      updateKoolkidSingleMartingalePanel();
      return;
    }
    if (st.pendingContractId) return;
    if (contractId && (mode === "koolkid_single_martingale" || action === st.pendingAction)) {
      st.pendingContractId = String(contractId);
      st.status = "Running";
      updateKoolkidSingleMartingalePanel();
    }
  }

  function resolveKoolkidTradeOutcome(payload) {
    const result = String(payload && (payload.result || payload.status || payload.outcome) || "").toUpperCase();
    if (["WIN", "WON", "PROFIT"].includes(result)) return "WIN";
    if (["LOSS", "LOST"].includes(result)) return "LOSS";
    const profit = Number(payload && (payload.profit ?? payload.pnl ?? payload.net_profit));
    if (Number.isFinite(profit) && profit > 0) return "WIN";
    if (Number.isFinite(profit) && profit < 0) return "LOSS";
    return "";
  }

  function koolkidSingleMartingaleResultStops(item, payload) {
    const action = String(
      (item && item.action)
      || (payload && payload.leg_action)
      || (payload && payload.action)
      || ""
    ).toUpperCase();
    if (action === "OVER_3") return false;
    if (action === "UNDER_3" || action === "OVER_6") return true;
    return !item || item.controlsStop !== false;
  }

  function resolveOver3Under6FinalDigitKoolkid(items) {
    const direct = items
      .map((item) => Number(item.exit_digit))
      .find((digit) => Number.isInteger(digit) && digit >= 0 && digit <= 9);
    if (Number.isInteger(direct)) return direct;
    const over = items.find((item) => item.key === "over3");
    const under = items.find((item) => item.key === "under6");
    if (over && under && over.outcome === "WIN" && under.outcome === "WIN") return 4;
    if (over && over.outcome === "LOSS") return 3;
    if (under && under.outcome === "LOSS") return 6;
    return null;
  }

  function handleOver3Under6PairResultKoolkid() {
    const pair = getOver3Under6PairStateKoolkid();
    const settings = readOver3Under6PairSettingsKoolkid();
    const items = Object.keys(pair.pendingContracts || {}).map((id) => pair.pendingContracts[id]).filter(Boolean);
    if (items.length < 2 || items.some((item) => !item.outcome)) return;
    const over = items.find((item) => item.key === "over3");
    const under = items.find((item) => item.key === "under6");
    if (!over || !under) return;
    const digit = resolveOver3Under6FinalDigitKoolkid(items);
    pair.lastDigit = digit;
    const bothWon = over.outcome === "WIN" && under.outcome === "WIN";
    const bothLost = over.outcome === "LOSS" && under.outcome === "LOSS";
    if (bothWon) {
      updateOver3Under6SideAfterWinKoolkid(pair.over3_state, settings.over3BaseStake);
      updateOver3Under6SideAfterWinKoolkid(pair.under6_state, settings.under6BaseStake);
      pair.running = false;
      pair.enabled = false;
      pair.inProgress = false;
      pair.pendingContracts = {};
      pair.pendingExpected = 0;
      pair.pendingSettled = 0;
      pair.round = 1;
      pair.status = "Both Won";
      safeToast("Both Over 3 and Under 6 won. Strategy stopped.", "success");
      updateKoolkidSingleMartingalePanel();
      return;
    }
    if (bothLost) {
      pair.running = false;
      pair.enabled = false;
      pair.inProgress = false;
      pair.pendingContracts = {};
      pair.status = "Error";
      pair.availabilityError = "Both sides lost or Deriv rejected a pair result. Strategy stopped.";
      safeToast(pair.availabilityError, "error");
      updateKoolkidSingleMartingalePanel();
      return;
    }
    if (over.outcome === "LOSS") {
      updateOver3Under6SideAfterLossKoolkid(pair.over3_state, settings);
      updateOver3Under6SideAfterWinKoolkid(pair.under6_state, settings.under6BaseStake);
      pair.status = "Over 3 increased";
    } else if (under.outcome === "LOSS") {
      updateOver3Under6SideAfterWinKoolkid(pair.over3_state, settings.over3BaseStake);
      updateOver3Under6SideAfterLossKoolkid(pair.under6_state, settings);
      pair.status = "Under 6 increased";
    }
    pair.inProgress = false;
    pair.pendingContracts = {};
    pair.pendingExpected = 0;
    pair.pendingSettled = 0;
    pair.round = Math.max(1, Number(pair.round || 1)) + 1;
    updateKoolkidSingleMartingalePanel();
    if (pair.running && pair.enabled) {
      setTimeout(() => startOver3Under6PairMartingaleKoolkid({ continuation: true }), 140);
    }
  }

  function updateKoolkidSingleMartingaleFromResult(payload) {
    if (!payload || String(payload.profile || "").toUpperCase() !== PROFILE) return;
    if (String(payload.mode || "").toLowerCase() === "koolkid_over3_under6_pair_martingale") {
      const pair = getOver3Under6PairStateKoolkid();
      const contractId = payload.contract_id || payload.buy_contract_id || payload.id;
      const key = String(contractId || "");
      const item = key ? (pair.pendingContracts || {})[key] : null;
      if (!item || item.outcome) return;
      const outcome = resolveKoolkidTradeOutcome(payload);
      if (!outcome) return;
      item.outcome = outcome;
      const exitDigit = Number(payload.exit_digit ?? payload.final_digit ?? payload.last_digit);
      if (Number.isInteger(exitDigit) && exitDigit >= 0 && exitDigit <= 9) item.exit_digit = exitDigit;
      pair.pendingSettled = Object.keys(pair.pendingContracts || {}).filter((id) => pair.pendingContracts[id] && pair.pendingContracts[id].outcome).length;
      pair.status = pair.pendingSettled < 2 ? `Running: waiting for ${2 - pair.pendingSettled} result(s)` : "Settling";
      updateKoolkidSingleMartingalePanel();
      handleOver3Under6PairResultKoolkid();
      return;
    }
    const st = getKoolkidSingleMartingaleState();
    if (!st.inProgress && !st.pendingContractId && !st.pendingPair) return;
    const contractId = payload.contract_id || payload.buy_contract_id || payload.id;
    const mode = String(payload.mode || "").toLowerCase();
    const action = normalizeKoolkidMartingaleAction(payload.action || [payload.type, payload.contract_type, payload.label].filter(Boolean).join(" ")).action;
    if (st.pendingPair) {
      const key = String(contractId || "");
      const item = key ? (st.pendingContracts || {})[key] : null;
      if (!item && mode !== "koolkid_single_martingale_pair" && action !== st.pendingAction) return;
      if (!item || item.outcome) return;
      const outcome = resolveKoolkidTradeOutcome(payload);
      if (!outcome) return;
      item.outcome = outcome;
      st.pendingSettled = Object.keys(st.pendingContracts || {}).filter((id) => st.pendingContracts[id] && st.pendingContracts[id].outcome).length;
      const wasMartingaleTrade = !!st.pendingMartingale;
      const settings = readKoolkidSingleMartingaleSettings();
      if (item.action === "OVER_3") {
        if (outcome === "LOSS") {
          const over3Step = Math.max(1, Math.min(3, Math.floor(Number(st.over3Step || 1) || 1)));
          st.over3Step = over3Step >= 3 ? 1 : over3Step + 1;
        } else if (outcome === "WIN") {
          st.over3Step = 1;
        }
      }
      if (settings.independentPair) {
        if (st.pendingSettled < Math.max(2, Number(st.pendingExpected) || 2)) {
          st.lastResult = outcome;
          st.status = `Running: waiting for ${Math.max(0, (Number(st.pendingExpected) || 2) - st.pendingSettled)} result(s)`;
          updateKoolkidSingleMartingalePanel();
          return;
        }
        const pendingItems = Object.keys(st.pendingContracts || {})
          .map((id) => st.pendingContracts[id])
          .filter(Boolean);
        pendingItems.forEach((pending) => {
          const legAction = String(pending.action || "").toUpperCase();
          if (!legAction) return;
          if (pending.outcome === "LOSS") {
            const currentStep = Math.max(1, Math.min(settings.maxSteps, Math.floor(Number((st.pairSteps || {})[legAction] || 1) || 1)));
            st.pairSteps[legAction] = nextKoolkidLimitedMartingaleStep(currentStep, settings);
          } else if (pending.outcome === "WIN") {
            st.pairSteps[legAction] = 1;
          }
        });
        const hasWinningLeg = pendingItems.some((pending) => pending.outcome === "WIN");
        clearKoolkidSingleMartingalePending();
        st.step = 1;
        st.lastResult = hasWinningLeg ? "WIN" : "LOSS";
        if (hasWinningLeg) {
          st.pairSteps = {};
          st.running = false;
          st.stopRequested = false;
          st.waitingForTicks = false;
          st.waitTicksRemaining = 0;
          st.status = wasMartingaleTrade ? "Reset" : "Ready";
        } else if (wasMartingaleTrade && st.enabled && st.running && !st.stopRequested) {
          if (st.restartTimer) clearTimeout(st.restartTimer);
          st.restartTimer = null;
          st.tickSpacing = settings.tickSpacing;
          st.waitTicksRemaining = settings.tickSpacing;
          st.waitingForTicks = true;
          st.status = `Waiting ${settings.tickSpacing} tick${settings.tickSpacing === 1 ? "" : "s"}`;
        } else {
          st.running = false;
          st.waitingForTicks = false;
          st.waitTicksRemaining = 0;
          st.status = "Ready";
        }
        updateKoolkidSingleMartingalePanel();
        return;
      }
      if (outcome === "WIN" && koolkidSingleMartingaleResultStops(item, payload)) {
        clearKoolkidSingleMartingalePending();
        st.step = 1;
        st.over3Step = 1;
        st.pairSteps = {};
        st.running = false;
        st.stopRequested = false;
        st.waitingForTicks = false;
        st.waitTicksRemaining = 0;
        st.lastResult = "WIN";
        st.status = wasMartingaleTrade ? "Reset" : "Ready";
        updateKoolkidSingleMartingalePanel();
        return;
      }
      if (st.pendingSettled < Math.max(2, Number(st.pendingExpected) || 2)) {
        st.lastResult = outcome === "WIN" ? "OVER 3 WIN" : "LOSS";
        st.status = `Running: waiting for ${Math.max(0, (Number(st.pendingExpected) || 2) - st.pendingSettled)} result(s)`;
        updateKoolkidSingleMartingalePanel();
        return;
      }
      const stoppingLegs = Object.keys(st.pendingContracts || {})
        .map((id) => st.pendingContracts[id])
        .filter((pending) => pending && koolkidSingleMartingaleResultStops(pending, null));
      const stoppingWin = stoppingLegs.some((pending) => pending.outcome === "WIN");
      if (stoppingWin) {
        clearKoolkidSingleMartingalePending();
        st.step = 1;
        st.over3Step = 1;
        st.pairSteps = {};
        st.running = false;
        st.stopRequested = false;
        st.waitingForTicks = false;
        st.waitTicksRemaining = 0;
        st.lastResult = "WIN";
        st.status = wasMartingaleTrade ? "Reset" : "Ready";
        updateKoolkidSingleMartingalePanel();
        return;
      }
      clearKoolkidSingleMartingalePending();
      st.lastResult = "LOSS";
      if (wasMartingaleTrade && st.enabled) {
        const settings = readKoolkidSingleMartingaleSettings();
        st.step = nextKoolkidLimitedMartingaleStep(st.step, settings);
        st.status = "Running";
        if (st.running && !st.stopRequested) {
          if (st.restartTimer) clearTimeout(st.restartTimer);
          st.restartTimer = null;
          st.tickSpacing = settings.tickSpacing;
          st.waitTicksRemaining = settings.tickSpacing;
          st.waitingForTicks = true;
          st.status = `Waiting ${settings.tickSpacing} tick${settings.tickSpacing === 1 ? "" : "s"}`;
        }
      } else {
        st.status = "Ready";
      }
      updateKoolkidSingleMartingalePanel();
      return;
    }
    if (st.pendingContractId && String(contractId || "") !== st.pendingContractId) return;
    if (!st.pendingContractId && mode !== "koolkid_single_martingale" && action !== st.pendingAction) return;
    const outcome = resolveKoolkidTradeOutcome(payload);
    if (!outcome) return;

    const wasMartingaleTrade = !!st.pendingMartingale;
    const pendingStakeBeforeClear = Number(st.pendingStake || 0);
    clearKoolkidSingleMartingalePending();
    const settings = readKoolkidSingleMartingaleSettings();
    if (settings.targetProfitMode || isKoolkidTargetProfitMartingaleAction(action)) {
      const targetAction = isKoolkidTargetProfitMartingaleAction(action) ? action : settings.action;
      const targetSettings = readKoolkidTargetProfitMartingaleSettings();
      const targetState = getKoolkidTargetProfitMartingaleState(targetAction);
      const tradeStake = Number(payload.stake || payload.amount || pendingStakeBeforeClear || targetState.currentStake || settings.startStake);
      const profit = Number(payload.profit ?? payload.pnl ?? payload.net_profit ?? (outcome === "WIN" ? (tradeStake * targetSettings.payoutMultiplier) : -tradeStake));
      targetState.sessionProfit = Number((Number(targetState.sessionProfit || 0) + (Number.isFinite(profit) ? profit : 0)).toFixed(2));
      if (outcome === "WIN") {
        resetKoolkidTargetProfitMartingaleAction(targetAction, settings.startStake);
        const freshState = getKoolkidTargetProfitMartingaleState(targetAction);
        freshState.sessionProfit = targetState.sessionProfit;
        freshState.lastResult = "WIN";
        st.lastResult = "WIN";
      } else {
        targetState.lossBank = Number((Number(targetState.lossBank || 0) + Math.max(0.35, tradeStake)).toFixed(2));
        targetState.step = Math.max(1, Math.floor(Number(targetState.step || 1))) + 1;
        targetState.currentStake = calculateNextKoolkidTargetProfitStake(targetState.lossBank, targetSettings.targetProfit, targetSettings.payoutMultiplier);
        targetState.lastResult = "LOSS";
        st.lastResult = "LOSS";
      }
      const hitTp = targetSettings.takeProfit > 0 && Number(targetState.sessionProfit || 0) >= targetSettings.takeProfit;
      const hitSl = targetSettings.stopLoss > 0 && Number(targetState.sessionProfit || 0) <= -Math.abs(targetSettings.stopLoss);
      if (hitTp || hitSl) {
        stopKoolkidSingleMartingaleOnRiskLimit(st, hitTp, targetState.sessionProfit);
      } else if (outcome === "WIN") {
        const keepCycling = (targetSettings.takeProfit > 0 || targetSettings.stopLoss > 0) && wasMartingaleTrade && st.enabled && st.running && !st.stopRequested;
        if (keepCycling) {
          scheduleKoolkidSingleMartingaleContinuation(st, settings, `Win reset. Waiting ${settings.tickSpacing} tick${settings.tickSpacing === 1 ? "" : "s"}`);
        } else {
          st.running = false;
          st.stopRequested = false;
          st.waitingForTicks = false;
          st.waitTicksRemaining = 0;
          st.status = wasMartingaleTrade ? "Reset" : "Ready";
        }
      } else if (wasMartingaleTrade && st.enabled && st.running && !st.stopRequested) {
        scheduleKoolkidSingleMartingaleContinuation(st, settings);
      } else {
        st.status = "Ready";
      }
      updateKoolkidSingleMartingalePanel();
      return;
    }
    if (outcome === "WIN") {
      const riskSettings = readKoolkidSingleMartingaleRiskSettings();
      const profit = resolveKoolkidMartingaleProfit(payload, outcome, pendingStakeBeforeClear || settings.startStake, settings, null);
      st.sessionProfit = Number((Number(st.sessionProfit || 0) + profit).toFixed(2));
      const hitTp = riskSettings.takeProfit > 0 && Number(st.sessionProfit || 0) >= riskSettings.takeProfit;
      const hitSl = riskSettings.stopLoss > 0 && Number(st.sessionProfit || 0) <= -Math.abs(riskSettings.stopLoss);
      resetKoolkidSingleMartingaleSteps();
      st.lastResult = "WIN";
      if (hitTp || hitSl) {
        stopKoolkidSingleMartingaleOnRiskLimit(st, hitTp, st.sessionProfit);
      } else if (riskSettings.active && wasMartingaleTrade && st.enabled && st.running && !st.stopRequested) {
        scheduleKoolkidSingleMartingaleContinuation(st, settings, `Win reset. Waiting ${settings.tickSpacing} tick${settings.tickSpacing === 1 ? "" : "s"}`);
      } else {
        st.running = false;
        st.stopRequested = false;
        st.waitingForTicks = false;
        st.waitTicksRemaining = 0;
        st.status = wasMartingaleTrade ? "Reset" : "Ready";
      }
    } else if (outcome === "LOSS") {
      const riskSettings = readKoolkidSingleMartingaleRiskSettings();
      const profit = resolveKoolkidMartingaleProfit(payload, outcome, pendingStakeBeforeClear || settings.startStake, settings, null);
      st.sessionProfit = Number((Number(st.sessionProfit || 0) + profit).toFixed(2));
      const hitSl = riskSettings.stopLoss > 0 && Number(st.sessionProfit || 0) <= -Math.abs(riskSettings.stopLoss);
      st.lastResult = "LOSS";
      if (hitSl) {
        stopKoolkidSingleMartingaleOnRiskLimit(st, false, st.sessionProfit);
      } else if (wasMartingaleTrade && st.enabled) {
        const settings = readKoolkidSingleMartingaleSettings();
        st.step = nextKoolkidLimitedMartingaleStep(st.step, settings);
        st.status = "Running";
        if (st.running && !st.stopRequested) {
          scheduleKoolkidSingleMartingaleContinuation(st, settings);
        }
      } else {
        st.status = "Ready";
      }
    }
    updateKoolkidSingleMartingalePanel();
  }

  function onKoolkidSingleMartingaleTick() {
    const st = getKoolkidSingleMartingaleState();
    if (!st.waitingForTicks || !st.running || !st.enabled || st.stopRequested || st.inProgress) return;
    const settings = readKoolkidSingleMartingaleSettings();
    st.waitTicksRemaining = Math.max(0, Math.floor(Number(st.waitTicksRemaining) || settings.tickSpacing) - 1);
    if (st.waitTicksRemaining > 0) {
      st.status = `Waiting ${st.waitTicksRemaining} tick${st.waitTicksRemaining === 1 ? "" : "s"}`;
      updateKoolkidSingleMartingalePanel();
      return;
    }
    st.waitingForTicks = false;
    st.waitTicksRemaining = 0;
    st.status = "Running";
    updateKoolkidSingleMartingalePanel();
    placeKoolkidSingleMartingaleTrade({ continuation: true });
  }

  function getKoolkidBalancedRecoveryState() {
    return state.balancedRecovery || {};
  }

  function getKoolkidPairRecoveryState() {
    return state.koolkidPairRecovery || {};
  }

  function readKoolkidBalancedRecoveryNumber(id, fallback, min, max) {
    const el = document.getElementById(id);
    const raw = el ? Number(el.value) : Number(fallback);
    let value = Number.isFinite(raw) ? raw : Number(fallback);
    if (Number.isFinite(Number(min))) value = Math.max(Number(min), value);
    if (Number.isFinite(Number(max))) value = Math.min(Number(max), value);
    return value;
  }

  function getKoolkidBalancedRecoveryPairConfig() {
    const node = document.getElementById("koolkidBalancedRecoveryPairType");
    const key = String((node && node.value) || "UNDER3_OVER5").toUpperCase();
    if (key === "OVER2_RECOVERY") {
      return {
        key: "OVER2_RECOVERY",
        label: "Over 2",
        single: { action: "OVER_2", type: "OVER", barrier: 2, label: "Over 2", multiplier: 0.43 },
      };
    }
    if (key === "OVER3_RECOVERY") {
      return {
        key: "OVER3_RECOVERY",
        label: "Over 3",
        single: { action: "OVER_3", type: "OVER", barrier: 3, label: "Over 3", multiplier: 0.63 },
      };
    }
    if (key === "UNDER6_RECOVERY") {
      return {
        key: "UNDER6_RECOVERY",
        label: "Under 6",
        single: { action: "UNDER_6", type: "UNDER", barrier: 6, label: "Under 6", multiplier: 0.63 },
      };
    }
    if (key === "UNDER7_RECOVERY") {
      return {
        key: "UNDER7_RECOVERY",
        label: "Under 7",
        single: { action: "UNDER_7", type: "UNDER", barrier: 7, label: "Under 7", multiplier: 0.43 },
      };
    }
    if (key === "OVER5_UNDER4") {
      return {
        key: "OVER5_UNDER4",
        label: "Over 5 + Under 4",
        under: { action: "UNDER_4", type: "UNDER", barrier: 4, label: "Under 4", multiplier: 1.43 },
        over: { action: "OVER_5", type: "OVER", barrier: 5, label: "Over 5", multiplier: 1.43 },
      };
    }
    return {
      key: "UNDER3_OVER5",
      label: "Under 3 + Over 5",
      under: { action: "UNDER_3", type: "UNDER", barrier: 3, label: "Under 3", multiplier: 2.142857142857143 },
      over: { action: "OVER_5", type: "OVER", barrier: 5, label: "Over 5", multiplier: 1.43 },
    };
  }

  function readKoolkidBalancedRecoverySettings() {
    const duration = Math.max(1, Math.min(10, Math.floor(readKoolkidBalancedRecoveryNumber("koolkidBalancedRecoveryDuration", 1, 1, 10))));
    const target = Number(readKoolkidBalancedRecoveryNumber("koolkidBalancedRecoveryTarget", 0.65, 0.01, 1000000).toFixed(2));
    const maxRounds = Math.max(1, Math.floor(readKoolkidBalancedRecoveryNumber("koolkidBalancedRecoveryMaxRounds", 5, 1, 1000000)));
    const budget = Number(readKoolkidBalancedRecoveryNumber("koolkidBalancedRecoveryBudget", 25, 0.01, 1000000).toFixed(2));
    const resetEl = document.getElementById("koolkidBalancedRecoveryResetAfterWin");
    const stopEl = document.getElementById("koolkidBalancedRecoveryStopAtBudget");
    const pair = getKoolkidBalancedRecoveryPairConfig();
    return {
      duration,
      target,
      maxRounds,
      budget,
      resetAfterWin: !resetEl || !!resetEl.checked,
      stopAtBudget: !stopEl || !!stopEl.checked,
      pair,
      isSingle: !!pair.single,
      singleMultiplier: pair.single ? pair.single.multiplier : 0,
      pu: pair.under ? pair.under.multiplier : 0,
      po: pair.over ? pair.over.multiplier : 0,
    };
  }

  function isKoolkidBalancedRecoveryThinkingTrade(settings) {
    const key = String(settings && settings.pair && settings.pair.key || "").toUpperCase();
    return key === "OVER2_RECOVERY" || key === "OVER3_RECOVERY";
  }

  function syncKoolkidBalancedRecoveryThinkingUi() {
    const st = getKoolkidBalancedRecoveryState();
    const node = document.getElementById("koolkidBalancedRecoveryThinkingLogic");
    if (node) node.checked = !!st.thinkingLogic;
  }

  function getKoolkidBalancedRecoveryThinkingSignal() {
    const d = state.over3Analysis || {};
    const settings = readKoolkidBalancedRecoverySettings();
    if (!isKoolkidBalancedRecoveryThinkingTrade(settings)) {
      return { ready: false, reason: "Thinking Logic only applies to Over 2 and Over 3.", key: "" };
    }
    if (!d || !d.symbol_ok) return { ready: false, reason: "Thinking: waiting for market ticks.", key: "" };
    if (d.session_stopped) return { ready: false, reason: "Thinking: Over 3 analysis session is stopped.", key: "" };
    if (d.trade_active) return { ready: false, reason: "Thinking: Over 3 analysis trade is active.", key: "" };
    if (d.wait_fresh_setup) return { ready: false, reason: "Thinking: waiting for fresh setup reset.", key: "" };
    if (d.loss_guard_blocked) return { ready: false, reason: String(d.loss_guard_reason || "Thinking: loss guard blocked this opening."), key: "" };
    const high100 = Number(d.high_count_100 || 0);
    const high10 = Number(d.high_count_10 || 0);
    const streak = Number(d.current_high_streak || 0);
    const key = [String(d.symbol || ""), high100, high10, streak, Number(d.total_trades || 0)].join("|");
    if (d.entry_conditions_ready) {
      return { ready: true, reason: "Thinking: opening found.", key };
    }
    return { ready: false, reason: `Thinking: scanning with Over 3 logic • H100 ${high100}/58 • H10 ${high10}/6 • Streak ${streak}/<6`, key };
  }

  async function ensureKoolkidBalancedRecoveryThinkingAnalysis() {
    const st = getKoolkidBalancedRecoveryState();
    if (st.thinkingAnalysisRequested) return;
    st.thinkingAnalysisRequested = true;
    try {
      await postJSON("/set_over_analysis_barrier_koolkid", { barrier: 3, enable: false, analysis_only: true });
    } catch (e) {}
  }

  function maybeRunKoolkidBalancedRecoveryThinking() {
    const st = getKoolkidBalancedRecoveryState();
    const settings = readKoolkidBalancedRecoverySettings();
    if (!st.thinkingLogic || !isKoolkidBalancedRecoveryThinkingTrade(settings)) return;
    if (!st.enabled || !st.running || st.stopRequested || st.inProgress || st.thinkingOpportunityActive === true) return;
    const signal = getKoolkidBalancedRecoveryThinkingSignal();
    if (!signal.ready) {
      st.thinkingScanning = true;
      st.status = signal.reason || "Thinking: scanning for opening.";
      updateKoolkidBalancedRecoveryPanel();
      return;
    }
    if (signal.key && signal.key === st.thinkingLastSignalKey) return;
    st.thinkingLastSignalKey = signal.key || String(Date.now());
    st.thinkingScanning = false;
    st.thinkingOpportunityActive = true;
    st.status = `Opening found: placing ${settings.pair.label}`;
    updateKoolkidBalancedRecoveryPanel();
    setTimeout(() => startKoolkidBalancedRecovery({ forceTrade: true }), 0);
  }

  function readKoolkidPairRecoverySettings() {
    const duration = Math.max(1, Math.min(10, Math.floor(readKoolkidBalancedRecoveryNumber("koolkidPairRecoveryDuration", 1, 1, 10))));
    const target = Number(readKoolkidBalancedRecoveryNumber("koolkidPairRecoveryTarget", 0.65, 0.01, 1000000).toFixed(2));
    const maxRounds = Math.max(1, Math.floor(readKoolkidBalancedRecoveryNumber("koolkidPairRecoveryMaxRounds", 5, 1, 1000000)));
    const budget = Number(readKoolkidBalancedRecoveryNumber("koolkidPairRecoveryBudget", 25, 0.01, 1000000).toFixed(2));
    const resetEl = document.getElementById("koolkidPairRecoveryResetAfterWin");
    const stopEl = document.getElementById("koolkidPairRecoveryStopAtBudget");
    return {
      duration,
      target,
      maxRounds,
      budget,
      resetAfterWin: !resetEl || !!resetEl.checked,
      stopAtBudget: !stopEl || !!stopEl.checked,
    };
  }

  function ceilKoolkidStakeCents(value) {
    const n = Number(value);
    if (!Number.isFinite(n) || n <= 0) return 0.35;
    return Number((Math.ceil((n - 1e-9) * 100) / 100).toFixed(2));
  }

  function calculateKoolkidBalancedRecoveryStakes(lossAccumulated, targetProfit) {
    const settings = readKoolkidBalancedRecoverySettings();
    const need = Math.max(0, Number(lossAccumulated) || 0) + Math.max(0.01, Number(targetProfit) || settings.target);
    if (settings.isSingle) {
      const multiplier = Math.max(0.01, Number(settings.singleMultiplier || 0.63));
      return { singleStake: ceilKoolkidStakeCents(need / multiplier), underStake: 0, overStake: 0 };
    }
    const denominator = (settings.pu * settings.po) - 1;
    let underStake = (need * (settings.po + 1)) / denominator;
    let overStake = (need + underStake) / settings.po;
    underStake = ceilKoolkidStakeCents(underStake);
    overStake = ceilKoolkidStakeCents(overStake);
    for (let i = 0; i < 100; i += 1) {
      const underScenario = (settings.pu * underStake) - overStake - (Number(lossAccumulated) || 0);
      const overScenario = (settings.po * overStake) - underStake - (Number(lossAccumulated) || 0);
      if (underScenario + 1e-9 >= settings.target && overScenario + 1e-9 >= settings.target) break;
      if (underScenario < settings.target) underStake = Number((underStake + 0.01).toFixed(2));
      if (overScenario < settings.target) overStake = Number((overStake + 0.01).toFixed(2));
    }
    return { underStake, overStake };
  }

  function koolkidBalancedRecoveryCanAfford(stakes, settings) {
    const st = getKoolkidBalancedRecoveryState();
    const total = settings.isSingle ? Number(stakes.singleStake || 0) : (Number(stakes.underStake || 0) + Number(stakes.overStake || 0));
    const cycleSpend = Number(st.lossAccumulated || 0) + total;
    return !settings.stopAtBudget || cycleSpend <= Number(settings.budget || 0) + 1e-9;
  }

  function koolkidPairRecoveryCanAfford(stakes, settings) {
    const st = getKoolkidPairRecoveryState();
    const total = Number(stakes.underStake || 0) + Number(stakes.overStake || 0);
    const cycleSpend = Number(st.lossAccumulated || 0) + total;
    return !settings.stopAtBudget || cycleSpend <= Number(settings.budget || 0) + 1e-9;
  }

  function normalizeKoolkidPairQuoteStakes(data) {
    const stakes = data && data.stakes ? data.stakes : {};
    return {
      underStake: Number(stakes.under_stake || stakes.underStake || 0),
      overStake: Number(stakes.over_stake || stakes.overStake || 0),
      underWinNet: Number(stakes.under_win_net || stakes.underWinNet || 0),
      overWinNet: Number(stakes.over_win_net || stakes.overWinNet || 0),
      underMultiplier: Number(data && data.under_multiplier),
      overMultiplier: Number(data && data.over_multiplier),
    };
  }

  async function fetchKoolkidPairRecoveryQuote(settings, st) {
    const symbol = typeof window.getConfirmedMarketSymbol === "function"
      ? window.getConfirmedMarketSymbol()
      : ((document.getElementById("symbol") || {}).value || "");
    const result = await postJSON("/koolkid_pair_recovery_quote", {
      symbol,
      duration: settings.duration,
      duration_unit: "t",
      target_profit: settings.target,
      loss_accumulated: 0,
      under_barrier: 2,
      over_barrier: 3,
      quote_stake: 1,
    });
    if (!(result && result.ok && result.data && result.data.status === "success")) {
      throw new Error((result && result.data && result.data.message) || "Payout quote unavailable");
    }
    return normalizeKoolkidPairQuoteStakes(result.data);
  }

  function updateKoolkidBalancedRecoveryPanel() {
    const panel = document.getElementById("koolkidBalancedRecoveryPanel");
    if (panel) panel.style.display = "";
    const st = getKoolkidBalancedRecoveryState();
    const settings = readKoolkidBalancedRecoverySettings();
    syncKoolkidBalancedRecoveryThinkingUi();
    const stakes = calculateKoolkidBalancedRecoveryStakes(st.lossAccumulated || 0, settings.target);
    st.underStake = stakes.underStake;
    st.overStake = stakes.overStake;
    const startBtn = document.getElementById("koolkidBalancedRecoveryStartBtn");
    if (startBtn) startBtn.disabled = !!st.inProgress;
    const statusEl = document.getElementById("koolkidBalancedRecoveryStatus");
    if (statusEl) {
      const total = settings.isSingle ? Number(stakes.singleStake || 0) : (stakes.underStake + stakes.overStake);
      const budgetText = settings.stopAtBudget ? `Budget check $${(Number(st.lossAccumulated || 0) + total).toFixed(2)} / $${settings.budget.toFixed(2)}` : "Budget cap ignored";
      const stakeLine = settings.isSingle
        ? `${settings.pair.single.label} stake $${Number(stakes.singleStake || 0).toFixed(2)}`
        : `${settings.pair.under.label} stake $${stakes.underStake.toFixed(2)} | ${settings.pair.over.label} stake $${stakes.overStake.toFixed(2)}`;
      statusEl.innerHTML = [
        `Status: ${st.status || "Ready"} | ${settings.pair.label} | Round ${Math.max(1, Number(st.round) || 1)} / ${settings.maxRounds}`,
        stakeLine,
        `Cycle loss $${Number(st.lossAccumulated || 0).toFixed(2)} | Target profit $${settings.target.toFixed(2)} | Session P/L $${Number(st.sessionProfit || 0).toFixed(2)} | Next total $${total.toFixed(2)}`,
        `${budgetText} | Thinking ${st.thinkingLogic && isKoolkidBalancedRecoveryThinkingTrade(settings) ? "ON" : "OFF"} | Last result: ${st.lastResult || "none"}`,
      ].join("<br>");
    }
  }

  function readKoolkidBalancedRecoveryLimits() {
    const tpNode = document.getElementById("tp");
    const slNode = document.getElementById("sl");
    const tp = Math.max(0, Number(tpNode && tpNode.value) || 0);
    const sl = Math.max(0, Number(slNode && slNode.value) || 0);
    return { tp, sl };
  }

  function koolkidBalancedRecoveryHitSessionLimit() {
    const st = getKoolkidBalancedRecoveryState();
    const limits = readKoolkidBalancedRecoveryLimits();
    const pnl = Number(st.sessionProfit || 0);
    if (limits.tp > 0 && pnl >= limits.tp) {
      stopKoolkidBalancedRecovery("Stopped: TP reached.");
      safeToast("Balanced Recovery TP reached.", "success");
      return true;
    }
    if (limits.sl > 0 && pnl <= -Math.abs(limits.sl)) {
      stopKoolkidBalancedRecovery("Stopped: SL reached.");
      safeToast("Balanced Recovery SL reached.", "error");
      return true;
    }
    return false;
  }

  function toggleKoolkidBalancedRecovery() {
    const st = getKoolkidBalancedRecoveryState();
    st.enabled = !st.enabled;
    st.status = st.enabled ? "Ready" : "Stopped";
    if (!st.enabled) {
      st.running = false;
      st.stopRequested = true;
    } else if (!st.inProgress) {
      st.running = true;
      st.stopRequested = false;
      startKoolkidBalancedRecovery();
    }
    updateKoolkidBalancedRecoveryPanel();
  }

  function resetKoolkidBalancedRecoveryCycle() {
    const st = getKoolkidBalancedRecoveryState();
    st.round = 1;
    st.lossAccumulated = 0;
    st.inProgress = false;
    st.batchId = "";
    st.pending = {};
    st.settled = 0;
    st.hasWin = false;
    st.totalProfit = 0;
    st.sessionProfit = 0;
    st.lastResult = "none";
    st.status = st.enabled ? "Ready" : "Ready";
    st.thinkingScanning = false;
    st.thinkingOpportunityActive = false;
    st.thinkingLastSignalKey = "";
    updateKoolkidBalancedRecoveryPanel();
  }

  function stopKoolkidBalancedRecovery(reason) {
    const st = getKoolkidBalancedRecoveryState();
    st.enabled = false;
    st.running = false;
    st.stopRequested = true;
    st.inProgress = false;
    st.round = 1;
    st.lossAccumulated = 0;
    st.batchId = "";
    st.pending = {};
    st.settled = 0;
    st.hasWin = false;
    st.totalProfit = 0;
    st.sessionProfit = 0;
    st.lastResult = "none";
    st.status = reason || "Stopped";
    st.thinkingScanning = false;
    st.thinkingOpportunityActive = false;
    st.thinkingLastSignalKey = "";
    updateKoolkidBalancedRecoveryPanel();
  }

  async function startKoolkidBalancedRecovery(options) {
    const st = getKoolkidBalancedRecoveryState();
    const settings = readKoolkidBalancedRecoverySettings();
    const opts = options || {};
    if (st.inProgress) return;
    const freshStart = !st.enabled && !st.running;
    if (typeof apiConnected !== "undefined" && !apiConnected) {
      st.status = "Stopped: API disconnected";
      updateKoolkidBalancedRecoveryPanel();
      safeToast("Connect your API first.", "error");
      return;
    }
    if (Math.max(1, Number(st.round) || 1) > settings.maxRounds) {
      stopKoolkidBalancedRecovery("Stopped: max rounds reached.");
      safeToast("Balanced Recovery stopped: max rounds reached.", "error");
      return;
    }
    const stakes = calculateKoolkidBalancedRecoveryStakes(st.lossAccumulated || 0, settings.target);
    if (!koolkidBalancedRecoveryCanAfford(stakes, settings)) {
      stopKoolkidBalancedRecovery("Insufficient Budget");
      safeToast("Balanced Recovery stopped: next round exceeds budget.", "error");
      return;
    }
    st.enabled = true;
    st.running = true;
    st.stopRequested = false;
    if (freshStart) st.sessionProfit = 0;
    if (st.thinkingLogic && isKoolkidBalancedRecoveryThinkingTrade(settings) && !opts.forceTrade && !st.thinkingOpportunityActive) {
      st.thinkingScanning = true;
      st.status = "Thinking: scanning for Over 3-style opening.";
      ensureKoolkidBalancedRecoveryThinkingAnalysis();
      updateKoolkidBalancedRecoveryPanel();
      maybeRunKoolkidBalancedRecoveryThinking();
      return;
    }
    st.inProgress = true;
    st.batchId = `kbr_${Date.now()}_${Math.floor(Math.random() * 10000)}`;
    st.pending = {};
    st.settled = 0;
    st.hasWin = false;
    st.totalProfit = 0;
    st.underStake = stakes.underStake || 0;
    st.overStake = stakes.overStake || 0;
    st.singleStake = stakes.singleStake || 0;
    st.status = "Running";
    updateKoolkidBalancedRecoveryPanel();
    try {
      const common = { duration: settings.duration, duration_unit: "t", mode: "koolkid_balanced_recovery", batch_id: st.batchId };
      if (settings.isSingle) {
        const singlePayload = Object.assign({}, common, {
          stake: stakes.singleStake,
          amount: stakes.singleStake,
          type: settings.pair.single.type,
          barrier: settings.pair.single.barrier,
          action: settings.pair.single.action,
          label: `Balanced Recovery ${settings.pair.single.label} Round ${st.round}`,
          pair_type: settings.pair.key,
        });
        const r = await sendFastManualTradeKoolkid(singlePayload, { turbo: false, queue: false, fireAndForget: false });
        if (!(r && r.data && r.data.status === "success")) {
          throw new Error((r && r.data && r.data.message) || "Balanced Recovery trade failed");
        }
        const id = r.data.contract_id || r.data.buy_contract_id || r.data.id;
        if (id) st.pending[String(id)] = { side: settings.pair.single.action, label: settings.pair.single.label, stake: stakes.singleStake, outcome: "" };
        safeToast(`Balanced Recovery ${settings.pair.single.label} sent at $${Number(stakes.singleStake || 0).toFixed(2)}`, "success");
        return;
      }
      const underPayload = Object.assign({}, common, {
        stake: stakes.underStake,
        amount: stakes.underStake,
        type: settings.pair.under.type,
        barrier: settings.pair.under.barrier,
        action: settings.pair.under.action,
        label: `Balanced Recovery ${settings.pair.under.label} Round ${st.round}`,
        pair_type: settings.pair.key,
      });
      const overPayload = Object.assign({}, common, {
        stake: stakes.overStake,
        amount: stakes.overStake,
        type: settings.pair.over.type,
        barrier: settings.pair.over.barrier,
        action: settings.pair.over.action,
        label: `Balanced Recovery ${settings.pair.over.label} Round ${st.round}`,
        pair_type: settings.pair.key,
      });
      const app = App();
      if (!(app && typeof app.sendFastProfileTradeBatch === "function")) {
        throw new Error("Same-tick batch sender is not ready");
      }
      const batchResult = await app.sendFastProfileTradeBatch(PROFILE, [
        Object.assign({}, underPayload, { same_tick: true }),
        Object.assign({}, overPayload, { same_tick: true }),
      ], { turbo: false, useSocket: true, fireAndForget: false, skipMartha: true });
      const responses = Array.isArray(batchResult && batchResult.data && batchResult.data.responses) ? batchResult.data.responses : [];
      if (!(batchResult && batchResult.data && batchResult.data.status === "success")) {
        throw new Error((batchResult && batchResult.data && batchResult.data.message) || "Balanced Recovery same-tick pair failed");
      }
      const underResp = responses[0] || {};
      const overResp = responses[1] || {};
      const underId = underResp.contract_id || underResp.buy_contract_id || underResp.id;
      if (underId) st.pending[String(underId)] = { side: settings.pair.under.action, label: settings.pair.under.label, stake: stakes.underStake, outcome: "" };
      const overId = overResp.contract_id || overResp.buy_contract_id || overResp.id;
      if (overId) st.pending[String(overId)] = { side: settings.pair.over.action, label: settings.pair.over.label, stake: stakes.overStake, outcome: "" };
      safeToast(`Balanced Recovery pair sent: ${settings.pair.under.label} $${stakes.underStake.toFixed(2)} + ${settings.pair.over.label} $${stakes.overStake.toFixed(2)}`, "success");
    } catch (e) {
      st.running = false;
      st.stopRequested = true;
      st.status = "Stopped";
      st.inProgress = Object.keys(st.pending || {}).length > 0;
      safeToast((e && e.message) || "Balanced Recovery pair failed", "error");
    } finally {
      updateKoolkidBalancedRecoveryPanel();
    }
  }

  function rememberKoolkidBalancedRecoveryTrade(payload) {
    if (!payload || String(payload.profile || "").toUpperCase() !== PROFILE) return;
    const st = getKoolkidBalancedRecoveryState();
    if (!st.inProgress || !st.batchId) return;
    const mode = String(payload.mode || "").toLowerCase();
    const batchId = String(payload.batch_id || payload.batchId || "");
    if (mode !== "koolkid_balanced_recovery" && batchId !== st.batchId) return;
    const id = payload.contract_id || payload.buy_contract_id || payload.id;
    if (!id || st.pending[String(id)]) return;
    const action = String(payload.action || payload.label || "").toUpperCase();
    const settings = readKoolkidBalancedRecoverySettings();
    if (settings.isSingle) {
      st.pending[String(id)] = { side: settings.pair.single.action, label: settings.pair.single.label, stake: Number(payload.stake || payload.amount || st.singleStake || 0), outcome: "" };
      updateKoolkidBalancedRecoveryPanel();
      return;
    }
    const isOver = action.includes("OVER");
    const side = isOver ? settings.pair.over.action : settings.pair.under.action;
    const label = isOver ? settings.pair.over.label : settings.pair.under.label;
    st.pending[String(id)] = { side, label, stake: Number(payload.stake || payload.amount || 0), outcome: "" };
    updateKoolkidBalancedRecoveryPanel();
  }

  function updateKoolkidBalancedRecoveryFromResult(payload) {
    if (!payload || String(payload.profile || "").toUpperCase() !== PROFILE) return;
    const st = getKoolkidBalancedRecoveryState();
    if (!st.inProgress || !st.batchId) return;
    const id = String(payload.contract_id || payload.buy_contract_id || payload.id || "");
    const mode = String(payload.mode || "").toLowerCase();
    const batchId = String(payload.batch_id || payload.batchId || "");
    if (id && !st.pending[id] && mode !== "koolkid_balanced_recovery" && batchId !== st.batchId) return;
    const item = id && st.pending[id] ? st.pending[id] : null;
    if (!item || item.outcome) return;
    const outcome = resolveKoolkidTradeOutcome(payload);
    if (!outcome) return;
    item.outcome = outcome;
    st.settled = Object.keys(st.pending || {}).filter((key) => st.pending[key] && st.pending[key].outcome).length;
    const profit = Number(payload.profit ?? payload.pnl ?? payload.net_profit);
    if (Number.isFinite(profit)) {
      st.totalProfit = Number((Number(st.totalProfit || 0) + profit).toFixed(2));
      st.sessionProfit = Number((Number(st.sessionProfit || 0) + profit).toFixed(2));
    }
    const settingsNow = readKoolkidBalancedRecoverySettings();
    if (outcome === "WIN") {
      st.hasWin = true;
      st.lastResult = `${item.label || item.side || "Side"} won`;
      st.status = "Won";
      st.inProgress = false;
      st.pending = {};
      const limits = readKoolkidBalancedRecoveryLimits();
      const shouldKeepCycling = limits.tp > 0 || limits.sl > 0;
      if (settingsNow.resetAfterWin || shouldKeepCycling) {
        st.round = 1;
        st.lossAccumulated = 0;
      }
      updateKoolkidBalancedRecoveryPanel();
      safeToast(`Balanced Recovery ${st.lastResult}. Cycle reset.`, "success");
      if (koolkidBalancedRecoveryHitSessionLimit()) return;
      if (st.thinkingLogic && isKoolkidBalancedRecoveryThinkingTrade(settingsNow)) {
        st.thinkingOpportunityActive = false;
        st.thinkingScanning = true;
        st.status = "Won: reset, scanning again.";
        updateKoolkidBalancedRecoveryPanel();
        setTimeout(() => maybeRunKoolkidBalancedRecoveryThinking(), 120);
      } else if (shouldKeepCycling && st.enabled && st.running && !st.stopRequested) {
        setTimeout(() => startKoolkidBalancedRecovery(), 0);
      } else {
        st.running = false;
        st.enabled = false;
        st.stopRequested = false;
        st.status = "Won";
        updateKoolkidBalancedRecoveryPanel();
      }
      return;
    }
    const pendingCount = Object.keys(st.pending || {}).length;
    if (((settingsNow.isSingle && st.settled >= 1) || (pendingCount >= 2 && st.settled >= 2)) && !st.hasWin) {
      const roundLoss = settingsNow.isSingle ? Number(st.singleStake || item.stake || 0) : (Number(st.underStake || 0) + Number(st.overStake || 0));
      st.lossAccumulated = Number((Number(st.lossAccumulated || 0) + roundLoss).toFixed(2));
      st.round = Math.max(1, Number(st.round) || 1) + 1;
      st.lastResult = settingsNow.isSingle ? `${item.label || item.side || "Trade"} lost` : "Both lost";
      st.inProgress = false;
      st.pending = {};
      if (koolkidBalancedRecoveryHitSessionLimit()) return;
      const settings = settingsNow;
      if (st.round > settings.maxRounds) {
        stopKoolkidBalancedRecovery("Stopped: max rounds reached.");
        safeToast("Balanced Recovery stopped: max rounds reached.", "error");
        return;
      }
      const nextStakes = calculateKoolkidBalancedRecoveryStakes(st.lossAccumulated, settings.target);
      if (!koolkidBalancedRecoveryCanAfford(nextStakes, settings)) {
        stopKoolkidBalancedRecovery("Insufficient Budget");
        safeToast("Balanced Recovery stopped: next round exceeds budget.", "error");
        return;
      }
      st.status = settings.isSingle ? "Running: firing next trade" : "Running: firing next pair";
      updateKoolkidBalancedRecoveryPanel();
      if (st.enabled && st.running && !st.stopRequested) {
        setTimeout(() => startKoolkidBalancedRecovery(st.thinkingLogic && isKoolkidBalancedRecoveryThinkingTrade(settings) ? { forceTrade: true } : undefined), 0);
      }
    } else {
      const expected = settingsNow.isSingle ? 1 : 2;
      st.status = `Running: waiting for ${Math.max(0, expected - st.settled)} result(s)`;
      updateKoolkidBalancedRecoveryPanel();
    }
  }

  function updateKoolkidPairRecoveryPanel() {
    const dropdown = document.getElementById("koolkidPairRecoveryDropdown");
    if (dropdown) dropdown.style.display = "";
    const st = getKoolkidPairRecoveryState();
    const settings = readKoolkidPairRecoverySettings();
    const startBtn = document.getElementById("koolkidPairRecoveryStartBtn");
    if (startBtn) startBtn.disabled = !!st.inProgress;
    const statusEl = document.getElementById("koolkidPairRecoveryStatus");
    if (statusEl) {
      const total = Number(st.underStake || 0) + Number(st.overStake || 0);
      const budgetText = settings.stopAtBudget ? `Budget check $${(Number(st.lossAccumulated || 0) + total).toFixed(2)} / $${settings.budget.toFixed(2)}` : "Budget cap ignored";
      const payoutText = st.underMultiplier && st.overMultiplier
        ? `Payout multipliers U2 ${Number(st.underMultiplier).toFixed(3)} / O3 ${Number(st.overMultiplier).toFixed(3)}`
        : "Payout multipliers update before START";
      statusEl.innerHTML = [
        `Status: ${st.status || "Ready"} | Round ${Math.max(1, Number(st.round) || 1)} / ${settings.maxRounds}`,
        `Under 2 stake $${Number(st.underStake || 0).toFixed(2)} | Over 3 stake $${Number(st.overStake || 0).toFixed(2)}`,
        `Cycle loss $${Number(st.lossAccumulated || 0).toFixed(2)} | Target profit $${settings.target.toFixed(2)} | Next total $${total.toFixed(2)}`,
        `${budgetText} | ${payoutText} | Last result: ${st.lastResult || "none"}`,
      ].join("<br>");
    }
    const btn = document.getElementById("koolkidPairRecoveryBtnKoolkid");
    if (btn) btn.innerText = st.inProgress ? "💲KOOLKID RUNNING..." : "💲KOOLKID💲";
  }

  function openKoolkidPairRecoveryPopup() {
    const dropdown = document.getElementById("koolkidPairRecoveryDropdown");
    if (!dropdown) return;
    dropdown.style.display = "";
    dropdown.open = !dropdown.open;
    updateKoolkidPairRecoveryPanel();
  }

  function closeKoolkidPairRecoveryPopup() {
    const dropdown = document.getElementById("koolkidPairRecoveryDropdown");
    if (dropdown) dropdown.open = false;
  }

  function stopKoolkidPairRecovery(reason) {
    const st = getKoolkidPairRecoveryState();
    st.enabled = false;
    st.running = false;
    st.stopRequested = true;
    st.inProgress = false;
    st.pending = {};
    st.status = reason || "Stopped";
    updateKoolkidPairRecoveryPanel();
  }

  function readKoolkidPairManualStake(id) {
    const node = document.getElementById(id);
    const value = Number(node && node.value);
    if (!Number.isFinite(value) || value < 0.35) return 0.35;
    return Number(value.toFixed(2));
  }

  window.placeKoolkidPairManualStakeTrade = async function () {
    if (typeof apiConnected !== "undefined" && !apiConnected) {
      safeToast("Connect your API first.", "error");
      return;
    }
    const settings = readKoolkidPairRecoverySettings();
    const underStake = readKoolkidPairManualStake("koolkidPairManualUnder2Stake");
    const overStake = readKoolkidPairManualStake("koolkidPairManualOver3Stake");
    const status = document.getElementById("koolkidPairManualStatus");
    const btn = document.getElementById("koolkidPairManualPlaceBtn");
    const symbol = typeof window.getConfirmedMarketSymbol === "function"
      ? window.getConfirmedMarketSymbol()
      : ((document.getElementById("symbol") || {}).value || "");
    const batchId = `kpr_manual_${Date.now()}_${Math.floor(Math.random() * 10000)}`;
    const common = {
      duration: settings.duration,
      duration_unit: "t",
      mode: "koolkid_pair_manual",
      batch_id: batchId,
      batch_size: 2,
      symbol,
    };
    const underPayload = Object.assign({}, common, {
      stake: underStake,
      amount: underStake,
      type: "UNDER",
      barrier: 2,
      action: "UNDER_2",
      label: "KOOLKID Manual UNDER 2",
    });
    const overPayload = Object.assign({}, common, {
      stake: overStake,
      amount: overStake,
      type: "OVER",
      barrier: 3,
      action: "OVER_3",
      label: "KOOLKID Manual OVER 3",
    });
    try {
      if (btn) btn.disabled = true;
      if (status) status.innerText = "Sending Under 2 + Over 3 on the same tick...";
      const app = App();
      if (!(app && typeof app.sendFastProfileTradeBatch === "function")) throw new Error("Same-tick batch sender is not ready");
      const result = await app.sendFastProfileTradeBatch(PROFILE, [
        Object.assign({}, underPayload, { same_tick: true }),
        Object.assign({}, overPayload, { same_tick: true }),
      ], { turbo: false, useSocket: true, fireAndForget: false, skipMartha: true });
      if (!(result && result.data && result.data.status === "success")) {
        throw new Error((result && result.data && result.data.message) || "Manual KOOLKID pair failed");
      }
      if (status) status.innerText = `Sent Under 2 $${underStake.toFixed(2)} + Over 3 $${overStake.toFixed(2)} for ${settings.duration} tick${settings.duration === 1 ? "" : "s"}.`;
      safeToast(`KOOLKID manual pair sent: U2 $${underStake.toFixed(2)} + O3 $${overStake.toFixed(2)}`, "success");
    } catch (e) {
      const msg = (e && e.message) || "Manual KOOLKID pair failed";
      if (status) status.innerText = msg;
      safeToast(msg, "error");
    } finally {
      if (btn) btn.disabled = false;
    }
  };

  async function startKoolkidPairRecovery() {
    const st = getKoolkidPairRecoveryState();
    const settings = readKoolkidPairRecoverySettings();
    if (st.inProgress) return;
    if (typeof apiConnected !== "undefined" && !apiConnected) {
      st.status = "Stopped: API disconnected";
      updateKoolkidPairRecoveryPanel();
      safeToast("Connect your API first.", "error");
      return;
    }
    if (Math.max(1, Number(st.round) || 1) > settings.maxRounds) {
      stopKoolkidPairRecovery("Stopped: max rounds reached.");
      safeToast("KOOLKID recovery stopped: max rounds reached.", "error");
      return;
    }
    let quote;
    try {
      st.status = "Checking payouts";
      updateKoolkidPairRecoveryPanel();
      quote = await fetchKoolkidPairRecoveryQuote(settings, st);
    } catch (e) {
      st.status = "Quote Error";
      updateKoolkidPairRecoveryPanel();
      safeToast((e && e.message) || "KOOLKID recovery payout quote failed", "error");
      return;
    }
    const stakes = { underStake: quote.underStake, overStake: quote.overStake };
    if (!koolkidPairRecoveryCanAfford(stakes, settings)) {
      stopKoolkidPairRecovery("Insufficient Budget");
      safeToast("KOOLKID recovery stopped: next round exceeds budget.", "error");
      return;
    }
    const symbol = typeof window.getConfirmedMarketSymbol === "function"
      ? window.getConfirmedMarketSymbol()
      : ((document.getElementById("symbol") || {}).value || "");
    st.enabled = true;
    st.running = true;
    st.stopRequested = false;
    st.inProgress = true;
    st.batchId = `kpr_${Date.now()}_${Math.floor(Math.random() * 10000)}`;
    st.pending = {};
    st.settled = 0;
    st.hasWin = false;
    st.totalProfit = 0;
    st.underStake = stakes.underStake;
    st.overStake = stakes.overStake;
    st.underMultiplier = quote.underMultiplier;
    st.overMultiplier = quote.overMultiplier;
    st.status = "Running";
    updateKoolkidPairRecoveryPanel();
    try {
      const common = { duration: settings.duration, duration_unit: "t", mode: "koolkid_pair_recovery", batch_id: st.batchId, batch_size: 2, symbol };
      const underPayload = Object.assign({}, common, {
        stake: stakes.underStake,
        amount: stakes.underStake,
        type: "UNDER",
        barrier: 2,
        action: "UNDER_2",
        label: `KOOLKID Recovery UNDER 2 Round ${st.round}`,
      });
      const overPayload = Object.assign({}, common, {
        stake: stakes.overStake,
        amount: stakes.overStake,
        type: "OVER",
        barrier: 3,
        action: "OVER_3",
        label: `KOOLKID Recovery OVER 3 Round ${st.round}`,
      });
      const app = App();
      if (!(app && typeof app.sendFastProfileTradeBatch === "function")) throw new Error("Same-tick batch sender is not ready");
      const batchResult = await app.sendFastProfileTradeBatch(PROFILE, [
        Object.assign({}, underPayload, { same_tick: true }),
        Object.assign({}, overPayload, { same_tick: true }),
      ], { turbo: false, useSocket: true, fireAndForget: false, skipMartha: true });
      const responses = Array.isArray(batchResult && batchResult.data && batchResult.data.responses) ? batchResult.data.responses : [];
      if (!(batchResult && batchResult.data && batchResult.data.status === "success")) {
        throw new Error((batchResult && batchResult.data && batchResult.data.message) || "KOOLKID same-tick pair failed");
      }
      const underResp = responses[0] || {};
      const overResp = responses[1] || {};
      const underId = underResp.contract_id || underResp.buy_contract_id || underResp.id;
      if (underId) st.pending[String(underId)] = { side: "UNDER_2", stake: stakes.underStake, outcome: "" };
      const overId = overResp.contract_id || overResp.buy_contract_id || overResp.id;
      if (overId) st.pending[String(overId)] = { side: "OVER_3", stake: stakes.overStake, outcome: "" };
      safeToast(`KOOLKID pair sent: U2 $${stakes.underStake.toFixed(2)} + O3 $${stakes.overStake.toFixed(2)}`, "success");
    } catch (e) {
      st.running = false;
      st.stopRequested = true;
      st.status = "Stopped";
      st.inProgress = Object.keys(st.pending || {}).length > 0;
      safeToast((e && e.message) || "KOOLKID pair failed", "error");
    } finally {
      updateKoolkidPairRecoveryPanel();
    }
  }

  function rememberKoolkidPairRecoveryTrade(payload) {
    if (!payload || String(payload.profile || "").toUpperCase() !== PROFILE) return;
    const st = getKoolkidPairRecoveryState();
    if (!st.inProgress || !st.batchId) return;
    const mode = String(payload.mode || "").toLowerCase();
    const batchId = String(payload.batch_id || payload.batchId || "");
    if (mode !== "koolkid_pair_recovery" && batchId !== st.batchId) return;
    const id = payload.contract_id || payload.buy_contract_id || payload.id;
    if (!id || st.pending[String(id)]) return;
    const action = String(payload.action || payload.label || "").toUpperCase();
    const side = action.includes("OVER") ? "OVER_3" : "UNDER_2";
    st.pending[String(id)] = { side, stake: Number(payload.stake || payload.amount || 0), outcome: "" };
    updateKoolkidPairRecoveryPanel();
  }

  function updateKoolkidPairRecoveryFromResult(payload) {
    if (!payload || String(payload.profile || "").toUpperCase() !== PROFILE) return;
    const st = getKoolkidPairRecoveryState();
    if (!st.inProgress || !st.batchId) return;
    const id = String(payload.contract_id || payload.buy_contract_id || payload.id || "");
    const mode = String(payload.mode || "").toLowerCase();
    const batchId = String(payload.batch_id || payload.batchId || "");
    if (id && !st.pending[id] && mode !== "koolkid_pair_recovery" && batchId !== st.batchId) return;
    const item = id && st.pending[id] ? st.pending[id] : null;
    if (!item || item.outcome) return;
    const outcome = resolveKoolkidTradeOutcome(payload);
    if (!outcome) return;
    item.outcome = outcome;
    st.settled = Object.keys(st.pending || {}).filter((key) => st.pending[key] && st.pending[key].outcome).length;
    const profit = Number(payload.profit ?? payload.pnl ?? payload.net_profit);
    if (Number.isFinite(profit)) st.totalProfit = Number((Number(st.totalProfit || 0) + profit).toFixed(2));
    if (outcome === "WIN") {
      st.hasWin = true;
      st.lastResult = item.side === "UNDER_2" ? "Under 2 won" : "Over 3 won";
      st.status = "Won";
      st.inProgress = false;
      st.running = false;
      st.pending = {};
      if (readKoolkidPairRecoverySettings().resetAfterWin) {
        st.round = 1;
        st.lossAccumulated = 0;
      }
      updateKoolkidPairRecoveryPanel();
      safeToast(`KOOLKID recovery ${st.lastResult}. Cycle reset.`, "success");
      return;
    }
    const pendingCount = Object.keys(st.pending || {}).length;
    if (pendingCount >= 2 && st.settled >= 2 && !st.hasWin) {
      st.lossAccumulated = 0;
      st.round = Math.max(1, Number(st.round) || 1) + 1;
      st.lastResult = "Both lost";
      st.inProgress = false;
      st.pending = {};
      const settings = readKoolkidPairRecoverySettings();
      if (st.round > settings.maxRounds) {
        stopKoolkidPairRecovery("Stopped: max rounds reached.");
        safeToast("KOOLKID recovery stopped: max rounds reached.", "error");
        return;
      }
      st.status = "Running: firing next pair";
      updateKoolkidPairRecoveryPanel();
      if (st.enabled && st.running && !st.stopRequested) {
        setTimeout(() => startKoolkidPairRecovery(), 0);
      }
    } else {
      st.status = `Running: waiting for ${Math.max(0, 2 - st.settled)} result(s)`;
      updateKoolkidPairRecoveryPanel();
    }
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

  function setSelectValueKoolkid(id, value) {
    const el = document.getElementById(id);
    if (!el) return;
    const next = value === null || value === undefined ? "" : String(value);
    if (el.value !== next) el.value = next;
  }

  function renderTesttrialKoolkid(data) {
    if (data && typeof data === "object") state.testtrial = data;
    const d = state.testtrial || {};
    const btn = document.getElementById("testtrialBtnKoolkid");
    const info = document.getElementById("testtrialInfoKoolkid");
    const modeSelect = document.getElementById("testtrialStrategyModeKoolkid");
    const stakeModeSelect = document.getElementById("testtrialStakeModeKoolkid");
    const windowInput = document.getElementById("testtrialWindowTicksKoolkid");
    const minTargetInput = document.getElementById("testtrialMinTargetKoolkid");
    const maxStakeInput = document.getElementById("testtrialMaxTotalStakeKoolkid");
    const filterBtn = document.getElementById("testtrialOverplayedBtnKoolkid");
    const symbolEl = document.getElementById("testtrialCurrentSymbolKoolkid");
    const streamEl = document.getElementById("testtrialDigitStreamKoolkid");
    const lowEl = document.getElementById("testtrialLowEdgeCountKoolkid");
    const highEl = document.getElementById("testtrialHighEdgeCountKoolkid");
    const middleEl = document.getElementById("testtrialMiddleZoneCountKoolkid");
    const recEl = document.getElementById("testtrialRecommendationKoolkid");
    const reasonEl = document.getElementById("testtrialReasonKoolkid");
    const payoutStatusEl = document.getElementById("testtrialPayoutStatusKoolkid");
    const payoutReasonEl = document.getElementById("testtrialPayoutReasonKoolkid");
    const cooldownStatusEl = document.getElementById("testtrialCooldownStatusKoolkid");
    const cooldownDetailEl = document.getElementById("testtrialCooldownDetailKoolkid");
    const confOver1El = document.getElementById("testtrialConfidenceOver1Koolkid");
    const confUnder8El = document.getElementById("testtrialConfidenceUnder8Koolkid");
    const confBothEl = document.getElementById("testtrialConfidenceBothKoolkid");

    const enabled = !!d.enabled;
    const strategyMode = String(d.strategy_mode || "AUTO_COMBINED");
    const stakeMode = String(d.stake_mode || "FIXED");
    const confidence = d.confidence || {};
    const counts = d.counts || {};
    const payout = d.payout_safety || {};
    const cooldown = d.cooldown || {};
    const overplayed = !!d.overplayed;
    const overplayedLabel = Array.isArray(d.overplayed_digits) && d.overplayed_digits.length
      ? ` (${d.overplayed_digits.join(", ")})`
      : "";

    if (btn) {
      btn.innerText = `testtrial: ${enabled ? "ON" : "OFF"}`;
      btn.style.background = enabled ? "#22c55e" : "#1e293b";
      btn.style.color = enabled ? "#052e16" : "#e2e8f0";
    }
    if (info) {
      info.innerText = enabled
        ? `testtrial is live on ${String(d.current_symbol || "--")} • ${String(d.reason_text || "Scanning combined Over 1 / Under 8 logic...")}`
        : "testtrial combines OVER 1, UNDER 8, and BOTH mode using KOOLKID tick pressure + payout safety.";
      info.style.color = enabled ? "#cbd5e1" : "#94a3b8";
    }

    setSelectValueKoolkid("testtrialStrategyModeKoolkid", strategyMode);
    setSelectValueKoolkid("testtrialStakeModeKoolkid", stakeMode);
    setInputValueIfIdle("testtrialWindowTicksKoolkid", d.window_ticks || 20);
    setInputValueIfIdle("testtrialMinTargetKoolkid", d.min_target || 0.15);
    setInputValueIfIdle("testtrialMaxTotalStakeKoolkid", d.max_total_stake || 3.0);

    if (filterBtn) {
      const filterOn = !!d.overplayed_filter_enabled;
      filterBtn.innerText = `Filter: ${filterOn ? "ON" : "OFF"}`;
      filterBtn.style.background = filterOn ? "#22c55e" : "#1e293b";
      filterBtn.style.color = filterOn ? "#052e16" : "#e2e8f0";
    }
    if (symbolEl) {
      symbolEl.innerText = `Market: ${String(d.current_symbol || "--")}`;
    }
    if (streamEl) {
      const digits = Array.isArray(d.last20_digits) ? d.last20_digits : [];
      if (!digits.length) {
        streamEl.innerHTML = `<div style="color:#64748b; font-size:12px;">Waiting for live digits...</div>`;
      } else {
        streamEl.innerHTML = digits.map((digit) => `<div class="testtrial-digit-chip">${digit}</div>`).join("");
      }
    }
    if (lowEl) lowEl.innerText = `${Number(counts.low_edge || 0)}`;
    if (highEl) highEl.innerText = `${Number(counts.high_edge || 0)}`;
    if (middleEl) middleEl.innerText = `${Number(counts.middle_zone || 0)}`;
    if (confOver1El) confOver1El.innerText = `${Number(confidence.over1 || 0)}%`;
    if (confUnder8El) confUnder8El.innerText = `${Number(confidence.under8 || 0)}%`;
    if (confBothEl) confBothEl.innerText = `${Number(confidence.both || 0)}%`;
    if (recEl) {
      recEl.innerText = String(d.recommended_action || "SKIP");
      recEl.style.color = d.recommended_action === "BOTH"
        ? "#facc15"
        : (d.recommended_action === "SKIP" ? "#f87171" : "#22c55e");
    }
    if (reasonEl) {
      const reasonPrefix = overplayed ? `Overplayed${overplayedLabel} • ` : "";
      reasonEl.innerText = `${reasonPrefix}${String(d.reason_text || "Waiting for testtrial analysis...")}`;
    }
    if (payoutStatusEl) {
      payoutStatusEl.innerText = String(payout.status || "WAIT");
      payoutStatusEl.style.color = payout.ok ? "#22c55e" : "#f59e0b";
    }
    if (payoutReasonEl) {
      const parts = [];
      if (payout.reason) parts.push(String(payout.reason));
      if (payout.net_low !== undefined && payout.net_low !== null) {
        parts.push(`Low ${Number(payout.net_low).toFixed(2)} / High ${Number(payout.net_high || 0).toFixed(2)} / Mid ${Number(payout.net_mid || 0).toFixed(2)}`);
      }
      payoutReasonEl.innerText = parts.join(" • ") || "Waiting for live quotes...";
    }
    if (cooldownStatusEl) {
      cooldownStatusEl.innerText = String(cooldown.status || "READY");
      cooldownStatusEl.style.color = String(cooldown.status || "").toUpperCase().includes("READY") ? "#22c55e" : "#f59e0b";
    }
    if (cooldownDetailEl) {
      const activeTrade = cooldown.active_trade || {};
      cooldownDetailEl.innerText = activeTrade.symbol
        ? `Active: ${String(activeTrade.action || "TRADE")} on ${String(activeTrade.symbol || "--")}`
        : `Ticks remaining: ${Number(cooldown.ticks_remaining || 0)}`;
    }
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
const optionE = document.getElementById("dual2xCustomComboBtnKoolkid");
    const under3SplitBtn = document.getElementById("under3SplitBtnKoolkid");
    if (btn) {
      btn.innerText = state.dual2xBusy ? "DUAL 2x (RUNNING...)" : (state.dual2xOpen ? "DUAL 2x ▼" : "DUAL 2x");
      btn.style.background = state.dual2xBusy ? "#0ea5e9" : (state.dual2xOpen ? "#22c55e" : "#1e293b");
    }
    if (wrap) wrap.style.display = state.dual2xOpen ? "block" : "none";
  [optionA, optionB, optionC, optionD, optionE].forEach((b) => {
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
    const batchId = `koolkid_dual2x_${Date.now()}_${Math.floor(Math.random() * 10000)}`;
    const fixedTotal = legs.reduce((sum, leg) => {
      const fixedStake = Number(leg && leg.fixedStake);
      return sum + ((Number.isFinite(fixedStake) && fixedStake > 0) ? fixedStake : 0);
    }, 0);
    const stake = fixedTotal > 0
      ? getProfileReinvestStakeKoolkid(fixedTotal)
      : getStakeValueKoolkid();
    const duration = getDurationTicksKoolkid();
    const totalWeight = legs.reduce((sum, leg) => sum + Math.max(0, Number(leg.weight || 1)), 0) || 1;
    const fixedWeightTotal = fixedTotal > 0
      ? legs.reduce((sum, leg) => {
        const fixedStake = Number(leg && leg.fixedStake);
        return sum + ((Number.isFinite(fixedStake) && fixedStake > 0) ? fixedStake : 0);
      }, 0)
      : 0;
    const plannedLegs = legs.map((leg) => {
      const fixedStake = Number(leg.fixedStake);
      const weight = Math.max(0, Number(leg.weight || 1));
      const legStake = (fixedWeightTotal > 0 && Number.isFinite(fixedStake) && fixedStake > 0)
        ? Number((stake * fixedStake / fixedWeightTotal).toFixed(2))
        : Number((stake * weight / totalWeight).toFixed(2));
      return Object.assign({}, leg, { legStake });
    });
    const jobs = plannedLegs.map((leg) => {
      const payload = {
        stake: leg.legStake,
        amount: leg.legStake,
        type: String(leg.type || "OVER").toUpperCase(),
        barrier: Number(leg.barrier),
        duration,
        duration_unit: "t",
        same_tick: true,
        mode: "koolkid_dual2x",
        batch_id: batchId,
        batch_size: plannedLegs.length,
        batch_stake: stake,
        label: leg.label || `${leg.type} ${leg.barrier}`,
      };
      return sendFastManualTradeKoolkid(payload, {
        turbo: true,
        queue: false,
        useSocket: true,
        fireAndForget: true,
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
    return { placed, failures, stake, stakes, duration };
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

  function getPredictionBarrierKoolkid() {
    const node = document.getElementById("barrier");
    const value = Number(node && node.value);
    return Number.isInteger(value) && value >= 0 && value <= 9 ? value : 5;
  }

  function getPredictionContractKoolkid(barrier) {
    const normalized = Math.max(0, Math.min(9, Number(barrier) || 0));
    return normalized <= 5
      ? { type: "OVER", barrier: normalized, label: `OVER ${normalized}` }
      : { type: "UNDER", barrier: normalized, label: `UNDER ${normalized}` };
  }

  function extractPredictionDigitsKoolkid(data) {
    const sources = [
      data && data.last20_digits,
      data && data.recent_digits,
      data && data.testtrial_data && data.testtrial_data.last20_digits,
      data && data.kid2vix_data && data.kid2vix_data.last20_digits,
      data && data.barrier_analysis && data.barrier_analysis.last20_digits,
    ];
    for (const source of sources) {
      if (!Array.isArray(source) || !source.length) continue;
      return source
        .map((digit) => Number(digit))
        .filter((digit) => Number.isInteger(digit) && digit >= 0 && digit <= 9)
        .slice(-20);
    }
    return null;
  }

  function extractPredictionTickCountKoolkid(data) {
    const candidates = [
      data && data.tick_count,
      data && data.global_tick_count,
    ];
    for (const candidate of candidates) {
      const tick = Number(candidate);
      if (Number.isFinite(tick)) return tick;
    }
    return null;
  }

  function extractPredictionLastDigitKoolkid(data) {
    const candidates = [
      data && data.last_digit,
      data && data.digit,
      data && data.current_digit,
      data && data.testtrial_data && data.testtrial_data.last_digit,
      data && data.kid2vix_data && data.kid2vix_data.last_digit,
    ];
    for (const candidate of candidates) {
      const digit = Number(candidate);
      if (Number.isInteger(digit) && digit >= 0 && digit <= 9) return digit;
    }
    return null;
  }

  function syncPredictionRecentDigitsKoolkid(data) {
    const explicitDigits = extractPredictionDigitsKoolkid(data);
    if (explicitDigits && explicitDigits.length) {
      state.predictionRecentDigits = explicitDigits.slice(-20);
      const explicitTick = extractPredictionTickCountKoolkid(data);
      if (Number.isFinite(explicitTick)) state.predictionLastTickCount = explicitTick;
      return;
    }
    const tick = extractPredictionTickCountKoolkid(data);
    const digit = extractPredictionLastDigitKoolkid(data);
    if (!Number.isInteger(digit)) return;
    if (Number.isFinite(tick) && tick === state.predictionLastTickCount) return;
    if (Number.isFinite(tick)) state.predictionLastTickCount = tick;
    const next = Array.isArray(state.predictionRecentDigits) ? state.predictionRecentDigits.slice(-19) : [];
    next.push(digit);
    state.predictionRecentDigits = next;
  }

  function buildPredictionSummaryKoolkid() {
    const barrier = getPredictionBarrierKoolkid();
    const contract = getPredictionContractKoolkid(barrier);
    const digits = Array.isArray(state.predictionRecentDigits) ? state.predictionRecentDigits.slice(-20) : [];
    const total = digits.length;
    if (total < 6) {
      return {
        label: contract.label,
        confidence: 50,
        analysis: "Analyzing digit distribution...",
        stream: digits,
      };
    }

    const isWin = (digit) => (contract.type === "OVER" ? digit > contract.barrier : digit < contract.barrier);
    const winCount = digits.filter(isWin).length;
    const lossCount = total - winCount;
    let maxLossStreak = 0;
    let currentLossStreak = 0;
    digits.forEach((digit) => {
      currentLossStreak = isWin(digit) ? 0 : currentLossStreak + 1;
      if (currentLossStreak > maxLossStreak) maxLossStreak = currentLossStreak;
    });
    const rawConfidence = (winCount / total) * 100;
    const confidence = Math.max(5, Math.min(99, Math.round(rawConfidence - (Math.max(0, maxLossStreak - 1) * 4))));
    const winningDigitsLabel = contract.type === "OVER" ? `${contract.barrier + 1}-9` : `0-${contract.barrier - 1}`;
    const losingDigitsLabel = contract.type === "OVER" ? `0-${contract.barrier}` : `${contract.barrier}-9`;
    const analysisLead = confidence >= 70
      ? `Winning digits ${winningDigitsLabel} dominated the last ${total} ticks.`
      : (confidence <= 40
        ? `Losing digits ${losingDigitsLabel} played too often across the last ${total} ticks.`
        : `The last ${total} ticks are mixed, so the edge is moderate right now.`);
    const analysisTail = contract.type === "OVER"
      ? `OVER ${contract.barrier} won ${winCount}/${total} checks, while ${losingDigitsLabel} printed ${lossCount} times.`
      : `UNDER ${contract.barrier} won ${winCount}/${total} checks, while ${losingDigitsLabel} printed ${lossCount} times.`;
    return {
      label: contract.label,
      confidence,
      analysis: `${analysisLead} ${analysisTail}`,
      stream: digits,
    };
  }

  function isLowDigitForOver6Koolkid(digit) {
    return Number.isInteger(digit) && digit >= 0 && digit <= 6;
  }

  function getLowDigitStreakOver6Koolkid(buffer) {
    const digits = Array.isArray(buffer) ? buffer : [];
    let streak = 0;
    for (let i = digits.length - 1; i >= 0; i -= 1) {
      if (!isLowDigitForOver6Koolkid(Number(digits[i]))) break;
      streak += 1;
    }
    return streak;
  }

  function countLowDigitsLastFiveOver6Koolkid(buffer) {
    return (Array.isArray(buffer) ? buffer.slice(-5) : []).filter((digit) => isLowDigitForOver6Koolkid(Number(digit))).length;
  }

  function getTicksSinceHighDigitOver6Koolkid(buffer) {
    const digits = Array.isArray(buffer) ? buffer : [];
    for (let i = digits.length - 1, ticks = 0; i >= 0; i -= 1, ticks += 1) {
      const digit = Number(digits[i]);
      if (Number.isInteger(digit) && digit >= 7 && digit <= 9) return ticks;
    }
    return digits.length;
  }

  function formatOver6DigitsStripKoolkid(digits) {
    if (!Array.isArray(digits) || !digits.length) return `<span style="color:#8fb1c9;">Waiting for live digits...</span>`;
    return digits.map((digit) => {
      const value = Number(digit);
      const tone = isLowDigitForOver6Koolkid(value) ? "low" : "high";
      return `<span class="over6-analyzer-digit ${tone}">${value}</span>`;
    }).join("");
  }

  function buildOver6AnalyzerSignalKoolkid() {
    const digits = Array.isArray(state.predictionRecentDigits) ? state.predictionRecentDigits.slice(-10) : [];
    const last5 = digits.slice(-5);
    const lowCountLast5 = countLowDigitsLastFiveOver6Koolkid(digits);
    const lowStreak = getLowDigitStreakOver6Koolkid(digits);
    const filterA = digits.length >= 3 && lowStreak >= 3;
    const filterB = last5.length >= 5 && lowCountLast5 >= 4;
    const total = digits.length;
    const lowCountLast10 = digits.filter((digit) => isLowDigitForOver6Koolkid(Number(digit))).length;
    const highCountLast10 = total - lowCountLast10;
    const lowPct = total ? Math.round((lowCountLast10 / total) * 100) : 0;
    const highPct = total ? Math.round((highCountLast10 / total) * 100) : 0;
    const status = total < 5
      ? "COLLECTING"
      : (filterA && filterB)
        ? "STRONG READY"
        : (filterA || filterB)
          ? "READY"
          : "WAITING";
    const suggestedAction = total < 5
      ? "Collecting data..."
      : (filterA && filterB)
        ? "Strong Over 6 Watch"
        : (filterA || filterB)
          ? "Watch Over 6"
          : "No Setup";
    const confidence = total < 5 ? null : (filterA && filterB ? 78 : (filterA || filterB ? 64 : 28));

    return {
      name: "OVER 6 ANALYZER",
      last_digits: digits,
      last_5: last5,
      low_count_last_5: lowCountLast5,
      low_streak: lowStreak,
      filter_a_triggered: filterA,
      filter_b_triggered: filterB,
      status,
      suggested_action: suggestedAction,
      confidence,
      low_pct_last_10: lowPct,
      high_pct_last_10: highPct,
      ticks_since_last_high: getTicksSinceHighDigitOver6Koolkid(digits),
    };
  }

  function isMonthlyPredictionSummaryUserKoolkid() {
    return !isLifetimeUserKoolkid() && (isRegularMonthlyUserKoolkid() || isPaidMonthlyUserKoolkid());
  }

  function syncPredictionSummaryDropdownKoolkid() {
    const block = document.getElementById("koolkidConfidenceBarsBlock");
    const dropdown = document.getElementById("predictionSummaryDropdownKoolkid");
    const card = document.getElementById("predictionSummaryCardKoolkid");
    const isMonthly = isMonthlyPredictionSummaryUserKoolkid();
    if (block) block.classList.toggle("monthly-prediction-summary-mode", isMonthly);
    if (dropdown) {
      dropdown.style.display = "";
      dropdown.removeAttribute("data-monthly-hidden");
      dropdown.classList.toggle("monthly-dropdown-mode", isMonthly);
      if (isMonthly) {
        if (dropdown.dataset.monthlyDefaultClosedApplied !== "1") {
          dropdown.open = false;
          dropdown.dataset.monthlyDefaultClosedApplied = "1";
        }
      } else {
        dropdown.open = true;
        delete dropdown.dataset.monthlyDefaultClosedApplied;
      }
    }
    if (card) {
      card.style.display = "";
      card.removeAttribute("data-monthly-hidden");
    }
  }

  function renderPredictionSummaryKoolkid(data) {
    if (data) syncPredictionRecentDigitsKoolkid(data);
    syncPredictionSummaryDropdownKoolkid();
    const card = document.getElementById("predictionSummaryCardKoolkid");
    const labelNode = document.getElementById("predictionSummaryLabelKoolkid");
    const confidenceNode = document.getElementById("predictionSummaryConfidenceKoolkid");
    const analysisNode = document.getElementById("predictionSummaryAnalysisKoolkid");
    const streamNode = document.getElementById("predictionSummaryStreamKoolkid");
    if (!card || !labelNode || !confidenceNode || !analysisNode || !streamNode) return;

    const summary = buildPredictionSummaryKoolkid();
    labelNode.innerText = summary.label;
    confidenceNode.innerText = `${summary.confidence}%`;
    analysisNode.innerText = summary.analysis;
    streamNode.innerHTML = summary.stream.length
      ? summary.stream.map((digit) => {
        const markerType = getPredictionResultMarkerKoolkid(digit);
        const markerClass = markerType ? ` trade-result-${markerType}` : "";
        const markerEmoji = markerType === "win"
          ? `<span class="prediction-summary-result-emoji">💲</span>`
          : markerType === "loss"
            ? `<span class="prediction-summary-result-emoji">😞</span>`
            : "";
        return `<span class="prediction-summary-digit-chip${markerClass}">${digit}${markerEmoji}</span>`;
      }).join("")
      : `<span style="color:#8fb1c9;">Waiting for live digits...</span>`;
  }

  function getPredictionResultMarkerKoolkid(digit) {
    const marker = state.predictionResultMarker || {};
    const markerDigit = Number(marker.digit);
    const currentDigit = Number(digit);
    if (!Number.isInteger(markerDigit) || !Number.isInteger(currentDigit)) return "";
    if (markerDigit !== currentDigit || Date.now() >= Number(marker.until || 0)) return "";
    return marker.type === "win" || marker.type === "loss" ? marker.type : "";
  }

  function resolveKoolkidTradeResultType(trade) {
    const raw = String((trade && (trade.result || trade.status || trade.outcome)) || "").toUpperCase();
    if (raw.includes("WIN")) return "win";
    if (raw.includes("LOSS") || raw.includes("LOST")) return "loss";
    const profit = Number(trade && (trade.profit ?? trade.profit_value ?? trade.pnl ?? trade.net_profit ?? trade.result_profit ?? trade.open_profit));
    if (Number.isFinite(profit) && profit > 0) return "win";
    if (Number.isFinite(profit) && profit < 0) return "loss";
    return "";
  }

  function extractKoolkidTradeResultDigit(trade) {
    const candidates = [
      trade && trade.exit_digit,
      trade && trade.exitDigit,
      trade && trade.last_digit,
      trade && trade.digit,
      trade && trade.final_digit,
    ];
    for (const value of candidates) {
      const digit = Number(value);
      if (Number.isInteger(digit) && digit >= 0 && digit <= 9) return digit;
    }
    return null;
  }

  function handleKoolkidLiveDigitTradeResult(trade) {
    if (!trade || String(trade.profile || "").toUpperCase() !== PROFILE) return;
    const type = resolveKoolkidTradeResultType(trade);
    const digit = extractKoolkidTradeResultDigit(trade);
    if (!type || digit === null) return;
    if (typeof window.markDigitAnalysisTradeResult === "function") {
      window.markDigitAnalysisTradeResult(digit, type);
    }
  }

  function renderOver6AnalyzerKoolkid(data) {
    if (data) syncPredictionRecentDigitsKoolkid(data);
    const cardNode = document.getElementById("over6AnalyzerCardKoolkid");
    const profileIsActive = String(window.activeProfile || "").toUpperCase() === PROFILE;
    const shouldShowCard = profileIsActive && isLifetimeUserKoolkid();
    if (cardNode) cardNode.style.display = shouldShowCard ? "block" : "none";
    if (!shouldShowCard) return;
    const badgeNode = document.getElementById("over6AnalyzerBadgeKoolkid");
    const statusNode = document.getElementById("over6AnalyzerStatusKoolkid");
    const actionNode = document.getElementById("over6AnalyzerActionKoolkid");
    const confidenceNode = document.getElementById("over6AnalyzerConfidenceKoolkid");
    const lastReadyNode = document.getElementById("over6AnalyzerLastReadyKoolkid");
    const last10Node = document.getElementById("over6AnalyzerLast10Koolkid");
    const last5Node = document.getElementById("over6AnalyzerLast5Koolkid");
    const lowCountNode = document.getElementById("over6AnalyzerLowCountKoolkid");
    const lowStreakNode = document.getElementById("over6AnalyzerLowStreakKoolkid");
    const splitNode = document.getElementById("over6AnalyzerSplitKoolkid");
    const ticksSinceHighNode = document.getElementById("over6AnalyzerTicksSinceHighKoolkid");
    const toggleNode = document.getElementById("over6AnalyzerUseForEntryKoolkid");
    if (!badgeNode || !statusNode || !actionNode || !confidenceNode || !lastReadyNode || !last10Node || !last5Node || !lowCountNode || !lowStreakNode || !splitNode || !ticksSinceHighNode) return;

    const signal = buildOver6AnalyzerSignalKoolkid();
    if (signal.status === "READY" || signal.status === "STRONG READY") state.over6Analyzer.lastReadyAt = Date.now();
    const readyAt = Number(state.over6Analyzer.lastReadyAt || 0);
    const lastReadyLabel = readyAt ? new Date(readyAt).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" }) : "Waiting for setup...";
    const signature = JSON.stringify({
      status: signal.status,
      action: signal.suggested_action,
      confidence: signal.confidence,
      last: signal.last_digits,
      useForEntry: !!state.over6Analyzer.useForEntry,
      lastReadyLabel,
    });
    if (signature === state.over6Analyzer.lastSignature) return;
    state.over6Analyzer.lastSignature = signature;

    const badgeClass = signal.status === "STRONG READY" ? "strong" : (signal.status === "READY" ? "ready" : "waiting");
    badgeNode.className = `over6-analyzer-badge ${badgeClass}`;
    badgeNode.innerText = signal.status === "COLLECTING" ? "WAITING" : signal.status;
    statusNode.innerText = signal.status === "COLLECTING" ? "Collecting data..." : signal.status;
    actionNode.innerText = signal.suggested_action;
    confidenceNode.innerText = signal.confidence === null ? "-" : `${signal.confidence}%`;
    lastReadyNode.innerText = lastReadyLabel;
    last10Node.innerHTML = formatOver6DigitsStripKoolkid(signal.last_digits);
    last5Node.innerHTML = signal.last_5.length ? formatOver6DigitsStripKoolkid(signal.last_5) : `<span style="color:#8fb1c9;">Collecting data...</span>`;
    lowCountNode.innerText = String(signal.low_count_last_5 || 0);
    lowStreakNode.innerText = String(signal.low_streak || 0);
    splitNode.innerText = `${signal.low_pct_last_10}% low / ${signal.high_pct_last_10}% high`;
    ticksSinceHighNode.innerText = String(signal.ticks_since_last_high || 0);
    if (toggleNode) toggleNode.checked = !!state.over6Analyzer.useForEntry;
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
    if (data && typeof data === "object") setTimeout(() => maybeRunKoolkidBalancedRecoveryThinking(), 0);
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
    const lossGuardBlocked = !!d.loss_guard_blocked;
    const lossGuardReason = String(d.loss_guard_reason || "");
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
    if (setupReady && lossGuardBlocked) {
      info.style.color = "#ef4444";
      info.innerText = `Trade skipped on ${marketLabel}: ${lossGuardReason} • ${counts} • ${session}`;
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

  function escapeHtmlKoolkid(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function findGoldenCardFocusRowKoolkid(results) {
    const rows = Array.isArray(results) ? results : [];
    const ready = rows.find((row) => row && (row.ready_confirmed || row.entry_ready));
    if (ready) return ready;
    return rows.reduce((best, row) => {
      if (!row) return best;
      const confidence = Number(row.confidence_pct || 0);
      const bestConfidence = best ? Number(best.confidence_pct || 0) : -1;
      return confidence > bestConfidence ? row : best;
    }, null);
  }

  function getGoldenCardAutoCandidateKoolkid(data) {
    const d = data || state.goldenCard || {};
    if (String(d.ready_state || "").toLowerCase() !== "ready") return null;
    const results = Array.isArray(d.results) ? d.results : [];
    return results.find((row) => {
      if (!row) return false;
      if (!(row.ready_confirmed && row.entry_ready)) return false;
      if (String(row.ready_state || "").toLowerCase() !== "ready") return false;
      if (row.loss_guard_blocked || row.conflict_blocked || row.market_quality_ok === false) return false;
      return Number(row.confidence_pct || 0) >= 85;
    }) || null;
  }

  function syncGoldenCardAutoUiKoolkid() {
    const autoNode = document.getElementById("goldenCardAutoTraderKoolkid");
    const statusNode = document.getElementById("goldenCardAutoStatusKoolkid");
    if (autoNode) autoNode.checked = !!state.goldenCardAutoOn;
    if (statusNode) {
      statusNode.style.color = state.goldenCardAutoOn ? "#fde68a" : "#94a3b8";
      statusNode.innerText = state.goldenCardAutoOn
        ? (state.goldenCardAutoWaitingReset
            ? "Auto Trader ON. One 85%+ trade already fired. Waiting for the board to reset before the next one."
            : "Auto Trader ON. Fires one trade instantly when a ready setup hits 85%+ confidence.")
        : "Auto Trader OFF.";
    }
  }

  async function maybeRunGoldenCardAutoKoolkid(data) {
    if (!state.goldenCardAutoOn || state.goldenCardTradeBusy || !isActive()) return;
    const row = getGoldenCardAutoCandidateKoolkid(data);
    if (!row) {
      state.goldenCardAutoLastSignalKey = "";
      state.goldenCardAutoWaitingReset = false;
      syncGoldenCardAutoUiKoolkid();
      return;
    }
    if (state.goldenCardAutoWaitingReset) return;
    const signalKey = [
      String(row.symbol || "").toUpperCase(),
      String(row.recommended_type || "").toUpperCase(),
      Number(row.recommended_barrier || 0),
      Number(row.confidence_pct || 0).toFixed(1),
      Number(row.confirmation_count || 0),
    ].join("|");
    if (signalKey === state.goldenCardAutoLastSignalKey) return;
    state.goldenCardAutoLastSignalKey = signalKey;
    const placed = await window.placeGoldenCardTradeKoolkid(String(row.symbol || "").toUpperCase());
    if (placed) {
      state.goldenCardAutoWaitingReset = true;
      syncGoldenCardAutoUiKoolkid();
    }
  }

  function renderGoldenCardHeroKoolkid(data, results) {
    const d = data || {};
    const btn = document.getElementById("goldenCardBtnKoolkid");
    const statePill = document.getElementById("goldenCardStatePillKoolkid");
    const confidenceEl = document.getElementById("goldenCardConfidenceKoolkid");
    const subtextEl = document.getElementById("goldenCardSubtextKoolkid");
    const reasonEl = document.getElementById("goldenCardReasonKoolkid");
    const running = !!d.running;
    const focus = findGoldenCardFocusRowKoolkid(results);
    const ready = !!(focus && (focus.ready_confirmed || focus.entry_ready));
    const visualState = ready ? "ready" : (running ? "active" : "waiting");
    const confidence = Number(d.best_confidence_pct != null ? d.best_confidence_pct : (focus ? focus.confidence_pct : 0)) || 0;
    const tradeLabel = String((ready && (d.ready_trade_label || (focus && focus.recommended_label))) || (focus && focus.recommended_label) || "OVER 1 / UNDER 8");
    const marketLabel = String((ready && (d.ready_market || (focus && (focus.market_label || focus.symbol)))) || (focus && (focus.market_label || focus.symbol)) || "best market");
    const reason = String(d.ready_reason || (focus && focus.ready_reason) || (running ? "Scanning live markets for a premium setup." : "Waiting for Golden Card scan to start."));

    if (btn) {
      btn.classList.remove("is-waiting", "is-ready", "is-active");
      btn.classList.add(`is-${visualState}`);
      btn.setAttribute("data-golden-state", visualState);
      btn.setAttribute("aria-label", `Golden Card ${visualState}`);
    }
    if (statePill) statePill.innerText = visualState === "ready" ? "READY" : (visualState === "active" ? "ACTIVE" : "WAITING");
    if (confidenceEl) confidenceEl.innerText = confidence > 0 ? `${confidence.toFixed(0)}% CONF` : "--% CONF";
    if (subtextEl) {
      subtextEl.innerText = ready
        ? `${tradeLabel} on ${marketLabel}`
        : (running ? "Live scan needs 2 clean checks in a row" : "Premium multi-market setup finder");
    }
    if (reasonEl) reasonEl.innerText = reason;
  }

  function renderGoldenCardKoolkid(data) {
    if (data && typeof data === "object") state.goldenCard = data;
    const d = state.goldenCard || {};
    const info = document.getElementById("goldenCardInfoKoolkid");
    const statusEl = document.getElementById("goldenCardStatusKoolkid");
    const progressEl = document.getElementById("goldenCardProgressKoolkid");
    const resultsEl = document.getElementById("goldenCardResultsKoolkid");
    const running = !!d.running;
    const historyTarget = Number(d.history_target || 20) || 20;
    const symbols = Array.isArray(d.symbols) ? d.symbols : [];
    const poolSize = Number(d.market_pool_size || symbols.length || 10) || (symbols.length || 10);
    const warmed = Number(d.completed_markets || 0) || 0;
    const statusText = String(d.status || "Golden Card is waiting to scan markets.");
    const results = Array.isArray(d.results) ? d.results : [];
    const filterMode = normalizeGoldenCardFilterModeKoolkid(d.filter_mode || "BOTH");
    const addJumpPairs = !!d.add_jump_pairs;

    syncGoldenCardControlsKoolkid(d);

    renderGoldenCardHeroKoolkid(d, results);
    if (info) {
      const stateReason = String(d.ready_reason || statusText);
      info.style.color = d.ready_state === "ready" ? "#facc15" : (running ? "#fde68a" : "#94a3b8");
      info.innerText = stateReason || statusText;
    }
    syncGoldenCardAutoUiKoolkid();
    if (statusEl) statusEl.innerText = statusText;
    if (progressEl) {
      const modeText = filterMode === "OVER1"
        ? "OVER 1 only"
        : (filterMode === "OVER2"
          ? "OVER 2 only"
          : (filterMode === "UNDER8" ? "UNDER 8 only" : "Both"));
      progressEl.innerText = `${warmed} / ${symbols.length || 10} active warmed • pool ${poolSize} • ${modeText}${addJumpPairs ? " • Jump ON" : ""} • rolling ${historyTarget} ticks`;
    }
    if (!resultsEl) return;
    if (!results.length) {
      const emptyText = running
        ? "Scanning market ticks live..."
        : (filterMode === "OVER1"
          ? "Golden Card will show OVER 1 setups here after the scan starts."
          : (filterMode === "OVER2"
            ? "Golden Card will show OVER 2 setups here after the scan starts."
          : (filterMode === "UNDER8"
            ? "Golden Card will show UNDER 8 setups here after the scan starts."
            : "Golden Card results will show here after the scan starts.")));
      resultsEl.innerHTML = `<div style="grid-column:1 / -1; text-align:center; color:#64748b; padding:20px;">${emptyText}</div>`;
      return;
    }
    resultsEl.innerHTML = results.map((row) => {
      const tier = String(row.tier || "danger");
      const marketLabel = String(row.market_label || row.symbol || "Market");
      const confidence = Number(row.confidence_pct || 0);
      const setupDigit = Number(row.setup_digit || 3);
      const ticksReady = Number(row.ticks_ready || 0);
      const blocked = !!row.loss_guard_blocked;
      const conflictBlocked = !!row.conflict_blocked;
      const qualityOk = row.market_quality_ok !== false;
      const confirmedReady = !!(row.ready_confirmed || row.entry_ready);
      const rawReady = !!row.raw_entry_ready;
      const confirmationCount = Number(row.confirmation_count || 0);
      const confirmationRequired = Number(row.confirmation_required || d.confirmation_required || 2) || 2;
      const tradeLabel = String(row.recommended_label || "OVER 1");
      const canSample = ticksReady >= historyTarget;
      const readyText = blocked
        ? `${tradeLabel} • SKIP • ${String(row.loss_guard_digits_label || "").trim()} HOT`
        : (conflictBlocked
          ? "WAITING • TRADE ACTIVE"
          : (!qualityOk
            ? `${tradeLabel} • CONF < ${Number(row.confidence_threshold || d.confidence_threshold || 70).toFixed(0)}%`
            : (confirmedReady
              ? `READY • ${tradeLabel}`
              : (rawReady ? `CONFIRMING ${confirmationCount}/${confirmationRequired} • ${tradeLabel}` : (canSample ? `${tradeLabel} LIVE` : `${tradeLabel} • ${ticksReady}/${historyTarget}`)))));
      const reasonText = String(row.ready_reason || readyText);
      const stateClass = confirmedReady ? "ready" : (rawReady ? "pending-confirm" : "");
      return `
        <div class="golden-card-market ${tier} ${stateClass}" data-golden-card-symbol="${escapeHtmlKoolkid(row.symbol || "")}">
          <div style="min-width:0;">
            <div style="display:flex; align-items:center; justify-content:space-between; gap:10px;">
              <div style="font-size:17px; font-weight:800; color:#f8fafc; line-height:1.1;">${escapeHtmlKoolkid(marketLabel)}</div>
              <div style="font-size:12px; color:#e2e8f0; font-weight:700; white-space:nowrap;">${confidence.toFixed(1)}%</div>
            </div>
            <div style="margin-top:6px; font-size:11px; color:${blocked || conflictBlocked ? "#fca5a5" : (confirmedReady ? "#fde68a" : (rawReady ? "#facc15" : "#cbd5e1"))}; font-weight:700; letter-spacing:.02em;">${escapeHtmlKoolkid(readyText)}</div>
            <div style="margin-top:4px; font-size:10px; color:#94a3b8; line-height:1.25;">${escapeHtmlKoolkid(reasonText)}</div>
          </div>
          <div class="golden-card-digit">${setupDigit}</div>
        </div>
      `;
    }).join("");
    Array.from(resultsEl.querySelectorAll("[data-golden-card-symbol]")).forEach((node) => {
      const symbol = String(node.getAttribute("data-golden-card-symbol") || "").toUpperCase();
      const row = results.find((item) => String(item.symbol || "").toUpperCase() === symbol);
      const canTrade = !!row
        && Number(row.ticks_ready || 0) >= historyTarget
        && !!(row.ready_confirmed || row.entry_ready)
        && !row.loss_guard_blocked
        && !row.conflict_blocked
        && row.market_quality_ok !== false;
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
    if (running && state.goldenCardAutoOn) {
      Promise.resolve().then(() => maybeRunGoldenCardAutoKoolkid(d)).catch(() => {});
    }
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

  function rememberG1LastDigitKoolkid(data) {
    const digit = Number(data && (data.last_digit ?? data.digit));
    if (Number.isInteger(digit) && digit >= 0 && digit <= 9) state.g1LastDigit = digit;
  }

  function renderG1AutoUiKoolkid() {
    const mainBtn = document.getElementById("g1AutoBtnKoolkid");
    const statusEl = document.getElementById("g1AutoStatusKoolkid");
    const gridEl = document.getElementById("g1AnalyzerGridKoolkid");
    if (state.g1AutoOn || state.g1AutoBusy) {
      state.g1AutoOn = false;
      state.g1AutoBusy = false;
    }
    if (mainBtn) {
      mainBtn.innerText = "G1🤖 ANALYZER";
      mainBtn.style.background = "#0f172a";
      mainBtn.style.border = "1px solid #334155";
      mainBtn.style.color = "#f8fafc";
    }

    const pct = (state.dual2xAnalysis && state.dual2xAnalysis.pctByDigit) || null;
    const ready = !!(state.dual2xAnalysis && state.dual2xAnalysis.ready && pct);
    if (!ready) {
      if (gridEl) gridEl.innerHTML = `<div style="grid-column:1/-1; color:#8fb1c9; font-size:12px;">Waiting for live digit percentages...</div>`;
      if (statusEl) {
        statusEl.innerText = "Waiting for live digit percentages...";
        statusEl.style.color = "#94a3b8";
      }
      return;
    }

    const rows = [];
    let hottestDigit = null;
    let hottestPct = -1;
    for (let digit = 0; digit <= 9; digit += 1) {
      const value = Number(pct[digit]);
      const safePct = Number.isFinite(value) ? value : 0;
      if (safePct > hottestPct) {
        hottestPct = safePct;
        hottestDigit = digit;
      }
    }
    const dangerThreshold = 10;
    const greenThreshold = 15;
    const liveDigit = Number(state.g1LastDigit);
    const hasLiveDigit = Number.isInteger(liveDigit) && liveDigit >= 0 && liveDigit <= 9;
    const dangerHot = [0, 1, 2].filter((digit) => Number(pct[digit]) > dangerThreshold);
    const dangerGroupActive = dangerHot.length > 0;
    const greenHot = [];
    for (let digit = 3; digit <= 9; digit += 1) {
      const value = Number(pct[digit]);
      if (Number.isFinite(value) && value >= greenThreshold) greenHot.push(digit);
    }
    const greenGroupActive = greenHot.length > 0;

    for (let digit = 0; digit <= 9; digit += 1) {
      const value = Number(pct[digit]);
      const safePct = Number.isFinite(value) ? value : 0;
      const danger = digit <= 2 && dangerGroupActive;
      const safe = digit >= 3 && greenGroupActive && !dangerGroupActive;
      const live = hasLiveDigit && digit === liveDigit;
      const label = danger ? "Danger Hot" : (safe ? "Green Hot" : "Blue");
      rows.push(`
        <div class="g1-analyzer-digit ${danger ? "is-danger" : ""} ${safe ? "is-safe" : ""} ${live ? "is-live" : ""}">
          <div class="g1-analyzer-number">${digit}</div>
          <div class="g1-analyzer-pct">${fmtPct(safePct)}</div>
          <div class="g1-analyzer-label">${label}</div>
        </div>
      `);
    }
    if (gridEl) gridEl.innerHTML = rows.join("");
    if (statusEl) {
      if (dangerHot.length) {
        statusEl.innerText = `RED ALERT: ${dangerHot.join(", ")} ${dangerHot.length === 1 ? "is" : "are"} over ${dangerThreshold}%. 0-2 group is danger.`;
        statusEl.style.color = "#fecaca";
      } else if (greenHot.length) {
        statusEl.innerText = `GREEN WATCH: ${greenHot.join(", ")} ${greenHot.length === 1 ? "is" : "are"} hot while 0-2 stay under ${dangerThreshold}%. 3-9 group is green.`;
        statusEl.style.color = "#bbf7d0";
      } else {
        statusEl.innerText = `BLUE / WAIT: 0-2 are under ${dangerThreshold}% and 3-9 are not hot yet. Hottest digit is ${hottestDigit} at ${fmtPct(hottestPct)}.`;
        statusEl.style.color = "#bfdbfe";
      }
    }
  }

  async function maybeRunG1AutoKoolkid(data) {
    rememberG1LastDigitKoolkid(data || {});
    renderG1AutoUiKoolkid();
  }

  window.openG1AutoPopupKoolkid = function () {
    showCenteredPopupKoolkid("g1AutoPopupKoolkid");
    renderG1AutoUiKoolkid();
  };

  window.hideG1AutoPopupKoolkid = function () {
    hideCenteredPopupKoolkid("g1AutoPopupKoolkid");
  };

  window.toggleG1AutoKoolkid = function () {
    state.g1AutoOn = false;
    state.g1AutoBusy = false;
    renderG1AutoUiKoolkid();
  };

  async function placeG1InstantOverKoolkid(barrier, buttonId) {
    const safeBarrier = Number(barrier) === 2 ? 2 : 1;
    const btn = document.getElementById(buttonId);
    if (btn && btn.disabled) return;
    try {
      if (btn) {
        btn.disabled = true;
        btn.style.opacity = "0.65";
        btn.style.cursor = "wait";
      }
      const stake = getStakeValueKoolkid();
      const payload = {
        stake,
        amount: stake,
        type: "OVER",
        barrier: safeBarrier,
        mode: `g1_instant_over${safeBarrier}`,
        label: `G1 Instant OVER ${safeBarrier}`,
      };
      const result = await sendFastManualTradeKoolkid(payload, {
        turbo: true,
        queue: false,
        useSocket: true,
        fireAndForget: true,
      });
      if (result && result.data && result.data.status === "success") {
        safeToast(`G1 sent OVER ${safeBarrier} instantly`, "success");
      } else {
        safeToast((result && result.data && result.data.message) || `G1 OVER ${safeBarrier} failed`, "error");
      }
    } catch (e) {
      safeToast(`G1 OVER ${safeBarrier} failed`, "error");
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.style.opacity = "1";
        btn.style.cursor = "pointer";
      }
    }
  }

  window.placeG1InstantOver1Koolkid = async function () {
    return placeG1InstantOverKoolkid(1, "g1InstantOver1BtnKoolkid");
  };

  window.placeG1InstantOver2Koolkid = async function () {
    return placeG1InstantOverKoolkid(2, "g1InstantOver2BtnKoolkid");
  };

  function getDual2xCustomConfigKoolkid() {
    const mode = String((document.getElementById("dual2xCustomModeKoolkid") || {}).value || "UNDER8_OVER8").toUpperCase();
    if (mode === "OVER1_UNDER1" || mode === "UNDER1_OVER1") {
      return {
        mode: "OVER1_UNDER1",
        legs: [
          { type: "OVER", barrier: 1, label: "OVER 1" },
          { type: "UNDER", barrier: 1, label: "UNDER 1" },
        ],
      };
    }
    return {
      mode: "UNDER8_OVER8",
      legs: [
        { type: "UNDER", barrier: 8, label: "UNDER 8" },
        { type: "OVER", barrier: 8, label: "OVER 8" },
      ],
    };
  }

  function parseDual2xCustomStakeKoolkid(inputId) {
    const node = document.getElementById(inputId);
    const value = Number(node && node.value);
    if (!Number.isFinite(value) || value < 0.35) return NaN;
    return Number(value.toFixed(2));
  }

  window.syncDual2xCustomPopupKoolkid = function () {
    const config = getDual2xCustomConfigKoolkid();
    const labelA = document.getElementById("dual2xCustomStakeLabelAKoolkid");
    const labelB = document.getElementById("dual2xCustomStakeLabelBKoolkid");
    if (labelA) labelA.innerText = config.legs[0].label;
    if (labelB) labelB.innerText = config.legs[1].label;
  };

  window.openDual2xCustomPopupKoolkid = function () {
    if (state.dual2xBusy) return;
    showCenteredPopupKoolkid("dual2xCustomPopupKoolkid");
    window.syncDual2xCustomPopupKoolkid();
  };

  window.hideDual2xCustomPopupKoolkid = function () {
    hideCenteredPopupKoolkid("dual2xCustomPopupKoolkid");
  };

  window.confirmDual2xCustomKoolkid = async function () {
    if (state.dual2xBusy) return;
    const config = getDual2xCustomConfigKoolkid();
    const stakeA = parseDual2xCustomStakeKoolkid("dual2xCustomStakeAKoolkid");
    const stakeB = parseDual2xCustomStakeKoolkid("dual2xCustomStakeBKoolkid");
    if (!(stakeA >= 0.35) || !(stakeB >= 0.35)) {
      safeToast("Set both stakes to at least $0.35.", "error");
      return;
    }
    state.dual2xBusy = true;
    updateDual2xUIKoolkid();
    try {
      const r = await placeDual2xLegsSameTickKoolkid([
        Object.assign({}, config.legs[0], { fixedStake: stakeA }),
        Object.assign({}, config.legs[1], { fixedStake: stakeB }),
      ]);
      if (r.placed === 2) {
        safeToast(`${config.legs[0].label} ${money(stakeA)} / ${config.legs[1].label} ${money(stakeB)} sent (same tick)`, "success");
        window.hideDual2xCustomPopupKoolkid();
      } else if (r.placed === 1) {
        safeToast(`${config.legs[0].label} / ${config.legs[1].label} partial (1/2)`, "error");
      } else {
        safeToast(`${config.legs[0].label} / ${config.legs[1].label} failed`, "error");
      }
    } catch (e) {
      safeToast("Dual 2x custom combo failed", "error");
    } finally {
      state.dual2xBusy = false;
      updateDual2xUIKoolkid();
    }
  };

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

  function paintDigitAnalysisKoolkid(data) {
    lastDigitAnalysisRenderAt = Date.now();
    rememberG1LastDigitKoolkid(data || {});
    renderPredictionSummaryKoolkid(data || {});
    renderOver6AnalyzerKoolkid(data || {});
    renderDual2xAnalysisKoolkid(data || {});
    renderG1AutoUiKoolkid();
    if (data && data.barrier_analysis) renderBarrierAnalysis(data.barrier_analysis);
    if (data && data.over3_analysis_data) renderOver3AnalysisKoolkid(data.over3_analysis_data);
    if (data && data.golden_card_data) scheduleGoldenCardRenderKoolkid(data.golden_card_data);
    if (data && data.kid2vix_data) renderKid2vixKoolkid(data.kid2vix_data);
    if (data && data.auto_modes) updateModeButtonsFromPayload(data.auto_modes, data);
  }

  function flushDigitAnalysisRenderKoolkid() {
    if (digitAnalysisRenderTimer) {
      const app = App();
      if (!(app && typeof app.clearFrontendTimeout === "function" && app.clearFrontendTimeout("koolkid_digit_analysis_render"))) {
        clearTimeout(digitAnalysisRenderTimer);
      }
      digitAnalysisRenderTimer = null;
    }
    const payload = pendingDigitAnalysisRender;
    pendingDigitAnalysisRender = null;
    if (isActive()) paintDigitAnalysisKoolkid(payload || {});
  }

  function scheduleDigitAnalysisRenderKoolkid(data) {
    pendingDigitAnalysisRender = data || pendingDigitAnalysisRender || {};
    const elapsed = Date.now() - Number(lastDigitAnalysisRenderAt || 0);
    if (elapsed >= DIGIT_RENDER_THROTTLE_MS) {
      flushDigitAnalysisRenderKoolkid();
      return;
    }
    if (!digitAnalysisRenderTimer) {
      digitAnalysisRenderTimer = setTimeout(flushDigitAnalysisRenderKoolkid, Math.max(50, DIGIT_RENDER_THROTTLE_MS - elapsed));
      const app = App();
      if (app && typeof app.registerFrontendTimeout === "function") app.registerFrontendTimeout("koolkid_digit_analysis_render", digitAnalysisRenderTimer);
    }
  }

  function paintGoldenCardRenderKoolkid(data) {
    lastGoldenCardRenderAt = Date.now();
    renderGoldenCardKoolkid(data || {});
  }

  function flushGoldenCardRenderKoolkid() {
    if (goldenCardRenderTimer) {
      const app = App();
      if (!(app && typeof app.clearFrontendTimeout === "function" && app.clearFrontendTimeout("koolkid_golden_card_render"))) {
        clearTimeout(goldenCardRenderTimer);
      }
      goldenCardRenderTimer = null;
    }
    const payload = pendingGoldenCardRender;
    pendingGoldenCardRender = null;
    if (isActive()) paintGoldenCardRenderKoolkid(payload || {});
  }

  function scheduleGoldenCardRenderKoolkid(data) {
    pendingGoldenCardRender = data || pendingGoldenCardRender || {};
    const elapsed = Date.now() - Number(lastGoldenCardRenderAt || 0);
    if (elapsed >= GOLDEN_RENDER_THROTTLE_MS) {
      flushGoldenCardRenderKoolkid();
      return;
    }
    if (!goldenCardRenderTimer) {
      goldenCardRenderTimer = setTimeout(flushGoldenCardRenderKoolkid, Math.max(50, GOLDEN_RENDER_THROTTLE_MS - elapsed));
      const app = App();
      if (app && typeof app.registerFrontendTimeout === "function") app.registerFrontendTimeout("koolkid_golden_card_render", goldenCardRenderTimer);
    }
  }

  function bindSocketListeners() {
    try {
      const app = App();
      const currentSocket = (typeof socket !== "undefined") ? socket : null;
      const hasAppBinder = app && typeof app.bindSocketListener === "function";
      if (!hasAppBinder) return;
      if (state.lastSocket === currentSocket && state.socketBound) return;
      const bind = (eventName, handler) => {
        return app.bindSocketListener(PROFILE, eventName, handler);
      };
      state.lastSocket = currentSocket;
      state.socketBound = true;

      bind("digit_analysis", (data) => {
        if (!isActive()) return;
        maybeRunKoolkidOver6ScanMartingale(data || {}).catch(() => {});
        scheduleDigitAnalysisRenderKoolkid(data || {});
        maybeRunG1AutoKoolkid(data || {}).catch(() => {});
        maybeRunKoolkidBalancedRecoveryThinking();
      });

      bind("golden_card_update", (data) => {
        if (!isActive()) return;
        scheduleGoldenCardRenderKoolkid(data || {});
      });

      bind("auto_mode_update", (modes) => {
        if (!isActive()) return;
        updateModeButtonsFromPayload(modes || {});
      });

      bind("tick", (tick) => {
        if (!isActive()) return;
        if (tick) maybeRunKoolkidOver6ScanMartingale(tick || {}).catch(() => {});
        onKoolkidSingleMartingaleTick();
        maybeRunKoolkidBalancedRecoveryThinking();
      });

      bind("trade_placed", (trade) => {
        if (!isActive()) return;
        trackGoldenCardReinvestPlacementKoolkid(trade || {});
        rememberKoolkidOver6ScanTrade(trade || {});
        rememberKoolkidSingleMartingaleTrade(trade || {});
        rememberKoolkidBalancedRecoveryTrade(trade || {});
        rememberKoolkidPairRecoveryTrade(trade || {});
      });

      bind("trade_result", (trade) => {
        if (!isActive()) return;
        handleKoolkidLiveDigitTradeResult(trade || {});
        handleProfileReinvestResultKoolkid(trade || {});
        handleGoldenCardReinvestResultKoolkid(trade || {});
        updateKoolkidOver6ScanFromResult(trade || {});
        updateKoolkidSingleMartingaleFromResult(trade || {});
        updateKoolkidBalancedRecoveryFromResult(trade || {});
        updateKoolkidPairRecoveryFromResult(trade || {});
      });

      if (app && typeof app.logSocketListenerCounts === "function") app.logSocketListenerCounts("koolkid_profile_init");
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
        renderProfileReinvestControlsKoolkid();
        syncProfileReinvestAutoStakeKoolkid();
        renderGoldenCardReinvestControlsKoolkid();
      }
      if (target && target.id === "barrier") {
        renderPredictionSummaryKoolkid();
      }
    });

  }

  async function onMount() {
    try { App().ensureDigitClickPatchSoon && App().ensureDigitClickPatchSoon(); } catch (e) {}
    try { App().applyDigitSelectionUI && App().applyDigitSelectionUI(); } catch (e) {}
    bindSocketListeners();
    bindWindowEvents();
    updateDual2xUIKoolkid();
    relocateKoolkidTradeHistoryForLifetime();
    renderProfileReinvestControlsKoolkid();
    updateKoolkidOver6ScanMartingalePanel();
    updateKoolkidSingleMartingalePanel();
    updateKoolkidBalancedRecoveryPanel();
    updateKoolkidPairRecoveryPanel();
    renderG1AutoUiKoolkid();
    renderDual2xAnalysisKoolkid();
    renderOver3AnalysisKoolkid();
    renderGoldenCardKoolkid();
    renderPredictionSummaryKoolkid();
    renderOver6AnalyzerKoolkid();
    renderKid2vixKoolkid();
    currentTurboModeKoolkid();
    renderTurboToggleKoolkid();
    setTimeout(syncSelectedDigitsToServer, 200);
  }

  async function onActivate() {
    try { App().applyDigitSelectionUI && App().applyDigitSelectionUI(); } catch (e) {}
    bindSocketListeners();
    updateDual2xUIKoolkid();
    relocateKoolkidTradeHistoryForLifetime();
    renderProfileReinvestControlsKoolkid();
    updateKoolkidOver6ScanMartingalePanel();
    updateKoolkidSingleMartingalePanel();
    updateKoolkidBalancedRecoveryPanel();
    updateKoolkidPairRecoveryPanel();
    renderG1AutoUiKoolkid();
    renderDual2xAnalysisKoolkid();
    renderOver3AnalysisKoolkid();
    renderGoldenCardKoolkid();
    renderPredictionSummaryKoolkid();
    renderOver6AnalyzerKoolkid();
    renderKid2vixKoolkid();
    currentTurboModeKoolkid();
    renderTurboToggleKoolkid();
    setTimeout(syncSelectedDigitsToServer, 150);
  }

  async function afterLoadProfileUI() {
    try { App().applyDigitSelectionUI && App().applyDigitSelectionUI(); } catch (e) {}
    bindSocketListeners();
    updateDual2xUIKoolkid();
    relocateKoolkidTradeHistoryForLifetime();
    renderProfileReinvestControlsKoolkid();
    updateKoolkidOver6ScanMartingalePanel();
    updateKoolkidSingleMartingalePanel();
    updateKoolkidBalancedRecoveryPanel();
    updateKoolkidPairRecoveryPanel();
    renderG1AutoUiKoolkid();
    renderDual2xAnalysisKoolkid();
    renderOver3AnalysisKoolkid();
    renderGoldenCardKoolkid();
    renderPredictionSummaryKoolkid();
    renderOver6AnalyzerKoolkid();
    renderKid2vixKoolkid();
    currentTurboModeKoolkid();
    renderTurboToggleKoolkid();
  }

  async function onDeactivate() {
    const app = App();
    const mgState = getKoolkidSingleMartingaleState();
    if (mgState.restartTimer) {
      clearTimeout(mgState.restartTimer);
      mgState.restartTimer = null;
    }
    if (digitAnalysisRenderTimer) {
      if (!(app && typeof app.clearFrontendTimeout === "function" && app.clearFrontendTimeout("koolkid_digit_analysis_render"))) {
        clearTimeout(digitAnalysisRenderTimer);
      }
      digitAnalysisRenderTimer = null;
    }
    if (goldenCardRenderTimer) {
      if (!(app && typeof app.clearFrontendTimeout === "function" && app.clearFrontendTimeout("koolkid_golden_card_render"))) {
        clearTimeout(goldenCardRenderTimer);
      }
      goldenCardRenderTimer = null;
    }
    pendingDigitAnalysisRender = null;
    pendingGoldenCardRender = null;
    mgState.running = false;
    mgState.inProgress = false;
    mgState.waitingForTicks = false;
    mgState.waitTicksRemaining = 0;
    stopKoolkidOver6ScanMartingale();
    state.socketBound = false;
    state.lastSocket = null;
    try { stopFallbackBootstrap(); } catch (e) {}
  }

  window.toggleTurboKoolkid = function () {
    const next = !currentTurboModeKoolkid();
    state.turboMode = next;
    persistTurboModeKoolkid(next);
    renderTurboToggleKoolkid();
  };

  window.toggleProfileReinvestKoolkid = function () {
    state.profileReinvestOn = !state.profileReinvestOn;
    resetProfileReinvestKoolkid();
    if (state.profileReinvestOn) state.profileReinvestBaseStake = Number(getRawStakeValueKoolkid().toFixed(2));
    renderProfileReinvestControlsKoolkid();
    syncProfileReinvestAutoStakeKoolkid();
    safeToast(`Koolkid Reinvest Profits: ${state.profileReinvestOn ? "ON" : "OFF"}`, state.profileReinvestOn ? "success" : "error");
  };

  window.setProfileReinvestPctKoolkid = function (pct) {
    const value = Number(pct);
    if (![25, 50, 75, 100].includes(value)) return;
    state.profileReinvestPct = value;
    resetProfileReinvestKoolkid();
    if (state.profileReinvestOn) state.profileReinvestBaseStake = Number(getRawStakeValueKoolkid().toFixed(2));
    renderProfileReinvestControlsKoolkid();
    syncProfileReinvestAutoStakeKoolkid();
  };

  window.toggleOver6AnalyzerEntryKoolkid = function (enabled) {
    state.over6Analyzer.useForEntry = !!enabled;
    state.over6Analyzer.lastSignature = "";
    renderOver6AnalyzerKoolkid();
  };

  const previousProfileReinvestStakeHookKoolkid = window.getProfileReinvestStake;
  window.getProfileReinvestStake = function (profile, stake) {
    if (String(profile || "").toUpperCase() === PROFILE) return getProfileReinvestStakeKoolkid(stake);
    if (typeof previousProfileReinvestStakeHookKoolkid === "function") return previousProfileReinvestStakeHookKoolkid(profile, stake);
    return stake;
  };

  window.setKoolkidSingleMartingaleAction = setKoolkidSingleMartingaleAction;
  window.toggleKoolkidSingleMartingale = toggleKoolkidSingleMartingale;
  window.updateKoolkidSingleMartingalePanel = updateKoolkidSingleMartingalePanel;
  window.placeKoolkidSingleMartingaleTrade = placeKoolkidSingleMartingaleTrade;
  window.quickStopKoolkidSingleMartingale = quickStopKoolkidSingleMartingale;
  window.openKoolkidMartingaleCalculator = openKoolkidMartingaleCalculator;
  window.closeKoolkidMartingaleCalculator = closeKoolkidMartingaleCalculator;
  window.updateKoolkidMartingaleCalculator = updateKoolkidMartingaleCalculator;
  window.startOver3Under6PairMartingaleKoolkid = startOver3Under6PairMartingaleKoolkid;
  window.stopOver3Under6PairMartingaleKoolkid = stopOver3Under6PairMartingaleKoolkid;
  window.resetOver3Under6PairMartingaleKoolkid = function () {
    const pair = getOver3Under6PairStateKoolkid();
    pair.running = false;
    pair.enabled = false;
    resetOver3Under6PairStateKoolkid("Ready");
  };
  window.startKoolkidOver6ScanMartingale = startKoolkidOver6ScanMartingale;
  window.stopKoolkidOver6ScanMartingale = stopKoolkidOver6ScanMartingale;
  window.updateKoolkidOver6ScanMartingalePanel = updateKoolkidOver6ScanMartingalePanel;
  window.toggleKoolkidBalancedRecovery = toggleKoolkidBalancedRecovery;
  window.updateKoolkidBalancedRecoveryPanel = updateKoolkidBalancedRecoveryPanel;
  window.startKoolkidBalancedRecovery = startKoolkidBalancedRecovery;
  window.stopKoolkidBalancedRecovery = stopKoolkidBalancedRecovery;
  window.resetKoolkidBalancedRecoveryCycle = resetKoolkidBalancedRecoveryCycle;
  window.toggleKoolkidBalancedRecoveryThinkingLogic = function (enabled) {
    const st = getKoolkidBalancedRecoveryState();
    const settings = readKoolkidBalancedRecoverySettings();
    st.thinkingLogic = !!enabled;
    st.thinkingScanning = false;
    st.thinkingOpportunityActive = false;
    st.thinkingLastSignalKey = "";
    st.status = st.thinkingLogic && isKoolkidBalancedRecoveryThinkingTrade(settings)
      ? "Thinking Logic armed. Press START to scan."
      : "Ready";
    updateKoolkidBalancedRecoveryPanel();
    safeToast(`Thinking Logic: ${st.thinkingLogic ? "ON" : "OFF"}`, st.thinkingLogic ? "success" : "error");
  };
  window.openKoolkidPairRecoveryPopup = openKoolkidPairRecoveryPopup;
  window.closeKoolkidPairRecoveryPopup = closeKoolkidPairRecoveryPopup;
  window.updateKoolkidPairRecoveryPanel = updateKoolkidPairRecoveryPanel;
  window.startKoolkidPairRecovery = startKoolkidPairRecovery;
  window.stopKoolkidPairRecovery = stopKoolkidPairRecovery;

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
    applyGoldenCardPcScrollKoolkid();
  };

  window.hideGoldenCardPopupKoolkid = function () {
    state.goldenCardPopupDismissedAt = Date.now();
    hideCenteredPopupKoolkid("goldenCardPopupKoolkid");
  };

  window.handleGoldenCardBtnKoolkid = async function () {
    const current = state.goldenCard || {};
    if (current.running) {
      window.openGoldenCardPopupKoolkid();
      return;
    }
    state.goldenCardAutoOn = false;
    state.goldenCardAutoLastSignalKey = "";
    state.goldenCardAutoWaitingReset = false;
    syncGoldenCardAutoUiKoolkid();
    const options = readGoldenCardOptionsKoolkid();
    renderGoldenCardKoolkid(Object.assign({}, current, {
      running: true,
      completed: false,
      status: "Starting live Golden Card scan across 10 markets...",
      filter_mode: options.filter_mode,
      add_jump_pairs: options.add_jump_pairs,
    }));
    window.openGoldenCardPopupKoolkid();
    await nextPaintFrame();
    let r = null;
    try {
      r = await postJSON("/start_golden_card_koolkid", options);
    } catch (e) {
      r = { data: { status: "error", message: "Golden Card scan failed to reach the server" } };
    }
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
    state.goldenCardAutoLastSignalKey = "";
    state.goldenCardAutoWaitingReset = false;
    const r = await postJSON("/stop_golden_card_koolkid", {});
    if (r.data && r.data.golden_card_data) renderGoldenCardKoolkid(r.data.golden_card_data);
    window.hideGoldenCardPopupKoolkid();
    safeToast("Golden Card turned off", "info");
  };

  window.updateGoldenCardSettingsKoolkid = async function () {
    const current = state.goldenCard || {};
    const options = readGoldenCardOptionsKoolkid();
    state.goldenCard = Object.assign({}, current, options);
    renderGoldenCardKoolkid(state.goldenCard);
    if (!current.running || state.goldenCardSettingsBusy) return;
    state.goldenCardSettingsBusy = true;
    try {
      const r = await postJSON("/start_golden_card_koolkid", options);
      if (r && r.data && r.data.status === "success" && r.data.golden_card_data) {
        renderGoldenCardKoolkid(r.data.golden_card_data);
      } else if (r && r.data && r.data.golden_card_data) {
        renderGoldenCardKoolkid(r.data.golden_card_data);
      }
    } catch (e) {
      safeToast("Golden Card settings failed to update", "error");
    } finally {
      state.goldenCardSettingsBusy = false;
    }
  };

  window.toggleGoldenCardAutoTraderKoolkid = function () {
    const dismissedAt = Number(state.goldenCardPopupDismissedAt || 0);
    if (dismissedAt > 0 && (Date.now() - dismissedAt) < 500) {
      const autoNode = document.getElementById("goldenCardAutoTraderKoolkid");
      if (autoNode) autoNode.checked = !!state.goldenCardAutoOn;
      syncGoldenCardAutoUiKoolkid();
      return;
    }
    state.goldenCardAutoOn = !state.goldenCardAutoOn;
    if (!state.goldenCardAutoOn) {
      state.goldenCardAutoLastSignalKey = "";
      state.goldenCardAutoWaitingReset = false;
    }
    syncGoldenCardAutoUiKoolkid();
    renderGoldenCardKoolkid(state.goldenCard || {});
    safeToast(`Golden Card Auto Trader: ${state.goldenCardAutoOn ? "ON" : "OFF"}`, state.goldenCardAutoOn ? "success" : "error");
  };

  window.toggleGoldenCardReinvestProfitsKoolkid = function () {
    state.goldenCardReinvestProfitsOn = !state.goldenCardReinvestProfitsOn;
    resetGoldenCardReinvestCycleKoolkid();
    if (state.goldenCardReinvestProfitsOn) {
      const base = Number(getStakeValueKoolkid());
      if (Number.isFinite(base) && base > 0) {
        state.goldenCardReinvestBaseStake = Number(base.toFixed(2));
        state.goldenCardReinvestCycleStake = Number(base.toFixed(2));
      }
    }
    renderGoldenCardReinvestControlsKoolkid();
    safeToast(`Golden Card Reinvest Profits: ${state.goldenCardReinvestProfitsOn ? "ON" : "OFF"}`, state.goldenCardReinvestProfitsOn ? "success" : "info");
  };

  window.toggleGoldenCardPcScrollKoolkid = function () {
    applyGoldenCardPcScrollKoolkid();
    safeToast("Golden Card scroll is always ON.", "info");
  };

  window.setGoldenCardReinvestPctKoolkid = function (pct) {
    const value = Number(pct);
    if (![25, 50, 75, 100].includes(value)) return;
    state.goldenCardReinvestProfitPct = value;
    resetGoldenCardReinvestCycleKoolkid();
    if (state.goldenCardReinvestProfitsOn) {
      const base = Number(getStakeValueKoolkid());
      if (Number.isFinite(base) && base > 0) {
        state.goldenCardReinvestBaseStake = Number(base.toFixed(2));
        state.goldenCardReinvestCycleStake = Number(base.toFixed(2));
      }
    }
    renderGoldenCardReinvestControlsKoolkid();
  };

  window.placeGoldenCardTradeKoolkid = async function (symbol) {
    if (state.goldenCardTradeBusy) return false;
    const market = String(symbol || "").toUpperCase().trim();
    if (!market) {
      safeToast("Golden Card market missing", "error");
      return false;
    }
    const current = state.goldenCard || {};
    const row = Array.isArray(current.results)
      ? current.results.find((item) => String(item.symbol || "").toUpperCase() === market)
      : null;
    if (!row || !(row.ready_confirmed || row.entry_ready)) {
      safeToast((row && row.ready_reason) || "Golden Card needs 2 clean checks before entry", "info");
      return false;
    }
    if (row && row.loss_guard_blocked) {
      safeToast(`Golden Card skipped on ${market}: ${row.loss_guard_reason || "losing digits are too hot"}`, "error");
      return false;
    }
    if (row && row.conflict_blocked) {
      safeToast("Golden Card skipped: another KOOLKID trade is still active", "info");
      return false;
    }
    if (row && row.market_quality_ok === false) {
      safeToast(`Golden Card skipped: confidence must stay above ${Number(row.confidence_threshold || 70).toFixed(0)}%`, "info");
      return false;
    }
    state.goldenCardTradeBusy = true;
    try {
      const stake = getGoldenCardReinvestAdjustedStakeKoolkid(getStakeValueKoolkid());
      const duration = Number(document.getElementById("durationTicks")?.value || 1) || 1;
      const tradeType = String((row && row.recommended_type) || "OVER").toUpperCase();
      const rawBarrier = row && row.recommended_barrier;
      const parsedBarrier = rawBarrier === undefined || rawBarrier === null || rawBarrier === "" ? 1 : Number(rawBarrier);
      const tradeBarrier = Number.isFinite(parsedBarrier) ? Math.max(0, Math.min(9, parsedBarrier)) : 1;
      const tradeLabel = String((row && row.recommended_label) || `${tradeType} ${tradeBarrier}`);
      const payload = {
        stake,
        amount: stake,
        type: tradeType,
        barrier: tradeBarrier,
        symbol: market,
        duration,
        mode: "golden_card",
      };
      const r = await sendFastManualTradeKoolkid(payload, {
        turbo: true,
        queue: false,
        useSocket: true,
        fireAndForget: false,
      });
      const ok = !!(r && r.data && r.data.status === "success");
      if (ok) {
        setGoldenCardReinvestCycleStakeFromTradeKoolkid(stake);
        renderGoldenCardReinvestControlsKoolkid();
        safeToast(`Golden Card sent ${tradeLabel} on ${market}`, "success");
      }
      else safeToast((r && r.data && r.data.message) || `Golden Card trade failed on ${market}`, "error");
      return ok;
    } catch (e) {
      safeToast(`Golden Card trade failed on ${market}`, "error");
      return false;
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
      if (r.data.barrier_analysis !== undefined) {
        if (!state.barrierAnalysis || typeof state.barrierAnalysis !== "object") state.barrierAnalysis = {};
        state.barrierAnalysis.running = !!r.data.barrier_analysis;
        if (r.data.selected) state.barrierAnalysis.selected = r.data.selected;
        renderBarrierAnalysis(state.barrierAnalysis);
      }
      updateModeButtonsFromPayload({ kidgx: state.autoModes.kidgx });
      const monthlyMsg = isMonthlyKidGxReplacementUserKoolkid() && r.data.kidgx_auto ? " • Barrier Analysis linked" : "";
      safeToast(`⚡kidGx ${r.data.kidgx_auto ? "ON" : "OFF"}${monthlyMsg}`, r.data.kidgx_auto ? "success" : "error");
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

  function renderProfitCalculatorResultsKoolkid(rows, status) {
    const node = document.getElementById("profitCalculatorResultsKoolkid");
    if (!node) return;
    if (!rows || !rows.length) {
      node.textContent = status || "No quote available.";
      return;
    }
    node.innerHTML = rows.map((row) => {
      if (row.error) {
        return `<div style="padding:8px; border:1px solid #334155; border-radius:10px; margin-top:6px;"><strong>${row.label}</strong><br><span style="color:#fca5a5;">${row.error}</span></div>`;
      }
      return `<div style="padding:8px; border:1px solid #334155; border-radius:10px; margin-top:6px;"><strong>${row.label}</strong><br>Stake $${Number(row.stake || 0).toFixed(2)} - Profit $${Number(row.profit || 0).toFixed(2)} - Return $${Number(row.payout || 0).toFixed(2)}</div>`;
    }).join("");
  }

  window.openProfitCalculatorKoolkid = function () {
    const popup = document.getElementById("profitCalculatorPopupKoolkid");
    const stake = document.getElementById("profitCalculatorStakeKoolkid");
    const digit = document.getElementById("profitCalculatorDigitKoolkid");
    if (stake) stake.value = String(getRawStakeValueKoolkid ? getRawStakeValueKoolkid() : 1);
    if (digit) digit.value = String(Math.max(0, Math.min(9, parseInt((document.getElementById("barrier") || {}).value || "5", 10) || 5)));
    renderProfitCalculatorResultsKoolkid([], "Choose a digit to preview Over/Under profit for the current market.");
    if (popup) popup.style.display = "flex";
  };

  window.closeProfitCalculatorKoolkid = function () {
    const popup = document.getElementById("profitCalculatorPopupKoolkid");
    if (popup) popup.style.display = "none";
  };

  window.runProfitCalculatorKoolkid = async function () {
    const stake = Math.max(0.35, Number((document.getElementById("profitCalculatorStakeKoolkid") || {}).value || 1) || 1);
    const digit = Math.max(0, Math.min(9, parseInt((document.getElementById("profitCalculatorDigitKoolkid") || {}).value || "5", 10) || 5));
    const symbol = typeof window.getConfirmedMarketSymbol === "function" ? window.getConfirmedMarketSymbol() : ((document.getElementById("symbol") || {}).value || "");
    renderProfitCalculatorResultsKoolkid([], "Checking live proposal profit...");
    const r = await postJSON("/profit_calculator_quote", {
      profile: "KOOLKID",
      symbol,
      stake,
      digit,
      duration: getDurationTicksKoolkid(),
      duration_unit: "t",
    });
    renderProfitCalculatorResultsKoolkid((r.data && r.data.quotes) || [], (r.data && r.data.message) || "Quote unavailable.");
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
    window.registerProfileModule(PROFILE, { onMount, afterLoadProfileUI, onActivate, onDeactivate });
  } else {
    window.ProfileModules = window.ProfileModules || {};
    window.ProfileModules[PROFILE] = { onMount, afterLoadProfileUI, onActivate, onDeactivate };
  }

  // Fallback bootstrap for index versions without Phase 2 hooks
  const FALLBACK_BOOTSTRAP_INTERVAL_LABEL = "koolkid_fallback_bootstrap";
  let fallbackBootstrapTimer = null;

  function stopFallbackBootstrap() {
    const app = App();
    const clearedTracked = !!(app && typeof app.clearFrontendInterval === "function" && app.clearFrontendInterval(FALLBACK_BOOTSTRAP_INTERVAL_LABEL));
    if (fallbackBootstrapTimer && !clearedTracked) {
      clearInterval(fallbackBootstrapTimer);
    }
    if (fallbackBootstrapTimer || clearedTracked) fallbackBootstrapTimer = null;
  }

  function fallbackBootstrap() {
    try {
      if (typeof window.registerProfileModule === "function") {
        stopFallbackBootstrap();
        const app = App();
        if (app && typeof app.logActiveIntervalCount === "function") app.logActiveIntervalCount("koolkid_fallback_module_loaded");
        return;
      }
      if (typeof window.registerProfileModule !== "function") {
        if (typeof onMount === "function") onMount();
        if (typeof afterLoadProfileUI === "function") afterLoadProfileUI();
        if (isActive() && typeof onActivate === "function") onActivate();
      }
    } catch (e) {}
  }
  if (typeof window.registerProfileModule !== "function") {
    fallbackBootstrapTimer = setInterval(fallbackBootstrap, 1200);
    const app = App();
    if (app && typeof app.registerFrontendInterval === "function") app.registerFrontendInterval(FALLBACK_BOOTSTRAP_INTERVAL_LABEL, fallbackBootstrapTimer);
    setTimeout(fallbackBootstrap, 200);
  } else {
    stopFallbackBootstrap();
    const app = App();
    if (app && typeof app.logActiveIntervalCount === "function") app.logActiveIntervalCount("koolkid_fallback_not_needed");
  }

})();
