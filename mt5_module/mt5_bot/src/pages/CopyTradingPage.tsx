import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowRightLeft, Gauge, Landmark, Link2, RefreshCw, ShieldCheck, Users } from 'lucide-react';
import { Badge, EmptyState, PageHeader, Panel, Spinner, Toggle } from '../components/ui';
import { useHub } from '../context/HubContext';
import NumberStepper from '../components/NumberStepper';
import { mt5MultiAccountService } from '../services/mt5MultiAccountService';

type LotMode = 'same' | 'fixed' | 'multiplier' | 'equity_proportional';

interface CopyTimingActivity {
  time?: number;
  event?: string;
  master_ticket?: string | number;
  elapsed_ms?: number;
  fill_spread_ms?: number;
  slave_count?: number;
  filled_count?: number;
  results?: Record<string, { ok?: boolean; elapsed_ms?: number; error?: string }>;
}

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
  const [trailByShoulders, setTrailByShoulders] = useState(false);
  const configDirty = useRef(false);

  const workerByLogin = useMemo(() => new Map(accounts.map((account) => [account.login, {
    account_id: `session-${account.login}`, login: account.login, connected: account.status === 'connected',
  }])), [accounts]);
  const running = status?.status === 'running';
  const copyActivity = useMemo(
    () => (Array.isArray(status?.activity) ? status.activity as CopyTimingActivity[] : []),
    [status],
  );
  const latestCopyTiming = useMemo(
    () => copyActivity.find((row) => row.event === 'copy_completed') || null,
    [copyActivity],
  );
  const latestSlaveTimings = useMemo(
    () => Object.entries(latestCopyTiming?.results || {}).sort((a, b) => Number(a[1].elapsed_ms || 0) - Number(b[1].elapsed_ms || 0)),
    [latestCopyTiming],
  );
  const copySamples = useMemo(
    () => copyActivity.filter((row) => row.event === 'copy_completed' && Number.isFinite(Number(row.elapsed_ms))).slice(0, 16),
    [copyActivity],
  );
  const medianCopyMs = useMemo(() => {
    const values = copySamples.map((row) => Number(row.elapsed_ms || 0)).sort((a, b) => a - b);
    if (!values.length) return 0;
    const mid = Math.floor(values.length / 2);
    return values.length % 2 ? values[mid] : (values[mid - 1] + values[mid]) / 2;
  }, [copySamples]);

  const load = async (hydrateConfig = false) => {
    try {
      const [accountData, copyData] = await Promise.all([mt5MultiAccountService.accounts(), mt5MultiAccountService.copyStatus()]);
      const rows = accountData.accounts || [];
      setStatus(copyData);
      setError('');
      const configuredMaster = rows.find((row) => row.account_id === accountData.master)?.login;
      const configuredSlaves = rows.filter((row) => (accountData.slaves || []).includes(row.account_id)).map((row) => Number(row.login));
      setMaster(configuredMaster ? Number(configuredMaster) : null);
      setSlaves(configuredSlaves);
      const config = (copyData.config || null) as {
        lot_mode?: LotMode; fixed_lot?: number; multiplier?: number;
        trail_by_shoulders?: boolean; risk_reward_ratio?: number;
      } | null;
      if (hydrateConfig && !configDirty.current) {
        if (config?.lot_mode) setLotMode(config.lot_mode);
        if (config?.fixed_lot !== undefined) setFixedLot(String(config.fixed_lot));
        if (config?.multiplier !== undefined) setMultiplier(String(config.multiplier));
        setTrailByShoulders(Boolean(config?.trail_by_shoulders));
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The multi-account worker is offline.');
    }
  };

  useEffect(() => { void load(true); }, []);

  useEffect(() => {
    if (!running) return;
    let cancelled = false;
    const refreshTiming = async () => {
      try {
        const copyData = await mt5MultiAccountService.copyStatus();
        if (!cancelled) setStatus(copyData);
      } catch {
        // The normal Refresh action surfaces worker errors.
      }
    };
    const id = window.setInterval(refreshTiming, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [running]);

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
        trail_by_shoulders: trailByShoulders,
        risk_reward_ratio: 2,
        source_filter: 'all',
        poll_ms: 300,
        approval_required: true,
      });
      configDirty.current = false;
      pushToast('success', 'Copy link established', trailByShoulders
        ? 'New master trades will ask for approval; copied trades use the master SL with a 1:2 target from the slave fill.'
        : 'New master trades will ask before any slave order is submitted.');
      await load(true);
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
      await load(false);
    } catch (reason) {
      pushToast('error', 'Could not stop copy link', reason instanceof Error ? reason.message : undefined);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHeader title="Copy Trading" sub="Choose one Account Session as master and any connected sessions as slaves" actions={<button className="btn-ghost" onClick={() => void load(false)}><RefreshCw size={14} /> Refresh</button>} />

      {error ? <Panel><EmptyState icon={ArrowRightLeft} title="Copy worker unavailable" sub={error} action={<button className="btn-primary" onClick={() => void load(false)}>Retry</button>} /></Panel> : accounts.length < 2 ? (
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
              const readOnly = Boolean(account.read_only || account.access_mode === 'investor');
              return <div key={account.id} className={`rounded-xl border p-4 ${isMaster ? 'border-brand-500/45 bg-brand-500/[0.08]' : isSlave ? 'border-gain-500/35 bg-gain-500/[0.05]' : 'border-white/[0.07] bg-white/[0.03]'}`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3 min-w-0"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-white/[0.05] text-brand-300"><Landmark size={18} /></span><div className="min-w-0"><p className="font-bold text-white truncate">{account.nickname}</p><p className="mono text-[11px] text-slate-500">#{account.login} · {account.server}</p></div></div>
                  <div className="flex flex-col items-end gap-1"><Badge tone={account.status === 'connected' ? 'gain' : 'slate'}>{account.status === 'connected' ? 'CONNECTED' : 'OFFLINE'}</Badge>{readOnly && <Badge tone="slate">INVESTOR</Badge>}</div>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-2">
                  <button className={isMaster ? 'btn-primary justify-center' : 'btn-ghost justify-center'} onClick={() => chooseMaster(account.login)}>Master</button>
                  <button className={isSlave ? 'btn-primary justify-center' : 'btn-ghost justify-center'} disabled={isMaster || readOnly} title={readOnly ? 'Investor/read-only accounts can be a master, but cannot receive copied trades.' : undefined} onClick={() => toggleSlave(account.login)}>Slave</button>
                </div>
              </div>;
            })}
          </div>
        </Panel>

        <Panel className="p-5 mb-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-bold text-white flex items-center gap-2"><Gauge size={15} className="text-brand-300" /> Copy execution latency</h3>
              <p className="mt-1 text-xs text-slate-500">Real concurrent slave timing from the Copy Trader engine.</p>
            </div>
            <Badge tone={latestCopyTiming && Number(latestCopyTiming.elapsed_ms || 0) <= 250 ? 'gain' : latestCopyTiming && Number(latestCopyTiming.elapsed_ms || 0) <= 750 ? 'warn' : latestCopyTiming ? 'loss' : 'slate'}>
              {latestCopyTiming ? `${Number(latestCopyTiming.elapsed_ms || 0).toFixed(1)} MS` : 'NO SAMPLE'}
            </Badge>
          </div>
          {latestCopyTiming ? (
            <>
              <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-2 text-center">
                <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] px-2 py-3">
                  <p className="text-[9px] uppercase tracking-widest text-slate-600 font-semibold">Latest</p>
                  <p className="mono mt-1 text-lg font-extrabold text-white">{Number(latestCopyTiming.elapsed_ms || 0).toFixed(1)}<span className="ml-1 text-[10px] text-slate-500">ms</span></p>
                </div>
                <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] px-2 py-3">
                  <p className="text-[9px] uppercase tracking-widest text-slate-600 font-semibold">Median</p>
                  <p className="mono mt-1 text-lg font-extrabold text-white">{medianCopyMs.toFixed(1)}<span className="ml-1 text-[10px] text-slate-500">ms</span></p>
                </div>
                <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] px-2 py-3">
                  <p className="text-[9px] uppercase tracking-widest text-slate-600 font-semibold">Fill spread</p>
                  <p className="mono mt-1 text-lg font-extrabold text-white">{Number(latestCopyTiming.fill_spread_ms || 0).toFixed(1)}<span className="ml-1 text-[10px] text-slate-500">ms</span></p>
                </div>
                <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] px-2 py-3">
                  <p className="text-[9px] uppercase tracking-widest text-slate-600 font-semibold">Filled</p>
                  <p className="mono mt-1 text-lg font-extrabold text-white">{Number(latestCopyTiming.filled_count || 0)}/{Number(latestCopyTiming.slave_count || 0)}</p>
                </div>
              </div>
              <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2">
                {latestSlaveTimings.map(([accountId, result]) => {
                  const login = Number(accountId.replace(/^session-/, ''));
                  const label = accounts.find((account) => account.login === login)?.nickname || accountId;
                  return (
                    <div key={accountId} className="flex items-center justify-between gap-3 rounded-xl border border-white/[0.05] bg-white/[0.025] px-3 py-2.5">
                      <div className="min-w-0">
                        <p className="truncate text-[12px] font-semibold text-slate-300">{label}</p>
                        <p className="mono text-[10px] text-slate-600">{accountId}</p>
                      </div>
                      <div className="text-right">
                        <p className={`mono text-[12px] font-bold ${result.ok ? 'text-gain-400' : 'text-loss-400'}`}>{Number(result.elapsed_ms || 0).toFixed(1)} ms</p>
                        <p className="text-[9px] uppercase tracking-wider text-slate-600">{result.ok ? 'FILLED' : 'FAILED'}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="mt-4 flex h-12 items-end gap-1 rounded-xl border border-white/[0.05] bg-black/20 px-2 py-2">
                {copySamples.slice().reverse().map((sample, index, values) => {
                  const peak = Math.max(1, ...values.map((item) => Number(item.elapsed_ms || 0)));
                  const height = Math.max(8, Math.round((Number(sample.elapsed_ms || 0) / peak) * 100));
                  return <div key={`${sample.time || 0}-${index}`} title={`${Number(sample.elapsed_ms || 0).toFixed(1)} ms`} className="flex-1 rounded-sm bg-brand-500/70" style={{ height: `${height}%` }} />;
                })}
              </div>
            </>
          ) : (
            <p className="mt-4 text-xs text-slate-600">No copied-trade timing sample yet. After the next approved copy, KOOLKID will show total execution time, each slave's ms, and the fill spread between slaves.</p>
          )}
        </Panel>

        <Panel className="p-5">
          <div className="flex items-center justify-between gap-3"><div><h3 className="text-sm font-bold text-white">Copy Link</h3><p className="mt-1 text-xs text-slate-500">Slave execution always waits for your confirmation popup.</p></div><Link2 size={19} className={running ? 'text-gain-400' : 'text-slate-600'} /></div>
          <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
            <div><label className="label">Lot mode</label><select className="input" value={lotMode} onChange={(event) => { configDirty.current = true; setLotMode(event.target.value as LotMode); }}><option value="same">Same as master</option><option value="fixed">Fixed lot</option><option value="multiplier">Multiplier</option><option value="equity_proportional">Equity proportional</option></select></div>
            {lotMode === 'fixed' && <div><label className="label">Fixed slave lot</label><NumberStepper value={fixedLot} onChange={(value) => { configDirty.current = true; setFixedLot(value); }} min={0.01} max={100} step={0.01} decimals={2} /></div>}
            {lotMode === 'multiplier' && <div><label className="label">Lot multiplier</label><NumberStepper value={multiplier} onChange={(value) => { configDirty.current = true; setMultiplier(value); }} min={0.01} max={100} step={0.01} decimals={2} /></div>}
            <div className="flex items-end gap-2"><button className="btn-primary flex-1 justify-center" disabled={busy} onClick={establish}>{busy ? <Spinner size={14} /> : <Link2 size={14} />} Establish Link</button>{running && <button className="btn-danger justify-center" disabled={busy} onClick={stop}>Stop</button>}</div>
            <div className="md:col-span-3 flex items-start justify-between gap-4 rounded-xl border border-white/[0.07] bg-white/[0.025] px-4 py-3">
              <div>
                <p className="text-[13px] font-semibold text-slate-200">Trail by Shoulders · 1:2</p>
                <p className="mt-1 text-[11px] leading-relaxed text-slate-500">Use the master trade's protective stop as the copied risk boundary and set each slave's target at 2R from its actual fill. Master SL changes still trail the copy; master TP changes do not replace the 2R target.</p>
              </div>
              <Toggle on={trailByShoulders} onChange={(value) => { configDirty.current = true; setTrailByShoulders(value); }} />
            </div>
          </div>
          <p className="mt-4 flex items-start gap-2 rounded-xl border border-warn-400/20 bg-warn-400/[0.06] px-4 py-3 text-[11px] leading-relaxed text-slate-400"><ShieldCheck size={14} className="mt-0.5 shrink-0 text-warn-400" />Manual, KOOLKID, Auto Trade and EA positions detected on the master create an approval popup before slave orders. The master position itself is never delayed or changed by Copy Trading.</p>
        </Panel>
      </>}
    </div>
  );
}
