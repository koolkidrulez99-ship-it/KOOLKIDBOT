import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { isSimulation } from '../config/runtime';
import { MARKET, SYMBOL_LIST, calcProfit } from '../lib/market';
import { aiControlService } from '../services/aiControlService';
import { mt5AccountService } from '../services/mt5AccountService';
import { mt5BotService } from '../services/mt5BotService';
import { mt5BridgeService } from '../services/mt5BridgeService';
import { mt5HistoryService } from '../services/mt5HistoryService';
import { hubPreferencesService } from '../services/hubPreferencesService';
import { mt5MarketService } from '../services/mt5MarketService';
import { mt5MultiAccountService } from '../services/mt5MultiAccountService';
import { mt5PositionService } from '../services/mt5PositionService';
import { DEFAULT_NOTIFICATION_PREFS, showBrowserNotification } from '../services/notificationService';
import type { NotificationPrefs } from '../services/notificationService';
import type { BridgeInfo, Mt5Account, Mt5Bot, Mt5Position, Mt5Quote, Mt5Stats, Mt5SymbolInfo } from '../types';
import { workspaceService } from '../services/workspaceService';

export type ActiveSel = number | 'all';

export type MarketBrokerFilter = 'all' | 'current' | 'deriv' | 'weltrade' | 'favorites' | 'custom';
export type MarketCategoryFilter = 'all' | 'synthetic' | 'forex' | 'metals' | 'indices' | 'crypto' | 'stocks' | 'energies' | 'weltrade_syntx' | 'fxvol' | 'sfxvol' | 'painx' | 'gainx' | 'flipx' | 'switchx' | 'breakx' | 'trendx' | 'progression' | 'maxx' | 'custom';

export interface HubPreferences {
  pollMs: number;
  confirmDanger: boolean;
  restoreWorkspace: boolean;
  reconnectOnStartup: boolean;
  notifications: NotificationPrefs;
  marketBrokerFilter: MarketBrokerFilter;
  marketCategoryFilter: MarketCategoryFilter;
  customBrokerFamilies: Array<'deriv' | 'weltrade' | 'other'>;
  customMarketGroups: Array<'synthetic' | 'forex' | 'metals' | 'indices' | 'crypto' | 'stocks' | 'energies' | 'weltrade_syntx'>;
  marketFavorites: Record<string, string[]>;
}

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
  prefs: HubPreferences;
  setPrefs: (p: Partial<HubPreferences>) => void;
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
  const [serverPrefsLoaded, setServerPrefsLoaded] = useState(isSimulation);

  const [prefs, setPrefsState] = useState<HubPreferences>(() => {
    const defaults: HubPreferences = {
      pollMs: isSimulation ? 15000 : 5000,
      confirmDanger: true,
      restoreWorkspace: true,
      reconnectOnStartup: true,
      notifications: DEFAULT_NOTIFICATION_PREFS,
      marketBrokerFilter: 'all',
      marketCategoryFilter: 'all',
      customBrokerFamilies: ['deriv', 'weltrade', 'other'],
      customMarketGroups: ['synthetic', 'forex', 'metals', 'indices', 'crypto', 'stocks', 'energies', 'weltrade_syntx'],
      marketFavorites: {},
    };
    try {
      const raw = localStorage.getItem('koolkid_mt5_prefs');
      if (raw) {
        const saved = JSON.parse(raw) as Partial<HubPreferences>;
        return { ...defaults, ...saved, notifications: { ...DEFAULT_NOTIFICATION_PREFS, ...(saved.notifications || {}) } };
      }
    } catch { /* ignore */ }
    return defaults;
  });

  const [market, setMarket] = useState<Record<string, number>>(() => {
    const result: Record<string, number> = {};
    for (const s of Object.keys(MARKET)) result[s] = MARKET[s].base;
    return result;
  });
  const [quotes, setQuotes] = useState<Record<string, Mt5Quote>>({});
  const [mt5Symbols, setMt5Symbols] = useState<Mt5SymbolInfo[]>([]);
  const [botDrift, setBotDrift] = useState<Record<number, number>>({});
  const notificationBaselineRef = useRef(false);
  const previousAccountsRef = useRef<Map<number, string>>(new Map());
  const previousPositionsRef = useRef<Map<string, Mt5Position>>(new Map());
  const previousBotsRef = useRef<Map<number, string>>(new Map());
  const previousBridgeRef = useRef<{ status?: string; trading?: boolean; ea?: string }>({});
  const copyNotificationRef = useRef<{ ready: boolean; status?: string; pending?: number; activity?: string }>({ ready: false });
  const aiNotificationRef = useRef<{ ready: boolean; autoEvent?: string; selectEvent?: string }>({ ready: false });

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

  useEffect(() => {
    if (isSimulation) return;
    let cancelled = false;
    hubPreferencesService.get()
      .then((saved) => {
        if (cancelled) return;
        setPrefsState((prev) => {
          const next: HubPreferences = {
            ...prev,
            ...saved,
            notifications: { ...DEFAULT_NOTIFICATION_PREFS, ...(prev.notifications || {}), ...(saved.notifications || {}) },
            customBrokerFamilies: saved.customBrokerFamilies?.length ? saved.customBrokerFamilies : prev.customBrokerFamilies,
            customMarketGroups: saved.customMarketGroups?.length ? saved.customMarketGroups : prev.customMarketGroups,
          };
          try { localStorage.setItem('koolkid_mt5_prefs', JSON.stringify(next)); } catch { /* ignore */ }
          return next;
        });
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setServerPrefsLoaded(true); });
    return () => { cancelled = true; };
  }, []);

  const didApplyStartupReconnect = useRef(false);
  useEffect(() => {
    if (!serverPrefsLoaded || loading || didApplyStartupReconnect.current || !accounts.length) return;
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
  }, [serverPrefsLoaded, loading, prefs.reconnectOnStartup, refresh]);

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

  useEffect(() => {
    if (loading) return;
    const accountMap = new Map(accounts.map((account) => [account.login, account.status]));
    const positionMap = new Map(positions.map((position) => [`${position.account_login}:${position.ticket}`, position]));
    const botMap = new Map(bots.map((bot) => [bot.id, bot.status]));
    const bridgeState = {
      status: bridge?.status,
      trading: bridge?.trading_enabled,
      ea: bridge?.ea_worker?.status,
    };

    if (!notificationBaselineRef.current) {
      previousAccountsRef.current = accountMap;
      previousPositionsRef.current = positionMap;
      previousBotsRef.current = botMap;
      previousBridgeRef.current = bridgeState;
      notificationBaselineRef.current = true;
      return;
    }

    const n = prefs.notifications;
    if (n.enabled) {
      if (n.accountStatus) {
        for (const account of accounts) {
          const before = previousAccountsRef.current.get(account.login);
          if (before && before !== account.status) {
            const title = account.status === 'connected' ? 'MT5 account connected' : 'MT5 account disconnected';
            void showBrowserNotification(title, `${account.nickname} (#${account.login}) is now ${account.status}.`, `account-${account.login}`);
          }
        }
      }

      if (n.tradeOpened) {
        for (const [key, position] of positionMap) {
          if (!previousPositionsRef.current.has(key)) {
            void showBrowserNotification(
              'Trade opened',
              `${position.type.toUpperCase()} ${position.symbol} · ${position.volume} lot · #${position.ticket}`,
              `trade-open-${key}`,
            );
          }
        }
      }

      if (n.tradeClosed) {
        const closed = [...previousPositionsRef.current.entries()].filter(([key]) => !positionMap.has(key));
        if (closed.length) {
          void mt5HistoryService.list().then((rows) => {
            for (const [key, position] of closed) {
              const row = rows.find((item) => item.ticket === position.ticket && item.account_login === position.account_login);
              const net = row ? Number(row.net_pl ?? Number(row.profit || 0) + Number(row.swap || 0) + Number(row.commission || 0)) : null;
              const result = net == null ? 'Position closed' : `${net >= 0 ? 'Profit' : 'Loss'} ${net >= 0 ? '+' : ''}${net.toFixed(2)}`;
              void showBrowserNotification('Trade closed', `${position.symbol} #${position.ticket} · ${result}`, `trade-close-${key}`);
            }
          }).catch(() => {
            for (const [key, position] of closed) {
              void showBrowserNotification('Trade closed', `${position.symbol} #${position.ticket} was closed.`, `trade-close-${key}`);
            }
          });
        }
      }

      if (n.botStatus) {
        for (const bot of bots) {
          const before = previousBotsRef.current.get(bot.id);
          if (before && before !== bot.status) {
            const isProblem = bot.status === 'error' || bot.status === 'worker_offline';
            void showBrowserNotification(
              isProblem ? 'Bot/EA problem' : 'Bot/EA status changed',
              `${bot.name} is now ${bot.status.replace('_', ' ')}.`,
              `bot-${bot.id}`,
            );
          }
        }
      }

      if (n.riskAlerts) {
        if (previousBridgeRef.current.status && previousBridgeRef.current.status !== bridgeState.status && bridgeState.status !== 'online') {
          void showBrowserNotification('MT5 bridge alert', `Bridge status changed to ${bridgeState.status || 'unknown'}.`, 'bridge-status');
        }
        if (previousBridgeRef.current.trading === true && bridgeState.trading === false) {
          void showBrowserNotification('Trading disabled', 'MT5 trading is no longer enabled for the active bridge.', 'trading-disabled');
        }
        if (previousBridgeRef.current.ea === 'online' && bridgeState.ea && bridgeState.ea !== 'online') {
          void showBrowserNotification('EA worker alert', `EA worker status changed to ${bridgeState.ea}.`, 'ea-worker');
        }
      }
    }

    previousAccountsRef.current = accountMap;
    previousPositionsRef.current = positionMap;
    previousBotsRef.current = botMap;
    previousBridgeRef.current = bridgeState;
  }, [accounts, bots, bridge, loading, positions, prefs.notifications]);

  useEffect(() => {
    if (!prefs.notifications.enabled || !prefs.notifications.copyTrader) {
      copyNotificationRef.current = { ready: false };
      return;
    }
    let cancelled = false;
    const load = async () => {
      try {
        const snapshot = await mt5MultiAccountService.copyStatus();
        if (cancelled) return;
        const status = String(snapshot.status || 'stopped');
        const pending = Number(snapshot.pending_count || 0);
        const activity = Array.isArray(snapshot.activity) ? snapshot.activity[0] as Record<string, unknown> | undefined : undefined;
        const activityKey = activity ? `${String(activity.time || '')}:${String(activity.event || '')}` : '';
        const previous = copyNotificationRef.current;
        if (previous.ready) {
          if (previous.status !== status) {
            void showBrowserNotification('Copy Trader status', `Copy Trader is now ${status}.`, 'copy-status');
          }
          if (pending > Number(previous.pending || 0)) {
            void showBrowserNotification('Copy approval waiting', `${pending} copied trade${pending === 1 ? '' : 's'} waiting for approval.`, 'copy-pending');
          }
          if (activityKey && activityKey !== previous.activity && /error|fail|reject/i.test(String(activity?.event || ''))) {
            void showBrowserNotification('Copy Trader alert', String(activity?.error || activity?.event || 'Copy Trader reported an error.'), 'copy-error');
          }
        }
        copyNotificationRef.current = { ready: true, status, pending, activity: activityKey };
      } catch { /* copy worker availability is already surfaced in its page */ }
    };
    void load();
    const id = window.setInterval(load, Math.max(3000, prefs.pollMs));
    return () => { cancelled = true; window.clearInterval(id); };
  }, [prefs.notifications.copyTrader, prefs.notifications.enabled, prefs.pollMs]);

  useEffect(() => {
    if (isSimulation || !prefs.notifications.enabled || !prefs.notifications.aiAlerts) {
      aiNotificationRef.current = { ready: false };
      return;
    }
    let cancelled = false;
    const eventKey = (row: Record<string, unknown> | undefined) => row ? `${String(row.time || '')}:${String(row.event || '')}` : '';
    const interesting = (rows: Array<Record<string, unknown>>) =>
      rows.find((row) => /execut|error|signal|start|stop/i.test(String(row.event || '')));
    const load = async () => {
      try {
        const [auto, select] = await Promise.all([aiControlService.autoStatus(), aiControlService.autoSelectStatus()]);
        if (cancelled) return;
        const autoEvent = interesting(auto.events as unknown as Array<Record<string, unknown>>);
        const selectEvent = interesting(select.events);
        const autoKey = eventKey(autoEvent);
        const selectKey = eventKey(selectEvent);
        const previous = aiNotificationRef.current;
        if (previous.ready) {
          if (autoKey && autoKey !== previous.autoEvent) {
            void showBrowserNotification('AI trading alert', String(autoEvent?.event || 'Human Apostle AI update'), 'ai-auto');
          }
          if (selectKey && selectKey !== previous.selectEvent) {
            const label = String(selectEvent?.event || 'AI Intelligence update').replaceAll('_', ' ');
            void showBrowserNotification('AI Intelligence alert', label, 'ai-select');
          }
        }
        aiNotificationRef.current = { ready: true, autoEvent: autoKey, selectEvent: selectKey };
      } catch { /* AI pages already surface API errors */ }
    };
    void load();
    const id = window.setInterval(load, Math.max(5000, prefs.pollMs));
    return () => { cancelled = true; window.clearInterval(id); };
  }, [prefs.notifications.aiAlerts, prefs.notifications.enabled, prefs.pollMs]);

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

  const setPrefs = useCallback((p: Partial<HubPreferences>) => {
    setPrefsState((prev) => {
      const next: HubPreferences = {
        ...prev,
        ...p,
        notifications: p.notifications ? { ...prev.notifications, ...p.notifications } : prev.notifications,
      };
      try { localStorage.setItem('koolkid_mt5_prefs', JSON.stringify(next)); } catch { /* ignore */ }
      if (!isSimulation) void hubPreferencesService.save(next).catch(() => {});
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
