import type { Mt5Position } from '../types';

export function normalizePositionSide(value: unknown): 'buy' | 'sell' {
  if (typeof value === 'number') return value === 1 ? 'sell' : 'buy';
  const side = String(value ?? '').trim().toUpperCase();
  if (side === 'SELL' || side === '1' || side === 'POSITION_TYPE_SELL') return 'sell';
  return 'buy';
}

function numberOr(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function nullableNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed !== 0 ? parsed : null;
}

function positionTime(raw: Record<string, unknown>): string {
  if (typeof raw.open_time === 'string' && raw.open_time) return raw.open_time;
  const epoch = numberOr(raw.time, 0);
  return epoch > 0 ? new Date(epoch * 1000).toISOString() : new Date(0).toISOString();
}

export function normalizeMt5Position(value: unknown, index = 0): Mt5Position {
  const raw = value && typeof value === 'object' ? value as Record<string, unknown> : {};
  const ticket = numberOr(raw.ticket, index + 1);
  return {
    id: numberOr(raw.id, ticket || index + 1),
    ticket,
    account_login: numberOr(raw.account_login, 0),
    symbol: String(raw.symbol ?? ''),
    type: normalizePositionSide(raw.side ?? raw.type),
    volume: numberOr(raw.volume, 0),
    open_price: numberOr(raw.open_price ?? raw.price_open, 0),
    current_price: numberOr(raw.current_price ?? raw.price_current ?? raw.open_price ?? raw.price_open, 0),
    sl: nullableNumber(raw.sl),
    tp: nullableNumber(raw.tp),
    profit: numberOr(raw.profit, 0),
    swap: numberOr(raw.swap, 0),
    commission: numberOr(raw.commission, 0),
    open_time: positionTime(raw),
    source: String(raw.source ?? 'MT5'),
    magic: raw.magic === null || raw.magic === undefined ? null : numberOr(raw.magic, 0),
  };
}
