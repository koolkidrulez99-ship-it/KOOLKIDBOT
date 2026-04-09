(function () {
  const PROFILE = "HUMAN";
  const STATUS_POLL_INTERVAL_MS = 5000;
  const STATUS_FETCH_MIN_INTERVAL_MS = 1000;
  let pollTimer = null;
  let cachedStatus = null;
  let socketHooked = false;
  let statusFetchTimer = null;
  let statusFetchPromise = null;
  let lastStatusFetchAt = 0;
  const fxState = { active: false, firing: false, lastToast: 0 };

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

  function renderHumanRFStatus(data){
    if(!data || !rootExists()) return;
    cachedStatus = data;

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
  }

  async function fetchHumanRFStatus(){
    if(!rootExists()) return;
    const nowTs = Date.now();
    if(statusFetchPromise) return statusFetchPromise;
    if((nowTs - Number(lastStatusFetchAt || 0)) < STATUS_FETCH_MIN_INTERVAL_MS) return false;
    try{
      if(window.BotPerf && typeof window.BotPerf.bump === "function"){
        window.BotPerf.bump("status_fetch_frequency", { profile: PROFILE, source: "/human_rf_status" });
      }
    }catch(_e){}
    statusFetchPromise = (async ()=>{
      try{
        const res = await fetch("/human_rf_status");
        if(!res.ok) return false;
        const data = await res.json();
        lastStatusFetchAt = Date.now();
        renderHumanRFStatus(data);
        maybeAutoFormulaX();
        return true;
      }catch(e){
        return false;
      }finally{
        statusFetchPromise = null;
      }
    })();
    return statusFetchPromise;
  }

  function scheduleHumanRFStatusFetch(reason, delay){
    if(statusFetchTimer){
      clearTimeout(statusFetchTimer);
    }
    statusFetchTimer = setTimeout(()=>{
      statusFetchTimer = null;
      try{
        if(window.BotPerf && typeof window.BotPerf.log === "function"){
          window.BotPerf.log("human_status_refresh_scheduled", { profile: PROFILE, reason: reason || "scheduled" });
        }
      }catch(_e){}
      try{
        const maybePromise = fetchHumanRFStatus();
        if(maybePromise && typeof maybePromise.catch === "function"){
          maybePromise.catch(()=>{});
        }
      }catch(_e){}
    }, Math.max(40, Number(delay || 180)));
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
      const data = await postJSON("/human_rf_trade", payload);
      if(typeof showToast === "function"){
        const d = (data && data.signal && data.signal.direction) ? data.signal.direction : (direction || "AUTO");
        showToast(`HUMAN ${d} trade sent`, "success");
      }
      await fetchHumanRFStatus();
    }catch(e){
      if(typeof showToast === "function") showToast(e.message || "No valid setup", "error");
    }
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
    scheduleHumanRFStatusFetch("poll_start", 0);
    pollTimer = setInterval(() => {
      if(!rootExists()) return;
      scheduleHumanRFStatusFetch("poll", 40);
    }, STATUS_POLL_INTERVAL_MS);
  }

  function stopPolling(){
    if(pollTimer){
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function bindSocketIfPossible(){
    if(socketHooked) return;
    try{
      if(typeof socket !== "undefined" && socket && typeof socket.on === "function"){
        try{
          if(window.BotPerf && typeof window.BotPerf.log === "function"){
            const listeners = window.BotPerf.getSocketListenerCount ? window.BotPerf.getSocketListenerCount(socket) : null;
            window.BotPerf.log("profile_socket_listener_count", { profile: PROFILE, listeners });
          }
        }catch(_e){}
        socket.on("human_rf_status", (payload) => {
          if(rootExists()) renderHumanRFStatus(payload);
        });
        socket.on("human_market_change", () => {
          scheduleHumanRFStatusFetch("human_market_change", 140);
        });
        socket.on("market_change", () => {
          scheduleHumanRFStatusFetch("market_change", 180);
        });
        socketHooked = true;
      }
    }catch(e){}
  }

  function getAppHooks(){
    const App = getApp();
    return App || {};
  }

  function updateFormulaXButton(){
    const btn = byId("formulaXBtn");
    if(!btn) return;
    if(fxState.active){
      btn.innerText = "FormulaX • ON (waiting)";
      btn.style.background = "#38bdf8";
    }else{
      btn.innerText = "FormulaX";
      btn.style.background = "#0ea5e9";
    }
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

      const r = await postJSON("/human_formula_x", {
        rise_stake: riseStake,
        fall_stake: fallStake,
        duration_ticks: durationTicks,
      });
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

  async function onMount(payload) {
    const root = payload && payload.root ? payload.root : byId("profileContainer");
    bindUI(root);
    bindSocketIfPossible();

    // expose globals for inline onclick in human.html
    window.humanRFTrade = humanRFTrade;
    window.saveHumanRFSettings = saveHumanRFSettings;
    window.toggleHumanRFSetting = toggleHumanRFSetting;
    window.humanRFSetStake = humanRFSetStake;
    window.runFormulaX = toggleFormulaX;

    // initial render/poll
    startPolling();
    maybeAutoFormulaX();
  }

  async function afterLoadProfileUI() {
    bindSocketIfPossible();
    startPolling();
    maybeAutoFormulaX();
  }

  async function onActivate() {
    startPolling();
    try{
      if(typeof refreshHumanKeepAliveUI === "function") await refreshHumanKeepAliveUI();
    }catch(e){}
    maybeAutoFormulaX();
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
