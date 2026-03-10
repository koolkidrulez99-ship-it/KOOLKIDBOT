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
    marketChart: { history: [], basePrice: null, lastPrice: null, lastSymbol: null, maxPoints: 72 },
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

  function getBarrierInputs(un) {
    const higher = num((un && un.higher_barrier) != null ? un.higher_barrier : readText("unchainHigherBarrier", "0.12"), 0.12);
    const lower = num((un && un.lower_barrier) != null ? un.lower_barrier : readText("unchainLowerBarrier", "-0.12"), -0.12);
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
    if (state.marketChart.history.length > state.marketChart.maxPoints) {
      state.marketChart.history = state.marketChart.history.slice(-state.marketChart.maxPoints);
      if (state.marketChart.history.length) {
        state.marketChart.basePrice = state.marketChart.history[0].price;
        state.marketChart.history = state.marketChart.history.map((point) => ({
          price: point.price,
          offset: point.price - state.marketChart.basePrice,
          t: point.t,
        }));
      }
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
    const offsets = history.map((p) => Number(p.offset || 0));
    const currentOffset = offsets[offsets.length - 1] || 0;
    const latestPrice = history[history.length - 1].price;
    const basePrice = state.marketChart.basePrice;
    const rangeMax = Math.max(0.18, ...offsets.map((v) => Math.abs(v)), Math.abs(higher), Math.abs(lower)) * 1.18;
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
    const zoneTopY = toY(topBarrier);
    const zoneBottomY = toY(bottomBarrier);
    const lineColor = currentOffset >= 0 ? "#38bdf8" : "#c084fc";
    const direction = offsets.length > 1 ? (offsets[offsets.length - 1] - offsets[Math.max(0, offsets.length - 2)]) : 0;

    let zoneText = "IN MIDDLE ZONE";
    let tone = "middle";
    if (currentOffset > topBarrier) { zoneText = "ABOVE HIGHER BARRIER"; tone = "above"; }
    else if (currentOffset < bottomBarrier) { zoneText = "BELOW LOWER BARRIER"; tone = "below"; }
    setBarrierZoneStatus(zoneText, tone);

    if (stats) {
      const widthValue = Math.abs(topBarrier - bottomBarrier);
      stats.innerText = `Base ${Number(basePrice).toFixed(2)} • Live ${Number(latestPrice).toFixed(2)} • Offset ${formatBarrierNumber(currentOffset)} • Middle zone ${widthValue.toFixed(2)} wide`;
    }
    if (meta) {
      meta.innerText = "The chart uses the first visible tick as the current base. Barrier lines are drawn from that same base so you can see when price is inside the middle zone or breaks out.";
    }

    const latestX = toX(history.length - 1);
    const latestY = toY(currentOffset);
    const areaPath = `${left},${bottom} ${polyline} ${right},${bottom}`;
    const arrow = direction >= 0 ? "▲" : "▼";

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
      <polygon points="${areaPath}" fill="url(#unchainLineFill)"></polygon>
      <polyline points="${polyline}" fill="none" stroke="${lineColor}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></polyline>
      <circle cx="${latestX.toFixed(1)}" cy="${latestY.toFixed(1)}" r="5.5" fill="${lineColor}" stroke="#e2e8f0" stroke-width="1.5"></circle>
      <text x="${left + 6}" y="${Math.max(16, higherY - 8).toFixed(1)}" fill="#86efac" font-size="11" font-weight="900">HIGHER ${escapeHtml(formatBarrierNumber(higher))}</text>
      <text x="${left + 6}" y="${Math.min(height - 10, lowerY - 8).toFixed(1)}" fill="#fca5a5" font-size="11" font-weight="900">LOWER ${escapeHtml(formatBarrierNumber(lower))}</text>
      <text x="${right - 6}" y="${Math.max(16, zoneTopY + 14).toFixed(1)}" text-anchor="end" fill="#fcd34d" font-size="11" font-weight="900">MIDDLE ZONE</text>
      <text x="${right - 6}" y="${Math.max(18, latestY - 10).toFixed(1)}" text-anchor="end" fill="#e2e8f0" font-size="11" font-weight="900">${arrow} ${escapeHtml(Number(latestPrice).toFixed(2))}</text>
    `;
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


  function renderAutoBoth(un) {
    const btn = el("unchainAutoBothBtn");
    const meta = el("unchainAutoBothMeta");
    if (!btn && !meta) return;
    const enabled = !!(un && un.auto_both_enabled);
    const status = String((un && un.auto_status) || (enabled ? "ARMED" : "OFF")).toUpperCase();
    const cooldown = Math.max(0, Number((un && un.auto_cooldown_remaining) || 0));

    if (btn) {
      const label = enabled ? `🤖 AUTO BOTH: ON • ${status}` : "🤖 AUTO BOTH: OFF";
      btn.innerText = label;
      btn.style.background = enabled ? "#06b6d4" : "#0ea5e9";
      btn.style.color = "#fff";
    }

    if (meta) {
      let text = "Auto Both repeats Higher + Lower together, waits for both to finish, then uses a 3s cooldown before the next pair.";
      if (enabled) {
        if (status === "RUNNING") {
          text = "AUTO BOTH is running. It is waiting for the current Higher + Lower pair to fully finish before the 3s cooldown starts.";
        } else if (status === "COOLDOWN") {
          text = `AUTO BOTH cooldown: ${cooldown.toFixed(1)}s remaining before the next Higher + Lower pair.`;
        } else if (status.startsWith("WAITING")) {
          const threshold = Number((un && un.auto_start_threshold) || 60);
          const bias = (un && un.bias) || {};
          const hp = Number(bias.higher_pct || 0);
          const lp = Number(bias.lower_pct || 0);
          text = `AUTO BOTH is armed but waiting for a good market. It will start only when Higher or Lower reaches ${threshold.toFixed(0)}% (now H ${hp.toFixed(1)}% / L ${lp.toFixed(1)}%).`;
        } else {
          text = "AUTO BOTH is armed and ready to send the next Higher + Lower pair using your saved UNCHAIN values.";
        }
      }
      meta.innerText = text;
    }
  }

  function renderActiveTrades(un) {
    const wrap = el("unchainActiveTrades");
    if (!wrap) return;
    const rawItems = Array.isArray(un && un.active_contracts) ? un.active_contracts : [];
    const items = rawItems.filter((item) => {
      if (!item || typeof item !== "object") return false;
      if (item.is_sold) return false;
      const status = String(item.status || "").toLowerCase();
      const contractStatus = String(item.contract_status || "").toLowerCase();
      return ![status, contractStatus].some((v) => ["sold", "won", "lost", "settled", "closed", "expired"].includes(v));
    });
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
    renderBias(un);
    renderBarrierMarketChart(un, payload);
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
      case "unchain-toggle-auto-both":
        await toggleAutoBoth();
        break;
      case "unchain-close-all":
        await closeAll();
        break;
      case "unchain-clear-active":
        await clearActive();
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
      });
      node.addEventListener("change", () => {
        markDirty(id);
        if (id === "unchainHigherStake") mirrorHigherStakeToLower();
        if (id === "unchainHigherBarrier" || id === "unchainLowerBarrier") renderBarrierMarketChart(state.lastPayload && (state.lastPayload.unchain || state.lastPayload) || {}, state.lastPayload || {});
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
