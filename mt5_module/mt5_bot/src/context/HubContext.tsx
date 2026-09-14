import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { isSimulation } from '../config/runtime';
import { MARKET, SYMBOL_LIST, calcProfit } from '../lib/market';
import { mt5AccountService } from '../services/mt5AccountService';
import { mt5BotService } from '../services/mt5BotService';
import { mt5BridgeService } from '../services/mt5BridgeService';
import { mt5HistoryService } from '../services/mt5HistoryService';
import { mt5MarketService } from '../services/mt5MarketService';
import { mt5PositionService } from '../services/mt5PositionService';
import type { BridgeInfo, Mt5Account, Mt5Bot, Mt5Position, Mt5Quote, Mt5Stats, Mt5SymbolInfo } from '../types';
import { workspaceService } from '../services/workspaceService';

export type ActiveSel = number | 'all';

export interface Toast {
  id: number;
  tone: 'success' | 'error' | 'info' | 'warning';
  title: string;
  message?: string;
}

interface HubCtx {
  accounts: Mt5Account[];
  bots: Mt5Bot[];
  positions: Mt5Position[];
  stats: Mt5Stats | null;
  bridge: BridgeInfo | null;
  loading: boolean;
  bridgeStarting: boolean;
  refreshing: boolean;
  error: string | null;
  market: Record<string, number>;
  quotes: Record<string, Mt5Quote>;
  mt5Symbols: Mt5SymbolInfo[];
  botDrift: Record<number, number>;
  active: ActiveSel;
  setActive: (sel: ActiveSel) => Promise<void>;
  activeAccount: Mt5Account | null;
  scopeAccounts: Mt5Account[];
  scopePositions: Mt5Position[];
  scopeBots: Mt5Bot[];
  derived: {
    balance: number;
    floating: number;
    equity: number;
    margin: number;
    todayPl: number;
    runningBots: number;
  };
  livePrice: (symbol: string) => number;
  liveQuote: (symbol: string) => Mt5Quote | null;
  liveProfit: (p: Mt5Position) => number;
  botLiveToday: (b: Mt5Bot) => number;
  refresh: (silent?: boolean) => Promise<void>;
  refreshPositions: () => Promise<void>;
  accountName: (login: number | null | undefined) => string;
  prefs: { pollMs: number; confirmDanger: boolean; restoreWorkspace: boolean; reconnectOnStartup: boolean };
  setPrefs: (p: Partial<{ pollMs: number; confirmDanger: boolean; restoreWorkspace: boolean; reconnectOnStartup: boolean }>) => void;
  toasts: Toast[];
  pushToast: (tone: Toast['tone'], title: string, message?: string) => void;
  dismissToast: (id: number) => void;
}

const Ctx = createContext<HubCtx | null>(null);
let toastSeq = 1;

export function HubProvider({ children }: { children: ReactNode }) {
  const [accounts, setAccounts] = useState<Mt5Account[]>([]);
  const [bots, setBots] = useState<Mt5Bot[]>([]);
  const [positions, setPositions] = useState<Mt5Position[]>([]);
  const [stats, setStats] = useState<Mt5Stats | null>(null);
  const [bridge, setBridge] = useState<BridgeInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [bridgeStarting, setBridgeStarting] = useState(!isSimulation);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [active, setActiveState] = useState<ActiveSel>(() => workspaceService.getRaw<ActiveSel>('active_account', 'all'));
  const [toasts, setToasts] = useState<Toast[]>([]);

  const [prefs, setPrefsState] = useState<{ pollMs: number; confirmDanger: boolean; restoreWorkspace: boolean; reconnectOnStartup: boolean }>(() => {
    try {
      const raw = localStorage.getItem('koolkid_mt5_prefs');
      if (raw) return { pollMs: isSimulation ? 15000 : 5000, confirmDanger: true, restoreWorkspace: true, reconnectOnStartup: true, ...JSON.parse(raw) };
    } catch { /* ignore */ }
    return { pollMs: isSimulation ? 15000 : 5000, confirmDanger: true, restoreWorkspace: true, reconnectOnStartup: true };
  });

  const [market, setMarket] = useState<Record<string, number>>(() => {
    const result: Record<string, number> = {};
    for (const s of Object.keys(MARKET)) result[s] = MARKET[s].base;
    return result;
  });
  const [quotes, setQuotes] = useState<Record<string, Mt5Quote>>({});
  const [mt5Symbols, setMt5Symbols] = useState<Mt5SymbolInfo[]>([]);
  const [botDrift, setBotDrift] = useState<Record<number, number>>({});

  const pushToast = useCallback((tone: Toast['tone'], title: string, message?: string) => {
    const id = toastSeq++;
    setToasts((t) => [...t, { id, tone, title, message }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4600);
  }, []);

  const dismissToast = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), []);

  const refresh = useCallback(async (silent = false, retryStartup = !silent) => {
    if (!silent) setRefreshing(true);
    const attempts = !isSimulation && retryStartup ? 20 : 1;
    if (attempts > 1) setBridgeStarting(true);
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      try {
        const [a, b, p, s, br] = await Promise.all([
          mt5AccountService.list(), mt5BotService.list(), mt5PositionService.list(),
          mt5HistoryService.stats(), mt5BridgeService.status(),
        ]);
        setAccounts(a); setBots(b); setPositions(p); setStats(s); setBridge(br); setError(null);
        break;
      } catch (e) {
        if (attempt + 1 < attempts) {
          await new Promise((resolve) => window.setTimeout(resolve, 1500));
          continue;
        }
        setError(isSimulation ? (e instanceof Error ? e.message : 'Failed to load MT5 Hub data.') : 'MT5 bridge is offline');
      }
    }
    setBridgeStarting(false);
    setLoading(false);
    setRefreshing(false);
  }, []);

  const refreshPositions = useCallback(async () => {
    try { setPositions(await mt5PositionService.list()); } catch { /* silent */ }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const didApplyStartupReconnect = useRef(false);
  useEffect(() => {
    if (loading || didApplyStartupReconnect.current || !accounts.length) return;
    didApplyStartupReconnect.current = true;
    const remembered = workspaceService.getRaw<ActiveSel>('active_account', 'all');
    const preferred = accounts.find((a) => a.login === remembered) || accounts.find((a) => a.is_active);
    const ordered = preferred ? [preferred, ...accounts.filter((a) => a.id !== preferred.id)] : accounts;
    let cancelled = false;
    void (async () => {
      for (const account of ordered) {
        if (cancelled) return;
        const action = prefs.reconnectOnStartup ? 'connect' : 'disconnect';
        if ((action === 'connect' && account.status === 'connected') || (action === 'disconnect' && account.status !== 'connected')) continue;
        try {
          await mt5AccountService.action(account.id, action);
        } catch {
          // Continue sequentially so one account requiring fresh credentials does not block the rest.
        }
      }
      if (!cancelled) await refresh(true);
    })();
    return () => { cancelled = true; };
  }, [loading, prefs.reconnectOnStartup, refresh]);

  const didInitActive = useRef(false);
  useEffect(() => {
    if (didInitActive.current || !accounts.length) return;
    const remembered = workspaceService.getRaw<ActiveSel>('active_account', 'all');
    if (remembered === 'all') {
      setActiveState('all');
    } else if (accounts.some((a) => a.login === remembered)) {
      setActiveState(remembered);
    } else {
      const cur = accounts.find((a) => a.is_active);
      setActiveState(cur?.login ?? 'all');
    }
    didInitActive.current = true;
  }, [accounts]);

  useEffect(() => {
    const id = window.setInterval(() => refresh(true), prefs.pollMs);
    return () => window.clearInterval(id);
  }, [refresh, prefs.pollMs]);

  // Self-contained market motion exists only in simulation mode. A real bridge must replace this feed.
  useEffect(() => {
    if (!isSimulation) return;
    const id = window.setInterval(() => {
      setMarket((prev) => {
        const next = { ...prev };
        for (const sym of Object.keys(MARKET)) {
          const meta = MARKET[sym];
          const p = prev[sym] ?? meta.base;
          const vol = meta.base * 0.00045;
          let np = p + (Math.random() - 0.5) * vol;
          np += (meta.base - np) * 0.015;
          next[sym] = np;
        }
        return next;
      });
      setBotDrift((prev) => {
        const next: Record<number, number> = {};
        for (const b of bots) {
          if (b.status === 'running') next[b.id] = (prev[b.id] || 0) + (Math.random() - 0.5) * 2;
        }
        return next;
      });
    }, 2000);
    return () => window.clearInterval(id);
  }, [bots]);

  // In bridge mode, pull real broker quotes from the local Python/MetaTrader 5 bridge.
  const marketAccountLogin = useMemo(() => {
    const selected = active === 'all' ? null : accounts.find((account) => account.login === active && account.status === 'connected');
    return selected?.login ?? accounts.find((account) => account.status === 'connected')?.login;
  }, [accounts, active]);

  useEffect(() => {
    if (isSimulation || !marketAccountLogin) {
      if (!isSimulation) setQuotes({});
      return;
    }
    let cancelled = false;
    let inFlight = false;
    const load = async () => {
      if (inFlight || document.hidden) return;
      inFlight = true;
      try {
        const supported = new Set(mt5Symbols.map((item) => item.symbol));
        const requested = SYMBOL_LIST.filter((symbol) => !supported.size || supported.has(symbol));
        const rows = await mt5MarketService.quotes(requested, marketAccountLogin);
        if (cancelled) return;
        const bySymbol: Record<string, Mt5Quote> = {};
        const prices: Record<string, number> = {};
        for (const q of rows) {
          bySymbol[q.symbol] = q;
          prices[q.symbol] = Number(q.bid || q.last || q.ask || 0);
        }
        setQuotes(bySymbol);
        setMarket((prev) => ({ ...prev, ...prices }));
      } catch { /* bridge status/refresh handles connection errors */ }
      finally { inFlight = false; }
    };
    load();
    const id = window.setInterval(load, 3000);
    return () => { cancelled = true; window.clearInterval(id); };
  }, [marketAccountLogin, mt5Symbols]);

  useEffect(() => {
    if (isSimulation || !marketAccountLogin) {
      if (!isSimulation) setMt5Symbols([]);
      return;
    }
    let cancelled = false;
    mt5MarketService.symbols(marketAccountLogin).then((rows) => { if (!cancelled) setMt5Symbols(rows); }).catch(() => {});
    return () => { cancelled = true; };
  }, [marketAccountLogin]);

  const liveQuote = useCallback((symbol: string) => quotes[symbol] || null, [quotes]);
  const livePrice = useCallback((symbol: string) => {
    const q = quotes[symbol];
    return Number(q?.bid || q?.last || q?.ask || market[symbol] || MARKET[symbol]?.base || 0);
  }, [quotes, market]);
  const liveProfit = useCallback(
    (p: Mt5Position) => isSimulation
      ? calcProfit(p.type, p.symbol, Number(p.open_price), livePrice(p.symbol) || Number(p.current_price), Number(p.volume))
      : Number(p.profit || 0),
    [livePrice]
  );
  const botLiveToday = useCallback(
    (b: Mt5Bot) => isSimulation && b.status === 'running' ? Number(b.profit_today || 0) + (botDrift[b.id] || 0) : Number(b.profit_today || 0),
    [botDrift]
  );

  const setActive = useCallback(async (sel: ActiveSel) => {
    setActiveState(sel);
    workspaceService.set('active_account', sel);
    if (sel === 'all') return;
    const acc = accounts.find((a) => a.login === sel);
    if (!acc) return;
    try { await mt5AccountService.action(acc.id, 'set_active'); } catch { /* local-first */ }
  }, [accounts]);

  const setPrefs = useCallback((p: Partial<{ pollMs: number; confirmDanger: boolean; restoreWorkspace: boolean; reconnectOnStartup: boolean }>) => {
    setPrefsState((prev) => {
      const next = { ...prev, ...p };
      try { localStorage.setItem('koolkid_mt5_prefs', JSON.stringify(next)); } catch { /* ignore */ }
      return next;
    });
  }, []);

  const scopeAccounts = useMemo(() => active === 'all' ? accounts : accounts.filter((a) => a.login === active), [accounts, active]);
  const activeAccount = useMemo(() => active === 'all' ? null : accounts.find((a) => a.login === active) || null, [accounts, active]);
  const scopePositions = useMemo(() => active === 'all' ? positions : positions.filter((p) => p.account_login === active), [positions, active]);
  const scopeBots = useMemo(() => active === 'all' ? bots : bots.filter((b) => b.account_login === active), [bots, active]);

  const derived = useMemo(() => {
    // For real MT5 accounts, use the terminal's own account_info values instead of
    // reconstructing equity from balance + positions. This keeps the header identical
    // to the broker terminal (including credit/commission effects).
    const balance = scopeAccounts.reduce((sum, a) => sum + Number(a.balance || 0), 0);
    const floating = isSimulation
      ? scopePositions.reduce((sum, p) => sum + liveProfit(p), 0)
      : scopeAccounts.reduce((sum, a) => sum + Number(a.floating_pl || 0), 0);
    const equity = isSimulation
      ? balance + floating
      : scopeAccounts.reduce((sum, a) => sum + Number(a.equity || 0), 0);
    const margin = scopeAccounts.reduce((sum, a) => sum + Number(a.margin || 0), 0);
    const terminalToday = Number(stats?.kpis.today_pl ?? NaN);
    const realized = Number(stats?.kpis.realized_today ?? 0);
    const todayPl = !isSimulation && Number.isFinite(terminalToday) ? terminalToday : realized + floating;
    return {
      balance, floating, equity, margin, todayPl,
      runningBots: scopeBots.filter((b) => b.status === 'running').length,
    };
  }, [scopeAccounts, scopePositions, liveProfit, stats, scopeBots]);

  const accountName = useCallback((login: number | null | undefined) => {
    if (!login) return 'Unassigned';
    const a = accounts.find((x) => x.login === login);
    return a ? a.nickname : `#${login}`;
  }, [accounts]);

  const value: HubCtx = {
    accounts, bots, positions, stats, bridge, loading, bridgeStarting, refreshing, error,
    market, quotes, mt5Symbols, botDrift, active, setActive, activeAccount,
    scopeAccounts, scopePositions, scopeBots, derived,
    livePrice, liveQuote, liveProfit, botLiveToday,
    refresh, refreshPositions, accountName,
    prefs, setPrefs, toasts, pushToast, dismissToast,
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useHub(): HubCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useHub must be used within HubProvider');
  return ctx;
}
