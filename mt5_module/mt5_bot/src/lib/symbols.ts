import type { Mt5SymbolInfo } from '../types';
import { SYMBOL_LIST } from './market';

const FX_CODES = ['USD','EUR','GBP','JPY','CHF','AUD','CAD','NZD','SGD','HKD','NOK','SEK','ZAR','TRY','MXN','CNH','PLN','HUF','CZK'];
const MAJORS = new Set(['EURUSD','GBPUSD','USDJPY','USDCHF','AUDUSD','USDCAD','NZDUSD']);

export function classifySymbol(symbol: string, description = '', path = '', explicit?: string) {
  const rawSymbol = symbol.toUpperCase();
  const hint = `${symbol} ${description} ${path} ${explicit || ''}`.toUpperCase();
  const clean = rawSymbol.replace(/[^A-Z]/g, '');

  // Weltrade SyntX families. These are grouped before generic broker categories
  // so an account exposing FXV50 / PainX / GainX / FlipX stays easy to browse.
  if (rawSymbol.startsWith('SFXV') || hint.includes('SFX VOL')) return 'Weltrade SyntX · SFX Volatility';
  if (rawSymbol.startsWith('FXV') || hint.includes('FX VOL')) return 'Weltrade SyntX · FX Volatility';
  if (rawSymbol.startsWith('PAIN') || hint.includes('PAINX')) return 'Weltrade SyntX · PainX';
  if (rawSymbol.startsWith('GAIN') || hint.includes('GAINX')) return 'Weltrade SyntX · GainX';
  if (rawSymbol.startsWith('FLIP') || hint.includes('FLIPX')) return 'Weltrade SyntX · FlipX';
  if (hint.includes('SYNTX') || hint.includes('SYNT X')) return 'Weltrade SyntX · Other';

  const fxPair = clean.slice(0, 6);
  const isFx = FX_CODES.some((a) => FX_CODES.some((b) => a !== b && clean.startsWith(a + b)));
  if (isFx || hint.includes('FOREX') || hint.includes('FX\\')) {
    return MAJORS.has(fxPair) ? 'Forex · Majors' : 'Forex · Minors & Exotics';
  }

  if (['VOLATILITY','BOOM','CRASH','STEP','JUMP','RANGE BREAK','SYNTHETIC','DERIVED'].some((x) => hint.includes(x))) return 'Synthetic / Volatility';
  if (['XAU','XAG','GOLD','SILVER','METAL'].some((x) => hint.includes(x))) return 'Metals';
  if (['OIL','WTI','BRENT','XBR','XTI','ENERGY','NATGAS','GAS'].some((x) => hint.includes(x))) return 'Energies';
  if (['BTC','ETH','LTC','XRP','SOL','DOGE','ADA','CRYPTO'].some((x) => hint.includes(x))) return 'Crypto';
  if (['INDEX','INDICES','US30','NAS','SP500','GER','DE40','UK100','JP225','AUS200','FRA40'].some((x) => hint.includes(x))) return 'Indices';
  if (['STOCK','SHARE','EQUITY','NASDAQ STOCK','NYSE'].some((x) => hint.includes(x))) return 'Stocks / CFDs';

  if (explicit && explicit.trim()) return explicit.trim();
  return 'Other';
}

export function groupMt5Symbols(rows: Mt5SymbolInfo[]) {
  const map = new Map<string, Mt5SymbolInfo[]>();
  for (const row of rows) {
    const group = classifySymbol(row.symbol, row.description, row.path, row.category);
    if (!map.has(group)) map.set(group, []);
    map.get(group)!.push(row);
  }
  for (const list of map.values()) list.sort((a, b) => a.symbol.localeCompare(b.symbol));

  const order = [
    'Weltrade SyntX · FX Volatility',
    'Weltrade SyntX · SFX Volatility',
    'Weltrade SyntX · PainX',
    'Weltrade SyntX · GainX',
    'Weltrade SyntX · FlipX',
    'Weltrade SyntX · Other',
    'Synthetic / Volatility',
    'Forex · Majors',
    'Forex · Minors & Exotics',
    'Metals',
    'Energies',
    'Indices',
    'Crypto',
    'Stocks / CFDs',
    'Other',
  ];

  return [...map.entries()].sort((a, b) => {
    const ai = order.indexOf(a[0]);
    const bi = order.indexOf(b[0]);
    const av = ai < 0 ? 99 : ai;
    const bv = bi < 0 ? 99 : bi;
    return av === bv ? a[0].localeCompare(b[0]) : av - bv;
  });
}

export function simulationSymbolRows(): Mt5SymbolInfo[] {
  return SYMBOL_LIST.map((symbol) => ({
    symbol,
    description: symbol,
    digits: 5,
    point: 0.00001,
    contract_size: 100000,
    volume_min: 0.01,
    volume_max: 100,
    volume_step: 0.01,
    visible: true,
    trade_allowed: true,
    category: classifySymbol(symbol),
  }));
}
