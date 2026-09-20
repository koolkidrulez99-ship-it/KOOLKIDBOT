import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, BarChart3, Clock, Cpu, Target, TrendingDown, TrendingUp } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { useHub } from '../context/HubContext';
import { mt5HistoryService } from '../services/mt5HistoryService';
import { fmtSigned, fmtUSD, profitTone, uptimeSince } from '../lib/format';
import { Badge, EmptyState, PageHeader, Panel, Skel, StatCard } from '../components/ui';
import { isSimulation } from '../config/runtime';
import type { Mt5HistoryRow } from '../types';

type Range = 'today' | '7' | '30' | 'all';

function tradeNet(row: Mt5HistoryRow) {
  return Number(row.net_pl ?? (Number(row.profit || 0) + Number(row.swap || 0) + Number(row.commission || 0)));
}

export default function BotPerformancePage() {
  const { id } = useParams();
  const { bots, accountName } = useHub();
  const bot = bots.find((b) => b.id === Number(id));
  const [history, setHistory] = useState<Mt5HistoryRow[] | null>(null);
  const [range, setRange] = useState<Range>('all');

  useEffect(() => {
    mt5HistoryService.list(true).then(setHistory).catch(() => setHistory([]));
  }, []);

  const rows = useMemo(() => {
    if (!bot || !history) return [];
    const sourceLabel = `KKBOT(${bot.name})`;
    const legacyNative = `KKN${bot.id}:`;
    const matching = history.filter((h) =>
      Number(h.bot_id || 0) === bot.id
      || h.source === sourceLabel
      || h.source === bot.name
      || String(h.source || '').startsWith(legacyNative)
    );
    if (range === 'all') return matching;
    const now = new Date();
    if (range === 'today') return matching.filter((h) => new Date(h.close_time).toDateString() === now.toDateString());
    const days = Number(range);
    const cutoff = now.getTime() - days * 86400000;
    return matching.filter((h) => new Date(h.close_time).getTime() >= cutoff);
  }, [bot, history, range]);

  const perf = useMemo(() => {
    const wins = rows.filter((r) => tradeNet(r) > 0);
    const losses = rows.filter((r) => tradeNet(r) < 0);
    const grossProfit = wins.reduce((s, r) => s + tradeNet(r), 0);
    const grossLoss = losses.reduce((s, r) => s + tradeNet(r), 0);
    let curve = 0;
    let peak = 0;
    let maxDrawdown = 0;
    for (const r of [...rows].reverse()) {
      curve += tradeNet(r);
      peak = Math.max(peak, curve);
      maxDrawdown = Math.max(maxDrawdown, peak - curve);
    }
    return {
      trades: rows.length,
      wins: wins.length,
      losses: losses.length,
      winRate: rows.length ? (wins.length / rows.length) * 100 : 0,
      grossProfit,
      grossLoss,
      net: grossProfit + grossLoss,
      avgWin: wins.length ? grossProfit / wins.length : 0,
      avgLoss: losses.length ? grossLoss / losses.length : 0,
      largestWin: wins.length ? Math.max(...wins.map(tradeNet)) : 0,
      largestLoss: losses.length ? Math.min(...losses.map(tradeNet)) : 0,
      currentDrawdown: Math.max(0, peak - curve),
      maxDrawdown,
    };
  }, [rows]);

  if (!bot) {
    return <Panel><EmptyState icon={Cpu} title="Bot not found" sub="This bot is not present in the current library." action={<Link to="/mt5/bots" className="btn-primary">Back to Bot Library</Link>} /></Panel>;
  }

  return (
    <div>
      <PageHeader
        title={`${bot.name} Performance`}
        sub={isSimulation ? 'Recorded simulation results only · no real EA performance is claimed' : 'Performance calculated from recorded MT5 trade history'}
        actions={<Link to="/mt5/bots" className="btn-ghost"><ArrowLeft size={14} /> Bot Library</Link>}
      />

      <Panel className="p-5 mb-4">
        <div className="flex flex-wrap items-center gap-4">
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-brand-500/10 border border-brand-500/25 text-brand-300"><Cpu size={19} /></span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2"><p className="text-[15px] font-bold text-white">{bot.name}</p><Badge tone={bot.status === 'running' ? 'gain' : bot.status === 'paused' ? 'warn' : 'slate'}>{bot.status}</Badge>{isSimulation && <Badge tone="warn">simulation</Badge>}</div>
            <p className="text-[11px] text-slate-500 mt-1">{accountName(bot.account_login)} · {bot.symbol} · {bot.timeframe} · {bot.lot_size.toFixed(2)} lots · runtime {uptimeSince(bot.started_at)}</p>
          </div>
          <div className="flex gap-1 rounded-xl glass p-1">
            {(['today', '7', '30', 'all'] as Range[]).map((r) => <button key={r} onClick={() => setRange(r)} className={`rounded-lg px-3 py-1.5 text-[11px] font-bold cursor-pointer ${range === r ? 'bg-brand-600 text-white' : 'text-slate-400 hover:text-white'}`}>{r === 'today' ? 'TODAY' : r === 'all' ? 'ALL TIME' : `${r} DAYS`}</button>)}
          </div>
        </div>
      </Panel>

      {history === null ? <div className="grid grid-cols-2 md:grid-cols-4 gap-3">{Array.from({ length: 8 }).map((_, i) => <Skel key={i} className="h-28" />)}</div> : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3">
            <StatCard label="Trades" value={perf.trades} icon={BarChart3} />
            <StatCard label="Wins / Losses" value={`${perf.wins} / ${perf.losses}`} icon={Target} />
            <StatCard label="Win rate" value={perf.trades ? `${perf.winRate.toFixed(1)}%` : '—'} tone="brand" />
            <StatCard label="Net P/L" value={perf.trades ? fmtSigned(perf.net) : '—'} tone={perf.net >= 0 ? 'gain' : 'loss'} icon={TrendingUp} />
            <StatCard label="Floating P/L" value={fmtSigned(Number(bot.current_pl || 0))} tone={Number(bot.current_pl || 0) >= 0 ? 'gain' : 'loss'} />
            <StatCard label="Realized today" value={fmtSigned(Number(bot.today_pl || 0))} tone={Number(bot.today_pl || 0) >= 0 ? 'gain' : 'loss'} />
            <StatCard label="Gross profit" value={perf.trades ? fmtUSD(perf.grossProfit) : '—'} tone="gain" />
            <StatCard label="Gross loss" value={perf.trades ? fmtSigned(perf.grossLoss) : '—'} tone="loss" />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3 mt-3">
            <StatCard label="Average win" value={perf.wins ? fmtUSD(perf.avgWin) : '—'} />
            <StatCard label="Average loss" value={perf.losses ? fmtSigned(perf.avgLoss) : '—'} />
            <StatCard label="Largest win" value={perf.wins ? fmtUSD(perf.largestWin) : '—'} icon={TrendingUp} tone="gain" />
            <StatCard label="Largest loss" value={perf.losses ? fmtSigned(perf.largestLoss) : '—'} icon={TrendingDown} tone="loss" />
            <StatCard label="Current DD" value={perf.trades ? fmtUSD(perf.currentDrawdown) : '—'} />
            <StatCard label="Max DD" value={perf.trades ? fmtUSD(perf.maxDrawdown) : '—'} />
          </div>

          <Panel className="mt-4 overflow-hidden">
            <div className="px-5 py-4 border-b border-white/[0.06] flex items-center gap-2"><Clock size={14} className="text-brand-300" /><h3 className="text-sm font-bold text-white">Recorded trades</h3><span className="text-[11px] text-slate-600">{rows.length} in selected range</span></div>
            {rows.length === 0 ? <EmptyState icon={BarChart3} title="No recorded performance in this range" sub="The hub will calculate results only from trades actually recorded for this bot. It does not invent performance data." /> : (
              <div className="overflow-x-auto"><table className="tbl"><thead><tr><th>Ticket</th><th>Symbol</th><th>Side</th><th>Volume</th><th>Close</th><th>P/L</th></tr></thead><tbody>{rows.slice(0, 50).map((r) => {
                const net = tradeNet(r);
                return <tr key={`${r.account_login}:${r.ticket}:${r.close_time}`}><td className="mono text-slate-400">#{r.ticket}</td><td className="font-semibold text-white">{r.symbol}</td><td><Badge tone={r.type === 'buy' ? 'brand' : 'loss'}>{r.type}</Badge></td><td className="mono text-slate-300">{r.volume.toFixed(2)}</td><td className="text-slate-500">{new Date(r.close_time).toLocaleString()}</td><td className={`mono font-bold ${profitTone(net)}`}>{fmtSigned(net)}</td></tr>;
              })}</tbody></table></div>
            )}
          </Panel>
        </>
      )}
    </div>
  );
}
