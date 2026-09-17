/* One global component. Only server-issued, allowlisted control effects are applied. */
(() => {
  "use strict";
  const preference = document.getElementById("aiBubblePreference");
  if (!preference || document.getElementById("aiIntelligence")) return;
  const root = document.createElement("section");
  root.id = "aiIntelligence";
  root.setAttribute("aria-label", "AI Intelligence");
  root.innerHTML = `
    <button class="ai-launcher" type="button" title="Open AI Intelligence" aria-label="Open AI Intelligence" aria-expanded="false" hidden><img src="/static/images/logo.png" alt="KOOLKID"></button>
    <section class="ai-panel" role="dialog" aria-label="AI Intelligence chat" hidden>
      <header class="ai-header"><img src="/static/images/logo.png" alt=""><div class="ai-heading"><strong>AI Intelligence</strong><span class="ai-ready">Connecting</span></div>
        <button class="ai-tool" data-tool="intelligence" title="Trading intelligence" aria-label="Trading intelligence"><i data-lucide="brain-circuit"></i></button>
        <button class="ai-tool" data-tool="clear" title="Clear chat" aria-label="Clear chat"><i data-lucide="trash-2"></i></button>
        <button class="ai-tool" data-tool="minimize" title="Minimize" aria-label="Minimize"><i data-lucide="minus"></i></button>
        <button class="ai-tool" data-tool="close" title="Close chat" aria-label="Close chat"><i data-lucide="x"></i></button>
      </header>
      <nav class="ai-tabs"><button type="button" data-ai-view="chat" class="is-active">Assistant</button><button type="button" data-ai-view="monitor">Intelligence</button></nav>
      <div class="ai-messages ai-chat-view" role="log" aria-live="polite"></div>
      <div class="ai-thinking ai-chat-view" role="status" hidden>Thinking...</div>
      <form class="ai-compose ai-chat-view"><textarea aria-label="Message AI Intelligence" maxlength="1200" placeholder="Ask AI Intelligence" rows="2"></textarea><button type="submit" class="ai-tool ai-send" title="Send" aria-label="Send"><i data-lucide="send"></i></button></form>
      <section class="ai-monitor" hidden>
        <div class="ai-monitor-head"><div><strong>Market Intelligence</strong><span class="ai-engine-mode">SIGNAL ONLY</span></div><button type="button" class="ai-refresh">Refresh</button></div>
        <div class="ai-status-grid"><div><span>AI status</span><strong data-ai-stat="status">CONNECTING</strong></div><div><span>Decision</span><strong data-ai-stat="decision">SCANNING</strong></div><div><span>Confidence</span><strong data-ai-stat="score">0%</strong></div><div><span>Stage</span><strong data-ai-stat="stage">SCANNING</strong></div></div>
        <form class="ai-scan-form">
          <label>MT5 account<select name="account" required></select></label>
          <label>Strategy<select name="strategy"><option>HUMAN APOSTLE</option><option>DEAR BRUCE</option></select></label>
          <label>Symbol<select name="symbol" required><option value="">Choose account first</option></select></label>
          <label>Execution timeframe<select name="timeframe"><option>M1</option><option>M5</option><option>M15</option><option>M30</option><option>H1</option><option>H4</option><option>H8</option><option>D1</option></select></label>
          <label>Operating mode<select name="mode"><option>ANALYSIS ONLY</option><option>ALERT ONLY</option><option>MANUAL CONFIRMATION</option><option>AI AUTO TRADE</option><option>EX5 + AI CONFIRMATION</option></select></label>
          <label>Minimum confidence<input name="threshold" type="number" min="1" max="100" value="75"></label>
          <button type="submit" class="ai-scan">Evaluate completed candles</button>
        </form>
        <div class="ai-decision"><strong>Decision explanation</strong><p>No setup evaluated yet.</p></div>
        <details open><summary>Recent AI decisions</summary><div class="ai-decisions"></div></details>
        <details><summary>Teach AI</summary><form class="ai-teach-form"><textarea name="teaching" maxlength="1200" placeholder="Teach a trading rule without changing live rules automatically." required></textarea><button type="submit">Store candidate rule</button></form><div class="ai-knowledge"></div></details>
        <div class="ai-future">Backtesting, approved learning models, internet context, cloud scheduling, and demo auto-execution are not connected in this milestone.</div>
      </section>
      <footer class="ai-footer"><button class="ai-hide" type="button">Hide AI Bubble</button><button class="ai-emergency" type="button">Stop All Trading</button></footer>
    </section>`;
  document.body.append(root);
  if (window.lucide) window.lucide.createIcons({root});
  const launcher = root.querySelector(".ai-launcher");
  const panel = root.querySelector(".ai-panel");
  const log = root.querySelector(".ai-messages");
  const input = root.querySelector("textarea");
  const thinking = root.querySelector(".ai-thinking");
  const ready = root.querySelector(".ai-ready");
  const monitor = root.querySelector(".ai-monitor");
  const chatViews = root.querySelectorAll(".ai-chat-view");
  let csrf = "";
  let busy = false;
  let cancelled = 0;
  let lastProfile = "";
  let socketBound = null;
  let contextId = null;
  let intelligenceLoaded = false;

  async function api(path, data) {
    const response = await fetch(`/ai-intelligence/${path}`, {
      method: data === undefined ? "GET" : "POST", credentials: "same-origin", cache: "no-store",
      headers: data === undefined ? {} : {"Content-Type": "application/json", "X-AI-CSRF": csrf},
      body: data === undefined ? undefined : JSON.stringify(data)
    });
    const body = await response.json();
    if (!response.ok) {
      if (response.status === 403) ready.textContent = "Access unavailable";
      throw new Error(body.error || "Request could not be completed.");
    }
    return body;
  }

  function message(text, role = "assistant") {
    const node = document.createElement("div");
    node.className = `ai-message${role === "user" ? " ai-user" : ""}`;
    node.textContent = String(text);
    log.append(node);
    while (log.children.length > 80) log.firstElementChild.remove();
    log.scrollTop = log.scrollHeight;
    return node;
  }

  function show(open) {
    panel.hidden = !open;
    launcher.setAttribute("aria-expanded", String(open));
    if (open) input.focus();
    else launcher.focus();
  }

  function showView(name) {
    const monitoring = name === "monitor";
    monitor.hidden = !monitoring;
    chatViews.forEach(node => node.hidden = monitoring || (node === thinking && !busy));
    root.querySelectorAll("[data-ai-view]").forEach(button => button.classList.toggle("is-active", button.dataset.aiView === name));
    panel.classList.toggle("ai-panel-wide", monitoring);
    if (monitoring && !intelligenceLoaded) loadIntelligence();
  }

  function renderIntelligence(data) {
    intelligenceLoaded = true;
    root.querySelector('[data-ai-stat="status"]').textContent = data.status || "READY";
    root.querySelector(".ai-engine-mode").textContent = data.execution || "SIGNAL ONLY";
    const account = root.querySelector('.ai-scan-form [name="account"]');
    const previous = account.value;
    account.replaceChildren();
    for (const row of data.accounts || []) {
      const option = document.createElement("option");
      option.value = row.login;
      option.textContent = `${row.name} (${row.login})${row.connected ? "" : " - OFFLINE"}`;
      option.disabled = !row.connected;
      account.append(option);
    }
    if (previous && [...account.options].some(option => option.value === previous && !option.disabled)) account.value = previous;
    renderDecisionRows(data.recent || []);
    renderKnowledge(data.knowledge || []);
    if (account.value) loadIntelligenceSymbols(account.value);
  }

  function renderDecisionRows(rows) {
    const wrap = root.querySelector(".ai-decisions");
    wrap.replaceChildren();
    for (const row of rows.slice(0, 20)) {
      const item = document.createElement("div");
      item.className = "ai-decision-row";
      item.textContent = `${row.decision} · ${row.score || 0}% · ${row.state?.symbol || ""} ${row.state?.timeframe || ""} — ${row.reason || ""}`;
      wrap.append(item);
    }
    if (!rows.length) wrap.textContent = "No evaluations recorded yet.";
  }

  function renderKnowledge(rows) {
    const wrap = root.querySelector(".ai-knowledge");
    wrap.replaceChildren();
    for (const row of rows.slice(0, 20)) {
      const item = document.createElement("div");
      item.className = "ai-knowledge-row";
      item.textContent = `${row.enabled ? "ON" : "OFF"} · ${row.strategy} · v${row.version}: ${row.rule}`;
      wrap.append(item);
    }
  }

  async function loadIntelligence() {
    try { renderIntelligence(await api("intelligence/status")); }
    catch (error) { root.querySelector('[data-ai-stat="status"]').textContent = "OFFLINE"; root.querySelector(".ai-decision p").textContent = error.message; }
  }

  async function loadIntelligenceSymbols(account) {
    const field = root.querySelector('.ai-scan-form [name="symbol"]');
    field.innerHTML = '<option value="">Loading symbols...</option>';
    try {
      const data = await api(`intelligence/symbols?account=${encodeURIComponent(account)}`);
      field.replaceChildren(...data.symbols.map(name => Object.assign(document.createElement("option"), {value: name, textContent: name})));
    } catch (error) { field.innerHTML = '<option value="">Symbols unavailable</option>'; }
  }

  function quickActions() {
    const group = document.createElement("div");
    group.className = "ai-quick";
    for (const [label, command] of [["Check Balance", "What's my balance?"], ["Trade History", "Show my last 5 trades"], ["Current Settings", "Current settings"], ["Resume Trading", "Resume trading"]]) {
      const b = document.createElement("button");
      b.className = "ai-command";
      b.type = "button";
      b.textContent = label;
      b.addEventListener("click", () => send(command));
      group.append(b);
    }
    log.append(group);
  }

  function currentProfile() {
    return typeof activeProfile !== "undefined" ? activeProfile : window.BotApp?.currentProfile?.() || lastProfile;
  }

  // These are the existing controls, not another martingale implementation.
  const martingale = {
    KOOLKID: {toggle: "koolkidMartingaleToggleBtn", multiplier: "koolkidMartingaleMultiplier", label: "KOOLKID single-contract martingale"},
    HUMAN: {toggle: "humanRfMartingaleToggleBtn", multiplier: "humanRfMartingaleMultiplier", label: "HUMAN Rise/Fall martingale"},
    JOKERJOE: {toggle: "jokerjoeBatchMartingaleToggleBtn", label: "JOKERJOE Match Batch martingale"},
    UNCHAIN: {toggle: "unchainSingleMartingaleToggleBtn", multiplier: "unchainSingleMartingaleMultiplier", label: "UNCHAIN single-contract martingale"}
  };

  function martingaleSnapshot() {
    const adapter = martingale[currentProfile()];
    if (!adapter) return "This profile uses its own martingale controls.";
    const button = document.getElementById(adapter.toggle);
    const field = document.getElementById(adapter.multiplier);
    return `${adapter.label}: ${button?.textContent?.trim() || "unavailable"}; multiplier: ${field?.value || (currentProfile() === "JOKERJOE" ? "fixed doubling" : "not selected")}.`;
  }

  function applyMartingale(action) {
    if (action.ui_profile !== currentProfile()) throw new Error("Profile changed.");
    const adapter = martingale[action.ui_profile];
    if (!adapter) throw new Error("Control unavailable.");
    const button = document.getElementById(adapter.toggle);
    if (action.action === "set_martingale_multiplier") {
      const field = document.getElementById(adapter.multiplier);
      if (!field || !Number.isFinite(action.multiplier) || action.multiplier < 1 || action.multiplier > 100) throw new Error("Multiplier unavailable.");
      field.value = String(action.multiplier);
      field.dispatchEvent(new Event("input", {bubbles: true}));
      field.dispatchEvent(new Event("change", {bubbles: true}));
      if (Number(field.value) !== action.multiplier) throw new Error("Multiplier was not applied.");
    } else {
      // The KOOLKID pair toggle places trades immediately; it is not a settings toggle.
      if (!button || button.disabled || !/MARTINGALE:\s*(ON|OFF)/i.test(button.textContent)) throw new Error("Select the normal martingale panel first.");
      const desired = action.action === "enable_martingale";
      const enabled = /MARTINGALE:\s*ON/i.test(button.textContent);
      if (enabled !== desired) button.click();
      if (/MARTINGALE:\s*ON/i.test(button.textContent) !== desired) throw new Error("Setting did not change.");
    }
  }

  const stopControls = {
    HUMAN: ["quickStopHumanRfMartingale", "quickStopHumanSingleMartingale", "quickStopHumanDualMartingale", "stopHumanParityMartingale", "quickStopHumanSpecialAuto"],
    KOOLKID: ["quickStopKoolkidSingleMartingale", "stopOver3Under6PairMartingaleKoolkid", "stopKoolkidOver6ScanMartingale", "stopKoolkidBalancedRecovery", "stopKoolkidPairRecovery"],
    JOKERJOE: ["quickStopJokerjoeBatchMartingale", "stopKid100WinsAutosJokerjoe"]
  };

  function stopBrowser(profile) {
    cancelled++;
    const targets = profile ? [profile] : Object.keys(stopControls);
    for (const p of targets) for (const name of stopControls[p] || []) {
      if (typeof window[name] === "function") {
        try { window[name]("AI Intelligence stop"); } catch (_) { /* Server pause is authoritative. */ }
      }
    }
    if (!profile || profile === "UNCHAIN") {
      document.querySelector('[data-action="unchain-single-martingale-stop"]')?.click();
    }
  }

  async function sync(result) {
    if (result.profile_data && typeof window.setProfile === "function") await window.setProfile(result.profile_data.profile, result.profile_data);
    const settings = result.settings;
    if (settings) {
      lastProfile = settings.profile;
      const stake = document.getElementById("stake");
      if (stake && settings.stake != null) stake.value = settings.stake;
      if (typeof setConfirmedMarketSymbol === "function" && settings.market) setConfirmedMarketSymbol(settings.market);
      const auto = document.getElementById("autoBtn");
      if (auto && typeof settings.auto_trade === "boolean") {
        auto.innerText = settings.auto_trade ? "AUTO ON" : "AUTO OFF";
        auto.style.background = settings.auto_trade ? "#22c55e" : "#38bdf8";
      }
      if (settings.auto_modes && typeof updateAutoModeButtons === "function") updateAutoModeButtons(settings.auto_modes);
    }
    if (result.control?.action === "change_barrier") {
      const field = document.getElementById("barrier");
      if (field) field.value = result.control.barrier;
    }
  }

  function renderResult(result) {
    if (result.status === "confirmed") message(`${result.trade_type} placed on ${result.market}, ${result.stake} USD stake. Contract ${result.contract_id}.`);
    else message(result.message || `${result.status}: ${result.trade_type || "action"} ${result.market || ""}`);
    if (result.trades) {
      if (!result.trades.length) message("No trades are available in this bot session.");
      for (const trade of result.trades) message(`${trade.time} | ${trade.type} | ${trade.symbol} | ${trade.result} | P/L ${trade.profit}`);
    }
    if (result.data) message(martingaleSnapshot());
  }

  function actionLabel(a) {
    if (a.action === "place_trade") return `${a.trade_type}${a.barrier == null ? "" : " " + a.barrier} on ${a.market}, ${a.stake} USD${a.current_stake_used ? " (current stake)" : ""}, ${a.duration}${a.duration_unit}`;
    if (a.ui_profile) return `${a.action.replaceAll("_", " ")} ${a.multiplier ?? ""}: ${martingale[a.ui_profile]?.label || a.ui_profile}`;
    return `${a.action.replaceAll("_", " ")}${a.profile ? " " + a.profile : ""}${a.market ? " " + a.market : ""}${a.stake != null ? " " + a.stake + " USD" : ""}${a.barrier != null ? " " + a.barrier : ""}`;
  }

  async function executePlan(plan, button) {
    if (busy) return;
    button.disabled = true;
    busy = true;
    thinking.hidden = false;
    thinking.textContent = "Applying confirmed actions...";
    const generation = cancelled;
    try {
      for (let index = 0; index < plan.actions.length; index++) {
        if (generation !== cancelled) break;
        const profileBefore = currentProfile();
        let data = await api("execute", {plan_id: plan.plan_id, index});
        if (profileBefore !== currentProfile()) {
          renderResult(data.result);
          throw new Error("Profile changed while the action was processing. Remaining actions cancelled; check the dashboard.");
        }
        if (data.settings && !data.result.settings) data.result.settings = data.settings;
        await sync(data.result);
        if (data.result.status === "ui_pending") {
          let success = false;
          try { if (generation === cancelled) { applyMartingale(data.result.ui_action); success = true; } } catch (_) { success = false; }
          data = await api("ui-result", {plan_id: plan.plan_id, index, success});
        }
        renderResult(data.result);
        if (data.result.halt_remaining) break;
      }
    } catch (e) { message(e.message); }
    finally { busy = false; thinking.hidden = true; }
  }

  async function send(text) {
    if (/^(?:please )?stop (?:everything|all(?: auto(?:matic)?)?(?: trading)?)[.! ]*$/i.test(text.trim())) {
      input.value = "";
      return stopEverything();
    }
    if (!text.trim() || busy) return;
    busy = true;
    thinking.hidden = false;
    thinking.textContent = "Thinking...";
    input.value = "";
    // Server rejects credential-like messages before they enter chat history.
    try {
      const data = await api("command", {message: text});
      message(text, "user");
      if (data.plan_id) {
        const node = message(`${data.settings.account_type.toUpperCase()} ${data.settings.account}\n${data.actions.map(actionLabel).join("\n")}\n\n${data.message}`);
        const button = document.createElement("button");
        button.className = "ai-confirm";
        button.textContent = "Confirm actions";
        button.type = "button";
        button.addEventListener("click", () => executePlan(data, button));
        node.append(button);
      } else for (const result of data.results || []) renderResult(result);
    } catch (e) { message(e.message); }
    finally { busy = false; thinking.hidden = true; log.scrollTop = log.scrollHeight; }
  }

  async function stopEverything() {
    stopBrowser();
    try {
      const data = await api("command", {message: "Stop everything"});
      for (const result of data.results || []) { await sync(result); renderResult(result); }
    } catch (e) { message(`Stop not confirmed: ${e.message}`); }
  }

  async function visibility(visible) {
    try {
      const data = await api("preferences", {visible});
      preference.checked = data.visible;
      launcher.hidden = !data.visible;
      if (!data.visible) panel.hidden = true;
    } catch (e) { preference.checked = !visible; message(e.message); }
  }

  launcher.addEventListener("click", () => show(panel.hidden));
  root.querySelector('[data-tool="intelligence"]').addEventListener("click", () => { show(true); showView("monitor"); });
  root.querySelectorAll("[data-ai-view]").forEach(button => button.addEventListener("click", () => showView(button.dataset.aiView)));
  root.querySelector(".ai-refresh").addEventListener("click", loadIntelligence);
  root.querySelector('.ai-scan-form [name="account"]').addEventListener("change", event => loadIntelligenceSymbols(event.target.value));
  root.querySelector(".ai-scan-form").addEventListener("submit", async event => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const button = event.currentTarget.querySelector("button");
    button.disabled = true;
    try {
      const result = await api("intelligence/evaluate", {
        account: form.get("account"), symbol: form.get("symbol"), timeframe: form.get("timeframe"),
        strategy: form.get("strategy"), mode: form.get("mode"), threshold: Number(form.get("threshold")),
        candle_confirmation: true, target_r: 2
      });
      root.querySelector('[data-ai-stat="decision"]').textContent = result.decision;
      root.querySelector('[data-ai-stat="score"]').textContent = `${result.score || 0}%`;
      root.querySelector('[data-ai-stat="stage"]').textContent = result.state?.state || "SCANNING";
      root.querySelector(".ai-decision p").textContent = `${result.reason}${result.execution_note ? " " + result.execution_note : ""}`;
      await loadIntelligence();
    } catch (error) { root.querySelector(".ai-decision p").textContent = error.message; }
    finally { button.disabled = false; }
  });
  root.querySelector(".ai-teach-form").addEventListener("submit", async event => {
    event.preventDefault();
    const teaching = event.currentTarget.elements.teaching.value;
    const strategy = root.querySelector('.ai-scan-form [name="strategy"]').value;
    const button = event.currentTarget.querySelector("button");
    button.disabled = true;
    try {
      const result = await api("intelligence/teach", {teaching, strategy});
      event.currentTarget.reset();
      root.querySelector(".ai-decision p").textContent = result.message;
      await loadIntelligence();
    } catch (error) { root.querySelector(".ai-decision p").textContent = error.message; }
    finally { button.disabled = false; }
  });
  root.querySelector("form").addEventListener("submit", e => { e.preventDefault(); send(input.value); });
  input.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(input.value); }
    if (e.key === "Escape") show(false);
  });
  root.querySelectorAll('[data-tool="minimize"],[data-tool="close"]').forEach(b => b.addEventListener("click", () => show(false)));
  root.querySelector('[data-tool="clear"]').addEventListener("click", async () => {
    try { await api("clear", {}); log.replaceChildren(); quickActions(); } catch (e) { message(e.message); }
  });
  root.querySelector(".ai-hide").addEventListener("click", () => visibility(false));
  preference.addEventListener("change", () => visibility(preference.checked));
  root.querySelector(".ai-emergency").addEventListener("click", stopEverything);

  function bindSocket() {
    const sock = typeof socket !== "undefined" ? socket : null;
    if (sock && sock !== socketBound) {
      socketBound = sock;
      sock.on("ai_intelligence_stop", data => stopBrowser(data?.profile));
      sock.on("connection_status", () => loadState().catch(() => {}));
    }
  }
  const timer = setInterval(bindSocket, 1500);
  window.addEventListener("pagehide", () => clearInterval(timer), {once: true});
  async function loadState() {
    const data = await api("state");
    csrf = data.csrf;
    launcher.hidden = !data.visible;
    preference.checked = data.visible;
    lastProfile = data.settings.profile;
    ready.textContent = "Ready";
    if (contextId !== data.context_id) {
      if (contextId !== null) cancelled++;
      log.replaceChildren();
      for (const item of data.messages) message(item.text, item.role);
      if (!data.messages.length) quickActions();
      contextId = data.context_id;
    }
    bindSocket();
  }
  loadState().catch(e => { preference.closest("label").hidden = true; ready.textContent = e.message; });
})();
