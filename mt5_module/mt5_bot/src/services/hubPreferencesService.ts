import { isSimulation } from '../config/runtime';
import type { HubPreferences } from '../context/HubContext';
import { apiRequest } from './http';

export const hubPreferencesService = {
  get: (): Promise<Partial<HubPreferences>> =>
    isSimulation ? Promise.resolve({}) : apiRequest<Partial<HubPreferences>>('/api/mt5/preferences'),
  save: (prefs: HubPreferences): Promise<Partial<HubPreferences>> =>
    isSimulation ? Promise.resolve(prefs) : apiRequest<Partial<HubPreferences>>('/api/mt5/preferences', 'PUT', prefs),
};
