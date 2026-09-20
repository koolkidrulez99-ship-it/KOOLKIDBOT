import { useEffect, useMemo, useState } from 'react';
import { FileDown, History as HistoryIcon, Trash2 } from 'lucide-react';
import { useHub } from '../context/HubContext';
import { durationBetween, fmtDateTime, fmtPrice, fmtSigned, fmtUSD, profitTone } from '../lib/format';
import { Badge, EmptyState, PageHeader, Panel, Skel, StatCard } from '../components/ui';
import { MARKET } from '../lib/market';
import type { Mt5HistoryRow } from '../types';
import { mt5HistoryService } from '../services/mt5HistoryService';
import { isSimulation } from '../config/runtime';
import { usePersistentState } from '../hooks/usePersistentState';
import ConfirmModal from '../components/ConfirmModal';

type ResultFilter = 'all' | 'win' | 'loss';
type DateFilter = 'today' | '7d' | '30d' | 'all';
type SourceFilter = 'all' | 'bot' | 'manual' | 'copy';

function netPl(r: Mt5HistoryRow): number {
  return Number(r.net_pl ?? (Number(r.profit || 0) + Number(r.swap || 0) + Number(r.commission || 0)));
}

export default function HistoryPage() {
  const { accounts, accountName } = useHub();
  const [rows, setRows] = useState<Mt5HistoryRow[] | null>(null);
  const [error, setError] = useState('');
  const [result, setResult] = usePersistentState<ResultFilter>('history_result_filter', 'all');
  const [dateFilter, setDateFilter] = useState<DateFilter>('today');
  const [sourceFilter, setSourceFilter] = usePersistentState<SourceFilter>('history_source_filter', 'all');
  const [symbol, setSymbol] = usePersistentState('history_symbol_filter', 'all');
  const [account, setAccount] = usePersistentState('history_account_filter', 'all');
  const [clearedAt, setClearedAt] = usePersistentState<string | null>('history_cleared_at', null);
  const [clearOpen, setClearOpen] = useState(false);

  const load = (force = false) => {
    mt5HistoryService.list(force)
      .then((data) => { setRows(data); setError(''); })
      .catch((e) => setError(e instanceof Error ? e.message : 'History request failed'));
  };

  useEffect(() => {
    load();
    const refreshVisible = () => { if (!document.hidden) load(); };
    const id = window.setInterval(refreshVisible, 20000);
    window.addEventListener('focus', refreshVisible);
    return () => {
      window.clearInterval(id);
      window.removeEventListener('focus', refreshVisible);
    };
  }, []);

  const filtered = useMemo(() => {
    let out = rows || [];
    if (account !== 'all') out = out.filter((r) => String(r.account_login) === account);
    if (symbol !== 'all') out = out.filter((r) => r.symbol === symbol);
    if (result === 'win') out = out.filter((r) => netPl(r) > 0);
    if (result === 'loss') out = out.filter((r) => netPl(r) < 0);
    if (sourceFilter === 'manual') out = out.filter((r) => r.source === 'Manual');
    if (sourceFilter === 'bot') out = out.filter((r) => r.source !== 'Manual' && !String(r.source).startsWith('COPY:'));
    if (sourceFilter === 'copy') out = out.filter((r) => String(r.source).startsWith('COPY:'));
    if (dateFilter !== 'all') {
      const now = new Date();
      const start = new Date(now);
      if (dateFilter === 'today') start.setHours(0, 0, 0, 0);
      if (dateFilter === '7d') start.setTime(now.getTime() - 7 * 86400000);
      if (dateFilter === '30d') start.setTime(now.getTime() - 30 * 86400000);
      out = out.filter((r) => new Date(r.close_time) >= start);
      if (clearedAt) out = out.filter((r) => new Date(r.close_time).getTime() > new Date(clearedAt).getTime());
    }
    return out;
  }, [rows, account, symbol, result, sourceFilter, dateFilter, clearedAt]);

  const summary = useMemo(() => {
    const list = filtered;
    const net = list.reduce((s, r) => s + netPl(r), 0);
    const wins = list.filter((r) => netPl(r) > 0);
    const losses = list.filter((r) => netPl(r) < 0);
    const gross = wins.reduce((s, r) => s + netPl(r), 0);
    const grossLoss = Math.abs(losses.reduce((s, r) => s + netPl(r), 0));
    return {
      net,
      trades: list.length,
      winRate: list.length ? (wins.length / list.length) * 100 : 0,
      avgWin: wins.length ? gross / wins.length : 0,
      avgLoss: losses.length ? grossLoss / losses.length : 0,
      profitFactor: grossLoss > 0 ? gross / grossLoss : wins.length ? 99 : 0,
      best: list.length ? Math.max(...list.map(netPl)) : 0,
      worst: list.length ? Math.min(...list.map(netPl)) : 0,
    };
  }, [filtered]);

  const exportCsv = () => {
    const head = 'ticket,close_time,account,symbol,type,volume,open_price,close_price,gross_profit,swap,commission,net_pl,source';
    const lines = filtered.map((r) =>
      [r.ticket, r.close_time, r.account_login, r.symbol, r.type, r.volume, r.open_price, r.close_price, r.profit, r.swap, r.commission, netPl(r), `"${r.source}"`].join(',')
    );
    const blob = new Blob([[head, ...lines].join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'mt5-hub-history.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div>
      <PageHeader
        title="Trade History"
        sub={isSimulation ? 'Simulated closed tickets · real MT5 history starts after bridge integration' : 'Every closed ticket across linked MT5 accounts'}
        actions={<>
          <button className="btn-ghost" onClick={() => setClearOpen(true)} disabled={!rows?.length}>
            <Trash2 size={15} /> Clear History
          </button>
          <button className="btn-ghost" onClick={exportCsv} disabled={!filtered.length}>
            <FileDown size={15} /> Export CSV
          </button>
        </>}
      />

      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3 mb-5">
        <StatCard label="Net P/L" value={fmtSigned(summary.net, 0)} tone={summary.net >= 0 ? 'gain' : 'loss'} />
        <StatCard label="Trades" value={summary.trades} />
        <StatCard label="Win rate" value={`${summary.winRate.toFixed(1)}%`} tone="brand" />
        <StatCard label="Avg win" value={fmtUSD(summary.avgWin)} />
        <StatCard label="Avg loss" value={fmtUSD(summary.avgLoss)} />
        <StatCard label="Profit factor" value={summary.profitFactor.toFixed(2)} tone="brand" />
        <StatCard label="Best trade" value={fmtSigned(summary.best)} tone="gain" />
        <StatCard label="Worst trade" value={fmtSigned(summary.worst)} tone="loss" />
      </div>

      <div className="flex flex-wrap items-center gap-2.5 mb-4">
        <div className="flex gap-1 rounded-xl glass p-1">
          {(['all', 'win', 'loss'] as const).map((r) => (
            <button
              key={r}
              onClick={() => setResult(r)}
              className={`rounded-lg px-3.5 py-1.5 text-xs font-bold capitalize cursor-pointer transition-colors ${
                result === r
                  ? r === 'win'
                    ? 'bg-gain-500/20 text-gain-400'
                    : r === 'loss'
                      ? 'bg-loss-500/20 text-loss-300'
                      : 'bg-brand-600 text-white'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              {r === 'all' ? 'All' : r === 'win' ? 'Wins' : 'Losses'}
            </button>
          ))}
        </div>
        <div className="flex gap-1 rounded-xl glass p-1">
          {(['today', '7d', '30d', 'all'] as const).map((d) => <button key={d} onClick={() => setDateFilter(d)} className={`rounded-lg px-3 py-1.5 text-[11px] font-bold ${dateFilter === d ? 'bg-brand-600 text-white' : 'text-slate-500 hover:text-white'}`}>{d === 'today' ? 'Today' : d === '7d' ? '7 Days' : d === '30d' ? '30 Days' : 'All Time'}</button>)}
        </div>
        <select className="input !w-auto !py-2 text-xs" value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value as SourceFilter)}>
          <option value="all">All sources</option><option value="bot">Bot trades</option><option value="manual">Manual trades</option><option value="copy">Copied trades</option>
        </select>
        <select className="input !w-auto !py-2 text-xs" value={symbol} onChange={(e) => setSymbol(e.target.value)}>
          <option value="all">All symbols</option>
          {[...new Set((rows || []).map((r) => r.symbol))].sort().map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
        <select className="input !w-auto !py-2 text-xs" value={account} onChange={(e) => setAccount(e.target.value)}>
          <option value="all">All accounts</option>
          {accounts
            .slice()
            .sort((a, b) => Number(a.login) - Number(b.login))
            .map((row) => (
              <option key={row.login} value={row.login}>
                {accountName(row.login)}{row.status === 'connected' ? '' : ' · offline'}
              </option>
            ))}
        </select>
        <span className="mono text-xs text-slate-600 ml-auto">{filtered.length} records</span>
      </div>

      {rows === null && !error ? (
        <div className="space-y-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skel key={i} className="h-12" />
          ))}
        </div>
      ) : error && !rows?.length ? (
        <Panel>
          <EmptyState icon={HistoryIcon} title="History unavailable" sub={error} action={<button className="btn-primary" onClick={() => load(true)}>Retry</button>} />
        </Panel>
      ) : filtered.length === 0 ? (
        <Panel>
          <EmptyState icon={HistoryIcon} title="No records match" sub="Adjust the filters or wait for tickets to close." />
        </Panel>
      ) : (
        <Panel className="overflow-hidden">
          <div className="hidden md:block overflow-x-auto">
            <table className="tbl">
              <thead>
                <tr>
                  <th>Closed</th>
                  <th>Ticket</th>
                  <th>Account</th>
                  <th>Symbol</th>
                  <th>Type</th>
                  <th className="!text-right">Volume</th>
                  <th className="!text-right">Open</th>
                  <th className="!text-right">Close</th>
                  <th className="!text-right">Pips</th>
                  <th className="!text-right">Duration</th>
                  <th>Source</th>
                  <th>Result</th>
                  <th className="!text-right">Net P/L</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => {
                  const p = netPl(r);
                  const meta = MARKET[r.symbol];
                  const pipMove = meta ? ((Number(r.close_price) - Number(r.open_price)) / meta.pip) * (r.type === 'buy' ? 1 : -1) : 0;
                  return (
                    <tr key={`${r.account_login}:${r.ticket}:${r.close_time}`}>
                      <td className="text-xs text-slate-400">{fmtDateTime(r.close_time)}</td>
                      <td className="mono text-xs text-slate-500">#{r.ticket}</td>
                      <td className="text-xs text-slate-300">{accountName(r.account_login)}</td>
                      <td className="font-semibold text-white text-[13px]">{r.symbol}</td>
                      <td><Badge tone={r.type === 'buy' ? 'brand' : 'loss'}>{r.type}</Badge></td>
                      <td className="mono !text-right text-[13px] text-slate-200">{Number(r.volume).toFixed(2)}</td>
                      <td className="mono !text-right text-xs text-slate-400">{fmtPrice(Number(r.open_price), r.symbol)}</td>
                      <td className="mono !text-right text-xs text-slate-400">{fmtPrice(Number(r.close_price), r.symbol)}</td>
                      <td className={`mono !text-right text-xs ${pipMove > 0 ? 'text-gain-400' : pipMove < 0 ? 'text-loss-400' : 'text-slate-500'}`}>
                        {pipMove > 0 ? '+' : ''}{pipMove.toFixed(1)}
                      </td>
                      <td className="mono !text-right text-xs text-slate-500">{durationBetween(r.open_time, r.close_time)}</td>
                      <td className="text-xs">{r.source === 'Manual' ? <span className="text-slate-400">Manual</span> : String(r.source).startsWith('COPY:') ? <span className="text-gain-300">Copy</span> : <span className="text-brand-300">{r.source}</span>}</td>
                      <td><Badge tone={p > 0 ? 'gain' : p < 0 ? 'loss' : 'neutral'}>{p > 0 ? 'WIN' : p < 0 ? 'LOSS' : 'BREAKEVEN'}</Badge></td>
                      <td className={`mono !text-right text-[13px] font-bold ${profitTone(p)}`}>{fmtSigned(p)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="md:hidden divide-y divide-white/[0.06]">
            {filtered.map((r) => {
              const p = netPl(r);
              return <div key={`${r.account_login}:${r.ticket}:${r.close_time}`} className="p-4">
                <div className="flex items-start justify-between gap-3"><div><p className="font-bold text-white">{r.symbol} <Badge tone={r.type === 'buy' ? 'brand' : 'loss'}>{r.type}</Badge> <Badge tone={p > 0 ? 'gain' : p < 0 ? 'loss' : 'neutral'}>{p > 0 ? 'WIN' : p < 0 ? 'LOSS' : 'BREAKEVEN'}</Badge></p><p className="mono text-[10px] text-slate-600 mt-1">#{r.ticket} · {fmtDateTime(r.close_time)}</p></div><div className="text-right"><p className="text-[9px] uppercase tracking-wider text-slate-600">Net P/L</p><p className={`mono text-sm font-bold ${profitTone(p)}`}>{fmtSigned(p)}</p></div></div>
                <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-[11px]"><p className="text-slate-500">Account <span className="block text-slate-300">{accountName(r.account_login)}</span></p><p className="text-slate-500">Source <span className="block text-slate-300">{r.source}</span></p><p className="text-slate-500">Volume <span className="mono block text-slate-300">{Number(r.volume).toFixed(2)}</span></p><p className="text-slate-500">Duration <span className="mono block text-slate-300">{durationBetween(r.open_time, r.close_time)}</span></p></div>
              </div>;
            })}
          </div>
        </Panel>
      )}

      <ConfirmModal
        open={clearOpen}
        onClose={() => setClearOpen(false)}
        title="Clear visible trade history?"
        message="This clears trades from the normal recent-history views. Original records remain available under All Time, and new trades will appear normally."
        confirmLabel="Clear History"
        tone="warning"
        onConfirm={() => {
          setClearedAt(new Date().toISOString());
          if (dateFilter === 'all') setDateFilter('today');
        }}
      />
    </div>
  );
}
