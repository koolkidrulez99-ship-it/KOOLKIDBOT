import { useEffect, useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { BarChart3, Boxes, Cpu, FileCode2, Play, Plus, ScanSearch, Settings2, Target, Trash2, Upload } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useHub } from '../context/HubContext';
import { fmtSigned, profitTone } from '../lib/format';
import { Badge, EmptyState, PageHeader, Panel, Progress, Spinner } from '../components/ui';
import Modal from '../components/Modal';
import ConfirmModal from '../components/ConfirmModal';
import BotConfigModal from '../components/BotConfigModal';
import { botControl, createBot, deleteBot } from '../lib/actions';
import { TIMEFRAMES } from '../lib/market';
import MarketSelect from '../components/MarketSelect';
import { isSimulation } from '../config/runtime';
import { mt5BotService } from '../services/mt5BotService';
import type { Mt5Bot } from '../types';

const STRATEGIES = ['System Preset', 'Custom EA'];

const PRESET_ACCENTS: Record<number, { icon: string; border: string; glow: string }> = {
  1000: { icon: 'text-slate-100 bg-slate-500/10 border-slate-400/25', border: '!border-slate-400/15', glow: 'from-slate-300/10' },
  1001: { icon: 'text-sky-300 bg-sky-500/10 border-sky-400/25', border: '!border-sky-400/15', glow: 'from-sky-400/10' },
  1002: { icon: 'text-emerald-300 bg-emerald-500/10 border-emerald-400/25', border: '!border-emerald-400/15', glow: 'from-emerald-400/10' },
  1003: { icon: 'text-amber-300 bg-amber-500/10 border-amber-400/25', border: '!border-amber-400/15', glow: 'from-amber-400/10' },
  1004: { icon: 'text-violet-300 bg-violet-500/10 border-violet-400/25', border: '!border-violet-400/15', glow: 'from-violet-400/10' },
  1005: { icon: 'text-rose-300 bg-rose-500/10 border-rose-400/25', border: '!border-rose-400/15', glow: 'from-rose-400/10' },
  1006: { icon: 'text-zinc-200 bg-zinc-400/10 border-zinc-300/25', border: '!border-zinc-300/15', glow: 'from-zinc-300/10' },
  1007: { icon: 'text-white bg-white/[0.06] border-white/20', border: '!border-white/15', glow: 'from-white/[0.06]' },
};

export default function BotLibraryPage() {
  const { bots, bridge, accountName, botLiveToday, pushToast, refresh } = useHub();
  const eaLaunchAvailable = isSimulation || bridge?.capabilities?.ea_launch === true;
  const [configBot, setConfigBot] = useState<Mt5Bot | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [removeTarget, setRemoveTarget] = useState<Mt5Bot | null>(null);
  const [fileTarget, setFileTarget] = useState<Mt5Bot | null>(null);
  const [strategyFilter, setStrategyFilter] = useState<string>('all');

  const filtered = useMemo(
    () => (strategyFilter === 'all' ? bots : bots.filter((b) => b.strategy === strategyFilter)),
    [bots, strategyFilter]
  );

  return (
    <div>
      <PageHeader
        title="Bot Library"
        sub={isSimulation ? 'KOOLKID native strategy presets + custom MT5 EAs' : 'KOOLKID native presets run server-side through the MT5 account worker · uploaded custom EAs use the EA Worker'}
        actions={
          <>
            <select className="input !w-auto !py-2 text-xs" value={strategyFilter} onChange={(e) => setStrategyFilter(e.target.value)}>
              <option value="all">All bots</option>
              {STRATEGIES.map((s) => <option key={s}>{s}</option>)}
            </select>
            <button className="btn-primary" onClick={() => setAddOpen(true)}><Upload size={15} /> Upload EA</button>
          </>
        }
      />

      <Panel className="mb-4 px-4 py-3 !border-brand-500/20 bg-brand-500/[0.04]">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-[11px] text-slate-400">
          <span className="inline-flex items-center gap-2"><Cpu size={14} className="text-brand-300" /> Built-in presets: <b className="text-slate-200">KOOLKID Native Engine</b></span>
          <span>Server-side · no chart attachment · no EA Worker</span>
          <span className="inline-flex items-center gap-2"><FileCode2 size={14} className="text-slate-500" /> Custom uploads: <b className="mono text-slate-200">.ex5 / .set</b> via EA Worker {eaLaunchAvailable ? '· online' : '· currently offline'}</span>
        </div>
      </Panel>

      {filtered.length === 0 ? (
        <Panel><EmptyState icon={Boxes} title="No bots in this view" sub="Try a different filter or register a new expert advisor." /></Panel>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3 gap-4">
          {filtered.map((b) => {
            const running = b.status === 'running';
            const paused = b.status === 'paused';
            const today = botLiveToday(b);
            const isCatalog = Boolean(b.system_preset);
            const isNative = Boolean(b.native_engine);
            const sourceRequired = isNative && b.native_ready === false;
            const accent = PRESET_ACCENTS[b.id] || { icon: 'text-brand-300 bg-brand-500/10 border-brand-500/25', border: '', glow: 'from-brand-500/[0.06]' };
            const nativeSignal = (b.native_signal || {}) as { stage?: string; score?: number; reason?: string };
            const nativeRuntime = (b.native_runtime || {}) as { status?: string; last_scan_at?: string; last_error?: string | null };
            return (
              <Panel key={b.id} hover className={`p-5 flex flex-col relative overflow-hidden ${isCatalog ? accent.border : ''}`}>
                {isCatalog && <span className={`pointer-events-none absolute inset-0 bg-gradient-to-br ${accent.glow} via-transparent to-transparent opacity-70`} />}
                <div className="relative z-[1] flex flex-col h-full">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3 min-w-0">
                    <span className={`grid h-12 w-12 shrink-0 place-items-center rounded-2xl border ${isCatalog ? accent.icon : running ? 'bg-gain-500/10 border-gain-500/25 text-gain-400' : paused ? 'bg-warn-400/10 border-warn-400/25 text-warn-400' : 'bg-brand-500/10 border-brand-500/25 text-brand-300'}`}>
                      <Cpu size={20} />
                    </span>
                    <div className="min-w-0">
                      {isCatalog ? <p className="text-[9px] font-extrabold tracking-[0.20em] text-slate-500">{b.name}</p> : null}
                      <p className={`${isCatalog ? 'text-[17px]' : 'text-[15px]'} font-extrabold text-white truncate tracking-tight`}>{isCatalog ? (b.display_title || b.name) : b.name}</p>
                      <p className="mono text-[10px] text-slate-500">v{b.version} · magic {b.settings?.magic_number ?? '—'}</p>
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-1.5">
                    <Badge tone={running ? 'gain' : paused ? 'warn' : b.status === 'error' ? 'loss' : 'slate'}>{b.status}</Badge>
                    {isNative && <Badge tone={sourceRequired ? 'warn' : 'brand'}>{sourceRequired ? 'SOURCE REQUIRED' : 'KOOLKID NATIVE'}</Badge>}
                  </div>
                </div>

                <p className="mt-3 text-xs leading-relaxed text-slate-400 min-h-[32px]">{isCatalog ? (b.display_subtitle || b.description) : b.description}</p>

                <div className="mt-3 flex flex-wrap items-center gap-1.5">
                  <Badge tone="slate">{b.strategy}</Badge>{isCatalog && <Badge tone="brand">BUILT-IN PRESET</Badge>}
                  <span className="chip mono !text-[11px]"><Target size={11} className="text-brand-300" /> {b.symbol} · {b.timeframe}</span>
                  {isNative ? <span className="chip !text-[11px]">Source risk sizing</span> : <span className="chip mono !text-[11px]">{b.lot_size.toFixed(2)} lots</span>}
                </div>

                {isNative ? (
                  <div className="mt-3 rounded-xl bg-black/25 border border-white/[0.06] p-3 space-y-1.5 text-[11px]">
                    <div className="flex justify-between gap-3"><span className="text-slate-600">Engine</span><span className="font-semibold text-slate-200">{sourceRequired ? 'Native source unavailable' : 'KOOLKID Native · server-side'}</span></div>
                    <div className="flex justify-between gap-3"><span className="text-slate-600">Execution</span><span className="text-slate-300">8002 account worker · no chart attachment</span></div>
                    <div className="flex justify-between gap-3"><span className="text-slate-600">Flow</span><span className="mono text-slate-300">{b.bias_timeframe || 'HTF'} → {b.timeframe}</span></div>
                    <div className="flex justify-between gap-3"><span className="text-slate-600">Source</span><span className="mono text-slate-400 truncate">{b.native_source || 'MQ5 source required'}</span></div>
                  </div>
                ) : (
                  <div className="mt-3 rounded-xl bg-black/25 border border-white/[0.06] p-3 space-y-1.5 text-[11px]">
                    <div className="flex justify-between gap-3"><span className="text-slate-600">EA file</span><span className="mono text-slate-300 truncate">{b.ea_filename || 'Not assigned'}</span></div>
                    <div className="flex justify-between gap-3"><span className="text-slate-600">Preset</span><span className="mono text-slate-300 truncate">{b.preset_filename || 'None'}</span></div>
                    <div className="flex justify-between gap-3"><span className="text-slate-600">File status</span><Badge tone={b.file_status === 'ready' ? 'gain' : 'warn'}>{b.file_status || 'metadata-only'}</Badge></div>
                    <div className="flex justify-between gap-3"><span className="text-slate-600">DLL</span><span className={b.dll_required ? 'text-warn-400 font-semibold' : 'text-slate-300'}>{b.dll_required ? 'Required by metadata' : 'Not required'}</span></div>
                  </div>
                )}

                {isNative ? (
                  <div className="mt-3 border-t border-white/[0.07] pt-3 text-[11px]">
                    <div className="flex items-center justify-between gap-3">
                      <span className="inline-flex items-center gap-1.5 text-slate-500"><ScanSearch size={13} /> Native strategy monitor</span>
                      <Badge tone={sourceRequired ? 'warn' : running && nativeRuntime.status === 'running' ? 'gain' : running ? 'warn' : 'slate'}>{sourceRequired ? 'source required' : nativeRuntime.status || (running ? 'starting' : 'ready')}</Badge>
                    </div>
                    {sourceRequired ? (
                      <p className="mt-1.5 text-warn-400">MQ5 source is required before this preset can run natively. The legacy EX5 is not decoded or used as a substitute.</p>
                    ) : (
                      <>
                        <p className="mt-1.5 text-slate-300">{nativeSignal.stage ? `${nativeSignal.stage}${typeof nativeSignal.score === 'number' ? ` · ${nativeSignal.score.toFixed(0)} score` : ''}` : 'Server-side strategy engine ready.'}</p>
                        <p className="mt-1 text-slate-500 line-clamp-2">{nativeRuntime.last_error || nativeSignal.reason || 'Runs continuously while KOOLKID services are online, even with the browser closed.'}</p>
                      </>
                    )}
                  </div>
                ) : (
                  <div className="mt-3 border-t border-white/[0.07] pt-3 text-[11px]">
                    <div className="flex items-center justify-between gap-3">
                      <span className="inline-flex items-center gap-1.5 text-slate-500"><ScanSearch size={13} /> Compiled EA runtime analysis</span>
                      <Badge tone={b.ea_verified ? 'gain' : running ? 'warn' : 'slate'}>{b.ea_verified ? 'EA verified' : running ? 'verifying' : 'awaiting launch'}</Badge>
                    </div>
                    <p className="mt-1.5 text-slate-500">Compiled strategy logic remains private. KOOLKID reports only verified files, MT5 runtime evidence and observed behavior.</p>
                    {!!b.strategy_analysis?.observed_traits?.length && <p className="mt-1.5 text-slate-300">Observed: {b.strategy_analysis.observed_traits.join(' · ')}</p>}
                    {!!b.strategy_analysis?.observed_messages?.length && <p className="mt-1.5 text-slate-500 line-clamp-2">Latest EA log: {b.strategy_analysis.observed_messages.at(-1)}</p>}
                    {b.preset_analysis && <p className="mt-1.5 text-slate-500">Preset inputs detected: <span className="mono text-slate-300">{b.preset_analysis.input_count ?? 0}</span></p>}
                  </div>
                )}

                <div className="mt-4 grid grid-cols-4 gap-2 text-center rounded-xl bg-black/25 border border-white/[0.06] p-3">
                  <div><p className="text-[9px] uppercase tracking-widest text-slate-600 font-semibold">Win rate</p><p className="mono text-[13px] font-bold text-white mt-1">{b.total_trades ? `${b.win_rate.toFixed(1)}%` : '—'}</p></div>
                  <div><p className="text-[9px] uppercase tracking-widest text-slate-600 font-semibold">Trades</p><p className="mono text-[13px] font-bold text-white mt-1">{b.total_trades}</p></div>
                  <div><p className="text-[9px] uppercase tracking-widest text-slate-600 font-semibold">Net P/L</p><p className={`mono text-[13px] font-bold mt-1 ${b.total_trades ? profitTone(b.net_profit) : 'text-slate-600'}`}>{b.total_trades ? fmtSigned(b.net_profit, 0) : '—'}</p></div>
                  <div><p className="text-[9px] uppercase tracking-widest text-slate-600 font-semibold">Today</p><p className={`mono text-[13px] font-bold mt-1 ${running ? profitTone(today) : 'text-slate-600'}`}>{running ? fmtSigned(today, 0) : '—'}</p></div>
                </div>

                <div className="mt-3">
                  <div className="flex justify-between text-[10px] text-slate-600 mb-1"><span>Recorded win rate</span><span className="mono">{b.total_trades} fills</span></div>
                  <Progress value={b.total_trades ? b.win_rate : 0} tone={b.win_rate >= 60 ? 'gain' : b.win_rate >= 50 ? 'brand' : 'warn'} />
                </div>

                <p className="mt-3 text-[11px] text-slate-500">Assignment: <span className="text-slate-300 font-medium">{accountName(b.account_login)}</span>{b.account_login === null && ' · pick an account at launch'}</p>

                <div className="mt-auto pt-4 flex flex-wrap items-center gap-2">
                  {isNative ? (
                    sourceRequired ? (
                      <button className="btn-ghost flex-1 opacity-60 cursor-not-allowed" disabled><FileCode2 size={14} /> MQ5 Source Required</button>
                    ) : running ? (
                      <>
                        <button className="btn-danger flex-1" onClick={async () => {
                          try { await botControl(b.id, 'stop'); pushToast('info', `${b.name} stopped`, 'Native scanner stopped. Existing open trades are not force-closed.'); await refresh(true); }
                          catch (e) { pushToast('error', 'Stop failed', e instanceof Error ? e.message : undefined); }
                        }}><Settings2 size={14} /> Stop Native Bot</button>
                        <button className="btn-ghost !px-3" title="Configure native preset" onClick={() => setConfigBot(b)}><Settings2 size={15} /></button>
                      </>
                    ) : (
                      <button className="btn-primary flex-1" onClick={() => setConfigBot(b)}><Play size={14} /> Start Native Bot</button>
                    )
                  ) : ['stopped', 'error', 'worker_offline'].includes(b.status) ? (
                    <button className="btn-primary flex-1" onClick={() => setConfigBot(b)}><Play size={14} /> Start Bot</button>
                  ) : (
                    <button className="btn-ghost flex-1" onClick={() => setConfigBot(b)}><Settings2 size={14} /> Configure</button>
                  )}
                  {!isCatalog && <button className="btn-ghost !px-3" title="Upload or update actual EA file" onClick={() => setFileTarget(b)}><FileCode2 size={15} /></button>}
                  <Link className="btn-ghost !px-3" to={`/mt5/bots/${b.id}`} title="View performance"><BarChart3 size={15} /></Link>
                  {!isCatalog && <button className="btn-icon hover:!text-loss-400" title="Delete custom bot" onClick={() => setRemoveTarget(b)}><Trash2 size={15} /></button>}
                </div>
                </div>
              </Panel>
            );
          })}
        </div>
      )}

      <BotConfigModal bot={configBot} open={configBot !== null} onClose={() => setConfigBot(null)} />
      <AddBotModal open={addOpen} onClose={() => setAddOpen(false)} />
      <UpdateEaModal bot={fileTarget} open={fileTarget !== null} onClose={() => setFileTarget(null)} />

      <ConfirmModal
        open={removeTarget !== null}
        onClose={() => setRemoveTarget(null)}
        title={`Delete ${removeTarget?.name}?`}
        tone="danger"
        confirmLabel="Delete Bot"
        message={<>The custom catalog entry and configuration metadata will be removed. Historical trades remain in history.</>}
        onConfirm={async () => {
          if (!removeTarget) return;
          try { await deleteBot(removeTarget.id); pushToast('info', 'Bot deleted', removeTarget.name); await refresh(true); }
          catch (e) { pushToast('error', 'Delete failed', e instanceof Error ? e.message : undefined); }
        }}
      />
    </div>
  );
}

function UpdateEaModal({ bot, open, onClose }: { bot: Mt5Bot | null; open: boolean; onClose: () => void }) {
  const { pushToast, refresh } = useHub();
  const [eaFilename, setEaFilename] = useState('');
  const [presetFilename, setPresetFilename] = useState('');
  const [dllRequired, setDllRequired] = useState(false);
  const [version, setVersion] = useState('1.0.0');
  const [eaFile, setEaFile] = useState<File | null>(null);
  const [presetFile, setPresetFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!bot || !open) return;
    setEaFilename(bot.ea_filename || '');
    setPresetFilename(bot.preset_filename || '');
    setDllRequired(Boolean(bot.dll_required));
    setVersion(bot.version || '1.0.0');
    setEaFile(null);
    setPresetFile(null);
    setError('');
  }, [bot, open]);

  const onEaFile = (file?: File) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.ex5')) { setError('EA files must use the .ex5 extension.'); return; }
    setError(''); setEaFilename(file.name); setEaFile(file);
  };
  const onPreset = (file?: File) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.set')) { setError('Preset files must use the .set extension.'); return; }
    setError(''); setPresetFilename(file.name); setPresetFile(file);
  };

  if (!bot) return null;
  const save = async () => {
    if (!eaFilename.toLowerCase().endsWith('.ex5')) { setError('Choose a valid .ex5 filename before saving.'); return; }
    setBusy(true); setError('');
    try {
      if (!isSimulation && (eaFile || presetFile)) {
        await mt5BotService.uploadFiles(bot.id, eaFile, presetFile);
      }
      await botControl(bot.id, 'update', {
        ea_filename: eaFilename,
        preset_filename: presetFilename || null,
        dll_required: dllRequired,
        version: version.trim() || bot.version,
        file_status: isSimulation ? 'metadata-only' : (eaFile ? 'ready' : bot.file_status || 'missing'),
        upload_date: new Date().toISOString(),
      });
      pushToast(
        'success',
        isSimulation ? 'EA metadata updated' : 'EA files saved',
        isSimulation
          ? `${bot.name}: filename metadata saved. Simulation mode never executes the file.`
          : `${bot.name}: ${eaFile ? eaFile.name + ' uploaded to the local MT5 bridge' : 'metadata updated'}${presetFile ? ' with ' + presetFile.name : ''}.`
      );
      await refresh(true); onClose();
    } catch (err) { setError(err instanceof Error ? err.message : 'Update failed.'); }
    finally { setBusy(false); }
  };

  return (
    <Modal open={open} onClose={busy ? () => {} : onClose} title={`Update ${bot.name}`} sub={isSimulation ? 'Update EA metadata. Simulation mode never executes files.' : 'Upload the actual .ex5/.set files into the local MT5 bridge library.'} wide>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="sm:col-span-2 rounded-xl border border-warn-400/20 bg-warn-400/[0.05] px-4 py-3 text-[11px] text-slate-400">{isSimulation ? 'Simulation security: only filenames and metadata are retained. Switch to real bridge mode to upload the actual file bytes.' : 'The selected .ex5/.set file is copied into the local bridge EA library. Uploading does not grant DLL permission and does not execute the EA by itself.'}</div>
        <div><label className="label">Replace EA (.ex5)</label><input className="input" type="file" accept=".ex5" onChange={(e) => onEaFile(e.target.files?.[0])} /><p className="mt-1 text-[10px] text-slate-600">Registered: {eaFilename || bot.ea_filename || 'none'}</p></div>
        <div><label className="label">Replace preset (.set)</label><input className="input" type="file" accept=".set" onChange={(e) => onPreset(e.target.files?.[0])} /><p className="mt-1 text-[10px] text-slate-600">Registered: {presetFilename || 'none'}</p></div>
        <div><label className="label">Version</label><input className="input mono" value={version} onChange={(e) => setVersion(e.target.value)} /></div>
        <label className="flex items-center gap-3 rounded-xl bg-white/[0.03] border border-white/[0.06] px-4 py-3 cursor-pointer"><input type="checkbox" checked={dllRequired} onChange={(e) => setDllRequired(e.target.checked)} /><span><span className="block text-[12px] font-semibold text-slate-200">DLL required by EA metadata</span><span className="block text-[10px] text-slate-600">Does not grant DLL permission.</span></span></label>
        {error && <div className="sm:col-span-2 rounded-xl border border-loss-500/30 bg-loss-500/10 px-4 py-3"><p className="text-xs text-loss-300">{error}</p></div>}
        <div className="sm:col-span-2 flex justify-end gap-2.5"><button className="btn-ghost" onClick={onClose} disabled={busy}>Cancel</button><button className="btn-primary" onClick={save} disabled={busy}>{busy ? <Spinner size={14} /> : <FileCode2 size={15} />}{busy ? 'Saving…' : 'Update EA'}</button></div>
      </div>
    </Modal>
  );
}

function AddBotModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { pushToast, refresh } = useHub();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [eaFile, setEaFile] = useState<File | null>(null);
  const [presetFile, setPresetFile] = useState<File | null>(null);
  const [form, setForm] = useState({
    name: '', description: '', strategy: 'Custom EA', symbol: 'EURUSD', timeframe: 'M15', version: '1.0.0',
    ea_filename: '', preset_filename: '', dll_required: false,
  });

  const onEaFile = (file?: File) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.ex5')) { setError('EA files must use the .ex5 extension.'); return; }
    setError('');
    setEaFile(file);
    setForm((f) => ({ ...f, ea_filename: file.name, name: f.name || file.name.replace(/\.ex5$/i, '') }));
  };
  const onPreset = (file?: File) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.set')) { setError('Preset files must use the .set extension.'); return; }
    setError('');
    setPresetFile(file);
    setForm((f) => ({ ...f, preset_filename: file.name }));
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) { setError('Bot name is required.'); return; }
    if (!eaFile) { setError('Choose the .ex5 EA file you want to add.'); return; }
    setError(''); setBusy(true);
    try {
      const created = await createBot({ ...form, file_status: isSimulation ? 'metadata-only' : 'missing' });
      if (!isSimulation) await mt5BotService.uploadFiles(created.id, eaFile, presetFile);
      pushToast(
        'success',
        isSimulation ? 'EA registered in simulation' : 'EA uploaded',
        isSimulation ? `${form.name} metadata was added. Actual bytes are not retained in simulation.` : `${eaFile.name} was saved to the local MT5 bridge EA library.`
      );
      await refresh(true);
      setForm({ name: '', description: '', strategy: 'Custom EA', symbol: 'EURUSD', timeframe: 'M15', version: '1.0.0', ea_filename: '', preset_filename: '', dll_required: false });
      setEaFile(null); setPresetFile(null);
      onClose();
    } catch (err) { setError(err instanceof Error ? err.message : 'Import failed.'); }
    finally { setBusy(false); }
  };

  return (
    <Modal open={open} onClose={busy ? () => {} : onClose} title="Upload MT5 Bot" sub={isSimulation ? 'Register a bot in simulation mode.' : 'Upload the actual .ex5 file and optional .set preset to the local MT5 bridge.'} wide>
      <form onSubmit={submit} className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="sm:col-span-2 rounded-xl border border-warn-400/20 bg-warn-400/[0.05] px-4 py-3 text-[11px] text-slate-400">
          {isSimulation ? 'Simulation mode keeps only file metadata. Start the Hub with the real MT5 bridge to store the actual .ex5 file.' : 'The actual file is sent only to your local bridge on 127.0.0.1 and stored in its EA library. It is not automatically executed just because it was uploaded.'}
        </div>
        <div><label className="label">EA file (.ex5)</label><input className="input" type="file" accept=".ex5" onChange={(e) => onEaFile(e.target.files?.[0])} /><p className="mt-1 text-[10px] text-slate-600">Selected: {form.ea_filename || 'none'}</p></div>
        <div><label className="label">Preset (.set) optional</label><input className="input" type="file" accept=".set" onChange={(e) => onPreset(e.target.files?.[0])} /><p className="mt-1 text-[10px] text-slate-600">Selected: {form.preset_filename || 'none'}</p></div>
        <div><label className="label">Bot name</label><input className="input" placeholder="My EA" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
        <div><label className="label">Version</label><input className="input mono" value={form.version} onChange={(e) => setForm({ ...form, version: e.target.value })} /></div>
        <div><label className="label">Default symbol</label><MarketSelect compact tradeOnly value={form.symbol} onChange={(symbol) => setForm({ ...form, symbol })} /></div>
        <div><label className="label">Default timeframe</label><select className="input" value={form.timeframe} onChange={(e) => setForm({ ...form, timeframe: e.target.value })}>{TIMEFRAMES.map((t) => <option key={t}>{t}</option>)}</select></div>
        <div className="sm:col-span-2"><label className="label">Description (optional)</label><textarea className="input min-h-[72px] resize-none" placeholder="Leave blank to keep strategy information neutral." value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
        <label className="sm:col-span-2 flex items-center gap-3 rounded-xl bg-white/[0.03] border border-white/[0.06] px-4 py-3 cursor-pointer"><input type="checkbox" checked={form.dll_required} onChange={(e) => setForm({ ...form, dll_required: e.target.checked })} /><span><span className="block text-[12px] font-semibold text-slate-200">EA metadata says DLL access is required</span><span className="block text-[10px] text-slate-600">DLL access remains disabled until a future worker explicitly allows it.</span></span></label>
        {error && <div className="sm:col-span-2 rounded-xl border border-loss-500/30 bg-loss-500/10 px-4 py-3"><p className="text-xs text-loss-300">{error}</p></div>}
        <div className="sm:col-span-2 flex justify-end gap-2.5"><button type="button" className="btn-ghost" onClick={onClose} disabled={busy}>Cancel</button><button type="submit" className="btn-primary" disabled={busy}>{busy ? <Spinner size={14} /> : <Plus size={15} />}{busy ? 'Uploading…' : isSimulation ? 'Register EA' : 'Upload EA'}</button></div>
      </form>
    </Modal>
  );
}
