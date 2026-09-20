import { useEffect, useMemo, useState } from 'react';
import { AlertOctagon, Cpu, Flame, OctagonPause, Save, Scale, ShieldAlert } from 'lucide-react';
import { useHub } from '../context/HubContext';
import { fmtSigned, fmtUSD, profitTone } from '../lib/format';
import { Badge, PageHeader, Panel, Progress, Toggle } from '../components/ui';
import ConfirmModal from '../components/ConfirmModal';
import { closeAllPositions, stopAllBots, stopAndCloseAll } from '../lib/actions';
import { mt5RiskService } from '../services/mt5RiskService';
import { isSimulation } from '../config/runtime';
import { SYMBOL_LIST } from '../lib/market';
import type { RiskSettings } from '../types';
import { usePersistentState } from '../hooks/usePersistentState';

export default function RiskCenterPage() {
  const { accounts, bots, scopeBots, positions, liveProfit, botLiveToday, stats, mt5Symbols, pushToast, refresh, prefs } = useHub();
  const [confirm, setConfirm] = useState<'stop' | 'close' | 'both' | null>(null);
  const [risk, setRisk] = useState<RiskSettings | null>(null);
  const [riskRows, setRiskRows] = useState<RiskSettings[]>([]);
  const [riskScope, setRiskScope] = usePersistentState('risk_scope', 'global');
  const [savingRisk, setSavingRisk] = useState(false);

  useEffect(() => {
    mt5RiskService.list().then((rows) => {
      setRiskRows(rows);
      setRisk(rows.find((r) => r.scope === 'global') || rows[0] || null);
    }).catch(() => setRisk(null));
  }, []);

  const selectRiskScope = (value: string) => {
    setRiskScope(value);
    const global = riskRows.find((r) => r.scope === 'global') || risk;
    if (!global) return;
    if (value === 'global') {
      setRisk(riskRows.find((r) => r.scope === 'global') || global);
      return;
    }
    const [kind, rawId] = value.split(':');
    const numericId = Number(rawId);
    if (kind === 'account') {
      const existing = riskRows.find((r) => r.scope === 'account' && r.account_login === numericId);
      setRisk(existing || { ...global, id: `account:${numericId}`, scope: 'account', account_login: numericId, bot_id: null });
    } else if (kind === 'bot') {
      const existing = riskRows.find((r) => r.scope === 'bot' && r.bot_id === numericId);
      setRisk(existing || { ...global, id: `bot:${numericId}`, scope: 'bot', account_login: null, bot_id: numericId });
    }
  };

  const runningBots = scopeBots.filter((b) => b.status === 'running' || b.status === 'paused');
  const netFloating = useMemo(() => positions.reduce((s, p) => s + liveProfit(p), 0), [positions, liveProfit]);

  const exposure = useMemo(() => {
    const map: Record<string, { symbol: string; volume: number; floating: number; count: number }> = {};
    for (const p of positions) {
      const row = map[p.symbol] ||= { symbol: p.symbol, volume: 0, floating: 0, count: 0 };
      row.volume += Number(p.volume);
      row.floating += liveProfit(p);
      row.count += 1;
    }
    return Object.values(map).sort((a, b) => b.volume - a.volume);
  }, [positions, liveProfit]);
  const maxExposureVol = Math.max(0.0001, ...exposure.map((e) => e.volume));

  const doStopAll = async () => {
    try { const r = await stopAllBots(); pushToast('warning', `${r.stopped} bot${r.stopped === 1 ? '' : 's'} stopped`, 'Open positions were left untouched.'); await refresh(true); }
    catch (e) { pushToast('error', 'Stop-all failed', e instanceof Error ? e.message : undefined); }
  };
  const doCloseAll = async () => {
    try { const r = await closeAllPositions(); pushToast(r.realized >= 0 ? 'success' : 'warning', `${r.closed} position${r.closed === 1 ? '' : 's'} closed`, `Realized P/L ${fmtSigned(r.realized)}.`); await refresh(true); }
    catch (e) { pushToast('error', 'Close-all failed', e instanceof Error ? e.message : undefined); }
  };
  const doBoth = async () => {
    try {
      const r = await stopAndCloseAll();
      pushToast('warning', 'Emergency flatten completed', `${r.stopped} bots stopped · ${r.closed} positions closed · ${fmtSigned(r.realized)} realized.`);
      await refresh(true);
    } catch (e) { pushToast('error', 'Emergency flatten failed', e instanceof Error ? e.message : undefined); }
  };

  const saveRisk = async () => {
    if (!risk) return;
    setSavingRisk(true);
    try { const saved = await mt5RiskService.save(risk); setRiskRows((rows) => [...rows.filter((r) => r.id !== saved.id), saved]); pushToast('success', 'Risk guardrails saved', isSimulation ? `Saved ${risk.scope} guardrails to the local simulation adapter.` : `Saved ${risk.scope} guardrails to the MT5 risk service.`); }
    catch (e) { pushToast('error', 'Risk settings failed', e instanceof Error ? e.message : undefined); }
    finally { setSavingRisk(false); }
  };

  const setNumber = (key: keyof RiskSettings, value: string) => {
    if (!risk) return;
    setRisk({ ...risk, [key]: Number(value) || 0 });
  };

  return (
    <div>
      <PageHeader title="Risk Center" sub={isSimulation ? 'Simulation guardrails, exposure and emergency controls' : 'Portfolio-level guardrails, exposure and emergency controls'} />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {accounts.map((a) => {
          const float = positions.filter((p) => p.account_login === a.login).reduce((s, p) => s + liveProfit(p), 0);
          const equity = Number(a.balance) + float;
          const margin = Number(a.margin);
          const level = margin > 0 ? (equity / margin) * 100 : null;
          const toneBar = !level || level > 400 ? 'gain' : level > 200 ? 'warn' : 'loss';
          return (
            <Panel key={a.id} className="p-5">
              <div className="flex items-center justify-between"><p className="text-[13px] font-bold text-white">{a.nickname}</p><Badge tone={a.status === 'connected' ? 'gain' : 'slate'}>{a.status}</Badge></div>
              <div className="mt-3 flex items-end justify-between">
                <div><p className="text-[9px] uppercase tracking-widest text-slate-600 font-semibold">Margin level</p><p className={`mono text-xl font-extrabold ${!level ? 'text-slate-500' : level > 400 ? 'text-gain-400' : level > 200 ? 'text-warn-400' : 'text-loss-400'}`}>{level ? `${level.toFixed(0)}%` : 'No leverage used'}</p></div>
                <div className="text-right text-[11px] text-slate-500 space-y-0.5"><p>Margin <span className="mono text-slate-300">{fmtUSD(margin)}</span></p><p>Free <span className="mono text-slate-300">{fmtUSD(equity - margin)}</span></p></div>
              </div>
              <div className="mt-3"><Progress value={level ? Math.min(100, level / 20) : 0} tone={toneBar} /></div>
            </Panel>
          );
        })}
      </div>

      {risk && (
        <Panel className="mt-4 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div><h3 className="text-sm font-bold text-white flex items-center gap-2"><ShieldAlert size={15} className="text-brand-300" /> {risk.scope === 'global' ? 'Global risk guardrails' : risk.scope === 'account' ? 'Account risk override' : 'Bot risk override'}</h3><p className="text-[11px] text-slate-500 mt-1">Global, account and individual-bot scopes are stored independently.</p></div>
            <div className="flex flex-wrap gap-2">
              <select className="input !w-auto !py-2 text-xs" value={riskScope} onChange={(e) => selectRiskScope(e.target.value)}>
                <option value="global">Global risk</option>
                <optgroup label="Account risk">{accounts.map((a) => <option key={a.id} value={`account:${a.login}`}>{a.nickname} · #{a.login}</option>)}</optgroup>
                <optgroup label="Bot risk">{bots.map((b) => <option key={b.id} value={`bot:${b.id}`}>{b.name}</option>)}</optgroup>
              </select>
              <button className="btn-primary" onClick={saveRisk} disabled={savingRisk}><Save size={14} /> {savingRisk ? 'Saving…' : 'Save Risk Settings'}</button>
            </div>
          </div>
          <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              ['Max daily loss', 'max_daily_loss', '$'], ['Max daily profit', 'max_daily_profit', '$'], ['Max drawdown', 'max_drawdown_pct', '%'], ['Max lot size', 'max_lot_size', 'lots'],
              ['Max open positions', 'max_open_positions', ''], ['Max trades/day', 'max_trades_per_day', ''], ['Max risk/trade', 'max_risk_per_trade', '%'],
            ].map(([label, key, suffix]) => <div key={key}><label className="label">{label}</label><div className="relative"><input className="input mono" type="number" min="0" step="0.1" value={String(risk[key as keyof RiskSettings] ?? '')} onChange={(e) => setNumber(key as keyof RiskSettings, e.target.value)} />{suffix && <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-slate-600">{suffix}</span>}</div></div>)}
            <div><label className="label">Trading hours</label><input className="input mono" value={risk.allowed_trading_hours} onChange={(e) => setRisk({ ...risk, allowed_trading_hours: e.target.value })} /></div>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <span className="text-[11px] text-slate-500 mr-1">Allowed symbols</span>
            {isSimulation ? SYMBOL_LIST.map((symbol) => {
              const on = risk.allowed_symbols.includes(symbol);
              return <button key={symbol} className={`rounded-lg border px-2.5 py-1 text-[10px] font-bold ${on ? 'border-brand-500/35 bg-brand-500/10 text-brand-300' : 'border-white/10 bg-white/[0.03] text-slate-600'}`} onClick={() => setRisk({ ...risk, allowed_symbols: on ? risk.allowed_symbols.filter((s) => s !== symbol) : [...risk.allowed_symbols, symbol] })}>{symbol}</button>;
            }) : (
              <input
                className="input !w-full md:!w-[520px] mono text-xs"
                value={risk.allowed_symbols.join(', ')}
                onChange={(e) => setRisk({ ...risk, allowed_symbols: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })}
                placeholder={mt5Symbols.length ? 'Blank = all broker symbols, or enter e.g. XAUUSD, EURUSD' : 'Blank = all broker symbols'}
              />
            )}
            {!isSimulation && <span className="text-[10px] text-slate-600">Blank means all symbols. Add exact broker symbol names to create a whitelist.</span>}
            <span className="ml-auto inline-flex items-center gap-2 text-[11px] text-slate-400">Auto-stop <Toggle on={risk.auto_stop} onChange={(v) => setRisk({ ...risk, auto_stop: v })} /></span>
          </div>
        </Panel>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mt-4">
        <Panel className="p-5">
          <h3 className="text-sm font-bold text-white flex items-center gap-2"><Scale size={15} className="text-brand-300" /> Exposure by symbol</h3>
          <div className="mt-4 space-y-3">
            {exposure.length === 0 && <p className="text-xs text-slate-600 py-6 text-center">No open exposure — book is flat.</p>}
            {exposure.map((e) => <div key={e.symbol}><div className="flex items-center justify-between text-[12px] mb-1"><span className="font-semibold text-slate-200">{e.symbol} <span className="text-slate-600 font-normal">· {e.count} ticket{e.count === 1 ? '' : 's'}</span></span><span className="mono"><span className="text-slate-400">{e.volume.toFixed(2)} lots</span>{' '}<span className={`font-bold ${profitTone(e.floating)}`}>{fmtSigned(e.floating)}</span></span></div><Progress value={(e.volume / maxExposureVol) * 100} tone={e.floating >= 0 ? 'brand' : 'loss'} /></div>)}
          </div>
          {stats && <div className="mt-5 grid grid-cols-3 gap-3"><div className="rounded-xl bg-white/[0.03] border border-white/[0.06] p-3 text-center"><p className="text-[9px] uppercase tracking-widest text-slate-600 font-semibold">Peak equity</p><p className="mono text-[14px] font-bold text-white mt-0.5">{fmtUSD(stats.kpis.peak_equity, 0)}</p></div><div className="rounded-xl bg-white/[0.03] border border-white/[0.06] p-3 text-center"><p className="text-[9px] uppercase tracking-widest text-slate-600 font-semibold">Drawdown</p><p className={`mono text-[14px] font-bold mt-0.5 ${stats.kpis.drawdown_pct > 3 ? 'text-loss-400' : 'text-gain-400'}`}>{stats.kpis.drawdown_pct}%</p></div><div className="rounded-xl bg-white/[0.03] border border-white/[0.06] p-3 text-center"><p className="text-[9px] uppercase tracking-widest text-slate-600 font-semibold">30d win rate</p><p className="mono text-[14px] font-bold text-white mt-0.5">{stats.kpis.trades_30d ? `${Number(stats.kpis.win_rate_30d.toFixed(2))}%` : '—'}</p></div></div>}
        </Panel>

        <Panel className="p-5">
          <h3 className="text-sm font-bold text-white flex items-center gap-2"><Cpu size={15} className="text-brand-300" /> Engine risk envelopes</h3>
          <div className="mt-4 space-y-3">
            {runningBots.length === 0 && <p className="text-xs text-slate-600 py-6 text-center">No active engines — risk surface is clear.</p>}
            {runningBots.map((b) => { const today = botLiveToday(b); const limit = Number(b.settings?.max_daily_loss || 250); const usedPct = today < 0 ? Math.min(100, (Math.abs(today) / limit) * 100) : 0; return <div key={b.id} className="rounded-xl bg-white/[0.03] border border-white/[0.06] p-3.5"><div className="flex items-center justify-between"><p className="text-[13px] font-semibold text-white">{b.name} <span className="mono text-[10px] text-slate-500">{b.symbol} · {b.lot_size.toFixed(2)} lots</span></p><p className={`mono text-[12px] font-bold ${profitTone(today)}`}>{fmtSigned(today)}</p></div><div className="mt-2"><div className="flex justify-between text-[10px] text-slate-600 mb-1"><span>Daily loss guard consumed</span><span className="mono">{fmtUSD(limit)} limit</span></div><Progress value={usedPct} tone={usedPct > 70 ? 'loss' : usedPct > 35 ? 'warn' : 'gain'} /></div></div>; })}
          </div>
        </Panel>
      </div>

      <Panel className="mt-4 p-6 !border-loss-500/25">
        <div className="flex items-center gap-2.5 mb-1"><Flame size={16} className="text-loss-400" /><h3 className="text-base font-bold text-white">Emergency Controls</h3></div>
        <p className="text-xs text-slate-500 mb-5">{isSimulation ? 'These controls affect simulation state only.' : 'These commands route to the configured MT5 backend.'} {prefs.confirmDanger ? 'Confirmation is required.' : 'Confirmations are disabled in Settings.'}</p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <button onClick={() => (prefs.confirmDanger ? setConfirm('stop') : doStopAll())} className="group rounded-2xl border border-warn-400/30 bg-warn-400/[0.06] hover:bg-warn-400/[0.12] transition-all p-5 text-left cursor-pointer active:scale-[0.99]"><div className="flex items-center justify-between"><span className="grid h-11 w-11 place-items-center rounded-xl bg-warn-400/15 border border-warn-400/30 text-warn-400"><OctagonPause size={20} /></span><Badge tone="warn">{runningBots.length} active</Badge></div><p className="mt-3 text-[14px] font-extrabold uppercase tracking-wider text-warn-400">Stop All Bots</p><p className="mt-1 text-xs text-slate-500 leading-relaxed">Stops automation only. Existing positions remain open.</p></button>
          <button onClick={() => (prefs.confirmDanger ? setConfirm('close') : doCloseAll())} className="group rounded-2xl border border-loss-500/30 bg-loss-500/[0.06] hover:bg-loss-500/[0.12] transition-all p-5 text-left cursor-pointer active:scale-[0.99]"><div className="flex items-center justify-between"><span className="grid h-11 w-11 place-items-center rounded-xl bg-loss-500/15 border border-loss-500/30 text-loss-400"><AlertOctagon size={20} /></span><Badge tone="loss">{positions.length} open</Badge></div><p className="mt-3 text-[14px] font-extrabold uppercase tracking-wider text-loss-400">Close All Positions</p><p className="mt-1 text-xs text-slate-500 leading-relaxed">Closes positions only. Bot status is not silently changed.</p></button>
          <button onClick={() => setConfirm('both')} className="group rounded-2xl border border-loss-500/50 bg-loss-500/[0.10] hover:bg-loss-500/[0.16] transition-all p-5 text-left cursor-pointer active:scale-[0.99]"><div className="flex items-center justify-between"><span className="grid h-11 w-11 place-items-center rounded-xl bg-loss-500/20 border border-loss-500/40 text-loss-300"><Flame size={20} /></span><Badge tone="loss">strong confirm</Badge></div><p className="mt-3 text-[14px] font-extrabold uppercase tracking-wider text-loss-300">Stop + Close All</p><p className="mt-1 text-xs text-slate-500 leading-relaxed">Stops every bot and flattens every MT5 position.</p></button>
        </div>
      </Panel>

      <ConfirmModal open={confirm === 'stop'} onClose={() => setConfirm(null)} title="Stop all bots?" tone="warning" confirmLabel="Stop All Bots" message={<>Every active engine will be halted. Open positions will remain open.</>} onConfirm={doStopAll} />
      <ConfirmModal open={confirm === 'close'} onClose={() => setConfirm(null)} title="Close all positions?" tone="danger" confirmLabel="Close All Positions" message={<>All <span className="mono font-bold text-white">{positions.length}</span> open positions will be closed, realizing approximately <span className={`mono font-bold ${profitTone(netFloating)}`}>{fmtSigned(netFloating)}</span>. Bots are not stopped by this action.</>} onConfirm={doCloseAll} />
      <ConfirmModal open={confirm === 'both'} onClose={() => setConfirm(null)} title="Stop every bot and close every position?" tone="danger" confirmLabel="STOP BOTS + CLOSE POSITIONS" message={<>This is the strongest emergency action. It stops all active bots and closes all <span className="mono font-bold text-white">{positions.length}</span> tracked positions. The two operations are never combined silently.</>} onConfirm={doBoth} />
    </div>
  );
}
