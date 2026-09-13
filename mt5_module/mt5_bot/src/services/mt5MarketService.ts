import type { Candle } from '../lib/market';
import { apiRequest } from './http';
import type { Mt5Quote, Mt5SymbolInfo } from '../types';

export const mt5MarketService = {
  quotes: (symbols: string[], accountLogin?: number): Promise<Mt5Quote[]> =>
    apiRequest<Mt5Quote[]>(`/api/mt5/quotes?symbols=${encodeURIComponent(symbols.join(','))}${accountLogin ? `&account_login=${accountLogin}` : ''}`),
  candles: (symbol: string, timeframe: string, count = 220, accountLogin?: number): Promise<Candle[]> =>
    apiRequest<Candle[]>(`/api/mt5/candles/${encodeURIComponent(symbol)}?timeframe=${encodeURIComponent(timeframe)}&count=${count}${accountLogin ? `&account_login=${accountLogin}` : ''}`),
  symbols: (accountLogin?: number): Promise<Mt5SymbolInfo[]> => apiRequest<Mt5SymbolInfo[]>(`/api/mt5/symbols?visible_only=false&limit=5000${accountLogin ? `&account_login=${accountLogin}` : ''}`),
};
