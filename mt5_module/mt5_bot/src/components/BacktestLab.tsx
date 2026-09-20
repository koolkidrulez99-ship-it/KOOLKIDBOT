import { useEffect, useMemo, useState } from 'react';
import { CheckCircle2, Clock3, Download, Eye, FileCode2, LoaderCircle, Upload, XCircle } from 'lucide-react';
import { useHub } from '../context/HubContext';
import { backtestService } from '../services/backtestService';
import type { BacktestJob, BacktestState } from '../services/backtestService';
import { Badge, Panel } from './ui';
import Modal from './Modal';
import MarketSelect from './MarketSelect';

const ACTIVE = new Set(['queued', 'preparing', 'compiling', 'testing', 'analyzing']);
const TIMEFRAMES = ['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1'];

function resultValue(job: BacktestJob, key: string) {
  const value = job.result?.[key];
  if (value === null || value === undefined || value === '') return '—';
  return String(value);
}

function percentTone(job: BacktestJob) {
  if (job.status === 'failed') return 'bg-loss-500';
  if (job.status === 'complete') return 'bg-gain-500';
  return 'bg-brand-500';
}

function formatDate(value?: string | null) {
  if (!value) return '—';
  return new Date(value).toLocaleString();
}

export default function BacktestLab() {
  const { accounts, pushToast } = useHub();
  const connected = useMemo(
    () => accounts.filter((account) => account.status === 'connected'),
    [accounts]
  );
  const [state, setState] = useState<BacktestState | null>(null);
  const [open, setOpen] = useState(false);
  const [selectedResult, setSelectedResult] = useState<BacktestJob | null>(null);
  const [busy, setBusy] = useState(false);
  const [downloadBusy, setDownloadBusy] = useState<string | null>(null);
  const [botFile, setBotFile] = useState<File | null>(null);
  const [presetFile, setPresetFile] = useState<File | null>(null);
  const [accountLogin, setAccountLogin] = useState<number | ''>('');
  const [symbol, setSymbol] = useState('XAUUSD');
  const [timeframe, setTimeframe] = useState('M15');
  const [dateFrom, setDateFrom] = useState(() => {
    const value = new Date();
    value.setFullYear(value.getFullYear() - 1);
    return value.toISOString().slice(0, 10);
  });
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [deposit, setDeposit] = useState(10000);
  const [leverage, setLeverage] = useState(100);
  const [model, setModel] = useState(4);
  const [researchOptIn, setResearchOptIn] = useState(false);

  const load = async () => {
    try {
      const next = await backtestService.list();
      setState(next);
    } catch (error) {
      pushToast('error', 'Backtest Lab unavailable', error instanceof Error ? error.message : undefined);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    const hasActive = state?.jobs.some((job) => ACTIVE.has(job.status));
    if (!hasActive) return;
    const timer = window.setInterval(() => {
      void load();
    }, 3000);
    return () => window.clearInterval(timer);
  }, [state?.jobs]);

  useEffect(() => {
    if (accountLogin === '' && connected.length) {
      setAccountLogin(connected[0].login);
    }
  }, [connected, accountLogin]);

  const activeJob =
    state?.active_job ||
    state?.jobs.find((job) => ACTIVE.has(job.status)) ||
    null;
  const latest = state?.jobs[0] || null;
  const start = async () => {
    if (!botFile || accountLogin === '') return;
    setBusy(true);
    try {
      await backtestService.create({
        botFile,
        presetFile,
        accountLogin: Number(accountLogin),
        symbol: symbol.trim(),
        timeframe,
        dateFrom,
        dateTo,
        deposit,
        leverage,
        model,
        researchOptIn,
      });
      setOpen(false);
      setBotFile(null);
      setPresetFile(null);
      await load();
    } catch (error) {
      pushToast('error', 'Backtest could not start', error instanceof Error ? error.message : undefined);
    } finally {
      setBusy(false);
    }
  };

  const download = async (job: BacktestJob, kind: 'report' | 'data') => {
    const key = `${job.id}:${kind}`;
    setDownloadBusy(key);
    try {
      if (kind === 'report') await backtestService.downloadReport(job.id);
      else await backtestService.downloadData(job.id);
    } catch (error) {
      pushToast('error', 'Backtest download failed', error instanceof Error ? error.message : undefined);
    } finally {
      setDownloadBusy(null);
    }
  };

  const resultMetrics: Array<[string, string]> = [
    ['Net profit', 'net_profit'],
    ['Gross profit', 'gross_profit'],
    ['Gross loss', 'gross_loss'],
    ['Profit factor', 'profit_factor'],
    ['Expected payoff', 'expected_payoff'],
    ['Max drawdown', 'max_drawdown'],
    ['Total trades', 'total_trades'],
    ['Winning trades', 'profit_trades'],
    ['Losing trades', 'loss_trades'],
    ['Largest win', 'largest_profit_trade'],
    ['Largest loss', 'largest_loss_trade'],
  ];

  // Backtest Lab display
  return (
    <>
    <div className="mb-5">
      <h2 className="text-lg font-extrabold text-white">Backtest Lab</h2>
      <p className="mt-1 text-xs text-slate-400">Historical testing runs on the KOOLKID server and stays saved when you leave the page.</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Badge tone="brand">SERVER-SIDE</Badge>
        <Badge tone="slate">1 ACTIVE TEST AT A TIME</Badge>
      </div>
      <button
        className="btn-primary mt-4 max-md:w-full max-md:justify-center"
        disabled={!state?.available || connected.length === 0}
        onClick={() => setOpen(true)}
      >
        <Upload size={15} /> Start New Backtest
      </button>
      {activeJob && (
        <div className="mt-5 rounded-xl border border-brand-500/20 bg-brand-500/[0.05] p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-bold text-white">{activeJob.bot_filename}</p>
              <p className="mt-0.5 text-[11px] text-slate-500">{activeJob.symbol} · {activeJob.timeframe} · {activeJob.stage}</p>
            </div>
            <span className="mono text-lg font-extrabold text-brand-300">{Math.round(activeJob.progress)}%</span>
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/[0.06]">
            <div className={`h-full transition-all ${percentTone(activeJob)}`} style={{ width: `${Math.max(2, activeJob.progress)}%` }} />
          </div>
          <p className="mt-2 text-[10px] text-slate-600">Started: {formatDate(activeJob.started_at || activeJob.created_at)}</p>
        </div>
      )}
      {!activeJob && latest && (
        <div className="mt-5 rounded-xl border border-white/[0.07] p-4">
          <div className="flex items-center gap-2">
            {latest.status === 'complete' ? <CheckCircle2 size={15} className="text-gain-400" /> : <XCircle size={15} className="text-loss-400" />}
            <p className="text-sm font-bold text-white">{latest.bot_filename}</p>
            <Badge tone={latest.status === 'complete' ? 'gain' : 'loss'}>{latest.status}</Badge>
          </div>
          <p className="mt-2 text-xs text-slate-500">{latest.symbol} · {latest.timeframe} · Finished {formatDate(latest.completed_at)}</p>
          {latest.error && <p className="mt-2 text-xs text-loss-400">{latest.error}</p>}
          {latest.status === 'complete' && (
            <div className="mt-3 flex flex-wrap gap-2">
              <button className="btn-primary" onClick={() => setSelectedResult(latest)}><Eye size={14} /> View Results</button>
              <button className="btn-ghost" disabled={!latest.report_filename || downloadBusy === `${latest.id}:report`} onClick={() => void download(latest, 'report')}>
                <Download size={14} /> {downloadBusy === `${latest.id}:report` ? 'Preparing...' : 'MT5 Report'}
              </button>
              <button className="btn-ghost" disabled={downloadBusy === `${latest.id}:data`} onClick={() => void download(latest, 'data')}>
                <Download size={14} /> {downloadBusy === `${latest.id}:data` ? 'Preparing...' : 'JSON Data'}
              </button>
            </div>
          )}
        </div>
      )}
      {!state?.available && activeJob && (
        <p className="mt-3 flex items-center gap-2 text-[11px] text-slate-500">
          <Clock3 size={12} /> Finish the active backtest before starting another.
        </p>
      )}
    </div>

    <Modal
      open={open}
      onClose={() => { if (!busy) setOpen(false); }}
      title="Start Server Backtest"
      sub="The job continues on the server after you leave."
      wide
    >
      <div className="space-y-4">
        <label className="block">
          <span className="label">MT5 bot (.ex5 or .mq5)</span>
          <input className="input" type="file" accept=".ex5,.mq5" onChange={(event) => setBotFile(event.target.files?.[0] || null)} />
        </label>
        <label className="block">
          <span className="label">Optional settings (.set)</span>
          <input className="input" type="file" accept=".set" onChange={(event) => setPresetFile(event.target.files?.[0] || null)} />
        </label>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label><span className="label">MT5 data account</span><select className="input" value={accountLogin} onChange={(event) => setAccountLogin(Number(event.target.value))}>
            <option value="">Select account</option>
            {connected.map((account) => <option key={account.id} value={account.login}>#{account.login} · {account.broker}</option>)}
          </select></label>
          <div><span className="label">Market</span><MarketSelect compact value={symbol} onChange={setSymbol} accountLogin={accountLogin === '' ? undefined : Number(accountLogin)} /></div>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <label><span className="label">Timeframe</span><select className="input" value={timeframe} onChange={(event) => setTimeframe(event.target.value)}>
            {TIMEFRAMES.map((value) => <option key={value}>{value}</option>)}
          </select></label>
          <label><span className="label">From</span><input className="input" type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} /></label>
          <label><span className="label">To</span><input className="input" type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} /></label>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <label><span className="label">Starting balance</span><input className="input" type="number" min="100" value={deposit} onChange={(event) => setDeposit(Number(event.target.value))} /></label>
          <label><span className="label">Leverage</span><input className="input" type="number" min="1" max="5000" value={leverage} onChange={(event) => setLeverage(Number(event.target.value))} /></label>
          <label><span className="label">Test model</span><select className="input" value={model} onChange={(event) => setModel(Number(event.target.value))}>
            <option value={4}>Real ticks</option>
            <option value={0}>Every tick</option>
            <option value={1}>1 minute OHLC</option>
            <option value={2}>Open prices</option>
          </select></label>
        </div>
        <label className="flex items-start gap-3 rounded-xl border border-white/[0.07] bg-white/[0.025] p-4">
          <input type="checkbox" className="mt-1" checked={researchOptIn} onChange={(event) => setResearchOptIn(event.target.checked)} />
          <span>
            <span className="block text-xs font-semibold text-slate-200">Optional KOOLKID AI research contribution</span>
            <span className="mt-1 block text-[11px] leading-relaxed text-slate-500">
              Allow generalized strategy observations and backtest results to enter KOOLKID research. Your original EA file is not published or shared with other users.
            </span>
          </span>
        </label>
        <div className="rounded-xl border border-warn-400/20 bg-warn-400/[0.05] p-3 text-[11px] text-warn-300">
          After the test starts, it keeps running as a server job and cannot be cancelled from the user dashboard.
        </div>
        <button className="btn-primary w-full justify-center" disabled={busy || !botFile || accountLogin === ''} onClick={start}>
          {busy ? <LoaderCircle size={15} className="animate-spin" /> : <FileCode2 size={15} />}
          {busy ? 'Starting...' : 'Start Backtest'}
        </button>
      </div>
    </Modal>

    <Modal
      open={Boolean(selectedResult)}
      onClose={() => setSelectedResult(null)}
      title={selectedResult ? `${selectedResult.bot_filename} · Backtest Results` : 'Backtest Results'}
      sub={selectedResult ? `${selectedResult.symbol} · ${selectedResult.timeframe} · ${selectedResult.date_from} → ${selectedResult.date_to}` : undefined}
      wide
    >
      {selectedResult && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {resultMetrics.map(([label, key]) => (
              <div key={key} className="rounded-xl border border-white/[0.07] bg-white/[0.025] p-3">
                <p className="text-[9px] font-bold uppercase tracking-wider text-slate-600">{label}</p>
                <p className="mono mt-1 text-sm font-extrabold text-white">{resultValue(selectedResult, key)}</p>
              </div>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <div className="rounded-xl border border-white/[0.07] p-3"><p className="text-[9px] uppercase tracking-wider text-slate-600">Starting balance</p><p className="mono mt-1 text-xs font-bold text-slate-200">{selectedResult.deposit}</p></div>
            <div className="rounded-xl border border-white/[0.07] p-3"><p className="text-[9px] uppercase tracking-wider text-slate-600">Leverage</p><p className="mono mt-1 text-xs font-bold text-slate-200">1:{selectedResult.leverage}</p></div>
            <div className="rounded-xl border border-white/[0.07] p-3"><p className="text-[9px] uppercase tracking-wider text-slate-600">Tester return</p><p className="mono mt-1 text-xs font-bold text-slate-200">{selectedResult.return_code ?? '—'}</p></div>
            <div className="rounded-xl border border-white/[0.07] p-3"><p className="text-[9px] uppercase tracking-wider text-slate-600">Finished</p><p className="mt-1 text-[10px] font-semibold text-slate-300">{formatDate(selectedResult.completed_at)}</p></div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="btn-primary" disabled={!selectedResult.report_filename || downloadBusy === `${selectedResult.id}:report`} onClick={() => void download(selectedResult, 'report')}>
              <Download size={14} /> {downloadBusy === `${selectedResult.id}:report` ? 'Preparing...' : 'Download MT5 Report'}
            </button>
            <button className="btn-ghost" disabled={downloadBusy === `${selectedResult.id}:data`} onClick={() => void download(selectedResult, 'data')}>
              <Download size={14} /> {downloadBusy === `${selectedResult.id}:data` ? 'Preparing...' : 'Download JSON Data'}
            </button>
          </div>
          <div className="rounded-xl border border-white/[0.07] bg-black/20 p-3">
            <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">MT5 Strategy Tester Log</p>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words text-[10px] leading-relaxed text-slate-400">{selectedResult.tester_log || 'No tester log was saved for this run.'}</pre>
          </div>
        </div>
      )}
    </Modal>
  </>
  );
}
