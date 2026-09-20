import { isSimulation } from '../config/runtime';
import type { Candle } from '../lib/market';
import type { DerivAccount, DerivSymbol, DerivTick } from '../types';
import { apiRequest } from './http';
import { simDerivAccounts, simSetActiveDeriv } from './simulationStore';

const PUBLIC_OPTIONS_WS = 'wss://api.derivws.com/trading/v1/options/ws/public';
const ENDPOINTS = [PUBLIC_OPTIONS_WS] as const;

type Handler = (message: any) => void;

type PendingRequest = {
  resolve: (value: any) => void;
  reject: (error: Error) => void;
  timer: number;
};

function messageError(msg: any): Error | null {
  const oldError = msg?.error;
  if (oldError) return new Error(String(oldError.message || oldError.code || 'Deriv request failed.'));
  const nextError = Array.isArray(msg?.errors) ? msg.errors[0] : null;
  if (nextError) return new Error(String(nextError.message || nextError.code || 'Deriv request failed.'));
  return null;
}

class DerivPublicSocket {
  private ws: WebSocket | null = null;
  private connecting: Promise<WebSocket> | null = null;
  private endpointIndex = 0;
  private reqSeq = 100;
  private pending = new Map<number, PendingRequest>();
  private streamHandlers = new Map<number, Handler>();
  private subscriptionHandlers = new Map<string, Handler>();
  private subscriptionByReq = new Map<number, string>();

  private rejectPending(reason: string) {
    const error = new Error(reason);
    for (const p of this.pending.values()) {
      window.clearTimeout(p.timer);
      p.reject(error);
    }
    this.pending.clear();
  }

  private resetSocket(reason = 'Deriv WebSocket disconnected.') {
    const old = this.ws;
    this.ws = null;
    this.connecting = null;
    this.rejectPending(reason);
    this.streamHandlers.clear();
    this.subscriptionHandlers.clear();
    this.subscriptionByReq.clear();
    if (old && old.readyState !== WebSocket.CLOSED) {
      try { old.close(); } catch { /* already closing */ }
    }
  }

  private connectTo(endpoint: string): Promise<WebSocket> {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(endpoint);
      let settled = false;
      const timer = window.setTimeout(() => {
        if (settled) return;
        settled = true;
        try { ws.close(); } catch { /* ignore */ }
        reject(new Error('Deriv public WebSocket connection timed out.'));
      }, 9000);
      ws.onopen = () => {
        if (settled) return;
        settled = true;
        window.clearTimeout(timer);
        resolve(ws);
      };
      ws.onerror = () => {
        if (settled) return;
        settled = true;
        window.clearTimeout(timer);
        reject(new Error('Could not connect to Deriv public market data.'));
      };
    });
  }

  private attachHandlers(ws: WebSocket) {
    ws.onmessage = (event) => {
      let msg: any;
      try { msg = JSON.parse(event.data); } catch { return; }
      const reqId = Number(msg.req_id || msg.echo_req?.req_id || 0);
      const error = messageError(msg);

      if (reqId && this.pending.has(reqId)) {
        const p = this.pending.get(reqId)!;
        window.clearTimeout(p.timer);
        this.pending.delete(reqId);
        if (error) p.reject(error);
        else p.resolve(msg);
      } else if (!reqId && error && this.pending.size) {
        // The newer endpoint can return top-level `errors` without echoing req_id.
        // Reject the oldest outstanding request so request-level failover can engage.
        const first = this.pending.entries().next().value as [number, PendingRequest] | undefined;
        if (first) {
          const [id, p] = first;
          window.clearTimeout(p.timer);
          this.pending.delete(id);
          p.reject(error);
        }
      }

      if (error) return;
      const subId = msg.subscription?.id ? String(msg.subscription.id) : '';
      const requestHandler = reqId ? this.streamHandlers.get(reqId) : undefined;
      if (subId) {
        if (!this.subscriptionHandlers.has(subId) && requestHandler) {
          this.subscriptionHandlers.set(subId, requestHandler);
          this.subscriptionByReq.set(reqId, subId);
        }
        (this.subscriptionHandlers.get(subId) || requestHandler)?.(msg);
      } else {
        requestHandler?.(msg);
      }
    };
    ws.onclose = () => {
      if (this.ws === ws) this.resetSocket('Deriv WebSocket disconnected.');
    };
  }

  async connect(): Promise<WebSocket> {
    if (this.ws?.readyState === WebSocket.OPEN) return this.ws;
    if (this.connecting) return this.connecting;

    this.connecting = (async () => {
      let lastError: unknown;
      for (let offset = 0; offset < ENDPOINTS.length; offset++) {
        const index = (this.endpointIndex + offset) % ENDPOINTS.length;
        try {
          const ws = await this.connectTo(ENDPOINTS[index]);
          this.endpointIndex = index;
          this.ws = ws;
          this.attachHandlers(ws);
          return ws;
        } catch (error) {
          lastError = error;
        }
      }
      throw lastError instanceof Error ? lastError : new Error('Could not connect to Deriv market data.');
    })().finally(() => { this.connecting = null; });

    return this.connecting;
  }

  private async sendRequest(payload: Record<string, any>, timeoutMs: number, handler?: Handler): Promise<{ msg: any; reqId: number }> {
    const ws = await this.connect();
    const reqId = ++this.reqSeq;
    if (handler) this.streamHandlers.set(reqId, handler);
    const msg = await new Promise<any>((resolve, reject) => {
      const timer = window.setTimeout(() => {
        this.pending.delete(reqId);
        this.streamHandlers.delete(reqId);
        reject(new Error('Deriv market-data request timed out.'));
      }, timeoutMs);
      this.pending.set(reqId, { resolve, reject, timer });
      try {
        ws.send(JSON.stringify({ ...payload, req_id: reqId }));
      } catch (error) {
        window.clearTimeout(timer);
        this.pending.delete(reqId);
        this.streamHandlers.delete(reqId);
        reject(error instanceof Error ? error : new Error('Could not send Deriv market-data request.'));
      }
    });
    return { msg, reqId };
  }

  private async failover() {
    this.resetSocket('Switching Deriv market-data endpoint.');
    this.endpointIndex = (this.endpointIndex + 1) % ENDPOINTS.length;
  }

  async request(payload: Record<string, any>, timeoutMs = 12000): Promise<any> {
    let lastError: unknown;
    for (let attempt = 0; attempt < ENDPOINTS.length; attempt++) {
      try {
        return (await this.sendRequest(payload, timeoutMs)).msg;
      } catch (error) {
        lastError = error;
        if (attempt < ENDPOINTS.length - 1) await this.failover();
      }
    }
    throw lastError instanceof Error ? lastError : new Error('Deriv request failed.');
  }

  async subscribe(payload: Record<string, any>, handler: Handler): Promise<() => void> {
    let lastError: unknown;
    for (let attempt = 0; attempt < ENDPOINTS.length; attempt++) {
      let reqId = 0;
      try {
        const result = await this.sendRequest({ ...payload, subscribe: 1 }, 12000, handler);
        reqId = result.reqId;
        const subId = result.msg?.subscription?.id ? String(result.msg.subscription.id) : '';
        if (subId) {
          this.subscriptionHandlers.set(subId, handler);
          this.subscriptionByReq.set(reqId, subId);
        }
        return () => {
          this.streamHandlers.delete(reqId);
          const id = this.subscriptionByReq.get(reqId);
          if (id) {
            this.subscriptionHandlers.delete(id);
            this.subscriptionByReq.delete(reqId);
            if (this.ws?.readyState === WebSocket.OPEN) {
              try { this.ws.send(JSON.stringify({ forget: id, req_id: ++this.reqSeq })); } catch { /* socket is already closing */ }
            }
          }
        };
      } catch (error) {
        if (reqId) this.streamHandlers.delete(reqId);
        lastError = error;
        if (attempt < ENDPOINTS.length - 1) await this.failover();
      }
    }
    throw lastError instanceof Error ? lastError : new Error('Deriv tick subscription failed.');
  }

  close() { this.resetSocket('Deriv public socket closed.'); }
}

const publicSocket = typeof window !== 'undefined' ? new DerivPublicSocket() : null;

type CandleCacheEntry = {
  rows: Candle[];
  expiresAt: number;
};

const candleCache = new Map<string, CandleCacheEntry>();
const candleInflight = new Map<string, Promise<Candle[]>>();
let historyQueue: Promise<void> = Promise.resolve();
let nextHistoryRequestAt = 0;
let historyCooldownUntil = 0;
const HISTORY_REQUEST_GAP_MS = 900;
const HISTORY_RATE_LIMIT_COOLDOWN_MS = 12000;
const LATEST_CANDLE_CACHE_MS = 15000;
const HISTORICAL_CANDLE_CACHE_MS = 10 * 60 * 1000;
const MAX_CANDLE_CACHE_ENTRIES = 80;

function isTicksHistoryRateLimit(error: unknown) {
  const message = error instanceof Error ? error.message : String(error || '');
  return /rate limit/i.test(message) && /ticks_history|tick/i.test(message);
}

function pruneCandleCache() {
  if (candleCache.size <= MAX_CANDLE_CACHE_ENTRIES) return;
  const oldest = [...candleCache.keys()].slice(0, candleCache.size - MAX_CANDLE_CACHE_ENTRIES);
  oldest.forEach((key) => candleCache.delete(key));
}

async function queuedHistoryRequest<T>(request: () => Promise<T>): Promise<T> {
  const previous = historyQueue;
  let release!: () => void;
  historyQueue = new Promise<void>((resolve) => { release = resolve; });
  await previous;
  try {
    const now = Date.now();
    const waitUntil = Math.max(nextHistoryRequestAt, historyCooldownUntil);
    if (waitUntil > now) {
      await new Promise((resolve) => window.setTimeout(resolve, waitUntil - now));
    }
    nextHistoryRequestAt = Date.now() + HISTORY_REQUEST_GAP_MS;
    try {
      return await request();
    } catch (error) {
      if (!isTicksHistoryRateLimit(error)) throw error;
      historyCooldownUntil = Date.now() + HISTORY_RATE_LIMIT_COOLDOWN_MS;
      await new Promise((resolve) => window.setTimeout(resolve, HISTORY_RATE_LIMIT_COOLDOWN_MS));
      nextHistoryRequestAt = Date.now() + HISTORY_REQUEST_GAP_MS;
      return await request();
    }
  } finally {
    release();
  }
}

function normalizeCandles(msg: any, symbol: string): Candle[] {
  const rows = msg.candles || msg.data?.candles || [];
  const normalized = rows.map((c: any) => ({
    time: Number(c.epoch ?? c.time),
    open: Number(c.open),
    high: Number(c.high),
    low: Number(c.low),
    close: Number(c.close),
    volume: Number(c.volume || 0),
  })).filter((c: Candle) => Number.isFinite(c.time) && Number.isFinite(c.close));
  if (!normalized.length) throw new Error(`Deriv returned no candle data for ${symbol}. Try Retry or another timeframe.`);
  return normalized;
}

function normalizeSymbol(row: any): DerivSymbol {
  return {
    symbol: String(row.underlying_symbol || row.symbol || ''),
    name: String(row.underlying_symbol_name || row.display_name || row.underlying_symbol || row.symbol || ''),
    market: String(row.market || row.submarket || 'other'),
    subgroup: row.subgroup ? String(row.subgroup) : undefined,
    submarket: row.submarket ? String(row.submarket) : undefined,
    symbol_type: String(row.underlying_symbol_type || row.symbol_type || ''),
    pip_size: Number(row.pip_size ?? row.pip ?? 0) || undefined,
    exchange_is_open: row.exchange_is_open == null ? undefined : Boolean(row.exchange_is_open),
    is_trading_suspended: row.is_trading_suspended == null ? undefined : Boolean(row.is_trading_suspended),
  };
}

const FALLBACK_SYMBOLS: DerivSymbol[] = [
  ['R_10','Volatility 10 Index'], ['R_25','Volatility 25 Index'], ['R_50','Volatility 50 Index'], ['R_75','Volatility 75 Index'], ['R_100','Volatility 100 Index'],
  ['1HZ10V','Volatility 10 (1s) Index'], ['1HZ15V','Volatility 15 (1s) Index'], ['1HZ25V','Volatility 25 (1s) Index'], ['1HZ30V','Volatility 30 (1s) Index'], ['1HZ50V','Volatility 50 (1s) Index'], ['1HZ75V','Volatility 75 (1s) Index'], ['1HZ90V','Volatility 90 (1s) Index'], ['1HZ100V','Volatility 100 (1s) Index'],
].map(([symbol, name]) => ({ symbol, name, market: 'synthetic_index', symbol_type: 'synthetic_index' }));

export const derivMarketService = {
  accounts: (): Promise<DerivAccount[]> => isSimulation ? simDerivAccounts() : apiRequest<DerivAccount[]>('/api/deriv/accounts'),
  setActiveAccount: (id: number): Promise<DerivAccount> => isSimulation ? simSetActiveDeriv(id) : apiRequest<DerivAccount>(`/api/deriv/accounts/${id}/active`, 'POST', {}),

  async activeSymbols(): Promise<DerivSymbol[]> {
    if (!publicSocket) return FALLBACK_SYMBOLS;
    try {
      const msg = await publicSocket.request({ active_symbols: 'brief' });
      const rows = (msg.active_symbols || msg.data?.active_symbols || []).map(normalizeSymbol).filter((x: DerivSymbol) => x.symbol);
      return rows.length ? rows : FALLBACK_SYMBOLS;
    } catch {
      return FALLBACK_SYMBOLS;
    }
  },

  async candles(symbol: string, granularity = 60, count = 500, end: 'latest' | number = 'latest'): Promise<Candle[]> {
    if (!publicSocket) return [];
    const safeCount = Math.max(10, Math.min(5000, count));
    const key = `${symbol}|${granularity}|${safeCount}|${end}`;
    const cached = candleCache.get(key);
    if (cached && (cached.expiresAt > Date.now() || historyCooldownUntil > Date.now())) {
      return cached.rows.map((row) => ({ ...row }));
    }
    const existing = candleInflight.get(key);
    if (existing) return (await existing).map((row) => ({ ...row }));

    const request = queuedHistoryRequest(async () => {
      try {
        const msg = await publicSocket.request({
          ticks_history: symbol,
          end,
          style: 'candles',
          granularity,
          count: safeCount,
        });
        const normalized = normalizeCandles(msg, symbol);
        candleCache.set(key, {
          rows: normalized,
          expiresAt: Date.now() + (end === 'latest' ? LATEST_CANDLE_CACHE_MS : HISTORICAL_CANDLE_CACHE_MS),
        });
        pruneCandleCache();
        return normalized;
      } catch (error) {
        const stale = candleCache.get(key);
        if (stale && isTicksHistoryRateLimit(error)) return stale.rows;
        throw error;
      }
    });

    candleInflight.set(key, request);
    try {
      const rows = await request;
      return rows.map((row) => ({ ...row }));
    } finally {
      candleInflight.delete(key);
    }
  },

  async subscribeTicks(symbol: string, onTick: (tick: DerivTick) => void): Promise<() => void> {
    if (!publicSocket) return () => {};
    let stopped = false;
    let stopCurrent: (() => void) | undefined;
    let lastTickAt = Date.now();
    let restarting = false;
    const subscribe = async () => {
      stopCurrent?.();
      stopCurrent = await publicSocket.subscribe({ ticks: symbol }, (msg) => {
        if (messageError(msg)) return;
        const t = msg.tick || msg.data?.tick;
        if (!t || stopped) return;
        lastTickAt = Date.now();
        onTick({
          symbol: String(t.symbol || symbol),
          quote: Number(t.quote),
          epoch: Number(t.epoch),
          pip_size: Number(t.pip_size || 0) || undefined,
        });
      });
    };
    await subscribe();
    const watchdog = window.setInterval(async () => {
      if (stopped || restarting || Date.now() - lastTickAt < 45000) return;
      restarting = true;
      try {
        publicSocket.close();
        await subscribe();
        lastTickAt = Date.now();
      } catch { /* retry on the next watchdog interval */ }
      finally { restarting = false; }
    }, 15000);
    return () => {
      stopped = true;
      window.clearInterval(watchdog);
      stopCurrent?.();
    };
  },

  reconnect() {
    publicSocket?.close();
  },

  fallbackSymbols: (): DerivSymbol[] => FALLBACK_SYMBOLS,
};
