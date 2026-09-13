import { isSimulation } from '../config/runtime';
import type { AiInsight, AiSettings } from '../types';
import { apiRequest } from './http';
import { simAiDelete, simAiGenerate, simAiGet, simAiSettings } from './simulationStore';

export interface AiControlSnapshot {
  insights: AiInsight[];
  settings: AiSettings;
}

export const aiControlService = {
  get: (): Promise<AiControlSnapshot> => isSimulation ? simAiGet() : apiRequest<AiControlSnapshot>('/api/mt5/ai'),
  generate: (): Promise<AiControlSnapshot> => isSimulation ? simAiGenerate() : apiRequest<AiControlSnapshot>('/api/mt5/ai', 'POST', {}),
  remove: (id: number): Promise<{ ok: boolean }> => isSimulation ? simAiDelete(id) : apiRequest<{ ok: boolean }>('/api/mt5/ai', 'DELETE', { id }),
  saveSettings: (settings: AiSettings): Promise<AiSettings> => isSimulation ? simAiSettings(settings) : apiRequest<AiSettings>('/api/mt5/ai', 'PUT', { settings }),
};
