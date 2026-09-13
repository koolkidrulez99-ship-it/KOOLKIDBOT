import { derivMarketService } from './derivMarketService';
import type { Candle } from '../lib/market';
import type { DerivSymbol, DerivTick } from '../types';

const RESOLUTION_SECONDS: Record<string, number> = {
  '1': 60, '2': 120, '3': 180, '5': 300, '10': 600, '15': 900, '30': 1800,
  '60': 3600, '120': 7200, '240': 14400, '480': 28800, '1D': 86400, 'D': 86400,
};

let cachedSymbols: DerivSymbol[] | null = null;
async function symbols() {
  if (!cachedSymbols) cachedSymbols = await derivMarketService.activeSymbols();
  return cachedSymbols;
}

function resolutionSeconds(resolution: string) {
  return RESOLUTION_SECONDS[resolution] || Math.max(60, Number(resolution || 1) * 60);
}

function toTvBar(c: Candle) {
  return { time: c.time * 1000, open: c.open, high: c.high, low: c.low, close: c.close, volume: c.volume || 0 };
}

export function createDerivTradingViewDatafeed() {
  const unsubscribers = new Map<string, () => void>();
  const bars = new Map<string, any>();

  return {
    onReady(cb: (config: any) => void) {
      setTimeout(() => cb({
        supported_resolutions: ['1','2','3','5','10','15','30','60','120','240','480','1D'],
        exchanges: [{ value: 'DERIV', name: 'Deriv', desc: 'Deriv public market data' }],
        symbols_types: [{ name: 'All', value: '' }, { name: 'Forex', value: 'forex' }, { name: 'Synthetic', value: 'synthetic_index' }],
        supports_marks: false,
        supports_timescale_marks: false,
        supports_time: true,
      }), 0);
    },

    async searchSymbols(userInput: string, exchange: string, symbolType: string, onResult: (rows: any[]) => void) {
      const q = userInput.trim().toLowerCase();
      const list = await symbols();
      const rows = list.filter((s) => (!q || `${s.symbol} ${s.name}`.toLowerCase().includes(q)) && (!symbolType || s.symbol_type === symbolType));
      onResult(rows.slice(0, 250).map((s) => ({ symbol: s.symbol, full_name: `DERIV:${s.symbol}`, description: s.name, exchange: 'DERIV', ticker: s.symbol, type: s.symbol_type || s.market || 'index' })));
    },

    async resolveSymbol(symbolName: string, onResolve: (info: any) => void, onError: (reason: string) => void) {
      try {
        const ticker = symbolName.includes(':') ? symbolName.split(':').pop()! : symbolName;
        const list = await symbols();
        const row = list.find((s) => s.symbol === ticker) || { symbol: ticker, name: ticker, market: 'deriv', pip_size: 0.001 } as DerivSymbol;
        const pip = Number(row.pip_size || 0.001);
        const decimals = pip > 0 ? Math.max(0, Math.ceil(-Math.log10(pip))) : 3;
        onResolve({
          ticker: row.symbol,
          name: row.symbol,
          full_name: `DERIV:${row.symbol}`,
          description: row.name,
          type: row.symbol_type || row.market || 'index',
          session: '24x7',
          timezone: 'Etc/UTC',
          exchange: 'DERIV',
          listed_exchange: 'DERIV',
          minmov: 1,
          pricescale: Math.pow(10, Math.min(8, decimals)),
          has_intraday: true,
          has_daily: true,
          has_weekly_and_monthly: false,
          supported_resolutions: ['1','2','3','5','10','15','30','60','120','240','480','1D'],
          volume_precision: 0,
          data_status: 'streaming',
        });
      } catch (e) { onError(e instanceof Error ? e.message : 'Could not resolve Deriv symbol.'); }
    },

    async getBars(symbolInfo: any, resolution: string, periodParams: any, onHistory: (bars: any[], meta: any) => void, onError: (reason: string) => void) {
      try {
        const count = Math.min(5000, Math.max(100, Number(periodParams.countBack || 500)));
        const end = Number.isFinite(Number(periodParams.to)) ? Number(periodParams.to) : 'latest';
        const data = await derivMarketService.candles(symbolInfo.ticker || symbolInfo.name, resolutionSeconds(resolution), count, end);
        onHistory(data.map(toTvBar), { noData: data.length === 0 });
      } catch (e) { onError(e instanceof Error ? e.message : 'Deriv candle request failed.'); }
    },

    async subscribeBars(symbolInfo: any, resolution: string, onTick: (bar: any) => void, subscriberUID: string) {
      const symbol = symbolInfo.ticker || symbolInfo.name;
      const seconds = resolutionSeconds(resolution);
      const stop = await derivMarketService.subscribeTicks(symbol, (tick: DerivTick) => {
        const slot = Math.floor(tick.epoch / seconds) * seconds;
        const key = `${subscriberUID}:${slot}`;
        let bar = bars.get(key);
        if (!bar) {
          bar = { time: slot * 1000, open: tick.quote, high: tick.quote, low: tick.quote, close: tick.quote, volume: 1 };
          bars.set(key, bar);
        } else {
          bar = { ...bar, high: Math.max(bar.high, tick.quote), low: Math.min(bar.low, tick.quote), close: tick.quote, volume: Number(bar.volume || 0) + 1 };
          bars.set(key, bar);
        }
        onTick(bar);
      });
      unsubscribers.set(subscriberUID, stop);
    },

    unsubscribeBars(subscriberUID: string) {
      unsubscribers.get(subscriberUID)?.();
      unsubscribers.delete(subscriberUID);
      for (const key of [...bars.keys()]) if (key.startsWith(`${subscriberUID}:`)) bars.delete(key);
    },
  };
}
