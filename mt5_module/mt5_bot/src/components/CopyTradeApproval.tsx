import { useEffect, useMemo, useState } from 'react';
import { ArrowRightLeft, ShieldCheck } from 'lucide-react';
import Modal from './Modal';
import { Badge, Spinner } from './ui';
import { useHub } from '../context/HubContext';
import { mt5MultiAccountService, type MultiAccount, type PendingCopy } from '../services/mt5MultiAccountService';

export default function CopyTradeApproval() {
  const { pushToast } = useHub();
  const [pending, setPending] = useState<PendingCopy[]>([]);
  const [accounts, setAccounts] = useState<MultiAccount[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const current = pending[0] || null;

  useEffect(() => {
    let stopped = false;
    const poll = async () => {
      try {
        const [queue, accountData] = await Promise.all([
          mt5MultiAccountService.pendingCopies(),
          mt5MultiAccountService.accounts(),
        ]);
        if (!stopped) {
          setPending(queue.pending || []);
          setAccounts(accountData.accounts || []);
        }
      } catch {
        if (!stopped) setPending([]);
      }
    };
    poll();
    const timer = window.setInterval(poll, 1000);
    return () => { stopped = true; window.clearInterval(timer); };
  }, []);

  useEffect(() => {
    setSelected(current?.slave_account_ids || []);
  }, [current?.master_ticket]);

  const accountById = useMemo(() => new Map(accounts.map((account) => [account.account_id, account])), [accounts]);

  const decide = async (copy: boolean) => {
    if (!current) return;
    if (copy && !selected.length) {
      pushToast('error', 'Choose at least one slave account');
      return;
    }
    setBusy(true);
    try {
      const result = await mt5MultiAccountService.decideCopy(current.master_ticket, copy, selected);
      if (!copy) {
        pushToast('info', 'Master trade kept separate', `Position #${current.master_ticket} was not copied.`);
      } else {
        const rows = Object.entries(result.results || {});
        const passed = rows.filter(([, row]) => row.ok);
        const failed = rows.filter(([, row]) => !row.ok);
        if (passed.length) pushToast('success', `Copied to ${passed.length} slave account${passed.length === 1 ? '' : 's'}`, `${String(current.position.side || current.position.type).toUpperCase()} ${current.position.symbol}`);
        if (failed.length) pushToast('error', `${failed.length} slave order${failed.length === 1 ? '' : 's'} failed`, failed.map(([id, row]) => `${accountById.get(id)?.nickname || id}: ${row.error || 'Rejected'}`).join(' · '));
      }
      setPending((items) => items.filter((item) => item.master_ticket !== current.master_ticket));
    } catch (error) {
      pushToast('error', 'Copy decision failed', error instanceof Error ? error.message : undefined);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={Boolean(current)} onClose={() => {}} title="Copy this trade?" sub="The master position is open. Choose whether to submit matching slave orders." wide>
      {current && <div>
        <div className="rounded-xl border border-brand-500/25 bg-brand-500/[0.06] p-4">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className="grid h-10 w-10 place-items-center rounded-lg bg-brand-500/15 text-brand-300"><ArrowRightLeft size={18} /></span>
              <div><p className="font-bold text-white">{current.position.symbol} · {String(current.position.side || current.position.type).toUpperCase()}</p><p className="mono text-[11px] text-slate-500">#{current.master_ticket} · {Number(current.position.volume || 0).toFixed(2)} lots</p></div>
            </div>
            <Badge tone="brand">MASTER OPEN</Badge>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-3 text-xs text-slate-400"><span>SL <b className="mono text-slate-200">{Number(current.position.sl || 0) || 'None'}</b></span><span>TP <b className="mono text-slate-200">{Number(current.position.tp || 0) || 'None'}</b></span></div>
        </div>

        <div className="mt-4">
          <div className="flex items-center justify-between"><p className="label !mb-0">Slave accounts</p><button className="text-[11px] font-bold text-brand-300" onClick={() => setSelected(current.slave_account_ids)}>SELECT ALL</button></div>
          <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-2">
            {current.slave_account_ids.map((id) => {
              const account = accountById.get(id);
              return <label key={id} className="flex items-center gap-3 rounded-xl border border-white/[0.07] bg-white/[0.03] px-3 py-3 text-xs text-slate-300">
                <input type="checkbox" checked={selected.includes(id)} onChange={(event) => setSelected(event.target.checked ? [...selected, id] : selected.filter((value) => value !== id))} />
                <span><b className="block text-white">{account?.nickname || id}</b><span className="mono text-slate-500">#{account?.login || id}</span></span>
              </label>;
            })}
          </div>
        </div>

        <p className="mt-4 flex items-start gap-2 rounded-xl border border-warn-400/20 bg-warn-400/[0.06] px-4 py-3 text-[11px] leading-relaxed text-slate-400"><ShieldCheck size={14} className="mt-0.5 shrink-0 text-warn-400" />No slave order is sent until you confirm. Skipping leaves the existing master position untouched.</p>
        <div className="mt-5 flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
          <button className="btn-ghost justify-center" disabled={busy} onClick={() => decide(false)}>Master Only</button>
          <button className="btn-primary justify-center" disabled={busy || !selected.length} onClick={() => decide(true)}>{busy ? <Spinner size={14} /> : <ArrowRightLeft size={14} />} Copy to Slaves</button>
        </div>
      </div>}
    </Modal>
  );
}
