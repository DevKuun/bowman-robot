// API Response Types

export interface BotStatus {
  running: boolean;
  mode: string;
  exchange: string | null;
  start_time: string | null;
  uptime_seconds: number | null;
  total_trades: number;
  total_fees: number;
  current_pnl?: number;
  current_pnl_percent?: number;
  total_value?: number;
  initial_value?: number;
  iteration_count?: number;
  risk_level?: number;
  session_id?: string;
  quote_currency?: string;
}

export interface Holding {
  currency: string;
  amount: number;
  price: number;
  value: number;
  current_weight: number;
  target_weight: number;
}

export interface Portfolio {
  quote_currency: string;
  total_value: number;
  initial_value: number;
  pnl: number;
  pnl_percent: number;
  holdings: Holding[];
}

export interface PnLDataPoint {
  timestamp: string;
  total_value: number;
  pnl: number;
  pnl_percent: number;
  btc_price?: number;
  eth_price?: number;
  btc_return?: number;  // BTC return since session start (%)
  eth_return?: number;  // ETH return since session start (%)
}

export interface Trade {
  timestamp: string;
  symbol: string;
  side: string;
  quantity: string;
  price: string;
  value: string;
  fee: string;
  best_price?: string;
  slippage_percent?: string;
  levels_consumed?: number;
  partially_filled?: boolean;
  below_minimum?: boolean;  // Trade value is below minimum trade amount
  slippage_reduced?: boolean;  // True if below_minimum was caused by slippage
  original_value?: string;  // Original requested trade value
}

export interface LogEntry {
  timestamp: string;
  level: string;
  message: string;
  module: string;
}

export interface Account {
  id: string;
  user_id: string;
  exchange: string;
  risk_level: number;
  cash_weight: number;
  is_active: boolean;
  created_at: string | null;
}

export interface TradeSummary {
  total_trades: number;
  buy_trades: number;
  sell_trades: number;
  total_volume: number;
  total_fees: number;
  avg_slippage: number;
  max_slippage: number;
}

export interface PortfolioSummary {
  total_value: number;
  initial_value: number;
  pnl: number;
  pnl_percent: number;
  allocation: {
    cash: number;
    cash_percent: number;
    stablecoins: number;
    stablecoins_percent: number;
    crypto: number;
    crypto_percent: number;
  };
  asset_count: number;
  total_trades: number;
  total_fees: number;
}
