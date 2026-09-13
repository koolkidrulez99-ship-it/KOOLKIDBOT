import { useEffect, useMemo, useRef } from 'react';
import { createChart, ColorType, CrosshairMode } from 'lightweight-charts';
import type { IChartApi, ISeriesApi, CandlestickData, HistogramData, UTCTimestamp } from 'lightweight-charts';
import { genCandles, MARKET, TF_SECONDS } from '../lib/market';
import type { Candle } from '../lib/market';
import type { Mt5Position } from '../types';
import { isSimulation } from '../config/runtime';
import { mt5MarketService } from '../services/mt5MarketService';

export default function CandleChart({
  symbol,
  tfSeconds,
  livePrice,
  positions,
  height = 460,
  onLastCandle,
  digitsOverride,
}: {
  symbol: string;
  tfSeconds: number;
  livePrice: number;
  positions: Mt5Position[];
  height?: number;
  onLastCandle?: (c: Candle) => void;
  digitsOverride?: number;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const lastRef = useRef<Candle | null>(null);
  const digits = digitsOverride ?? MARKET[symbol]?.digits ?? 5;

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
    };

    chartRef.current = chart;
    candleSeriesRef.current = candles;
    volSeriesRef.current = vol;

    if (isSimulation) {
      applyData(genCandles(symbol, tfSeconds, 220));
    } else {
      const tf = (Object.entries(TF_SECONDS).find(([, seconds]) => seconds === tfSeconds)?.[0] || 'M15');
      mt5MarketService.candles(symbol, tf, 220).then(applyData).catch(() => {
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
  }, [symbol, tfSeconds, digits, height]);

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

  return <div ref={wrapRef} className="w-full" style={{ height }} />;
}
