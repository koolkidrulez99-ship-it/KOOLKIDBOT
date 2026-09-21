import { useEffect, useMemo, useRef, useState } from 'react';
import Modal from './Modal';
import ConfirmModal from './ConfirmModal';
import MarketSelect from './MarketSelect';
import { Spinner, Toggle } from './ui';
import { useHub } from '../context/HubContext';
import { botControl } from '../lib/actions';
import { TIMEFRAMES } from '../lib/market';
import { Plus, Rocket, Save, X } from 'lucide-react';
import type { Mt5Bot } from '../types';
import type { Timeframe } from '../lib/market';
import { isSimulation } from '../config/runtime';
import NumberStepper from './NumberStepper';

export default function BotConfigModal({
  bot,
  open,
  onClose,
}: {
  bot: Mt5Bot | null;
  open: boolean;
  onClose: () => void;
}) {
  const { accounts, activeAccount, bridge, pushToast, refresh } = useHub();
  const eaLaunchAvailable = isSimulation || bridge?.capabilities?.ea_launch === true;
  const nativePreset = Boolean(bot?.native_engine);
  const nativeReady = !nativePreset || bot?.native_ready !== false;
  const launchAvailable = nativePreset ? nativeReady : eaLaunchAvailable;
  const availableAccounts = useMemo(
    () => nativePreset
      ? accounts.filter((account) => !account.read_only && account.access_mode !== 'investor')
      : accounts,
    [accounts, nativePreset],
  );

  const [accountLogin, setAccountLogin] = useState<number | ''>('');
  const [symbol, setSymbol] = useState('EURUSD');
  const [symbols, setSymbols] = useState<string[]>(['EURUSD']);
  const [marketMode, setMarketMode] = useState<'single' | 'multi'>('single');
  const [marketCandidate, setMarketCandidate] = useState('EURUSD');
  const [timeframe, setTimeframe] = useState<Timeframe>('M15');
  const [biasTimeframe, setBiasTimeframe] = useState<Timeframe>('H4');
  const [lot, setLot] = useState('0.01');
  const [risk, setRisk] = useState('2');
  const [maxSpread, setMaxSpread] = useState('3.5');
  const [maxDailyLoss, setMaxDailyLoss] = useState('250');
  const [maxOpenPositions, setMaxOpenPositions] = useState('3');
  const [multiTradeEnabled, setMultiTradeEnabled] = useState(false);
  const [maxConcurrentTrades, setMaxConcurrentTrades] = useState('1');
  const [tradingSession, setTradingSession] = useState('All Sessions');
  const [trailing, setTrailing] = useState(true);
  const [confirmLive, setConfirmLive] = useState(false);
  const [liveConfirmOpen, setLiveConfirmOpen] = useState(false);
  const [allowDll, setAllowDll] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const initializedBotId = useRef<number | null>(null);

  const isLaunch = bot?.status === 'stopped' || bot?.status === 'error' || bot?.status === 'worker_offline';
  const selectedAccount = accounts.find((account) => account.login === accountLogin) || null;

  useEffect(() => {
    if (!bot || !open) {
      initializedBotId.current = null;
      return;
    }
    if (initializedBotId.current === bot.id) return;
    initializedBotId.current = bot.id;
    const savedSymbols = (bot.symbols?.length ? bot.symbols : [bot.symbol]).filter(Boolean).slice(0, 10);
    const primarySymbol = savedSymbols[0] || bot.symbol || 'EURUSD';
    setSymbol(primarySymbol);
    setSymbols(savedSymbols.length ? savedSymbols : [primarySymbol]);
    setMarketCandidate(primarySymbol);
    setMarketMode(bot.market_mode === 'multi' || savedSymbols.length > 1 ? 'multi' : 'single');
    setTimeframe((TIMEFRAMES as readonly string[]).includes(bot.timeframe) ? (bot.timeframe as Timeframe) : 'M15');
    const bias = String(bot.bias_timeframe || 'H4').replace('+', ' ').split(' ')[0];
    setBiasTimeframe((TIMEFRAMES as readonly string[]).includes(bias) ? (bias as Timeframe) : 'H4');
    setLot(String(bot.lot_size ?? 0.01));
    setRisk(String(bot.settings?.risk_percent ?? 2));
    setMaxSpread(String(bot.settings?.max_spread ?? 3.5));
    setMaxDailyLoss(String(bot.settings?.max_daily_loss ?? 250));
    setMaxOpenPositions(String(bot.settings?.max_open_positions ?? 3));
    setMultiTradeEnabled(Boolean(bot.settings?.multi_trade_enabled ?? false));
    setMaxConcurrentTrades(String(bot.settings?.max_concurrent_trades ?? 1));
    setTradingSession(String(bot.settings?.trading_session ?? 'All Sessions'));
    setTrailing(Boolean(bot.settings?.trailing_stop ?? true));
    setConfirmLive(false);
    setAllowDll(false);
    const fallback = activeAccount?.login ?? availableAccounts[0]?.login;
    setAccountLogin(bot.account_login ?? fallback ?? '');
    setErrors([]);
  }, [bot, open, activeAccount, availableAccounts]);

  if (!bot) return null;

  const validatedPayload = (forStart = false, liveConfirmed = confirmLive) => {
    const errs: string[] = [];
    const effectiveSymbols = marketMode === 'multi' ? symbols : [symbol];
    if (marketMode === 'multi' && effectiveSymbols.length < 2) errs.push('Multi-market mode requires at least 2 markets.');
    if (effectiveSymbols.length > 10) errs.push('Choose no more than 10 markets.');
    const lotNum = Number(lot);
    if (!nativePreset && (!lotNum || lotNum < 0.01 || lotNum > 50)) errs.push('Lot size must be between 0.01 and 50.');
    const riskNum = Number(risk);
    if (!riskNum || riskNum <= 0 || riskNum > 20) errs.push('Risk per trade must be between 0.1% and 20%.');
    if (forStart && nativePreset && !nativeReady) errs.push('This preset needs its MQ5 source before native execution can be started.');
    const maxOpenNum = Number(maxOpenPositions);
    if (!maxOpenNum || maxOpenNum < 1 || maxOpenNum > 100) errs.push('Maximum open positions must be between 1 and 100.');
    const maxConcurrentNum = marketMode === 'multi' && multiTradeEnabled ? Number(maxConcurrentTrades) : 1;
    if (!maxConcurrentNum || maxConcurrentNum < 1 || maxConcurrentNum > Math.min(10, effectiveSymbols.length)) {
      errs.push(`Simultaneous trades must be between 1 and ${Math.min(10, effectiveSymbols.length)} for the selected markets.`);
    }
    if (!accountLogin) errs.push('Assign a connected MT5 account.');
    if (forStart && selectedAccount?.account_type === 'live' && !liveConfirmed) errs.push('Confirm the LIVE-account risk warning before starting this bot.');
    if (forStart && bot.dll_required && !allowDll) errs.push('This EA requires explicit DLL-import approval.');
    setErrors(errs);
    if (errs.length) return null;

    const settings = {
      ...bot.settings,
      risk_percent: riskNum,
      max_spread: Number(maxSpread) || 3.5,
      max_daily_loss: Number(maxDailyLoss) || 250,
      max_open_positions: maxOpenNum,
      multi_trade_enabled: marketMode === 'multi' && multiTradeEnabled,
      max_concurrent_trades: Math.max(1, Math.min(10, maxConcurrentNum)),
      trading_session: tradingSession,
      trailing_stop: trailing,
    };
    return {
      symbol: effectiveSymbols[0],
      symbols: effectiveSymbols,
      market_mode: effectiveSymbols.length > 1 ? 'multi' : 'single',
      timeframe,
      bias_timeframe: nativePreset ? biasTimeframe : undefined,
      lot_size: nativePreset ? (bot.lot_size || 0.01) : lotNum,
      account_login: accountLogin,
      settings,
      confirm_live: liveConfirmed,
      allow_dll: nativePreset ? false : allowDll,
    };
  };

  const save = async () => {
    const payload = validatedPayload();
    if (!payload) return;
    setBusy(true);
    try {
      await botControl(bot.id, 'update', payload);
      pushToast('success', `${bot.name} configuration saved`, 'Settings were saved. The bot was not started.');
      await refresh(true);
      onClose();
    } catch (e) {
      setErrors([e instanceof Error ? e.message : 'Command failed.']);
    } finally {
      setBusy(false);
    }
  };

  const doStart = async (liveConfirmed = confirmLive) => {
    const payload = validatedPayload(true, liveConfirmed);
    if (!payload) return;
    setBusy(true);
    try {
      await botControl(bot.id, 'update', payload);
      if (!launchAvailable) {
        pushToast('warning', `${bot.name} is not launchable`, nativePreset ? 'The MQ5 source is required before this built-in preset can run natively.' : 'Configuration saved. Automatic .ex5 attachment requires the MT5 EA worker; no bot was started.');
        await refresh(true);
        return;
      }
      await botControl(bot.id, 'launch', payload);
      const selectedMarkets = payload.symbols as string[];
      const marketLabel = selectedMarkets.length === 1 ? selectedMarkets[0] : `${selectedMarkets.length} markets`;
      pushToast(
        'success',
        `${bot.name} started`,
        nativePreset
          ? `${marketLabel} · native scanner · ${marketMode === 'multi' && multiTradeEnabled ? `${Math.max(1, Number(maxConcurrentTrades) || 1)} trade slots` : '1 trade slot'} · all markets keep scanning`
          : `${marketLabel} · ${timeframe} · ${selectedMarkets.length} isolated EA instance${selectedMarkets.length === 1 ? '' : 's'}`,
      );
      await refresh(true);
      onClose();
    } catch (e) {
      setErrors([e instanceof Error ? e.message : 'Start request failed.']);
    } finally {
      setBusy(false);
    }
  };

  const start = async () => {
    if (selectedAccount?.account_type === 'live' && !confirmLive) {
      setLiveConfirmOpen(true);
      return;
    }
    await doStart(confirmLive);
  };

  return (
    <>
    <Modal
      open={open}
      onClose={busy ? () => {} : onClose}
      title={isLaunch ? `Start ${bot.name}` : `Configure ${bot.name}`}
      sub={nativePreset
        ? `${bot.display_title || 'KOOLKID Native Strategy'} · server-side engine · ${bot.display_subtitle || 'source-derived trading rules'}`
        : isLaunch ? (isSimulation ? 'Assign account → bot → symbol → timeframe and start the bot simulation.' : eaLaunchAvailable ? 'Assign account → bot → symbol → timeframe and launch the uploaded EA through the worker.' : 'The Start Bot control is ready, but automatic .ex5 attachment requires an MT5 EA worker. Save the assignment now; KOOLKID will not pretend the EA started.') : (isSimulation ? 'Update simulation metadata and controls.' : 'Adjust engine parameters for the connected worker.')}
      wide
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="label">MT5 Account</label>
          <select className="input" value={accountLogin} onChange={(e) => { setAccountLogin(e.target.value ? Number(e.target.value) : ''); setConfirmLive(false); }}>
            <option value="">Select account...</option>
            {availableAccounts.map((a) => (
              <option key={a.id} value={a.login}>
                {a.nickname} &middot; #{a.login}
              </option>
            ))}
          </select>
          {availableAccounts.length === 0 && (
            <p className="mt-1.5 text-[11px] text-warn-400">No saved accounts - connect one from the Accounts page.</p>
          )}
        </div>
        <div className="sm:col-span-2">
          <div className="flex items-center justify-between gap-3">
            <label className="label mb-0">Markets</label>
            <span className="text-[10px] text-slate-500">{marketMode === 'multi' ? `${symbols.length}/10 selected` : '1 market'}</span>
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <button
              type="button"
              className={`rounded-xl border px-3 py-2 text-xs font-bold transition-colors ${marketMode === 'single' ? 'border-brand-500/50 bg-brand-500/10 text-brand-200' : 'border-white/[0.08] bg-white/[0.03] text-slate-400'}`}
              onClick={() => {
                setMarketMode('single');
                const next = symbols[0] || symbol;
                setSymbol(next);
                setSymbols([next]);
                setMarketCandidate(next);
              }}
            >
              Single Market
            </button>
            <button
              type="button"
              className={`rounded-xl border px-3 py-2 text-xs font-bold transition-colors ${marketMode === 'multi' ? 'border-brand-500/50 bg-brand-500/10 text-brand-200' : 'border-white/[0.08] bg-white/[0.03] text-slate-400'}`}
              onClick={() => {
                setMarketMode('multi');
                setSymbols((current) => current.includes(symbol) ? current : [symbol, ...current].slice(0, 10));
                setMarketCandidate(symbol);
              }}
            >
              Multi-Market (2–10)
            </button>
          </div>

          {marketMode === 'single' ? (
            <div className="mt-2">
              <MarketSelect
                value={symbol}
                onChange={(value) => { setSymbol(value); setSymbols([value]); setMarketCandidate(value); }}
                compact
                tradeOnly
                accountLogin={accountLogin ? Number(accountLogin) : undefined}
              />
            </div>
          ) : (
            <div className="mt-2 space-y-2">
              <div className="flex gap-2">
                <div className="min-w-0 flex-1">
                  <MarketSelect
                    value={marketCandidate}
                    onChange={setMarketCandidate}
                    compact
                    tradeOnly
                    accountLogin={accountLogin ? Number(accountLogin) : undefined}
                  />
                </div>
                <button
                  type="button"
                  className="btn-ghost shrink-0"
                  disabled={!marketCandidate || symbols.includes(marketCandidate) || symbols.length >= 10}
                  onClick={() => {
                    if (!marketCandidate || symbols.includes(marketCandidate) || symbols.length >= 10) return;
                    setSymbols((current) => [...current, marketCandidate].slice(0, 10));
                  }}
                >
                  <Plus size={14} /> Add
                </button>
              </div>
              <div className="flex min-h-9 flex-wrap gap-1.5 rounded-xl border border-white/[0.07] bg-white/[0.02] p-2">
                {symbols.map((market) => (
                  <button
                    key={market}
                    type="button"
                    className="inline-flex items-center gap-1 rounded-lg border border-brand-500/20 bg-brand-500/[0.08] px-2.5 py-1 text-[11px] font-semibold text-brand-100"
                    onClick={() => setSymbols((current) => current.filter((item) => item !== market))}
                    title={`Remove ${market}`}
                  >
                    {market}<X size={11} />
                  </button>
                ))}
                {symbols.length === 0 && <span className="px-1 py-1 text-[11px] text-slate-600">Add at least 2 markets.</span>}
              </div>
            </div>
          )}
          <p className="mt-1 text-[10px] text-slate-600">
            Markets come directly from the selected MT5 account. Native presets scan all selected markets from one engine; uploaded EAs run one isolated market instance per selection.
          </p>
          {nativePreset && marketMode === 'multi' && (
            <div className="mt-3 rounded-xl border border-white/[0.07] bg-white/[0.025] p-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-[12px] font-bold text-slate-200">Concurrent trades</p>
                  <p className="mt-0.5 text-[10px] text-slate-600">All selected markets keep scanning even when every trade slot is occupied.</p>
                </div>
                <Toggle on={multiTradeEnabled} onChange={setMultiTradeEnabled} />
              </div>
              <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => { setMultiTradeEnabled(false); setMaxConcurrentTrades('1'); }}
                  className={`rounded-lg border px-3 py-2 text-xs font-bold ${!multiTradeEnabled ? 'border-brand-500/50 bg-brand-500/10 text-brand-200' : 'border-white/[0.08] bg-white/[0.03] text-slate-400'}`}
                >
                  One trade total
                </button>
                <button
                  type="button"
                  onClick={() => { setMultiTradeEnabled(true); if (Number(maxConcurrentTrades) < 2) setMaxConcurrentTrades('2'); }}
                  className={`rounded-lg border px-3 py-2 text-xs font-bold ${multiTradeEnabled ? 'border-brand-500/50 bg-brand-500/10 text-brand-200' : 'border-white/[0.08] bg-white/[0.03] text-slate-400'}`}
                >
                  Multiple markets
                </button>
              </div>
              {multiTradeEnabled && (
                <div className="mt-3">
                  <label className="label">Maximum simultaneous trades</label>
                  <NumberStepper value={maxConcurrentTrades} onChange={setMaxConcurrentTrades} min={1} max={Math.max(1, Math.min(10, symbols.length))} step={1} decimals={0} />
                  <p className="mt-1 text-[10px] text-slate-600">Maximum one open position per selected market for this bot.</p>
                </div>
              )}
            </div>
          )}
        </div>
        <div>
          <label className="label">Timeframe</label>
          {nativePreset ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              <label>
                <span className="text-[10px] text-slate-600">Execution timeframe</span>
                <select className="input mono mt-1" value={timeframe} onChange={(e) => setTimeframe(e.target.value as Timeframe)}>
                  {TIMEFRAMES.map((tf) => <option key={tf} value={tf}>{tf}</option>)}
                </select>
              </label>
              <label>
                <span className="text-[10px] text-slate-600">Bias timeframe</span>
                <select className="input mono mt-1" value={biasTimeframe} onChange={(e) => setBiasTimeframe(e.target.value as Timeframe)}>
                  {TIMEFRAMES.map((tf) => <option key={tf} value={tf}>{tf}</option>)}
                </select>
              </label>
              <p className="sm:col-span-2 text-[10px] text-slate-600">Defaults come from the preset, but KOOLKID will run this start using your chosen execution and bias candles.</p>
            </div>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {TIMEFRAMES.map((tf) => (
                <button
                  key={tf}
                  type="button"
                  onClick={() => setTimeframe(tf)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-bold transition-colors cursor-pointer ${
                    timeframe === tf ? 'bg-brand-600 text-white shadow-glow-brand' : 'bg-white/[0.05] text-slate-400 hover:text-white'
                  }`}
                >
                  {tf}
                </button>
              ))}
            </div>
          )}
        </div>
        <div>
          <label className="label">{nativePreset ? 'Position size' : 'Lot size'}</label>
          {nativePreset ? <div className="input flex items-center justify-between"><span className="font-semibold text-slate-200">Automatic risk sizing</span><span className="text-[10px] text-slate-600">broker min/step enforced</span></div> : <NumberStepper value={lot} onChange={setLot} min={0.01} max={50} step={0.01} decimals={2} />}
        </div>
        <div>
          <label className="label">{nativePreset ? 'Risk cap (%)' : 'Risk per trade (%)'}</label>
          <NumberStepper value={risk} onChange={setRisk} min={0.1} max={20} step={0.1} decimals={1} />
          {nativePreset && <p className="mt-1 text-[10px] text-slate-600">KOOLKID will not exceed the source strategy risk or this lower user cap.</p>}
        </div>
        {!nativePreset && <>
          <div>
            <label className="label">Max spread (pips)</label>
            <input className="input mono" value={maxSpread} onChange={(e) => setMaxSpread(e.target.value)} inputMode="decimal" />
          </div>
          <div>
            <label className="label">Max daily loss ($)</label>
            <input className="input mono" value={maxDailyLoss} onChange={(e) => setMaxDailyLoss(e.target.value)} inputMode="decimal" />
          </div>
          <div>
            <label className="label">Maximum open positions</label>
            <NumberStepper value={maxOpenPositions} onChange={setMaxOpenPositions} min={1} max={100} step={1} decimals={0} />
          </div>
          <div>
            <label className="label">Trading session</label>
            <select className="input" value={tradingSession} onChange={(e) => setTradingSession(e.target.value)}>
              {['All Sessions', 'London', 'New York', 'Asia', 'London + New York'].map((session) => <option key={session}>{session}</option>)}
            </select>
          </div>
          <div className="flex items-end justify-between gap-3 rounded-xl bg-white/[0.03] border border-white/[0.07] px-4 py-3">
            <div>
              <p className="text-[13px] font-semibold text-slate-200">Trailing stop</p>
              <p className="text-[11px] text-slate-500">Lock in profit as price moves</p>
            </div>
            <Toggle on={trailing} onChange={setTrailing} />
          </div>
        </>}
      </div>

      {!isSimulation && nativePreset ? (
        <div className={`mt-4 rounded-xl border px-4 py-3 text-[11px] ${nativeReady ? 'border-brand-500/25 bg-brand-500/[0.05]' : 'border-warn-400/30 bg-warn-400/[0.07]'}`}>
          <p className={`font-bold ${nativeReady ? 'text-brand-200' : 'text-warn-300'}`}>{nativeReady ? 'KOOLKID Native Engine' : 'MQ5 Source Required'}</p>
          <p className="mt-1 text-slate-400">{nativeReady ? 'This built-in strategy runs on the KOOLKID server process and places orders through the authoritative 8002 MT5 account worker. It does not attach an EX5 to a chart and does not require the EA Worker.' : 'This preset stays locked until its MQ5 source is supplied. KOOLKID will not reverse-engineer or guess strategy logic from the compiled EX5.'}</p>
          {nativeReady && <p className="mt-1 text-slate-500">Source: <span className="mono text-slate-300">{bot.native_source || 'verified MQ5'}</span> · flow: <span className="mono text-slate-300">{bot.bias_timeframe || 'HTF'} → M5</span></p>}
        </div>
      ) : !isSimulation ? (
        <div className="mt-4 border-t border-white/[0.07] pt-3 text-[11px] text-slate-500">
          <p><span className="font-semibold text-slate-300">Compiled EX5 configuration:</span> account, symbol and timeframe are applied by MT5 at startup. The EA uses its compiled defaults unless an uploaded <span className="mono text-slate-300">.set</span> preset supplies its own input values.</p>
          <p className="mt-1">Lot, risk and Hub safety fields remain tracking settings unless that EA exposes matching inputs.</p>
          {bot.preset_analysis && <p className="mt-1.5 text-slate-300">Detected preset inputs: <span className="mono">{bot.preset_analysis.input_count ?? 0}</span></p>}
        </div>
      ) : null}

      {!isSimulation && !nativePreset && isLaunch && !eaLaunchAvailable && (
        <div className="mt-4 rounded-xl border border-warn-400/30 bg-warn-400/[0.08] px-4 py-3">
          <p className="text-xs font-bold text-warn-300">EA Worker Offline</p>
          <p className="text-[11px] text-slate-400 mt-1">{bridge?.ea_worker?.message || 'Start the local worker with START_KOOLKID.bat.'}</p>
        </div>
      )}

      {!isSimulation && selectedAccount?.account_type === 'live' && (
        <div className="mt-4 rounded-xl border border-loss-500/30 bg-loss-500/[0.08] px-4 py-3 text-xs text-slate-300">
          <p className="font-bold text-loss-300">LIVE account selected</p>
          <p className="mt-1 text-slate-400">Pressing Start will show a final risk confirmation before any bot is allowed to run on real funds.</p>
        </div>
      )}
      {!isSimulation && !nativePreset && bot.dll_required && <label className="mt-4 flex items-start gap-3 rounded-xl border border-warn-400/30 bg-warn-400/[0.08] px-4 py-3 text-xs text-slate-300"><input type="checkbox" checked={allowDll} onChange={(e) => setAllowDll(e.target.checked)} /><span>I explicitly approve DLL imports for this EA. The worker's DLL safety lock must also be enabled.</span></label>}

      {errors.length > 0 && (
        <div className="mt-4 rounded-xl border border-loss-500/30 bg-loss-500/10 px-4 py-3 space-y-1">
          {errors.map((e) => (
            <p key={e} className="text-xs text-loss-300">{e}</p>
          ))}
        </div>
      )}

      <div className="mt-6 flex justify-end gap-2.5">
        <button className="btn-ghost" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button className="btn-ghost" onClick={save} disabled={busy}>
          {busy ? <Spinner size={14} /> : <Save size={15} />} Save Config
        </button>
        {isLaunch && <button className="btn-primary" onClick={start} disabled={busy || (nativePreset && !nativeReady)}>
          {busy ? <Spinner size={14} /> : <Rocket size={15} />} {nativePreset ? (nativeReady ? 'Start Native Bot' : 'Source Required') : 'Start Bot'}
        </button>}
      </div>
    </Modal>

    <ConfirmModal
      open={liveConfirmOpen}
      onClose={() => setLiveConfirmOpen(false)}
      title="Start bot on a LIVE account?"
      tone="danger"
      confirmLabel="I Accept the Risk & Start"
      message={
        <>This bot is still in its testing phase. A LIVE MT5 account uses real funds and trading losses can occur. Continue only if you accept that risk. By confirming, you choose to run the bot at your own risk and understand that KOOLKID and its admin are not liable for any trading losses.</>
      }
      onConfirm={async () => {
        setConfirmLive(true);
        await doStart(true);
      }}
    />
    </>
  );
}
