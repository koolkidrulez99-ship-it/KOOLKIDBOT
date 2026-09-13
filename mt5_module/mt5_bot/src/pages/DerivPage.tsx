import { useEffect, useState } from 'react';
import { Check, Hexagon, RefreshCw, Workflow } from 'lucide-react';
import { useHub } from '../context/HubContext';
import { fmtUSD } from '../lib/format';
import { Badge, EmptyState, PageHeader, Panel, Skel, StatusDot } from '../components/ui';
import type { DerivAccount } from '../types';
import { derivMarketService } from '../services/derivMarketService';
import { isSimulation } from '../config/runtime';

export default function DerivPage() {
  const { pushToast } = useHub();
  const [rows, setRows] = useState<DerivAccount[] | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = () => {
    derivMarketService.accounts()
      .then(setRows)
      .catch((e) => {
        setRows([]);
        pushToast('error', 'Deriv module unavailable', e instanceof Error ? e.message : undefined);
      });
  };

  useEffect(load, []); // eslint-disable-line react-hooks/exhaustive-deps

  const setActive = async (a: DerivAccount) => {
    setBusyId(a.id);
    try {
      await derivMarketService.setActiveAccount(a.id);
      pushToast('success', `${a.nickname} selected`, 'Deriv console will target this account.');
      load();
    } catch (e) {
      pushToast('error', 'Switch failed', e instanceof Error ? e.message : undefined);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="Deriv · Core Bots"
        sub="The original automation module - MT5 Hub ships alongside it"
        actions={
          <button className="btn-ghost" onClick={load}>
            <RefreshCw size={14} /> Refresh
          </button>
        }
      />

      {rows === null ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {Array.from({ length: 2 }).map((_, i) => (
            <Skel key={i} className="h-44" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <Panel>
          <EmptyState icon={Hexagon} title="No Deriv accounts linked" sub="Deriv API accounts appear here once connected in the core module." />
        </Panel>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {rows.map((a) => (
            <Panel key={a.id} hover className="p-5">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <span className="grid h-11 w-11 place-items-center rounded-xl bg-warn-400/10 border border-warn-400/30 text-warn-400">
                    <Hexagon size={19} />
                  </span>
                  <div>
                    <p className="text-[15px] font-bold text-white">{a.nickname}</p>
                    <p className="mono text-[11px] text-slate-500">{a.login}</p>
                  </div>
                </div>
                <Badge tone={a.account_type === 'live' ? 'loss' : 'warn'}>{a.account_type}</Badge>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3">
                <div className="rounded-xl bg-black/25 border border-white/[0.06] p-3">
                  <p className="text-[9px] uppercase tracking-widest text-slate-600 font-semibold">Balance</p>
                  <p className="mono text-lg font-bold text-white mt-0.5">{fmtUSD(Number(a.balance))}</p>
                </div>
                <div className="rounded-xl bg-black/25 border border-white/[0.06] p-3">
                  <p className="text-[9px] uppercase tracking-widest text-slate-600 font-semibold">Platform</p>
                  <p className="text-[12px] font-semibold text-slate-200 mt-1">{a.platform}</p>
                </div>
              </div>
              <div className="mt-4 flex items-center gap-2">
                {a.is_active ? (
                  <span className="btn-ghost flex-1 !cursor-default opacity-70">
                    <Check size={14} className="text-gain-400" /> Active console account
                  </span>
                ) : (
                  <button className="btn-ghost flex-1" disabled={busyId === a.id} onClick={() => setActive(a)}>
                    Set Active
                  </button>
                )}
                <span className="chip">
                  <StatusDot status={a.status} /> {a.status}
                </span>
              </div>
            </Panel>
          ))}
        </div>
      )}

      <Panel className="mt-4 p-6">
        <div className="flex items-center gap-2.5">
          <Workflow size={16} className="text-warn-400" />
          <h3 className="text-base font-bold text-white">Core engine status</h3>
          <Badge tone={isSimulation ? 'warn' : 'gain'}>{isSimulation ? 'Not connected here' : 'Core connected'}</Badge>
        </div>
        <p className="mt-2 text-xs text-slate-500 leading-relaxed max-w-2xl">
          This standalone page is only an integration boundary for your existing Deriv system. Account authentication,
          market data and Deriv trade execution remain owned by the existing Deriv code path. MT5 Hub adds a separate
          MetaTrader 5 workspace without changing that execution path.
        </p>
        <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            ['Deriv account service', isSimulation ? 'disconnected' : 'connected'],
            ['Deriv market data service', isSimulation ? 'disconnected' : 'connected'],
            ['Deriv trading engine', isSimulation ? 'disconnected' : 'connected'],
            ['MT5 integration boundary', 'ready'],
          ].map(([name, status]) => (
            <div key={name} className="rounded-xl bg-white/[0.03] border border-white/[0.06] px-3.5 py-3 flex items-center gap-2.5">
              <StatusDot status={status} />
              <div className="min-w-0">
                <p className="text-[12px] font-semibold text-slate-200 truncate">{name}</p>
                <p className="text-[10px] text-slate-600 capitalize">{status}</p>
              </div>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
