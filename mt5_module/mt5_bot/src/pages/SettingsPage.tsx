import { useState } from 'react';
import { Bell, DatabaseBackup, FileDown, Filter, Headphones, RefreshCw, Server, ShieldCheck, Timer, Moon, Sun } from 'lucide-react';
import { useHub } from '../context/HubContext';
import type { MarketBrokerFilter, MarketCategoryFilter } from '../context/HubContext';
import { PageHeader, Panel, Toggle, Badge, StatusDot } from '../components/ui';
import { isSimulation } from '../config/runtime';
import { mt5HistoryService } from '../services/mt5HistoryService';
import { simReset } from '../services/simulationStore';
import { useTheme } from '../hooks/useTheme';
import { notificationPermission, requestNotificationPermission } from '../services/notificationService';
import type { NotificationAlertKey } from '../services/notificationService';
import { CONTACT_SUPPORT_OPEN_EVENT } from '../components/ContactSupport';

const POLL_OPTIONS = [
  { label: '3 seconds', value: 3000 },
  { label: '5 seconds', value: 5000 },
  { label: '15 seconds', value: 15000 },
  { label: '30 seconds', value: 30000 },
  { label: '60 seconds', value: 60000 },
  { label: '2 minutes', value: 120000 },
];

const BROKER_FILTERS: Array<{ value: MarketBrokerFilter; label: string }> = [
  { value: 'all', label: 'All brokers' },
  { value: 'current', label: 'Current account broker' },
  { value: 'deriv', label: 'Deriv only' },
  { value: 'weltrade', label: 'Weltrade only' },
  { value: 'favorites', label: 'Favorites only' },
  { value: 'custom', label: 'Custom broker mix' },
];

const MARKET_FILTERS: Array<{ value: MarketCategoryFilter; label: string }> = [
  { value: 'all', label: 'All markets' },
  { value: 'synthetic', label: 'Synthetic / Volatility' },
  { value: 'forex', label: 'Forex' },
  { value: 'metals', label: 'Metals' },
  { value: 'indices', label: 'Indices' },
  { value: 'crypto', label: 'Crypto' },
  { value: 'stocks', label: 'Stocks / CFDs' },
  { value: 'energies', label: 'Energies' },
  { value: 'weltrade_syntx', label: 'Weltrade SyntX' },
  { value: 'fxvol', label: 'FXVol only' },
  { value: 'sfxvol', label: 'SFX Vol only' },
  { value: 'painx', label: 'PainX only' },
  { value: 'gainx', label: 'GainX only' },
  { value: 'flipx', label: 'FlipX only' },
  { value: 'switchx', label: 'SwitchX only' },
  { value: 'breakx', label: 'BreakX only' },
  { value: 'trendx', label: 'TrendX only' },
  { value: 'progression', label: 'PlusX / FiboX / QuadX' },
  { value: 'maxx', label: 'MAX PainX / MAX GainX' },
  { value: 'custom', label: 'Custom market groups' },
];

const ALERT_OPTIONS: Array<{ key: NotificationAlertKey; title: string; description: string }> = [
  { key: 'tradeOpened', title: 'Trade opened', description: 'Alert when a new MT5 position opens.' },
  { key: 'tradeClosed', title: 'Trade closed / result', description: 'Alert when a position closes, including profit or loss when available.' },
  { key: 'accountStatus', title: 'Account connection', description: 'Alert when an MT5 account connects or disconnects.' },
  { key: 'botStatus', title: 'Bot / EA status', description: 'Alert when a bot starts, stops, errors, or its worker goes offline.' },
  { key: 'copyTrader', title: 'Copy Trader', description: 'Alert for link status, pending approvals, and copy errors.' },
  { key: 'riskAlerts', title: 'Risk / system alerts', description: 'Alert if trading, the bridge, or the EA worker becomes unavailable.' },
  { key: 'aiAlerts', title: 'AI Intelligence', description: 'Alert for AI signals, executions, starts/stops, and errors.' },
];

export default function SettingsPage() {
  const { prefs, setPrefs, accounts, bridge, pushToast, refresh } = useHub();
  const { theme, setTheme } = useTheme();
  const [permission, setPermission] = useState(() => notificationPermission());

  const setNotificationsEnabled = async (enabled: boolean) => {
    if (!enabled) {
      setPrefs({ notifications: { ...prefs.notifications, enabled: false } });
      pushToast('info', 'Notifications off', 'KOOLKID browser alerts are disabled.');
      return;
    }
    const nextPermission = await requestNotificationPermission();
    setPermission(nextPermission);
    if (nextPermission === 'granted') {
      setPrefs({ notifications: { ...prefs.notifications, enabled: true } });
      pushToast('success', 'Notifications enabled', 'KOOLKID will alert you for the categories selected below.');
    } else {
      setPrefs({ notifications: { ...prefs.notifications, enabled: false } });
      pushToast('warning', 'Notification permission needed', 'Allow notifications in your browser/site settings, then try again.');
    }
  };

  const setAlert = (key: NotificationAlertKey, enabled: boolean) => {
    setPrefs({ notifications: { ...prefs.notifications, [key]: enabled } });
  };

  const toggleBrokerFamily = (family: 'deriv' | 'weltrade' | 'other') => {
    const has = prefs.customBrokerFamilies.includes(family);
    const next = has ? prefs.customBrokerFamilies.filter((item) => item !== family) : [...prefs.customBrokerFamilies, family];
    if (next.length) setPrefs({ customBrokerFamilies: next });
  };

  const toggleMarketGroup = (group: 'synthetic' | 'forex' | 'metals' | 'indices' | 'crypto' | 'stocks' | 'energies' | 'weltrade_syntx') => {
    const has = prefs.customMarketGroups.includes(group);
    const next = has ? prefs.customMarketGroups.filter((item) => item !== group) : [...prefs.customMarketGroups, group];
    if (next.length) setPrefs({ customMarketGroups: next });
  };

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
              <div className="flex items-center gap-2">
                <Filter size={14} className="text-brand-300" />
                <p className="text-[13px] font-semibold text-slate-200">Market visibility</p>
              </div>
              <p className="mt-1 text-[11px] text-slate-500">Choose which broker families and market groups appear across KOOLKID. These preferences are saved to your KOOLKID account.</p>
              <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2.5">
                <label><span className="label">Broker source</span>
                  <select className="input" value={prefs.marketBrokerFilter} onChange={(e) => setPrefs({ marketBrokerFilter: e.target.value as MarketBrokerFilter })}>
                    {BROKER_FILTERS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                  </select>
                </label>
                <label><span className="label">Market type</span>
                  <select className="input" value={prefs.marketCategoryFilter} onChange={(e) => setPrefs({ marketCategoryFilter: e.target.value as MarketCategoryFilter })}>
                    {MARKET_FILTERS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                  </select>
                </label>
              </div>
              {prefs.marketBrokerFilter === 'custom' && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {(['deriv', 'weltrade', 'other'] as const).map((family) => <button key={family} type="button" onClick={() => toggleBrokerFamily(family)} className={prefs.customBrokerFamilies.includes(family) ? 'btn-primary !px-3 !py-1.5' : 'btn-ghost !px-3 !py-1.5'}>{family === 'deriv' ? 'Deriv' : family === 'weltrade' ? 'Weltrade' : 'Other brokers'}</button>)}
                </div>
              )}
              {prefs.marketCategoryFilter === 'custom' && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {([
                    ['synthetic', 'Synthetic'], ['forex', 'Forex'], ['metals', 'Metals'], ['indices', 'Indices'],
                    ['crypto', 'Crypto'], ['stocks', 'Stocks'], ['energies', 'Energies'], ['weltrade_syntx', 'Weltrade SyntX'],
                  ] as const).map(([key, label]) => <button key={key} type="button" onClick={() => toggleMarketGroup(key)} className={prefs.customMarketGroups.includes(key) ? 'btn-primary !px-3 !py-1.5' : 'btn-ghost !px-3 !py-1.5'}>{label}</button>)}
                </div>
              )}
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
            <div className="flex items-start gap-3">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-500/15 text-brand-300 ring-1 ring-brand-500/25">
                <Headphones size={18} />
              </span>
              <div className="min-w-0 flex-1">
                <h3 className="text-sm font-bold text-white">Contact Us</h3>
                <p className="mt-1 text-xs leading-relaxed text-slate-500">Need help or more information? Reopen the KOOLKID contact card for Telegram and WhatsApp support.</p>
                <button
                  type="button"
                  className="btn-primary mt-4"
                  onClick={() => {
                    window.dispatchEvent(new Event(CONTACT_SUPPORT_OPEN_EVENT));
                    pushToast('info', 'Contact Us opened', 'Telegram and WhatsApp support is available in the contact card.');
                  }}
                >
                  <Headphones size={14} /> Contact Us
                </button>
              </div>
            </div>
          </Panel>

          <Panel className="p-6">
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <Bell size={15} className="text-brand-300" /> Notifications
              </h3>
              <Badge tone={permission === 'granted' ? 'gain' : permission === 'denied' ? 'loss' : 'slate'}>
                {permission === 'unsupported' ? 'UNSUPPORTED' : permission.toUpperCase()}
              </Badge>
            </div>
            <div className="mt-4 flex items-start justify-between gap-4 rounded-xl bg-white/[0.03] border border-white/[0.06] p-4">
              <div>
                <p className="text-[13px] font-semibold text-slate-200">Browser notifications</p>
                <p className="text-[11px] text-slate-500 mt-0.5">Master switch for KOOLKID MT5 alerts on this browser/device.</p>
              </div>
              <Toggle on={prefs.notifications.enabled && permission === 'granted'} onChange={setNotificationsEnabled} />
            </div>
            <div className="mt-3 space-y-2">
              {ALERT_OPTIONS.map((option) => (
                <div key={option.key} className="flex items-start justify-between gap-4 rounded-xl bg-white/[0.025] border border-white/[0.05] px-4 py-3">
                  <div>
                    <p className="text-[12px] font-semibold text-slate-300">{option.title}</p>
                    <p className="text-[10px] text-slate-600 mt-0.5">{option.description}</p>
                  </div>
                  <Toggle on={prefs.notifications[option.key]} onChange={(value) => setAlert(option.key, value)} />
                </div>
              ))}
            </div>
            {permission === 'denied' && (
              <p className="mt-3 rounded-lg border border-warn-400/20 bg-warn-400/[0.05] px-3 py-2 text-[11px] text-warn-300">
                Notifications are blocked by the browser. Re-enable them in this site's browser permissions, then turn the master switch on again.
              </p>
            )}
          </Panel>

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
