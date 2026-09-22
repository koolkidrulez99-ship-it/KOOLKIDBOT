import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowDown, ArrowUp, ArrowRightLeft, Crosshair, Gauge, History as HistoryIcon, Info } from 'lucide-react';
import { useHub } from '../context/HubContext';
import { MARKET, SYMBOL_LIST, marginFor, pipValue } from '../lib/market';
import { fmtDateTime, fmtPrice, fmtSigned, fmtUSD, profitTone } from '../lib/format';
import { Badge, PageHeader, Panel, Spinner, Toggle } from '../components/ui';
import { openTrade } from '../lib/actions';
import type { Mt5HistoryRow, Mt5Quote, Mt5SymbolInfo } from '../types';
import { mt5HistoryService } from '../services/mt5HistoryService';
import { mt5MarketService } from '../services/mt5MarketService';
import { isSimulation } from '../config/runtime';
import MarketSelect from '../components/MarketSelect';
import { usePersistentState } from '../hooks/usePersistentState';
import Modal from '../components/Modal';
import ConfirmModal from '../components/ConfirmModal';
import { mt5MultiAccountService, type MultiAccount } from '../services/mt5MultiAccountService';

interface ExecutionLatencySample {
  at: number;
  accounts: number;
  clickToBackendMs: number;
  backendToWorkerMs: number;
  orderSendMs: number;
  confirmMs: number;
  backendTotalMs: number;
  uiTotalMs: number;
  fillSpreadMs: number;
}

function avg(values: number[]) {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
}

function diffMs(later: unknown, earlier: unknown) {
  const end = Number(later || 0);
  const start = Number(earlier || 0);
  return end > 0 && start > 0 && end >= start ? (end - start) * 1000 : 0;
}

export default function ManualTradePage() {
  const { accounts, activeAccount, market, livePrice, liveQuote, pushToast, refresh, refreshPositions } = useHub();
  const connected = useMemo(() => accounts.filter((a) => a.status === 'connected'), [accounts]);

  const [login, setLogin] = usePersistentState<number | ''>('manual_account_login', '');
  const [symbol, setSymbol] = usePersistentState('manual_symbol', 'XAUUSD');
  const [side, setSide] = usePersistentState<'buy' | 'sell'>('manual_side', 'buy');
  const [volume, setVolume] = usePersistentState('manual_volume', '0.10');
  const [useProtection, setUseProtection] = usePersistentState('manual_protection', true);
  const [sl, setSl] = usePersistentState('manual_sl', '');
  const [tp, setTp] = usePersistentState('manual_tp', '');
  const [latencySamples, setLatencySamples] = usePersistentState<ExecutionLatencySample[]>('manual_execution_latency_ms', []);
  const [busy, setBusy] = useState(false);
  const [manualHistory, setManualHistory] = useState<Mt5HistoryRow[]>([]);
  const [selectedBridgeQuote, setSelectedBridgeQuote] = useState<Mt5Quote | null>(null);
  const [selectedAccountSymbols, setSelectedAccountSymbols] = useState<Mt5SymbolInfo[]>([]);
  const [symbolsLoading, setSymbolsLoading] = useState(false);
  const [copyOpen, setCopyOpen] = useState(false);
  const [multiAccounts, setMultiAccounts] = useState<MultiAccount[]>([]);
  const [configuredSlaves, setConfiguredSlaves] = useState<string[]>([]);
  const [selectedSlaves, setSelectedSlaves] = useState<string[]>([]);
  const [copyLotMode, setCopyLotMode] = useState<'same' | 'fixed' | 'multiplier'>('same');
  const [copyLotValue, setCopyLotValue] = useState('1.00');
  const [liveConfirmOpen, setLiveConfirmOpen] = useState(false);
  const [pendingLiveSlaves, setPendingLiveSlaves] = useState<string[]>([]);
  const routingRef = useRef(false);
  const acc = connected.find((account) => Number(account.login) === Number(login)) || null;
  const latestLatency = latencySamples[0] || null;
  const medianLatency = useMemo(() => {
    if (!latencySamples.length) return 0;
    const values = latencySamples.map((sample) => sample.uiTotalMs).filter((value) => Number.isFinite(value)).sort((a, b) => a - b);
    if (!values.length) return 0;
    const mid = Math.floor(values.length / 2);
    return values.length % 2 ? values[mid] : (values[mid - 1] + values[mid]) / 2;
  }, [latencySamples]);

  useEffect(() => {
    if (acc) return;
    const def = activeAccount && activeAccount.status === 'connected' ? activeAccount : connected[0];
    if (def) setLogin(Number(def.login));
    else if (login !== '') setLogin('');
  }, [acc, connected, activeAccount, login]);

  const loadManual = () => {
    mt5HistoryService.list()
      .then((rows) => setManualHistory(rows.filter((r) => r.source === 'Manual').slice(0, 6)))
      .catch(() => setManualHistory([]));
  };
  useEffect(loadManual, []);

  useEffect(() => {
    if (isSimulation) return;
    Promise.all([mt5MultiAccountService.accounts(), mt5MultiAccountService.copyStatus()]).then(([accountData, copyData]) => {
      const rows = accountData.accounts || [];
      const selectedMasterId = rows.find((row) => Number(row.login) === Number(acc?.login))?.account_id || '';
      const groups = (copyData.groups || {}) as Record<string, { config?: { master_account_id?: string; slave_account_ids?: string[] } | null }>;
      const matchingGroup = Object.values(groups).find((group) => group?.config?.master_account_id === selectedMasterId);
      const legacyConfig = (copyData.config || {}) as { master_account_id?: string; slave_account_ids?: string[] };
      const slaveIds = matchingGroup?.config?.slave_account_ids
        || (legacyConfig.master_account_id === selectedMasterId ? legacyConfig.slave_account_ids : [])
        || [];
      const slaves = slaveIds.filter((id) => rows.some((row) => row.account_id === id && row.connected));
      setMultiAccounts(rows);
      setConfiguredSlaves(slaves);
      setSelectedSlaves(slaves);
    }).catch(() => { setMultiAccounts([]); setConfiguredSlaves([]); setSelectedSlaves([]); });
  }, [accounts, acc?.login]);

  useEffect(() => {
    if (isSimulation || !acc) {
      setSelectedAccountSymbols([]);
      setSymbolsLoading(false);
      return;
    }
    let cancelled = false;
    setSymbolsLoading(true);
    mt5MarketService.symbols(acc.login)
      .then((rows) => {
        if (cancelled) return;
        const tradable = rows.filter((row) => row.trade_allowed);
        setSelectedAccountSymbols(tradable);
        if (tradable.some((row) => row.symbol === symbol)) return;
        const preferred = tradable.find((row) => row.symbol.toUpperCase() === 'XAUUSD')
          || tradable.find((row) => row.symbol.toUpperCase().startsWith('XAUUSD'))
          || tradable[0];
        if (preferred) setSymbol(preferred.symbol);
      })
      .catch(() => {
        if (!cancelled) setSelectedAccountSymbols([]);
      })
      .finally(() => {
        if (!cancelled) setSymbolsLoading(false);
      });
    return () => { cancelled = true; };
  }, [acc?.login]);



  useEffect(() => {
    if (isSimulation || !symbol || !acc) { setSelectedBridgeQuote(null); return; }
    let cancelled = false;
    let inFlight = false;
    const load = async () => {
      if (inFlight || document.hidden || busy) return;
      inFlight = true;
      try {
        const rows = await mt5MarketService.quotes([symbol], acc.login);
        if (!cancelled) setSelectedBridgeQuote(rows[0] || null);
      } catch {
        if (!cancelled) setSelectedBridgeQuote(null);
      } finally {
        inFlight = false;
      }
    };
    load();
    const id = window.setInterval(load, 2500);
    return () => { cancelled = true; window.clearInterval(id); };
  }, [symbol, acc?.login, busy]);

  const price = livePrice(symbol);
  const quote = selectedBridgeQuote || liveQuote(symbol);
  const meta = MARKET[symbol];
  const symbolInfo = selectedAccountSymbols.find((s) => s.symbol === symbol);
  const bid = quote?.bid || price;
  const ask = quote?.ask || (price + (meta?.pip || 0) * 2);
  const entryPrice = side === 'buy' ? ask : bid;
  const vol = Number(volume) || 0;
  const digits = quote?.digits ?? symbolInfo?.digits ?? meta?.digits ?? 5;
  const point = quote?.point || symbolInfo?.point || (meta ? meta.pip / (digits === 3 || digits === 5 ? 10 : 1) : 0);
  const pipSize = meta?.pip || (point ? point * (digits === 3 || digits === 5 ? 10 : 1) : 0);
  const contractSize = symbolInfo?.contract_size || meta?.contract || 0;
  const marginEst = acc && contractSize ? (entryPrice * contractSize * vol) / Math.max(1, acc.leverage) : (acc ? marginFor(symbol, price, vol, acc.leverage) : 0);
  const pipVal = meta ? pipValue(symbol, vol) : contractSize * pipSize * vol;

  const slNum = Number(sl);
  const tpNum = Number(tp);
  const slError = useProtection && sl && side === 'buy' && slNum >= entryPrice ? 'Stop loss must sit below entry for a BUY.'
    : useProtection && sl && side === 'sell' && slNum <= entryPrice ? 'Stop loss must sit above entry for a SELL.' : '';
  const tpError = useProtection && tp && side === 'buy' && tpNum <= entryPrice ? 'Take profit must sit above entry for a BUY.'
    : useProtection && tp && side === 'sell' && tpNum >= entryPrice ? 'Take profit must sit below entry for a SELL.' : '';

  const slPips = sl && pipSize ? Math.abs(entryPrice - slNum) / pipSize : 0;
  const tpPips = tp && pipSize ? Math.abs(tpNum - entryPrice) / pipSize : 0;

  const submit = async () => {
    if (!acc) {
      pushToast('error', 'No connected account', 'Connect an MT5 account first.');
      return;
    }
    const minVolume = isSimulation ? 0.01 : (symbolInfo?.volume_min || 0.01);
    const maxVolume = isSimulation ? 50 : (symbolInfo?.volume_max || 50);
    if (!vol || vol < minVolume || vol > maxVolume) {
      pushToast('error', 'Invalid volume', `Volume must be between ${minVolume} and ${maxVolume} lots.`);
      return;
    }
    if (slError || tpError) {
      pushToast('error', 'Check SL/TP', slError || tpError);
      return;
    }
    if (!isSimulation && configuredSlaves.length) {
      setCopyOpen(true);
      return;
    }
    await requestOrder([]);
  };

  const hasLiveTarget = (slaveIds: string[]) => {
    if (acc?.account_type === 'live') return true;
    return slaveIds.some((id) => {
      const multi = multiAccounts.find((row) => row.account_id === id);
      if (Number(multi?.account_info?.trade_mode) === 2) return true;
      const hub = accounts.find((row) => Number(row.login) === Number(multi?.login));
      return hub?.account_type === 'live';
    });
  };

  const requestOrder = async (slaveIds: string[]) => {
    if (!isSimulation && hasLiveTarget(slaveIds)) {
      setPendingLiveSlaves(slaveIds);
      setCopyOpen(false);
      setLiveConfirmOpen(true);
      return;
    }
    await executeOrder(slaveIds, false);
  };

  const executeOrder = async (slaveIds: string[], confirmLive = false) => {
    if (!acc || routingRef.current) return;
    routingRef.current = true;
    setBusy(true);
    setCopyOpen(false);
    const uiClickedAt = Date.now() / 1000;
    let timingDraft: Omit<ExecutionLatencySample, 'at' | 'uiTotalMs'> | null = null;
    try {
      const master = multiAccounts.find((row) => Number(row.login) === Number(acc.login) && row.connected);
      if (!isSimulation && master) {
        const targetIds = [master.account_id, ...slaveIds.filter((id) => id !== master.account_id)];
        const response = await mt5MultiAccountService.manualTrade({ target_account_ids: targetIds, symbol, side, volume: vol,
          sl: useProtection && sl ? slNum : 0, tp: useProtection && tp ? tpNum : 0, ui_clicked_at: uiClickedAt,
          lot_mode: copyLotMode, fixed_lot: copyLotMode === 'fixed' ? Math.max(0.01, Number(copyLotValue) || 0.01) : 0.01,
          multiplier: copyLotMode === 'multiplier' ? Math.max(0.01, Number(copyLotValue) || 1) : 1,
          confirm_live: confirmLive });
        const rows = Object.entries(response.results || {});
        const filled = rows.filter(([, row]) => row.ok);
        const failed = rows.filter(([, row]) => !row.ok);
        const elapsed = filled.map(([, row]) => Math.max(0, Number(row.timing?.backend_result_at || 0) - uiClickedAt) * 1000);
        const timingRows = filled.map(([, row]) => row.timing || {});
        const backendReceived = timingRows.map((timing) => Number(timing.backend_received_at || 0)).filter(Boolean);
        const backendResults = timingRows.map((timing) => Number(timing.backend_result_at || 0)).filter(Boolean);
        if (timingRows.length && backendResults.length) {
          timingDraft = {
            accounts: filled.length,
            clickToBackendMs: backendReceived.length ? diffMs(Math.min(...backendReceived), uiClickedAt) : 0,
            backendToWorkerMs: avg(timingRows.map((timing) => diffMs(timing.worker_received_at, timing.backend_received_at)).filter(Boolean)),
            orderSendMs: avg(timingRows.map((timing) => diffMs(timing.order_send_result_at, timing.order_send_started_at)).filter(Boolean)),
            confirmMs: avg(timingRows.map((timing) => diffMs(timing.position_confirmed_at, timing.order_send_result_at)).filter(Boolean)),
            backendTotalMs: diffMs(Math.max(...backendResults), uiClickedAt),
            fillSpreadMs: elapsed.length > 1 ? Math.max(...elapsed) - Math.min(...elapsed) : 0,
          };
        }
        const names = new Map(multiAccounts.map((row) => [row.account_id, row.nickname || `#${row.login}`]));
        const detail = rows.map(([id, row]) => `${names.get(id) || id}: ${row.ok ? `FILLED ${Math.round(Math.max(0, Number(row.timing?.backend_result_at || 0) - uiClickedAt) * 1000)}ms` : `FAILED ${row.error || 'Rejected'}`}`).join(' · ');
        if (filled.length) pushToast('success', `${filled.length} account order${filled.length === 1 ? '' : 's'} filled`, `${detail}${elapsed.length > 1 ? ` · fill spread ${(Math.max(...elapsed) - Math.min(...elapsed)).toFixed(1)}ms` : ''}`);
        if (failed.length) pushToast('error', `${failed.length} account order${failed.length === 1 ? '' : 's'} failed`, detail);
        console.info('KOOLKID MT5 execution timing', { ui_clicked_at: uiClickedAt, accounts: response.results });
      } else {
        await openTrade({ account_login: acc.login, symbol, type: side, volume: vol,
          sl: useProtection && sl ? slNum : null, tp: useProtection && tp ? tpNum : null, source: 'Manual', confirm_live: confirmLive });
        pushToast('success', `${side.toUpperCase()} ${vol.toFixed(2)} ${symbol} filled`, `Account ${acc.nickname} \u00b7 market execution.`);
      }
      setSl('');
      setTp('');
      // The order response is authoritative. Do not block the UI on a second
      // full Hub refresh before releasing the trade button and showing timing.
      const uiUpdatedAt = Date.now() / 1000;
      if (timingDraft) {
        const sample: ExecutionLatencySample = {
          ...timingDraft,
          at: Date.now(),
          uiTotalMs: diffMs(uiUpdatedAt, uiClickedAt),
        };
        setLatencySamples((previous) => [sample, ...previous].slice(0, 30));
      }
      console.info('KOOLKID MT5 UI updated', { ui_updated_at: uiUpdatedAt, ui_clicked_at: uiClickedAt });
      void refreshPositions();
      window.setTimeout(() => void refresh(true), 500);
      window.setTimeout(loadManual, 0);
    } catch (e) {
      pushToast('error', 'Order rejected', e instanceof Error ? e.message : undefined);
    } finally {
      routingRef.current = false;
      setBusy(false);
    }
  };

  return (
    <div>
      <Modal open={copyOpen} onClose={() => !busy && setCopyOpen(false)} title="Copy trade to slaves?" sub="The master and selected slaves will be dispatched concurrently." wide>
        <div className="flex items-center justify-between"><p className="label !mb-0">Slave accounts</p><button className="text-[11px] font-bold text-brand-300" onClick={() => setSelectedSlaves(configuredSlaves)}>SELECT ALL</button></div>
        <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2">
          {configuredSlaves.map((id) => { const account = multiAccounts.find((row) => row.account_id === id); return <label key={id} className="flex items-center gap-3 rounded-xl border border-white/[0.07] bg-white/[0.03] px-3 py-3 text-xs text-slate-300"><input type="checkbox" checked={selectedSlaves.includes(id)} onChange={(event) => setSelectedSlaves(event.target.checked ? [...selectedSlaves, id] : selectedSlaves.filter((value) => value !== id))} /><span><b className="block text-white">{account?.nickname || id}</b><span className="mono text-slate-500">#{account?.login || id}</span></span></label>; })}
        </div>
        <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3"><div><label className="label">Slave lot mode</label><select className="input" value={copyLotMode} onChange={(event) => setCopyLotMode(event.target.value as 'same' | 'fixed' | 'multiplier')}><option value="same">Same as master</option><option value="fixed">Fixed lot</option><option value="multiplier">Multiplier</option></select></div>{copyLotMode !== 'same' && <div><label className="label">{copyLotMode === 'fixed' ? 'Fixed slave lot' : 'Lot multiplier'}</label><input className="input mono" type="number" min="0.01" step="0.01" value={copyLotValue} onChange={(event) => setCopyLotValue(event.target.value)} /></div>}</div>
        <div className="mt-5 flex flex-col-reverse sm:flex-row sm:justify-end gap-2"><button className="btn-ghost justify-center" disabled={busy} onClick={() => requestOrder([])}>Master Only</button><button className="btn-primary justify-center" disabled={busy || !selectedSlaves.length} onClick={() => requestOrder(selectedSlaves)}><ArrowRightLeft size={14} /> Copy Trade</button></div>
      </Modal>

      <ConfirmModal
        open={liveConfirmOpen}
        onClose={() => setLiveConfirmOpen(false)}
        title="Place this order on a LIVE account?"
        tone="danger"
        confirmLabel="I Accept the Risk & Place Order"
        message={<>KOOLKID MT5 is still in its testing phase. LIVE accounts use real funds and losses can occur. Continue only if you accept that risk. By confirming, you choose to place this order at your own risk and understand that KOOLKID and its admin are not liable for any trading losses.</>}
        onConfirm={() => executeOrder(pendingLiveSlaves, true)}
      />
      <PageHeader title="Manual Trading" sub={isSimulation ? 'Simulation order ticket · no broker order is sent' : 'Discretionary execution through the authenticated MT5 bridge'} />

      <div className="grid grid-cols-1 xl:grid-cols-5 gap-4">
        {/* Order ticket */}
        <Panel className="xl:col-span-3 p-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="label">MT5 Account</label>
              <select className="input" value={login} onChange={(e) => setLogin(Number(e.target.value))}>
                {connected.length === 0 && <option value="">No connected accounts</option>}
                {connected.map((a) => (
                  <option key={a.id} value={a.login}>
                    {a.nickname} &middot; #{a.login}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Symbol</label>
              <MarketSelect compact tradeOnly accountLogin={acc?.login} value={symbol} onChange={(next) => { setSymbol(next); setSl(''); setTp(''); }} />
            </div>
          </div>

          <div className="mt-5 rounded-2xl bg-black/30 border border-white/[0.07] p-5 flex items-center justify-between">
            <div>
              <p className="text-[10px] uppercase tracking-[0.18em] text-slate-600 font-bold">{isSimulation ? 'Simulated quote' : acc ? 'Live broker quote' : 'Account disconnected'} · {symbol}</p>
              <p className="mono text-3xl font-extrabold text-white mt-1">{acc && quote ? entryPrice.toFixed(digits) : '—'}</p>
            </div>
            <div className="text-right text-xs text-slate-500 space-y-1">
              <p>Bid <span className="mono text-slate-200">{acc && quote ? bid.toFixed(digits) : '—'}</span></p>
              <p>Ask <span className="mono text-slate-200">{acc && quote ? ask.toFixed(digits) : '—'}</span></p>
              <p>Spread <span className="mono text-slate-200">{acc && quote ? `${quote.spread_points.toFixed(1)} pts` : '—'}</span></p>
            </div>
          </div>

          <label className="label mt-5">Side</label>
          <div className="grid grid-cols-2 gap-2.5">
            {(['buy', 'sell'] as const).map((s) => (
              <button
                key={s}
                disabled={!acc}
                onClick={() => { setSide(s); setSl(''); setTp(''); }}
                className={`rounded-xl py-3 text-sm font-extrabold uppercase tracking-wider transition-all cursor-pointer border ${
                  side === s
                    ? s === 'buy'
                      ? 'bg-gain-500 text-black border-gain-400 shadow-glow-gain'
                      : 'bg-loss-500 text-white border-loss-400 shadow-glow-loss'
                    : 'bg-white/[0.03] text-slate-500 border-white/10 hover:text-slate-300'
                }`}
              >
                {s === 'buy' ? <ArrowUp size={15} className="inline -mt-0.5 mr-1" /> : <ArrowDown size={15} className="inline -mt-0.5 mr-1" />}
                {s}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-5">
            <div>
              <label className="label">Volume (lots)</label>
              <div className="flex items-center gap-2">
                <button className="btn-ghost !px-3" aria-label="Decrease lot size" onClick={() => setVolume((v) => Math.max(0.01, Number(v) - 0.01).toFixed(2))}>-</button>
                <input className="input mono text-center" value={volume} onChange={(e) => setVolume(e.target.value)} inputMode="decimal" />
                <button className="btn-ghost !px-3" aria-label="Increase lot size" onClick={() => setVolume((v) => Math.min(50, Number(v) + 0.01).toFixed(2))}>+</button>
              </div>
              <div className="mt-2 flex gap-1">
                {['0.01', '0.05', '0.10', '0.25', '0.50', '1.00'].map((v) => (
                  <button
                    key={v}
                    onClick={() => setVolume(v)}
                    className={`flex-1 rounded-lg py-1 mono text-[10px] font-bold cursor-pointer transition-colors ${
                      volume === v ? 'bg-brand-600 text-white' : 'bg-white/[0.05] text-slate-500 hover:text-white'
                    }`}
                  >
                    {v}
                  </button>
                ))}
              </div>
            </div>
            <div className="md:col-span-2">
              <div className="flex items-center justify-between mb-1.5">
                <label className="label !mb-0">Protection (SL / TP)</label>
                <Toggle on={useProtection} onChange={setUseProtection} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <input
                    className={`input mono ${slError ? '!border-loss-500/60' : ''}`}
                    placeholder={`Stop loss (${digits}d)`}
                    value={sl}
                    onChange={(e) => setSl(e.target.value)}
                    inputMode="decimal"
                    disabled={!useProtection}
                  />
                  <p className="mt-1 text-[10px] text-slate-600">{useProtection && sl && !slError ? `${slPips.toFixed(1)} pips away \u00b7 -${fmtUSD(slPips * pipVal)}` : 'Max acceptable loss'}</p>
                  {slError && <p className="mt-1 text-[10px] text-loss-400">{slError}</p>}
                </div>
                <div>
                  <input
                    className={`input mono ${tpError ? '!border-loss-500/60' : ''}`}
                    placeholder={`Take profit (${digits}d)`}
                    value={tp}
                    onChange={(e) => setTp(e.target.value)}
                    inputMode="decimal"
                    disabled={!useProtection}
                  />
                  <p className="mt-1 text-[10px] text-slate-600">{useProtection && tp && !tpError ? `${tpPips.toFixed(1)} pips away \u00b7 +${fmtUSD(tpPips * pipVal)}` : 'Target exit'}</p>
                  {tpError && <p className="mt-1 text-[10px] text-loss-400">{tpError}</p>}
                </div>
              </div>
            </div>
          </div>

          <div className="mt-5 grid grid-cols-3 gap-3 text-center">
            <div className="rounded-xl bg-white/[0.03] border border-white/[0.06] py-2.5">
              <p className="text-[9px] uppercase tracking-widest text-slate-600 font-semibold">Est. margin</p>
              <p className="mono text-[13px] font-bold text-white mt-0.5">{fmtUSD(marginEst)}</p>
            </div>
            <div className="rounded-xl bg-white/[0.03] border border-white/[0.06] py-2.5">
              <p className="text-[9px] uppercase tracking-widest text-slate-600 font-semibold">Pip value</p>
              <p className="mono text-[13px] font-bold text-white mt-0.5">{fmtUSD(pipVal)}</p>
            </div>
            <div className="rounded-xl bg-white/[0.03] border border-white/[0.06] py-2.5">
              <p className="text-[9px] uppercase tracking-widest text-slate-600 font-semibold">Leverage</p>
              <p className="mono text-[13px] font-bold text-white mt-0.5">1:{acc?.leverage ?? '\u2014'}</p>
            </div>
          </div>

          <button
            onClick={submit}
            disabled={busy || !acc || !quote}
            className={`mt-5 w-full btn justify-center !rounded-xl !py-4 text-[15px] font-extrabold uppercase tracking-widest disabled:opacity-50 ${
              side === 'buy' ? 'bg-gain-500 hover:bg-gain-400 text-black shadow-glow-gain' : 'bg-loss-500 hover:bg-loss-400 text-white shadow-glow-loss'
            }`}
          >
            {busy ? <Spinner size={16} /> : <Crosshair size={16} />}
            {busy ? (isSimulation ? 'Simulating order…' : 'Routing order…') : `Place ${side} · ${vol.toFixed(2)} lots ${symbol}`}
          </button>
          <p className="mt-3 flex items-start gap-1.5 text-[11px] text-slate-600">
            <Info size={12} className="mt-px shrink-0" />
            {isSimulation ? 'Simulation only: the order is stored locally and does not reach a broker or MetaTrader terminal.' : 'Orders route through the configured authenticated MT5 bridge.'}
          </p>
        </Panel>

        {/* side column */}
        <div className="xl:col-span-2 space-y-4">
          <Panel className="p-5">
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-sm font-bold text-white flex items-center gap-2"><Gauge size={15} className="text-brand-300" /> Execution latency</h3>
              <Badge tone={latestLatency && latestLatency.uiTotalMs <= 250 ? 'gain' : latestLatency && latestLatency.uiTotalMs <= 750 ? 'warn' : latestLatency ? 'loss' : 'slate'}>
                {latestLatency ? `${Math.round(latestLatency.uiTotalMs)} MS` : 'NO SAMPLE'}
              </Badge>
            </div>
            {latestLatency ? (
              <>
                <div className="mt-4 grid grid-cols-3 gap-2 text-center">
                  <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] px-2 py-3">
                    <p className="text-[9px] uppercase tracking-widest text-slate-600 font-semibold">Latest</p>
                    <p className="mono mt-1 text-lg font-extrabold text-white">{Math.round(latestLatency.uiTotalMs)}<span className="ml-1 text-[10px] text-slate-500">ms</span></p>
                  </div>
                  <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] px-2 py-3">
                    <p className="text-[9px] uppercase tracking-widest text-slate-600 font-semibold">Median</p>
                    <p className="mono mt-1 text-lg font-extrabold text-white">{Math.round(medianLatency)}<span className="ml-1 text-[10px] text-slate-500">ms</span></p>
                  </div>
                  <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] px-2 py-3">
                    <p className="text-[9px] uppercase tracking-widest text-slate-600 font-semibold">Fill spread</p>
                    <p className="mono mt-1 text-lg font-extrabold text-white">{latestLatency.fillSpreadMs.toFixed(1)}<span className="ml-1 text-[10px] text-slate-500">ms</span></p>
                  </div>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-[11px]">
                  <div className="flex justify-between gap-3"><span className="text-slate-500">Click → backend</span><span className="mono text-slate-300">{latestLatency.clickToBackendMs.toFixed(1)} ms</span></div>
                  <div className="flex justify-between gap-3"><span className="text-slate-500">Backend → worker</span><span className="mono text-slate-300">{latestLatency.backendToWorkerMs.toFixed(1)} ms</span></div>
                  <div className="flex justify-between gap-3"><span className="text-slate-500">MT5 order_send</span><span className="mono text-slate-300">{latestLatency.orderSendMs.toFixed(1)} ms</span></div>
                  <div className="flex justify-between gap-3"><span className="text-slate-500">Position confirm</span><span className="mono text-slate-300">{latestLatency.confirmMs.toFixed(1)} ms</span></div>
                  <div className="flex justify-between gap-3"><span className="text-slate-500">Backend result</span><span className="mono text-slate-300">{latestLatency.backendTotalMs.toFixed(1)} ms</span></div>
                  <div className="flex justify-between gap-3"><span className="text-slate-500">UI updated</span><span className="mono text-slate-300">{latestLatency.uiTotalMs.toFixed(1)} ms</span></div>
                </div>
                <div className="mt-4 flex h-14 items-end gap-1 rounded-xl border border-white/[0.05] bg-black/20 px-2 py-2">
                  {latencySamples.slice(0, 16).reverse().map((sample, index, values) => {
                    const peak = Math.max(1, ...values.map((item) => item.uiTotalMs));
                    const height = Math.max(8, Math.round((sample.uiTotalMs / peak) * 100));
                    return <div key={`${sample.at}-${index}`} title={`${sample.uiTotalMs.toFixed(1)} ms`} className="flex-1 rounded-sm bg-brand-500/70" style={{ height: `${height}%` }} />;
                  })}
                </div>
                <p className="mt-2 text-[10px] text-slate-600">Real measured path: click → backend → worker → MT5 order_send → position confirmation → refreshed UI. Last {latencySamples.length} sample{latencySamples.length === 1 ? '' : 's'}.</p>
              </>
            ) : (
              <p className="mt-3 text-xs leading-relaxed text-slate-600">No real execution timing yet. The first routed MT5 order will populate Latest, Median, stage timings and copy fill spread.</p>
            )}
          </Panel>

          <Panel className="p-5">
            <h3 className="text-sm font-bold text-white">Watchlist</h3>
            <div className="mt-3 space-y-1.5">
              {SYMBOL_LIST.filter((s) => isSimulation || selectedAccountSymbols.some((x) => x.symbol === s)).map((s) => {
                const p = market[s] ?? MARKET[s].base;
                const chg = ((p - MARKET[s].base) / MARKET[s].base) * 100;
                return (
                  <button
                    key={s}
                    onClick={() => setSymbol(s)}
                    className={`w-full flex items-center justify-between rounded-xl px-3.5 py-2.5 text-left transition-colors cursor-pointer ${
                      symbol === s ? 'bg-brand-600/15 border border-brand-500/30' : 'bg-white/[0.02] border border-transparent hover:bg-white/[0.05]'
                    }`}
                  >
                    <div>
                      <p className="text-[13px] font-bold text-white">{s}</p>
                      <p className="text-[10px] text-slate-600">{MARKET[s].name}</p>
                    </div>
                    <div className="text-right">
                      <p className="mono text-[13px] font-bold text-white">{fmtPrice(p, s)}</p>
                      <p className={`mono text-[10px] ${chg >= 0 ? 'text-gain-400' : 'text-loss-400'}`}>{chg >= 0 ? '+' : ''}{chg.toFixed(2)}%</p>
                    </div>
                  </button>
                );
              })}
            </div>
          </Panel>

          <Panel className="p-5">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <HistoryIcon size={14} className="text-brand-300" /> Recent manual fills
            </h3>
            <div className="mt-3 space-y-2">
              {manualHistory.length === 0 && <p className="text-xs text-slate-600 py-3">No manual fills recorded yet.</p>}
              {manualHistory.map((r) => (
                <div key={r.id} className="flex items-center gap-2.5 rounded-xl bg-white/[0.03] border border-white/[0.05] px-3 py-2.5">
                  <Badge tone={r.type === 'buy' ? 'brand' : 'loss'}>{r.type}</Badge>
                  <div className="min-w-0 flex-1">
                    <p className="text-[12px] font-semibold text-white">{r.symbol} &middot; {Number(r.volume).toFixed(2)}</p>
                    <p className="text-[10px] text-slate-600">{fmtDateTime(r.close_time)}</p>
                  </div>
                  {(() => { const net = Number(r.net_pl ?? (Number(r.profit || 0) + Number(r.swap || 0) + Number(r.commission || 0))); return <p className={`mono text-[12px] font-bold ${profitTone(net)}`}>{fmtSigned(net)}</p>; })()}
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
