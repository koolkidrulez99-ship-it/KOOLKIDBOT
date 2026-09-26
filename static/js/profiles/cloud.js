(function () {
  const PROFILE = "CLOUD";
  const POLL_LABEL = "cloud_under9_status_poll";
  const DEFAULT_MARKET_LIST = ["R_10","R_25","R_50","R_75","R_100","1HZ10V","1HZ25V","1HZ50V","1HZ75V","1HZ100V","JD10","JD25","JD50","JD75","JD100","STPRNG","STPRNG2","STPRNG3","STPRNG4","STPRNG5"];
  const CLOUD_FIXED_TRADE_MARKETS = {
    odd: ["JD10","JD25","JD50","JD75","JD100"],
    rise: ["STPRNG","STPRNG2","STPRNG3","STPRNG4","STPRNG5"],
    higher: ["R_75"],
  };
  const DEFAULT_MARKETS = DEFAULT_MARKET_LIST.join(",");
  const KOOLKID_PROFIT_MARKETS = ["R_10","R_25","R_50","R_75","R_100"];
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
    STPRNG: "Step Index 100",
    STPRNG2: "Step Index 200",
    STPRNG3: "Step Index 300",
    STPRNG4: "Step Index 400",
    STPRNG5: "Step Index 500",
  };
  let pollTimer = null;
  let socketBound = false;
  let latestStatus = null;
  let settingsDirty = false;
  let statusRequest = null;
  let actionBusy = "";

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
    const preset = ((byId("cloudPreset") || {}).value || "reinvest_profits_100");
    const selected = selectedMarkets();
    const tradeType = ((byId("cloudReinvestTradeType") || {}).value || "under9");
    const fixedTradeMarkets = CLOUD_FIXED_TRADE_MARKETS[tradeType] || null;
    const marketScope = ((byId("cloudReinvestMarketScope") || {}).value || "ALL");
    const singleMarket = ((byId("cloudReinvestSingleMarket") || {}).value || DEFAULT_MARKET_LIST[0]);
    const reinvestMarkets = fixedTradeMarkets ? fixedTradeMarkets.slice() : (marketScope === "ONE" ? [singleMarket] : DEFAULT_MARKET_LIST.slice());
    const markets = preset === "koolkid_profit"
      ? selected.filter((symbol)=> KOOLKID_PROFIT_MARKETS.includes(symbol))
      : (preset === "reinvest_profits_100" ? reinvestMarkets : selected);
    if(preset === "koolkid_profit" && !markets.length) markets.push(...KOOLKID_PROFIT_MARKETS);
    if(!markets.length) throw new Error("Choose at least one Cloud market.");
    if(preset === "reinvest_profits_100"){
      const stakeMode = ((byId("cloudReinvestStakeMode") || {}).value || "FIXED");
      const balancePercent = readNumber("cloudReinvestPercent", 10);
      if(stakeMode === "PERCENT" && (balancePercent < 10 || balancePercent > 20)) throw new Error("Balance percentage must be between 10% and 20%.");
    }
    syncMarketTextarea(false);
    return {
      strategy_name: preset,
      base_stake: preset === "koolkid_profit" ? readNumber("cloudKoolkidProfitStake", 1) : (preset === "reinvest_profits_100" ? readNumber("cloudReinvestStake", 1) : readNumber("cloudBaseStake", 1)),
      compound_percent: readNumber("cloudCompoundPercent", 100),
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
      allow_auto_resume: preset === "koolkid_profit" || !!((byId("cloudAllowAutoResume") || {}).checked),
      max_digit9_last5: readNumber("cloudMax9Last5", 2),
      max_digit9_last10: readNumber("cloudMax9Last10", 2),
      max_digit9_last20: readNumber("cloudMax9Last20", 4),
      min_seconds_between_99_streaks: readNumber("cloudStreakCooldown", 20),
      stake_mode: ((byId("cloudReinvestStakeMode") || {}).value || "FIXED"),
      balance_percent: readNumber("cloudReinvestPercent", 10),
      market_scan_scope: marketScope,
      selected_market: singleMarket,
      cloud_trade_type: tradeType,
      cloud_trade_mode: ((byId("cloudReinvestMode") || {}).value || "SAFE"),
      kid100_mode: ((byId("cloudKid100Mode") || {}).value || "LOW"),
      ai_auto_strategy: ((byId("cloudAiAutoStrategy") || {}).value || "GOLDEN_CARD"),
      trades_per_session: readNumber("cloudTradesPerSession", 1),
      session_runs: readNumber("cloudSessionRuns", 1),
      session_delay: readNumber("cloudSessionDelay", 30),
      session_delay_unit: ((byId("cloudSessionDelayUnit") || {}).value || "seconds"),
      stop_after_one_win: !!((byId("cloudStopAfterOneWin") || {}).checked),
      stop_after_one_loss: !!((byId("cloudStopAfterOneLoss") || {}).checked),
      min_profit_percent: readNumber("cloudMinProfitPercent", 0),
    };
  }
  function updatePresetUI(){
    const preset = ((byId("cloudPreset") || {}).value || "reinvest_profits_100");
    const isProfit = preset === "koolkid_profit";
    const isReinvest = preset === "reinvest_profits_100";
    const profit = byId("cloudKoolkidProfitSettings");
    const reinvest = byId("cloudReinvest100Settings");
    const under9 = byId("cloudUnder9Settings");
    if(profit) profit.hidden = !isProfit;
    if(reinvest) reinvest.hidden = !isReinvest;
    if(under9) under9.hidden = isProfit || isReinvest;
    const tradeType = ((byId("cloudReinvestTradeType") || {}).value || "under9");
    const modeDriven = ["digit_differs", "under9", "over0"].includes(tradeType);
    const kid100 = tradeType === "kid100wins";
    const aiAuto = tradeType === "ai_auto_trading";
    const stakeMode = ((byId("cloudReinvestStakeMode") || {}).value || "FIXED");
    const fixedWrap = byId("cloudReinvestFixedStakeWrap");
    const percentWrap = byId("cloudReinvestPercentWrap");
    const modeWrap = byId("cloudReinvestModeWrap");
    const tradesWrap = byId("cloudTradesPerSessionWrap");
    const kid100Wrap = byId("cloudKid100ModeWrap");
    const aiAutoWrap = byId("cloudAiAutoStrategyWrap");
    const marketScopeEl = byId("cloudReinvestMarketScope");
    const marketScope = ((marketScopeEl || {}).value || "ALL");
    const singleMarketEl = byId("cloudReinvestSingleMarket");
    const singleMarketWrap = byId("cloudReinvestSingleMarketWrap");
    const fixedNote = byId("cloudFixedMarketNote");
    const fixedMarkets = CLOUD_FIXED_TRADE_MARKETS[tradeType] || null;
    if(fixedWrap) fixedWrap.hidden = stakeMode !== "FIXED";
    if(percentWrap) percentWrap.hidden = stakeMode !== "PERCENT";
    if(modeWrap) modeWrap.hidden = !modeDriven;
    if(tradesWrap) tradesWrap.hidden = modeDriven;
    if(kid100Wrap) kid100Wrap.hidden = !kid100;
    if(aiAutoWrap) aiAutoWrap.hidden = !aiAuto;
    if(fixedMarkets){
      if(marketScopeEl){
        marketScopeEl.value = tradeType === "higher" ? "ONE" : "ALL";
        marketScopeEl.disabled = true;
      }
      if(singleMarketEl){
        singleMarketEl.value = fixedMarkets[0];
        singleMarketEl.disabled = true;
      }
      if(singleMarketWrap) singleMarketWrap.hidden = true;
      if(fixedNote){
        fixedNote.hidden = false;
        fixedNote.innerText = tradeType === "odd"
          ? "ODD scans Jump markets only • enters after 4 consecutive even digits."
          : (tradeType === "rise"
            ? "RISE scans Step markets only • 1-tick Rise after a sustained uptrend."
            : "HIGHER scans V75 only • -7.5 barrier • 5 ticks after drop-and-recovery.");
      }
    }else{
      if(marketScopeEl) marketScopeEl.disabled = false;
      if(singleMarketEl) singleMarketEl.disabled = false;
      if(singleMarketWrap) singleMarketWrap.hidden = marketScope !== "ONE";
      if(fixedNote) fixedNote.hidden = true;
    }
    const modeNote = byId("cloudModeSessionNote");
    if(modeNote) modeNote.hidden = !modeDriven;
    updateCloudSessionSummary();
    setText("cloudPresetTitle", isProfit ? "KOOLKID PROFIT" : (isReinvest ? "REINVEST PROFITS 100%" : "Under 9 Reinvest"));
    setText("cloudPresetDescription", isProfit
      ? "Waits for a qualified crash after at least 30 ticks, confirms five later ticks, then opens a 5% accumulator for two ticks. Runs two independent setups per day and compounds the selected share of profit."
      : (isReinvest ? "Scans eligible markets in two stages, trades one setup at a time, and reinvests every confirmed profit within the current session." : "Scans every configured volatility and jump market, waits for digit 9 frequency to be 9% or lower, then places one Under 9 trade when a fresh 9 prints."));
    setText("cloudTpMetricLabel", isProfit ? "Daily Trades" : (isReinvest ? "Session Progress" : "TP Progress"));
    setText("cloudReinvestMetricLabel", isProfit ? "Compound" : (isReinvest ? "Session" : "Reinvest Step"));
    setText("cloudSignalMetricLabel", isProfit ? "Confirmations" : (isReinvest ? "Scanner" : "Digit 9"));
  }
  function updateCloudSessionSummary(){
    const type = ((byId("cloudReinvestTradeType") || {}).value || "under9");
    const modeDriven = ["digit_differs", "under9", "over0"].includes(type);
    const trades = Math.max(1, Math.floor(readNumber("cloudTradesPerSession", 1)));
    const runs = Math.max(1, Math.min(10, Math.floor(readNumber("cloudSessionRuns", 1))));
    const delay = Math.max(1, Math.floor(readNumber("cloudSessionDelay", 30)));
    const unit = String(((byId("cloudSessionDelayUnit") || {}).value || "seconds"));
    const target = String(((byId("cloudReinvestMode") || {}).value || "SAFE")).toUpperCase();
    setText("cloudSessionSummary", `${modeDriven ? `${target} target` : `${trades} trade${trades === 1 ? "" : "s"}`}, ${runs} run${runs === 1 ? "" : "s"}, ${delay} ${unit} wait`);
  }
  function bindSettingsDirtyHandlers(){
    const panel = byId("cloudProfilePanel");
    if(!panel || panel.dataset.settingsDirtyBound === "1") return;
    panel.dataset.settingsDirtyBound = "1";
    panel.querySelectorAll("input, textarea, select").forEach((el)=> {
      if(el && el.id !== "cloudBudget"){
        el.addEventListener("input", ()=> {
          settingsDirty = true;
          if(["cloudTradesPerSession","cloudSessionRuns","cloudSessionDelay","cloudSessionDelayUnit","cloudReinvestMode"].includes(el.id)) updateCloudSessionSummary();
        });
        el.addEventListener("change", ()=> {
          if(el.id === "cloudAllowedMarkets") writeMarketPicker(parseMarkets(el.value));
          if(["cloudPreset","cloudReinvestStakeMode","cloudReinvestTradeType","cloudReinvestMarketScope"].includes(el.id)) updatePresetUI();
          if(["cloudTradesPerSession","cloudSessionRuns","cloudSessionDelay","cloudSessionDelayUnit","cloudReinvestMode"].includes(el.id)) updateCloudSessionSummary();
          settingsDirty = true;
        });
      }
    });
  }
  function writeSettings(status, force){
    if(settingsDirty && !force) return;
    const settings = (status && status.settings) || status || {};
    const map = {
      cloudPreset: settings.strategy_name,
      cloudBaseStake: settings.base_stake,
      cloudKoolkidProfitStake: settings.base_stake,
      cloudReinvestStake: settings.base_stake,
      cloudReinvestStakeMode: settings.stake_mode,
      cloudReinvestPercent: settings.balance_percent,
      cloudReinvestMarketScope: settings.market_scan_scope,
      cloudReinvestSingleMarket: settings.selected_market,
      cloudReinvestTradeType: settings.cloud_trade_type,
      cloudReinvestMode: settings.cloud_trade_mode,
      cloudKid100Mode: settings.kid100_mode,
      cloudAiAutoStrategy: settings.ai_auto_strategy,
      cloudTradesPerSession: settings.trades_per_session,
      cloudSessionRuns: settings.session_runs,
      cloudSessionDelay: settings.session_delay,
      cloudSessionDelayUnit: settings.session_delay_unit,
      cloudMinProfitPercent: settings.min_profit_percent,
      cloudCompoundPercent: settings.compound_percent,
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
    updatePresetUI();
    [["cloudCapitalBuildMode","capital_build_mode"],["cloudTelegramAlerts","enable_telegram_alerts"],["cloudWhatsappAlerts","enable_whatsapp_alerts"],["cloudAllowAutoResume","allow_auto_resume"],["cloudStopAfterOneWin","stop_after_one_win"],["cloudStopAfterOneLoss","stop_after_one_loss"]].forEach(([id,key])=>{
      const el = byId(id);
      if(el) el.checked = !!settings[key];
    });
  }
  function setText(id, value){
    const el = byId(id);
    if(el && el.textContent !== String(value)) el.textContent = String(value);
  }
  function presetLabel(status){
    const name = String((status && status.strategy_name) || "");
    if(name === "koolkid_profit") return "KOOLKID PROFIT";
    if(name === "reinvest_profits_100") return "REINVEST PROFITS 100%";
    return "Cloud Under 9";
  }
  function renderSessionEvents(status){
    const root = byId("cloudSessionEvents");
    if(!root) return;
    const events = Array.isArray(status && status.session_events) ? status.session_events : [];
    root.innerHTML = "";
    root.hidden = !events.length;
    if(!events.length){
      return;
    }
    events.slice().reverse().forEach((event)=> {
      const item = document.createElement("div");
      const result = String((event || {}).result || "").toLowerCase();
      item.className = `cloud-session-event ${result === "won" ? "won" : (result === "lost" ? "lost" : "")}`;
      const copy = document.createElement("div");
      copy.className = "cloud-session-event-copy";
      const label = document.createElement("span");
      label.className = "cloud-session-event-title";
      label.textContent = String((event || {}).label || "Completed Cloud session");
      if((event || {}).time) label.title = String(event.time);
      const profit = document.createElement("strong");
      profit.className = "cloud-session-event-profit";
      profit.textContent = signedMoney((event || {}).profit);
      copy.append(label, profit);
      const clear = document.createElement("button");
      clear.type = "button";
      clear.title = "Clear this session result";
      clear.setAttribute("aria-label", "Clear this session result");
      clear.textContent = "x";
      clear.addEventListener("click", ()=> clearCloudSessionEvent((event || {}).id));
      item.append(copy, clear);
      root.appendChild(item);
    });
  }
  function renderCloudToggle(running){
    const button = byId("cloudToggleBtn");
    if(!button) return;
    const restart = byId("cloudRestartBtn");
    const isRunning = !!running;
    button.dataset.running = isRunning ? "1" : "0";
    button.disabled = !!actionBusy;
    if(restart) restart.disabled = !!actionBusy;
    if(actionBusy === "start") button.textContent = "Starting...";
    else if(actionBusy === "stop") button.textContent = "Stopping...";
    else if(actionBusy === "restart") button.textContent = "Restarting...";
    else button.textContent = isRunning ? "Stop Cloud Bot" : "Start Cloud Bot";
    button.classList.toggle("cloud-start", !isRunning && actionBusy !== "stop");
    button.classList.toggle("cloud-stop", isRunning || actionBusy === "stop");
  }
  async function clearCloudSessionEvent(eventId){
    const id = String(eventId || "").trim();
    if(!id) return;
    try{
      const res = await fetch(`/cloud/under9/session-events/${encodeURIComponent(id)}`, { method:"DELETE" });
      const data = await res.json().catch(()=>({}));
      if(!res.ok || String(data.status || "").toLowerCase() === "error") throw new Error(data.message || data.error || "Could not clear session result");
      renderStatus(data);
    }catch(e){
      if(typeof showToast === "function") showToast(e.message || "Could not clear session result", "error");
    }
  }
  function renderStatus(status){
    if(!status || !byId("cloudProfilePanel")) return;
    latestStatus = status;
    writeSettings(status);
    updatePresetUI();
    renderSessionEvents(status);
    const running = !!status.running;
    renderCloudToggle(running);
    setText("cloudRunningBadge", running ? "Running" : "Stopped");
    setText("cloudTokenBadge", status.token_verified ? "PAT account verified" : "PAT connection needed");
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
    const isProfit = String(status.strategy_name || "") === "koolkid_profit";
    const isReinvest = String(status.strategy_name || "") === "reinvest_profits_100";
    setText("cloudTpProgress", isProfit ? `${Number(status.daily_trade_count || 0)}/${Number(status.max_daily_trades || 2)} trades` : (isReinvest ? `${Number(status.session_wins || 0)}/${Number(status.mode_target || 1)} wins` : `${Math.min(100, (profit / target) * 100).toFixed(1)}%`));
    setText("cloudReinvestStep", isProfit ? `${Number(status.compound_percent || 100).toFixed(0)}%` : (isReinvest ? `${Number(status.session_number || 1)}/${Number(status.session_runs || 1)}` : `${Number(status.reinvest_step || 0)}/${Number(status.max_reinvest_steps || 5)}`));
    setText("cloudDigit9Pct", isProfit ? `${Number(status.confirmation_progress || 0)}/5` : (isReinvest ? `${(status.deep_markets || []).length} deep` : `${Number(status.digit9_percentage || 0).toFixed(1)}%`));
    const statusLines = [
      `State: ${status.cloud_status || "Stopped"}`,
      `Last signal: ${status.last_signal || "Waiting"}`,
      isProfit ? `Crash gap ticks: ${status.ticks_since_crash || 0}/30` : `Ticks: ${status.tick_count || 0}/100`,
      `Trade lock: ${status.trade_locked ? "locked" : "open for next setup"}`,
      `Last result: ${status.last_trade_result || "none"}`,
      `Jamaica time: ${status.jamaica_time || "--:--"} ${status.jamaica_timezone || "EST Jamaica"}`,
      `Time window: ${status.trade_window_label || "Anytime"}`,
      `Cloud ID: ${status.cloud_account_id || status.token_fingerprint || "not verified"}`,
      `PAT account: ${status.token_verified ? "verified" : "connect and select a PAT account to view/run Cloud"}`,
    ];
    setText("cloudStatusText", statusLines.join("\n"));
    setText("cloudDecisionLog", statusLines.concat([
      `Markets: ${(status.allowed_markets || []).join(", ")}`,
      isProfit ? `Daily trades: ${status.daily_trade_count || 0}/${status.max_daily_trades || 2}` : `Capital build: ${status.capital_build_mode ? "ON" : "OFF"}`,
    ]).join("\n"));
  }
  async function refreshStatus(silent){
    if(statusRequest) return statusRequest;
    statusRequest = (async()=>{
      try{
        const status = await getJSON("/cloud/under9/status");
        renderStatus(status);
        return status;
      }catch(e){
        if(!silent && typeof showToast === "function") showToast(e.message || "Cloud status failed", "error");
        return null;
      }finally{
        statusRequest = null;
      }
    })();
    return statusRequest;
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

  async function runCloudAction(action){
    if(actionBusy) return;
    const normalized = String(action || "").toLowerCase();
    if(!["start","stop","restart"].includes(normalized)) return;
    actionBusy = normalized;
    renderCloudToggle(normalized === "stop" ? true : !!(latestStatus && latestStatus.running));
    try{
      const body = normalized === "start" ? readSettings() : {};
      const data = await postJSON(`/cloud/under9/${normalized}`, body);
      settingsDirty = false;
      writeSettings(data, true);
      latestStatus = data;
      renderStatus(data);
      if(data.running) startPoll();
      if(typeof showToast === "function"){
        if(normalized === "stop") showToast("Cloud Bot stopped", "error");
        else if(normalized === "restart") showToast("Cloud Bot restarted", "success");
        else showToast(`${presetLabel(data)} started`, "success");
      }
    }catch(e){
      if(typeof showToast === "function") showToast(e.message || `Cloud ${normalized} failed`, "error");
    }finally{
      actionBusy = "";
      renderCloudToggle(!!(latestStatus && latestStatus.running));
    }
  }
  window.toggleCloudUnder9 = function(){
    const running = !!(latestStatus && latestStatus.running);
    return runCloudAction(running ? "stop" : "start");
  };
  window.startCloudUnder9 = function(){ return runCloudAction("start"); };
  window.stopCloudUnder9 = function(){ return runCloudAction("stop"); };
  window.restartCloudUnder9 = function(){ return runCloudAction("restart"); };
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
  window.openCloudSessionPopup = function(){
    updatePresetUI();
    const popup = byId("cloudSessionPopup");
    if(popup) popup.style.display = "flex";
  };
  window.closeCloudSessionPopup = function(){
    const popup = byId("cloudSessionPopup");
    if(popup) popup.style.display = "none";
  };
  window.applyCloudSessionPopup = function(){
    const trades = Math.floor(readNumber("cloudTradesPerSession", 0));
    const runs = Math.floor(readNumber("cloudSessionRuns", 0));
    const delay = Math.floor(readNumber("cloudSessionDelay", 0));
    const unit = String(((byId("cloudSessionDelayUnit") || {}).value || ""));
    if(trades < 1 || trades > 100){ if(typeof showToast === "function") showToast("Trades per session must be between 1 and 100.", "error"); return; }
    if(runs < 1 || runs > 10){ if(typeof showToast === "function") showToast("Session runs must be between 1 and 10.", "error"); return; }
    if(delay < 1 || !["ticks","seconds","minutes"].includes(unit)){ if(typeof showToast === "function") showToast("Enter a valid session wait.", "error"); return; }
    settingsDirty = true;
    updateCloudSessionSummary();
    window.closeCloudSessionPopup();
    if(typeof showToast === "function") showToast("Cloud session settings applied. Save Cloud Settings to keep them.", "success");
  };
  window.resetCloudBudget = async function(){
    const input = byId("cloudBudget");
    if(input) input.value = "";
    if(typeof saveProfileBudget === "function") await saveProfileBudget("CLOUD");
  };

  async function onMount(){
    bindSocket();
    buildMarketPicker();
    bindSettingsDirtyHandlers();
    updatePresetUI();
    await refreshStatus(true);
    startPoll();
  }
  async function afterLoadProfileUI(){ return onMount(); }
  async function onActivate(){ return onMount(); }
  async function onDeactivate(){
    stopPoll();
    socketBound = false;
    window.closeCloudSessionPopup();
  }

  if(typeof window.registerProfileModule === "function"){
    window.registerProfileModule(PROFILE, { onMount, afterLoadProfileUI, onActivate, onDeactivate });
  }else{
    window.ProfileModules = window.ProfileModules || {};
    window.ProfileModules[PROFILE] = { onMount, afterLoadProfileUI, onActivate, onDeactivate };
  }
})();
