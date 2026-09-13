import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import {
  Activity, ArrowRight, Brain, ChevronRight, Crosshair, Cpu, Gauge, Scale, ShieldAlert, Square,
  TrendingUp, Wallet, Zap,
} from 'lucide-react';
import { useHub } from '../context/HubContext';
import { fmtDay, fmtSigned, fmtUSD, profitTone, uptimeSince } from '../lib/format';
import { Badge, PageHeader, Panel, Skel, StatCard, StatusDot } from '../components/ui';
import ConfirmModal from '../components/ConfirmModal';
import { botControl, closeAllPositions, stopAllBots } from '../lib/actions';
import type { AiInsight } from '../types';
import { aiControlService } from '../services/aiControlService';
import { isSimulation } from '../config/runtime';

const ChartTip = ({ active, payload, label }: { active?: boolean; payload?: { value: number }[]; label?: string }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="glass-strong rounded-lg px-3 py-2 text-xs shadow-xl">
      <p className="text-slate-500 mb-0.5">{label ? fmtDay(label) : ''}</p>
      <p className="mono font-bold text-white">{fmtUSD(payload[0].value)}</p>
    </div>
  );
};

const DailyTip = ({ active, payload, label }: { active?: boolean; payload?: { value: number }[]; label?: string }) => {
  if (!active || !payload?.length) return null;
  const v = payload[0].value;
  return (
    <div className="glass-strong rounded-lg px-3 py-2 text-xs shadow-xl">
      <p className="text-slate-500 mb-0.5">{label ? fmtDay(label) : ''}</p>
      <p className={`mono font-bold ${profitTone(v)}`}>{fmtSigned(v)}</p>
    </div>
  );
};

export default function OverviewPage() {
  const { stats, derived, scopeAccounts, scopeBots, positions, liveProfit, botLiveToday, accountName, pushToast, refresh, prefs } = useHub();
  const [range, setRange] = useState<'30' | '60' | 'all'>('all');
  const [confirm, setConfirm] = useState<'stop' | 'close' | null>(null);
  const [insights, setInsights] = useState<AiInsight[]>([]);

  useEffect(() => {
    aiControlService.get().then((d) => setInsights(d.insights || [])).catch(() => {});
  }, []);

  const equityData = useMemo(() => {
    const eq = stats?.equity || [];
    if (range === '30') return eq.slice(-30);
    if (range === '60') return eq.slice(-60);
    return eq;
  }, [stats, range]);

  const runningBots = scopeBots.filter((b) => b.status === 'running' || b.status === 'paused');

  const doStopAll = async () => {
    try {
      const r = await stopAllBots();
      pushToast('warning', `${r.stopped} bot${r.stopped === 1 ? '' : 's'} stopped`, 'All engines halted across the hub.');
      await refresh(true);
    } catch (e) {
      pushToast('error', 'Stop-all failed', e instanceof Error ? e.message : undefined);
    }
  };

  const doCloseAll = async () => {
    try {
      const r = await closeAllPositions();
      pushToast(
        r.realized >= 0 ? 'success' : 'warning',
        `Closed ${r.closed} position${r.closed === 1 ? '' : 's'}`,
        `Realized P/L ${fmtSigned(r.realized)} moved to history.`
      );
      await refresh(true);
    } catch (e) {
      pushToast('error', 'Close-all failed', e instanceof Error ? e.message : undefined);
    }
  };

  if (!stats) {
    return (
      <div className="space-y-4">
        <Skel className="h-8 w-72" />
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-4">
          {Array.from({ length: 5 }).map((_, i) => <Skel key={i} className="h-28" />)}
        </div>
        <Skel className="h-[340px]" />
      </div>
    );
  }

  const k = stats.kpis;

  return (
    <div>
      <PageHeader
        title="MT5 Overview"
        sub={`Aggregated telemetry across ${k.total_accounts} linked MetaTrader 5 account${k.total_accounts === 1 ? '' : 's'} \u00b7 as of ${k.latest_day ? fmtDay(k.latest_day) : '\u2014'}`}
        actions={
          <>
            <Link to="/mt5/manual" className="btn-ghost">
              <Crosshair size={15} /> New Trade
            </Link>
            <button className="btn-warn" onClick={() => (prefs.confirmDanger ? setConfirm('stop') : doStopAll())}>
              <Square size={13} /> Stop All Bots
            </button>
            <button className="btn-danger" onClick={() => (prefs.confirmDanger ? setConfirm('close') : doCloseAll())}>
              <ShieldAlert size={15} /> Close All Positions
            </button>
          </>
        }
      />

      {/* KPI cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-4">
        <StatCard label="Total Balance" value={fmtUSD(derived.balance)} icon={Wallet} sub={`${k.connected_accounts}/${k.total_accounts} ${isSimulation ? 'simulation profiles' : 'accounts connected'}`} />
        <StatCard label="Total Equity" value={fmtUSD(derived.equity)} icon={Scale} sub={`Peak ${fmtUSD(k.peak_equity, 0)} \u00b7 DD ${k.drawdown_pct}%`} />
        <StatCard
          label="Today's P/L"
          value={fmtSigned(derived.todayPl)}
          tone={derived.todayPl >= 0 ? 'gain' : 'loss'}
          icon={TrendingUp}
          sub={`Realized ${fmtSigned(k.realized_today)} \u00b7 Float ${fmtSigned(derived.floating)}`}
        />
        <StatCard
          label="Open Exposure"
          value={`${positions.length} ticket${positions.length === 1 ? '' : 's'}`}
          icon={Activity}
          tone="brand"
          sub={`Floating ${fmtSigned(derived.floating)}`}
        />
        <StatCard
          label="Margin Level"
          value={k.margin_level ? `${k.margin_level.toFixed(0)}%` : '\u221e'}
          icon={Gauge}
          tone="brand"
          sub={`Used ${fmtUSD(derived.margin, 0)} \u00b7 Free ${fmtUSD(derived.equity - derived.margin, 0)}`}
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 mt-4">
        <Panel className="xl:col-span-2 p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-sm font-bold text-white">Equity Curve</h3>
              <p className="text-[11px] text-slate-500">Consolidated across linked accounts</p>
            </div>
            <div className="flex gap-1.5">
              {(['30', '60', 'all'] as const).map((r) => (
                <button
                  key={r}
                  onClick={() => setRange(r)}
                  className={`rounded-lg px-2.5 py-1 text-[11px] font-bold cursor-pointer transition-colors ${
                    range === r ? 'bg-brand-600 text-white' : 'bg-white/[0.05] text-slate-400 hover:text-white'
                  }`}
                >
                  {r === 'all' ? 'ALL' : `${r}D`}
                </button>
              ))}
            </div>
          </div>
          <div className="h-[280px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={equityData} margin={{ top: 4, right: 4, left: 4, bottom: 0 }}>
                <defs>
                  <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="rgba(148,163,184,0.07)" vertical={false} />
                <XAxis dataKey="date" tickFormatter={fmtDay} tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={40} />
                <YAxis
                  domain={['auto', 'auto']}
                  tick={{ fill: '#64748b', fontSize: 10, fontFamily: 'JetBrains Mono' }}
                  axisLine={false}
                  tickLine={false}
                  width={64}
                  tickFormatter={(v: number) => `${(v / 1000).toFixed(0)}K`}
                />
                <Tooltip content={<ChartTip />} cursor={{ stroke: 'rgba(91,140,255,0.4)' }} />
                <Area type="monotone" dataKey="equity" stroke="#3b82f6" strokeWidth={2.2} fill="url(#eqGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel className="p-5">
          <h3 className="text-sm font-bold text-white">Daily P/L</h3>
          <p className="text-[11px] text-slate-500 mb-4">Last {stats.daily.length} sessions</p>
          <div className="h-[280px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={stats.daily} margin={{ top: 4, right: 4, left: 4, bottom: 0 }}>
                <CartesianGrid stroke="rgba(148,163,184,0.07)" vertical={false} />
                <XAxis dataKey="date" tickFormatter={fmtDay} tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={30} />
                <YAxis tick={{ fill: '#64748b', fontSize: 10, fontFamily: 'JetBrains Mono' }} axisLine={false} tickLine={false} width={44} />
                <Tooltip content={<DailyTip />} cursor={{ fill: 'rgba(148,163,184,0.06)' }} />
                <ReferenceLine y={0} stroke="rgba(148,163,184,0.25)" />
                <Bar dataKey="pl" radius={[4, 4, 0, 0]}>
                  {stats.daily.map((d, i) => (
                    <Cell key={i} fill={d.pl >= 0 ? '#10b981' : '#f43f5e'} fillOpacity={0.85} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      {/* Accounts + bots row */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mt-4">
        <Panel className="p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-bold text-white">Connected Accounts</h3>
            <Link to="/mt5/accounts" className="text-[11px] font-semibold text-brand-300 hover:text-brand-200 inline-flex items-center gap-1">
              Manage <ArrowRight size={12} />
            </Link>
          </div>
          <div className="divide-y divide-white/[0.05]">
            {scopeAccounts.map((a) => {
              const float = positions.filter((p) => p.account_login === a.login).reduce((s, p) => s + liveProfit(p), 0);
              return (
                <div key={a.id} className="flex items-center gap-3 py-3">
                  <StatusDot status={a.status} />
                  <div className="min-w-0 flex-1">
                    <p className="text-[13px] font-semibold text-white truncate">
                      {a.nickname} <span className="mono text-[10px] text-slate-500">#{a.login}</span>
                    </p>
                    <p className="text-[11px] text-slate-500">{a.broker} &middot; {a.server}</p>
                  </div>
                  <div className="text-right">
                    <p className="mono text-[13px] font-bold text-white">{fmtUSD(Number(a.balance) + float)}</p>
                    <p className={`mono text-[11px] ${profitTone(float)}`}>{float !== 0 ? fmtSigned(float) : 'flat'}</p>
                  </div>
                  <ChevronRight size={14} className="text-slate-600" />
                </div>
              );
            })}
            {!scopeAccounts.length && <p className="py-8 text-center text-sm text-slate-500">No accounts in this scope.</p>}
          </div>
        </Panel>

        <Panel className="p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-bold text-white">Bot Engines</h3>
            <Link to="/mt5/running" className="text-[11px] font-semibold text-brand-300 hover:text-brand-200 inline-flex items-center gap-1">
              Control room <ArrowRight size={12} />
            </Link>
          </div>
          <div className="divide-y divide-white/[0.05]">
            {runningBots.map((b) => (
              <div key={b.id} className="flex items-center gap-3 py-3">
                <span className={`grid h-9 w-9 place-items-center rounded-xl border ${
                  b.status === 'running' ? 'bg-gain-500/10 border-gain-500/25 text-gain-400' : 'bg-warn-400/10 border-warn-400/25 text-warn-400'
                }`}>
                  <Cpu size={15} />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] font-semibold text-white truncate">{b.name}</p>
                  <p className="text-[11px] text-slate-500">
                    {b.symbol} &middot; {b.timeframe} &middot; {accountName(b.account_login)} &middot; up {uptimeSince(b.started_at)}
                  </p>
                </div>
                <Badge tone={b.status === 'running' ? 'gain' : 'warn'}>{b.status}</Badge>
                <p className={`mono w-20 text-right text-[13px] font-bold ${profitTone(botLiveToday(b))}`}>{fmtSigned(botLiveToday(b))}</p>
                <button
                  className="btn-icon !p-1.5 hover:!text-loss-400"
                  title="Stop bot"
                  onClick={async () => {
                    try {
                      await botControl(b.id, 'stop');
                      pushToast('info', `${b.name} stopped`);
                      refresh(true);
                    } catch (e) {
                      pushToast('error', 'Stop failed', e instanceof Error ? e.message : undefined);
                    }
                  }}
                >
                  <Square size={13} />
                </button>
              </div>
            ))}
            {!runningBots.length && (
              <div className="py-8 text-center">
                <p className="text-sm text-slate-500">No engines running in this scope.</p>
                <Link to="/mt5/bots" className="btn-primary mt-4 inline-flex">
                  <Zap size={14} /> Launch from library
                </Link>
              </div>
            )}
          </div>
        </Panel>
      </div>

      {/* AI strip */}
      {insights.length > 0 && (
        <Panel className="mt-4 p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Brain size={15} className="text-brand-300" /> AI Desk - latest signals
            </h3>
            <Link to="/mt5/ai" className="text-[11px] font-semibold text-brand-300 hover:text-brand-200 inline-flex items-center gap-1">
              Open AI Intelligence <ArrowRight size={12} />
            </Link>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {insights.slice(0, 2).map((i) => (
              <div key={i.id} className="rounded-xl bg-white/[0.03] border border-white/[0.07] p-4">
                <div className="flex items-center gap-2 mb-1.5">
                  <Badge tone={i.sentiment === 'positive' ? 'gain' : i.sentiment === 'critical' ? 'loss' : i.sentiment === 'warning' ? 'warn' : 'brand'}>
                    {i.category}
                  </Badge>
                  <span className="mono text-[10px] text-slate-500">conf {i.confidence}%</span>
                </div>
                <p className="text-[13px] font-semibold text-white">{i.title}</p>
                <p className="text-xs text-slate-500 mt-1 line-clamp-2">{i.body}</p>
              </div>
            ))}
          </div>
        </Panel>
      )}

      <ConfirmModal
        open={confirm === 'stop'}
        onClose={() => setConfirm(null)}
        title="Stop all bots?"
        tone="warning"
        confirmLabel="Stop All Bots"
        message={
          <>Every running and paused engine across all MT5 accounts will be halted immediately. Open positions are <span className="text-slate-200 font-medium">not</span> closed by this action.</>
        }
        onConfirm={doStopAll}
      />
      <ConfirmModal
        open={confirm === 'close'}
        onClose={() => setConfirm(null)}
        title="Close all positions?"
        tone="danger"
        confirmLabel="Close All Positions"
        message={
          <>All <span className="mono font-bold text-white">{positions.length}</span> open tickets will be market-closed at current prices, realizing <span className={`mono font-bold ${profitTone(derived.floating)}`}>{fmtSigned(derived.floating)}</span> of floating P/L. This cannot be undone.</>
        }
        onConfirm={doCloseAll}
      />
    </div>
  );
}
