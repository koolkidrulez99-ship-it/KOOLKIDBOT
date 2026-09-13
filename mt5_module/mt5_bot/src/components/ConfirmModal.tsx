import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import Modal from './Modal';
import { Spinner } from './ui';
import { TriangleAlert, ShieldAlert } from 'lucide-react';

export default function ConfirmModal({
  open,
  onClose,
  title,
  message,
  confirmLabel = 'Confirm',
  tone = 'danger',
  onConfirm,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  message?: ReactNode;
  confirmLabel?: string;
  tone?: 'danger' | 'warning' | 'primary';
  onConfirm: () => Promise<void> | void;
  children?: ReactNode;
}) {
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!open) setBusy(false);
  }, [open]);

  const run = async () => {
    setBusy(true);
    try {
      await onConfirm();
      onClose();
    } finally {
      setBusy(false);
    }
  };

  const Icon = tone === 'warning' ? ShieldAlert : TriangleAlert;
  const btnCls = tone === 'warning' ? 'btn-warn' : tone === 'primary' ? 'btn-primary' : 'btn-danger';
  const iconCls =
    tone === 'warning'
      ? 'bg-warn-400/10 text-warn-400 border-warn-400/25'
      : tone === 'primary'
        ? 'bg-brand-500/10 text-brand-300 border-brand-500/25'
        : 'bg-loss-500/10 text-loss-400 border-loss-500/25';

  return (
    <Modal open={open} onClose={busy ? () => {} : onClose} title={title}>
      <div className="flex items-start gap-3.5">
        <div className={`shrink-0 rounded-xl border p-2.5 ${iconCls}`}>
          <Icon size={20} />
        </div>
        <div className="text-sm text-slate-400 leading-relaxed">{message}</div>
      </div>
      {children && <div className="mt-4">{children}</div>}
      <div className="flex justify-end gap-2.5 mt-6">
        <button className="btn-ghost" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button className={btnCls} onClick={run} disabled={busy}>
          {busy ? <Spinner size={14} /> : null}
          {busy ? 'Working\u2026' : confirmLabel}
        </button>
      </div>
    </Modal>
  );
}
