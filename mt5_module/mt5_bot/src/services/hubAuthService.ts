import { apiUrl } from '../config/runtime';

const TOKEN_KEY = 'koolkid_mt5_hub_token';

export interface HubTrialInfo {
  version: number;
  start_at: string;
  end_at: string;
  duration_days: number;
  server_now: string;
  active: boolean;
  expired: boolean;
  remaining_seconds: number;
}

export interface HubIdentity {
  user_id: string;
  username: string;
  workspace_id: string;
  role: 'user' | 'admin';
}

export interface HubAuthResponse extends HubIdentity {
  token?: string;
  trial?: HubTrialInfo;
}

export function hubToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

async function request<T>(path: string, body?: Record<string, string>): Promise<T> {
  const res = await fetch(apiUrl(path), {
    method: body ? 'POST' : 'GET',
    headers: {
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(hubToken() ? { Authorization: `Bearer ${hubToken()}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'MT5 Hub sign-in failed.');
  return data as T;
}

export const hubAuthService = {
  trial: () => request<HubTrialInfo>('/api/mt5/hub/auth/trial'),
  me: () => request<HubAuthResponse>('/api/mt5/hub/auth/me'),
  presence: () => request<{ ok: boolean; seen_at: string }>('/api/mt5/hub/presence', {}),
  login: async (username: string, password: string) => {
    const result = await request<HubAuthResponse>('/api/mt5/hub/auth/login', { username, password });
    if (result.token) sessionStorage.setItem(TOKEN_KEY, result.token);
    return result;
  },
  signup: async (username: string, password: string) => {
    const result = await request<HubAuthResponse>('/api/mt5/hub/auth/signup', { username, password });
    if (result.token) sessionStorage.setItem(TOKEN_KEY, result.token);
    return result;
  },
  logout: () => sessionStorage.removeItem(TOKEN_KEY),
};
