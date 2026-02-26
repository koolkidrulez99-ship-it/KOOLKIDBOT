(function () {
  const PROFILE = "JOKERJOE";
  const state = { lastSocket: null, socketBound: false, autoModes: {}, kidgxBarrier: 5 };

  function App() { return window.BotApp || {}; }
  function isActive() { try { return typeof activeProfile !== "undefined" && activeProfile === PROFILE; } catch (e) { return false; } }
  function safeToast(msg, type) { try { if (typeof showToast === "function") showToast(msg, type || "info"); } catch (e) {} }

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
      const on = !!state.autoModes.ai_auto_trading;
      aiBtn.innerText = `🤖AI AUTO-TRADING: ${on ? "ON" : "OFF"}`;
      aiBtn.style.background = on ? "#22c55e" : "#1e293b";
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
        updateButtons();
      });

      socket.on("auto_mode_update", (modes) => {
        if (!isActive()) return;
        state.autoModes = Object.assign({}, state.autoModes, modes || {});
        updateButtons();
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
    bindSocketListeners();
    bindBarrierSync();
    updateButtons();
  }

  async function afterLoadProfileUI() {
    try { App().applyDigitSelectionUI && App().applyDigitSelectionUI(); } catch (e) {}
    patchKidgambleConfirm();
    bindSocketListeners();
    bindBarrierSync();
    updateButtons();
  }

  async function onActivate() {
    try { App().applyDigitSelectionUI && App().applyDigitSelectionUI(); } catch (e) {}
    patchKidgambleConfirm();
    bindSocketListeners();
    bindBarrierSync();
    state.kidgxBarrier = currentBarrier();
    updateButtons();
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
    const r = await postJSON("/toggle_ai_auto_trading", { profile: "JOKERJOE" });
    if (r.data && r.data.status === "success") {
      state.autoModes.ai_auto_trading = !!r.data.ai_auto_trading;
      updateButtons();
      safeToast(`🤖AI AUTO-TRADING: ${state.autoModes.ai_auto_trading ? "ON" : "OFF"}`, state.autoModes.ai_auto_trading ? "success" : "error");
    } else {
      safeToast((r.data && r.data.message) || "AI auto failed", "error");
    }
  };

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
