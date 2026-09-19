import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, Clock3, Search, Star } from 'lucide-react';
import { useHub } from '../context/HubContext';
import { isSimulation } from '../config/runtime';
import { classifySymbol, groupMt5Symbols, simulationSymbolRows, weltradeSyntxCatalogRows } from '../lib/symbols';
import { mt5MarketService } from '../services/mt5MarketService';
import { workspaceService } from '../services/workspaceService';
import type { Mt5SymbolInfo } from '../types';

function brokerFamily(broker = '', server = ''): 'deriv' | 'weltrade' | 'other' {
  const text = `${broker} ${server}`.toLowerCase();
  if (text.includes('weltrade') || text.includes('syntx')) return 'weltrade';
  if (text.includes('deriv') || text.includes('binary.com')) return 'deriv';
  return 'other';
}

function marketGroupKey(row: Mt5SymbolInfo) {
  const group = classifySymbol(row.symbol, row.description, row.path, row.category);
  if (group === 'Weltrade SyntX · FX Volatility') return 'fxvol';
  if (group === 'Weltrade SyntX · SFX Volatility') return 'sfxvol';
  if (group === 'Weltrade SyntX · PainX') return 'painx';
  if (group === 'Weltrade SyntX · GainX') return 'gainx';
  if (group === 'Weltrade SyntX · FlipX') return 'flipx';
  if (group === 'Weltrade SyntX · SwitchX') return 'switchx';
  if (group === 'Weltrade SyntX · BreakX') return 'breakx';
  if (group === 'Weltrade SyntX · TrendX') return 'trendx';
  if (group === 'Weltrade SyntX · Progression') return 'progression';
  if (group === 'Weltrade SyntX · MAX') return 'maxx';
  if (group.startsWith('Weltrade SyntX')) return 'weltrade_syntx';
  if (group.startsWith('Forex')) return 'forex';
  if (group === 'Synthetic / Volatility') return 'synthetic';
  if (group === 'Metals') return 'metals';
  if (group === 'Indices') return 'indices';
  if (group === 'Crypto') return 'crypto';
  if (group === 'Stocks / CFDs') return 'stocks';
  if (group === 'Energies') return 'energies';
  return 'other';
}

function normalizedSymbolKey(symbol: string) {
  return symbol
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, '')
    .replace(/^SFXVOL/, 'SFXV')
    .replace(/^FXVOL/, 'FXV');
}

const symbolRequestCache = new Map<number, Promise<Mt5SymbolInfo[]>>();

function cachedSymbols(login: number) {
  const existing = symbolRequestCache.get(login);
  if (existing) return existing;
  const request = mt5MarketService.symbols(login).catch((error) => {
    symbolRequestCache.delete(login);
    throw error;
  });
  symbolRequestCache.set(login, request);
  return request;
}

function mergeMarketRows(rows: Mt5SymbolInfo[]) {
  const merged = new Map<string, Mt5SymbolInfo>();
  for (const row of rows) {
    const family = row.broker_family || 'other';
    const key = family + ':' + normalizedSymbolKey(row.symbol);
    const prior = merged.get(key);
    if (!prior) {
      merged.set(key, { ...row, broker_family: family, available_logins: [...(row.available_logins || [])] });
      continue;
    }
    const available = [...new Set([...(prior.available_logins || []), ...(row.available_logins || [])])];
    const actual = prior.catalog_only && !row.catalog_only ? row : prior;
    merged.set(key, {
      ...actual,
      broker_family: family,
      available_logins: available,
      catalog_only: Boolean(prior.catalog_only && row.catalog_only),
    });
  }
  return [...merged.values()];
}

export default function MarketSelect({
  value,
  onChange,
  compact = false,
  tradeOnly = false,
  accountLogin,
  disabled = false,
}: {
  value: string;
  onChange: (symbol: string) => void;
  compact?: boolean;
  tradeOnly?: boolean;
  accountLogin?: number;
  disabled?: boolean;
}) {
  const { mt5Symbols, accounts, activeAccount, prefs, setPrefs } = useHub();
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [accountRows, setAccountRows] = useState<Mt5SymbolInfo[] | null>(null);
  const [connectedCatalogRows, setConnectedCatalogRows] = useState<Mt5SymbolInfo[]>([]);
  const [loadingAccount, setLoadingAccount] = useState(false);
  const [favorites, setFavorites] = useState<string[]>([]);
  const [recent, setRecent] = useState<string[]>([]);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const storageScope = String(accountLogin || 'global');
  const connectedAccountKey = useMemo(
    () => accounts.filter((item) => item.status === 'connected').map((item) => `${item.login}:${item.broker}:${item.server}`).sort().join('|'),
    [accounts],
  );

  useEffect(() => {
    const serverFavorites = prefs.marketFavorites?.[storageScope];
    setFavorites(serverFavorites?.length ? serverFavorites : workspaceService.getRaw<string[]>(`market_favorites:${storageScope}`, []));
    setRecent(workspaceService.getRaw<string[]>(`market_recent:${storageScope}`, []));
  }, [storageScope, prefs.marketFavorites]);

  useEffect(() => {
    if (isSimulation || !accountLogin) {
      setAccountRows(null);
      setLoadingAccount(false);
      return;
    }
    let cancelled = false;
    setLoadingAccount(true);
    cachedSymbols(accountLogin)
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

  useEffect(() => {
    if (isSimulation) {
      setConnectedCatalogRows([]);
      return;
    }
    let cancelled = false;
    const connected = accounts.filter((item) => item.status === 'connected');
    Promise.all(connected.map(async (account) => {
      try {
        const rows = await cachedSymbols(account.login);
        const family = brokerFamily(account.broker, account.server);
        return rows.map((row) => ({
          ...row,
          broker_family: family,
          available_logins: [account.login],
          catalog_only: false,
        }));
      } catch {
        return [];
      }
    })).then((groups) => {
      if (!cancelled) setConnectedCatalogRows(mergeMarketRows(groups.flat()));
    });
    return () => { cancelled = true; };
  }, [connectedAccountKey]);

  const allRows = useMemo(() => {
    if (isSimulation) {
      let rows = simulationSymbolRows();
      const category = prefs.marketCategoryFilter;
      if (category !== 'all') rows = rows.filter((row) => marketGroupKey(row) === category);
      return rows;
    }

    const account = accountLogin
      ? accounts.find((item) => item.login === accountLogin)
      : (activeAccount?.status === 'connected' ? activeAccount : accounts.find((item) => item.status === 'connected'));
    const currentFamily = account ? brokerFamily(account.broker, account.server) : 'other';
    const selectedRows = accountLogin && accountRows
      ? accountRows.map((row) => ({ ...row, broker_family: currentFamily, available_logins: [accountLogin], catalog_only: false }))
      : [];
    const fallbackRows = connectedCatalogRows.length || !mt5Symbols.length
      ? []
      : mt5Symbols.map((row) => ({
          ...row,
          broker_family: currentFamily,
          available_logins: account ? [account.login] : [],
          catalog_only: false,
        }));
    const globalRows = mergeMarketRows([
      ...connectedCatalogRows,
      ...selectedRows,
      ...fallbackRows,
      ...weltradeSyntxCatalogRows(),
    ]);

    let rows = globalRows;
    const brokerFilter = prefs.marketBrokerFilter;
    if (brokerFilter === 'current') {
      rows = accountLogin
        ? globalRows.filter((row) => (row.available_logins || []).includes(accountLogin))
        : globalRows.filter((row) => row.broker_family === currentFamily);
    } else if (brokerFilter === 'deriv' || brokerFilter === 'weltrade') {
      rows = globalRows.filter((row) => row.broker_family === brokerFilter);
    } else if (brokerFilter === 'favorites') {
      rows = globalRows.filter((row) => favorites.includes(row.symbol));
    } else if (brokerFilter === 'custom') {
      rows = globalRows.filter((row) => prefs.customBrokerFamilies.includes(row.broker_family || 'other'));
    }

    if (tradeOnly) rows = rows.filter((row) => row.catalog_only || row.trade_allowed);

    const category = prefs.marketCategoryFilter;
    if (category !== 'all') {
      rows = rows.filter((row) => {
        const key = marketGroupKey(row);
        if (category === 'weltrade_syntx') return row.broker_family === 'weltrade';
        if (category === 'custom') {
          return prefs.customMarketGroups.includes(key as typeof prefs.customMarketGroups[number])
            || (row.broker_family === 'weltrade' && prefs.customMarketGroups.includes('weltrade_syntx'));
        }
        return key === category;
      });
    }
    return rows;
  }, [mt5Symbols, accountRows, connectedCatalogRows, accountLogin, tradeOnly, accounts, activeAccount, prefs, favorites]);

  useEffect(() => {
    if (loadingAccount || !allRows.length) return;
    const current = allRows.find((row) => row.symbol === value);
    const selectable = allRows.find((row) => !accountLogin || (row.available_logins || []).includes(accountLogin));
    if ((!current || (accountLogin && !(current.available_logins || []).includes(accountLogin))) && selectable) {
      onChange(selectable.symbol);
    }
  }, [allRows, accountLogin, loadingAccount, onChange, value]);

  const source = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q
      ? allRows.filter((row) => `${row.symbol} ${row.description} ${row.category || ''} ${row.path || ''}`.toLowerCase().includes(q))
      : allRows;
  }, [allRows, query]);

  const groups = useMemo(() => groupMt5Symbols(source), [source]);
  const selected = allRows.find((row) => row.symbol === value);
  const rowAvailable = (row: Mt5SymbolInfo) => !accountLogin || (row.available_logins || []).includes(accountLogin);
  const unavailableCount = accountLogin ? allRows.filter((row) => !rowAvailable(row)).length : 0;
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
    setPrefs({ marketFavorites: { ...prefs.marketFavorites, [storageScope]: next } });
  };

  const choose = (row: Mt5SymbolInfo) => {
    if (!rowAvailable(row)) return;
    onChange(row.symbol);
    remember(row.symbol);
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

  const renderMarketRow = (row: Mt5SymbolInfo) => {
    const available = rowAvailable(row);
    return (
    <div key={`${row.broker_family || 'other'}:${row.symbol}`} className={`flex items-center rounded-lg ${available ? 'hover:bg-white/[0.06]' : 'opacity-60'}`}>
      <button
        type="button"
        disabled={!available}
        onClick={() => choose(row)}
        className="flex min-w-0 flex-1 items-center gap-2 px-2.5 py-2.5 text-left disabled:cursor-not-allowed"
      >
        <span className="min-w-0 flex-1">
          <span className="mono block truncate text-xs font-bold text-slate-200">{row.symbol}</span>
          {row.description && row.description !== row.symbol && <span className="block truncate text-[10px] text-slate-600">{row.description}</span>}
          {!available && <span className="block truncate text-[9px] text-warn-300">Not available on MT5 account #{accountLogin} · connect/select the matching broker account</span>}
        </span>
        {available && row.symbol === value && <Check size={14} className="shrink-0 text-brand-300" />}
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
  };

  if (compact) {
    return (
      <div className="relative min-w-0" ref={wrapRef}>
        <button type="button" disabled={disabled} className="input flex w-full items-center justify-between gap-3 text-left disabled:cursor-not-allowed disabled:opacity-60" onClick={() => setOpen((current) => !current)} aria-expanded={open}>
          <span className="min-w-0 flex-1">
            <span className="mono block truncate text-slate-100">{loadingAccount ? 'Loading broker markets…' : selected?.symbol || (allRows.length ? 'Choose market' : value || 'Choose symbol')}</span>
            {selected?.description && selected.description !== selected.symbol && <span className="block truncate text-[10px] text-slate-600">{selected.description}</span>}
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
                  ? `${source.length} markets shown · ${Math.max(0, source.length - unavailableCount)} available on account #${accountLogin}`
                  : `${source.length} markets across connected brokers + catalog`} · type to filter instantly
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
      <select disabled={disabled} className="input !py-2 text-xs disabled:cursor-not-allowed disabled:opacity-60" value={value} onChange={(e) => { onChange(e.target.value); remember(e.target.value); }}>
        {groups.map(([group, rows]) => (
          <optgroup key={group} label={group + ' (' + rows.length + ')'}>
            {rows.map((row) => <option key={`${row.broker_family || 'other'}:${row.symbol}`} value={row.symbol} disabled={!rowAvailable(row)}>{row.symbol}{row.description && row.description !== row.symbol ? ' — ' + row.description : ''}{!rowAvailable(row) ? ' — unavailable on selected account' : ''}</option>)}
          </optgroup>
        ))}
      </select>
      <p className="mt-1.5 text-[10px] text-slate-600">{isSimulation ? source.length + ' simulated markets available' : accountLogin ? `${source.length} markets shown · ${Math.max(0, source.length - unavailableCount)} available on account #${accountLogin}` : `${source.length} markets across connected brokers + catalog`}</p>
    </div>
  );
}
