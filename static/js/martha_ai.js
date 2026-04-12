(function () {
  "use strict";

  if (window.MarthaAI && window.MarthaAI.__loaded) return;

  const STORAGE_KEYS = {
    enabled: "martha_ai_enabled",
    threshold: "martha_ai_threshold",
    emergency: "martha_ai_emergency_reconnect",
  };

  const MAX_TICKS = 80;
  const SCAN_INTERVAL_MS = 900;
  const DEFAULT_THRESHOLD = 60;

  const state = {
    __loaded: true,
    enabled: false,
    emergencyReconnect: false,
    threshold: DEFAULT_THRESHOLD,
    activeProfile: "KOOLKID",
    scanTimer: null,
    lastScanAt: 0,
    ticks: [],
    hiddenScores: {},
    profileStats: {},
    recentResults: [],
    initialized: false,
    backendSyncTimer: null,
  };

  function clamp(value, min, max) {
    const n = Number(value);
    if (!Number.isFinite(n)) return min;
    return Math.max(min, Math.min(max, n));
  }

  function nowMs() {
    return Date.now ? Date.now() : new Date().getTime();
  }

  function safeText(value) {
    return String(value == null ? "" : value).trim();
  }

  function normalizeProfile(profile) {
    const p = safeText(profile).toUpperCase();
    return p || state.activeProfile || "KOOLKID";
  }

  function normalizeType(type) {
    return safeText(type).toUpperCase().replace(/\s+/g, "_");
  }

  function getLicenseContext() {
    return window.LICENSE_CONTEXT || (window.BotApp && window.BotApp.licenseContext) || {};
  }

  function isAllowedForUser() {
    const ctx = getLicenseContext();
    if (!ctx || !Object.keys(ctx).length) return true;
    return !!(
      ctx.is_full_access ||
      ctx.is_lifetime ||
      String(ctx.license_type || "").toLowerCase() === "admin" ||
      String(ctx.access || "").toLowerCase() === "admin"
    );
  }

  function loadSettings() {
    try {
      state.enabled = localStorage.getItem(STORAGE_KEYS.enabled) === "1";
    } catch (_err) {}
    try {
      const rawThreshold = Number(localStorage.getItem(STORAGE_KEYS.threshold));
      state.threshold = Number.isFinite(rawThreshold) ? clamp(rawThreshold, 1, 95) : DEFAULT_THRESHOLD;
    } catch (_err) {
      state.threshold = DEFAULT_THRESHOLD;
    }
    try {
      state.emergencyReconnect = localStorage.getItem(STORAGE_KEYS.emergency) === "1";
    } catch (_err) {}
  }

  function saveSettings() {
    try { localStorage.setItem(STORAGE_KEYS.enabled, state.enabled ? "1" : "0"); } catch (_err) {}
    try { localStorage.setItem(STORAGE_KEYS.threshold, String(state.threshold)); } catch (_err) {}
    try { localStorage.setItem(STORAGE_KEYS.emergency, state.emergencyReconnect ? "1" : "0"); } catch (_err) {}
  }

  function syncBackendSettings(reason) {
    if (!isAllowedForUser()) return;
    fetch("/martha_ai/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        enabled: !!state.enabled,
        threshold: state.threshold,
        emergency_reconnect: !!state.emergencyReconnect,
        reason: reason || "sync",
      }),
    }).then((res) => res.json().catch(() => ({})).then((data) => ({ ok: res.ok, data })))
      .then((result) => {
        if (!result.ok) {
          console.warn("martha_ai_backend_sync_failed", result.data || {});
        }
      })
      .catch((err) => console.warn("martha_ai_backend_sync_failed", err));
  }

  function scheduleBackendSync(reason) {
    if (state.backendSyncTimer) clearTimeout(state.backendSyncTimer);
    state.backendSyncTimer = setTimeout(() => {
      state.backendSyncTimer = null;
      syncBackendSettings(reason || "scheduled");
    }, 250);
  }

  function byId(id) {
    return document.getElementById(id);
  }

  function showToast(message, type) {
    try {
      if (typeof window.showToast === "function") {
        window.showToast(message, type || "info");
      }
    } catch (_err) {}
  }

  function setNodeText(node, text) {
    if (!node) return;
    const next = String(text == null ? "" : text);
    if (node.textContent !== next) node.textContent = next;
  }

  function renderUi() {
    const panel = byId("marthaAiPanel");
    const status = byId("marthaAiStatus");
    const toggle = byId("marthaAiToggleBtn");
    const threshold = byId("marthaAiThreshold");
    const emergency = byId("marthaAiEmergencyToggle");
    const decision = byId("marthaAiLastDecision");

    if (!panel) return;

    const allowed = isAllowedForUser();
    panel.style.display = allowed ? "block" : "none";
    if (!allowed) {
      stopScanner();
      return;
    }

    panel.classList.toggle("martha-ai-on", !!state.enabled);
    panel.classList.toggle("martha-ai-off", !state.enabled);
    panel.classList.toggle("martha-ai-emergency-on", !!state.emergencyReconnect);
    setNodeText(status, state.enabled ? "Martha AI: ON / Watching" : "Martha AI: OFF");

    if (toggle) {
      toggle.textContent = state.enabled ? "ON" : "OFF";
      toggle.classList.toggle("martha-toggle-on", !!state.enabled);
    }
    if (threshold && String(threshold.value) !== String(state.threshold)) {
      threshold.value = String(state.threshold);
    }
    if (emergency) {
      emergency.checked = !!state.emergencyReconnect;
    }
    if (decision && !state.enabled) {
      decision.style.display = "none";
    }
  }

  function bindUi() {
    const toggle = byId("marthaAiToggleBtn");
    const threshold = byId("marthaAiThreshold");
    const emergency = byId("marthaAiEmergencyToggle");

    if (toggle && toggle.dataset.marthaBound !== "1") {
      toggle.dataset.marthaBound = "1";
      toggle.addEventListener("click", () => toggleEnabled());
    }
    if (threshold && threshold.dataset.marthaBound !== "1") {
      threshold.dataset.marthaBound = "1";
      threshold.addEventListener("input", () => {
        state.threshold = clamp(Number(threshold.value || DEFAULT_THRESHOLD), 1, 95);
        saveSettings();
        scheduleBackendSync("threshold");
        renderUi();
      });
    }
    if (emergency && emergency.dataset.marthaBound !== "1") {
      emergency.dataset.marthaBound = "1";
      emergency.addEventListener("change", () => {
        state.emergencyReconnect = !!emergency.checked;
        saveSettings();
        scheduleBackendSync("emergency_reconnect");
        renderUi();
      });
    }
  }

  function toggleEnabled(forceValue) {
    if (!isAllowedForUser()) return false;
    state.enabled = typeof forceValue === "boolean" ? forceValue : !state.enabled;
    saveSettings();
    syncBackendSettings("toggle");
    renderUi();
    if (state.enabled) {
      startScanner();
      showToast("Martha AI is watching quietly in the background.", "info");
    } else {
      stopScanner();
      showToast("Martha AI is OFF. Trades pass normally.", "info");
    }
    return state.enabled;
  }

  function setProfile(profile) {
    state.activeProfile = normalizeProfile(profile);
    if (state.enabled) scanCurrentProfile();
    renderUi();
  }

  function startScanner() {
    stopScanner();
    if (!state.enabled || !isAllowedForUser()) return;
    scanCurrentProfile();
    state.scanTimer = setInterval(scanCurrentProfile, SCAN_INTERVAL_MS);
    try {
      if (window.BotApp && typeof window.BotApp.registerFrontendInterval === "function") {
        window.BotApp.registerFrontendInterval("martha_ai_scan", state.scanTimer);
      }
    } catch (_err) {}
  }

  function stopScanner() {
    if (state.scanTimer) {
      try {
        if (window.BotApp && typeof window.BotApp.clearFrontendInterval === "function") {
          window.BotApp.clearFrontendInterval("martha_ai_scan");
        } else {
          clearInterval(state.scanTimer);
        }
      } catch (_err) {
        clearInterval(state.scanTimer);
      }
      state.scanTimer = null;
    }
  }

  function isVisible(node) {
    if (!node) return false;
    if (node.disabled) return false;
    const style = window.getComputedStyle ? window.getComputedStyle(node) : null;
    if (style && (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0)) return false;
    const rect = node.getBoundingClientRect ? node.getBoundingClientRect() : null;
    return !rect || rect.width > 0 || rect.height > 0;
  }

  function looksLikeTradeButton(text) {
    const t = normalizeType(text);
    if (!t) return false;
    if (/(CLOSE|CLEAR|CANCEL|SAVE|SETTINGS|REFRESH|HISTORY|GUIDE|SHOW|HIDE|LOGIN|LOGOUT)/.test(t)) return false;
    return /(OVER|UNDER|MATCH|DIFFER|TOUCH|NO_TOUCH|HIGHER|LOWER|RISE|FALL|TAKE|BURST|INSTA|KIDG|DUAL|BOTH|BLACK|GOLDEN)/.test(t);
  }

  function readCurrentSymbol() {
    const symbolNode = byId("symbol");
    if (symbolNode) return symbolNode.dataset.confirmedSymbol || symbolNode.value || "";
    const latest = state.ticks.length ? state.ticks[state.ticks.length - 1] : null;
    return latest ? latest.symbol : "";
  }

  function inferButtonAction(button) {
    const text = safeText(button && (button.innerText || button.textContent));
    if (!looksLikeTradeButton(text)) return null;
    const typeMatch = text.match(/\b(OVER|UNDER|MATCHES|MATCH|DIFFERS|DIFFER|TOUCH|NO\s*TOUCH|HIGHER|LOWER|RISE|FALL|BOTH)\b/i);
    const digitMatch = text.match(/\b([0-9])\b/);
    return {
      profile: state.activeProfile,
      source: "button_scan",
      id: button.id || "",
      label: text.slice(0, 80),
      type: typeMatch ? typeMatch[1].replace(/\s+/g, "_") : text,
      barrier: digitMatch ? digitMatch[1] : "",
      symbol: readCurrentSymbol(),
      batch_count: /BURST/i.test(text) ? 4 : (/TAKE\s*3/i.test(text) ? 3 : 1),
    };
  }

  function scanCurrentProfile() {
    if (!state.enabled || !isAllowedForUser()) return;
    state.lastScanAt = nowMs();
    const root = byId("profileContainer");
    if (!root) return;
    const buttons = root.querySelectorAll("button, [role='button']");
    buttons.forEach((button) => {
      if (!isVisible(button)) return;
      const action = inferButtonAction(button);
      if (!action) return;
      const decision = evaluateAction(action, { hidden: true });
      state.hiddenScores[actionKey(action)] = {
        confidence: decision.confidence,
        reason: decision.reason,
        at: nowMs(),
      };
    });
  }

  function actionKey(action) {
    const a = action || {};
    return [
      normalizeProfile(a.profile || state.activeProfile),
      normalizeType(a.source || "manual"),
      normalizeType(a.type || a.side || a.direction || a.label || "TRADE"),
      safeText(a.barrier),
      safeText(a.symbol || readCurrentSymbol()),
    ].join("|");
  }

  function observeTick(data) {
    if (!state.enabled || !isAllowedForUser()) return;
    const digit = Number(data && data.digit);
    const price = Number(
      (data && (data.quote ?? data.price ?? data.tick ?? data.value ?? data.spot)) ||
      (data && data.tick && data.tick.quote)
    );
    const symbol = safeText(data && data.symbol) || readCurrentSymbol();
    const entry = {
      digit: Number.isInteger(digit) && digit >= 0 && digit <= 9 ? digit : null,
      price: Number.isFinite(price) ? price : null,
      symbol,
      at: nowMs(),
    };
    state.ticks.push(entry);
    if (state.ticks.length > MAX_TICKS) state.ticks.splice(0, state.ticks.length - MAX_TICKS);
    if (nowMs() - state.lastScanAt > SCAN_INTERVAL_MS) scanCurrentProfile();
  }

  function observeDigitAnalysis(data) {
    if (!state.enabled || !isAllowedForUser()) return;
    state.latestDigitAnalysis = data || {};
  }

  function observeStats(data) {
    if (!state.enabled || !isAllowedForUser()) return;
    const profile = normalizeProfile((data && data.profile) || state.activeProfile);
    state.profileStats[profile] = {
      wins: Number((data && data.wins) || 0),
      losses: Number((data && data.losses) || 0),
      net_pnl: Number((data && data.net_pnl) || 0),
      at: nowMs(),
    };
  }

  function observeTradeEvent(data) {
    if (!state.enabled || !isAllowedForUser()) return;
    const result = normalizeType(data && (data.result || data.status));
    if (!result || (result !== "WIN" && result !== "LOSS")) return;
    state.recentResults.push({
      profile: normalizeProfile((data && data.profile) || state.activeProfile),
      result,
      profit: Number((data && (data.profit ?? data.profit_value)) || 0),
      at: nowMs(),
    });
    if (state.recentResults.length > 20) state.recentResults.splice(0, state.recentResults.length - 20);
  }

  function getSessionScore() {
    const hour = new Date().getUTCHours();
    const london = hour >= 7 && hour < 16;
    const ny = hour >= 12 && hour < 21;
    const overlap = hour >= 12 && hour < 16;
    if (overlap) return { adjust: 12, reason: "London/New York overlap is active" };
    if (london) return { adjust: 7, reason: "London session is active" };
    if (ny) return { adjust: 7, reason: "New York session is active" };
    return { adjust: -8, reason: "Off-session conditions are weaker" };
  }

  function movementQuality() {
    const priced = state.ticks.filter((t) => Number.isFinite(t.price)).slice(-24);
    if (priced.length < 6) {
      return { adjust: 0, clean: 0.5, volatility: 0, speed: 0, reason: "Limited movement data" };
    }
    const deltas = [];
    for (let i = 1; i < priced.length; i += 1) {
      deltas.push(priced[i].price - priced[i - 1].price);
    }
    const nonZero = deltas.filter((d) => Math.abs(d) > 0);
    const avgAbs = nonZero.length ? nonZero.reduce((a, b) => a + Math.abs(b), 0) / nonZero.length : 0;
    let flips = 0;
    let lastSign = 0;
    nonZero.forEach((d) => {
      const sign = d > 0 ? 1 : -1;
      if (lastSign && sign !== lastSign) flips += 1;
      lastSign = sign;
    });
    const clean = nonZero.length > 1 ? 1 - (flips / Math.max(1, nonZero.length - 1)) : 0.5;
    const recentTicks = state.ticks.filter((t) => nowMs() - t.at <= 10000).length;
    const speed = clamp(recentTicks / 12, 0, 1);
    const volatility = clamp(avgAbs * 10000, 0, 1);
    let adjust = Math.round((clean - 0.5) * 26);
    if (speed > 0.25 && speed < 0.95) adjust += 5;
    if (volatility > 0.9) adjust -= 7;
    const reason = clean >= 0.62 ? "Market movement looks clean" : (clean <= 0.38 ? "Market movement looks choppy" : "Market movement is mixed");
    return { adjust, clean, volatility, speed, reason };
  }

  function recentDigits(size) {
    return state.ticks
      .map((t) => t.digit)
      .filter((d) => Number.isInteger(d) && d >= 0 && d <= 9)
      .slice(-(size || 20));
  }

  function countDigit(digits, wanted) {
    const set = new Set(Array.isArray(wanted) ? wanted.map(Number) : [Number(wanted)]);
    return digits.filter((d) => set.has(Number(d))).length;
  }

  function digitSetupScore(action) {
    const type = normalizeType(action.type || action.side || action.direction || action.label);
    const digits20 = recentDigits(20);
    const digits10 = recentDigits(10);
    const reasons = [];
    if (digits10.length < 5) {
      return { adjust: 0, reason: "Waiting for more recent digits" };
    }

    const barrierRaw = action.barrier;
    const barrier = Number.isFinite(Number(barrierRaw)) ? Number(barrierRaw) : null;
    let adjust = 0;

    if (type.includes("OVER") && barrier !== null) {
      const losers = digits10.filter((d) => d <= barrier).length;
      adjust += Math.round(((digits10.length - losers) / digits10.length - 0.55) * 55);
      reasons.push(losers <= 2 ? "Recent losing digits are low for OVER" : "OVER has too many recent losing digits");
    } else if (type.includes("UNDER") && barrier !== null) {
      const losers = digits10.filter((d) => d >= barrier).length;
      adjust += Math.round(((digits10.length - losers) / digits10.length - 0.55) * 55);
      reasons.push(losers <= 2 ? "Recent losing digits are low for UNDER" : "UNDER has too many recent losing digits");
    } else if (type.includes("DIFFER")) {
      const target = barrier === null ? 5 : barrier;
      const count = countDigit(digits20, target);
      if (count <= 1) adjust += 18;
      else if (count >= 4) adjust -= 24;
      else adjust += 4;
      reasons.push(count <= 1 ? "Differs barrier is not overplayed" : "Differs barrier has appeared recently");
    } else if (type.includes("MATCH")) {
      const target = barrier === null ? 5 : barrier;
      const count = countDigit(digits20, target);
      if (count >= 3) adjust += 15;
      else if (count === 0) adjust -= 12;
      else adjust += 2;
      reasons.push(count >= 3 ? "Match digit has repeated recently" : "Match digit is not repeating strongly");
    } else if (/(TOUCH|NO_TOUCH|HIGHER|LOWER|RISE|FALL)/.test(type)) {
      const movement = movementQuality();
      adjust += Math.round(movement.adjust * 0.8);
      reasons.push(movement.reason);
    } else if (type.includes("BOTH")) {
      const middle = countDigit(digits10, [2, 3, 4, 5, 6, 7]);
      adjust += middle >= 6 ? 10 : -5;
      reasons.push(middle >= 6 ? "Middle digits are showing balance" : "Both-mode setup is not clean yet");
    } else {
      const unique = new Set(digits10).size;
      adjust += unique >= 5 ? 4 : -4;
      reasons.push(unique >= 5 ? "Recent digits are balanced" : "Recent digits are clustered");
    }

    const overplayed = digits10.some((d) => countDigit(digits10, d) >= 4);
    if (overplayed) {
      adjust -= 10;
      reasons.push("One digit is overplayed in the last 10");
    }

    return { adjust, reason: reasons.filter(Boolean).slice(0, 2).join(", ") };
  }

  function recentPerformanceScore(profile) {
    const p = normalizeProfile(profile);
    const recent = state.recentResults.filter((r) => normalizeProfile(r.profile) === p).slice(-4);
    if (!recent.length) return { adjust: 0, reason: "No recent Martha-tracked result yet" };
    const wins = recent.filter((r) => r.result === "WIN").length;
    const losses = recent.filter((r) => r.result === "LOSS").length;
    if (wins >= 2 && losses === 0) return { adjust: 8, reason: "Recent results are positive" };
    if (losses >= 2) return { adjust: -10, reason: "Recent losses reduce confidence" };
    return { adjust: wins > losses ? 4 : -3, reason: wins > losses ? "Recent edge is slightly positive" : "Recent edge is soft" };
  }

  function batchPenalty(action) {
    const count = Number(action.batch_count || action.batchCount || 1);
    if (!Number.isFinite(count) || count <= 1) return { adjust: 0, reason: "" };
    return { adjust: -Math.min(12, (count - 1) * 3), reason: `${count} trades increases risk` };
  }

  function evaluateAction(action, options) {
    const a = Object.assign({}, action || {});
    a.profile = normalizeProfile(a.profile || state.activeProfile);
    a.symbol = safeText(a.symbol || readCurrentSymbol());

    const reasons = [];
    if (recentDigits(5).length < 5) {
      return {
        action: a,
        approved: true,
        confidence: Math.max(state.threshold, DEFAULT_THRESHOLD),
        threshold: state.threshold,
        reason: "Martha has limited live data, so the trade is allowed safely",
        hidden: !!(options && options.hidden),
      };
    }

    let score = 50;
    const session = getSessionScore();
    const movement = movementQuality();
    const setup = digitSetupScore(a);
    const performance = recentPerformanceScore(a.profile);
    const batch = batchPenalty(a);

    score += session.adjust;
    score += movement.adjust;
    score += setup.adjust;
    score += performance.adjust;
    score += batch.adjust;

    [session.reason, movement.reason, setup.reason, performance.reason, batch.reason].forEach((reason) => {
      if (reason) reasons.push(reason);
    });

    const confidence = Math.round(clamp(score, 5, 95));
    return {
      action: a,
      approved: confidence >= Number(state.threshold || DEFAULT_THRESHOLD),
      confidence,
      threshold: state.threshold,
      reason: reasons.slice(0, 3).join(", "),
      hidden: !!(options && options.hidden),
    };
  }

  function showDecision(decision, options) {
    const card = byId("marthaAiLastDecision");
    const conf = byId("marthaAiDecisionConfidence");
    const status = byId("marthaAiDecisionStatus");
    const reason = byId("marthaAiDecisionReason");
    if (card) {
      card.style.display = "block";
      card.classList.toggle("martha-decision-approved", !!decision.approved);
      card.classList.toggle("martha-decision-blocked", !decision.approved);
    }
    if (conf) setNodeText(conf, `Martha AI Confidence: ${decision.confidence}%`);
    if (status) setNodeText(status, `Decision: ${decision.approved ? "Approved" : "Blocked"}`);
    if (reason) setNodeText(reason, `Reason: ${decision.reason || "Live setup quality check completed"}`);
    if (!(options && options.silent)) {
      showToast(
        `Martha AI ${decision.approved ? "approved" : "blocked"} this trade (${decision.confidence}%).`,
        decision.approved ? "success" : "error"
      );
    }
  }

  function blockedResponse(decision) {
    const message = `Martha AI blocked this trade (${decision.confidence}% confidence, minimum ${decision.threshold}%).`;
    return {
      ok: false,
      status: "blocked",
      message,
      data: {
        status: "blocked",
        message,
        martha_ai: decision,
      },
      martha_ai: decision,
    };
  }

  function triggerEmergencyReconnect(decision) {
    console.warn("martha_ai_emergency_reconnect_requested", {
      confidence: decision && decision.confidence,
      threshold: decision && decision.threshold,
      profile: decision && decision.action && decision.action.profile,
    });
    fetch("/martha_ai/emergency_reconnect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        reason: "martha_ai_blocked_trade",
        confidence: decision && decision.confidence,
        threshold: decision && decision.threshold,
      }),
    }).then((res) => res.json().catch(() => ({})).then((data) => ({ ok: res.ok, data })))
      .then((result) => {
        if (result.ok) {
          showToast("Martha emergency reconnect started.", "warn");
        } else {
          const msg = (result.data && (result.data.message || result.data.error)) || "Martha emergency reconnect failed.";
          showToast(msg, "error");
        }
      })
      .catch((err) => {
        console.warn("martha_ai_emergency_reconnect_failed", err);
        showToast("Martha emergency reconnect failed.", "error");
      });
  }

  async function guardAction(action, proceed) {
    if (typeof proceed !== "function") return null;
    if (!isAllowedForUser() || !state.enabled) {
      return proceed();
    }
    try {
      const key = actionKey(action || {});
      let decision = evaluateAction(action || {});
      state.hiddenScores[key] = {
        confidence: decision.confidence,
        reason: decision.reason,
        at: nowMs(),
      };
      showDecision(decision);
      console.info("martha_ai_trade_decision", {
        profile: decision.action.profile,
        type: decision.action.type || decision.action.side || decision.action.direction,
        source: decision.action.source,
        confidence: decision.confidence,
        threshold: decision.threshold,
        approved: decision.approved,
        emergency_reconnect: state.emergencyReconnect,
      });
      if (!decision.approved) {
        if (state.emergencyReconnect) triggerEmergencyReconnect(decision);
        return blockedResponse(decision);
      }
      return await proceed();
    } catch (err) {
      console.warn("martha_ai_guard_failed_allowing_trade", err);
      showToast("Martha AI had missing data, so the trade is allowed normally.", "warn");
      return proceed();
    }
  }

  function observeAutoDecision(data) {
    if (!state.enabled || !isAllowedForUser() || !data || !data.active) return;
    const decision = {
      action: data.action || {},
      approved: !!data.approved,
      confidence: Number(data.confidence || 0),
      threshold: Number(data.threshold || state.threshold || DEFAULT_THRESHOLD),
      reason: data.reason || "Backend auto signal checked",
    };
    showDecision(decision, { silent: true });
    console.info("martha_ai_auto_decision", {
      profile: decision.action.profile,
      mode: decision.action.mode,
      type: decision.action.type,
      confidence: decision.confidence,
      threshold: decision.threshold,
      approved: decision.approved,
    });
  }

  function init() {
    if (state.initialized) {
      bindUi();
      renderUi();
      return;
    }
    state.initialized = true;
    loadSettings();
    bindUi();
    renderUi();
    syncBackendSettings("init");
    if (state.enabled && isAllowedForUser()) startScanner();
    console.info("martha_ai_initialized", {
      enabled: state.enabled,
      threshold: state.threshold,
      emergency_reconnect: state.emergencyReconnect,
      allowed: isAllowedForUser(),
    });
  }

  window.MarthaAI = {
    __loaded: true,
    init,
    toggle: toggleEnabled,
    setProfile,
    guardAction,
    observeTick,
    observeDigitAnalysis,
    observeStats,
    observeTradeEvent,
    observeAutoDecision,
    scanCurrentProfile,
    evaluateAction,
    isEnabled: () => !!state.enabled,
    getState: () => Object.assign({}, state, {
      ticks: state.ticks.slice(-10),
      hiddenScores: Object.assign({}, state.hiddenScores),
    }),
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
