import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createChart, ColorType, CrosshairMode } from 'lightweight-charts';
import type { IChartApi, ISeriesApi, CandlestickData, LineData, UTCTimestamp } from 'lightweight-charts';
import { Activity, Camera, Eraser, FolderOpen, Minus, MousePointer2, PenLine, Radio, RefreshCw, Save, Search, SlidersHorizontal, Square, Undo2, Percent } from 'lucide-react';
import { Badge, Panel } from './ui';
import { derivMarketService } from '../services/derivMarketService';
import { usePersistentState } from '../hooks/usePersistentState';
import type { Candle } from '../lib/market';
import type { DerivSymbol } from '../types';
import TradingViewAdvancedChart from './TradingViewAdvancedChart';

const RESOLUTIONS = [
  { label: '1m', seconds: 60 }, { label: '2m', seconds: 120 }, { label: '5m', seconds: 300 }, { label: '15m', seconds: 900 },
  { label: '30m', seconds: 1800 }, { label: '1H', seconds: 3600 }, { label: '2H', seconds: 7200 }, { label: '4H', seconds: 14400 }, { label: '8H', seconds: 28800 }, { label: '1D', seconds: 86400 },
];

type DrawMode = 'cursor' | 'hline' | 'trend' | 'rect' | 'fib';
type Point = { time: number; price: number };
type Drawing =
  | { id: string; type: 'hline'; price: number; label: string }
  | { id: string; type: 'trend' | 'rect' | 'fib'; a: Point; b: Point };

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
const EMPTY_DRAWINGS: Drawing[] = [];

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

function toolLabel(mode: DrawMode, started: boolean) {
  if (mode === 'hline') return 'Click a price level.';
  if (mode === 'cursor') return '';
  return started ? 'Click the second point.' : 'Click the first point.';
}

export default function DerivAdvancedChart() {
  const wrapRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<any>(null);
  const candlesRef = useRef<Candle[]>([]);
  const needsInitialFitRef = useRef(true);
  const priceScaleFrozenRef = useRef(false);
  const extrasRef = useRef<Record<string, ISeriesApi<'Line'> | undefined>>({});
  const drawModeRef = useRef<DrawMode>('cursor');
  const drawStartRef = useRef<Point | null>(null);
  const chartStyleRef = useRef<Workspace['chartStyle']>('candles');
  const [symbols, setSymbols] = useState<DerivSymbol[]>([]);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<'connecting' | 'live' | 'error'>('connecting');
  const [lastPrice, setLastPrice] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [reloadKey, setReloadKey] = useState(0);
  const [chartRevision, setChartRevision] = useState(0);
  const [historyRevision, setHistoryRevision] = useState(0);
  const [drawMode, setDrawMode] = useState<DrawMode>('cursor');
  const [drawStart, setDrawStart] = useState<Point | null>(null);
  const [workspace, setWorkspace] = usePersistentState<Workspace>('deriv_chart_workspace', {
    symbol: 'R_75', seconds: 60, ema9: false, ema20: true, ema50: false, ema200: false, bollinger: false,
  });
  const [drawingsBySymbol, setDrawingsBySymbol] = usePersistentState<Record<string, Drawing[]>>('deriv_chart_drawings_v3', {});
  const drawings = useMemo(() => drawingsBySymbol[workspace.symbol] || EMPTY_DRAWINGS, [drawingsBySymbol, workspace.symbol]);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [chartEngine, setChartEngine] = usePersistentState<'builtin' | 'tradingview'>('deriv_chart_engine', 'builtin');
  const [officialReady, setOfficialReady] = useState(() => typeof window !== 'undefined' && Boolean((window as any).TradingView?.widget));
  const chartStyle = workspace.chartStyle || 'candles';

  useEffect(() => {
    chartStyleRef.current = chartStyle;
  }, [chartStyle]);

  const setDrawings = useCallback((next: Drawing[] | ((prev: Drawing[]) => Drawing[])) => {
    setDrawingsBySymbol((prev) => {
      const current = prev[workspace.symbol] || [];
      const resolved = typeof next === 'function' ? (next as (rows: Drawing[]) => Drawing[])(current) : next;
      return { ...prev, [workspace.symbol]: resolved };
    });
  }, [setDrawingsBySymbol, workspace.symbol]);

  useEffect(() => { drawModeRef.current = drawMode; }, [drawMode]);
  useEffect(() => { drawStartRef.current = drawStart; }, [drawStart]);

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
  }, [workspace.symbol, workspace.seconds, reloadKey]);

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

    const addSegment = (a: Point, b: Point, color = '#38bdf8', width: 1 | 2 | 3 | 4 = 1) => {
      const line = chart.addLineSeries({ lineWidth: width, color, priceLineVisible: false, lastValueVisible: false });
      const points = a.time <= b.time ? [a, b] : [b, a];
      line.setData(points.map((p) => ({ time: p.time as UTCTimestamp, value: p.price })));
    };
    for (const d of drawings) {
      if (d.type === 'hline') {
        cs.createPriceLine({ price: d.price, color: '#38bdf8', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: d.label || 'H-Line' });
      } else if (d.type === 'trend') {
        addSegment(d.a, d.b, '#38bdf8', 2);
      } else if (d.type === 'rect') {
        const loT = Math.min(d.a.time, d.b.time); const hiT = Math.max(d.a.time, d.b.time);
        const loP = Math.min(d.a.price, d.b.price); const hiP = Math.max(d.a.price, d.b.price);
        addSegment({ time: loT, price: loP }, { time: hiT, price: loP });
        addSegment({ time: loT, price: hiP }, { time: hiT, price: hiP });
        addSegment({ time: loT, price: loP }, { time: loT, price: hiP });
        addSegment({ time: hiT, price: loP }, { time: hiT, price: hiP });
      } else if (d.type === 'fib') {
        const low = d.a.price; const diff = d.b.price - d.a.price;
        for (const level of [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1]) {
          cs.createPriceLine({ price: low + diff * level, color: '#a78bfa', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: `Fib ${(level * 100).toFixed(1)}%` });
        }
      }
    }

    const click = (param: any) => {
      const mode = drawModeRef.current;
      if (mode === 'cursor' || !param.point || !param.time) return;
      const price = cs.coordinateToPrice(param.point.y);
      if (price == null) return;
      const point = { time: Number(param.time), price: Number(price) };
      if (mode === 'hline') {
        setDrawings((prev) => [...prev, { id: crypto.randomUUID(), type: 'hline', price: point.price, label: 'Price level' }]);
        setDrawMode('cursor');
        return;
      }
      const first = drawStartRef.current;
      if (!first) {
        drawStartRef.current = point; setDrawStart(point); return;
      }
      setDrawings((prev) => [...prev, { id: crypto.randomUUID(), type: mode, a: first, b: point } as Drawing]);
      drawStartRef.current = null; setDrawStart(null); setDrawMode('cursor');
    };
    chart.subscribeClick(click);
    return () => {
      chart.unsubscribeClick(click); chart.remove();
      chartRef.current = null; candleRef.current = null; extrasRef.current = {};
    };
  }, [workspace.symbol, workspace.seconds, workspace.ema9, workspace.ema20, workspace.ema50, workspace.ema200, workspace.bollinger, drawings, chartEngine, chartStyle, setDrawings]);

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
    localStorage.setItem(SAVED_GRAPH_KEY, JSON.stringify({ workspace, drawingsBySymbol, savedAt: Date.now() }));
  };
  const loadGraph = () => {
    try {
      const saved = JSON.parse(localStorage.getItem(SAVED_GRAPH_KEY) || '');
      if (saved?.workspace) setWorkspace(saved.workspace);
      if (saved?.drawingsBySymbol) setDrawingsBySymbol(saved.drawingsBySymbol);
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

  const chooseTool = (mode: DrawMode) => { setDrawMode(mode); setDrawStart(null); drawStartRef.current = null; };

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
        <div className="flex flex-wrap items-center gap-1.5 border-t border-white/[.06] pt-3">
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-600 mr-1">Markup</span>
          <button title="Cursor" className={`btn-icon ${drawMode === 'cursor' ? '!bg-brand-600 !text-white' : ''}`} onClick={() => chooseTool('cursor')}><MousePointer2 size={14} /></button>
          <button title="Horizontal line" className={`btn-icon ${drawMode === 'hline' ? '!bg-brand-600 !text-white' : ''}`} onClick={() => chooseTool('hline')}><Minus size={14} /></button>
          <button title="Trend line" className={`btn-icon ${drawMode === 'trend' ? '!bg-brand-600 !text-white' : ''}`} onClick={() => chooseTool('trend')}><PenLine size={14} /></button>
          <button title="Rectangle" className={`btn-icon ${drawMode === 'rect' ? '!bg-brand-600 !text-white' : ''}`} onClick={() => chooseTool('rect')}><Square size={14} /></button>
          <button title="Fibonacci retracement" className={`btn-icon ${drawMode === 'fib' ? '!bg-brand-600 !text-white' : ''}`} onClick={() => chooseTool('fib')}><Percent size={14} /></button>
          <button title="Undo last drawing" className="btn-icon" disabled={!drawings.length} onClick={() => setDrawings((prev) => prev.slice(0, -1))}><Undo2 size={14} /></button>
          <button title="Clear drawings" className="btn-ghost !py-1.5" disabled={!drawings.length} onClick={() => { setDrawings([]); chooseTool('cursor'); }}><Eraser size={13} /> Clear</button>
          {drawMode !== 'cursor' && <span className="text-[10px] text-warn-400 ml-2">{toolLabel(drawMode, Boolean(drawStart))}</span>}
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
          {chartEngine === 'tradingview' && officialReady ? <TradingViewAdvancedChart symbol={workspace.symbol} seconds={workspace.seconds} /> : <div className={`${status === 'connecting' && !candles.length ? 'hidden' : ''} h-[545px] px-2`} ref={wrapRef} />}
          <div className="px-3 pb-3 text-[10px] text-slate-600">Public chart data only. Deriv options execution remains separate from this chart feed. Built-in drawings are saved in this browser.</div>
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
            <p className="mt-2 text-[10px] leading-relaxed text-slate-500">Cursor, horizontal line, trend line, rectangle, Fibonacci retracement, undo and clear are available from the toolbar above the chart.</p>
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
