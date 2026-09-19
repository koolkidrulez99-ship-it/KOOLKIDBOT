import { apiRequest } from './http';
import type { BacktestJob } from './backtestService';

export interface AdminOverview {
  total_users: number;
  online_users: number;
  active_backtests: number;
  completed_backtests: number;
  pending_research: number;
  approved_candidates: number;
}

export interface AdminUser {
  username: string;
  role: 'user' | 'admin';
  joined_at?: string | null;
  last_seen?: string | null;
  online: boolean;
  backtests: number;
}

export interface ResearchItem {
  id: string;
  job_id: string;
  username: string;
  bot_filename: string;
  source_type: string;
  symbol: string;
  timeframe: string;
  status: string;
  created_at: string;
  observations: string[];
  backtest: Record<string, number | string | null>;
  decision_note?: string | null;
}

export const adminService = {
  overview: () => apiRequest<AdminOverview>('/api/mt5/admin/overview'),
  users: () => apiRequest<AdminUser[]>('/api/mt5/admin/users'),
  backtests: () => apiRequest<BacktestJob[]>('/api/mt5/admin/backtests'),
  research: () => apiRequest<ResearchItem[]>('/api/mt5/admin/research'),
  decide: (id: string, decision: 'approve' | 'reject' | 'research', note = '') =>
    apiRequest<ResearchItem>(`/api/mt5/admin/research/${id}/decision`, 'POST', { decision, note }),
};
