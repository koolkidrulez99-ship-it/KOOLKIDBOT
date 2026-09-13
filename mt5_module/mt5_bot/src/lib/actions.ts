import { emergencyService } from '../services/emergencyService';
import { mt5AccountService } from '../services/mt5AccountService';
import { mt5BotService } from '../services/mt5BotService';
import { mt5PositionService } from '../services/mt5PositionService';
import { mt5TradingService } from '../services/mt5TradingService';
import type { OpenTradePayload } from '../services/mt5TradingService';

export type { OpenTradePayload };

export const botControl = (id: number, action: string, payload: Record<string, unknown> = {}) =>
  mt5BotService.control(id, action, payload);

export const stopAllBots = () => emergencyService.stopAllBots();
export const closeAllPositions = () => emergencyService.closeAllPositions();
export const stopAndCloseAll = () => emergencyService.stopAndCloseAll();
export const closePosition = (id: number) => mt5PositionService.close(id);
export const openTrade = (payload: OpenTradePayload) => mt5TradingService.open(payload);
export const addAccount = (payload: Record<string, unknown>) => mt5AccountService.connect(payload);
export const testAccount = (payload: Record<string, unknown>) => mt5AccountService.testConnection(payload);
export const removeAccount = (id: number) => mt5AccountService.remove(id);
export const accountAction = (id: number, action: string, extra: Record<string, unknown> = {}) =>
  mt5AccountService.action(id, action, extra);
export const createBot = (payload: Record<string, unknown>) => mt5BotService.create(payload);
export const deleteBot = (id: number) => mt5BotService.remove(id);
