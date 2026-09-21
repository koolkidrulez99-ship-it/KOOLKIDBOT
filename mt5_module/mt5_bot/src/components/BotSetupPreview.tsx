import { useEffect, useMemo, useRef, useState } from 'react';
import { createChart, ColorType, CrosshairMode } from 'lightweight-charts';
import type { CandlestickData, IChartApi, IPriceLine, ISeriesApi, UTCTimestamp } from 'lightweight-charts';
import type { Candle } from '../lib/market';
import type { Mt5Bot } from '../types';
import { mt5MarketService } from '../services/mt5MarketService';
import Modal from './Modal';

type SetupInfo = {
  stage: string;
  direction?: string;
  entry?: number;
  sl?: number;
  tp?: number;
  eventTime?: string;
  label: string;
};

const QUIET_STAGES = new Set(['', 'SCANNING', 'WAITING_DATA', 'BUILDING_RANGE', 'WAITING_RANGE']);

type SavedChartRange = { from: UTCTimestamp; to: UTCTimestamp };
const SAVED_VIEWPORTS = new Map<string, SavedChartRange>();

function numberOrUndefined(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed !== 0 ? parsed : undefined;
}

function setupInfo(bot: Mt5Bot): SetupInfo | null {
  const signal = (bot.native_signal || {}) as Record<string, unknown>;
  const execution = (bot.native_last_execution || {}) as Record<string, unknown>;
  const stage = String(signal.stage || '').toUpperCase();
  if (stage && !QUIET_STAGES.has(stage)) {
    return {
      stage,
      direction: String(signal.direction || execution.direction || '').toUpperCase() || undefined,
      entry: numberOrUndefined(signal.entry ?? execution.entry),
      sl: numberOrUndefined(signal.sl ?? execution.sl),
      tp: numberOrUndefined(signal.tp ?? execution.tp),
      eventTime: String(execution.executed_at || '') || undefined,
      label: stage.replaceAll('_', ' '),
    };
  }
  if (bot.last_trade) {
    return {
      stage: 'TRADE_FOUND',
      eventTime: bot.last_trade.time,
      label: `Trade #${bot.last_trade.ticket}`,
    };
  }
  return null;
}

function SetupChartCanvas({ candles, setup, height, chartKey }: { candles: Candle[]; setup: SetupInfo; height: number; chartKey: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const priceLinesRef = useRef<IPriceLine[]>([]);
  const initialSavedRange = SAVED_VIEWPORTS.get(chartKey) || null;
  const userMovedRef = useRef(Boolean(initialSavedRange));
  const visibleRangeRef = useRef<SavedChartRange | null>(initialSavedRange);
  const programmaticRangeRef = useRef(false);
  const renderedLastTimeRef = useRef<number | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, {
      autoSize: true,
      height,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#72809a', fontSize: 9, attributionLogo: false },
      grid: { vertLines: { color: 'rgba(148,163,184,0.05)' }, horzLines: { color: 'rgba(148,163,184,0.05)' } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: 'rgba(148,163,184,0.12)' },
      timeScale: { borderColor: 'rgba(148,163,184,0.12)', timeVisible: true, secondsVisible: false },
    });
    const series = chart.addCandlestickSeries({
      upColor: '#10b981', downColor: '#f43f5e',
      borderUpColor: '#10b981', borderDownColor: '#f43f5e',
      wickUpColor: 'rgba(16,185,129,0.75)', wickDownColor: 'rgba(244,63,94,0.75)',
    });
    const rememberRange = () => {
      if (!userMovedRef.current || programmaticRangeRef.current) return;
      const range = chart.timeScale().getVisibleRange();
      if (range) {
        const saved = { from: range.from as UTCTimestamp, to: range.to as UTCTimestamp };
        visibleRangeRef.current = saved;
        SAVED_VIEWPORTS.set(chartKey, saved);
      }
    };
    chart.timeScale().subscribeVisibleTimeRangeChange(rememberRange);
    chartRef.current = chart;
    seriesRef.current = series;
    return () => {
      if (userMovedRef.current) {
        const range = chart.timeScale().getVisibleRange();
        if (range) SAVED_VIEWPORTS.set(chartKey, { from: range.from as UTCTimestamp, to: range.to as UTCTimestamp });
      }
      chart.timeScale().unsubscribeVisibleTimeRangeChange(rememberRange);
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      priceLinesRef.current = [];
      renderedLastTimeRef.current = null;
    };
  }, [chartKey]);

  useEffect(() => {
    chartRef.current?.applyOptions({ height });
  }, [height]);

  useEffect(() => {
    const chart = chartRef.current;
    const series = seriesRef.current;
    if (!chart || !series || !candles.length) return;
    const savedRange = SAVED_VIEWPORTS.get(chartKey)
      || (userMovedRef.current ? (visibleRangeRef.current || chart.timeScale().getVisibleRange() as SavedChartRange | null) : null);
    const data: CandlestickData<UTCTimestamp>[] = candles.map((c) => ({
      time: c.time as UTCTimestamp, open: c.open, high: c.high, low: c.low, close: c.close,
    }));
    const previousLastTime = renderedLastTimeRef.current;
    programmaticRangeRef.current = true;
    if (previousLastTime === null) {
      series.setData(data);
      renderedLastTimeRef.current = Number(data[data.length - 1].time);
      if (savedRange) {
        const range = { from: savedRange.from as UTCTimestamp, to: savedRange.to as UTCTimestamp };
        chart.timeScale().setVisibleRange(range);
        visibleRangeRef.current = range;
        SAVED_VIEWPORTS.set(chartKey, range);
        userMovedRef.current = true;
      } else {
        chart.timeScale().fitContent();
      }
    } else {
      const previousIndex = data.findIndex((row) => Number(row.time) === previousLastTime);
      if (previousIndex >= 0) {
        for (let index = previousIndex; index < data.length; index += 1) series.update(data[index]);
        renderedLastTimeRef.current = Number(data[data.length - 1].time);
      } else {
        const rangeBeforeRebuild = savedRange || (userMovedRef.current ? chart.timeScale().getVisibleRange() : null);
        series.setData(data);
        renderedLastTimeRef.current = Number(data[data.length - 1].time);
        if (rangeBeforeRebuild) {
          const range = { from: rangeBeforeRebuild.from as UTCTimestamp, to: rangeBeforeRebuild.to as UTCTimestamp };
          chart.timeScale().setVisibleRange(range);
          visibleRangeRef.current = range;
          SAVED_VIEWPORTS.set(chartKey, range);
        } else {
          chart.timeScale().fitContent();
        }
      }
    }
    window.requestAnimationFrame(() => { programmaticRangeRef.current = false; });
  }, [candles, chartKey]);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series || !candles.length) return;

    let markerCandle = candles[candles.length - 1];
    if (setup.eventTime) {
      const target = new Date(setup.eventTime).getTime() / 1000;
      if (Number.isFinite(target)) {
        markerCandle = candles.reduce((best, row) =>
          Math.abs(row.time - target) < Math.abs(best.time - target) ? row : best, markerCandle);
      }
    }
    const markerDirection = String(setup.direction || '').toUpperCase();
    series.setMarkers([{
      time: markerCandle.time as UTCTimestamp,
      position: markerDirection === 'SELL' ? 'aboveBar' : 'belowBar',
      color: markerDirection === 'SELL' ? '#f43f5e' : '#10b981',
      shape: markerDirection === 'SELL' ? 'arrowDown' : 'arrowUp',
      text: markerDirection ? `${markerDirection} · ${setup.label}` : setup.label,
      size: 1,
    }]);

    priceLinesRef.current.forEach((line) => series.removePriceLine(line));
    priceLinesRef.current = [];
    if (setup.entry) priceLinesRef.current.push(series.createPriceLine({ price: setup.entry, color: '#5b8cff', lineWidth: 1, axisLabelVisible: true, title: 'Entry' }));
    if (setup.sl) priceLinesRef.current.push(series.createPriceLine({ price: setup.sl, color: '#f43f5e', lineWidth: 1, axisLabelVisible: true, title: 'SL' }));
    if (setup.tp) priceLinesRef.current.push(series.createPriceLine({ price: setup.tp, color: '#10b981', lineWidth: 1, axisLabelVisible: true, title: 'TP' }));
  }, [candles, setup]);

  const rememberUserView = () => {
    userMovedRef.current = true;
    const range = chartRef.current?.timeScale().getVisibleRange();
    if (range) {
      const saved = { from: range.from as UTCTimestamp, to: range.to as UTCTimestamp };
      visibleRangeRef.current = saved;
      SAVED_VIEWPORTS.set(chartKey, saved);
    }
  };

  const resetView = () => {
    const chart = chartRef.current;
    if (!chart) return;
    SAVED_VIEWPORTS.delete(chartKey);
    visibleRangeRef.current = null;
    userMovedRef.current = false;
    programmaticRangeRef.current = true;
    chart.timeScale().fitContent();
    window.requestAnimationFrame(() => { programmaticRangeRef.current = false; });
  };

  return (
    <div className="relative w-full">
      <div ref={ref} className="w-full" style={{ height }} onPointerDown={rememberUserView} onWheel={rememberUserView} />
      <button type="button" className="absolute right-2 top-2 rounded-md border border-white/[0.08] bg-black/55 px-2 py-1 text-[9px] text-slate-300 hover:text-white" onClick={resetView}>
        Latest
      </button>
    </div>
  );
}

export default function BotSetupPreview({ bot }: { bot: Mt5Bot }) {
  const setup = useMemo<SetupInfo>(() => setupInfo(bot) || {
    stage: 'SCANNING',
    label: 'Live chart',
  }, [bot.native_signal, bot.native_last_execution, bot.last_trade]);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!bot.account_login || !bot.symbol || !bot.timeframe) {
      setCandles([]);
      return;
    }
    const load = () => mt5MarketService.candles(bot.symbol, bot.timeframe, 90, bot.account_login!)
      .then((rows) => { if (!cancelled) setCandles(Array.isArray(rows) ? rows : []); })
      .catch(() => { if (!cancelled && !candles.length) setCandles([]); });
    void load();
    const timer = window.setInterval(() => void load(), 3000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [bot.account_login, bot.symbol, bot.timeframe]);

  if (!candles.length) return null;

  return (
    <>
      <div className="mt-4 w-full overflow-hidden rounded-xl border border-white/[0.07] bg-black/20">
        <div className="flex items-center justify-between gap-3 px-3 py-2 border-b border-white/[0.06]">
          <div>
            <p className="text-[10px] uppercase tracking-widest text-slate-500 font-semibold">{setup.stage === 'SCANNING' ? 'Live bot chart' : 'Latest setup'}</p>
            <p className="text-[11px] text-slate-300">{bot.symbol} · {bot.timeframe} · {setup.label}</p>
          </div>
          <button type="button" onClick={() => setExpanded(true)} className="text-[10px] text-brand-300 hover:text-brand-200">
            View Chart
          </button>
        </div>
        <SetupChartCanvas candles={candles} setup={setup} height={155} chartKey={`bot-${bot.id}-compact`} />
      </div>

      <Modal
        open={expanded}
        onClose={() => setExpanded(false)}
        title={`${bot.name} setup`}
        sub={`${bot.symbol} · ${bot.timeframe} · ${setup.label}`}
        wide
      >
        <div className="rounded-xl border border-white/[0.07] bg-black/20 overflow-hidden">
          <SetupChartCanvas candles={candles} setup={setup} height={460} chartKey={`bot-${bot.id}-expanded`} />
        </div>
        <div className="mt-3 flex flex-wrap gap-2 text-[10px] text-slate-500">
          {setup.direction && <span className="chip">{setup.direction}</span>}
          {setup.entry && <span className="chip mono">Entry {setup.entry}</span>}
          {setup.sl && <span className="chip mono">SL {setup.sl}</span>}
          {setup.tp && <span className="chip mono">TP {setup.tp}</span>}
          <span className="chip">Snapshot from this running bot session</span>
        </div>
      </Modal>
    </>
  );
}
