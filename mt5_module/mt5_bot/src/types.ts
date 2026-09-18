export type RuntimeMode = 'simulation' | 'bridge';
export type EnvironmentBadge = 'SIMULATION' | 'DEMO' | 'LIVE';
export type BridgeStatus = 'simulation' | 'connecting' | 'online' | 'offline' | 'reconnecting' | 'error';

export interface Mt5Account {
  id: number;
  login: number;
  nickname: string;
  broker: string;
  server: string;
  balance: number;
  equity: number;
  margin: number;
  free_margin: number;
  floating_pl: number;
  leverage: number;
  currency: string;
  status: 'connected' | 'disconnected' | 'connecting';
  is_active: boolean;
  account_type: 'live' | 'demo';
  access_mode?: 'trading' | 'investor';
  read_only?: boolean;
  worker_id?: string | null;
  terminal_id?: string | null;
  connection_status?: BridgeStatus | null;
  last_heartbeat?: string | null;
  created_at?: string;
  cached?: boolean;
  budget?: number | null;
  budget_enabled?: boolean;
  budget_virtual_balance?: number | null;
  budget_virtual_equity?: number | null;
  budget_virtual_free_margin?: number | null;
}

export interface BotSettings {
  risk_percent: number;
  max_spread: number;
  trailing_stop: boolean;
  magic_number: number;
  max_daily_loss: number;
  slippage?: number;
  max_open_positions?: number;
  trading_session?: string;
}

export interface EaStrategyAnalysis {
  ea_verified?: boolean;
  verification_error?: string | null;
  observed_messages?: string[];
  observed_timeframes?: string[];
  observed_traits?: string[];
  last_ea_activity?: string | null;
  analysis_scope?: string;
}

export interface Mt5Bot {
  id: number;
  name: string;
  description: string;
  strategy: string;
  symbol: string;
  timeframe: string;
  account_login: number | null;
  status: 'starting' | 'running' | 'paused' | 'stopping' | 'stopped' | 'error' | 'worker_offline' | 'connecting';
  lot_size: number;
  win_rate: number;
  total_trades: number;
  net_profit: number;
  profit_today: number;
  version: string;
  started_at: string | null;
  settings: BotSettings;
  ea_filename?: string | null;
  preset_filename?: string | null;
  file_status?: 'ready' | 'missing' | 'metadata-only' | 'native' | 'source-required' | 'compile-error';
  source_filename?: string | null;
  source_storage_path?: string | null;
  source_sha256?: string | null;
  compile_status?: 'success' | 'failed' | null;
  compile_errors?: number | null;
  compile_warnings?: number | null;
  compile_log?: string | null;
  compile_date?: string | null;
  upload_date?: string | null;
  dll_required?: boolean;
  display_title?: string | null;
  display_subtitle?: string | null;
  native_engine?: boolean;
  native_key?: string | null;
  native_ready?: boolean;
  native_source?: string | null;
  engine_type?: 'native' | 'ex5' | 'source_required' | string;
  bias_timeframe?: string | null;
  legacy_ex5_available?: boolean;
  native_config?: Record<string, unknown> | null;
  native_runtime?: Record<string, unknown> | null;
  native_signal?: Record<string, unknown> | null;
  native_last_execution?: Record<string, unknown> | null;
  recommended_timeframe?: string | null;
  ea_storage_path?: string | null;
  preset_storage_path?: string | null;
  ea_size_bytes?: number | null;
  preset_size_bytes?: number | null;
  ea_sha256?: string | null;
  preset_sha256?: string | null;
  worker_id?: string | null;
  terminal_id?: string | null;
  process_id?: number | null;
  terminal_status?: 'online' | 'offline' | null;
  last_activity?: string | null;
  last_error?: string | null;
  account_verified?: boolean;
  open_positions?: number;
  current_pl?: number;
  today_pl?: number;
  account_open_positions?: number;
  account_current_pl?: number;
  metrics_scope?: string | null;
  bot_trade_count?: number;
  bot_wins?: number;
  bot_losses?: number;
  bot_win_rate?: number;
  detected_magic?: number | null;
  attribution_status?: 'pending' | 'verified' | 'ambiguous';
  last_trade?: { ticket: number; symbol: string; time: string } | null;
  ea_verified?: boolean;
  ea_status?: 'active' | 'verifying' | 'stopped' | null;
  verification_message?: string | null;
  background_mode?: boolean;
  metrics_error?: string | null;
  strategy_analysis?: EaStrategyAnalysis | null;
  file_analysis?: { format?: string; compiled?: boolean; file_verified?: boolean; strategy_visibility?: string } | null;
  preset_analysis?: { format?: string; input_count?: number; inputs?: { name: string; value: string }[]; truncated?: boolean } | null;
  system_preset?: boolean;
  locked?: boolean;
}


export interface Mt5Quote {
  symbol: string;
  resolved_symbol: string;
  bid: number;
  ask: number;
  last: number;
  digits: number;
  point: number;
  spread_points: number;
  time: string;
  trade_allowed: boolean;
  path?: string;
  category?: string;
}

export interface Mt5SymbolInfo {
  symbol: string;
  description: string;
  digits: number;
  point: number;
  contract_size: number;
  volume_min: number;
  volume_max: number;
  volume_step: number;
  visible: boolean;
  trade_allowed: boolean;
  path?: string;
  category?: string;
}

export interface Mt5Position {
  id: number;
  ticket: number;
  account_login: number;
  symbol: string;
  type: 'buy' | 'sell';
  volume: number;
  open_price: number;
  current_price: number;
  sl: number | null;
  tp: number | null;
  profit: number;
  swap: number;
  commission: number;
  open_time: string;
  source: string;
  magic: number | null;
}

export interface Mt5HistoryRow {
  id: number;
  ticket: number;
  account_login: number;
  symbol: string;
  type: 'buy' | 'sell';
  volume: number;
  open_price: number;
  close_price: number;
  profit: number;
  swap: number;
  commission: number;
  open_time: string;
  close_time: string;
  source: string;
  net_pl?: number;
}

export interface DerivSymbol {
  symbol: string;
  name: string;
  market: string;
  subgroup?: string;
  submarket?: string;
  symbol_type?: string;
  pip_size?: number;
  exchange_is_open?: boolean;
  is_trading_suspended?: boolean;
}

export interface DerivTick {
  symbol: string;
  quote: number;
  epoch: number;
  pip_size?: number;
}

export type CopyMode = 'same_lot' | 'fixed_lot' | 'balance_ratio' | 'risk_ratio' | 'multiplier';

export interface CopyRelationship {
  id: string;
  name: string;
  master_login: number;
  follower_login: number;
  enabled: boolean;
  status: 'stopped' | 'armed' | 'copying' | 'blocked' | 'error';
  copy_mode: CopyMode;
  fixed_lot: number;
  multiplier: number;
  max_lot: number;
  max_daily_loss: number;
  max_drawdown_pct: number;
  max_open_positions: number;
  copy_new_trades: boolean;
  copy_sl_tp: boolean;
  copy_closes: boolean;
  created_at: string;
  last_event?: string | null;
}

export interface CopyEvent {
  id: string;
  relationship_id: string;
  time: string;
  action: 'open' | 'modify' | 'close' | 'blocked' | 'status';
  symbol?: string;
  side?: 'buy' | 'sell';
  master_ticket?: number;
  follower_ticket?: number;
  master_volume?: number;
  follower_volume?: number;
  profit?: number;
  message: string;
}

export interface CopyState {
  relationships: CopyRelationship[];
  events: CopyEvent[];
  real_execution_available: boolean;
  execution_message: string;
}

export interface EquityPoint {
  date: string;
  equity: number;
  daily_pl: number;
}

export interface Mt5Stats {
  kpis: {
    total_balance: number;
    total_equity: number;
    floating: number;
    margin: number;
    free_margin: number;
    margin_level: number | null;
    realized_today: number;
    today_pl: number;
    trades_today: number;
    latest_day: string | null;
    connected_accounts: number;
    total_accounts: number;
    running_bots: number;
    paused_bots: number;
    total_bots: number;
    open_positions: number;
    win_rate_30d: number;
    trades_30d: number;
    profit_30d: number;
    drawdown_pct: number;
    peak_equity: number;
  };
  equity: EquityPoint[];
  daily: { date: string; pl: number }[];
  bots: Mt5Bot[];
  symbolPnl: { symbol: string; pl: number; trades: number }[];
  exposure: { symbol: string; volume: number; floating: number; count: number }[];
}

export interface AiInsight {
  id: number;
  title: string;
  body: string;
  category: 'risk' | 'opportunity' | 'performance' | 'market';
  sentiment: 'positive' | 'warning' | 'critical' | 'neutral';
  confidence: number;
  account_login: number | null;
  bot_id: number | null;
  created_at: string;
}

export interface AiSettings {
  auto_trading: boolean;
  risk_guard: boolean;
  sentiment_filter: boolean;
  news_pause: boolean;
}

export interface AiTrialSwing {
  kind: 'high' | 'low';
  index: number;
  confirm_index: number;
  time: number;
  price: number;
  label: 'HH' | 'LH' | 'HL' | 'LL' | 'H' | 'L';
}

export interface AiTrialTrade {
  direction: 'BUY' | 'SELL';
  index: number;
  time: number;
  entry: number;
  sl: number;
  tp: number;
  risk_distance: number;
  r_multiple: number;
  confidence: number;
  confidence_factors: string[];
  reason: string;
}

export interface AiTrialExecution {
  executed: boolean;
  account_login: number;
  symbol: string;
  volume: number;
  direction: 'BUY' | 'SELL';
  executed_at: string;
  signal_time?: number;
  mode: 'DEMO_AUTO_TRADE';
  automatic?: boolean;
  source?: 'ai_manual_demo' | 'ai_auto_human_apostle' | string;
  signal_key?: string;
  result: Record<string, unknown>;
  message: string;
}

export interface AiTrialSnapshot {
  trial_version: string;
  strategy: string;
  mode: 'SIGNAL_ONLY';
  execution: string;
  execution_mode?: 'SIGNAL_ONLY' | 'DEMO_AUTO_TRADE';
  execution_lock?: 'demo_only';
  account_login: number;
  symbol: string;
  execution_timeframe: 'M15';
  bias_timeframe: 'H4';
  generated_at: string;
  latest_completed_candle: { time: number; open: number; high: number; low: number; close: number; volume: number };
  completed_candles: { execution: number; bias: number };
  state: string;
  decision: string;
  reason: string;
  execution_structure: 'bullish' | 'bearish' | 'neutral';
  execution_structure_reason: string;
  bias_structure: 'bullish' | 'bearish' | 'neutral';
  bias_reason: string;
  previous_structure: 'bullish' | 'bearish' | 'neutral';
  last_confirmed_high: AiTrialSwing | null;
  last_confirmed_low: AiTrialSwing | null;
  trendline: { anchor_1: AiTrialSwing; anchor_2: AiTrialSwing; break_index: number; break_time: number; line_at_break: number; close: number } | null;
  protected_structure: number | null;
  structure_shift: { confirmed: boolean; index: number | null; time: number | null };
  retest: { level: number | null; touched: boolean; same_candle_blocked: boolean };
  confidence: number;
  confidence_factors: string[];
  proposed_trade: AiTrialTrade | null;
  last_historical_signal: AiTrialTrade | null;
  last_execution?: AiTrialExecution | null;
  rules: {
    completed_candles_only: boolean;
    swing_left: number;
    swing_right: number;
    same_candle_shift_retest: boolean;
    required_sequence: string[];
    take_profit_r: number;
  };
}

export interface AiTrialStatus {
  trial_version: string;
  strategy: string;
  mode: 'SIGNAL_ONLY' | 'DEMO_EXECUTION_LOCKED_TO_DEMO';
  execution_timeframe: 'M15';
  bias_timeframe: 'H4';
  snapshot: AiTrialSnapshot | null;
  execution: string;
}

export interface AiAutoConfig {
  enabled?: boolean;
  strategy?: 'human_apostle';
  account_login?: number;
  symbol?: string;
  volume?: number;
  scan_seconds?: number;
  execution_timeframe?: 'M15';
  bias_timeframe?: 'H4';
  demo_only?: boolean;
  updated_at?: string;
}

export interface AiAutoRuntime {
  status?: 'starting' | 'running' | 'waiting' | 'blocked' | 'stopping' | 'stopped' | string;
  started_at?: string;
  stopped_at?: string;
  last_scan_at?: string;
  last_signal_at?: string;
  last_execution_at?: string;
  last_error_at?: string;
  last_error?: string | null;
  last_symbol?: string;
  last_decision?: string;
  last_confidence?: number;
  last_signal?: 'BUY' | 'SELL' | string;
  last_signal_key?: string;
  last_execution?: AiTrialExecution | null;
}

export interface AiAutoEvent {
  time: string;
  event: string;
  account_login?: number;
  symbol?: string;
  direction?: 'BUY' | 'SELL' | string;
  signal_time?: number;
  volume?: number;
}

export interface AiAutoStatus {
  strategy: 'Human Apostle';
  execution_lock: 'demo_only';
  execution_timeframe: 'M15';
  bias_timeframe: 'H4';
  enabled: boolean;
  scanner_alive: boolean;
  config: AiAutoConfig;
  runtime: AiAutoRuntime;
  events: AiAutoEvent[];
}

export type AiAutoSelectMode = 'analysis' | 'alert' | 'manual' | 'auto';

export interface AiAutoSelectCandidate {
  bot_id: number;
  name: string;
  title: string;
  subtitle?: string;
  decision: 'APPROVE' | 'WAIT' | 'REJECT';
  stage: string;
  score: number;
  selection_score: number;
  reason: string;
  history: { trades: number; wins: number; losses: number; win_rate: number; net_pl: number; selection_bonus: number };
  signal: Record<string, unknown> | null;
}

export interface AiAutoSelectSnapshot {
  generated_at: string;
  account_login: number;
  account_mode: 'demo' | 'live' | 'unknown';
  symbol: string;
  decision: 'APPROVE' | 'WAIT';
  selected: AiAutoSelectCandidate | null;
  results: AiAutoSelectCandidate[];
  rules: {
    completed_candles_only: boolean;
    confidence_cannot_complete_setup: boolean;
    history_is_tiebreaker_only: boolean;
    live_auto_execution: boolean;
  };
}

export interface AiAutoSelectStatus {
  enabled: boolean;
  scanner_alive: boolean;
  config: {
    enabled?: boolean;
    mode?: AiAutoSelectMode;
    account_login?: number;
    symbol?: string;
    enabled_bot_ids?: number[];
    scan_seconds?: number;
    demo_only_auto_execution?: boolean;
  };
  runtime: {
    status?: string;
    started_at?: string;
    stopped_at?: string;
    last_scan_at?: string;
    last_error?: string | null;
    selected_bot_id?: number | null;
    selected_name?: string | null;
    selected_title?: string | null;
    selected_score?: number | null;
    selected_stage?: string | null;
    last_execution_at?: string | null;
    last_execution?: Record<string, unknown> | null;
  };
  snapshot: AiAutoSelectSnapshot | null;
  events: Array<Record<string, unknown> & { time?: string; event?: string }>;
  available_presets: Array<{
    bot_id: number; name: string; title: string; subtitle?: string; ready: boolean;
    source?: string | null; entry_tf?: string | null; bias_tf?: string | null;
  }>;
  execution_lock: 'demo_only_auto_execution';
}

export interface DerivAccount {
  id: number;
  login: string;
  nickname: string;
  platform: string;
  balance: number;
  currency: string;
  status: 'connected' | 'disconnected';
  account_type: 'live' | 'demo';
  is_active: boolean;
}

export interface BridgeInfo {
  status: BridgeStatus;
  mode: RuntimeMode;
  terminal: string | null;
  trading_enabled: boolean;
  endpoint: string | null;
  protocol: string | null;
  last_heartbeat: string | null;
  message?: string | null;
  services?: { bridge: 'online' | 'offline' | 'error'; ea_worker: 'online' | 'offline' | 'error'; copy_worker: 'online' | 'offline' | 'error' };
  ea_worker?: {
    status: 'starting' | 'online' | 'offline' | 'error';
    message: string;
    endpoint: string;
    running?: number;
    terminals: { id: string; name: string; path: string }[];
    capabilities?: { start: boolean; stop: boolean; pause: boolean; resume: boolean };
  };
  capabilities?: {
    account_data: boolean;
    quotes: boolean;
    candles: boolean;
    manual_trading: boolean;
    positions: boolean;
    history: boolean;
    ea_launch: boolean;
  };
}

export interface RiskSettings {
  id: string;
  scope: 'global' | 'account' | 'bot';
  account_login?: number | null;
  bot_id?: number | null;
  max_daily_loss: number;
  max_daily_profit: number;
  max_drawdown_pct: number;
  max_lot_size: number;
  max_open_positions: number;
  max_trades_per_day: number;
  max_risk_per_trade: number;
  allowed_trading_hours: string;
  allowed_symbols: string[];
  auto_stop: boolean;
}

export interface BotPerformance {
  bot_id: number;
  trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  gross_profit: number;
  gross_loss: number;
  net_pl: number;
  average_win: number;
  average_loss: number;
  largest_win: number;
  largest_loss: number;
  current_drawdown: number;
  max_drawdown: number;
}
