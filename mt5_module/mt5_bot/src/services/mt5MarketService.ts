import type { Candle } from '../lib/market';
import { apiRequest } from './http';
import type { Mt5Quote, Mt5SymbolInfo } from '../types';

export const mt5MarketService = {
  quotes: (symbols: string[], accountLogin?: number): Promise<Mt5Quote[]> => {
    const requested = [...new Set(symbols.map((symbol) => String(symbol || '').trim()).filter(Boolean))];
    if (!requested.length || !accountLogin) return Promise.resolve([]);
    const params = new URLSearchParams({ symbols: requested.join(','), account_login: String(accountLogin) });
    return apiRequest<Mt5Quote[]>(`/api/mt5/quotes?${params.toString()}`);
  },
  candles: (symbol: string, timeframe: string, count = 220, accountLogin?: number): Promise<Candle[]> =>
    apiRequest<Candle[]>(`/api/mt5/candles/${encodeURIComponent(symbol)}?timeframe=${encodeURIComponent(timeframe)}&count=${count}${accountLogin ? `&account_login=${accountLogin}` : ''}`),
  symbols: (accountLogin?: number): Promise<Mt5SymbolInfo[]> => apiRequest<Mt5SymbolInfo[]>(`/api/mt5/symbols?visible_only=false&limit=5000${accountLogin ? `&account_login=${accountLogin}` : ''}`),
};
