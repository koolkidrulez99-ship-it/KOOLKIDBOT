(function () {
  const PROFILE = "HUMAN";

  function getApp() {
    return window.BotApp || {};
  }

  function bindUI(root) {
    const App = getApp();
    if (!root || !App.bindActionButtons) return;

    App.bindActionButtons(root, async ({ action, btn, event }) => {
      switch (action) {
        // ===== Add HUMAN-only buttons here later =====
        // Suggested actions:
        // case "human-chart-zoom-out":
        // case "human-chart-reset":
        // case "human-keepalive-toggle":
        // case "humanx-auto-toggle":
        // etc.

        default:
          break;
      }
    }, "human_action_clicks");
  }

  async function onMount(payload) {
    const root = payload && payload.root ? payload.root : document.getElementById("profileContainer");
    bindUI(root);

    // Keep this empty for now.
    // Your index currently still initializes HUMAN chart/keepalive itself.
    // Later we move that logic here.
  }

  async function afterLoadProfileUI(payload) {
    // Optional future move:
    // if (typeof initHumanChartIfPresent === "function") initHumanChartIfPresent();
    // if (typeof refreshHumanKeepAliveStatus === "function") refreshHumanKeepAliveStatus();
  }

  async function onActivate(payload) {
    // Optional future move:
    // if (typeof refreshHumanKeepAliveUI === "function") await refreshHumanKeepAliveUI();
  }

  if (typeof window.registerProfileModule === "function") {
    window.registerProfileModule(PROFILE, {
      onMount,
      afterLoadProfileUI,
      onActivate
    });
  } else {
    window.ProfileModules = window.ProfileModules || {};
    window.ProfileModules[PROFILE] = { onMount, afterLoadProfileUI, onActivate };
  }
})();