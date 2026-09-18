import { useEffect, useMemo, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { Activity, ArrowRightLeft, Brain, Globe, RefreshCw, ShieldAlert, Sparkles, TrendingUp, X, Zap } from 'lucide-react';
import { useHub } from '../context/HubContext';
import { timeAgo } from '../lib/format';
import { Badge, PageHeader, Panel, Progress, Skel, Spinner, Toggle } from '../components/ui';
import type { AiAutoSelectMode, AiAutoSelectStatus, AiAutoStatus, AiInsight, AiSettings, AiTrialSnapshot } from '../types';
import { aiControlService } from '../services/aiControlService';
import { mt5MultiAccountService } from '../services/mt5MultiAccountService';
import NativeAutoSelectPanel from '../components/NativeAutoSelectPanel';
import { isSimulation } from '../config/runtime';

const CATEGORY_META: Record<string, { icon: typeof Brain; cls: string }> = {
  risk: { icon: ShieldAlert, cls: 'text-loss-400 bg-loss-500/12 border-loss-500/25' },
  opportunity: { icon: Zap, cls: 'text-gain-400 bg-gain-500/12 border-gain-500/25' },
  performance: { icon: TrendingUp, cls: 'text-brand-300 bg-brand-500/12 border-brand-500/25' },
  market: { icon: Globe, cls: 'text-warn-400 bg-warn-400/10 border-warn-400/25' },
};

const SENTIMENT_TONE: Record<string, 'gain' | 'loss' | 'warn' | 'slate'> = {
  positive: 'gain', critical: 'loss', warning: 'warn', neutral: 'slate',
};

const TOGGLE_DEFS: { key: keyof AiSettings; label: string; desc: string }[] = [
  { key: 'risk_guard', label: 'AI Risk Guard', desc: 'Surface risk warnings when account, position or drawdown limits are approached.' },
  { key: 'sentiment_filter', label: 'Sentiment Filter', desc: 'Reserved for later external market context. It does not alter Human Apostle entries yet.' },
  { key: 'news_pause', label: 'Red-Folder News Pause', desc: 'Reserved for a later trusted news/calendar provider.' },
];

const fmt = (value: number | null | undefined) => {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return Math.abs(value) >= 100 ? value.toFixed(2) : value.toFixed(5);
};

const structureTone = (value: string): 'gain' | 'loss' | 'slate' => value === 'bullish' ? 'gain' : value === 'bearish' ? 'loss' : 'slate';


type CopyAnywhereConfig = {
  master_account_id?: string;
  slave_account_ids?: string[];
  lot_mode?: 'same' | 'fixed' | 'multiplier' | 'equity_proportional';
  fixed_lot?: number;
  multiplier?: number;
  source_filter?: 'all' | 'manual' | 'ea' | 'magic';
  magic_number?: number | null;
  poll_ms?: number;
  approval_required?: boolean;
};

type CopyAnywhereStatus = {
  status?: string;
  config?: CopyAnywhereConfig | null;
  pending_count?: number;
};

export default function AIPage() {
  const { accounts, mt5Symbols, activeAccount, pushToast } = useHub();
  const connectedAccounts = useMemo(() => accounts.filter((a) => a.status === 'connected'), [accounts]);
  const symbols = useMemo(() => {
    const rows = mt5Symbols.filter((s) => s.trade_allowed).map((s) => s.symbol);
    return rows.length ? rows : ['XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY'];
  }, [mt5Symbols]);

  const [insights, setInsights] = useState<AiInsight[] | null>(null);
  const [settings, setSettings] = useState<AiSettings | null>(null);
  const [generating, setGenerating] = useState(false);
  const [scanPulse, setScanPulse] = useState(0);
  const [trial, setTrial] = useState<AiTrialSnapshot | null>(null);
  const [trialLoading, setTrialLoading] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [accountLogin, setAccountLogin] = useState<number>(0);
  const [symbol, setSymbol] = useState('XAUUSD');
  const [trialVolume, setTrialVolume] = useState('0.01');
  const [autoStatus, setAutoStatus] = useState<AiAutoStatus | null>(null);
  const [autoBusy, setAutoBusy] = useState(false);
  const [autoSelectStatus, setAutoSelectStatus] = useState<AiAutoSelectStatus | null>(null);
  const [autoSelectBusy, setAutoSelectBusy] = useState(false);
  const [autoSelectMode, setAutoSelectMode] = useState<AiAutoSelectMode>('analysis');
  const [autoSelectBotIds, setAutoSelectBotIds] = useState<number[]>([]);
  const autoSelectInitRef = useRef(false);
  const [copyAnywhere, setCopyAnywhere] = useState(false);
  const [copyAnywhereBusy, setCopyAnywhereBusy] = useState(false);
  const [copyStatus, setCopyStatus] = useState<CopyAnywhereStatus | null>(null);
  const [copyStatusError, setCopyStatusError] = useState('');

  const selectedAccount = useMemo(() => connectedAccounts.find((a) => a.login === accountLogin) || null, [connectedAccounts, accountLogin]);
  const selectedNative = autoSelectStatus?.snapshot?.selected || null;

  const loadCopyAnywhere = async () => {
    if (isSimulation) return;
    try {
      const status = await mt5MultiAccountService.copyStatus() as CopyAnywhereStatus;
      setCopyStatus(status);
      const cfg = status.config || null;
      setCopyAnywhere(status.status === 'running' && cfg?.approval_required === false && cfg?.source_filter === 'all');
      setCopyStatusError('');
    } catch (e) {
      setCopyStatus(null);
      setCopyAnywhere(false);
      setCopyStatusError(e instanceof Error ? e.message : 'Copy worker unavailable.');
    }
  };

  const load = () => {
    aiControlService.get()
      .then((d) => { setInsights(d.insights); setSettings(d.settings); })
      .catch(() => pushToast('error', 'AI feed unavailable', 'Could not load the intelligence feed.'));
    if (!isSimulation) {
      aiControlService.trialGet().then((d) => setTrial(d.snapshot)).catch(() => {});
      aiControlService.autoStatus().then(setAutoStatus).catch(() => {});
      aiControlService.autoSelectStatus().then(setAutoSelectStatus).catch(() => {});
      loadCopyAnywhere();
    }
  };

  useEffect(load, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (isSimulation) return;
    const id = window.setInterval(() => {
      aiControlService.autoStatus().then(setAutoStatus).catch(() => {});
      aiControlService.autoSelectStatus().then(setAutoSelectStatus).catch(() => {});
      aiControlService.trialGet().then((d) => setTrial(d.snapshot)).catch(() => {});
    }, 5000);
    return () => window.clearInterval(id);
  }, []);
  useEffect(() => {
    const id = window.setInterval(() => setScanPulse((p) => p + 1), 2400);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    if (accountLogin && connectedAccounts.some((a) => a.login === accountLogin)) return;
    setAccountLogin(activeAccount?.status === 'connected' ? activeAccount.login : connectedAccounts[0]?.login || 0);
  }, [accountLogin, activeAccount, connectedAccounts]);

  useEffect(() => {
    if (!symbols.includes(symbol)) setSymbol(symbols[0] || 'XAUUSD');
  }, [symbol, symbols]);

  useEffect(() => {
    if (!autoSelectStatus || autoSelectInitRef.current) return;
    autoSelectInitRef.current = true;
    setAutoSelectMode(autoSelectStatus.config.mode || 'analysis');
    const configured = autoSelectStatus.config.enabled_bot_ids || [];
    setAutoSelectBotIds(configured.length ? configured : autoSelectStatus.available_presets.filter((p) => p.ready).map((p) => p.bot_id));
    if (autoSelectStatus.enabled && autoSelectStatus.config.account_login) setAccountLogin(autoSelectStatus.config.account_login);
    if (autoSelectStatus.enabled && autoSelectStatus.config.symbol) setSymbol(autoSelectStatus.config.symbol);
  }, [autoSelectStatus]);

  const runTrial = async () => {
    if (isSimulation) {
      pushToast('warning', 'Real MT5 bridge required', 'Human Apostle reads completed M15/H4 candles from a connected MT5 account.');
      return;
    }
    if (!accountLogin || !symbol) {
      pushToast('warning', 'Select an account and symbol');
      return;
    }
    setTrialLoading(true);
    try {
      const result = await aiControlService.trialScan(accountLogin, symbol);
      setTrial(result);
      pushToast('success', 'Apostle scan complete', `${result.decision} · ${result.confidence}% confidence`);
    } catch (e) {
      pushToast('error', 'Trial scan failed', e instanceof Error ? e.message : undefined);
    } finally {
      setTrialLoading(false);
    }
  };

  const executeTrial = async () => {
    if (isSimulation) {
      pushToast('warning', 'Real MT5 bridge required');
      return;
    }
    if (!trial?.proposed_trade || !['BUY', 'SELL'].includes(trial.decision)) {
      pushToast('warning', 'No tradable Apostle signal', 'Run a scan and wait for a current BUY or SELL first.');
      return;
    }
    if (selectedAccount?.account_type !== 'demo') {
      pushToast('warning', 'Demo account required', 'Live AI execution is locked. Use a demo MT5 account.');
      return;
    }
    const volume = Number(trialVolume);
    if (!Number.isFinite(volume) || volume <= 0) {
      pushToast('warning', 'Enter a valid lot size');
      return;
    }
    setExecuting(true);
    try {
      const result = await aiControlService.trialExecute(accountLogin, symbol, volume);
      setTrial((prev) => prev ? { ...prev, execution: 'Demo execution sent to MT5. Live accounts stay locked.', execution_mode: 'DEMO_AUTO_TRADE', last_execution: result } : prev);
      pushToast('success', 'Demo AI trade sent', `${result.direction} ${result.symbol} · lot ${result.volume}`);
    } catch (e) {
      pushToast('error', 'Demo AI execution failed', e instanceof Error ? e.message : undefined);
    } finally {
      setExecuting(false);
    }
  };

  const startAutoTrading = async () => {
    if (isSimulation) {
      pushToast('warning', 'Real MT5 bridge required');
      return;
    }
    if (!accountLogin || !symbol) {
      pushToast('warning', 'Select an account and symbol');
      return;
    }
    if (selectedAccount?.account_type !== 'demo') {
      pushToast('warning', 'Demo account required', 'Human Apostle auto-trading is locked to demo accounts for the user trial.');
      return;
    }
    if (autoSelectStatus?.enabled && autoSelectStatus.config.mode === 'auto') {
      pushToast('warning', 'Auto Select auto mode is already active', 'Stop Auto Select automatic execution before starting Human Apostle Auto-Trading.');
      return;
    }
    const volume = Number(trialVolume);
    if (!Number.isFinite(volume) || volume <= 0) {
      pushToast('warning', 'Enter a valid lot size');
      return;
    }
    setAutoBusy(true);
    try {
      const status = await aiControlService.autoConfigure({ enabled: true, account_login: accountLogin, symbol, volume, scan_seconds: 30 });
      setAutoStatus(status);
      setSettings((prev) => prev ? { ...prev, auto_trading: true } : prev);
      pushToast('success', 'Human Apostle Auto-Trading started', `${symbol} · demo #${accountLogin} · lot ${volume}`);
    } catch (e) {
      pushToast('error', 'Could not start AI Auto-Trading', e instanceof Error ? e.message : undefined);
    } finally {
      setAutoBusy(false);
    }
  };

  const stopAutoTrading = async () => {
    setAutoBusy(true);
    try {
      const status = await aiControlService.autoConfigure({ enabled: false });
      setAutoStatus(status);
      setSettings((prev) => prev ? { ...prev, auto_trading: false } : prev);
      pushToast('info', 'Human Apostle Auto-Trading stopped', 'The server scanner will not open new AI trades.');
    } catch (e) {
      pushToast('error', 'Could not stop AI Auto-Trading', e instanceof Error ? e.message : undefined);
    } finally {
      setAutoBusy(false);
    }
  };

  const toggleAutoSelectPreset = (botId: number) => {
    if (autoSelectStatus?.enabled) return;
    setAutoSelectBotIds((current) => current.includes(botId) ? current.filter((id) => id !== botId) : [...current, botId]);
  };

  const runAutoSelectScan = async () => {
    if (isSimulation) {
      pushToast('warning', 'Real MT5 bridge required');
      return;
    }
    if (!accountLogin || !symbol || !autoSelectBotIds.length) {
      pushToast('warning', 'Choose an account, symbol, and at least one native preset.');
      return;
    }
    setAutoSelectBusy(true);
    try {
      const snapshot = await aiControlService.autoSelectScan(accountLogin, symbol, autoSelectBotIds);
      const status = await aiControlService.autoSelectStatus();
      setAutoSelectStatus({ ...status, snapshot });
      pushToast(snapshot.selected ? 'success' : 'info', snapshot.selected ? 'Native setup selected' : 'Auto Select scan complete',
        snapshot.selected ? `${snapshot.selected.name} · ${snapshot.selected.title} · ${snapshot.selected.selection_score.toFixed(1)} score` : 'No enabled native strategy has a fully confirmed setup yet.');
    } catch (e) {
      pushToast('error', 'Auto Select scan failed', e instanceof Error ? e.message : undefined);
    } finally {
      setAutoSelectBusy(false);
    }
  };

  const startAutoSelect = async () => {
    if (!accountLogin || !symbol || !autoSelectBotIds.length) {
      pushToast('warning', 'Choose an account, symbol, and at least one native preset.');
      return;
    }
    if (autoSelectMode === 'auto' && selectedAccount?.account_type !== 'demo') {
      pushToast('warning', 'Demo account required', 'Auto Select automatic execution is locked to DEMO accounts.');
      return;
    }
    setAutoSelectBusy(true);
    try {
      const status = await aiControlService.autoSelectConfigure({
        enabled: true, account_login: accountLogin, symbol,
        enabled_bot_ids: autoSelectBotIds, mode: autoSelectMode, scan_seconds: 30,
      });
      setAutoSelectStatus(status);
      pushToast('success', 'AI Auto Select started', `${symbol} · ${autoSelectMode.toUpperCase()} · ${autoSelectBotIds.length} native presets`);
    } catch (e) {
      pushToast('error', 'Could not start Auto Select', e instanceof Error ? e.message : undefined);
    } finally {
      setAutoSelectBusy(false);
    }
  };

  const stopAutoSelect = async () => {
    setAutoSelectBusy(true);
    try {
      const status = await aiControlService.autoSelectConfigure({ enabled: false, mode: autoSelectMode });
      setAutoSelectStatus(status);
      pushToast('info', 'AI Auto Select stopped', 'No new Auto Select entries will be submitted.');
    } catch (e) {
      pushToast('error', 'Could not stop Auto Select', e instanceof Error ? e.message : undefined);
    } finally {
      setAutoSelectBusy(false);
    }
  };

  const executeAutoSelectSelection = async () => {
    if (selectedAccount?.account_type !== 'demo') {
      pushToast('warning', 'Demo account required', 'Manual AI confirmation execution is DEMO-only.');
      return;
    }
    setAutoSelectBusy(true);
    try {
      const execution = await aiControlService.autoSelectExecute();
      const status = await aiControlService.autoSelectStatus();
      setAutoSelectStatus(status);
      const direction = String(execution.direction || '');
      pushToast('success', 'Selected native setup executed', `${selectedNative?.name || 'Native strategy'} · ${direction} ${symbol}`);
    } catch (e) {
      pushToast('error', 'Selected setup was not executed', e instanceof Error ? e.message : undefined);
    } finally {
      setAutoSelectBusy(false);
    }
  };

  const toggleCopyAnywhere = async (enabled: boolean) => {
    if (isSimulation) {
      pushToast('warning', 'Real multi-account worker required');
      return;
    }
    setCopyAnywhereBusy(true);
    try {
      const latest = await mt5MultiAccountService.copyStatus() as CopyAnywhereStatus;
      const cfg = latest.config || null;
      if (!cfg?.master_account_id || !cfg.slave_account_ids?.length) {
        pushToast('warning', 'Set up Copy Trading first', 'Choose a master and at least one slave on the Copy Trading page, then return here.');
        return;
      }
      await mt5MultiAccountService.startCopy({
        master_account_id: cfg.master_account_id,
        slave_account_ids: cfg.slave_account_ids,
        lot_mode: cfg.lot_mode || 'same',
        fixed_lot: cfg.fixed_lot ?? 0.01,
        multiplier: cfg.multiplier ?? 1,
        source_filter: enabled ? 'all' : (cfg.source_filter || 'all'),
        magic_number: cfg.magic_number ?? null,
        poll_ms: cfg.poll_ms ?? 300,
        approval_required: !enabled,
      });
      setCopyAnywhere(enabled);
      pushToast(enabled ? 'success' : 'info', enabled ? 'Copy Trades From Anywhere enabled' : 'Copy Trades From Anywhere disabled', enabled
        ? 'New eligible trades that appear on the connected master account will copy automatically to linked slaves.'
        : 'The copy link stays active, but new master trades return to the normal approval popup.');
      await loadCopyAnywhere();
    } catch (e) {
      pushToast('error', 'Could not change Copy Trades From Anywhere', e instanceof Error ? e.message : undefined);
      await loadCopyAnywhere();
    } finally {
      setCopyAnywhereBusy(false);
    }
  };

  const generate = async () => {
    setGenerating(true);
    try {
      const result = await aiControlService.generate();
      setInsights(result.insights); setSettings(result.settings);
      pushToast('success', 'Fresh account analysis published', result.insights[0]?.title || 'Analysis updated.');
    } catch (e) {
      pushToast('error', 'Analysis failed', e instanceof Error ? e.message : undefined);
    } finally { setGenerating(false); }
  };

  const dismiss = async (id: number) => {
    setInsights((prev) => (prev || []).filter((i) => i.id !== id));
    try { await aiControlService.remove(id); } catch { /* visual removal already applied */ }
  };

  const updateSetting = async (key: keyof AiSettings, value: boolean) => {
    if (!settings) return;
    const previous = settings;
    const next = { ...settings, [key]: value };
    setSettings(next);
    try {
      await aiControlService.saveSettings(next);
      pushToast('info', `${TOGGLE_DEFS.find((t) => t.key === key)?.label} ${value ? 'enabled' : 'disabled'}`);
    } catch {
      setSettings(previous);
      pushToast('error', 'Persist failed', 'Reverting the toggle.');
    }
  };

  return (
    <div>
      <PageHeader
        title="AI Intelligence"
        sub="Human Apostle + KOOLKID native strategy intelligence · completed candles only · server-side scanning · automatic execution stays DEMO-only"
        actions={
          <div className="flex flex-wrap gap-2">
            <button className="btn-secondary" onClick={executeTrial} disabled={executing || isSimulation || !trial?.proposed_trade || !['BUY', 'SELL'].includes(trial?.decision || '') || selectedAccount?.account_type !== 'demo'}>
              {executing ? <Spinner size={15} /> : <Zap size={15} />}
              {executing ? 'Sending demo order…' : 'Execute current demo signal'}
            </button>
            <button className="btn-primary" onClick={runTrial} disabled={trialLoading || isSimulation || !accountLogin}>
              {trialLoading ? <Spinner size={15} /> : <Brain size={15} />}
              {trialLoading ? 'Scanning M15 + H4…' : 'Run Apostle Scan'}
            </button>
          </div>
        }
      />

      <Panel className="p-5 mb-4 border-brand-500/20">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-[15px] font-extrabold text-white">Human Apostle AI</p>
              <Badge tone="warn">DEMO ONLY</Badge>
              <Badge tone={isSimulation ? 'warn' : 'gain'}>{autoStatus?.enabled ? 'AUTO RUNNING' : (isSimulation ? 'Bridge required' : 'Ready')}</Badge>
            </div>
            <p className="mt-1 text-[12px] text-slate-500 max-w-3xl">
              Sequence: market structure → opposing trendline break → protected structure break → later retest → rejection candle → H4 alignment. You can scan manually, execute a current signal manually, or let the server keep scanning and execute fresh confirmed signals automatically on a demo account. Live AI execution remains locked.
            </p>
          </div>
          <p className="mono text-[10px] text-slate-600">{trial?.execution || (autoStatus?.enabled ? 'SERVER SCANNER ACTIVE' : 'WAITING FOR SCAN')}</p>
        </div>

        <div className="mt-4 grid grid-cols-1 md:grid-cols-5 gap-3">
          <div>
            <label className="label">Connected account</label>
            <select className="input" value={accountLogin || ''} onChange={(e) => setAccountLogin(Number(e.target.value))} disabled={!connectedAccounts.length || !!autoStatus?.enabled || !!autoSelectStatus?.enabled}>
              {!connectedAccounts.length && <option value="">No connected MT5 account</option>}
              {connectedAccounts.map((a) => <option key={a.login} value={a.login}>{a.nickname || `MT5 #${a.login}`} · #{a.login}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Symbol</label>
            <select className="input" value={symbol} onChange={(e) => setSymbol(e.target.value)} disabled={!!autoStatus?.enabled || !!autoSelectStatus?.enabled}>
              {symbols.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Fixed demo lot</label>
            <input className="input mono" value={trialVolume} onChange={(e) => setTrialVolume(e.target.value)} placeholder="0.01" disabled={!!autoStatus?.enabled || !!autoSelectStatus?.enabled} />
          </div>
          <div>
            <label className="label">Execution timeframe</label>
            <div className="input mono flex items-center">M15 <span className="text-slate-600 ml-2">fixed</span></div>
          </div>
          <div>
            <label className="label">Bias timeframe</label>
            <div className="input mono flex items-center">H4 <span className="text-slate-600 ml-2">fixed</span></div>
          </div>
        </div>
        <p className="mt-3 text-[11px] text-slate-500">Selected account type: <span className="text-white font-semibold">{selectedAccount?.account_type || '—'}</span>. Human Apostle uses its proposed SL/TP and your fixed lot. Auto-Trading keeps running on the server even if this browser closes.</p>
        <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-white/[0.07] pt-4">
          <button
            className={autoStatus?.enabled ? 'btn-secondary' : 'btn-primary'}
            onClick={autoStatus?.enabled ? stopAutoTrading : startAutoTrading}
            disabled={autoBusy || isSimulation || (!autoStatus?.enabled && (!accountLogin || selectedAccount?.account_type !== 'demo' || (autoSelectStatus?.enabled && autoSelectStatus.config.mode === 'auto')))}
          >
            {autoBusy ? <Spinner size={15} /> : <Activity size={15} />}
            {autoBusy ? 'Updating…' : autoStatus?.enabled ? 'Stop AI Auto-Trading' : 'Start AI Auto-Trading'}
          </button>
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={autoStatus?.runtime?.status === 'running' ? 'gain' : autoStatus?.runtime?.status === 'blocked' ? 'loss' : autoStatus?.enabled ? 'warn' : 'slate'}>{autoStatus?.runtime?.status || 'stopped'}</Badge>
            <span className="text-[10px] text-slate-600">Server scanner · 30s checks · fresh completed-candle signals only · duplicate signal protection</span>
          </div>
        </div>
      </Panel>

      {autoStatus && (
        <Panel className="p-5 mb-4 border border-brand-500/20">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex flex-wrap items-center gap-2"><p className="text-[14px] font-bold text-white">AI Auto-Trading Monitor</p><Badge tone={autoStatus.enabled && autoStatus.scanner_alive ? 'gain' : autoStatus.enabled ? 'warn' : 'slate'}>{autoStatus.enabled ? (autoStatus.scanner_alive ? 'SERVER ACTIVE' : 'STARTING') : 'OFF'}</Badge></div>
              <p className="mt-1 text-[11px] text-slate-500">This is workspace-isolated and server-side. Browser logout or closing the page does not stop an enabled scanner. Restart recovery restores enabled scanners.</p>
            </div>
            <div className="text-right text-[10px] text-slate-600">
              <p>{autoStatus.config?.symbol || symbol} · #{autoStatus.config?.account_login || accountLogin || '—'} · lot {autoStatus.config?.volume ?? trialVolume}</p>
              <p>M15 execution · H4 bias · DEMO ONLY</p>
            </div>
          </div>
          <div className="mt-4 grid grid-cols-2 lg:grid-cols-4 gap-2.5">
            <div className="rounded-xl bg-black/25 border border-white/[0.06] p-3"><p className="text-[9px] uppercase tracking-widest text-slate-600">Last scan</p><p className="mt-1 text-xs font-semibold text-slate-200">{autoStatus.runtime.last_scan_at ? timeAgo(autoStatus.runtime.last_scan_at) : '—'}</p></div>
            <div className="rounded-xl bg-black/25 border border-white/[0.06] p-3"><p className="text-[9px] uppercase tracking-widest text-slate-600">Last decision</p><p className="mt-1 text-xs font-semibold text-slate-200">{autoStatus.runtime.last_decision || '—'}{typeof autoStatus.runtime.last_confidence === 'number' ? ` · ${autoStatus.runtime.last_confidence}%` : ''}</p></div>
            <div className="rounded-xl bg-black/25 border border-white/[0.06] p-3"><p className="text-[9px] uppercase tracking-widest text-slate-600">Last signal</p><p className="mt-1 text-xs font-semibold text-slate-200">{autoStatus.runtime.last_signal || '—'}{autoStatus.runtime.last_signal_at ? ` · ${timeAgo(autoStatus.runtime.last_signal_at)}` : ''}</p></div>
            <div className="rounded-xl bg-black/25 border border-white/[0.06] p-3"><p className="text-[9px] uppercase tracking-widest text-slate-600">Last execution</p><p className="mt-1 text-xs font-semibold text-slate-200">{autoStatus.runtime.last_execution_at ? timeAgo(autoStatus.runtime.last_execution_at) : '—'}</p></div>
          </div>
          {autoStatus.runtime.last_error && <p className="mt-3 rounded-xl border border-warn-400/20 bg-warn-400/5 px-3 py-2 text-[11px] text-warn-400">{autoStatus.runtime.last_error}</p>}
          {!!autoStatus.events?.length && <div className="mt-3 border-t border-white/[0.06] pt-3"><p className="text-[9px] uppercase tracking-widest text-slate-600 mb-2">Recent AI events</p><div className="space-y-1">{autoStatus.events.slice(0, 5).map((event, idx) => <p key={`${event.time}-${idx}`} className="text-[10px] text-slate-500"><span className="mono text-slate-600">{timeAgo(event.time)}</span> · {event.event.replaceAll('_', ' ')}{event.symbol ? ` · ${event.symbol}` : ''}{event.direction ? ` · ${event.direction}` : ''}</p>)}</div></div>}
        </Panel>
      )}

      <NativeAutoSelectPanel
        status={autoSelectStatus}
        accountLogin={accountLogin}
        accountType={selectedAccount?.account_type}
        symbol={symbol}
        busy={autoSelectBusy}
        mode={autoSelectMode}
        selectedBotIds={autoSelectBotIds}
        simulation={isSimulation}
        onMode={setAutoSelectMode}
        onTogglePreset={toggleAutoSelectPreset}
        onScan={runAutoSelectScan}
        onStart={startAutoSelect}
        onStop={stopAutoSelect}
        onExecute={executeAutoSelectSelection}
      />

      <Panel className="p-5 mb-4 border border-gain-500/20">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex min-w-0 items-start gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-gain-500/25 bg-gain-500/10 text-gain-400"><ArrowRightLeft size={18} /></span>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2"><p className="text-[14px] font-bold text-white">Copy Trades From Anywhere</p><Badge tone={copyAnywhere ? 'gain' : 'slate'}>{copyAnywhere ? 'AUTO COPY ON' : 'APPROVAL MODE'}</Badge></div>
              <p className="mt-1 max-w-4xl text-[12px] leading-relaxed text-slate-500">When enabled, KOOLKID watches the connected Master account itself. Any eligible new trade that appears on that Master can be copied automatically to the linked Slave accounts — whether it was opened from KOOLKID, MT5 desktop, MT5 mobile, WebTerminal, an EA, a VPS, another bot, or another connected trading app. The trade must appear on the same connected Master account.</p>
              <p className="mt-2 text-[10px] text-slate-600">Uses your existing Copy Trading master/slave link and lot settings. Existing open positions are not copied when the toggle is switched on; only new positions detected afterward are eligible.</p>
              {copyStatusError && <p className="mt-2 text-[10px] text-loss-400">Copy worker: {copyStatusError}</p>}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="text-right"><p className="text-[10px] uppercase tracking-widest text-slate-600">Copy link</p><p className="text-[11px] font-semibold text-slate-300">{copyStatus?.config?.master_account_id && copyStatus?.config?.slave_account_ids?.length ? `${copyStatus.status === 'running' ? 'Active' : 'Saved'} · ${copyStatus.config.slave_account_ids.length} slave${copyStatus.config.slave_account_ids.length === 1 ? '' : 's'}` : 'Not configured'}</p></div>
            {copyAnywhereBusy ? <Spinner size={18} /> : <Toggle on={copyAnywhere} onChange={toggleCopyAnywhere} disabled={isSimulation || !copyStatus?.config?.master_account_id || !copyStatus?.config?.slave_account_ids?.length} />}
          </div>
        </div>
      </Panel>

      {trial && (
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 mb-4">
          <Panel className="p-5 xl:col-span-2">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={trial.decision === 'BUY' ? 'gain' : trial.decision === 'SELL' ? 'loss' : 'slate'}>{trial.decision}</Badge>
              <p className="text-[15px] font-bold text-white">{trial.symbol} · {trial.state}</p>
              <span className="mono text-[10px] text-slate-600 ml-auto">{timeAgo(trial.generated_at)}</span>
            </div>
            <p className="mt-2 text-[13px] leading-relaxed text-slate-400">{trial.reason}</p>

            <div className="mt-4 grid grid-cols-2 lg:grid-cols-5 gap-2.5">
              <div className="rounded-xl bg-black/25 border border-white/[0.06] p-3"><p className="text-[9px] uppercase tracking-widest text-slate-600">M15 structure</p><div className="mt-1"><Badge tone={structureTone(trial.execution_structure)}>{trial.execution_structure}</Badge></div></div>
              <div className="rounded-xl bg-black/25 border border-white/[0.06] p-3"><p className="text-[9px] uppercase tracking-widest text-slate-600">Trendline</p><p className="mt-1 text-xs font-bold text-slate-200">{trial.trendline ? 'BROKEN' : 'WAITING'}</p></div>
              <div className="rounded-xl bg-black/25 border border-white/[0.06] p-3"><p className="text-[9px] uppercase tracking-widest text-slate-600">Structure shift</p><p className="mt-1 text-xs font-bold text-slate-200">{trial.structure_shift.confirmed ? 'CONFIRMED' : 'WAITING'}</p></div>
              <div className="rounded-xl bg-black/25 border border-white/[0.06] p-3"><p className="text-[9px] uppercase tracking-widest text-slate-600">Later retest</p><p className="mt-1 text-xs font-bold text-slate-200">{trial.retest.touched ? 'TOUCHED' : 'WAITING'}</p></div>
              <div className="rounded-xl bg-black/25 border border-white/[0.06] p-3"><p className="text-[9px] uppercase tracking-widest text-slate-600">H4 bias</p><div className="mt-1"><Badge tone={structureTone(trial.bias_structure)}>{trial.bias_structure}</Badge></div></div>
            </div>

            <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3 text-[11px]">
              <div className="rounded-xl border border-white/[0.06] p-3 bg-black/15">
                <p className="font-semibold text-slate-300">Latest confirmed structure</p>
                <p className="mt-1 text-slate-500">High: {trial.last_confirmed_high ? `${trial.last_confirmed_high.label} @ ${fmt(trial.last_confirmed_high.price)}` : '—'}</p>
                <p className="text-slate-500">Low: {trial.last_confirmed_low ? `${trial.last_confirmed_low.label} @ ${fmt(trial.last_confirmed_low.price)}` : '—'}</p>
                <p className="text-slate-500">Protected level: {fmt(trial.protected_structure)}</p>
                <p className="text-slate-500">Retest level: {fmt(trial.retest.level)}</p>
              </div>
              <div className="rounded-xl border border-white/[0.06] p-3 bg-black/15">
                <div className="flex items-center justify-between"><p className="font-semibold text-slate-300">Confidence</p><span className="mono text-sm font-extrabold text-white">{trial.confidence}%</span></div>
                <Progress value={trial.confidence} tone={trial.confidence >= 80 ? 'gain' : trial.confidence >= 55 ? 'brand' : 'warn'} />
                <div className="mt-2 space-y-1">{trial.confidence_factors.length ? trial.confidence_factors.map((f) => <p key={f} className="text-slate-500">• {f}</p>) : <p className="text-slate-600">No setup factors confirmed yet.</p>}</div>
              </div>
            </div>
          </Panel>

          <Panel className="p-5">
            <p className="text-[13px] font-bold text-white">Trade proposal</p>
            {trial.proposed_trade ? (
              <div className="mt-3 space-y-2">
                <Badge tone={trial.proposed_trade.direction === 'BUY' ? 'gain' : 'loss'}>{trial.proposed_trade.direction}</Badge>
                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  <span className="text-slate-500">Entry</span><span className="mono text-right text-white">{fmt(trial.proposed_trade.entry)}</span>
                  <span className="text-slate-500">SL</span><span className="mono text-right text-loss-400">{fmt(trial.proposed_trade.sl)}</span>
                  <span className="text-slate-500">TP</span><span className="mono text-right text-gain-400">{fmt(trial.proposed_trade.tp)}</span>
                  <span className="text-slate-500">Target</span><span className="mono text-right text-white">2.0R</span>
                </div>
                <p className="text-[10px] text-warn-400 border-t border-white/[0.06] pt-2">This setup can be sent manually or by the server auto-trader on the selected demo account only.</p>
                {trial.last_execution && (
                  <div className="mt-3 rounded-xl bg-black/20 border border-white/[0.06] p-3 text-[11px]">
                    <p className="text-[10px] uppercase tracking-widest text-slate-600">Last demo execution</p>
                    <p className="mt-1 text-slate-300">{trial.last_execution.direction} {trial.last_execution.symbol} · lot {trial.last_execution.volume}</p>
                    <p className="text-slate-500">{timeAgo(trial.last_execution.executed_at)} · {trial.last_execution.message}</p>
                  </div>
                )}
              </div>
            ) : (
              <div className="mt-4">
                <p className="text-[12px] text-slate-500">No current entry. The engine will not invent one before every required stage is complete.</p>
                {trial.last_historical_signal && (
                  <div className="mt-3 rounded-xl bg-black/20 border border-white/[0.06] p-3">
                    <p className="text-[10px] uppercase tracking-widest text-slate-600">Last historical setup found</p>
                    <p className="mt-1 text-xs text-slate-300">{trial.last_historical_signal.direction} @ {fmt(trial.last_historical_signal.entry)}</p>
                    <p className="text-[10px] text-slate-600">Reference only — it is not a current signal.</p>
                  </div>
                )}
              </div>
            )}
          </Panel>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Panel className="p-6 xl:row-span-2 h-fit xl:sticky xl:top-24">
          <div className="flex items-center gap-3">
            <span className="relative grid h-12 w-12 place-items-center rounded-2xl bg-brand-600/20 border border-brand-500/40 text-brand-300">
              <Brain size={22} />
              <motion.span key={scanPulse} className="absolute inset-0 rounded-2xl border border-brand-400/50" initial={{ opacity: 0.7, scale: 1 }} animate={{ opacity: 0, scale: 1.45 }} transition={{ duration: 1.6, ease: 'easeOut' }} />
            </span>
            <div><p className="text-[15px] font-extrabold text-white tracking-tight">MT5 AI CONTROL</p><p className="mono text-[10px] text-slate-500">Human Apostle + account insight feed</p></div>
            <Badge tone={isSimulation ? 'warn' : 'gain'}>{isSimulation ? 'Simulation' : 'Online'}</Badge>
          </div>
          <div className="mt-5 grid grid-cols-3 gap-2.5 text-center">
            <div className="rounded-xl bg-black/25 border border-white/[0.06] p-2.5"><p className="mono text-lg font-extrabold text-white">{insights?.length ?? 0}</p><p className="text-[9px] uppercase tracking-widest text-slate-600 font-semibold mt-0.5">Insights</p></div>
            <div className="rounded-xl bg-black/25 border border-white/[0.06] p-2.5"><p className="mono text-lg font-extrabold text-white">{insights && insights.length ? Math.round(insights.reduce((s, i) => s + i.confidence, 0) / insights.length) : 0}%</p><p className="text-[9px] uppercase tracking-widest text-slate-600 font-semibold mt-0.5">Avg conf</p></div>
            <div className="rounded-xl bg-black/25 border border-white/[0.06] p-2.5"><p className="mono text-lg font-extrabold text-gain-400">{scanPulse}</p><p className="text-[9px] uppercase tracking-widest text-slate-600 font-semibold mt-0.5">Scan pulse</p></div>
          </div>
          <p className="mt-4 flex items-center gap-2 text-[11px] text-slate-500"><Activity size={12} className="text-gain-400" />{isSimulation ? 'Simulation insight feed is active; Human Apostle requires the real MT5 bridge.' : autoStatus?.enabled ? 'Human Apostle server scanner is active for this workspace.' : 'Connected MT5 account state is available to AI Intelligence.'}</p>
          <div className="mt-5 pt-5 border-t border-white/[0.07] space-y-4">
            {TOGGLE_DEFS.map((t) => <div key={t.key} className="flex items-start justify-between gap-3"><div><p className="text-[13px] font-semibold text-slate-200">{t.label}</p><p className="text-[11px] text-slate-500 leading-snug mt-0.5">{t.desc}</p></div><Toggle on={settings ? settings[t.key] : false} onChange={(v) => updateSetting(t.key, v)} disabled={!settings} /></div>)}
          </div>
        </Panel>

        <div className="xl:col-span-2 space-y-3">
          <div className="flex justify-end"><button className="btn-secondary" onClick={generate} disabled={generating}>{generating ? <Spinner size={14} /> : <RefreshCw size={14} />}{generating ? 'Refreshing…' : 'Refresh account insights'}</button></div>
          {insights === null ? Array.from({ length: 3 }).map((_, i) => <Skel key={i} className="h-32" />) : insights.length === 0 ? (
            <Panel><div className="py-14 text-center"><Sparkles size={26} className="mx-auto text-brand-300 mb-3" /><p className="text-sm text-slate-400">No account insights yet.</p></div></Panel>
          ) : insights.map((i) => {
            const meta = CATEGORY_META[i.category] || CATEGORY_META.market; const Icon = meta.icon;
            return <motion.div key={i.id} layout initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}><Panel hover className="p-5"><div className="flex items-start gap-3.5"><span className={`shrink-0 grid h-10 w-10 place-items-center rounded-xl border ${meta.cls}`}><Icon size={17} /></span><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><p className="text-[14px] font-bold text-white">{i.title}</p><Badge tone={SENTIMENT_TONE[i.sentiment] || 'slate'}>{i.sentiment}</Badge></div><p className="mt-1.5 text-[13px] leading-relaxed text-slate-400">{i.body}</p><div className="mt-3 flex items-center gap-3"><span className="text-[10px] uppercase tracking-widest text-slate-600 font-semibold">Confidence</span><div className="w-32"><Progress value={i.confidence} tone={i.confidence >= 80 ? 'gain' : i.confidence >= 65 ? 'brand' : 'warn'} /></div><span className="mono text-[11px] font-bold text-slate-300">{i.confidence}%</span><span className="text-[10px] text-slate-600 ml-auto">{timeAgo(i.created_at)}</span></div></div><button className="btn-icon !p-1.5" title="Dismiss" onClick={() => dismiss(i.id)}><X size={14} /></button></div></Panel></motion.div>;
          })}
        </div>
      </div>
    </div>
  );
}
