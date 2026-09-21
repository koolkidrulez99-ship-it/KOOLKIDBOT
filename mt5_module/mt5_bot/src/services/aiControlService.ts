import { isSimulation } from '../config/runtime';
import type { AiAutoSelectMode, AiAutoSelectSnapshot, AiAutoSelectStatus, AiAutoStatus, AiInsight, AiSettings, AiTimeframe, AiTrialSnapshot, AiTrialStatus } from '../types';
import { apiRequest } from './http';
import { simAiDelete, simAiGenerate, simAiGet, simAiSettings } from './simulationStore';

export interface AiControlSnapshot {
  insights: AiInsight[];
  settings: AiSettings;
}

export function normalizeAiTrialSnapshot(value: AiTrialSnapshot | null | undefined): AiTrialSnapshot | null {
  if (!value || typeof value !== 'object') return null;
  const raw = value as AiTrialSnapshot & Record<string, unknown>;
  const executionStructure = ['bullish', 'bearish', 'neutral'].includes(String(raw.execution_structure)) ? raw.execution_structure : 'neutral';
  const biasStructure = ['bullish', 'bearish', 'neutral'].includes(String(raw.bias_structure)) ? raw.bias_structure : 'neutral';
  const confidence = Number(raw.confidence);
  return {
    ...raw,
    execution_structure: executionStructure as AiTrialSnapshot['execution_structure'],
    bias_structure: biasStructure as AiTrialSnapshot['bias_structure'],
    structure_shift: raw.structure_shift && typeof raw.structure_shift === 'object'
      ? {
          confirmed: Boolean(raw.structure_shift.confirmed),
          index: raw.structure_shift.index ?? null,
          time: raw.structure_shift.time ?? null,
        }
      : { confirmed: false, index: null, time: null },
    retest: raw.retest && typeof raw.retest === 'object'
      ? {
          level: raw.retest.level ?? null,
          touched: Boolean(raw.retest.touched),
          same_candle_blocked: Boolean(raw.retest.same_candle_blocked),
        }
      : { level: null, touched: false, same_candle_blocked: false },
    confidence: Number.isFinite(confidence) ? confidence : 0,
    confidence_factors: Array.isArray(raw.confidence_factors) ? raw.confidence_factors : [],
    last_confirmed_high: raw.last_confirmed_high ?? null,
    last_confirmed_low: raw.last_confirmed_low ?? null,
    trendline: raw.trendline ?? null,
    protected_structure: raw.protected_structure ?? null,
    proposed_trade: raw.proposed_trade ?? null,
    last_historical_signal: raw.last_historical_signal ?? null,
    last_execution: raw.last_execution ?? null,
    rules: raw.rules && typeof raw.rules === 'object'
      ? {
          completed_candles_only: Boolean(raw.rules.completed_candles_only),
          swing_left: Number(raw.rules.swing_left || 0),
          swing_right: Number(raw.rules.swing_right || 0),
          same_candle_shift_retest: Boolean(raw.rules.same_candle_shift_retest),
          required_sequence: Array.isArray(raw.rules.required_sequence) ? raw.rules.required_sequence : [],
          take_profit_r: Number(raw.rules.take_profit_r || 2),
        }
      : {
          completed_candles_only: true,
          swing_left: 0,
          swing_right: 0,
          same_candle_shift_retest: false,
          required_sequence: [],
          take_profit_r: 2,
        },
  };
}

export const aiControlService = {
  get: (): Promise<AiControlSnapshot> => isSimulation ? simAiGet() : apiRequest<AiControlSnapshot>('/api/mt5/ai'),
  generate: (): Promise<AiControlSnapshot> => isSimulation ? simAiGenerate() : apiRequest<AiControlSnapshot>('/api/mt5/ai', 'POST', {}),
  remove: (id: number): Promise<{ ok: boolean }> => isSimulation ? simAiDelete(id) : apiRequest<{ ok: boolean }>('/api/mt5/ai', 'DELETE', { id }),
  saveSettings: (settings: AiSettings): Promise<AiSettings> => isSimulation ? simAiSettings(settings) : apiRequest<AiSettings>('/api/mt5/ai', 'PUT', { settings }),

  // Session 1 trial endpoints are deliberately bridge-only and read-only.
  trialGet: async (): Promise<AiTrialStatus> => {
    const status = await apiRequest<AiTrialStatus>('/api/mt5/ai/trial');
    return { ...status, snapshot: normalizeAiTrialSnapshot(status?.snapshot) };
  },
  trialScan: async (account_login: number, symbol: string, execution_timeframe: AiTimeframe, bias_timeframe: AiTimeframe): Promise<AiTrialSnapshot> => {
    const snapshot = normalizeAiTrialSnapshot(await apiRequest<AiTrialSnapshot>('/api/mt5/ai/trial/scan', 'POST', { account_login, symbol, execution_timeframe, bias_timeframe }));
    if (!snapshot) throw new Error('AI scan returned an invalid or empty setup snapshot.');
    return snapshot;
  },
  trialExecute: (account_login: number, symbol: string, volume: number, confirm_live = false) =>
    apiRequest<{ executed: boolean; account_login: number; account_type?: 'demo' | 'live'; symbol: string; volume: number; direction: 'BUY' | 'SELL'; executed_at: string; mode: 'DEMO_AUTO_TRADE' | 'LIVE_AUTO_TRADE'; result: Record<string, unknown>; message: string }>('/api/mt5/ai/trial/execute', 'POST', { account_login, symbol, volume, confirm_live }),
  trialClear: (): Promise<{ ok: boolean }> => apiRequest<{ ok: boolean }>('/api/mt5/ai/trial', 'DELETE', {}),
  autoStatus: (): Promise<AiAutoStatus> => apiRequest<AiAutoStatus>('/api/mt5/ai/auto'),
  autoConfigure: (payload: { enabled: boolean; account_login?: number; symbol?: string; volume?: number; scan_seconds?: number; execution_timeframe?: AiTimeframe; bias_timeframe?: AiTimeframe; confirm_live?: boolean }): Promise<AiAutoStatus> =>
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
