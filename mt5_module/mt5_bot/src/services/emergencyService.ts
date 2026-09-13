import { isSimulation } from '../config/runtime';
import { apiRequest } from './http';
import { simCloseAllPositions, simStopAllBots, simStopAndCloseAll } from './simulationStore';

export const emergencyService = {
  stopAllBots: (): Promise<{ ok: boolean; stopped: number }> => isSimulation ? simStopAllBots() : apiRequest<{ ok: boolean; stopped: number }>('/api/mt5/emergency/stop-all-bots', 'POST', {}),
  closeAllPositions: (): Promise<{ ok: boolean; closed: number; realized: number }> => isSimulation ? simCloseAllPositions() : apiRequest<{ ok: boolean; closed: number; realized: number }>('/api/mt5/positions/close-all', 'POST', {}),
  stopAndCloseAll: (): Promise<{ ok: boolean; stopped: number; closed: number; realized: number }> => isSimulation ? simStopAndCloseAll() : apiRequest<{ ok: boolean; stopped: number; closed: number; realized: number }>('/api/mt5/emergency/stop-and-close-all', 'POST', {}),
};
