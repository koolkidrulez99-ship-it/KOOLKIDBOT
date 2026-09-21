import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowRightLeft, Gauge, Landmark, Link2, RefreshCw, ShieldCheck, Users } from 'lucide-react';
import { Badge, EmptyState, PageHeader, Panel, Spinner, Toggle } from '../components/ui';
import { useHub } from '../context/HubContext';
import NumberStepper from '../components/NumberStepper';
import { mt5MultiAccountService } from '../services/mt5MultiAccountService';

type LotMode = 'same' | 'fixed' | 'multiplier' | 'equity_proportional';
type GroupId = '1' | '2';

interface CopyTimingActivity {
  time?: number;
  event?: string;
  group_id?: GroupId;
  master_ticket?: string | number;
  elapsed_ms?: number;
  fill_spread_ms?: number;
  slave_count?: number;
  filled_count?: number;
  results?: Record<string, { ok?: boolean; elapsed_ms?: number; error?: string }>;
}

interface GroupSnapshot {
  group_id?: GroupId;
  status?: string;
  config?: Record<string, unknown> | null;
  preferences?: Record<string, unknown>;
  pending_count?: number;
  copy_map?: Record<string, unknown>;
  activity?: CopyTimingActivity[];
}

interface CopyStatus {
  status?: string;
  groups?: Record<GroupId, GroupSnapshot>;
  activity?: CopyTimingActivity[];
  copy_anywhere_groups?: GroupId[];
}

interface GroupForm {
  master: number | null;
  slaves: number[];
  lotMode: LotMode;
  fixedLot: string;
  multiplier: string;
  trailByShoulders: boolean;
  limitCopiedTrades: boolean;
  maxCopiedTrades: string;
}

const blankGroup = (): GroupForm => ({
  master: null,
  slaves: [],
  lotMode: 'same',
  fixedLot: '0.01',
  multiplier: '1.00',
  trailByShoulders: false,
  limitCopiedTrades: false,
  maxCopiedTrades: '1',
});

function groupConfig(snapshot?: GroupSnapshot | null) {
  return (snapshot?.config || snapshot?.preferences || {}) as {
    lot_mode?: LotMode;
    fixed_lot?: number;
    multiplier?: number;
    trail_by_shoulders?: boolean;
    limit_copied_trades?: boolean;
    max_copied_trades_per_slave?: number;
    master_account_id?: string;
    slave_account_ids?: string[];
  };
}

export default function CopyTradingPage() {
  const { accounts, pushToast } = useHub();
  const [status, setStatus] = useState<CopyStatus | null>(null);
  const [error, setError] = useState('');
  const [busyGroup, setBusyGroup] = useState<GroupId | null>(null);
  const [groups, setGroups] = useState<Record<GroupId, GroupForm>>({ '1': blankGroup(), '2': blankGroup() });
  const configDirty = useRef<Record<GroupId, boolean>>({ '1': false, '2': false });

  const workerByLogin = useMemo(() => new Map(accounts.map((account) => [account.login, {
    account_id: `session-${account.login}`,
    login: account.login,
    connected: account.status === 'connected',
  }])), [accounts]);

  const setGroup = (groupId: GroupId, patch: Partial<GroupForm>) => {
    setGroups((current) => ({ ...current, [groupId]: { ...current[groupId], ...patch } }));
  };

  const load = async (hydrateConfig = false) => {
    try {
      const [accountData, copyDataRaw] = await Promise.all([
        mt5MultiAccountService.accounts(),
        mt5MultiAccountService.copyStatus(),
      ]);
      const copyData = copyDataRaw as CopyStatus;
      setStatus(copyData);
      setError('');
      const accountGroups = accountData.groups;
      for (const groupId of ['1', '2'] as GroupId[]) {
        const groupSnapshot = copyData.groups?.[groupId];
        const config = groupConfig(groupSnapshot);
        const savedGroup = accountGroups?.[groupId];
        const masterId = savedGroup?.master || config.master_account_id || (groupId === '1' ? accountData.master : null);
        const slaveIds = savedGroup?.slaves || config.slave_account_ids || (groupId === '1' ? accountData.slaves : []);
        const masterLogin = accountData.accounts.find((row) => row.account_id === masterId)?.login ?? null;
        const slaveLogins = accountData.accounts.filter((row) => slaveIds.includes(row.account_id)).map((row) => Number(row.login));

        setGroups((current) => {
          const next = { ...current[groupId], master: masterLogin ? Number(masterLogin) : null, slaves: slaveLogins };
          if (hydrateConfig && !configDirty.current[groupId]) {
            if (config.lot_mode) next.lotMode = config.lot_mode;
            if (config.fixed_lot !== undefined) next.fixedLot = String(config.fixed_lot);
            if (config.multiplier !== undefined) next.multiplier = String(config.multiplier);
            next.trailByShoulders = Boolean(config.trail_by_shoulders);
            next.limitCopiedTrades = Boolean(config.limit_copied_trades);
            if (config.max_copied_trades_per_slave !== undefined) next.maxCopiedTrades = String(config.max_copied_trades_per_slave);
          }
          return { ...current, [groupId]: next };
        });
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The multi-account worker is offline.');
    }
  };

  const savePreference = (groupId: GroupId, patch: Record<string, unknown>) => {
    configDirty.current[groupId] = true;
    void mt5MultiAccountService.saveCopyPreferences(groupId, patch).catch((reason) => {
      pushToast('error', `Could not save Master Group ${groupId} setting`, reason instanceof Error ? reason.message : undefined);
    });
  };

  useEffect(() => { void load(true); }, []);

  useEffect(() => {
    if (!status || !Object.values(status.groups || {}).some((group) => group?.status === 'running')) return;
    let cancelled = false;
    const refreshStatus = async () => {
      try {
        const next = await mt5MultiAccountService.copyStatus() as CopyStatus;
        if (!cancelled) setStatus(next);
      } catch { /* normal Refresh surfaces worker errors */ }
    };
    const id = window.setInterval(refreshStatus, 1500);
    return () => { cancelled = true; window.clearInterval(id); };
  }, [status?.groups?.['1']?.status, status?.groups?.['2']?.status]);

  const chooseMaster = (groupId: GroupId, login: number) => {
    const otherId: GroupId = groupId === '1' ? '2' : '1';
    if (groups[otherId].master === login) {
      pushToast('error', 'Master already used', 'The same account cannot be Master in both groups.');
      return;
    }
    setGroup(groupId, { master: login, slaves: groups[groupId].slaves.filter((value) => value !== login) });
  };

  const toggleSlave = (groupId: GroupId, login: number) => {
    const group = groups[groupId];
    if (login === group.master) return;
    setGroup(groupId, {
      slaves: group.slaves.includes(login)
        ? group.slaves.filter((value) => value !== login)
        : [...group.slaves, login],
    });
  };

  const establish = async (groupId: GroupId) => {
    const group = groups[groupId];
    if (!group.master) { pushToast('error', `Choose Master ${groupId}`); return; }
    if (!group.slaves.length) { pushToast('error', `Choose at least one slave for Master ${groupId}`); return; }
    const otherId: GroupId = groupId === '1' ? '2' : '1';
    if (groups[otherId].master === group.master) {
      pushToast('error', 'Duplicate master blocked', 'Master Group 1 and Master Group 2 must use different accounts.');
      return;
    }
    const selected = [group.master, ...group.slaves];
    const missing = selected.filter((login) => !workerByLogin.get(login)?.connected);
    if (missing.length) {
      pushToast('error', 'Connect selected accounts first', missing.map((login) => accounts.find((account) => account.login === login)?.nickname || `#${login}`).join(' · '));
      return;
    }
    const masterWorker = workerByLogin.get(group.master)!;
    const slaveWorkers = group.slaves.map((login) => workerByLogin.get(login)!).filter(Boolean);
    setBusyGroup(groupId);
    try {
      await mt5MultiAccountService.startCopy({
        group_id: groupId,
        master_account_id: masterWorker.account_id,
        slave_account_ids: slaveWorkers.map((worker) => worker.account_id),
        lot_mode: group.lotMode,
        fixed_lot: Math.max(0.01, Number(group.fixedLot) || 0.01),
        multiplier: Math.max(0.01, Number(group.multiplier) || 1),
        trail_by_shoulders: group.trailByShoulders,
        risk_reward_ratio: 2,
        shoulder_timeframe: 'M5',
        shoulder_strength: 2,
        shoulder_buffer_points: 5,
        limit_copied_trades: group.limitCopiedTrades,
        max_copied_trades_per_slave: Math.max(1, Math.min(100, Number(group.maxCopiedTrades) || 1)),
        source_filter: 'all',
        poll_ms: 300,
        approval_required: true,
      });
      configDirty.current[groupId] = false;
      pushToast('success', `Master Group ${groupId} set`, `${group.slaves.length} slave account${group.slaves.length === 1 ? '' : 's'} linked. New trades use the normal approval popup.`);
      await load(true);
    } catch (reason) {
      pushToast('error', `Could not set Master Group ${groupId}`, reason instanceof Error ? reason.message : undefined);
    } finally {
      setBusyGroup(null);
    }
  };

  const stop = async (groupId: GroupId) => {
    setBusyGroup(groupId);
    try {
      await mt5MultiAccountService.stopCopy(groupId);
      pushToast('info', `Master Group ${groupId} stopped`, 'Existing positions were left untouched.');
      setGroup(groupId, blankGroup());
      await load(false);
    } catch (reason) {
      pushToast('error', `Could not stop Master Group ${groupId}`, reason instanceof Error ? reason.message : undefined);
    } finally {
      setBusyGroup(null);
    }
  };

  const activity = useMemo(() => Array.isArray(status?.activity) ? status!.activity! : [], [status]);
  const samples = useMemo(() => activity.filter((row) => row.event === 'copy_completed' && Number.isFinite(Number(row.elapsed_ms))).slice(0, 16), [activity]);
  const latest = samples[0] || null;
  const median = useMemo(() => {
    const values = samples.map((row) => Number(row.elapsed_ms || 0)).sort((a, b) => a - b);
    if (!values.length) return 0;
    const mid = Math.floor(values.length / 2);
    return values.length % 2 ? values[mid] : (values[mid - 1] + values[mid]) / 2;
  }, [samples]);

  const renderGroup = (groupId: GroupId) => {
    const group = groups[groupId];
    const snapshot = status?.groups?.[groupId];
    const running = snapshot?.status === 'running';
    const autoAnywhere = snapshot?.config?.approval_required === false;
    const otherMaster = groups[groupId === '1' ? '2' : '1'].master;

    return (
      <Panel className="p-5 border border-brand-500/20">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold text-white">Master Group {groupId}</h3>
            <p className="mt-1 text-xs text-slate-500">One master with its own slaves, settings, mappings and close tracking.</p>
          </div>
          <div className="flex gap-2">
            {autoAnywhere && <Badge tone="gain">FROM ANYWHERE</Badge>}
            <Badge tone={running ? 'gain' : group.master ? 'warn' : 'slate'}>{running ? 'ACTIVE' : group.master ? 'SAVED' : 'NOT SET'}</Badge>
          </div>
        </div>

        <div className="mt-4">
          <label className="label">Master account</label>
          <select className="input" value={group.master || ''} onChange={(event) => chooseMaster(groupId, Number(event.target.value))}>
            <option value="">Choose master</option>
            {accounts.map((account) => (
              <option key={account.login} value={account.login} disabled={otherMaster === account.login}>
                {account.nickname} · #{account.login}{otherMaster === account.login ? ' · used by other master' : ''}
              </option>
            ))}
          </select>
        </div>

        <div className="mt-4">
          <label className="label">Slave accounts</label>
          <p className="mb-2 text-[10px] text-slate-600">A slave may belong to both master groups.</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {accounts.map((account) => {
              const selected = group.slaves.includes(account.login);
              const readOnly = Boolean(account.read_only || account.access_mode === 'investor');
              const blocked = group.master === account.login || readOnly;
              return (
                <button
                  key={account.login}
                  type="button"
                  disabled={blocked}
                  onClick={() => toggleSlave(groupId, account.login)}
                  className={`rounded-xl border px-3 py-3 text-left transition ${selected ? 'border-gain-500/40 bg-gain-500/[0.07]' : 'border-white/[0.07] bg-white/[0.025]'} ${blocked ? 'opacity-45' : 'hover:border-brand-400/30'}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-xs font-semibold text-slate-200">{account.nickname}</span>
                    {selected && <Badge tone="gain">SLAVE</Badge>}
                  </div>
                  <p className="mono mt-1 text-[10px] text-slate-600">#{account.login} · {account.status}</p>
                </button>
              );
            })}
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className="label">Lot mode</label>
            <select className="input" value={group.lotMode} onChange={(event) => {
              const value = event.target.value as LotMode;
              setGroup(groupId, { lotMode: value });
              savePreference(groupId, { lot_mode: value });
            }}>
              <option value="same">Same as master</option>
              <option value="fixed">Fixed lot</option>
              <option value="multiplier">Multiplier</option>
              <option value="equity_proportional">Equity proportional</option>
            </select>
          </div>
          {group.lotMode === 'fixed' && (
            <div><label className="label">Fixed slave lot</label><NumberStepper value={group.fixedLot} onChange={(value) => {
              setGroup(groupId, { fixedLot: value });
              savePreference(groupId, { fixed_lot: Math.max(0.01, Number(value) || 0.01) });
            }} min={0.01} max={100} step={0.01} decimals={2} /></div>
          )}
          {group.lotMode === 'multiplier' && (
            <div><label className="label">Lot multiplier</label><NumberStepper value={group.multiplier} onChange={(value) => {
              setGroup(groupId, { multiplier: value });
              savePreference(groupId, { multiplier: Math.max(0.01, Number(value) || 1) });
            }} min={0.01} max={100} step={0.01} decimals={2} /></div>
          )}
        </div>

        <div className="mt-4 flex items-start justify-between gap-4 rounded-xl border border-white/[0.07] bg-white/[0.025] px-4 py-3">
          <div>
            <p className="text-[13px] font-semibold text-slate-200">Trail by Shoulders · 1:2</p>
            <p className="mt-1 text-[11px] leading-relaxed text-slate-500">Confirmed M5 market-structure shoulders; stop only ratchets toward protection.</p>
          </div>
          <Toggle on={group.trailByShoulders} onChange={(value) => {
            setGroup(groupId, { trailByShoulders: value });
            savePreference(groupId, { trail_by_shoulders: value });
          }} />
        </div>

        <div className="mt-3 rounded-xl border border-white/[0.07] bg-white/[0.025] px-4 py-3">
          <div className="flex items-start justify-between gap-4">
            <div><p className="text-[13px] font-semibold text-slate-200">Limit copied trades per slave</p><p className="mt-1 text-[11px] text-slate-500">This limit is independent for this master group.</p></div>
            <Toggle on={group.limitCopiedTrades} onChange={(value) => {
              setGroup(groupId, { limitCopiedTrades: value });
              savePreference(groupId, { limit_copied_trades: value });
            }} />
          </div>
          {group.limitCopiedTrades && (
            <div className="mt-3 max-w-xs">
              <label className="label">Maximum open copied trades</label>
              <NumberStepper value={group.maxCopiedTrades} onChange={(value) => {
                const next = String(Math.max(1, Math.min(100, Number(value) || 1)));
                setGroup(groupId, { maxCopiedTrades: next });
                savePreference(groupId, { max_copied_trades_per_slave: Number(next) });
              }} min={1} max={100} step={1} decimals={0} />
            </div>
          )}
        </div>

        <div className="mt-4 flex gap-2">
          <button className="btn-primary flex-1 justify-center" disabled={busyGroup !== null} onClick={() => void establish(groupId)}>
            {busyGroup === groupId ? <Spinner size={14} /> : <Link2 size={14} />} Set Master Group {groupId}
          </button>
          {(running || group.master) && <button className="btn-danger justify-center" disabled={busyGroup !== null} onClick={() => void stop(groupId)}>Stop</button>}
        </div>
      </Panel>
    );
  };

  return (
    <div>
      <PageHeader
        title="Copy Trading"
        sub="Up to two independent master groups · a slave may follow both masters"
        actions={<button className="btn-ghost" onClick={() => void load(false)}><RefreshCw size={14} /> Refresh</button>}
      />

      {error ? (
        <Panel><EmptyState icon={ArrowRightLeft} title="Copy worker unavailable" sub={error} action={<button className="btn-primary" onClick={() => void load(false)}>Retry</button>} /></Panel>
      ) : accounts.length < 2 ? (
        <Panel><EmptyState icon={Users} title="Two Account Sessions are required" sub="Add another account from MT5 Accounts, then return here to choose master and slave roles." /></Panel>
      ) : (
        <>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mb-5">
            {renderGroup('1')}
            {renderGroup('2')}
          </div>

          <Panel className="p-5 mb-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-bold text-white flex items-center gap-2"><Gauge size={15} className="text-brand-300" /> Copy execution latency</h3>
                <p className="mt-1 text-xs text-slate-500">Combined timing samples from both independent master groups.</p>
              </div>
              <Badge tone={latest && Number(latest.elapsed_ms || 0) <= 250 ? 'gain' : latest ? 'warn' : 'slate'}>
                {latest ? `${Number(latest.elapsed_ms || 0).toFixed(1)} MS · G${latest.group_id || '1'}` : 'NO SAMPLE'}
              </Badge>
            </div>
            {latest ? (
              <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-2 text-center">
                <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] px-2 py-3"><p className="text-[9px] uppercase tracking-widest text-slate-600">Latest</p><p className="mono mt-1 text-lg font-extrabold text-white">{Number(latest.elapsed_ms || 0).toFixed(1)} ms</p></div>
                <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] px-2 py-3"><p className="text-[9px] uppercase tracking-widest text-slate-600">Median</p><p className="mono mt-1 text-lg font-extrabold text-white">{median.toFixed(1)} ms</p></div>
                <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] px-2 py-3"><p className="text-[9px] uppercase tracking-widest text-slate-600">Fill spread</p><p className="mono mt-1 text-lg font-extrabold text-white">{Number(latest.fill_spread_ms || 0).toFixed(1)} ms</p></div>
                <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] px-2 py-3"><p className="text-[9px] uppercase tracking-widest text-slate-600">Filled</p><p className="mono mt-1 text-lg font-extrabold text-white">{Number(latest.filled_count || 0)}/{Number(latest.slave_count || 0)}</p></div>
              </div>
            ) : <p className="mt-4 text-xs text-slate-600">No copied-trade timing sample yet.</p>}
          </Panel>

          <p className="flex items-start gap-2 rounded-xl border border-warn-400/20 bg-warn-400/[0.06] px-4 py-3 text-[11px] leading-relaxed text-slate-400">
            <ShieldCheck size={14} className="mt-0.5 shrink-0 text-warn-400" />
            Each master group is isolated. The same slave can follow both groups, but the same account cannot be Master in both groups. Master closes only close copies mapped to that master group.
          </p>
        </>
      )}
    </div>
  );
}
