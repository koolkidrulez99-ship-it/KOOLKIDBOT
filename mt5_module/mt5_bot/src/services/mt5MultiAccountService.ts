const isLocalHost = window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost';
const localMultiBase = 'http://127.0.0.1:5055/mt5-multi';
const publicMultiBase = String(import.meta.env.VITE_MT5_MULTI_ACCOUNT_API_BASE || 'http://127.0.0.1:8002').replace(/\/$/, '');
let resolvedMultiBase: string | null = isLocalHost ? localMultiBase : null;
let resolvingMultiBase: Promise<string> | null = null;

async function resolveMultiBase(): Promise<string> {
  if (resolvedMultiBase) return resolvedMultiBase;
  if (resolvingMultiBase) return resolvingMultiBase;
  resolvingMultiBase = (async () => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 1200);
    try {
      const response = await fetch(`${localMultiBase}/health`, {
        method: 'GET',
        cache: 'no-store',
        signal: controller.signal,
      });
      resolvedMultiBase = response.ok ? localMultiBase : publicMultiBase;
    } catch {
      resolvedMultiBase = publicMultiBase;
    } finally {
      window.clearTimeout(timer);
    }
    return resolvedMultiBase!;
  })();
  try {
    return await resolvingMultiBase;
  } finally {
    resolvingMultiBase = null;
  }
}

function authHeaders(): Record<string, string> {
  const token = sessionStorage.getItem('koolkid_mt5_hub_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

const inflightGets = new Map<string, Promise<unknown>>();

async function multiRequest<T>(path: string, method = 'GET', body?: unknown, timeoutMs = 20000): Promise<T> {
  const normalizedMethod = method.toUpperCase();
  const base = await resolveMultiBase();
  const url = `${base}${path.startsWith('/') ? path : `/${path}`}`;
  const dedupeKey = normalizedMethod === 'GET' && body === undefined ? url : '';
  const existing = dedupeKey ? inflightGets.get(dedupeKey) : undefined;
  if (existing) return existing as Promise<T>;

  const task = (async (): Promise<T> => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const request: RequestInit & { priority?: 'high' | 'low' | 'auto' } = {
        method: normalizedMethod,
        headers: { ...authHeaders(), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
        cache: 'no-store',
        priority: normalizedMethod === 'GET' ? 'low' : 'high',
      };
      const res = await fetch(url, request);
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
  })();

  if (dedupeKey) inflightGets.set(dedupeKey, task);
  try {
    return await task;
  } finally {
    if (dedupeKey && inflightGets.get(dedupeKey) === task) inflightGets.delete(dedupeKey);
  }
}

export interface MultiAccountInfo {
  login?: number;
  server?: string;
  balance?: number;
  equity?: number;
  currency?: string;
  trade_mode?: number;
  access_mode?: string;
  read_only?: boolean;
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
  group_id?: '1' | '2';
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
  elapsed_ms?: number;
  fill_spread_ms?: number;
}

export const mt5MultiAccountService = {
  health: () => multiRequest<{ ok: boolean; connected: number; max_accounts: number; copy_status: string }>('/health'),
  bootstrapSimulation: () => multiRequest<{ ok: boolean; accounts: string[]; master: string; slaves: string[] }>('/demo/bootstrap', 'POST', {}),
  accounts: () => multiRequest<{
    accounts: MultiAccount[];
    master?: string | null;
    slaves: string[];
    groups?: Record<'1' | '2', { group_id: '1' | '2'; master?: string | null; slaves: string[]; enabled: boolean }>;
  }>('/accounts'),
  connect: (payload: Record<string, unknown>) => multiRequest<MultiAccount>('/accounts/connect', 'POST', payload),
  disconnect: (accountId: string) => multiRequest<{ ok: boolean }>(`/accounts/${encodeURIComponent(accountId)}/disconnect`, 'POST', {}),
  copyStatus: () => multiRequest<Record<string, unknown>>('/copy/status'),
  saveCopyPreferences: (groupId: '1' | '2', payload: Record<string, unknown>) => multiRequest<{ ok: boolean; preferences: Record<string, unknown>; status: string }>(`/copy/preferences?group_id=${groupId}`, 'PUT', payload),
  startCopy: (payload: Record<string, unknown>) => multiRequest<Record<string, unknown>>('/copy/start', 'POST', payload),
  stopCopy: (groupId: '1' | '2' = '1') => multiRequest<Record<string, unknown>>(`/copy/stop?group_id=${groupId}`, 'POST', {}),
  pendingCopies: () => multiRequest<{ pending: PendingCopy[] }>('/copy/pending'),
  decideCopy: (masterTicket: number, copy: boolean, slaveAccountIds: string[], groupId: '1' | '2' = '1') => multiRequest<CopyDecisionResult>('/copy/decision', 'POST', {
    group_id: groupId,
    master_ticket: masterTicket,
    should_copy: copy,
    slave_account_ids: slaveAccountIds,
  }),
  manualTrade: (payload: Record<string, unknown>) => multiRequest<{ results: Record<string, { ok: boolean; result?: unknown; error?: string; timing?: Record<string, number> }> }>('/manual-trade', 'POST', payload, 18000),
  positions: () => multiRequest<{ positions: MultiPosition[]; errors: Record<string, string> }>('/positions'),
  candles: (accountId: string, symbol: string, timeframe = 'M5', count = 220) => multiRequest<Array<{ time: number; open: number; high: number; low: number; close: number; volume?: number }>>(
    `/accounts/${encodeURIComponent(accountId)}/candles/${encodeURIComponent(symbol)}?timeframe=${encodeURIComponent(timeframe)}&count=${count}`,
  ),
  closePosition: (accountId: string, ticket: number) => multiRequest<Record<string, unknown>>('/positions/close', 'POST', { account_id: accountId, ticket }),
  closeMany: (targets: Array<{ account_id: string; ticket: number }>, uiClickedAt = Date.now() / 1000) => multiRequest<Record<string, unknown>>('/positions/close-many', 'POST', { targets, ui_clicked_at: uiClickedAt }),
};
