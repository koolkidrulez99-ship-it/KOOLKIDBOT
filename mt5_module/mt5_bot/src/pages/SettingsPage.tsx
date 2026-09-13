import { DatabaseBackup, FileDown, RefreshCw, Server, ShieldCheck, Timer, Moon, Sun } from 'lucide-react';
import { useHub } from '../context/HubContext';
import { PageHeader, Panel, Toggle, Badge, StatusDot } from '../components/ui';
import { isSimulation } from '../config/runtime';
import { mt5HistoryService } from '../services/mt5HistoryService';
import { simReset } from '../services/simulationStore';
import { useTheme } from '../hooks/useTheme';

const POLL_OPTIONS = [
  { label: '3 seconds', value: 3000 },
  { label: '5 seconds', value: 5000 },
  { label: '15 seconds', value: 15000 },
  { label: '30 seconds', value: 30000 },
  { label: '60 seconds', value: 60000 },
  { label: '2 minutes', value: 120000 },
];

export default function SettingsPage() {
  const { prefs, setPrefs, accounts, bridge, pushToast, refresh } = useHub();
  const { theme, setTheme } = useTheme();

  const exportAll = async () => {
    try {
      const rows = await mt5HistoryService.list();
      const head = 'ticket,close_time,account,symbol,type,volume,open_price,close_price,gross_profit,swap,commission,net_pl,source';
      const lines = rows.map((r) =>
        [r.ticket, r.close_time, r.account_login, r.symbol, r.type, r.volume, r.open_price, r.close_price, r.profit, r.swap, r.commission, r.net_pl ?? (Number(r.profit) + Number(r.swap || 0) + Number(r.commission || 0)), `"${r.source}"`].join(',')
      );
      const blob = new Blob([[head, ...lines].join('\n')], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'mt5-hub-history-full.csv';
      a.click();
      URL.revokeObjectURL(url);
      pushToast('success', 'Export ready', `${rows.length} records downloaded as CSV.`);
    } catch (e) {
      pushToast('error', 'Export failed', e instanceof Error ? e.message : 'History service unavailable.');
    }
  };

  const resetSimulation = async () => {
    if (!isSimulation) return;
    await simReset();
    pushToast('info', 'Simulation reset', 'Local demo accounts, positions, history and settings were returned to defaults.');
    await refresh();
  };

  return (
    <div>
      <PageHeader title="Settings" sub="Hub behaviour, runtime connectivity and data tools" />

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Panel className="p-6">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <Timer size={15} className="text-brand-300" /> Behaviour
          </h3>
          <div className="mt-5 space-y-5">
            <div>
              <label className="label">Data refresh interval</label>
              <div className="flex flex-wrap gap-1.5">
                {POLL_OPTIONS.map((o) => (
                  <button
                    key={o.value}
                    onClick={() => {
                      setPrefs({ pollMs: o.value });
                      pushToast('info', 'Refresh interval updated', `Hub refresh every ${o.label}.`);
                    }}
                    className={`rounded-lg px-3 py-1.5 text-xs font-bold cursor-pointer transition-colors ${
                      prefs.pollMs === o.value ? 'bg-brand-600 text-white' : 'bg-white/[0.05] text-slate-400 hover:text-white'
                    }`}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
              <p className="mt-1.5 text-[11px] text-slate-600">
                {isSimulation ? 'Simulation market motion updates separately every 2 seconds.' : 'The bridge may also push faster terminal updates independently.'}
              </p>
            </div>

            <div className="flex items-start justify-between gap-4 rounded-xl bg-white/[0.03] border border-white/[0.06] p-4">
              <div>
                <p className="text-[13px] font-semibold text-slate-200">Require confirmation for emergency actions</p>
                <p className="text-[11px] text-slate-500 mt-0.5">Stop-all and close-all require an explicit confirmation when enabled.</p>
              </div>
              <Toggle on={prefs.confirmDanger} onChange={(v) => setPrefs({ confirmDanger: v })} />
            </div>

            <div className="flex items-start justify-between gap-4 rounded-xl bg-white/[0.03] border border-white/[0.06] p-4">
              <div>
                <p className="text-[13px] font-semibold text-slate-200">Restore my workspace</p>
                <p className="text-[11px] text-slate-500 mt-0.5">Remember the selected account, last page, chart market/timeframe, indicators, drawings and page filters on this browser.</p>
              </div>
              <Toggle on={prefs.restoreWorkspace} onChange={(v) => setPrefs({ restoreWorkspace: v })} />
            </div>

            <div className="flex items-start justify-between gap-4 rounded-xl bg-white/[0.03] border border-white/[0.06] p-4">
              <div>
                <p className="text-[13px] font-semibold text-slate-200">Reconnect MT5 on startup</p>
                <p className="text-[11px] text-slate-500 mt-0.5">Automatically reconnect the last MT5 account using credentials already saved in the MetaTrader 5 terminal.</p>
              </div>
              <Toggle on={prefs.reconnectOnStartup} onChange={(v) => setPrefs({ reconnectOnStartup: v })} />
            </div>

            <div className="rounded-xl bg-white/[0.03] border border-white/[0.06] p-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-[13px] font-semibold text-slate-200">Theme</p>
                  <p className="text-[11px] text-slate-500 mt-0.5">Choose dark or light mode. Your choice is restored on this browser.</p>
                </div>
                <div className="flex gap-1.5">
                  <button type="button" onClick={() => setTheme('dark')} className={`btn-ghost !px-3 ${theme === 'dark' ? '!bg-brand-600 !text-white' : ''}`}><Moon size={14} /> Dark</button>
                  <button type="button" onClick={() => setTheme('light')} className={`btn-ghost !px-3 ${theme === 'light' ? '!bg-brand-600 !text-white' : ''}`}><Sun size={14} /> Light</button>
                </div>
              </div>
            </div>
          </div>
        </Panel>

        <div className="space-y-4">
          <Panel className="p-6">
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <Server size={15} className="text-brand-300" /> MT5 bridge status
              </h3>
              <Badge tone={bridge?.status === 'online' ? 'gain' : bridge?.status === 'simulation' ? 'warn' : 'slate'}>{bridge?.status || 'unknown'}</Badge>
            </div>
            <div className="mt-4 space-y-2.5 text-[12px]">
              <div className="flex justify-between gap-4"><span className="text-slate-500">Runtime</span><span className="mono text-slate-300">{bridge?.mode || (isSimulation ? 'simulation' : 'bridge')}</span></div>
              <div className="flex justify-between gap-4"><span className="text-slate-500">Terminal</span><span className="mono text-slate-300">{bridge?.terminal || 'Not connected'}</span></div>
              {!isSimulation && <div className="flex justify-between gap-4"><span className="text-slate-500">EA Worker</span><span className={bridge?.ea_worker?.status === 'online' ? 'text-gain-400 font-semibold' : 'text-loss-400 font-semibold'}>{bridge?.ea_worker?.status === 'online' ? 'ONLINE' : 'OFFLINE'}</span></div>}
              <div className="flex justify-between gap-4"><span className="text-slate-500">Account</span><span className={accounts.some((account) => account.status === 'connected') ? 'text-gain-400 font-semibold' : 'text-slate-500'}>{accounts.some((account) => account.status === 'connected') ? 'CONNECTED' : 'DISCONNECTED'}</span></div>
              <div className="flex justify-between gap-4"><span className="text-slate-500">Trading</span><span className={bridge?.trading_enabled ? 'text-gain-400 font-semibold' : 'text-warn-400 font-semibold'}>{bridge?.trading_enabled ? 'Enabled' : 'Disabled'}</span></div>
              <div className="flex justify-between gap-4"><span className="text-slate-500">Endpoint</span><span className="mono text-slate-300 text-right">{bridge?.endpoint || 'Not configured'}</span></div>
              <div className="flex justify-between gap-4"><span className="text-slate-500">Protocol</span><span className="mono text-slate-300">{bridge?.protocol || 'Not configured'}</span></div>
              <div className="flex justify-between gap-4 items-center">
                <span className="text-slate-500">Frontend credential storage</span>
                <span className="inline-flex items-center gap-1.5 text-gain-400 font-semibold"><ShieldCheck size={13} /> Disabled</span>
              </div>
            </div>
            <div className="mt-4 rounded-xl border border-warn-400/20 bg-warn-400/[0.05] px-4 py-3 text-[11px] leading-relaxed text-slate-400">
              {bridge?.message || 'A real Windows MT5 terminal worker has not been connected yet.'}
            </div>
            <div className="mt-4 pt-4 border-t border-white/[0.06] space-y-2">
              <p className="label !mb-2">Account / worker assignments</p>
              {accounts.map((a) => (
                <div key={a.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-white/[0.03] px-3 py-2 text-[12px]">
                  <span className="text-slate-300 inline-flex items-center gap-2"><StatusDot status={a.status} /> #{a.login} · {a.broker}</span>
                  <span className="mono text-slate-500">{a.worker_id || 'worker pending'} · {a.terminal_id || 'terminal pending'}</span>
                </div>
              ))}
              {accounts.length === 0 && <p className="text-xs text-slate-600">No MT5 account profiles.</p>}
            </div>
          </Panel>

          <Panel className="p-6">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <FileDown size={15} className="text-brand-300" /> Data tools
            </h3>
            <p className="mt-2 text-xs text-slate-500 leading-relaxed">Export closed-trade history or restart the local hub session.</p>
            <div className="mt-4 flex flex-wrap gap-2.5">
              <button className="btn-ghost" onClick={exportAll}><FileDown size={14} /> Export full history (CSV)</button>
              <button className="btn-ghost" onClick={() => window.location.reload()}><RefreshCw size={14} /> Restart hub session</button>
              {isSimulation && <button className="btn-warn" onClick={resetSimulation}><DatabaseBackup size={14} /> Reset simulation data</button>}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
