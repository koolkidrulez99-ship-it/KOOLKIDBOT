import { apiUrl } from '../config/runtime';

async function parseResponse<T>(res: Response): Promise<T> {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = data as { error?: string; detail?: string };
    throw new Error(err.error || err.detail || `Request failed (${res.status})`);
  }
  return data as T;
}

export async function apiRequest<T>(path: string, method = 'GET', body?: unknown, timeoutMs?: number): Promise<T> {
  const controller = timeoutMs ? new AbortController() : undefined;
  const timer = controller ? window.setTimeout(() => controller.abort(), timeoutMs) : undefined;
  try {
    const res = await fetch(apiUrl(path), {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller?.signal,
    });
    return await parseResponse<T>(res);
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('The MT5 request timed out. Check the worker or terminal status and try again.');
    }
    throw error;
  } finally {
    if (timer !== undefined) window.clearTimeout(timer);
  }
}

export async function apiFormRequest<T>(path: string, form: FormData, method = 'POST'): Promise<T> {
  const res = await fetch(apiUrl(path), { method, body: form });
  return parseResponse<T>(res);
}
