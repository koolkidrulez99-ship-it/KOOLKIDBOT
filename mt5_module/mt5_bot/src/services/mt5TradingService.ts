import { isSimulation } from '../config/runtime';
import type { Mt5Position } from '../types';
import { apiRequest } from './http';
import { simOpenTrade } from './simulationStore';

export interface OpenTradePayload {
  account_login: number;
  symbol: string;
  type: 'buy' | 'sell';
  volume: number;
  sl?: number | null;
  tp?: number | null;
  source?: string;
}

export const mt5TradingService = {
  open: (payload: OpenTradePayload): Promise<Mt5Position> => isSimulation ? simOpenTrade(payload) : apiRequest<Mt5Position>('/api/mt5/trade', 'POST', payload, 60000),
};
