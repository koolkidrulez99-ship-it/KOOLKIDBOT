import type { Mt5SymbolInfo } from '../types';
import { SYMBOL_LIST } from './market';

const FX_CODES = ['USD','EUR','GBP','JPY','CHF','AUD','CAD','NZD','SGD','HKD','NOK','SEK','ZAR','TRY','MXN','CNH','PLN','HUF','CZK'];

export function classifySymbol(symbol: string, description = '', path = '', explicit?: string) {
  if (explicit) return explicit;
  const hint = `${symbol} ${description} ${path}`.toUpperCase();
  const clean = symbol.toUpperCase().replace(/[^A-Z]/g, '');
  const isFx = FX_CODES.some((a) => FX_CODES.some((b) => a !== b && clean.startsWith(a + b)));
  if (isFx || hint.includes('FOREX') || hint.includes('FX\\')) return 'Forex';
  if (['VOLATILITY','BOOM','CRASH','STEP','JUMP','RANGE BREAK','SYNTHETIC','DERIVED'].some((x) => hint.includes(x))) return 'Synthetic / Volatility';
  if (['XAU','XAG','GOLD','SILVER','METAL'].some((x) => hint.includes(x))) return 'Metals';
  if (['BTC','ETH','LTC','XRP','SOL','CRYPTO'].some((x) => hint.includes(x))) return 'Crypto';
  if (['INDEX','INDICES','US30','NAS','SP500','GER','UK100','JP225'].some((x) => hint.includes(x))) return 'Indices';
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
  const order = ['Forex', 'Synthetic / Volatility', 'Metals', 'Indices', 'Crypto', 'Other'];
  return [...map.entries()].sort((a, b) => (order.indexOf(a[0]) < 0 ? 99 : order.indexOf(a[0])) - (order.indexOf(b[0]) < 0 ? 99 : order.indexOf(b[0])));
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
