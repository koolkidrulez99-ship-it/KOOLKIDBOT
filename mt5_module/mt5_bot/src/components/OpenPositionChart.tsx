import { useCallback, useEffect, useRef, useState } from 'react';
import { createChart, ColorType, CrosshairMode } from 'lightweight-charts';
import type { CandlestickData, IChartApi, IPriceLine, ISeriesApi, UTCTimestamp } from 'lightweight-charts';
import type { Candle } from '../lib/market';
import { mt5MarketService } from '../services/mt5MarketService';
import { mt5MultiAccountService } from '../services/mt5MultiAccountService';
import Modal from './Modal';

type SavedPositionChartRange = { from: UTCTimestamp; to: UTCTimestamp };
const SAVED_POSITION_VIEWPORTS = new Map<string, SavedPositionChartRange>();

type ChartPosition = {
  ticket: number;
  account_login: number;
  multiAccountId?: string;
  symbol: string;
  type: 'buy' | 'sell';
  volume: number;
  open_price: number;
  current_price: number;
  sl: number | null;
  tp: number | null;
  open_time: string;
};

export default function OpenPositionChart({ position, onClose }: { position: ChartPosition | null; onClose: () => void }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const linesRef = useRef<IPriceLine[]>([]);
  const userMovedRef = useRef(false);
  const visibleRangeRef = useRef<SavedPositionChartRange | null>(null);
  const programmaticRangeRef = useRef(false);
  const renderedLastTimeRef = useRef<number | null>(null);
  const [timeframe, setTimeframe] = useState('M5');
  const chartKey = position ? `${position.multiAccountId || position.account_login}:${position.ticket}:${timeframe}` : '';
  const [candles, setCandles] = useState<Candle[]>([]);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    if (!position) return;
    try {
      const rows = position.multiAccountId
        ? await mt5MultiAccountService.candles(position.multiAccountId, position.symbol, timeframe, 220)
        : await mt5MarketService.candles(position.symbol, timeframe, 220, position.account_login);
      const safeRows = Array.isArray(rows)
        ? rows.filter((row) => row && Number.isFinite(Number(row.time)) && Number.isFinite(Number(row.open)) && Number.isFinite(Number(row.high)) && Number.isFinite(Number(row.low)) && Number.isFinite(Number(row.close)))
        : [];
      setCandles(safeRows as Candle[]);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to load MT5 candles.');
    }
  }, [position?.multiAccountId, position?.account_login, position?.symbol, timeframe]);

  useEffect(() => {
    if (!position) return;
    void load();
    const timer = window.setInterval(() => void load(), 2500);
    return () => window.clearInterval(timer);
  }, [chartKey, load]);

  useEffect(() => {
    if (!position || !hostRef.current) return;
    const savedViewport = SAVED_POSITION_VIEWPORTS.get(chartKey) || null;
    userMovedRef.current = Boolean(savedViewport);
    visibleRangeRef.current = savedViewport;
    renderedLastTimeRef.current = null;
    const chart = createChart(hostRef.current, {
      autoSize: true,
      height: 460,
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
        SAVED_POSITION_VIEWPORTS.set(chartKey, saved);
      }
    };
    chart.timeScale().subscribeVisibleTimeRangeChange(rememberRange);
    chartRef.current = chart;
    seriesRef.current = series;
    return () => {
      if (userMovedRef.current) {
        const range = chart.timeScale().getVisibleRange();
        if (range) SAVED_POSITION_VIEWPORTS.set(chartKey, { from: range.from as UTCTimestamp, to: range.to as UTCTimestamp });
      }
      chart.timeScale().unsubscribeVisibleTimeRangeChange(rememberRange);
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      linesRef.current = [];
      renderedLastTimeRef.current = null;
    };
  }, [chartKey]);

  useEffect(() => {
    const chart = chartRef.current;
    const series = seriesRef.current;
    if (!position || !chart || !series || !candles.length) return;
    const data: CandlestickData<UTCTimestamp>[] = candles.map((row) => ({
      time: row.time as UTCTimestamp, open: row.open, high: row.high, low: row.low, close: row.close,
    }));
    const savedRange = SAVED_POSITION_VIEWPORTS.get(chartKey)
      || (userMovedRef.current ? (visibleRangeRef.current || chart.timeScale().getVisibleRange() as SavedPositionChartRange | null) : null);
    const previousLastTime = renderedLastTimeRef.current;
    programmaticRangeRef.current = true;

    if (previousLastTime === null) {
      series.setData(data);
      renderedLastTimeRef.current = Number(data[data.length - 1].time);
      if (savedRange) {
        const range = { from: savedRange.from as UTCTimestamp, to: savedRange.to as UTCTimestamp };
        chart.timeScale().setVisibleRange(range);
        visibleRangeRef.current = range;
        userMovedRef.current = true;
      } else {
        chart.timeScale().fitContent();
        chart.timeScale().scrollToPosition(4, false);
      }
    } else {
      const previousIndex = data.findIndex((row) => Number(row.time) === previousLastTime);
      if (previousIndex >= 0) {
        for (let index = previousIndex; index < data.length; index += 1) {
          series.update(data[index]);
        }
        renderedLastTimeRef.current = Number(data[data.length - 1].time);
      } else {
        // Only rebuild the full series if MT5 returned a discontinuous history window.
        // Normal 2.5s polling never calls setData(), so a user's pan/zoom cannot be reset.
        const rangeBeforeRebuild = savedRange || (userMovedRef.current ? chart.timeScale().getVisibleRange() : null);
        series.setData(data);
        renderedLastTimeRef.current = Number(data[data.length - 1].time);
        if (rangeBeforeRebuild) {
          const range = { from: rangeBeforeRebuild.from as UTCTimestamp, to: rangeBeforeRebuild.to as UTCTimestamp };
          chart.timeScale().setVisibleRange(range);
          visibleRangeRef.current = range;
          SAVED_POSITION_VIEWPORTS.set(chartKey, range);
        } else {
          chart.timeScale().fitContent();
          chart.timeScale().scrollToPosition(4, false);
        }
      }
    }
    window.requestAnimationFrame(() => { programmaticRangeRef.current = false; });
    const opened = Math.floor(Date.parse(position.open_time) / 1000);
    const marker = candles.reduce((best, row) => Math.abs(row.time - opened) < Math.abs(best.time - opened) ? row : best, candles[0]);
    series.setMarkers([{
      time: marker.time as UTCTimestamp,
      position: position.type === 'buy' ? 'belowBar' : 'aboveBar',
      color: position.type === 'buy' ? '#10b981' : '#f43f5e',
      shape: position.type === 'buy' ? 'arrowUp' : 'arrowDown',
      text: `${position.type.toUpperCase()} #${position.ticket}`,
      size: 1,
    }]);
  }, [candles, position]);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series || !position) return;
    linesRef.current.forEach((line) => series.removePriceLine(line));
    linesRef.current = [
      series.createPriceLine({ price: Number(position.open_price), color: '#5b8cff', lineWidth: 1, axisLabelVisible: true, title: 'Entry' }),
      series.createPriceLine({ price: Number(position.current_price), color: '#94a3b8', lineWidth: 1, axisLabelVisible: true, title: 'Current' }),
    ];
    if (position.sl) linesRef.current.push(series.createPriceLine({ price: Number(position.sl), color: '#f43f5e', lineWidth: 1, axisLabelVisible: true, title: 'SL' }));
    if (position.tp) linesRef.current.push(series.createPriceLine({ price: Number(position.tp), color: '#10b981', lineWidth: 1, axisLabelVisible: true, title: 'TP' }));
  }, [position?.open_price, position?.current_price, position?.sl, position?.tp, position?.ticket]);

  return (
    <Modal open={position !== null} onClose={onClose} title={position ? `${position.symbol} · #${position.ticket}` : 'Position chart'} sub={position ? `${position.type.toUpperCase()} · ${position.volume} lots · live MT5 data` : undefined} wide>
      <div className="mb-3 flex flex-wrap gap-2">
        {['M1', 'M5', 'M15', 'H1'].map((tf) => <button key={tf} type="button" className={timeframe === tf ? 'btn-primary !px-3 !py-1.5 text-xs' : 'btn-secondary !px-3 !py-1.5 text-xs'} onClick={() => setTimeframe(tf)}>{tf}</button>)}
      </div>
      <div className="relative rounded-xl border border-white/[0.07] bg-black/20 overflow-hidden">
        <div
          ref={hostRef}
          className="w-full"
          style={{ height: 460 }}
          onPointerDown={() => {
            userMovedRef.current = true;
            const range = chartRef.current?.timeScale().getVisibleRange();
            if (range) {
              const saved = { from: range.from as UTCTimestamp, to: range.to as UTCTimestamp };
              visibleRangeRef.current = saved;
              SAVED_POSITION_VIEWPORTS.set(chartKey, saved);
            }
          }}
          onWheel={() => {
            userMovedRef.current = true;
            const range = chartRef.current?.timeScale().getVisibleRange();
            if (range) {
              const saved = { from: range.from as UTCTimestamp, to: range.to as UTCTimestamp };
              visibleRangeRef.current = saved;
              SAVED_POSITION_VIEWPORTS.set(chartKey, saved);
            }
          }}
        />
        <button
          type="button"
          className="absolute right-2 top-2 rounded-md border border-white/[0.08] bg-black/55 px-2 py-1 text-[9px] text-slate-300 hover:text-white"
          onClick={() => {
            const chart = chartRef.current;
            if (!chart) return;
            visibleRangeRef.current = null;
            userMovedRef.current = false;
            SAVED_POSITION_VIEWPORTS.delete(chartKey);
            programmaticRangeRef.current = true;
            chart.timeScale().fitContent();
            chart.timeScale().scrollToPosition(4, false);
            window.requestAnimationFrame(() => { programmaticRangeRef.current = false; });
          }}
        >
          Latest
        </button>
      </div>
      {error && <p className="mt-2 text-xs text-loss-400">{error}</p>}
      {position && <div className="mt-3 flex flex-wrap gap-2 text-[10px] text-slate-500">
        <span className="chip mono">Entry {position.open_price}</span>
        <span className="chip mono">Current {position.current_price}</span>
        {position.sl ? <span className="chip mono">SL {position.sl}</span> : null}
        {position.tp ? <span className="chip mono">TP {position.tp}</span> : null}
        <span className="chip">Updates from MT5 every 2.5s</span>
      </div>}
    </Modal>
  );
}
