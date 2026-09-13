export interface SymbolMeta {
  symbol: string;
  name: string;
  base: number;
  digits: number;
  contract: number;
  mult: number;
  pip: number;
}

const forexBases: Record<string, number> = {
  EURUSD: 1.08652, GBPUSD: 1.27104, USDJPY: 147.815, USDCHF: 0.8042, AUDUSD: 0.6584, USDCAD: 1.3725, NZDUSD: 0.6031,
  EURGBP: 0.85548, EURJPY: 160.61, EURCHF: 0.8739, EURAUD: 1.6501, EURCAD: 1.4912, EURNZD: 1.8010,
  GBPJPY: 187.86, GBPCHF: 1.0224, GBPAUD: 1.9305, GBPCAD: 1.7450, GBPNZD: 2.1054,
  AUDJPY: 97.32, AUDCHF: 0.5297, AUDCAD: 0.9039, AUDNZD: 1.0916, CADJPY: 107.72, CADCHF: 0.5858, CHFJPY: 183.72,
  NZDJPY: 89.17, NZDCHF: 0.4852, NZDCAD: 0.8278, USDZAR: 17.62, USDTRY: 41.15, USDMXN: 18.73, USDSGD: 1.2780,
  USDHKD: 7.789, USDNOK: 10.05, USDSEK: 9.47, USDCNH: 7.116, EURTRY: 44.70, EURZAR: 19.15, GBPZAR: 22.40, SGDJPY: 115.66,
};

function forexMeta(symbol: string, base: number): SymbolMeta {
  const jpy = symbol.endsWith('JPY');
  return { symbol, name: `${symbol.slice(0, 3)} vs ${symbol.slice(3, 6)}`, base, digits: jpy ? 3 : 5, contract: 100000, mult: jpy ? 680 : 100000, pip: jpy ? 0.01 : 0.0001 };
}

export const MARKET: Record<string, SymbolMeta> = {
  ...Object.fromEntries(Object.entries(forexBases).map(([symbol, base]) => [symbol, forexMeta(symbol, base)])),
  XAUUSD: { symbol: 'XAUUSD', name: 'Gold vs US Dollar', base: 3419.85, digits: 2, contract: 100, mult: 100, pip: 0.1 },
  XAGUSD: { symbol: 'XAGUSD', name: 'Silver vs US Dollar', base: 39.5, digits: 3, contract: 5000, mult: 50, pip: 0.01 },
  BTCUSD: { symbol: 'BTCUSD', name: 'Bitcoin vs US Dollar', base: 112520.4, digits: 1, contract: 1, mult: 1, pip: 25 },
  ETHUSD: { symbol: 'ETHUSD', name: 'Ethereum vs US Dollar', base: 4360.2, digits: 2, contract: 1, mult: 1, pip: 1 },
  US30: { symbol: 'US30', name: 'Wall Street 30', base: 45892.5, digits: 1, contract: 1, mult: 1, pip: 1 },
  NAS100: { symbol: 'NAS100', name: 'US Tech 100', base: 23890.0, digits: 1, contract: 1, mult: 1, pip: 1 },
  'Volatility 10 Index': { symbol: 'Volatility 10 Index', name: 'Volatility 10 Index', base: 7345.2, digits: 3, contract: 1, mult: 0.1, pip: 0.001 },
  'Volatility 25 Index': { symbol: 'Volatility 25 Index', name: 'Volatility 25 Index', base: 18422.4, digits: 3, contract: 1, mult: 0.1, pip: 0.001 },
  'Volatility 50 Index': { symbol: 'Volatility 50 Index', name: 'Volatility 50 Index', base: 228115.0, digits: 2, contract: 1, mult: 0.01, pip: 0.01 },
  'Volatility 75 Index': { symbol: 'Volatility 75 Index', name: 'Volatility 75 Index', base: 451832.0, digits: 2, contract: 1, mult: 0.01, pip: 0.01 },
  'Volatility 100 Index': { symbol: 'Volatility 100 Index', name: 'Volatility 100 Index', base: 12984.5, digits: 2, contract: 1, mult: 0.1, pip: 0.01 },
  'Volatility 10 (1s) Index': { symbol: 'Volatility 10 (1s) Index', name: 'Volatility 10 (1s) Index', base: 3124.2, digits: 2, contract: 1, mult: 0.1, pip: 0.01 },
  'Volatility 15 (1s) Index': { symbol: 'Volatility 15 (1s) Index', name: 'Volatility 15 (1s) Index', base: 5421.0, digits: 2, contract: 1, mult: 0.1, pip: 0.01 },
  'Volatility 25 (1s) Index': { symbol: 'Volatility 25 (1s) Index', name: 'Volatility 25 (1s) Index', base: 8734.8, digits: 2, contract: 1, mult: 0.1, pip: 0.01 },
  'Volatility 30 (1s) Index': { symbol: 'Volatility 30 (1s) Index', name: 'Volatility 30 (1s) Index', base: 6322.3, digits: 2, contract: 1, mult: 0.1, pip: 0.01 },
  'Volatility 50 (1s) Index': { symbol: 'Volatility 50 (1s) Index', name: 'Volatility 50 (1s) Index', base: 12045.6, digits: 2, contract: 1, mult: 0.1, pip: 0.01 },
  'Volatility 75 (1s) Index': { symbol: 'Volatility 75 (1s) Index', name: 'Volatility 75 (1s) Index', base: 18755.2, digits: 2, contract: 1, mult: 0.1, pip: 0.01 },
  'Volatility 90 (1s) Index': { symbol: 'Volatility 90 (1s) Index', name: 'Volatility 90 (1s) Index', base: 22643.8, digits: 2, contract: 1, mult: 0.1, pip: 0.01 },
  'Volatility 100 (1s) Index': { symbol: 'Volatility 100 (1s) Index', name: 'Volatility 100 (1s) Index', base: 32184.4, digits: 2, contract: 1, mult: 0.1, pip: 0.01 },
  'Boom 300 Index': { symbol: 'Boom 300 Index', name: 'Boom 300 Index', base: 1240.0, digits: 3, contract: 1, mult: 1, pip: 0.001 },
  'Boom 500 Index': { symbol: 'Boom 500 Index', name: 'Boom 500 Index', base: 2750.0, digits: 3, contract: 1, mult: 1, pip: 0.001 },
  'Boom 1000 Index': { symbol: 'Boom 1000 Index', name: 'Boom 1000 Index', base: 3650.0, digits: 3, contract: 1, mult: 1, pip: 0.001 },
  'Crash 300 Index': { symbol: 'Crash 300 Index', name: 'Crash 300 Index', base: 1450.0, digits: 3, contract: 1, mult: 1, pip: 0.001 },
  'Crash 500 Index': { symbol: 'Crash 500 Index', name: 'Crash 500 Index', base: 2380.0, digits: 3, contract: 1, mult: 1, pip: 0.001 },
  'Crash 1000 Index': { symbol: 'Crash 1000 Index', name: 'Crash 1000 Index', base: 3410.0, digits: 3, contract: 1, mult: 1, pip: 0.001 },
  'Step Index': { symbol: 'Step Index', name: 'Step Index', base: 12455.0, digits: 2, contract: 1, mult: 0.1, pip: 0.01 },
  'Range Break 100 Index': { symbol: 'Range Break 100 Index', name: 'Range Break 100 Index', base: 1840.0, digits: 2, contract: 1, mult: 0.1, pip: 0.01 },
  'Range Break 200 Index': { symbol: 'Range Break 200 Index', name: 'Range Break 200 Index', base: 2710.0, digits: 2, contract: 1, mult: 0.1, pip: 0.01 },
};

export const SYMBOL_LIST = Object.keys(MARKET);

export const TIMEFRAMES = ['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1'] as const;
export type Timeframe = (typeof TIMEFRAMES)[number];

export const TF_SECONDS: Record<Timeframe, number> = {
  M1: 60,
  M5: 300,
  M15: 900,
  M30: 1800,
  H1: 3600,
  H4: 14400,
  D1: 86400,
};

export const TF_VOL: Record<Timeframe, number> = {
  M1: 0.0005,
  M5: 0.0011,
  M15: 0.0019,
  M30: 0.0026,
  H1: 0.0038,
  H4: 0.0078,
  D1: 0.016,
};

export function calcProfit(type: 'buy' | 'sell', symbol: string, open: number, cur: number, volume: number): number {
  const m = MARKET[symbol];
  if (!m) return 0;
  const dir = type === 'buy' ? 1 : -1;
  return (cur - open) * dir * m.mult * volume;
}

export function pipValue(symbol: string, volume: number): number {
  const m = MARKET[symbol];
  if (!m) return 0;
  return m.mult * m.pip * volume;
}

export function marginFor(symbol: string, price: number, volume: number, leverage: number): number {
  const m = MARKET[symbol];
  if (!m) return 0;
  return (price * m.contract * volume) / Math.max(1, leverage);
}

export function mulberry32(a: number) {
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function seedFrom(str: string): number {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export interface Candle {
  time: number; // unix seconds
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export function genCandles(symbol: string, tfSeconds: number, count: number): Candle[] {
  const meta = MARKET[symbol];
  const base = meta ? meta.base : 100;
  const volFactor = base * 0.0011 * Math.sqrt(tfSeconds / 300);
  const rnd = mulberry32(seedFrom(symbol + ':' + tfSeconds));

  const now = Math.floor(Date.now() / 1000 / tfSeconds) * tfSeconds;
  const candles: Candle[] = [];

  let close = base;
  // walk backwards from the live book price so the chart always ends "now"
  for (let i = 0; i < count; i++) {
    const t = now - i * tfSeconds;
    const open = close;
    const drift = (rnd() - 0.5) * 2 * volFactor;
    const nextClose = open - drift * (0.6 + rnd());
    const hi = Math.max(open, nextClose) + rnd() * volFactor * 0.6;
    const lo = Math.min(open, nextClose) - rnd() * volFactor * 0.6;
    candles.push({
      time: t,
      open: round(open, meta?.digits),
      high: round(hi, meta?.digits),
      low: round(lo, meta?.digits),
      close: round(nextClose, meta?.digits),
      volume: Math.round(120 + rnd() * 880),
    });
    close = nextClose;
  }
  return candles.reverse();
}

function round(v: number, digits = 5): number {
  const p = Math.pow(10, digits);
  return Math.round(v * p) / p;
}
