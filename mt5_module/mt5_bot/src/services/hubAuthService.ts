import { apiUrl } from '../config/runtime';

const TOKEN_KEY = 'koolkid_mt5_hub_token';

export interface HubIdentity {
  user_id: string;
  username: string;
  workspace_id: string;
}

export function hubToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

async function request(path: string, body?: Record<string, string>): Promise<HubIdentity & { token?: string }> {
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
  return data;
}

export const hubAuthService = {
  me: () => request('/api/mt5/hub/auth/me'),
  login: async (username: string, password: string) => {
    const result = await request('/api/mt5/hub/auth/login', { username, password });
    if (result.token) sessionStorage.setItem(TOKEN_KEY, result.token);
    return result;
  },
  signup: async (username: string, password: string) => {
    const result = await request('/api/mt5/hub/auth/signup', { username, password });
    if (result.token) sessionStorage.setItem(TOKEN_KEY, result.token);
    return result;
  },
  logout: () => sessionStorage.removeItem(TOKEN_KEY),
};
