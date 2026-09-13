import { isSimulation } from '../config/runtime';
import type { Mt5HistoryRow, Mt5Stats } from '../types';
import { apiRequest } from './http';
import { simHistory, simStats } from './simulationStore';

export const mt5HistoryService = {
  list: (): Promise<Mt5HistoryRow[]> => isSimulation ? simHistory() : apiRequest<Mt5HistoryRow[]>('/api/mt5/history'),
  stats: (): Promise<Mt5Stats> => isSimulation ? simStats() : apiRequest<Mt5Stats>('/api/mt5/stats'),
};
