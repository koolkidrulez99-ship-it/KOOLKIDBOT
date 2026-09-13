import { isSimulation } from '../config/runtime';
import type { RiskSettings } from '../types';
import { apiRequest } from './http';
import { simGetRisk, simSetRisk } from './simulationStore';

export const mt5RiskService = {
  list: (): Promise<RiskSettings[]> => isSimulation ? simGetRisk() : apiRequest<RiskSettings[]>('/api/mt5/risk'),
  save: (row: RiskSettings): Promise<RiskSettings> => isSimulation ? simSetRisk(row) : apiRequest<RiskSettings>('/api/mt5/risk', 'PUT', row),
};
