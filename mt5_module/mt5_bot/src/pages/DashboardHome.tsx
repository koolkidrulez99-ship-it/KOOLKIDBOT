import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight, ChartCandlestick, Cpu, Hexagon, History as HistoryIcon, Sparkles, TrendingUp } from 'lucide-react';
import { useHub } from '../context/HubContext';
import { fmtDateTime, fmtSigned, fmtUSD, profitTone } from '../lib/format';
import { Badge, Panel, Skel, StatCard } from '../components/ui';
import type { DerivAccount, Mt5HistoryRow } from '../types';
import { derivMarketService } from '../services/derivMarketService';
import { mt5HistoryService } from '../services/mt5HistoryService';
import { isSimulation } from '../config/runtime';

export default function DashboardHome() {
  const { stats, derived } = useHub();
  const [deriv, setDeriv] = useState<DerivAccount[]>([]);
  const [recent, setRecent] = useState<Mt5HistoryRow[] | null>(null);

  useEffect(() => {
    derivMarketService.accounts().then(setDeriv).catch(() => setDeriv([]));
    mt5HistoryService.list().then((rows) => setRecent(rows.slice(0, 6))).catch(() => setRecent([]));
  }, []);

  const today = new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });

  return (
    <div>
      {/* hero */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>
        <Panel className="relative overflow-hidden p-6 md:p-8">
          <div className="absolute -right-24 -top-24 h-72 w-72 rounded-full bg-brand-600/20 blur-3xl" />
          <div className="absolute -left-16 -bottom-24 h-56 w-56 rounded-full bg-gain-500/10 blur-3xl" />
          <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-brand-400">{today}</p>
          <h1 className="mt-2 text-2xl md:text-3xl font-extrabold text-white tracking-tight">
            Command every book from <span className="bg-gradient-to-r from-brand-300 to-brand-500 bg-clip-text text-transparent">one terminal</span>
          </h1>
          <p className="mt-2 max-w-xl text-sm text-slate-400 leading-relaxed">
            A standalone MetaTrader 5 control hub prepared to plug into your existing Deriv bot - accounts, bots, risk, charts and AI controls stay cleanly separated.
          </p>
          <div className="mt-5 flex flex-wrap gap-2.5">
            <Link to="/mt5" className="btn-primary">
              <ChartCandlestick size={15} /> Open MT5 Hub
            </Link>
            <Link to="/deriv" className="btn-ghost">
              <Hexagon size={15} /> Deriv Module
            </Link>
          </div>
        </Panel>
      </motion.div>

      {/* stats */}
      {stats ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 mt-4">
          <StatCard label="Platform Equity" value={fmtUSD(derived.equity)} icon={TrendingUp} tone="brand" sub={`${stats.kpis.total_accounts} MT5 \u00b7 ${deriv.length} Deriv accounts`} />
          <StatCard
            label="Today's P/L"
            value={fmtSigned(derived.todayPl)}
            tone={derived.todayPl >= 0 ? 'gain' : 'loss'}
            icon={Sparkles}
            sub={`${stats.kpis.trades_today} fills today \u00b7 ${fmtSigned(stats.kpis.realized_today)} realized`}
          />
          <StatCard label="Engines Running" value={stats.kpis.running_bots} icon={Cpu} tone="brand" sub={`${stats.kpis.total_bots} in library \u00b7 ${stats.kpis.paused_bots} paused`} />
          <StatCard label="30-Day Net" value={fmtSigned(stats.kpis.profit_30d)} tone={stats.kpis.profit_30d >= 0 ? 'gain' : 'loss'} icon={HistoryIcon} sub={`${stats.kpis.win_rate_30d}% win rate \u00b7 ${stats.kpis.trades_30d} trades`} />
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 mt-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skel key={i} className="h-28" />
          ))}
        </div>
      )}

      {/* modules */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
        <Link to="/mt5" className="block group">
          <Panel hover className="p-6 h-full">
            <div className="flex items-center justify-between">
              <span className="grid h-12 w-12 place-items-center rounded-2xl bg-brand-600/20 border border-brand-500/40 text-brand-300">
                <ChartCandlestick size={22} />
              </span>
              <Badge tone={isSimulation ? 'warn' : 'gain'}>{isSimulation ? 'Simulation' : 'Active'}</Badge>
            </div>
            <h3 className="mt-4 text-lg font-bold text-white">MT5 Hub</h3>
            <p className="mt-1.5 text-xs text-slate-500 leading-relaxed">
              Connect MetaTrader 5 accounts, deploy engines, watch positions and control risk - all from the browser.
            </p>
            <p className="mt-4 inline-flex items-center gap-1.5 text-[12px] font-bold text-brand-300 group-hover:gap-2.5 transition-all">
              Launch module <ArrowRight size={14} />
            </p>
          </Panel>
        </Link>
        <Link to="/deriv" className="block group">
          <Panel hover className="p-6 h-full">
            <div className="flex items-center justify-between">
              <span className="grid h-12 w-12 place-items-center rounded-2xl bg-warn-400/10 border border-warn-400/30 text-warn-400">
                <Hexagon size={22} />
              </span>
              <Badge tone="warn">Core</Badge>
            </div>
            <h3 className="mt-4 text-lg font-bold text-white">Deriv Bots</h3>
            <p className="mt-1.5 text-xs text-slate-500 leading-relaxed">
              The original automation core - Deriv API accounts, synthetic indices strategies and DBot deployments.
            </p>
            <p className="mt-4 inline-flex items-center gap-1.5 text-[12px] font-bold text-warn-400 group-hover:gap-2.5 transition-all">
              Open module <ArrowRight size={14} />
            </p>
          </Panel>
        </Link>
      </div>

      {/* recent activity */}
      <Panel className="mt-4 p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold text-white">Latest MT5 fills</h3>
          <Link to="/mt5/history" className="text-[11px] font-semibold text-brand-300 hover:text-brand-200 inline-flex items-center gap-1">
            Full history <ArrowRight size={12} />
          </Link>
        </div>
        {recent === null ? (
          <div className="space-y-2">{Array.from({ length: 4 }).map((_, i) => <Skel key={i} className="h-11" />)}</div>
        ) : recent.length === 0 ? (
          <p className="text-xs text-slate-600 py-4 text-center">No fills yet.</p>
        ) : (
          <div className="divide-y divide-white/[0.05]">
            {recent.map((r) => (
              <div key={r.id} className="flex items-center gap-3 py-2.5">
                <Badge tone={r.type === 'buy' ? 'brand' : 'loss'}>{r.type}</Badge>
                <span className="text-[13px] font-semibold text-white">{r.symbol}</span>
                <span className="mono text-[11px] text-slate-500">{Number(r.volume).toFixed(2)} lots</span>
                <span className="hidden sm:block text-[11px] text-slate-600">{r.source}</span>
                <span className="ml-auto text-[11px] text-slate-500">{fmtDateTime(r.close_time)}</span>
                <span className={`mono w-20 text-right text-[13px] font-bold ${profitTone(Number(r.profit))}`}>{fmtSigned(Number(r.profit))}</span>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
