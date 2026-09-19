import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, Clock3, Search, Star } from 'lucide-react';
import { useHub } from '../context/HubContext';
import { isSimulation } from '../config/runtime';
import { groupMt5Symbols, simulationSymbolRows } from '../lib/symbols';
import { mt5MarketService } from '../services/mt5MarketService';
import { workspaceService } from '../services/workspaceService';
import type { Mt5SymbolInfo } from '../types';

export default function MarketSelect({
  value,
  onChange,
  compact = false,
  tradeOnly = false,
  accountLogin,
}: {
  value: string;
  onChange: (symbol: string) => void;
  compact?: boolean;
  tradeOnly?: boolean;
  accountLogin?: number;
}) {
  const { mt5Symbols } = useHub();
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [accountRows, setAccountRows] = useState<Mt5SymbolInfo[] | null>(null);
  const [loadingAccount, setLoadingAccount] = useState(false);
  const [favorites, setFavorites] = useState<string[]>([]);
  const [recent, setRecent] = useState<string[]>([]);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const storageScope = String(accountLogin || 'global');

  useEffect(() => {
    setFavorites(workspaceService.getRaw<string[]>(`market_favorites:${storageScope}`, []));
    setRecent(workspaceService.getRaw<string[]>(`market_recent:${storageScope}`, []));
  }, [storageScope]);

  useEffect(() => {
    if (isSimulation || !accountLogin) {
      setAccountRows(null);
      setLoadingAccount(false);
      return;
    }
    let cancelled = false;
    setLoadingAccount(true);
    mt5MarketService.symbols(accountLogin)
      .then((rows) => {
        if (!cancelled) setAccountRows(rows);
      })
      .catch(() => {
        if (!cancelled) setAccountRows([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingAccount(false);
      });
    return () => { cancelled = true; };
  }, [accountLogin]);

  const allRows = useMemo(() => {
    const rows = isSimulation
      ? simulationSymbolRows()
      : accountLogin && accountRows !== null
        ? accountRows
        : mt5Symbols;
    return tradeOnly ? rows.filter((row) => row.trade_allowed) : rows;
  }, [mt5Symbols, accountRows, accountLogin, tradeOnly]);

  useEffect(() => {
    if (loadingAccount || !allRows.length) return;
    if (!allRows.some((row) => row.symbol === value)) onChange(allRows[0].symbol);
  }, [allRows, loadingAccount, onChange, value]);

  const source = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q
      ? allRows.filter((row) => `${row.symbol} ${row.description} ${row.category || ''} ${row.path || ''}`.toLowerCase().includes(q))
      : allRows;
  }, [allRows, query]);

  const groups = useMemo(() => groupMt5Symbols(source), [source]);
  const selected = allRows.find((row) => row.symbol === value);
  const favoritesRows = useMemo(
    () => favorites.map((symbol) => allRows.find((row) => row.symbol === symbol)).filter(Boolean) as Mt5SymbolInfo[],
    [favorites, allRows],
  );
  const recentRows = useMemo(
    () => recent.map((symbol) => allRows.find((row) => row.symbol === symbol)).filter(Boolean) as Mt5SymbolInfo[],
    [recent, allRows],
  );

  const remember = (nextSymbol: string) => {
    const next = [nextSymbol, ...recent.filter((symbol) => symbol !== nextSymbol)].slice(0, 8);
    setRecent(next);
    workspaceService.set(`market_recent:${storageScope}`, next);
  };

  const toggleFavorite = (nextSymbol: string) => {
    const next = favorites.includes(nextSymbol)
      ? favorites.filter((symbol) => symbol !== nextSymbol)
      : [nextSymbol, ...favorites].slice(0, 16);
    setFavorites(next);
    workspaceService.set(`market_favorites:${storageScope}`, next);
  };

  const choose = (nextSymbol: string) => {
    onChange(nextSymbol);
    remember(nextSymbol);
    setOpen(false);
    setQuery('');
  };

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!wrapRef.current?.contains(event.target as Node)) {
        setOpen(false);
        setQuery('');
      }
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);

  const renderMarketRow = (row: Mt5SymbolInfo) => (
    <div key={row.symbol} className="flex items-center rounded-lg hover:bg-white/[0.06]">
      <button
        type="button"
        onClick={() => choose(row.symbol)}
        className="flex min-w-0 flex-1 items-center gap-2 px-2.5 py-2.5 text-left"
      >
        <span className="min-w-0 flex-1">
          <span className="mono block truncate text-xs font-bold text-slate-200">{row.symbol}</span>
          {row.description && row.description !== row.symbol && <span className="block truncate text-[10px] text-slate-600">{row.description}</span>}
        </span>
        {row.symbol === value && <Check size={14} className="shrink-0 text-brand-300" />}
      </button>
      <button
        type="button"
        onClick={() => toggleFavorite(row.symbol)}
        className="mr-1 grid h-8 w-8 shrink-0 place-items-center rounded-md text-slate-600 hover:bg-white/[0.06] hover:text-warn-300"
        title={favorites.includes(row.symbol) ? 'Remove from favorites' : 'Add to favorites'}
        aria-label={favorites.includes(row.symbol) ? `Remove ${row.symbol} from favorites` : `Add ${row.symbol} to favorites`}
      >
        <Star size={13} fill={favorites.includes(row.symbol) ? 'currentColor' : 'none'} />
      </button>
    </div>
  );

  if (compact) {
    return (
      <div className="relative min-w-0" ref={wrapRef}>
        <button type="button" className="input flex w-full items-center justify-between gap-3 text-left" onClick={() => setOpen((current) => !current)} aria-expanded={open}>
          <span className="min-w-0 flex-1">
            <span className="mono block truncate text-slate-100">{loadingAccount ? 'Loading broker markets…' : value || 'Choose symbol'}</span>
            {selected?.description && selected.description !== value && <span className="block truncate text-[10px] text-slate-600">{selected.description}</span>}
          </span>
          <ChevronDown size={15} className={`shrink-0 text-slate-500 transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>

        {open && (
          <div className="absolute left-0 z-[80] mt-2 w-[440px] max-w-[calc(100vw-32px)] overflow-hidden rounded-xl border border-white/10 bg-[#0b1019] p-2 shadow-2xl">
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-600" />
              <input
                autoFocus
                className="input !pl-9 !py-2 text-xs"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Escape') {
                    setOpen(false);
                    setQuery('');
                  }
                }}
                placeholder="Search FXV50, gold, EURUSD, PainX…"
              />
            </div>

            <div className="mt-2 max-h-80 overflow-y-auto pr-1">
              {loadingAccount && <p className="px-3 py-6 text-center text-xs text-slate-600">Loading every symbol from this MT5 account…</p>}
              {!loadingAccount && !groups.length && <p className="px-3 py-6 text-center text-xs text-slate-600">No matching markets.</p>}

              {!loadingAccount && !query.trim() && favoritesRows.length > 0 && (
                <div className="mb-2">
                  <p className="sticky top-0 z-10 flex items-center gap-1.5 bg-[#0b1019] px-2 py-1.5 text-[9px] font-bold uppercase tracking-widest text-warn-300"><Star size={10} fill="currentColor" /> Favorites · {favoritesRows.length}</p>
                  {favoritesRows.map(renderMarketRow)}
                </div>
              )}

              {!loadingAccount && !query.trim() && recentRows.length > 0 && (
                <div className="mb-2">
                  <p className="sticky top-0 z-10 flex items-center gap-1.5 bg-[#0b1019] px-2 py-1.5 text-[9px] font-bold uppercase tracking-widest text-slate-500"><Clock3 size={10} /> Recent · {recentRows.length}</p>
                  {recentRows.map(renderMarketRow)}
                </div>
              )}

              {!loadingAccount && groups.map(([group, rows]) => (
                <div key={group} className="mb-2 last:mb-0">
                  <p className="sticky top-0 z-10 bg-[#0b1019] px-2 py-1.5 text-[9px] font-bold uppercase tracking-widest text-slate-500">{group} · {rows.length}</p>
                  {rows.map(renderMarketRow)}
                </div>
              ))}
            </div>

            <p className="border-t border-white/[0.06] px-2 pt-2 text-[9px] text-slate-600">
              {isSimulation
                ? `${source.length} simulated markets`
                : accountLogin
                  ? `${source.length} tradable broker markets loaded from MT5 account #${accountLogin}`
                  : `${source.length} broker symbols`} · type to filter instantly
            </p>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-white/[0.07] bg-black/20 p-2.5 min-w-[260px]">
      <div className="relative mb-2">
        <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-600" />
        <input className="input !pl-8 !py-2 text-xs" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search broker markets…" />
      </div>
      <select className="input !py-2 text-xs" value={value} onChange={(e) => { onChange(e.target.value); remember(e.target.value); }}>
        {groups.map(([group, rows]) => (
          <optgroup key={group} label={group + ' (' + rows.length + ')'}>
            {rows.map((row) => <option key={row.symbol} value={row.symbol}>{row.symbol}{row.description && row.description !== row.symbol ? ' — ' + row.description : ''}</option>)}
          </optgroup>
        ))}
      </select>
      <p className="mt-1.5 text-[10px] text-slate-600">{isSimulation ? source.length + ' simulated markets available' : source.length + ' broker symbols loaded from MT5'}</p>
    </div>
  );
}
