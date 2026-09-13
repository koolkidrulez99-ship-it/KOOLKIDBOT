import { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { ChevronsUpDown, Menu, RefreshCw, Sparkles, Check, Moon, Sun } from 'lucide-react';
import { useHub } from '../context/HubContext';
import type { ActiveSel } from '../context/HubContext';
import { fmtSigned, fmtUSD } from '../lib/format';
import { Badge, StatusDot } from './ui';
import { isSimulation } from '../config/runtime';
import { useTheme } from '../hooks/useTheme';

const TITLES: [string, string][] = [
  ['/', 'Platform Dashboard'],
  ['/deriv', 'Deriv · Core Bots'],
  ['/mt5', 'MT5 Overview'],
  ['/mt5/accounts', 'MT5 Accounts'],
  ['/mt5/bots', 'Bot Library'],
  ['/mt5/running', 'Running Bots'],
  ['/mt5/charts', 'Charts'],
  ['/mt5/positions', 'Open Positions'],
  ['/mt5/history', 'Trade History'],
  ['/mt5/manual', 'Manual Trading'],
  ['/mt5/risk', 'Risk Center'],
  ['/mt5/ai', 'AI Intelligence'],
  ['/mt5/copy', 'Copy Trading'],
  ['/settings', 'Settings'],
];

function titleFor(path: string): string {
  const exact = TITLES.find(([p]) => p === path);
  if (exact) return exact[1];
  const partial = [...TITLES].reverse().find(([p]) => p !== '/' && path.startsWith(p));
  return partial ? partial[1] : 'MT5 Hub';
}

export default function TopBar({ onMenu }: { onMenu: () => void }) {
  const { accounts, active, setActive, derived, refresh, refreshing } = useHub();
  const [dropOpen, setDropOpen] = useState(false);
  const { theme, toggleTheme } = useTheme();
  const dropRef = useRef<HTMLDivElement>(null);
  const location = useLocation();

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (dropRef.current && !dropRef.current.contains(e.target as Node)) setDropOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const activeAcc = accounts.find((a) => a.login === active);
  const connected = accounts.filter((account) => account.status === 'connected').length;
  const totalAcc = accounts.length;
  const activeIsLive = activeAcc?.status === 'connected';
  const displayBalance = activeAcc ? (activeIsLive ? Number(activeAcc.balance || 0) : 0) : derived.balance;
  const displayEquity = activeAcc ? (activeIsLive ? Number(activeAcc.equity || 0) : 0) : derived.equity;
  const displayTodayPl = derived.todayPl;
  const plTone = displayTodayPl > 0 ? 'text-gain-400' : displayTodayPl < 0 ? 'text-loss-400' : 'text-slate-400';

  const pick = (sel: ActiveSel) => {
    setDropOpen(false);
    setActive(sel);
  };

  return (
    <header className="sticky top-0 z-30 border-b border-white/[0.06] bg-[#04060b]/80 backdrop-blur-xl">
      <div className="flex h-16 items-center gap-3 px-4 md:px-6">
        <button className="btn-icon lg:hidden" onClick={onMenu}>
          <Menu size={18} />
        </button>
        <h2 className="hidden sm:block text-sm font-bold text-white tracking-tight w-40 truncate">{titleFor(location.pathname)}</h2>

        {/* account switcher */}
        <div className="relative" ref={dropRef}>
          <button
            onClick={() => setDropOpen((o) => !o)}
            className="flex items-center gap-2.5 rounded-xl glass px-3 py-2 hover:border-brand-500/40 transition-colors cursor-pointer"
          >
            <StatusDot status={active === 'all' ? (connected > 0 ? 'connected' : 'disconnected') : activeAcc?.status || 'disconnected'} />
            <span className="text-left leading-tight">
              <span className="block text-[12px] font-semibold text-white max-w-[130px] truncate">
                {active === 'all' ? 'All Accounts' : activeAcc?.nickname || 'Select account'}
              </span>
              <span className="mono block text-[10px] text-slate-500">
                {active === 'all' ? `${totalAcc} linked` : activeAcc ? `#${activeAcc.login} · ${activeAcc.server}` : ''}
              </span>
            </span>
            <ChevronsUpDown size={14} className="text-slate-500" />
          </button>

          {dropOpen && (
            <div className="absolute left-0 top-[calc(100%+8px)] w-[300px] rounded-xl glass-strong p-1.5 shadow-2xl z-50">
              <button
                onClick={() => pick('all')}
                className={`w-full flex items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors cursor-pointer ${
                  active === 'all' ? 'bg-brand-500/15' : 'hover:bg-white/[0.05]'
                }`}
              >
                <StatusDot status={connected > 0 ? 'connected' : 'disconnected'} />
                <span className="flex-1 min-w-0">
                  <span className="block text-[13px] font-semibold text-white">All Accounts</span>
                  <span className="block text-[10px] text-slate-500">Aggregated portfolio view</span>
                </span>
                {active === 'all' && <Check size={14} className="text-brand-400" />}
              </button>
              <div className="my-1.5 h-px bg-white/[0.07]" />
              {accounts.map((a) => (
                <button
                  key={a.id}
                  onClick={() => pick(a.login)}
                  className={`w-full flex items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors cursor-pointer ${
                    active === a.login ? 'bg-brand-500/15' : 'hover:bg-white/[0.05]'
                  }`}
                >
                  <StatusDot status={a.status} />
                  <span className="flex-1 min-w-0">
                    <span className="block text-[13px] font-semibold text-white truncate">
                      {a.nickname}
                      {a.account_type === 'demo' && (
                        <span className="ml-1.5 text-[9px] font-bold uppercase tracking-wider text-warn-400">Demo</span>
                      )}
                    </span>
                    <span className="mono block text-[10px] text-slate-500">
                      #{a.login} · {a.broker}
                    </span>
                  </span>
                  <span className="mono text-[11px] text-slate-400">{fmtUSD(Number(a.balance), 2)}</span>
                  {active === a.login && <Check size={14} className="text-brand-400 shrink-0" />}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="flex-1" />

        <div className="hidden sm:block">
          <Badge tone={isSimulation ? 'warn' : activeAcc?.account_type === 'live' ? 'loss' : 'gain'}>
            {isSimulation ? 'SIMULATION' : activeAcc?.account_type === 'live' ? 'LIVE' : 'DEMO'}
          </Badge>
        </div>

        {/* metric chips */}
        <div className="hidden xl:flex items-center gap-2">
          <span className="chip">
            <span className="text-slate-500">Balance</span>
            <span className="mono font-bold text-white">{fmtUSD(displayBalance, 2)}</span>
          </span>
          <span className="chip">
            <span className="text-slate-500">Equity</span>
            <span className="mono font-bold text-white">{fmtUSD(displayEquity, 2)}</span>
          </span>
          <span className="chip">
            <span className="text-slate-500">Today P/L</span>
            <span className={`mono font-bold ${plTone}`}>{fmtSigned(displayTodayPl, 2)}</span>
          </span>
        </div>

        <span className="hidden md:inline-flex chip">
          <span className="relative flex h-2 w-2">
            {connected > 0 && <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${isSimulation ? 'bg-warn-400' : 'bg-gain-400'}`} />}
            <span className={`relative inline-flex h-2 w-2 rounded-full ${connected > 0 ? (isSimulation ? 'bg-warn-400' : 'bg-gain-400') : 'bg-slate-600'}`} />
          </span>
          <span className={connected > 0 ? (isSimulation ? 'text-warn-400 font-semibold' : 'text-gain-400 font-semibold') : 'text-slate-500 font-semibold'}>{isSimulation ? `${connected}/${totalAcc} Sim` : `${connected}/${totalAcc} Live`}</span>
        </span>

        <button onClick={toggleTheme} className="btn-icon" title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'} aria-label="Toggle color theme">
          {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
        </button>
        <button onClick={() => refresh()} className="btn-icon" title="Refresh hub data">
          <RefreshCw size={15} className={refreshing ? 'animate-spin text-brand-400' : ''} />
        </button>
        <span className="hidden lg:inline-flex chip !bg-brand-500/10 !border-brand-500/25">
          <Sparkles size={12} className="text-brand-300" />
          <span className="text-brand-300 font-semibold">{isSimulation ? 'AI Sim' : 'AI Active'}</span>
        </span>
      </div>
    </header>
  );
}
