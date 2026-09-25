(() => {
  let csrf = '', busy = false;
  const el = id => document.getElementById(id);
  const status = el('globalIntelligenceStatus');
  const buttons = [...document.querySelectorAll('[data-intelligence]')];
  async function refresh() {
    try {
      const r = await fetch('/admin/intelligence/status', {cache: 'no-store'});
      if (!r.ok) throw Error('Admin status unavailable.');
      const d = await r.json(); csrf = d.csrf; const h = d.health;
      status.textContent = `Research Engine: ${h.state} | Connection: ${h.connected ? 'ONLINE' : 'OFFLINE'} | Authorization: ${h.authorized ? 'CONFIRMED' : 'UNCONFIRMED'} | PAT: ${h.pat_configured ? 'Saved' : 'Not configured'} | App ID: ${h.app_id_configured ? 'Saved' : 'Not configured'} | Markets: ${h.markets_monitored || 0} | Ticks: ${h.ticks_received || 0}${h.error ? ' | ' + h.error : ''}${h.test_result ? ' | Test: ' + h.test_result : ''}`;
    } catch (e) { status.textContent = e.message; }
  }
  buttons.forEach(b => b.onclick = async () => {
    if (busy) return; busy = true; buttons.forEach(x => x.disabled = true);
    try {
      const field = el('globalIntelligencePat'), action = b.dataset.intelligence;
      let data = {};
      if (action === 'save') data = {pat: field.value, app_id: el('globalIntelligenceAppId').value};
      const r = await fetch('/admin/intelligence/' + action, {method:'POST',headers:{'Content-Type':'application/json','X-Intelligence-CSRF':csrf},body:JSON.stringify(data)});
      const d = await r.json(); if (!r.ok) throw Error(d.error || 'Command failed.');
      if (action === 'save') field.value = '';
      await refresh();
    } catch (e) { status.textContent = e.message; }
    finally { busy = false; buttons.forEach(x => x.disabled = false); }
  });
  refresh(); setInterval(() => { if (!busy && !document.hidden) refresh(); }, 5000);
})();
