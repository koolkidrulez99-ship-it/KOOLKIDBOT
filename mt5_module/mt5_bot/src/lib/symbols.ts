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
  if (rawSymbol.startsWith('SWITCH') || hint.includes('SWITCHX')) return 'Weltrade SyntX · SwitchX';
  if (rawSymbol.startsWith('BREAK') || hint.includes('BREAKX')) return 'Weltrade SyntX · BreakX';
  if (rawSymbol.startsWith('TREND') || hint.includes('TRENDX')) return 'Weltrade SyntX · TrendX';
  if (rawSymbol.startsWith('PLUS') || rawSymbol.startsWith('FIBO') || rawSymbol.startsWith('QUAD') || hint.includes('PLUSX') || hint.includes('FIBOX') || hint.includes('QUADX')) return 'Weltrade SyntX · Progression';
  if (hint.includes('MAX PAIN') || hint.includes('MAXPAIN') || hint.includes('MAX GAIN') || hint.includes('MAXGAIN')) return 'Weltrade SyntX · MAX';
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
    'Weltrade SyntX · SwitchX',
    'Weltrade SyntX · BreakX',
    'Weltrade SyntX · TrendX',
    'Weltrade SyntX · Progression',
    'Weltrade SyntX · MAX',
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

const WELTRADE_SYNTX_CATALOG: Array<[string, string, string?]> = [
  ...[20, 40, 60, 80, 99].map((n) => [`FX Vol ${n}`, 'FX Volatility', `FXVol${n} / FXV${n}`] as [string, string, string]),
  ...[20, 40, 60, 80, 99].map((n) => [`SFX Vol ${n}`, 'SFX Volatility', `SFXVol${n} / SFXV${n}`] as [string, string, string]),
  ...[400, 600, 800, 999, 1200].map((n) => [`PainX ${n}`, 'PainX'] as [string, string]),
  ...[400, 600, 800, 999, 1200].map((n) => [`GainX ${n}`, 'GainX'] as [string, string]),
  ...[1, 2, 3, 4, 5].map((n) => [`FlipX ${n}`, 'FlipX'] as [string, string]),
  ...[600, 1200, 1800].map((n) => [`SwitchX ${n}`, 'SwitchX'] as [string, string]),
  ...[600, 1200, 1800].map((n) => [`BreakX ${n}`, 'BreakX'] as [string, string]),
  ...[600, 1200, 1800].map((n) => [`TrendX ${n}`, 'TrendX'] as [string, string]),
  ['PlusX 1', 'Progression'],
  ['FiboX', 'Progression'],
  ['QuadX', 'Progression'],
  ['MAX PainX', 'MAX'],
  ['MAX GainX', 'MAX'],
];

export function weltradeSyntxCatalogRows(): Mt5SymbolInfo[] {
  return WELTRADE_SYNTX_CATALOG.map(([symbol, group, alias]) => ({
    symbol,
    description: `Weltrade SyntX · ${group}${alias ? ` · ${alias}` : ''}`,
    digits: 0,
    point: 0,
    contract_size: 0,
    volume_min: 0,
    volume_max: 0,
    volume_step: 0,
    visible: true,
    trade_allowed: false,
    path: `Weltrade\\SyntX\\${group}`,
    category: `Weltrade SyntX · ${group}`,
    broker_family: 'weltrade',
    available_logins: [],
    catalog_only: true,
    availability_note: 'Connect a Weltrade SyntX MT5 account to use the broker-exact symbol.',
  }));
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
