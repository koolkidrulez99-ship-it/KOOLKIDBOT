import { useEffect, useMemo, useRef, useState } from 'react';
import { createChart, ColorType, CrosshairMode } from 'lightweight-charts';
import type { CandlestickData, IChartApi, ISeriesApi, UTCTimestamp } from 'lightweight-charts';
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

function SetupChartCanvas({ candles, setup, height }: { candles: Candle[]; setup: SetupInfo; height: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);

  useEffect(() => {
    if (!ref.current || !candles.length) return;
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
    const data: CandlestickData<UTCTimestamp>[] = candles.map((c) => ({
      time: c.time as UTCTimestamp, open: c.open, high: c.high, low: c.low, close: c.close,
    }));
    series.setData(data);

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

    if (setup.entry) series.createPriceLine({ price: setup.entry, color: '#5b8cff', lineWidth: 1, axisLabelVisible: true, title: 'Entry' });
    if (setup.sl) series.createPriceLine({ price: setup.sl, color: '#f43f5e', lineWidth: 1, axisLabelVisible: true, title: 'SL' });
    if (setup.tp) series.createPriceLine({ price: setup.tp, color: '#10b981', lineWidth: 1, axisLabelVisible: true, title: 'TP' });
    chart.timeScale().fitContent();
    chartRef.current = chart;
    seriesRef.current = series;
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [candles, setup, height]);

  return <div ref={ref} className="w-full" style={{ height }} />;
}

export default function BotSetupPreview({ bot }: { bot: Mt5Bot }) {
  const setup = useMemo(() => setupInfo(bot), [bot.native_signal, bot.native_last_execution, bot.last_trade]);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!setup || !bot.account_login || !bot.symbol || !bot.timeframe) {
      setCandles([]);
      return;
    }
    mt5MarketService.candles(bot.symbol, bot.timeframe, 90, bot.account_login)
      .then((rows) => { if (!cancelled) setCandles(rows); })
      .catch(() => { if (!cancelled) setCandles([]); });
    return () => { cancelled = true; };
  }, [bot.account_login, bot.symbol, bot.timeframe, setup?.stage, setup?.eventTime, setup?.entry, setup?.sl, setup?.tp]);

  if (!setup || !candles.length) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setExpanded(true)}
        className="mt-4 w-full overflow-hidden rounded-xl border border-white/[0.07] bg-black/20 text-left transition hover:border-brand-400/30 hover:bg-black/25"
        title="Open larger setup chart"
      >
        <div className="flex items-center justify-between gap-3 px-3 py-2 border-b border-white/[0.06]">
          <div>
            <p className="text-[10px] uppercase tracking-widest text-slate-500 font-semibold">Latest setup</p>
            <p className="text-[11px] text-slate-300">{bot.symbol} · {bot.timeframe} · {setup.label}</p>
          </div>
          <span className="text-[10px] text-brand-300">Click to enlarge</span>
        </div>
        <SetupChartCanvas candles={candles} setup={setup} height={155} />
      </button>

      <Modal
        open={expanded}
        onClose={() => setExpanded(false)}
        title={`${bot.name} setup`}
        sub={`${bot.symbol} · ${bot.timeframe} · ${setup.label}`}
        wide
      >
        <div className="rounded-xl border border-white/[0.07] bg-black/20 overflow-hidden">
          <SetupChartCanvas candles={candles} setup={setup} height={460} />
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
