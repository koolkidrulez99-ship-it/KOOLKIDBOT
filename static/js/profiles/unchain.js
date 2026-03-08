(function () {
  const PROFILE = "UNCHAIN";
  const state = {
    socketBound: false,
    lastSocket: null,
    auto_sl: true,
    pollTimer: null,
    lastPayload: null,
    dirtyFields: new Set(),
    isSaving: false,
  };

  const FORM_FIELDS = [
    "unchainHigherStake",
    "unchainLowerStake",
    "unchainHigherBarrier",
    "unchainLowerBarrier",
    "unchainDuration",
    "unchainDurationUnit",
    "unchainTp",
    "unchainSl",
  ];

  function App() { return window.BotApp || {}; }
  function isActive() { try { return typeof activeProfile !== "undefined" && activeProfile === PROFILE; } catch (e) { return false; } }
  function el(id) { return document.getElementById(id); }
  function setText(id, v) { const n = el(id); if (n) n.innerText = v == null ? "—" : String(v); }
  function toast(msg, type) { try { if (typeof showToast === "function") showToast(msg, type || "info"); } catch (e) {} }

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

  function readForm() {
    return {
      higher_stake: readNumber("unchainHigherStake", 1),
      lower_stake: readNumber("unchainLowerStake", 1),
      higher_barrier: readText("unchainHigherBarrier", "0.12"),
      lower_barrier: readText("unchainLowerBarrier", "-0.12"),
      duration: readInteger("unchainDuration", 5),
      duration_unit: readText("unchainDurationUnit", "t").toLowerCase(),
      tp: readNumber("unchainTp", 0),
      sl: readNumber("unchainSl", 0),
      auto_sl: !!state.auto_sl,
    };
  }

  function applyAutoSlBtn() {
    const btn = el("unchainAutoSlBtn");
    if (!btn) return;
    btn.innerText = `AUTO SL: ${state.auto_sl ? "ON" : "OFF"}`;
    btn.style.background = state.auto_sl ? "#facc15" : "#64748b";
    btn.style.color = state.auto_sl ? "#111827" : "#fff";
  }

  function setFieldValue(id, value, force) {
    const node = el(id);
    if (!node) return;
    if (!force && (isFieldDirty(id) || document.activeElement === node)) return;
    node.value = value;
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

  function fillForm(un, force) {
    if (!un) return;
    setFieldValue("unchainHigherStake", Number(un.higher_stake || 1).toFixed(2), force);
    setFieldValue("unchainLowerStake", Number(un.lower_stake || 1).toFixed(2), force);
    setFieldValue("unchainHigherBarrier", un.higher_barrier || "0.12", force);
    setFieldValue("unchainLowerBarrier", un.lower_barrier || "-0.12", force);
    setFieldValue("unchainDuration", String(un.duration || 5), force);
    setFieldValue("unchainDurationUnit", (un.duration_unit || "t").toLowerCase(), force);
    setFieldValue("unchainTp", String(un.tp || 0), force);
    setFieldValue("unchainSl", String(un.sl || 0), force);
    state.auto_sl = !!un.auto_sl;
    applyAutoSlBtn();
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

  function renderActiveTrades(un) {
    const wrap = el("unchainActiveTrades");
    if (!wrap) return;
    const items = Array.isArray(un && un.active_contracts) ? un.active_contracts : [];
    if (!items.length) {
      wrap.innerHTML = '<div class="unchain-empty">No active UNCHAIN trades.</div>';
      return;
    }
    wrap.innerHTML = items.map((item) => {
      const type = String(item.type || item.side || "TRADE").toUpperCase();
      const profit = item.open_profit == null ? "—" : `$${Number(item.open_profit).toFixed(2)}`;
      const profitColor = item.open_profit == null ? "#f8fafc" : (Number(item.open_profit) >= 0 ? "#22c55e" : "#ef4444");
      const durationLabel = `${item.duration || "—"}${String(item.duration_unit || "").toUpperCase()}`;
      return `<div class="unchain-active-item"><div class="top"><div style="font-weight:900;color:${type === "HIGHER" ? "#22c55e" : "#ef4444"};">${type}</div><div class="unchain-chip">#${item.contract_id || "—"}</div></div><div style="margin-top:8px;color:#cbd5e1;display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;"><div><span class="unchain-label">Stake</span><div>$${Number(item.stake || 0).toFixed(2)}</div></div><div><span class="unchain-label">Barrier</span><div>${item.barrier || "—"}</div></div><div><span class="unchain-label">Duration</span><div>${durationLabel}</div></div><div><span class="unchain-label">Symbol</span><div>${item.symbol || "—"}</div></div><div><span class="unchain-label">Open P/L</span><div style="color:${profitColor};font-weight:800;">${profit}</div></div></div></div>`;
    }).join("");
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
      subEl.innerText = basis;
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
    state.lastPayload = payload;
    const un = payload.unchain || payload;
    fillForm(un, !!(opts && opts.forceForm));
    renderStatusChip(un, payload);
    renderRiskBlock(un);
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
    renderBias(un);
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

  async function handleAction(action) {
    switch (action) {
      case "unchain-toggle-autosl":
        state.auto_sl = !state.auto_sl;
        applyAutoSlBtn();
        break;
      case "unchain-save-settings":
        await saveSettings(true);
        break;
      case "unchain-refresh":
        await refreshStatus(false);
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
      case "unchain-close-all":
        await closeAll();
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
      socket.on("unchain_status", (data) => {
        if (!isActive() || !data) return;
        renderPayload(data);
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
      });
      node.addEventListener("change", () => {
        markDirty(id);
        if (id === "unchainHigherStake") mirrorHigherStakeToLower();
      });
      node.addEventListener("keydown", (evt) => {
        if (evt.key === "Enter") {
          evt.preventDefault();
          saveSettings(true).catch(() => {});
        }
      });
    });
  }

  function bindUI(root) {
    const app = App();
    if (root && app.bindActionButtons) {
      app.bindActionButtons(root, async ({ action }) => {
        try {
          await handleAction(action);
        } catch (e) {
          toast("UNCHAIN action error", "error");
        }
      }, "unchain_action_clicks_v2");
    }
    bindFormInputs();
    applyAutoSlBtn();
  }

  function startPolling() {
    stopPolling();
    state.pollTimer = setInterval(() => {
      if (isActive()) refreshStatus(true);
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
