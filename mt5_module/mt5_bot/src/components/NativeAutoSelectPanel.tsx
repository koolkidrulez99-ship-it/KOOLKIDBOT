import { Activity, Brain, Play, ScanSearch, ShieldCheck, Square } from 'lucide-react';
import { Badge, Panel, Spinner } from './ui';
import type { AiAutoSelectMode, AiAutoSelectStatus } from '../types';

type Props = {
  status: AiAutoSelectStatus | null;
  accountLogin: number;
  accountType?: string;
  symbol: string;
  busy: boolean;
  mode: AiAutoSelectMode;
  selectedBotIds: number[];
  simulation: boolean;
  onMode: (mode: AiAutoSelectMode) => void;
  onTogglePreset: (botId: number) => void;
  onScan: () => void;
  onStart: () => void;
  onStop: () => void;
  onExecute: () => void;
};

const MODES: Array<{ value: AiAutoSelectMode; label: string; note: string }> = [
  { value: 'analysis', label: 'ANALYSIS ONLY', note: 'Scan and rank only' },
  { value: 'alert', label: 'ALERT ONLY', note: 'Notify on a full setup' },
  { value: 'manual', label: 'MANUAL CONFIRM', note: 'You approve the DEMO order' },
  { value: 'auto', label: 'AUTO DEMO', note: 'DEMO execution only' },
];
const tone = (decision?: string): 'gain' | 'loss' | 'warn' | 'slate' => {
  if (decision === 'APPROVE') return 'gain';
  if (decision === 'REJECT') return 'loss';
  if (decision === 'WAIT') return 'warn';
  return 'slate';
};

export default function NativeAutoSelectPanel(props: Props) {
  const { status, accountLogin, accountType, symbol, busy, mode, selectedBotIds, simulation } = props;
  const selected = status?.snapshot?.selected || null;
  const running = Boolean(status?.enabled);
  const active = Boolean(status?.enabled && status.scanner_alive);
  const presets = status?.available_presets || [];
  const results = status?.snapshot?.results || [];

  return (
    <Panel className="p-5 mb-4 !border-violet-500/20 bg-gradient-to-br from-violet-500/[0.06] via-transparent to-brand-500/[0.03]">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="grid h-10 w-10 place-items-center rounded-xl border border-violet-400/25 bg-violet-500/10 text-violet-300"><Brain size={18} /></span>
            <div><p className="text-[15px] font-extrabold text-white">AI Auto Select · Native Strategies</p>
              <p className="text-[10px] text-slate-600">KOOLKID evaluates the enabled native presets independently.</p></div>
            <Badge tone={active ? 'gain' : running ? 'warn' : 'slate'}>{active ? 'SERVER ACTIVE' : running ? 'STARTING' : 'OFF'}</Badge>
            <Badge tone="warn">AUTO = DEMO ONLY</Badge>
          </div>
        </div>
        <div className="text-right text-[10px] text-slate-600">
          <p>#{accountLogin || '—'} · {accountType || '—'} · {symbol}</p>
          <p>{status?.runtime?.last_scan_at ? 'Last scan ' + new Date(status.runtime.last_scan_at).toLocaleTimeString() : 'Waiting for scan'}</p>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 lg:grid-cols-4 gap-2">
        {MODES.map((item) => (
          <button key={item.value} type="button" disabled={running}
            onClick={() => props.onMode(item.value)}
            className={'rounded-xl border px-3 py-2.5 text-left transition ' + (mode === item.value ? 'border-violet-400/35 bg-violet-500/10 text-white' : 'border-white/[0.07] bg-black/20 text-slate-400 hover:text-white')}>
            <p className="text-[10px] font-extrabold tracking-wide">{item.label}</p>
            <p className="mt-0.5 text-[9px] text-slate-600">{item.note}</p>
          </button>
        ))}
      </div>

      <div className="mt-4">
        <div className="flex items-center justify-between gap-3">
          <p className="text-[10px] uppercase tracking-widest font-bold text-slate-600">Enabled native presets</p>
          <span className="mono text-[10px] text-slate-600">{selectedBotIds.length} selected</span>
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          {presets.map((preset) => {
            const checked = selectedBotIds.includes(preset.bot_id);
            return <button key={preset.bot_id} type="button" disabled={running || !preset.ready}
              onClick={() => props.onTogglePreset(preset.bot_id)}
              className={'rounded-lg border px-2.5 py-2 text-left ' + (!preset.ready ? 'opacity-45 border-white/[0.05]' : checked ? 'border-brand-400/35 bg-brand-500/10' : 'border-white/[0.07] bg-black/20')}>
              <p className="text-[10px] font-bold text-slate-200">{preset.name}</p>
              <p className="text-[9px] text-slate-600">{preset.ready ? preset.title : 'SOURCE REQUIRED'}</p>
            </button>;
          })}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2 border-t border-white/[0.07] pt-4">
        <button className="btn-secondary" onClick={props.onScan}
          disabled={busy || simulation || running || !accountLogin || !selectedBotIds.length}>
          {busy ? <Spinner size={14} /> : <ScanSearch size={14} />} Run Auto Select Scan
        </button>
        <button className={running ? 'btn-secondary' : 'btn-primary'}
          onClick={running ? props.onStop : props.onStart}
          disabled={busy || simulation || (!running && (!accountLogin || !selectedBotIds.length || (mode === 'auto' && accountType !== 'demo')))}>
          {busy ? <Spinner size={14} /> : running ? <Square size={14} /> : <Activity size={14} />}
          {running ? 'Stop Auto Select' : 'Start Auto Select'}
        </button>
        {mode === 'manual' && selected?.decision === 'APPROVE' && (
          <button className="btn-primary" onClick={props.onExecute} disabled={busy || simulation || accountType !== 'demo'}>
            <Play size={14} /> Execute Selected DEMO Setup
          </button>
        )}
      </div>

      <div className="mt-4 rounded-xl border border-white/[0.06] bg-black/20 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <ShieldCheck size={14} className="text-brand-300" />
          <p className="text-[11px] font-semibold text-slate-300">Setup validity always comes first.</p>
        </div>
        <p className="mt-1 text-[10px] leading-relaxed text-slate-500">
          Historical performance only breaks ties between strategies that already have a fully valid completed-candle setup. It cannot turn an incomplete setup into a trade.
        </p>
      </div>

      {selected ? (
        <div className="mt-4 rounded-xl border border-gain-500/20 bg-gain-500/[0.04] p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div><div className="flex flex-wrap items-center gap-2"><Badge tone="gain">SELECTED</Badge>
              <p className="text-[13px] font-extrabold text-white">{selected.name} · {selected.title}</p></div>
              <p className="mt-1 text-[11px] text-slate-500">{selected.stage} · {selected.reason}</p>
            </div>
            <div className="text-right"><p className="mono text-lg font-extrabold text-white">{selected.selection_score.toFixed(1)}</p>
              <p className="text-[9px] uppercase tracking-widest text-slate-600">selection score</p></div>
          </div>
          <div className="mt-3 flex flex-wrap gap-3 text-[10px] text-slate-500">
            <span>Source score <b className="mono text-slate-300">{selected.score.toFixed(1)}</b></span>
            <span>History {selected.history.trades} trades</span>
            <span>Win rate {selected.history.trades ? selected.history.win_rate.toFixed(1) + '%' : '—'}</span>
            <span>Net P/L <b className="mono text-slate-300">{selected.history.net_pl.toFixed(2)}</b></span>
          </div>
        </div>
      ) : status?.snapshot ? (
        <p className="mt-4 text-[11px] text-slate-500">No enabled native preset has a fully confirmed setup right now. KOOLKID will wait rather than force an entry.</p>
      ) : null}

      {!!results.length && (
        <div className="mt-4 border-t border-white/[0.06] pt-3">
          <p className="text-[9px] uppercase tracking-widest font-bold text-slate-600 mb-2">Strategy evaluation</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {results.slice(0, 8).map((row) => (
              <div key={row.bot_id} className="rounded-xl border border-white/[0.06] bg-black/15 px-3 py-2.5">
                <div className="flex items-center justify-between gap-2"><p className="text-[11px] font-bold text-slate-200">{row.name}</p><Badge tone={tone(row.decision)}>{row.decision}</Badge></div>
                <p className="mt-1 text-[10px] text-slate-500">{row.stage} · score {row.score.toFixed(1)}</p>
                <p className="mt-1 text-[9px] text-slate-600 line-clamp-2">{row.reason}</p>
              </div>
            ))}
          </div>
        </div>
      )}
      {status?.runtime?.last_error && <p className="mt-3 rounded-xl border border-warn-400/20 bg-warn-400/[0.05] px-3 py-2 text-[10px] text-warn-400">{status.runtime.last_error}</p>}
    </Panel>
  );
}
