import type { Mt5Bot } from '../types';

export const PREINSTALLED_BOT_NAMES = new Set([
  'WASP',
  'PRIMORDIAL PURPLE',
  'PRIMORDIAL BLACK',
  'PRIMORDIAL RED',
  'PRIMORDIAL WHITE',
  'PRIMORDIAL SILVER',
  'PRIMORDIAL GOLD',
  'PRIMORDIAL EMERALD',
  'PRIMORDIAL BLUE',
  'JOHN WICK',
  'JAMAICA',
  'PUSH',
  'NICK',
  'RED RIOT',
  'SCARLET RAIN',
  'CRIMSON RIOT',
  'MAROON',
  'TLG',
  'BOOM',
  'CRASH',
]);

export const LEGACY_PLACEHOLDERS = new Set([
  'Scalper Pro',
  'Trend Hunter',
  'Mean Reverter',
  'Gold Breakout',
  'Grid Master',
  'BTC Momentum',
]);

export const BOT_CATALOG: Mt5Bot[] = [];
