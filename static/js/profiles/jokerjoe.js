(function () {
  const PROFILE = "JOKERJOE";
const FALLBACK_BOOTSTRAP_INTERVAL_LABEL = "jokerjoe_fallback_bootstrap";
const ACTIVITY_POLL_INTERVAL_LABEL = "jokerjoe_activity_poll";
const FAST_INTERVAL_MS_NORMAL = 400; // 0.4s as requested
const FAST_INTERVAL_MS_TURBO = 120;  // faster Turbo lane for JOKERJOE
const FAST_MAX_BUY_QUEUE = 12;       // safety limit
const BLACKCARD_RENDER_THROTTLE_MS = 300;
const state = { lastSocket: null, socketBound: false, autoModes: {}, turboMode: loadTurboModeJokerjoe(), kidgxBarrier: 5, matchesAnalysisOn: false, matchesLastKey: "", matchesObserverBound: false, matchSniperOn: false, matchSniperCooldownUntil: 0, matchSniperActiveDigit: null, matchSniperConsumed: false, matchSniperBusy: false, matchesSnapshot: null, matchesSorted: [], matchSniper5xOn: false, matchSniper5xCooldownUntil: 0, matchSniper5xBusy: false, matchSniper5xLastTopKey: "", matchSniper5xRotationSets: null, matchSniper5xRotationIndex: 0, matchSniper5xCurrentDigits: [], aiAutoModeChoice: "golden_digits", aiAutoLowestTradeCountChoice: 5, aiAutoLowestLocalOn: false, aiAutoModalOpen: false, aiLowestLastTickCount: 0, aiLowestTouches: {}, aiLowestArmed: null, aiLowestBatchActive: false, aiLowestBatchPending: 0, aiLowestBatchBarrier: null, aiLowestBatchProfit: 0, aiLowestCooldownUntil: 0, aiLowestSubmitting: false, aiLowestRecoveryDeficit: 0, aiLowestRecoveryOnly: false, randomMatchesDiffersOn: false, randomMatchesDiffersMode: "DIFFERS", randomMatchesDiffersModalOpen: false, randomMatchesDiffersBusy: false, randomMatchesDiffersCooldownUntil: 0, randomMatchesDiffersLastSignalKey: "", randomMatchesDiffersTickHistory: [], randomMatchesDiffersLastTickCount: 0, randomMatchesDiffersSnapshot: null, blackcard: { lastDigit: null, recentDigits: [], percentages: {}, busy: false }, insta2Busy: false };
  const fastBuyQueueJokerjoe = { items: [], running: false, lastRunAt: 0 };
  let activityPollTimerJokerjoe = null;
  let blackcardRenderTimerJokerjoe = null;
  let lastBlackcardRenderAtJokerjoe = 0;

  function App() { return window.BotApp || {}; }
  function isActive() { try { return typeof activeProfile !== "undefined" && activeProfile === PROFILE; } catch (e) { return false; } }
  function safeToast(msg, type) { try { if (typeof showToast === "function") showToast(msg, type || "info"); } catch (e) {} }

function getFastIntervalMsJokerjoe() {
  return currentTurboModeJokerjoe() ? FAST_INTERVAL_MS_TURBO : FAST_INTERVAL_MS_NORMAL;
}

function delayFastBuyMsJokerjoe(ms) {
  const waitMs = Math.max(0, Number(ms) || 0);
  if (waitMs <= 0) return Promise.resolve();
  return new Promise((resolve) => setTimeout(resolve, waitMs));
}

async function runFastBuyQueueJokerjoe() {
  if (fastBuyQueueJokerjoe.running) return;
  fastBuyQueueJokerjoe.running = true;
  try {
    while ((fastBuyQueueJokerjoe.items || []).length) {
      const item = fastBuyQueueJokerjoe.items.shift();
      if (!item || typeof item.task !== "function") continue;
      const intervalMs = getFastIntervalMsJokerjoe();
      const elapsedMs = Date.now() - Number(fastBuyQueueJokerjoe.lastRunAt || 0);
      if (fastBuyQueueJokerjoe.lastRunAt) {
        if (elapsedMs < intervalMs) await delayFastBuyMsJokerjoe(intervalMs - elapsedMs);
      }
      try {
        const result = await item.task();
        item.resolve(result);
      } catch (err) {
        item.reject(err);
      } finally {
        fastBuyQueueJokerjoe.lastRunAt = Date.now();
      }
    }
  } finally {
    fastBuyQueueJokerjoe.running = false;
  }
}

function enqueueFastBuyJokerjoe(task) {
  if (typeof task !== "function") return Promise.resolve();
  const queuedCount = Number((fastBuyQueueJokerjoe.items || []).length || 0);
  const inFlightCount = fastBuyQueueJokerjoe.running ? 1 : 0;
  if ((queuedCount + inFlightCount) >= FAST_MAX_BUY_QUEUE) {
    return Promise.reject(new Error(`Fast buy queue is full (${FAST_MAX_BUY_QUEUE})`));
  }
  return new Promise((resolve, reject) => {
    fastBuyQueueJokerjoe.items.push({ task, resolve, reject });
    runFastBuyQueueJokerjoe();
  });
}

function turboStorageKeyJokerjoe() {
  return "profileTurbo:JOKERJOE";
}

function loadTurboModeJokerjoe() {
  const app = App();
  if (app && typeof app.getProfileTurboEnabled === "function") {
    return !!app.getProfileTurboEnabled(PROFILE);
  }
  try {
    return localStorage.getItem(turboStorageKeyJokerjoe()) === "1";
  } catch (e) {
    return false;
  }
}

function persistTurboModeJokerjoe(enabled) {
  const app = App();
  if (app && typeof app.setProfileTurboEnabled === "function") {
    app.setProfileTurboEnabled(PROFILE, !!enabled);
    return;
  }
  try {
    localStorage.setItem(turboStorageKeyJokerjoe(), enabled ? "1" : "0");
  } catch (e) {}
}

function currentTurboModeJokerjoe() {
  const enabled = !!loadTurboModeJokerjoe();
  state.turboMode = enabled;
  return enabled;
}

function renderTurboToggleJokerjoe() {
  const btn = document.getElementById("turboToggleBtnJokerjoe");
  if (!btn) return;
  state.turboMode = currentTurboModeJokerjoe();
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

  function signedMoney(value, payload) {
    const num = Number(value || 0);
    try { if (typeof formatSignedCurrencyAmount === "function") return formatSignedCurrencyAmount(num, currencyPayload(payload)); } catch (e) {}
    if (!Number.isFinite(num)) return "—";
    return `${num >= 0 ? "+" : "-"}$${Math.abs(num).toFixed(2)}`;
  }

  function getEl(id) { return document.getElementById(id); }
  function setTextIfChanged(node, value) {
    if (!node) return;
    const text = String(value ?? "");
    if (node.textContent !== text) node.textContent = text;
  }
  function setHtmlIfChanged(node, value) {
    if (!node) return;
    const html = String(value ?? "");
    if (node.innerHTML !== html) node.innerHTML = html;
  }
  function setStyleIfChanged(node, prop, value) {
    if (!node || !prop) return;
    const text = String(value ?? "");
    if (node.style[prop] !== text) node.style[prop] = text;
  }

  function getBlackcardPopupJokerjoe() { return getEl("blackcardPopupJokerjoe"); }

function getBlackcardDigitButtonsJokerjoe() {
  return Array.from(document.querySelectorAll("[data-blackcard-digit-jokerjoe]"));
}

function normalizeBlackcardPercentagesJokerjoe(raw) {
  const out = {};
  for (let i = 0; i <= 9; i++) out[i] = 0;
  if (!raw || typeof raw !== "object") return out;
  Object.keys(raw).forEach((key) => {
    const digit = Number(key);
    const pct = Number(raw[key]);
    if (Number.isInteger(digit) && digit >= 0 && digit <= 9 && Number.isFinite(pct)) {
      out[digit] = pct;
    }
  });
  return out;
}

function buildBlackcardFallbackPercentagesJokerjoe() {
  const history = Array.isArray(state.blackcard.recentDigits) ? state.blackcard.recentDigits.slice(-20) : [];
  const out = {};
  for (let i = 0; i <= 9; i++) out[i] = 0;
  if (!history.length) return out;
  history.forEach((digit) => {
    const safeDigit = Number(digit);
    if (Number.isInteger(safeDigit) && safeDigit >= 0 && safeDigit <= 9) out[safeDigit] += 1;
  });
  for (let i = 0; i <= 9; i++) out[i] = (out[i] / history.length) * 100;
  return out;
}

  function positionBlackcardPopupJokerjoe() {
    const popup = getBlackcardPopupJokerjoe();
    if (!popup) return;
    popup.style.visibility = "hidden";
    popup.style.display = "block";
    const width = Math.max(popup.offsetWidth || 340, 300);
    const height = Math.max(popup.offsetHeight || 320, 280);
    const left = Math.max(10, Math.round((window.innerWidth - width) / 2));
    const top = Math.max(20, Math.round((window.innerHeight - height) / 2));
    popup.style.left = `${left}px`;
    popup.style.top = `${top}px`;
    popup.style.visibility = "visible";
  }

  function renderBlackcardJokerjoe() {
    lastBlackcardRenderAtJokerjoe = Date.now();
    const popup = getBlackcardPopupJokerjoe();
    const liveDigitEl = getEl("blackcardLiveDigitJokerjoe");
    const statusEl = getEl("blackcardStatusJokerjoe");
    const recentEl = getEl("blackcardRecentDigitsJokerjoe");
    const lastDigit = Number(state.blackcard.lastDigit);
    const hasDigit = Number.isInteger(lastDigit) && lastDigit >= 0 && lastDigit <= 9;
    const recentDigits = Array.isArray(state.blackcard.recentDigits) ? state.blackcard.recentDigits.slice(-12) : [];
    const percentages = Object.keys(state.blackcard.percentages || {}).length
      ? state.blackcard.percentages
      : buildBlackcardFallbackPercentagesJokerjoe();
    const busy = !!state.blackcard.busy;

    if (liveDigitEl) {
      setTextIfChanged(liveDigitEl, hasDigit ? String(lastDigit) : "-");
      setStyleIfChanged(liveDigitEl, "borderColor", hasDigit ? "#38bdf8" : "#334155");
      setStyleIfChanged(liveDigitEl, "boxShadow", hasDigit ? "0 0 0 1px rgba(56,189,248,0.35), 0 10px 24px rgba(15,23,42,0.45)" : "0 10px 24px rgba(15,23,42,0.45)");
      setStyleIfChanged(liveDigitEl, "color", hasDigit ? "#67e8f9" : "#f8fafc");
    }
    if (statusEl) {
      if (busy) setTextIfChanged(statusEl, "Sending DIFFERS trade...");
      else if (hasDigit) setTextIfChanged(statusEl, `Last digit ${lastDigit} just played. Tap any digit to send DIFFERS instantly.`);
      else setTextIfChanged(statusEl, "Waiting for market ticks...");
      setStyleIfChanged(statusEl, "color", busy ? "#38bdf8" : "#cbd5e1");
    }
    if (recentEl) {
      setTextIfChanged(recentEl, recentDigits.length ? `Recent digits: ${recentDigits.join(" ")}` : "Recent digits: warming up...");
    }
    getBlackcardDigitButtonsJokerjoe().forEach((btn) => {
      const digit = Number(btn.getAttribute("data-blackcard-digit-jokerjoe"));
      const isLast = hasDigit && digit === lastDigit;
      const pct = Number((percentages || {})[digit]);
      btn.disabled = busy;
      setStyleIfChanged(btn, "cursor", busy ? "wait" : "pointer");
      setStyleIfChanged(btn, "opacity", busy ? "0.75" : "1");
      setStyleIfChanged(btn, "height", "60px");
      setStyleIfChanged(btn, "touchAction", "manipulation");
      setStyleIfChanged(btn, "background", isLast ? "linear-gradient(135deg,#0f766e,#06b6d4)" : "#111827");
      setStyleIfChanged(btn, "borderColor", isLast ? "#67e8f9" : "#334155");
      setStyleIfChanged(btn, "boxShadow", isLast ? "0 0 0 1px rgba(103,232,249,0.4), 0 10px 18px rgba(6,182,212,0.18)" : "none");
      setHtmlIfChanged(btn, `<span style="display:block; font-size:18px; line-height:1; font-weight:800;">${digit}</span><span style="display:block; font-size:11px; line-height:1.2; margin-top:4px; color:${isLast ? "#e0fbff" : "#94a3b8"};">${Number.isFinite(pct) ? pct.toFixed(1) : "0.0"}%</span>`);
    });
    if (popup && popup.style.display === "block") positionBlackcardPopupJokerjoe();
  }

  function scheduleBlackcardRenderJokerjoe() {
    const elapsed = Date.now() - Number(lastBlackcardRenderAtJokerjoe || 0);
    if (elapsed >= BLACKCARD_RENDER_THROTTLE_MS) {
      if (blackcardRenderTimerJokerjoe) {
        clearTimeout(blackcardRenderTimerJokerjoe);
        blackcardRenderTimerJokerjoe = null;
      }
      renderBlackcardJokerjoe();
      return;
    }
    if (!blackcardRenderTimerJokerjoe) {
      blackcardRenderTimerJokerjoe = setTimeout(() => {
        blackcardRenderTimerJokerjoe = null;
        renderBlackcardJokerjoe();
      }, Math.max(40, BLACKCARD_RENDER_THROTTLE_MS - elapsed));
    }
  }

  function trackBlackcardTickJokerjoe(data) {
    const digit = Number((data && data.digit) ?? (data && data.last_digit));
    if (!Number.isInteger(digit) || digit < 0 || digit > 9) return;
    state.blackcard.lastDigit = digit;
    const next = Array.isArray(state.blackcard.recentDigits) ? state.blackcard.recentDigits.slice() : [];
    next.push(digit);
    while (next.length > 12) next.shift();
    state.blackcard.recentDigits = next;
    scheduleBlackcardRenderJokerjoe();
  }

  function bindBlackcardDigitHandlersJokerjoe() {
    getBlackcardDigitButtonsJokerjoe().forEach((btn) => {
      if (btn.dataset.blackcardBound === "1") return;
      btn.dataset.blackcardBound = "1";
      btn.addEventListener("pointerdown", (event) => {
        event.preventDefault();
        const digit = Number(btn.getAttribute("data-blackcard-digit-jokerjoe"));
        window.sendBlackcardDiffersJokerjoe(digit, event);
      });
      btn.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        const digit = Number(btn.getAttribute("data-blackcard-digit-jokerjoe"));
        window.sendBlackcardDiffersJokerjoe(digit, event);
      });
      btn.addEventListener("click", (event) => {
        event.preventDefault();
      });
    });
  }

  function setText(id, value) {
    const el = getEl(id);
    if (el) el.innerText = value;
  }

  function shuffleDigitsJokerjoe() {
    const digits = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9];
    for (let i = digits.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      const tmp = digits[i];
      digits[i] = digits[j];
      digits[j] = tmp;
    }
    return digits;
  }

  function ensureMatchSniper5xRotationJokerjoe(reset) {
    if (!reset && Array.isArray(state.matchSniper5xRotationSets) && state.matchSniper5xRotationSets.length === 2) {
      return;
    }
    const shuffled = shuffleDigitsJokerjoe();
    state.matchSniper5xRotationSets = [
      shuffled.slice(0, 5).sort((a, b) => a - b),
      shuffled.slice(5, 10).sort((a, b) => a - b),
    ];
    state.matchSniper5xRotationIndex = 0;
    state.matchSniper5xCurrentDigits = [];
    state.matchSniper5xLastTopKey = "";
  }

  function activateNextMatchSniper5xDigitsJokerjoe(opts) {
    ensureMatchSniper5xRotationJokerjoe(!!(opts && opts.reset));
    const sets = Array.isArray(state.matchSniper5xRotationSets) ? state.matchSniper5xRotationSets : [];
    if (sets.length !== 2) return [];
    const idx = Number(state.matchSniper5xRotationIndex) === 1 ? 1 : 0;
    const nextDigits = Array.isArray(sets[idx]) ? sets[idx].slice() : [];
    state.matchSniper5xCurrentDigits = nextDigits;
    state.matchSniper5xRotationIndex = idx === 0 ? 1 : 0;
    return nextDigits.slice();
  }

  function getActiveMatchSniper5xDigitsJokerjoe() {
    if (!Array.isArray(state.matchSniper5xCurrentDigits) || state.matchSniper5xCurrentDigits.length !== 5) {
      return activateNextMatchSniper5xDigitsJokerjoe();
    }
    return state.matchSniper5xCurrentDigits.slice();
  }


  function normalizeAIAutoModeJokerjoe(mode) {
    return String(mode || "golden_digits").toLowerCase() === "lowest_pct" ? "lowest_pct" : "golden_digits";
  }

  function normalizeAIAutoLowestTradeCountJokerjoe(count) {
    return Number(count) === 1 ? 1 : 5;
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
    const lowestCount = normalizeAIAutoLowestTradeCountJokerjoe(state.aiAutoLowestTradeCountChoice);
    const goldenBtn = getEl("aiAutoGoldenBtnJokerjoe");
    const lowestBtn = getEl("aiAutoLowestBtnJokerjoe");
    const lowestWrap = getEl("aiAutoLowestTradeOptionsWrapJokerjoe");
    const lowest5Btn = getEl("aiAutoLowest5TradesBtnJokerjoe");
    const lowest1Btn = getEl("aiAutoLowest1TradeBtnJokerjoe");
    const status = getEl("aiAutoModeModalStatusJokerjoe");
    if (goldenBtn) goldenBtn.style.background = mode === "golden_digits" ? "#22c55e" : "#1e293b";
    if (lowestBtn) lowestBtn.style.background = mode === "lowest_pct" ? "#22c55e" : "#1e293b";
    if (lowestWrap) lowestWrap.style.display = mode === "lowest_pct" ? "grid" : "none";
    if (lowest5Btn) lowest5Btn.style.background = mode === "lowest_pct" && lowestCount === 5 ? "#22c55e" : "#1e293b";
    if (lowest1Btn) lowest1Btn.style.background = mode === "lowest_pct" && lowestCount === 1 ? "#22c55e" : "#1e293b";
    if (status) {
      if (mode === "lowest_pct") {
        const rec = state.aiLowestRecoveryOnly ? ` • Recovery ON (${money(Number(state.aiLowestRecoveryDeficit || 0))} left)` : "";
        status.innerText = `Lowest % mode (DIFFERS): touch → move-away → next tick • ${lowestCount} trade${lowestCount === 1 ? "" : "s"} • 10s cooldown${rec}`;
      } else {
        status.innerText = "Golden Digits mode: existing backend AI AUTO logic";
      }
    }
  }

  function normalizeRandomMatchesDiffersModeJokerjoe(mode) {
    return String(mode || "").toUpperCase() === "MATCHES" ? "MATCHES" : "DIFFERS";
  }

  function pushRandomMatchesDiffersTickJokerjoe(data) {
    if (!data) return;
    const tickCount = Number(data.tick_count);
    const lastDigit = Number(data.last_digit);
    if (!Number.isFinite(tickCount) || !Number.isInteger(lastDigit) || lastDigit < 0 || lastDigit > 9) return;
    if (tickCount < Number(state.randomMatchesDiffersLastTickCount || 0)) {
      state.randomMatchesDiffersTickHistory = [];
      state.randomMatchesDiffersLastTickCount = 0;
      state.randomMatchesDiffersLastSignalKey = "";
    }
    if (tickCount <= Number(state.randomMatchesDiffersLastTickCount || 0)) return;
    state.randomMatchesDiffersLastTickCount = tickCount;
    state.randomMatchesDiffersTickHistory.push({ tick: tickCount, digit: lastDigit });
    if (state.randomMatchesDiffersTickHistory.length > 160) {
      state.randomMatchesDiffersTickHistory = state.randomMatchesDiffersTickHistory.slice(-160);
    }
  }

  function buildRandomMatchesDiffersSnapshotJokerjoe() {
    const history = Array.isArray(state.randomMatchesDiffersTickHistory) ? state.randomMatchesDiffersTickHistory : [];
    const recent100 = history.slice(-100);
    if (recent100.length < 100) {
      return {
        ready: false,
        warmupCount: recent100.length,
        needed: Math.max(0, 100 - recent100.length),
      };
    }
    const totalCounts = Array(10).fill(0);
    recent100.forEach((entry) => {
      const digit = Number(entry && entry.digit);
      if (Number.isInteger(digit) && digit >= 0 && digit <= 9) totalCounts[digit] += 1;
    });
    const ranked = totalCounts.map((count, digit) => ({ digit, count })).sort((a, b) => a.count - b.count || a.digit - b.digit);
    const leastDigits = ranked.slice(0, 4).map((row) => Number(row.digit));
    const leastSet = new Set(leastDigits);
    const otherDigits = ranked.slice(4).map((row) => Number(row.digit)).sort((a, b) => a - b);
    const recent10 = recent100.slice(-10);
    const recentCounts = {};
    leastDigits.forEach((digit) => { recentCounts[digit] = 0; });
    recent10.forEach((entry) => {
      const digit = Number(entry && entry.digit);
      if (leastSet.has(digit)) recentCounts[digit] = Number(recentCounts[digit] || 0) + 1;
    });
    const quietDigits = leastDigits.filter((digit) => Number(recentCounts[digit] || 0) <= 1);
    const pass = quietDigits.length === leastDigits.length;
    const countsSummary = leastDigits.map((digit) => `${digit}:${Number(recentCounts[digit] || 0)}`).join(" ");
    const signalKey = `${leastDigits.join("")}|${leastDigits.map((digit) => Number(recentCounts[digit] || 0)).join("")}|${recent10.map((entry) => entry.digit).join("")}`;
    return {
      ready: true,
      leastDigits,
      otherDigits,
      recentCounts,
      countsSummary,
      quietDigits,
      pass,
      signalKey,
      tickCount: Number(recent100[recent100.length - 1].tick || 0),
      recent10Digits: recent10.map((entry) => Number(entry.digit)),
      rankedCounts: ranked,
    };
  }

  function mergeRandomMatchesDiffersCold4PayloadJokerjoe(data, fallbackSnapshot) {
    const cold4 = data && data.cold4_score;
    const snap = fallbackSnapshot || buildRandomMatchesDiffersSnapshotJokerjoe();
    if (!cold4 || !Array.isArray(cold4.coldest_4) || cold4.coldest_4.length !== 4) return snap;
    const leastDigits = cold4.coldest_4.map((digit) => Number(digit)).filter((digit) => Number.isInteger(digit) && digit >= 0 && digit <= 9);
    if (leastDigits.length !== 4) return snap;
    const leastSet = new Set(leastDigits);
    const otherDigits = [];
    for (let d = 0; d <= 9; d++) {
      if (!leastSet.has(d)) otherDigits.push(d);
    }
    const recent10 = (Array.isArray(state.randomMatchesDiffersTickHistory) ? state.randomMatchesDiffersTickHistory : []).slice(-10);
    const recentCounts = {};
    leastDigits.forEach((digit) => { recentCounts[digit] = 0; });
    recent10.forEach((entry) => {
      const digit = Number(entry && entry.digit);
      if (leastSet.has(digit)) recentCounts[digit] = Number(recentCounts[digit] || 0) + 1;
    });
    const quietDigits = leastDigits.filter((digit) => Number(recentCounts[digit] || 0) <= 1);
    const countsSummary = leastDigits.map((digit) => `${digit}:${Number(recentCounts[digit] || 0)}`).join(" ");
    return {
      ready: true,
      leastDigits,
      otherDigits,
      recentCounts,
      countsSummary,
      quietDigits,
      pass: quietDigits.length === leastDigits.length && !!cold4.signal_valid,
      cold4Valid: !!cold4.signal_valid,
      cold4Strength: String(cold4.signal_strength || "WEAK").toUpperCase(),
      cold4Gap: Number(cold4.score_gap || 0),
      cold4Scores: cold4.scores || {},
      signalKey: `${leastDigits.join("")}|${leastDigits.map((digit) => Number(recentCounts[digit] || 0)).join("")}|${recent10.map((entry) => entry.digit).join("")}|${Number(cold4.score_gap || 0)}`,
      tickCount: snap.tickCount,
      recent10Digits: recent10.map((entry) => Number(entry.digit)),
      rankedCounts: Array.isArray(cold4.sorted_digits) ? cold4.sorted_digits : snap.rankedCounts,
      warmupCount: snap.warmupCount,
      needed: snap.needed,
    };
  }

  function updateRandomMatchesDiffersButtonJokerjoe() {
    const btn = getEl("randomMatchesDiffersBtnJokerjoe");
    if (!btn) return;
    const mode = normalizeRandomMatchesDiffersModeJokerjoe(state.randomMatchesDiffersMode);
    const on = !!state.randomMatchesDiffersOn;
    btn.innerText = `🎲 Random Matches/Differs: ${on ? `${mode} ON` : "OFF"}`;
    btn.style.background = on ? "#22c55e" : "#1e293b";
  }

  function updateRandomMatchesDiffersStatusJokerjoe(snapshot) {
    const el = getEl("randomMatchesDiffersStatusJokerjoe");
    if (!el) return;
    const mode = normalizeRandomMatchesDiffersModeJokerjoe(state.randomMatchesDiffersMode);
    const snap = snapshot || state.randomMatchesDiffersSnapshot || buildRandomMatchesDiffersSnapshotJokerjoe();
    const now = Date.now();
    const cdMs = Math.max(0, Number(state.randomMatchesDiffersCooldownUntil || 0) - now);
    if (!state.randomMatchesDiffersOn) {
      el.style.color = "#94a3b8";
      el.innerText = "OFF • Collects the latest 100 ticks in the background • waits for the 4 least digits to stay quiet";
      return;
    }
    if (!snap || !snap.ready) {
      el.style.color = "#94a3b8";
      el.innerText = `Warm-up • ${Number((snap && snap.warmupCount) || 0)}/100 ticks collected`;
      return;
    }
    const leastText = (snap.leastDigits || []).join(", ");
    if (snap.cold4Valid === false) {
      el.style.color = "#fb7185";
      el.innerText = `Cold 4 weak • least digits ${leastText} • gap ${Number(snap.cold4Gap || 0)} < 3`;
      return;
    }
    if (state.randomMatchesDiffersBusy) {
      const targetDigits = mode === "DIFFERS" ? (snap.leastDigits || []) : (snap.otherDigits || []);
      el.style.color = "#38bdf8";
      el.innerText = `Placing ${targetDigits.length} ${mode} trades • least digits ${leastText}`;
      return;
    }
    if (cdMs > 0) {
      el.style.color = "#facc15";
      el.innerText = `Cooldown ${(cdMs / 1000).toFixed(1)}s • least digits ${leastText} • last 10 = ${snap.countsSummary}`;
      return;
    }
    if (!snap.pass) {
      el.style.color = "#fb7185";
      el.innerText = `Watching ${leastText} • last 10 = ${snap.countsSummary} • need each at 0 or 1`;
      return;
    }
    el.style.color = "#22c55e";
    el.innerText = `ARMED • least digits ${leastText} stayed quiet in the last 10 ticks • mode ${mode}`;
  }

  function updateRandomMatchesDiffersModalUiJokerjoe(snapshot) {
    const mode = normalizeRandomMatchesDiffersModeJokerjoe(state.randomMatchesDiffersMode);
    const matchesBtn = getEl("randomMatchesOptionBtnJokerjoe");
    const differsBtn = getEl("randomDiffersOptionBtnJokerjoe");
    const offBtn = getEl("randomMatchesDiffersOffBtnJokerjoe");
    const status = getEl("randomMatchesDiffersModalStatusJokerjoe");
    const snap = snapshot || state.randomMatchesDiffersSnapshot || buildRandomMatchesDiffersSnapshotJokerjoe();
    if (matchesBtn) matchesBtn.style.background = mode === "MATCHES" && state.randomMatchesDiffersOn ? "#22c55e" : "#1e293b";
    if (differsBtn) differsBtn.style.background = mode === "DIFFERS" && state.randomMatchesDiffersOn ? "#22c55e" : "#1e293b";
    if (offBtn) offBtn.style.background = state.randomMatchesDiffersOn ? "#ef4444" : "#334155";
    if (!status) return;
    if (!snap || !snap.ready) {
      status.innerText = `Collecting background ticks • ${Number((snap && snap.warmupCount) || 0)}/100 ready`;
      return;
    }
    const leastText = (snap.leastDigits || []).join(", ");
    if (snap.cold4Valid === false) {
      status.innerText = `Cold 4 weak • least digits ${leastText} • gap ${Number(snap.cold4Gap || 0)} < 3`;
      return;
    }
    status.innerText = `Least digits: ${leastText} • last 10 = ${snap.countsSummary} • ${snap.pass ? "signal ready" : "waiting for quieter 10-tick block"}`;
  }

  async function tryRandomMatchesDiffersTradeJokerjoe(snapshot) {
    const snap = snapshot || state.randomMatchesDiffersSnapshot || buildRandomMatchesDiffersSnapshotJokerjoe();
    if (!state.randomMatchesDiffersOn || state.randomMatchesDiffersBusy || !snap || !snap.ready || !snap.pass) {
      updateRandomMatchesDiffersStatusJokerjoe(snap);
      return;
    }
    const now = Date.now();
    if (Number(state.randomMatchesDiffersCooldownUntil || 0) > now) {
      updateRandomMatchesDiffersStatusJokerjoe(snap);
      return;
    }
    const mode = normalizeRandomMatchesDiffersModeJokerjoe(state.randomMatchesDiffersMode);
    const targetDigits = mode === "DIFFERS" ? (snap.leastDigits || []).slice() : (snap.otherDigits || []).slice();
    if (!targetDigits.length) {
      updateRandomMatchesDiffersStatusJokerjoe(snap);
      return;
    }
    const signalKey = `${mode}|${snap.signalKey}`;
    if (state.randomMatchesDiffersLastSignalKey === signalKey) {
      updateRandomMatchesDiffersStatusJokerjoe(snap);
      return;
    }

    state.randomMatchesDiffersBusy = true;
    updateRandomMatchesDiffersStatusJokerjoe(snap);
    try {
      const result = await placeBatchManualTradesJokerjoe(mode, targetDigits);
      if (result.placed === targetDigits.length) {
        state.randomMatchesDiffersLastSignalKey = signalKey;
        state.randomMatchesDiffersCooldownUntil = Date.now() + 10000;
        safeToast(`🎲 Random ${mode}: ${targetDigits.join(", ")} fired on the same tick`, "success");
      } else {
        safeToast(`🎲 Random ${mode}: partial batch (${result.placed}/${targetDigits.length})`, "error");
      }
    } catch (e) {
      safeToast(`🎲 Random ${mode} failed`, "error");
    } finally {
      state.randomMatchesDiffersBusy = false;
      updateRandomMatchesDiffersStatusJokerjoe(snap);
    }
  }

  function processRandomMatchesDiffersTickJokerjoe(data) {
    pushRandomMatchesDiffersTickJokerjoe(data);
    const snapshot = mergeRandomMatchesDiffersCold4PayloadJokerjoe(data, buildRandomMatchesDiffersSnapshotJokerjoe());
    state.randomMatchesDiffersSnapshot = snapshot;
    updateRandomMatchesDiffersButtonJokerjoe();
    updateRandomMatchesDiffersStatusJokerjoe(snapshot);
    updateRandomMatchesDiffersModalUiJokerjoe(snapshot);
    if (!state.randomMatchesDiffersOn) return;
    tryRandomMatchesDiffersTradeJokerjoe(snapshot);
  }

  function openRandomMatchesDiffersModalJokerjoe() {
    const modal = getEl("randomMatchesDiffersModalJokerjoe");
    if (!modal) return;
    state.randomMatchesDiffersModalOpen = true;
    modal.style.display = "flex";
    updateRandomMatchesDiffersModalUiJokerjoe();
    refreshActivityPollJokerjoe();
  }

  function closeRandomMatchesDiffersModalJokerjoe() {
    const modal = getEl("randomMatchesDiffersModalJokerjoe");
    if (!modal) return;
    state.randomMatchesDiffersModalOpen = false;
    modal.style.display = "none";
    refreshActivityPollJokerjoe();
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

  function getDurationTicksJokerjoe() {
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

  async function placeBatchManualTradesJokerjoe(contractType, digits, options) {
    const stakeEl = document.getElementById("stake");
    let stake = Number(stakeEl && stakeEl.value);
    if (!Number.isFinite(stake) || stake <= 0) stake = 1;
    const duration = getDurationTicksJokerjoe();
    const sameTick = !!(options && options.sameTick);
    const turboOn = sameTick ? true : currentTurboModeJokerjoe();

    // Send stake with each manual trade so batch actions (MatchSniper 5x) respect the UI stake.
    // Include both `stake` and `amount` for compatibility with different backend parsers.
    const base = { type: contractType, stake, amount: stake, duration, duration_unit: "t" };

    const jobs = (digits || []).map((d) => sendFastManualTradeJokerjoe(Object.assign({}, base, { barrier: Number(d) }), {
      turbo: turboOn,
      queue: sameTick ? false : !turboOn,
      useSocket: turboOn,
      fireAndForget: sameTick,
    }));
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

  function getManualStakeValueJokerjoe() {
    const stakeEl = document.getElementById("stake");
    let stake = Number(stakeEl && stakeEl.value);
    if (!Number.isFinite(stake) || stake <= 0) stake = 1;
    return stake;
  }

  async function placeExactFiveDiffersBatchJokerjoe(digit) {
    let totalPlaced = 0;
    let attempts = 0;
    const turboOn = currentTurboModeJokerjoe();
    try {
      const stake = getManualStakeValueJokerjoe();
      const duration = getDurationTicksJokerjoe();
      const r = await postJSON("/insta5", { barrier: Number(digit), stake, amount: stake, duration, duration_unit: "t", turbo: turboOn });
      totalPlaced = Math.max(0, Number(r && r.data && r.data.placed) || 0);
    } catch (e) {}

    while (totalPlaced < 5 && attempts < 20) {
      attempts += 1;
      const missing = 5 - totalPlaced;
      const stake = getManualStakeValueJokerjoe();
      const duration = getDurationTicksJokerjoe();
      const jobs = [];
      for (let i = 0; i < missing; i++) {
        jobs.push(sendFastManualTradeJokerjoe({ type: "DIFFERS", barrier: Number(digit), stake, amount: stake, duration, duration_unit: "t" }, {
          turbo: turboOn,
          queue: !turboOn,
          useSocket: turboOn,
        }));
      }
      const rs = await Promise.allSettled(jobs);
      let add = 0;
      rs.forEach((x) => {
        if (x.status === "fulfilled" && x.value && x.value.data && x.value.data.status === "success") add += 1;
      });
      totalPlaced += add;
      if (totalPlaced < 5) await new Promise((resolve) => setTimeout(resolve, turboOn ? 8 : 40));
    }
    return { placed: totalPlaced, exact: totalPlaced === 5 };
  }

  async function placeExactTwoDiffersBatchJokerjoe(digit) {
    const turboOn = currentTurboModeJokerjoe();
    const stake = getManualStakeValueJokerjoe();
    const duration = getDurationTicksJokerjoe();
    const payload = { type: "DIFFERS", barrier: Number(digit), stake, amount: stake, duration, duration_unit: "t" };
    const jobs = [0, 1].map(() => sendFastManualTradeJokerjoe(payload, {
      turbo: turboOn,
      queue: false,
      useSocket: true,
    }));
    const results = await Promise.allSettled(jobs);
    let placed = 0;
    results.forEach((r) => {
      if (r.status === "fulfilled" && r.value && r.value.data && r.value.data.status === "success") placed += 1;
    });
    return { placed, exact: placed === 2 };
  }

  async function placeOneDiffersTradeJokerjoe(digit) {
    try {
      const turboOn = currentTurboModeJokerjoe();
      const stake = getManualStakeValueJokerjoe();
      const duration = getDurationTicksJokerjoe();
      const payload = { type: "DIFFERS", barrier: Number(digit), stake, amount: stake, duration, duration_unit: "t" };
      const task = () => sendFastManualTradeJokerjoe(payload, {
        turbo: turboOn,
        queue: false,
        useSocket: turboOn,
      });
      const r = turboOn ? await task() : await enqueueFastBuyJokerjoe(task);
      const ok = !!(r && r.data && r.data.status === "success");
      return { placed: ok ? 1 : 0, exact: ok };
    } catch (e) {
      return { placed: 0, exact: false };
    }
  }

  async function fireAIAutoLowestBatchJokerjoe(digit, pct) {
    if (state.aiLowestSubmitting || state.aiLowestBatchActive) return;
    state.aiLowestSubmitting = true;
    const d = Number(digit);
    const tradeCount = normalizeAIAutoLowestTradeCountJokerjoe(state.aiAutoLowestTradeCountChoice);
    try {
      const r = tradeCount === 1
        ? await placeOneDiffersTradeJokerjoe(d)
        : await placeExactFiveDiffersBatchJokerjoe(d);

      if (r && r.exact) {
        state.aiLowestBatchActive = true;
        state.aiLowestBatchPending = tradeCount;
        state.aiLowestBatchBarrier = d;
        state.aiLowestBatchProfit = 0;
        safeToast(`🤖AI Lowest % batch: ${tradeCount}/${tradeCount} DIFFERS on ${d}${Number.isFinite(Number(pct)) ? ` (${Number(pct).toFixed(1)}%)` : ""}`, "success");
      } else {
        state.aiLowestBatchActive = false;
        state.aiLowestBatchPending = 0;
        state.aiLowestBatchBarrier = null;
        safeToast(`🤖AI Lowest % exact batch failed (${r && r.placed ? r.placed : 0}/${tradeCount})`, "error");
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

      safeToast(`🤖AI Lowest % batch done: ${signedMoney(batchProfit)}${state.aiLowestRecoveryOnly ? ` • Recovery ${money(Number(state.aiLowestRecoveryDeficit || 0))} left` : ""}`, batchProfit >= 0 ? "success" : "error");
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
    if (!state.matchSniper5xOn) {
      el.style.color = "#94a3b8";
      el.innerText = "OFF • 5 random MATCHES digits • same-tick batch • 10s cooldown";
      return;
    }
    const digits = getActiveMatchSniper5xDigitsJokerjoe();
    const digitText = digits.length ? digits.join(", ") : "building set";
    if (state.matchSniper5xBusy) {
      el.style.color = "#38bdf8";
      el.innerText = `Placing 5 MATCHES trades (${digitText})…`;
      return;
    }
    if (cdMs > 0) {
      el.style.color = "#facc15";
      el.innerText = `Cooldown: ${(cdMs/1000).toFixed(1)}s • next set ${digitText}`;
      return;
    }
    el.style.color = "#22c55e";
    el.innerText = `ARMED • Random 5 = ${digitText}`;
  }

  async function tryMatchSniper5xTradeJokerjoe(sorted) {
    if (!state.matchSniper5xOn || state.matchSniper5xBusy) return;
    const now = Date.now();
    if ((state.matchSniper5xCooldownUntil || 0) > now) return;
    if (!Array.isArray(sorted) || sorted.length < 5) return;
    const currentSet = getActiveMatchSniper5xDigitsJokerjoe();
    if (currentSet.length !== 5) return;
    const uniq = Array.from(new Set(currentSet));
    if (uniq.length < 5) return;
    const key = currentSet.join("|");
    if (state.matchSniper5xLastTopKey === key) return;

    state.matchSniper5xBusy = true;
    updateMatchSniper5xStatusJokerjoe(sorted);
    try {
      const r = await placeBatchManualTradesJokerjoe("MATCHES", currentSet, { sameTick: true });
      if (r.placed === 5) {
        state.matchSniper5xLastTopKey = key;
        state.matchSniper5xCooldownUntil = Date.now() + 10000;
        safeToast(`🎯 MatchSniper 5x: MATCHES ${currentSet.join(', ')} (same-tick request)`, "success");
        activateNextMatchSniper5xDigitsJokerjoe();
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

  function shouldRunActivityPollJokerjoe() {
    return isActive() && (
      state.matchesAnalysisOn ||
      state.matchSniperOn ||
      state.matchSniper5xOn ||
      state.randomMatchesDiffersOn ||
      state.randomMatchesDiffersModalOpen
    );
  }

  function runActivityPollOnceJokerjoe() {
    try {
      if (state.matchesAnalysisOn || state.matchSniperOn || state.matchSniper5xOn) {
        refreshMatchesAnalysisJokerjoe();
        updateMatchSniperStatusJokerjoe();
        updateMatchSniper5xStatusJokerjoe();
        updateAIAutoModeModalUiJokerjoe();
      }
      if (state.randomMatchesDiffersOn || state.randomMatchesDiffersModalOpen) {
        updateRandomMatchesDiffersStatusJokerjoe();
        updateRandomMatchesDiffersModalUiJokerjoe();
      }
    } catch (e) {}
  }

  function stopActivityPollJokerjoe() {
    const app = App();
    const clearedTracked = !!(app && typeof app.clearFrontendInterval === "function" && app.clearFrontendInterval(ACTIVITY_POLL_INTERVAL_LABEL));
    if (activityPollTimerJokerjoe && !clearedTracked) {
      clearInterval(activityPollTimerJokerjoe);
    }
    if (activityPollTimerJokerjoe || clearedTracked) activityPollTimerJokerjoe = null;
  }

  function refreshActivityPollJokerjoe() {
    if (!shouldRunActivityPollJokerjoe()) {
      stopActivityPollJokerjoe();
      const app = App();
      if (app && typeof app.logActiveIntervalCount === "function") app.logActiveIntervalCount("jokerjoe_activity_poll_idle");
      return;
    }
    if (activityPollTimerJokerjoe) return;
    activityPollTimerJokerjoe = setInterval(() => {
      if (!shouldRunActivityPollJokerjoe()) {
        stopActivityPollJokerjoe();
        return;
      }
      runActivityPollOnceJokerjoe();
    }, 1500);
    const app = App();
    if (app && typeof app.registerFrontendInterval === "function") app.registerFrontendInterval(ACTIVITY_POLL_INTERVAL_LABEL, activityPollTimerJokerjoe);
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
    refreshActivityPollJokerjoe();
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
    refreshActivityPollJokerjoe();
    safeToast(`🎯 MatchSniper 1x: ${state.matchSniperOn ? "ON" : "OFF"}`, state.matchSniperOn ? "success" : "error");
  };

  window.toggleMatchSniper5xJokerjoe = function () {
    state.matchSniper5xOn = !state.matchSniper5xOn;
    if (state.matchSniper5xOn && !state.matchesAnalysisOn) {
      state.matchesAnalysisOn = true;
      updateMatchesAnalysisButtonJokerjoe();
    }
    if (state.matchSniper5xOn) {
      activateNextMatchSniper5xDigitsJokerjoe();
    }
    if (!state.matchSniper5xOn) {
      state.matchSniper5xBusy = false;
    }
    updateMatchSniper5xButtonJokerjoe();
    bindMatchesAnalysisObserverJokerjoe();
    refreshMatchesAnalysisJokerjoe();
    updateMatchSniper5xStatusJokerjoe();
    refreshActivityPollJokerjoe();
    safeToast(`🎯 MatchSniper 5x: ${state.matchSniper5xOn ? "ON" : "OFF"}`, state.matchSniper5xOn ? "success" : "error");
  };



  async function postJSON(url, body) {
    const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
    let data = {};
    try { data = await res.json(); } catch (e) {}
    return { ok: res.ok, data };
  }

  async function sendFastManualTradeJokerjoe(payload, options) {
    const app = App();
    const turbo = !!(options && Object.prototype.hasOwnProperty.call(options, "turbo")
      ? options.turbo
      : currentTurboModeJokerjoe());
    const requestPayload = Object.assign({}, payload || {}, { turbo });
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
      return enqueueFastBuyJokerjoe(sendNow);
    }
    return sendNow();
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
    const insta2Btn = document.getElementById("insta2BtnJokerjoe");
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
    if (insta2Btn) {
      const barrier = currentBarrier();
      insta2Btn.innerText = state.insta2Busy ? `INSTA 2 ON ${barrier} (RUNNING...)` : `INSTA 2 ON ${barrier}`;
      insta2Btn.disabled = !!state.insta2Busy;
      insta2Btn.style.opacity = state.insta2Busy ? "0.75" : "1";
      insta2Btn.style.cursor = state.insta2Busy ? "wait" : "pointer";
    }
    updateRandomMatchesDiffersButtonJokerjoe();
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
        if (!isActive() || !data) return;
        if (data.auto_modes) state.autoModes = Object.assign({}, state.autoModes, data.auto_modes);
        if (data.auto_settings && data.auto_settings.kidgx_barrier !== undefined) state.kidgxBarrier = Number(data.auto_settings.kidgx_barrier);
        if (data.meta_brain) state.metaBrain = data.meta_brain;
        if (data.percentages) state.blackcard.percentages = normalizeBlackcardPercentagesJokerjoe(data.percentages);
        processRandomMatchesDiffersTickJokerjoe(data);
        updateButtons();
        updateAdvancedAIModeButtonsJokerjoe(data);
        processAIAutoLowestTickJokerjoe(data);
        refreshMatchesAnalysisJokerjoe(data);
      });

      bind("auto_mode_update", (modes) => {
        if (!isActive()) return;
        state.autoModes = Object.assign({}, state.autoModes, modes || {});
        updateButtons();
        updateAdvancedAIModeButtonsJokerjoe();
      });

      bind("trade_result", (entry) => {
        if (!isActive()) return;
        onJokerjoeTradeResultForLowestAI(entry || {});
      });

      bind("tick", (data) => {
        if (!isActive()) return;
        trackBlackcardTickJokerjoe(data || {});
      });
      if (app && typeof app.logSocketListenerCounts === "function") app.logSocketListenerCounts("jokerjoe_profile_init");
    } catch (e) {}
  }

  function bindBarrierSync() {
    const input = document.getElementById("barrier");
    if (!input || input.dataset.kidgxSyncBound === "1") return;
    input.dataset.kidgxSyncBound = "1";
    const sync = async (opts) => {
      const nextBarrier = currentBarrier();
      const changed = Number(nextBarrier) !== Number(state.kidgxBarrier);
      state.kidgxBarrier = nextBarrier;
      updateButtons();
      if (!changed && !(opts && opts.force)) return;
      try { await postJSON("/set_kidgx_barrier", { barrier: state.kidgxBarrier }); } catch (e) {}
    };
    input.addEventListener("input", () => { sync(); });
    input.addEventListener("change", () => { sync(); });
    input.addEventListener("blur", () => { sync(); });
    input.addEventListener("keyup", () => { sync(); });

    const digitGrid = document.getElementById("digitGrid");
    if (digitGrid && digitGrid.dataset.kidgxBarrierSyncBound !== "1") {
      digitGrid.dataset.kidgxBarrierSyncBound = "1";
      digitGrid.addEventListener("click", () => {
        setTimeout(() => { sync(); }, 0);
      });
    }

    setTimeout(() => { sync({ force: true }); }, 150);
  }

  function bindBlackcardWindowEventsJokerjoe() {
    if (window.__blackcardJokerjoeBound) return;
    window.__blackcardJokerjoeBound = true;
    bindBlackcardDigitHandlersJokerjoe();
    window.addEventListener("resize", () => {
      const popup = getBlackcardPopupJokerjoe();
      if (popup && popup.style.display === "block") positionBlackcardPopupJokerjoe();
    });
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
    bindSocketListeners();
    bindBarrierSync();
    bindBlackcardWindowEventsJokerjoe();
    bindMatchesAnalysisObserverJokerjoe();
    updateButtons();
    updateMatchesAnalysisButtonJokerjoe();
    updateMatchSniperButtonJokerjoe();
    updateMatchSniperStatusJokerjoe();
    updateMatchSniper5xButtonJokerjoe();
    updateMatchSniper5xStatusJokerjoe();
    updateAIAutoModeModalUiJokerjoe();
    updateRandomMatchesDiffersButtonJokerjoe();
    updateRandomMatchesDiffersStatusJokerjoe();
    updateRandomMatchesDiffersModalUiJokerjoe();
    renderBlackcardJokerjoe();
    currentTurboModeJokerjoe();
    renderTurboToggleJokerjoe();
    refreshActivityPollJokerjoe();
  }

  async function afterLoadProfileUI() {
    try { App().applyDigitSelectionUI && App().applyDigitSelectionUI(); } catch (e) {}
    patchKidgambleConfirm();
    bindSocketListeners();
    bindBarrierSync();
    bindBlackcardWindowEventsJokerjoe();
    bindMatchesAnalysisObserverJokerjoe();
    updateButtons();
    updateMatchesAnalysisButtonJokerjoe();
    updateMatchSniperButtonJokerjoe();
    updateMatchSniperStatusJokerjoe();
    updateMatchSniper5xButtonJokerjoe();
    updateMatchSniper5xStatusJokerjoe();
    updateAIAutoModeModalUiJokerjoe();
    updateRandomMatchesDiffersButtonJokerjoe();
    updateRandomMatchesDiffersStatusJokerjoe();
    updateRandomMatchesDiffersModalUiJokerjoe();
    renderBlackcardJokerjoe();
    currentTurboModeJokerjoe();
    renderTurboToggleJokerjoe();
    refreshActivityPollJokerjoe();
  }

  async function onActivate() {
    try { App().applyDigitSelectionUI && App().applyDigitSelectionUI(); } catch (e) {}
    patchKidgambleConfirm();
    bindSocketListeners();
    bindBarrierSync();
    bindBlackcardWindowEventsJokerjoe();
    bindMatchesAnalysisObserverJokerjoe();
    state.kidgxBarrier = currentBarrier();
    updateButtons();
    updateMatchesAnalysisButtonJokerjoe();
    updateMatchSniperButtonJokerjoe();
    updateMatchSniperStatusJokerjoe();
    updateMatchSniper5xButtonJokerjoe();
    updateMatchSniper5xStatusJokerjoe();
    updateAIAutoModeModalUiJokerjoe();
    updateRandomMatchesDiffersButtonJokerjoe();
    updateRandomMatchesDiffersStatusJokerjoe();
    updateRandomMatchesDiffersModalUiJokerjoe();
    renderBlackcardJokerjoe();
    currentTurboModeJokerjoe();
    renderTurboToggleJokerjoe();
    refreshMatchesAnalysisJokerjoe();
    refreshActivityPollJokerjoe();
  }

window.toggleTurboJokerjoe = function () {
  const next = !currentTurboModeJokerjoe();
  state.turboMode = next;
  persistTurboModeJokerjoe(next);
  renderTurboToggleJokerjoe();
};

if (!window.__jokerjoeTurboSyncBound) {
  window.__jokerjoeTurboSyncBound = true;
  window.addEventListener("bot-profile-turbo-change", (event) => {
    const detail = (event && event.detail) || {};
    if (String(detail.profile || "").toUpperCase() !== PROFILE) return;
    state.turboMode = !!detail.enabled;
    renderTurboToggleJokerjoe();
  });
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
      const lowestCount = normalizeAIAutoLowestTradeCountJokerjoe(state.aiAutoLowestTradeCountChoice);
      safeToast(`🤖AI AUTO-TRADING: ON (Lowest % mode • ${lowestCount} trade${lowestCount === 1 ? "" : "s"})`, "success");
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

  window.openAIAutoLowestTradeCountOptionsJokerjoe = function () {
    state.aiAutoModeChoice = "lowest_pct";
    updateAIAutoModeModalUiJokerjoe();
  };

  window.selectAIAutoLowestTradeCountJokerjoe = async function (count) {
    state.aiAutoLowestTradeCountChoice = normalizeAIAutoLowestTradeCountJokerjoe(count);
    state.aiAutoModeChoice = "lowest_pct";
    updateAIAutoModeModalUiJokerjoe();
    return window.selectAIAutoModeJokerjoe("lowest_pct");
  };

  window.closeAIAutoModeModalJokerjoe = function () {
    closeAIAutoModeModalJokerjoe();
  };

  window.openRandomMatchesDiffersModalJokerjoe = function () {
    openRandomMatchesDiffersModalJokerjoe();
  };

  window.closeRandomMatchesDiffersModalJokerjoe = function () {
    closeRandomMatchesDiffersModalJokerjoe();
  };

  window.disableRandomMatchesDiffersJokerjoe = function () {
    state.randomMatchesDiffersOn = false;
    state.randomMatchesDiffersBusy = false;
    updateRandomMatchesDiffersButtonJokerjoe();
    updateRandomMatchesDiffersStatusJokerjoe();
    updateRandomMatchesDiffersModalUiJokerjoe();
    closeRandomMatchesDiffersModalJokerjoe();
    refreshActivityPollJokerjoe();
    safeToast("🎲 Random Matches/Differs: OFF", "error");
  };

  window.selectRandomMatchesDiffersModeJokerjoe = function (mode) {
    state.randomMatchesDiffersMode = normalizeRandomMatchesDiffersModeJokerjoe(mode);
    state.randomMatchesDiffersOn = true;
    updateRandomMatchesDiffersButtonJokerjoe();
    updateRandomMatchesDiffersStatusJokerjoe();
    updateRandomMatchesDiffersModalUiJokerjoe();
    closeRandomMatchesDiffersModalJokerjoe();
    refreshActivityPollJokerjoe();
    safeToast(`🎲 Random Matches/Differs: ${state.randomMatchesDiffersMode} ON`, "success");
    tryRandomMatchesDiffersTradeJokerjoe(state.randomMatchesDiffersSnapshot || buildRandomMatchesDiffersSnapshotJokerjoe());
  };

  document.addEventListener("keydown", (evt) => {
    if (evt.key !== "Escape") return;
    if (state.aiAutoModalOpen) closeAIAutoModeModalJokerjoe();
    if (state.randomMatchesDiffersModalOpen) closeRandomMatchesDiffersModalJokerjoe();
  });


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

window.showBlackcardPopupJokerjoe = function () {
  const popup = getBlackcardPopupJokerjoe();
  if (!popup) return;
  bindBlackcardDigitHandlersJokerjoe();
  renderBlackcardJokerjoe();
  positionBlackcardPopupJokerjoe();
};

window.hideBlackcardPopupJokerjoe = function () {
  const popup = getBlackcardPopupJokerjoe();
  if (popup) popup.style.display = "none";
};

window.sendBlackcardDiffersJokerjoe = async function (digit, event) {
  if (event && typeof event.preventDefault === "function") event.preventDefault();
  const selectedDigit = Number(digit);
  if (!Number.isInteger(selectedDigit) || selectedDigit < 0 || selectedDigit > 9) {
    safeToast("Pick a valid digit for DIFFERS.", "error");
    return;
  }
  if (state.blackcard.busy) return;
  if (typeof apiConnected !== "undefined" && !apiConnected) {
    safeToast("Connect your API first.", "error");
    return;
  }

  state.blackcard.busy = true;
  renderBlackcardJokerjoe();
  try {
    const symbol = (typeof window.getConfirmedMarketSymbol === "function")
      ? window.getConfirmedMarketSymbol()
      : ((document.getElementById("symbol") || {}).value || "R_25");
    const stake = getManualStakeValueJokerjoe();
    const duration = getDurationTicksJokerjoe();
    const task = () => sendFastManualTradeJokerjoe({
      type: "DIFFERS",
      barrier: Number(selectedDigit),
      stake,
      amount: stake,
      duration,
      duration_unit: "t",
      symbol,
    }, {
      turbo: true,
      queue: false,
      useSocket: true,
      fireAndForget: true,
    });
    const result = await task();
    if (result && result.data && result.data.status === "success") safeToast(`DIFFERS ${selectedDigit} sent instantly.`, "success");
    else safeToast((result && result.data && result.data.message) || `DIFFERS ${selectedDigit} failed`, "error");
  } catch (e) {
    safeToast(`DIFFERS ${selectedDigit} failed`, "error");
  } finally {
    state.blackcard.busy = false;
    renderBlackcardJokerjoe();
  }
};

window.insta2Jokerjoe = async function () {
  if (state.insta2Busy) return;
  if (typeof apiConnected !== "undefined" && !apiConnected) {
    safeToast("Connect your API first.", "error");
    return;
  }
  const digit = currentBarrier();
  state.insta2Busy = true;
  updateButtons();
  try {
    const result = await placeExactTwoDiffersBatchJokerjoe(digit);
    if (result && result.exact) {
      safeToast(`INSTA 2: DIFFERS ${digit} x2 sent.`, "success");
    } else {
      const placed = Number(result && result.placed) || 0;
      safeToast(`INSTA 2 placed ${placed}/2 trades on ${digit}.`, placed > 0 ? "warn" : "error");
    }
  } catch (e) {
    safeToast(`INSTA 2 on ${digit} failed.`, "error");
  } finally {
    state.insta2Busy = false;
    updateButtons();
  }
};

  if (typeof window.registerProfileModule === "function") {
    window.registerProfileModule(PROFILE, { onMount, afterLoadProfileUI, onActivate });
  } else {
    window.ProfileModules = window.ProfileModules || {};
    window.ProfileModules[PROFILE] = { onMount, afterLoadProfileUI, onActivate };
  }

  // Fallback bootstrap for index versions without Phase 2 hooks
  let fallbackBootstrapTimerJokerjoe = null;

  function stopFallbackBootstrapJokerjoe() {
    const app = App();
    const clearedTracked = !!(app && typeof app.clearFrontendInterval === "function" && app.clearFrontendInterval(FALLBACK_BOOTSTRAP_INTERVAL_LABEL));
    if (fallbackBootstrapTimerJokerjoe && !clearedTracked) {
      clearInterval(fallbackBootstrapTimerJokerjoe);
    }
    if (fallbackBootstrapTimerJokerjoe || clearedTracked) fallbackBootstrapTimerJokerjoe = null;
  }

  function fallbackBootstrap() {
    try {
      if (typeof window.registerProfileModule === "function") {
        stopFallbackBootstrapJokerjoe();
        const app = App();
        if (app && typeof app.logActiveIntervalCount === "function") app.logActiveIntervalCount("jokerjoe_fallback_module_loaded");
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
    fallbackBootstrapTimerJokerjoe = setInterval(fallbackBootstrap, 1200);
    const app = App();
    if (app && typeof app.registerFrontendInterval === "function") app.registerFrontendInterval(FALLBACK_BOOTSTRAP_INTERVAL_LABEL, fallbackBootstrapTimerJokerjoe);
    setTimeout(fallbackBootstrap, 200);
  } else {
    stopFallbackBootstrapJokerjoe();
    const app = App();
    if (app && typeof app.logActiveIntervalCount === "function") app.logActiveIntervalCount("jokerjoe_fallback_not_needed");
  }

})();
