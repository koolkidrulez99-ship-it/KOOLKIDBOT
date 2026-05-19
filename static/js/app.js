(function () {
  // Shared app namespace (safe to load even if empty before)
  const App = (window.BotApp = window.BotApp || {});

  // Prevent double-init if script loads again
  if (App.__booted) return;
  App.__booted = true;

  App.debug = false;

  App.log = function (...args) {
    try {
      if (App.debug) console.log("[BotApp]", ...args);
    } catch (e) {}
  };

  App.safeToast = function (msg, type = "info") {
    try {
      if (typeof window.showToast === "function") {
        window.showToast(msg, type);
      }
    } catch (e) {}
  };

  App.safeCall = function (fn, ...args) {
    try {
      if (typeof fn === "function") return fn(...args);
    } catch (e) {}
    return null;
  };

  App.safeFetchJSON = async function (url, options) {
    try {
      const res = await fetch(url, options || {});
      let data = null;
      try {
        data = await res.json();
      } catch (e) {
        data = null;
      }
      return { ok: res.ok, status: res.status, data, res };
    } catch (e) {
      return { ok: false, status: 0, data: null, error: e };
    }
  };

  // Bind a delegated event ONE TIME per root + key
  App.bindDelegated = function (root, eventName, selector, handler, bindKey) {
    try {
      if (!root || !eventName || !selector || typeof handler !== "function") return false;

      const key = bindKey || `${eventName}:${selector}`;
      const attr = `delegateBound_${key.replace(/[^a-zA-Z0-9_-]/g, "_")}`;

      if (root.dataset && root.dataset[attr] === "1") return true;

      root.addEventListener(eventName, function (e) {
        try {
          const target = e.target && e.target.closest ? e.target.closest(selector) : null;
          if (!target || !root.contains(target)) return;
          handler(e, target, root);
        } catch (err) {}
      });

      if (root.dataset) root.dataset[attr] = "1";
      return true;
    } catch (e) {
      return false;
    }
  };

  // Utility for action buttons: [data-action]
  App.bindActionButtons = function (root, actionHandler, bindKey = "dataActionClicks") {
    return App.bindDelegated(
      root,
      "click",
      "[data-action]",
      function (e, btn, r) {
        try {
          const action = (btn.dataset.action || "").trim();
          if (!action) return;
          actionHandler({ event: e, btn, root: r, action });
        } catch (err) {}
      },
      bindKey
    );
  };

  App.currentProfile = function () {
    try {
      if (typeof activeProfile !== "undefined") return activeProfile;
    } catch (e) {}
    return null;
  };


  // ---------------- Digit selection styling (blue box) ----------------
  App.__digitStyleInjected = false;
  App.ensureDigitSelectionStyles = function () {
    try {
      if (App.__digitStyleInjected) return;
      const st = document.createElement("style");
      st.id = "botapp-digit-selection-style";
      st.textContent = `
        .digit-cell.botapp-selected { background:#1d4ed8 !important; border-color:#60a5fa !important; box-shadow:0 0 0 1px rgba(96,165,250,.6) inset !important; }
        .digit-cell.botapp-selected > div:first-child { color:#e2e8f0 !important; }
        .digit-cell.flash { background:#b91c1c !important; border-color:#ef4444 !important; box-shadow:0 0 0 1px rgba(239,68,68,.45) inset, 0 0 14px rgba(239,68,68,.25) !important; }
        .digit-cell.flash > div:first-child { color:#f8fafc !important; }
        .digit-cell.flash > div:last-child { color:#fecaca !important; }
      `;
      document.head.appendChild(st);
      App.__digitStyleInjected = true;
    } catch (e) {}
  };

  App.koolkidSelectedDigits = App.koolkidSelectedDigits || [];
  App.jokerjoeSelectedDigit = App.jokerjoeSelectedDigit ?? null;

  App.applyDigitSelectionUI = function () {
    try {
      App.ensureDigitSelectionStyles();
      const prof = App.currentProfile();
      for (let i = 0; i < 10; i++) {
        const cell = document.getElementById(`digit-${i}`);
        if (!cell) continue;
        cell.classList.remove("botapp-selected");
      }
      if (prof === "KOOLKID") {
        const set = new Set((App.koolkidSelectedDigits || []).map(Number));
        set.forEach((d) => {
          const cell = document.getElementById(`digit-${d}`);
          if (cell) cell.classList.add("botapp-selected");
        });
      } else if (prof === "JOKERJOE") {
        const d = Number(App.jokerjoeSelectedDigit);
        if (!isNaN(d)) {
          const cell = document.getElementById(`digit-${d}`);
          if (cell) cell.classList.add("botapp-selected");
        }
      }
    } catch (e) {}
  };

  App.ensureDigitClickPatch = function () {
    try {
      if (App.__digitClickPatched) return true;
      if (typeof window.onDigitClicked !== "function") return false;
      const original = window.onDigitClicked;
      window.onDigitClicked = function (digit, ev) {
        const prof = App.currentProfile();
        if (prof === "KOOLKID") {
          const d = Number(digit);
          App.koolkidSelectedDigits = isNaN(d) ? [] : [d];
          try {
            window.dispatchEvent(new CustomEvent("botapp:koolkidSelectedDigitsChanged", { detail: { digits: App.koolkidSelectedDigits.slice() } }));
          } catch (e) {}
        } else if (prof === "JOKERJOE") {
          App.jokerjoeSelectedDigit = Number(digit);
        }
        const out = original.apply(this, arguments);
        setTimeout(() => App.applyDigitSelectionUI(), 0);
        return out;
      };
      App.__digitClickPatched = true;
      return true;
    } catch (e) {
      return false;
    }
  };

  App.ensureDigitClickPatchSoon = function () {
    if (App.ensureDigitClickPatch()) return;
    if (App.__digitClickPatchTimer) return;
    let tries = 0;
    const t = setInterval(() => {
      tries += 1;
      if (App.ensureDigitClickPatch() || tries > 40) {
        if (typeof App.clearFrontendInterval === "function") {
          App.clearFrontendInterval("digit_click_patch_retry");
        } else {
          clearInterval(t);
        }
        App.__digitClickPatchTimer = null;
      }
    }, 250);
    App.__digitClickPatchTimer = t;
    if (typeof App.registerFrontendInterval === "function") App.registerFrontendInterval("digit_click_patch_retry", t);
  };

  App.ensureDigitClickPatchSoon();
  document.addEventListener("DOMContentLoaded", () => {
    App.ensureDigitSelectionStyles();
    setTimeout(() => App.applyDigitSelectionUI(), 200);
    App.loadCustomUiSettings().catch(() => {});
  });

  App.customUi = App.customUi || {
    settings: { hidden: [] },
    loaded: false,
    editMode: false,
    saveTimer: null,
  };

  App.normalizeCustomUiKey = function (value) {
    const key = String(value || "").trim();
    if (!key || key.length > 160) return "";
    return /^[a-zA-Z0-9_\-:.]+$/.test(key) ? key : "";
  };

  App.getCustomUiCandidates = function () {
    const selector = [
      "#koolkidAutoTradeLaunchBtn",
      "#marthaAiPanel",
      "#accountDashboard",
      "#liveTickCard",
      "#profileTitle",
      ".profile-btn[id]",
      "#profileContainer button[id]",
      "#profileContainer details[id]",
      "#profileContainer .card[id]",
      "#profileContainer .ui-group[id]",
      "#profileContainer [data-custom-ui-id]",
    ].join(",");
    const nodes = Array.from(document.querySelectorAll(selector));
    const seen = new Set();
    return nodes.filter((node) => {
      if (!node || node === document.getElementById("customEditsOpenBtn")) return false;
      if (node.closest && node.closest("#customUiModal")) return false;
      const raw = node.getAttribute("data-custom-ui-id") || node.id;
      const key = App.normalizeCustomUiKey(raw);
      if (!key || seen.has(key)) return false;
      seen.add(key);
      node.dataset.customUiKey = key;
      return true;
    });
  };

  App.customUiLabelFor = function (node) {
    if (!node) return "UI item";
    const explicit = node.getAttribute("aria-label") || node.getAttribute("title") || node.dataset.customUiLabel;
    if (explicit) return explicit.trim();
    const text = String(node.innerText || node.textContent || "").replace(/\s+/g, " ").trim();
    if (text) return text.slice(0, 80);
    return node.id || node.dataset.customUiKey || "UI item";
  };

  App.applyCustomUiSettings = function () {
    try {
      const hidden = new Set(((App.customUi.settings || {}).hidden || []).map(String));
      App.getCustomUiCandidates().forEach((node) => {
        const key = node.dataset.customUiKey;
        node.classList.toggle("custom-ui-hidden", hidden.has(key));
        node.setAttribute("data-custom-ui-managed", "1");
      });
      App.renderCustomUiEditorList();
    } catch (e) {}
  };

  App.loadCustomUiSettings = async function () {
    const result = await App.safeFetchJSON("/custom_ui_settings", { method: "GET" });
    if (result.ok && result.data && result.data.settings) {
      App.customUi.settings = {
        hidden: Array.isArray(result.data.settings.hidden) ? result.data.settings.hidden : [],
      };
      App.customUi.loaded = true;
      App.applyCustomUiSettings();
    }
  };

  App.queueCustomUiSave = function () {
    if (App.customUi.saveTimer) clearTimeout(App.customUi.saveTimer);
    App.customUi.saveTimer = setTimeout(() => {
      App.saveCustomUiSettings(false).catch(() => {});
    }, 350);
  };

  App.saveCustomUiSettings = async function (showMessage = true) {
    const payload = { settings: { hidden: ((App.customUi.settings || {}).hidden || []) } };
    const result = await App.safeFetchJSON("/custom_ui_settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (result.ok && result.data && result.data.settings) {
      App.customUi.settings = result.data.settings;
      App.applyCustomUiSettings();
      if (showMessage) App.safeToast("Custom UI saved.", "success");
      return true;
    }
    if (showMessage) App.safeToast("Could not save Custom UI.", "error");
    return false;
  };

  App.resetCustomUiSettings = async function () {
    const result = await App.safeFetchJSON("/custom_ui_reset", { method: "POST" });
    App.customUi.settings = { hidden: [] };
    App.applyCustomUiSettings();
    if (result.ok) App.safeToast("Custom UI reset to default.", "success");
    else App.safeToast("Custom UI reset locally. Server save failed.", "warn");
  };

  App.hideCustomUiKey = function (key) {
    const safe = App.normalizeCustomUiKey(key);
    if (!safe) return;
    const hidden = new Set(((App.customUi.settings || {}).hidden || []).map(String));
    hidden.add(safe);
    App.customUi.settings = { hidden: Array.from(hidden) };
    App.applyCustomUiSettings();
    App.queueCustomUiSave();
  };

  App.restoreCustomUiKey = function (key) {
    const safe = App.normalizeCustomUiKey(key);
    const hidden = ((App.customUi.settings || {}).hidden || []).filter((item) => String(item) !== safe);
    App.customUi.settings = { hidden };
    App.applyCustomUiSettings();
    App.queueCustomUiSave();
  };

  App.openCustomUiEditor = function () {
    const modal = document.getElementById("customUiModal");
    if (modal) modal.classList.add("is-open");
    App.applyCustomUiSettings();
    App.renderCustomUiEditorList();
  };

  App.closeCustomUiEditor = function () {
    const modal = document.getElementById("customUiModal");
    if (modal) modal.classList.remove("is-open");
  };

  App.toggleCustomUiEditMode = function () {
    App.customUi.editMode = !App.customUi.editMode;
    document.body.classList.toggle("custom-ui-editing", !!App.customUi.editMode);
    const btn = document.getElementById("customUiEditModeBtn");
    if (btn) {
      btn.textContent = `Edit Mode: ${App.customUi.editMode ? "ON" : "OFF"}`;
      btn.style.background = App.customUi.editMode ? "#22c55e" : "#f59e0b";
      btn.style.color = App.customUi.editMode ? "#052e16" : "#111827";
    }
    const status = document.getElementById("customUiStatus");
    if (status) status.textContent = App.customUi.editMode
      ? "Edit Mode is ON. Click a highlighted button or section to hide it from your UI."
      : "Turn on Edit Mode, then click a highlighted UI item to hide it.";
    App.applyCustomUiSettings();
  };

  App.renderCustomUiEditorList = function () {
    const list = document.getElementById("customUiList");
    if (!list) return;
    const hidden = new Set(((App.customUi.settings || {}).hidden || []).map(String));
    const candidates = App.getCustomUiCandidates()
      .map((node) => ({ key: node.dataset.customUiKey, label: App.customUiLabelFor(node), hidden: hidden.has(node.dataset.customUiKey) }))
      .filter((row) => row.key);
    const visibleRows = candidates.filter((row) => !row.hidden).slice(0, 120);
    const hiddenRows = Array.from(hidden).map((key) => {
      const found = candidates.find((row) => row.key === key);
      return { key, label: found ? found.label : key, hidden: true };
    });
    const rows = hiddenRows.concat(visibleRows);
    if (!rows.length) {
      list.innerHTML = `<div class="custom-ui-row"><div><div class="custom-ui-row-title">No customizable UI loaded yet.</div><div class="custom-ui-row-meta">Open a profile first, then come back here.</div></div></div>`;
      return;
    }
    list.innerHTML = rows.map((row) => `
      <div class="custom-ui-row">
        <div>
          <div class="custom-ui-row-title">${String(row.label || row.key).replace(/[<>&"]/g, (ch) => ({ "<":"&lt;", ">":"&gt;", "&":"&amp;", "\"":"&quot;" }[ch]))}</div>
          <div class="custom-ui-row-meta">${row.hidden ? "Hidden" : "Visible"} • ${row.key}</div>
        </div>
        <button type="button" onclick="BotApp.${row.hidden ? "restoreCustomUiKey" : "hideCustomUiKey"}('${row.key.replace(/'/g, "\\'")}')">${row.hidden ? "Restore" : "Hide"}</button>
      </div>
    `).join("");
  };

  document.addEventListener("click", function (event) {
    try {
      if (!App.customUi.editMode) return;
      const target = event.target && event.target.closest ? event.target.closest("[data-custom-ui-key]") : null;
      if (!target || target.closest("#customUiModal")) return;
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      App.hideCustomUiKey(target.dataset.customUiKey);
      App.safeToast(`${App.customUiLabelFor(target)} hidden. Restore it from Custom Edits.`, "info");
    } catch (e) {}
  }, true);

  if (document.readyState !== "loading") {
    setTimeout(() => App.loadCustomUiSettings().catch(() => {}), 0);
  }

  App.log("app.js ready");
})();
