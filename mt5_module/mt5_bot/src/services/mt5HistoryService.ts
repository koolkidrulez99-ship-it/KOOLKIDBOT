import { isSimulation } from '../config/runtime';
import type { Mt5HistoryRow, Mt5Stats } from '../types';
import { apiRequest } from './http';
import { simHistory, simStats } from './simulationStore';

let historyCache: { at: number; rows: Mt5HistoryRow[] } | null = null;
let historyInflight: Promise<Mt5HistoryRow[]> | null = null;
const HISTORY_CACHE_MS = 15000;

async function loadHistory(force = false): Promise<Mt5HistoryRow[]> {
  if (isSimulation) return simHistory();
  const now = Date.now();
  if (!force && historyCache && now - historyCache.at < HISTORY_CACHE_MS) {
    return historyCache.rows.map((row) => ({ ...row }));
  }
  if (!force && historyInflight) {
    return (await historyInflight).map((row) => ({ ...row }));
  }

  const request = apiRequest<Mt5HistoryRow[]>('/api/mt5/history?days=0')
    .then((rows) => {
      historyCache = { at: Date.now(), rows };
      return rows;
    })
    .finally(() => {
      if (historyInflight === request) historyInflight = null;
    });

  historyInflight = request;
  return (await request).map((row) => ({ ...row }));
}

export const mt5HistoryService = {
  list: (force = false): Promise<Mt5HistoryRow[]> => loadHistory(force),
  invalidate: () => { historyCache = null; historyInflight = null; },
  stats: (): Promise<Mt5Stats> => isSimulation ? simStats() : apiRequest<Mt5Stats>('/api/mt5/stats'),
};
