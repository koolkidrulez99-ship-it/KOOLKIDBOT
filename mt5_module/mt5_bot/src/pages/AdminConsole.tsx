import { useEffect, useState } from 'react';
import { Activity, Beaker, Bot, Check, Clock3, LogOut, RefreshCw, ShieldCheck, Users, X } from 'lucide-react';
import { adminService } from '../services/adminService';
import type { AdminOverview, AdminUser, ResearchItem } from '../services/adminService';
import type { BacktestJob } from '../services/backtestService';
import { hubAuthService } from '../services/hubAuthService';

type Tab = 'users' | 'backtests' | 'research';

function when(value?: string | null) {
  return value ? new Date(value).toLocaleString() : '—';
}

function metric(value: unknown) {
  return value === null || value === undefined || value === '' ? '—' : String(value);
}

export default function AdminConsole({ username }: { username: string }) {
  const [tab, setTab] = useState<Tab>('users');
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [members, setMembers] = useState<AdminUser[]>([]);
  const [jobs, setJobs] = useState<BacktestJob[]>([]);
  const [research, setResearch] = useState<ResearchItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState('');

  const load = async () => {
    try {
      const [nextOverview, nextUsers, nextJobs, nextResearch] = await Promise.all([
        adminService.overview(),
        adminService.users(),
        adminService.backtests(),
        adminService.research(),
      ]);
      setOverview(nextOverview);
      setMembers(nextUsers);
      setJobs(nextJobs);
      setResearch(nextResearch);
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Admin data could not load.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => { void load(); }, 15000);
    return () => window.clearInterval(timer);
  }, []);
  const decide = async (item: ResearchItem, decision: 'approve' | 'reject' | 'research') => {
    setBusyId(item.id);
    try {
      await adminService.decide(item.id, decision);
      await load();
    } finally {
      setBusyId(null);
    }
  };

  const tabs: Array<[Tab, string]> = [
    ['users', 'Users'],
    ['backtests', 'Backtests'],
    ['research', 'Strategy Approval'],
  ];

  return (
    <div className="min-h-screen bg-[#04060b] text-slate-200">
      <header className="border-b border-white/[0.07] p-5">
        <div className="mx-auto flex max-w-[1600px] items-center gap-3">
          <ShieldCheck size={20} className="text-brand-300" />
          <div>
            <p className="font-extrabold text-white">KOOLKID Admin Console</p>
            <p className="text-[10px] text-slate-500">Signed in as {username}</p>
          </div>
          <div className="flex-1" />
          <button className="btn-ghost" onClick={() => void load()}><RefreshCw size={14} /> Refresh</button>
          <button className="btn-ghost" onClick={() => { hubAuthService.logout(); window.location.assign('/mt5-bot'); }}><LogOut size={14} /> Log out</button>
        </div>
      </header>
      <main className="mx-auto max-w-[1600px] p-5">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
          {[
            ['Users', overview?.total_users ?? 0],
            ['Online', overview?.online_users ?? 0],
            ['Active tests', overview?.active_backtests ?? 0],
            ['Completed', overview?.completed_backtests ?? 0],
            ['Pending research', overview?.pending_research ?? 0],
            ['Candidates', overview?.approved_candidates ?? 0],
          ].map(([label, value]) => (
            <div key={String(label)} className="rounded-xl border border-white/[0.07] bg-white/[0.025] p-4">
              <p className="text-[10px] uppercase tracking-wider text-slate-600">{label}</p>
              <p className="mono mt-1 text-xl font-extrabold text-white">{value}</p>
            </div>
          ))}
        </div>
        {error && <p className="mt-4 rounded-xl border border-loss-500/20 bg-loss-500/[0.05] p-3 text-xs text-loss-400">{error}</p>}
        <div className="mt-5 flex flex-wrap gap-2">
          {tabs.map(([value, label]) => (
            <button key={value} className={tab === value ? 'btn-primary' : 'btn-ghost'} onClick={() => setTab(value)}>{label}</button>
          ))}
        </div>
        {tab === 'users' && (
          <div className="mt-4 space-y-2">
            {members.map((member) => (
              <div key={member.username} className="rounded-xl border border-white/[0.07] p-4">
                <div className="flex items-center justify-between gap-3">
                  <b className="text-white">{member.username}</b>
                  <span className={member.online ? 'text-gain-400' : 'text-slate-500'}>{member.online ? 'Online' : 'Offline'}</span>
                </div>
                <p className="mt-1 text-[11px] text-slate-500">Role {member.role} · Last seen {when(member.last_seen)} · Backtests {member.backtests}</p>
              </div>
            ))}
          </div>
        )}
        {tab === 'backtests' && (
          <div className="mt-4 space-y-2">
            {jobs.map((job) => (
              <div key={job.id} className="rounded-xl border border-white/[0.07] p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <b className="text-white">{job.bot_filename}</b>
                    <p className="text-[11px] text-slate-500">{job.username} · {job.symbol} · {job.timeframe}</p>
                  </div>
                  <span className="mono text-sm font-bold text-brand-300">{job.progress}% · {job.status}</span>
                </div>
                <p className="mt-2 text-[11px] text-slate-500">{job.stage} · Started {when(job.started_at || job.created_at)}</p>
                {job.error && <p className="mt-1 text-[11px] text-loss-400">{job.error}</p>}
              </div>
            ))}
          </div>
        )}
        {tab === 'research' && (
          <div className="mt-4 space-y-3">
            {research.map((item) => (
              <div key={item.id} className="rounded-xl border border-white/[0.07] p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <b className="text-white">{item.bot_filename}</b>
                    <p className="text-[11px] text-slate-500">{item.username} · {item.symbol} · {item.timeframe}</p>
                  </div>
                  <span className="text-xs text-brand-300">{item.status}</span>
                </div>
                <div className="mt-3 space-y-1">
                  {item.observations.map((observation) => (
                    <p key={observation} className="text-xs text-slate-400">• {observation}</p>
                  ))}
                </div>
                <p className="mt-3 text-[11px] text-slate-500">
                  Trades {metric(item.backtest.total_trades)} · Factor {metric(item.backtest.profit_factor)} · Drawdown {metric(item.backtest.max_drawdown)}
                </p>
                {item.status === 'pending' && (
                  <div className="mt-4 flex flex-wrap gap-2">
                    <button className="btn-primary" disabled={busyId === item.id} onClick={() => void decide(item, 'approve')}>
                      <Check size={13} /> Approve Candidate
                    </button>
                    <button className="btn-ghost" disabled={busyId === item.id} onClick={() => void decide(item, 'research')}>
                      <Clock3 size={13} /> Keep Researching
                    </button>
                    <button className="btn-danger" disabled={busyId === item.id} onClick={() => void decide(item, 'reject')}>
                      <X size={13} /> Reject
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
        {loading && <p className="mt-6 text-sm text-slate-500">Loading...</p>}
      </main>
    </div>
  );
}
