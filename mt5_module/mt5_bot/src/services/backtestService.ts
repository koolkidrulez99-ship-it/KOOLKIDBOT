import { apiFormRequest, apiRequest } from './http';
import { apiUrl } from '../config/runtime';

export interface BacktestJob {
  id: string;
  username: string;
  account_login: number;
  bot_filename: string;
  preset_filename?: string | null;
  symbol: string;
  timeframe: string;
  date_from: string;
  date_to: string;
  deposit: number;
  leverage: number;
  model: number;
  research_opt_in: boolean;
  status: 'queued' | 'preparing' | 'compiling' | 'testing' | 'analyzing' | 'complete' | 'failed';
  stage: string;
  progress: number;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  result?: Record<string, number | string | null>;
  report_filename?: string | null;
  tester_log?: string | null;
  return_code?: number | null;
  error?: string | null;
}

export interface BacktestState {
  jobs: BacktestJob[];
  daily_limit: number;
  available: boolean;
  next_available_at?: string | null;
  active_job?: BacktestJob | null;
}

export interface BacktestCreateInput {
  botFile: File;
  presetFile?: File | null;
  accountLogin: number;
  symbol: string;
  timeframe: string;
  dateFrom: string;
  dateTo: string;
  deposit: number;
  leverage: number;
  model: number;
  researchOptIn: boolean;
}

async function downloadBacktestFile(jobId: string, kind: 'report' | 'data') {
  const token = sessionStorage.getItem('koolkid_mt5_hub_token');
  const response = await fetch(apiUrl(`/api/mt5/backtests/${encodeURIComponent(jobId)}/${kind}`), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `Backtest ${kind} could not be downloaded.`);
  }
  const disposition = response.headers.get('content-disposition') || '';
  const match = disposition.match(/filename="?([^";]+)"?/i);
  const filename = match?.[1] || `backtest_${jobId}.${kind === 'report' ? 'html' : 'json'}`;
  const blob = await response.blob();
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = href;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(href);
}


export const backtestService = {
  list: () => apiRequest<BacktestState>('/api/mt5/backtests'),
  dismiss: (jobId: string) => apiRequest<BacktestJob>(`/api/mt5/backtests/${encodeURIComponent(jobId)}`, 'DELETE'),
  downloadReport: (jobId: string) => downloadBacktestFile(jobId, 'report'),
  downloadData: (jobId: string) => downloadBacktestFile(jobId, 'data'),
  create: (input: BacktestCreateInput) => {
    const form = new FormData();
    form.append('bot_file', input.botFile, input.botFile.name);
    if (input.presetFile) form.append('preset_file', input.presetFile, input.presetFile.name);
    form.append('account_login', String(input.accountLogin));
    form.append('symbol', input.symbol);
    form.append('timeframe', input.timeframe);
    form.append('date_from', input.dateFrom);
    form.append('date_to', input.dateTo);
    form.append('deposit', String(input.deposit));
    form.append('leverage', String(input.leverage));
    form.append('model', String(input.model));
    form.append('research_opt_in', String(input.researchOptIn));
    return apiFormRequest<BacktestJob>('/api/mt5/backtests', form);
  },
};
