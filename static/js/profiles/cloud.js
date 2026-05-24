(function () {
  const PROFILE = "CLOUD";
  const POLL_LABEL = "cloud_under9_status_poll";
  const DEFAULT_MARKET_LIST = ["R_10","R_25","R_50","R_75","R_100","1HZ10V","1HZ25V","1HZ50V","1HZ75V","1HZ100V","JD10","JD25","JD50","JD75","JD100"];
  const DEFAULT_MARKETS = DEFAULT_MARKET_LIST.join(",");
  const MARKET_LABELS = {
    R_10: "Vol 10",
    R_25: "Vol 25",
    R_50: "Vol 50",
    R_75: "Vol 75",
    R_100: "Vol 100",
    "1HZ10V": "Vol 10 1s",
    "1HZ25V": "Vol 25 1s",
    "1HZ50V": "Vol 50 1s",
    "1HZ75V": "Vol 75 1s",
    "1HZ100V": "Vol 100 1s",
    JD10: "Jump 10",
    JD25: "Jump 25",
    JD50: "Jump 50",
    JD75: "Jump 75",
    JD100: "Jump 100",
  };
  let pollTimer = null;
  let socketBound = false;
  let latestStatus = null;
  let settingsDirty = false;

  function app(){ return window.BotApp || {}; }
  function byId(id){ return document.getElementById(id); }
  function isActive(){
    try{ return String(activeProfile || "").toUpperCase() === PROFILE; }catch(e){}
    return !!byId("cloudProfilePanel");
  }
  function money(value){
    const n = Number(value || 0);
    return Number.isFinite(n) ? `$${n.toFixed(2)}` : "$0.00";
  }
  function signedMoney(value){
    const n = Number(value || 0);
    if(!Number.isFinite(n)) return "$0.00";
    return `${n >= 0 ? "+" : "-"}$${Math.abs(n).toFixed(2)}`;
  }
  async function postJSON(url, body){
    const res = await fetch(url, { method:"POST", headers:{ "Content-Type":"application/json" }, body:JSON.stringify(body || {}) });
    const data = await res.json().catch(()=>({}));
    if(!res.ok || String(data.status || "").toLowerCase() === "error") throw new Error(data.message || data.error || "Cloud request failed");
    return data;
  }
  async function getJSON(url){
    const res = await fetch(url, { method:"GET", cache:"no-store" });
    const data = await res.json().catch(()=>({}));
    if(!res.ok) throw new Error(data.message || data.error || "Cloud request failed");
    return data;
  }
  function readNumber(id, fallback){
    const n = Number((byId(id) || {}).value);
    return Number.isFinite(n) ? n : fallback;
  }
  function parseMarkets(value){
    const raw = Array.isArray(value) ? value : String(value || "").replace(/\n/g, ",").replace(/;/g, ",").split(",");
    const seen = new Set();
    const out = [];
    raw.forEach((item)=> {
      const symbol = String(item || "").trim().toUpperCase();
      if(symbol && !seen.has(symbol)){
        seen.add(symbol);
        out.push(symbol);
      }
    });
    return out;
  }
  function selectedMarkets(){
    const picker = byId("cloudMarketPicker");
    if(picker && picker.dataset.built === "1"){
      const checked = Array.from(picker.querySelectorAll("input[type='checkbox']:checked")).map((el)=> el.value);
      return checked;
    }
    return parseMarkets((byId("cloudAllowedMarkets") || {}).value || DEFAULT_MARKETS);
  }
  function syncMarketTextarea(markDirty){
    const markets = selectedMarkets();
    const textarea = byId("cloudAllowedMarkets");
    if(textarea) textarea.value = markets.join(",");
    setText("cloudMarketCount", `${markets.length} market${markets.length === 1 ? "" : "s"} selected`);
    if(markDirty) settingsDirty = true;
    return markets;
  }
  function buildMarketPicker(){
    const picker = byId("cloudMarketPicker");
    if(!picker || picker.dataset.built === "1") return;
    picker.dataset.built = "1";
    picker.innerHTML = DEFAULT_MARKET_LIST.map((symbol)=> `
      <label class="cloud-market-option">
        <span>${MARKET_LABELS[symbol] || symbol}</span>
        <input type="checkbox" value="${symbol}" checked>
      </label>
    `).join("");
    picker.querySelectorAll("input[type='checkbox']").forEach((input)=> {
      input.addEventListener("change", ()=> syncMarketTextarea(true));
    });
    syncMarketTextarea(false);
  }
  function writeMarketPicker(markets){
    buildMarketPicker();
    const selected = new Set(parseMarkets(markets && markets.length ? markets : DEFAULT_MARKET_LIST));
    const picker = byId("cloudMarketPicker");
    if(picker){
      picker.querySelectorAll("input[type='checkbox']").forEach((input)=> {
        input.checked = selected.has(String(input.value || "").toUpperCase());
      });
    }
    const textarea = byId("cloudAllowedMarkets");
    const list = Array.from(selected);
    if(textarea && document.activeElement !== textarea) textarea.value = list.join(",");
    setText("cloudMarketCount", `${list.length} market${list.length === 1 ? "" : "s"} selected`);
  }
  function readSettings(){
    const markets = selectedMarkets();
    if(!markets.length) throw new Error("Choose at least one Cloud market.");
    syncMarketTextarea(false);
    return {
      base_stake: readNumber("cloudBaseStake", 1),
      take_profit_target: readNumber("cloudTpTarget", 50),
      max_reinvest_steps: readNumber("cloudMaxReinvestSteps", 5),
      duration: readNumber("cloudDuration", 1),
      market_switch_minutes: readNumber("cloudMarketSwitchMinutes", 10),
      low_balance_stop: readNumber("cloudLowBalanceStop", 0),
      max_daily_loss: readNumber("cloudMaxDailyLoss", 0),
      max_trades_per_session: readNumber("cloudMaxTrades", 0),
      trade_time_mode: ((byId("cloudTradeTimeMode") || {}).value || "ANYTIME"),
      custom_trade_start_time: ((byId("cloudCustomTradeStart") || {}).value || "09:00"),
      custom_trade_end_time: ((byId("cloudCustomTradeEnd") || {}).value || "13:00"),
      allowed_markets: markets.join(","),
      capital_build_mode: !!((byId("cloudCapitalBuildMode") || {}).checked),
      enable_telegram_alerts: !!((byId("cloudTelegramAlerts") || {}).checked),
      enable_whatsapp_alerts: !!((byId("cloudWhatsappAlerts") || {}).checked),
      allow_auto_resume: !!((byId("cloudAllowAutoResume") || {}).checked),
      max_digit9_last5: readNumber("cloudMax9Last5", 2),
      max_digit9_last10: readNumber("cloudMax9Last10", 2),
      max_digit9_last20: readNumber("cloudMax9Last20", 4),
      min_seconds_between_99_streaks: readNumber("cloudStreakCooldown", 20),
    };
  }
  function bindSettingsDirtyHandlers(){
    const panel = byId("cloudProfilePanel");
    if(!panel || panel.dataset.settingsDirtyBound === "1") return;
    panel.dataset.settingsDirtyBound = "1";
    panel.querySelectorAll("input, textarea, select").forEach((el)=> {
      if(el && el.id !== "cloudBudget"){
        el.addEventListener("input", ()=> { settingsDirty = true; });
        el.addEventListener("change", ()=> {
          if(el.id === "cloudAllowedMarkets") writeMarketPicker(parseMarkets(el.value));
          settingsDirty = true;
        });
      }
    });
  }
  function writeSettings(status, force){
    if(settingsDirty && !force) return;
    const settings = (status && status.settings) || status || {};
    const map = {
      cloudBaseStake: settings.base_stake,
      cloudTpTarget: settings.take_profit_target || status.configured_tp_target,
      cloudMaxReinvestSteps: settings.max_reinvest_steps,
      cloudDuration: settings.duration,
      cloudMarketSwitchMinutes: settings.market_switch_minutes,
      cloudLowBalanceStop: settings.low_balance_stop,
      cloudMaxDailyLoss: settings.max_daily_loss,
      cloudMaxTrades: settings.max_trades_per_session,
      cloudTradeTimeMode: settings.trade_time_mode,
      cloudCustomTradeStart: settings.custom_trade_start_time,
      cloudCustomTradeEnd: settings.custom_trade_end_time,
      cloudMax9Last5: settings.max_digit9_last5,
      cloudMax9Last10: settings.max_digit9_last10,
      cloudMax9Last20: settings.max_digit9_last20,
      cloudStreakCooldown: settings.min_seconds_between_99_streaks,
    };
    Object.keys(map).forEach((id)=>{
      const el = byId(id);
      if(!el || document.activeElement === el || map[id] === undefined) return;
      el.value = String(map[id]);
    });
    const markets = byId("cloudAllowedMarkets");
    if(markets && document.activeElement !== markets && Array.isArray(settings.allowed_markets)){
      markets.value = settings.allowed_markets.join(",");
    }
    writeMarketPicker(settings.allowed_markets);
    [["cloudCapitalBuildMode","capital_build_mode"],["cloudTelegramAlerts","enable_telegram_alerts"],["cloudWhatsappAlerts","enable_whatsapp_alerts"],["cloudAllowAutoResume","allow_auto_resume"]].forEach(([id,key])=>{
      const el = byId(id);
      if(el) el.checked = !!settings[key];
    });
  }
  function setText(id, value){
    const el = byId(id);
    if(el && el.textContent !== String(value)) el.textContent = String(value);
  }
  function renderStatus(status){
    if(!status || !byId("cloudProfilePanel")) return;
    latestStatus = status;
    writeSettings(status);
    const running = !!status.running;
    setText("cloudRunningBadge", running ? "Running" : "Stopped");
    setText("cloudTokenBadge", status.token_verified ? "Token verified" : "Token verification needed");
    const badge = byId("cloudRunningBadge");
    if(badge){
      badge.style.background = running ? "rgba(34,197,94,.16)" : "rgba(239,68,68,.14)";
      badge.style.borderColor = running ? "rgba(34,197,94,.38)" : "rgba(239,68,68,.34)";
    }
    setText("cloudCurrentMarket", status.current_market || "R_10");
    setText("cloudCurrentStake", money(status.current_stake));
    setText("cloudSessionProfit", signedMoney(status.session_profit));
    const target = Math.max(0.01, Number(status.tp_target || status.configured_tp_target || 50));
    const profit = Math.max(0, Number(status.session_profit || 0));
    setText("cloudTpProgress", `${Math.min(100, (profit / target) * 100).toFixed(1)}%`);
    setText("cloudReinvestStep", `${Number(status.reinvest_step || 0)}/${Number(status.max_reinvest_steps || 5)}`);
    setText("cloudDigit9Pct", `${Number(status.digit9_percentage || 0).toFixed(1)}%`);
    const statusLines = [
      `State: ${status.cloud_status || "Stopped"}`,
      `Last signal: ${status.last_signal || "Waiting"}`,
      `Ticks: ${status.tick_count || 0}/100`,
      `Trade lock: ${status.trade_locked ? "locked" : "open for next setup"}`,
      `Last result: ${status.last_trade_result || "none"}`,
      `Jamaica time: ${status.jamaica_time || "--:--"} ${status.jamaica_timezone || "EST Jamaica"}`,
      `Time window: ${status.trade_window_label || "Anytime"}`,
      `Cloud ID: ${status.cloud_account_id || status.token_fingerprint || "not verified"}`,
      `Token: ${status.token_verified ? "verified" : "connect the exact API token/account to view/run Cloud"}`,
    ];
    setText("cloudStatusText", statusLines.join("\n"));
    setText("cloudDecisionLog", statusLines.concat([
      `Markets: ${(status.allowed_markets || []).join(", ")}`,
      `Capital build: ${status.capital_build_mode ? "ON" : "OFF"}`,
    ]).join("\n"));
  }
  async function refreshStatus(silent){
    try{
      const status = await getJSON("/cloud/under9/status");
      renderStatus(status);
      return status;
    }catch(e){
      if(!silent && typeof showToast === "function") showToast(e.message || "Cloud status failed", "error");
      return null;
    }
  }
  function startPoll(){
    stopPoll();
    pollTimer = setInterval(()=> {
      if(!isActive()){ stopPoll(); return; }
      refreshStatus(true);
    }, 2500);
    if(app().registerFrontendInterval) app().registerFrontendInterval(POLL_LABEL, pollTimer);
  }
  function stopPoll(){
    if(pollTimer){
      if(!(app().clearFrontendInterval && app().clearFrontendInterval(POLL_LABEL))) clearInterval(pollTimer);
      pollTimer = null;
    }
  }
  function bindSocket(){
    if(socketBound) return;
    if(app().bindSocketListener){
      app().bindSocketListener(PROFILE, "cloud_under9_status", (status)=> {
        if(isActive()) renderStatus(status || {});
      });
      socketBound = true;
    }
  }

  window.startCloudUnder9 = async function(){
    try{
      const data = await postJSON("/cloud/under9/start", readSettings());
      settingsDirty = false;
      writeSettings(data, true);
      renderStatus(data);
      startPoll();
      if(typeof showToast === "function") showToast("Cloud Under 9 started", "success");
    }catch(e){
      if(typeof showToast === "function") showToast(e.message || "Cloud start failed", "error");
    }
  };
  window.stopCloudUnder9 = async function(){
    try{
      const data = await postJSON("/cloud/under9/stop", {});
      settingsDirty = false;
      writeSettings(data, true);
      renderStatus(data);
      if(typeof showToast === "function") showToast("Cloud Under 9 stopped", "error");
    }catch(e){
      if(typeof showToast === "function") showToast(e.message || "Cloud stop failed", "error");
    }
  };
  window.restartCloudUnder9 = async function(){
    try{
      const data = await postJSON("/cloud/under9/restart", {});
      settingsDirty = false;
      writeSettings(data, true);
      renderStatus(data);
      startPoll();
      if(typeof showToast === "function") showToast("Cloud Under 9 restarted", "success");
    }catch(e){
      if(typeof showToast === "function") showToast(e.message || "Cloud restart failed", "error");
    }
  };
  window.saveCloudUnder9Settings = async function(){
    try{
      const data = await postJSON("/cloud/under9/settings", readSettings());
      settingsDirty = false;
      writeSettings(data, true);
      renderStatus(data);
      if(typeof showToast === "function") showToast("Cloud settings saved", "success");
    }catch(e){
      if(typeof showToast === "function") showToast(e.message || "Cloud settings failed", "error");
    }
  };
  window.cloudSelectMarkets = function(mode){
    buildMarketPicker();
    const picker = byId("cloudMarketPicker");
    if(!picker) return;
    const normalized = String(mode || "ALL").toUpperCase();
    picker.querySelectorAll("input[type='checkbox']").forEach((input)=> {
      const symbol = String(input.value || "").toUpperCase();
      if(normalized === "ALL") input.checked = true;
      else if(normalized === "JUMP") input.checked = symbol.startsWith("JD");
      else if(normalized === "VOL") input.checked = !symbol.startsWith("JD");
    });
    syncMarketTextarea(true);
  };

  async function onMount(){
    bindSocket();
    buildMarketPicker();
    bindSettingsDirtyHandlers();
    await refreshStatus(true);
    startPoll();
  }
  async function afterLoadProfileUI(){ return onMount(); }
  async function onActivate(){ return onMount(); }
  async function onDeactivate(){
    stopPoll();
    socketBound = false;
  }

  if(typeof window.registerProfileModule === "function"){
    window.registerProfileModule(PROFILE, { onMount, afterLoadProfileUI, onActivate, onDeactivate });
  }else{
    window.ProfileModules = window.ProfileModules || {};
    window.ProfileModules[PROFILE] = { onMount, afterLoadProfileUI, onActivate, onDeactivate };
  }
})();
