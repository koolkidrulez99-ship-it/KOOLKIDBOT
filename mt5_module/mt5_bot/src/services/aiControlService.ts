import { isSimulation } from '../config/runtime';
import type { AiAutoSelectMode, AiAutoSelectSnapshot, AiAutoSelectStatus, AiAutoStatus, AiInsight, AiSettings, AiTrialSnapshot, AiTrialStatus } from '../types';
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
  trialExecute: (account_login: number, symbol: string, volume: number, confirm_live = false) =>
    apiRequest<{ executed: boolean; account_login: number; account_type?: 'demo' | 'live'; symbol: string; volume: number; direction: 'BUY' | 'SELL'; executed_at: string; mode: 'DEMO_AUTO_TRADE' | 'LIVE_AUTO_TRADE'; result: Record<string, unknown>; message: string }>('/api/mt5/ai/trial/execute', 'POST', { account_login, symbol, volume, confirm_live }),
  trialClear: (): Promise<{ ok: boolean }> => apiRequest<{ ok: boolean }>('/api/mt5/ai/trial', 'DELETE', {}),
  autoStatus: (): Promise<AiAutoStatus> => apiRequest<AiAutoStatus>('/api/mt5/ai/auto'),
  autoConfigure: (payload: { enabled: boolean; account_login?: number; symbol?: string; volume?: number; scan_seconds?: number; confirm_live?: boolean }): Promise<AiAutoStatus> =>
    apiRequest<AiAutoStatus>('/api/mt5/ai/auto', 'PUT', payload),

  autoSelectStatus: (): Promise<AiAutoSelectStatus> =>
    apiRequest<AiAutoSelectStatus>('/api/mt5/ai/auto-select'),
  autoSelectScan: (account_login: number, symbol: string, enabled_bot_ids: number[]): Promise<AiAutoSelectSnapshot> =>
    apiRequest<AiAutoSelectSnapshot>('/api/mt5/ai/auto-select/scan', 'POST', { account_login, symbol, enabled_bot_ids }),
  autoSelectConfigure: (payload: { enabled: boolean; account_login?: number; symbol?: string; enabled_bot_ids?: number[]; mode?: AiAutoSelectMode; scan_seconds?: number; confirm_live?: boolean }): Promise<AiAutoSelectStatus> =>
    apiRequest<AiAutoSelectStatus>('/api/mt5/ai/auto-select', 'PUT', payload),
  autoSelectExecute: (confirm_live = false): Promise<Record<string, unknown>> =>
    apiRequest<Record<string, unknown>>('/api/mt5/ai/auto-select/execute', 'POST', { confirm_live }),
};
