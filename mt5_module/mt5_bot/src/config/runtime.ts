import type { RuntimeMode } from '../types';

const requested = String(import.meta.env.VITE_MT5_MODE || 'simulation').toLowerCase();

export const runtimeMode: RuntimeMode = requested === 'bridge' ? 'bridge' : 'simulation';
export const isSimulation = runtimeMode === 'simulation';
const isLocalHost = window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost';
export const apiBase = String(isLocalHost && runtimeMode === 'bridge' ? 'http://127.0.0.1:8000' : (import.meta.env.VITE_MT5_API_BASE || (runtimeMode === 'bridge' ? 'http://127.0.0.1:8000' : ''))).replace(/\/$/, '');
export const appVersion = '4.2.0';
export const routerBase = String(import.meta.env.VITE_ROUTER_BASE || '').replace(/\/$/, '');
export const hostHomeUrl = String(import.meta.env.VITE_HOST_HOME_URL || '');

export function apiUrl(path: string): string {
  if (!path.startsWith('/')) path = `/${path}`;
  return `${apiBase}${path}`;
}
