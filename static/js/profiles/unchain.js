(function () {
  const PROFILE = "UNCHAIN";
  const state = {
    socketBound: false,
    lastSocket: null,
    auto_sl: true,
    half_barrier_enabled: false,
    koolkid_reversal_enabled: false,
    koolkid_half_barrier_enabled: false,
    pollTimer: null,
    lastPayload: null,
    scanner: null,
    bothAnalyzerEnabled: false,
    koolkidPanelOpen: false,
    dirtyFields: new Set(),
    isSaving: false,
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
    tradeCountdownToastEl: null,
    lastMainSymbol: null,
    lastBarrierKey: null,
    marketBarrierSyncInFlight: false,
    marketBarrierSyncSignature: "",
    marketBarrierSyncTimer: null,
    marketBarrierStore: {},
  };

  const FORM_FIELDS = [
    "unchainHigherStake",
    "unchainLowerStake",
    "unchainHigherBarrier",
    "unchainLowerBarrier",
    "unchainKoolkidHigherBarrier",
    "unchainKoolkidLowerBarrier",
    "unchainKoolkidSimDuration",
    "unchainKoolkidSimDurationUnit",
    "unchainKoolkidLiveDuration",
    "unchainKoolkidLiveDurationUnit",
    "unchainKoolkidHlLossPct",
    "unchainDuration",
    "unchainDurationUnit",
    "unchainTp",
    "unchainSl",
    "unchainAutoConfidence",
    "unchainAutoMinMovement",
    "unchainAutoMinTickSpeed",
    "unchainAutoMinRange",
  ];
  const MARKET_BARRIER_STORAGE_KEY = "unchainMarketBarrierSettingsV2";
  try {
    if (window.localStorage) window.localStorage.removeItem(MARKET_BARRIER_STORAGE_KEY);
  } catch (e) {}
  const BARRIER_FIELD_IDS = new Set([
    "unchainHigherBarrier",
    "unchainLowerBarrier",
    "unchainKoolkidHigherBarrier",
    "unchainKoolkidLowerBarrier",
  ]);

  const range = (start, end, step = 1) => {
    const arr = [];
    for (let v = start; v <= end; v += step) arr.push(v);
    return arr;
  };
  const DURATION_PRESETS = {
    t: range(5, 10, 1),
    s: range(15, 59, 1),
    m: range(1, 59, 1),
    h: range(1, 24, 1),
  };
  function App() { return window.BotApp || {}; }
  function isActive() { try { return typeof activeProfile !== "undefined" && activeProfile === PROFILE; } catch (e) { return false; } }
  function el(id) { return document.getElementById(id); }
  function setText(id, v) { const n = el(id); if (n) n.innerText = v == null ? "—" : String(v); }
  function toast(msg, type) { try { if (typeof showToast === "function") showToast(msg, type || "info"); } catch (e) {} }

  function ensureTradeCountdownToast() {
    const container = document.getElementById("toastContainer");
    if (!container) return null;
    let toastEl = state.tradeCountdownToastEl;
    if (toastEl && !container.contains(toastEl)) {
      state.tradeCountdownToastEl = null;
      toastEl = null;
    }
    if (!toastEl) {
      toastEl = document.createElement("div");
      toastEl.className = "toast info";
      toastEl.dataset.unchainCountdownToast = "1";
      container.prepend(toastEl);
      requestAnimationFrame(() => {
        try { toastEl.classList.add("show"); } catch (e) {}
      });
      state.tradeCountdownToastEl = toastEl;
    }
    return toastEl;
  }

  function removeTradeCountdownToast() {
    const toastEl = state.tradeCountdownToastEl;
    if (!toastEl) return;
    state.tradeCountdownToastEl = null;
    try { toastEl.classList.remove("show"); } catch (e) {}
    setTimeout(() => {
      try {
        if (toastEl.parentNode) toastEl.parentNode.removeChild(toastEl);
      } catch (e) {}
    }, 250);
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

  async function getJSON(url) {
    const res = await fetch(url, { method: "GET" });
    let data = {};
    try { data = await res.json(); } catch (e) {}
    return { ok: res.ok, data };
  }

  function markDirty(id) {
    if (!id) return;
    state.dirtyFields.add(id);
  }

  function clearDirtyFields() {
    state.dirtyFields.clear();
  }

  function isFieldDirty(id) {
    return state.dirtyFields.has(id);
  }

  function readNumber(id, fallback) {
    const node = el(id);
    const raw = node ? String(node.value || "").trim() : "";
    const num = parseFloat(raw);
    return Number.isFinite(num) ? num : fallback;
  }

  function readInteger(id, fallback) {
    const node = el(id);
    const raw = node ? String(node.value || "").trim() : "";
    const num = parseInt(raw, 10);
    return Number.isFinite(num) ? num : fallback;
  }

  function readText(id, fallback) {
    const node = el(id);
    const raw = node ? String(node.value || "").trim() : "";
    return raw || fallback;
  }

  function formatBarrierInputValue(v, fallback) {
    const n = Number(v);
    const safe = Number.isFinite(n) ? n : Number(fallback);
    if (!Number.isFinite(safe)) return String(fallback);
    const absText = Math.abs(safe).toFixed(2);
    return `${safe < 0 ? "-" : "+"}${absText || "0"}`;
  }

  function scaleBarrierText(rawValue, factor, fallback) {
    const scaled = num(rawValue, fallback) * Number(factor || 1);
    return formatBarrierInputValue(scaled, num(fallback, 0));
  }

  function flipBarrierSignText(rawValue, fallback) {
    const flipped = -num(rawValue, fallback);
    return formatBarrierInputValue(flipped, num(fallback, 0));
  }

  function getDisplayedBarrierText(rawValue, fallback, halfEnabled) {
    const source = String(rawValue == null || rawValue === "" ? formatBarrierInputValue(fallback, fallback) : rawValue).trim();
    return halfEnabled ? scaleBarrierText(source, 0.5, fallback) : source;
  }

  function normalizeMarketSymbol(symbol) {
    return String(symbol || "").trim().toUpperCase();
  }

  function getCurrentMarketSymbol() {
    const payload = state.lastPayload && (state.lastPayload.unchain || state.lastPayload);
    const payloadSymbol = normalizeMarketSymbol(
      (state.lastPayload && (state.lastPayload.main_symbol || state.lastPayload.symbol)) ||
      (payload && (payload.main_symbol || payload.symbol)) ||
      state.lastMainSymbol
    );
    if (payloadSymbol) return payloadSymbol;
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
    const higher = String(src.higher_barrier != null ? src.higher_barrier : "+0.12").trim() || "+0.12";
    const lower = String(src.lower_barrier != null ? src.lower_barrier : "-0.12").trim() || "-0.12";
    const koolkidHigher = String(src.koolkid_higher_barrier != null ? src.koolkid_higher_barrier : higher).trim() || higher;
    const koolkidLower = String(src.koolkid_lower_barrier != null ? src.koolkid_lower_barrier : lower).trim() || lower;
    const isCustom = !!src.is_custom;
    return {
      higher_barrier: higher,
      lower_barrier: lower,
      koolkid_higher_barrier: koolkidHigher,
      koolkid_lower_barrier: koolkidLower,
      is_custom: isCustom,
    };
  }

  function buildMarketBarrierSignature(symbol, settings) {
    const sym = normalizeMarketSymbol(symbol);
    if (!sym || !settings) return "";
    const safe = buildMarketBarrierSettings(settings);
    return [
      sym,
      safe.higher_barrier,
      safe.lower_barrier,
      safe.koolkid_higher_barrier,
      safe.koolkid_lower_barrier,
      safe.is_custom ? "CUSTOM" : "DEFAULT",
    ].join("|");
  }

  function areBarrierSettingsEqual(a, b) {
    const left = buildMarketBarrierSettings(a);
    const right = buildMarketBarrierSettings(b);
    return (
      left.higher_barrier === right.higher_barrier &&
      left.lower_barrier === right.lower_barrier &&
      left.koolkid_higher_barrier === right.koolkid_higher_barrier &&
      left.koolkid_lower_barrier === right.koolkid_lower_barrier
    );
  }

  function getSavedMarketBarrierSettings(symbol) {
    const sym = normalizeMarketSymbol(symbol);
    if (!sym) return null;
    const store = getMarketBarrierStore();
    if (!store || !store[sym]) return null;
    return buildMarketBarrierSettings(store[sym]);
  }

  window.addEventListener("bot-transient-reset", () => {
    state.marketBarrierStore = {};
    state.lastBarrierKey = null;
    state.marketBarrierSyncSignature = "";
  });

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

  function getPayloadMarketBarrierSettings(un) {
    if (!un) return null;
    return buildMarketBarrierSettings({
      higher_barrier: un.higher_barrier,
      lower_barrier: un.lower_barrier,
      koolkid_higher_barrier: un.koolkid_higher_barrier,
      koolkid_lower_barrier: un.koolkid_lower_barrier,
    });
  }

  function readCurrentMarketBarrierSettings() {
    const form = readForm();
    return buildMarketBarrierSettings(form);
  }

  function persistCurrentMarketBarrierSettings(symbolOverride, opts) {
    const sym = normalizeMarketSymbol(symbolOverride || getCurrentMarketSymbol());
    if (!sym) return null;
    return persistMarketBarrierSettings(sym, readCurrentMarketBarrierSettings(), opts);
  }

  function seedMarketBarrierSettingsFromPayload(symbol, un) {
    const sym = normalizeMarketSymbol(symbol);
    if (!sym || !un) return null;
    const existing = getSavedMarketBarrierSettings(sym);
    const payloadSettings = getPayloadMarketBarrierSettings(un);
    if (existing && existing.is_custom) {
      if (payloadSettings && areBarrierSettingsEqual(existing, payloadSettings)) {
        return persistMarketBarrierSettings(sym, payloadSettings, { custom: false });
      }
      return existing;
    }
    return persistMarketBarrierSettings(sym, payloadSettings, { custom: false });
  }

  function applySavedMarketBarrierSettingsToForm(settings, force) {
    if (!settings) return;
    const safe = buildMarketBarrierSettings(settings);
    setFieldValue("unchainHigherBarrier", getDisplayedBarrierText(safe.higher_barrier, 0.12, !!state.half_barrier_enabled), !!force);
    setFieldValue("unchainLowerBarrier", getDisplayedBarrierText(safe.lower_barrier, -0.12, !!state.half_barrier_enabled), !!force);
    setFieldValue("unchainKoolkidHigherBarrier", getDisplayedBarrierText(safe.koolkid_higher_barrier, 0.06, !!state.koolkid_half_barrier_enabled), !!force);
    setFieldValue("unchainKoolkidLowerBarrier", getDisplayedBarrierText(safe.koolkid_lower_barrier, -0.06, !!state.koolkid_half_barrier_enabled), !!force);
  }

  async function syncSavedMarketBarrierSettingsToServer(symbol, settings) {
    const sym = normalizeMarketSymbol(symbol);
    if (!sym || !settings) return null;
    if (sym !== getCurrentMarketSymbol()) return null;
    const normalized = buildMarketBarrierSettings(settings);
    if (!normalized.is_custom) return { ok: true, skipped: true };
    const nextSignature = buildMarketBarrierSignature(sym, normalized);
    if (!nextSignature) return null;
    const payload = state.lastPayload && (state.lastPayload.unchain || state.lastPayload);
    const currentSignature = buildMarketBarrierSignature(sym, getPayloadMarketBarrierSettings(payload));
    if (currentSignature === nextSignature) return { ok: true, skipped: true };
    if (state.marketBarrierSyncInFlight && state.marketBarrierSyncSignature === nextSignature) {
      return { ok: true, skipped: true };
    }
    state.marketBarrierSyncInFlight = true;
    state.marketBarrierSyncSignature = nextSignature;
    try {
      const r = await postJSON("/unchain_settings", normalized);
      if (r && r.ok && r.data) {
        renderPayload(r.data, { forceForm: false });
      }
      return r;
    } catch (e) {
      return null;
    } finally {
      state.marketBarrierSyncInFlight = false;
    }
  }

  function scheduleCurrentMarketBarrierSync(symbolOverride, opts) {
    const sym = normalizeMarketSymbol(symbolOverride || getCurrentMarketSymbol());
    if (!sym) return;
    const savedNow = persistCurrentMarketBarrierSettings(sym, opts);
    if (state.marketBarrierSyncTimer) {
      clearTimeout(state.marketBarrierSyncTimer);
      state.marketBarrierSyncTimer = null;
    }
    if (!(savedNow && savedNow.is_custom)) return;
    state.marketBarrierSyncTimer = setTimeout(() => {
      state.marketBarrierSyncTimer = null;
      const currentSymbol = getCurrentMarketSymbol();
      if (sym !== currentSymbol) return;
      const saved = getSavedMarketBarrierSettings(sym);
      if (!(saved && saved.is_custom)) return;
      syncSavedMarketBarrierSettingsToServer(sym, saved).catch(() => {});
    }, 180);
  }

  function hasDirtyBarrierFields() {
    let anyDirty = false;
    for (const id of BARRIER_FIELD_IDS) {
      if (isFieldDirty(id)) {
        anyDirty = true;
        break;
      }
    }
    if (!anyDirty) return false;
    const payload = state.lastPayload && (state.lastPayload.unchain || state.lastPayload);
    const payloadSettings = getPayloadMarketBarrierSettings(payload);
    if (!payloadSettings) return true;
    return !areBarrierSettingsEqual(readCurrentMarketBarrierSettings(), payloadSettings);
  }

  function readForm() {
    const autoConfidence = Math.max(45, Math.min(80, readNumber("unchainAutoConfidence", 48)));
    const autoMinMovement = Math.max(0.00001, readNumber("unchainAutoMinMovement", 0.06));
    const autoMinTickSpeed = Math.max(0.05, Math.min(10, readNumber("unchainAutoMinTickSpeed", 2.4)));
    const autoMinRange = Math.max(0.00001, readNumber("unchainAutoMinRange", 0.12));
    const halfBarrierToggle = el("unchainHalfBarrierToggle");
    const halfBarrierEnabled = halfBarrierToggle ? !!halfBarrierToggle.checked : !!state.half_barrier_enabled;
    const koolkidReversalToggle = el("unchainKoolkidReversalToggle");
    const koolkidReversalEnabled = koolkidReversalToggle ? !!koolkidReversalToggle.checked : !!state.koolkid_reversal_enabled;
    const koolkidHalfBarrierToggle = el("unchainKoolkidHalfBarrierToggle");
    const koolkidHalfBarrierEnabled = koolkidHalfBarrierToggle ? !!koolkidHalfBarrierToggle.checked : !!state.koolkid_half_barrier_enabled;
    const higherBarrierRaw = readText("unchainHigherBarrier", "+0.12");
    const lowerBarrierRaw = readText("unchainLowerBarrier", "-0.12");
    const koolkidHigherBarrierRaw = readText("unchainKoolkidHigherBarrier", "+0.06");
    const koolkidLowerBarrierRaw = readText("unchainKoolkidLowerBarrier", "-0.06");
    return {
      higher_stake: readNumber("unchainHigherStake", 1),
      lower_stake: readNumber("unchainLowerStake", 1),
      higher_barrier: halfBarrierEnabled ? scaleBarrierText(higherBarrierRaw, 2, 0.12) : higherBarrierRaw,
      lower_barrier: halfBarrierEnabled ? scaleBarrierText(lowerBarrierRaw, 2, -0.12) : lowerBarrierRaw,
      koolkid_higher_barrier: koolkidHalfBarrierEnabled ? scaleBarrierText(koolkidHigherBarrierRaw, 2, 0.06) : koolkidHigherBarrierRaw,
      koolkid_lower_barrier: koolkidHalfBarrierEnabled ? scaleBarrierText(koolkidLowerBarrierRaw, 2, -0.06) : koolkidLowerBarrierRaw,
      koolkid_sim_duration: Math.max(1, Math.min(59, readInteger("unchainKoolkidSimDuration", 15))),
      koolkid_sim_duration_unit: readText("unchainKoolkidSimDurationUnit", "s").toLowerCase(),
      koolkid_live_duration: Math.max(1, Math.min(59, readInteger("unchainKoolkidLiveDuration", 5))),
      koolkid_live_duration_unit: readText("unchainKoolkidLiveDurationUnit", "t").toLowerCase(),
      koolkid_hl_loss_trigger_pct: Math.max(50, Math.min(70, readInteger("unchainKoolkidHlLossPct", 50))),
      koolkid_reversal_enabled: koolkidReversalEnabled,
      koolkid_half_barrier_enabled: koolkidHalfBarrierEnabled,
      duration: readInteger("unchainDuration", 5),
      duration_unit: readText("unchainDurationUnit", "t").toLowerCase(),
      tp: readNumber("unchainTp", 0),
      sl: readNumber("unchainSl", 0),
      auto_sl: !!state.auto_sl,
      half_barrier_enabled: halfBarrierEnabled,
      auto_start_threshold: autoConfidence,
      auto_min_movement: autoMinMovement,
      auto_min_tick_speed: autoMinTickSpeed,
      auto_min_range: autoMinRange,
    };
  }


  function num(v, d) {
    const n = Number(v);
    return Number.isFinite(n) ? n : d;
  }

  function escapeHtml(v) {
    return String(v == null ? "" : v)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatBarrierNumber(v) {
    const n = Number(v);
    if (!Number.isFinite(n)) return "—";
    return `${n >= 0 ? "+" : ""}${n.toFixed(2)}`;
  }

  function formatInputNumber(v, fallback) {
    const n = Number(v);
    const safe = Number.isFinite(n) ? n : fallback;
    if (!Number.isFinite(safe)) return String(fallback);
    return String(safe.toFixed(10)).replace(/\.?0+$/, "");
  }

  function formatKoolkidDurationText(value, unit) {
    const amount = Number(value);
    const safe = Number.isFinite(amount) ? Math.max(0, Math.floor(amount)) : 0;
    const cleaned = String(unit || "s").toLowerCase();
    if (cleaned === "t") return `${safe}T`;
    if (cleaned === "m") return `${safe}m`;
    return `${safe}s`;
  }

  function isReasonableBaseSpot(base, live) {
    const b = Number(base);
    if (!Number.isFinite(b) || b <= 0) return false;
    const p = Number(live);
    if (!Number.isFinite(p) || p <= 0) return true;
    const drift = Math.abs(b - p) / Math.max(Math.abs(p), 1);
    return drift <= 0.35;
  }

  function getBarrierInputs(un) {
    const higherField = el("unchainHigherBarrier");
    const lowerField = el("unchainLowerBarrier");
    const higherRaw = higherField ? String(higherField.value || "").trim() : "";
    const lowerRaw = lowerField ? String(lowerField.value || "").trim() : "";
    const halfBarrier = !!(state.half_barrier_enabled || (un && un.half_barrier_enabled));
    const higher = num(
      higherRaw !== "" ? higherRaw : getDisplayedBarrierText((un && un.higher_barrier) != null ? un.higher_barrier : "+0.12", 0.12, halfBarrier),
      halfBarrier ? 0.06 : 0.12,
    );
    const lower = num(
      lowerRaw !== "" ? lowerRaw : getDisplayedBarrierText((un && un.lower_barrier) != null ? un.lower_barrier : "-0.12", -0.12, halfBarrier),
      halfBarrier ? -0.06 : -0.12,
    );
    return {
      higher,
      lower,
      top: Math.max(higher, lower),
      bottom: Math.min(higher, lower),
    };
  }

  function resetBarrierChartBase(price, symbol) {
    const p = Number(price);
    if (!Number.isFinite(p)) return;
    state.marketChart.basePrice = p;
    state.marketChart.previewBasePrice = p;
    state.marketChart.previewBaseSymbol = symbol || state.marketChart.lastSymbol || null;
    state.marketChart.wasActiveTrade = false;
    state.marketChart.lastPrice = p;
    state.marketChart.lastSymbol = symbol || state.marketChart.lastSymbol || null;
    state.marketChart.history = [{ price: p, offset: 0, t: Date.now() }];
  }

  function pushBarrierChartPrice(price, symbol) {
    const p = Number(price);
    if (!Number.isFinite(p)) return;
    const s = symbol || state.marketChart.lastSymbol || null;
    if (state.marketChart.basePrice == null || (s && state.marketChart.lastSymbol && s !== state.marketChart.lastSymbol)) {
      resetBarrierChartBase(p, s);
    }
    state.marketChart.lastSymbol = s || state.marketChart.lastSymbol;
    state.marketChart.lastPrice = p;
    if (state.marketChart.basePrice == null) state.marketChart.basePrice = p;
    state.marketChart.history.push({ price: p, offset: p - state.marketChart.basePrice, t: Date.now() });
    // Keep a fixed base so barrier offsets remain stable; just trim history without re-basing.
    if (state.marketChart.history.length > state.marketChart.maxPoints) {
      state.marketChart.history = state.marketChart.history.slice(-state.marketChart.maxPoints);
    }
  }

  function setBarrierZoneStatus(text, tone) {
    const box = el("unchainBarrierZoneState");
    if (!box) return;
    let bg = "#1e293b";
    let fg = "#e2e8f0";
    let dot = "#38bdf8";
    if (tone === "above") { bg = "rgba(34,197,94,0.16)"; fg = "#bbf7d0"; dot = "#22c55e"; }
    else if (tone === "below") { bg = "rgba(239,68,68,0.16)"; fg = "#fecaca"; dot = "#ef4444"; }
    else if (tone === "middle") { bg = "rgba(245,158,11,0.18)"; fg = "#fde68a"; dot = "#f59e0b"; }
    else if (tone === "wait") { bg = "rgba(148,163,184,0.16)"; fg = "#e2e8f0"; dot = "#38bdf8"; }
    box.style.background = bg;
    box.style.color = fg;
    box.style.borderColor = "rgba(148,163,184,0.22)";
    box.innerHTML = `<span class="dot" style="background:${dot};box-shadow:0 0 0 4px ${tone === "above" ? "rgba(34,197,94,0.18)" : tone === "below" ? "rgba(239,68,68,0.18)" : tone === "middle" ? "rgba(245,158,11,0.20)" : "rgba(56,189,248,0.18)"};"></span><span>${escapeHtml(text)}</span>`;
  }

  function renderBarrierMarketChart(un, payload) {
    const svg = el("unchainBarrierMarketChart");
    if (!svg) return;

    const liveCandidate = num(payload && (payload.price != null ? payload.price : payload.quote), null);
    if (Number.isFinite(liveCandidate)) pushBarrierChartPrice(liveCandidate, payload && payload.symbol);

    const barriers = getBarrierInputs(un || {});
    const higher = barriers.higher;
    const lower = barriers.lower;
    const topBarrier = barriers.top;
    const bottomBarrier = barriers.bottom;
    const history = Array.isArray(state.marketChart.history) ? state.marketChart.history : [];
    const activeEntries = Array.isArray(un && un.active_contracts)
      ? un.active_contracts.filter((item) => item && !item.is_sold)
      : [];
    activeEntries.sort((a, b) => {
      const ta = Date.parse(String(a.updated_at || a.time || "")) || 0;
      const tb = Date.parse(String(b.updated_at || b.time || "")) || 0;
      return tb - ta;
    });
    const anchorEntry = activeEntries[0] || null;
    const hasActiveContract = !!anchorEntry;
    const activeEntrySpot = num(anchorEntry && anchorEntry.entry_spot, null);
    const priceHigh = history.length ? Math.max(...history.map((p) => Number(p.price || p.quote || 0))) : null;
    const priceLow = history.length ? Math.min(...history.map((p) => Number(p.price || p.quote || 0))) : null;
    const priceLabel = el("unchainPriceRangeLabel");
    if (priceLabel) {
      if (priceHigh != null && priceLow != null && Number.isFinite(priceHigh) && Number.isFinite(priceLow)) {
        priceLabel.innerText = `Price range: ${priceLow.toFixed(2)} – ${priceHigh.toFixed(2)} (width ${(priceHigh - priceLow).toFixed(2)})`;
      } else {
        priceLabel.innerText = "Price range: —";
      }
    }
    const stats = el("unchainBarrierChartStats");
    const meta = el("unchainBarrierChartMeta");

    if (!history.length) {
      svg.innerHTML = `<rect x="0" y="0" width="760" height="260" rx="18" fill="#020617"></rect><text x="380" y="132" text-anchor="middle" fill="#94a3b8" font-size="15" font-weight="700">Waiting for live market price…</text>`;
      if (stats) stats.innerText = `Higher ${formatBarrierNumber(higher)} • Lower ${formatBarrierNumber(lower)} • Middle zone ${Math.abs(topBarrier - bottomBarrier).toFixed(2)} wide`;
      if (meta) meta.innerText = "Live market line will appear here and show when price is inside the middle zone or breaks above/below it.";
      setBarrierZoneStatus("WAITING FOR LIVE PRICE", "wait");
      return;
    }

    const width = 760, height = 260, left = 16, right = width - 16, top = 18, bottom = height - 28;
    const chartW = right - left, chartH = bottom - top;
    const latestPrice = num(history[history.length - 1] && history[history.length - 1].price, null);
    const hasActiveEntrySpot = hasActiveContract && isReasonableBaseSpot(activeEntrySpot, latestPrice);
    const symbolNow = state.marketChart.lastSymbol || (payload && payload.symbol) || null;
    if (hasActiveContract) {
      state.marketChart.wasActiveTrade = true;
    } else {
      const previewSymbolChanged = symbolNow && state.marketChart.previewBaseSymbol && symbolNow !== state.marketChart.previewBaseSymbol;
      const needsPreviewReset = !Number.isFinite(num(state.marketChart.previewBasePrice, null)) || previewSymbolChanged || state.marketChart.wasActiveTrade;
      if (needsPreviewReset && Number.isFinite(latestPrice)) {
        state.marketChart.previewBasePrice = latestPrice;
        state.marketChart.previewBaseSymbol = symbolNow || state.marketChart.previewBaseSymbol || state.marketChart.lastSymbol || null;
      }
      state.marketChart.wasActiveTrade = false;
    }

    let basePrice = hasActiveEntrySpot ? activeEntrySpot : num(state.marketChart.previewBasePrice, null);
    if (!Number.isFinite(basePrice)) basePrice = num(state.marketChart.basePrice, null);
    if (!Number.isFinite(basePrice)) basePrice = num(history[0] && history[0].price, null);
    if (!Number.isFinite(basePrice)) basePrice = num(latestPrice, 0);
    const offsets = history.map((point) => num(point && point.price, basePrice) - basePrice);
    const currentOffset = num(latestPrice, basePrice) - basePrice;
    const rangeHigh = offsets.length ? Math.max(...offsets) : 0;
    const rangeLow = offsets.length ? Math.min(...offsets) : 0;
    const rangeWidth = rangeHigh - rangeLow;
    const rangeMax = Math.max(0.18, ...offsets.map((v) => Math.abs(v)), Math.abs(higher), Math.abs(lower), Math.abs(topBarrier), Math.abs(bottomBarrier)) * 1.18;
    const toY = (value) => top + (rangeMax - value) / (rangeMax * 2) * chartH;
    const toX = (index) => left + (history.length <= 1 ? chartW : (index / (history.length - 1)) * chartW);
    const polyline = offsets.map((value, index) => `${toX(index).toFixed(1)},${toY(value).toFixed(1)}`).join(" ");
    const gridVals = [-rangeMax, -rangeMax / 2, 0, rangeMax / 2, rangeMax];
    const grid = gridVals.map((value) => {
      const y = toY(value);
      return `<line x1="${left}" y1="${y.toFixed(1)}" x2="${right}" y2="${y.toFixed(1)}" stroke="rgba(148,163,184,${value === 0 ? 0.28 : 0.12})" stroke-width="${value === 0 ? 1.4 : 1}" stroke-dasharray="${value === 0 ? "0" : "5 6"}"></line><text x="${right - 4}" y="${(y - 6).toFixed(1)}" text-anchor="end" fill="#64748b" font-size="10">${formatBarrierNumber(value)}</text>`;
    }).join("");

    const higherY = toY(higher);
    const lowerY = toY(lower);
    const zoneTopOffset = topBarrier;
    const zoneBottomOffset = bottomBarrier;
    const zoneTopY = toY(zoneTopOffset);
    const zoneBottomY = toY(zoneBottomOffset);
    const lineColor = currentOffset >= 0 ? "#38bdf8" : "#c084fc";
    const direction = offsets.length > 1 ? (offsets[offsets.length - 1] - offsets[Math.max(0, offsets.length - 2)]) : 0;

    const epsilon = Math.max(0.00002, Math.abs(zoneTopOffset - zoneBottomOffset) * 0.001);
    const span = Math.max(0.000001, zoneTopOffset - zoneBottomOffset);
    const posPct = Math.min(1, Math.max(0, (currentOffset - zoneBottomOffset) / span));
    const higherNowWin = currentOffset >= (higher - epsilon);
    const lowerNowWin = currentOffset <= (lower + epsilon);
    let zoneText = "PREVIEW MODE • NO ACTIVE TRADE";
    let tone = "wait";
    if (hasActiveEntrySpot) {
      zoneText = "MIDDLE ZONE • BOTH LOSING / WAIT";
      tone = "middle";
      if (currentOffset > zoneTopOffset + epsilon) { zoneText = "HIGHER WIN ZONE • LOWER LOSING"; tone = "above"; }
      else if (currentOffset < zoneBottomOffset - epsilon) { zoneText = "LOWER WIN ZONE • HIGHER LOSING"; tone = "below"; }
      else { zoneText = `MIDDLE ZONE • BOTH LOSING / WAIT • ${Math.round(posPct * 100)}%`; tone = "middle"; }
    } else if (hasActiveContract) {
      if (currentOffset > zoneTopOffset + epsilon) { zoneText = "ACTIVE TRADE • ABOVE UPPER ZONE"; tone = "above"; }
      else if (currentOffset < zoneBottomOffset - epsilon) { zoneText = "ACTIVE TRADE • BELOW LOWER ZONE"; tone = "below"; }
      else { zoneText = `ACTIVE TRADE • IN MIDDLE ZONE • ${Math.round(posPct * 100)}%`; tone = "middle"; }
    } else {
      if (currentOffset > zoneTopOffset + epsilon) { zoneText = "PREVIEW • ABOVE UPPER ZONE"; tone = "above"; }
      else if (currentOffset < zoneBottomOffset - epsilon) { zoneText = "PREVIEW • BELOW LOWER ZONE"; tone = "below"; }
      else { zoneText = `PREVIEW • IN MIDDLE ZONE • ${Math.round(posPct * 100)}%`; tone = "middle"; }
    }
    setBarrierZoneStatus(zoneText, tone);

    const higherSpot = Number.isFinite(Number(basePrice)) ? Number(basePrice) + Number(higher) : null;
    const lowerSpot = Number.isFinite(Number(basePrice)) ? Number(basePrice) + Number(lower) : null;
    if (stats) {
      const widthValue = Math.abs(zoneTopOffset - zoneBottomOffset);
      const higherLabel = higherSpot == null ? "—" : Number(higherSpot).toFixed(2);
      const lowerLabel = lowerSpot == null ? "—" : Number(lowerSpot).toFixed(2);
      if (hasActiveEntrySpot) {
        const higherState = higherNowWin ? "WINNING" : "LOSING";
        const lowerState = lowerNowWin ? "WINNING" : "LOSING";
        stats.innerText = `Base ${Number(basePrice).toFixed(2)} • Live ${Number(latestPrice).toFixed(2)} • Higher @ ${higherLabel} (${higherState}) • Lower @ ${lowerLabel} (${lowerState}) • Offset ${formatBarrierNumber(currentOffset)} • Middle zone ${widthValue.toFixed(2)} wide • Range ${rangeWidth.toFixed(3)}`;
      } else {
        const baseMode = hasActiveContract ? "Live base" : "Preview base";
        const suffix = hasActiveContract ? " • Active trade detected (waiting for reliable entry spot)" : "";
        stats.innerText = `${baseMode} ${Number(basePrice).toFixed(2)} • Live ${Number(latestPrice).toFixed(2)} • If enter now: Higher target ${higherLabel} / Lower target ${lowerLabel} • Need ${formatBarrierNumber(higher)} / ${formatBarrierNumber(lower)} • Middle zone ${widthValue.toFixed(2)} wide • Range ${rangeWidth.toFixed(3)}${suffix}`;
      }
    }
    if (meta) {
      if (hasActiveEntrySpot) {
        const toHigherWin = Number(higher - currentOffset).toFixed(3);
        const toLowerWin = Number(currentOffset - lower).toFixed(3);
        meta.innerText = `Range last ticks: ${rangeWidth.toFixed(3)} (high ${formatBarrierNumber(rangeHigh)}, low ${formatBarrierNumber(rangeLow)}). Position: ${Math.round(posPct * 100)}% inside middle zone (0% = lower edge, 100% = higher edge). Distance to win lines: ${toHigherWin} to HIGHER / ${toLowerWin} to LOWER. Using active entry spot ${Number(basePrice).toFixed(2)} as chart base.`;
      } else if (hasActiveContract) {
        meta.innerText = `Range last ticks: ${rangeWidth.toFixed(3)} (high ${formatBarrierNumber(rangeHigh)}, low ${formatBarrierNumber(rangeLow)}). Position now is ${Math.round(posPct * 100)}% inside your zone (0% lower edge, 100% upper edge). Active trade is open, but entry spot has not synced yet, so chart stays on live base until a reliable entry spot arrives.`;
      } else {
        meta.innerText = `No active trade. Entry preview mode is ON. Position now is ${Math.round(posPct * 100)}% inside your zone (0% lower edge, 100% upper edge). If entering now, HIGHER needs ${formatBarrierNumber(higher)} and LOWER needs ${formatBarrierNumber(lower)} from this preview base. Recent swing: ${rangeWidth.toFixed(3)} (high ${formatBarrierNumber(rangeHigh)}, low ${formatBarrierNumber(rangeLow)}).`;
      }
    }

    const latestX = toX(history.length - 1);
    const latestY = toY(currentOffset);
    const areaPath = `${left},${bottom} ${polyline} ${right},${bottom}`;
    const arrow = direction >= 0 ? "▲" : "▼";
    const rangeHighY = toY(rangeHigh);
    const rangeLowY = toY(rangeLow);
    const middleLabelY = Math.max(top + 12, Math.min(bottom - 8, ((zoneTopY + zoneBottomY) / 2 + 4)));

    svg.innerHTML = `
      <defs>
        <linearGradient id="unchainLineFill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stop-color="rgba(56,189,248,0.26)"></stop>
          <stop offset="100%" stop-color="rgba(56,189,248,0.03)"></stop>
        </linearGradient>
      </defs>
      <rect x="0" y="0" width="${width}" height="${height}" rx="18" fill="#020617"></rect>
      <rect x="${left}" y="${zoneTopY.toFixed(1)}" width="${chartW}" height="${Math.max(2, zoneBottomY - zoneTopY).toFixed(1)}" fill="rgba(245,158,11,0.12)" stroke="rgba(245,158,11,0.22)" stroke-dasharray="8 7"></rect>
      ${grid}
      <line x1="${left}" y1="${higherY.toFixed(1)}" x2="${right}" y2="${higherY.toFixed(1)}" stroke="#22c55e" stroke-width="2.4"></line>
      <line x1="${left}" y1="${lowerY.toFixed(1)}" x2="${right}" y2="${lowerY.toFixed(1)}" stroke="#ef4444" stroke-width="2.4"></line>
      <line x1="${left}" y1="${rangeHighY.toFixed(1)}" x2="${right}" y2="${rangeHighY.toFixed(1)}" stroke="#a855f7" stroke-width="1.6" stroke-dasharray="6 5"></line>
      <line x1="${left}" y1="${rangeLowY.toFixed(1)}" x2="${right}" y2="${rangeLowY.toFixed(1)}" stroke="#a855f7" stroke-width="1.6" stroke-dasharray="6 5"></line>
      <polygon points="${areaPath}" fill="url(#unchainLineFill)"></polygon>
      <polyline points="${polyline}" fill="none" stroke="${lineColor}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></polyline>
      <circle cx="${latestX.toFixed(1)}" cy="${latestY.toFixed(1)}" r="5.5" fill="${lineColor}" stroke="#e2e8f0" stroke-width="1.5"></circle>
      <text x="${left + 6}" y="${Math.max(16, higherY - 8).toFixed(1)}" fill="#86efac" font-size="11" font-weight="900">HIGHER ${escapeHtml(formatBarrierNumber(higher))}</text>
      <text x="${left + 6}" y="${Math.min(height - 10, lowerY - 8).toFixed(1)}" fill="#fca5a5" font-size="11" font-weight="900">LOWER ${escapeHtml(formatBarrierNumber(lower))}</text>
      <text x="${right - 6}" y="${middleLabelY.toFixed(1)}" text-anchor="end" fill="#fcd34d" font-size="11" font-weight="900">MIDDLE ZONE</text>
      <text x="${right - 6}" y="${Math.max(16, rangeHighY - 10).toFixed(1)}" text-anchor="end" fill="#a855f7" font-size="10" font-weight="800">RANGE HIGH</text>
      <text x="${right - 6}" y="${Math.min(height - 10, rangeLowY + 16).toFixed(1)}" text-anchor="end" fill="#a855f7" font-size="10" font-weight="800">RANGE LOW</text>
      <text x="${right - 6}" y="${Math.max(18, latestY - 10).toFixed(1)}" text-anchor="end" fill="#e2e8f0" font-size="11" font-weight="900">${arrow} ${escapeHtml(Number(latestPrice).toFixed(2))}</text>
    `;
  }

  function applyDurationPresets(forceSelect) {
    const unit = (el("unchainDurationUnit") || {}).value || "t";
    const select = el("unchainDuration");
    if (!select) return;
    const presets = DURATION_PRESETS[unit] || [];
    if (!presets.length) return;
    const presetKey = `${unit}:${presets.join(",")}`;
    const previousPresetKey = String(select.dataset.presetKey || "");
    const shouldRebuild = !!forceSelect || previousPresetKey !== presetKey || select.options.length !== presets.length;
    const current = select.value;
    if (shouldRebuild) {
      select.innerHTML = presets.map((v) => `<option value="${v}">${v}</option>`).join("");
      select.dataset.presetKey = presetKey;
    }
    const isValid = presets.some((v) => String(v) === String(current));
    if (!isValid) {
      select.value = String(presets[0] ?? current ?? 5);
      return;
    }
    if (shouldRebuild || forceSelect) {
      select.value = String(current);
    }
  }

  function applyAutoSlBtn() {
    const btn = el("unchainAutoSlBtn");
    if (!btn) return;
    btn.innerText = `AUTO SL: ${state.auto_sl ? "ON" : "OFF"}`;
    btn.style.background = state.auto_sl ? "#facc15" : "#64748b";
    btn.style.color = state.auto_sl ? "#111827" : "#fff";
  }

  function applyHalfBarrierToggle() {
    const wrap = el("unchainHalfBarrierWrap");
    const input = el("unchainHalfBarrierToggle");
    const label = el("unchainHalfBarrierState");
    if (input) input.checked = !!state.half_barrier_enabled;
    if (wrap) wrap.classList.toggle("is-on", !!state.half_barrier_enabled);
    if (label) label.innerText = state.half_barrier_enabled ? "ON" : "OFF";
  }

  function applyKoolkidReversalToggle() {
    const wrap = el("unchainKoolkidReversalWrap");
    const input = el("unchainKoolkidReversalToggle");
    const label = el("unchainKoolkidReversalState");
    if (input) input.checked = !!state.koolkid_reversal_enabled;
    if (wrap) wrap.classList.toggle("is-on", !!state.koolkid_reversal_enabled);
    if (label) label.innerText = state.koolkid_reversal_enabled ? "ON" : "OFF";
  }

  function applyKoolkidHalfBarrierToggle() {
    const wrap = el("unchainKoolkidHalfBarrierWrap");
    const input = el("unchainKoolkidHalfBarrierToggle");
    const label = el("unchainKoolkidHalfBarrierState");
    if (input) input.checked = !!state.koolkid_half_barrier_enabled;
    if (wrap) wrap.classList.toggle("is-on", !!state.koolkid_half_barrier_enabled);
    if (label) label.innerText = state.koolkid_half_barrier_enabled ? "ON" : "OFF";
  }

  function applyAutoConfidenceLabel() {
    const slider = el("unchainAutoConfidence");
    const label = el("unchainAutoConfidenceValue");
    if (!slider || !label) return;
    const v = Math.max(45, Math.min(80, Number(slider.value || 48)));
    slider.value = String(Math.round(v));
    label.innerText = `${Math.round(v)}%`;
  }

  function setFieldValue(id, value, force) {
    const node = el(id);
    if (!node) return;
    if (!force && (isFieldDirty(id) || document.activeElement === node)) return;
    node.value = value;
    if (id === "unchainDuration") {
      node.dataset.manual = "0";
    }
  }

  function mirrorHigherStakeToLower() {
    const higher = el("unchainHigherStake");
    const lower = el("unchainLowerStake");
    if (!higher || !lower) return;
    const raw = String(higher.value || "").trim();
    if (!raw) return;
    lower.value = raw;
    markDirty("unchainLowerStake");
  }

  function fillForm(un, force, opts) {
    if (!un) return;
    const options = opts || {};
    const barrierForce = !!force || !!options.forceBarriers;
    const halfEnabled = !!un.half_barrier_enabled;
    state.auto_sl = !!un.auto_sl;
    state.half_barrier_enabled = halfEnabled;
    state.koolkid_reversal_enabled = !!un.koolkid_reversal_enabled;
    state.koolkid_half_barrier_enabled = !!un.koolkid_half_barrier_enabled;
    setFieldValue("unchainHigherStake", formatInputNumber(un.higher_stake, 1), force);
    setFieldValue("unchainLowerStake", formatInputNumber(un.lower_stake, 1), force);
    setFieldValue("unchainHigherBarrier", getDisplayedBarrierText(un.higher_barrier || "+0.12", 0.12, halfEnabled), barrierForce);
    setFieldValue("unchainLowerBarrier", getDisplayedBarrierText(un.lower_barrier || "-0.12", -0.12, halfEnabled), barrierForce);
    setFieldValue("unchainKoolkidHigherBarrier", getDisplayedBarrierText(String(un.koolkid_higher_barrier || "+0.06"), 0.06, !!state.koolkid_half_barrier_enabled), barrierForce);
    setFieldValue("unchainKoolkidLowerBarrier", getDisplayedBarrierText(String(un.koolkid_lower_barrier || "-0.06"), -0.06, !!state.koolkid_half_barrier_enabled), barrierForce);
    setFieldValue("unchainKoolkidSimDuration", String(un.koolkid_sim_duration || 15), force);
    setFieldValue("unchainKoolkidSimDurationUnit", String(un.koolkid_sim_duration_unit || "s"), force);
    setFieldValue("unchainKoolkidLiveDuration", String(un.koolkid_live_duration || 5), force);
    setFieldValue("unchainKoolkidLiveDurationUnit", String(un.koolkid_live_duration_unit || "t"), force);
    setFieldValue("unchainKoolkidHlLossPct", String(un.koolkid_hl_loss_trigger_pct || 50), force);
    setFieldValue("unchainDurationUnit", (un.duration_unit || "t").toLowerCase(), force);
    setFieldValue("unchainDuration", String(un.duration || 5), force);
    applyDurationPresets(!!force);
    setFieldValue("unchainTp", String(un.tp || 0), force);
    setFieldValue("unchainSl", String(un.sl || 0), force);
    setFieldValue("unchainAutoConfidence", String(Math.max(45, Math.min(80, Number(un.auto_start_threshold || 48)))), force);
    setFieldValue("unchainAutoMinMovement", formatInputNumber(un.auto_min_movement, 0.06), force);
    setFieldValue("unchainAutoMinTickSpeed", formatInputNumber(un.auto_min_tick_speed, 2.4), force);
    setFieldValue("unchainAutoMinRange", formatInputNumber(un.auto_min_range, 0.12), force);
    applyAutoSlBtn();
    applyHalfBarrierToggle();
    applyKoolkidReversalToggle();
    applyKoolkidHalfBarrierToggle();
    applyAutoConfidenceLabel();
  }

  function syncHalfBarrierPreview() {
    renderBarrierMarketChart((state.lastPayload && (state.lastPayload.unchain || state.lastPayload)) || {}, state.lastPayload || {});
  }

  function transformHalfBarrierFieldValues(enabled) {
    const factor = enabled ? 0.5 : 2;
    const higherEl = el("unchainHigherBarrier");
    const lowerEl = el("unchainLowerBarrier");
    if (higherEl) {
      higherEl.value = scaleBarrierText(higherEl.value, factor, 0.12);
      markDirty("unchainHigherBarrier");
    }
    if (lowerEl) {
      lowerEl.value = scaleBarrierText(lowerEl.value, factor, -0.12);
      markDirty("unchainLowerBarrier");
    }
  }

  function transformKoolkidReversalFieldValues() {
    const higherEl = el("unchainKoolkidHigherBarrier");
    const lowerEl = el("unchainKoolkidLowerBarrier");
    if (higherEl) {
      higherEl.value = flipBarrierSignText(higherEl.value, 0.06);
      markDirty("unchainKoolkidHigherBarrier");
    }
    if (lowerEl) {
      lowerEl.value = flipBarrierSignText(lowerEl.value, -0.06);
      markDirty("unchainKoolkidLowerBarrier");
    }
  }

  function transformKoolkidHalfBarrierFieldValues(enabled) {
    const factor = enabled ? 0.5 : 2;
    const higherEl = el("unchainKoolkidHigherBarrier");
    const lowerEl = el("unchainKoolkidLowerBarrier");
    if (higherEl) {
      higherEl.value = scaleBarrierText(higherEl.value, factor, 0.06);
      markDirty("unchainKoolkidHigherBarrier");
    }
    if (lowerEl) {
      lowerEl.value = scaleBarrierText(lowerEl.value, factor, -0.06);
      markDirty("unchainKoolkidLowerBarrier");
    }
  }

  function applyMainBarrierPreset(side, rawValue) {
    const sideName = String(side || "").toUpperCase();
    const targetId = sideName === "LOWER" ? "unchainLowerBarrier" : "unchainHigherBarrier";
    const fallback = sideName === "LOWER" ? -0.12 : 0.12;
    const node = el(targetId);
    if (!node) return;
    const shownValue = getDisplayedBarrierText(String(rawValue || ""), fallback, !!state.half_barrier_enabled);
    node.value = shownValue;
    markDirty(targetId);
    persistCurrentMarketBarrierSettings(null, { custom: true });
    scheduleCurrentMarketBarrierSync(null, { custom: true });
    renderBarrierMarketChart((state.lastPayload && (state.lastPayload.unchain || state.lastPayload)) || {}, state.lastPayload || {});
  }

  function nudgeBarrierField(targetId, deltaValue) {
    const node = el(targetId);
    if (!node) return;
    const raw = String(node.value || "").trim();
    const targetText = String(targetId || "");
    const isKoolkidBarrier = targetText.toLowerCase().includes("koolkid");
    const baseIsLower = targetText.toLowerCase().includes("lower");
    const effectiveIsLower = isKoolkidBarrier && state.koolkid_reversal_enabled ? !baseIsLower : baseIsLower;
    const fallback = effectiveIsLower ? (isKoolkidBarrier ? -0.06 : -0.12) : (isKoolkidBarrier ? 0.06 : 0.12);
    const current = num(raw || fallback, fallback);
    const delta = num(deltaValue, 0);
    let next = Math.round((current + delta) * 100) / 100;
    if (effectiveIsLower) {
      const magnitude = Math.max(0.01, Math.round((Math.abs(current) + delta) * 100) / 100);
      next = -magnitude;
    } else {
      next = Math.max(0.01, Math.round((Math.abs(current) + delta) * 100) / 100);
    }
    node.value = formatBarrierInputValue(next, fallback);
    markDirty(targetId);
    persistCurrentMarketBarrierSettings(null, { custom: true });
    scheduleCurrentMarketBarrierSync(null, { custom: true });
    const un = state.lastPayload && (state.lastPayload.unchain || state.lastPayload);
    renderBarrierMarketChart(un || {}, state.lastPayload || {});
  }

  function bindHalfBarrierToggle() {
    const input = el("unchainHalfBarrierToggle");
    if (!input || input.dataset.unchainBound === "1") return;
    input.dataset.unchainBound = "1";
    input.addEventListener("change", async () => {
      const previous = !!state.half_barrier_enabled;
      const nextEnabled = !!input.checked;
      const higherEl = el("unchainHigherBarrier");
      const lowerEl = el("unchainLowerBarrier");
      const previousHigher = higherEl ? String(higherEl.value || "") : "";
      const previousLower = lowerEl ? String(lowerEl.value || "") : "";
      state.half_barrier_enabled = nextEnabled;
      transformHalfBarrierFieldValues(nextEnabled);
      applyHalfBarrierToggle();
      syncHalfBarrierPreview();
      const r = await saveSettings(false);
      if (!(r && r.ok)) {
        const fallbackPayload = state.lastPayload && (state.lastPayload.unchain || state.lastPayload);
        if (higherEl) higherEl.value = previousHigher;
        if (lowerEl) lowerEl.value = previousLower;
        state.half_barrier_enabled = fallbackPayload && typeof fallbackPayload.half_barrier_enabled !== "undefined"
          ? !!fallbackPayload.half_barrier_enabled
          : previous;
        applyHalfBarrierToggle();
        syncHalfBarrierPreview();
      }
    });
  }

  function bindKoolkidReversalToggle() {
    const input = el("unchainKoolkidReversalToggle");
    if (!input || input.dataset.unchainBound === "1") return;
    input.dataset.unchainBound = "1";
    input.addEventListener("change", async () => {
      const previous = !!state.koolkid_reversal_enabled;
      const nextEnabled = !!input.checked;
      const higherEl = el("unchainKoolkidHigherBarrier");
      const lowerEl = el("unchainKoolkidLowerBarrier");
      const previousHigher = higherEl ? String(higherEl.value || "") : "";
      const previousLower = lowerEl ? String(lowerEl.value || "") : "";
      state.koolkid_reversal_enabled = nextEnabled;
      transformKoolkidReversalFieldValues();
      applyKoolkidReversalToggle();
      const r = await saveSettings(false);
      if (!(r && r.ok)) {
        const fallbackPayload = state.lastPayload && (state.lastPayload.unchain || state.lastPayload);
        if (higherEl) higherEl.value = previousHigher;
        if (lowerEl) lowerEl.value = previousLower;
        state.koolkid_reversal_enabled = fallbackPayload && typeof fallbackPayload.koolkid_reversal_enabled !== "undefined"
          ? !!fallbackPayload.koolkid_reversal_enabled
          : previous;
        applyKoolkidReversalToggle();
      }
    });
  }

  function bindKoolkidHalfBarrierToggle() {
    const input = el("unchainKoolkidHalfBarrierToggle");
    if (!input || input.dataset.unchainBound === "1") return;
    input.dataset.unchainBound = "1";
    input.addEventListener("change", async () => {
      const previous = !!state.koolkid_half_barrier_enabled;
      const nextEnabled = !!input.checked;
      const higherEl = el("unchainKoolkidHigherBarrier");
      const lowerEl = el("unchainKoolkidLowerBarrier");
      const previousHigher = higherEl ? String(higherEl.value || "") : "";
      const previousLower = lowerEl ? String(lowerEl.value || "") : "";
      state.koolkid_half_barrier_enabled = nextEnabled;
      transformKoolkidHalfBarrierFieldValues(nextEnabled);
      applyKoolkidHalfBarrierToggle();
      const r = await saveSettings(false);
      if (!(r && r.ok)) {
        const fallbackPayload = state.lastPayload && (state.lastPayload.unchain || state.lastPayload);
        if (higherEl) higherEl.value = previousHigher;
        if (lowerEl) lowerEl.value = previousLower;
        state.koolkid_half_barrier_enabled = fallbackPayload && typeof fallbackPayload.koolkid_half_barrier_enabled !== "undefined"
          ? !!fallbackPayload.koolkid_half_barrier_enabled
          : previous;
        applyKoolkidHalfBarrierToggle();
      }
    });
  }

  function renderStatusChip(un, payload) {
    const chip = el("unchainStatusChip");
    if (!chip) return;
    if (!(payload && payload.ws_connected)) {
      chip.innerText = "NOT CONNECTED";
      chip.style.background = "#7f1d1d";
      chip.style.color = "#fff";
      return;
    }
    if (un && un.risk_block_reason) {
      chip.innerText = "RISK BLOCK";
      chip.style.background = "#7f1d1d";
      chip.style.color = "#fff";
      return;
    }
    const count = Number((un && un.active_count) || 0);
    if (count > 0) {
      chip.innerText = `ACTIVE ${count}`;
      chip.style.background = "#22c55e";
      chip.style.color = "#111827";
      return;
    }
    chip.innerText = "READY";
    chip.style.background = "#1e293b";
    chip.style.color = "#e2e8f0";
  }

  function renderRiskBlock(un) {
    const box = el("unchainRiskBlock");
    if (!box) return;
    const reason = un && un.risk_block_reason;
    if (reason) {
      box.style.display = "block";
      box.innerText = reason;
    } else {
      box.style.display = "none";
      box.innerText = "";
    }
  }


  function renderAutoBoth(un) {
    const autoBothBtn = el("unchainAutoBothBtn");
    const aiBtn = el("unchainAiAutoTradeBtn");
    const meta = el("unchainAutoBothMeta");
    if (!autoBothBtn && !aiBtn && !meta) return;
    const bothEnabled = !!(un && un.auto_both_enabled);
    const bothStatus = String((un && un.auto_status) || (bothEnabled ? "ARMED" : "OFF")).toUpperCase();
    const bothCooldown = Math.max(0, Number((un && un.auto_cooldown_remaining) || 0));
    const aiEnabled = !!(un && un.ai_auto_trade_enabled);
    const aiStatus = String((un && un.ai_auto_status) || (aiEnabled ? "ARMED" : "OFF")).toUpperCase();
    const aiCooldown = Math.max(0, Number((un && un.ai_auto_cooldown_remaining) || 0));
    const gate = (un && (un.ai_auto_gate || un.auto_gate)) || {};
    const metrics = (gate && gate.metrics) || {};
    const confidenceNow = Number(gate.market_confidence || metrics.confidence_score || metrics.market_confidence || 0);
    const confidenceNeed = Number((un && un.auto_start_threshold) || gate.threshold || 60);
    const expansion = Number(metrics.range_expansion_ratio);
    const compression = Number(metrics.compression_score);
    const burst = Number(metrics.momentum_burst_score);
    const breakout = Number(metrics.micro_breakout_score);
    const avgGap = Number(metrics.tick_arrival_speed != null ? metrics.tick_arrival_speed : metrics.average_tick_interval);
    const currentRange20 = Number(metrics.current_20_range != null ? metrics.current_20_range : metrics.recent_range);
    const avgRange20 = Number(metrics.avg_20_range);
    const regime = String(metrics.movement_regime || "WEAK").toUpperCase();
    const dynBarrier = metrics.dynamic_barrier_mag != null ? Number(metrics.dynamic_barrier_mag) : null;
    const dynDuration = metrics.dynamic_duration != null ? Number(metrics.dynamic_duration) : null;
    const dynDurationUnit = String(metrics.dynamic_duration_unit || "t").toUpperCase();
    const rejectReasons = Array.isArray(gate.reject_reasons) && gate.reject_reasons.length
      ? gate.reject_reasons
      : (Array.isArray(metrics.reject_reasons) ? metrics.reject_reasons : []);

    if (autoBothBtn) {
      autoBothBtn.innerText = bothEnabled ? `🤖 AUTO BOTH: ON • ${bothStatus}` : "🤖 AUTO BOTH: OFF";
      autoBothBtn.style.background = bothEnabled ? "#0891b2" : "#0284c7";
      autoBothBtn.style.color = "#fff";
    }

    if (aiBtn) {
      aiBtn.innerText = aiEnabled ? `🤖 AI AUTO TRADE: ON • ${aiStatus}` : "🤖 AI AUTO TRADE: OFF";
      aiBtn.style.background = aiEnabled ? "#06b6d4" : "#0ea5e9";
      aiBtn.style.color = "#fff";
    }

    if (meta) {
      const bothText = !bothEnabled
        ? "AUTO BOTH is OFF."
        : (bothStatus === "RUNNING"
            ? "AUTO BOTH is running and waiting for active contracts to settle."
            : (bothStatus.includes("PAUSED")
                ? "AUTO BOTH is ON but paused while AI AUTO TRADE is enabled."
            : (bothStatus === "COOLDOWN"
                ? `AUTO BOTH cooldown: ${bothCooldown.toFixed(1)}s before next pair.`
                : "AUTO BOTH armed: sends Higher + Lower with your saved barriers/duration.")));

      let aiText = "AI AUTO TRADE is OFF.";
      if (aiEnabled) {
        if (aiStatus === "RUNNING") {
          aiText = "AI AUTO TRADE is running. It waits for both contracts to fully settle before evaluating the next cycle.";
        } else if (aiStatus === "COOLDOWN") {
          aiText = `AI AUTO TRADE cooldown: ${aiCooldown.toFixed(1)}s before next evaluation.`;
        } else if (aiStatus.startsWith("WAITING")) {
          const gapText = Number.isFinite(avgGap) ? `${avgGap.toFixed(3)}s` : "—";
          const rangeText = Number.isFinite(currentRange20) && Number.isFinite(avgRange20)
            ? `${currentRange20.toFixed(5)} / ${avgRange20.toFixed(5)}`
            : "—";
          const expansionText = Number.isFinite(expansion) ? `${expansion.toFixed(2)}x` : "—";
          const compText = Number.isFinite(compression) ? compression.toFixed(1) : "—";
          const burstText = Number.isFinite(burst) ? burst.toFixed(1) : "—";
          const breakoutText = Number.isFinite(breakout) ? breakout.toFixed(1) : "—";
          const reasonText = rejectReasons.length ? ` • ${rejectReasons[0]}` : "";
          aiText = `AI AUTO TRADE waiting: conf ${confidenceNow.toFixed(0)}% / ${confidenceNeed.toFixed(0)}% • 20R ${rangeText} (${expansionText}) • comp ${compText} • burst ${burstText} • breakout ${breakoutText} • tick ${gapText}${reasonText}`;
        } else {
          const dynText = (dynBarrier != null && dynDuration != null)
            ? ` • barrier ±${dynBarrier.toFixed(2)} • duration ${dynDuration}${dynDurationUnit}`
            : "";
          aiText = `AI AUTO TRADE armed: confidence ${confidenceNow.toFixed(0)}% / ${confidenceNeed.toFixed(0)}% • regime ${regime}${dynText}`;
        }
      }
      meta.innerText = `${bothText} ${aiText}`;
    }
  }

  function fmtUsd(v) {
    const n = Number(v);
    return Number.isFinite(n) ? `$${n.toFixed(2)}` : "—";
  }

  function renderBothAnalyzer(un) {
    const data = (un && un.both_analyzer) || {};
    const rec = data && typeof data.recommended === "object" ? data.recommended : null;
    const bestHigher = data && typeof data.best_higher_setup === "object" ? data.best_higher_setup : null;
    const bestLower = data && typeof data.best_lower_setup === "object" ? data.best_lower_setup : null;
    const bestBoth = data && typeof data.best_both_setup === "object"
      ? data.best_both_setup
      : ((rec && String(rec.recommended_side || rec.side || "").toUpperCase() === "BOTH") ? rec : null);
    const status = String(data.status || "WAIT").toUpperCase();
    const signal = String(data.signal || "WAIT").toUpperCase();
    const recommendedSide = String(data.recommended_side || (rec && rec.recommended_side) || "").toUpperCase();
    const marketOutlook = String(data.market_outlook || (bestBoth && bestBoth.market_outlook) || "WAITING").toUpperCase();
    const reason = String(data.reason || "Tap Analyze to run Barrier Analysis Tool.");
    const symbol = String(data.symbol || (state.lastPayload && state.lastPayload.symbol) || "—");
    const tested = Number(data.tested_setups || 0);
    const ticksCollected = Number(data.ticks_collected != null ? data.ticks_collected : (data.sample_size || 0));
    const minTicks = Number(data.required_min_ticks || 50);
    const maxTicks = Number(data.max_ticks_considered || 200);
    const confidence = Number(
      data.confidence != null
        ? data.confidence
        : (bestBoth && bestBoth.confidence != null ? bestBoth.confidence : data.final_score)
    );
    const expectedProfit = Number(
      data.expected_profit != null
        ? data.expected_profit
        : (bestBoth && bestBoth.ev_score != null ? bestBoth.ev_score : NaN)
    );
    const higherProb = Number(data.higher_probability);
    const lowerProb = Number(data.lower_probability);
    const middleProb = Number(data.middle_probability);
    const bothMinProfit = Number(
      data.both_min_win_profit != null
        ? data.both_min_win_profit
        : (bestBoth && bestBoth.balanced_profit != null ? bestBoth.balanced_profit : NaN)
    );
    const bothProfitTarget = Number(
      data.both_profit_target != null
        ? data.both_profit_target
        : (bestBoth && bestBoth.both_profit_target != null ? bestBoth.both_profit_target : NaN)
    );
    const payoutDiff = Number(
      data.payout_difference != null
        ? data.payout_difference
        : (bestBoth && bestBoth.payout_difference != null ? bestBoth.payout_difference : NaN)
    );
    const higherExpected = Number(
      data.higher_expected_profit != null
        ? data.higher_expected_profit
        : (bestHigher && bestHigher.expected_profit != null ? bestHigher.expected_profit : NaN)
    );
    const lowerExpected = Number(
      data.lower_expected_profit != null
        ? data.lower_expected_profit
        : (bestLower && bestLower.expected_profit != null ? bestLower.expected_profit : NaN)
    );

    const fmtSideSetup = (setup, side) => {
      if (!setup || typeof setup !== "object") return `${side}: —`;
      const dur = Number(setup.duration);
      const unit = String(setup.duration_unit || "t").toUpperCase();
      const barrier = side === "HIGHER"
        ? String(setup.higher_barrier || "—")
        : String(setup.lower_barrier || "—");
      const net = Number(setup.net);
      const exp = Number(setup.expected_profit);
      const prob = Number(setup.probability);
      const netText = Number.isFinite(net) ? `${net >= 0 ? "+" : "-"}$${Math.abs(net).toFixed(2)}` : "—";
      const expText = Number.isFinite(exp) ? `${exp >= 0 ? "+" : "-"}$${Math.abs(exp).toFixed(2)}` : "—";
      const probText = Number.isFinite(prob) ? `${(prob * 100).toFixed(1)}%` : "—";
      return `${Number.isFinite(dur) ? `${dur}${unit}` : "—"} ${barrier} • Net ${netText} • E ${expText} • P ${probText}`;
    };

    const chip = el("unchainBothSignalChip");
    if (chip) {
      chip.innerText = signal;
      if (status === "READY" && recommendedSide === "BOTH") {
        chip.style.background = "#22c55e";
        chip.style.color = "#052e16";
      } else if (status === "READY") {
        chip.style.background = "#38bdf8";
        chip.style.color = "#082f49";
      } else if (signal === "MIDDLE ZONE" || marketOutlook === "MIDDLE ZONE") {
        chip.style.background = "#f59e0b";
        chip.style.color = "#451a03";
      } else {
        chip.style.background = "#1e293b";
        chip.style.color = "#e2e8f0";
      }
    }

    const body = el("unchainBothBody");
    const toggleBtn = el("unchainBothToggleBtn");
    if (body) body.style.display = state.bothAnalyzerEnabled ? "" : "none";
    if (toggleBtn) {
      toggleBtn.innerText = state.bothAnalyzerEnabled ? "ON" : "OFF";
      toggleBtn.style.background = state.bothAnalyzerEnabled ? "#22c55e" : "#475569";
      toggleBtn.style.color = state.bothAnalyzerEnabled ? "#052e16" : "#e2e8f0";
    }

    const summary = el("unchainBothSummary");
    if (summary) {
      const bothText = bestBoth
        ? `BOTH ${bestBoth.duration || "—"}${String(bestBoth.duration_unit || "t").toUpperCase()} ${bestBoth.higher_barrier || "—"} / ${bestBoth.lower_barrier || "—"}`
        : "BOTH: —";
      const probText = [
        `H ${Number.isFinite(higherProb) ? `${higherProb.toFixed(1)}%` : "—"}`,
        `L ${Number.isFinite(lowerProb) ? `${lowerProb.toFixed(1)}%` : "—"}`,
        `M ${Number.isFinite(middleProb) ? `${middleProb.toFixed(1)}%` : "—"}`
      ].join(" • ");
      summary.innerText = `${reason} • Symbol ${symbol} • Outlook ${marketOutlook} • ${probText} • Ticks ${ticksCollected}/${minTicks} required (max ${maxTicks}) • ${fmtSideSetup(bestHigher, "HIGHER")} • ${fmtSideSetup(bestLower, "LOWER")} • ${bothText} • Tested ${tested} setup${tested === 1 ? "" : "s"}.`;
      summary.style.color = status === "READY"
        ? (recommendedSide === "BOTH" ? "#86efac" : "#7dd3fc")
        : ((signal === "MIDDLE ZONE" || marketOutlook === "MIDDLE ZONE") ? "#fcd34d" : "#94a3b8");
    }

    setText("unchainBothScore", Number.isFinite(confidence) ? `${confidence.toFixed(1)}%` : "0.0%");
    setText("unchainBothOutlook", marketOutlook || "WAITING");
    setText(
      "unchainBothProbabilities",
      `H ${Number.isFinite(higherProb) ? `${higherProb.toFixed(1)}%` : "—"} • L ${Number.isFinite(lowerProb) ? `${lowerProb.toFixed(1)}%` : "—"} • M ${Number.isFinite(middleProb) ? `${middleProb.toFixed(1)}%` : "—"}`
    );
    const recDuration = Number(data.recommended_duration);
    const recDurationUnit = String((rec && rec.duration_unit) || (bestBoth && bestBoth.duration_unit) || "t").toUpperCase();
    setText("unchainBothDuration", Number.isFinite(recDuration) && recDuration > 0
      ? `${recDuration}${recDurationUnit}`
      : (rec ? `${rec.duration || "—"}${String(rec.duration_unit || "").toUpperCase()}` : (bestBoth ? `${bestBoth.duration || "—"}${String(bestBoth.duration_unit || "").toUpperCase()}` : "—")));
    setText("unchainBothBarriers", bestBoth ? `${bestBoth.higher_barrier || "—"} / ${bestBoth.lower_barrier || "—"}` : "—");
    setText("unchainBothMiddleRisk", bestBoth ? String(bestBoth.middle_zone_risk || data.middle_zone_risk || "—") : String(data.middle_zone_risk || "—"));
    setText("unchainBothPayoutHigher", fmtSideSetup(bestHigher, "HIGHER"));
    setText("unchainBothPayoutLower", fmtSideSetup(bestLower, "LOWER"));
    setText("unchainBothTotalCost", Number.isFinite(bothMinProfit) ? fmtUsd(bothMinProfit) : "—");
    setText("unchainBothProfitTarget", Number.isFinite(bothProfitTarget) ? fmtUsd(bothProfitTarget) : "—");
    setText("unchainBothPayoutDiff", Number.isFinite(payoutDiff) ? fmtUsd(payoutDiff) : "—");
    setText("unchainBothHigherExp", Number.isFinite(higherExpected) ? fmtUsd(higherExpected) : "—");
    setText("unchainBothLowerExp", Number.isFinite(lowerExpected) ? fmtUsd(lowerExpected) : "—");
    const ev = Number(bestBoth && bestBoth.ev_score != null ? bestBoth.ev_score : (rec && rec.ev_score != null ? rec.ev_score : expectedProfit));
    const pMid = Number(bestBoth && bestBoth.p_mid != null ? bestBoth.p_mid : (rec && rec.p_mid));
    const evText = Number.isFinite(ev) ? `EV ${ev >= 0 ? "+" : ""}${ev.toFixed(2)}` : "EV —";
    const pMidText = Number.isFinite(pMid) ? `P_mid ${(pMid * 100).toFixed(1)}%` : "P_mid —";
    setText("unchainBothTopSetup", `${evText} • ${pMidText}`);

    const applyBtn = el("unchainBothApplyBtn");
    if (applyBtn) {
      const canApply = !!rec;
      applyBtn.disabled = !canApply;
      applyBtn.style.opacity = canApply ? "1" : "0.55";
      applyBtn.style.cursor = canApply ? "pointer" : "not-allowed";
    }
  }

  async function analyzeBothTool() {
    if (!state.bothAnalyzerEnabled) {
      toast("Barrier Analysis Tool is OFF", "info");
      return;
    }
    try {
      await saveSettings(false);
      const r = await postJSON("/unchain_both_analyze", {});
      if (r.ok && r.data) {
        if (r.data.payload) renderPayload(r.data.payload, { forceForm: false });
        const okNow = !!r.data.ok_to_trade;
        const reason = String(r.data.message || "");
        toast(reason || (okNow ? "Barrier setup ready" : "Barrier setup says wait"), okNow ? "success" : "info");
        return;
      }
      toast((r.data && (r.data.message || r.data.error)) || "Barrier analysis failed", "error");
      if (r.data && r.data.payload) renderPayload(r.data.payload);
    } catch (e) {
      toast("Barrier analysis failed", "error");
    }
  }

  async function applyBothRecommendation() {
    if (!state.bothAnalyzerEnabled) {
      toast("Barrier Analysis Tool is OFF", "info");
      return;
    }
    const un = state.lastPayload && (state.lastPayload.unchain || state.lastPayload);
    const analyzer = (un && un.both_analyzer) || {};
    const rec = analyzer && typeof analyzer.recommended === "object" ? analyzer.recommended : null;
    if (!rec) {
      toast("No analyzed barrier setup to apply", "info");
      return;
    }

    const durationUnit = String(rec.duration_unit || "t").toLowerCase();
    const duration = parseInt(rec.duration, 10);
    const higherBarrier = String(rec.higher_barrier || "").trim();
    const lowerBarrier = String(rec.lower_barrier || "").trim();
    const displayHigherBarrier = higherBarrier
      ? getDisplayedBarrierText(higherBarrier, 0.12, !!state.half_barrier_enabled)
      : "";
    const displayLowerBarrier = lowerBarrier
      ? getDisplayedBarrierText(lowerBarrier, -0.12, !!state.half_barrier_enabled)
      : "";

    const unitEl = el("unchainDurationUnit");
    if (unitEl && durationUnit) {
      unitEl.value = durationUnit;
      markDirty("unchainDurationUnit");
      applyDurationPresets(true);
    }
    const durationEl = el("unchainDuration");
    if (durationEl && Number.isFinite(duration)) {
      const asText = String(duration);
      const hasOption = Array.from(durationEl.options || []).some((opt) => String(opt.value) === asText);
      if (!hasOption) {
        const opt = document.createElement("option");
        opt.value = asText;
        opt.text = asText;
        durationEl.appendChild(opt);
      }
      durationEl.value = asText;
      markDirty("unchainDuration");
    }
    const higherEl = el("unchainHigherBarrier");
    if (higherEl && displayHigherBarrier) {
      higherEl.value = displayHigherBarrier;
      markDirty("unchainHigherBarrier");
    }
    const lowerEl = el("unchainLowerBarrier");
    if (lowerEl && displayLowerBarrier) {
      lowerEl.value = displayLowerBarrier;
      markDirty("unchainLowerBarrier");
    }

    renderBarrierMarketChart(un || {}, state.lastPayload || {});
    await saveSettings(true);
    toast("Applied barrier setup", "success");
  }

  function toggleBothAnalyzer() {
    state.bothAnalyzerEnabled = !state.bothAnalyzerEnabled;
    const un = state.lastPayload && (state.lastPayload.unchain || state.lastPayload);
    renderBothAnalyzer(un || {});
  }

  function renderKoolkidHl(un) {
    const data = (un && un.koolkid_hl) || {};
    const bothData = (un && un.koolkid_both) || {};
    const sim = data && typeof data.simulation === "object" ? data.simulation : null;
    const bothSim = bothData && typeof bothData.simulation === "object" ? bothData.simulation : null;
    const isEnabled = !!data.enabled;
    const isBothEnabled = !!bothData.enabled;
    const anyEnabled = isEnabled || isBothEnabled;
    state.koolkid_reversal_enabled = !!((un && un.koolkid_reversal_enabled) || data.reversal_enabled);
    state.koolkid_half_barrier_enabled = !!((un && un.koolkid_half_barrier_enabled) || data.half_barrier_enabled || bothData.half_barrier_enabled);
    applyKoolkidReversalToggle();
    applyKoolkidHalfBarrierToggle();

    const panelBtn = el("unchainKoolkidBtn");
    if (panelBtn) {
      panelBtn.innerText = `KOOLKID: ${anyEnabled ? "ON" : "OFF"}`;
      panelBtn.style.background = anyEnabled ? "#1d4ed8" : "#2563eb";
      panelBtn.style.color = "#eff6ff";
    }

    const body = el("unchainKoolkidBody");
    if (body) body.style.display = state.koolkidPanelOpen ? "flex" : "none";

    const hlBtn = el("unchainKoolkidHlBtn");
    if (hlBtn) {
      hlBtn.innerText = `📈 HIGHER/LOWER: ${isEnabled ? "ON" : "OFF"}`;
      hlBtn.style.background = isEnabled ? "#22c55e" : "#1d4ed8";
      hlBtn.style.color = isEnabled ? "#052e16" : "#eff6ff";
    }

    const bothBtn = el("unchainKoolkidBothBtn");
    if (bothBtn) {
      bothBtn.innerText = `⚖️ BOTH: ${isBothEnabled ? "ON" : "OFF"}`;
      bothBtn.style.background = isBothEnabled ? "#f59e0b" : "#475569";
      bothBtn.style.color = isBothEnabled ? "#111827" : "#e2e8f0";
    }

    const status = el("unchainKoolkidStatus");
    if (!status) return;
    if (bothSim && bothSim.active) {
      const sides = Array.isArray(bothSim.sides) ? bothSim.sides : [];
      const hi = sides.find((item) => String((item && item.side) || "").toUpperCase() === "HIGHER") || null;
      const lo = sides.find((item) => String((item && item.side) || "").toUpperCase() === "LOWER") || null;
      const hiPct = Number(hi && hi.profit_pct);
      const loPct = Number(lo && lo.profit_pct);
      const remaining = Number(bothSim.countdown_remaining || 0);
      const checkRemaining = Number(bothSim.check_remaining || 0);
      const leader = String(bothSim.leading_side || "—").toUpperCase();
      const countdownUnit = String(bothSim.countdown_unit || "s").toLowerCase();
      const simUnit = String(bothSim.duration_unit || bothData.simulation_duration_unit || "s").toLowerCase();
      const liveUnit = String(bothSim.live_duration_unit || bothData.live_duration_unit || "t").toLowerCase();
      status.innerText =
        `Paper BOTH sim • HIGHER ${Number.isFinite(hiPct) ? `${hiPct >= 0 ? "+" : ""}${hiPct.toFixed(0)}%` : "—"} • ` +
        `LOWER ${Number.isFinite(loPct) ? `${loPct >= 0 ? "+" : ""}${loPct.toFixed(0)}%` : "—"} • ` +
        `${formatKoolkidDurationText(remaining, countdownUnit)} left • ${checkRemaining > 0 ? `decision in ${formatKoolkidDurationText(checkRemaining, countdownUnit)}` : "checking now"} • ` +
        `sim ${formatKoolkidDurationText(bothSim.duration || bothData.simulation_duration || 0, simUnit)} • ` +
        `leader ${leader} • if flow is strong enough, BOTH uses your saved Higher/Lower stakes and KOOLKID barriers.`;
      status.style.color = "#fcd34d";
      return;
    }
    if (sim && sim.active) {
      const estValue = Number(sim.estimated_value);
      const estPnl = Number(sim.estimated_pnl);
      const remaining = Number(sim.countdown_remaining || 0);
      const checkRemaining = Number(sim.check_remaining || 0);
      const lossTriggerPct = Number(sim.loss_trigger_pct || data.loss_trigger_pct || 50);
      const valueText = Number.isFinite(estValue) ? `$${estValue.toFixed(2)}` : "—";
      const pnlText = Number.isFinite(estPnl) ? `${estPnl >= 0 ? "+" : "-"}$${Math.abs(estPnl).toFixed(2)}` : "—";
      const countdownUnit = String(sim.countdown_unit || "s").toLowerCase();
      const liveUnit = String(sim.live_duration_unit || data.live_duration_unit || "t").toLowerCase();
      status.innerText =
        `Paper ${String(sim.side || "—").toUpperCase()} sim live ${valueText} (${pnlText}) • ` +
        `${formatKoolkidDurationText(remaining, countdownUnit)} left • ${checkRemaining > 0 ? `decision in ${formatKoolkidDurationText(checkRemaining, countdownUnit)}` : "checking now"} • ` +
        `needs ${Number.isFinite(lossTriggerPct) ? lossTriggerPct.toFixed(0) : "50"}% loss • ` +
        `live ${String(sim.opposite_side || "—").toUpperCase()} ${formatKoolkidDurationText(Number(sim.live_duration || 5), liveUnit)} will use ${sim.live_barrier || "—"}.`;
      status.style.color = "#93c5fd";
      return;
    }
    if (isBothEnabled) {
      status.innerText = String(bothData.last_reason || "KOOLKID Both is waiting for a dual paper trade setup.");
      status.style.color = "#fcd34d";
      return;
    }
    status.innerText = String(data.last_reason || "KOOLKID Higher/Lower is waiting for a weak-side paper trade setup.");
    status.style.color = isEnabled ? "#93c5fd" : "#cbd5e1";
  }

  function toggleKoolkidPanel() {
    state.koolkidPanelOpen = !state.koolkidPanelOpen;
    const un = state.lastPayload && (state.lastPayload.unchain || state.lastPayload);
    renderKoolkidHl(un || {});
  }

  function attachKoolkidModal(root) {
    return;
  }

  function bindKoolkidModal() {
    const modal = el("unchainKoolkidBody");
    if (!modal || modal.dataset.unchainModalBound === "1") return;
    modal.dataset.unchainModalBound = "1";
    const closePanel = () => {
      state.koolkidPanelOpen = false;
      const un = state.lastPayload && (state.lastPayload.unchain || state.lastPayload);
      renderKoolkidHl(un || {});
    };
    modal.addEventListener("click", (evt) => {
      if (evt.target !== modal) return;
      closePanel();
    });
    document.addEventListener("keydown", (evt) => {
      if (evt.key !== "Escape" || !state.koolkidPanelOpen) return;
      closePanel();
    });
  }

  async function toggleKoolkidHl() {
    const saved = await saveSettings(false);
    if (!saved || !saved.ok) return;
    const un = state.lastPayload && (state.lastPayload.unchain || state.lastPayload);
    const current = !!(un && un.koolkid_hl && un.koolkid_hl.enabled);
    const r = await postJSON("/toggle_unchain_koolkid_hl", { enabled: !current });
    if (r.ok && r.data) {
      if (r.data.payload) renderPayload(r.data.payload, { forceForm: true });
      toast(r.data.message || (!current ? "KOOLKID HIGHER/LOWER ON" : "KOOLKID HIGHER/LOWER OFF"), !current ? "success" : "warn");
    } else {
      toast((r.data && (r.data.message || r.data.error)) || "Failed to toggle KOOLKID Higher/Lower", "error");
      if (r.data && r.data.payload) renderPayload(r.data.payload);
    }
  }

  async function toggleKoolkidBoth() {
    const saved = await saveSettings(false);
    if (!saved || !saved.ok) return;
    const un = state.lastPayload && (state.lastPayload.unchain || state.lastPayload);
    const current = !!(un && un.koolkid_both && un.koolkid_both.enabled);
    const r = await postJSON("/toggle_unchain_koolkid_both", { enabled: !current });
    if (r.ok && r.data) {
      if (r.data.payload) renderPayload(r.data.payload, { forceForm: true });
      toast(r.data.message || (!current ? "KOOLKID BOTH ON" : "KOOLKID BOTH OFF"), !current ? "success" : "warn");
    } else {
      toast((r.data && (r.data.message || r.data.error)) || "Failed to toggle KOOLKID Both", "error");
      if (r.data && r.data.payload) renderPayload(r.data.payload);
    }
  }

  function formatTradeCountdown(item) {
    if (!item) return "—";
    const unit = String(item.countdown_unit || "").toLowerCase();
    const remaining = Number(item.countdown_remaining);
    const duration = Number(item.duration);
    if (!Number.isFinite(remaining) || remaining < 0 || !unit) return "—";
    const safeRemaining = Math.max(0, Math.floor(remaining));
    if (unit === "t") {
      const total = Number.isFinite(duration) ? Math.max(1, Math.floor(duration)) : null;
      return `${safeRemaining}${total ? ` / ${total}` : ""} ticks`;
    }
    if (unit === "s") return `${safeRemaining}s`;
    if (unit === "m") return `${safeRemaining}m`;
    if (unit === "h") return `${safeRemaining}h`;
    return String(safeRemaining);
  }

  function countdownSortValue(item) {
    if (!item) return Number.POSITIVE_INFINITY;
    const unit = String(item.countdown_unit || "").toLowerCase();
    const remaining = Number(item.countdown_remaining);
    const remainingSeconds = Number(item.countdown_seconds);
    if (!Number.isFinite(remaining) || remaining < 0) return Number.POSITIVE_INFINITY;
    if (unit === "s") return Number.isFinite(remainingSeconds) ? remainingSeconds : remaining;
    if (unit === "m") return Number.isFinite(remainingSeconds) ? remainingSeconds : (remaining * 60);
    if (unit === "h") return Number.isFinite(remainingSeconds) ? remainingSeconds : (remaining * 3600);
    return remaining;
  }

  function countdownToastTone(item) {
    const n = countdownSortValue(item);
    if (!Number.isFinite(n)) return "info";
    if (n <= 1) return "warn";
    return "info";
  }

  function syncTradeCountdownToast(items) {
    if (!isActive()) {
      removeTradeCountdownToast();
      return;
    }
    const list = Array.isArray(items) ? items.filter(Boolean) : [];
    if (!list.length) {
      removeTradeCountdownToast();
      return;
    }
    const ranked = list.slice().sort((a, b) => countdownSortValue(a) - countdownSortValue(b));
    const focus = ranked[0];
    const countdownLabel = formatTradeCountdown(focus);
    if (!focus || countdownLabel === "—") {
      removeTradeCountdownToast();
      return;
    }
    const type = String(focus.type || focus.side || "TRADE").toUpperCase();
    const contractId = focus.contract_id != null ? `#${focus.contract_id}` : "#—";
    const extra = ranked.length > 1 ? ` • +${ranked.length - 1} more` : "";
    const message = `⏳ ${type} ${contractId} • ${countdownLabel} left${extra}`;
    const toastEl = ensureTradeCountdownToast();
    if (!toastEl) return;
    const tone = countdownToastTone(focus);
    toastEl.className = `toast ${tone} show`;
    if (toastEl.innerText !== message) toastEl.innerText = message;
  }

  function renderActiveTrades(un) {
    const rawItems = Array.isArray(un && un.active_contracts) ? un.active_contracts : [];
    const items = rawItems.filter((item) => {
      if (!item || typeof item !== "object") return false;
      if (item.is_sold) return false;
      const status = String(item.status || "").toLowerCase();
      const contractStatus = String(item.contract_status || "").toLowerCase();
      return ![status, contractStatus].some((v) => ["sold", "won", "lost", "settled", "closed", "expired"].includes(v));
    });
    syncTradeCountdownToast(items);
    const wrap = el("unchainActiveTrades");
    if (!wrap) return;
    if (!items.length) {
      wrap.innerHTML = '<div class="unchain-empty">No active UNCHAIN trades.</div>';
      return;
    }
    wrap.innerHTML = items.map((item) => {
      const type = String(item.type || item.side || "TRADE").toUpperCase();
      const profit = item.open_profit == null ? "—" : `$${Number(item.open_profit).toFixed(2)}`;
      const profitColor = item.open_profit == null ? "#f8fafc" : (Number(item.open_profit) >= 0 ? "#22c55e" : "#ef4444");
      const durationLabel = `${item.duration || "—"}${String(item.duration_unit || "").toUpperCase()}`;
      const countdown = formatTradeCountdown(item);
      return `<div class="unchain-active-item"><div class="top"><div style="font-weight:900;color:${type === "HIGHER" ? "#22c55e" : "#ef4444"};">${type}</div><div class="unchain-chip">#${item.contract_id || "—"}</div></div><div style="margin-top:8px;color:#cbd5e1;display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;"><div><span class="unchain-label">Stake</span><div>$${Number(item.stake || 0).toFixed(2)}</div></div><div><span class="unchain-label">Barrier</span><div>${item.barrier || "—"}</div></div><div><span class="unchain-label">Duration</span><div>${durationLabel}</div></div><div><span class="unchain-label">Countdown</span><div>${countdown}</div></div><div><span class="unchain-label">Symbol</span><div>${item.symbol || "—"}</div></div><div><span class="unchain-label">Open P/L</span><div style="color:${profitColor};font-weight:800;">${profit}</div></div></div></div>`;
    }).join("");
  }

  function fmtScannerPct(v) {
    const n = Number(v);
    return Number.isFinite(n) ? `${n.toFixed(1)}%` : "—";
  }

  function fmtScannerNum(v) {
    const n = Number(v);
    return Number.isFinite(n) ? n.toFixed(2) : "—";
  }

  function fmtScannerSigned(v) {
    const n = Number(v);
    return Number.isFinite(n) ? `${n >= 0 ? "+" : "-"}${Math.abs(n).toFixed(2)}` : "—";
  }

  function renderScanner(scanner) {
    state.scanner = scanner || state.scanner || {};
    const payload = state.scanner || {};
    const statusEl = el("unchainScannerStatus");
    const headlineEl = el("unchainScannerHeadline");
    const tickCountEl = el("unchainScannerTickCount");
    const footerEl = el("unchainScannerFooter");
    const bodyEl = el("unchainScannerBody");
    const windowsEl = el("unchainScannerWindows");
    const listEl = el("unchainScannerList");

    const currentWindow = Number(payload.window_ticks || 20);
    const windowOptions = Array.isArray(payload.window_options) && payload.window_options.length
      ? payload.window_options
      : [20];

    if (windowsEl) {
      windowsEl.innerHTML = windowOptions.map((ticks) => {
        const active = Number(ticks) === currentWindow;
        return `<button type="button" class="unchain-scanner-window-btn${active ? " is-active" : ""}" data-action="unchain-scanner-window" data-window="${Number(ticks) || 15}">${Number(ticks) || 15}</button>`;
      }).join("");
    }
    if (headlineEl) {
      headlineEl.innerText = payload.headline || `Top 4 pairs by longest movement (${currentWindow}-tick window)`;
    }
    if (tickCountEl) {
      const totalTicks = Number(payload.total_ticks || 0);
      tickCountEl.innerText = `${totalTicks.toLocaleString()} ticks`;
    }
    if (footerEl) {
      footerEl.innerHTML = payload.footer_note
        ? `<strong>Live mode:</strong> ${String(payload.footer_note).replace(/^Live mode:\s*/i, "")}`
        : "<strong>Live mode:</strong> Scans up to 10 markets over 20 ticks, shows the best 4 pairs with the longest up & down movement from spot price, and sets barriers at 25% of average movement for balanced win. Updates every 2 seconds.";
    }

    const running = !!payload.running;
    if (statusEl) {
      statusEl.innerText = running ? "ON" : "OFF";
      statusEl.classList.toggle("is-on", running);
      statusEl.classList.toggle("is-off", !running);
    }
    if (tickCountEl) tickCountEl.style.display = running ? "" : "none";
    if (bodyEl) bodyEl.style.display = running ? "grid" : "none";

    if (!listEl) return;
    const recs = Array.isArray(payload.recommendations) ? payload.recommendations.slice(0, 4) : [];
    const progress = Array.isArray(payload.progress) ? payload.progress.slice(0, 4) : [];
    const minimumHistory = Number(payload.minimum_history || payload.sample_size || 20);

    if (!running) {
      listEl.innerHTML = '<div class="unchain-empty">Scanner is off. Tap ON to start.</div>';
      return;
    }

    if (!progress.length && !recs.length) {
      listEl.innerHTML = '<div class="unchain-empty">Collecting live ticks across up to 10 markets…</div>';
      return;
    }

    const recMap = new Map(recs.map((item) => [String(item.symbol || ""), item]));
    const rowPool = [];
    const seen = new Set();
    recs.forEach((item) => {
      const symbol = String(item && item.symbol || "");
      if (!symbol || seen.has(symbol)) return;
      seen.add(symbol);
      rowPool.push(item);
    });
    progress.forEach((item) => {
      const symbol = String(item && item.symbol || "");
      if (!symbol || seen.has(symbol) || rowPool.length >= 4) return;
      seen.add(symbol);
      rowPool.push(recMap.get(symbol) || item);
    });
    const rows = rowPool.slice(0, 4).map((item, idx) => Object.assign({ rank: idx + 1 }, item));

    listEl.innerHTML = rows.map((row, idx) => {
      const rank = Number(row.rank || idx + 1);
      const displayName = row.display_name || row.symbol || "—";
      const active = !!row.is_active;
      const sampleCount = Number(row.sample_count || 0);
      const ticksReady = Number(row.ticks_ready || 0);
      const rawPct = Math.round((ticksReady / Math.max(1, minimumHistory)) * 100);
      const hasAnalysis = Number.isFinite(Number(row.avg_move_up)) && Number.isFinite(Number(row.avg_move_down));
      if (!hasAnalysis) {
        const pct = Math.max(6, Math.min(ticksReady >= minimumHistory ? 99 : 100, rawPct));
        const activeBadge = active ? '<span class="unchain-scanner-badge">ACTIVE</span>' : "";
        return `<div class="unchain-scanner-market${rank === 1 ? " is-rank-1" : ""}${active ? " is-active" : ""}">
          <div class="unchain-scanner-market-head">
            <div class="unchain-scanner-market-left">
              <div class="unchain-scanner-rank-row">
                <span class="unchain-scanner-rank">#${rank}</span>
                <span class="unchain-scanner-market-name">${displayName}</span>
                ${activeBadge}
              </div>
              <div class="unchain-scanner-mini-meta"><span>↗ ${sampleCount}t</span><span class="muted">${ticksReady}/${minimumHistory}</span></div>
            </div>
            <div class="unchain-scanner-score-wrap">
              <div>
                <div class="unchain-scanner-score">${pct}</div>
                <div class="unchain-scanner-score-label">LOAD</div>
              </div>
            </div>
          </div>
          <div class="unchain-scanner-bar-wrap">
            <div class="unchain-scanner-bar-label">Collecting live ticks across 20 ticks</div>
            <div class="unchain-scanner-bar"><span style="width:${pct}%;"></span></div>
          </div>
        </div>`;
      }
      const pct = Math.max(6, Math.min(100, rawPct));
      const score = Math.max(1, Math.min(99, Number(row.score || pct)));
      const higherWin = Number(row.higher_win);
      const lowerWin = Number(row.lower_win);
      const avgUp = Number(row.avg_move_up);
      const avgDown = Number(row.avg_move_down);
      const difference = Number(row.difference);
      const drift = Number(row.recent_drift != null ? row.recent_drift : row.drift);
      const trendIcon = drift >= 0 ? "↗" : "↘";
      const bestSide = String(row.best_side || (higherWin >= lowerWin ? "HIGHER" : "LOWER")).toUpperCase();
      const bestPillClass = bestSide === "HIGHER" ? "is-best-higher" : (bestSide === "LOWER" ? "is-best-lower" : "is-best");
      const differenceClass = difference >= 0 ? "is-green" : "is-red";
      const applyBtn = `<button class="unchain-scanner-apply" data-action="unchain-scanner-apply" data-symbol="${row.symbol || ""}">Apply</button>`;
      return `<div class="unchain-scanner-market${rank === 1 ? " is-rank-1" : ""}${active ? " is-active" : ""}">
        <div class="unchain-scanner-market-head">
          <div class="unchain-scanner-market-left">
            <div class="unchain-scanner-rank-row">
              <span class="unchain-scanner-rank">#${rank}</span>
              <span class="unchain-scanner-market-name">${displayName}</span>
              ${active ? '<span class="unchain-scanner-badge">ACTIVE</span>' : ""}
            </div>
            <div class="unchain-scanner-mini-meta">
              <span>${trendIcon} ${sampleCount}t</span>
              <span class="muted">${ticksReady} ticks tracked</span>
            </div>
          </div>
          <div class="unchain-scanner-score-wrap">
            <div>
              <div class="unchain-scanner-score">${score}</div>
              <div class="unchain-scanner-score-label">Score</div>
            </div>
          </div>
        </div>
        <div class="unchain-scanner-stats">
          <div class="unchain-scanner-stat"><span class="label">Higher win:</span><span class="value ${higherWin >= lowerWin ? "is-green" : "is-red"}">${fmtScannerPct(higherWin)}</span></div>
          <div class="unchain-scanner-stat"><span class="label">Lower win:</span><span class="value ${lowerWin > higherWin ? "is-green" : "is-red"}">${fmtScannerPct(lowerWin)}</span></div>
          <div class="unchain-scanner-stat"><span class="label">Avg move up:</span><span class="value is-green">${fmtScannerNum(avgUp)}</span></div>
          <div class="unchain-scanner-stat"><span class="label">Avg move dn:</span><span class="value is-red">${fmtScannerNum(avgDown)}</span></div>
        </div>
        <div class="unchain-scanner-diff">Difference (Up - Down): <strong class="${differenceClass}">${fmtScannerSigned(difference)}</strong></div>
        <div class="unchain-scanner-chip-row">
          <span class="unchain-scanner-pill is-green">↗ H: ${row.barrier_high || fmtScannerSigned(row.barrier_value)}</span>
          <span class="unchain-scanner-pill is-red">↘ L: ${row.barrier_low || fmtScannerSigned(-Number(row.barrier_value || 0))}</span>
          <span class="unchain-scanner-pill ${bestPillClass}">✧ Best: ${bestSide}</span>
          ${applyBtn}
        </div>
        <div class="unchain-scanner-bar-wrap">
          <div class="unchain-scanner-bar-label">Score</div>
          <div class="unchain-scanner-bar"><span style="width:${score}%;"></span></div>
        </div>
      </div>`;
    }).join("");
  }

  async function analyzeScanner(windowTicks) {
    try {
      const activeWindow = Number(windowTicks || (state.scanner && state.scanner.window_ticks) || 20);
      const r = await postJSON("/unchain_scanner/start", { window: activeWindow });
      const msg = (r.data && (r.data.message || r.data.error)) || `Market Scanner ON (${activeWindow} ticks)`;
      if (r.ok && r.data && r.data.scanner) renderScanner(r.data.scanner);
      toast(msg, (r.ok && (!r.data || r.data.status !== "error")) ? "success" : "error");
    } catch (e) {
      toast("Failed to start market scanner", "error");
    }
  }

  async function stopScanner() {
    try {
      const r = await postJSON("/unchain_scanner/stop", {});
      if (r.ok && r.data && r.data.scanner) renderScanner(r.data.scanner);
      toast((r.data && (r.data.message || "Market Scanner OFF")) || "Market Scanner OFF", r.ok ? "info" : "error");
    } catch (e) {
      toast("Failed to stop market scanner", "error");
    }
  }

  async function toggleScanner() {
    const running = !!(state.scanner && state.scanner.running);
    if (running) {
      await stopScanner();
      return;
    }
    await analyzeScanner();
  }

  async function applyScannerSymbol(symbol) {
    if (!symbol) return;
    const r = await postJSON("/unchain_scanner/apply", { symbol, switch_symbol: true });
    if (r.ok && r.data) {
      if (r.data.payload) renderPayload(r.data.payload, { forceForm: true });
      toast(r.data.message || `Applied ${symbol}`, "success");
    } else {
      toast((r.data && (r.data.message || r.data.error)) || `Apply failed for ${symbol}`, "error");
      if (r.data && r.data.payload) renderPayload(r.data.payload);
    }
  }


  function renderBias(un) {
    const bias = (un && un.bias) || {};
    const headlineEl = el("unchainBiasHeadline");
    const subEl = el("unchainBiasSub");
    const higherEl = el("unchainHigherBiasPct");
    const lowerEl = el("unchainLowerBiasPct");
    const strengthEl = el("unchainBiasStrength");
    const reasonsEl = el("unchainBiasReasons");

    const status = String(bias.status || "LOADING ANALYZER…");
    const higherPct = Number.isFinite(Number(bias.higher_pct)) ? Number(bias.higher_pct) : 50;
    const lowerPct = Number.isFinite(Number(bias.lower_pct)) ? Number(bias.lower_pct) : 50;
    const strength = String(bias.strength || "Building");
    const reasons = Array.isArray(bias.reasons) && bias.reasons.length ? bias.reasons : ["Waiting for data"];
    const lookback = Number(bias.lookback || 0);
    const rangeWidth = Number.isFinite(Number(bias.range_width)) ? Number(bias.range_width) : null;
    const rangePct = Number.isFinite(Number(bias.range_pct)) ? Number(bias.range_pct) : null;

    if (headlineEl) {
      headlineEl.innerText = status;
      const upper = status.toUpperCase();
      headlineEl.style.color = upper.includes("HIGHER")
        ? "#22c55e"
        : upper.includes("LOWER")
        ? "#ef4444"
        : "#e2e8f0";
    }

    if (subEl) {
      const basis = bias.summary || (lookback > 0
        ? `Based on the latest ${lookback} ticks and your current UNCHAIN duration/barriers.`
        : "Gathering enough recent ticks to score Higher vs Lower.");
      const rangeText = rangeWidth != null ? `Range ${rangeWidth.toFixed(4)} (${rangePct != null ? rangePct.toFixed(2) : "—"}%) • ` : "";
      subEl.innerText = basis ? `${rangeText}${basis}` : rangeText;
    }

    if (higherEl) higherEl.innerText = `${higherPct.toFixed(1)}%`;
    if (lowerEl) lowerEl.innerText = `${lowerPct.toFixed(1)}%`;

    if (strengthEl) {
      strengthEl.innerText = strength;
      const s = strength.toUpperCase();
      strengthEl.style.color = s.includes("STRONG")
        ? "#f59e0b"
        : s.includes("MEDIUM")
        ? "#38bdf8"
        : "#cbd5e1";
    }

    if (reasonsEl) {
      reasonsEl.innerHTML = reasons
        .map((reason) => `<span class="unchain-reason-chip">${String(reason)}</span>`)
        .join("");
    }
  }

  function renderPayload(payload, opts) {
    if (!payload) return;
    const un = payload.unchain || payload;
    const nextSymbol = String(
      payload.main_symbol || payload.symbol || un.main_symbol || un.symbol || ""
    ).toUpperCase();
    const nextBarrierKey = String(un.market_default_key || payload.market_default_key || "").toUpperCase();
    const symbolChanged = !!nextSymbol && nextSymbol !== String(state.lastMainSymbol || "").toUpperCase();
    const barrierKeyChanged = !!nextBarrierKey && nextBarrierKey !== String(state.lastBarrierKey || "").toUpperCase();
    state.lastPayload = payload;
    state.scanner = payload.scanner || state.scanner;
    fillForm(un, !!(opts && opts.forceForm), { forceBarriers: symbolChanged || barrierKeyChanged });
    let savedMarketBarriers = seedMarketBarrierSettingsFromPayload(nextSymbol, un);
    if (savedMarketBarriers && savedMarketBarriers.is_custom) {
      applySavedMarketBarrierSettingsToForm(savedMarketBarriers, symbolChanged || barrierKeyChanged || !!(opts && opts.forceForm));
      const payloadSignature = buildMarketBarrierSignature(nextSymbol, getPayloadMarketBarrierSettings(un));
      const savedSignature = buildMarketBarrierSignature(nextSymbol, savedMarketBarriers);
      if (savedSignature && savedSignature !== payloadSignature) {
        syncSavedMarketBarrierSettingsToServer(nextSymbol, savedMarketBarriers).catch(() => {});
      }
    }
    if (nextSymbol) state.lastMainSymbol = nextSymbol;
    if (nextBarrierKey) state.lastBarrierKey = nextBarrierKey;
    renderStatusChip(un, payload);
    renderRiskBlock(un);
    renderAutoBoth(un);
    const stats = (un && un.stats) || {};
    const net = Number(stats.net_pnl || 0);
    setText("unchainNetPnl", `${net >= 0 ? "+" : "-"}$${Math.abs(net).toFixed(2)}`);
    const pnlEl = el("unchainNetPnl");
    if (pnlEl) pnlEl.style.color = net >= 0 ? "#22c55e" : "#ef4444";
    setText("unchainWinLoss", `${Number(stats.wins || 0)} / ${Number(stats.losses || 0)}`);
    setText("unchainActiveCount", Number(un.active_count || 0));
    const lastResult = un.last_result;
    if (lastResult) {
      const p = Number(lastResult.profit || 0);
      setText("unchainLastResult", `${String(lastResult.type || "TRADE").toUpperCase()} ${p >= 0 ? "+" : "-"}$${Math.abs(p).toFixed(2)}`);
      const lr = el("unchainLastResult");
      if (lr) lr.style.color = p >= 0 ? "#22c55e" : "#ef4444";
    } else {
      setText("unchainLastResult", "—");
      const lr = el("unchainLastResult");
      if (lr) lr.style.color = "#f8fafc";
    }
    setText("unchainLastAction", un.last_action || "Ready");
    renderScanner(state.scanner);
    renderBothAnalyzer(un);
    renderKoolkidHl(un);
    renderBias(un);
    renderBarrierMarketChart(un, payload);
    try {
      if (typeof window.syncUnchainPendingTradesFromStatus === "function") {
        const changed = window.syncUnchainPendingTradesFromStatus(payload);
        if (changed && isActive() && typeof renderTradeList === "function") {
          renderTradeList(PROFILE);
        }
      }
    } catch (e) {}
    renderActiveTrades(un);
  }

  async function refreshStatus(silent) {
    if (!isActive()) return;
    const r = await getJSON("/unchain_status");
    if (r.ok && r.data) {
      renderPayload(r.data);
    } else if (!silent) {
      toast((r.data && (r.data.message || r.data.error)) || "Failed to load UNCHAIN status", "error");
    }
  }

  async function saveSettings(showToastMsg) {
    const form = readForm();
    state.isSaving = true;
    const r = await postJSON("/unchain_settings", form);
    state.isSaving = false;
    if (r.ok && r.data) {
      const payload = r.data && (r.data.unchain || r.data);
      const symbol = normalizeMarketSymbol(
        (r.data && (r.data.main_symbol || r.data.symbol)) ||
        (payload && (payload.main_symbol || payload.symbol)) ||
        state.lastMainSymbol ||
        getCurrentMarketSymbol()
      );
      persistMarketBarrierSettings(symbol, form, {
        custom: !areBarrierSettingsEqual(form, getPayloadMarketBarrierSettings(payload)),
      });
      clearDirtyFields();
      renderPayload(r.data, { forceForm: true });
      if (showToastMsg) toast("UNCHAIN settings saved", "success");
    } else {
      toast((r.data && (r.data.message || r.data.error)) || "Failed to save UNCHAIN settings", "error");
    }
    return r;
  }

  async function sendTrade(side) {
    await saveSettings(false);
    const form = readForm();
    const r = await postJSON("/unchain_trade", Object.assign({ side }, form));
    if (r.ok && r.data) {
      clearDirtyFields();
      if (r.data.payload) renderPayload(r.data.payload, { forceForm: true });
      toast(r.data.message || `${side} sent`, "success");
    } else {
      toast((r.data && (r.data.message || r.data.error)) || `${side} failed`, "error");
      if (r.data && r.data.payload) renderPayload(r.data.payload);
    }
  }

  async function refreshMarketBarriers() {
    const r = await postJSON("/unchain_refresh_barriers", {});
    if (r.ok && r.data) {
      const payload = r.data.payload || {};
      const un = payload.unchain || payload;
      const symbol = normalizeMarketSymbol(
        payload.main_symbol || payload.symbol || un.main_symbol || un.symbol || state.lastMainSymbol || getCurrentMarketSymbol()
      );
      persistMarketBarrierSettings(symbol, {
        higher_barrier: un.higher_barrier,
        lower_barrier: un.lower_barrier,
        koolkid_higher_barrier: un.koolkid_higher_barrier,
        koolkid_lower_barrier: un.koolkid_lower_barrier,
      }, { custom: false });
      BARRIER_FIELD_IDS.forEach((id) => state.dirtyFields.delete(id));
      renderPayload(payload, { forceForm: true });
      toast(r.data.message || "Barrier refreshed", "success");
    } else {
      toast((r.data && (r.data.message || r.data.error)) || "Failed to refresh barrier", "error");
      if (r.data && r.data.payload) renderPayload(r.data.payload, { forceForm: true });
    }
  }

  async function closeAll() {
    const r = await postJSON("/unchain_close_now", {});
    if (r.ok && r.data) {
      if (r.data.payload) renderPayload(r.data.payload);
      toast(r.data.message || "Sell request sent", "warn");
    } else {
      toast((r.data && (r.data.message || r.data.error)) || "Close failed", "error");
      if (r.data && r.data.payload) renderPayload(r.data.payload);
    }
  }

  async function clearActive() {
    const r = await postJSON("/unchain_clear_active", {});
    if (r.ok && r.data) {
      if (r.data.payload) renderPayload(r.data.payload, { forceForm: true });
      const count = Array.isArray(r.data.cleared) ? r.data.cleared.length : 0;
      const msg = r.data.message || (count ? `Cleared ${count} active trade(s)` : "No active UNCHAIN trades to clear");
      toast(msg, count ? "success" : "info");
    } else {
      toast((r.data && (r.data.message || r.data.error)) || "Clear failed", "error");
      if (r.data && r.data.payload) renderPayload(r.data.payload);
    }
  }

  async function toggleAutoBoth() {
    await saveSettings(false);
    const current = !!(state.lastPayload && state.lastPayload.unchain && state.lastPayload.unchain.auto_both_enabled);
    const r = await postJSON("/toggle_unchain_auto", { enabled: !current });
    if (r.ok && r.data) {
      if (r.data.payload) renderPayload(r.data.payload, { forceForm: true });
      toast(r.data.message || (!current ? "UNCHAIN AUTO BOTH ON" : "UNCHAIN AUTO BOTH OFF"), !current ? "success" : "warn");
    } else {
      toast((r.data && (r.data.message || r.data.error)) || "Failed to toggle UNCHAIN AUTO BOTH", "error");
      if (r.data && r.data.payload) renderPayload(r.data.payload);
    }
  }

  async function toggleAiAutoTrade() {
    await saveSettings(false);
    const current = !!(state.lastPayload && state.lastPayload.unchain && state.lastPayload.unchain.ai_auto_trade_enabled);
    const r = await postJSON("/toggle_unchain_ai_auto_trade", { enabled: !current });
    if (r.ok && r.data) {
      if (r.data.payload) renderPayload(r.data.payload, { forceForm: true });
      toast(r.data.message || (!current ? "UNCHAIN AI AUTO TRADE ON" : "UNCHAIN AI AUTO TRADE OFF"), !current ? "success" : "warn");
    } else {
      toast((r.data && (r.data.message || r.data.error)) || "Failed to toggle UNCHAIN AI AUTO TRADE", "error");
      if (r.data && r.data.payload) renderPayload(r.data.payload);
    }
  }

  async function handleAction(action, btn) {
    switch (action) {
      case "unchain-toggle-autosl":
        state.auto_sl = !state.auto_sl;
        applyAutoSlBtn();
        break;
      case "unchain-save-settings":
        await saveSettings(true);
        break;
      case "unchain-trade-higher":
        await sendTrade("HIGHER");
        break;
      case "unchain-trade-lower":
        await sendTrade("LOWER");
        break;
      case "unchain-trade-both":
        await sendTrade("BOTH");
        break;
      case "unchain-higher-preset":
        applyMainBarrierPreset("HIGHER", btn && btn.dataset ? btn.dataset.value : "+0.12");
        break;
      case "unchain-lower-preset":
        applyMainBarrierPreset("LOWER", btn && btn.dataset ? btn.dataset.value : "-0.12");
        break;
      case "unchain-barrier-step":
        if (btn && btn.dataset && btn.dataset.target) {
          nudgeBarrierField(btn.dataset.target, btn.dataset.delta);
        }
        break;
      case "unchain-koolkid-panel":
        toggleKoolkidPanel();
        break;
      case "unchain-koolkid-close":
        toggleKoolkidPanel();
        break;
      case "unchain-koolkid-hl":
        await toggleKoolkidHl();
        break;
      case "unchain-koolkid-both":
        await toggleKoolkidBoth();
        break;
      case "unchain-toggle-auto-both":
        await toggleAutoBoth();
        break;
      case "unchain-toggle-ai-auto-trade":
        await toggleAiAutoTrade();
        break;
      case "unchain-close-all":
        await closeAll();
        break;
      case "unchain-clear-active":
        await clearActive();
        break;
      case "unchain-scanner-toggle":
        await toggleScanner();
        break;
      case "unchain-scanner-window":
        if (btn && btn.dataset && btn.dataset.window) {
          await analyzeScanner(Number(btn.dataset.window));
        }
        break;
      case "unchain-scanner-analyze":
        await analyzeScanner();
        break;
      case "unchain-both-toggle":
        toggleBothAnalyzer();
        break;
      case "unchain-both-analyze":
        await analyzeBothTool();
        break;
      case "unchain-both-apply":
        await applyBothRecommendation();
        break;
      case "unchain-scanner-apply":
        if (btn && btn.dataset && btn.dataset.symbol) {
          await applyScannerSymbol(btn.dataset.symbol);
        }
        break;
      case "unchain-refresh-barriers":
        await refreshMarketBarriers();
        break;
      default:
        break;
    }
  }

  function bindSocket() {
    try {
      if (typeof socket === "undefined" || !socket) return;
      if (state.lastSocket === socket && state.socketBound) return;
      state.lastSocket = socket;
      state.socketBound = true;
      socket.on("tick", (data) => {
        if (!data) return;
        pushBarrierChartPrice(data.price != null ? data.price : data.quote, data.symbol);
        if (isActive()) {
          const un = state.lastPayload && (state.lastPayload.unchain || state.lastPayload);
          renderBarrierMarketChart(un || {}, state.lastPayload || data || {});
        }
      });
      socket.on("unchain_status", (data) => {
        if (!isActive() || !data) return;
        renderPayload(data);
      });
      socket.on("unchain_scanner", (data) => {
        if (!isActive() || !data) return;
        renderScanner(data);
      });
      socket.on("unchain_toast", (data) => {
        if (!isActive() || !data) return;
        toast(data.message || "UNCHAIN notice", data.type || "info");
      });
      socket.on("trade_result", () => {
        if (!isActive()) return;
        setTimeout(() => refreshStatus(true), 200);
      });
      socket.on("trade_placed", (trade) => {
        if (!isActive() || !trade) return;
        if ((trade.profile || "").toUpperCase() === "UNCHAIN") {
          setTimeout(() => refreshStatus(true), 120);
        }
      });
    } catch (e) {}
  }

  function bindFormInputs() {
    FORM_FIELDS.forEach((id) => {
      const node = el(id);
      if (!node || node.dataset.unchainBound === "1") return;
      node.dataset.unchainBound = "1";
      node.addEventListener("focus", () => { markDirty(id); });
      node.addEventListener("input", () => {
        markDirty(id);
        if (id === "unchainHigherStake") mirrorHigherStakeToLower();
        if (id === "unchainHigherBarrier" || id === "unchainLowerBarrier") renderBarrierMarketChart(state.lastPayload && (state.lastPayload.unchain || state.lastPayload) || {}, state.lastPayload || {});
        if (id === "unchainAutoConfidence") applyAutoConfidenceLabel();
      });
      node.addEventListener("change", () => {
        markDirty(id);
        if (id === "unchainHigherStake") mirrorHigherStakeToLower();
        if (id === "unchainHigherBarrier" || id === "unchainLowerBarrier") renderBarrierMarketChart(state.lastPayload && (state.lastPayload.unchain || state.lastPayload) || {}, state.lastPayload || {});
        if (id === "unchainDurationUnit") applyDurationPresets();
        if (id === "unchainAutoConfidence") applyAutoConfidenceLabel();
        if (BARRIER_FIELD_IDS.has(id)) {
          persistCurrentMarketBarrierSettings(null, { custom: true });
          scheduleCurrentMarketBarrierSync(null, { custom: true });
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

  function bindMarketBarrierPersistence() {
    const picker = el("symbol");
    if (!picker || picker.dataset.unchainBarrierBound === "1") return;
    picker.dataset.unchainBarrierBound = "1";
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
    const app = App();
    if (root && app.bindActionButtons) {
      app.bindActionButtons(root, async ({ action, btn }) => {
        try {
          await handleAction(action, btn);
        } catch (e) {
          toast("UNCHAIN action error", "error");
        }
      }, "unchain_action_clicks_v2");
    }
    applyDurationPresets(true);
    bindFormInputs();
    applyAutoSlBtn();
    applyHalfBarrierToggle();
    applyKoolkidReversalToggle();
    applyKoolkidHalfBarrierToggle();
    applyAutoConfidenceLabel();
    bindHalfBarrierToggle();
    bindKoolkidReversalToggle();
    bindKoolkidHalfBarrierToggle();
    bindKoolkidModal();
    bindMarketBarrierPersistence();
  }

  function startPolling() {
    stopPolling();
    state.pollTimer = setInterval(() => {
      if (isActive()) refreshStatus(true);
      else removeTradeCountdownToast();
    }, 1200);
  }

  function stopPolling() {
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
  }

  async function onMount(payload) {
    const root = payload && payload.root ? payload.root : document.getElementById("profileContainer");
    bindUI(root);
    bindSocket();
    startPolling();
    await refreshStatus(true);
  }

  async function afterLoadProfileUI() {
    bindUI(document.getElementById("profileContainer"));
    bindSocket();
    startPolling();
    await refreshStatus(true);
  }

  async function onActivate() {
    bindSocket();
    bindUI(document.getElementById("profileContainer"));
    startPolling();
    await refreshStatus(true);
  }

  if (typeof window.registerProfileModule === "function") {
    window.registerProfileModule(PROFILE, { onMount, afterLoadProfileUI, onActivate });
  } else {
    window.ProfileModules = window.ProfileModules || {};
    window.ProfileModules[PROFILE] = { onMount, afterLoadProfileUI, onActivate };
  }
})();
