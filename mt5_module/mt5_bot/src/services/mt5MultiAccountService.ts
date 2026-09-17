const multiBase = String(import.meta.env.VITE_MT5_MULTI_ACCOUNT_API_BASE || 'http://127.0.0.1:8002').replace(/\/$/, '');

function authHeaders(): Record<string, string> {
  const token = sessionStorage.getItem('koolkid_mt5_hub_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function multiRequest<T>(path: string, method = 'GET', body?: unknown, timeoutMs = 20000): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${multiBase}${path.startsWith('/') ? path : `/${path}`}`, {
      method,
      headers: { ...authHeaders(), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = data as { detail?: string; error?: string };
      throw new Error(err.detail || err.error || `Multi-account request failed (${res.status})`);
    }
    return data as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('MT5 order routing timed out. Check the selected account worker and try again.');
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

export interface MultiAccountInfo {
  login?: number;
  server?: string;
  balance?: number;
  equity?: number;
  currency?: string;
}

export interface MultiAccount {
  account_id: string;
  nickname: string;
  login: number;
  server: string;
  terminal_path?: string;
  mode: 'real' | 'simulation';
  connected: boolean;
  is_master?: boolean;
  is_slave?: boolean;
  account_info?: MultiAccountInfo;
  error?: string;
}

export interface MultiPosition {
  account_id: string;
  account_login?: number;
  account_nickname?: string;
  ticket: number;
  symbol: string;
  type?: number | string;
  side?: 'BUY' | 'SELL' | 'buy' | 'sell';
  volume: number;
  price_open?: number;
  open_price?: number;
  price_current?: number;
  current_price?: number;
  sl?: number;
  tp?: number;
  profit?: number;
  swap?: number;
  commission?: number;
  time?: number;
  open_time?: string;
  source?: string;
  magic?: number;
}

export interface PendingCopy {
  master_ticket: number;
  master_account_id: string;
  slave_account_ids: string[];
  created_at: number;
  position: MultiPosition;
}

export interface CopyDecisionResult {
  ok: boolean;
  decision: 'master_only' | 'copied';
  results: Record<string, { ok: boolean; ticket?: number; error?: string; elapsed_ms?: number }>;
  fill_spread_ms?: number;
}

export const mt5MultiAccountService = {
  health: () => multiRequest<{ ok: boolean; connected: number; max_accounts: number; copy_status: string }>('/health'),
  bootstrapSimulation: () => multiRequest<{ ok: boolean; accounts: string[]; master: string; slaves: string[] }>('/demo/bootstrap', 'POST', {}),
  accounts: () => multiRequest<{ accounts: MultiAccount[]; master?: string | null; slaves: string[] }>('/accounts'),
  connect: (payload: Record<string, unknown>) => multiRequest<MultiAccount>('/accounts/connect', 'POST', payload),
  disconnect: (accountId: string) => multiRequest<{ ok: boolean }>(`/accounts/${encodeURIComponent(accountId)}/disconnect`, 'POST', {}),
  copyStatus: () => multiRequest<Record<string, unknown>>('/copy/status'),
  startCopy: (payload: Record<string, unknown>) => multiRequest<Record<string, unknown>>('/copy/start', 'POST', payload),
  stopCopy: () => multiRequest<Record<string, unknown>>('/copy/stop', 'POST', {}),
  pendingCopies: () => multiRequest<{ pending: PendingCopy[] }>('/copy/pending'),
  decideCopy: (masterTicket: number, copy: boolean, slaveAccountIds: string[]) => multiRequest<CopyDecisionResult>('/copy/decision', 'POST', {
    master_ticket: masterTicket,
    should_copy: copy,
    slave_account_ids: slaveAccountIds,
  }),
  manualTrade: (payload: Record<string, unknown>) => multiRequest<{ results: Record<string, { ok: boolean; result?: unknown; error?: string; timing?: Record<string, number> }> }>('/manual-trade', 'POST', payload, 18000),
  positions: () => multiRequest<{ positions: MultiPosition[]; errors: Record<string, string> }>('/positions'),
  closePosition: (accountId: string, ticket: number) => multiRequest<Record<string, unknown>>('/positions/close', 'POST', { account_id: accountId, ticket }),
  closeMany: (targets: Array<{ account_id: string; ticket: number }>, uiClickedAt = Date.now() / 1000) => multiRequest<Record<string, unknown>>('/positions/close-many', 'POST', { targets, ui_clicked_at: uiClickedAt }),
};
