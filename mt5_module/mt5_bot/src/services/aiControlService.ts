import { isSimulation } from '../config/runtime';
import type { AiInsight, AiSettings, AiTrialSnapshot, AiTrialStatus } from '../types';
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

  // Session 1 trial endpoints are deliberately bridge-only and read-only.
  trialGet: (): Promise<AiTrialStatus> => apiRequest<AiTrialStatus>('/api/mt5/ai/trial'),
  trialScan: (account_login: number, symbol: string): Promise<AiTrialSnapshot> =>
    apiRequest<AiTrialSnapshot>('/api/mt5/ai/trial/scan', 'POST', { account_login, symbol }),
  trialExecute: (account_login: number, symbol: string, volume: number) =>
    apiRequest<{ executed: boolean; account_login: number; symbol: string; volume: number; direction: 'BUY' | 'SELL'; executed_at: string; mode: 'DEMO_AUTO_TRADE'; result: Record<string, unknown>; message: string }>('/api/mt5/ai/trial/execute', 'POST', { account_login, symbol, volume }),
  trialClear: (): Promise<{ ok: boolean }> => apiRequest<{ ok: boolean }>('/api/mt5/ai/trial', 'DELETE', {}),
};
