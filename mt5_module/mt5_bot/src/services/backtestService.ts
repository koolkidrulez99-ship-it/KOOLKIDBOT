import { apiFormRequest, apiRequest } from './http';

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

export const backtestService = {
  list: () => apiRequest<BacktestState>('/api/mt5/backtests'),
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
