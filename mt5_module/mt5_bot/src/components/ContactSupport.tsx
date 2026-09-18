import { useEffect, useState } from 'react';
import { ExternalLink, Headphones, Timer, X } from 'lucide-react';
import { hubAuthService } from '../services/hubAuthService';
import type { HubTrialInfo } from '../services/hubAuthService';

export const TELEGRAM_URL = 'https://t.me/jordibrown';
export const WHATSAPP_URL = 'https://wa.me/qr/XFJMRUGZX5SBF1';
export const CONTACT_SUPPORT_OPEN_EVENT = 'koolkid:mt5-contact-support-open';

function TelegramLogo({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={className} fill="currentColor">
      <path d="M23.91 3.79 20.3 20.84c-.27 1.21-.98 1.51-1.99.94l-5.5-4.06-2.65 2.55c-.29.29-.54.54-1.1.54l.39-5.56L19.56 6.1c.44-.39-.1-.61-.68-.22L6.39 13.75 1 12.07c-1.17-.37-1.19-1.17.24-1.73L22.3 2.23c.98-.36 1.83.24 1.61 1.56Z" />
    </svg>
  );
}

function WhatsAppLogo({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={className} fill="none" stroke="currentColor" strokeWidth="1.9">
      <path d="M20 11.7a8 8 0 0 1-11.8 7L4 20l1.3-4.1A8 8 0 1 1 20 11.7Z" fill="currentColor" opacity=".12" />
      <path d="M8.4 7.8c.2-.5.4-.5.7-.5h.5c.2 0 .4.1.5.4l.7 1.7c.1.3 0 .5-.1.7l-.5.7c-.1.2-.2.4 0 .7.5.9 1.3 1.7 2.2 2.2.3.2.5.1.7-.1l.8-1c.2-.2.4-.3.7-.2l1.7.8c.3.1.4.3.4.5 0 .4-.2 1.2-.8 1.8-.6.6-1.4.9-2.4.6-1.3-.4-3-1.2-4.8-3-1.4-1.4-2.4-3.1-2.6-4.1-.2-.9.1-1.7.6-2.2Z" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function ContactButtons({ compact = false }: { compact?: boolean }) {
  const shared = compact
    ? 'flex-1 min-w-0 rounded-xl px-3 py-2.5 text-xs font-bold flex items-center justify-center gap-2 transition-transform hover:-translate-y-0.5'
    : 'flex-1 rounded-xl px-4 py-3 text-sm font-bold flex items-center justify-center gap-2.5 transition-transform hover:-translate-y-0.5';

  return (
    <div className="flex gap-2.5">
      <a href={TELEGRAM_URL} target="_blank" rel="noreferrer noopener" className={`${shared} bg-[#229ED9] text-white shadow-lg shadow-[#229ED9]/10`}>
        <TelegramLogo className={compact ? 'h-4 w-4' : 'h-5 w-5'} />
        <span>Telegram</span>
        <ExternalLink size={compact ? 11 : 13} className="opacity-70" />
      </a>
      <a href={WHATSAPP_URL} target="_blank" rel="noreferrer noopener" className={`${shared} bg-[#25D366] text-[#052e16] shadow-lg shadow-[#25D366]/10`}>
        <WhatsAppLogo className={compact ? 'h-4 w-4' : 'h-5 w-5'} />
        <span>WhatsApp</span>
        <ExternalLink size={compact ? 11 : 13} className="opacity-60" />
      </a>
    </div>
  );
}

function formatRemaining(total: number) {
  const value = Math.max(0, Math.floor(total));
  const days = Math.floor(value / 86400);
  const hours = Math.floor((value % 86400) / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const seconds = value % 60;
  return { days, hours, minutes, seconds };
}

export function useTrialCountdown(trial: HubTrialInfo | null | undefined) {
  const [remaining, setRemaining] = useState(() => Math.max(0, Number(trial?.remaining_seconds || 0)));

  useEffect(() => {
    const initial = Math.max(0, Number(trial?.remaining_seconds || 0));
    const started = performance.now();
    setRemaining(initial);
    const update = () => {
      const elapsed = Math.floor((performance.now() - started) / 1000);
      setRemaining(Math.max(0, initial - elapsed));
    };
    update();
    const id = window.setInterval(update, 1000);
    return () => window.clearInterval(id);
  }, [trial?.end_at, trial?.remaining_seconds, trial?.server_now]);

  return { remaining, ...formatRemaining(remaining) };
}

export function TrialCountdown({ trial, large = false }: { trial?: HubTrialInfo | null; large?: boolean }) {
  const countdown = useTrialCountdown(trial);
  if (!trial) return <span className="text-slate-500">Loading trial time...</span>;
  if (trial.expired || countdown.remaining <= 0) {
    return <span className="font-extrabold text-loss-400">TRIAL EXPIRED</span>;
  }
  const units = [
    ['DAYS', countdown.days],
    ['HRS', countdown.hours],
    ['MIN', countdown.minutes],
    ['SEC', countdown.seconds],
  ] as const;

  return (
    <div className={large ? 'grid grid-cols-4 gap-2' : 'flex items-center gap-1.5'}>
      {units.map(([label, value]) => (
        <div key={label} className={large
          ? 'rounded-xl border border-brand-500/20 bg-brand-500/[0.07] px-2 py-3 text-center'
          : 'rounded-md border border-white/[0.07] bg-white/[0.04] px-1.5 py-1 text-center'}>
          <span className={large ? 'mono block text-xl font-extrabold text-white' : 'mono block text-[11px] font-bold text-white'}>
            {String(value).padStart(2, '0')}
          </span>
          <span className={large ? 'block text-[8px] font-bold tracking-[0.16em] text-slate-500 mt-0.5' : 'block text-[6px] font-bold tracking-wider text-slate-600'}>
            {label}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function ContactSupport({ trial: suppliedTrial }: { trial?: HubTrialInfo | null }) {
  const [trial, setTrial] = useState<HubTrialInfo | null>(suppliedTrial || null);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    if (suppliedTrial) {
      setTrial(suppliedTrial);
      return;
    }
    let cancelled = false;
    hubAuthService.trial().then((value) => {
      if (!cancelled) setTrial(value);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [suppliedTrial]);

  useEffect(() => {
    const reopen = () => setVisible(true);
    window.addEventListener(CONTACT_SUPPORT_OPEN_EVENT, reopen);
    return () => window.removeEventListener(CONTACT_SUPPORT_OPEN_EVENT, reopen);
  }, []);

  const countdown = useTrialCountdown(trial);

  if (!visible) return null;

  return (
    <aside className="fixed bottom-4 right-4 z-[70] w-[min(360px,calc(100vw-2rem))] rounded-2xl border border-brand-500/25 bg-[#070b13]/95 p-3.5 shadow-2xl shadow-black/40 backdrop-blur-xl">
      <button
        type="button"
        onClick={() => setVisible(false)}
        className="absolute right-2.5 top-2.5 grid h-7 w-7 place-items-center rounded-lg border border-white/[0.07] bg-white/[0.04] text-slate-500 transition-colors hover:bg-white/[0.08] hover:text-white"
        title="Close Contact Us"
        aria-label="Close Contact Us"
      >
        <X size={14} />
      </button>
      <div className="flex items-start gap-3 pr-8">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-brand-500/15 text-brand-300 ring-1 ring-brand-500/25">
          <Headphones size={17} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[13px] font-extrabold text-white">Contact Us</p>
            <span className="rounded-full border border-warn-400/25 bg-warn-400/10 px-2 py-0.5 text-[8px] font-extrabold uppercase tracking-[0.14em] text-warn-300">
              30-Day Free Trial
            </span>
          </div>
          <p className="mt-0.5 text-[10px] text-slate-500">Need help or more information? Contact the KOOLKID admin.</p>
        </div>
      </div>
      <div className="mt-3 flex items-center justify-between gap-3 rounded-xl border border-white/[0.06] bg-white/[0.025] px-3 py-2">
        <span className="flex items-center gap-1.5 text-[9px] font-bold uppercase tracking-wider text-slate-500"><Timer size={11} /> Trial left</span>
        <span className="mono text-[10px] font-bold text-slate-200">
          {trial ? (trial.expired || countdown.remaining <= 0 ? 'EXPIRED' : `${countdown.days}d ${String(countdown.hours).padStart(2, '0')}h ${String(countdown.minutes).padStart(2, '0')}m`) : 'Loading...'}
        </span>
      </div>
      <div className="mt-3"><ContactButtons compact /></div>
    </aside>
  );
}
