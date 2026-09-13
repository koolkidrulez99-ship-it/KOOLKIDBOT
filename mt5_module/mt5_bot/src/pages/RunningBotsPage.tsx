import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Cpu, Pause, Play, RefreshCw, Settings2, Square, Timer, Zap } from 'lucide-react';
import { useHub } from '../context/HubContext';
import { fmtSigned, profitTone, uptimeSince } from '../lib/format';
import { Badge, EmptyState, PageHeader, Panel, StatCard } from '../components/ui';
import BotConfigModal from '../components/BotConfigModal';
import { botControl } from '../lib/actions';
import { isSimulation } from '../config/runtime';
import type { Mt5Bot } from '../types';

export default function RunningBotsPage() {
  const { accounts, bots, bridge, accountName, botLiveToday, pushToast, refresh } = useHub();
  const eaLaunchAvailable = isSimulation || bridge?.capabilities?.ea_launch === true;
  const pauseAvailable = isSimulation || bridge?.ea_worker?.capabilities?.pause === true;
  const [configBot, setConfigBot] = useState<Mt5Bot | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const active = useMemo(() => bots.filter((b) => b.status !== 'stopped'), [bots]);
  const running = active.filter((b) => b.status === 'running');
  const combined = running.reduce((s, b) => s + botLiveToday(b), 0);
  const lifetime = active.reduce((s, b) => s + Number(b.net_profit || 0), 0);

  const cmd = async (b: Mt5Bot, action: 'pause' | 'resume' | 'stop' | 'restart') => {
    setBusyId(b.id);
    try {
      if (action === 'restart') {
        const account = accounts.find((row) => row.login === b.account_login);
        if (account?.account_type === 'live') throw new Error('Open Bot Library to reconfirm LIVE execution before restarting this EA.');
        await botControl(b.id, 'stop');
        await botControl(b.id, 'launch', { account_login: b.account_login, symbol: b.symbol, timeframe: b.timeframe, lot_size: b.lot_size, settings: b.settings });
      } else {
        await botControl(b.id, action);
      }
      pushToast(
        action === 'stop' ? 'info' : 'success',
        `${b.name} ${action === 'stop' ? 'stopped' : action === 'pause' ? 'paused' : action === 'restart' ? 'restarted' : 'resumed'}`,
        action === 'stop' ? 'Engine halted; open tickets remain untouched.' : undefined
      );
      await refresh(true);
    } catch (e) {
      pushToast('error', 'Command failed', e instanceof Error ? e.message : undefined);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div>
      <PageHeader title="Running Bots" sub={isSimulation ? 'Simulation bot control room · no .ex5 process is running' : eaLaunchAvailable ? 'MT5 worker control room · stop assigned EAs without closing positions' : 'EA Worker Offline · start the local system with START_KOOLKID.bat'} />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-5">
        <StatCard label="Engines Running" value={running.length} icon={Zap} tone="brand" sub={`${active.filter((b) => b.status === 'paused').length} paused`} />
        <StatCard label={isSimulation ? "Session P/L (sim)" : "Session P/L (live)"} value={fmtSigned(combined)} icon={Timer} tone={combined >= 0 ? 'gain' : 'loss'} sub="Across running engines" />
        <StatCard label="Lifetime Net (active set)" value={fmtSigned(lifetime, 0)} icon={Cpu} tone={lifetime >= 0 ? 'gain' : 'loss'} sub={`${active.reduce((s, b) => s + b.total_trades, 0)} lifetime fills`} />
      </div>

      {active.length === 0 ? (
        <Panel>
          <EmptyState
            icon={Cpu}
            title="No bots currently running"
            sub={isSimulation ? 'Start a bot simulation from the library and it will appear here.' : eaLaunchAvailable ? 'Deploy an EA from the library and it will appear here with worker controls.' : 'Configure your EA assignments in the Bot Library. Automatic .ex5 launch controls will activate after the isolated EA worker is added.'}
            action={
              <Link to="/mt5/bots" className="btn-primary">
                <Zap size={14} /> Open Bot Library
              </Link>
            }
          />
        </Panel>
      ) : (
        <div className="space-y-3">
          {active.map((b) => {
            const runningNow = b.status === 'running';
            const pausedNow = b.status === 'paused';
            const today = botLiveToday(b);
            return (
              <Panel key={b.id} hover className="p-4 md:p-5">
                <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
                  <span
                    className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl border ${
                      runningNow ? 'bg-gain-500/10 border-gain-500/25 text-gain-400' : 'bg-warn-400/10 border-warn-400/25 text-warn-400'
                    }`}
                  >
                    <Cpu size={19} className={runningNow ? 'animate-pulse' : ''} />
                  </span>

                  <div className="min-w-0 flex-1 basis-48">
                    <div className="flex items-center gap-2">
                      <p className="text-[15px] font-bold text-white truncate">{b.name}</p>
                      <Badge tone={runningNow ? 'gain' : 'warn'}>{b.status}</Badge>
                    </div>
                    <p className="text-[11px] text-slate-500 mt-0.5">
                      {b.symbol} &middot; {b.timeframe} &middot; {b.lot_size.toFixed(2)} lots &middot; on <span className="text-slate-300">{accountName(b.account_login)}</span>
                    </p>
                    <p className="text-[10px] text-slate-600 mt-1">Terminal: <span className={b.terminal_status === 'online' ? 'text-gain-400' : 'text-loss-400'}>{b.terminal_status || 'unknown'}</span>{b.last_activity ? ` · last activity ${new Date(b.last_activity).toLocaleString()}` : ''}</p>
                    <p className="text-[10px] text-slate-600 mt-1">Open positions: <span className="text-slate-300">{b.open_positions ?? 0}</span> · Current P/L: <span className={profitTone(Number(b.current_pl || 0))}>{fmtSigned(Number(b.current_pl || 0))}</span> · Today: <span className={profitTone(Number(b.today_pl || 0))}>{fmtSigned(Number(b.today_pl || 0))}</span></p>
                    {b.last_error && <p className="mt-1 text-[10px] text-loss-400">{b.last_error}</p>}
                  </div>

                  <div className="hidden md:block">
                    <p className="text-[9px] uppercase tracking-widest text-slate-600 font-semibold">Session P/L</p>
                    <p className={`mono text-lg font-bold ${profitTone(today)}`}>{fmtSigned(today)}</p>
                  </div>
                  <div className="hidden md:block">
                    <p className="text-[9px] uppercase tracking-widest text-slate-600 font-semibold">Uptime</p>
                    <p className="mono text-sm font-bold text-slate-200">{uptimeSince(b.started_at)}</p>
                  </div>
                  <div className="hidden lg:block">
                    <p className="text-[9px] uppercase tracking-widest text-slate-600 font-semibold">Win rate</p>
                    <p className="mono text-sm font-bold text-slate-200">{b.win_rate.toFixed(1)}%</p>
                  </div>
                  <div className="hidden lg:block">
                    <p className="text-[9px] uppercase tracking-widest text-slate-600 font-semibold">Risk / trade</p>
                    <p className="mono text-sm font-bold text-slate-200">{b.settings?.risk_percent ?? 2}%</p>
                  </div>

                  <div className="flex items-center gap-1.5 ml-auto">
                    {runningNow ? (
                      <button className="btn-warn !px-3 !py-2 text-xs" title={pauseAvailable ? 'Pause bot' : 'This EA does not expose a safe pause control'} disabled={busyId === b.id || !pauseAvailable} onClick={() => cmd(b, 'pause')}>
                        <Pause size={13} /> Pause
                      </button>
                    ) : pausedNow ? (
                      <button className="btn-success !px-3 !py-2 text-xs" disabled={busyId === b.id} onClick={() => cmd(b, 'resume')}>
                        <Play size={13} /> Resume
                      </button>
                    ) : null}
                    <button className="btn-danger !px-3 !py-2 text-xs" disabled={busyId === b.id} onClick={() => cmd(b, 'stop')}>
                      <Square size={12} /> Stop
                    </button>
                    <button className="btn-ghost !px-3 !py-2 text-xs" disabled={busyId === b.id} onClick={() => cmd(b, 'restart')}>
                      <RefreshCw size={13} /> Restart
                    </button>
                    <button className="btn-icon" title="Edit settings" onClick={() => setConfigBot(b)}>
                      <Settings2 size={15} />
                    </button>
                  </div>
                </div>
              </Panel>
            );
          })}
        </div>
      )}

      <BotConfigModal bot={configBot} open={configBot !== null} onClose={() => setConfigBot(null)} />
    </div>
  );
}
