import { apiRequest } from './http';

export interface JournalTrade {
  id?: number;
  ticket?: number;
  account_login: number;
  symbol: string;
  type: string;
  volume: number;
  open_price?: number;
  close_price?: number;
  net_pl: number;
  profit?: number;
  swap?: number;
  commission?: number;
  open_time?: string;
  close_time: string;
  source?: string;
}

export interface JournalDay {
  date: string;
  day: number;
  pnl: number;
  trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  motivation?: string | null;
  trade_rows: JournalTrade[];
}

export interface JournalMonthSummary {
  net_pnl: number;
  trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  winning_days: number;
  losing_days: number;
  best_day?: JournalDay | null;
  worst_day?: JournalDay | null;
  average_day_pnl: number;
}

export interface JournalMonth {
  account: { login: number; nickname?: string; broker?: string; server?: string; currency: string };
  view: 'month';
  year: number;
  month: number;
  days: JournalDay[];
  summary: JournalMonthSummary;
  today: string;
  today_motivation: string;
  archive_updated_at?: string | null;
  live_refresh: boolean;
  refresh_error?: string | null;
}

export interface JournalYearMonth {
  month: number;
  pnl: number;
  trades: number;
  wins: number;
  losses: number;
  win_rate: number;
}

export interface JournalYear {
  account: { login: number; nickname?: string; broker?: string; server?: string; currency: string };
  view: 'year';
  year: number;
  months: JournalYearMonth[];
  summary: {
    net_pnl: number;
    trades: number;
    wins: number;
    losses: number;
    win_rate: number;
    profitable_months: number;
    losing_months: number;
  };
  archive_updated_at?: string | null;
  live_refresh: boolean;
  refresh_error?: string | null;
}

export const journalService = {
  month: (accountLogin: number, year: number, month: number) =>
    apiRequest<JournalMonth>(`/api/mt5/journal/${accountLogin}?view=month&year=${year}&month=${month}`),
  year: (accountLogin: number, year: number) =>
    apiRequest<JournalYear>(`/api/mt5/journal/${accountLogin}?view=year&year=${year}`),
};
