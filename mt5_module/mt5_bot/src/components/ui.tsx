import type { ReactNode } from 'react';
import { motion } from 'framer-motion';
import type { LucideIcon } from 'lucide-react';

export function Panel({ className = '', children, hover = false }: { className?: string; children: ReactNode; hover?: boolean }) {
  return <div className={`glass rounded-2xl ${hover ? 'glass-hover' : ''} ${className}`}>{children}</div>;
}

export function PageHeader({ title, sub, actions }: { title: string; sub?: string; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 mb-6 max-md:items-stretch max-md:gap-3 max-md:mb-4">
      <div>
        <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-brand-400 mb-1.5">MT5 Hub</p>
        <h1 className="text-2xl md:text-[28px] font-bold text-white tracking-tight">{title}</h1>
        {sub && <p className="text-sm text-slate-500 mt-1">{sub}</p>}
      </div>
      {actions && <div className="flex items-center gap-2.5 flex-wrap max-md:w-full max-md:[&>button]:flex-1 max-md:[&>button]:justify-center max-md:[&>div]:w-full">{actions}</div>}
    </div>
  );
}

export function StatCard({
  label,
  value,
  sub,
  icon: Icon,
  tone = 'neutral',
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  icon?: LucideIcon;
  tone?: 'neutral' | 'gain' | 'loss' | 'brand';
}) {
  const toneText =
    tone === 'gain' ? 'text-gain-400' : tone === 'loss' ? 'text-loss-400' : tone === 'brand' ? 'text-brand-300' : 'text-white';
  const iconBg =
    tone === 'gain'
      ? 'bg-gain-500/12 text-gain-400'
      : tone === 'loss'
        ? 'bg-loss-500/12 text-loss-400'
        : 'bg-brand-500/12 text-brand-300';
  return (
    <Panel hover className="p-5 max-md:p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">{label}</p>
          <div className={`mono text-[22px] leading-8 font-bold mt-1.5 truncate max-md:text-[18px] max-md:leading-7 ${toneText}`}>{value}</div>
          {sub && <div className="text-xs text-slate-500 mt-1.5">{sub}</div>}
        </div>
        {Icon && (
          <div className={`shrink-0 rounded-xl p-2.5 ${iconBg}`}>
            <Icon size={18} strokeWidth={2.2} />
          </div>
        )}
      </div>
    </Panel>
  );
}

const BADGE_TONES: Record<string, string> = {
  brand: 'bg-brand-500/15 text-brand-300 border-brand-500/30',
  gain: 'bg-gain-500/12 text-gain-400 border-gain-500/25',
  loss: 'bg-loss-500/12 text-loss-400 border-loss-500/25',
  warn: 'bg-warn-400/10 text-warn-400 border-warn-400/25',
  slate: 'bg-white/[0.06] text-slate-400 border-white/10',
};

export function Badge({ tone = 'slate', children }: { tone?: keyof typeof BADGE_TONES; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${BADGE_TONES[tone]}`}>
      {children}
    </span>
  );
}

export function StatusDot({ status, className = '' }: { status: string; className?: string }) {
  const map: Record<string, string> = {
    connected: 'bg-gain-400 pulse-dot',
    running: 'bg-gain-400 pulse-dot',
    connecting: 'bg-warn-400 pulse-dot-amber',
    ready: 'bg-brand-400 pulse-dot',
    paused: 'bg-warn-400',
    disconnected: 'bg-slate-600',
    stopped: 'bg-slate-600',
  };
  return <span className={`inline-block h-2 w-2 rounded-full ${map[status] || 'bg-slate-600'} ${className}`} />;
}

export function EmptyState({ icon: Icon, title, sub, action }: { icon: LucideIcon; title: string; sub?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center py-14 px-6 text-center">
      <div className="rounded-2xl bg-brand-500/10 border border-brand-500/20 p-4 text-brand-300 mb-4">
        <Icon size={26} strokeWidth={1.8} />
      </div>
      <h3 className="text-base font-semibold text-white">{title}</h3>
      {sub && <p className="text-sm text-slate-500 mt-1.5 max-w-sm">{sub}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function Spinner({ size = 16, className = '' }: { size?: number; className?: string }) {
  return (
    <span
      className={`inline-block animate-spin rounded-full border-2 border-slate-600 border-t-brand-400 ${className}`}
      style={{ width: size, height: size }}
    />
  );
}

export function Progress({ value, tone = 'brand' }: { value: number; tone?: 'brand' | 'gain' | 'loss' | 'warn' }) {
  const pct = Math.max(0, Math.min(100, value));
  const bar =
    tone === 'gain' ? 'from-gain-500 to-gain-400' : tone === 'loss' ? 'from-loss-500 to-loss-400' : tone === 'warn' ? 'from-amber-500 to-warn-400' : 'from-brand-600 to-brand-400';
  return (
    <div className="h-1.5 w-full rounded-full bg-white/[0.07] overflow-hidden">
      <motion.div
        className={`h-full rounded-full bg-gradient-to-r ${bar}`}
        initial={{ width: 0 }}
        animate={{ width: `${pct}%` }}
        transition={{ duration: 0.7, ease: 'easeOut' }}
      />
    </div>
  );
}

export function Toggle({ on, onChange, disabled }: { on: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => onChange(!on)}
      className={`relative h-6 w-11 rounded-full transition-colors duration-200 cursor-pointer disabled:opacity-40 ${
        on ? 'bg-brand-600' : 'bg-white/10'
      }`}
    >
      <motion.span
        layout
        transition={{ type: 'spring', stiffness: 500, damping: 32 }}
        className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow ${on ? 'left-[22px]' : 'left-0.5'}`}
      />
    </button>
  );
}

export function Skel({ className = '' }: { className?: string }) {
  return <div className={`skeleton ${className}`} />;
}
