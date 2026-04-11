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
  });

  App.log("app.js ready");
})();
