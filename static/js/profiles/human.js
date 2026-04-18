(function () {
  const PROFILE = "HUMAN";
  const POLL_INTERVAL_LABEL = "human_rf_status_poll";
  const STATUS_RENDER_THROTTLE_MS = 500;
  let pollTimer = null;
  let cachedStatus = null;
  let socketHooked = false;
  let pendingStatusPayload = null;
  let statusRenderTimer = null;
  let lastStatusRenderAt = 0;
  const fxState = { active: false, firing: false, lastToast: 0 };
  let humanRFAllowEqualsOn = false;
  let humanManualContracts = null;
  let humanManualContractsSymbol = "";
  let humanManualLoading = false;

  function getApp() {
    return window.BotApp || {};
  }

  function money(value, payload){
    const num = Number(value || 0);
    try{
      if(typeof formatCurrencyAmount === "function") return formatCurrencyAmount(num, payload || {});
    }catch(e){}
    return Number.isFinite(num) ? `$${Math.abs(num).toFixed(2)}` : "—";
  }

  function byId(id){ return document.getElementById(id); }
  function rootExists(){ return !!byId("humanRiseFallCard"); }
  function isActive(){
    try{
      if(typeof activeProfile !== "undefined") return String(activeProfile || "").toUpperCase() === PROFILE;
    }catch(e){}
    try{
      return String(window.activeProfile || "").toUpperCase() === PROFILE;
    }catch(e){}
    return rootExists();
  }

  function clampNum(v, min, max, fallback){
    let n = Number(v);
    if(!Number.isFinite(n)) return fallback;
    if(n < min) n = min;
    if(n > max) n = max;
    return n;
  }

  function setBtnState(btn, enabled, onText, offText, onColor, offColor){
    if(!btn) return;
    btn.textContent = enabled ? onText : offText;
    btn.style.background = enabled ? (onColor || "#22c55e") : (offColor || "#1e293b");
  }

  function setAutoToast(modeKey, enabled, label){
    const App = getApp();
    if(App && typeof App.setAutoScanningToast === "function"){
      App.setAutoScanningToast(PROFILE, modeKey, !!enabled, label);
    }
  }

  const HUMAN_MANUAL_BUTTONS = {
    HIGH_TICK: "humanHighTickBtn",
    LOW_TICK: "humanLowTickBtn",
    ONLY_UPS: "humanOnlyUpsBtn",
    ONLY_DOWNS: "humanOnlyDownsBtn",
  };
  const HUMAN_SPECIAL_LABELS = {
    HIGH_TICK: "High Tick",
    LOW_TICK: "Low Tick",
    ONLY_UPS: "Only Ups",
    ONLY_DOWNS: "Only Downs",
  };
  const HUMAN_SPECIAL_AUTO_STATE = {
    pair: "TICKS",
    firing: false,
    running: false,
    step: 0,
    pendingCount: 0,
    expectedCount: 0,
    settledCount: 0,
    cycleWon: false,
    stopRequested: false,
    restartTimer: null,
    contractActions: {},
    cycleContractActions: {},
    settledContracts: {},
    localOrderActions: [],
  };
  const HUMAN_SINGLE_MARTINGALE_STATE = {
    action: "ONLY_UPS",
    enabled: false,
    step: 1,
    inProgress: false,
    pendingAction: "",
    pendingContractId: "",
    pendingMartingale: false,
    pendingStake: 0,
    running: false,
    stopRequested: false,
    restartTimer: null,
    lastResult: "none",
    status: "Ready",
  };
  const HUMAN_RF_MARTINGALE_STATE = {
    direction: "RISE",
    enabled: false,
    step: 1,
    inProgress: false,
    pendingDirection: "",
    pendingContractId: "",
    pendingMartingale: false,
    pendingStake: 0,
    running: false,
    stopRequested: false,
    restartTimer: null,
    lastResult: "none",
    status: "Ready",
  };

  function setHumanManualNote(text, color){
    const note = byId("humanManualContractNote");
    if(!note) return;
    note.textContent = text || "";
    note.style.color = color || "#94a3b8";
  }

  function renderHumanManualContracts(data){
    const actions = (data && data.actions) || {};
    humanManualContracts = actions;
    humanManualContractsSymbol = (data && data.symbol) || humanManualContractsSymbol || "";
    let availableCount = 0;
    Object.keys(HUMAN_MANUAL_BUTTONS).forEach((key) => {
      const btn = byId(HUMAN_MANUAL_BUTTONS[key]);
      if(!btn) return;
      const item = actions[key] || {};
      const available = !!item.available;
      if(available) availableCount += 1;
      btn.disabled = humanManualLoading || !available;
      btn.style.opacity = available ? "1" : "0.45";
      btn.title = available ? `${item.contract_type || item.contract_display || "Available"}` : "This contract is not available for the selected market.";
    });

    const onlyUps = actions.ONLY_UPS || actions.ONLY_DOWNS || {};
    const durEl = byId("humanOnlyDuration");
    if(durEl && (onlyUps.min_duration || onlyUps.default_duration)){
      const minDur = Math.max(1, Number(onlyUps.min_duration || 2));
      const defaultDur = Math.max(minDur, Number(onlyUps.default_duration || 2));
      durEl.min = String(minDur);
      if(!durEl.value || Number(durEl.value) < minDur) durEl.value = String(defaultDur);
      if(onlyUps.max_duration) durEl.max = String(onlyUps.max_duration);
    }

    if(humanManualLoading){
      setHumanManualNote("Checking contract availability for this market...", "#94a3b8");
    }else if(availableCount > 0){
      setHumanManualNote(`Available on ${humanManualContractsSymbol || "selected market"}: ${availableCount}/4 actions`, "#86efac");
    }else{
      setHumanManualNote("These contracts are not available for the selected market.", "#fca5a5");
    }
    updateHumanSingleMartingalePanel();
    updateHumanSpecialPopup();
  }

  async function refreshHumanManualContracts(force){
    if(!rootExists()) return;
    humanManualLoading = true;
    renderHumanManualContracts({ actions: humanManualContracts || {}, symbol: humanManualContractsSymbol });
    try{
      const suffix = force ? "?refresh=1" : "";
      const res = await fetch(`/human_manual_contracts${suffix}`, { cache: "no-store" });
      let data = {};
      try{ data = await res.json(); }catch(e){}
      if(!res.ok) throw new Error(data.error || data.message || "Contract discovery failed");
      humanManualLoading = false;
      renderHumanManualContracts(data);
      return data;
    }catch(e){
      humanManualLoading = false;
      humanManualContracts = {};
      renderHumanManualContracts({ actions: {}, symbol: humanManualContractsSymbol });
      setHumanManualNote(e.message || "Could not check contract availability.", "#fca5a5");
      return null;
    }
  }

  function guardMartha(action, proceed){
    if(window.MarthaAI && typeof window.MarthaAI.guardAction === "function"){
      return window.MarthaAI.guardAction(action || {}, proceed);
    }
    return proceed();
  }
  function isMarthaBlocked(result){
    return !!(result && (result.status === "blocked" || (result.data && result.data.status === "blocked")));
  }

  function prettySignalStyles(signalEl, signalState, tradeDirection){
    if(!signalEl) return;
    const state = (signalState || "WAIT").toUpperCase();
    const dir = (tradeDirection || "").toUpperCase();
    const text = (dir && state !== "WAIT") ? `${state} - ${dir}` : state;
    signalEl.textContent = text;

    signalEl.style.color = "#e5e7eb";
    signalEl.style.borderColor = "#334155";
    signalEl.style.background = "#111827";

    if(state === "TAKE NOW"){
      const isRise = dir === "RISE";
      signalEl.style.color = isRise ? "#22c55e" : (dir === "FALL" ? "#ef4444" : "#38bdf8");
      signalEl.style.borderColor = isRise ? "rgba(34,197,94,0.35)" : (dir === "FALL" ? "rgba(239,68,68,0.35)" : "rgba(56,189,248,0.35)");
      signalEl.style.background = isRise ? "rgba(34,197,94,0.10)" : (dir === "FALL" ? "rgba(239,68,68,0.10)" : "rgba(56,189,248,0.10)");
    }else if(state === "READY"){
      signalEl.style.color = "#38bdf8";
      signalEl.style.borderColor = "rgba(56,189,248,0.28)";
      signalEl.style.background = "rgba(56,189,248,0.08)";
    }else if(state === "LATE"){
      signalEl.style.color = "#f59e0b";
      signalEl.style.borderColor = "rgba(245,158,11,0.28)";
      signalEl.style.background = "rgba(245,158,11,0.08)";
    }else{
      signalEl.style.color = "#facc15";
      signalEl.style.borderColor = "rgba(250,204,21,0.25)";
      signalEl.style.background = "rgba(250,204,21,0.06)";
    }
  }

  function formatHumanChartPrice(value){
    const num = Number(value);
    if(!Number.isFinite(num)) return "--";
    const abs = Math.abs(num);
    if(abs >= 1000) return num.toFixed(2);
    if(abs >= 100) return num.toFixed(3);
    if(abs >= 1) return num.toFixed(4);
    return num.toFixed(5);
  }

  function drawHumanLiteDirectionChart(data){
    const chart = data && data.chart ? data.chart : {};
    const prices = Array.isArray(chart.prices)
      ? chart.prices.map((v) => Number(v)).filter((v) => Number.isFinite(v))
      : [];
    const canvas = byId("humanLiteDirectionChart");
    const badge = byId("humanLiteChartBadge");
    const subtitle = byId("humanLiteChartSubtitle");
    const priceEl = byId("humanLiteChartPrice");
    const moveEl = byId("humanLiteChartMove");
    const ticksEl = byId("humanLiteChartTicks");
    if(!canvas) return;

    const latest = prices.length ? prices[prices.length - 1] : Number(chart.last_price);
    const previous = prices.length > 1 ? prices[prices.length - 2] : latest;
    const first = prices.length > 1 ? prices[0] : previous;
    const tickCount = Number(chart.tick_count || data.tick_count || prices.length || 0);
    const lastMove = Number(latest) - Number(previous);
    const windowMove = Number(latest) - Number(first);
    const direction = lastMove > 0 ? "up" : (lastMove < 0 ? "down" : "flat");
    const color = direction === "up" ? "#22c55e" : (direction === "down" ? "#ef4444" : "#38bdf8");
    const label = direction === "up" ? "MOVING UP" : (direction === "down" ? "MOVING DOWN" : "FLAT");

    if(badge){
      badge.textContent = prices.length >= 2 ? label : "WAITING";
      badge.style.background = prices.length >= 2 ? `${color}22` : "#1e293b";
      badge.style.color = prices.length >= 2 ? color : "#cbd5e1";
      badge.style.border = prices.length >= 2 ? `1px solid ${color}55` : "1px solid #334155";
    }
    if(subtitle){
      subtitle.textContent = prices.length >= 2
        ? `Last ${Math.min(prices.length, 80)} ticks from the selected Human market.`
        : "Waiting for Human market ticks...";
    }
    if(priceEl) priceEl.textContent = formatHumanChartPrice(latest);
    if(moveEl){
      const sign = windowMove > 0 ? "+" : "";
      moveEl.textContent = prices.length >= 2 ? `${sign}${formatHumanChartPrice(windowMove)}` : "--";
      moveEl.style.color = windowMove > 0 ? "#22c55e" : (windowMove < 0 ? "#ef4444" : "#cbd5e1");
    }
    if(ticksEl) ticksEl.textContent = String(Number.isFinite(tickCount) ? Math.floor(tickCount) : prices.length);

    const rect = canvas.getBoundingClientRect();
    const width = Math.max(260, Math.floor(rect.width || canvas.clientWidth || 600));
    const height = Math.max(140, Math.floor(rect.height || canvas.clientHeight || 170));
    const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
    if(canvas.width !== Math.floor(width * dpr) || canvas.height !== Math.floor(height * dpr)){
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
    }
    const ctx = canvas.getContext("2d");
    if(!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const gradient = ctx.createLinearGradient(0, 0, width, height);
    gradient.addColorStop(0, "rgba(15, 23, 42, 0.95)");
    gradient.addColorStop(1, "rgba(2, 6, 23, 0.95)");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, width, height);

    ctx.strokeStyle = "rgba(148, 163, 184, 0.12)";
    ctx.lineWidth = 1;
    for(let i = 1; i <= 3; i += 1){
      const y = (height / 4) * i;
      ctx.beginPath();
      ctx.moveTo(12, y);
      ctx.lineTo(width - 12, y);
      ctx.stroke();
    }

    if(prices.length < 2){
      ctx.fillStyle = "#64748b";
      ctx.font = "700 13px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("Collecting Human market ticks...", width / 2, height / 2);
      return;
    }

    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const span = Math.max(max - min, Math.abs(max) * 0.000001, 0.000001);
    const padX = 14;
    const padY = 18;
    const chartW = width - (padX * 2);
    const chartH = height - (padY * 2);
    const points = prices.map((price, idx) => {
      const x = padX + ((prices.length === 1 ? 0 : idx / (prices.length - 1)) * chartW);
      const y = padY + ((max - price) / span) * chartH;
      return { x, y };
    });

    ctx.beginPath();
    points.forEach((point, idx) => {
      if(idx === 0) ctx.moveTo(point.x, point.y);
      else ctx.lineTo(point.x, point.y);
    });
    ctx.lineTo(points[points.length - 1].x, height - padY);
    ctx.lineTo(points[0].x, height - padY);
    ctx.closePath();
    const fill = ctx.createLinearGradient(0, padY, 0, height - padY);
    fill.addColorStop(0, `${color}30`);
    fill.addColorStop(1, "rgba(2, 6, 23, 0)");
    ctx.fillStyle = fill;
    ctx.fill();

    ctx.beginPath();
    points.forEach((point, idx) => {
      if(idx === 0) ctx.moveTo(point.x, point.y);
      else ctx.lineTo(point.x, point.y);
    });
    ctx.strokeStyle = color;
    ctx.lineWidth = 2.5;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.stroke();

    const last = points[points.length - 1];
    ctx.beginPath();
    ctx.arc(last.x, last.y, 4, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
  }

  function renderHumanRFStatus(data){
    lastStatusRenderAt = Date.now();
    if(!data || !rootExists()) return;
    cachedStatus = data;
    drawHumanLiteDirectionChart(data);

    const bias = (data.bias || "NEUTRAL").toUpperCase();
    const signal = (data.signal || "WAIT").toUpperCase();
    const tradeDirection = (data.trade_direction || "").toUpperCase();
    const confidence = Number(data.confidence || 0);
    const reason = data.reason || "Waiting...";
    const cooldown = Number(data.cooldown_sec || 0);
    const edgeGap = Number(data.edge_gap || 0);
    const flags = data.flags || {};
    const settings = data.settings || {};
    const comps = data.components || {};
    const streaks = data.streaks || {};

    const biasEl = byId("humanRfBias");
    if(biasEl){
      biasEl.textContent = bias;
      biasEl.style.color = bias === "BULLISH" ? "#22c55e" : (bias === "BEARISH" ? "#ef4444" : "#facc15");
    }

    const confEl = byId("humanRfConfidence");
    if(confEl) confEl.textContent = `${confidence.toFixed(1)}%`;

    prettySignalStyles(byId("humanRfSignal"), signal, tradeDirection);

    const reasonEl = byId("humanRfReason");
    if(reasonEl){
      const prefix = (tradeDirection && signal !== "WAIT") ? `${tradeDirection}: ` : "";
      reasonEl.textContent = `${prefix}${reason}`;
    }

    const cdEl = byId("humanRfCooldown");
    if(cdEl) cdEl.textContent = `Cooldown: ${cooldown.toFixed(1)}s`;

    const edgeEl = byId("humanRfEdgeGap");
    if(edgeEl) edgeEl.textContent = `Edge Gap: ${edgeGap.toFixed(1)}`;

    const marketStateEl = byId("humanRfMarketState");
    if(marketStateEl){
      let stateText = "Watching";
      if(flags.choppy) stateText = "Choppy";
      else if(signal === "READY") stateText = "Setup Forming";
      else if(signal === "TAKE NOW") stateText = "Entry Window";
      else if(signal === "LATE") stateText = "Late Window";
      else if(signal === "WAIT") stateText = "Watching";
      marketStateEl.textContent = `Market: ${stateText}`;
      marketStateEl.style.background = flags.choppy ? "rgba(239,68,68,0.12)" : (signal === "TAKE NOW" ? "rgba(34,197,94,0.12)" : (signal === "READY" ? "rgba(56,189,248,0.10)" : (signal === "LATE" ? "rgba(245,158,11,0.10)" : "rgba(30,41,59,1)")));
    }

    const streakEl = byId("humanRfStreaks");
    if(streakEl){
      streakEl.textContent = `Wins: ${streaks.wins || 0} | Losses: ${streaks.losses || 0} | Last: ${streaks.last_result || "-"}`;
    }

    if(byId("humanRfScoreTrend")) byId("humanRfScoreTrend").textContent = comps.trend ?? 0;
    if(byId("humanRfScoreMomentum")) byId("humanRfScoreMomentum").textContent = comps.momentum ?? 0;
    if(byId("humanRfScorePullback")) byId("humanRfScorePullback").textContent = comps.pullback ?? 0;
    if(byId("humanRfScoreTrigger")) byId("humanRfScoreTrigger").textContent = comps.trigger ?? 0;
    if(byId("humanRfScoreClean")) byId("humanRfScoreClean").textContent = comps.cleanliness ?? 0;

    const durEl = byId("humanRfDuration");
    if(durEl && settings.duration_ticks != null && String(durEl.value) !== String(settings.duration_ticks)){
      if(document.activeElement !== durEl){
        durEl.value = String(settings.duration_ticks);
      }
    }
    const thEl = byId("humanRfThreshold");
    if(thEl && settings.conf_threshold != null && String(thEl.value) !== String(Math.round(Number(settings.conf_threshold)))){
      thEl.value = String(Math.round(Number(settings.conf_threshold)));
    }

    setBtnState(byId("humanRfSmartBtn"), !!settings.smart_assist, "Smart Assist: ON", "Smart Assist: OFF", "#22c55e", "#334155");
    setBtnState(byId("humanRfAutoBtn"), !!settings.auto_assist, "Take Auto Trades: ON", "Take Auto Trades: OFF", "#38bdf8", "#334155");
    setBtnState(byId("humanRfBiasLockBtn"), !!settings.bias_lock, "Bias Lock: ON", "Bias Lock: OFF", "#a855f7", "#334155");
    setBtnState(byId("humanRfNoTradeBtn"), !!settings.no_trade_filter, "No-Trade Filter: ON", "No-Trade Filter: OFF", "#f59e0b", "#334155");
    setBtnState(byId("humanRfAdaptiveBtn"), !!settings.adaptive_cooldown, "Adaptive Cooldown: ON", "Adaptive Cooldown: OFF", "#14b8a6", "#334155");
    setAutoToast("human_rf_auto", !!settings.auto_assist, "HUMAN Rise/Fall Auto");
  }

  async function fetchHumanRFStatus(){
    if(!rootExists()) return;
    try{
      const res = await fetch("/human_rf_status");
      if(!res.ok) return;
      const data = await res.json();
      renderHumanRFStatus(data);
      maybeAutoFormulaX();
    }catch(e){
      // silent
    }
  }

  async function postJSON(url, body){
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {})
    });
    let data = {};
    try { data = await res.json(); } catch(e) {}
    if(!res.ok && data && data.error) throw new Error(data.error);
    if(!res.ok && data && data.message) throw new Error(data.message);
    if(!res.ok) throw new Error("Request failed");
    return data;
  }

  async function saveHumanRFSettings(){
    const durEl = byId("humanRfDuration");
    const thEl = byId("humanRfThreshold");
    const durationTicks = durEl ? clampNum(durEl.value || 5, 1, 10, 5) : 5;
    const confThreshold = thEl ? clampNum(thEl.value || 70, 1, 100, 70) : 70;
    if(durEl) durEl.value = String(durationTicks);
    if(thEl) thEl.value = String(Math.round(confThreshold));
    const body = {
      duration_ticks: durationTicks,
      conf_threshold: confThreshold
    };
    if(cachedStatus && cachedStatus.settings){
      body.smart_assist = !!cachedStatus.settings.smart_assist;
      body.auto_assist = !!cachedStatus.settings.auto_assist;
      body.bias_lock = !!cachedStatus.settings.bias_lock;
      body.no_trade_filter = !!cachedStatus.settings.no_trade_filter;
      body.adaptive_cooldown = !!cachedStatus.settings.adaptive_cooldown;
    }
    try{
      const data = await postJSON("/human_rf_settings", body);
      if(data && data.rise_fall) renderHumanRFStatus(data.rise_fall);
      if(typeof showToast === "function") showToast("🧠 HUMAN Rise/Fall settings saved", "success");
    }catch(e){
      if(typeof showToast === "function") showToast(e.message || "Failed to save Human RF settings", "error");
    }
  }

  async function toggleHumanRFSetting(key){
    const current = !!(cachedStatus && cachedStatus.settings && cachedStatus.settings[key]);
    const durEl = byId("humanRfDuration");
    const thEl = byId("humanRfThreshold");
    const durationTicks = durEl ? clampNum(durEl.value || 5, 1, 10, 5) : 5;
    const confThreshold = thEl ? clampNum(thEl.value || 70, 1, 100, 70) : 70;
    if(durEl) durEl.value = String(durationTicks);
    if(thEl) thEl.value = String(Math.round(confThreshold));
    const body = {
      duration_ticks: durationTicks,
      conf_threshold: confThreshold
    };
    if(cachedStatus && cachedStatus.settings){
      body.smart_assist = !!cachedStatus.settings.smart_assist;
      body.auto_assist = !!cachedStatus.settings.auto_assist;
      body.bias_lock = !!cachedStatus.settings.bias_lock;
      body.no_trade_filter = !!cachedStatus.settings.no_trade_filter;
      body.adaptive_cooldown = !!cachedStatus.settings.adaptive_cooldown;
    }
    body[key] = !current;
    try{
      const data = await postJSON("/human_rf_settings", body);
      if(data && data.rise_fall) renderHumanRFStatus(data.rise_fall);
      if(typeof showToast === "function"){
        const label = key.replaceAll("_"," ");
        showToast(`${label}: ${(!current) ? "ON" : "OFF"}`, (!current) ? "success" : "warn");
      }
    }catch(e){
      if(typeof showToast === "function") showToast(e.message || "Toggle failed", "error");
    }
  }

  async function humanRFTrade(direction){
    try{
      const stakeEl = byId("stake");
      const durEl = byId("humanRfDuration");
      const stakeVal = stakeEl ? clampNum(stakeEl.value || 1, 0.35, 1000000, 1) : 1;
      const durationTicks = durEl ? clampNum(durEl.value || 5, 1, 10, 5) : 5;
      if(stakeEl) stakeEl.value = String(stakeVal);
      if(durEl) durEl.value = String(durationTicks);
      const payload = {
        direction: direction || "AUTO",
        stake: stakeVal,
        duration_ticks: durationTicks
      };
      const data = await guardMartha({
        profile: PROFILE,
        source: "human_rf_trade",
        type: payload.direction,
        label: `HUMAN ${payload.direction}`,
        stake: stakeVal,
        duration: durationTicks,
        duration_unit: "t",
        batch_count: 1,
      }, ()=>postJSON("/human_rf_trade", payload));
      if(isMarthaBlocked(data)) return;
      if(typeof showToast === "function"){
        const d = (data && data.signal && data.signal.direction) ? data.signal.direction : (direction || "AUTO");
        showToast(`HUMAN ${d} trade sent`, "success");
      }
      await fetchHumanRFStatus();
    }catch(e){
      if(typeof showToast === "function") showToast(e.message || "No valid setup", "error");
    }
  }

  function syncHumanRFAllowEqualsToggle(){
    const btn = byId("humanRfAllowEqualsToggle");
    if(!btn) return;
    btn.textContent = humanRFAllowEqualsOn ? "Allow Equals: ON" : "Allow Equals: OFF";
    btn.setAttribute("aria-pressed", humanRFAllowEqualsOn ? "true" : "false");
    btn.style.background = humanRFAllowEqualsOn ? "#22c55e" : "#1e293b";
    btn.style.color = humanRFAllowEqualsOn ? "#052e16" : "#e5e7eb";
    btn.style.borderColor = humanRFAllowEqualsOn ? "#86efac" : "#334155";
  }

  function toggleHumanRFAllowEquals(){
    humanRFAllowEqualsOn = !humanRFAllowEqualsOn;
    syncHumanRFAllowEqualsToggle();
  }

  function readHumanRFAllowEquals(){
    return !!humanRFAllowEqualsOn;
  }

  async function humanAutoRiseFall(){
    try{
      const stakeEl = byId("stake");
      const durEl = byId("humanRfDuration");
      const stakeVal = stakeEl ? clampNum(stakeEl.value || 1, 0.35, 1000000, 1) : 1;
      const durationTicks = durEl ? clampNum(durEl.value || 5, 1, 10, 5) : 5;
      if(stakeEl) stakeEl.value = String(stakeVal);
      if(durEl) durEl.value = String(durationTicks);
      const allowEquals = readHumanRFAllowEquals();
      const payload = {
        rise_stake: stakeVal,
        fall_stake: stakeVal,
        duration_ticks: durationTicks
      };
      if(allowEquals) payload.allow_equals = true;
      const data = await guardMartha({
        profile: PROFILE,
        source: "human_auto_rise_fall",
        type: "AUTO_RISE_FALL",
        label: "HUMAN AUTO RISE & FALL",
        stake: stakeVal,
        duration: durationTicks,
        duration_unit: "t",
        batch_count: 2,
      }, ()=>postJSON("/human_auto_rise_fall", payload));
      if(isMarthaBlocked(data)) return;
      if(typeof showToast === "function"){
        const ok = data && data.status === "success";
        showToast(`AUTO RISE & FALL sent RISE ${money(stakeVal)} + FALL ${money(stakeVal)}${allowEquals ? " with Allow Equals" : ""}`, ok ? "success" : "warn");
      }
      await fetchHumanRFStatus();
    }catch(e){
      if(typeof showToast === "function") showToast(e.message || "AUTO RISE & FALL failed", "error");
    }
  }

  function readHumanManualPayload(action, options){
    const opts = options || {};
    const key = String(action || "").toUpperCase();
    const stakeEl = byId("stake");
    const selectedTickEl = byId("humanSelectedTick");
    const durationEl = byId("humanOnlyDuration");
    const stakeSource = opts.stake !== undefined ? opts.stake : (stakeEl ? stakeEl.value : 1);
    const stakeVal = clampNum(stakeSource || 1, 0.35, 1000000, 1);
    if(stakeEl && opts.stake === undefined) stakeEl.value = String(stakeVal);

    const payload = { action: key, stake: stakeVal };
    if(key === "HIGH_TICK" || key === "LOW_TICK"){
      const selectedTickSource = opts.selected_tick !== undefined ? opts.selected_tick : (selectedTickEl ? selectedTickEl.value : 5);
      const selectedTick = Math.round(clampNum(selectedTickSource || 5, 1, 5, 5));
      if(selectedTickEl && opts.selected_tick === undefined) selectedTickEl.value = String(selectedTick);
      payload.selected_tick = selectedTick;
    }else{
      const minDur = durationEl ? Number(durationEl.min || 2) : 2;
      const maxDur = durationEl && durationEl.max ? Number(durationEl.max) : 1000000;
      const durationSource = opts.duration_ticks !== undefined ? opts.duration_ticks : (durationEl ? durationEl.value : 2);
      const durationTicks = Math.round(clampNum(durationSource || 2, minDur, maxDur, Math.max(2, minDur)));
      if(durationEl && opts.duration_ticks === undefined) durationEl.value = String(durationTicks);
      payload.duration_ticks = durationTicks;
    }
    return payload;
  }

  async function placeHumanManualAction(action, options){
    const opts = options || {};
    const key = String(action || "").toUpperCase();
    if(!humanManualContracts || !humanManualContracts[key]){
      await refreshHumanManualContracts(false);
    }
    const actionInfo = (humanManualContracts || {})[key] || {};
    if(!actionInfo.available){
      throw new Error("This contract is not available for the selected market.");
    }
    const payload = readHumanManualPayload(key, opts);
    const actionLabel = actionInfo.label || HUMAN_SPECIAL_LABELS[key] || key.replaceAll("_", " ");
    const data = await guardMartha({
      profile: PROFILE,
      source: "human_manual_contract",
      type: actionLabel,
      label: `HUMAN ${actionLabel}`,
      stake: payload.stake,
      duration: payload.duration_ticks || 5,
      duration_unit: "t",
      batch_count: 1,
    }, ()=>postJSON("/human_manual_trade", payload));
    if(isMarthaBlocked(data)) return data;
    if(!opts.quiet && typeof showToast === "function") showToast(`HUMAN ${actionLabel} trade sent`, "success");
    await fetchHumanRFStatus();
    return data;
  }

  async function humanManualTrade(action){
    try{
      await placeHumanManualAction(action);
    }catch(e){
      if(typeof showToast === "function") showToast(e.message || "HUMAN trade failed", "error");
    }
  }

  function isHumanTickPickAction(action){
    const key = String(action || "").toUpperCase();
    return key === "HIGH_TICK" || key === "LOW_TICK";
  }

  function readHumanSingleMartingaleNumber(id, fallback, min, max){
    const el = byId(id);
    const raw = el ? String(el.value || "").trim() : "";
    let value = raw === "" ? fallback : Number(raw);
    if(!Number.isFinite(value)) value = fallback;
    if(Number.isFinite(min)) value = Math.max(min, value);
    if(Number.isFinite(max)) value = Math.min(max, value);
    return value;
  }

  function readHumanSingleMartingaleSettings(){
    const actionEl = byId("humanMartingaleAction");
    const action = normalizeHumanSpecialAction(actionEl ? actionEl.value : HUMAN_SINGLE_MARTINGALE_STATE.action) || "ONLY_UPS";
    const startStake = Number(readHumanSingleMartingaleNumber("humanMartingaleStartStake", 0.35, 0.35, 1000000).toFixed(2));
    const modeEl = byId("humanMartingaleMode");
    const mode = String((modeEl && modeEl.value) || "STEP_005").toUpperCase() === "MULTIPLIER" ? "MULTIPLIER" : "STEP_005";
    const stepAmount = Number(readHumanSingleMartingaleNumber("humanMartingaleStepAmount", 0.05, 0.01, 1000000).toFixed(2));
    const multiplier = Math.max(1, readHumanSingleMartingaleNumber("humanMartingaleMultiplier", 2, 1, 100));
    const maxSteps = Math.max(1, Math.floor(readHumanSingleMartingaleNumber("humanMartingaleMaxSteps", 1000, 1, 1000000)));
    const capRaw = byId("humanMartingaleMaxStake");
    const maxStakeValue = capRaw && String(capRaw.value || "").trim() !== ""
      ? Math.max(0.35, Number(capRaw.value))
      : null;
    const maxStake = Number.isFinite(maxStakeValue) ? Number(maxStakeValue.toFixed(2)) : null;
    const option = {};
    if(isHumanTickPickAction(action)){
      const selectedTick = Math.round(readHumanSingleMartingaleNumber("humanMartingaleSelectedTick", 5, 1, 5));
      option.selected_tick = selectedTick;
      const selectedTickEl = byId("humanMartingaleSelectedTick");
      if(selectedTickEl) selectedTickEl.value = String(selectedTick);
    }else{
      const durationEl = byId("humanMartingaleDuration");
      const minDuration = Math.max(2, Number(durationEl && durationEl.min) || 2);
      const maxDuration = durationEl && durationEl.max ? Number(durationEl.max) : 1000000;
      const durationTicks = Math.round(readHumanSingleMartingaleNumber("humanMartingaleDuration", 2, minDuration, maxDuration));
      option.duration_ticks = durationTicks;
      if(durationEl) durationEl.value = String(durationTicks);
    }
    if(modeEl) modeEl.value = mode;
    return { action, startStake, mode, stepAmount, multiplier, maxSteps, maxStake, option };
  }

  function humanSingleMartingaleStakeForStep(stepValue){
    const settings = readHumanSingleMartingaleSettings();
    const maxSteps = settings.maxSteps;
    const step = Math.max(1, Math.min(maxSteps, Math.floor(Number(stepValue || HUMAN_SINGLE_MARTINGALE_STATE.step) || 1)));
    let stake = settings.mode === "STEP_005"
      ? settings.startStake + ((step - 1) * settings.stepAmount)
      : settings.startStake * Math.pow(settings.multiplier, step - 1);
    if(settings.maxStake !== null) stake = Math.min(stake, settings.maxStake);
    return Number(Math.max(0.35, stake).toFixed(2));
  }

  function updateHumanSingleMartingalePanel(){
    const settings = readHumanSingleMartingaleSettings();
    HUMAN_SINGLE_MARTINGALE_STATE.action = settings.action;
    const isTick = isHumanTickPickAction(settings.action);
    const durationWrap = byId("humanMartingaleDurationWrap");
    const tickWrap = byId("humanMartingaleSelectedTickWrap");
    if(durationWrap) durationWrap.style.display = isTick ? "none" : "grid";
    if(tickWrap) tickWrap.style.display = isTick ? "grid" : "none";

    const actionInfo = (humanManualContracts || {})[settings.action] || {};
    const available = !!actionInfo.available;
    const actionEl = byId("humanMartingaleAction");
    if(actionEl){
      Array.from(actionEl.options || []).forEach((option) => {
        const key = normalizeHumanSpecialAction(option.value);
        const info = (humanManualContracts || {})[key] || {};
        option.disabled = !!humanManualContracts && !info.available;
      });
    }
    const durationEl = byId("humanMartingaleDuration");
    if(durationEl && !isTick){
      const minDur = Math.max(2, Number(actionInfo.min_duration || 2));
      durationEl.min = String(minDur);
      if(actionInfo.max_duration) durationEl.max = String(actionInfo.max_duration);
      if(!durationEl.value || Number(durationEl.value) < minDur) durationEl.value = String(Math.max(minDur, Number(actionInfo.default_duration || 2)));
    }

    const toggleBtn = byId("humanMartingaleToggleBtn");
    if(toggleBtn){
      toggleBtn.textContent = `MARTINGALE: ${HUMAN_SINGLE_MARTINGALE_STATE.enabled ? "ON" : "OFF"}`;
      toggleBtn.style.background = HUMAN_SINGLE_MARTINGALE_STATE.enabled ? "#f59e0b" : "#334155";
      toggleBtn.style.color = HUMAN_SINGLE_MARTINGALE_STATE.enabled ? "#111827" : "#f8fafc";
    }
    const placeBtn = byId("humanMartingalePlaceBtn");
    if(placeBtn){
      placeBtn.disabled = humanManualLoading || !available || HUMAN_SINGLE_MARTINGALE_STATE.inProgress || HUMAN_SINGLE_MARTINGALE_STATE.running;
      placeBtn.style.opacity = placeBtn.disabled ? "0.55" : "1";
      placeBtn.style.cursor = placeBtn.disabled ? "not-allowed" : "pointer";
    }
    const stopBtn = byId("humanMartingaleQuickStopBtn");
    if(stopBtn){
      const canStop = HUMAN_SINGLE_MARTINGALE_STATE.running || HUMAN_SINGLE_MARTINGALE_STATE.inProgress;
      stopBtn.disabled = !canStop;
      stopBtn.style.opacity = canStop ? "1" : "0.55";
      stopBtn.style.cursor = canStop ? "pointer" : "not-allowed";
    }
    const note = byId("humanMartingaleAvailabilityNote");
    if(note){
      if(humanManualLoading){
        note.textContent = "Checking contract availability for this market...";
        note.style.color = "#94a3b8";
      }else if(available){
        note.textContent = `${HUMAN_SPECIAL_LABELS[settings.action]} is available on ${humanManualContractsSymbol || "selected market"}.`;
        note.style.color = "#86efac";
      }else{
        note.textContent = "This contract is not available for the selected market.";
        note.style.color = "#fca5a5";
      }
    }
    const status = byId("humanMartingaleStatus");
    if(status){
      const currentStake = humanSingleMartingaleStakeForStep();
      const nextStep = Math.min(settings.maxSteps, HUMAN_SINGLE_MARTINGALE_STATE.step + 1);
      const nextStake = HUMAN_SINGLE_MARTINGALE_STATE.enabled ? humanSingleMartingaleStakeForStep(nextStep) : settings.startStake;
      const modeLabel = settings.mode === "STEP_005" ? `$${settings.stepAmount.toFixed(2)} step` : `${settings.multiplier}x`;
      status.textContent = `${HUMAN_SINGLE_MARTINGALE_STATE.status}. ${modeLabel} • Step ${HUMAN_SINGLE_MARTINGALE_STATE.step} • Current stake $${currentStake.toFixed(2)} • Next stake $${nextStake.toFixed(2)} • Last result: ${HUMAN_SINGLE_MARTINGALE_STATE.lastResult}`;
      status.style.color = HUMAN_SINGLE_MARTINGALE_STATE.inProgress ? "#fbbf24" : (available ? "#94a3b8" : "#fca5a5");
    }
  }

  function setHumanSingleMartingaleAction(action){
    HUMAN_SINGLE_MARTINGALE_STATE.action = normalizeHumanSpecialAction(action) || "ONLY_UPS";
    HUMAN_SINGLE_MARTINGALE_STATE.status = "Ready";
    updateHumanSingleMartingalePanel();
  }

  function toggleHumanSingleMartingale(){
    HUMAN_SINGLE_MARTINGALE_STATE.enabled = !HUMAN_SINGLE_MARTINGALE_STATE.enabled;
    if(HUMAN_SINGLE_MARTINGALE_STATE.enabled){
      HUMAN_SINGLE_MARTINGALE_STATE.step = 1;
      HUMAN_SINGLE_MARTINGALE_STATE.status = "Ready";
      HUMAN_SINGLE_MARTINGALE_STATE.lastResult = "none";
    }else{
      quickStopHumanSingleMartingale("Martingale stopped.");
      return;
    }
    updateHumanSingleMartingalePanel();
  }

  function clearHumanSingleMartingalePending(){
    HUMAN_SINGLE_MARTINGALE_STATE.inProgress = false;
    HUMAN_SINGLE_MARTINGALE_STATE.pendingAction = "";
    HUMAN_SINGLE_MARTINGALE_STATE.pendingContractId = "";
    HUMAN_SINGLE_MARTINGALE_STATE.pendingMartingale = false;
    HUMAN_SINGLE_MARTINGALE_STATE.pendingStake = 0;
  }

  function quickStopHumanSingleMartingale(reason){
    if(HUMAN_SINGLE_MARTINGALE_STATE.restartTimer){
      clearTimeout(HUMAN_SINGLE_MARTINGALE_STATE.restartTimer);
      HUMAN_SINGLE_MARTINGALE_STATE.restartTimer = null;
    }
    HUMAN_SINGLE_MARTINGALE_STATE.running = false;
    HUMAN_SINGLE_MARTINGALE_STATE.stopRequested = true;
    HUMAN_SINGLE_MARTINGALE_STATE.enabled = false;
    clearHumanSingleMartingalePending();
    HUMAN_SINGLE_MARTINGALE_STATE.status = reason || "Stopped";
    updateHumanSingleMartingalePanel();
  }

  async function placeHumanSingleMartingaleTrade(options){
    const opts = options || {};
    if(HUMAN_SINGLE_MARTINGALE_STATE.inProgress) return;
    const settings = readHumanSingleMartingaleSettings();
    if(!humanManualContracts || !humanManualContracts[settings.action]){
      await refreshHumanManualContracts(false);
    }
    const actionInfo = (humanManualContracts || {})[settings.action] || {};
    if(!actionInfo.available){
      if(typeof showToast === "function") showToast("This contract is not available for the selected market.", "error");
      updateHumanSingleMartingalePanel();
      return;
    }
    const stake = HUMAN_SINGLE_MARTINGALE_STATE.enabled ? humanSingleMartingaleStakeForStep() : settings.startStake;
    if(HUMAN_SINGLE_MARTINGALE_STATE.enabled && !opts.continuation){
      HUMAN_SINGLE_MARTINGALE_STATE.running = true;
      HUMAN_SINGLE_MARTINGALE_STATE.stopRequested = false;
    }
    HUMAN_SINGLE_MARTINGALE_STATE.inProgress = true;
    HUMAN_SINGLE_MARTINGALE_STATE.pendingAction = settings.action;
    HUMAN_SINGLE_MARTINGALE_STATE.pendingContractId = "";
    HUMAN_SINGLE_MARTINGALE_STATE.pendingMartingale = !!HUMAN_SINGLE_MARTINGALE_STATE.enabled;
    HUMAN_SINGLE_MARTINGALE_STATE.pendingStake = stake;
    HUMAN_SINGLE_MARTINGALE_STATE.status = "Running";
    updateHumanSingleMartingalePanel();
    try{
      await placeHumanManualAction(settings.action, Object.assign({ stake, quiet: true }, settings.option));
      if(typeof showToast === "function") showToast(`HUMAN ${HUMAN_SPECIAL_LABELS[settings.action]} sent at $${stake.toFixed(2)}`, "success");
    }catch(e){
      HUMAN_SINGLE_MARTINGALE_STATE.running = false;
      HUMAN_SINGLE_MARTINGALE_STATE.stopRequested = true;
      clearHumanSingleMartingalePending();
      HUMAN_SINGLE_MARTINGALE_STATE.status = "Stopped";
      if(typeof showToast === "function") showToast(e.message || "HUMAN martingale trade failed", "error");
    }finally{
      updateHumanSingleMartingalePanel();
    }
  }

  function readHumanRfMartingaleNumber(id, fallback, min, max){
    const el = byId(id);
    let value = Number(el && el.value);
    if(!Number.isFinite(value)) value = fallback;
    if(Number.isFinite(min)) value = Math.max(min, value);
    if(Number.isFinite(max)) value = Math.min(max, value);
    return value;
  }

  function readHumanRfMartingaleSettings(){
    const directionEl = byId("humanRfMartingaleDirection");
    const direction = String((directionEl && directionEl.value) || HUMAN_RF_MARTINGALE_STATE.direction || "RISE").toUpperCase() === "FALL" ? "FALL" : "RISE";
    const duration = Math.round(readHumanRfMartingaleNumber("humanRfMartingaleDuration", 5, 1, 10));
    const startStake = Number(readHumanRfMartingaleNumber("humanRfMartingaleStartStake", 0.35, 0.35, 1000000).toFixed(2));
    const multiplier = Math.max(1, readHumanRfMartingaleNumber("humanRfMartingaleMultiplier", 2, 1, 100));
    const maxSteps = Math.max(1, Math.floor(readHumanRfMartingaleNumber("humanRfMartingaleMaxSteps", 8, 1, 1000)));
    const capRaw = byId("humanRfMartingaleMaxStake");
    const maxStakeValue = capRaw && String(capRaw.value || "").trim() !== ""
      ? Math.max(0.35, Number(capRaw.value))
      : null;
    const maxStake = Number.isFinite(maxStakeValue) ? Number(maxStakeValue.toFixed(2)) : null;
    if(directionEl) directionEl.value = direction;
    const durationEl = byId("humanRfMartingaleDuration");
    if(durationEl) durationEl.value = String(duration);
    return { direction, duration, startStake, multiplier, maxSteps, maxStake };
  }

  function humanRfMartingaleStakeForStep(stepValue){
    const settings = readHumanRfMartingaleSettings();
    const step = Math.max(1, Math.min(settings.maxSteps, Math.floor(Number(stepValue || HUMAN_RF_MARTINGALE_STATE.step) || 1)));
    let stake = settings.startStake * Math.pow(settings.multiplier, step - 1);
    if(settings.maxStake !== null) stake = Math.min(stake, settings.maxStake);
    return Number(Math.max(0.35, stake).toFixed(2));
  }

  function updateHumanRfMartingalePanel(){
    const settings = readHumanRfMartingaleSettings();
    HUMAN_RF_MARTINGALE_STATE.direction = settings.direction;
    const toggleBtn = byId("humanRfMartingaleToggleBtn");
    if(toggleBtn){
      toggleBtn.textContent = `MARTINGALE: ${HUMAN_RF_MARTINGALE_STATE.enabled ? "ON" : "OFF"}`;
      toggleBtn.style.background = HUMAN_RF_MARTINGALE_STATE.enabled ? "#f59e0b" : "#334155";
      toggleBtn.style.color = HUMAN_RF_MARTINGALE_STATE.enabled ? "#111827" : "#f8fafc";
    }
    const placeBtn = byId("humanRfMartingalePlaceBtn");
    if(placeBtn){
      placeBtn.disabled = HUMAN_RF_MARTINGALE_STATE.inProgress || HUMAN_RF_MARTINGALE_STATE.running;
      placeBtn.style.opacity = placeBtn.disabled ? "0.55" : "1";
      placeBtn.style.cursor = placeBtn.disabled ? "not-allowed" : "pointer";
    }
    const stopBtn = byId("humanRfMartingaleQuickStopBtn");
    if(stopBtn){
      const canStop = HUMAN_RF_MARTINGALE_STATE.running || HUMAN_RF_MARTINGALE_STATE.inProgress;
      stopBtn.disabled = !canStop;
      stopBtn.style.opacity = canStop ? "1" : "0.55";
      stopBtn.style.cursor = canStop ? "pointer" : "not-allowed";
    }
    const status = byId("humanRfMartingaleStatus");
    if(status){
      const currentStake = humanRfMartingaleStakeForStep();
      const nextStep = Math.min(settings.maxSteps, HUMAN_RF_MARTINGALE_STATE.step + 1);
      const nextStake = HUMAN_RF_MARTINGALE_STATE.enabled ? humanRfMartingaleStakeForStep(nextStep) : settings.startStake;
      status.textContent = `${HUMAN_RF_MARTINGALE_STATE.status}. ${settings.direction} • Step ${HUMAN_RF_MARTINGALE_STATE.step} • Current stake $${currentStake.toFixed(2)} • Next stake $${nextStake.toFixed(2)} • Last result: ${HUMAN_RF_MARTINGALE_STATE.lastResult}`;
      status.style.color = HUMAN_RF_MARTINGALE_STATE.inProgress ? "#fbbf24" : "#94a3b8";
    }
  }

  function setHumanRfMartingaleDirection(direction){
    HUMAN_RF_MARTINGALE_STATE.direction = String(direction || "RISE").toUpperCase() === "FALL" ? "FALL" : "RISE";
    HUMAN_RF_MARTINGALE_STATE.status = "Ready";
    updateHumanRfMartingalePanel();
  }

  function toggleHumanRfMartingale(){
    HUMAN_RF_MARTINGALE_STATE.enabled = !HUMAN_RF_MARTINGALE_STATE.enabled;
    if(HUMAN_RF_MARTINGALE_STATE.enabled){
      HUMAN_RF_MARTINGALE_STATE.step = 1;
      HUMAN_RF_MARTINGALE_STATE.status = "Ready";
      HUMAN_RF_MARTINGALE_STATE.lastResult = "none";
    }else{
      quickStopHumanRfMartingale("Martingale stopped.");
      return;
    }
    updateHumanRfMartingalePanel();
  }

  function clearHumanRfMartingalePending(){
    HUMAN_RF_MARTINGALE_STATE.inProgress = false;
    HUMAN_RF_MARTINGALE_STATE.pendingDirection = "";
    HUMAN_RF_MARTINGALE_STATE.pendingContractId = "";
    HUMAN_RF_MARTINGALE_STATE.pendingMartingale = false;
    HUMAN_RF_MARTINGALE_STATE.pendingStake = 0;
  }

  function quickStopHumanRfMartingale(reason){
    if(HUMAN_RF_MARTINGALE_STATE.restartTimer){
      clearTimeout(HUMAN_RF_MARTINGALE_STATE.restartTimer);
      HUMAN_RF_MARTINGALE_STATE.restartTimer = null;
    }
    HUMAN_RF_MARTINGALE_STATE.running = false;
    HUMAN_RF_MARTINGALE_STATE.stopRequested = true;
    HUMAN_RF_MARTINGALE_STATE.enabled = false;
    clearHumanRfMartingalePending();
    HUMAN_RF_MARTINGALE_STATE.status = reason || "Stopped";
    updateHumanRfMartingalePanel();
  }

  async function placeHumanRfMartingaleTrade(options){
    const opts = options || {};
    if(HUMAN_RF_MARTINGALE_STATE.inProgress) return;
    const settings = readHumanRfMartingaleSettings();
    const stake = HUMAN_RF_MARTINGALE_STATE.enabled ? humanRfMartingaleStakeForStep() : settings.startStake;
    if(HUMAN_RF_MARTINGALE_STATE.enabled && !opts.continuation){
      HUMAN_RF_MARTINGALE_STATE.running = true;
      HUMAN_RF_MARTINGALE_STATE.stopRequested = false;
    }
    HUMAN_RF_MARTINGALE_STATE.inProgress = true;
    HUMAN_RF_MARTINGALE_STATE.pendingDirection = settings.direction;
    HUMAN_RF_MARTINGALE_STATE.pendingContractId = "";
    HUMAN_RF_MARTINGALE_STATE.pendingMartingale = !!HUMAN_RF_MARTINGALE_STATE.enabled;
    HUMAN_RF_MARTINGALE_STATE.pendingStake = stake;
    HUMAN_RF_MARTINGALE_STATE.status = "Running";
    updateHumanRfMartingalePanel();
    try{
      const payload = {
        direction: settings.direction,
        stake,
        duration_ticks: settings.duration,
        ignore_cooldown: true,
      };
      const data = await guardMartha({
        profile: PROFILE,
        source: "human_rf_martingale",
        type: settings.direction,
        label: `HUMAN ${settings.direction} Martingale`,
        stake,
        duration: settings.duration,
        duration_unit: "t",
        batch_count: 1,
      }, () => postJSON("/human_rf_trade", payload));
      if(isMarthaBlocked(data)) throw new Error("Trade blocked");
      if(typeof showToast === "function") showToast(`HUMAN ${settings.direction} martingale sent at $${stake.toFixed(2)}`, "success");
    }catch(e){
      HUMAN_RF_MARTINGALE_STATE.running = false;
      HUMAN_RF_MARTINGALE_STATE.stopRequested = true;
      clearHumanRfMartingalePending();
      HUMAN_RF_MARTINGALE_STATE.status = "Stopped";
      if(typeof showToast === "function") showToast(e.message || "HUMAN Rise/Fall martingale trade failed", "error");
    }finally{
      updateHumanRfMartingalePanel();
    }
  }

  function humanSpecialPairActions(pair){
    return String(pair || HUMAN_SPECIAL_AUTO_STATE.pair).toUpperCase() === "RUNS"
      ? ["ONLY_UPS", "ONLY_DOWNS"]
      : ["HIGH_TICK", "LOW_TICK"];
  }

  function humanSpecialStakeForStep(stepValue){
    const step = Math.max(0, Math.floor(Number(stepValue !== undefined ? stepValue : HUMAN_SPECIAL_AUTO_STATE.step) || 0));
    if(step === 0) return 0.35;
    if(step === 1) return 0.70;
    if(step === 2) return 1.00;
    return Number((step - 1).toFixed(2));
  }

  function readHumanSpecialStake(id, fallback){
    const el = byId(id);
    const safe = clampNum(el ? el.value : fallback, 0.35, 1000000, fallback);
    if(el) el.value = safe.toFixed(2).replace(/\.00$/, "");
    return safe;
  }

  function setHumanSpecialStatus(text, color){
    const el = byId("humanSpecialAutoStatus");
    if(!el) return;
    el.textContent = text || "";
    el.style.color = color || "#94a3b8";
  }

  function updateHumanSpecialPopup(){
    const popup = byId("humanSpecialAutoPopup");
    const actions = humanSpecialPairActions();
    const isRuns = HUMAN_SPECIAL_AUTO_STATE.pair === "RUNS";
    const tickBtn = byId("humanSpecialPairTicksBtn");
    const runsBtn = byId("humanSpecialPairRunsBtn");
    if(tickBtn){
      tickBtn.style.background = isRuns ? "#1e293b" : "#f59e0b";
      tickBtn.style.color = isRuns ? "#e5e7eb" : "#111827";
    }
    if(runsBtn){
      runsBtn.style.background = isRuns ? "#f59e0b" : "#1e293b";
      runsBtn.style.color = isRuns ? "#111827" : "#e5e7eb";
    }
    const martingale = !!(byId("humanSpecialMartingaleToggle") && byId("humanSpecialMartingaleToggle").checked);
    const stakeA = byId("humanSpecialStakeA");
    const stakeB = byId("humanSpecialStakeB");
    const labelA = byId("humanSpecialStakeALabel");
    const labelB = byId("humanSpecialStakeBLabel");
    const placeBtn = byId("humanSpecialPlaceBtn");
    const quickStopBtn = byId("humanSpecialQuickStopBtn");
    const autoBackToBack = !!(byId("humanSpecialAutoToggle") && byId("humanSpecialAutoToggle").checked);
    if(labelA) labelA.textContent = `${HUMAN_SPECIAL_LABELS[actions[0]] || actions[0]} stake`;
    if(labelB) labelB.textContent = `${HUMAN_SPECIAL_LABELS[actions[1]] || actions[1]} stake`;
    if(martingale){
      const stepStake = humanSpecialStakeForStep();
      if(stakeA) stakeA.value = stepStake.toFixed(2);
      if(stakeB) stakeB.value = stepStake.toFixed(2);
    }
    const aInfo = (humanManualContracts || {})[actions[0]] || {};
    const bInfo = (humanManualContracts || {})[actions[1]] || {};
    const canPlace = !!aInfo.available && ((autoBackToBack || martingale) ? !!bInfo.available : true);
    if(placeBtn){
      placeBtn.disabled = humanManualLoading || !canPlace || HUMAN_SPECIAL_AUTO_STATE.firing || HUMAN_SPECIAL_AUTO_STATE.running || !!HUMAN_SPECIAL_AUTO_STATE.restartTimer;
      placeBtn.style.opacity = placeBtn.disabled ? "0.55" : "1";
      placeBtn.style.cursor = placeBtn.disabled ? "not-allowed" : "pointer";
    }
    if(quickStopBtn){
      const canStop = HUMAN_SPECIAL_AUTO_STATE.running || HUMAN_SPECIAL_AUTO_STATE.firing || HUMAN_SPECIAL_AUTO_STATE.pendingCount > 0 || !!HUMAN_SPECIAL_AUTO_STATE.restartTimer;
      quickStopBtn.disabled = !canStop;
      quickStopBtn.style.opacity = canStop ? "1" : "0.55";
      quickStopBtn.style.cursor = canStop ? "pointer" : "not-allowed";
    }
    if(popup && popup.style.display !== "none"){
      if(humanManualLoading){
        setHumanSpecialStatus("Checking this market before enabling special trades...", "#94a3b8");
      }else if(canPlace && (autoBackToBack || martingale)){
        const stakeText = martingale ? `$${humanSpecialStakeForStep().toFixed(2)}` : "entered stakes";
        setHumanSpecialStatus(HUMAN_SPECIAL_AUTO_STATE.running ? `Pair loop running at ${stakeText}. Waiting for ${HUMAN_SPECIAL_AUTO_STATE.pendingCount} pending trade(s).` : `${HUMAN_SPECIAL_LABELS[actions[0]]} and ${HUMAN_SPECIAL_LABELS[actions[1]]} are available.`, "#86efac");
      }else if(canPlace){
        setHumanSpecialStatus(`${HUMAN_SPECIAL_LABELS[actions[0]]} is available. Turn Auto ON only if both sides are available.`, "#86efac");
      }else{
        setHumanSpecialStatus("The selected contract is not available for this market.", "#fca5a5");
      }
    }
  }

  async function openHumanSpecialAutoPopup(){
    const popup = byId("humanSpecialAutoPopup");
    if(popup) popup.style.display = "flex";
    updateHumanSpecialPopup();
    await refreshHumanManualContracts(false);
  }

  function closeHumanSpecialAutoPopup(){
    const popup = byId("humanSpecialAutoPopup");
    if(popup) popup.style.display = "none";
  }

  function setHumanSpecialPair(pair){
    HUMAN_SPECIAL_AUTO_STATE.pair = String(pair || "").toUpperCase() === "RUNS" ? "RUNS" : "TICKS";
    updateHumanSpecialPopup();
  }

  function setHumanSpecialMartingale(enabled){
    if(!enabled){
      if(HUMAN_SPECIAL_AUTO_STATE.running){
        stopHumanSpecialAuto("Martingale stopped by user.", { resetToggles: true });
        return;
      }
      setHumanSpecialStatus("Martingale off. The popup will use the two stake fields as entered.", "#94a3b8");
    }else{
      HUMAN_SPECIAL_AUTO_STATE.step = 0;
      setHumanSpecialStatus("Martingale on. Both sides start at $0.35, then $0.70, $1, $2, $3, $4 until a win.", "#fbbf24");
    }
    updateHumanSpecialPopup();
  }

  function clearHumanSpecialRestartTimer(){
    if(HUMAN_SPECIAL_AUTO_STATE.restartTimer){
      clearTimeout(HUMAN_SPECIAL_AUTO_STATE.restartTimer);
      HUMAN_SPECIAL_AUTO_STATE.restartTimer = null;
    }
  }

  function stopHumanSpecialAuto(reason, options){
    const opts = options || {};
    clearHumanSpecialRestartTimer();
    HUMAN_SPECIAL_AUTO_STATE.running = false;
    HUMAN_SPECIAL_AUTO_STATE.firing = false;
    HUMAN_SPECIAL_AUTO_STATE.pendingCount = 0;
    HUMAN_SPECIAL_AUTO_STATE.expectedCount = 0;
    HUMAN_SPECIAL_AUTO_STATE.settledCount = 0;
    HUMAN_SPECIAL_AUTO_STATE.cycleWon = false;
    HUMAN_SPECIAL_AUTO_STATE.stopRequested = true;
    HUMAN_SPECIAL_AUTO_STATE.contractActions = {};
    HUMAN_SPECIAL_AUTO_STATE.cycleContractActions = {};
    HUMAN_SPECIAL_AUTO_STATE.settledContracts = {};
    HUMAN_SPECIAL_AUTO_STATE.localOrderActions = [];
    if(opts.resetToggles){
      const autoToggle = byId("humanSpecialAutoToggle");
      const martingaleToggle = byId("humanSpecialMartingaleToggle");
      if(autoToggle) autoToggle.checked = false;
      if(martingaleToggle) martingaleToggle.checked = false;
    }
    updateHumanSpecialPopup();
    if(reason) setHumanSpecialStatus(reason, "#fbbf24");
  }

  function setHumanSpecialAutoBackToBack(enabled){
    if(!enabled && HUMAN_SPECIAL_AUTO_STATE.running){
      stopHumanSpecialAuto("Auto back-to-back stopped by user.", { resetToggles: true });
      return;
    }
    updateHumanSpecialPopup();
  }

  function quickStopHumanSpecialAuto(){
    stopHumanSpecialAuto("Quick Stop pressed. Human Special Auto is OFF.", { resetToggles: true });
  }

  async function runHumanSpecialPair(options){
    const opts = options || {};
    if(HUMAN_SPECIAL_AUTO_STATE.firing) return;
    const actions = humanSpecialPairActions();
    const autoBackToBack = !!(byId("humanSpecialAutoToggle") && byId("humanSpecialAutoToggle").checked);
    const martingale = !!(byId("humanSpecialMartingaleToggle") && byId("humanSpecialMartingaleToggle").checked);
    const targets = (autoBackToBack || martingale) ? actions : [actions[0]];
    const stakes = {};
    const martingaleStake = humanSpecialStakeForStep();
    stakes[actions[0]] = martingale ? martingaleStake : readHumanSpecialStake("humanSpecialStakeA", 0.35);
    stakes[actions[1]] = martingale ? martingaleStake : readHumanSpecialStake("humanSpecialStakeB", 0.35);
    if((autoBackToBack || martingale) && !opts.continuation){
      HUMAN_SPECIAL_AUTO_STATE.stopRequested = false;
    }
    HUMAN_SPECIAL_AUTO_STATE.firing = true;
    HUMAN_SPECIAL_AUTO_STATE.running = autoBackToBack || martingale;
    HUMAN_SPECIAL_AUTO_STATE.cycleWon = false;
    HUMAN_SPECIAL_AUTO_STATE.pendingCount = 0;
    HUMAN_SPECIAL_AUTO_STATE.expectedCount = targets.length;
    HUMAN_SPECIAL_AUTO_STATE.settledCount = 0;
    HUMAN_SPECIAL_AUTO_STATE.cycleContractActions = {};
    HUMAN_SPECIAL_AUTO_STATE.settledContracts = {};
    HUMAN_SPECIAL_AUTO_STATE.localOrderActions = targets.slice();
    if(HUMAN_SPECIAL_AUTO_STATE.running && HUMAN_SPECIAL_AUTO_STATE.stopRequested){
      HUMAN_SPECIAL_AUTO_STATE.firing = false;
      updateHumanSpecialPopup();
      return;
    }
    setHumanSpecialStatus(targets.length > 1 ? `Sending both trades at $${stakes[actions[0]].toFixed(2)}...` : `Sending ${HUMAN_SPECIAL_LABELS[actions[0]]} only...`, "#fbbf24");
    try{
      await refreshHumanManualContracts(false);
      for(const action of targets){
        const actionInfo = (humanManualContracts || {})[action] || {};
        if(!actionInfo.available) throw new Error(`${HUMAN_SPECIAL_LABELS[action]} is not available for the selected market.`);
        await placeHumanManualAction(action, { stake: stakes[action], quiet: true });
        HUMAN_SPECIAL_AUTO_STATE.pendingCount += 1;
      }
      const runningLabel = martingale ? "Martingale running" : "Auto running";
      setHumanSpecialStatus(
        (autoBackToBack || martingale)
          ? `${runningLabel}. Waiting for ${HUMAN_SPECIAL_AUTO_STATE.pendingCount} pending trades to settle.`
          : (targets.length > 1 ? "Both special trades were sent." : "One special trade was sent."),
        "#86efac"
      );
      if(typeof showToast === "function"){
        showToast(targets.length > 1 ? "HUMAN special pair trades sent" : "HUMAN special trade sent", "success");
      }
    }catch(e){
      HUMAN_SPECIAL_AUTO_STATE.running = false;
      HUMAN_SPECIAL_AUTO_STATE.pendingCount = 0;
      HUMAN_SPECIAL_AUTO_STATE.expectedCount = 0;
      HUMAN_SPECIAL_AUTO_STATE.settledCount = 0;
      HUMAN_SPECIAL_AUTO_STATE.cycleContractActions = {};
      HUMAN_SPECIAL_AUTO_STATE.settledContracts = {};
      HUMAN_SPECIAL_AUTO_STATE.localOrderActions = [];
      HUMAN_SPECIAL_AUTO_STATE.stopRequested = true;
      setHumanSpecialStatus(e.message || "HUMAN special auto failed.", "#fca5a5");
      if(typeof showToast === "function") showToast(e.message || "HUMAN special auto failed", "error");
    }finally{
      HUMAN_SPECIAL_AUTO_STATE.firing = false;
      updateHumanSpecialPopup();
    }
  }

  function normalizeHumanSpecialAction(value){
    const text = String(value || "").toUpperCase().replace(/[^A-Z0-9]+/g, "_");
    const compact = text.replace(/[^A-Z0-9]/g, "");
    if(text.includes("HIGH_TICK") || text.includes("HIGH_TICKS") || compact.includes("TICKHIGH") || compact.includes("HIGHTICK")) return "HIGH_TICK";
    if(text.includes("LOW_TICK") || text.includes("LOW_TICKS") || compact.includes("TICKLOW") || compact.includes("LOWTICK")) return "LOW_TICK";
    if(text.includes("ONLY_UP") || compact.includes("RUNHIGH") || compact.includes("ONLYUP") || compact.includes("RUNSUP")) return "ONLY_UPS";
    if(text.includes("ONLY_DOWN") || compact.includes("RUNLOW") || compact.includes("ONLYDOWN") || compact.includes("RUNSDOWN")) return "ONLY_DOWNS";
    return "";
  }

  function normalizeHumanRfDirection(value){
    const text = String(value || "").toUpperCase();
    const compact = text.replace(/[^A-Z]/g, "");
    if(text.includes("RISE") || text.includes("CALL") || compact.includes("RISE")) return "RISE";
    if(text.includes("FALL") || text.includes("PUT") || compact.includes("FALL")) return "FALL";
    return "";
  }

  function rememberHumanSpecialTrade(payload){
    if(!payload || String(payload.profile || "").toUpperCase() !== PROFILE) return;
    const activeCycle = HUMAN_SPECIAL_AUTO_STATE.running || HUMAN_SPECIAL_AUTO_STATE.firing || HUMAN_SPECIAL_AUTO_STATE.pendingCount > 0 || HUMAN_SPECIAL_AUTO_STATE.expectedCount > 0;
    const action = normalizeHumanSpecialAction([payload.type, payload.contract_type, payload.label, payload.action].filter(Boolean).join(" "))
      || (activeCycle ? (HUMAN_SPECIAL_AUTO_STATE.localOrderActions[Object.keys(HUMAN_SPECIAL_AUTO_STATE.cycleContractActions || {}).length] || "") : "");
    const contractId = payload.contract_id || payload.buy_contract_id || payload.id;
    if(action && contractId){
      const contractKey = String(contractId);
      HUMAN_SPECIAL_AUTO_STATE.contractActions[contractKey] = action;
      if(
        activeCycle
        && humanSpecialPairActions().includes(action)
      ){
        HUMAN_SPECIAL_AUTO_STATE.cycleContractActions[contractKey] = action;
      }
    }
    if(
      action
      && contractId
      && HUMAN_SINGLE_MARTINGALE_STATE.inProgress
      && !HUMAN_SINGLE_MARTINGALE_STATE.pendingContractId
      && action === HUMAN_SINGLE_MARTINGALE_STATE.pendingAction
    ){
      HUMAN_SINGLE_MARTINGALE_STATE.pendingContractId = String(contractId);
      HUMAN_SINGLE_MARTINGALE_STATE.status = "Running";
      updateHumanSingleMartingalePanel();
    }
    const rfDirection = normalizeHumanRfDirection([payload.type, payload.contract_type, payload.label, payload.action].filter(Boolean).join(" "));
    if(
      rfDirection
      && contractId
      && HUMAN_RF_MARTINGALE_STATE.inProgress
      && !HUMAN_RF_MARTINGALE_STATE.pendingContractId
      && rfDirection === HUMAN_RF_MARTINGALE_STATE.pendingDirection
    ){
      HUMAN_RF_MARTINGALE_STATE.pendingContractId = String(contractId);
      HUMAN_RF_MARTINGALE_STATE.status = "Running";
      updateHumanRfMartingalePanel();
    }
  }

  function humanTradeNumber(payload, fields){
    for(const field of fields){
      if(!payload || payload[field] === undefined || payload[field] === null || payload[field] === "") continue;
      const value = Number(payload[field]);
      if(Number.isFinite(value)) return value;
    }
    return NaN;
  }

  function resolveHumanTradeOutcome(payload){
    const resultText = String([
      payload && payload.result,
      payload && payload.status,
      payload && payload.contract_status,
      payload && payload.sell_status,
    ].filter(Boolean).join(" ")).toUpperCase();
    const profit = humanTradeNumber(payload, ["profit", "profit_value", "pnl", "net_profit", "result_profit"]);
    if(resultText.includes("WIN") || resultText.includes("WON") || resultText.includes("PROFIT")) return "WIN";
    if(resultText.includes("LOSS") || resultText.includes("LOST") || resultText.includes("LOSE")) return "LOSS";
    if(Number.isFinite(profit) && profit > 0) return "WIN";
    if(Number.isFinite(profit) && profit < 0) return "LOSS";
    const payout = humanTradeNumber(payload, ["payout", "sell_price", "bid_price"]);
    const buyPrice = humanTradeNumber(payload, ["buy_price", "stake", "amount"]);
    if((resultText.includes("SOLD") || resultText.includes("SETTLED") || resultText.includes("CLOSED")) && Number.isFinite(payout) && Number.isFinite(buyPrice)){
      return payout > buyPrice ? "WIN" : "LOSS";
    }
    return "";
  }

  function updateHumanSingleMartingaleFromResult(payload){
    if(!payload || String(payload.profile || "").toUpperCase() !== PROFILE) return;
    if(!HUMAN_SINGLE_MARTINGALE_STATE.inProgress && !HUMAN_SINGLE_MARTINGALE_STATE.pendingContractId) return;
    const contractId = payload.contract_id || payload.buy_contract_id || payload.id;
    const mode = String(payload.mode || "").toLowerCase();
    const action = normalizeHumanSpecialAction([payload.type, payload.contract_type, payload.label, payload.action].filter(Boolean).join(" "))
      || (mode === "human_manual_contract" ? HUMAN_SINGLE_MARTINGALE_STATE.pendingAction : "");
    const pendingId = HUMAN_SINGLE_MARTINGALE_STATE.pendingContractId;
    if(pendingId && String(contractId || "") !== pendingId) return;
    if(!pendingId && action && action !== HUMAN_SINGLE_MARTINGALE_STATE.pendingAction) return;
    const outcome = resolveHumanTradeOutcome(payload);
    const won = outcome === "WIN";
    const lost = outcome === "LOSS";
    if(!outcome) return;

    const wasMartingaleTrade = !!HUMAN_SINGLE_MARTINGALE_STATE.pendingMartingale;
    clearHumanSingleMartingalePending();
    if(won){
      HUMAN_SINGLE_MARTINGALE_STATE.step = 1;
      HUMAN_SINGLE_MARTINGALE_STATE.running = false;
      HUMAN_SINGLE_MARTINGALE_STATE.stopRequested = false;
      HUMAN_SINGLE_MARTINGALE_STATE.enabled = false;
      HUMAN_SINGLE_MARTINGALE_STATE.lastResult = "WIN";
      HUMAN_SINGLE_MARTINGALE_STATE.status = wasMartingaleTrade ? "Reset" : "Ready";
    }else if(lost){
      HUMAN_SINGLE_MARTINGALE_STATE.lastResult = "LOSS";
      if(wasMartingaleTrade && HUMAN_SINGLE_MARTINGALE_STATE.enabled){
        const settings = readHumanSingleMartingaleSettings();
        HUMAN_SINGLE_MARTINGALE_STATE.step = Math.min(settings.maxSteps, HUMAN_SINGLE_MARTINGALE_STATE.step + 1);
        HUMAN_SINGLE_MARTINGALE_STATE.status = "Running";
        if(HUMAN_SINGLE_MARTINGALE_STATE.running && !HUMAN_SINGLE_MARTINGALE_STATE.stopRequested){
          if(HUMAN_SINGLE_MARTINGALE_STATE.restartTimer) clearTimeout(HUMAN_SINGLE_MARTINGALE_STATE.restartTimer);
          HUMAN_SINGLE_MARTINGALE_STATE.restartTimer = setTimeout(() => {
            HUMAN_SINGLE_MARTINGALE_STATE.restartTimer = null;
            if(HUMAN_SINGLE_MARTINGALE_STATE.running && HUMAN_SINGLE_MARTINGALE_STATE.enabled && !HUMAN_SINGLE_MARTINGALE_STATE.stopRequested){
              placeHumanSingleMartingaleTrade({ continuation: true });
            }
          }, 350);
        }
      }else{
        HUMAN_SINGLE_MARTINGALE_STATE.status = "Ready";
      }
    }
    updateHumanSingleMartingalePanel();
  }

  function updateHumanRfMartingaleFromResult(payload){
    if(!payload || String(payload.profile || "").toUpperCase() !== PROFILE) return;
    if(!HUMAN_RF_MARTINGALE_STATE.inProgress && !HUMAN_RF_MARTINGALE_STATE.pendingContractId) return;
    const contractId = payload.contract_id || payload.buy_contract_id || payload.id;
    const direction = normalizeHumanRfDirection([payload.type, payload.contract_type, payload.label, payload.action].filter(Boolean).join(" "));
    const pendingId = HUMAN_RF_MARTINGALE_STATE.pendingContractId;
    if(pendingId && String(contractId || "") !== pendingId) return;
    if(!pendingId && direction && direction !== HUMAN_RF_MARTINGALE_STATE.pendingDirection) return;
    const outcome = resolveHumanTradeOutcome(payload);
    const won = outcome === "WIN";
    const lost = outcome === "LOSS";
    if(!outcome) return;

    const wasMartingaleTrade = !!HUMAN_RF_MARTINGALE_STATE.pendingMartingale;
    clearHumanRfMartingalePending();
    if(won){
      HUMAN_RF_MARTINGALE_STATE.step = 1;
      HUMAN_RF_MARTINGALE_STATE.running = false;
      HUMAN_RF_MARTINGALE_STATE.stopRequested = false;
      HUMAN_RF_MARTINGALE_STATE.enabled = false;
      HUMAN_RF_MARTINGALE_STATE.lastResult = "WIN";
      HUMAN_RF_MARTINGALE_STATE.status = wasMartingaleTrade ? "Reset" : "Ready";
    }else if(lost){
      HUMAN_RF_MARTINGALE_STATE.lastResult = "LOSS";
      if(wasMartingaleTrade && HUMAN_RF_MARTINGALE_STATE.enabled){
        const settings = readHumanRfMartingaleSettings();
        HUMAN_RF_MARTINGALE_STATE.step = Math.min(settings.maxSteps, HUMAN_RF_MARTINGALE_STATE.step + 1);
        HUMAN_RF_MARTINGALE_STATE.status = "Running";
        if(HUMAN_RF_MARTINGALE_STATE.running && !HUMAN_RF_MARTINGALE_STATE.stopRequested){
          if(HUMAN_RF_MARTINGALE_STATE.restartTimer) clearTimeout(HUMAN_RF_MARTINGALE_STATE.restartTimer);
          HUMAN_RF_MARTINGALE_STATE.restartTimer = setTimeout(() => {
            HUMAN_RF_MARTINGALE_STATE.restartTimer = null;
            if(HUMAN_RF_MARTINGALE_STATE.running && HUMAN_RF_MARTINGALE_STATE.enabled && !HUMAN_RF_MARTINGALE_STATE.stopRequested){
              placeHumanRfMartingaleTrade({ continuation: true });
            }
          }, 350);
        }
      }else{
        HUMAN_RF_MARTINGALE_STATE.status = "Ready";
      }
    }
    updateHumanRfMartingalePanel();
  }

  function updateHumanSpecialMartingaleFromResult(payload){
    if(!payload || String(payload.profile || "").toUpperCase() !== PROFILE) return;
    const contractId = payload.contract_id || payload.buy_contract_id || payload.id;
    const contractKey = contractId ? String(contractId) : "";
    const mode = String(payload.mode || "").toLowerCase();
    const activeCycle = HUMAN_SPECIAL_AUTO_STATE.running || HUMAN_SPECIAL_AUTO_STATE.pendingCount > 0 || HUMAN_SPECIAL_AUTO_STATE.expectedCount > 0;
    const pairActions = humanSpecialPairActions();
    const action = normalizeHumanSpecialAction([payload.type, payload.contract_type, payload.label, payload.action].filter(Boolean).join(" "))
      || (contractKey ? HUMAN_SPECIAL_AUTO_STATE.cycleContractActions[contractKey] : "")
      || (contractKey ? HUMAN_SPECIAL_AUTO_STATE.contractActions[contractKey] : "")
      || (activeCycle && mode === "human_manual_contract" ? pairActions[0] : "");
    if(!action || !Object.prototype.hasOwnProperty.call(HUMAN_SPECIAL_LABELS, action)) return;
    if(!activeCycle) return;
    const outcome = resolveHumanTradeOutcome(payload);
    const won = outcome === "WIN";
    const lost = outcome === "LOSS";
    if(!outcome) return;
    if(contractKey){
      if(HUMAN_SPECIAL_AUTO_STATE.settledContracts[contractKey]) return;
      HUMAN_SPECIAL_AUTO_STATE.settledContracts[contractKey] = true;
      delete HUMAN_SPECIAL_AUTO_STATE.contractActions[contractKey];
      delete HUMAN_SPECIAL_AUTO_STATE.cycleContractActions[contractKey];
    }
    const expectedCount = Math.max(1, Number(HUMAN_SPECIAL_AUTO_STATE.expectedCount || 0), Number(HUMAN_SPECIAL_AUTO_STATE.pendingCount || 0));
    HUMAN_SPECIAL_AUTO_STATE.settledCount = Math.min(expectedCount, Number(HUMAN_SPECIAL_AUTO_STATE.settledCount || 0) + 1);
    HUMAN_SPECIAL_AUTO_STATE.pendingCount = Math.max(0, Number(HUMAN_SPECIAL_AUTO_STATE.pendingCount || 0) - 1);
    const autoBackToBack = !!(byId("humanSpecialAutoToggle") && byId("humanSpecialAutoToggle").checked);
    const martingale = !!(byId("humanSpecialMartingaleToggle") && byId("humanSpecialMartingaleToggle").checked);
    if(won){
      HUMAN_SPECIAL_AUTO_STATE.step = 0;
      stopHumanSpecialAuto(`${HUMAN_SPECIAL_LABELS[action]} won. Pair loop stopped.`, { resetToggles: true });
      return;
    }
    const cycleComplete = Number(HUMAN_SPECIAL_AUTO_STATE.expectedCount || 0) > 0
      ? HUMAN_SPECIAL_AUTO_STATE.settledCount >= expectedCount
      : HUMAN_SPECIAL_AUTO_STATE.pendingCount <= 0;
    if(cycleComplete && !HUMAN_SPECIAL_AUTO_STATE.firing){
      if(martingale){
        HUMAN_SPECIAL_AUTO_STATE.step = Math.min(200, HUMAN_SPECIAL_AUTO_STATE.step + 1);
      }
      HUMAN_SPECIAL_AUTO_STATE.expectedCount = 0;
      HUMAN_SPECIAL_AUTO_STATE.settledCount = 0;
      HUMAN_SPECIAL_AUTO_STATE.cycleContractActions = {};
      HUMAN_SPECIAL_AUTO_STATE.settledContracts = {};
      HUMAN_SPECIAL_AUTO_STATE.localOrderActions = [];
      if(lost && HUMAN_SPECIAL_AUTO_STATE.running && (autoBackToBack || martingale) && !HUMAN_SPECIAL_AUTO_STATE.stopRequested){
        const nextStake = martingale ? humanSpecialStakeForStep() : readHumanSpecialStake("humanSpecialStakeA", 0.35);
        setHumanSpecialStatus(`Both trades lost. Sending next pair at $${nextStake.toFixed(2)}...`, "#fbbf24");
        clearHumanSpecialRestartTimer();
        HUMAN_SPECIAL_AUTO_STATE.restartTimer = setTimeout(() => {
          HUMAN_SPECIAL_AUTO_STATE.restartTimer = null;
          const keepAuto = !!(byId("humanSpecialAutoToggle") && byId("humanSpecialAutoToggle").checked);
          const keepMartingale = !!(byId("humanSpecialMartingaleToggle") && byId("humanSpecialMartingaleToggle").checked);
          if(HUMAN_SPECIAL_AUTO_STATE.running && (keepAuto || keepMartingale) && !HUMAN_SPECIAL_AUTO_STATE.firing && !HUMAN_SPECIAL_AUTO_STATE.stopRequested){
            runHumanSpecialPair({ continuation: true });
          }
        }, 350);
      }else if(lost && martingale){
        setHumanSpecialStatus(`Both trades lost. Next martingale pair is $${humanSpecialStakeForStep().toFixed(2)}.`, "#fbbf24");
      }
    }
    updateHumanSpecialPopup();
  }

  async function humanRFSetStake(){
    try{
      const stakeEl = byId("stake");
      const stakeVal = stakeEl ? clampNum(stakeEl.value || 1, 0.35, 1000000, 1) : 1;
      if(stakeEl) stakeEl.value = String(stakeVal);
      const data = await postJSON("/set_auto_stake", { stake: stakeVal });
      if(typeof showToast === "function") showToast("HUMAN stake set: " + Number(data.auto_stake || stakeVal).toFixed(2), "success");
    }catch(e){
      if(typeof showToast === "function") showToast(e.message || "Failed to set stake", "error");
    }
  }

  function startPolling(){
    stopPolling();
    if(!isActive() || !rootExists()){
      const App = getApp();
      if(App && typeof App.logActiveIntervalCount === "function") App.logActiveIntervalCount("human_poll_skipped_inactive");
      return;
    }
    fetchHumanRFStatus();
    pollTimer = setInterval(() => {
      if(!isActive() || !rootExists()){
        stopPolling();
        return;
      }
      fetchHumanRFStatus();
    }, 1500);
    const App = getApp();
    if(App && typeof App.registerFrontendInterval === "function") App.registerFrontendInterval(POLL_INTERVAL_LABEL, pollTimer);
  }

  function flushHumanRFStatusRender(){
    if(statusRenderTimer){
      const App = getApp();
      if(!(App && typeof App.clearFrontendTimeout === "function" && App.clearFrontendTimeout("human_status_render"))){
        clearTimeout(statusRenderTimer);
      }
      statusRenderTimer = null;
    }
    const payload = pendingStatusPayload;
    pendingStatusPayload = null;
    if(payload) renderHumanRFStatus(payload);
  }

  function scheduleHumanRFStatusRender(payload){
    pendingStatusPayload = payload || pendingStatusPayload;
    const elapsed = Date.now() - Number(lastStatusRenderAt || 0);
    if(elapsed >= STATUS_RENDER_THROTTLE_MS){
      flushHumanRFStatusRender();
      return;
    }
    if(!statusRenderTimer){
      const delay = Math.max(50, STATUS_RENDER_THROTTLE_MS - elapsed);
      statusRenderTimer = setTimeout(flushHumanRFStatusRender, delay);
      const App = getApp();
      if(App && typeof App.registerFrontendTimeout === "function") App.registerFrontendTimeout("human_status_render", statusRenderTimer);
    }
  }

  function stopPolling(){
    const App = getApp();
    const clearedTracked = !!(App && typeof App.clearFrontendInterval === "function" && App.clearFrontendInterval(POLL_INTERVAL_LABEL));
    if(pollTimer && !clearedTracked){
      clearInterval(pollTimer);
    }
    if(pollTimer || clearedTracked){
      pollTimer = null;
    }
  }

  function clearStatusRenderTimer(){
    const App = getApp();
    const clearedTracked = !!(App && typeof App.clearFrontendTimeout === "function" && App.clearFrontendTimeout("human_status_render"));
    if(statusRenderTimer && !clearedTracked){
      clearTimeout(statusRenderTimer);
    }
    statusRenderTimer = null;
    pendingStatusPayload = null;
  }

  function bindSocketIfPossible(){
    bindHumanSpecialGlobalSocketFallback();
    if(socketHooked) return;
    try{
      const App = getApp();
      const hasAppBinder = App && typeof App.bindSocketListener === "function";
      if(hasAppBinder){
        const bind = (eventName, handler) => {
          return App.bindSocketListener(PROFILE, eventName, handler);
        };
        bind("human_rf_status", (payload) => {
          if(rootExists()) scheduleHumanRFStatusRender(payload);
        });
        bind("human_market_change", () => {
          fetchHumanRFStatus();
          refreshHumanManualContracts(true);
        });
        bind("market_change", () => {
          fetchHumanRFStatus();
          refreshHumanManualContracts(true);
        });
        bind("trade_placed", rememberHumanSpecialTrade);
        bind("trade_result", updateHumanSpecialMartingaleFromResult);
        bind("trade_result", updateHumanSingleMartingaleFromResult);
        bind("trade_result", updateHumanRfMartingaleFromResult);
        socketHooked = true;
        if(App && typeof App.logSocketListenerCounts === "function") App.logSocketListenerCounts("human_profile_init");
      }
    }catch(e){}
  }

  function bindHumanSpecialGlobalSocketFallback(){
    let liveSocket = null;
    try{
      liveSocket = (typeof socket !== "undefined" && socket) ? socket : (window.socket || null);
    }catch(e){
      liveSocket = window.socket || null;
    }
    if(!liveSocket || typeof liveSocket.on !== "function") return false;
    try{
      const previous = window.__humanSpecialSocketFallback || {};
      if(previous.socket && previous.handlers && typeof previous.socket.off === "function"){
        previous.socket.off("trade_placed", previous.handlers.placed);
        previous.socket.off("trade_result", previous.handlers.specialResult);
        previous.socket.off("trade_result", previous.handlers.singleResult);
        if(previous.handlers.rfResult) previous.socket.off("trade_result", previous.handlers.rfResult);
      }
      const placed = (payload) => {
        if(payload && String(payload.profile || "").toUpperCase() === PROFILE) rememberHumanSpecialTrade(payload);
      };
      const specialResult = (payload) => {
        if(payload && String(payload.profile || "").toUpperCase() === PROFILE) updateHumanSpecialMartingaleFromResult(payload);
      };
      const singleResult = (payload) => {
        if(payload && String(payload.profile || "").toUpperCase() === PROFILE) updateHumanSingleMartingaleFromResult(payload);
      };
      const rfResult = (payload) => {
        if(payload && String(payload.profile || "").toUpperCase() === PROFILE) updateHumanRfMartingaleFromResult(payload);
      };
      liveSocket.on("trade_placed", placed);
      liveSocket.on("trade_result", specialResult);
      liveSocket.on("trade_result", singleResult);
      liveSocket.on("trade_result", rfResult);
      window.__humanSpecialSocketFallback = { socket: liveSocket, handlers: { placed, specialResult, singleResult, rfResult } };
      return true;
    }catch(e){
      return false;
    }
  }

  function getAppHooks(){
    const App = getApp();
    return App || {};
  }

  function updateFormulaXButton(){
    const btn = byId("formulaXBtn");
    if(btn){
      if(fxState.active){
        btn.innerText = "FormulaX • ON (waiting)";
        btn.style.background = "#38bdf8";
      }else{
        btn.innerText = "FormulaX";
        btn.style.background = "#0ea5e9";
      }
    }
    setAutoToast("formula_x", !!fxState.active, "HUMAN FormulaX");
  }

  function inferMarketDirection(){
    const bias = (cachedStatus && cachedStatus.bias || "").toUpperCase();
    const td = (cachedStatus && cachedStatus.trade_direction || cachedStatus && cachedStatus.signal || "").toUpperCase();
    if(td.includes("RISE") || td.includes("HIGH")) return "RISE";
    if(td.includes("FALL") || td.includes("LOW")) return "FALL";
    if(bias.includes("BULL")) return "RISE";
    if(bias.includes("BEAR")) return "FALL";
    return null;
  }

  function maybeAutoFormulaX(){
    if(!fxState.active || fxState.firing) return;
    const dir = inferMarketDirection();
    if(dir){
      runFormulaXOnce(dir);
    }else{
      const now = Date.now();
      if(now - fxState.lastToast > 4000 && typeof showToast === "function"){
        fxState.lastToast = now;
        showToast("FormulaX: waiting for market trend…", "info");
      }
    }
  }

  async function runFormulaXOnce(dir){
    try{
      fxState.firing = true;
      const stakeEl = byId("stake");
      const durEl = byId("humanRfDuration");
      const stakeVal = stakeEl ? clampNum(stakeEl.value || 1, 0.35, 1000000, 1) : 1;
      const durationTicks = durEl ? clampNum(durEl.value || 5, 1, 10, 5) : 5;
      if(stakeEl) stakeEl.value = String(stakeVal);
      if(durEl) durEl.value = String(durationTicks);

      const bigStake = Number((stakeVal * 2 / 3).toFixed(2));
      const smallStake = Math.max(0.35, Number((stakeVal - bigStake).toFixed(2)));
      const riseStake = dir === "RISE" ? bigStake : smallStake;
      const fallStake = dir === "FALL" ? bigStake : smallStake;

      const formulaPayload = {
        rise_stake: riseStake,
        fall_stake: fallStake,
        duration_ticks: durationTicks,
      };
      const r = await guardMartha({
        profile: PROFILE,
        source: "human_formula_x",
        type: dir || "FORMULA_X",
        label: `FormulaX ${dir}`,
        stake: stakeVal,
        duration: durationTicks,
        duration_unit: "t",
        batch_count: 2,
      }, ()=>postJSON("/human_formula_x", formulaPayload));
      if(isMarthaBlocked(r)){
        fxState.active = false;
        return;
      }
      const ok = r && r.status === "success";
      if(typeof showToast === "function"){
        showToast(`FormulaX sent RISE ${money(riseStake)} + FALL ${money(fallStake)} (${dir} favored)`, ok ? "success" : "warn");
      }
      fxState.active = false;
      await fetchHumanRFStatus();
    }catch(e){
      if(typeof showToast === "function") showToast(e.message || "FormulaX failed", "error");
      fxState.active = false;
    }finally{
      fxState.firing = false;
      updateFormulaXButton();
    }
  }

  async function toggleFormulaX(){
    fxState.active = !fxState.active;
    fxState.firing = false;
    fxState.lastToast = 0;
    updateFormulaXButton();
    if(fxState.active){
      if(typeof showToast === "function") showToast("FormulaX armed: waiting for market trend…", "info");
      maybeAutoFormulaX();
    }else{
      if(typeof showToast === "function") showToast("FormulaX off", "warn");
    }
  }

  function bindUI(root) {
    const App = getAppHooks();
    if (!root || !App.bindActionButtons) return;

    App.bindActionButtons(root, async ({ action }) => {
      switch (action) {
        default:
          break;
      }
    }, "human_action_clicks");

    // also poll FormulaX while actions come in
    maybeAutoFormulaX();
  }

  function bindHumanDropdownPanels(root) {
    const scope = root && typeof root.querySelectorAll === "function" ? root : document;
    scope.querySelectorAll("#humanProfilePanel details.human-dropdown-panel > summary").forEach((summary) => {
      if (!summary || summary.dataset.humanDropdownBound === "1") return;
      summary.dataset.humanDropdownBound = "1";
      const syncExpanded = () => {
        const details = summary.closest("details.human-dropdown-panel");
        if (details) summary.setAttribute("aria-expanded", details.open ? "true" : "false");
      };
      const togglePanel = (event) => {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        const details = summary.closest("details.human-dropdown-panel");
        if (!details) return;
        details.open = !details.open;
        syncExpanded();
      };
      summary.setAttribute("role", "button");
      summary.setAttribute("tabindex", "0");
      summary.addEventListener("click", togglePanel);
      summary.addEventListener("keydown", (event) => {
        if (!event || (event.key !== "Enter" && event.key !== " ")) return;
        togglePanel(event);
      });
      syncExpanded();
    });
  }

  async function onMount(payload) {
    const root = payload && payload.root ? payload.root : byId("profileContainer");
    bindUI(root);
    bindHumanDropdownPanels(root);
    bindSocketIfPossible();

    // expose globals for inline onclick in human.html
    window.humanRFTrade = humanRFTrade;
    window.humanAutoRiseFall = humanAutoRiseFall;
    window.toggleHumanRFAllowEquals = toggleHumanRFAllowEquals;
    window.saveHumanRFSettings = saveHumanRFSettings;
    window.toggleHumanRFSetting = toggleHumanRFSetting;
    window.humanRFSetStake = humanRFSetStake;
    window.runFormulaX = toggleFormulaX;
    window.humanManualTrade = humanManualTrade;
    window.refreshHumanManualContracts = refreshHumanManualContracts;
    window.openHumanSpecialAutoPopup = openHumanSpecialAutoPopup;
    window.closeHumanSpecialAutoPopup = closeHumanSpecialAutoPopup;
    window.setHumanSpecialPair = setHumanSpecialPair;
    window.setHumanSpecialMartingale = setHumanSpecialMartingale;
    window.setHumanSpecialAutoBackToBack = setHumanSpecialAutoBackToBack;
    window.updateHumanSpecialAutoPopup = updateHumanSpecialPopup;
    window.runHumanSpecialPair = runHumanSpecialPair;
    window.quickStopHumanSpecialAuto = quickStopHumanSpecialAuto;
    window.setHumanSingleMartingaleAction = setHumanSingleMartingaleAction;
    window.toggleHumanSingleMartingale = toggleHumanSingleMartingale;
    window.updateHumanSingleMartingalePanel = updateHumanSingleMartingalePanel;
    window.placeHumanSingleMartingaleTrade = placeHumanSingleMartingaleTrade;
    window.quickStopHumanSingleMartingale = quickStopHumanSingleMartingale;
    window.setHumanRfMartingaleDirection = setHumanRfMartingaleDirection;
    window.toggleHumanRfMartingale = toggleHumanRfMartingale;
    window.updateHumanRfMartingalePanel = updateHumanRfMartingalePanel;
    window.placeHumanRfMartingaleTrade = placeHumanRfMartingaleTrade;
    window.quickStopHumanRfMartingale = quickStopHumanRfMartingale;

    // initial render/poll
    startPolling();
    refreshHumanManualContracts(false);
    syncHumanRFAllowEqualsToggle();
    updateHumanSingleMartingalePanel();
    updateHumanRfMartingalePanel();
    maybeAutoFormulaX();
  }

  async function afterLoadProfileUI() {
    bindHumanDropdownPanels(byId("profileContainer"));
    bindSocketIfPossible();
    startPolling();
    refreshHumanManualContracts(false);
    syncHumanRFAllowEqualsToggle();
    updateHumanSingleMartingalePanel();
    updateHumanRfMartingalePanel();
    maybeAutoFormulaX();
  }

  async function onActivate() {
    bindHumanDropdownPanels(byId("profileContainer"));
    startPolling();
    try{
      if(typeof refreshHumanKeepAliveUI === "function") await refreshHumanKeepAliveUI();
    }catch(e){}
    refreshHumanManualContracts(false);
    syncHumanRFAllowEqualsToggle();
    updateHumanSingleMartingalePanel();
    updateHumanRfMartingalePanel();
    maybeAutoFormulaX();
  }

  async function onDeactivate() {
    stopPolling();
    clearStatusRenderTimer();
    socketHooked = false;
  }

  if (typeof window.registerProfileModule === "function") {
    window.registerProfileModule(PROFILE, {
      onMount,
      afterLoadProfileUI,
      onActivate,
      onDeactivate
    });
  } else {
    window.ProfileModules = window.ProfileModules || {};
    window.ProfileModules[PROFILE] = { onMount, afterLoadProfileUI, onActivate, onDeactivate };
  }
})();
