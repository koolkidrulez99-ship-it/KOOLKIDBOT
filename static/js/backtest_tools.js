(() => {
  'use strict';
  const el = id => document.getElementById(id);
  const num = (v, suffix = '') => v == null || !Number.isFinite(Number(v)) ? '—' : Number(v).toFixed(2) + suffix;
  const count = v => Number(v || 0).toLocaleString();
  const date = v => v ? new Date(v * 1000).toLocaleString() : 'Not yet';
  const stages = {INSUFFICIENT_DATA: ['Gathering samples', 'neutral'], RESEARCHING: ['Researching', 'neutral'], PAPER_TESTING: ['Paper testing', 'wait'], VALIDATED: ['Sample validated', ''], DEGRADED: ['Below criteria', 'bad'], DISABLED: ['Disabled', 'neutral']};
  let controller, detailController, lastDetailButton;
  const node = (tag, text, cls) => { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; };
  const cell = (row, text, cls) => { const n = node('td', text, cls); row.append(n); return n; };
  const pill = (text, cls = '') => node('span', text, 'pill ' + cls);
  function table(headers, rows) {
    const t = node('table'), h = t.createTHead().insertRow();
    headers.forEach(v => h.append(node('th', v)));
    const b = t.createTBody(); rows.forEach(values => { const r = b.insertRow(); values.forEach(v => cell(r, v)); });
    return t;
  }
  async function get(url, signal) {
    const r = await fetch(url, {cache: 'no-store', signal});
    if (!r.ok) throw Error(r.status === 401 ? 'Your session expired. Sign in again to view research.' : 'Research is temporarily unavailable. Try Refresh.');
    return r.json();
  }
  function options(id, rows) {
    const select = el(id), selected = select.value;
    const first = select.options[0].cloneNode(true);
    select.replaceChildren(first);
    rows.forEach(([value, label]) => { const o = node('option', label); o.value = value; select.append(o); });
    if ([...select.options].some(o => o.value === selected)) select.value = selected;
  }
  function equity(history) {
    const box = el('btEquity'); box.replaceChildren();
    const priced = [...history].reverse().filter(r => r.profit != null && Number.isFinite(Number(r.profit)));
    if (!priced.length) { box.append(node('p', 'No priced outcomes yet. An equity curve appears once proposal payouts are observed.', 'muted')); return; }
    const values = [0]; priced.forEach(r => values.push(values[values.length - 1] + Number(r.profit)));
    const lo = Math.min(...values), hi = Math.max(...values), range = Math.max(.1, hi - lo);
    const ns = 'http://www.w3.org/2000/svg', svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 700 145'); svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', `Paper equity across ${priced.length} priced outcomes, ending at ${num(values[values.length - 1])} stake units. Unpriced outcomes excluded.`);
    const y = v => 120 - (v - lo) / range * 100;
    const line = document.createElementNS(ns, 'line');
    [['x1', 40], ['x2', 690], ['y1', y(0)], ['y2', y(0)], ['stroke', '#34465f'], ['stroke-dasharray', '4 5']].forEach(([k,v]) => line.setAttribute(k,v)); svg.append(line);
    const curve = document.createElementNS(ns, 'polyline'); curve.setAttribute('points', values.map((v,i) => `${40 + i / Math.max(1, values.length - 1) * 645},${y(v)}`).join(' '));
    curve.setAttribute('fill', 'none'); curve.setAttribute('stroke', values[values.length - 1] >= 0 ? '#7ae0c0' : '#fb939e'); curve.setAttribute('stroke-width', '2.5'); svg.append(curve);
    [[hi, 22], [lo, 126]].forEach(([v,top]) => { const text = document.createElementNS(ns, 'text'); text.textContent = num(v); text.setAttribute('x', '0'); text.setAttribute('y', top); text.setAttribute('fill', '#98a6bc'); text.setAttribute('font-size', '10'); svg.append(text); });
    box.append(svg);
  }
  async function details(row, button) {
    detailController?.abort(); detailController = new AbortController(); lastDetailButton = button;
    el('btDetails').hidden = false; el('btDetailTitle').textContent = row.bot + ' / ' + row.market;
    el('btDetailConfirmation').textContent = 'Loading matching research…';
    ['btComparison', 'btHistory', 'btEquity'].forEach(id => el(id).replaceChildren());
    el('btDetails').focus({preventScroll: true}); el('btDetails').scrollIntoView({block: 'start', behavior: 'auto'});
    try {
      const d = await get('/backtest-tools/api/details?' + new URLSearchParams({symbol: row.symbol, strategy: row.strategy}), detailController.signal);
      const confirmations = d.confirmations || [], approved = confirmations.find(c => c.decision === 'APPROVE');
      el('btDetailConfirmation').textContent = approved ? 'At least one exact contract passes confirmation. Each submitted order is checked again.' : confirmations[0]?.reason || 'Waiting for matching contract samples. A research score alone does not approve a trade.';
      el('btComparison').replaceChildren(table(['Window', 'Score / 100', 'Win rate', 'Outcomes', 'EV', 'Drawdown', 'Losing streak', 'Live outcomes', 'Priced', 'Stage'], Object.entries(d.windows).map(([w,r]) => r ? [w,num(r.score),num(r.win_rate,'%'),r.paper_trades,num(r.ev),num(r.max_drawdown),r.longest_losing_streak,r.forward_samples,r.priced_samples,(stages[r.status] || [r.status])[0]] : [w,'No data'])));
      if (d.history.length) el('btHistory').replaceChildren(table(['Time', 'Contract', 'Target', 'Duration', 'Outcome', 'Profit (units)', 'Pricing'], d.history.map(r => [date(r.created),r.contract || '—',r.barrier ?? '—',(r.duration || 1) + ' ticks',r.won ? 'Win' : 'Loss',num(r.profit),r.pricing || (r.profit == null ? 'Unpriced' : 'Observed proposal')])));
      else el('btHistory').append(node('p', 'No paper outcomes recorded for this strategy and market yet.', 'muted'));
      equity(d.history);
    } catch (e) { if (e.name !== 'AbortError') el('btDetailConfirmation').textContent = e.message; }
  }
  function renderRows(rows, coverage) {
    const fragment = document.createDocumentFragment();
    rows.forEach((r,i) => {
      const tr = node('tr'); cell(tr, String(i + 1).padStart(2, '0'), 'rank');
      const strategy = cell(tr, null); strategy.append(node('span', r.bot, 'strategy-name'), node('span', coverage.includes(r.strategy) ? 'Confirmation adapter available' : 'Research only · adapter required', 'table-sub'));
      const market = cell(tr, r.market); market.append(node('span', r.symbol + (r.market_live ? ' · Live' : ' · Historical'), 'table-sub'));
      const score = cell(tr, null, 'score-cell'); score.append(node('span', num(r.score), 'score-value'));
      if (r.score != null) { const bar = node('div', null, 'score-bar'), fill = node('span'); fill.style.width = Math.max(0, Math.min(100, r.score)) + '%'; bar.append(fill); score.append(bar); }
      cell(tr, num(r.win_rate, '%')); cell(tr, (r.ev > 0 ? '+' : '') + num(r.ev), r.ev == null ? 'muted' : r.ev > 0 ? 'positive' : 'negative');
      cell(tr, count(r.paper_trades)); cell(tr, num(r.max_drawdown)); const stage = stages[r.status] || [r.status, 'neutral']; cell(tr, null).append(pill(...stage));
      const button = node('button', 'Details ↗', 'details-button'); button.type = 'button'; button.setAttribute('aria-label', 'Details for ' + r.bot + ' on ' + r.market); button.onclick = () => details(r, button); cell(tr, null).append(button); fragment.append(tr);
    });
    el('btRows').replaceChildren(fragment);
  }
  function renderDecisions(rows) {
    const box = el('btDecisions'); box.replaceChildren();
    if (!rows.length) { box.append(node('p', 'No confirmation activity yet. Start an automated strategy to see its checks here.', 'quiet-empty')); return; }
    rows.forEach(r => {
      const item = node('article', null, 'decision-item'); item.append(pill(r.decision, r.decision === 'REJECT' ? 'bad' : r.decision === 'WAIT' ? 'wait' : r.decision === 'BYPASS' ? 'neutral' : ''));
      const info = node('div'); info.append(node('strong', [r.profile, r.mode, r.symbol].filter(Boolean).join(' · ')), node('p', r.reason));
      const s = r.statistics; info.append(node('small', date(r.created) + (s ? ` · ${r.window} ticks · ${s.paper_trades} outcomes · Score ${num(s.score)} · EV ${num(s.ev)}` : ''))); item.append(info); box.append(item);
    });
  }
  async function refresh() {
    controller?.abort(); const current = new AbortController(); controller = current; el('btRefresh').disabled = true;
    try {
      const d = await get('/backtest-tools/api/rankings?' + new URLSearchParams({window:el('btWindow').value,strategy:el('btBot').value,symbol:el('btMarket').value,status:el('btStatus').value,sort:el('btSort').value}), current.signal);
      const h = d.health, live = h.state === 'READY' && !h.stale && !d.stale && h.connected;
      el('btLiveDot').classList.toggle('live', !!live); el('btLiveLabel').textContent = live ? 'Research is live' : 'Research: ' + (h.state || 'unavailable').replaceAll('_', ' ').toLowerCase();
      el('btHealth').textContent = h.error || (live ? 'The engine is collecting market ticks and evaluating paper outcomes.' : 'Automated confirmation waits until fresh, connected research is available.');
      el('btTickTime').textContent = h.latest_tick ? new Date(h.latest_tick * 1000).toLocaleTimeString() : 'Waiting for ticks';
      [['btMarketsCount',h.markets_monitored],['btBotsCount',h.bots_tracked],['btPapersCount',h.paper_trades],['btTicksCount',h.historical_records]].forEach(([id,v]) => el(id).textContent = count(v));
      el('btCounts').textContent = 'Retained research observations';
      const p = d.confirmation_policy || {}, on = p.enabled !== false;
      el('btGuardTitle').textContent = on ? 'Backtest confirmation is required' : 'Backtest confirmation is disabled';
      el('btGuardCopy').textContent = on ? `${p.window || '500'}-tick checks · Cloud Reinvest Under 9 / Over 0 adapters available. Other setups wait for matching research adapters.` : 'The admin switch is off. Automated trades can use their original entry rules without this check.';
      el('btGuardBadge').textContent = on ? 'Guard enabled' : 'Guard disabled'; el('btGuardBadge').className = 'pill' + (on ? '' : ' wait');
      el('btCriteria').textContent = `The ${p.window || '500'}-tick confirmation window needs ${p.min_trades || 20} matching outcomes, including ${p.min_forward || 10} live outcomes, ${Math.round((p.min_coverage || .95) * 100)}% payout coverage, positive expected value, score ≥ ${p.min_score ?? 10}, drawdown ≤ ${p.max_drawdown ?? 5} units and a losing streak ≤ ${p.max_losing_streak ?? 5}. Changing the page window only changes your view.`;
      options('btMarket', d.markets); options('btBot', d.bots); renderRows(d.rows, d.confirmation_coverage || []);
      el('btResultsLabel').textContent = `${d.rows.length} strategy / market combinations · ${d.window === 'ALL' ? 'All recorded ticks' : 'Last ' + d.window + ' ticks'}`;
      el('btUpdated').textContent = (d.stale ? 'Results are stale · ' : 'Updated ') + date(d.updated) + ' · Refreshes every 10 seconds';
      el('btEmpty').hidden = !!d.rows.length;
      const filtered = ['btBot','btMarket','btStatus'].some(id => el(id).value);
      el('btEmptyTitle').textContent = filtered ? 'No results match these filters' : 'Building your research view';
      el('btEmptyCopy').textContent = filtered ? 'Try another strategy, market or research stage to explore the available results.' : 'Results appear once the engine collects market data. Connection status above shows what is happening.';
      el('btResetFilters').hidden = !filtered;
      try { const activity = await get('/backtest-tools/api/decisions', current.signal); renderDecisions(activity.decisions); }
      catch (e) { if (e.name !== 'AbortError') el('btDecisions').replaceChildren(node('p', e.message, 'quiet-empty')); }
    } catch (e) {
      if (e.name !== 'AbortError') {
        el('btHealth').textContent = e.message; el('btLiveLabel').textContent = 'Research unavailable'; el('btLiveDot').classList.remove('live');
        el('btUpdated').textContent = 'Connection interrupted. Previously displayed results may be stale.';
        renderRows([], []);
        el('btEmpty').hidden = false;
        el('btEmptyTitle').textContent = 'Research data could not be loaded';
        el('btEmptyCopy').textContent = e.message || 'Refresh the page and try again.';
        el('btResetFilters').hidden = true;
      }
    } finally { if (controller === current) el('btRefresh').disabled = false; }
  }
  ['btBot','btMarket','btWindow','btStatus','btSort'].forEach(id => el(id).addEventListener('change', refresh));
  el('btRefresh').onclick = refresh;
  el('btResetFilters').onclick = () => { ['btBot','btMarket','btStatus'].forEach(id => el(id).value = ''); refresh(); };
  el('btCloseDetails').onclick = () => { detailController?.abort(); el('btDetails').hidden = true; lastDetailButton?.focus(); };
  refresh(); setInterval(() => { if (!document.hidden) refresh(); }, 10000);
})();
