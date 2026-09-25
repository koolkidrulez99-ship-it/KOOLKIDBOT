(function () {
  "use strict";
  const MODE_KEY = "koolkidUiMode";
  const TIMER_LABEL = "koolkid_concept_hud";
  let hudTimer = null;

  function active() {
    try { return String(activeProfile || "").toUpperCase() === "KOOLKID"; }
    catch (e) { return false; }
  }

  function mode() {
    try { return localStorage.getItem(MODE_KEY) === "concept" ? "concept" : "classic"; }
    catch (e) { return "classic"; }
  }

  function textOf(id, fallback) {
    const el = document.getElementById(id);
    const value = el ? String(el.textContent || "").trim() : "";
    return value || fallback;
  }

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  function syncHud() {
    if (!active() || !document.body || !document.body.classList.contains("koolkid-concept-ui")) return;
    const market = document.getElementById("symbol");
    const marketText = market && market.options && market.selectedIndex >= 0
      ? String(market.options[market.selectedIndex].text || market.value || "MARKET")
      : "MARKET";
    const stakeEl = document.getElementById("stake");
    const stake = Number(stakeEl && stakeEl.value);
    const pnlText = textOf("netPnlBox", "0.00");
    const pnlNumber = Number(String(pnlText).replace(/[^0-9+.-]/g, ""));
    const balanceText = textOf("balance", "0.00");
    setText("koolkidConceptMarket", marketText);
    setText("koolkidConceptDigit", textOf("lastDigitBox", "-"));
    setText("koolkidConceptTicks", textOf("tickCount", "0"));
    setText("koolkidConceptStake", Number.isFinite(stake) ? "$" + stake.toFixed(2) : "$0.00");
    setText("koolkidConceptBalance", /[$£€J]/.test(balanceText) ? balanceText : "$" + balanceText);
    setText("koolkidConceptPnl", /[$£€J]/.test(pnlText) ? pnlText : "$" + pnlText);
    setText("koolkidConceptState", textOf("apiStatus", "Idle"));
    const pnl = document.getElementById("koolkidConceptPnl");
    if (pnl) {
      pnl.classList.toggle("is-win", Number.isFinite(pnlNumber) && pnlNumber > 0);
      pnl.classList.toggle("is-loss", Number.isFinite(pnlNumber) && pnlNumber < 0);
    }
  }

  function stopHud() {
    const app = window.BotApp || {};
    const tracked = !!(app.clearFrontendInterval && app.clearFrontendInterval(TIMER_LABEL));
    if (hudTimer && !tracked) clearInterval(hudTimer);
    hudTimer = null;
  }
  function startHud() {
    stopHud();
    syncHud();
    hudTimer = setInterval(syncHud, 750);
    const app = window.BotApp || {};
    if (app.registerFrontendInterval) app.registerFrontendInterval(TIMER_LABEL, hudTimer);
  }

  function apply(nextMode, persist) {
    const next = nextMode === "concept" ? "concept" : "classic";
    if (persist !== false) {
      try { localStorage.setItem(MODE_KEY, next); } catch (e) {}
    }
    const enabled = next === "concept" && active();
    if (document.body) document.body.classList.toggle("koolkid-concept-ui", enabled);
    const btn = document.getElementById("koolkidUiModeSwitch");
    if (btn) {
      btn.textContent = next === "concept" ? "Use Original UI" : "Try New UI";
      btn.classList.toggle("is-concept", next === "concept");
      btn.setAttribute("aria-pressed", next === "concept" ? "true" : "false");
    }
    if (enabled) startHud();
    else stopHud();
  }

  function focus(section, shouldScroll) {
    const key = String(section || "trade").toLowerCase();
    document.querySelectorAll("[data-koolkid-concept-tab]").forEach((btn) => {
      btn.classList.toggle("is-active", btn.getAttribute("data-koolkid-concept-tab") === key);
    });
    const targets = {
      trade: document.getElementById("koolkidGoldenCardPromo") || document.getElementById("stake"),
      strategies: document.querySelector("#koolkidProfileUi .ui-primary-stack"),
      analysis: document.getElementById("digitGrid"),
      history: document.getElementById("koolkidTradeHistoryCard"),
    };
    let target = targets[key] || targets.trade;
    if (key === "analysis" && target && target.parentElement) target = target.parentElement;
    if (shouldScroll !== false && target && target.scrollIntoView) {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function toggle() {
    const next = mode() === "concept" ? "classic" : "concept";
    apply(next, true);
    if (next === "concept") focus("trade", false);
  }

  function deactivate() {
    stopHud();
    if (document.body) document.body.classList.remove("koolkid-concept-ui");
  }

  window.KoolkidConceptUI = { applySaved: () => apply(mode(), false), apply, deactivate, focus, syncHud };
  window.toggleKoolkidUiMode = toggle;
  window.focusKoolkidConceptSection = focus;
})();

(function () {
  const applyWhenReady = () => setTimeout(() => {
    if (document.getElementById("koolkidProfileUi") && window.KoolkidConceptUI) window.KoolkidConceptUI.applySaved();
  }, 0);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", applyWhenReady, { once: true });
  else applyWhenReady();
})();
