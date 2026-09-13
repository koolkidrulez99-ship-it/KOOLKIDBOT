import { MARKET } from './market';

export const fmtUSD = (v: number | null | undefined, digits = 2): string => {
  if (v === null || v === undefined || Number.isNaN(v)) return '$0.00';
  return (
    (v < 0 ? '-$' : '$') +
    Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
  );
};

export const fmtSigned = (v: number | null | undefined, digits = 2): string => {
  if (v === null || v === undefined || Number.isNaN(v)) return '$0.00';
  const abs = Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return v > 0 ? `+$${abs}` : v < 0 ? `-$${abs}` : `$${abs}`;
};

export const fmtCompact = (v: number): string => {
  const abs = Math.abs(v);
  const sign = v < 0 ? '-' : '';
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(1)}K`;
  return `${sign}$${abs.toFixed(0)}`;
};

export const fmtPrice = (v: number | null | undefined, symbol?: string): string => {
  if (v === null || v === undefined) return '\u2014';
  const digits = symbol && MARKET[symbol] ? MARKET[symbol].digits : 2;
  return v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
};

export const fmtLots = (v: number): string => v.toFixed(2);

export const fmtPct = (v: number, digits = 1): string => `${v.toFixed(digits)}%`;

export const profitTone = (v: number): string =>
  v > 0 ? 'text-gain-400' : v < 0 ? 'text-loss-400' : 'text-slate-400';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export const fmtDay = (dateStr: string): string => {
  const [y, m, d] = dateStr.slice(0, 10).split('-').map(Number);
  return `${MONTHS[(m || 1) - 1]} ${d}`;
};

export const fmtDateTime = (iso: string): string => {
  const d = new Date(iso);
  return `${MONTHS[d.getMonth()]} ${d.getDate()}, ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
};

export const fmtTime = (iso: string): string => {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
};

export const timeAgo = (iso: string): string => {
  const ms = Date.now() - new Date(iso).getTime();
  const min = Math.floor(ms / 60000);
  if (min < 1) return 'just now';
  if (min < 60) return `${min}m ago`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h}h ${min % 60}m ago`;
  const days = Math.floor(h / 24);
  return `${days}d ${h % 24}h ago`;
};

export const durationBetween = (fromIso: string, toIso: string): string => {
  const ms = new Date(toIso).getTime() - new Date(fromIso).getTime();
  const min = Math.max(1, Math.floor(ms / 60000));
  if (min < 60) return `${min}m`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h}h ${min % 60}m`;
  const days = Math.floor(h / 24);
  return `${days}d ${h % 24}h`;
};

export const uptimeSince = (iso: string | null): string => {
  if (!iso) return '\u2014';
  const ms = Date.now() - new Date(iso).getTime();
  const min = Math.max(1, Math.floor(ms / 60000));
  if (min < 60) return `${min}m`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h}h ${min % 60}m`;
  return `${Math.floor(h / 24)}d ${h % 24}h`;
};

export const pips = (symbol: string, open: number, close: number): number => {
  const m = MARKET[symbol];
  if (!m) return 0;
  return (close - open) / m.pip;
};
