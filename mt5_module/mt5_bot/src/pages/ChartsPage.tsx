import { useEffect, useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, Cable, Crosshair, Layers, Radio, X } from 'lucide-react';
import { useHub } from '../context/HubContext';
import CandleChart from '../components/CandleChart';
import { MARKET, SYMBOL_LIST, TIMEFRAMES, TF_SECONDS, calcProfit } from '../lib/market';
import type { Timeframe } from '../lib/market';
import { fmtPrice, fmtSigned, profitTone } from '../lib/format';
import { Badge, PageHeader, Panel } from '../components/ui';
import { openTrade, closePosition } from '../lib/actions';
import { isSimulation } from '../config/runtime';
import { mt5MarketService } from '../services/mt5MarketService';
import type { Mt5Quote } from '../types';
import DerivAdvancedChart from '../components/DerivAdvancedChart';
import MarketSelect from '../components/MarketSelect';
import ConfirmModal from '../components/ConfirmModal';
import { usePersistentState } from '../hooks/usePersistentState';

export default function ChartsPage() {
  const { market, positions, livePrice, liveQuote, liveProfit, mt5Symbols, accounts, active, activeAccount, pushToast, refresh } = useHub();
  const [source, setSource] = usePersistentState<'mt5' | 'deriv'>('charts_source', 'mt5');
  const [symbol, setSymbol] = usePersistentState('mt5_chart_symbol', 'XAUUSD');
  const [tf, setTf] = usePersistentState<Timeframe>('mt5_chart_timeframe', 'M15');
  const [volume, setVolume] = useState('0.10');
  const [busy, setBusy] = useState<'buy' | 'sell' | null>(null);
  const [closingId, setClosingId] = useState<number | null>(null);
  const [selectedBridgeQuote, setSelectedBridgeQuote] = useState<Mt5Quote | null>(null);
  const [pendingLiveSide, setPendingLiveSide] = useState<'buy' | 'sell' | null>(null);

  const account = useMemo(() => {
    if (activeAccount && activeAccount.status === 'connected') return activeAccount;
    return accounts.find((a) => a.status === 'connected') || null;
  }, [accounts, activeAccount]);

  useEffect(() => {
    if (isSimulation || !mt5Symbols.length) return;
    if (mt5Symbols.some((s) => s.symbol === symbol && s.trade_allowed)) return;
    const preferred = mt5Symbols.find((s) => s.trade_allowed && s.symbol.toUpperCase() === 'XAUUSD')
      || mt5Symbols.find((s) => s.trade_allowed && s.symbol.toUpperCase().startsWith('XAUUSD'))
      || mt5Symbols.find((s) => s.trade_allowed);
    if (preferred) setSymbol(preferred.symbol);
  }, [mt5Symbols, symbol]);

  useEffect(() => {
    if (isSimulation || !symbol || !account) { setSelectedBridgeQuote(null); return; }
    let cancelled = false;
    const load = () => mt5MarketService.quotes([symbol], account.login).then((rows) => {
      if (!cancelled) setSelectedBridgeQuote(rows[0] || null);
    }).catch(() => { if (!cancelled) setSelectedBridgeQuote(null); });
    load();
    const id = window.setInterval(load, 1200);
    return () => { cancelled = true; window.clearInterval(id); };
  }, [symbol, account?.login]);

  const price = selectedBridgeQuote?.bid || livePrice(symbol);
  const meta = MARKET[symbol];
  const quote = selectedBridgeQuote || liveQuote(symbol);
  const spread = quote ? Math.max(0, quote.ask - quote.bid) : (meta ? meta.pip * 2 : 0);
  const askPrice = quote?.ask || (price + spread);
  const chgPct = meta ? ((price - meta.base) / meta.base) * 100 : 0;

  const symbolPositions = useMemo(() => positions.filter((p) => p.symbol === symbol), [positions, symbol]);

  const doTrade = async (type: 'buy' | 'sell', confirmLive = false) => {
    if (!account) {
      pushToast('error', 'No connected account', 'Connect an MT5 account before placing trades.');
      return;
    }
    const vol = Number(volume);
    if (!vol || vol < 0.01) {
      pushToast('error', 'Invalid volume', 'Volume must be at least 0.01 lots.');
      return;
    }
    setBusy(type);
    try {
      await openTrade({ account_login: account.login, symbol, type, volume: vol, source: 'Manual', confirm_live: confirmLive });
      pushToast('success', `${type.toUpperCase()} ${vol.toFixed(2)} ${symbol}`, `Filled on ${account.nickname} at market.`);
      await refresh(true);
    } catch (e) {
      pushToast('error', 'Order rejected', e instanceof Error ? e.message : undefined);
    } finally {
      setBusy(null);
    }
  };

  const trade = (type: 'buy' | 'sell') => {
    if (account?.account_type === 'live') {
      setPendingLiveSide(type);
      return;
    }
    void doTrade(type, false);
  };

  const close = async (id: number, ticket: number) => {
    setClosingId(id);
    try {
      const r = await closePosition(id);
      pushToast(r.profit >= 0 ? 'success' : 'warning', `Position #${ticket} closed`, `Realized ${fmtSigned(r.profit)}.`);
      await refresh(true);
    } catch (e) {
      pushToast('error', 'Close failed', e instanceof Error ? e.message : undefined);
    } finally {
      setClosingId(null);
    }
  };

  return (
    <div>
      <PageHeader title="Charts" sub={source === 'mt5' ? (isSimulation ? 'MT5 chart workspace · clearly labeled simulation feed' : 'MT5 chart workspace · quote feed must be supplied by the connected bridge') : 'Live Deriv market workspace · indicators, drawings and TradingView Advanced-ready datafeed'} />

      <Panel className="p-2 mb-4 inline-flex items-center gap-1">
        <button onClick={() => setSource('mt5')} className={`btn ${source === 'mt5' ? 'bg-brand-600 text-white' : 'btn-ghost'}`}><Cable size={14} /> MT5</button>
        <button onClick={() => setSource('deriv')} className={`btn ${source === 'deriv' ? 'bg-brand-600 text-white' : 'btn-ghost'}`}><Radio size={14} /> DERIV</button>
      </Panel>

      {source === 'deriv' ? <DerivAdvancedChart /> : (
      <div className="grid grid-cols-1 xl:grid-cols-4 gap-4">
        <div className="xl:col-span-3 space-y-4">
          {/* toolbar */}
          <Panel className="p-3 flex flex-wrap items-center gap-2">
            <MarketSelect value={symbol} onChange={setSymbol} accountLogin={account?.login} />
            <div className="flex flex-wrap gap-1.5">
              {SYMBOL_LIST.filter((s) => ['XAUUSD','EURUSD','GBPUSD','USDJPY','BTCUSD','Volatility 75 Index'].includes(s)).filter((s) => isSimulation || !mt5Symbols.length || mt5Symbols.some((x) => x.symbol === s)).map((s) => {
                const p = market[s] ?? MARKET[s].base;
                const chg = ((p - MARKET[s].base) / MARKET[s].base) * 100;
                return (
                  <button
                    key={s}
                    onClick={() => setSymbol(s)}
                    className={`rounded-lg px-3 py-1.5 text-left transition-colors cursor-pointer ${
                      symbol === s ? 'bg-brand-600 text-white shadow-glow-brand' : 'bg-white/[0.04] hover:bg-white/[0.08]'
                    }`}
                  >
                    <span className="block text-[11px] font-bold">{s}</span>
                    <span className={`mono block text-[9px] ${symbol === s ? 'text-brand-100' : chg >= 0 ? 'text-gain-400' : 'text-loss-400'}`}>
                      {chg >= 0 ? '+' : ''}{chg.toFixed(2)}%
                    </span>
                  </button>
                );
              })}
            </div>
            <div className="ml-auto flex gap-1.5">
              {TIMEFRAMES.map((t) => (
                <button
                  key={t}
                  onClick={() => setTf(t)}
                  className={`rounded-lg px-2.5 py-1.5 text-[11px] font-bold cursor-pointer transition-colors ${
                    tf === t ? 'bg-brand-600 text-white' : 'bg-white/[0.04] text-slate-400 hover:text-white'
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          </Panel>

          {/* chart */}
          <Panel className="p-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2 px-1 pb-3">
              <div>
                <span className="text-lg font-bold text-white">{symbol}</span>
                <span className="text-xs text-slate-500 ml-2">{mt5Symbols.find((s) => s.symbol === symbol)?.description || meta?.name}</span>
              </div>
              <div className="flex items-center gap-4 mono text-[13px]">
                <span className="text-slate-500">Bid <span className="text-white font-bold">{quote ? price.toFixed(quote.digits) : fmtPrice(price, symbol)}</span></span>
                <span className="text-slate-500">Ask <span className="text-white font-bold">{quote ? askPrice.toFixed(quote.digits) : fmtPrice(askPrice, symbol)}</span></span>
                <span className={chgPct >= 0 ? 'text-gain-400 font-bold' : 'text-loss-400 font-bold'}>
                  {chgPct >= 0 ? '+' : ''}{chgPct.toFixed(2)}%
                </span>
              </div>
            </div>
            <CandleChart symbol={symbol} tfSeconds={TF_SECONDS[tf]} livePrice={price} positions={symbolPositions} height={440} digitsOverride={quote?.digits} accountKey={active === 'all' ? 'all' : active} accountLabel={activeAccount?.nickname || (active === 'all' ? 'All accounts' : account?.nickname)} />
          </Panel>

          {/* positions on symbol */}
          <Panel className="p-4">
            <h3 className="text-sm font-bold text-white flex items-center gap-2 mb-3">
              <Layers size={14} className="text-brand-300" /> Open on {symbol}
              <span className="mono text-[11px] text-slate-500">{symbolPositions.length} ticket{symbolPositions.length === 1 ? '' : 's'}</span>
            </h3>
            {symbolPositions.length === 0 ? (
              <p className="text-xs text-slate-600 py-2">No open exposure on {symbol}.</p>
            ) : (
              <div className="space-y-2">
                {symbolPositions.map((p) => {
                  const pl = liveProfit(p);
                  return (
                    <div key={p.id} className="flex flex-wrap items-center gap-3 rounded-xl bg-white/[0.03] border border-white/[0.06] px-3.5 py-2.5">
                      <Badge tone={p.type === 'buy' ? 'brand' : 'loss'}>{p.type}</Badge>
                      <span className="mono text-xs text-slate-400">#{p.ticket}</span>
                      <span className="mono text-xs font-bold text-white">{Number(p.volume).toFixed(2)} lots</span>
                      <span className="mono text-xs text-slate-500">@ {fmtPrice(Number(p.open_price), p.symbol)}</span>
                      <span className={`mono text-xs font-bold ml-auto ${profitTone(pl)}`}>{fmtSigned(pl)}</span>
                      <button className="btn-icon !p-1.5 hover:!text-loss-400" disabled={closingId === p.id} onClick={() => close(p.id, p.ticket)} title="Close position">
                        <X size={14} />
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </Panel>
        </div>

        {/* quick trade side panel */}
        <Panel className="p-5 h-fit xl:sticky xl:top-24">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <Crosshair size={14} className="text-brand-300" /> Quick Order
          </h3>
          <p className="text-[11px] text-slate-500 mt-1">
            Executes on <span className="text-slate-300 font-medium">{account ? account.nickname : '\u2014'}</span>
          </p>

          <div className="mt-4 rounded-xl bg-black/30 border border-white/[0.07] p-3.5 text-center">
            <p className="mono text-2xl font-bold text-white">{quote ? price.toFixed(quote.digits) : fmtPrice(price, symbol)}</p>
            <p className={`mono text-[11px] mt-0.5 ${chgPct >= 0 ? 'text-gain-400' : 'text-loss-400'}`}>
              {chgPct >= 0 ? '+' : ''}{chgPct.toFixed(3)}% session
            </p>
          </div>

          <label className="label mt-4">Volume (lots)</label>
          <div className="flex items-center gap-2">
            <button className="btn-ghost !px-3" aria-label="Decrease lot size" onClick={() => setVolume((v) => Math.max(0.01, Number(v) - 0.01).toFixed(2))}>-</button>
            <input className="input mono text-center" value={volume} onChange={(e) => setVolume(e.target.value)} inputMode="decimal" />
            <button className="btn-ghost !px-3" aria-label="Increase lot size" onClick={() => setVolume((v) => Math.min(50, Number(v) + 0.01).toFixed(2))}>+</button>
          </div>
          <div className="mt-2 flex gap-1.5">
            {['0.01', '0.05', '0.10', '0.25', '0.50'].map((v) => (
              <button
                key={v}
                onClick={() => setVolume(v)}
                className={`flex-1 rounded-lg px-1 py-1 mono text-[10px] font-bold cursor-pointer transition-colors ${
                  volume === v ? 'bg-brand-600 text-white' : 'bg-white/[0.05] text-slate-500 hover:text-white'
                }`}
              >
                {v}
              </button>
            ))}
          </div>

          <div className="mt-4 grid grid-cols-2 gap-2.5">
            <button
              onClick={() => trade('buy')}
              disabled={busy !== null}
              className="btn justify-center !rounded-xl !py-3.5 bg-gain-500/90 hover:bg-gain-400 text-black font-extrabold disabled:opacity-50"
            >
              <ArrowUp size={16} strokeWidth={2.6} /> {busy === 'buy' ? 'BUYING\u2026' : 'BUY'}
            </button>
            <button
              onClick={() => trade('sell')}
              disabled={busy !== null}
              className="btn justify-center !rounded-xl !py-3.5 bg-loss-500/90 hover:bg-loss-400 text-white font-extrabold disabled:opacity-50"
            >
              <ArrowDown size={16} strokeWidth={2.6} /> {busy === 'sell' ? 'SELLING\u2026' : 'SELL'}
            </button>
          </div>

          <div className="mt-4 space-y-2 text-[11px] text-slate-500">
            <div className="flex justify-between"><span>Spread</span><span className="mono text-slate-300">{(spread / (meta?.pip || 1)).toFixed(1)} pips</span></div>
            <div className="flex justify-between"><span>Pip value ({Number(volume || 0).toFixed(2)} lots)</span><span className="mono text-slate-300">{fmtSigned(calcPipValue(symbol, Number(volume) || 0)).replace('$', '$')}</span></div>
            <div className="flex justify-between"><span>Contract size</span><span className="mono text-slate-300">{(mt5Symbols.find((s) => s.symbol === symbol)?.contract_size || meta?.contract || 0).toLocaleString()}</span></div>
          </div>
        </Panel>
      </div>
      )}

      <ConfirmModal
        open={pendingLiveSide !== null}
        onClose={() => setPendingLiveSide(null)}
        title="Place this order on a LIVE account?"
        tone="danger"
        confirmLabel="I Accept the Risk & Place Order"
        message={<>KOOLKID MT5 is still in its testing phase. LIVE accounts use real funds and losses can occur. Continue only if you accept that risk. By confirming, you choose to place this order at your own risk and understand that KOOLKID and its admin are not liable for any trading losses.</>}
        onConfirm={async () => {
          const side = pendingLiveSide;
          if (side) await doTrade(side, true);
        }}
      />
    </div>
  );
}

function calcPipValue(symbol: string, volume: number): number {
  const m = MARKET[symbol];
  if (!m) return 0;
  return m.mult * m.pip * volume;
}
