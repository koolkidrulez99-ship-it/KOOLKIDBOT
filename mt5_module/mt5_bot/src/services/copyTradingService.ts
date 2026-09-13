import { isSimulation } from '../config/runtime';
import type { CopyRelationship, CopyState } from '../types';
import { apiRequest } from './http';
import { simCopyState, simCreateCopyRelationship, simDeleteCopyRelationship, simUpdateCopyRelationship } from './simulationStore';

export type NewCopyRelationship = Omit<CopyRelationship, 'id' | 'created_at' | 'status'>;

export const copyTradingService = {
  state: (): Promise<CopyState> => isSimulation ? simCopyState() : apiRequest<CopyState>('/api/mt5/copy'),
  create: (payload: NewCopyRelationship): Promise<CopyRelationship> => isSimulation ? simCreateCopyRelationship(payload) : apiRequest<CopyRelationship>('/api/mt5/copy', 'POST', payload),
  update: (id: string, patch: Partial<CopyRelationship>): Promise<CopyRelationship> => isSimulation ? simUpdateCopyRelationship(id, patch) : apiRequest<CopyRelationship>(`/api/mt5/copy/${encodeURIComponent(id)}`, 'PUT', patch),
  remove: (id: string): Promise<{ ok: boolean }> => isSimulation ? simDeleteCopyRelationship(id) : apiRequest<{ ok: boolean }>(`/api/mt5/copy/${encodeURIComponent(id)}`, 'DELETE'),
};
