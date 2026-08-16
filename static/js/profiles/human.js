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
  const HUMAN_PARITY_DIGIT_SEQUENCE = [];
  let humanParityLastTickKey = "";
  const HUMAN_PARITY_DIGIT_LIMIT = 24;

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
    ASIANS_UP: "Asians Up",
    ASIANS_DOWN: "Asians Down",
  };
  const HUMAN_DUAL_MARKET_LABELS = Object.assign({
    RISE: "Rise",
    FALL: "Fall",
    EVEN: "Even",
    ODD: "Odd",
  }, HUMAN_SPECIAL_LABELS);
  const HUMAN_DUAL_FALLBACK_MARKETS = [
    ["R_10", "Volatility 10"],
    ["R_25", "Volatility 25"],
    ["R_50", "Volatility 50"],
    ["R_75", "Volatility 75"],
    ["R_100", "Volatility 100"],
    ["1HZ10V", "Volatility 10 (1s)"],
    ["1HZ25V", "Volatility 25 (1s)"],
    ["1HZ50V", "Volatility 50 (1s)"],
    ["1HZ75V", "Volatility 75 (1s)"],
    ["1HZ100V", "Volatility 100 (1s)"],
    ["stpRNG", "Step Index"],
    ["stpRNG2", "Step 200"],
    ["stpRNG3", "Step 300"],
    ["stpRNG4", "Step 400"],
    ["stpRNG5", "Step 500"],
  ];
  const HUMAN_SINGLE_MARTINGALE_PAIR_CONFIGS = {
    ONLY_UPS_DOWNS: {
      label: "Only Ups + Only Downs",
      actions: ["ONLY_UPS", "ONLY_DOWNS"],
    },
    ASIANS_UP_DOWNS: {
      label: "Asians Up + Asians Down",
      actions: ["ASIANS_UP", "ASIANS_DOWN"],
    },
    HIGH_LOW_TICKS: {
      label: "High Tick + Low Tick",
      actions: ["HIGH_TICK", "LOW_TICK"],
    },
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
    pairSteps: {},
    inProgress: false,
    pendingAction: "",
    pendingContractId: "",
    pendingContracts: {},
    pendingExpected: 0,
    pendingSettled: 0,
    pendingPair: false,
    pendingMartingale: false,
    pendingStake: 0,
    running: false,
    stopRequested: false,
    restartTimer: null,
    spacingWait: 0,
    oneWinStopTriggered: false,
    lastResult: "none",
    status: "Ready",
  };
  const HUMAN_RF_MARTINGALE_STATE = {
    direction: "RISE",
    enabled: false,
    step: 1,
    riseDoubleCount: 0,
    fallDoubleCount: 0,
    inProgress: false,
    pendingDirection: "",
    pendingDirections: {},
    settledCount: 0,
    pendingContractId: "",
    pendingMartingale: false,
    pendingStake: 0,
    riseBaseStake: 0.35,
    fallBaseStake: 0.35,
    riseStake: 0.35,
    fallStake: 0.35,
    multiplier: 2,
    running: false,
    stopRequested: false,
    restartTimer: null,
    spacingWait: 0,
    lastResult: "none",
    status: "Ready",
  };
  const HUMAN_PARITY_MARTINGALE_STATE = {
    running: false,
    inFlight: false,
    mode: "EVEN",
    runId: "",
    evenBaseStake: 1,
    oddBaseStake: 1,
    evenStake: 1,
    oddStake: 1,
    multiplier: 2,
    pending: {},
    settled: 0,
    currentBatch: null,
    sessionPnl: 0,
    takeProfit: 0,
    stopLoss: 0,
    limitHit: false,
    plusRecoveryPending: false,
    capAfterThreeDoubles: false,
    doubleLimit: 0,
    evenDoubleCount: 0,
    oddDoubleCount: 0,
    lastResult: "none",
    status: "Ready",
    restartTimer: null,
    completionTimer: null,
    spacingWait: 0,
    marketSwitcherEnabled: false,
    marketSwitcherIndex: 0,
    marketSwitcherMarkets: [],
    activeMarket: "",
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
    const asiansPairBtn = byId("humanAsiansPairBtn");
    if(asiansPairBtn){
      const asianUp = actions.ASIANS_UP || {};
      const asianDown = actions.ASIANS_DOWN || {};
      const asiansPairAvailable = !!asianUp.available && !!asianDown.available;
      asiansPairBtn.disabled = humanManualLoading || !asiansPairAvailable;
      asiansPairBtn.style.opacity = asiansPairAvailable ? "1" : "0.45";
      asiansPairBtn.title = asiansPairAvailable
        ? `${asianUp.contract_type || asianUp.contract_display || "Asians Up"} + ${asianDown.contract_type || asianDown.contract_display || "Asians Down"}`
        : "Asians Up + Asians Down is not available for the selected market.";
    }

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

  function normalizeHumanParityMode(value){
    const mode = String(value || "EVEN").toUpperCase();
    return ["ODD", "EVEN_ODD", "EVEN_PLUS", "ODD_PLUS"].includes(mode) ? mode : "EVEN";
  }

  function humanParityExecutionSide(modeValue){
    const mode = normalizeHumanParityMode(modeValue);
    return mode === "ODD" || mode === "ODD_PLUS" ? "ODD" : "EVEN";
  }

  function isHumanParityPlusMode(modeValue){
    const mode = normalizeHumanParityMode(modeValue);
    return mode === "EVEN_PLUS" || mode === "ODD_PLUS";
  }

  function readHumanParityNumber(id, fallback, min, max){
    const el = byId(id);
    let value = Number(el && el.value);
    if(!Number.isFinite(value)) value = fallback;
    if(Number.isFinite(min)) value = Math.max(min, value);
    if(Number.isFinite(max)) value = Math.min(max, value);
    return value;
  }

  function readHumanParityInteger(id, fallback, min, max){
    return Math.round(readHumanParityNumber(id, fallback, min, max));
  }

  function readHumanTickSpacing(id, fallback){
    return readHumanParityInteger(id, fallback || 1, 1, 10);
  }

  function getCurrentHumanMarketSymbol(){
    try{
      if(typeof window.getConfirmedMarketSymbol === "function") return String(window.getConfirmedMarketSymbol() || "R_10").trim() || "R_10";
    }catch(e){}
    const symbolEl = byId("symbol");
    return String((symbolEl && (symbolEl.dataset.confirmedSymbol || symbolEl.value)) || "R_10").trim() || "R_10";
  }

  function getHumanParityMarketOptions(){
    const symbolEl = byId("symbol");
    const seen = {};
    const out = [];
    if(symbolEl && symbolEl.options){
      Array.from(symbolEl.options).forEach((opt) => {
        const symbol = String(opt && opt.value || "").trim();
        if(symbol && !seen[symbol]){
          seen[symbol] = true;
          out.push(symbol);
        }
      });
    }
    if(!out.length){
      HUMAN_DUAL_FALLBACK_MARKETS.forEach((row) => {
        const symbol = String((row && row[0]) || "").trim();
        if(symbol && !seen[symbol]){
          seen[symbol] = true;
          out.push(symbol);
        }
      });
    }
    return out.length ? out : ["R_10"];
  }

  function buildHumanParityMarketRotation(startSymbol){
    const current = String(startSymbol || getCurrentHumanMarketSymbol()).trim() || "R_10";
    const markets = getHumanParityMarketOptions();
    const index = markets.findIndex((symbol) => String(symbol).toUpperCase() === current.toUpperCase());
    if(index < 0) return [current].concat(markets.filter((symbol) => String(symbol).toUpperCase() !== current.toUpperCase()));
    return markets.slice(index).concat(markets.slice(0, index));
  }

  function resetHumanParityMarketSwitcher(){
    const st = HUMAN_PARITY_MARTINGALE_STATE;
    st.marketSwitcherIndex = 0;
    st.marketSwitcherMarkets = buildHumanParityMarketRotation(getCurrentHumanMarketSymbol());
    st.activeMarket = "";
  }

  function nextHumanParityTradeMarket(){
    const st = HUMAN_PARITY_MARTINGALE_STATE;
    if(!st.marketSwitcherEnabled) return getCurrentHumanMarketSymbol();
    if(!Array.isArray(st.marketSwitcherMarkets) || !st.marketSwitcherMarkets.length){
      resetHumanParityMarketSwitcher();
    }
    const markets = st.marketSwitcherMarkets || [];
    const index = Math.max(0, Math.floor(Number(st.marketSwitcherIndex || 0))) % Math.max(1, markets.length);
    const symbol = markets[index] || getCurrentHumanMarketSymbol();
    st.marketSwitcherIndex = (index + 1) % Math.max(1, markets.length);
    st.activeMarket = symbol;
    return symbol;
  }

  function peekHumanParityNextMarket(){
    const st = HUMAN_PARITY_MARTINGALE_STATE;
    if(!st.marketSwitcherEnabled) return getCurrentHumanMarketSymbol();
    const markets = Array.isArray(st.marketSwitcherMarkets) && st.marketSwitcherMarkets.length
      ? st.marketSwitcherMarkets
      : buildHumanParityMarketRotation(getCurrentHumanMarketSymbol());
    const index = Math.max(0, Math.floor(Number(st.marketSwitcherIndex || 0))) % Math.max(1, markets.length);
    return markets[index] || getCurrentHumanMarketSymbol();
  }

  function processHumanMartingaleTickSpacing(){
    if(HUMAN_SINGLE_MARTINGALE_STATE.running && HUMAN_SINGLE_MARTINGALE_STATE.spacingWait > 0){
      HUMAN_SINGLE_MARTINGALE_STATE.spacingWait = Math.max(0, HUMAN_SINGLE_MARTINGALE_STATE.spacingWait - 1);
      if(HUMAN_SINGLE_MARTINGALE_STATE.spacingWait > 0){
        HUMAN_SINGLE_MARTINGALE_STATE.status = `Waiting ${HUMAN_SINGLE_MARTINGALE_STATE.spacingWait} tick(s) before next round`;
        updateHumanSingleMartingalePanel();
      }else if(!HUMAN_SINGLE_MARTINGALE_STATE.inProgress){
        HUMAN_SINGLE_MARTINGALE_STATE.status = "Next round starting";
        updateHumanSingleMartingalePanel();
        placeHumanSingleMartingaleTrade({ continuation: true });
      }
    }
    if(HUMAN_PARITY_MARTINGALE_STATE.running && HUMAN_PARITY_MARTINGALE_STATE.spacingWait > 0){
      HUMAN_PARITY_MARTINGALE_STATE.spacingWait = Math.max(0, HUMAN_PARITY_MARTINGALE_STATE.spacingWait - 1);
      if(HUMAN_PARITY_MARTINGALE_STATE.spacingWait > 0){
        HUMAN_PARITY_MARTINGALE_STATE.status = `Waiting ${HUMAN_PARITY_MARTINGALE_STATE.spacingWait} tick(s) before next round`;
        updateHumanParityMartingalePanel();
      }else if(!HUMAN_PARITY_MARTINGALE_STATE.inFlight){
        HUMAN_PARITY_MARTINGALE_STATE.status = "Next round starting";
        updateHumanParityMartingalePanel();
        sendHumanParityMartingaleRound();
      }
    }
    if(HUMAN_RF_MARTINGALE_STATE.running && HUMAN_RF_MARTINGALE_STATE.spacingWait > 0){
      HUMAN_RF_MARTINGALE_STATE.spacingWait = Math.max(0, HUMAN_RF_MARTINGALE_STATE.spacingWait - 1);
      if(HUMAN_RF_MARTINGALE_STATE.spacingWait > 0){
        HUMAN_RF_MARTINGALE_STATE.status = `Waiting ${HUMAN_RF_MARTINGALE_STATE.spacingWait} tick(s) before next round`;
        updateHumanRfMartingalePanel();
      }else if(!HUMAN_RF_MARTINGALE_STATE.inProgress){
        HUMAN_RF_MARTINGALE_STATE.status = "Next round starting";
        updateHumanRfMartingalePanel();
        placeHumanRfMartingaleTrade({ continuation: true });
      }
    }
  }

  function extractHumanParityDigit(payload){
    if(!payload) return null;
    const directFields = ["digit", "last_digit", "lastDigit"];
    for(const field of directFields){
      const value = Number(payload[field]);
      if(Number.isInteger(value) && value >= 0 && value <= 9) return value;
    }
    const nested = payload.tick || payload.data || payload.market || null;
    if(nested && nested !== payload){
      const nestedDigit = extractHumanParityDigit(nested);
      if(nestedDigit !== null) return nestedDigit;
    }
    const quote = payload.quote ?? payload.price ?? payload.value ?? payload.last_price ?? payload.lastPrice;
    if(quote === undefined || quote === null || quote === "") return null;
    const text = String(quote).replace(/[^0-9]/g, "");
    if(!text) return null;
    const digit = Number(text.slice(-1));
    return Number.isInteger(digit) && digit >= 0 && digit <= 9 ? digit : null;
  }

  function resolveHumanParityResultSide(payload){
    if(!payload) return "";
    const candidates = [
      payload.leg_action,
      payload.action,
      payload.type,
      payload.contract_type,
      payload.deriv_contract_type,
      payload.label,
      payload.trade_type,
    ];
    for(const value of candidates){
      const text = String(value || "").toUpperCase().replace(/[_-]+/g, " ").trim();
      const compact = text.replace(/[^A-Z]/g, "");
      if(compact === "EVEN" || compact === "DIGITEVEN" || /\bEVEN\b/.test(text)) return "EVEN";
      if(compact === "ODD" || compact === "DIGITODD" || /\bODD\b/.test(text)) return "ODD";
    }
    return "";
  }

  function renderHumanParityDigitScreen(){
    const wrap = byId("humanParityDigitScreen");
    const lastEl = byId("humanParityDigitLast");
    if(!wrap) return;
    wrap.innerHTML = "";
    if(lastEl){
      const last = HUMAN_PARITY_DIGIT_SEQUENCE[HUMAN_PARITY_DIGIT_SEQUENCE.length - 1];
      lastEl.textContent = last ? `${last.label} ${last.digit}` : "Waiting...";
      lastEl.style.color = last ? (last.label === "E" ? "#86efac" : "#fecaca") : "#e5e7eb";
    }
    if(!HUMAN_PARITY_DIGIT_SEQUENCE.length){
      const empty = document.createElement("span");
      empty.textContent = "Collecting digits...";
      empty.style.color = "#64748b";
      empty.style.fontSize = "11px";
      wrap.appendChild(empty);
      return;
    }
    HUMAN_PARITY_DIGIT_SEQUENCE.forEach((item) => {
      const box = document.createElement("span");
      const even = item.label === "E";
      box.textContent = item.label;
      box.title = `${even ? "Even" : "Odd"} digit ${item.digit}`;
      box.style.width = "22px";
      box.style.height = "22px";
      box.style.borderRadius = "6px";
      box.style.display = "inline-flex";
      box.style.alignItems = "center";
      box.style.justifyContent = "center";
      box.style.flex = "0 0 auto";
      box.style.fontSize = "12px";
      box.style.fontWeight = "950";
      box.style.color = even ? "#052e16" : "#fff7ed";
      box.style.background = even ? "#22c55e" : "#ef4444";
      box.style.boxShadow = even ? "0 0 12px rgba(34,197,94,.42)" : "0 0 12px rgba(239,68,68,.42)";
      wrap.appendChild(box);
    });
  }

  function updateHumanParityDigitScreen(payload){
    const digit = extractHumanParityDigit(payload);
    if(digit === null) return;
    const key = [
      payload && (payload.tick_count ?? payload.tickCount ?? payload.epoch ?? payload.time),
      payload && (payload.quote ?? payload.price ?? payload.value),
      digit,
    ].filter((part) => part !== undefined && part !== null && part !== "").join(":");
    if(key && key === humanParityLastTickKey) return;
    humanParityLastTickKey = key;
    HUMAN_PARITY_DIGIT_SEQUENCE.push({ digit, label: digit % 2 === 0 ? "E" : "O" });
    while(HUMAN_PARITY_DIGIT_SEQUENCE.length > HUMAN_PARITY_DIGIT_LIMIT){
      HUMAN_PARITY_DIGIT_SEQUENCE.shift();
    }
    renderHumanParityDigitScreen();
    processHumanMartingaleTickSpacing();
  }

  function resetHumanParityDigitScreen(){
    HUMAN_PARITY_DIGIT_SEQUENCE.length = 0;
    humanParityLastTickKey = "";
    renderHumanParityDigitScreen();
  }

  function readHumanParitySettings(){
    const modeEl = byId("humanParityMartingaleMode");
    const capToggleEl = byId("humanParityMartingaleCapToggle");
    const mode = normalizeHumanParityMode((modeEl && modeEl.value) || HUMAN_PARITY_MARTINGALE_STATE.mode);
    const startStake = Number(readHumanParityNumber("humanParityMartingaleStake", 1, 0.35, 1000000).toFixed(2));
    const multiplier = Number(readHumanParityNumber("humanParityMartingaleMultiplier", 2, 1, 100).toFixed(2));
    const duration = readHumanParityInteger("humanParityMartingaleDuration", 5, 1, 10);
    const tickSpacing = readHumanTickSpacing("humanParityMartingaleTickSpacing", 1);
    const takeProfit = Number(readHumanParityNumber("humanParityMartingaleTp", 0, 0, 100000000).toFixed(2));
    const stopLoss = Number(readHumanParityNumber("humanParityMartingaleSl", 0, 0, 100000000).toFixed(2));
    const doubleLimit = readHumanParityInteger("humanParityMartingaleDoubleLimit", capToggleEl && capToggleEl.checked ? 3 : 0, 0, 1000);
    const marketSwitcherEl = byId("humanParityMarketSwitcher");
    const marketSwitcherEnabled = !!(marketSwitcherEl && marketSwitcherEl.checked);
    const stakeEl = byId("humanParityMartingaleStake");
    const multEl = byId("humanParityMartingaleMultiplier");
    const durationEl = byId("humanParityMartingaleDuration");
    const spacingEl = byId("humanParityMartingaleTickSpacing");
    const tpEl = byId("humanParityMartingaleTp");
    const slEl = byId("humanParityMartingaleSl");
    const doubleLimitEl = byId("humanParityMartingaleDoubleLimit");
    const capAfterThreeDoubles = doubleLimit > 0;
    if(modeEl) modeEl.value = mode;
    if(stakeEl && String(stakeEl.value || "").trim() === "") stakeEl.value = startStake.toFixed(2);
    if(multEl && String(multEl.value || "").trim() === "") multEl.value = String(multiplier);
    if(durationEl) durationEl.value = String(duration);
    if(spacingEl) spacingEl.value = String(tickSpacing);
    if(tpEl && String(tpEl.value || "").trim() === "") tpEl.value = "0";
    if(slEl && String(slEl.value || "").trim() === "") slEl.value = "0";
    if(doubleLimitEl && String(doubleLimitEl.value || "").trim() === "") doubleLimitEl.value = "0";
    return { mode, startStake, multiplier, duration, tickSpacing, capAfterThreeDoubles, doubleLimit, takeProfit, stopLoss, marketSwitcherEnabled };
  }

  function updateHumanParityMartingalePanel(){
    const settings = readHumanParitySettings();
    const mode = settings.mode;
    HUMAN_PARITY_MARTINGALE_STATE.mode = mode;
    HUMAN_PARITY_MARTINGALE_STATE.multiplier = settings.multiplier;
    HUMAN_PARITY_MARTINGALE_STATE.capAfterThreeDoubles = !!settings.capAfterThreeDoubles;
    HUMAN_PARITY_MARTINGALE_STATE.doubleLimit = settings.doubleLimit;
    HUMAN_PARITY_MARTINGALE_STATE.takeProfit = settings.takeProfit;
    HUMAN_PARITY_MARTINGALE_STATE.stopLoss = settings.stopLoss;
    if(HUMAN_PARITY_MARTINGALE_STATE.marketSwitcherEnabled !== settings.marketSwitcherEnabled && !HUMAN_PARITY_MARTINGALE_STATE.running && !HUMAN_PARITY_MARTINGALE_STATE.inFlight){
      HUMAN_PARITY_MARTINGALE_STATE.marketSwitcherEnabled = settings.marketSwitcherEnabled;
      resetHumanParityMarketSwitcher();
    }else{
      HUMAN_PARITY_MARTINGALE_STATE.marketSwitcherEnabled = settings.marketSwitcherEnabled;
    }
    if(!HUMAN_PARITY_MARTINGALE_STATE.running && !HUMAN_PARITY_MARTINGALE_STATE.inFlight && !HUMAN_PARITY_MARTINGALE_STATE.runId){
      HUMAN_PARITY_MARTINGALE_STATE.evenBaseStake = settings.startStake;
      HUMAN_PARITY_MARTINGALE_STATE.oddBaseStake = settings.startStake;
      HUMAN_PARITY_MARTINGALE_STATE.evenStake = settings.startStake;
      HUMAN_PARITY_MARTINGALE_STATE.oddStake = settings.startStake;
    }
    const pendingActive = Object.values(HUMAN_PARITY_MARTINGALE_STATE.pending || {}).some((item) => item && !item.result);
    const startBtn = byId("humanParityMartingaleStartBtn");
    const stopBtn = byId("humanParityMartingaleStopBtn");
    if(startBtn){
      startBtn.disabled = !!HUMAN_PARITY_MARTINGALE_STATE.running || !!HUMAN_PARITY_MARTINGALE_STATE.inFlight || pendingActive;
      startBtn.style.opacity = startBtn.disabled ? "0.6" : "1";
    }
    if(stopBtn){
      const canStop = !!HUMAN_PARITY_MARTINGALE_STATE.running || !!HUMAN_PARITY_MARTINGALE_STATE.inFlight || pendingActive;
      stopBtn.disabled = !canStop;
      stopBtn.style.opacity = canStop ? "1" : "0.6";
    }
    const statusEl = byId("humanParityMartingaleStatus");
    if(statusEl){
      const modeLabel = mode === "EVEN_ODD"
        ? "Even + Odd"
        : mode === "ODD"
          ? "Odd"
          : mode === "EVEN_PLUS"
            ? "Even Plus"
            : mode === "ODD_PLUS"
              ? "Odd Plus"
              : "Even";
      const modeDetail = isHumanParityPlusMode(mode)
        ? "1-step 2x recovery"
        : `${settings.multiplier}x${settings.doubleLimit > 0 ? ` • limit ${settings.doubleLimit} double-up(s)` : ""}`;
      const limits = [
        settings.takeProfit > 0 ? `TP ${money(settings.takeProfit)}` : "TP off",
        settings.stopLoss > 0 ? `SL ${money(settings.stopLoss)}` : "SL off",
        `Session P/L ${money(HUMAN_PARITY_MARTINGALE_STATE.sessionPnl || 0)}`,
      ].join(" • ");
      const marketLine = HUMAN_PARITY_MARTINGALE_STATE.marketSwitcherEnabled
        ? `Market Switcher ON • Current ${HUMAN_PARITY_MARTINGALE_STATE.activeMarket || "none"} • Next ${peekHumanParityNextMarket()}`
        : `Market Switcher OFF • Market ${getCurrentHumanMarketSymbol()}`;
      statusEl.innerHTML = [
        `${HUMAN_PARITY_MARTINGALE_STATE.status || "Ready"} • ${modeLabel} • ${modeDetail}`,
        `Even stake ${money(HUMAN_PARITY_MARTINGALE_STATE.evenStake || 1)} • Odd stake ${money(HUMAN_PARITY_MARTINGALE_STATE.oddStake || 1)}`,
        marketLine,
        limits,
        `Pending: ${Object.keys(HUMAN_PARITY_MARTINGALE_STATE.pending || {}).join(" + ") || "none"} • Last result: ${HUMAN_PARITY_MARTINGALE_STATE.lastResult || "none"}`,
        `Double count • Even ${Number(HUMAN_PARITY_MARTINGALE_STATE.evenDoubleCount || 0)} • Odd ${Number(HUMAN_PARITY_MARTINGALE_STATE.oddDoubleCount || 0)}`,
      ].join("<br>");
      statusEl.style.color = HUMAN_PARITY_MARTINGALE_STATE.limitHit ? "#fbbf24" : (HUMAN_PARITY_MARTINGALE_STATE.inFlight ? "#fbbf24" : "#94a3b8");
    }
  }

  function resetHumanParityMartingaleRun(){
    const settings = readHumanParitySettings();
    HUMAN_PARITY_MARTINGALE_STATE.mode = settings.mode;
    HUMAN_PARITY_MARTINGALE_STATE.runId = `hpm_${Date.now()}_${Math.floor(Math.random() * 10000)}`;
    HUMAN_PARITY_MARTINGALE_STATE.evenBaseStake = settings.startStake;
    HUMAN_PARITY_MARTINGALE_STATE.oddBaseStake = settings.startStake;
    HUMAN_PARITY_MARTINGALE_STATE.evenStake = settings.startStake;
    HUMAN_PARITY_MARTINGALE_STATE.oddStake = settings.startStake;
    HUMAN_PARITY_MARTINGALE_STATE.multiplier = settings.multiplier;
    HUMAN_PARITY_MARTINGALE_STATE.pending = {};
    HUMAN_PARITY_MARTINGALE_STATE.settled = 0;
    HUMAN_PARITY_MARTINGALE_STATE.currentBatch = null;
    HUMAN_PARITY_MARTINGALE_STATE.sessionPnl = 0;
    HUMAN_PARITY_MARTINGALE_STATE.takeProfit = settings.takeProfit;
    HUMAN_PARITY_MARTINGALE_STATE.stopLoss = settings.stopLoss;
    HUMAN_PARITY_MARTINGALE_STATE.marketSwitcherEnabled = settings.marketSwitcherEnabled;
    resetHumanParityMarketSwitcher();
    HUMAN_PARITY_MARTINGALE_STATE.limitHit = false;
    HUMAN_PARITY_MARTINGALE_STATE.plusRecoveryPending = false;
    HUMAN_PARITY_MARTINGALE_STATE.capAfterThreeDoubles = !!settings.capAfterThreeDoubles;
    HUMAN_PARITY_MARTINGALE_STATE.doubleLimit = settings.doubleLimit;
    HUMAN_PARITY_MARTINGALE_STATE.evenDoubleCount = 0;
    HUMAN_PARITY_MARTINGALE_STATE.oddDoubleCount = 0;
    HUMAN_PARITY_MARTINGALE_STATE.lastResult = "none";
    HUMAN_PARITY_MARTINGALE_STATE.status = "Ready";
  }

  function getHumanParityMartingalePlan(){
    const mode = normalizeHumanParityMode(HUMAN_PARITY_MARTINGALE_STATE.mode);
    if(mode === "EVEN_ODD"){
      return [
        { side: "EVEN", stake: Math.max(0.35, Number(HUMAN_PARITY_MARTINGALE_STATE.evenStake || 1)) },
        { side: "ODD", stake: Math.max(0.35, Number(HUMAN_PARITY_MARTINGALE_STATE.oddStake || 1)) },
      ];
    }
    const side = humanParityExecutionSide(mode);
    const isPlus = isHumanParityPlusMode(mode);
    const liveStake = side === "ODD" ? HUMAN_PARITY_MARTINGALE_STATE.oddStake : HUMAN_PARITY_MARTINGALE_STATE.evenStake;
    const baseStake = side === "ODD" ? HUMAN_PARITY_MARTINGALE_STATE.oddBaseStake : HUMAN_PARITY_MARTINGALE_STATE.evenBaseStake;
    const stake = isPlus && HUMAN_PARITY_MARTINGALE_STATE.plusRecoveryPending
      ? Number((Math.max(0.35, Number(baseStake || 1)) * 2).toFixed(2))
      : Math.max(0.35, Number(liveStake || baseStake || 1));
    return [{ side, stake: Math.max(0.35, Number(stake || baseStake || 1)), plusMode: isPlus, recoveryTrade: isPlus && HUMAN_PARITY_MARTINGALE_STATE.plusRecoveryPending }];
  }

  function purgeHumanParityBatchLegRows(batch){
    return;
  }

  function renderHumanParityBatchHistory(batch, pending){
    return;
  }

  function removeHumanParitySyntheticBatchRows(){
    try{
      if(typeof tradeStore === "undefined" || !tradeStore || !Array.isArray(tradeStore[PROFILE])) return;
      const before = tradeStore[PROFILE].length;
      tradeStore[PROFILE] = tradeStore[PROFILE].filter((item) => {
        return String(item && item.mode || "") !== "human_parity_even_odd_visible";
      });
      if(tradeStore[PROFILE].length !== before){
        if(typeof persistTradeHistoryCache === "function") persistTradeHistoryCache();
        if(typeof renderTradeList === "function" && typeof activeProfile !== "undefined" && String(activeProfile || "").toUpperCase() === PROFILE) renderTradeList(PROFILE);
      }
    }catch(e){}
  }

  function clearHumanParityBatchCompletionTimer(){
    const st = HUMAN_PARITY_MARTINGALE_STATE;
    if(st.completionTimer){
      clearTimeout(st.completionTimer);
      st.completionTimer = null;
    }
  }

  function finalizeHumanParityBatchByTimeout(batchId){
    const st = HUMAN_PARITY_MARTINGALE_STATE;
    if(!st.currentBatch || String(st.currentBatch.id || "") !== String(batchId || "")) return;
    const expected = Object.keys(st.pending || {}).length || 2;
    if(st.settled >= expected) return;
    clearHumanParityBatchCompletionTimer();
    const missing = Object.keys(st.pending || {}).filter((side) => {
      const item = st.pending && st.pending[side];
      return item && !item.result;
    });
    renderHumanParityBatchHistory(st.currentBatch, true);
    st.status = `Waiting for delayed ${missing.join(" + ") || "Even+Odd"} result.`;
    updateHumanParityMartingalePanel();
    if(st.running && st.runId && !st.inFlight){
      const retryMs = 5000;
      st.completionTimer = setTimeout(() => {
        st.completionTimer = null;
        finalizeHumanParityBatchByTimeout(batchId);
      }, retryMs);
    }
  }

  function scheduleHumanParityBatchFallback(batch){
    if(!batch || !batch.id) return;
    clearHumanParityBatchCompletionTimer();
    const st = HUMAN_PARITY_MARTINGALE_STATE;
    const duration = Math.max(1, Math.floor(Number(batch.duration || 5)));
    const waitMs = Math.max(7000, (duration * 1200) + 7000);
    st.completionTimer = setTimeout(() => {
      st.completionTimer = null;
      finalizeHumanParityBatchByTimeout(batch.id);
    }, waitMs);
  }

  function clearHumanParityVisibleBatch(){
    clearHumanParityBatchCompletionTimer();
    HUMAN_PARITY_MARTINGALE_STATE.currentBatch = null;
  }

  async function sendHumanParityMartingaleRound(){
    const st = HUMAN_PARITY_MARTINGALE_STATE;
    if(!st.running || st.inFlight) return;
    const plan = getHumanParityMartingalePlan();
    if(!plan.length) return;
    const duration = readHumanParityInteger("humanParityMartingaleDuration", 5, 1, 10);
    const pairMode = normalizeHumanParityMode(st.mode) === "EVEN_ODD";
    const tradeMarket = nextHumanParityTradeMarket();
    const batchId = pairMode ? `HUMAN-EVENODD-${Date.now()}-${Math.floor(Math.random() * 10000)}` : "";
    const batchStake = plan.reduce((sum, leg) => sum + Number(leg.stake || 0), 0);
    st.spacingWait = 0;
    st.inFlight = true;
    st.pending = {};
    st.settled = 0;
    plan.forEach((leg) => { st.pending[leg.side] = { stake: leg.stake, result: "", symbol: tradeMarket }; });
    if(pairMode){
      st.currentBatch = {
        id: batchId,
        mode: `human_parity_martingale:${st.runId}`,
        totalStake: Number(batchStake.toFixed(2)),
        totalProfit: 0,
        exitDigits: [],
        duration,
        symbol: tradeMarket,
        time: new Date().toLocaleTimeString(),
      };
    }else{
      clearHumanParityVisibleBatch();
    }
    st.status = `Sending ${plan.map((leg) => `${leg.side} ${money(leg.stake)}`).join(" + ")} on ${tradeMarket}`;
    updateHumanParityMartingalePanel();
    try{
      const payload = {
        side: pairMode ? "EVEN_ODD" : humanParityExecutionSide(st.mode),
        stake: plan[0].stake,
        even_stake: (plan.find((leg) => leg.side === "EVEN") || {}).stake,
        odd_stake: (plan.find((leg) => leg.side === "ODD") || {}).stake,
        symbol: tradeMarket,
        duration,
        duration_unit: "t",
        mode: `human_parity_martingale:${st.runId}`,
        batch_id: batchId,
        batch_label: "Even+Odd",
        batch_stake: Number(batchStake.toFixed(2)),
      };
      await postJSON("/human_parity_trade", payload);
      st.status = `Running. Waiting for ${plan.length} result(s).`;
    }catch(e){
      if(st.marketSwitcherEnabled && Array.isArray(st.marketSwitcherMarkets) && st.marketSwitcherMarkets.length){
        st.marketSwitcherIndex = (Math.max(0, Number(st.marketSwitcherIndex || 0)) - 1 + st.marketSwitcherMarkets.length) % st.marketSwitcherMarkets.length;
        st.activeMarket = "";
      }
      clearHumanParityVisibleBatch();
      st.running = false;
      st.runId = "";
      st.plusRecoveryPending = false;
      st.status = (e && e.message) || "Even/Odd martingale trade failed";
      if(typeof showToast === "function") showToast(st.status, "error");
    }finally{
      st.inFlight = false;
      updateHumanParityMartingalePanel();
    }
  }

  function scheduleHumanParityMartingaleRound(delayMs){
    const st = HUMAN_PARITY_MARTINGALE_STATE;
    if(!st.running || st.inFlight || st.restartTimer) return;
    const spacing = readHumanTickSpacing("humanParityMartingaleTickSpacing", 1);
    st.spacingWait = spacing;
    st.status = `Waiting ${spacing} tick(s) before next round`;
    updateHumanParityMartingalePanel();
  }

  function applyHumanParityTpSlAfterResult(profitValue){
    const st = HUMAN_PARITY_MARTINGALE_STATE;
    const profit = Number(profitValue);
    if(Number.isFinite(profit)){
      st.sessionPnl = Number((Number(st.sessionPnl || 0) + profit).toFixed(2));
    }
    if(st.limitHit) return true;
    const settings = readHumanParitySettings();
    st.takeProfit = settings.takeProfit;
    st.stopLoss = settings.stopLoss;
    let reason = "";
    if(settings.takeProfit > 0 && Number(st.sessionPnl || 0) >= settings.takeProfit){
      reason = `TP reached at ${money(st.sessionPnl)}`;
    }else if(settings.stopLoss > 0 && Number(st.sessionPnl || 0) <= -Math.abs(settings.stopLoss)){
      reason = `SL reached at ${money(st.sessionPnl)}`;
    }
    if(!reason) return false;
    st.running = false;
    st.spacingWait = 0;
    st.limitHit = true;
    st.status = `${reason}. Martingale stopped.`;
    if(st.restartTimer){
      clearTimeout(st.restartTimer);
      st.restartTimer = null;
    }
    if(typeof showToast === "function") showToast(`HUMAN Even/Odd ${reason}. Martingale stopped.`, settings.takeProfit > 0 && Number(st.sessionPnl || 0) >= settings.takeProfit ? "success" : "error");
    return true;
  }

  function updateHumanParityMartingaleFromResult(payload){
    const st = HUMAN_PARITY_MARTINGALE_STATE;
    if(!payload || String(payload.profile || "").toUpperCase() !== PROFILE || !st.runId) return;
    if(String(payload.mode || "") !== `human_parity_martingale:${st.runId}`) return;
    const contractId = payload.contract_id || payload.buy_contract_id || payload.id;
    let side = resolveHumanParityResultSide(payload);
    if(!side && contractId){
      const contractKey = String(contractId);
      side = Object.keys(st.pending || {}).find((key) => {
        const item = st.pending && st.pending[key];
        return item && String(item.contractId || "") === contractKey;
      }) || "";
    }
    if(side !== "EVEN" && side !== "ODD") return;
    const pending = st.pending && st.pending[side];
    if(!pending || pending.result) return;
    const outcome = resolveHumanTradeOutcome(payload);
    if(!outcome) return;
    pending.result = outcome;
    st.settled = Object.values(st.pending || {}).filter((item) => item && item.result).length;
    const stake = Math.max(0.35, Number(pending.stake || (side === "EVEN" ? st.evenStake : st.oddStake) || 1));
    const resultProfit = humanTradeNumber(payload, ["profit", "profit_value", "pnl", "net_profit", "result_profit"]);
    const limitReached = applyHumanParityTpSlAfterResult(resultProfit);
    if(st.mode === "EVEN_ODD" && st.currentBatch){
      if(Number.isFinite(resultProfit)){
        st.currentBatch.totalProfit = Number((Number(st.currentBatch.totalProfit || 0) + resultProfit).toFixed(2));
      }
      const exitDigit = extractHumanParityDigit(payload);
      if(exitDigit !== null){
        st.currentBatch.exitDigits = Array.isArray(st.currentBatch.exitDigits) ? st.currentBatch.exitDigits : [];
        st.currentBatch.exitDigits.push(exitDigit);
      }
    }
    const counterKey = side === "EVEN" ? "evenDoubleCount" : "oddDoubleCount";
    const baseStake = Number(Math.max(0.35, Number(side === "EVEN" ? st.evenBaseStake : st.oddBaseStake) || 1).toFixed(2));
    let capResetApplied = false;
    if(outcome === "WIN"){
      if(side === "EVEN") st.evenStake = Number((st.evenBaseStake || 1).toFixed(2));
      if(side === "ODD") st.oddStake = Number((st.oddBaseStake || 1).toFixed(2));
      st[counterKey] = 0;
      if(isHumanParityPlusMode(st.mode)){
        st.plusRecoveryPending = false;
      }else if(st.mode !== "EVEN_ODD"){
        st.running = false;
        st.runId = "";
        st.pending = {};
        st.settled = 0;
        if(!limitReached) st.status = `${side} won. Martingale stopped.`;
        st.lastResult = `${side} WIN at ${money(stake)}`;
        updateHumanParityMartingalePanel();
        if(typeof showToast === "function") showToast(`HUMAN ${side} martingale won and stopped`, "success");
        return;
      }
    }else{
      if(isHumanParityPlusMode(st.mode)){
        if(st.plusRecoveryPending){
          st.plusRecoveryPending = false;
          if(side === "EVEN") st.evenStake = Number((st.evenBaseStake || 1).toFixed(2));
          if(side === "ODD") st.oddStake = Number((st.oddBaseStake || 1).toFixed(2));
        }else{
          st.plusRecoveryPending = true;
          const next = Number((baseStake * 2).toFixed(2));
          if(side === "EVEN") st.evenStake = next;
          if(side === "ODD") st.oddStake = next;
        }
      }else{
        const currentDoubleCount = Math.max(0, Number(st[counterKey] || 0));
        const doubleLimit = Math.max(0, Math.floor(Number(st.doubleLimit || 0)));
        if(doubleLimit > 0 && currentDoubleCount >= doubleLimit){
          if(side === "EVEN") st.evenStake = baseStake;
          if(side === "ODD") st.oddStake = baseStake;
          st[counterKey] = 0;
          st.lastResult = `${side} LOSS at ${money(stake)} • double-up limit ${doubleLimit} reached, reset to base`;
          capResetApplied = true;
        }else{
          const next = Number((stake * Math.max(1, Number(st.multiplier || 2))).toFixed(2));
          if(side === "EVEN") st.evenStake = next;
          if(side === "ODD") st.oddStake = next;
          st[counterKey] = currentDoubleCount + 1;
        }
      }
    }
    if(!capResetApplied){
      st.lastResult = `${side} ${outcome} at ${money(stake)}`;
    }
    const expected = Object.keys(st.pending || {}).length;
    if(!st.limitHit){
      st.status = st.running ? `Running. Settled ${st.settled}/${expected}.` : "Stopped";
    }
    updateHumanParityMartingalePanel();
    if(!st.running && st.limitHit && expected > 0 && st.settled >= expected){
      if(st.mode === "EVEN_ODD" && st.currentBatch){
        clearHumanParityBatchCompletionTimer();
        st.currentBatch = null;
      }
      st.pending = {};
      st.settled = 0;
      st.runId = "";
      updateHumanParityMartingalePanel();
      return;
    }
    if(st.running && expected > 0 && st.settled >= expected){
      if(st.mode === "EVEN_ODD" && st.currentBatch){
        clearHumanParityBatchCompletionTimer();
        st.currentBatch = null;
      }
      st.pending = {};
      st.settled = 0;
      st.status = "Next round queued";
      updateHumanParityMartingalePanel();
      scheduleHumanParityMartingaleRound(450);
    }
  }

  function startHumanParityMartingale(){
    const st = HUMAN_PARITY_MARTINGALE_STATE;
    if(st.running || st.inFlight) return;
    resetHumanParityMartingaleRun();
    st.running = true;
    st.status = "Starting";
    updateHumanParityMartingalePanel();
    sendHumanParityMartingaleRound();
  }

  function stopHumanParityMartingale(){
    const st = HUMAN_PARITY_MARTINGALE_STATE;
    st.running = false;
    st.status = "Stopped";
    st.runId = "";
    st.spacingWait = 0;
    st.plusRecoveryPending = false;
    st.limitHit = false;
    st.evenDoubleCount = 0;
    st.oddDoubleCount = 0;
    st.pending = {};
    st.settled = 0;
    clearHumanParityBatchCompletionTimer();
    if(st.restartTimer){
      clearTimeout(st.restartTimer);
      st.restartTimer = null;
    }
    updateHumanParityMartingalePanel();
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
    if(opts.symbol !== undefined && opts.symbol !== null && String(opts.symbol).trim()){
      payload.symbol = String(opts.symbol).trim();
    }
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

  async function placeHumanManualPairAction(actions, optionsByAction, metaOptions){
    const keys = Array.isArray(actions) ? actions.map((item) => String(item || "").toUpperCase()).filter(Boolean) : [];
    if(!keys.length) throw new Error("No HUMAN pair actions provided.");
    if(!humanManualContracts){
      await refreshHumanManualContracts(false);
    }
    keys.forEach((key) => {
      const actionInfo = (humanManualContracts || {})[key] || {};
      if(!actionInfo.available){
        throw new Error("This contract is not available for the selected market.");
      }
    });
    const payloadActions = keys.map((key) => readHumanManualPayload(key, (optionsByAction || {})[key] || {}));
    const meta = metaOptions || {};
    const totalStake = payloadActions.reduce((sum, item) => sum + Number(item.stake || 0), 0);
    const maxDuration = payloadActions.reduce((maxVal, item) => Math.max(maxVal, Number(item.duration_ticks || 0)), 0);
    const data = await guardMartha({
      profile: PROFILE,
      source: "human_manual_pair_contract",
      type: meta.type || "PAIR",
      label: meta.label || "HUMAN pair contract",
      stake: totalStake,
      duration: maxDuration || 2,
      duration_unit: "t",
      batch_count: payloadActions.length,
    }, ()=>postJSON("/human_manual_pair_trade", { actions: payloadActions }));
    if(isMarthaBlocked(data)) return data;
    if(!data || String(data.status || "").toLowerCase() !== "success"){
      throw new Error((data && (data.error || data.message)) || "HUMAN pair trade failed");
    }
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

  function buildHumanAsiansPairOptions(stakeOverride, durationOverride){
    const durationEl = byId("humanOnlyDuration");
    const minDur = durationEl ? Number(durationEl.min || 2) : 2;
    const maxDur = durationEl && durationEl.max ? Number(durationEl.max) : 1000000;
    const durationTicks = Math.round(clampNum(durationOverride !== undefined ? durationOverride : (durationEl ? durationEl.value : 2), minDur, maxDur, Math.max(2, minDur)));
    if(durationEl && durationOverride === undefined) durationEl.value = String(durationTicks);
    const stakeEl = byId("stake");
    const baseStake = clampNum(stakeOverride !== undefined ? stakeOverride : (stakeEl ? stakeEl.value : 1), 0.35, 1000000, 1);
    if(stakeEl && stakeOverride === undefined) stakeEl.value = String(baseStake);
    return {
      durationTicks,
      baseStake,
      pairOptions: {
        ASIANS_UP: { stake: baseStake, duration_ticks: durationTicks, quiet: true },
        ASIANS_DOWN: { stake: baseStake, duration_ticks: durationTicks, quiet: true },
      },
    };
  }

  async function placeHumanManualAsiansPair(opts){
    const settings = buildHumanAsiansPairOptions(opts && opts.stake, opts && opts.durationTicks);
    const data = await placeHumanManualPairAction(
      ["ASIANS_UP", "ASIANS_DOWN"],
      settings.pairOptions,
      {
        type: "ASIANS_UP_DOWNS",
        label: "HUMAN Asians Up + Asians Down",
      }
    );
    return Object.assign({}, settings, { data });
  }

  async function humanManualAsiansPairTrade(){
    try{
      const settings = await placeHumanManualAsiansPair();
      if(typeof showToast === "function") showToast(`HUMAN Asians Up + Asians Down sent at $${Number(settings.baseStake).toFixed(2)} each`, "success");
    }catch(e){
      if(typeof showToast === "function") showToast(e.message || "HUMAN Asians pair trade failed", "error");
    }
  }

  function getHumanCurrentMarketSymbol(){
    try{
      if(typeof window.getConfirmedMarketSymbol === "function"){
        const sym = window.getConfirmedMarketSymbol();
        if(sym) return String(sym);
      }
    }catch(e){}
    const source = byId("symbol");
    return String((source && source.value) || humanManualContractsSymbol || "R_10");
  }

  function getHumanDualMarketOptions(){
    const source = byId("symbol");
    const options = [];
    if(source && source.options && source.options.length){
      Array.from(source.options).forEach((opt) => {
        if(!opt || !opt.value) return;
        options.push([String(opt.value), String(opt.textContent || opt.value)]);
      });
    }
    return options.length ? options : HUMAN_DUAL_FALLBACK_MARKETS.slice();
  }

  function syncHumanDualMarketSelect(id, preferredSymbol){
    const sel = byId(id);
    if(!sel) return;
    const options = getHumanDualMarketOptions();
    const previous = sel.value || preferredSymbol || "";
    const signature = options.map((item) => item[0]).join("|");
    if(sel.dataset.humanDualMarketSignature !== signature){
      sel.innerHTML = "";
      options.forEach(([value, label]) => {
        const opt = document.createElement("option");
        opt.value = value;
        opt.textContent = label;
        sel.appendChild(opt);
      });
      sel.dataset.humanDualMarketSignature = signature;
    }
    const values = new Set(options.map((item) => item[0]));
    if(previous && values.has(previous)){
      sel.value = previous;
    }else if(preferredSymbol && values.has(preferredSymbol)){
      sel.value = preferredSymbol;
    }else if(options.length){
      sel.value = options[0][0];
    }
  }

  function populateHumanDualMarketSelects(){
    const current = getHumanCurrentMarketSymbol();
    const options = getHumanDualMarketOptions();
    const firstOther = (options.find((item) => item[0] !== current) || options[0] || [current])[0];
    syncHumanDualMarketSelect("humanDualMarketA", current);
    syncHumanDualMarketSelect("humanDualMarketB", firstOther);
    updateHumanDualMarketPanel();
  }

  function setHumanDualStake(side){
    const suffix = String(side || "A").toUpperCase() === "B" ? "B" : "A";
    const input = byId(`humanDualStake${suffix}`);
    const mainStake = byId("stake");
    if(!input) return;
    const source = mainStake && mainStake.value ? mainStake.value : input.value;
    const stake = clampNum(source || 0.35, 0.35, 1000000, 0.35);
    input.value = stake.toFixed(2).replace(/\.00$/, "");
    updateHumanDualMarketPanel();
  }

  function readHumanDualLeg(side){
    const suffix = String(side || "A").toUpperCase() === "B" ? "B" : "A";
    const symbolEl = byId(`humanDualMarket${suffix}`);
    const actionEl = byId(`humanDualTrade${suffix}`);
    const stakeEl = byId(`humanDualStake${suffix}`);
    const durationEl = byId(`humanDualDuration${suffix}`);
    const tickEl = byId(`humanDualSelectedTick${suffix}`);
    const symbol = String((symbolEl && symbolEl.value) || getHumanCurrentMarketSymbol()).trim();
    const action = String((actionEl && actionEl.value) || "RISE").toUpperCase();
    const stake = Number(clampNum(stakeEl ? stakeEl.value : 0.35, 0.35, 1000000, 0.35).toFixed(2));
    const minDuration = (action === "ONLY_UPS" || action === "ONLY_DOWNS") ? 2 : 1;
    const duration = Math.round(clampNum(durationEl ? durationEl.value : minDuration, minDuration, 1000, minDuration));
    const selectedTick = Math.round(clampNum(tickEl ? tickEl.value : 5, 1, 5, 5));
    if(stakeEl) stakeEl.value = stake.toFixed(2).replace(/\.00$/, "");
    if(durationEl) durationEl.value = String(duration);
    if(tickEl) tickEl.value = String(selectedTick);
    const payload = {
      symbol,
      action,
      stake,
      duration_ticks: duration,
      duration_unit: "t",
    };
    if(action === "HIGH_TICK" || action === "LOW_TICK"){
      payload.selected_tick = selectedTick;
    }
    return payload;
  }

  function updateHumanDualMarketPanel(){
    const status = byId("humanDualMarketStatus");
    const btn = byId("humanDualMarketPlaceBtn");
    if(!status && !btn) return;
    let message = "Ready. High/Low Tick uses selected tick; the other contracts use duration.";
    let color = "#94a3b8";
    try{
      const a = readHumanDualLeg("A");
      const b = readHumanDualLeg("B");
      const labelA = HUMAN_DUAL_MARKET_LABELS[a.action] || a.action.replaceAll("_", " ");
      const labelB = HUMAN_DUAL_MARKET_LABELS[b.action] || b.action.replaceAll("_", " ");
      const totalStake = Number(a.stake || 0) + Number(b.stake || 0);
      message = `${a.symbol} ${labelA} + ${b.symbol} ${labelB} • Total stake $${totalStake.toFixed(2)}`;
      if(a.symbol && b.symbol && a.symbol === b.symbol){
        message = "Choose two different markets for Dual Market Contracts.";
        color = "#fbbf24";
      }
    }catch(e){
      message = e.message || message;
      color = "#fca5a5";
    }
    if(status){
      status.textContent = message;
      status.style.color = color;
    }
    if(btn){
      btn.disabled = false;
      btn.style.opacity = "1";
      btn.style.cursor = "pointer";
    }
  }

  async function humanDualMarketPlaceBoth(){
    const btn = byId("humanDualMarketPlaceBtn");
    try{
      populateHumanDualMarketSelects();
      const legs = [readHumanDualLeg("A"), readHumanDualLeg("B")];
      if(!legs[0].symbol || !legs[1].symbol) throw new Error("Select both markets first.");
      if(legs[0].symbol === legs[1].symbol) throw new Error("Choose two different markets for this mode.");
      const totalStake = legs.reduce((sum, leg) => sum + Number(leg.stake || 0), 0);
      const maxDuration = legs.reduce((maxVal, leg) => Math.max(maxVal, Number(leg.duration_ticks || 0)), 0);
      if(btn){
        btn.disabled = true;
        btn.style.opacity = "0.65";
        btn.style.cursor = "wait";
      }
      const data = await guardMartha({
        profile: PROFILE,
        source: "human_dual_market_contracts",
        type: "DUAL_MARKET_CONTRACTS",
        label: "HUMAN Dual Market Contracts",
        stake: totalStake,
        duration: maxDuration || 1,
        duration_unit: "t",
        batch_count: 2,
      }, () => postJSON("/human_dual_market_contracts", { legs }));
      if(isMarthaBlocked(data)) return;
      if(!data || (data.status !== "success" && data.status !== "partial")){
        throw new Error((data && (data.error || data.message)) || "Dual Market Contracts failed");
      }
      const toastType = data.status === "success" ? "success" : "warn";
      if(typeof showToast === "function") showToast(data.message || "Dual Market Contracts sent", toastType);
      await fetchHumanRFStatus();
    }catch(e){
      if(typeof showToast === "function") showToast(e.message || "Dual Market Contracts failed", "error");
    }finally{
      if(btn){
        btn.disabled = false;
        btn.style.opacity = "1";
        btn.style.cursor = "pointer";
      }
      updateHumanDualMarketPanel();
    }
  }

  function isHumanTickPickAction(action){
    const key = String(action || "").toUpperCase();
    return key === "HIGH_TICK" || key === "LOW_TICK";
  }

  function getHumanSingleMartingalePairConfig(action){
    const key = String(action || "").toUpperCase();
    return HUMAN_SINGLE_MARTINGALE_PAIR_CONFIGS[key] || null;
  }

  function isHumanSingleMartingalePairAction(action){
    return !!getHumanSingleMartingalePairConfig(action);
  }

  function humanSingleMartingaleLabel(action){
    const pairConfig = getHumanSingleMartingalePairConfig(action);
    if(pairConfig) return pairConfig.label;
    return HUMAN_SPECIAL_LABELS[action] || String(action || "").replaceAll("_", " ");
  }

  function humanSingleMartingaleActionAvailable(action){
    if(!humanManualContracts) return false;
    const pairConfig = getHumanSingleMartingalePairConfig(action);
    if(pairConfig){
      return pairConfig.actions.every((key) => !!((humanManualContracts || {})[key] || {}).available);
    }
    return !!((humanManualContracts || {})[String(action || "").toUpperCase()] || {}).available;
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
    const pairConfig = getHumanSingleMartingalePairConfig(action);
    const startStake = Number(readHumanSingleMartingaleNumber("humanMartingaleStartStake", 0.35, 0.35, 1000000).toFixed(2));
    const modeEl = byId("humanMartingaleMode");
    const mode = String((modeEl && modeEl.value) || "STEP_005").toUpperCase() === "MULTIPLIER" ? "MULTIPLIER" : "STEP_005";
    const stepAmount = Number(readHumanSingleMartingaleNumber("humanMartingaleStepAmount", 0.05, 0.01, 1000000).toFixed(2));
    const multiplier = Math.max(1, readHumanSingleMartingaleNumber("humanMartingaleMultiplier", 2, 1, 100));
    const maxSteps = Math.max(1, Math.floor(readHumanSingleMartingaleNumber("humanMartingaleMaxSteps", 1000, 1, 1000000)));
    const doubleLimit = Math.max(0, Math.floor(readHumanSingleMartingaleNumber("humanMartingaleDoubleLimit", 0, 0, 1000000)));
    const tickSpacing = readHumanTickSpacing("humanMartingaleTickSpacing", 1);
    const alwaysBoth = !!(byId("humanMartingaleAlwaysBoth") && byId("humanMartingaleAlwaysBoth").checked);
    const oneWinStop = !!(byId("humanMartingaleOneWinStop") && byId("humanMartingaleOneWinStop").checked);
    const capRaw = byId("humanMartingaleMaxStake");
    const maxStakeValue = capRaw && String(capRaw.value || "").trim() !== ""
      ? Math.max(0.35, Number(capRaw.value))
      : null;
    const maxStake = Number.isFinite(maxStakeValue) ? Number(maxStakeValue.toFixed(2)) : null;
    const option = {};
    const isTickAction = isHumanTickPickAction(action) || action === "HIGH_LOW_TICKS";
    if(isTickAction){
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
    return { action, startStake, mode, stepAmount, multiplier, maxSteps, maxStake, doubleLimit, tickSpacing, alwaysBoth, oneWinStop, option, isPair: !!pairConfig, pairConfig };
  }

  function nextHumanLimitedMartingaleStep(currentStep, settings){
    const step = Math.max(1, Math.min(settings.maxSteps || 1000000, Math.floor(Number(currentStep || 1) || 1)));
    const limit = Math.max(0, Math.floor(Number(settings.doubleLimit || 0) || 0));
    if(limit > 0 && (step - 1) >= limit) return 1;
    return Math.min(settings.maxSteps || 1000000, step + 1);
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

  function humanSingleMartingaleStakeForPairAction(action, stepValue){
    const settings = readHumanSingleMartingaleSettings();
    const pairStep = Math.max(1, Math.min(settings.maxSteps, Math.floor(Number(stepValue || (HUMAN_SINGLE_MARTINGALE_STATE.pairSteps || {})[String(action || "").toUpperCase()] || 1) || 1)));
    let stake = settings.mode === "STEP_005"
      ? settings.startStake + ((pairStep - 1) * settings.stepAmount)
      : settings.startStake * Math.pow(settings.multiplier, pairStep - 1);
    if(settings.maxStake !== null) stake = Math.min(stake, settings.maxStake);
    return Number(Math.max(0.35, stake).toFixed(2));
  }

  function updateHumanSingleMartingalePanel(){
    const settings = readHumanSingleMartingaleSettings();
    HUMAN_SINGLE_MARTINGALE_STATE.action = settings.action;
    const isTick = isHumanTickPickAction(settings.action) || settings.action === "HIGH_LOW_TICKS";
    const durationWrap = byId("humanMartingaleDurationWrap");
    const tickWrap = byId("humanMartingaleSelectedTickWrap");
    if(durationWrap) durationWrap.style.display = isTick ? "none" : "grid";
    if(tickWrap) tickWrap.style.display = isTick ? "grid" : "none";

    const actionInfo = settings.isPair
      ? null
      : ((humanManualContracts || {})[settings.action] || {});
    const available = humanSingleMartingaleActionAvailable(settings.action);
    const actionEl = byId("humanMartingaleAction");
    if(actionEl){
      Array.from(actionEl.options || []).forEach((option) => {
        const key = normalizeHumanSpecialAction(option.value);
        option.disabled = !!humanManualContracts && !humanSingleMartingaleActionAvailable(key);
      });
    }
    const durationEl = byId("humanMartingaleDuration");
    if(durationEl && !isTick){
      const durationSource = settings.isPair
        ? (settings.pairConfig.actions || []).map((key) => (humanManualContracts || {})[key] || {})
        : [actionInfo];
      const minDur = Math.max(2, ...durationSource.map((info) => Number(info.min_duration || 2) || 2));
      const maxDurCandidates = durationSource.map((info) => Number(info.max_duration || 0)).filter((value) => Number.isFinite(value) && value > 0);
      durationEl.min = String(minDur);
      if(maxDurCandidates.length) durationEl.max = String(Math.min(...maxDurCandidates));
      if(!durationEl.value || Number(durationEl.value) < minDur) {
        const defaults = durationSource.map((info) => Number(info.default_duration || 2) || 2);
        durationEl.value = String(Math.max(minDur, ...defaults));
      }
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
        note.textContent = `${humanSingleMartingaleLabel(settings.action)} is available on ${humanManualContractsSymbol || "selected market"}.`;
        note.style.color = "#86efac";
      }else{
        note.textContent = "This contract is not available for the selected market.";
        note.style.color = "#fca5a5";
      }
    }
    const status = byId("humanMartingaleStatus");
    if(status){
      const modeLabel = settings.mode === "STEP_005" ? `$${settings.stepAmount.toFixed(2)} step` : `${settings.multiplier}x`;
      const limitLabel = settings.doubleLimit > 0 ? ` • Limit ${settings.doubleLimit} double-up${settings.doubleLimit === 1 ? "" : "s"}` : "";
      const spacingLabel = ` • spacing ${settings.tickSpacing} tick${settings.tickSpacing === 1 ? "" : "s"}`;
      const alwaysBothLabel = settings.isPair && settings.alwaysBoth ? " • Always Both" : "";
      const oneWinLabel = settings.isPair && settings.oneWinStop ? " • One Win Stop" : "";
      if(settings.isPair){
        if(!HUMAN_SINGLE_MARTINGALE_STATE.running && !HUMAN_SINGLE_MARTINGALE_STATE.inProgress){
          (settings.pairConfig.actions || []).forEach((key) => {
            HUMAN_SINGLE_MARTINGALE_STATE.pairSteps[key] = 1;
          });
        }
        const currentLabel = (settings.pairConfig.actions || [])
          .map((key) => `${humanSingleMartingaleLabel(key)} $${humanSingleMartingaleStakeForPairAction(key).toFixed(2)}`)
          .join(" • ");
        status.textContent = `${HUMAN_SINGLE_MARTINGALE_STATE.status}. ${humanSingleMartingaleLabel(settings.action)} • ${modeLabel}${limitLabel}${spacingLabel}${alwaysBothLabel}${oneWinLabel} • ${currentLabel} • Last result: ${HUMAN_SINGLE_MARTINGALE_STATE.lastResult}`;
      }else{
        const currentStake = humanSingleMartingaleStakeForStep();
        const nextStep = nextHumanLimitedMartingaleStep(HUMAN_SINGLE_MARTINGALE_STATE.step, settings);
        const nextStake = HUMAN_SINGLE_MARTINGALE_STATE.enabled ? humanSingleMartingaleStakeForStep(nextStep) : settings.startStake;
        status.textContent = `${HUMAN_SINGLE_MARTINGALE_STATE.status}. ${modeLabel}${limitLabel}${spacingLabel} • Step ${HUMAN_SINGLE_MARTINGALE_STATE.step} • Current stake $${currentStake.toFixed(2)} • Next stake $${nextStake.toFixed(2)} • Last result: ${HUMAN_SINGLE_MARTINGALE_STATE.lastResult}`;
      }
      status.style.color = HUMAN_SINGLE_MARTINGALE_STATE.inProgress ? "#fbbf24" : (available ? "#94a3b8" : "#fca5a5");
    }
  }

  function setHumanSingleMartingaleAction(action){
    HUMAN_SINGLE_MARTINGALE_STATE.action = normalizeHumanSpecialAction(action) || "ONLY_UPS";
    HUMAN_SINGLE_MARTINGALE_STATE.pairSteps = {};
    HUMAN_SINGLE_MARTINGALE_STATE.spacingWait = 0;
    HUMAN_SINGLE_MARTINGALE_STATE.oneWinStopTriggered = false;
    HUMAN_SINGLE_MARTINGALE_STATE.status = "Ready";
    updateHumanSingleMartingalePanel();
  }

  function toggleHumanSingleMartingale(){
    HUMAN_SINGLE_MARTINGALE_STATE.enabled = !HUMAN_SINGLE_MARTINGALE_STATE.enabled;
    if(HUMAN_SINGLE_MARTINGALE_STATE.enabled){
      HUMAN_SINGLE_MARTINGALE_STATE.step = 1;
      HUMAN_SINGLE_MARTINGALE_STATE.pairSteps = {};
      HUMAN_SINGLE_MARTINGALE_STATE.spacingWait = 0;
      HUMAN_SINGLE_MARTINGALE_STATE.oneWinStopTriggered = false;
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
    HUMAN_SINGLE_MARTINGALE_STATE.pendingContracts = {};
    HUMAN_SINGLE_MARTINGALE_STATE.pendingExpected = 0;
    HUMAN_SINGLE_MARTINGALE_STATE.pendingSettled = 0;
    HUMAN_SINGLE_MARTINGALE_STATE.pendingPair = false;
    HUMAN_SINGLE_MARTINGALE_STATE.pendingMartingale = false;
    HUMAN_SINGLE_MARTINGALE_STATE.pendingStake = 0;
    HUMAN_SINGLE_MARTINGALE_STATE.oneWinStopTriggered = false;
  }

  function scheduleHumanSingleMartingaleRound(){
    if(!HUMAN_SINGLE_MARTINGALE_STATE.running || !HUMAN_SINGLE_MARTINGALE_STATE.enabled || HUMAN_SINGLE_MARTINGALE_STATE.stopRequested || HUMAN_SINGLE_MARTINGALE_STATE.inProgress) return;
    const spacing = readHumanTickSpacing("humanMartingaleTickSpacing", 1);
    HUMAN_SINGLE_MARTINGALE_STATE.spacingWait = spacing;
    HUMAN_SINGLE_MARTINGALE_STATE.status = `Waiting ${spacing} tick(s) before next round`;
    updateHumanSingleMartingalePanel();
  }

  function quickStopHumanSingleMartingale(reason){
    if(HUMAN_SINGLE_MARTINGALE_STATE.restartTimer){
      clearTimeout(HUMAN_SINGLE_MARTINGALE_STATE.restartTimer);
      HUMAN_SINGLE_MARTINGALE_STATE.restartTimer = null;
    }
    HUMAN_SINGLE_MARTINGALE_STATE.running = false;
    HUMAN_SINGLE_MARTINGALE_STATE.stopRequested = true;
    HUMAN_SINGLE_MARTINGALE_STATE.enabled = false;
    HUMAN_SINGLE_MARTINGALE_STATE.pairSteps = {};
    HUMAN_SINGLE_MARTINGALE_STATE.spacingWait = 0;
    HUMAN_SINGLE_MARTINGALE_STATE.oneWinStopTriggered = false;
    clearHumanSingleMartingalePending();
    HUMAN_SINGLE_MARTINGALE_STATE.status = reason || "Stopped";
    updateHumanSingleMartingalePanel();
  }

  async function placeHumanSingleMartingaleTrade(options){
    const opts = options || {};
    if(HUMAN_SINGLE_MARTINGALE_STATE.inProgress) return;
    const settings = readHumanSingleMartingaleSettings();
    if(!humanManualContracts || (!settings.isPair && !humanManualContracts[settings.action])){
      await refreshHumanManualContracts(false);
    }
    if(!humanSingleMartingaleActionAvailable(settings.action)){
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
    HUMAN_SINGLE_MARTINGALE_STATE.pendingContracts = {};
    HUMAN_SINGLE_MARTINGALE_STATE.pendingExpected = settings.isPair ? (settings.pairConfig.actions || []).length : 1;
    HUMAN_SINGLE_MARTINGALE_STATE.pendingSettled = 0;
    HUMAN_SINGLE_MARTINGALE_STATE.pendingPair = !!settings.isPair;
    HUMAN_SINGLE_MARTINGALE_STATE.pendingMartingale = !!HUMAN_SINGLE_MARTINGALE_STATE.enabled;
    HUMAN_SINGLE_MARTINGALE_STATE.pendingStake = settings.isPair
      ? (settings.pairConfig.actions || []).reduce((sum, key) => sum + humanSingleMartingaleStakeForPairAction(key), 0)
      : stake;
    HUMAN_SINGLE_MARTINGALE_STATE.spacingWait = 0;
    HUMAN_SINGLE_MARTINGALE_STATE.oneWinStopTriggered = false;
    HUMAN_SINGLE_MARTINGALE_STATE.status = "Running";
    updateHumanSingleMartingalePanel();
    try{
      if(settings.isPair){
        const actions = settings.pairConfig.actions || [];
        const pairOptions = {};
        actions.forEach((key) => {
          pairOptions[key] = Object.assign({ stake: humanSingleMartingaleStakeForPairAction(key), quiet: true }, settings.option);
        });
        await placeHumanManualPairAction(actions, pairOptions, {
          type: settings.action,
          label: `HUMAN ${humanSingleMartingaleLabel(settings.action)}`,
        });
        if(typeof showToast === "function") {
          const sentText = actions
            .map((key) => `${humanSingleMartingaleLabel(key)} $${humanSingleMartingaleStakeForPairAction(key).toFixed(2)}`)
            .join(" + ");
          showToast(`HUMAN ${humanSingleMartingaleLabel(settings.action)} sent: ${sentText}`, "success");
        }
      }else{
        await placeHumanManualAction(settings.action, Object.assign({ stake, quiet: true }, settings.option));
        if(typeof showToast === "function") showToast(`HUMAN ${humanSingleMartingaleLabel(settings.action)} sent at $${stake.toFixed(2)}`, "success");
      }
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

  function readHumanRfMartingaleDurationSelection(){
    const el = byId("humanRfMartingaleDuration");
    const raw = String((el && el.value) || "t:5").trim().toLowerCase();
    let durationUnit = "t";
    let duration = 5;
    if(raw.includes(":")){
      const parts = raw.split(":");
      durationUnit = parts[0] === "s" ? "s" : "t";
      duration = Number(parts[1]);
    }else{
      duration = Number(raw);
    }
    if(durationUnit === "s"){
      duration = Math.round(clampNum(duration, 15, 30, 15));
    }else{
      duration = Math.round(clampNum(duration, 1, 10, 5));
    }
    if(el) el.value = `${durationUnit}:${duration}`;
    return { duration, durationUnit };
  }

  function readHumanRfMartingaleSettings(){
    const directionEl = byId("humanRfMartingaleDirection");
    const directionRaw = String((directionEl && directionEl.value) || HUMAN_RF_MARTINGALE_STATE.direction || "RISE").toUpperCase();
    const direction = directionRaw === "FALL" || directionRaw === "BOTH" || directionRaw === "BOTH_EQUALS" ? directionRaw : "RISE";
    const durationSelection = readHumanRfMartingaleDurationSelection();
    const duration = durationSelection.duration;
    const durationUnit = durationSelection.durationUnit;
    const riseStake = Number(readHumanRfMartingaleNumber("humanRfMartingaleRiseStake", 0.35, 0.35, 1000000).toFixed(2));
    const fallStake = Number(readHumanRfMartingaleNumber("humanRfMartingaleFallStake", 0.35, 0.35, 1000000).toFixed(2));
    const startStake = direction === "FALL" ? fallStake : riseStake;
    const multiplier = Math.max(1, readHumanRfMartingaleNumber("humanRfMartingaleMultiplier", 2, 1, 100));
    const tickSpacing = readHumanTickSpacing("humanRfMartingaleTickSpacing", 1);
    const maxSteps = Math.max(1, Math.floor(readHumanRfMartingaleNumber("humanRfMartingaleMaxSteps", 8, 1, 1000)));
    const doubleLimit = Math.max(0, Math.floor(readHumanRfMartingaleNumber("humanRfMartingaleDoubleLimit", 0, 0, 1000000)));
    const capRaw = byId("humanRfMartingaleMaxStake");
    const maxStakeValue = capRaw && String(capRaw.value || "").trim() !== ""
      ? Math.max(0.35, Number(capRaw.value))
      : null;
    const maxStake = Number.isFinite(maxStakeValue) ? Number(maxStakeValue.toFixed(2)) : null;
    if(directionEl) directionEl.value = direction;
    const spacingEl = byId("humanRfMartingaleTickSpacing");
    if(spacingEl) spacingEl.value = String(tickSpacing);
    return { direction, duration, durationUnit, startStake, riseStake, fallStake, multiplier, tickSpacing, maxSteps, maxStake, doubleLimit };
  }

  function humanRfMartingaleStakeForStep(stepValue){
    const settings = readHumanRfMartingaleSettings();
    const step = Math.max(1, Math.min(settings.maxSteps, Math.floor(Number(stepValue || HUMAN_RF_MARTINGALE_STATE.step) || 1)));
    let stake = settings.startStake * Math.pow(settings.multiplier, step - 1);
    if(settings.maxStake !== null) stake = Math.min(stake, settings.maxStake);
    return Number(Math.max(0.35, stake).toFixed(2));
  }

  function humanRfPairStakeForDirection(direction){
    const side = normalizeHumanRfDirection(direction);
    const stake = side === "FALL" ? HUMAN_RF_MARTINGALE_STATE.fallStake : HUMAN_RF_MARTINGALE_STATE.riseStake;
    const base = side === "FALL" ? HUMAN_RF_MARTINGALE_STATE.fallBaseStake : HUMAN_RF_MARTINGALE_STATE.riseBaseStake;
    return Number(Math.max(0.35, Number(stake || base || 0.35)).toFixed(2));
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
      if(settings.direction === "BOTH" || settings.direction === "BOTH_EQUALS"){
        if(!HUMAN_RF_MARTINGALE_STATE.running && !HUMAN_RF_MARTINGALE_STATE.inProgress){
          HUMAN_RF_MARTINGALE_STATE.riseBaseStake = settings.riseStake;
          HUMAN_RF_MARTINGALE_STATE.fallBaseStake = settings.fallStake;
          HUMAN_RF_MARTINGALE_STATE.riseStake = settings.riseStake;
          HUMAN_RF_MARTINGALE_STATE.fallStake = settings.fallStake;
          HUMAN_RF_MARTINGALE_STATE.multiplier = settings.multiplier;
        }
        const pairLabel = settings.direction === "BOTH_EQUALS" ? "Rise + Fall Equals" : "Rise + Fall";
        const limitLabel = settings.doubleLimit > 0 ? ` • Limit ${settings.doubleLimit} double-up${settings.doubleLimit === 1 ? "" : "s"}` : "";
        const durationLabel = `${settings.duration} ${settings.durationUnit === "s" ? "sec" : "tick"}${settings.duration === 1 ? "" : "s"}`;
        status.textContent = `${HUMAN_RF_MARTINGALE_STATE.status}. ${pairLabel} • ${durationLabel} • ${settings.multiplier}x${limitLabel} • Rise stake $${humanRfPairStakeForDirection("RISE").toFixed(2)} • Fall stake $${humanRfPairStakeForDirection("FALL").toFixed(2)} • Last result: ${HUMAN_RF_MARTINGALE_STATE.lastResult}`;
      }else{
        const currentStake = humanRfMartingaleStakeForStep();
        const nextStep = nextHumanLimitedMartingaleStep(HUMAN_RF_MARTINGALE_STATE.step, settings);
        const nextStake = HUMAN_RF_MARTINGALE_STATE.enabled ? humanRfMartingaleStakeForStep(nextStep) : settings.startStake;
        const limitLabel = settings.doubleLimit > 0 ? ` • Limit ${settings.doubleLimit} double-up${settings.doubleLimit === 1 ? "" : "s"}` : "";
        const durationLabel = `${settings.duration} ${settings.durationUnit === "s" ? "sec" : "tick"}${settings.duration === 1 ? "" : "s"}`;
        status.textContent = `${HUMAN_RF_MARTINGALE_STATE.status}. ${settings.direction} • ${durationLabel}${limitLabel} • Step ${HUMAN_RF_MARTINGALE_STATE.step} • Current stake $${currentStake.toFixed(2)} • Next stake $${nextStake.toFixed(2)} • Last result: ${HUMAN_RF_MARTINGALE_STATE.lastResult}`;
      }
      status.style.color = HUMAN_RF_MARTINGALE_STATE.inProgress ? "#fbbf24" : "#94a3b8";
    }
  }

  function setHumanRfMartingaleDirection(direction){
    const raw = String(direction || "RISE").toUpperCase();
    HUMAN_RF_MARTINGALE_STATE.direction = raw === "FALL" || raw === "BOTH" || raw === "BOTH_EQUALS" ? raw : "RISE";
    HUMAN_RF_MARTINGALE_STATE.status = "Ready";
    updateHumanRfMartingalePanel();
  }

  function toggleHumanRfMartingale(){
    HUMAN_RF_MARTINGALE_STATE.enabled = !HUMAN_RF_MARTINGALE_STATE.enabled;
    if(HUMAN_RF_MARTINGALE_STATE.enabled){
      HUMAN_RF_MARTINGALE_STATE.step = 1;
      HUMAN_RF_MARTINGALE_STATE.riseDoubleCount = 0;
      HUMAN_RF_MARTINGALE_STATE.fallDoubleCount = 0;
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
    HUMAN_RF_MARTINGALE_STATE.pendingDirections = {};
    HUMAN_RF_MARTINGALE_STATE.settledCount = 0;
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
    HUMAN_RF_MARTINGALE_STATE.spacingWait = 0;
    HUMAN_RF_MARTINGALE_STATE.riseDoubleCount = 0;
    HUMAN_RF_MARTINGALE_STATE.fallDoubleCount = 0;
    clearHumanRfMartingalePending();
    HUMAN_RF_MARTINGALE_STATE.status = reason || "Stopped";
    updateHumanRfMartingalePanel();
  }

  async function placeHumanRfMartingaleTrade(options){
    const opts = options || {};
    if(HUMAN_RF_MARTINGALE_STATE.inProgress) return;
    const settings = readHumanRfMartingaleSettings();
    if((settings.direction === "BOTH" || settings.direction === "BOTH_EQUALS") && HUMAN_RF_MARTINGALE_STATE.enabled && !opts.continuation){
      HUMAN_RF_MARTINGALE_STATE.riseBaseStake = settings.riseStake;
      HUMAN_RF_MARTINGALE_STATE.fallBaseStake = settings.fallStake;
      HUMAN_RF_MARTINGALE_STATE.riseStake = settings.riseStake;
      HUMAN_RF_MARTINGALE_STATE.fallStake = settings.fallStake;
      HUMAN_RF_MARTINGALE_STATE.multiplier = settings.multiplier;
    }
    const pairMode = settings.direction === "BOTH" || settings.direction === "BOTH_EQUALS";
    const allowEquals = settings.direction === "BOTH_EQUALS";
    const pairPlan = pairMode
      ? [
        { direction: "RISE", stake: humanRfPairStakeForDirection("RISE") },
        { direction: "FALL", stake: humanRfPairStakeForDirection("FALL") },
      ]
      : [];
    const stake = HUMAN_RF_MARTINGALE_STATE.enabled ? humanRfMartingaleStakeForStep() : settings.startStake;
    if(HUMAN_RF_MARTINGALE_STATE.enabled && !opts.continuation){
      HUMAN_RF_MARTINGALE_STATE.running = true;
      HUMAN_RF_MARTINGALE_STATE.stopRequested = false;
    }
    HUMAN_RF_MARTINGALE_STATE.inProgress = true;
    HUMAN_RF_MARTINGALE_STATE.spacingWait = 0;
    HUMAN_RF_MARTINGALE_STATE.pendingDirection = settings.direction;
    HUMAN_RF_MARTINGALE_STATE.pendingDirections = {};
    HUMAN_RF_MARTINGALE_STATE.settledCount = 0;
    pairPlan.forEach((leg) => { HUMAN_RF_MARTINGALE_STATE.pendingDirections[leg.direction] = { stake: leg.stake, result: "" }; });
    HUMAN_RF_MARTINGALE_STATE.pendingContractId = "";
    HUMAN_RF_MARTINGALE_STATE.pendingMartingale = !!HUMAN_RF_MARTINGALE_STATE.enabled;
    HUMAN_RF_MARTINGALE_STATE.pendingStake = pairMode ? pairPlan.reduce((sum, leg) => sum + leg.stake, 0) : stake;
    HUMAN_RF_MARTINGALE_STATE.status = "Running";
    updateHumanRfMartingalePanel();
    try{
      if(pairMode){
        const totalStake = pairPlan.reduce((sum, leg) => sum + leg.stake, 0);
        const data = await guardMartha({
          profile: PROFILE,
          source: "human_rf_pair_martingale",
          type: allowEquals ? "RISE_FALL_EQUALS" : "RISE_FALL",
          label: allowEquals ? "HUMAN Rise + Fall Equals Martingale" : "HUMAN Rise + Fall Martingale",
          stake: totalStake,
          duration: settings.duration,
          duration_unit: settings.durationUnit,
          batch_count: 2,
        }, async () => {
          return postJSON("/human_auto_rise_fall", {
            rise_stake: pairPlan[0].stake,
            fall_stake: pairPlan[1].stake,
            duration_ticks: settings.duration,
            duration_unit: settings.durationUnit,
            allow_equals: allowEquals,
          });
        });
        if(isMarthaBlocked(data)) throw new Error("Trade blocked");
        if(typeof showToast === "function") showToast(`HUMAN ${allowEquals ? "Rise + Fall Equals" : "Rise + Fall"} martingale sent: RISE $${pairPlan[0].stake.toFixed(2)} + FALL $${pairPlan[1].stake.toFixed(2)}`, "success");
      }else{
        const payload = {
          direction: settings.direction,
          stake,
          duration_ticks: settings.duration,
          duration_unit: settings.durationUnit,
          ignore_cooldown: true,
        };
        const data = await guardMartha({
          profile: PROFILE,
          source: "human_rf_martingale",
          type: settings.direction,
          label: `HUMAN ${settings.direction} Martingale`,
          stake,
          duration: settings.duration,
          duration_unit: settings.durationUnit,
          batch_count: 1,
        }, () => postJSON("/human_rf_trade", payload));
        if(isMarthaBlocked(data)) throw new Error("Trade blocked");
        if(typeof showToast === "function") showToast(`HUMAN ${settings.direction} martingale sent at $${stake.toFixed(2)}`, "success");
      }
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
    if(compact === "ONLYUPSONLYDOWNS" || compact === "ONLYUPSDOWNS" || compact === "RUNSUPRUNSDOWN") return "ONLY_UPS_DOWNS";
    if(text === "ASIANS_UP_DOWNS" || text === "ASIANS_UP_DOWN" || text === "ASIAN_UP_DOWNS" || text === "ASIAN_UP_DOWN" || compact === "ASIANSUPDOWNS" || compact === "ASIANUPDOWNS" || compact === "ASIANSUPASIANSDOWN" || compact === "ASIANSUPASIANDOWN" || compact === "ASIANUPASIANSDOWN" || compact === "ASIANUPASIANDOWN" || compact === "ASIANSUPDOWN" || compact === "ASIANUPDOWN") return "ASIANS_UP_DOWNS";
    if(compact === "HIGHTICKLOWTICKS" || compact === "HIGHLOWTICKS" || compact === "HIGHTICKLOWTICK") return "HIGH_LOW_TICKS";
    if(text.includes("ASIANS_UP") || text.includes("ASIAN_UP") || compact.includes("ASIANU") || compact.includes("ASIANSUP")) return "ASIANS_UP";
    if(text.includes("ASIANS_DOWN") || text.includes("ASIAN_DOWN") || compact.includes("ASIAND") || compact.includes("ASIANSDOWN")) return "ASIANS_DOWN";
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

  function resolveHumanRfPayloadDirection(payload){
    if(!payload) return "";
    const contractType = String(payload.contract_type || "").toUpperCase().replace(/[^A-Z]/g, "");
    if(contractType === "CALL" || contractType === "CALLE") return "RISE";
    if(contractType === "PUT" || contractType === "PUTE") return "FALL";
    for(const key of ["type", "action", "leg_action"]){
      const direction = normalizeHumanRfDirection(payload[key]);
      if(direction) return direction;
    }
    return normalizeHumanRfDirection(payload.label);
  }

  function isHumanRfPairDirection(direction){
    const value = String(direction || "").toUpperCase();
    return value === "BOTH" || value === "BOTH_EQUALS";
  }

  function rememberHumanSpecialTrade(payload){
    if(!payload || String(payload.profile || "").toUpperCase() !== PROFILE) return;
    const activeCycle = HUMAN_SPECIAL_AUTO_STATE.running || HUMAN_SPECIAL_AUTO_STATE.firing || HUMAN_SPECIAL_AUTO_STATE.pendingCount > 0 || HUMAN_SPECIAL_AUTO_STATE.expectedCount > 0;
    const action = normalizeHumanSpecialAction([payload.pair_action, payload.action, payload.leg_action, payload.type, payload.contract_type, payload.label].filter(Boolean).join(" "))
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
    const paritySide = resolveHumanParityResultSide(payload);
    if(
      paritySide
      && contractId
      && HUMAN_PARITY_MARTINGALE_STATE.runId
      && String(payload.mode || "") === `human_parity_martingale:${HUMAN_PARITY_MARTINGALE_STATE.runId}`
      && HUMAN_PARITY_MARTINGALE_STATE.pending
      && HUMAN_PARITY_MARTINGALE_STATE.pending[paritySide]
    ){
      HUMAN_PARITY_MARTINGALE_STATE.pending[paritySide].contractId = String(contractId);
    }
    if(
      action
      && contractId
      && HUMAN_SINGLE_MARTINGALE_STATE.inProgress
    ){
      if(HUMAN_SINGLE_MARTINGALE_STATE.pendingPair){
        const pairConfig = getHumanSingleMartingalePairConfig(HUMAN_SINGLE_MARTINGALE_STATE.pendingAction);
        if(pairConfig && pairConfig.actions.includes(action) && !HUMAN_SINGLE_MARTINGALE_STATE.pendingContracts[String(contractId)]){
          HUMAN_SINGLE_MARTINGALE_STATE.pendingContracts[String(contractId)] = {
            action,
            outcome: "",
          };
          HUMAN_SINGLE_MARTINGALE_STATE.status = "Running";
          updateHumanSingleMartingalePanel();
        }
      }else if(!HUMAN_SINGLE_MARTINGALE_STATE.pendingContractId && action === HUMAN_SINGLE_MARTINGALE_STATE.pendingAction){
        HUMAN_SINGLE_MARTINGALE_STATE.pendingContractId = String(contractId);
        HUMAN_SINGLE_MARTINGALE_STATE.status = "Running";
        updateHumanSingleMartingalePanel();
      }
    }
    const rfDirection = resolveHumanRfPayloadDirection(payload);
    if(
      rfDirection
      && contractId
      && HUMAN_RF_MARTINGALE_STATE.inProgress
      && !HUMAN_RF_MARTINGALE_STATE.pendingContractId
      && (
        rfDirection === HUMAN_RF_MARTINGALE_STATE.pendingDirection
        || (isHumanRfPairDirection(HUMAN_RF_MARTINGALE_STATE.pendingDirection) && HUMAN_RF_MARTINGALE_STATE.pendingDirections && HUMAN_RF_MARTINGALE_STATE.pendingDirections[rfDirection])
      )
    ){
      if(isHumanRfPairDirection(HUMAN_RF_MARTINGALE_STATE.pendingDirection)){
        HUMAN_RF_MARTINGALE_STATE.pendingDirections[rfDirection].contractId = String(contractId);
      }else{
        HUMAN_RF_MARTINGALE_STATE.pendingContractId = String(contractId);
      }
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
    if(!HUMAN_SINGLE_MARTINGALE_STATE.inProgress && !HUMAN_SINGLE_MARTINGALE_STATE.pendingContractId && !HUMAN_SINGLE_MARTINGALE_STATE.pendingPair) return;
    const contractId = payload.contract_id || payload.buy_contract_id || payload.id;
    const mode = String(payload.mode || "").toLowerCase();
    const action = normalizeHumanSpecialAction([payload.pair_action, payload.action, payload.leg_action, payload.type, payload.contract_type, payload.label].filter(Boolean).join(" "))
      || (contractId ? (((HUMAN_SINGLE_MARTINGALE_STATE.pendingContracts || {})[String(contractId)] || {}).action || "") : "")
      || (mode === "human_manual_contract" ? HUMAN_SINGLE_MARTINGALE_STATE.pendingAction : "");
    if(HUMAN_SINGLE_MARTINGALE_STATE.pendingPair){
      const pairConfig = getHumanSingleMartingalePairConfig(HUMAN_SINGLE_MARTINGALE_STATE.pendingAction);
      if(!pairConfig || !pairConfig.actions.includes(action)) return;
      const outcome = resolveHumanTradeOutcome(payload);
      if(!outcome) return;
      const contractKey = contractId ? String(contractId) : `${action}_${HUMAN_SINGLE_MARTINGALE_STATE.pendingSettled}`;
      const pendingItem = HUMAN_SINGLE_MARTINGALE_STATE.pendingContracts[contractKey] || { action, outcome: "" };
      if(pendingItem.outcome) return;
      pendingItem.action = action;
      pendingItem.outcome = outcome;
      HUMAN_SINGLE_MARTINGALE_STATE.pendingContracts[contractKey] = pendingItem;
      HUMAN_SINGLE_MARTINGALE_STATE.pendingSettled = Object.values(HUMAN_SINGLE_MARTINGALE_STATE.pendingContracts || {}).filter((item) => item && item.outcome).length;
      const wasMartingaleTrade = !!HUMAN_SINGLE_MARTINGALE_STATE.pendingMartingale;
      const settings = readHumanSingleMartingaleSettings();
      if(wasMartingaleTrade && settings.oneWinStop && outcome === "WIN"){
        HUMAN_SINGLE_MARTINGALE_STATE.oneWinStopTriggered = true;
        HUMAN_SINGLE_MARTINGALE_STATE.running = false;
        HUMAN_SINGLE_MARTINGALE_STATE.stopRequested = true;
      }
      if(HUMAN_SINGLE_MARTINGALE_STATE.pendingSettled < Math.max(2, Number(HUMAN_SINGLE_MARTINGALE_STATE.pendingExpected || 2))){
        HUMAN_SINGLE_MARTINGALE_STATE.lastResult = `${humanSingleMartingaleLabel(action)} ${outcome}`;
        HUMAN_SINGLE_MARTINGALE_STATE.status = HUMAN_SINGLE_MARTINGALE_STATE.oneWinStopTriggered
          ? `One Win hit. Settling ${HUMAN_SINGLE_MARTINGALE_STATE.pendingSettled}/${HUMAN_SINGLE_MARTINGALE_STATE.pendingExpected}, then stopped.`
          : `Running. Settled ${HUMAN_SINGLE_MARTINGALE_STATE.pendingSettled}/${HUMAN_SINGLE_MARTINGALE_STATE.pendingExpected}.`;
        updateHumanSingleMartingalePanel();
        return;
      }
      const stopAfterOneWin = !!(wasMartingaleTrade && settings.oneWinStop && (
        HUMAN_SINGLE_MARTINGALE_STATE.oneWinStopTriggered
        || Object.values(HUMAN_SINGLE_MARTINGALE_STATE.pendingContracts || {}).some((item) => item && item.outcome === "WIN")
      ));
      if(!stopAfterOneWin && wasMartingaleTrade && settings.alwaysBoth){
        const currentMaxStep = (pairConfig.actions || []).reduce((max, key) => {
          const step = Math.max(1, Math.floor(Number((HUMAN_SINGLE_MARTINGALE_STATE.pairSteps || {})[key] || 1) || 1));
          return Math.max(max, step);
        }, 1);
        const nextStep = nextHumanLimitedMartingaleStep(currentMaxStep, settings);
        (pairConfig.actions || []).forEach((key) => {
          HUMAN_SINGLE_MARTINGALE_STATE.pairSteps[key] = nextStep;
        });
      }else if(!stopAfterOneWin){
        (pairConfig.actions || []).forEach((key) => {
          const legItem = Object.values(HUMAN_SINGLE_MARTINGALE_STATE.pendingContracts || {}).find((item) => item && item.action === key);
          if(!legItem) return;
          if(legItem.outcome === "WIN"){
            HUMAN_SINGLE_MARTINGALE_STATE.pairSteps[key] = 1;
          }else if(legItem.outcome === "LOSS"){
            const currentStep = Math.max(1, Math.min(settings.maxSteps, Math.floor(Number((HUMAN_SINGLE_MARTINGALE_STATE.pairSteps || {})[key] || 1) || 1)));
            HUMAN_SINGLE_MARTINGALE_STATE.pairSteps[key] = nextHumanLimitedMartingaleStep(currentStep, settings);
          }
        });
      }
      const lastParts = (pairConfig.actions || []).map((key) => {
        const legItem = Object.values(HUMAN_SINGLE_MARTINGALE_STATE.pendingContracts || {}).find((item) => item && item.action === key);
        return legItem ? `${humanSingleMartingaleLabel(key)} ${legItem.outcome}` : null;
      }).filter(Boolean);
      clearHumanSingleMartingalePending();
      HUMAN_SINGLE_MARTINGALE_STATE.step = 1;
      HUMAN_SINGLE_MARTINGALE_STATE.lastResult = lastParts.join(" • ") || outcome;
      if(stopAfterOneWin){
        HUMAN_SINGLE_MARTINGALE_STATE.pairSteps = {};
        HUMAN_SINGLE_MARTINGALE_STATE.running = false;
        HUMAN_SINGLE_MARTINGALE_STATE.stopRequested = true;
        HUMAN_SINGLE_MARTINGALE_STATE.enabled = false;
        HUMAN_SINGLE_MARTINGALE_STATE.spacingWait = 0;
        HUMAN_SINGLE_MARTINGALE_STATE.status = "One Win hit. Martingale stopped.";
        updateHumanSingleMartingalePanel();
        return;
      }
      if(wasMartingaleTrade && HUMAN_SINGLE_MARTINGALE_STATE.enabled){
        HUMAN_SINGLE_MARTINGALE_STATE.status = "Running";
        if(HUMAN_SINGLE_MARTINGALE_STATE.running && !HUMAN_SINGLE_MARTINGALE_STATE.stopRequested){
          if(HUMAN_SINGLE_MARTINGALE_STATE.restartTimer) clearTimeout(HUMAN_SINGLE_MARTINGALE_STATE.restartTimer);
          HUMAN_SINGLE_MARTINGALE_STATE.restartTimer = null;
          scheduleHumanSingleMartingaleRound();
        }
      }else{
        HUMAN_SINGLE_MARTINGALE_STATE.running = false;
        HUMAN_SINGLE_MARTINGALE_STATE.status = "Ready";
      }
      updateHumanSingleMartingalePanel();
      return;
    }
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
        HUMAN_SINGLE_MARTINGALE_STATE.step = nextHumanLimitedMartingaleStep(HUMAN_SINGLE_MARTINGALE_STATE.step, settings);
        HUMAN_SINGLE_MARTINGALE_STATE.status = "Running";
        if(HUMAN_SINGLE_MARTINGALE_STATE.running && !HUMAN_SINGLE_MARTINGALE_STATE.stopRequested){
          if(HUMAN_SINGLE_MARTINGALE_STATE.restartTimer) clearTimeout(HUMAN_SINGLE_MARTINGALE_STATE.restartTimer);
          HUMAN_SINGLE_MARTINGALE_STATE.restartTimer = null;
          scheduleHumanSingleMartingaleRound();
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
    const direction = resolveHumanRfPayloadDirection(payload);
    if(isHumanRfPairDirection(HUMAN_RF_MARTINGALE_STATE.pendingDirection)){
      if(!direction || !HUMAN_RF_MARTINGALE_STATE.pendingDirections || !HUMAN_RF_MARTINGALE_STATE.pendingDirections[direction]) return;
      const pendingLeg = HUMAN_RF_MARTINGALE_STATE.pendingDirections[direction];
      if(pendingLeg.result) return;
      if(pendingLeg.contractId && String(contractId || "") !== pendingLeg.contractId) return;
      const outcome = resolveHumanTradeOutcome(payload);
      if(!outcome) return;
      pendingLeg.result = outcome;
      HUMAN_RF_MARTINGALE_STATE.settledCount = Object.values(HUMAN_RF_MARTINGALE_STATE.pendingDirections || {}).filter((item) => item && item.result).length;
      const stake = Math.max(0.35, Number(pendingLeg.stake || humanRfPairStakeForDirection(direction)));
      if(outcome === "WIN"){
        if(direction === "RISE") HUMAN_RF_MARTINGALE_STATE.riseStake = Number((HUMAN_RF_MARTINGALE_STATE.riseBaseStake || 0.35).toFixed(2));
        if(direction === "FALL") HUMAN_RF_MARTINGALE_STATE.fallStake = Number((HUMAN_RF_MARTINGALE_STATE.fallBaseStake || 0.35).toFixed(2));
        if(direction === "RISE") HUMAN_RF_MARTINGALE_STATE.riseDoubleCount = 0;
        if(direction === "FALL") HUMAN_RF_MARTINGALE_STATE.fallDoubleCount = 0;
      }else{
        const settings = readHumanRfMartingaleSettings();
        const countKey = direction === "FALL" ? "fallDoubleCount" : "riseDoubleCount";
        const limit = Math.max(0, Math.floor(Number(settings.doubleLimit || 0) || 0));
        const currentCount = Math.max(0, Math.floor(Number(HUMAN_RF_MARTINGALE_STATE[countKey] || 0) || 0));
        if(limit > 0 && currentCount >= limit){
          if(direction === "RISE") HUMAN_RF_MARTINGALE_STATE.riseStake = Number((HUMAN_RF_MARTINGALE_STATE.riseBaseStake || settings.riseStake || 0.35).toFixed(2));
          if(direction === "FALL") HUMAN_RF_MARTINGALE_STATE.fallStake = Number((HUMAN_RF_MARTINGALE_STATE.fallBaseStake || settings.fallStake || 0.35).toFixed(2));
          HUMAN_RF_MARTINGALE_STATE[countKey] = 0;
        }else{
          let next = Number((stake * Math.max(1, Number(settings.multiplier || HUMAN_RF_MARTINGALE_STATE.multiplier || 2))).toFixed(2));
          if(settings.maxStake !== null) next = Math.min(next, settings.maxStake);
          if(direction === "RISE") HUMAN_RF_MARTINGALE_STATE.riseStake = Number(Math.max(0.35, next).toFixed(2));
          if(direction === "FALL") HUMAN_RF_MARTINGALE_STATE.fallStake = Number(Math.max(0.35, next).toFixed(2));
          HUMAN_RF_MARTINGALE_STATE[countKey] = currentCount + 1;
        }
      }
      HUMAN_RF_MARTINGALE_STATE.lastResult = `${direction} ${outcome} at ${money(stake)}`;
      const expected = Object.keys(HUMAN_RF_MARTINGALE_STATE.pendingDirections || {}).length;
      HUMAN_RF_MARTINGALE_STATE.status = HUMAN_RF_MARTINGALE_STATE.running ? `Running. Settled ${HUMAN_RF_MARTINGALE_STATE.settledCount}/${expected}.` : "Stopped";
      updateHumanRfMartingalePanel();
      if(expected > 0 && HUMAN_RF_MARTINGALE_STATE.settledCount >= expected){
        HUMAN_RF_MARTINGALE_STATE.inProgress = false;
        HUMAN_RF_MARTINGALE_STATE.pendingDirections = {};
        HUMAN_RF_MARTINGALE_STATE.settledCount = 0;
        HUMAN_RF_MARTINGALE_STATE.status = HUMAN_RF_MARTINGALE_STATE.running ? "Next round queued" : "Ready";
        updateHumanRfMartingalePanel();
        if(HUMAN_RF_MARTINGALE_STATE.running && !HUMAN_RF_MARTINGALE_STATE.stopRequested){
          const spacing = readHumanTickSpacing("humanRfMartingaleTickSpacing", 1);
          HUMAN_RF_MARTINGALE_STATE.spacingWait = spacing;
          HUMAN_RF_MARTINGALE_STATE.status = `Waiting ${spacing} tick(s) before next round`;
          updateHumanRfMartingalePanel();
        }
      }
      return;
    }
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
      HUMAN_RF_MARTINGALE_STATE.riseDoubleCount = 0;
      HUMAN_RF_MARTINGALE_STATE.fallDoubleCount = 0;
      HUMAN_RF_MARTINGALE_STATE.running = false;
      HUMAN_RF_MARTINGALE_STATE.stopRequested = false;
      HUMAN_RF_MARTINGALE_STATE.enabled = false;
      HUMAN_RF_MARTINGALE_STATE.lastResult = "WIN";
      HUMAN_RF_MARTINGALE_STATE.status = wasMartingaleTrade ? "Reset" : "Ready";
    }else if(lost){
      HUMAN_RF_MARTINGALE_STATE.lastResult = "LOSS";
      if(wasMartingaleTrade && HUMAN_RF_MARTINGALE_STATE.enabled){
        const settings = readHumanRfMartingaleSettings();
        HUMAN_RF_MARTINGALE_STATE.step = nextHumanLimitedMartingaleStep(HUMAN_RF_MARTINGALE_STATE.step, settings);
        HUMAN_RF_MARTINGALE_STATE.status = "Running";
        if(HUMAN_RF_MARTINGALE_STATE.running && !HUMAN_RF_MARTINGALE_STATE.stopRequested){
          if(HUMAN_RF_MARTINGALE_STATE.restartTimer) clearTimeout(HUMAN_RF_MARTINGALE_STATE.restartTimer);
          const spacing = readHumanTickSpacing("humanRfMartingaleTickSpacing", 1);
          HUMAN_RF_MARTINGALE_STATE.spacingWait = spacing;
          HUMAN_RF_MARTINGALE_STATE.status = `Waiting ${spacing} tick(s) before next round`;
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
          resetHumanParityDigitScreen();
          fetchHumanRFStatus();
          refreshHumanManualContracts(true);
        });
        bind("market_change", () => {
          resetHumanParityDigitScreen();
          fetchHumanRFStatus();
          refreshHumanManualContracts(true);
        });
        bind("tick", updateHumanParityDigitScreen);
        bind("trade_placed", rememberHumanSpecialTrade);
        bind("trade_result", updateHumanSpecialMartingaleFromResult);
        bind("trade_result", updateHumanSingleMartingaleFromResult);
        bind("trade_result", updateHumanRfMartingaleFromResult);
        bind("trade_result", updateHumanParityMartingaleFromResult);
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
        if(previous.handlers.parityResult) previous.socket.off("trade_result", previous.handlers.parityResult);
        if(previous.handlers.tickResult) previous.socket.off("tick", previous.handlers.tickResult);
      }
      const tickResult = (payload) => {
        updateHumanParityDigitScreen(payload);
      };
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
      const parityResult = (payload) => {
        if(payload && String(payload.profile || "").toUpperCase() === PROFILE) updateHumanParityMartingaleFromResult(payload);
      };
      liveSocket.on("tick", tickResult);
      liveSocket.on("trade_placed", placed);
      liveSocket.on("trade_result", specialResult);
      liveSocket.on("trade_result", singleResult);
      liveSocket.on("trade_result", rfResult);
      liveSocket.on("trade_result", parityResult);
      window.__humanSpecialSocketFallback = { socket: liveSocket, handlers: { tickResult, placed, specialResult, singleResult, rfResult, parityResult } };
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
        case "human-parity-martingale-start":
          startHumanParityMartingale();
          break;
        case "human-parity-martingale-stop":
          stopHumanParityMartingale();
          break;
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
    window.humanManualAsiansPairTrade = humanManualAsiansPairTrade;
    window.populateHumanDualMarketSelects = populateHumanDualMarketSelects;
    window.updateHumanDualMarketPanel = updateHumanDualMarketPanel;
    window.setHumanDualStake = setHumanDualStake;
    window.humanDualMarketPlaceBoth = humanDualMarketPlaceBoth;
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
    window.updateHumanParityMartingalePanel = updateHumanParityMartingalePanel;
    window.startHumanParityMartingale = startHumanParityMartingale;
    window.stopHumanParityMartingale = stopHumanParityMartingale;
    removeHumanParitySyntheticBatchRows();

    // initial render/poll
    startPolling();
    refreshHumanManualContracts(false);
    populateHumanDualMarketSelects();
    syncHumanRFAllowEqualsToggle();
    updateHumanSingleMartingalePanel();
    updateHumanRfMartingalePanel();
    updateHumanParityMartingalePanel();
    renderHumanParityDigitScreen();
    removeHumanParitySyntheticBatchRows();
    maybeAutoFormulaX();
  }

  async function afterLoadProfileUI() {
    bindHumanDropdownPanels(byId("profileContainer"));
    bindSocketIfPossible();
    startPolling();
    refreshHumanManualContracts(false);
    populateHumanDualMarketSelects();
    syncHumanRFAllowEqualsToggle();
    updateHumanSingleMartingalePanel();
    updateHumanRfMartingalePanel();
    updateHumanParityMartingalePanel();
    renderHumanParityDigitScreen();
    removeHumanParitySyntheticBatchRows();
    maybeAutoFormulaX();
  }

  async function onActivate() {
    bindHumanDropdownPanels(byId("profileContainer"));
    startPolling();
    try{
      if(typeof refreshHumanKeepAliveUI === "function") await refreshHumanKeepAliveUI();
    }catch(e){}
    refreshHumanManualContracts(false);
    populateHumanDualMarketSelects();
    syncHumanRFAllowEqualsToggle();
    updateHumanSingleMartingalePanel();
    updateHumanRfMartingalePanel();
    updateHumanParityMartingalePanel();
    renderHumanParityDigitScreen();
    maybeAutoFormulaX();
  }

  async function onDeactivate() {
    stopPolling();
    clearStatusRenderTimer();
    stopHumanParityMartingale();
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
