import { AlertTriangle, CalendarDays, ShieldCheck } from 'lucide-react';
import Modal from './Modal';
import { ContactButtons, TrialCountdown } from './ContactSupport';
import type { HubTrialInfo } from '../services/hubAuthService';

function dateLabel(value?: string) {
  if (!value) return '—';
  return new Date(value).toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  });
}

export default function TrialNotice({
  open,
  onClose,
  trial,
}: {
  open: boolean;
  onClose: () => void;
  trial?: HubTrialInfo | null;
}) {
  const expired = Boolean(trial?.expired || (trial && trial.remaining_seconds <= 0));

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="KOOLKID 30-Day Free Trial"
      sub="One global trial period for all KOOLKID MT5 Hub users"
      wide
    >
      <div className={`rounded-2xl border p-4 ${expired ? 'border-loss-500/25 bg-loss-500/[0.06]' : 'border-brand-500/25 bg-brand-500/[0.06]'}`}>
        <div className="flex items-start gap-3">
          <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${expired ? 'bg-loss-500/15 text-loss-300' : 'bg-brand-500/15 text-brand-300'}`}>
            {expired ? <AlertTriangle size={19} /> : <ShieldCheck size={19} />}
          </span>
          <div>
            <p className="text-sm font-extrabold text-white">{expired ? 'The free trial period has ended.' : 'This is a free public testing trial.'}</p>
            <p className="mt-1 text-xs leading-relaxed text-slate-400">
              {expired
                ? 'Contact the KOOLKID admin for more information about continued access.'
                : 'KOOLKID is free during this trial so users can test the MT5 Hub and its features while the admin identifies bugs, fixes issues, and continues improving the platform.'}
            </p>
          </div>
        </div>
      </div>

      <div className="mt-5">
        <p className="mb-2 text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">Global trial time remaining</p>
        <TrialCountdown trial={trial} large />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.025] px-3 py-3">
          <p className="flex items-center gap-1.5 text-[9px] font-bold uppercase tracking-wider text-slate-600"><CalendarDays size={11} /> Trial started</p>
          <p className="mt-1 text-[12px] font-semibold text-slate-300">{dateLabel(trial?.start_at)}</p>
        </div>
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.025] px-3 py-3">
          <p className="flex items-center gap-1.5 text-[9px] font-bold uppercase tracking-wider text-slate-600"><CalendarDays size={11} /> Trial ends</p>
          <p className="mt-1 text-[12px] font-semibold text-slate-300">{dateLabel(trial?.end_at)}</p>
        </div>
      </div>

      <p className="mt-4 text-xs leading-relaxed text-slate-500">
        This is one shared 30-day trial for everyone. New users do not receive a fresh 30 days. The countdown continues from the same global start date and does not reset when KOOLKID is updated, rebuilt, restarted, or redeployed.
      </p>

      <div className="mt-5 rounded-2xl border border-white/[0.07] bg-black/20 p-4">
        <p className="text-sm font-bold text-white">Need help or more information?</p>
        <p className="mt-1 text-xs text-slate-500">Contact the KOOLKID admin directly through Telegram or WhatsApp.</p>
        <div className="mt-3"><ContactButtons /></div>
      </div>

      <button type="button" onClick={onClose} className="btn-primary mt-5 w-full justify-center">
        Continue to KOOLKID
      </button>
      <p className="mt-3 text-center text-[10px] text-slate-600">Trading involves risk. Use the trial to test features and controls carefully.</p>
    </Modal>
  );
}
