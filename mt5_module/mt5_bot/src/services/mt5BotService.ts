import { apiUrl, isSimulation } from '../config/runtime';
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

export interface BotCompileResult {
  bot_id: number;
  success: boolean;
  source_filename: string;
  ex5_filename?: string | null;
  errors: number;
  warnings: number;
  log: string;
  bot: Mt5Bot;
}

export const mt5BotService = {
  list: (): Promise<Mt5Bot[]> => isSimulation ? simListBots() : apiRequest<Mt5Bot[]>('/api/mt5/bots'),
  downloadEx5: async (id: number): Promise<Blob> => {
    if (isSimulation) throw new Error('EX5 downloads require the real MT5 bridge.');
    const token = sessionStorage.getItem('koolkid_mt5_hub_token');
    const res = await fetch(apiUrl(`/api/mt5/bots/${id}/download`), {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({})) as { detail?: string; error?: string };
      throw new Error(data.detail || data.error || `Download failed (${res.status})`);
    }
    return res.blob();
  },
  create: (payload: Record<string, unknown>): Promise<Mt5Bot> => isSimulation ? simCreateBot(payload) : apiRequest<Mt5Bot>('/api/mt5/bots', 'POST', payload),
  remove: (id: number): Promise<{ ok: boolean }> => isSimulation ? simDeleteBot(id) : apiRequest<{ ok: boolean }>(`/api/mt5/bots/${id}`, 'DELETE'),
  control: (id: number, action: string, payload: Record<string, unknown> = {}): Promise<Mt5Bot> =>
    isSimulation ? simBotControl(id, action, payload) : bridgeControl(id, action, payload),
  performance: (id: number): Promise<BotPerformance> => isSimulation ? simBotPerformance(id) : apiRequest<BotPerformance>(`/api/mt5/bots/${id}/performance`),
  compileSource: async (id: number, sourceFile: File): Promise<BotCompileResult> => {
    if (isSimulation) throw new Error('MQ5 compilation requires the real MT5 bridge.');
    if (!sourceFile.name.toLowerCase().endsWith('.mq5')) throw new Error('Choose an .mq5 source file.');
    const form = new FormData();
    form.append('source_file', sourceFile, sourceFile.name);
    return apiFormRequest<BotCompileResult>(`/api/mt5/bots/${id}/compile`, form);
  },
  uploadFiles: async (id: number, eaFile?: File | null, presetFile?: File | null): Promise<BotFileUploadResult> => {
    if (isSimulation) throw new Error('Actual EA files can only be uploaded while the local MT5 bridge is running.');
    const form = new FormData();
    if (eaFile) form.append('ea_file', eaFile, eaFile.name);
    if (presetFile) form.append('preset_file', presetFile, presetFile.name);
    if (!eaFile && !presetFile) throw new Error('Choose an .ex5 EA file or .set preset first.');
    return apiFormRequest<BotFileUploadResult>(`/api/mt5/bots/${id}/files`, form);
  },
};
