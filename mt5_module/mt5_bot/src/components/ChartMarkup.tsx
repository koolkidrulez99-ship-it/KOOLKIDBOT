import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { MutableRefObject, PointerEvent as ReactPointerEvent, ReactNode } from 'react';
import type { IChartApi, UTCTimestamp } from 'lightweight-charts';
import {
  ArrowUpRight,
  Eye,
  EyeOff,
  Lock,
  Minus,
  MousePointer2,
  PenLine,
  Percent,
  Redo2,
  Ruler,
  Square,
  Trash2,
  Type,
  Undo2,
  Unlock,
} from 'lucide-react';

export type MarkupTool =
  | 'cursor'
  | 'hline'
  | 'entry'
  | 'sl'
  | 'tp'
  | 'trend'
  | 'ray'
  | 'vline'
  | 'rect'
  | 'long'
  | 'short'
  | 'fib'
  | 'arrow'
  | 'text'
  | 'measure';

export type MarkupPoint = { time: number; price: number };

type DrawingBase = {
  id: string;
  locked?: boolean;
  hidden?: boolean;
};

export type MarkupDrawing =
  | (DrawingBase & { type: 'hline' | 'entry' | 'sl' | 'tp'; price: number })
  | (DrawingBase & { type: 'vline'; time: number })
  | (DrawingBase & { type: 'trend' | 'ray' | 'rect' | 'fib' | 'arrow' | 'measure'; a: MarkupPoint; b: MarkupPoint })
  | (DrawingBase & { type: 'long' | 'short'; entry: MarkupPoint; stop: MarkupPoint; target: MarkupPoint })
  | (DrawingBase & { type: 'text'; at: MarkupPoint; text: string });

const STORAGE_KEY = 'koolkid_chart_markup_v1';

function makeId() {
  try { return crypto.randomUUID(); } catch { return `mk-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`; }
}

function readStore(): Record<string, MarkupDrawing[]> {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function readScope(scopeKey: string): MarkupDrawing[] {
  const rows = readStore()[scopeKey];
  return Array.isArray(rows) ? rows : [];
}

function writeScope(scopeKey: string, rows: MarkupDrawing[]) {
  try {
    const store = readStore();
    store[scopeKey] = rows;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  } catch {
    // Browser storage may be disabled. Keep the in-memory drawings working.
  }
}

function toolPrompt(tool: MarkupTool, count: number) {
  if (tool === 'cursor') return '';
  if (['hline', 'entry', 'sl', 'tp', 'vline', 'text'].includes(tool)) return 'Click the chart.';
  if (tool === 'long' || tool === 'short') {
    if (count === 0) return 'Click entry.';
    if (count === 1) return 'Click stop loss.';
    return 'Click take profit.';
  }
  return count === 0 ? 'Click the first point.' : 'Click the second point.';
}

export function useChartMarkup(platform: 'mt5' | 'deriv', accountKey: string | number | null | undefined, symbol: string) {
  const normalizedAccount = String(accountKey ?? 'unassigned');
  const scopeKey = `${platform}:${normalizedAccount}:${symbol}`;
  const [drawings, setDrawings] = useState<MarkupDrawing[]>(() => readScope(scopeKey));
  const [tool, setToolState] = useState<MarkupTool>('cursor');
  const [draftPoints, setDraftPoints] = useState<MarkupPoint[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hiddenAll, setHiddenAll] = useState(false);
  const undoRef = useRef<MarkupDrawing[][]>([]);
  const redoRef = useRef<MarkupDrawing[][]>([]);
  const scopeRef = useRef(scopeKey);

  useEffect(() => {
    scopeRef.current = scopeKey;
    setDrawings(readScope(scopeKey));
    setSelectedId(null);
    setDraftPoints([]);
    setToolState('cursor');
    setHiddenAll(false);
    undoRef.current = [];
    redoRef.current = [];
  }, [scopeKey]);

  const commit = useCallback((next: MarkupDrawing[] | ((prev: MarkupDrawing[]) => MarkupDrawing[]), history = true) => {
    setDrawings((prev) => {
      const resolved = typeof next === 'function' ? (next as (rows: MarkupDrawing[]) => MarkupDrawing[])(prev) : next;
      if (history) {
        undoRef.current = [...undoRef.current.slice(-39), prev];
        redoRef.current = [];
      }
      writeScope(scopeRef.current, resolved);
      return resolved;
    });
  }, []);

  const setTool = useCallback((next: MarkupTool) => {
    setToolState(next);
    setDraftPoints([]);
    if (next !== 'cursor') setSelectedId(null);
  }, []);

  const addDrawing = useCallback((drawing: MarkupDrawing) => commit((prev) => [...prev, drawing]), [commit]);

  const undo = useCallback(() => {
    const previous = undoRef.current.pop();
    if (!previous) return;
    setDrawings((current) => {
      redoRef.current.push(current);
      writeScope(scopeRef.current, previous);
      return previous;
    });
    setSelectedId(null);
    setDraftPoints([]);
  }, []);

  const redo = useCallback(() => {
    const next = redoRef.current.pop();
    if (!next) return;
    setDrawings((current) => {
      undoRef.current.push(current);
      writeScope(scopeRef.current, next);
      return next;
    });
    setSelectedId(null);
    setDraftPoints([]);
  }, []);

  const clearAll = useCallback(() => {
    if (!drawings.length) return;
    commit([]);
    setSelectedId(null);
    setDraftPoints([]);
    setToolState('cursor');
  }, [commit, drawings.length]);

  const deleteSelected = useCallback(() => {
    if (!selectedId) return;
    commit((prev) => prev.filter((row) => row.id !== selectedId));
    setSelectedId(null);
  }, [commit, selectedId]);

  const toggleSelectedLock = useCallback(() => {
    if (!selectedId) return;
    commit((prev) => prev.map((row) => row.id === selectedId ? { ...row, locked: !row.locked } : row));
  }, [commit, selectedId]);

  const toggleSelectedHidden = useCallback(() => {
    if (!selectedId) return;
    commit((prev) => prev.map((row) => row.id === selectedId ? { ...row, hidden: !row.hidden } : row));
    setSelectedId(null);
  }, [commit, selectedId]);

  const selected = drawings.find((row) => row.id === selectedId) || null;

  return {
    platform,
    accountKey: normalizedAccount,
    symbol,
    scopeKey,
    drawings,
    tool,
    setTool,
    draftPoints,
    setDraftPoints,
    selectedId,
    setSelectedId,
    selected,
    hiddenAll,
    setHiddenAll,
    addDrawing,
    commit,
    undo,
    redo,
    clearAll,
    deleteSelected,
    toggleSelectedLock,
    toggleSelectedHidden,
    canUndo: undoRef.current.length > 0,
    canRedo: redoRef.current.length > 0,
    prompt: toolPrompt(tool, draftPoints.length),
  };
}

export type ChartMarkupController = ReturnType<typeof useChartMarkup>;

export function ChartMarkupToolbar({ controller, scopeLabel }: { controller: ChartMarkupController; scopeLabel: string }) {
  const c = controller;
  const tools: Array<{ tool: MarkupTool; title: string; content: ReactNode }> = [
    { tool: 'cursor', title: 'Select drawings', content: <MousePointer2 size={14} /> },
    { tool: 'hline', title: 'Horizontal line', content: <Minus size={14} /> },
    { tool: 'entry', title: 'Entry line', content: <span className="mono text-[9px] font-extrabold">ENTRY</span> },
    { tool: 'sl', title: 'Stop Loss line', content: <span className="mono text-[10px] font-extrabold text-loss-300">SL</span> },
    { tool: 'tp', title: 'Take Profit line', content: <span className="mono text-[10px] font-extrabold text-gain-300">TP</span> },
    { tool: 'trend', title: 'Trend line', content: <PenLine size={14} /> },
    { tool: 'ray', title: 'Ray', content: <ArrowUpRight size={14} /> },
    { tool: 'vline', title: 'Vertical line', content: <span className="text-sm leading-none">│</span> },
    { tool: 'rect', title: 'Rectangle / zone', content: <Square size={14} /> },
    { tool: 'long', title: 'Long position', content: <span className="mono text-[9px] font-extrabold text-gain-300">LONG</span> },
    { tool: 'short', title: 'Short position', content: <span className="mono text-[9px] font-extrabold text-loss-300">SHORT</span> },
    { tool: 'fib', title: 'Fibonacci retracement', content: <Percent size={14} /> },
    { tool: 'arrow', title: 'Arrow', content: <ArrowUpRight size={14} /> },
    { tool: 'text', title: 'Text note', content: <Type size={14} /> },
    { tool: 'measure', title: 'Price range / measurement', content: <Ruler size={14} /> },
  ];

  const clear = () => {
    if (!c.drawings.length) return;
    if (window.confirm(`Clear ALL drawings for ${scopeLabel}?\n\nOnly this active account + market will be cleared.`)) c.clearAll();
  };

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-600 mr-1">Markup</span>
      {tools.map((item) => (
        <button
          key={item.tool}
          title={item.title}
          className={`btn-icon ${c.tool === item.tool ? '!bg-brand-600 !text-white' : ''}`}
          onClick={() => c.setTool(item.tool)}
        >
          {item.content}
        </button>
      ))}
      <span className="mx-1 h-5 w-px bg-white/[.08]" />
      <button title="Undo" className="btn-icon" disabled={!c.canUndo} onClick={c.undo}><Undo2 size={14} /></button>
      <button title="Redo" className="btn-icon" disabled={!c.canRedo} onClick={c.redo}><Redo2 size={14} /></button>
      <button title="Delete selected drawing" className="btn-icon" disabled={!c.selected} onClick={c.deleteSelected}><Trash2 size={14} /></button>
      <button title={c.selected?.locked ? 'Unlock selected drawing' : 'Lock selected drawing'} className="btn-icon" disabled={!c.selected} onClick={c.toggleSelectedLock}>
        {c.selected?.locked ? <Unlock size={14} /> : <Lock size={14} />}
      </button>
      <button title="Hide selected drawing" className="btn-icon" disabled={!c.selected} onClick={c.toggleSelectedHidden}><EyeOff size={14} /></button>
      <button title={c.hiddenAll ? 'Show all drawings' : 'Hide all drawings'} className="btn-icon" disabled={!c.drawings.length} onClick={() => c.setHiddenAll((value) => !value)}>
        {c.hiddenAll ? <Eye size={14} /> : <EyeOff size={14} />}
      </button>
      <button title="Clear all drawings for current account and market" className="btn-ghost !py-1.5" disabled={!c.drawings.length} onClick={clear}>
        <Trash2 size={13} /> Clear All
      </button>
      {c.tool !== 'cursor' && <span className="text-[10px] text-warn-400 ml-2">{c.prompt}</span>}
      {c.tool === 'cursor' && c.selected && <span className="text-[10px] text-brand-200 ml-2">Selected · {c.selected.type}{c.selected.locked ? ' · locked' : ''}</span>}
    </div>
  );
}

function eventPoint(
  e: ReactPointerEvent<SVGSVGElement>,
  chart: IChartApi,
  series: any,
  candleTimes: number[],
): MarkupPoint | null {
  const rect = e.currentTarget.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const y = e.clientY - rect.top;
  const price = series?.coordinateToPrice?.(y);
  let time = chart.timeScale().coordinateToTime(x) as any;
  if (time && typeof time === 'object' && 'year' in time) {
    time = Date.UTC(Number(time.year), Number(time.month) - 1, Number(time.day)) / 1000;
  }
  if (typeof time !== 'number' || !Number.isFinite(time)) {
    let bestTime: number | null = null;
    let bestDistance = Infinity;
    for (const candidate of candleTimes) {
      const cx = chart.timeScale().timeToCoordinate(candidate as UTCTimestamp);
      if (cx == null) continue;
      const distance = Math.abs(cx - x);
      if (distance < bestDistance) { bestDistance = distance; bestTime = candidate; }
    }
    time = bestTime;
  }
  if (typeof price !== 'number' || !Number.isFinite(price) || typeof time !== 'number' || !Number.isFinite(time)) return null;
  return { time, price };
}

function nearestTimeCoordinate(chart: IChartApi, target: number, candleTimes: number[]) {
  const direct = chart.timeScale().timeToCoordinate(target as UTCTimestamp);
  if (direct != null) return direct;
  if (!candleTimes.length) return null;
  let nearest = candleTimes[0];
  let distance = Math.abs(nearest - target);
  for (const time of candleTimes) {
    const nextDistance = Math.abs(time - target);
    if (nextDistance < distance) { nearest = time; distance = nextDistance; }
  }
  return chart.timeScale().timeToCoordinate(nearest as UTCTimestamp);
}

function pointToXY(chart: IChartApi, series: any, point: MarkupPoint, candleTimes: number[]) {
  const x = nearestTimeCoordinate(chart, point.time, candleTimes);
  const y = series?.priceToCoordinate?.(point.price);
  return x == null || y == null ? null : { x: Number(x), y: Number(y) };
}

function positionColor(type: 'long' | 'short') {
  return type === 'long'
    ? { target: 'rgba(16,185,129,.16)', stop: 'rgba(244,63,94,.16)', border: '#38bdf8' }
    : { target: 'rgba(16,185,129,.16)', stop: 'rgba(244,63,94,.16)', border: '#f59e0b' };
}

export function ChartMarkupOverlay({
  controller,
  chartRef,
  seriesRef,
  candleTimes,
  revisionToken,
  digits = 5,
}: {
  controller: ChartMarkupController;
  chartRef: MutableRefObject<IChartApi | null>;
  seriesRef: MutableRefObject<any>;
  candleTimes: number[];
  revisionToken?: number;
  digits?: number;
}) {
  const c = controller;
  const [layoutRevision, setLayoutRevision] = useState(0);
  const [hoverPoint, setHoverPoint] = useState<MarkupPoint | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const chart = chartRef.current;
    const svg = svgRef.current;
    if (!chart || !svg) return;
    const bump = () => setLayoutRevision((value) => value + 1);
    chart.timeScale().subscribeVisibleLogicalRangeChange(bump);
    chart.subscribeCrosshairMove(bump);
    const observer = new ResizeObserver(bump);
    observer.observe(svg);
    return () => {
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(bump);
      chart.unsubscribeCrosshairMove(bump);
      observer.disconnect();
    };
  }, [chartRef, revisionToken]);

  const dimensions = useMemo(() => {
    const rect = svgRef.current?.getBoundingClientRect();
    return { width: rect?.width || 0, height: rect?.height || 0 };
    // layoutRevision intentionally invalidates pixel-coordinate projections.
  }, [layoutRevision, revisionToken]);

  const addPoint = (point: MarkupPoint) => {
    if (['hline', 'entry', 'sl', 'tp'].includes(c.tool)) {
      c.addDrawing({ id: makeId(), type: c.tool as 'hline' | 'entry' | 'sl' | 'tp', price: point.price });
      c.setTool('cursor');
      return;
    }
    if (c.tool === 'vline') {
      c.addDrawing({ id: makeId(), type: 'vline', time: point.time });
      c.setTool('cursor');
      return;
    }
    if (c.tool === 'text') {
      const text = window.prompt('Chart note text:')?.trim();
      if (text) c.addDrawing({ id: makeId(), type: 'text', at: point, text: text.slice(0, 120) });
      c.setTool('cursor');
      return;
    }
    if (c.tool === 'long' || c.tool === 'short') {
      if (c.draftPoints.length < 2) {
        c.setDraftPoints((prev) => [...prev, point]);
        return;
      }
      c.addDrawing({ id: makeId(), type: c.tool, entry: c.draftPoints[0], stop: c.draftPoints[1], target: point });
      c.setTool('cursor');
      return;
    }
    if (!c.draftPoints.length) {
      c.setDraftPoints([point]);
      return;
    }
    c.addDrawing({ id: makeId(), type: c.tool as 'trend' | 'ray' | 'rect' | 'fib' | 'arrow' | 'measure', a: c.draftPoints[0], b: point });
    c.setTool('cursor');
  };

  const pointerDown = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (c.tool === 'cursor') return;
    const chart = chartRef.current;
    const series = seriesRef.current;
    if (!chart || !series) return;
    const point = eventPoint(e, chart, series, candleTimes);
    if (!point) return;
    e.preventDefault();
    e.stopPropagation();
    addPoint(point);
  };

  const pointerMove = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (c.tool === 'cursor' || !c.draftPoints.length) return;
    const chart = chartRef.current;
    const series = seriesRef.current;
    if (!chart || !series) return;
    setHoverPoint(eventPoint(e, chart, series, candleTimes));
  };

  const chart = chartRef.current;
  const series = seriesRef.current;
  if (!chart || !series || c.hiddenAll) {
    return c.tool === 'cursor' ? null : <svg ref={svgRef} className="absolute inset-0 z-20 h-full w-full" style={{ pointerEvents: 'auto', cursor: 'crosshair' }} onPointerDown={pointerDown} onPointerMove={pointerMove} />;
  }

  const priceLabel = (price: number) => Number(price).toFixed(Math.max(0, Math.min(8, digits)));
  const selectedStroke = (id: string, fallback: string) => id === c.selectedId ? '#f8fafc' : fallback;
  const clickSelect = (id: string, locked?: boolean) => (e: ReactPointerEvent<SVGElement>) => {
    e.stopPropagation();
    if (!locked) c.setSelectedId(id);
    else c.setSelectedId(id);
  };

  const renderLineHit = (id: string, x1: number, y1: number, x2: number, y2: number, locked?: boolean) => (
    <line key={`${id}-hit`} x1={x1} y1={y1} x2={x2} y2={y2} stroke="transparent" strokeWidth={12} style={{ pointerEvents: 'stroke', cursor: locked ? 'not-allowed' : 'pointer' }} onPointerDown={clickSelect(id, locked)} />
  );

  const renderDrawing = (d: MarkupDrawing) => {
    if (d.hidden) return null;
    const selected = d.id === c.selectedId;
    if (d.type === 'hline' || d.type === 'entry' || d.type === 'sl' || d.type === 'tp') {
      const y = series.priceToCoordinate(d.price);
      if (y == null) return null;
      const color = d.type === 'sl' ? '#f43f5e' : d.type === 'tp' ? '#10b981' : d.type === 'entry' ? '#f59e0b' : '#38bdf8';
      const title = d.type === 'hline' ? 'H' : d.type.toUpperCase();
      return (
        <g key={d.id}>
          <line x1={0} y1={y} x2={dimensions.width} y2={y} stroke={selectedStroke(d.id, color)} strokeWidth={selected ? 2.5 : 1.5} strokeDasharray={d.type === 'hline' ? '6 5' : '8 4'} />
          <rect x={Math.max(2, dimensions.width - 112)} y={y - 10} width={108} height={20} rx={5} fill="rgba(2,6,23,.82)" stroke={color} strokeWidth="1" />
          <text x={Math.max(8, dimensions.width - 106)} y={y + 4} fontSize="10" fontFamily="JetBrains Mono, monospace" fill={color}>{title} {priceLabel(d.price)}</text>
          {renderLineHit(d.id, 0, y, dimensions.width, y, d.locked)}
        </g>
      );
    }
    if (d.type === 'vline') {
      const x = nearestTimeCoordinate(chart, d.time, candleTimes);
      if (x == null) return null;
      return <g key={d.id}><line x1={x} y1={0} x2={x} y2={dimensions.height} stroke={selectedStroke(d.id, '#64748b')} strokeWidth={selected ? 2.5 : 1.5} strokeDasharray="5 5" />{renderLineHit(d.id, x, 0, x, dimensions.height, d.locked)}</g>;
    }
    if (d.type === 'text') {
      const p = pointToXY(chart, series, d.at, candleTimes);
      if (!p) return null;
      return <g key={d.id} style={{ pointerEvents: 'all', cursor: 'pointer' }} onPointerDown={clickSelect(d.id, d.locked)}><rect x={p.x - 4} y={p.y - 17} width={Math.max(50, d.text.length * 7)} height={22} rx={5} fill="rgba(2,6,23,.82)" stroke={selected ? '#f8fafc' : '#a78bfa'} /><text x={p.x + 3} y={p.y - 2} fontSize="11" fill="#e2e8f0">{d.text}</text></g>;
    }
    if (d.type === 'long' || d.type === 'short') {
      const entry = pointToXY(chart, series, d.entry, candleTimes);
      const stop = pointToXY(chart, series, d.stop, candleTimes);
      const target = pointToXY(chart, series, d.target, candleTimes);
      if (!entry || !stop || !target) return null;
      const x1 = Math.min(entry.x, stop.x, target.x);
      const x2 = Math.max(entry.x, stop.x, target.x, x1 + 48);
      const colors = positionColor(d.type);
      const risk = Math.abs(d.entry.price - d.stop.price);
      const reward = Math.abs(d.target.price - d.entry.price);
      const rr = risk > 0 ? reward / risk : 0;
      return (
        <g key={d.id} style={{ pointerEvents: 'all', cursor: 'pointer' }} onPointerDown={clickSelect(d.id, d.locked)}>
          <rect x={x1} y={Math.min(entry.y, target.y)} width={Math.max(1, x2 - x1)} height={Math.abs(entry.y - target.y)} fill={colors.target} stroke="none" />
          <rect x={x1} y={Math.min(entry.y, stop.y)} width={Math.max(1, x2 - x1)} height={Math.abs(entry.y - stop.y)} fill={colors.stop} stroke="none" />
          <line x1={x1} y1={entry.y} x2={x2} y2={entry.y} stroke={selectedStroke(d.id, colors.border)} strokeWidth={selected ? 2.5 : 1.5} />
          <line x1={x1} y1={stop.y} x2={x2} y2={stop.y} stroke="#f43f5e" strokeWidth="1.5" />
          <line x1={x1} y1={target.y} x2={x2} y2={target.y} stroke="#10b981" strokeWidth="1.5" />
          <rect x={x1 + 5} y={entry.y - 25} width={142} height={20} rx={5} fill="rgba(2,6,23,.86)" />
          <text x={x1 + 10} y={entry.y - 11} fontSize="10" fontWeight="700" fill="#e2e8f0">{d.type.toUpperCase()} · R:R {rr.toFixed(2)}</text>
        </g>
      );
    }

    if (!('a' in d) || !('b' in d)) return null;
    const a = pointToXY(chart, series, d.a, candleTimes);
    const b = pointToXY(chart, series, d.b, candleTimes);
    if (!a || !b) return null;
    if (d.type === 'rect') {
      const x = Math.min(a.x, b.x); const y = Math.min(a.y, b.y);
      const w = Math.abs(a.x - b.x); const h = Math.abs(a.y - b.y);
      return <g key={d.id} style={{ pointerEvents: 'all', cursor: 'pointer' }} onPointerDown={clickSelect(d.id, d.locked)}><rect x={x} y={y} width={Math.max(1, w)} height={Math.max(1, h)} fill="rgba(56,189,248,.10)" stroke={selectedStroke(d.id, '#38bdf8')} strokeWidth={selected ? 2.5 : 1.5} /></g>;
    }
    if (d.type === 'fib') {
      const levels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];
      const x1 = Math.min(a.x, b.x); const x2 = Math.max(a.x, b.x);
      return (
        <g key={d.id} style={{ pointerEvents: 'all', cursor: 'pointer' }} onPointerDown={clickSelect(d.id, d.locked)}>
          {levels.map((level) => {
            const price = d.a.price + (d.b.price - d.a.price) * level;
            const y = series.priceToCoordinate(price);
            if (y == null) return null;
            return <g key={level}><line x1={x1} y1={y} x2={x2} y2={y} stroke={selected ? '#f8fafc' : '#a78bfa'} strokeWidth="1" /><text x={x2 + 4} y={y + 3} fontSize="9" fill="#a78bfa">{(level * 100).toFixed(1)}%</text></g>;
          })}
        </g>
      );
    }
    if (d.type === 'ray') {
      const dx = b.x - a.x || 1;
      const slope = (b.y - a.y) / dx;
      const endX = dx >= 0 ? dimensions.width : 0;
      const endY = a.y + (endX - a.x) * slope;
      return <g key={d.id}><line x1={a.x} y1={a.y} x2={endX} y2={endY} stroke={selectedStroke(d.id, '#38bdf8')} strokeWidth={selected ? 2.5 : 2} />{renderLineHit(d.id, a.x, a.y, endX, endY, d.locked)}</g>;
    }
    if (d.type === 'arrow') {
      return <g key={d.id}><line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={selectedStroke(d.id, '#f59e0b')} strokeWidth={selected ? 2.5 : 2} markerEnd="url(#kk-arrow)" />{renderLineHit(d.id, a.x, a.y, b.x, b.y, d.locked)}</g>;
    }
    if (d.type === 'measure') {
      const delta = d.b.price - d.a.price;
      const pct = d.a.price ? (delta / d.a.price) * 100 : 0;
      const midX = (a.x + b.x) / 2; const midY = (a.y + b.y) / 2;
      return <g key={d.id}><line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={selectedStroke(d.id, '#22d3ee')} strokeWidth={selected ? 2.5 : 1.5} strokeDasharray="5 4" />{renderLineHit(d.id, a.x, a.y, b.x, b.y, d.locked)}<rect x={midX - 70} y={midY - 24} width={140} height={20} rx={5} fill="rgba(2,6,23,.86)" /><text x={midX - 64} y={midY - 10} fontSize="10" fill="#67e8f9">Δ {delta.toFixed(digits)} · {pct.toFixed(2)}%</text></g>;
    }
    return <g key={d.id}><line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={selectedStroke(d.id, '#38bdf8')} strokeWidth={selected ? 2.5 : 2} />{renderLineHit(d.id, a.x, a.y, b.x, b.y, d.locked)}</g>;
  };

  const preview = (() => {
    if (!c.draftPoints.length || !hoverPoint) return null;
    const first = pointToXY(chart, series, c.draftPoints[0], candleTimes);
    const hover = pointToXY(chart, series, hoverPoint, candleTimes);
    if (!first || !hover) return null;
    if (c.tool === 'long' || c.tool === 'short') {
      if (c.draftPoints.length === 1) return <line x1={0} y1={first.y} x2={dimensions.width} y2={first.y} stroke="#f59e0b" strokeWidth="1.5" strokeDasharray="5 4" />;
      const stop = pointToXY(chart, series, c.draftPoints[1], candleTimes);
      if (!stop) return null;
      const x1 = Math.min(first.x, stop.x, hover.x); const x2 = Math.max(first.x, stop.x, hover.x, x1 + 48);
      return <g opacity=".7"><rect x={x1} y={Math.min(first.y, hover.y)} width={Math.max(1, x2 - x1)} height={Math.abs(first.y - hover.y)} fill="rgba(16,185,129,.14)" /><rect x={x1} y={Math.min(first.y, stop.y)} width={Math.max(1, x2 - x1)} height={Math.abs(first.y - stop.y)} fill="rgba(244,63,94,.14)" /><line x1={x1} y1={first.y} x2={x2} y2={first.y} stroke="#f59e0b" /></g>;
    }
    if (c.tool === 'rect') return <rect x={Math.min(first.x, hover.x)} y={Math.min(first.y, hover.y)} width={Math.abs(first.x - hover.x)} height={Math.abs(first.y - hover.y)} fill="rgba(56,189,248,.08)" stroke="#38bdf8" strokeDasharray="5 4" />;
    return <line x1={first.x} y1={first.y} x2={hover.x} y2={hover.y} stroke="#38bdf8" strokeWidth="1.5" strokeDasharray="5 4" />;
  })();

  return (
    <svg
      ref={svgRef}
      className="absolute inset-0 z-20 h-full w-full"
      style={{ pointerEvents: c.tool === 'cursor' ? 'none' : 'auto', cursor: c.tool === 'cursor' ? 'default' : 'crosshair' }}
      onPointerDown={pointerDown}
      onPointerMove={pointerMove}
      onPointerLeave={() => setHoverPoint(null)}
    >
      <defs>
        <marker id="kk-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7 z" fill="#f59e0b" /></marker>
      </defs>
      {c.drawings.map(renderDrawing)}
      {preview}
    </svg>
  );
}
