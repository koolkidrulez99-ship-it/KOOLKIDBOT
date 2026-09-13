import { isSimulation } from '../config/runtime';
import type { Mt5HistoryRow, Mt5Position } from '../types';
import { apiRequest } from './http';
import { simCloseAllPositions, simClosePosition, simListPositions } from './simulationStore';

export interface ClosePositionResult {
  ok: boolean;
  profit: number;
  closed: Mt5HistoryRow;
}

export const mt5PositionService = {
  list: (): Promise<Mt5Position[]> => isSimulation ? simListPositions() : apiRequest<Mt5Position[]>('/api/mt5/positions'),
  close: (id: number): Promise<ClosePositionResult> => isSimulation ? simClosePosition(id) : apiRequest<ClosePositionResult>(`/api/mt5/positions/${id}/close`, 'POST', {}, 60000),
  closeAll: (): Promise<{ ok: boolean; closed: number; realized: number }> => isSimulation ? simCloseAllPositions() : apiRequest<{ ok: boolean; closed: number; realized: number }>('/api/mt5/positions/close-all', 'POST', {}),
};
