import { useEffect, useMemo, useRef, useState } from 'react';
import { createChart, ColorType, CrosshairMode } from 'lightweight-charts';
import type { IChartApi, ISeriesApi, CandlestickData, HistogramData, UTCTimestamp } from 'lightweight-charts';
import { genCandles, MARKET, TF_SECONDS } from '../lib/market';
import type { Candle } from '../lib/market';
import type { Mt5Position } from '../types';
import { isSimulation } from '../config/runtime';
import { mt5MarketService } from '../services/mt5MarketService';
import { ChartMarkupOverlay, ChartMarkupToolbar, useChartMarkup } from './ChartMarkup';

export default function CandleChart({
  symbol,
  tfSeconds,
  historyDays = 7,
  livePrice,
  positions,
  height = 460,
  onLastCandle,
  digitsOverride,
  accountLogin,
  accountKey,
  accountLabel,
}: {
  symbol: string;
  tfSeconds: number;
  historyDays?: number;
  livePrice: number;
  positions: Mt5Position[];
  height?: number;
  onLastCandle?: (c: Candle) => void;
  digitsOverride?: number;
  accountLogin?: number;
  accountKey?: string | number | null;
  accountLabel?: string;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const lastRef = useRef<Candle | null>(null);
  const [chartRevision, setChartRevision] = useState(0);
  const [candleTimes, setCandleTimes] = useState<number[]>([]);
  const digits = digitsOverride ?? MARKET[symbol]?.digits ?? 5;
  const markup = useChartMarkup('mt5', accountKey, symbol);

  const symbolPositions = useMemo(() => positions.filter((p) => p.symbol === symbol), [positions, symbol]);

  // (re)build chart when symbol / timeframe changes
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;

    const chart = createChart(el, {
      autoSize: true,
      height,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#68738c',
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 10,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: 'rgba(148,163,184,0.06)' },
        horzLines: { color: 'rgba(148,163,184,0.06)' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: 'rgba(91,140,255,0.35)', labelBackgroundColor: '#1d4ed8' },
        horzLine: { color: 'rgba(91,140,255,0.35)', labelBackgroundColor: '#1d4ed8' },
      },
      rightPriceScale: { borderColor: 'rgba(148,163,184,0.12)' },
      timeScale: { borderColor: 'rgba(148,163,184,0.12)', timeVisible: true, secondsVisible: false },
    });

    const candles = chart.addCandlestickSeries({
      upColor: '#10b981',
      downColor: '#f43f5e',
      borderUpColor: '#10b981',
      borderDownColor: '#f43f5e',
      wickUpColor: 'rgba(16,185,129,0.7)',
      wickDownColor: 'rgba(244,63,94,0.7)',
      priceFormat: { type: 'price', precision: digits, minMove: 1 / Math.pow(10, digits) },
    });

    const vol = chart.addHistogramSeries({
      priceScaleId: 'vol',
      priceFormat: { type: 'volume' },
    });
    chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });

    let cancelled = false;
    const applyData = (data: Candle[]) => {
      if (cancelled) return;
      const cd: CandlestickData<UTCTimestamp>[] = data.map((c) => ({
        time: c.time as UTCTimestamp,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }));
      const vd: HistogramData<UTCTimestamp>[] = data.map((c) => ({
        time: c.time as UTCTimestamp,
        value: c.volume,
        color: c.close >= c.open ? 'rgba(16,185,129,0.28)' : 'rgba(244,63,94,0.28)',
      }));
      candles.setData(cd);
      vol.setData(vd);
      chart.timeScale().fitContent();
      chart.timeScale().scrollToPosition(4, false);
      lastRef.current = data[data.length - 1] || null;
      setCandleTimes(data.map((row) => row.time));
    };

    chartRef.current = chart;
    candleSeriesRef.current = candles;
    volSeriesRef.current = vol;
    setChartRevision((value) => value + 1);

    if (isSimulation) {
      const simulatedBars = Math.max(220, Math.min(5000, Math.ceil((Math.max(1, Math.min(30, historyDays)) * 86400) / tfSeconds) + 4));
      applyData(genCandles(symbol, tfSeconds, simulatedBars));
    } else {
      const tf = (Object.entries(TF_SECONDS).find(([, seconds]) => seconds === tfSeconds)?.[0] || 'M15');
      mt5MarketService.candles(symbol, tf, 220, accountLogin, historyDays).then(applyData).catch(() => {
        // Keep the live bridge chart empty instead of fabricating historical candles.
      });
    }

    return () => {
      cancelled = true;
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volSeriesRef.current = null;
      lastRef.current = null;
    };
  }, [symbol, tfSeconds, historyDays, digits, height, accountLogin]);

  // live price tick -> update/append last candle
  useEffect(() => {
    const series = candleSeriesRef.current;
    const last = lastRef.current;
    if (!series || !last || !livePrice) return;
    const price = Number(livePrice.toFixed(digits));
    const nowSlot = Math.floor(Date.now() / 1000 / tfSeconds) * tfSeconds;

    let cur = last;
    if (nowSlot > last.time) {
      cur = { time: nowSlot, open: last.close, high: Math.max(last.close, price), low: Math.min(last.close, price), close: price, volume: 100 };
      volSeriesRef.current?.update({ time: nowSlot as UTCTimestamp, value: 120, color: 'rgba(91,140,255,0.3)' });
      setCandleTimes((prev) => prev[prev.length - 1] === nowSlot ? prev : [...prev.slice(-999), nowSlot]);
    } else {
      cur = { ...last, close: price, high: Math.max(last.high, price), low: Math.min(last.low, price) };
    }
    lastRef.current = cur;
    series.update({ time: cur.time as UTCTimestamp, open: cur.open, high: cur.high, low: cur.low, close: cur.close });
    onLastCandle?.(cur);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [livePrice, symbol, tfSeconds, digits]);

  // position markers
  useEffect(() => {
    const series = candleSeriesRef.current;
    if (!series) return;
    const markers = symbolPositions
      .map((p) => {
        const t = Math.floor(new Date(p.open_time).getTime() / 1000 / tfSeconds) * tfSeconds;
        return {
          time: t as UTCTimestamp,
          position: (p.type === 'buy' ? 'belowBar' : 'aboveBar') as 'belowBar' | 'aboveBar',
          color: p.type === 'buy' ? '#10b981' : '#f43f5e',
          shape: (p.type === 'buy' ? 'arrowUp' : 'arrowDown') as 'arrowUp' | 'arrowDown',
          text: `${p.type === 'buy' ? 'B' : 'S'} ${Number(p.volume).toFixed(2)}`,
          size: 1,
        };
      })
      .sort((a, b) => (a.time as number) - (b.time as number));
    // dedupe identical times (lightweight-charts requires strictly ascending unique times)
    const seen = new Set<number>();
    const deduped = markers.filter((m) => {
      const t = m.time as number;
      if (seen.has(t)) return false;
      seen.add(t);
      return true;
    });
    try {
      series.setMarkers(deduped);
    } catch { /* markers outside visible range in some tf - safe to ignore */ }
  }, [symbolPositions, tfSeconds, symbol]);

  return (
    <div className="space-y-2">
      <div className="rounded-xl border border-white/[0.06] bg-black/15 px-2.5 py-2">
        <ChartMarkupToolbar controller={markup} scopeLabel={`${accountLabel || `MT5 #${accountKey ?? 'unassigned'}`} · ${symbol}`} />
      </div>
      <div className="relative w-full" style={{ height }}>
        <div ref={wrapRef} className="absolute inset-0 h-full w-full" />
        <ChartMarkupOverlay
          controller={markup}
          chartRef={chartRef}
          seriesRef={candleSeriesRef}
          candleTimes={candleTimes}
          revisionToken={chartRevision}
          digits={digits}
        />
      </div>
    </div>
  );
}
