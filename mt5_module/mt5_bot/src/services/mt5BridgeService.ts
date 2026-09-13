import { isSimulation } from '../config/runtime';
import type { BridgeInfo } from '../types';
import { apiRequest } from './http';
import { simBridgeInfo } from './simulationStore';

export const mt5BridgeService = {
  status: (): Promise<BridgeInfo> => isSimulation ? simBridgeInfo() : apiRequest<BridgeInfo>('/api/mt5/bridge/status'),
};
