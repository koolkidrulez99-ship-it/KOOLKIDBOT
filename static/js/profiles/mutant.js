(function () {
  const PROFILE = "NTT";
  const FORM_FIELDS = [
    "nttTouchStake",
    "nttNoTouchStake",
    "nttTouchBarrier",
    "nttNoTouchBarrier",
    "nttUseSharedDuration",
    "nttTouchDuration",
    "nttTouchDurationUnit",
    "nttNoTouchDuration",
    "nttNoTouchDurationUnit",
    "nttKoolkidTouchBarrier",
    "nttKoolkidNoTouchBarrier",
    "nttKoolkidSimDuration",
    "nttKoolkidSimDurationUnit",
    "nttKoolkidLiveDuration",
    "nttKoolkidLiveDurationUnit",
    "nttKoolkidTntLossPct",
    "nttKoolkidTntSimSide",
    "nttDuration",
    "nttDurationUnit",
    "nttTp",
    "nttSl",
  ];
  const BARRIER_FIELD_IDS = new Set([
    "nttTouchBarrier",
    "nttNoTouchBarrier",
  ]);
  const DURATION_PRESETS = {
    t: Array.from({ length: 6 }, (_, idx) => idx + 5),
    m: Array.from({ length: 58 }, (_, idx) => idx + 2),
    h: Array.from({ length: 24 }, (_, idx) => idx + 1),
  };
  const state = {
    socketBound: false,
    lastSocket: null,
    pollTimer: null,
    lastPayload: null,
    lastMainSymbol: null,
    auto_sl: true,
    tradeRequestInFlight: false,
    tradeRequestSide: null,
    predictionTimer: null,
    predictionSignature: "",
    predictionLoading: false,
    expectedProfitTimer: null,
    expectedProfitSignature: "",
    expectedProfitLoading: false,
    noTouchStakeCustom: false,
    koolkid_reversal_enabled: false,
    koolkid_half_barrier_enabled: false,
    koolkidPanelOpen: false,
    autoPanelOpen: false,
    dirtyFields: new Set(),
    lastBarrierKey: null,
    marketBarrierSyncInFlight: false,
    marketBarrierSyncSignature: "",
    marketBarrierSyncTimer: null,
    marketBarrierStore: {},
    autoBothDraft: null,
    marketChart: {
      history: [],
      basePrice: null,
      lastPrice: null,
      lastSymbol: null,
      maxPoints: 72,
      previewBasePrice: null,
      previewBaseSymbol: null,
      wasActiveTrade: false,
    },
  };

  function App() { return window.BotApp || {}; }
  function isActive() {
    try { return typeof activeProfile !== "undefined" && activeProfile === PROFILE; } catch (_e) { return false; }
  }
  function el(id) { return document.getElementById(id); }
  function setText(id, value) {
    const node = el(id);
    if (node) node.innerText = value == null ? "-" : String(value);
  }
  function toast(message, type) {
    try {
      if (typeof showToast === "function") showToast(message, type || "info");
    } catch (_e) {}
  }
  function currencyPayload(payload) { return payload || state.lastPayload || {}; }
  function money(value, payload) {
    try { if (typeof formatCurrencyAmount === "function") return formatCurrencyAmount(value, currencyPayload(payload)); } catch (_e) {}
    const parsed = Number(value);
    return Number.isFinite(parsed) ? `$${Math.abs(parsed).toFixed(2)}` : "—";
  }
  function signedMoney(value, payload) {
    try { if (typeof formatSignedCurrencyAmount === "function") return formatSignedCurrencyAmount(value, currencyPayload(payload)); } catch (_e) {}
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return "—";
    return `${parsed >= 0 ? "+" : "-"}$${Math.abs(parsed).toFixed(2)}`;
  }
  async function postJSON(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    let data = {};
    try { data = await res.json(); } catch (_e) {}
    return { ok: res.ok, data };
  }
  async function getJSON(url) {
    const res = await fetch(url, { method: "GET", cache: "no-store" });
    let data = {};
    try { data = await res.json(); } catch (_e) {}
    return { ok: res.ok, data };
  }
  function num(value, fallback) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }
  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }
  function normalizeMarketSymbol(symbol) {
    return String(symbol || "").trim().toUpperCase();
  }
  function readText(id, fallback) {
    const node = el(id);
    const raw = node ? String(node.value || "").trim() : "";
    return raw || fallback;
  }
  function readNumber(id, fallback) {
    return num(readText(id, ""), fallback);
  }
  function readInteger(id, fallback) {
    const value = parseInt(readText(id, ""), 10);
    return Number.isFinite(value) ? value : fallback;
  }
  function isBlankEditableValue(value) {
    return String(value == null ? "" : value).trim() === "";
  }
  function formatBarrierInputValue(value, fallback, opts) {
    const options = opts || {};
    if (options.preserveBlank && isBlankEditableValue(value)) return "";
    const safe = num(value, fallback);
    if (!Number.isFinite(safe)) return String(fallback || "+0.12");
    const absText = Math.abs(safe).toFixed(2);
    return `${safe < 0 ? "-" : "+"}${absText}`;
  }
  function formatBarrierNumber(value) {
    return formatBarrierInputValue(value, 0);
  }
  function scaleBarrierText(rawValue, factor, fallback) {
    const scaled = num(rawValue, fallback) * Number(factor || 1);
    return formatBarrierInputValue(scaled, num(fallback, 0));
  }
  function flipBarrierSignText(rawValue, fallback) {
    const flipped = -num(rawValue, fallback);
    return formatBarrierInputValue(flipped, num(fallback, 0));
  }
  function formatStakeInputValue(value, fallback, opts) {
    const options = opts || {};
    if (options.preserveBlank && isBlankEditableValue(value)) return "";
    const safe = num(value, fallback);
    if (!Number.isFinite(safe)) return String(fallback == null ? 1 : fallback);
    return String(Number(safe.toFixed(2)));
  }
  function currentSymbol() {
    const payload = state.lastPayload || {};
    const ntt = payload.ntt || {};
    const fromPayload = normalizeMarketSymbol(payload.main_symbol || payload.symbol || ntt.symbol || state.marketChart.lastSymbol);
    if (fromPayload) return fromPayload;
    const picker = el("symbol");
    return normalizeMarketSymbol(picker ? picker.value : "");
  }
  function getMarketBarrierStore() {
    const store = state.marketBarrierStore;
    return store && typeof store === "object" ? store : {};
  }
  function setMarketBarrierStore(store) {
    state.marketBarrierStore = store && typeof store === "object" ? JSON.parse(JSON.stringify(store)) : {};
  }
  function buildMarketBarrierSettings(raw) {
    const src = raw && typeof raw === "object" ? raw : {};
    const touch = formatBarrierInputValue(src.touch_barrier != null ? src.touch_barrier : "+0.12", 0.12);
    const noTouch = formatBarrierInputValue(src.no_touch_barrier != null ? src.no_touch_barrier : "+0.12", 0.12);
    const isCustom = !!src.is_custom;
    return {
      touch_barrier: touch,
      no_touch_barrier: noTouch,
      is_custom: isCustom,
    };
  }
  function buildMarketBarrierSignature(symbol, settings) {
    const sym = normalizeMarketSymbol(symbol);
    if (!sym || !settings) return "";
    const safe = buildMarketBarrierSettings(settings);
    return [
      sym,
      safe.touch_barrier,
      safe.no_touch_barrier,
      safe.is_custom ? "CUSTOM" : "DEFAULT",
    ].join("|");
  }
  function areBarrierSettingsEqual(leftValue, rightValue) {
    const left = buildMarketBarrierSettings(leftValue);
    const right = buildMarketBarrierSettings(rightValue);
    return left.touch_barrier === right.touch_barrier && left.no_touch_barrier === right.no_touch_barrier;
  }
  function getSavedMarketBarrierSettings(symbol) {
    const sym = normalizeMarketSymbol(symbol);
    if (!sym) return null;
    const store = getMarketBarrierStore();
    if (!store || !store[sym]) return null;
    return buildMarketBarrierSettings(store[sym]);
  }
  function persistMarketBarrierSettings(symbol, settings, opts) {
    const sym = normalizeMarketSymbol(symbol);
    if (!sym || !settings) return null;
    const store = getMarketBarrierStore();
    const current = buildMarketBarrierSettings(store[sym] || {});
    const options = opts || {};
    const next = buildMarketBarrierSettings(Object.assign({}, current, settings, {
      is_custom: typeof options.custom === "boolean" ? options.custom : current.is_custom,
    }));
    store[sym] = next;
    setMarketBarrierStore(store);
    return next;
  }
  function readCurrentMarketBarrierSettings() {
    const form = readForm();
    return buildMarketBarrierSettings(form);
  }
  function getPayloadMarketBarrierSettings(ntt) {
    if (!ntt) return null;
    return buildMarketBarrierSettings({
      touch_barrier: ntt.touch_barrier,
      no_touch_barrier: ntt.no_touch_barrier,
    });
  }
  function persistCurrentMarketBarrierSettings(symbolOverride, opts) {
    const sym = normalizeMarketSymbol(symbolOverride || currentSymbol());
    if (!sym) return null;
    return persistMarketBarrierSettings(sym, readCurrentMarketBarrierSettings(), opts);
  }
  function seedMarketBarrierSettingsFromPayload(symbol, ntt, opts) {
    const sym = normalizeMarketSymbol(symbol);
    if (!sym || !ntt) return null;
    const options = opts || {};
    const existing = getSavedMarketBarrierSettings(sym);
    const payloadSettings = getPayloadMarketBarrierSettings(ntt);
    if (!payloadSettings) return existing;
    if (!existing) {
      return persistMarketBarrierSettings(sym, payloadSettings, { custom: false });
    }
    if (options.preferPayload) {
      return persistMarketBarrierSettings(sym, payloadSettings, { custom: false });
    }
    if (existing.is_custom) return existing;
    return existing;
  }
  function applySavedMarketBarrierSettingsToForm(settings, force) {
    if (!settings) return;
    const safe = buildMarketBarrierSettings(settings);
    setValueIfAllowed("nttTouchBarrier", safe.touch_barrier, !!force);
    setValueIfAllowed("nttNoTouchBarrier", safe.no_touch_barrier, !!force);
  }
  async function syncSavedMarketBarrierSettingsToServer(symbol, settings) {
    const sym = normalizeMarketSymbol(symbol);
    if (!sym || !settings) return null;
    if (sym !== currentSymbol()) return null;
    const normalized = buildMarketBarrierSettings(settings);
    if (!normalized.is_custom) return { ok: true, skipped: true };
    const nextSignature = buildMarketBarrierSignature(sym, normalized);
    if (!nextSignature) return null;
    const payload = state.lastPayload && (state.lastPayload.ntt || state.lastPayload);
    const currentSignature = buildMarketBarrierSignature(sym, getPayloadMarketBarrierSettings(payload));
    if (currentSignature === nextSignature) return { ok: true, skipped: true };
    if (state.marketBarrierSyncInFlight && state.marketBarrierSyncSignature === nextSignature) {
      return { ok: true, skipped: true };
    }
    state.marketBarrierSyncInFlight = true;
    state.marketBarrierSyncSignature = nextSignature;
    try {
      const res = await postJSON("/ntt_settings", normalized);
      if (res && res.ok && res.data) renderPayload(res.data, { forceForm: false });
      return res;
    } catch (_e) {
      return null;
    } finally {
      state.marketBarrierSyncInFlight = false;
    }
  }
  function scheduleCurrentMarketBarrierSync(symbolOverride, opts) {
    const sym = normalizeMarketSymbol(symbolOverride || currentSymbol());
    if (!sym) return;
    const savedNow = persistCurrentMarketBarrierSettings(sym, opts);
    if (state.marketBarrierSyncTimer) {
      clearTimeout(state.marketBarrierSyncTimer);
      state.marketBarrierSyncTimer = null;
    }
    if (!(savedNow && savedNow.is_custom)) return;
    state.marketBarrierSyncTimer = setTimeout(() => {
      state.marketBarrierSyncTimer = null;
      const current = currentSymbol();
      if (sym !== current) return;
      const saved = getSavedMarketBarrierSettings(sym);
      if (!(saved && saved.is_custom)) return;
      syncSavedMarketBarrierSettingsToServer(sym, saved).catch(() => {});
    }, 180);
  }
  function hasDirtyBarrierFields() {
    let anyDirty = false;
    for (const id of BARRIER_FIELD_IDS) {
      if (state.dirtyFields.has(id)) {
        anyDirty = true;
        break;
      }
    }
    if (!anyDirty) return false;
    const payload = state.lastPayload && (state.lastPayload.ntt || state.lastPayload);
    const payloadSettings = getPayloadMarketBarrierSettings(payload);
    if (!payloadSettings) return true;
    return !areBarrierSettingsEqual(readCurrentMarketBarrierSettings(), payloadSettings);
  }
  window.addEventListener("bot-transient-reset", () => {
    state.marketBarrierStore = {};
    state.lastBarrierKey = null;
    state.marketBarrierSyncSignature = "";
  });
  function readForm() {
    const koolkidReversalToggle = el("nttKoolkidReversalToggle");
    const koolkidHalfBarrierToggle = el("nttKoolkidHalfBarrierToggle");
    const koolkidSimSideRaw = readText("nttKoolkidTntSimSide", "AUTO").toUpperCase();
    const useSharedDuration = !!(el("nttUseSharedDuration") ? el("nttUseSharedDuration").checked : true);
    return {
      symbol: currentSymbol(),
      touch_stake: readNumber("nttTouchStake", 1.0),
      no_touch_stake: readNumber("nttNoTouchStake", readNumber("nttTouchStake", 1.0)),
      touch_barrier: formatBarrierInputValue(readText("nttTouchBarrier", "+0.12"), 0.12),
      no_touch_barrier: formatBarrierInputValue(readText("nttNoTouchBarrier", "+0.12"), 0.12),
      use_shared_duration: useSharedDuration,
      koolkid_touch_barrier: formatBarrierInputValue(readText("nttKoolkidTouchBarrier", "+0.06"), 0.06),
      koolkid_no_touch_barrier: formatBarrierInputValue(readText("nttKoolkidNoTouchBarrier", "+0.06"), 0.06),
      koolkid_sim_duration: Math.max(1, Math.min(59, readInteger("nttKoolkidSimDuration", 15))),
      koolkid_sim_duration_unit: readText("nttKoolkidSimDurationUnit", "s"),
      koolkid_live_duration: Math.max(1, Math.min(59, readInteger("nttKoolkidLiveDuration", 5))),
      koolkid_live_duration_unit: readText("nttKoolkidLiveDurationUnit", "t"),
      koolkid_hl_loss_trigger_pct: Math.max(50, Math.min(70, readInteger("nttKoolkidTntLossPct", 50))),
      koolkid_hl_sim_side: koolkidSimSideRaw === "TOUCH" || koolkidSimSideRaw === "NO_TOUCH" ? koolkidSimSideRaw : "AUTO",
      koolkid_reversal_enabled: koolkidReversalToggle ? !!koolkidReversalToggle.checked : !!state.koolkid_reversal_enabled,
      koolkid_half_barrier_enabled: koolkidHalfBarrierToggle ? !!koolkidHalfBarrierToggle.checked : !!state.koolkid_half_barrier_enabled,
      duration: readInteger("nttDuration", 5),
      duration_unit: readText("nttDurationUnit", "t"),
      touch_duration: readInteger("nttTouchDuration", 5),
      touch_duration_unit: readText("nttTouchDurationUnit", "t"),
      no_touch_duration: readInteger("nttNoTouchDuration", 5),
      no_touch_duration_unit: readText("nttNoTouchDurationUnit", "t"),
      tp: readNumber("nttTp", 0.0),
      sl: readNumber("nttSl", 0.0),
      auto_sl: !!state.auto_sl,
    };
  }
  function markDirty(id) {
    if (id) state.dirtyFields.add(id);
  }
  function clearDirty(ids) {
    if (!ids) {
      state.dirtyFields.clear();
      return;
    }
    ids.forEach((id) => state.dirtyFields.delete(id));
  }
  function setValueIfAllowed(id, value, force) {
    const node = el(id);
    if (!node) return;
    if (!force && (state.dirtyFields.has(id) || document.activeElement === node)) return;
    node.value = value == null ? "" : String(value);
  }
  function applyDurationPresets(durationId, unitId, preferredValue) {
    const unitNode = el(unitId);
    const durationNode = el(durationId);
    if (!unitNode || !durationNode) return;
    const unit = String(unitNode.value || "t").toLowerCase();
    const options = DURATION_PRESETS[unit] || DURATION_PRESETS.t;
    const existing = String(preferredValue != null ? preferredValue : durationNode.value || "");
    durationNode.innerHTML = options.map((value) => `<option value="${value}">${value}</option>`).join("");
    const desired = options.includes(Number(existing)) ? String(Number(existing)) : String(options[0]);
    durationNode.value = desired;
  }
  function usesSharedDuration(safe) {
    if (safe && typeof safe.use_shared_duration !== "undefined") return !!safe.use_shared_duration;
    const node = el("nttUseSharedDuration");
    return node ? !!node.checked : true;
  }
  function updateDurationModeUI(force) {
    const sharedEnabled = usesSharedDuration();
    const touchWrap = el("nttTouchDurationWrap");
    const noTouchWrap = el("nttNoTouchDurationWrap");
    const modeLabel = el("nttDurationModeLabel");
    const sharedDuration = el("nttDuration");
    const sharedUnit = el("nttDurationUnit");
    const touchDuration = el("nttTouchDuration");
    const touchUnit = el("nttTouchDurationUnit");
    const noTouchDuration = el("nttNoTouchDuration");
    const noTouchUnit = el("nttNoTouchDurationUnit");
    if (touchWrap) touchWrap.style.display = sharedEnabled ? "none" : "grid";
    if (noTouchWrap) noTouchWrap.style.display = sharedEnabled ? "none" : "grid";
    if (modeLabel) {
      modeLabel.innerText = sharedEnabled
        ? "Both trades use the shared duration."
        : "Each side now uses its own saved duration.";
      modeLabel.style.color = sharedEnabled ? "#94a3b8" : "#67e8f9";
    }
    [sharedDuration, sharedUnit].forEach((node) => {
      if (!node) return;
      node.disabled = !sharedEnabled;
      node.style.opacity = sharedEnabled ? "1" : "0.55";
    });
    [touchDuration, touchUnit, noTouchDuration, noTouchUnit].forEach((node) => {
      if (!node) return;
      node.disabled = sharedEnabled;
      node.style.opacity = sharedEnabled ? "0.65" : "1";
    });
    if (force) {
      if (sharedEnabled) {
        applyDurationPresets("nttDuration", "nttDurationUnit", readInteger("nttDuration", 5));
      } else {
        applyDurationPresets("nttTouchDuration", "nttTouchDurationUnit", readInteger("nttTouchDuration", 5));
        applyDurationPresets("nttNoTouchDuration", "nttNoTouchDurationUnit", readInteger("nttNoTouchDuration", 5));
      }
    }
  }
  function applyAutoSlBtn() {
    const btn = el("nttAutoSlBtn");
    if (!btn) return;
    btn.innerText = state.auto_sl ? "AUTO SL: ON" : "AUTO SL: OFF";
    btn.style.background = state.auto_sl ? "#facc15" : "#64748b";
    btn.style.color = state.auto_sl ? "#111827" : "#f8fafc";
  }
  function applyKoolkidReversalToggle() {
    const toggle = el("nttKoolkidReversalToggle");
    const label = el("nttKoolkidReversalState");
    if (toggle) toggle.checked = !!state.koolkid_reversal_enabled;
    if (label) label.innerText = state.koolkid_reversal_enabled ? "ON" : "OFF";
  }
  function applyKoolkidHalfBarrierToggle() {
    const toggle = el("nttKoolkidHalfBarrierToggle");
    const label = el("nttKoolkidHalfBarrierState");
    if (toggle) toggle.checked = !!state.koolkid_half_barrier_enabled;
    if (label) label.innerText = state.koolkid_half_barrier_enabled ? "ON" : "OFF";
  }
  function fillForm(ntt, force, opts) {
    const safe = ntt || {};
    const options = opts || {};
    const barrierForce = !!force || !!options.forceBarriers;
    const barrierOnly = !!options.barrierOnly;
    const protectSharedDurationFields = !force && (state.dirtyFields.has("nttDuration") || state.dirtyFields.has("nttDurationUnit"));
    const protectTouchDurationFields = !force && (state.dirtyFields.has("nttTouchDuration") || state.dirtyFields.has("nttTouchDurationUnit"));
    const protectNoTouchDurationFields = !force && (state.dirtyFields.has("nttNoTouchDuration") || state.dirtyFields.has("nttNoTouchDurationUnit"));
    if (barrierOnly) {
      setValueIfAllowed("nttTouchBarrier", safe.touch_barrier || "+0.12", true);
      setValueIfAllowed("nttNoTouchBarrier", safe.no_touch_barrier || "+0.12", true);
      return;
    }
    const touchStakeValue = formatStakeInputValue(safe.touch_stake, 1);
    const noTouchStakeValue = formatStakeInputValue(safe.no_touch_stake, num(safe.touch_stake, 1));
    setValueIfAllowed("nttTouchStake", touchStakeValue, force);
    setValueIfAllowed("nttNoTouchStake", noTouchStakeValue, force);
    setValueIfAllowed("nttTouchBarrier", safe.touch_barrier || "+0.12", barrierForce);
    setValueIfAllowed("nttNoTouchBarrier", safe.no_touch_barrier || "+0.12", barrierForce);
    setValueIfAllowed("nttKoolkidTouchBarrier", safe.koolkid_touch_barrier || safe.touch_barrier || "+0.06", force);
    setValueIfAllowed("nttKoolkidNoTouchBarrier", safe.koolkid_no_touch_barrier || safe.no_touch_barrier || "+0.06", force);
    setValueIfAllowed("nttKoolkidSimDuration", safe.koolkid_sim_duration || 15, force);
    setValueIfAllowed("nttKoolkidSimDurationUnit", safe.koolkid_sim_duration_unit || "s", force);
    setValueIfAllowed("nttKoolkidLiveDuration", safe.koolkid_live_duration || 5, force);
    setValueIfAllowed("nttKoolkidLiveDurationUnit", safe.koolkid_live_duration_unit || "t", force);
    setValueIfAllowed("nttKoolkidTntLossPct", safe.koolkid_hl_loss_trigger_pct || 50, force);
    setValueIfAllowed("nttKoolkidTntSimSide", safe.koolkid_hl_sim_side || "AUTO", force);
    const sharedToggle = el("nttUseSharedDuration");
    if (sharedToggle && (force || !state.dirtyFields.has("nttUseSharedDuration"))) {
      sharedToggle.checked = typeof safe.use_shared_duration === "undefined" ? true : !!safe.use_shared_duration;
    }
    if (!protectSharedDurationFields) {
      setValueIfAllowed("nttDurationUnit", safe.duration_unit || "t", force);
      applyDurationPresets("nttDuration", "nttDurationUnit", safe.duration || 5);
      setValueIfAllowed("nttDuration", safe.duration || 5, force);
    } else {
      applyDurationPresets("nttDuration", "nttDurationUnit", readInteger("nttDuration", safe.duration || 5));
    }
    if (!protectTouchDurationFields) {
      setValueIfAllowed("nttTouchDurationUnit", safe.touch_duration_unit || safe.duration_unit || "t", force);
      applyDurationPresets("nttTouchDuration", "nttTouchDurationUnit", safe.touch_duration || safe.duration || 5);
      setValueIfAllowed("nttTouchDuration", safe.touch_duration || safe.duration || 5, force);
    } else {
      applyDurationPresets("nttTouchDuration", "nttTouchDurationUnit", readInteger("nttTouchDuration", safe.touch_duration || safe.duration || 5));
    }
    if (!protectNoTouchDurationFields) {
      setValueIfAllowed("nttNoTouchDurationUnit", safe.no_touch_duration_unit || safe.duration_unit || "t", force);
      applyDurationPresets("nttNoTouchDuration", "nttNoTouchDurationUnit", safe.no_touch_duration || safe.duration || 5);
      setValueIfAllowed("nttNoTouchDuration", safe.no_touch_duration || safe.duration || 5, force);
    } else {
      applyDurationPresets("nttNoTouchDuration", "nttNoTouchDurationUnit", readInteger("nttNoTouchDuration", safe.no_touch_duration || safe.duration || 5));
    }
    setValueIfAllowed("nttTp", num(safe.tp, 0), force);
    setValueIfAllowed("nttSl", num(safe.sl, 0), force);
    state.auto_sl = !!safe.auto_sl;
    state.koolkid_reversal_enabled = !!safe.koolkid_reversal_enabled;
    state.koolkid_half_barrier_enabled = !!safe.koolkid_half_barrier_enabled;
    if (force || !state.dirtyFields.has("nttNoTouchStake")) {
      state.noTouchStakeCustom = Number(num(safe.no_touch_stake, 1)) !== Number(num(safe.touch_stake, 1));
    }
    applyAutoSlBtn();
    applyKoolkidReversalToggle();
    applyKoolkidHalfBarrierToggle();
    updateDurationModeUI(true);
    if (force) {
      clearDirty([
        "nttTouchStake", "nttNoTouchStake", "nttTouchBarrier", "nttNoTouchBarrier",
        "nttUseSharedDuration", "nttTouchDuration", "nttTouchDurationUnit", "nttNoTouchDuration", "nttNoTouchDurationUnit",
        "nttKoolkidTouchBarrier", "nttKoolkidNoTouchBarrier", "nttKoolkidSimDuration",
        "nttKoolkidSimDurationUnit", "nttKoolkidLiveDuration", "nttKoolkidLiveDurationUnit",
        "nttKoolkidTntLossPct", "nttKoolkidTntSimSide", "nttDuration", "nttDurationUnit", "nttTp", "nttSl"
      ]);
    }
  }
  function syncNoTouchStakeFromTouch(force) {
    if (!force && state.noTouchStakeCustom) return;
    const touchNode = el("nttTouchStake");
    const noTouchNode = el("nttNoTouchStake");
    if (!touchNode || !noTouchNode) return;
    const mirrored = String(touchNode.value || "");
    noTouchNode.value = mirrored;
    if (force) {
      state.noTouchStakeCustom = false;
    }
  }
  function updateNoTouchStakeCustomFlag() {
    const touchRaw = readText("nttTouchStake", "");
    const noTouchRaw = readText("nttNoTouchStake", "");
    if (!noTouchRaw) {
      state.noTouchStakeCustom = false;
      return;
    }
    if (!touchRaw) {
      state.noTouchStakeCustom = true;
      return;
    }
    const touchValue = Number(touchRaw);
    const noTouchValue = Number(noTouchRaw);
    if (Number.isFinite(touchValue) && Number.isFinite(noTouchValue)) {
      state.noTouchStakeCustom = Math.abs(touchValue - noTouchValue) > 0.000001;
      return;
    }
    state.noTouchStakeCustom = touchRaw !== noTouchRaw;
  }
  function renderStatusChip(ntt) {
    const chip = el("nttStatusChip");
    if (!chip) return;
    const risk = String((ntt && ntt.risk_block_reason) || "").trim();
    const activeCount = Number((ntt && ntt.active_count) || 0);
    if (risk) {
      chip.innerText = `RISK BLOCK: ${risk}`;
      chip.style.borderColor = "rgba(239,68,68,0.32)";
      chip.style.background = "rgba(127,29,29,0.35)";
      chip.style.color = "#fecaca";
      return;
    }
    if (activeCount > 0) {
      chip.innerText = `${activeCount} ACTIVE TRADE${activeCount === 1 ? "" : "S"}`;
      chip.style.borderColor = "rgba(34,197,94,0.32)";
      chip.style.background = "rgba(20,83,45,0.35)";
      chip.style.color = "#dcfce7";
      return;
    }
    chip.innerText = "READY";
    chip.style.borderColor = "rgba(34,211,238,0.22)";
    chip.style.background = "rgba(8,47,73,0.42)";
    chip.style.color = "#cffafe";
  }
  function renderRiskBlock(ntt) {
    const block = el("nttRiskBlock");
    if (!block) return;
    const reason = String((ntt && ntt.risk_block_reason) || "").trim();
    if (!reason) {
      block.style.display = "none";
      block.innerText = "";
      return;
    }
    block.style.display = "block";
    block.innerText = `Trading blocked: ${reason}`;
  }
  function renderBias(ntt) {
    const bias = (ntt && ntt.bias) || {};
    const touchPct = num(bias.touch_pct != null ? bias.touch_pct : bias.higher_pct, 50);
    const noTouchPct = num(bias.no_touch_pct != null ? bias.no_touch_pct : bias.lower_pct, 50);
    const dominant = touchPct >= noTouchPct ? "TOUCH" : "NO TOUCH";
    setText("nttTouchBiasPct", `${touchPct.toFixed(1)}%`);
    setText("nttNoTouchBiasPct", `${noTouchPct.toFixed(1)}%`);
    setText("nttBiasStrength", bias.strength || "Building");
    setText("nttBiasHeadline", `${dominant} BIAS ${Math.max(touchPct, noTouchPct).toFixed(1)}%`);
    setText("nttBiasSub", bias.summary || "Gathering enough recent ticks to score Touch vs No Touch.");
    const reasonsNode = el("nttBiasReasons");
    if (reasonsNode) {
      const reasons = Array.isArray(bias.reasons) ? bias.reasons : [];
      reasonsNode.innerHTML = reasons.length
        ? reasons.slice(0, 5).map((reason) => `<span class="ntt-reason-chip">${escapeHtml(String(reason))}</span>`).join("")
        : '<span class="ntt-reason-chip">Waiting for data</span>';
    }
  }
  function formatPredictionDurationLabel(duration, unit) {
    const value = Number(duration || 0);
    const safeUnit = String(unit || "t").toLowerCase();
    if (safeUnit === "m") return `${value} minute${value === 1 ? "" : "s"}`;
    if (safeUnit === "h") return `${value} hour${value === 1 ? "" : "s"}`;
    return `${value} tick${value === 1 ? "" : "s"}`;
  }
  function getSelectorReasoningLine(payload) {
    const contractType = String(payload && payload.chosen_contract_type || "").toUpperCase();
    if (contractType === "TOUCH / NO TOUCH") {
      const model = payload && payload.touch_no_touch_model || {};
      const preferred = String(model.preferred_side || "").toUpperCase();
      const sim = model && model.simulation || {};
      const barrierRatio = num(payload && payload.market_context && payload.market_context.barrier_distance_ratio, NaN);
      let barrierText = "Barrier mixed";
      if (Number.isFinite(barrierRatio)) {
        barrierText = preferred === "TOUCH"
          ? (barrierRatio <= 1 ? "Barrier close" : "Barrier reachable")
          : (barrierRatio >= 1 ? "Barrier safer" : "Barrier still close");
      }
      const speedScore = num(model && model.score_breakdown && model.score_breakdown.speed_push && (preferred === "TOUCH" ? model.score_breakdown.speed_push.touch_score : model.score_breakdown.speed_push.no_touch_score), 50);
      const flowText = preferred === "TOUCH"
        ? (speedScore >= 68 ? "Market fast" : "Push building")
        : (speedScore >= 62 ? "Market calm" : "Escape building");
      const simScore = preferred === "TOUCH" ? num(sim.touch_win_rate, 50) : num(sim.no_touch_win_rate, 50);
      const simText = simScore >= 60 ? "Sim agrees" : "Sim mixed";
      return `${barrierText} • ${flowText} • ${simText}`;
    }
    const model = payload && payload.higher_lower_model || {};
    const preferred = String(model.preferred_side || "").toUpperCase();
    const breakdown = model && model.score_breakdown || {};
    const direction = num(breakdown.direction && (preferred === "LOWER" ? breakdown.direction.lower_score : breakdown.direction.higher_score), 50);
    const strength = num(breakdown.strength && (preferred === "LOWER" ? breakdown.strength.lower_score : breakdown.strength.higher_score), 50);
    const sim = model && model.simulation || {};
    const simScore = preferred === "LOWER" ? num(sim.lower_win_rate, 50) : num(sim.higher_win_rate, 50);
    const trendText = preferred === "LOWER"
      ? (direction >= 68 || strength >= 68 ? "Trend heavy" : "Trend leaning down")
      : (direction >= 68 || strength >= 68 ? "Trend strong" : "Trend leaning up");
    const finishText = strength >= 62 ? "Expiry cleaner" : "Finish still building";
    const simText = simScore >= 60 ? "Sim agrees" : "Sim mixed";
    return `${trendText} • ${finishText} • ${simText}`;
  }
  function getTouchNoTouchModelReason(payload) {
    const model = payload && payload.touch_no_touch_model || {};
    const preferred = String(model.preferred_side || "").toUpperCase();
    const sim = model && model.simulation || {};
    const barrierRatio = num(payload && payload.market_context && payload.market_context.barrier_distance_ratio, NaN);
    let barrierText = "Barrier mixed";
    if (Number.isFinite(barrierRatio)) {
      if (barrierRatio <= 0.5) barrierText = preferred === "TOUCH" ? "Barrier close" : "Barrier avoidable";
      else if (barrierRatio <= 1.05) barrierText = preferred === "TOUCH" ? "Barrier reachable" : "Barrier steady";
      else barrierText = preferred === "TOUCH" ? "Barrier far" : "Barrier wide";
    }
    const simScore = preferred === "NO_TOUCH" ? num(sim.no_touch_win_rate, 50) : num(sim.touch_win_rate, 50);
    const flowText = preferred === "TOUCH" ? "Push building" : "Calm path";
    const simText = simScore >= 60 ? "Sim agrees" : "Sim mixed";
    return `${barrierText} • ${flowText} • ${simText}`;
  }
  function renderNttAutoAnalysis(prediction) {
    const card = el("nttAutoAnalysisCard");
    const primary = el("nttAnalysisPrimaryAction");
    if (!card) return;
    const ok = prediction && prediction.status === "success";
    if (!ok) {
      card.className = "card ntt-analysis-panel";
      setText("nttAnalysisDirectionIcon", "↑");
      setText("nttAnalysisDirection", "SCANNING");
      setText("nttAnalysisDuration", "NEXT --");
      setText("nttAnalysisPct", "--");
      setText("nttAnalysisConfidence", "SKIP");
      setText("nttAnalysisLead", prediction && prediction.message ? String(prediction.message) : "Waiting for enough recent ticks to score Touch versus No Touch.");
      setText("nttAnalysisReason", "Reading barrier distance, push, persistence, simulation, and market quality.");
      setText("nttAnalysisMeterValue", "0%");
      const idleFill = el("nttAnalysisMeterFill");
      if (idleFill) idleFill.style.width = "0%";
      if (primary) {
        primary.innerText = "SCANNING";
        primary.dataset.analysisSide = "TOUCH";
        primary.dataset.tradeValid = "0";
        primary.disabled = true;
      }
      return;
    }

    const touch = num(prediction.touch_pct, 0);
    const noTouch = num(prediction.no_touch_pct, 0);
    const side = noTouch > touch ? "NO_TOUCH" : "TOUCH";
    const dominantPct = side === "NO_TOUCH" ? noTouch : touch;
    const confidence = String(prediction.confidence_label || "Skip").toUpperCase();
    const valid = !!prediction.model_valid;
    const durationLabel = formatPredictionDurationLabel(prediction && prediction.duration, prediction && prediction.duration_unit);
    const lead = `Next ${durationLabel} predicted to ${side === "NO_TOUCH" ? "avoid touching" : "reach"} the barrier.`;
    const reason = getTouchNoTouchModelReason({ touch_no_touch_model: prediction, market_context: prediction.market_context || {} });

    card.className = `card ntt-analysis-panel ${valid ? (side === "NO_TOUCH" ? "is-no-touch" : "is-touch") : ""}`.trim();
    setText("nttAnalysisDirectionIcon", side === "NO_TOUCH" ? "↓" : "↑");
    setText("nttAnalysisDirection", side === "NO_TOUCH" ? "NO TOUCH" : "TOUCH");
    setText("nttAnalysisDuration", `NEXT ${String(durationLabel || "--").toUpperCase()}`);
    setText("nttAnalysisPct", `${Math.max(0, Math.min(100, dominantPct)).toFixed(0)}%`);
    setText("nttAnalysisConfidence", confidence);
    setText("nttAnalysisLead", lead);
    setText("nttAnalysisReason", reason);
    setText("nttAnalysisMeterValue", `${Math.max(0, Math.min(100, dominantPct)).toFixed(0)}%`);
    const fill = el("nttAnalysisMeterFill");
    if (fill) fill.style.width = `${Math.max(0, Math.min(100, dominantPct))}%`;
    if (primary) {
      primary.innerText = valid ? `TAKE ${side === "NO_TOUCH" ? "NO TOUCH" : "TOUCH"}` : `WATCH ${side === "NO_TOUCH" ? "NO TOUCH" : "TOUCH"}`;
      primary.dataset.analysisSide = side;
      primary.dataset.tradeValid = valid ? "1" : "0";
      primary.disabled = !valid;
    }
  }
  function renderTouchPrediction(prediction) {
    const card = el("nttContractSelectorCard");
    const primary = el("nttSelectorPrimaryAction");
    if (!card) return;
    const ok = prediction && prediction.status === "success";
    const tntModel = ok && prediction.touch_no_touch_model && typeof prediction.touch_no_touch_model === "object"
      ? prediction.touch_no_touch_model
      : {};
    const touchPct = ok ? num(tntModel.touch_pct, 50) : 0;
    const noTouchPct = ok ? num(tntModel.no_touch_pct, 50) : 0;
    const side = ok
      ? String(tntModel.preferred_side || (touchPct >= noTouchPct ? "TOUCH" : "NO_TOUCH")).toUpperCase()
      : "SKIP";
    const tradeConfidence = ok ? num(prediction.tnt_confidence || tntModel.model_confidence, 0) : 0;
    const modeLabel = "TOUCH / NO TOUCH";
    const confidenceLabel = String((tntModel && tntModel.confidence_label) || (prediction && prediction.confidence_label) || "Skip").toUpperCase();
    const tradeValid = ok && !!tntModel.model_valid;
    const primaryLabel = ok
      ? (side === "NO_TOUCH" ? (tradeValid ? "TAKE NO TOUCH" : "WATCH NO TOUCH") : (tradeValid ? "TAKE TOUCH" : "WATCH TOUCH"))
      : "SCANNING";
    card.className = `card contract-selector-panel ${ok ? "is-tnt" : "is-skip"}`;
    setText("nttSelectorKicker", "SELECTED CONTRACT");
    setText("nttSelectorModePill", modeLabel);
    setText("nttSelectorHlConfidence", `TOUCH: ${Math.max(0, Math.min(100, touchPct)).toFixed(0)}%`);
    setText("nttSelectorTntConfidence", `NO TOUCH: ${Math.max(0, Math.min(100, noTouchPct)).toFixed(0)}%`);
    setText("nttSelectorContractType", "TOUCH / NO TOUCH");
    setText("nttSelectorTradeConfidence", `${tradeConfidence.toFixed(0)}%`);
    setText("nttSelectorConfidenceLabel", `(${confidenceLabel})`);
    setText("nttSelectorReasoning", ok
      ? String(tntModel.reasoning_summary || tntModel.summary || getSelectorReasoningLine(prediction) || "Waiting for cleaner Touch / No Touch structure.")
      : "Waiting for enough recent ticks to score Touch versus No Touch.");
    const fill = el("nttSelectorProgressFill");
    if (fill) fill.style.width = `${Math.max(0, Math.min(100, tradeConfidence))}%`;
    if (primary) {
      primary.innerText = primaryLabel;
      primary.dataset.selectorContractType = "TOUCH / NO TOUCH";
      primary.dataset.selectorSide = side;
      primary.dataset.tradeValid = tradeValid ? "1" : "0";
      primary.disabled = !tradeValid;
    }
  }
  function formatKoolkidDurationText(value, unit) {
    const safeUnit = String(unit || "s").toLowerCase();
    const amount = Math.max(0, parseInt(value, 10) || 0);
    if (safeUnit === "t") return `${amount}T`;
    if (safeUnit === "m") return `${amount}m`;
    return `${amount}s`;
  }
  function renderKoolkid(ntt) {
    const data = (ntt && ntt.koolkid_hl) || {};
    const bothData = (ntt && ntt.koolkid_both) || {};
    const sim = data && typeof data.simulation === "object" ? data.simulation : null;
    const bothSim = bothData && typeof bothData.simulation === "object" ? bothData.simulation : null;
    const isEnabled = !!data.enabled;
    const isBothEnabled = !!bothData.enabled;
    const anyEnabled = isEnabled || isBothEnabled;
    state.koolkid_reversal_enabled = !!((ntt && ntt.koolkid_reversal_enabled) || data.reversal_enabled);
    state.koolkid_half_barrier_enabled = !!((ntt && ntt.koolkid_half_barrier_enabled) || data.half_barrier_enabled || bothData.half_barrier_enabled);
    applyKoolkidReversalToggle();
    applyKoolkidHalfBarrierToggle();

    const panelBtn = el("nttKoolkidBtn");
    if (panelBtn) {
      panelBtn.innerText = `KOOLKID: ${anyEnabled ? "ON" : "OFF"}`;
      panelBtn.style.background = anyEnabled ? "#1d4ed8" : "#2563eb";
      panelBtn.style.color = "#eff6ff";
    }
    const modal = el("nttKoolkidBody");
    if (modal) modal.style.display = state.koolkidPanelOpen ? "flex" : "none";

    const tntBtn = el("nttKoolkidTntBtn");
    if (tntBtn) {
      tntBtn.innerText = `🎯 TOUCH / NO TOUCH: ${isEnabled ? "ON" : "OFF"}`;
      tntBtn.style.background = isEnabled ? "#22c55e" : "#1d4ed8";
      tntBtn.style.color = isEnabled ? "#052e16" : "#eff6ff";
    }
    const bothBtn = el("nttKoolkidBothBtn");
    if (bothBtn) {
      bothBtn.innerText = `⚖️ BOTH: ${isBothEnabled ? "ON" : "OFF"}`;
      bothBtn.style.background = isBothEnabled ? "#f59e0b" : "#475569";
      bothBtn.style.color = isBothEnabled ? "#111827" : "#e2e8f0";
    }
    const status = el("nttKoolkidStatus");
    if (!status) return;
    if (bothSim && bothSim.active) {
      const touchRow = (bothSim.sides || []).find((item) => String((item && item.side) || "").toUpperCase() === "TOUCH") || null;
      const noTouchRow = (bothSim.sides || []).find((item) => String((item && item.side) || "").toUpperCase() === "NO_TOUCH") || null;
      const touchPct = Number(touchRow && touchRow.profit_pct);
      const noTouchPct = Number(noTouchRow && noTouchRow.profit_pct);
      status.innerText =
        `Paper BOTH sim • TOUCH ${Number.isFinite(touchPct) ? `${touchPct >= 0 ? "+" : ""}${touchPct.toFixed(0)}%` : "—"} • ` +
        `NO TOUCH ${Number.isFinite(noTouchPct) ? `${noTouchPct >= 0 ? "+" : ""}${noTouchPct.toFixed(0)}%` : "—"} • ` +
        `${formatKoolkidDurationText(bothSim.countdown_remaining || 0, bothSim.countdown_unit || "s")} left • ` +
        `${Number(bothSim.check_remaining || 0) > 0 ? `decision in ${formatKoolkidDurationText(bothSim.check_remaining, bothSim.countdown_unit || "s")}` : "checking now"} • ` +
        `sim ${formatKoolkidDurationText(bothSim.duration || bothData.simulation_duration || 0, bothSim.duration_unit || bothData.simulation_duration_unit || "s")} • ` +
        `leader ${String(bothSim.leading_side || "—").replace("_", " ")} • live BOTH uses your saved Mutant stakes and KOOLKID barriers.`;
      status.style.color = "#fcd34d";
      return;
    }
    if (sim && sim.active) {
      const estValue = Number(sim.estimated_value);
      const estPnl = Number(sim.estimated_pnl);
      status.innerText =
        `Paper ${String(sim.side || "—").replace("_", " ")} sim live ${Number.isFinite(estValue) ? money(estValue, sim) : "—"} ` +
        `(${Number.isFinite(estPnl) ? signedMoney(estPnl, sim) : "—"}) • ` +
        `${formatKoolkidDurationText(sim.countdown_remaining || 0, sim.countdown_unit || "s")} left • ` +
        `${Number(sim.check_remaining || 0) > 0 ? `decision in ${formatKoolkidDurationText(sim.check_remaining, sim.countdown_unit || "s")}` : "checking now"} • ` +
        `needs ${Number(sim.loss_trigger_pct || data.loss_trigger_pct || 50).toFixed(0)}% loss • ` +
        `live ${String(sim.opposite_side || "—").replace("_", " ")} ${formatKoolkidDurationText(sim.live_duration || 5, sim.live_duration_unit || data.live_duration_unit || "t")} will use ${sim.live_barrier || "—"}.`;
      status.style.color = "#93c5fd";
      return;
    }
    if (isBothEnabled) {
      status.innerText = String(bothData.last_reason || "KOOLKID Both is waiting for a dual paper trade setup.");
      status.style.color = "#fcd34d";
      return;
    }
    status.innerText = String(data.last_reason || "KOOLKID Touch / No Touch is waiting for a weaker-side paper trade setup.");
    status.style.color = isEnabled ? "#93c5fd" : "#cbd5e1";
  }
  function renderAutoBoth(ntt) {
    const data = (ntt && ntt.auto_both) || {};
    const btn = el("nttAutoBothBtn");
    if (!btn) return;
    const enabled = !!data.enabled;
    const label = String(data.label || (enabled ? "ARMED" : "OFF")).toUpperCase();
    btn.innerHTML = `
      <span style="display:block;font-weight:900;">🤖 AUTO</span>
      <span style="display:block;font-size:11px;font-weight:700;opacity:.92;margin-top:4px;">${escapeHtml(label)}</span>
    `;
    btn.style.background = enabled ? "#0f766e" : "#155e75";
    btn.style.color = "#ecfeff";
    btn.title = String(data.last_reason || "Mutant AUTO is OFF.");
    renderAutoBothPanel(data);
  }
  function syncAutoBothPanelInputs(data, force) {
    const safe = data || {};
    const shouldForce = !!force;
    const barrierNode = el("nttAutoBarrier");
    const budgetNode = el("nttAutoBudget");
    const martingaleNode = el("nttAutoMartingaleToggle");
    const step50Node = el("nttAutoStep50Toggle");
    if (barrierNode && (shouldForce || !state.autoPanelOpen)) {
      barrierNode.value = formatBarrierInputValue(safe.barrier || "+0.12", 0.12);
    }
    if (budgetNode && (shouldForce || !state.autoPanelOpen)) {
      budgetNode.value = formatStakeInputValue(num(safe.budget, 10), 10);
    }
    const touchOnlyBtn = el("nttAutoTouchOnlyBtn");
    const noTouchOnlyBtn = el("nttAutoNoTouchOnlyBtn");
    const draftSide = state.autoPanelOpen && !shouldForce && state.autoBothDraft && state.autoBothDraft.selected_side;
    const selectedSide = String(draftSide || safe.selected_side || "TOUCH").toUpperCase();
    if (touchOnlyBtn) touchOnlyBtn.dataset.selected = selectedSide === "TOUCH" ? "1" : "0";
    if (noTouchOnlyBtn) noTouchOnlyBtn.dataset.selected = selectedSide === "NO_TOUCH" ? "1" : "0";
    if (martingaleNode && (shouldForce || !state.autoPanelOpen)) {
      martingaleNode.checked = !!safe.martingale_enabled;
    }
    if (step50Node && (shouldForce || !state.autoPanelOpen)) {
      step50Node.checked = !!safe.step50_enabled;
    }
    applyAutoBothModeToggles();
  }
  function applyAutoBothModeToggles() {
    const martingaleNode = el("nttAutoMartingaleToggle");
    const step50Node = el("nttAutoStep50Toggle");
    const martingaleEnabled = !!(martingaleNode && martingaleNode.checked);
    const step50Enabled = !!(step50Node && step50Node.checked);
    setText("nttAutoMartingaleState", martingaleEnabled ? "ON" : "OFF");
    setText("nttAutoStep50State", step50Enabled ? "ON" : "OFF");
  }
  function renderAutoBothPanel(data) {
    const safe = data || {};
    syncAutoBothPanelInputs(safe, false);
    const selectedSide = String(((state.autoBothDraft && state.autoBothDraft.selected_side) || safe.selected_side || "TOUCH")).toUpperCase();
    const touchOnlyBtn = el("nttAutoTouchOnlyBtn");
    const noTouchOnlyBtn = el("nttAutoNoTouchOnlyBtn");
    if (touchOnlyBtn) {
      const active = selectedSide === "TOUCH";
      touchOnlyBtn.innerText = `TOUCH ONLY: ${active ? "ON" : "OFF"}`;
      touchOnlyBtn.style.background = active ? "#22c55e" : "#166534";
      touchOnlyBtn.style.color = active ? "#052e16" : "#ecfdf5";
      touchOnlyBtn.style.boxShadow = active ? "0 0 0 2px rgba(134,239,172,0.45) inset" : "none";
    }
    if (noTouchOnlyBtn) {
      const active = selectedSide === "NO_TOUCH";
      noTouchOnlyBtn.innerText = `NO TOUCH ONLY: ${active ? "ON" : "OFF"}`;
      noTouchOnlyBtn.style.background = active ? "#ef4444" : "#991b1b";
      noTouchOnlyBtn.style.color = active ? "#fee2e2" : "#fef2f2";
      noTouchOnlyBtn.style.boxShadow = active ? "0 0 0 2px rgba(252,165,165,0.45) inset" : "none";
    }
    setText("nttAutoSideValue", selectedSide === "NO_TOUCH" ? "NO TOUCH ONLY: ON" : "TOUCH ONLY: ON");
    setText("nttAutoModeValue", safe.mode_label || "BASE");
    setText("nttAutoStakeValue", money(num(safe.current_stake, 0), state.lastPayload || safe));
    setText("nttAutoDecisionValue", String(safe.last_decision || safe.label || "OFF").replace(/_/g, " "));
    setText("nttAutoReason", safe.last_reason || "Mutant AUTO is OFF.");
    const startBtn = el("nttAutoStartBtn");
    if (startBtn) {
      startBtn.innerText = safe.enabled ? "UPDATE AUTO" : "START AUTO";
      startBtn.style.background = safe.enabled ? "#0f766e" : "#0f766e";
    }
    const stopBtn = el("nttAutoStopBtn");
    if (stopBtn) {
      stopBtn.disabled = !safe.enabled;
      stopBtn.style.opacity = safe.enabled ? "1" : ".6";
      stopBtn.style.cursor = safe.enabled ? "pointer" : "not-allowed";
    }
    const decisionNode = el("nttAutoDecisionValue");
    if (decisionNode) {
      const decision = String(safe.last_decision || safe.label || "OFF").toUpperCase();
      decisionNode.style.color = decision === "RUNNING" ? "#86efac" : (decision === "WAITING" ? "#fcd34d" : "#e2e8f0");
    }
  }
  function setAutoBothPanelOpen(open, forceSync) {
    state.autoPanelOpen = !!open;
    const modal = el("nttAutoBody");
    if (modal) modal.style.display = state.autoPanelOpen ? "flex" : "none";
    if (state.autoPanelOpen) {
      const ntt = state.lastPayload && (state.lastPayload.ntt || state.lastPayload);
      state.autoBothDraft = Object.assign({}, ((ntt && ntt.auto_both) || {}));
      syncAutoBothPanelInputs((ntt && ntt.auto_both) || {}, forceSync !== false);
      renderAutoBothPanel((ntt && ntt.auto_both) || {});
    } else {
      state.autoBothDraft = null;
    }
  }
  function readAutoBothForm() {
    normalizeBarrierField("nttAutoBarrier");
    const budgetNode = el("nttAutoBudget");
    const budgetValue = Math.max(0.35, num(readText("nttAutoBudget", "10"), 10));
    if (budgetNode) budgetNode.value = formatStakeInputValue(budgetValue, 10);
    const selectedSide = (el("nttAutoNoTouchOnlyBtn") && el("nttAutoNoTouchOnlyBtn").dataset.selected === "1") ? "NO_TOUCH" : "TOUCH";
    return {
      barrier: readText("nttAutoBarrier", "+0.12"),
      budget: Number(budgetValue.toFixed(2)),
      selected_side: selectedSide,
      martingale_enabled: !!(el("nttAutoMartingaleToggle") && el("nttAutoMartingaleToggle").checked),
      step50_enabled: !!(el("nttAutoStep50Toggle") && el("nttAutoStep50Toggle").checked),
    };
  }
  function setAutoBothSelectedSide(side) {
    const chosen = String(side || "TOUCH").toUpperCase() === "NO_TOUCH" ? "NO_TOUCH" : "TOUCH";
    const touchOnlyBtn = el("nttAutoTouchOnlyBtn");
    const noTouchOnlyBtn = el("nttAutoNoTouchOnlyBtn");
    if (touchOnlyBtn) touchOnlyBtn.dataset.selected = chosen === "TOUCH" ? "1" : "0";
    if (noTouchOnlyBtn) noTouchOnlyBtn.dataset.selected = chosen === "NO_TOUCH" ? "1" : "0";
    const ntt = state.lastPayload && (state.lastPayload.ntt || state.lastPayload);
    state.autoBothDraft = Object.assign({}, state.autoBothDraft || (ntt && ntt.auto_both) || {}, { selected_side: chosen });
    const auto = Object.assign({}, (ntt && ntt.auto_both) || {}, state.autoBothDraft);
    renderAutoBothPanel(auto);
  }
  function resetChartBase(symbol, price) {
    const safeSymbol = normalizeMarketSymbol(symbol);
    const safePrice = num(price, NaN);
    if (!safeSymbol || !Number.isFinite(safePrice)) return;
    if (state.marketChart.lastSymbol !== safeSymbol) {
      state.marketChart.history = [];
      state.marketChart.basePrice = safePrice;
      state.marketChart.previewBasePrice = safePrice;
      state.marketChart.previewBaseSymbol = safeSymbol;
      state.marketChart.wasActiveTrade = false;
      state.marketChart.lastSymbol = safeSymbol;
    }
    if (!Number.isFinite(state.marketChart.basePrice)) state.marketChart.basePrice = safePrice;
    if (!Number.isFinite(num(state.marketChart.previewBasePrice, NaN))) {
      state.marketChart.previewBasePrice = safePrice;
      state.marketChart.previewBaseSymbol = safeSymbol;
    }
  }
  function resetChartTracking(symbol, price) {
    const safeSymbol = normalizeMarketSymbol(symbol);
    const safePrice = num(price, NaN);
    state.marketChart.history = [];
    state.marketChart.basePrice = Number.isFinite(safePrice) ? safePrice : null;
    state.marketChart.previewBasePrice = Number.isFinite(safePrice) ? safePrice : null;
    state.marketChart.previewBaseSymbol = safeSymbol || null;
    state.marketChart.lastPrice = Number.isFinite(safePrice) ? safePrice : null;
    state.marketChart.lastSymbol = safeSymbol || null;
    state.marketChart.wasActiveTrade = false;
    if (Number.isFinite(safePrice)) {
      state.marketChart.history = [{ price: safePrice, time: Date.now() }];
    }
  }
  function pushChartPrice(price, symbol) {
    const safePrice = num(price, NaN);
    const safeSymbol = normalizeMarketSymbol(symbol || currentSymbol());
    if (!Number.isFinite(safePrice) || !safeSymbol) return;
    resetChartBase(safeSymbol, safePrice);
    state.marketChart.lastPrice = safePrice;
    state.marketChart.lastSymbol = safeSymbol;
    state.marketChart.history.push({ price: safePrice, time: Date.now() });
    if (state.marketChart.history.length > state.marketChart.maxPoints) {
      state.marketChart.history.splice(0, state.marketChart.history.length - state.marketChart.maxPoints);
    }
  }
  function getNttPreviewMotionStats(history) {
    const prices = Array.isArray(history)
      ? history.map((item) => num(item && item.price, NaN)).filter((value) => Number.isFinite(value))
      : [];
    if (prices.length < 2) {
      return { span: 0, avgMove: 0 };
    }
    let moveSum = 0;
    for (let index = 1; index < prices.length; index += 1) {
      moveSum += Math.abs(prices[index] - prices[index - 1]);
    }
    return {
      span: Math.max(...prices) - Math.min(...prices),
      avgMove: moveSum / Math.max(1, prices.length - 1),
    };
  }
  function setZoneStatus(text, color) {
    const pill = el("nttBarrierZoneState");
    if (!pill) return;
    const dot = pill.querySelector(".dot");
    const label = pill.querySelector("span:last-child");
    if (dot) dot.style.background = color || "#38bdf8";
    if (label) label.innerText = text || "WAITING FOR LIVE PRICE";
  }
  function renderBarrierMarketChart(ntt, payload) {
    const svg = el("nttBarrierMarketChart");
    if (!svg) return;
    const livePrice = num(payload && (payload.price != null ? payload.price : payload.quote), state.marketChart.lastPrice);
    if (Number.isFinite(livePrice)) pushChartPrice(livePrice, payload && (payload.main_symbol || payload.symbol));
    const chart = state.marketChart;
    const points = chart.history.slice();
    const touchBarrier = num(readText("nttTouchBarrier", (ntt && ntt.touch_barrier) || "+0.12"), num(ntt && ntt.touch_barrier, 0.12));
    const noTouchBarrier = num(readText("nttNoTouchBarrier", (ntt && ntt.no_touch_barrier) || "+0.12"), num(ntt && ntt.no_touch_barrier, 0.12));
    const history = Array.isArray(points) ? points : [];
    const activeEntries = Array.isArray(ntt && ntt.active_contracts)
      ? ntt.active_contracts.filter((item) => item && !item.is_sold)
      : [];
    activeEntries.sort((a, b) => {
      const ta = Date.parse(String(a.updated_at || a.time || "")) || 0;
      const tb = Date.parse(String(b.updated_at || b.time || "")) || 0;
      return tb - ta;
    });
    const anchorEntry = activeEntries[0] || null;
    const hasActiveEntry = !!anchorEntry;
    const activeEntrySpot = num(anchorEntry && anchorEntry.entry_spot, null);
    const latestPrice = Number.isFinite(chart.lastPrice) ? chart.lastPrice : livePrice;
    const symbolNow = normalizeMarketSymbol(chart.lastSymbol || (payload && (payload.main_symbol || payload.symbol)) || currentSymbol());
    const previewStats = getNttPreviewMotionStats(history);

    if (hasActiveEntry && Number.isFinite(activeEntrySpot)) {
      chart.wasActiveTrade = true;
      chart.previewBasePrice = activeEntrySpot;
      chart.previewBaseSymbol = symbolNow || chart.previewBaseSymbol || chart.lastSymbol || null;
    } else {
      const previewBasePrice = num(chart.previewBasePrice, null);
      const previewSymbolChanged = !!symbolNow && !!chart.previewBaseSymbol && symbolNow !== chart.previewBaseSymbol;
      const previewDrift = Number.isFinite(previewBasePrice) && Number.isFinite(latestPrice)
        ? Math.abs(latestPrice - previewBasePrice)
        : 0;
      const previewDriftFloor = Math.max(0.18, previewStats.span * 2.4, previewStats.avgMove * 14);
      const needsPreviewReset = !Number.isFinite(previewBasePrice)
        || previewSymbolChanged
        || chart.wasActiveTrade
        || previewDrift > previewDriftFloor;
      if (needsPreviewReset && Number.isFinite(latestPrice)) {
        chart.previewBasePrice = latestPrice;
        chart.previewBaseSymbol = symbolNow || chart.previewBaseSymbol || chart.lastSymbol || null;
      }
      chart.wasActiveTrade = false;
    }

    let anchor = hasActiveEntry && Number.isFinite(activeEntrySpot) ? activeEntrySpot : num(chart.previewBasePrice, null);
    if (!Number.isFinite(anchor)) anchor = Number.isFinite(chart.basePrice) ? chart.basePrice : null;
    if (!Number.isFinite(anchor)) anchor = Number.isFinite(latestPrice) ? latestPrice : 100;

    const rawPriceValues = history.map((item) => num(item && item.price, NaN)).filter((value) => Number.isFinite(value));
    const priceOffsets = rawPriceValues.map((value) => value - anchor);
    const marketAbsMax = Math.max(0.18, ...priceOffsets.map((value) => Math.abs(value)), Math.abs(num(latestPrice, anchor) - anchor));
    const barrierAbsMax = Math.max(Math.abs(touchBarrier), Math.abs(noTouchBarrier), 0.01);
    const barrierCap = Math.max(0.24, marketAbsMax * 2.2, previewStats.avgMove * 16);
    const effectiveBarrierAbs = Math.min(barrierAbsMax, barrierCap);
    const scaleBarrierOffset = (raw) => {
      const numeric = num(raw, 0);
      if (!Number.isFinite(numeric)) return 0;
      if (barrierAbsMax <= 0 || effectiveBarrierAbs >= barrierAbsMax) return numeric;
      return Math.sign(numeric || 1) * ((Math.abs(numeric) / barrierAbsMax) * effectiveBarrierAbs);
    };

    const touchLine = anchor + scaleBarrierOffset(touchBarrier);
    const noTouchLine = anchor + scaleBarrierOffset(noTouchBarrier);
    const sharedBarrier = Math.abs(touchBarrier - noTouchBarrier) < 0.0001;
    const triggerLine = anchor + scaleBarrierOffset(touchBarrier);
    const currentPrice = Number.isFinite(latestPrice) ? latestPrice : anchor;
    const priceValues = rawPriceValues.length ? rawPriceValues : (Number.isFinite(currentPrice) ? [currentPrice] : []);
    const allValues = priceValues.concat(sharedBarrier ? [triggerLine] : [touchLine, noTouchLine]).filter((value) => Number.isFinite(value));
    if (!allValues.length) {
      svg.innerHTML = "";
      setText("nttPriceRangeLabel", "Price range: waiting for live ticks");
      setText("nttBarrierChartStats", sharedBarrier
        ? `Shared barrier ${formatBarrierInputValue(touchBarrier, 0.12)}`
        : `Touch ${formatBarrierInputValue(touchBarrier, 0.12)} | No Touch ${formatBarrierInputValue(noTouchBarrier, 0.12)}`);
      setText("nttBarrierChartMeta", sharedBarrier
        ? "Live market line will appear here and show whether price reaches your shared Touch / No Touch barrier."
        : "Live market line will appear here and show whether Touch or No Touch is favored against your current barriers.");
      setZoneStatus("WAITING FOR LIVE PRICE", "#38bdf8");
      return;
    }
    const width = 760;
    const height = 260;
    const padX = 30;
    const padY = 22;
    const minValue = Math.min.apply(null, allValues);
    const maxValue = Math.max.apply(null, allValues);
    const span = Math.max(Math.abs(maxValue - minValue), 0.01);
    const paddedMin = minValue - span * 0.16;
    const paddedMax = maxValue + span * 0.16;
    const toY = (value) => {
      const ratio = (value - paddedMin) / Math.max(paddedMax - paddedMin, 0.000001);
      return height - padY - ratio * (height - padY * 2);
    };
    const toX = (index, total) => total <= 1 ? padX : padX + (index / (total - 1)) * (width - padX * 2);
    const polyline = points.length
      ? points.map((item, index) => `${toX(index, points.length)},${toY(item.price)}`).join(" ")
      : "";
    const currentY = toY(currentPrice);
    const touchY = toY(touchLine);
    const noTouchY = toY(noTouchLine);
    const triggerY = toY(triggerLine);
    const lineMarkup = sharedBarrier
      ? `<line x1="${padX}" x2="${width - padX}" y1="${triggerY}" y2="${triggerY}" stroke="#f59e0b" stroke-width="2.4" stroke-dasharray="8 6"></line>`
      : `<line x1="${padX}" x2="${width - padX}" y1="${touchY}" y2="${touchY}" stroke="#22c55e" stroke-width="2" stroke-dasharray="8 6"></line>
      <line x1="${padX}" x2="${width - padX}" y1="${noTouchY}" y2="${noTouchY}" stroke="#ef4444" stroke-width="2" stroke-dasharray="8 6"></line>`;
    const labelMarkup = sharedBarrier
      ? `<text x="${width - padX - 6}" y="${triggerY - 8}" fill="#fcd34d" font-size="14" font-weight="800" text-anchor="end">TOUCH / NO TOUCH ${escapeHtml(formatBarrierInputValue(touchBarrier, 0.12))}</text>`
      : `<text x="${width - padX - 6}" y="${touchY - 8}" fill="#86efac" font-size="14" font-weight="800" text-anchor="end">TOUCH ${escapeHtml(formatBarrierInputValue(touchBarrier, 0.12))}</text>
      <text x="${width - padX - 6}" y="${noTouchY - 8}" fill="#fca5a5" font-size="14" font-weight="800" text-anchor="end">NO TOUCH ${escapeHtml(formatBarrierInputValue(noTouchBarrier, 0.12))}</text>`;
    svg.innerHTML = `
      <defs>
        <linearGradient id="nttLineGradient" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stop-color="#38bdf8" />
          <stop offset="100%" stop-color="#8b5cf6" />
        </linearGradient>
      </defs>
      <rect x="0" y="0" width="${width}" height="${height}" rx="18" fill="#08111f"></rect>
      <g opacity="0.14" stroke="#334155" stroke-width="1">
        <line x1="${padX}" x2="${width - padX}" y1="${height * 0.25}" y2="${height * 0.25}"></line>
        <line x1="${padX}" x2="${width - padX}" y1="${height * 0.5}" y2="${height * 0.5}"></line>
        <line x1="${padX}" x2="${width - padX}" y1="${height * 0.75}" y2="${height * 0.75}"></line>
      </g>
      ${lineMarkup}
      ${polyline ? `<polyline fill="none" stroke="url(#nttLineGradient)" stroke-width="4" points="${polyline}" stroke-linecap="round" stroke-linejoin="round"></polyline>` : ""}
      <circle cx="${width - padX}" cy="${currentY}" r="5.5" fill="#38bdf8"></circle>
      ${labelMarkup}
    `;
    let zoneText = "BETWEEN BOTH BARRIERS";
    let zoneColor = "#38bdf8";
    if (sharedBarrier) {
      const priceTrail = priceValues.concat(Number.isFinite(currentPrice) ? [currentPrice] : []);
      let touched = false;
      if (touchBarrier >= 0) {
        touched = priceTrail.some((value) => Number.isFinite(value) && value >= triggerLine);
      } else {
        touched = priceTrail.some((value) => Number.isFinite(value) && value <= triggerLine);
      }
      zoneText = touched ? "TOUCH LINE HIT • TOUCH LEADS" : "LINE NOT HIT YET • NO TOUCH LEADS";
      zoneColor = touched ? "#22c55e" : "#ef4444";
    } else {
      const mid = (touchLine + noTouchLine) / 2;
      const distTouch = Math.abs(currentPrice - touchLine);
      const distNoTouch = Math.abs(currentPrice - noTouchLine);
      if (distTouch < distNoTouch * 0.82 || currentPrice >= mid) {
        zoneText = "TOUCH PRESSURE BUILDING";
        zoneColor = "#22c55e";
      } else if (distNoTouch < distTouch * 0.82 || currentPrice < mid) {
        zoneText = "NO TOUCH BUFFER HOLDING";
        zoneColor = "#ef4444";
      }
    }
    setZoneStatus(zoneText, zoneColor);
    setText("nttPriceRangeLabel", `Price range: ${paddedMin.toFixed(4)} to ${paddedMax.toFixed(4)}`);
    if (sharedBarrier) {
      setText("nttBarrierChartStats", `Shared barrier ${formatBarrierInputValue(touchBarrier, 0.12)} | Live ${Number.isFinite(currentPrice) ? currentPrice.toFixed(4) : "-"}`);
      setText("nttBarrierChartMeta", `Chart anchored on ${normalizeMarketSymbol(chart.lastSymbol || currentSymbol()) || "current market"}. If price touches the shared line before expiry, TOUCH wins. If it never reaches that line, NO TOUCH wins.`);
    } else {
      setText("nttBarrierChartStats", `Touch ${formatBarrierInputValue(touchBarrier, 0.12)} | No Touch ${formatBarrierInputValue(noTouchBarrier, 0.12)} | Live ${Number.isFinite(currentPrice) ? currentPrice.toFixed(4) : "-"}`);
      setText("nttBarrierChartMeta", `Chart anchored on ${normalizeMarketSymbol(chart.lastSymbol || currentSymbol()) || "current market"}. Touch line and No Touch line move with your saved Mutant barriers.`);
    }
  }
  function renderActiveTrades(ntt) {
    const list = el("nttActiveTrades");
    if (!list) return;
    const items = Array.isArray(ntt && ntt.active_contracts) ? ntt.active_contracts : [];
    if (!items.length) {
      list.innerHTML = '<div class="ntt-empty">No active Mutant trades</div>';
      return;
    }
    list.innerHTML = items.map((item) => {
      const resultText = String(item.status || item.result || "OPEN");
      const openProfit = num(item.open_profit, NaN);
      const countdown = item.countdown_remaining != null
        ? `${item.countdown_remaining}${String(item.countdown_unit || "").toUpperCase()}`
        : "-";
      const sideColor = String(item.type || "").toUpperCase().includes("NO") ? "#fca5a5" : "#86efac";
      const pnlText = Number.isFinite(openProfit) ? signedMoney(openProfit, item) : "-";
      const pnlColor = Number.isFinite(openProfit) ? (openProfit >= 0 ? "#22c55e" : "#ef4444") : "#e2e8f0";
      return `
        <div class="ntt-active-item">
          <div style="display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap;">
            <div style="font-weight:900;font-size:1rem;color:${sideColor};">${escapeHtml(String(item.type || "TRADE").replace(/_/g, " "))}</div>
            <div style="font-size:12px;color:#94a3b8;">${escapeHtml(String(item.symbol || currentSymbol() || "-"))}</div>
          </div>
          <div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:10px;">
            <div><div style="font-size:11px;color:#94a3b8;">Stake</div><div style="font-weight:800;">${money(num(item.stake, 0), item)}</div></div>
            <div><div style="font-size:11px;color:#94a3b8;">Barrier</div><div style="font-weight:800;">${escapeHtml(String(item.barrier || "-"))}</div></div>
            <div><div style="font-size:11px;color:#94a3b8;">Countdown</div><div style="font-weight:800;">${escapeHtml(String(countdown))}</div></div>
            <div><div style="font-size:11px;color:#94a3b8;">Open P/L</div><div style="font-weight:800;color:${pnlColor};">${pnlText}</div></div>
          </div>
          <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-top:10px;color:#94a3b8;font-size:12px;">
            <span>${escapeHtml(resultText)}</span>
            <span>${escapeHtml(String(item.time || ""))}</span>
          </div>
        </div>
      `;
    }).join("");
  }
  function renderPayload(payload, opts) {
    const options = opts || {};
    const root = payload || {};
    const ntt = root.ntt || root;
    const nextSymbol = normalizeMarketSymbol(root.main_symbol || root.symbol || ntt.main_symbol || ntt.symbol || currentSymbol());
    const symbolChanged = !!nextSymbol && nextSymbol !== String(state.lastMainSymbol || "").toUpperCase();
    const nextBarrierKey = String(ntt.market_default_key || root.market_default_key || "").toUpperCase();
    const forceMarketDefaults = !!options.forceMarketDefaults;
    const shouldUseFreshMarketDefaults = !!nextSymbol && (symbolChanged || forceMarketDefaults);
    state.lastPayload = root;
    fillForm(ntt, !!options.forceForm, {
      forceBarriers: shouldUseFreshMarketDefaults || !!options.forceForm,
      barrierOnly: !!options.barrierOnly,
    });
    let savedMarketBarriers = seedMarketBarrierSettingsFromPayload(nextSymbol, ntt, {
      preferPayload: shouldUseFreshMarketDefaults || !!options.forceForm,
    });
    if (savedMarketBarriers && savedMarketBarriers.is_custom) {
      applySavedMarketBarrierSettingsToForm(savedMarketBarriers, !!options.forceForm);
      const payloadSignature = buildMarketBarrierSignature(nextSymbol, getPayloadMarketBarrierSettings(ntt));
      const savedSignature = buildMarketBarrierSignature(nextSymbol, savedMarketBarriers);
      if (savedSignature && savedSignature !== payloadSignature) {
        syncSavedMarketBarrierSettingsToServer(nextSymbol, savedMarketBarriers).catch(() => {});
      }
    }
    if (options.barrierOnly) {
      clearDirty(["nttTouchBarrier", "nttNoTouchBarrier"]);
    } else if (symbolChanged) {
      clearDirty(["nttTouchBarrier", "nttNoTouchBarrier"]);
      resetChartTracking(nextSymbol, root.price);
    }
    if (nextSymbol) state.lastMainSymbol = nextSymbol;
    if (nextBarrierKey) state.lastBarrierKey = nextBarrierKey;
    renderStatusChip(ntt);
    renderRiskBlock(ntt);
    renderBias(ntt);
    renderAutoBoth(ntt);
    renderActiveTrades(ntt);
    renderKoolkid(ntt);
    const stats = ntt.stats || {};
    const wins = Number(stats.wins || 0);
    const losses = Number(stats.losses || 0);
    const netPnl = num(stats.net_pnl, 0);
    setText("nttNetPnl", signedMoney(netPnl, ntt));
    const pnlNode = el("nttNetPnl");
    if (pnlNode) pnlNode.style.color = netPnl > 0 ? "#22c55e" : (netPnl < 0 ? "#ef4444" : "#e2e8f0");
    setText("nttWinLoss", `${wins} / ${losses}`);
    setText("nttActiveCount", Number(ntt.active_count || (Array.isArray(ntt.active_contracts) ? ntt.active_contracts.length : 0)));
    if (ntt.last_result && typeof ntt.last_result === "object") {
      const profit = num(ntt.last_result.profit, 0);
      setText("nttLastResult", `${String(ntt.last_result.type || "TRADE").replace(/_/g, " ")} ${signedMoney(profit, ntt.last_result)}`);
    } else {
      setText("nttLastResult", "-");
    }
    setText("nttLastAction", ntt.last_action || "Ready");
    if (Number.isFinite(num(root.price, NaN))) pushChartPrice(root.price, root.main_symbol || root.symbol);
    renderBarrierMarketChart(ntt, root);
    scheduleTouchPrediction(80);
    scheduleExpectedProfitPreview(80);
  }
  async function refreshStatus(silent) {
    const { ok, data } = await getJSON("/ntt_status");
    if (!ok) {
      if (!silent) toast((data && (data.error || data.message)) || "Failed to load Mutant status", "error");
      return false;
    }
    renderPayload(data, { forceForm: false });
    return true;
  }
  async function saveSettings(showToastMessage) {
    const body = readForm();
    const { ok, data } = await postJSON("/ntt_settings", body);
    if (!ok) {
      toast((data && (data.error || data.message)) || "Could not save Mutant settings", "error");
      return false;
    }
    renderPayload(data, { forceForm: true });
    if (showToastMessage) toast("Mutant settings saved", "success");
    return true;
  }
  async function sendTrade(side) {
    if (state.tradeRequestInFlight) return false;
    state.tradeRequestInFlight = true;
    state.tradeRequestSide = side;
    const body = Object.assign(readForm(), { side: side });
    const { ok, data } = await postJSON("/ntt_trade", body);
    state.tradeRequestInFlight = false;
    state.tradeRequestSide = null;
    renderPayload((data && data.payload) || state.lastPayload || {}, { forceForm: false });
    if (!ok) {
      toast((data && (data.message || data.error)) || `Failed to send ${side}`, "error");
      return false;
    }
    toast(data && data.message ? data.message : `Sent ${side}`, "success");
    return true;
  }
  async function refreshMarketBarriers() {
    const { ok, data } = await postJSON("/ntt_refresh_barriers", {});
    if (ok && data) {
      const payload = data.payload || {};
      const ntt = payload.ntt || payload;
      const symbol = normalizeMarketSymbol(
        payload.main_symbol || payload.symbol || ntt.main_symbol || ntt.symbol || state.lastMainSymbol || currentSymbol()
      );
      persistMarketBarrierSettings(symbol, {
        touch_barrier: ntt.touch_barrier,
        no_touch_barrier: ntt.no_touch_barrier,
      }, { custom: false });
      BARRIER_FIELD_IDS.forEach((id) => state.dirtyFields.delete(id));
      renderPayload(payload, { forceForm: false, forceMarketDefaults: true, barrierOnly: true });
      toast(data && data.message ? data.message : "Mutant barriers refreshed", "success");
      return true;
    }
    renderPayload((data && data.payload) || state.lastPayload || {}, { forceForm: true });
    if (!ok) {
      toast((data && (data.error || data.message)) || "Could not refresh barriers", "error");
      return false;
    }
    return false;
  }
  async function closeAll() {
    const { ok, data } = await postJSON("/ntt_close_now", {});
    renderPayload((data && data.payload) || state.lastPayload || {}, { forceForm: false });
    if (!ok) {
      toast((data && (data.message || data.error)) || "No active Mutant trade", "error");
      return false;
    }
    toast(data && data.message ? data.message : "Close request sent", "warn");
    return true;
  }
  async function clearActive() {
    const { ok, data } = await postJSON("/ntt_clear_active", {});
    renderPayload((data && data.payload) || state.lastPayload || {}, { forceForm: false });
    if (!ok) {
      toast((data && (data.message || data.error)) || "Could not clear active Mutant trades", "error");
      return false;
    }
    toast(data && data.message ? data.message : "Cleared Mutant active trades", "warn");
    return true;
  }
  async function toggleAutoBoth() {
    setAutoBothPanelOpen(true, true);
    return true;
  }
  function closeAutoBothPanel() {
    setAutoBothPanelOpen(false, false);
    return true;
  }
  async function startAutoBoth() {
    const config = readAutoBothForm();
    state.autoBothDraft = Object.assign({}, state.autoBothDraft || {}, config);
    const saved = await saveSettings(false);
    if (!saved) return false;
    const { ok, data } = await postJSON("/toggle_ntt_auto_both", {
      enabled: true,
      barrier: config.barrier,
      budget: config.budget,
      selected_side: config.selected_side,
      martingale_enabled: config.martingale_enabled,
      step50_enabled: config.step50_enabled,
    });
    renderPayload((data && data.payload) || state.lastPayload || {}, { forceForm: true });
    const ntt = ((data && data.payload) || state.lastPayload || {}).ntt || ((data && data.payload) || state.lastPayload || {});
    if (ntt && ntt.auto_both) {
      state.autoBothDraft = Object.assign({}, ntt.auto_both);
      syncAutoBothPanelInputs(ntt.auto_both, true);
    }
    setAutoBothPanelOpen(true, false);
    if (!ok) {
      toast((data && (data.message || data.error)) || "Could not start Mutant AUTO", "error");
      return false;
    }
    toast((data && data.message) || "MUTANT AUTO ON", "success");
    return true;
  }
  async function stopAutoBoth() {
    const { ok, data } = await postJSON("/toggle_ntt_auto_both", { enabled: false });
    renderPayload((data && data.payload) || state.lastPayload || {}, { forceForm: true });
    const ntt = ((data && data.payload) || state.lastPayload || {}).ntt || ((data && data.payload) || state.lastPayload || {});
    if (ntt && ntt.auto_both) {
      state.autoBothDraft = Object.assign({}, ntt.auto_both);
      syncAutoBothPanelInputs(ntt.auto_both, true);
    }
    setAutoBothPanelOpen(true, false);
    if (!ok) {
      toast((data && (data.message || data.error)) || "Could not stop Mutant AUTO", "error");
      return false;
    }
    toast((data && data.message) || "MUTANT AUTO OFF", "warn");
    return true;
  }
  async function toggleAutoSl() {
    state.auto_sl = !state.auto_sl;
    applyAutoSlBtn();
    await saveSettings(false);
  }
  function nudgeBarrierField(target, delta) {
    const node = el(target);
    if (!node) return;
    const targetText = String(target || "");
    const isTouch = targetText.toLowerCase().includes("touch") && !targetText.toLowerCase().includes("no");
    const fallback = targetText.toLowerCase().includes("koolkid") ? 0.06 : 0.12;
    const current = num(node.value, fallback);
    const deltaValue = num(delta, 0);
    const nextMagnitude = Math.max(0.01, Math.round((Math.abs(current) + deltaValue) * 100) / 100);
    const nextValue = current < 0 ? -nextMagnitude : nextMagnitude;
    node.value = formatBarrierInputValue(nextValue, fallback);
    markDirty(target);
    if (BARRIER_FIELD_IDS.has(target)) {
      persistCurrentMarketBarrierSettings(null, { custom: true });
      scheduleCurrentMarketBarrierSync(null, { custom: true });
    }
    renderBarrierMarketChart(state.lastPayload && state.lastPayload.ntt || {}, state.lastPayload || {});
    scheduleTouchPrediction(120);
    scheduleExpectedProfitPreview(120);
  }
  function normalizeBarrierField(target, opts) {
    const node = el(target);
    if (!node) return false;
    const options = opts || {};
    const targetText = String(target || "").toLowerCase();
    const fallback = targetText.includes("koolkid") ? 0.06 : 0.12;
    if (options.preserveBlank && isBlankEditableValue(node.value)) {
      node.value = "";
      markDirty(target);
      return false;
    }
    node.value = formatBarrierInputValue(node.value, fallback, options);
    markDirty(target);
    return !isBlankEditableValue(node.value);
  }
  function renderExpectedProfitPreview(preview) {
    const touch = preview && preview.touch ? preview.touch : {};
    const noTouch = preview && preview.no_touch ? preview.no_touch : {};
    const both = preview && preview.both ? preview.both : {};
    const touchText = Number.isFinite(Number(touch.profit))
      ? `Expected profit ${signedMoney(Number(touch.profit), touch)}`
      : "Expected profit —";
    const noTouchText = Number.isFinite(Number(noTouch.profit))
      ? `Expected profit ${signedMoney(Number(noTouch.profit), noTouch)}`
      : "Expected profit —";
    const bothText = Number.isFinite(Number(both.net_profit))
      ? `Net expected ${signedMoney(Number(both.net_profit), both)}`
      : "Net expected —";
    setText("nttTouchExpectedProfit", touchText);
    setText("nttNoTouchExpectedProfit", noTouchText);
    setText("nttBothExpectedProfit", bothText);
  }
  async function refreshExpectedProfitPreview() {
    if (!isActive() || state.expectedProfitLoading) return;
    const form = readForm();
    const signature = JSON.stringify([
      form.symbol,
      form.use_shared_duration,
      form.touch_stake,
      form.no_touch_stake,
      form.touch_barrier,
      form.no_touch_barrier,
      form.duration,
      form.duration_unit,
      form.touch_duration,
      form.touch_duration_unit,
      form.no_touch_duration,
      form.no_touch_duration_unit,
    ]);
    state.expectedProfitSignature = signature;
    state.expectedProfitLoading = true;
    try {
      const res = await postJSON("/ntt_expected_profit", form);
      if (!res.ok || !res.data) {
        renderExpectedProfitPreview(null);
        return;
      }
      if (signature !== state.expectedProfitSignature) return;
      renderExpectedProfitPreview(res.data.preview || null);
    } catch (_e) {
      renderExpectedProfitPreview(null);
    } finally {
      state.expectedProfitLoading = false;
    }
  }
  function scheduleExpectedProfitPreview(delay) {
    if (state.expectedProfitTimer) {
      clearTimeout(state.expectedProfitTimer);
      state.expectedProfitTimer = null;
    }
    state.expectedProfitTimer = setTimeout(() => {
      refreshExpectedProfitPreview().catch(() => {});
    }, Math.max(60, Number(delay || 180)));
  }
  async function handleAction(action, btn) {
    const key = String(action || "");
    if (btn && btn.disabled && key !== "ntt-toggle-autosl") return;
    if (key === "ntt-toggle-autosl") return toggleAutoSl();
    if (key === "ntt-save-settings") return saveSettings(true);
    if (key === "ntt-auto-both") return toggleAutoBoth();
    if (key === "ntt-auto-close") return closeAutoBothPanel();
    if (key === "ntt-auto-start") return startAutoBoth();
    if (key === "ntt-auto-stop") return stopAutoBoth();
    if (key === "ntt-auto-side-touch") return setAutoBothSelectedSide("TOUCH");
    if (key === "ntt-auto-side-no-touch") return setAutoBothSelectedSide("NO_TOUCH");
    if (key === "ntt-trade-touch") return sendTrade("TOUCH");
    if (key === "ntt-trade-no-touch") return sendTrade("NO_TOUCH");
    if (key === "ntt-trade-both") return sendTrade("BOTH");
    if (key === "ntt-analysis-primary") return handleAutoAnalysisPrimary();
    if (key === "ntt-selector-primary") return handleSelectorPrimary();
    if (key === "ntt-selector-skip") return scheduleTouchPrediction(60);
    if (key === "ntt-koolkid-tnt") return toggleKoolkidTnt();
    if (key === "ntt-koolkid-both") return toggleKoolkidBoth();
    if (key === "ntt-koolkid-panel" || key === "ntt-koolkid-close") return toggleKoolkidPanel();
    if (key === "ntt-refresh-barriers") return refreshMarketBarriers();
    if (key === "ntt-close-all") return closeAll();
    if (key === "ntt-clear-active") return clearActive();
    if (key === "ntt-barrier-step") return nudgeBarrierField(btn && btn.dataset.target, btn && btn.dataset.delta);
    if (key === "ntt-koolkid-barrier-step") return nudgeBarrierField(btn && btn.dataset.target, btn && btn.dataset.delta);
    return null;
  }
  function buildPredictionRequest() {
    const form = readForm();
    return {
      profile: PROFILE,
      symbol: form.symbol,
      duration: form.duration,
      duration_unit: form.duration_unit,
      contract_selector_mode: "AUTO_SELECT",
      touch_barrier: form.touch_barrier,
      no_touch_barrier: form.no_touch_barrier,
    };
  }
  function buildNttAutoAnalysisRequest() {
    const form = readForm();
    const touchBarrier = formatBarrierInputValue(form.touch_barrier, 0.12);
    const noTouchBarrier = formatBarrierInputValue(form.no_touch_barrier, 0.12);
    const touchValue = Math.abs(num(touchBarrier, 0.12));
    const noTouchValue = Math.abs(num(noTouchBarrier, 0.12));
    return {
      symbol: form.symbol,
      duration: form.duration,
      duration_unit: form.duration_unit,
      touch_barrier: touchBarrier,
      no_touch_barrier: noTouchBarrier,
      barrier: touchValue <= noTouchValue ? touchBarrier : noTouchBarrier,
    };
  }
  async function refreshTouchPrediction() {
    if (!isActive()) return;
    const autoBody = buildNttAutoAnalysisRequest();
    const selectorBody = buildPredictionRequest();
    const signature = JSON.stringify([autoBody, selectorBody]);
    if (state.predictionLoading && state.predictionSignature === signature) return;
    state.predictionSignature = signature;
    state.predictionLoading = true;
    try {
      const [autoRes, selectorRes] = await Promise.all([
        postJSON("/touch_no_touch_prediction", autoBody),
        postJSON("/contract_selector_analysis", selectorBody),
      ]);
      if (signature !== state.predictionSignature) return;
      renderNttAutoAnalysis(autoRes && autoRes.data ? autoRes.data : null);
      renderTouchPrediction(selectorRes && selectorRes.ok ? selectorRes.data : null);
    } catch (_e) {
      if (signature !== state.predictionSignature) return;
      renderNttAutoAnalysis(null);
      renderTouchPrediction(null);
    } finally {
      state.predictionLoading = false;
    }
  }
  function scheduleTouchPrediction(delay) {
    clearTimeout(state.predictionTimer);
    state.predictionTimer = setTimeout(() => {
      refreshTouchPrediction().catch(() => {});
    }, Math.max(0, Number(delay || 0)));
  }
  async function handleSelectorPrimary() {
    const btn = el("nttSelectorPrimaryAction");
    if (!btn) return;
    const side = String(btn.dataset.selectorSide || "SKIP").toUpperCase();
    const valid = btn.dataset.tradeValid === "1";
    if (!valid) {
      toast("Selector says skip this Touch / No Touch setup for now.", "info");
      return;
    }
    if (side === "TOUCH") return sendTrade("TOUCH");
    if (side === "NO_TOUCH") return sendTrade("NO_TOUCH");
    toast("Touch / No Touch side is not ready yet.", "info");
  }
  function toggleKoolkidPanel() {
    state.koolkidPanelOpen = !state.koolkidPanelOpen;
    const modal = el("nttKoolkidBody");
    if (modal) modal.style.display = state.koolkidPanelOpen ? "flex" : "none";
  }
  async function toggleKoolkidTnt() {
    const saved = await saveSettings(false);
    if (!saved) return;
    const ntt = state.lastPayload && (state.lastPayload.ntt || state.lastPayload);
    const current = !!(ntt && ntt.koolkid_hl && ntt.koolkid_hl.enabled);
    const res = await postJSON("/toggle_ntt_koolkid_hl", { enabled: !current });
    if (res.ok && res.data) {
      if (res.data.payload) renderPayload(res.data.payload, { forceForm: true });
      toast(res.data.message || (!current ? "KOOLKID TOUCH / NO TOUCH ON" : "KOOLKID TOUCH / NO TOUCH OFF"), !current ? "success" : "warn");
      return;
    }
    toast((res.data && (res.data.message || res.data.error)) || "Failed to toggle KOOLKID Touch / No Touch", "error");
    if (res.data && res.data.payload) renderPayload(res.data.payload, { forceForm: true });
  }
  async function toggleKoolkidBoth() {
    const saved = await saveSettings(false);
    if (!saved) return;
    const ntt = state.lastPayload && (state.lastPayload.ntt || state.lastPayload);
    const current = !!(ntt && ntt.koolkid_both && ntt.koolkid_both.enabled);
    const res = await postJSON("/toggle_ntt_koolkid_both", { enabled: !current });
    if (res.ok && res.data) {
      if (res.data.payload) renderPayload(res.data.payload, { forceForm: true });
      toast(res.data.message || (!current ? "KOOLKID BOTH ON" : "KOOLKID BOTH OFF"), !current ? "success" : "warn");
      return;
    }
    toast((res.data && (res.data.message || res.data.error)) || "Failed to toggle KOOLKID Both", "error");
    if (res.data && res.data.payload) renderPayload(res.data.payload, { forceForm: true });
  }
  async function handleAutoAnalysisPrimary() {
    const btn = el("nttAnalysisPrimaryAction");
    if (!btn) return;
    const side = String(btn.dataset.analysisSide || "TOUCH").toUpperCase();
    const valid = btn.dataset.tradeValid === "1";
    if (!valid) {
      toast("Auto analysis says wait for a cleaner Touch / No Touch setup.", "info");
      return;
    }
    if (side === "NO_TOUCH") return sendTrade("NO_TOUCH");
    return sendTrade("TOUCH");
  }
  function bindSocket() {
    try {
      if (typeof socket === "undefined" || !socket) return;
      if (state.lastSocket === socket && state.socketBound) return;
      state.lastSocket = socket;
      state.socketBound = true;
      socket.on("tick", (data) => {
        if (!data) return;
        pushChartPrice(data.price != null ? data.price : data.quote, data.symbol);
        if (isActive()) renderBarrierMarketChart((state.lastPayload && state.lastPayload.ntt) || {}, state.lastPayload || data || {});
      });
      socket.on("ntt_status", (data) => {
        if (data && isActive()) renderPayload(data, { forceForm: false });
      });
      socket.on("trade_result", (trade) => {
        if (trade && String(trade.profile || "").toUpperCase() === PROFILE && isActive()) {
          setTimeout(() => refreshStatus(true), 180);
        }
      });
      socket.on("trade_placed", (trade) => {
        if (trade && String(trade.profile || "").toUpperCase() === PROFILE && isActive()) {
          setTimeout(() => refreshStatus(true), 120);
        }
      });
    } catch (_e) {}
  }
  function bindFormInputs() {
    FORM_FIELDS.forEach((id) => {
      const node = el(id);
      if (!node || node.dataset.nttBound === "1") return;
      node.dataset.nttBound = "1";
      node.addEventListener("focus", () => markDirty(id));
      node.addEventListener("input", () => {
        markDirty(id);
        if (id === "nttTouchStake") {
          syncNoTouchStakeFromTouch(false);
        }
        if (id === "nttNoTouchStake") updateNoTouchStakeCustomFlag();
        if (id === "nttDurationUnit") applyDurationPresets("nttDuration", "nttDurationUnit");
        if (id === "nttTouchDurationUnit") applyDurationPresets("nttTouchDuration", "nttTouchDurationUnit");
        if (id === "nttNoTouchDurationUnit") applyDurationPresets("nttNoTouchDuration", "nttNoTouchDurationUnit");
        if (id === "nttUseSharedDuration") updateDurationModeUI(true);
        if (id === "nttTouchBarrier" || id === "nttNoTouchBarrier") {
          renderBarrierMarketChart((state.lastPayload && state.lastPayload.ntt) || {}, state.lastPayload || {});
        }
        if (
          id === "nttUseSharedDuration" ||
          id === "nttDuration" || id === "nttDurationUnit" ||
          id === "nttTouchDuration" || id === "nttTouchDurationUnit" ||
          id === "nttNoTouchDuration" || id === "nttNoTouchDurationUnit" ||
          id === "nttTouchBarrier" || id === "nttNoTouchBarrier" ||
          id === "nttTouchStake" || id === "nttNoTouchStake"
        ) {
          scheduleTouchPrediction(120);
          scheduleExpectedProfitPreview(120);
        }
        if (id === "nttKoolkidReversalToggle") {
          state.koolkid_reversal_enabled = !!node.checked;
          applyKoolkidReversalToggle();
        }
        if (id === "nttKoolkidHalfBarrierToggle") {
          state.koolkid_half_barrier_enabled = !!node.checked;
          applyKoolkidHalfBarrierToggle();
        }
      });
      node.addEventListener("change", () => {
        markDirty(id);
        if (id === "nttTouchStake") {
          node.value = formatStakeInputValue(node.value, 1, { preserveBlank: true });
          syncNoTouchStakeFromTouch(false);
        }
        if (id === "nttNoTouchStake") {
          node.value = formatStakeInputValue(node.value, readNumber("nttTouchStake", 1), { preserveBlank: true });
          updateNoTouchStakeCustomFlag();
        }
        if (id === "nttDurationUnit") applyDurationPresets("nttDuration", "nttDurationUnit");
        if (id === "nttTouchDurationUnit") applyDurationPresets("nttTouchDuration", "nttTouchDurationUnit");
        if (id === "nttNoTouchDurationUnit") applyDurationPresets("nttNoTouchDuration", "nttNoTouchDurationUnit");
        if (id === "nttUseSharedDuration") updateDurationModeUI(true);
        if (id === "nttTouchBarrier" || id === "nttNoTouchBarrier") {
          const normalized = normalizeBarrierField(id, { preserveBlank: true });
          if (normalized) {
            persistCurrentMarketBarrierSettings(null, { custom: true });
            scheduleCurrentMarketBarrierSync(null, { custom: true });
          }
        }
        if (id === "nttKoolkidTouchBarrier" || id === "nttKoolkidNoTouchBarrier") {
          normalizeBarrierField(id, { preserveBlank: true });
        }
        if (id === "nttTouchBarrier" || id === "nttNoTouchBarrier") {
          renderBarrierMarketChart((state.lastPayload && state.lastPayload.ntt) || {}, state.lastPayload || {});
        }
        if (
          id === "nttUseSharedDuration" ||
          id === "nttDuration" || id === "nttDurationUnit" ||
          id === "nttTouchDuration" || id === "nttTouchDurationUnit" ||
          id === "nttNoTouchDuration" || id === "nttNoTouchDurationUnit" ||
          id === "nttTouchBarrier" || id === "nttNoTouchBarrier" ||
          id === "nttTouchStake" || id === "nttNoTouchStake"
        ) {
          scheduleTouchPrediction(80);
          scheduleExpectedProfitPreview(80);
        }
      });
      node.addEventListener("blur", () => {
        if (id === "nttTouchStake") {
          node.value = formatStakeInputValue(node.value, 1, { preserveBlank: true });
          syncNoTouchStakeFromTouch(false);
          scheduleExpectedProfitPreview(80);
        }
        if (id === "nttNoTouchStake") {
          node.value = formatStakeInputValue(node.value, readNumber("nttTouchStake", 1), { preserveBlank: true });
          updateNoTouchStakeCustomFlag();
          scheduleExpectedProfitPreview(80);
        }
        if (id === "nttTouchBarrier" || id === "nttNoTouchBarrier") {
          const normalized = normalizeBarrierField(id, { preserveBlank: true });
          if (normalized) {
            persistCurrentMarketBarrierSettings(null, { custom: true });
            scheduleCurrentMarketBarrierSync(null, { custom: true });
          }
          renderBarrierMarketChart((state.lastPayload && state.lastPayload.ntt) || {}, state.lastPayload || {});
          scheduleExpectedProfitPreview(80);
        }
        if (id === "nttKoolkidTouchBarrier" || id === "nttKoolkidNoTouchBarrier") {
          normalizeBarrierField(id, { preserveBlank: true });
        }
      });
      node.addEventListener("keydown", (evt) => {
        if (evt.key === "Enter") {
          evt.preventDefault();
          saveSettings(true).catch(() => {});
        }
      });
    });
  }
  function bindSymbolPicker() {
    const picker = el("symbol");
    if (!picker || picker.dataset.nttSymbolBound === "1") return;
    picker.dataset.nttSymbolBound = "1";
    picker.addEventListener("change", () => {
      const previousSymbol = normalizeMarketSymbol(state.lastMainSymbol || "");
      if (previousSymbol) {
        persistCurrentMarketBarrierSettings(previousSymbol, {
          custom: hasDirtyBarrierFields(),
        });
      }
    }, true);
  }
  function bindUI(root) {
    if (!root || root.dataset.nttUiBound === "1") return;
    root.dataset.nttUiBound = "1";
    root.querySelectorAll("[data-action]").forEach((btn) => {
      if (btn.dataset.nttActionBound === "1") return;
      btn.dataset.nttActionBound = "1";
      btn.addEventListener("click", (evt) => {
        evt.preventDefault();
        handleAction(btn.dataset.action, btn).catch(() => {});
      });
    });
    const modal = el("nttKoolkidBody");
    if (modal && modal.dataset.nttModalBound !== "1") {
      modal.dataset.nttModalBound = "1";
      modal.addEventListener("click", (evt) => {
        if (evt.target === modal && state.koolkidPanelOpen) toggleKoolkidPanel();
      });
    }
    const autoModal = el("nttAutoBody");
    if (autoModal && autoModal.dataset.nttModalBound !== "1") {
      autoModal.dataset.nttModalBound = "1";
      autoModal.addEventListener("click", (evt) => {
        if (evt.target === autoModal && state.autoPanelOpen) closeAutoBothPanel();
      });
    }
    const martingaleToggle = el("nttAutoMartingaleToggle");
    if (martingaleToggle && martingaleToggle.dataset.nttAutoBound !== "1") {
      martingaleToggle.dataset.nttAutoBound = "1";
      martingaleToggle.addEventListener("change", () => {
        if (martingaleToggle.checked) {
          const step50Node = el("nttAutoStep50Toggle");
          if (step50Node) step50Node.checked = false;
        }
        applyAutoBothModeToggles();
      });
    }
    const step50Toggle = el("nttAutoStep50Toggle");
    if (step50Toggle && step50Toggle.dataset.nttAutoBound !== "1") {
      step50Toggle.dataset.nttAutoBound = "1";
      step50Toggle.addEventListener("change", () => {
        if (step50Toggle.checked) {
          const martingaleNode = el("nttAutoMartingaleToggle");
          if (martingaleNode) martingaleNode.checked = false;
        }
        applyAutoBothModeToggles();
      });
    }
    applyKoolkidReversalToggle();
    applyKoolkidHalfBarrierToggle();
    applyAutoBothModeToggles();
    bindFormInputs();
    bindSymbolPicker();
  }
  function startPolling() {
    if (state.pollTimer) clearInterval(state.pollTimer);
    state.pollTimer = setInterval(() => {
      if (!isActive()) return;
      refreshStatus(true).catch(() => {});
    }, 2500);
  }
  function stopPolling() {
    if (state.pollTimer) clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
  async function onMount(ctx) {
    bindUI((ctx && ctx.root) || el("nttRoot"));
    bindSocket();
    applyDurationPresets("nttDuration", "nttDurationUnit", readInteger("nttDuration", 5));
    applyDurationPresets("nttTouchDuration", "nttTouchDurationUnit", readInteger("nttTouchDuration", 5));
    applyDurationPresets("nttNoTouchDuration", "nttNoTouchDurationUnit", readInteger("nttNoTouchDuration", 5));
    updateDurationModeUI(true);
    applyAutoSlBtn();
    scheduleExpectedProfitPreview(25);
    if (isActive()) {
      startPolling();
      await refreshStatus(true);
    }
  }
  async function afterLoadProfileUI() {
    bindUI(el("nttRoot"));
    bindSocket();
    applyDurationPresets("nttDuration", "nttDurationUnit", readInteger("nttDuration", 5));
    applyDurationPresets("nttTouchDuration", "nttTouchDurationUnit", readInteger("nttTouchDuration", 5));
    applyDurationPresets("nttNoTouchDuration", "nttNoTouchDurationUnit", readInteger("nttNoTouchDuration", 5));
    updateDurationModeUI(true);
    applyAutoSlBtn();
    scheduleExpectedProfitPreview(25);
    if (isActive()) {
      startPolling();
      await refreshStatus(true);
    }
  }
  async function onActivate() {
    startPolling();
    bindSocket();
    scheduleExpectedProfitPreview(25);
    await refreshStatus(true);
  }

  window.registerProfileModule(PROFILE, {
    onMount,
    afterLoadProfileUI,
    onActivate,
  });
})();
