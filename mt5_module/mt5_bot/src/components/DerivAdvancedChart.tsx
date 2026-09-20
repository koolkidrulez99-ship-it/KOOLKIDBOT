import { useEffect, useMemo, useRef, useState } from 'react';
import { createChart, ColorType, CrosshairMode } from 'lightweight-charts';
import type { IChartApi, ISeriesApi, CandlestickData, LineData, UTCTimestamp } from 'lightweight-charts';
import { Activity, Camera, FolderOpen, PenLine, Radio, RefreshCw, Save, Search, SlidersHorizontal } from 'lucide-react';
import { Badge, Panel } from './ui';
import { derivMarketService } from '../services/derivMarketService';
import { usePersistentState } from '../hooks/usePersistentState';
import type { Candle } from '../lib/market';
import type { DerivSymbol } from '../types';
import TradingViewAdvancedChart from './TradingViewAdvancedChart';
import { ChartMarkupOverlay, ChartMarkupToolbar, useChartMarkup } from './ChartMarkup';

const RESOLUTIONS = [
  { label: '1m', seconds: 60 }, { label: '2m', seconds: 120 }, { label: '5m', seconds: 300 }, { label: '15m', seconds: 900 },
  { label: '30m', seconds: 1800 }, { label: '1H', seconds: 3600 }, { label: '2H', seconds: 7200 }, { label: '4H', seconds: 14400 }, { label: '8H', seconds: 28800 }, { label: '1D', seconds: 86400 },
];

type Workspace = {
  symbol: string;
  seconds: number;
  chartStyle?: 'candles' | 'bars' | 'line' | 'area' | 'baseline' | 'heikin';
  ema9?: boolean;
  ema20?: boolean;
  ema50?: boolean;
  ema200?: boolean;
  bollinger?: boolean;
};

const SAVED_GRAPH_KEY = 'deriv_chart_saved_graph_v1';
function heikinAshi(data: Candle[]): Candle[] {
  let previousOpen = data[0]?.open ?? 0;
  let previousClose = data[0]?.close ?? 0;
  return data.map((c, index) => {
    const close = (c.open + c.high + c.low + c.close) / 4;
    const open = index === 0 ? (c.open + c.close) / 2 : (previousOpen + previousClose) / 2;
    const row = { ...c, open, close, high: Math.max(c.high, open, close), low: Math.min(c.low, open, close) };
    previousOpen = open; previousClose = close;
    return row;
  });
}

function ema(data: Candle[], period: number): LineData<UTCTimestamp>[] {
  if (!data.length) return [];
  const k = 2 / (period + 1);
  let value = data[0].close;
  return data.map((c, i) => {
    value = i === 0 ? c.close : c.close * k + value * (1 - k);
    return { time: c.time as UTCTimestamp, value };
  });
}

function bollinger(data: Candle[], period = 20, mult = 2) {
  const upper: LineData<UTCTimestamp>[] = [];
  const mid: LineData<UTCTimestamp>[] = [];
  const lower: LineData<UTCTimestamp>[] = [];
  for (let i = period - 1; i < data.length; i++) {
    const slice = data.slice(i - period + 1, i + 1).map((x) => x.close);
    const avg = slice.reduce((a, b) => a + b, 0) / period;
    const variance = slice.reduce((a, b) => a + (b - avg) ** 2, 0) / period;
    const sd = Math.sqrt(variance);
    const time = data[i].time as UTCTimestamp;
    mid.push({ time, value: avg }); upper.push({ time, value: avg + sd * mult }); lower.push({ time, value: avg - sd * mult });
  }
  return { upper, mid, lower };
}

function rsi(data: Candle[], period = 14): number | null {
  if (data.length <= period) return null;
  const closes = data.slice(-(period + 1)).map((c) => c.close);
  let gain = 0; let loss = 0;
  for (let i = 1; i < closes.length; i++) {
    const d = closes[i] - closes[i - 1];
    if (d >= 0) gain += d; else loss -= d;
  }
  if (loss === 0) return 100;
  const rs = (gain / period) / (loss / period);
  return 100 - 100 / (1 + rs);
}

function atr(data: Candle[], period = 14): number | null {
  if (data.length <= period) return null;
  const rows = data.slice(-(period + 1));
  let total = 0;
  for (let i = 1; i < rows.length; i++) {
    total += Math.max(rows[i].high - rows[i].low, Math.abs(rows[i].high - rows[i - 1].close), Math.abs(rows[i].low - rows[i - 1].close));
  }
  return total / period;
}

function macd(data: Candle[]): { macd: number; signal: number; histogram: number } | null {
  if (data.length < 35) return null;
  const fast = ema(data, 12); const slow = ema(data, 26);
  const diffs = fast.slice(-Math.min(fast.length, slow.length)).map((v, i, arr) => ({ time: v.time, value: v.value - slow[slow.length - arr.length + i].value }));
  if (!diffs.length) return null;
  const k = 2 / 10; let signal = diffs[0].value;
  for (let i = 1; i < diffs.length; i++) signal = diffs[i].value * k + signal * (1 - k);
  const value = diffs[diffs.length - 1].value;
  return { macd: value, signal, histogram: value - signal };
}

function groupSymbols(rows: DerivSymbol[]) {
  const map = new Map<string, DerivSymbol[]>();
  for (const s of rows) {
    const hint = `${s.market} ${s.subgroup || ''} ${s.submarket || ''} ${s.symbol_type || ''} ${s.name}`.toLowerCase();
    const group = hint.includes('forex') ? 'Forex'
      : ['synthetic','volatility','boom','crash','step','jump','range'].some((x) => hint.includes(x)) ? 'Synthetic / Volatility'
      : s.market ? s.market.replace(/_/g, ' ') : 'Other';
    if (!map.has(group)) map.set(group, []);
    map.get(group)!.push(s);
  }
  return [...map.entries()].map(([g, list]) => [g, list.sort((a, b) => a.name.localeCompare(b.name))] as const)
    .sort((a, b) => (a[0] === 'Synthetic / Volatility' ? -1 : b[0] === 'Synthetic / Volatility' ? 1 : a[0].localeCompare(b[0])));
}

function priceFormatForSymbol(rows: DerivSymbol[], symbol: string) {
  const pipSize = rows.find((s) => s.symbol === symbol)?.pip_size;
  let precision = 3;
  if (typeof pipSize === 'number' && Number.isFinite(pipSize) && pipSize > 0) {
    if (Number.isInteger(pipSize) && pipSize <= 8) {
      precision = pipSize;
    } else {
      const raw = String(pipSize);
      precision = raw.includes('e-') ? Number(raw.split('e-')[1]) : (raw.split('.')[1]?.length || precision);
    }
  }
  const priceDigits = Math.max(2, Math.min(8, precision));
  return { type: 'price' as const, precision: priceDigits, minMove: 1 / (10 ** priceDigits) };
}

function applyTickToCandles(prev: Candle[], quote: number, epoch: number, seconds: number) {
  const slot = Math.floor(epoch / seconds) * seconds;
  const last = prev[prev.length - 1];
  if (!last || slot > last.time) {
    return [...prev.slice(-999), { time: slot, open: last?.close ?? quote, high: quote, low: quote, close: quote, volume: 1 }];
  }
  if (slot === last.time) {
    return [...prev.slice(0, -1), { ...last, high: Math.max(last.high, quote), low: Math.min(last.low, quote), close: quote, volume: (last.volume || 0) + 1 }];
  }
  return prev;
}

export default function DerivAdvancedChart() {
  const wrapRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<any>(null);
  const candlesRef = useRef<Candle[]>([]);
  const needsInitialFitRef = useRef(true);
  const priceScaleFrozenRef = useRef(false);
  const extrasRef = useRef<Record<string, ISeriesApi<'Line'> | undefined>>({});
  const chartStyleRef = useRef<Workspace['chartStyle']>('candles');
  const [symbols, setSymbols] = useState<DerivSymbol[]>([]);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<'connecting' | 'live' | 'error'>('connecting');
  const [lastPrice, setLastPrice] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [reloadKey, setReloadKey] = useState(0);
  const [chartRevision, setChartRevision] = useState(0);
  const [historyRevision, setHistoryRevision] = useState(0);
  const [workspace, setWorkspace] = usePersistentState<Workspace>('deriv_chart_workspace', {
    symbol: 'R_75', seconds: 60, ema9: false, ema20: true, ema50: false, ema200: false, bollinger: false,
  });
  const [activeDerivLogin, setActiveDerivLogin] = useState<string>('unassigned');
  const markup = useChartMarkup('deriv', activeDerivLogin, workspace.symbol);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [chartEngine, setChartEngine] = usePersistentState<'builtin' | 'tradingview'>('deriv_chart_engine', 'builtin');
  const [officialReady, setOfficialReady] = useState(() => typeof window !== 'undefined' && Boolean((window as any).TradingView?.widget));
  const chartStyle = workspace.chartStyle || 'candles';

  useEffect(() => {
    chartStyleRef.current = chartStyle;
  }, [chartStyle]);

  useEffect(() => {
    if (officialReady || String(import.meta.env.VITE_TRADINGVIEW_ADVANCED || '') !== '1') return;
    const existing = document.querySelector<HTMLScriptElement>('script[data-koolkid-tradingview]');
    if (existing) {
      const onLoad = () => setOfficialReady(Boolean((window as any).TradingView?.widget));
      existing.addEventListener('load', onLoad);
      return () => existing.removeEventListener('load', onLoad);
    }
    const script = document.createElement('script');
    script.src = `${import.meta.env.BASE_URL || '/'}charting_library/charting_library.js`;
    script.async = true;
    script.dataset.koolkidTradingview = '1';
    script.onload = () => setOfficialReady(Boolean((window as any).TradingView?.widget));
    script.onerror = () => setOfficialReady(false);
    document.head.appendChild(script);
  }, [officialReady]);

  useEffect(() => {
    let cancelled = false;
    derivMarketService.accounts().then((rows) => {
      if (cancelled) return;
      const active = rows.find((row) => row.is_active) || rows.find((row) => row.status === 'connected') || rows[0];
      setActiveDerivLogin(active?.login ? String(active.login) : 'unassigned');
    }).catch(() => {
      if (!cancelled) setActiveDerivLogin('unassigned');
    });
    return () => { cancelled = true; };
  }, [reloadKey]);

  useEffect(() => {
    let cancelled = false;
    derivMarketService.activeSymbols().then((rows) => {
      if (cancelled) return;
      setSymbols(rows);
      if (!rows.some((s) => s.symbol === workspace.symbol) && rows[0]) setWorkspace((w) => ({ ...w, symbol: rows[0].symbol }));
    });
    return () => { cancelled = true; };
  }, [reloadKey]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let cancelled = false;
    let stop: (() => void) | undefined;
    needsInitialFitRef.current = true;
    priceScaleFrozenRef.current = false;
    candlesRef.current = [];
    chartRef.current?.priceScale('right').applyOptions({ autoScale: true });
    setStatus('connecting'); setError(''); setCandles([]); setLastPrice(null);
    const start = async () => {
      try {
        if (chartEngine === 'tradingview') {
          const unsubscribe = await derivMarketService.subscribeTicks(workspace.symbol, (tick) => {
            if (cancelled || !Number.isFinite(tick.quote)) return;
            setError('');
            setStatus('live');
            setLastPrice(tick.quote);
          });
          if (cancelled) unsubscribe();
          else stop = unsubscribe;
          return;
        }

        const rows = await derivMarketService.candles(workspace.symbol, workspace.seconds, 700);
        if (cancelled) return;
        candlesRef.current = rows;
        setCandles(rows);
        setHistoryRevision((x) => x + 1);
        setLastPrice(rows[rows.length - 1]?.close ?? null);
        setError('');
        setStatus('live');
        const unsubscribe = await derivMarketService.subscribeTicks(workspace.symbol, (tick) => {
          if (cancelled || !Number.isFinite(tick.quote) || !Number.isFinite(tick.epoch)) return;
          setError(''); setStatus('live'); setLastPrice(tick.quote);
          const next = applyTickToCandles(candlesRef.current, tick.quote, tick.epoch, workspace.seconds);
          if (next !== candlesRef.current) {
            candlesRef.current = next;
            const chart = chartRef.current;
            const cs = candleRef.current;
            if (chart && cs && chartEngine === 'builtin' && !needsInitialFitRef.current) {
              const style = chartStyleRef.current || 'candles';
              const source = style === 'heikin' ? heikinAshi(next) : next;
              const latest = source[source.length - 1];
              const visibleLogicalRange = chart.timeScale().getVisibleLogicalRange();
              if (latest) {
                if (['line', 'area', 'baseline'].includes(style)) {
                  cs.update({ time: latest.time as UTCTimestamp, value: latest.close });
                } else {
                  cs.update({ time: latest.time as UTCTimestamp, open: latest.open, high: latest.high, low: latest.low, close: latest.close });
                }
              }
              const extras = extrasRef.current;
              const ema9 = ema(next, 9).slice(-1)[0]; if (ema9) extras.ema9?.update(ema9);
              const ema20 = ema(next, 20).slice(-1)[0]; if (ema20) extras.ema20?.update(ema20);
              const ema50 = ema(next, 50).slice(-1)[0]; if (ema50) extras.ema50?.update(ema50);
              const ema200 = ema(next, 200).slice(-1)[0]; if (ema200) extras.ema200?.update(ema200);
              if (workspace.bollinger) {
                const bb = bollinger(next);
                const upper = bb.upper.slice(-1)[0]; if (upper) extras.bbUpper?.update(upper);
                const mid = bb.mid.slice(-1)[0]; if (mid) extras.bbMid?.update(mid);
                const lower = bb.lower.slice(-1)[0]; if (lower) extras.bbLower?.update(lower);
              }
              if (visibleLogicalRange) chart.timeScale().setVisibleLogicalRange(visibleLogicalRange);
            }
            setCandles(next);
          }
        });
        if (cancelled) unsubscribe();
        else stop = unsubscribe;
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : 'Deriv market feed unavailable.'); setStatus('error');
      }
    };
    start();
    return () => { cancelled = true; stop?.(); };
  }, [workspace.symbol, workspace.seconds, reloadKey, chartEngine]);

  // Build the chart only when layout/tools change. Live candles are updated in the next effect,
  // avoiding the old behavior that recreated the whole chart on every incoming tick.
  useEffect(() => {
    const el = wrapRef.current;
    if (!el || chartEngine !== 'builtin') return;
    priceScaleFrozenRef.current = false;
    const chart = createChart(el, {
      autoSize: true,
      height: 545,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#68738c', fontFamily: 'JetBrains Mono, monospace', fontSize: 10, attributionLogo: false },
      grid: { vertLines: { color: 'rgba(148,163,184,0.055)' }, horzLines: { color: 'rgba(148,163,184,0.055)' } },
      crosshair: { mode: CrosshairMode.Normal, vertLine: { color: 'rgba(91,140,255,.35)' }, horzLine: { color: 'rgba(91,140,255,.35)' } },
      rightPriceScale: { borderColor: 'rgba(148,163,184,.12)', autoScale: true },
      timeScale: { borderColor: 'rgba(148,163,184,.12)', timeVisible: true, secondsVisible: workspace.seconds < 60, shiftVisibleRangeOnNewBar: false },
    });
    chartRef.current = chart;
    const priceFormat = priceFormatForSymbol(symbols, workspace.symbol);
    const cs: any = chartStyle === 'bars'
      ? chart.addBarSeries({ upColor: '#10b981', downColor: '#f43f5e', priceFormat })
      : chartStyle === 'line'
        ? chart.addLineSeries({ color: '#5b8cff', lineWidth: 2, priceFormat })
        : chartStyle === 'area'
          ? chart.addAreaSeries({ lineColor: '#5b8cff', topColor: 'rgba(59,130,246,.35)', bottomColor: 'rgba(59,130,246,.02)', priceFormat })
          : chartStyle === 'baseline'
            ? chart.addBaselineSeries({ baseValue: { type: 'price', price: 0 }, topLineColor: '#10b981', topFillColor1: 'rgba(16,185,129,.28)', topFillColor2: 'rgba(16,185,129,.02)', bottomLineColor: '#f43f5e', bottomFillColor1: 'rgba(244,63,94,.02)', bottomFillColor2: 'rgba(244,63,94,.28)', priceFormat })
            : chart.addCandlestickSeries({ upColor: '#10b981', downColor: '#f43f5e', borderVisible: false, wickUpColor: '#10b981', wickDownColor: '#f43f5e', priceFormat });
    candleRef.current = cs;
    setChartRevision((x) => x + 1);
    const extras: Record<string, ISeriesApi<'Line'> | undefined> = {};
    if (workspace.ema9) extras.ema9 = chart.addLineSeries({ lineWidth: 1, color: '#22d3ee', priceLineVisible: false, lastValueVisible: false });
    if (workspace.ema20) extras.ema20 = chart.addLineSeries({ lineWidth: 1, color: '#60a5fa', priceLineVisible: false, lastValueVisible: false });
    if (workspace.ema50) extras.ema50 = chart.addLineSeries({ lineWidth: 1, color: '#f59e0b', priceLineVisible: false, lastValueVisible: false });
    if (workspace.ema200) extras.ema200 = chart.addLineSeries({ lineWidth: 2, color: '#ec4899', priceLineVisible: false, lastValueVisible: false });
    if (workspace.bollinger) {
      extras.bbUpper = chart.addLineSeries({ lineWidth: 1, color: '#a78bfa', priceLineVisible: false, lastValueVisible: false });
      extras.bbMid = chart.addLineSeries({ lineWidth: 1, color: '#64748b', priceLineVisible: false, lastValueVisible: false });
      extras.bbLower = chart.addLineSeries({ lineWidth: 1, color: '#a78bfa', priceLineVisible: false, lastValueVisible: false });
    }
    extrasRef.current = extras;

    return () => {
      chart.remove();
      chartRef.current = null; candleRef.current = null; extrasRef.current = {};
    };
  }, [workspace.symbol, workspace.seconds, workspace.ema9, workspace.ema20, workspace.ema50, workspace.ema200, workspace.bollinger, chartEngine, chartStyle]);

  useEffect(() => {
    const cs = candleRef.current;
    if (!cs || chartEngine !== 'builtin') return;
    cs.applyOptions({ priceFormat: priceFormatForSymbol(symbols, workspace.symbol) });
  }, [symbols, workspace.symbol, chartEngine]);

  useEffect(() => {
    const cs = candleRef.current;
    if (!cs || chartEngine !== 'builtin') return;
    const freezePriceScaleAfterLayout = () => {
      const chart = chartRef.current;
      if (!chart || priceScaleFrozenRef.current) return;
      window.requestAnimationFrame(() => {
        if (chartRef.current !== chart) return;
        chart.priceScale('right').applyOptions({ autoScale: false });
        priceScaleFrozenRef.current = true;
      });
    };
    const rows = candlesRef.current;
    const source = chartStyle === 'heikin' ? heikinAshi(rows) : rows;
    const ohlc = source.map((c) => ({ time: c.time as UTCTimestamp, open: c.open, high: c.high, low: c.low, close: c.close })) as CandlestickData<UTCTimestamp>[];
    const values = source.map((c) => ({ time: c.time as UTCTimestamp, value: c.close }));
    if (chartStyle === 'baseline' && source[0]) cs.applyOptions({ baseValue: { type: 'price', price: source[0].close } });
    const usesValueSeries = ['line', 'area', 'baseline'].includes(chartStyle);
    cs.setData(usesValueSeries ? values : ohlc);
    if (source.length && needsInitialFitRef.current) {
      chartRef.current?.timeScale().fitContent();
      needsInitialFitRef.current = false;
    }
    if (source.length) freezePriceScaleAfterLayout();
    const extras = extrasRef.current;
    extras.ema9?.setData(ema(rows, 9));
    extras.ema20?.setData(ema(rows, 20));
    extras.ema50?.setData(ema(rows, 50));
    extras.ema200?.setData(ema(rows, 200));
    if (workspace.bollinger) {
      const bb = bollinger(rows);
      extras.bbUpper?.setData(bb.upper); extras.bbMid?.setData(bb.mid); extras.bbLower?.setData(bb.lower);
    }
  }, [historyRevision, chartEngine, workspace.ema9, workspace.ema20, workspace.ema50, workspace.ema200, workspace.bollinger, chartStyle, chartRevision]);

  const saveGraph = () => {
    localStorage.setItem(SAVED_GRAPH_KEY, JSON.stringify({ workspace, savedAt: Date.now() }));
  };
  const loadGraph = () => {
    try {
      const saved = JSON.parse(localStorage.getItem(SAVED_GRAPH_KEY) || '');
      if (saved?.workspace) setWorkspace(saved.workspace);
    } catch { /* no saved graph */ }
  };
  const downloadSnapshot = () => {
    const canvas = chartRef.current?.takeScreenshot?.();
    if (!canvas) return;
    const link = document.createElement('a');
    link.download = `${workspace.symbol}-${workspace.seconds}s-chart.png`;
    link.href = canvas.toDataURL('image/png');
    link.click();
  };
  const applyIndicatorPreset = () => setWorkspace((w) => ({ ...w, ema9: true, ema20: true, ema50: true, ema200: true, bollinger: false }));

  const retry = () => { derivMarketService.reconnect(); setReloadKey((x) => x + 1); };
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? symbols.filter((s) => `${s.symbol} ${s.name} ${s.market}`.toLowerCase().includes(q)) : symbols;
  }, [symbols, query]);
  const groups = useMemo(() => groupSymbols(filtered), [filtered]);
  const selected = symbols.find((s) => s.symbol === workspace.symbol);
  const rsiNow = rsi(candles); const atrNow = atr(candles); const macdNow = macd(candles);


  return (
    <div className="space-y-4">
      <Panel className="p-3 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[210px] flex-1 sm:flex-none">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-600" />
            <input className="input !pl-8 !py-2 text-xs" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search Deriv markets…" />
          </div>
          <select className="input !w-auto min-w-[260px] !py-2 text-xs" value={workspace.symbol} onChange={(e) => setWorkspace((w) => ({ ...w, symbol: e.target.value }))}>
            {groups.map(([group, rows]) => <optgroup key={group} label={`${group} (${rows.length})`}>{rows.map((s) => <option key={s.symbol} value={s.symbol}>{s.name} · {s.symbol}</option>)}</optgroup>)}
          </select>
          <button className="btn-ghost !py-2" onClick={retry}><RefreshCw size={13} /> Retry feed</button>
          <button className="btn-ghost !py-2" onClick={saveGraph} title="Save graph layout"><Save size={13} /> Save Graph</button>
          <button className="btn-icon" onClick={loadGraph} title="Load saved graph"><FolderOpen size={14} /></button>
          <button className="btn-icon" onClick={downloadSnapshot} disabled={chartEngine !== 'builtin'} title="Download chart snapshot"><Camera size={14} /></button>
          <div className="flex gap-1 rounded-lg bg-white/[.03] p-1 ml-auto">
            <button onClick={() => setChartEngine('builtin')} className={`rounded-md px-2.5 py-1 text-[10px] font-bold ${chartEngine === 'builtin' ? 'bg-brand-600 text-white' : 'text-slate-500 hover:text-white'}`}>KOOLKID Chart</button>
            <button disabled={!officialReady} title={officialReady ? 'Use licensed TradingView Advanced Charts runtime' : 'Official TradingView Advanced Charts library has not been installed'} onClick={() => setChartEngine('tradingview')} className={`rounded-md px-2.5 py-1 text-[10px] font-bold disabled:opacity-40 ${chartEngine === 'tradingview' && officialReady ? 'bg-brand-600 text-white' : 'text-slate-500 hover:text-white'}`}>TradingView Advanced</button>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-1.5 border-t border-white/[.06] pt-3">
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-600 mr-1">Timeframe</span>
          {RESOLUTIONS.map((r) => <button key={r.seconds} onClick={() => setWorkspace((w) => ({ ...w, seconds: r.seconds }))} className={`rounded-lg px-2.5 py-1.5 text-[11px] font-bold ${workspace.seconds === r.seconds ? 'bg-brand-600 text-white' : 'bg-white/[.04] text-slate-400 hover:text-white'}`}>{r.label}</button>)}
          <span className="mx-2 h-5 w-px bg-white/[.08]" />
          <select className="input !w-auto !py-1.5 text-[11px]" value={chartStyle} onChange={(e) => setWorkspace((w) => ({ ...w, chartStyle: e.target.value as Workspace['chartStyle'] }))} aria-label="Chart style">
            <option value="candles">Candles</option><option value="bars">Bars</option><option value="line">Line</option><option value="area">Area</option><option value="baseline">Baseline</option><option value="heikin">Heikin Ashi</option>
          </select>
          <span className="mx-2 h-5 w-px bg-white/[.08]" />
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-600 mr-1">Indicators</span>
          {([
            ['EMA 9', 'ema9'], ['EMA 20', 'ema20'], ['EMA 50', 'ema50'], ['EMA 200', 'ema200'], ['Bollinger', 'bollinger'],
          ] as const).map(([label, key]) => <button key={key} onClick={() => setWorkspace((w) => ({ ...w, [key]: !w[key] }))} className={`rounded-lg px-2.5 py-1.5 text-[10px] font-bold ${(workspace[key] ?? false) ? 'bg-brand-500/20 text-brand-200 border border-brand-500/30' : 'bg-white/[.04] text-slate-500 border border-transparent hover:text-white'}`}>{label}</button>)}
          <button onClick={applyIndicatorPreset} className="rounded-lg px-2.5 py-1.5 text-[10px] font-bold bg-white/[.04] text-slate-400 hover:text-white">EMA 9/20/50/200 Preset</button>
        </div>
        <div className="border-t border-white/[.06] pt-3">
          {chartEngine === 'builtin' ? (
            <ChartMarkupToolbar controller={markup} scopeLabel={`Deriv ${activeDerivLogin} · ${workspace.symbol}`} />
          ) : (
            <p className="text-[10px] text-slate-500">TradingView Advanced uses its own native drawing toolbar.</p>
          )}
        </div>
      </Panel>

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_235px] gap-4">
        <Panel className="overflow-hidden">
          <div className="p-3 border-b border-white/[.06] flex flex-wrap items-center gap-3">
            <div><p className="text-sm font-bold text-white">{selected?.name || workspace.symbol}</p><p className="mono text-[10px] text-slate-600">{workspace.symbol}</p></div>
            <Badge tone={status === 'live' ? 'gain' : status === 'error' ? 'loss' : 'warn'}><Radio size={9} /> {status === 'live' ? 'LIVE DERIV DATA' : status}</Badge>
            {lastPrice != null && <span className="mono ml-auto text-lg font-bold text-white">{lastPrice}</span>}
          </div>
          {error && <div className="mx-3 mt-3 rounded-xl border border-loss-500/20 bg-loss-500/[.06] px-3 py-2 text-xs text-loss-300 flex items-center justify-between gap-3"><span>{error}</span><button className="btn-ghost !py-1.5" onClick={retry}>Retry</button></div>}
          {status === 'connecting' && !candles.length && <div className="h-[545px] grid place-items-center text-xs text-slate-500"><span className="inline-flex items-center gap-2"><RefreshCw size={14} className="animate-spin" /> Loading live Deriv candles…</span></div>}
          {chartEngine === 'tradingview' && officialReady ? (
            <TradingViewAdvancedChart symbol={workspace.symbol} seconds={workspace.seconds} />
          ) : (
            <div className={`${status === 'connecting' && !candles.length ? 'hidden' : ''} relative h-[545px] px-2`}>
              <div className="absolute inset-0 mx-2" ref={wrapRef} />
              <div className="absolute inset-0 mx-2">
                <ChartMarkupOverlay
                  controller={markup}
                  chartRef={chartRef}
                  seriesRef={candleRef}
                  candleTimes={candles.map((row) => row.time)}
                  revisionToken={chartRevision}
                  digits={priceFormatForSymbol(symbols, workspace.symbol).precision}
                />
              </div>
            </div>
          )}
          <div className="px-3 pb-3 text-[10px] text-slate-600">Public chart data only. Deriv options execution remains separate from this chart feed. Drawings auto-save per active Deriv account + market in this browser.</div>
        </Panel>

        <div className="space-y-4">
          <Panel className="p-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2"><SlidersHorizontal size={14} className="text-brand-300" /> Indicator readings</h3>
            <div className="mt-3 space-y-2 text-[11px]">
              <div className="flex justify-between"><span className="text-slate-500">RSI 14</span><span className="mono text-slate-200">{rsiNow == null ? '—' : rsiNow.toFixed(1)}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">ATR 14</span><span className="mono text-slate-200">{atrNow == null ? '—' : atrNow.toFixed(5)}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">MACD</span><span className="mono text-slate-200">{macdNow == null ? '—' : macdNow.macd.toFixed(5)}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Signal</span><span className="mono text-slate-200">{macdNow == null ? '—' : macdNow.signal.toFixed(5)}</span></div>
            </div>
          </Panel>
          <Panel className="p-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2"><PenLine size={14} className="text-brand-300" /> Built-in tools</h3>
            <p className="mt-2 text-[10px] leading-relaxed text-slate-500">Entry/SL/TP lines, trend/ray, rectangles, long/short position tools, Fibonacci, arrows, notes, measurement, undo/redo and Clear All are available above the chart. Drawings are isolated by active account + market.</p>
          </Panel>
          <Panel className="p-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2"><Activity size={14} className="text-brand-300" /> TradingView Advanced</h3>
            <Badge tone={officialReady ? 'gain' : 'warn'}>{officialReady ? 'Runtime detected · ready' : 'Official library not installed'}</Badge>
            <p className="mt-2 text-[10px] leading-relaxed text-slate-500">KOOLKID includes the Deriv datafeed adapter and integration slot. TradingView's full Advanced Charts toolset appears only after you add the official licensed library; it is not legally bundled in this ZIP.</p>
          </Panel>
        </div>
      </div>
    </div>
  );
}
