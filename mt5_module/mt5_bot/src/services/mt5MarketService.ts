import type { Candle } from '../lib/market';
import { apiRequest } from './http';
import type { Mt5Quote, Mt5SymbolInfo } from '../types';

const symbolCache = new Map<number, { at: number; rows: Mt5SymbolInfo[] }>();
const symbolInflight = new Map<number, Promise<Mt5SymbolInfo[]>>();
const SYMBOL_CACHE_MS = 30000;

async function loadSymbols(accountLogin?: number): Promise<Mt5SymbolInfo[]> {
  if (!accountLogin) {
    return apiRequest<Mt5SymbolInfo[]>('/api/mt5/symbols?visible_only=false&limit=5000');
  }
  const cached = symbolCache.get(accountLogin);
  if (cached && Date.now() - cached.at < SYMBOL_CACHE_MS) return cached.rows.map((row) => ({ ...row }));
  const pending = symbolInflight.get(accountLogin);
  if (pending) return (await pending).map((row) => ({ ...row }));

  const request = apiRequest<Mt5SymbolInfo[]>(`/api/mt5/symbols?visible_only=false&limit=5000&account_login=${accountLogin}`)
    .then((rows) => {
      symbolCache.set(accountLogin, { at: Date.now(), rows });
      return rows;
    })
    .finally(() => symbolInflight.delete(accountLogin));
  symbolInflight.set(accountLogin, request);
  return (await request).map((row) => ({ ...row }));
}

export const mt5MarketService = {
  quotes: (symbols: string[], accountLogin?: number): Promise<Mt5Quote[]> => {
    const requested = [...new Set(symbols.map((symbol) => String(symbol || '').trim()).filter(Boolean))];
    if (!requested.length || !accountLogin) return Promise.resolve([]);
    const params = new URLSearchParams({ symbols: requested.join(','), account_login: String(accountLogin) });
    return apiRequest<Mt5Quote[]>(`/api/mt5/quotes?${params.toString()}`);
  },
  candles: (symbol: string, timeframe: string, count = 220, accountLogin?: number, days?: number): Promise<Candle[]> => {
    const params = new URLSearchParams({ timeframe, count: String(count) });
    if (accountLogin) params.set('account_login', String(accountLogin));
    if (days) params.set('days', String(Math.max(1, Math.min(30, Math.round(days)))));
    return apiRequest<Candle[]>(`/api/mt5/candles/${encodeURIComponent(symbol)}?${params.toString()}`);
  },
  symbols: (accountLogin?: number): Promise<Mt5SymbolInfo[]> => loadSymbols(accountLogin),
  invalidateSymbols: (accountLogin?: number) => {
    if (accountLogin) {
      symbolCache.delete(accountLogin);
      symbolInflight.delete(accountLogin);
    } else {
      symbolCache.clear();
      symbolInflight.clear();
    }
  },
};
