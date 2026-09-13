import { isSimulation } from '../config/runtime';
import type { Mt5Account } from '../types';
import { apiRequest } from './http';
import { simAccountAction, simAddAccount, simListAccounts, simRemoveAccount, simTestAccount } from './simulationStore';

export interface ConnectionTestResult {
  ok: boolean;
  mode?: 'simulation' | 'bridge';
  message: string;
}

export const mt5AccountService = {
  list: (): Promise<Mt5Account[]> => isSimulation ? simListAccounts() : apiRequest<Mt5Account[]>('/api/mt5/accounts'),
  testConnection: (payload: Record<string, unknown>): Promise<ConnectionTestResult> => isSimulation ? simTestAccount(payload) : apiRequest<ConnectionTestResult>('/api/mt5/accounts/test', 'POST', payload, 45000),
  connect: (payload: Record<string, unknown>): Promise<Mt5Account> => isSimulation ? simAddAccount(payload) : apiRequest<Mt5Account>('/api/mt5/accounts/connect', 'POST', payload, 45000),
  cancelConnect: (login: number): Promise<{ ok: boolean }> => isSimulation ? Promise.resolve({ ok: true }) : apiRequest<{ ok: boolean }>('/api/mt5/accounts/connect/cancel', 'POST', { login }, 7000),
  remove: (id: number): Promise<{ ok: boolean }> => isSimulation ? simRemoveAccount(id) : apiRequest<{ ok: boolean }>(`/api/mt5/accounts/${id}`, 'DELETE'),
  action: (id: number, action: string, extra: Record<string, unknown> = {}): Promise<Mt5Account> =>
    isSimulation ? simAccountAction(id, action, extra) : apiRequest<Mt5Account>(`/api/mt5/accounts/${id}`, 'PUT', { action, ...extra }, 45000),
};
