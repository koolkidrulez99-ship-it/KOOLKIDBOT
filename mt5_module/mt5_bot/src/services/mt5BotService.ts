import { isSimulation } from '../config/runtime';
import type { BotPerformance, Mt5Bot } from '../types';
import { apiFormRequest, apiRequest } from './http';
import { simBotControl, simBotPerformance, simCreateBot, simDeleteBot, simListBots } from './simulationStore';

function bridgeControl(id: number, action: string, payload: Record<string, unknown>): Promise<Mt5Bot> {
  if (action === 'launch') return apiRequest<Mt5Bot>(`/api/mt5/bots/${id}/start`, 'POST', payload);
  if (action === 'update') return apiRequest<Mt5Bot>(`/api/mt5/bots/${id}`, 'PUT', payload);
  return apiRequest<Mt5Bot>(`/api/mt5/bots/${id}/${action}`, 'POST', payload);
}

export interface BotFileUploadResult {
  bot_id: number;
  ea?: { filename: string; size_bytes: number; sha256: string; stored_path: string };
  preset?: { filename: string; size_bytes: number; sha256: string; stored_path: string };
  bot: Mt5Bot;
}

export const mt5BotService = {
  list: (): Promise<Mt5Bot[]> => isSimulation ? simListBots() : apiRequest<Mt5Bot[]>('/api/mt5/bots'),
  create: (payload: Record<string, unknown>): Promise<Mt5Bot> => isSimulation ? simCreateBot(payload) : apiRequest<Mt5Bot>('/api/mt5/bots', 'POST', payload),
  remove: (id: number): Promise<{ ok: boolean }> => isSimulation ? simDeleteBot(id) : apiRequest<{ ok: boolean }>(`/api/mt5/bots/${id}`, 'DELETE'),
  control: (id: number, action: string, payload: Record<string, unknown> = {}): Promise<Mt5Bot> =>
    isSimulation ? simBotControl(id, action, payload) : bridgeControl(id, action, payload),
  performance: (id: number): Promise<BotPerformance> => isSimulation ? simBotPerformance(id) : apiRequest<BotPerformance>(`/api/mt5/bots/${id}/performance`),
  uploadFiles: async (id: number, eaFile?: File | null, presetFile?: File | null): Promise<BotFileUploadResult> => {
    if (isSimulation) throw new Error('Actual EA files can only be uploaded while the local MT5 bridge is running.');
    const form = new FormData();
    if (eaFile) form.append('ea_file', eaFile, eaFile.name);
    if (presetFile) form.append('preset_file', presetFile, presetFile.name);
    if (!eaFile && !presetFile) throw new Error('Choose an .ex5 EA file or .set preset first.');
    return apiFormRequest<BotFileUploadResult>(`/api/mt5/bots/${id}/files`, form);
  },
};
