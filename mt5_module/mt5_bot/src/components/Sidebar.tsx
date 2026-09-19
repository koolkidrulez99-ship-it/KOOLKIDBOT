import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard, Hexagon, Gauge, Wallet, Boxes, Cpu, ChartCandlestick, Layers, History,
  Crosshair, ShieldAlert, Sparkles, Settings, X, Signal, ArrowRightLeft, ArrowLeft, BookOpenText,
} from 'lucide-react';
import { useHub } from '../context/HubContext';
import { hostHomeUrl } from '../config/runtime';

interface NavDef {
  to: string;
  label: string;
  icon: typeof Gauge;
  end?: boolean;
  badge?: string;
  count?: number;
}

export default function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { accounts, stats, positions, bots, bridge } = useHub();
  const running = bots.filter((b) => b.status === 'running').length;

  const groups: { label: string; items: NavDef[] }[] = [
    { label: 'Platform', items: [
      { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
      { to: '/deriv', label: 'Deriv', icon: Hexagon, badge: 'Core' },
    ]},
    { label: 'MT5 Hub', items: [
      { to: '/mt5', label: 'Overview', icon: Gauge, end: true },
      { to: '/mt5/accounts', label: 'Accounts', icon: Wallet, count: stats?.kpis.total_accounts },
      { to: '/mt5/bots', label: 'Bot Library', icon: Boxes, count: bots.length },
      { to: '/mt5/running', label: 'Running Bots', icon: Cpu, count: running },
      { to: '/mt5/charts', label: 'Charts', icon: ChartCandlestick },
      { to: '/mt5/positions', label: 'Positions', icon: Layers, count: positions.length },
      { to: '/mt5/history', label: 'History', icon: History },
      { to: '/mt5/manual', label: 'Manual Trade', icon: Crosshair },
      { to: '/mt5/risk', label: 'Risk Center', icon: ShieldAlert },
      { to: '/mt5/ai', label: 'AI Intelligence', icon: Sparkles },
      { to: '/mt5/copy', label: 'Copy Trading', icon: ArrowRightLeft },
      { to: '/mt5/journal', label: '📔 Journal', icon: BookOpenText },
    ]},
    { label: 'System', items: [{ to: '/settings', label: 'Settings', icon: Settings }] },
  ];

  const services = bridge?.services || { bridge: bridge?.status === 'online' ? 'online' : 'offline', ea_worker: bridge?.ea_worker?.status || 'offline', copy_worker: 'offline' };
  const serviceTone = (status: string) => status === 'online' ? 'text-gain-400' : status === 'error' ? 'text-loss-400' : 'text-slate-500';
  const connectedAccounts = accounts.filter((account) => account.status === 'connected').length;

  return (
    <>
      <div className={`fixed inset-0 z-40 bg-black/60 backdrop-blur-sm transition-opacity lg:hidden ${open ? 'opacity-100' : 'opacity-0 pointer-events-none'}`} onClick={onClose} />
      <aside className={`fixed left-0 top-0 z-50 h-screen w-[248px] shrink-0 border-r border-white/[0.07] bg-[#05080f]/95 backdrop-blur-2xl flex flex-col transition-transform duration-300 lg:translate-x-0 ${open ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="flex items-center justify-between px-5 h-16 border-b border-white/[0.06]">
          <NavLink to="/" className="flex items-center gap-2.5">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 shadow-glow-brand"><ChartCandlestick size={18} className="text-white" strokeWidth={2.2} /></span>
            <span className="leading-none"><span className="block text-[15px] font-extrabold tracking-tight text-white">MT5 <span className="text-brand-400">HUB</span></span><span className="block text-[9px] font-semibold uppercase tracking-[0.24em] text-slate-500 mt-1">KOOLKID Integration Module</span></span>
          </NavLink>
          <button className="btn-icon lg:hidden" onClick={onClose}><X size={16} /></button>
        </div>

        {hostHomeUrl && <div className="px-3 pt-3"><a href={hostHomeUrl} className="btn-ghost w-full justify-center"><ArrowLeft size={14} /> Back to KOOLKID</a></div>}

        <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-5">
          {groups.map((g) => <div key={g.label}><p className="px-3 mb-1.5 text-[10px] font-bold uppercase tracking-[0.18em] text-slate-600">{g.label}</p><div className="space-y-0.5">{g.items.map((item) => <NavLink key={item.to} to={item.to} end={item.end} onClick={onClose} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}><item.icon size={16} strokeWidth={2.1} className="shrink-0" /><span className="flex-1 truncate">{item.label}</span>{typeof item.count === 'number' && item.count > 0 && <span className="mono rounded-md bg-white/[0.06] border border-white/10 px-1.5 py-0.5 text-[10px] font-bold text-slate-300">{item.count}</span>}{item.badge && <span className="rounded-md bg-brand-500/15 border border-brand-500/30 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-brand-300">{item.badge}</span>}</NavLink>)}</div></div>)}
        </nav>

        <div className="m-3 rounded-xl glass p-3.5">
          {([['MT5 Bridge', services.bridge], ['EA Worker', services.ea_worker], ['Copy Worker', services.copy_worker]] as const).map(([label, status]) => <div key={label} className="flex items-center justify-between py-1"><span className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-300"><Signal size={11} className={serviceTone(status)} /> {label}</span><span className={`mono text-[9px] font-bold uppercase ${serviceTone(status)}`}>{status}</span></div>)}
          <p className="mt-2 border-t border-white/[0.06] pt-2 text-[10px] text-slate-600">{connectedAccounts}/{accounts.length} live account sessions</p>
        </div>
      </aside>
    </>
  );
}
