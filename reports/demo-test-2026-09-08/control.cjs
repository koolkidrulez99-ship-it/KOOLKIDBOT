const { chromium } = require('C:/Users/jjmje/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs = require('node:fs');
const path = require('node:path');
const log = value => {
  const entry = { at: new Date().toISOString(), ...value };
  fs.appendFileSync(path.join(__dirname, 'evidence.jsonl'), JSON.stringify(entry) + '\n');
  const output = { ...entry };
  if (output.events) output.events = output.events.map(e => ({at:e.at,event:e.event,...Object.fromEntries(Object.entries(e.data || {}).filter(([k]) => ['contract_id','type','contract_type','batch_id','mode','stake','profit','result','status','message'].includes(k)))}));
  if (output.budgets) output.budgets = { [output.profile]:output.budgets[output.profile] };
  if (output.kind === 'trade_response' && output.data?.payload) output.data = {...output.data,payload:'[strategy analysis retained in evidence file]'};
  console.log(JSON.stringify(output));
};

async function main() {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9227');
  const page = browser.contexts().flatMap(c => c.pages()).find(p => p.url() === 'http://127.0.0.1:5055/');
  if (!page) throw new Error('Dashboard tab unavailable');
  await page.evaluate(() => {
    if (window.__demoTest) return;
    const safe = value => {
      if (Array.isArray(value)) return value.map(safe);
      if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, /token|password|secret|authorization|cookie|otp|loginid|account_id|client_id|username|email|url/i.test(k) ? '[REDACTED]' : safe(v)]));
      if (typeof value === 'string') return value.replace(/(?:D|R)OT\d+|VRTC\d+|CR\d+/g, '[ACCOUNT REDACTED]').replace(/Bearer\s+\S+/gi, 'Bearer [REDACTED]').replace(/https?:\/\/\S+|wss?:\/\/\S+/gi, '[URL REDACTED]');
      return value;
    };
    const recorder = window.__demoTest = { events: [], ticks: 0, started: null, baseline: null, safe };
    const live = typeof socket !== 'undefined' ? socket : window.socket;
    live.onAny((event, data) => {
      if (event === 'tick') { recorder.ticks++; return; }
      if (['trade_placed', 'trade_result', 'api_error', 'stats_update', 'balance_update'].includes(event)) {
        recorder.events.push({ at: new Date().toISOString(), event, data: safe(data) });
      }
    });
  });
  const api = (url, body) => page.evaluate(async ({ url, body }) => {
    const response = await fetch(url, body === undefined ? { cache: 'no-store' } : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    return { http: response.status, data: window.__demoTest.safe(await response.json()) };
  }, { url, body });
  const reveal = async field => {
    for (const details of await field.locator('xpath=ancestor::details').all()) {
      if (await details.getAttribute('open') === null) await details.locator(':scope > summary').click();
    }
  };
  const status = () => page.evaluate(async () => {
    const d = await (await fetch('/api_connection_status', { cache: 'no-store' })).json();
    const id = d.pat_current_account_id || d.loginid || '';
    const account = (d.pat_accounts || []).find(a => a.account_id === id);
    const demo = !!account && (account.is_virtual === true || account.account_kind === 'demo');
    return { connected: d.connected, hasSavedToken: !!d.has_token, demo, account: '***' + id.slice(-4), balance: d.account_balance, profile: d.active_profile, currency: account?.currency, mode: d.connection_mode, tickHealthy: d.tick_stream_healthy, tickRecovering: d.tick_stream_recovering, symbols: d.tick_stream_symbols, staleSymbols: d.tick_stream_stale_symbols, tickAge: d.last_tick_age_sec, ticks: window.__demoTest.ticks, budgets: d.profile_budgets, counters: Object.fromEntries(Object.entries(d).filter(([k]) => !/account/i.test(k) && /count|pending|open_contract/i.test(k))) };
  });
  const before = await status();
  const [command, ...args] = process.argv.slice(2);
  if (command === 'resume-status') {
    await page.bringToFront();
    log({kind:'resume_status', ...before});
    return;
  }
  const recoverableDemo = command === 'reconnect' && before.mode === 'pat' && before.hasSavedToken;
  if ((!before.connected && !recoverableDemo) || !before.demo || before.currency !== 'USD') throw new Error('Connected USD demo account required');
  if (command === 'status') log({ kind: 'status', ...before });
  else if (command === 'ui') {
    log({ kind: 'ui', data: await page.evaluate(() => Array.from(document.querySelectorAll('button, input, select, [id$="Status"], [id$="StatusText"]')).filter(e => e.getBoundingClientRect().width && !/token|account|login|password|user|email/i.test(e.id)).map(e => ({ tag: e.tagName, id: e.id, text: e.tagName === 'INPUT' ? undefined : e.textContent.trim().replace(/\s+/g, ' ').slice(0, 250), value: ['INPUT', 'SELECT'].includes(e.tagName) ? e.value : undefined, checked: e.type === 'checkbox' ? e.checked : undefined, disabled: e.disabled, onclick: e.getAttribute('onclick') }))) });
  } else if (command === 'profile') {
    if (!['KOOLKID','JOKERJOE','HUMAN','UNCHAIN','NTT','CLOUD'].includes(args[0])) throw new Error('Unknown profile');
    await page.evaluate(p => setProfile(p), args[0]);
    await page.waitForTimeout(1500);
    log({ kind: 'profile', ...(await status()) });
  } else if (command === 'read') {
    if (!['/human_rf_status','/human_manual_contracts','/unchain_status','/ntt_status','/market_state','/profile_history_snapshot','/auto-session/status','/seqvix_status','/cloud/under9/status'].includes(args[0].split('?')[0])) throw new Error('Read endpoint not allowed');
    log({ kind: 'api_read', path: args[0], ...(await api(args[0])) });
  } else if (command === 'resume-remaining') {
    if (Object.values(before.budgets).some(b => b.enabled || b.reserved)) throw new Error('Existing budget or exposure; do not reset cumulative limits');
    if (before.balance !== 47587.36) throw new Error('Balance changed since user-confirmed reconciliation');
    for (const profile of ['KOOLKID','JOKERJOE','HUMAN','UNCHAIN','NTT']) {
      const history = await api('/profile_history_snapshot?profile=' + profile);
      log({kind:'resume_history_check',profile,...history});
      if (history.http !== 200 || JSON.stringify(history.data).includes('"pending":true')) throw new Error('Pending history or unavailable preflight');
    }
    for (const [profile,budget] of Object.entries({KOOLKID:1,JOKERJOE:2,NTT:2,HUMAN:0.1,UNCHAIN:0.1,CLOUD:0.1})) {
      const result = await api('/profile_budget',{profile,budget});
      if (result.http !== 200) throw new Error('Remaining budget setup failed');
      log({kind:'remaining_budget',profile,budget});
    }
    const excluded = await page.evaluate(balance => {
      const r = window.__demoTest;
      const excludedEventCount = r.events.length;
      r.events = [];
      r.started = Date.now() - 1380000;
      r.baseline = Number((balance + 1.69).toFixed(2));
      r.resumePrepared = true;
      return excludedEventCount;
    },before.balance);
    log({kind:'remaining_prepared',carriedLoss:1.69,carriedActiveMinutes:23,remainingMinutes:37,excludedPauseEventCount:excluded,userConfirmedUnrelatedBalanceChange:266.22,...(await status())});
  } else if (command === 'resume-prepare') {
    if (Object.values(before.budgets).some(b => b.enabled || b.reserved)) throw new Error('Existing budget or exposure; do not reset cumulative limits');
    if (before.balance !== 47854.87) throw new Error('Balance changed since checkpoint; reconcile before resuming');
    for (const [profile,budget] of Object.entries({KOOLKID:2.5,JOKERJOE:2.5,NTT:2,HUMAN:0.1,UNCHAIN:0.1,CLOUD:0.1})) {
      const result=await api('/profile_budget',{profile,budget});
      if(result.http!==200) throw new Error('Resume budget setup failed');
      log({kind:'resume_budget',profile,budget});
    }
    await page.evaluate(balance => {
      const r=window.__demoTest;
      r.started=Date.now()-720000;
      r.baseline=Number((balance+0.4).toFixed(2));
      r.resumePrepared=true;
    },before.balance);
    log({kind:'resume_prepared',carriedLoss:0.4,carriedActiveMinutes:12,remainingMinutes:48,...(await status())});
  } else if (command === 'prepare') {
    if (Object.values(before.budgets).some(b => b.enabled || b.reserved)) throw new Error('Existing budget or exposure; inspect before changing');
    for (const [profile, budget] of Object.entries({ HUMAN:3, KOOLKID:1.5, JOKERJOE:1.5, UNCHAIN:1.5, NTT:1, CLOUD:1 })) {
      const result = await api('/profile_budget', { profile, budget });
      if (result.http !== 200) throw new Error('Budget setup failed');
      log({ kind: 'budget_prepared', profile, budget });
    }
    log({ kind:'prepared', ...(await status()) });
  } else if (command === 'budget') {
    if (!['KOOLKID','JOKERJOE','HUMAN','UNCHAIN','NTT'].includes(args[0])) throw new Error('Unknown budget profile');
    const budget = Number(args[1]);
    if (!(budget > 0 && budget <= 3)) throw new Error('Budget out of test range');
    log({ kind: 'budget', profile: args[0], ...(await api('/profile_budget', {profile: args[0], budget})) });
  } else if (command === 'fill') {
    if (/token|password|account|email|username/i.test(args[0])) throw new Error('Sensitive field excluded');
    const field = page.locator('#' + args[0]);
    await reveal(field);
    const type = await field.evaluate(e => e.tagName === 'SELECT' ? 'select' : e.type);
    if (type === 'select') await field.selectOption(args[1]);
    else if (type === 'checkbox') await field.setChecked(args[1] === 'true');
    else await field.fill(args[1] === 'EMPTY' ? '' : args[1]);
    log({kind: 'fill', id: args[0], value: args[1]});
  } else if (command === 'events') {
    log({ kind: 'events', data: await page.evaluate(() => window.__demoTest.events.splice(0)) });
  } else if (command === 'text') {
    log({ kind: 'text', selector: args[0], text: await page.locator(args[0]).innerText() });
  } else if (command === 'reconnect') {
    if (Object.values(before.budgets).some(b => b.reserved > 0)) throw new Error('Cannot reconnect while test positions are open');
    log({kind:'reconnect_start', ...before});
    log({kind:'reconnect_response', ...(await api('/martha_ai/emergency_reconnect',{reason:'authorized_demo_connection_test'}))});
    for (let i=0;i<24;i++) {
      await page.waitForTimeout(2000);
      const current = await status();
      log({kind:'reconnect_progress', ...current});
      if (current.connected && current.demo && current.tickHealthy && current.ticks > before.ticks) break;
    }
  } else if (command === 'trade') {
    const cases = {
      'koolkid-luck-auto': {profile:'KOOLKID',selector:'#koolluckBtn',cost:0.35,seconds:40,maxTrades:2,toggleRun:'toggleKoolluckAuto',status:'#koolluckBtn',fields:{stake:'0.35',barrier:'5',durationTicks:'1'}},
      'jokerjoe-kidgx-auto': {profile:'JOKERJOE',selector:'#kidGxBtnJokerjoe',cost:0.35,seconds:24,maxTrades:3,toggleRun:'toggleKidGxJokerjoe',status:'#kidGxBtnJokerjoe',fields:{stake:'0.35',barrier:'5',durationTicks:'1'}},
      'mutant-auto-base': {profile:'NTT',selector:'#nttAutoStartBtn',open:'#nttAutoBothBtn',cost:0.35,seconds:24,maxTrades:2,settleSeconds:16,stopSelector:'#nttAutoStopBtn',status:'#nttAutoReason',fields:{nttTouchStake:'0.35',nttNoTouchStake:'0.35',nttTouchBarrier:'+0.160',nttNoTouchBarrier:'+0.160',nttDurationUnit:'t',nttDuration:'5',nttAutoBarrier:'+0.160',nttAutoBudget:'0.35',nttAutoMartingaleToggle:false,nttAutoStep50Toggle:false}},
      'koolkid-three-under': {profile:'KOOLKID',selector:'button[onclick="take3(\'UNDER\')"]',cost:1.05,fields:{stake:'0.35',barrier:'5',durationTicks:'1'}},
      'koolkid-burst-over': {profile:'KOOLKID',selector:'button[onclick="burst4(\'OVER\')"]',cost:1.4,fields:{stake:'0.35',barrier:'5',durationTicks:'1'}},
      'koolkid-auto': {profile:'KOOLKID',selector:'#autoBtn',cost:0.35,seconds:30,auto:true,status:'#autoBtn',fields:{stake:'0.35',barrier:'5',durationTicks:'1'}},
      'koolkid-martingale-stop': {profile:'KOOLKID',selector:'#koolkidMartingalePlaceBtn',cost:0.35,seconds:12,stop:'quickStopKoolkidSingleMartingale',status:'#koolkidMartingaleStatus',toggle:'#koolkidMartingaleToggleBtn',fields:{koolkidMartingaleAction:'OVER_5',koolkidMartingaleDuration:'1',koolkidMartingaleStartStake:'0.35',koolkidMartingaleMode:'MULTIPLIER',koolkidMartingaleMultiplier:'2',koolkidMartingaleMaxStake:'0.35',koolkidMartingaleTP:'0.10',koolkidMartingaleSL:'0.35'}},
      'jokerjoe-differs': {profile:'JOKERJOE',selector:'button[onclick="trade(\'DIFFERS\')"]',cost:0.35,fields:{stake:'0.35',barrier:'5',durationTicks:'1'}},
      'jokerjoe-match-batch': {profile:'JOKERJOE',selector:'#jokerjoeBatchMartingalePlaceBtn',cost:1.05,seconds:12,stop:'quickStopJokerjoeBatchMartingale',status:'#jokerjoeBatchMartingaleStatus',fields:{stake:'0.35',durationTicks:'1',jokerjoeBatchMartingaleStartStake:'1.05',jokerjoeBatchMartingaleMaxSteps:'1'}},
      'jokerjoe-auto': {profile:'JOKERJOE',selector:'#autoBtn',cost:0.35,seconds:30,auto:true,status:'#autoBtn',fields:{stake:'0.35',barrier:'5',durationTicks:'1'}},
      'mutant-touch': {profile:'NTT',selector:'button[data-action="ntt-trade-touch"]',cost:0.35,seconds:16,fields:{nttTouchStake:'0.35',nttNoTouchStake:'0.35',nttTouchBarrier:'+0.160',nttNoTouchBarrier:'+0.160',nttDurationUnit:'t',nttDuration:'5'}},
      'mutant-no-touch': {profile:'NTT',selector:'button[data-action="ntt-trade-no-touch"]',cost:0.35,seconds:16,fields:{nttTouchStake:'0.35',nttNoTouchStake:'0.35',nttTouchBarrier:'+0.160',nttNoTouchBarrier:'+0.160',nttDurationUnit:'t',nttDuration:'5'}},
      'mutant-both': {profile:'NTT',selector:'button[data-action="ntt-trade-both"]',cost:0.70,seconds:16,fields:{nttTouchStake:'0.35',nttNoTouchStake:'0.35',nttTouchBarrier:'+0.160',nttNoTouchBarrier:'+0.160',nttDurationUnit:'t',nttDuration:'5'}},
      'human-rise': { profile:'HUMAN', selector:'button[onclick="humanRFTrade(\'RISE\')"]', cost:0.35 },
      'human-fall': { profile:'HUMAN', selector:'button[onclick="humanRFTrade(\'FALL\')"]', cost:0.35 },
      'human-pair': { profile:'HUMAN', selector:'button[onclick="humanAutoRiseFall()"]', cost:0.70 },
      'human-do-both': { profile:'HUMAN', selector:'#humanRfMartingalePlaceBtn', cost:0.70, seconds:34, stop:'quickStopHumanRfMartingale', status:'#humanRfMartingaleStatus', toggle:'#humanRfMartingaleToggleBtn', fields:{ humanRfMartingaleDuration:'t:1', humanRfMartingaleRiseStake:'0.35', humanRfMartingaleFallStake:'0.35', humanRfMartingaleMultiplier:'2', humanRfMartingaleMaxStake:'0.35', humanRfMartingaleTp:'1', humanRfMartingaleSl:'0.70', humanRfMartingaleDoBothTrades:true } },
      'human-even-odd': { profile:'HUMAN', selector:'#humanParityMartingaleStartBtn', cost:0.70, seconds:25, stop:'stopHumanParityMartingale', status:'#humanParityMartingaleStatus', fields:{ humanParityMartingaleMode:'EVEN_ODD', humanParityMartingaleStake:'0.35', humanParityMartingaleMultiplier:'1', humanParityMartingaleDuration:'1', humanParityMartingaleTp:'1', humanParityMartingaleSl:'0.15' } },
      'human-dual-same': { profile:'HUMAN', selector:'#humanDualMarketPlaceBtn', cost:0.70, fields:{ humanDualMarketA:'stpRNG', humanDualMarketB:'stpRNG', humanDualTradeA:'RISE', humanDualTradeB:'FALL', humanDualStakeA:'0.35', humanDualStakeB:'0.35', humanDualDurationA:'1', humanDualDurationB:'1' } },
      'unchain-higher': { profile:'UNCHAIN', selector:'button[data-action="unchain-trade-higher"]', cost:0.35, fields:{unchainHigherStake:'0.35',unchainLowerStake:'0.35',unchainHigherBarrier:'+0.10',unchainLowerBarrier:'-0.10',unchainDurationUnit:'t',unchainDuration:'5'} },
      'unchain-lower': { profile:'UNCHAIN', selector:'button[data-action="unchain-trade-lower"]', cost:0.35, fields:{unchainHigherStake:'0.35',unchainLowerStake:'0.35',unchainHigherBarrier:'+0.10',unchainLowerBarrier:'-0.10',unchainDurationUnit:'t',unchainDuration:'5'} },
      'unchain-both': { profile:'UNCHAIN', selector:'button[data-action="unchain-trade-both"]', cost:0.70, fields:{unchainHigherStake:'0.35',unchainLowerStake:'0.35',unchainHigherBarrier:'+0.10',unchainLowerBarrier:'-0.10',unchainDurationUnit:'t',unchainDuration:'5'} },
    };
    const test = cases[args[0]];
    if (!test || before.profile !== test.profile) throw new Error('Test/profile mismatch');
    if (!before.tickHealthy) {
      let ready = false;
      for (let i=0;i<6;i++) { await page.waitForTimeout(1000); const s=await status(); if(s.tickHealthy && s.demo && s.connected) {ready=true;break;} }
      if(!ready) throw new Error('Wait for healthy ticks');
    }
    if (Object.values(before.budgets).some(b => b.reserved > 0)) throw new Error('Wait for existing exposure to settle');
    if (!before.budgets[test.profile]?.enabled || before.budgets[test.profile].remaining_budget < test.cost) throw new Error('Insufficient test budget');
    const limits = await page.evaluate(balance => {
      const r = window.__demoTest;
      if (!r.started) { r.started = Date.now(); r.baseline = balance; }
      return { start:r.started, elapsedMs:Date.now()-r.started, pnl:Number((balance-r.baseline).toFixed(2)), baseline:r.baseline };
    }, before.balance);
    if (limits.elapsedMs >= 3600000 || limits.pnl - test.cost < -10) throw new Error('Demo test limit reached');
    if (test.profile === 'HUMAN') {
      await page.locator('#stake').fill('0.35');
      await page.locator('#humanRfDuration').selectOption('1');
    }
    if (test.profile === 'UNCHAIN' && args[1]) {
      if (!/^\+0\.\d+$/.test(args[1])) throw new Error('Expected a relative test barrier');
      test.fields.unchainHigherBarrier=args[1];
      test.fields.unchainLowerBarrier=args[1].replace('+','-');
    }
    for (const [id,value] of Object.entries(test.fields || {})) {
      if (test.open && id === 'nttAutoBarrier') { await reveal(page.locator(test.open)); await page.locator(test.open).click(); }
      const field = page.locator('#'+id);
      await reveal(field);
      const type = await field.evaluate(e => e.tagName === 'SELECT' ? 'select' : e.type);
      if (type === 'select') await field.selectOption(value);
      else if (type === 'checkbox') await field.setChecked(value);
      else await field.fill(value);
    }
    if (test.toggle) await page.locator(test.toggle).click();
    if (test.auto) {
      if ((await page.locator('#autoBtn').innerText()).includes('ON')) throw new Error('Master Auto was already running; inspect before testing');
      await page.evaluate(() => syncAutoStake());
    }
    if (test.toggleRun) {
      if ((await page.locator(test.selector).innerText()).includes(': ON')) throw new Error('Named auto was already running');
      await page.evaluate(() => syncAutoStake());
    }
    page.on('response', async response => {
      const pathname = new URL(response.url()).pathname;
      if (['/human_rf_trade','/human_auto_rise_fall','/human_parity_trade','/human_dual_market_contracts','/unchain_trade','/ntt_trade','/manual_trade','/manual_3_trades','/burst_4','/toggle_auto','/toggle_kidgx_auto','/toggle_koolluck_auto','/toggle_ntt_auto_both'].includes(pathname)) {
        const data = await response.json().catch(() => ({ error:'non_json_response' }));
        const safeData = await page.evaluate(d => window.__demoTest.safe(d), data);
        log({kind:'trade_response', path:pathname, http:response.status(), data:safeData});
      }
    });
    const eventOffset = await page.evaluate(() => window.__demoTest.events.length);
    log({ kind:'test_start', test:args[0], ...limits });
    try {
      await reveal(page.locator(test.selector).last());
      await page.locator(test.selector).last().click();
      for (let i=0; i<(test.seconds || 12); i+=2) {
        await page.waitForTimeout(2000);
        const current = await status();
        if (!current.demo || !current.connected || current.balance < limits.baseline-8.8 || Date.now()-limits.start >= 3600000) throw new Error('Demo watchdog stopped this test');
        if (test.status) log({kind:'cycle_status',test:args[0],text:await page.locator(test.status).innerText(),balance:current.balance});
        if (test.maxTrades && await page.evaluate(offset => window.__demoTest.events.slice(offset).filter(e => e.event === 'trade_placed').length,eventOffset) >= test.maxTrades) break;
      }
    } finally {
      if (test.stop) await page.evaluate(name => window[name]('Demo test stopped'),test.stop);
      if (test.stopSelector) await page.locator(test.stopSelector).click();
      if (test.toggleRun && (await page.locator(test.selector).innerText()).includes(': ON')) await page.evaluate(name => window[name](),test.toggleRun);
      if (test.auto && (await page.locator('#autoBtn').innerText()).includes('ON')) await page.evaluate(() => toggleAuto());
    }
    await page.waitForTimeout(test.settleSeconds ? test.settleSeconds * 1000 : test.stop || test.auto || test.toggleRun ? 7000 : 0);
    log({ kind:'test_end', test:args[0], ...(await status()), events:await page.evaluate(() => window.__demoTest.events.splice(0).filter(e => !['stats_update','balance_update'].includes(e.event))) });
  } else {
    throw new Error('Unknown read-only/preparation command');
  }
}
main().then(() => process.exit(0)).catch(error => { console.error(error.message); process.exit(1); });
