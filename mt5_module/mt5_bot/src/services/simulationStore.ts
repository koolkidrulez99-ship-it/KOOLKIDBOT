import { BOT_CATALOG, LEGACY_PLACEHOLDERS } from '../data/botCatalog';
import { MARKET, calcProfit, marginFor } from '../lib/market';
import type {
  AiInsight,
  AiSettings,
  BotPerformance,
  BridgeInfo,
  DerivAccount,
  Mt5Account,
  Mt5Bot,
  Mt5HistoryRow,
  Mt5Position,
  Mt5Stats,
  RiskSettings,
  CopyRelationship,
  CopyEvent,
  CopyState,
} from '../types';

interface SimulationState {
  version: number;
  accounts: Mt5Account[];
  bots: Mt5Bot[];
  positions: Mt5Position[];
  history: Mt5HistoryRow[];
  derivAccounts: DerivAccount[];
  insights: AiInsight[];
  aiSettings: AiSettings;
  risk: RiskSettings[];
  copyRelationships: CopyRelationship[];
  copyEvents: CopyEvent[];
}

const KEY = 'koolkid_mt5_hub_simulation_v3';
const STATE_VERSION = 3;

const now = () => new Date().toISOString();
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;
const money = (n: number) => Number(n.toFixed(2));
const delay = (ms = 90) => new Promise((resolve) => window.setTimeout(resolve, ms));

function defaultRisk(): RiskSettings[] {
  return [{
    id: 'global',
    scope: 'global',
    account_login: null,
    bot_id: null,
    max_daily_loss: 500,
    max_daily_profit: 1500,
    max_drawdown_pct: 10,
    max_lot_size: 5,
    max_open_positions: 10,
    max_trades_per_day: 100,
    max_risk_per_trade: 2,
    allowed_trading_hours: '00:00-23:59',
    allowed_symbols: Object.keys(MARKET),
    auto_stop: true,
  }];
}

function seed(): SimulationState {
  const account: Mt5Account = {
    id: 1,
    login: 900001,
    nickname: 'Deriv MT5 Demo',
    broker: 'Deriv',
    server: 'Simulation-Demo',
    balance: 10000,
    equity: 10000,
    margin: 0,
    free_margin: 10000,
    floating_pl: 0,
    leverage: 500,
    currency: 'USD',
    status: 'connected',
    is_active: true,
    account_type: 'demo',
    worker_id: 'sim-worker-01',
    terminal_id: 'sim-terminal-01',
    connection_status: 'simulation',
    last_heartbeat: now(),
    created_at: now(),
  };

  return {
    version: STATE_VERSION,
    accounts: [account],
    bots: clone(BOT_CATALOG),
    positions: [],
    history: [],
    derivAccounts: [],
    insights: [{
      id: 1,
      title: 'Simulation environment ready',
      body: 'No real MT5 terminal is connected. Account values, market ticks and trade actions in this build are simulated until a real bridge is configured.',
      category: 'market',
      sentiment: 'neutral',
      confidence: 100,
      account_login: null,
      bot_id: null,
      created_at: now(),
    }],
    aiSettings: { auto_trading: false, risk_guard: true, sentiment_filter: false, news_pause: true },
    risk: defaultRisk(),
    copyRelationships: [],
    copyEvents: [],
  };
}

function normalizeState(raw: Partial<SimulationState> | null): SimulationState {
  if (!raw || raw.version !== STATE_VERSION) return seed();
  const persistedBots = raw.bots || [];
  const botsByName = new Map(persistedBots.map((b) => [b.name, b]));
  const catalogNames = new Set(BOT_CATALOG.map((b) => b.name.toLowerCase()));
  const catalogBots = BOT_CATALOG.map((catalogBot) => ({ ...catalogBot, ...(botsByName.get(catalogBot.name) || {}) }));
  const customBots = persistedBots.filter((b) => !catalogNames.has(b.name.toLowerCase()) && !LEGACY_PLACEHOLDERS.has(b.name));
  const bots = [...catalogBots, ...customBots];
  return {
    version: STATE_VERSION,
    accounts: raw.accounts || [],
    bots,
    positions: raw.positions || [],
    history: raw.history || [],
    derivAccounts: raw.derivAccounts || [],
    insights: raw.insights || [],
    aiSettings: raw.aiSettings || { auto_trading: false, risk_guard: true, sentiment_filter: false, news_pause: true },
    risk: raw.risk?.length ? raw.risk : defaultRisk(),
    copyRelationships: raw.copyRelationships || [],
    copyEvents: raw.copyEvents || [],
  };
}

function load(): SimulationState {
  try {
    const parsed = JSON.parse(localStorage.getItem(KEY) || 'null') as Partial<SimulationState> | null;
    const state = normalizeState(parsed);
    save(state);
    return state;
  } catch {
    const state = seed();
    save(state);
    return state;
  }
}

function save(state: SimulationState) {
  try { localStorage.setItem(KEY, JSON.stringify(state)); } catch { /* storage unavailable */ }
}

function withState<T>(fn: (state: SimulationState) => T): T {
  const state = load();
  const out = fn(state);
  save(state);
  return out;
}

function nextId(rows: Array<{ id: number }>, start = 1): number {
  return Math.max(start - 1, ...rows.map((r) => Number(r.id) || 0)) + 1;
}

function currentBookPrice(symbol: string): number {
  const meta = MARKET[symbol];
  if (!meta) return 1;
  const spread = meta.base * 0.00055;
  return Number((meta.base + (Math.random() - 0.5) * spread).toFixed(meta.digits));
}

function refreshAccountAggregates(state: SimulationState, login: number) {
  const account = state.accounts.find((a) => a.login === login);
  if (!account) return;
  const positions = state.positions.filter((p) => p.account_login === login);
  const floating = positions.reduce((sum, p) => sum + Number(p.profit || 0), 0);
  const margin = positions.reduce((sum, p) => sum + marginFor(p.symbol, p.open_price, p.volume, account.leverage), 0);
  account.floating_pl = money(floating);
  account.margin = money(margin);
  account.equity = money(account.balance + floating);
  account.free_margin = money(account.equity - margin);
  account.last_heartbeat = now();
}

function recalcPositionSnapshots(state: SimulationState) {
  for (const p of state.positions) {
    const close = currentBookPrice(p.symbol);
    p.current_price = close;
    p.profit = money(calcProfit(p.type, p.symbol, p.open_price, close, p.volume));
  }
  for (const a of state.accounts) refreshAccountAggregates(state, a.login);
}

export async function simListAccounts(): Promise<Mt5Account[]> {
  await delay();
  return clone(withState((state) => {
    recalcPositionSnapshots(state);
    return state.accounts;
  }));
}

export async function simAddAccount(payload: Record<string, unknown>): Promise<Mt5Account> {
  await delay(180);
  return clone(withState((state) => {
    const login = Number(payload.login);
    if (!login || !/^[0-9]{4,12}$/.test(String(login))) throw new Error('A valid numeric MT5 login is required.');
    if (state.accounts.some((a) => a.login === login)) throw new Error('This MT5 login is already connected.');
    const nickname = String(payload.nickname || '').trim();
    const server = String(payload.server || '').trim();
    if (!nickname) throw new Error('Account nickname is required.');
    if (!server) throw new Error('Broker server is required.');
    const balance = Math.max(100, Number(payload.balance) || 10000);
    const id = nextId(state.accounts);
    const account: Mt5Account = {
      id,
      login,
      nickname,
      broker: String(payload.broker || 'MetaTrader 5'),
      server,
      balance,
      equity: balance,
      margin: 0,
      free_margin: balance,
      floating_pl: 0,
      leverage: Number(payload.leverage) || 500,
      currency: String(payload.currency || 'USD'),
      status: 'connected',
      is_active: state.accounts.length === 0,
      account_type: payload.account_type === 'live' ? 'live' : 'demo',
      worker_id: `sim-worker-${String(id).padStart(2, '0')}`,
      terminal_id: `sim-terminal-${String(id).padStart(2, '0')}`,
      connection_status: 'simulation',
      last_heartbeat: now(),
      created_at: now(),
    };
    state.accounts.push(account);
    return account;
  }));
}

export async function simTestAccount(_payload: Record<string, unknown>) {
  await delay(450);
  return { ok: true, mode: 'simulation' as const, message: 'Simulation validation passed. No broker or MT5 terminal was contacted.' };
}

export async function simAccountAction(id: number, action: string, extra: Record<string, unknown> = {}): Promise<Mt5Account> {
  await delay();
  return clone(withState((state) => {
    const account = state.accounts.find((a) => a.id === id);
    if (!account) throw new Error('Account not found.');
    if (action === 'set_active') {
      state.accounts.forEach((a) => { a.is_active = a.id === id; });
    } else if (action === 'toggle' || action === 'connect' || action === 'disconnect') {
      account.status = action === 'connect' ? 'connected' : action === 'disconnect' ? 'disconnected' : account.status === 'connected' ? 'disconnected' : 'connected';
      account.connection_status = account.status === 'connected' ? 'simulation' : 'offline';
    } else {
      if (extra.nickname !== undefined) account.nickname = String(extra.nickname);
      if (extra.leverage !== undefined) account.leverage = Number(extra.leverage) || account.leverage;
    }
    account.last_heartbeat = now();
    return account;
  }));
}

export async function simRemoveAccount(id: number): Promise<{ ok: true }> {
  await delay();
  withState((state) => {
    const account = state.accounts.find((a) => a.id === id);
    if (!account) throw new Error('Account not found.');
    state.positions = state.positions.filter((p) => p.account_login !== account.login);
    state.bots = state.bots.map((b) => b.account_login === account.login ? { ...b, account_login: null, status: 'stopped', started_at: null } : b);
    state.accounts = state.accounts.filter((a) => a.id !== id);
    if (!state.accounts.some((a) => a.is_active) && state.accounts[0]) state.accounts[0].is_active = true;
  });
  return { ok: true };
}

export async function simListBots(): Promise<Mt5Bot[]> {
  await delay();
  return clone(withState((state) => state.bots));
}

export async function simCreateBot(payload: Record<string, unknown>): Promise<Mt5Bot> {
  await delay();
  return clone(withState((state) => {
    const name = String(payload.name || '').trim();
    if (!name) throw new Error('Bot name is required.');
    if (state.bots.some((b) => b.name.toLowerCase() === name.toLowerCase())) throw new Error('A bot with this name already exists.');
    const bot: Mt5Bot = {
      id: nextId(state.bots, 1000),
      name,
      description: String(payload.description || 'Custom EA. No strategy claims are attached to this metadata entry.'),
      strategy: String(payload.strategy || 'Custom EA'),
      symbol: String(payload.symbol || 'EURUSD'),
      timeframe: String(payload.timeframe || 'M15'),
      recommended_timeframe: String(payload.timeframe || 'M15'),
      account_login: null,
      status: 'stopped',
      lot_size: 0.01,
      win_rate: 0,
      total_trades: 0,
      net_profit: 0,
      profit_today: 0,
      version: String(payload.version || '1.0.0'),
      started_at: null,
      ea_filename: payload.ea_filename ? String(payload.ea_filename) : `${name.replace(/\s+/g, '_')}.ex5`,
      preset_filename: payload.preset_filename ? String(payload.preset_filename) : null,
      file_status: 'metadata-only',
      upload_date: payload.ea_filename ? now() : null,
      dll_required: Boolean(payload.dll_required),
      settings: {
        risk_percent: 1,
        max_spread: 3.5,
        trailing_stop: true,
        magic_number: Math.floor(100000 + Math.random() * 899999),
        max_daily_loss: 250,
        slippage: 1.5,
        max_open_positions: 3,
        trading_session: 'All Sessions',
      },
    };
    state.bots.push(bot);
    return bot;
  }));
}

export async function simDeleteBot(id: number) {
  await delay();
  if (id >= 1000 && id < 1020) throw new Error('Built-in KOOLKID bot catalog entries cannot be deleted. Add the real EA file later or reset its metadata.');
  withState((state) => { state.bots = state.bots.filter((b) => b.id !== id); });
  return { ok: true };
}

export async function simBotControl(id: number, action: string, payload: Record<string, unknown> = {}): Promise<Mt5Bot> {
  await delay(120);
  return clone(withState((state) => {
    const bot = state.bots.find((b) => b.id === id);
    if (!bot) throw new Error('Bot not found.');
    if (action === 'launch') {
      const accountLogin = Number(payload.account_login);
      const account = state.accounts.find((a) => a.login === accountLogin);
      if (!account) throw new Error('Select an MT5 account to launch the bot on.');
      if (account.status !== 'connected') throw new Error('Assigned account is disconnected.');
      bot.status = 'running';
      bot.started_at = now();
      bot.account_login = accountLogin;
      if (payload.symbol) bot.symbol = String(payload.symbol);
      if (payload.timeframe) bot.timeframe = String(payload.timeframe);
      if (payload.lot_size) bot.lot_size = Number(payload.lot_size) || bot.lot_size;
      if (payload.settings && typeof payload.settings === 'object') bot.settings = { ...bot.settings, ...(payload.settings as Partial<Mt5Bot['settings']>) };
    } else if (action === 'pause') {
      if (bot.status !== 'running') throw new Error('Only running bots can be paused.');
      bot.status = 'paused';
    } else if (action === 'resume') {
      if (bot.status !== 'paused') throw new Error('Only paused bots can be resumed.');
      bot.status = 'running';
      bot.started_at ||= now();
    } else if (action === 'stop') {
      bot.status = 'stopped';
      bot.started_at = null;
    } else {
      Object.assign(bot, payload);
    }
    return bot;
  }));
}

export async function simListPositions(): Promise<Mt5Position[]> {
  await delay();
  return clone(withState((state) => {
    recalcPositionSnapshots(state);
    return state.positions;
  }));
}

function tradingHourAllowed(windowText: string): boolean {
  const match = /^\s*(\d{2}):(\d{2})\s*-\s*(\d{2}):(\d{2})\s*$/.exec(windowText || '');
  if (!match) return true;
  const start = Number(match[1]) * 60 + Number(match[2]);
  const end = Number(match[3]) * 60 + Number(match[4]);
  const d = new Date();
  const cur = d.getHours() * 60 + d.getMinutes();
  return start <= end ? cur >= start && cur <= end : cur >= start || cur <= end;
}

function applicableRisk(state: SimulationState, accountLogin: number, source: string): RiskSettings[] {
  const bot = state.bots.find((b) => b.name === source);
  return state.risk.filter((r) =>
    r.scope === 'global' ||
    (r.scope === 'account' && r.account_login === accountLogin) ||
    (r.scope === 'bot' && bot && r.bot_id === bot.id)
  );
}

function enforceSimulationRisk(state: SimulationState, payload: {
  account_login: number; symbol: string; volume: number; source?: string;
}) {
  const source = payload.source || 'Manual';
  const rules = applicableRisk(state, Number(payload.account_login), source);
  const today = new Date().toISOString().slice(0, 10);
  for (const rule of rules) {
    if (!rule.auto_stop) continue;
    if (rule.allowed_symbols?.length && !rule.allowed_symbols.includes(payload.symbol)) {
      throw new Error(`Risk limit: ${payload.symbol} is not allowed for the ${rule.scope} risk scope.`);
    }
    if (!tradingHourAllowed(rule.allowed_trading_hours)) {
      throw new Error(`Risk limit: trading is outside ${rule.allowed_trading_hours} for the ${rule.scope} risk scope.`);
    }
    if (rule.max_lot_size > 0 && payload.volume > rule.max_lot_size) {
      throw new Error(`Risk limit: ${payload.volume.toFixed(2)} lots exceeds the ${rule.max_lot_size.toFixed(2)} lot maximum.`);
    }
    const scopePositions = state.positions.filter((p) => {
      if (rule.scope === 'account') return p.account_login === rule.account_login;
      if (rule.scope === 'bot') return p.source === source;
      return true;
    });
    if (rule.max_open_positions > 0 && scopePositions.length >= rule.max_open_positions) {
      throw new Error(`Risk limit: maximum open positions (${rule.max_open_positions}) reached for the ${rule.scope} scope.`);
    }
    const scopeHistory = state.history.filter((h) => {
      if (!h.close_time.startsWith(today)) return false;
      if (rule.scope === 'account') return h.account_login === rule.account_login;
      if (rule.scope === 'bot') return h.source === source;
      return true;
    });
    if (rule.max_trades_per_day > 0 && scopeHistory.length >= rule.max_trades_per_day) {
      throw new Error(`Risk limit: maximum trades per day (${rule.max_trades_per_day}) reached for the ${rule.scope} scope.`);
    }
    const realized = scopeHistory.reduce((sum, h) => sum + Number(h.profit || 0), 0);
    if (rule.max_daily_loss > 0 && realized <= -Math.abs(rule.max_daily_loss)) {
      throw new Error(`Risk limit: daily loss limit of $${rule.max_daily_loss.toFixed(2)} has been reached.`);
    }
    if (rule.max_daily_profit > 0 && realized >= Math.abs(rule.max_daily_profit)) {
      throw new Error(`Risk limit: daily profit stop of $${rule.max_daily_profit.toFixed(2)} has been reached.`);
    }
  }
}

function addCopyEvent(state: SimulationState, event: Omit<CopyEvent, 'id' | 'time'>) {
  state.copyEvents.unshift({ id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, time: now(), ...event });
  state.copyEvents = state.copyEvents.slice(0, 500);
}

function copyVolume(rel: CopyRelationship, masterVolume: number, master: Mt5Account, follower: Mt5Account) {
  let volume = masterVolume;
  if (rel.copy_mode === 'fixed_lot') volume = rel.fixed_lot;
  if (rel.copy_mode === 'multiplier') volume = masterVolume * rel.multiplier;
  if (rel.copy_mode === 'balance_ratio' || rel.copy_mode === 'risk_ratio') {
    volume = masterVolume * (Math.max(1, follower.equity || follower.balance) / Math.max(1, master.equity || master.balance));
    if (rel.copy_mode === 'risk_ratio') volume *= rel.multiplier || 1;
  }
  volume = Math.min(Math.max(0.01, volume), Math.max(0.01, rel.max_lot || volume));
  return Number((Math.round(volume * 100) / 100).toFixed(2));
}

function makePosition(state: SimulationState, payload: {
  account_login: number; symbol: string; type: 'buy' | 'sell'; volume: number; sl?: number | null; tp?: number | null; source?: string;
}) {
  const account = state.accounts.find((a) => a.login === Number(payload.account_login));
  if (!account) throw new Error('MT5 account not found.');
  if (account.status !== 'connected') throw new Error('Account is disconnected.');
  if (!MARKET[payload.symbol]) throw new Error('Unsupported symbol.');
  const volume = Number(payload.volume);
  if (!volume || volume < 0.01 || volume > 50) throw new Error('Volume must be between 0.01 and 50 lots.');
  enforceSimulationRisk(state, { account_login: account.login, symbol: payload.symbol, volume, source: payload.source });
  const open = currentBookPrice(payload.symbol);
  const margin = marginFor(payload.symbol, open, volume, account.leverage);
  if (account.free_margin < margin) throw new Error('Insufficient simulated free margin.');
  const position: Mt5Position = {
    id: nextId(state.positions),
    ticket: Math.floor(10000000 + Math.random() * 89999999),
    account_login: account.login,
    symbol: payload.symbol,
    type: payload.type,
    volume,
    open_price: open,
    current_price: open,
    sl: payload.sl ? Number(payload.sl) : null,
    tp: payload.tp ? Number(payload.tp) : null,
    profit: 0,
    swap: 0,
    commission: 0,
    open_time: now(),
    source: payload.source || 'Manual',
    magic: null,
  };
  state.positions.unshift(position);
  refreshAccountAggregates(state, account.login);
  return position;
}

export async function simOpenTrade(payload: {
  account_login: number;
  symbol: string;
  type: 'buy' | 'sell';
  volume: number;
  sl?: number | null;
  tp?: number | null;
  source?: string;
}): Promise<Mt5Position> {
  await delay(180);
  return clone(withState((state) => {
    const masterPosition = makePosition(state, payload);
    if (!(payload.source || '').startsWith('COPY:')) {
      const masterAccount = state.accounts.find((a) => a.login === Number(payload.account_login));
      if (masterAccount) {
        for (const rel of state.copyRelationships.filter((r) => r.enabled && r.master_login === masterAccount.login && r.copy_new_trades)) {
          const follower = state.accounts.find((a) => a.login === rel.follower_login);
          if (!follower || follower.status !== 'connected') {
            rel.status = 'blocked'; rel.last_event = 'Follower unavailable';
            addCopyEvent(state, { relationship_id: rel.id, action: 'blocked', master_ticket: masterPosition.ticket, message: 'Follower account is not connected.' });
            continue;
          }
          const copyHistory = state.history.filter((h) => String(h.source).startsWith(`COPY:${rel.id}:`));
          const today = new Date().toISOString().slice(0, 10);
          const todayPl = copyHistory.filter((h) => h.close_time.startsWith(today)).reduce((a, h) => a + Number(h.net_pl ?? h.profit), 0);
          if (rel.max_daily_loss > 0 && todayPl <= -Math.abs(rel.max_daily_loss)) {
            rel.status = 'blocked'; rel.last_event = 'Copy daily loss limit reached';
            addCopyEvent(state, { relationship_id: rel.id, action: 'blocked', master_ticket: masterPosition.ticket, message: `Copy daily loss limit of $${rel.max_daily_loss.toFixed(2)} reached.` });
            continue;
          }
          const openCopies = state.positions.filter((p) => p.account_login === follower.login && String(p.source).startsWith(`COPY:${rel.id}:`)).length;
          if (rel.max_open_positions > 0 && openCopies >= rel.max_open_positions) {
            rel.status = 'blocked'; rel.last_event = 'Max copied positions reached';
            addCopyEvent(state, { relationship_id: rel.id, action: 'blocked', master_ticket: masterPosition.ticket, message: `Maximum copied positions (${rel.max_open_positions}) reached.` });
            continue;
          }
          const volume = copyVolume(rel, masterPosition.volume, masterAccount, follower);
          try {
            const copied = makePosition(state, { ...payload, account_login: follower.login, volume, source: `COPY:${rel.id}:${masterPosition.ticket}` });
            rel.status = 'copying'; rel.last_event = `${payload.type.toUpperCase()} ${payload.symbol} ${volume.toFixed(2)}`;
            addCopyEvent(state, { relationship_id: rel.id, action: 'open', symbol: payload.symbol, side: payload.type, master_ticket: masterPosition.ticket, follower_ticket: copied.ticket, master_volume: masterPosition.volume, follower_volume: volume, message: `Copied ${payload.type.toUpperCase()} ${payload.symbol} to #${follower.login}.` });
          } catch (e) {
            rel.status = 'blocked'; rel.last_event = e instanceof Error ? e.message : 'Follower risk check blocked trade';
            addCopyEvent(state, { relationship_id: rel.id, action: 'blocked', symbol: payload.symbol, side: payload.type, master_ticket: masterPosition.ticket, master_volume: masterPosition.volume, follower_volume: volume, message: rel.last_event || 'Copy blocked.' });
          }
        }
      }
    }
    return masterPosition;
  }));
}

function closeOne(state: SimulationState, id: number): { profit: number; row: Mt5HistoryRow } {
  const pos = state.positions.find((p) => p.id === id);
  if (!pos) throw new Error('Position not found (already closed?).');
  const close = currentBookPrice(pos.symbol);
  const profit = money(calcProfit(pos.type, pos.symbol, pos.open_price, close, pos.volume) + Number(pos.swap || 0) + Number(pos.commission || 0));
  const row: Mt5HistoryRow = {
    id: nextId(state.history),
    ticket: pos.ticket,
    account_login: pos.account_login,
    symbol: pos.symbol,
    type: pos.type,
    volume: pos.volume,
    open_price: pos.open_price,
    close_price: close,
    profit,
    swap: pos.swap || 0,
    commission: pos.commission || 0,
    open_time: pos.open_time,
    close_time: now(),
    source: pos.source || 'Manual',
    net_pl: profit,
  };
  state.history.unshift(row);
  state.positions = state.positions.filter((p) => p.id !== id);
  const account = state.accounts.find((a) => a.login === pos.account_login);
  if (account) account.balance = money(account.balance + profit);
  refreshAccountAggregates(state, pos.account_login);
  const bot = state.bots.find((b) => b.name === pos.source);
  if (bot) {
    bot.total_trades += 1;
    bot.net_profit = money(bot.net_profit + profit);
    bot.profit_today = money(bot.profit_today + profit);
    const botRows = state.history.filter((h) => h.source === bot.name);
    bot.win_rate = botRows.length ? Number(((botRows.filter((h) => h.profit > 0).length / botRows.length) * 100).toFixed(1)) : 0;
  }

  // If this is a master trade, close its mapped follower tickets when the copy rule says to mirror closes.
  if (!String(pos.source || '').startsWith('COPY:')) {
    for (const rel of state.copyRelationships.filter((r) => r.enabled && r.master_login === pos.account_login && r.copy_closes)) {
      const prefix = `COPY:${rel.id}:${pos.ticket}`;
      const followers = state.positions.filter((p) => String(p.source) === prefix).map((p) => p.id);
      for (const followerId of followers) {
        try {
          const copiedResult = closeOne(state, followerId);
          addCopyEvent(state, { relationship_id: rel.id, action: 'close', symbol: pos.symbol, side: pos.type, master_ticket: pos.ticket, profit: copiedResult.profit, message: `Follower position closed with ${copiedResult.profit >= 0 ? 'profit' : 'loss'} $${Math.abs(copiedResult.profit).toFixed(2)}.` });
          rel.status = 'armed'; rel.last_event = 'Master close mirrored';
        } catch { /* follower may already be closed */ }
      }
    }
  }
  return { profit, row };
}

export async function simClosePosition(id: number) {
  await delay(150);
  return clone(withState((state) => {
    const result = closeOne(state, id);
    return { ok: true as const, profit: result.profit, closed: result.row };
  }));
}

export async function simStopAllBots() {
  await delay(150);
  return withState((state) => {
    let stopped = 0;
    state.bots.forEach((b) => {
      if (b.status === 'running' || b.status === 'paused' || b.status === 'connecting') {
        b.status = 'stopped';
        b.started_at = null;
        stopped += 1;
      }
    });
    return { ok: true as const, stopped };
  });
}

export async function simCloseAllPositions() {
  await delay(180);
  return withState((state) => {
    const initialCount = state.positions.length;
    let realized = 0;
    // Closing a master can also close mapped follower positions. Always take the
    // next position that still exists so a mirrored close is never closed twice.
    while (state.positions.length) {
      const nextId = state.positions[0].id;
      realized += closeOne(state, nextId).profit;
    }
    return { ok: true as const, closed: initialCount, realized: money(realized) };
  });
}

export async function simStopAndCloseAll() {
  const bots = await simStopAllBots();
  const positions = await simCloseAllPositions();
  return { ok: true as const, stopped: bots.stopped, closed: positions.closed, realized: positions.realized };
}

export async function simHistory(): Promise<Mt5HistoryRow[]> {
  await delay();
  return clone(withState((state) => state.history));
}

export async function simStats(): Promise<Mt5Stats> {
  await delay();
  return clone(withState((state) => {
    recalcPositionSnapshots(state);
    const totalBalance = state.accounts.reduce((s, a) => s + a.balance, 0);
    const floating = state.accounts.reduce((s, a) => s + a.floating_pl, 0);
    const totalEquity = money(totalBalance + floating);
    const margin = money(state.accounts.reduce((s, a) => s + a.margin, 0));
    const latestDay = state.history[0]?.close_time.slice(0, 10) || null;
    const todayRows = latestDay ? state.history.filter((h) => h.close_time.startsWith(latestDay)) : [];
    const realizedToday = money(todayRows.reduce((s, h) => s + h.profit, 0));
    const recent = state.history.slice(0, 300);
    const wins = recent.filter((h) => h.profit > 0).length;
    const winRate = recent.length ? Number(((wins / recent.length) * 100).toFixed(1)) : 0;
    const profit30 = money(recent.reduce((s, h) => s + h.profit, 0));
    const today = new Date();
    const dates = Array.from({ length: 14 }, (_, idx) => new Date(today.getTime() - (13 - idx) * 86400000).toISOString().slice(0, 10));
    const dailyMap = new Map<string, number>();
    for (const h of state.history) dailyMap.set(h.close_time.slice(0, 10), money((dailyMap.get(h.close_time.slice(0, 10)) || 0) + h.profit));
    const rangeRealized = dates.reduce((sum, date) => sum + (dailyMap.get(date) || 0), 0);
    let curveEquity = money(totalEquity - floating - rangeRealized);
    const equity = dates.map((date, idx) => {
      const dailyPl = dailyMap.get(date) || 0;
      curveEquity = money(curveEquity + dailyPl);
      const endEquity = idx === dates.length - 1 ? totalEquity : curveEquity;
      return { date, equity: endEquity, daily_pl: dailyPl };
    });
    const peakEquity = equity.reduce((peak, point) => Math.max(peak, point.equity), equity[0]?.equity || totalEquity);
    const drawdownPct = peakEquity > 0 ? Number((((peakEquity - totalEquity) / peakEquity) * 100).toFixed(2)) : 0;
    const symbolPnlMap: Record<string, { symbol: string; pl: number; trades: number }> = {};
    for (const h of recent) {
      const row = symbolPnlMap[h.symbol] ||= { symbol: h.symbol, pl: 0, trades: 0 };
      row.pl = money(row.pl + h.profit);
      row.trades += 1;
    }
    const exposureMap: Record<string, { symbol: string; volume: number; floating: number; count: number }> = {};
    for (const p of state.positions) {
      const row = exposureMap[p.symbol] ||= { symbol: p.symbol, volume: 0, floating: 0, count: 0 };
      row.volume = money(row.volume + p.volume);
      row.floating = money(row.floating + p.profit);
      row.count += 1;
    }
    return {
      kpis: {
        total_balance: money(totalBalance),
        total_equity: totalEquity,
        floating: money(floating),
        margin,
        free_margin: money(totalEquity - margin),
        margin_level: margin > 0 ? Number(((totalEquity / margin) * 100).toFixed(1)) : null,
        realized_today: realizedToday,
        today_pl: money(realizedToday + floating),
        trades_today: todayRows.length,
        latest_day: latestDay,
        connected_accounts: state.accounts.filter((a) => a.status === 'connected').length,
        total_accounts: state.accounts.length,
        running_bots: state.bots.filter((b) => b.status === 'running').length,
        paused_bots: state.bots.filter((b) => b.status === 'paused').length,
        total_bots: state.bots.length,
        open_positions: state.positions.length,
        win_rate_30d: winRate,
        trades_30d: recent.length,
        profit_30d: profit30,
        drawdown_pct: drawdownPct,
        peak_equity: money(peakEquity),
      },
      equity,
      daily: equity.map((e) => ({ date: e.date, pl: e.daily_pl })),
      bots: state.bots,
      symbolPnl: Object.values(symbolPnlMap),
      exposure: Object.values(exposureMap),
    };
  }));
}

export async function simBridgeInfo(): Promise<BridgeInfo> {
  await delay(40);
  return {
    status: 'simulation',
    mode: 'simulation',
    terminal: null,
    trading_enabled: false,
    endpoint: null,
    protocol: null,
    last_heartbeat: now(),
    message: 'Self-contained simulation adapter. No real MT5 terminal or broker connection is active.',
  };
}

export async function simDerivAccounts(): Promise<DerivAccount[]> {
  await delay();
  return clone(withState((state) => state.derivAccounts));
}

export async function simSetActiveDeriv(id: number): Promise<DerivAccount> {
  await delay();
  return clone(withState((state) => {
    const row = state.derivAccounts.find((a) => a.id === id);
    if (!row) throw new Error('Deriv account not found in this standalone module.');
    state.derivAccounts.forEach((a) => { a.is_active = a.id === id; });
    return row;
  }));
}

export async function simAiGet(): Promise<{ insights: AiInsight[]; settings: AiSettings }> {
  await delay();
  return clone(withState((state) => ({ insights: state.insights, settings: state.aiSettings })));
}

export async function simAiGenerate(): Promise<{ insights: AiInsight[]; settings: AiSettings }> {
  await delay(220);
  return clone(withState((state) => {
    recalcPositionSnapshots(state);
    const generated: AiInsight[] = [];
    if (!state.positions.length) {
      generated.push({
        id: Date.now(), title: 'Book is flat', body: 'There are no simulated MT5 positions open. Risk exposure is currently zero in the standalone hub.',
        category: 'risk', sentiment: 'neutral', confidence: 100, account_login: null, bot_id: null, created_at: now(),
      });
    } else {
      const floating = state.positions.reduce((s, p) => s + p.profit, 0);
      generated.push({
        id: Date.now(), title: 'Open-position risk snapshot',
        body: `${state.positions.length} simulated position${state.positions.length === 1 ? '' : 's'} are open with combined floating P/L of ${floating >= 0 ? '+' : '-'}$${Math.abs(floating).toFixed(2)}.`,
        category: 'risk', sentiment: floating < 0 ? 'warning' : 'neutral', confidence: 100, account_login: null, bot_id: null, created_at: now(),
      });
    }
    const activeBots = state.bots.filter((b) => b.status === 'running' || b.status === 'paused');
    if (activeBots.length) {
      generated.push({
        id: Date.now() + 1, title: 'Automation status',
        body: `${activeBots.length} EA${activeBots.length === 1 ? '' : 's'} are active in simulation. These controls do not launch .ex5 files until a real Windows MT5 worker is connected.`,
        category: 'performance', sentiment: 'neutral', confidence: 100, account_login: null, bot_id: null, created_at: now(),
      });
    }
    state.insights = [...generated, ...state.insights].slice(0, 30);
    return { insights: state.insights, settings: state.aiSettings };
  }));
}

export async function simAiDelete(id: number) {
  await delay();
  withState((state) => { state.insights = state.insights.filter((i) => i.id !== id); });
  return { ok: true };
}

export async function simAiSettings(settings: AiSettings) {
  await delay();
  return clone(withState((state) => { state.aiSettings = settings; return state.aiSettings; }));
}

export async function simGetRisk(): Promise<RiskSettings[]> {
  await delay();
  return clone(withState((state) => state.risk));
}

export async function simSetRisk(row: RiskSettings): Promise<RiskSettings> {
  await delay();
  return clone(withState((state) => {
    const idx = state.risk.findIndex((r) => r.id === row.id);
    if (idx >= 0) state.risk[idx] = row; else state.risk.push(row);
    return row;
  }));
}

export async function simBotPerformance(botId: number): Promise<BotPerformance> {
  await delay();
  return clone(withState((state) => {
    const bot = state.bots.find((b) => b.id === botId);
    if (!bot) throw new Error('Bot not found.');
    const rows = state.history.filter((h) => h.source === bot.name);
    const wins = rows.filter((r) => r.profit > 0);
    const losses = rows.filter((r) => r.profit < 0);
    const grossProfit = money(wins.reduce((s, r) => s + r.profit, 0));
    const grossLoss = money(losses.reduce((s, r) => s + r.profit, 0));
    let peak = 0;
    let curve = 0;
    let maxDrawdown = 0;
    for (const r of [...rows].reverse()) {
      curve += r.profit;
      peak = Math.max(peak, curve);
      maxDrawdown = Math.max(maxDrawdown, peak - curve);
    }
    return {
      bot_id: botId,
      trades: rows.length,
      wins: wins.length,
      losses: losses.length,
      win_rate: rows.length ? Number(((wins.length / rows.length) * 100).toFixed(1)) : 0,
      gross_profit: grossProfit,
      gross_loss: grossLoss,
      net_pl: money(grossProfit + grossLoss),
      average_win: wins.length ? money(grossProfit / wins.length) : 0,
      average_loss: losses.length ? money(grossLoss / losses.length) : 0,
      largest_win: wins.length ? Math.max(...wins.map((r) => r.profit)) : 0,
      largest_loss: losses.length ? Math.min(...losses.map((r) => r.profit)) : 0,
      current_drawdown: money(Math.max(0, peak - curve)),
      max_drawdown: money(maxDrawdown),
    };
  }));
}

export async function simCopyState(): Promise<CopyState> {
  await delay();
  return clone(withState((state) => ({
    relationships: state.copyRelationships,
    events: state.copyEvents,
    real_execution_available: false,
    execution_message: 'Simulation copy engine is active. Real multi-account copying requires isolated MT5 terminal workers.',
  })));
}

export async function simCreateCopyRelationship(payload: Omit<CopyRelationship, 'id' | 'created_at' | 'status'>): Promise<CopyRelationship> {
  await delay();
  return clone(withState((state) => {
    if (payload.master_login === payload.follower_login) throw new Error('Master and follower accounts must be different.');
    if (!state.accounts.some((a) => a.login === payload.master_login)) throw new Error('Master account not found.');
    if (!state.accounts.some((a) => a.login === payload.follower_login)) throw new Error('Follower account not found.');
    const row: CopyRelationship = { ...payload, id: `copy-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, created_at: now(), status: payload.enabled ? 'armed' : 'stopped', last_event: null };
    state.copyRelationships.unshift(row);
    addCopyEvent(state, { relationship_id: row.id, action: 'status', message: row.enabled ? 'Copy relationship armed.' : 'Copy relationship created but stopped.' });
    return row;
  }));
}

export async function simUpdateCopyRelationship(id: string, patch: Partial<CopyRelationship>): Promise<CopyRelationship> {
  await delay();
  return clone(withState((state) => {
    const row = state.copyRelationships.find((r) => r.id === id);
    if (!row) throw new Error('Copy relationship not found.');
    Object.assign(row, patch);
    row.status = row.enabled ? (row.status === 'copying' ? 'copying' : 'armed') : 'stopped';
    addCopyEvent(state, { relationship_id: row.id, action: 'status', message: row.enabled ? 'Copy relationship armed.' : 'Copy relationship stopped.' });
    return row;
  }));
}

export async function simDeleteCopyRelationship(id: string) {
  await delay();
  return withState((state) => {
    const before = state.copyRelationships.length;
    state.copyRelationships = state.copyRelationships.filter((r) => r.id !== id);
    return { ok: state.copyRelationships.length !== before };
  });
}

export async function simReset() {
  localStorage.removeItem(KEY);
  await delay(50);
  return { ok: true };
}
