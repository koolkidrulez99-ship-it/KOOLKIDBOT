import { apiBase, isSimulation } from '../config/runtime';

const localBridgeBase = 'http://127.0.0.1:8000';
let resolvedBridgeBase: string | null =
  window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost'
    ? localBridgeBase
    : (isSimulation ? apiBase : null);
let resolvingBridgeBase: Promise<string> | null = null;
const inflightGets = new Map<string, Promise<unknown>>();

function authHeaders(): Record<string, string> {
  const token = sessionStorage.getItem('koolkid_mt5_hub_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function resolveBridgeBase(): Promise<string> {
  if (resolvedBridgeBase !== null) return resolvedBridgeBase;
  if (resolvingBridgeBase) return resolvingBridgeBase;
  resolvingBridgeBase = (async () => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 450);
    try {
      const response = await fetch(`${localBridgeBase}/health`, {
        method: 'GET',
        cache: 'no-store',
        signal: controller.signal,
      });
      resolvedBridgeBase = response.ok ? localBridgeBase : apiBase;
    } catch {
      resolvedBridgeBase = apiBase;
    } finally {
      window.clearTimeout(timer);
    }
    return resolvedBridgeBase;
  })();
  try {
    return await resolvingBridgeBase;
  } finally {
    resolvingBridgeBase = null;
  }
}

function joinUrl(base: string, path: string): string {
  const normalized = path.startsWith('/') ? path : `/${path}`;
  return `${String(base || '').replace(/\/$/, '')}${normalized}`;
}

async function parseResponse<T>(res: Response): Promise<T> {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = data as { error?: string; detail?: string };
    throw new Error(err.error || err.detail || `Request failed (${res.status})`);
  }
  return data as T;
}

export async function apiRequest<T>(path: string, method = 'GET', body?: unknown, timeoutMs?: number): Promise<T> {
  const normalizedMethod = method.toUpperCase();
  const base = await resolveBridgeBase();
  const url = joinUrl(base, path);
  const token = sessionStorage.getItem('koolkid_mt5_hub_token') || '';
  const dedupeKey = normalizedMethod === 'GET' && body === undefined ? `${token}|${url}` : '';
  const existing = dedupeKey ? inflightGets.get(dedupeKey) : undefined;
  if (existing) return existing as Promise<T>;

  const task = (async (): Promise<T> => {
    const controller = timeoutMs ? new AbortController() : undefined;
    const timer = controller ? window.setTimeout(() => controller.abort(), timeoutMs) : undefined;
    try {
      const request: RequestInit & { priority?: 'high' | 'low' | 'auto' } = {
        method: normalizedMethod,
        headers: { ...authHeaders(), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller?.signal,
        cache: 'no-store',
        priority: normalizedMethod === 'GET' ? 'low' : 'high',
      };
      const res = await fetch(url, request);
      return await parseResponse<T>(res);
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new Error('The MT5 request timed out. Check the worker or terminal status and try again.');
      }
      throw error;
    } finally {
      if (timer !== undefined) window.clearTimeout(timer);
    }
  })();

  if (dedupeKey) inflightGets.set(dedupeKey, task);
  try {
    return await task;
  } finally {
    if (dedupeKey && inflightGets.get(dedupeKey) === task) inflightGets.delete(dedupeKey);
  }
}

export async function apiFormRequest<T>(path: string, form: FormData, method = 'POST'): Promise<T> {
  const base = await resolveBridgeBase();
  const res = await fetch(joinUrl(base, path), {
    method,
    headers: authHeaders(),
    body: form,
    cache: 'no-store',
    priority: 'high',
  } as RequestInit & { priority?: 'high' | 'low' | 'auto' });
  return parseResponse<T>(res);
}
