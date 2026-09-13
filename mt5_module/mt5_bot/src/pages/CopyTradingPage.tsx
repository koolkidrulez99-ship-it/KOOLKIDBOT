import { useEffect, useMemo, useState } from 'react';
import { ArrowRightLeft, Landmark, Link2, RefreshCw, ShieldCheck, Users } from 'lucide-react';
import { Badge, EmptyState, PageHeader, Panel, Spinner } from '../components/ui';
import { useHub } from '../context/HubContext';
import { isSimulation } from '../config/runtime';
import NumberStepper from '../components/NumberStepper';
import { mt5MultiAccountService } from '../services/mt5MultiAccountService';

type LotMode = 'same' | 'fixed' | 'multiplier' | 'equity_proportional';

export default function CopyTradingPage() {
  const { accounts, pushToast } = useHub();
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [master, setMaster] = useState<number | null>(null);
  const [slaves, setSlaves] = useState<number[]>([]);
  const [lotMode, setLotMode] = useState<LotMode>('same');
  const [fixedLot, setFixedLot] = useState('0.01');
  const [multiplier, setMultiplier] = useState('1.00');

  const workerByLogin = useMemo(() => new Map(accounts.map((account) => [account.login, {
    account_id: `session-${account.login}`, login: account.login, connected: account.status === 'connected',
  }])), [accounts]);
  const running = status?.status === 'running';

  const load = async () => {
    try {
      const [accountData, copyData] = await Promise.all([mt5MultiAccountService.accounts(), mt5MultiAccountService.copyStatus()]);
      const rows = accountData.accounts || [];
      setStatus(copyData);
      setError('');
      const configuredMaster = rows.find((row) => row.account_id === accountData.master)?.login;
      const configuredSlaves = rows.filter((row) => (accountData.slaves || []).includes(row.account_id)).map((row) => Number(row.login));
      if (configuredMaster) setMaster(Number(configuredMaster));
      if (configuredSlaves.length) setSlaves(configuredSlaves);
      const config = (copyData.config || null) as { lot_mode?: LotMode; fixed_lot?: number; multiplier?: number } | null;
      if (config?.lot_mode) setLotMode(config.lot_mode);
      if (config?.fixed_lot) setFixedLot(String(config.fixed_lot));
      if (config?.multiplier) setMultiplier(String(config.multiplier));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The multi-account worker is offline.');
    }
  };

  useEffect(() => { load(); }, []);

  const chooseMaster = (login: number) => {
    setMaster(login);
    setSlaves((values) => values.filter((value) => value !== login));
  };

  const toggleSlave = (login: number) => {
    if (login === master) return;
    setSlaves((values) => values.includes(login) ? values.filter((value) => value !== login) : [...values, login]);
  };

  const establish = async () => {
    if (!master) { pushToast('error', 'Choose a master account'); return; }
    if (!slaves.length) { pushToast('error', 'Choose at least one slave account'); return; }
    const selected = [master, ...slaves];
    const missing = selected.filter((login) => !workerByLogin.get(login)?.connected);
    if (missing.length) {
      pushToast('error', 'Connect selected accounts from MT5 Accounts', missing.map((login) => accounts.find((account) => account.login === login)?.nickname || `#${login}`).join(' · '));
      return;
    }
    const masterWorker = workerByLogin.get(master)!;
    const slaveWorkers = slaves.map((login) => workerByLogin.get(login)!).filter(Boolean);
    setBusy(true);
    try {
      await mt5MultiAccountService.startCopy({
        master_account_id: masterWorker.account_id,
        slave_account_ids: slaveWorkers.map((worker) => worker.account_id),
        lot_mode: lotMode,
        fixed_lot: Math.max(0.01, Number(fixedLot) || 0.01),
        multiplier: Math.max(0.01, Number(multiplier) || 1),
        source_filter: 'all',
        poll_ms: 300,
        approval_required: true,
      });
      pushToast('success', 'Copy link established', 'New master trades will ask before any slave order is submitted.');
      await load();
    } catch (reason) {
      pushToast('error', 'Could not establish copy link', reason instanceof Error ? reason.message : undefined);
    } finally {
      setBusy(false);
    }
  };

  const stop = async () => {
    setBusy(true);
    try {
      await mt5MultiAccountService.stopCopy();
      pushToast('info', 'Copy link stopped', 'Existing positions were left untouched.');
      await load();
    } catch (reason) {
      pushToast('error', 'Could not stop copy link', reason instanceof Error ? reason.message : undefined);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHeader title="Copy Trading" sub="Choose one Account Session as master and any connected sessions as slaves" actions={<button className="btn-ghost" onClick={load}><RefreshCw size={14} /> Refresh</button>} />

      {error ? <Panel><EmptyState icon={ArrowRightLeft} title="Copy worker unavailable" sub={error} action={<button className="btn-primary" onClick={load}>Retry</button>} /></Panel> : accounts.length < 2 ? (
        <Panel><EmptyState icon={Users} title="Two Account Sessions are required" sub="Add another account from MT5 Accounts, then return here to choose master and slave roles." /></Panel>
      ) : <>
        <Panel className="p-5 mb-5 border border-brand-500/20">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div><h3 className="text-sm font-bold text-white">Account Sessions</h3><p className="mt-1 text-xs text-slate-500">Your existing sessions are unchanged. Connect only the accounts that should participate in copying.</p></div>
            <Badge tone={running ? 'gain' : 'slate'}>{running ? 'LINK ACTIVE' : 'NOT LINKED'}</Badge>
          </div>
          <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3 gap-3">
            {accounts.map((account) => {
              const worker = workerByLogin.get(account.login);
              const isMaster = master === account.login;
              const isSlave = slaves.includes(account.login);
              return <div key={account.id} className={`rounded-xl border p-4 ${isMaster ? 'border-brand-500/45 bg-brand-500/[0.08]' : isSlave ? 'border-gain-500/35 bg-gain-500/[0.05]' : 'border-white/[0.07] bg-white/[0.03]'}`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3 min-w-0"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-white/[0.05] text-brand-300"><Landmark size={18} /></span><div className="min-w-0"><p className="font-bold text-white truncate">{account.nickname}</p><p className="mono text-[11px] text-slate-500">#{account.login} · {account.server}</p></div></div>
                  <Badge tone={account.status === 'connected' ? 'gain' : 'slate'}>{account.status === 'connected' ? 'CONNECTED' : 'OFFLINE'}</Badge>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-2">
                  <button className={isMaster ? 'btn-primary justify-center' : 'btn-ghost justify-center'} onClick={() => chooseMaster(account.login)}>Master</button>
                  <button className={isSlave ? 'btn-primary justify-center' : 'btn-ghost justify-center'} disabled={isMaster} onClick={() => toggleSlave(account.login)}>Slave</button>
                </div>
              </div>;
            })}
          </div>
        </Panel>

        <Panel className="p-5">
          <div className="flex items-center justify-between gap-3"><div><h3 className="text-sm font-bold text-white">Copy Link</h3><p className="mt-1 text-xs text-slate-500">Slave execution always waits for your confirmation popup.</p></div><Link2 size={19} className={running ? 'text-gain-400' : 'text-slate-600'} /></div>
          <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
            <div><label className="label">Lot mode</label><select className="input" value={lotMode} onChange={(event) => setLotMode(event.target.value as LotMode)}><option value="same">Same as master</option><option value="fixed">Fixed lot</option><option value="multiplier">Multiplier</option><option value="equity_proportional">Equity proportional</option></select></div>
            {lotMode === 'fixed' && <div><label className="label">Fixed slave lot</label><NumberStepper value={fixedLot} onChange={setFixedLot} min={0.01} max={100} step={0.01} decimals={2} /></div>}
            {lotMode === 'multiplier' && <div><label className="label">Lot multiplier</label><NumberStepper value={multiplier} onChange={setMultiplier} min={0.01} max={100} step={0.01} decimals={2} /></div>}
            <div className="flex items-end gap-2"><button className="btn-primary flex-1 justify-center" disabled={busy} onClick={establish}>{busy ? <Spinner size={14} /> : <Link2 size={14} />} Establish Link</button>{running && <button className="btn-danger justify-center" disabled={busy} onClick={stop}>Stop</button>}</div>
          </div>
          <p className="mt-4 flex items-start gap-2 rounded-xl border border-warn-400/20 bg-warn-400/[0.06] px-4 py-3 text-[11px] leading-relaxed text-slate-400"><ShieldCheck size={14} className="mt-0.5 shrink-0 text-warn-400" />Manual, KOOLKID, Auto Trade and EA positions detected on the master create an approval popup before slave orders. The master position itself is never delayed or changed by Copy Trading.</p>
        </Panel>
      </>}
    </div>
  );
}
