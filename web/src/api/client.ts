import axios from 'axios';
import type { 
  BotStatus, Portfolio, PnLDataPoint, Trade, LogEntry, 
  Account, TradeSummary, PortfolioSummary 
} from '../types';

// Use same origin - API is served from the same server
const getApiBase = (): string => {
  // For Vite dev server, redirect to API port
  if (typeof window !== 'undefined' && window.location.port === '5173') {
    return `${window.location.protocol}//${window.location.hostname}:8002`;
  }
  // Use same origin (empty string = relative URLs)
  return '';
};

const API_BASE = getApiBase();

const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Bot API
export const botApi = {
  getStatus: () => api.get<BotStatus>('/api/bot/status').then(r => r.data),
  
  start: (params: {
    exchange: string;
    mode?: string;
    initial_balance?: number;
    risk_level?: number;
    realistic_execution?: boolean;
    skip_optimization?: boolean;
  }) => api.post('/api/bot/start', params).then(r => r.data),
  
  stop: () => api.post('/api/bot/stop').then(r => r.data),
  
  optimize: (params: { exchange: string; force?: boolean }) => 
    api.post('/api/bot/optimize', params).then(r => r.data),
  
  getOptimizationStatus: () => 
    api.get<{ status: string; running: boolean; error?: string }>('/api/bot/optimize/status').then(r => r.data),
  
  cancelOptimization: () =>
    api.post('/api/bot/optimize/cancel').then(r => r.data),
  
  getWeights: (exchange: string, riskLevel: number = 2) => 
    api.get<{ exists: boolean; weights: Record<string, number> | null; asset_count?: number; created_at?: string }>(
      '/api/bot/weights', 
      { params: { exchange, risk_level: riskLevel } }
    ).then(r => r.data),
};

// Portfolio API
export const portfolioApi = {
  get: () => api.get<Portfolio>('/api/portfolio').then(r => r.data),
  
  getPnLHistory: (limit?: number, hours?: number) => 
    api.get<{ data: PnLDataPoint[]; count: number; source?: string }>(
      '/api/portfolio/pnl', 
      { params: { limit, hours } }
    ).then(r => r.data),
  
  getSummary: () => 
    api.get<PortfolioSummary>('/api/portfolio/summary').then(r => r.data),
  
  getWeights: () => api.get('/api/portfolio/weights').then(r => r.data),
};

// Trades API
export const tradesApi = {
  get: (params?: { limit?: number; offset?: number; symbol?: string; side?: string }) =>
    api.get<{ trades: Trade[]; total: number; limit: number; offset: number }>(
      '/api/trades',
      { params }
    ).then(r => r.data),
  
  getSummary: () => api.get<TradeSummary>('/api/trades/summary').then(r => r.data),
  
  getByAsset: () => api.get('/api/trades/by-asset').then(r => r.data),
};

// Accounts API
export const accountsApi = {
  getAll: () => api.get<{ accounts: Account[] }>('/api/accounts').then(r => r.data),
  
  get: (id: string) => api.get<Account>(`/api/accounts/${id}`).then(r => r.data),
  
  create: (params: {
    exchange: string;
    access_key: string;
    secret_key: string;
    risk_level?: number;
    cash_weight?: number;
    email?: string;
  }) => api.post('/api/accounts', params).then(r => r.data),
  
  update: (id: string, params: {
    risk_level?: number;
    cash_weight?: number;
    is_active?: boolean;
  }) => api.patch(`/api/accounts/${id}`, params).then(r => r.data),
  
  delete: (id: string) => api.delete(`/api/accounts/${id}`).then(r => r.data),
};

// Sessions API
export interface TradingSession {
  id: string;
  session_id: string;
  exchange: string;
  mode: string;
  risk_level: number;
  initial_balance: number | null;
  status: string;
  total_trades: number;
  total_fees: number;
  final_pnl: number | null;
  final_pnl_percent: number | null;
  started_at: string | null;
  ended_at: string | null;
}

export interface SessionTrade {
  id: string;
  symbol: string;
  side: string;
  quantity: number;
  price: number;
  value: number | null;
  fee: number;
  status: string;
  slippage_percent: number | null;
  created_at: string | null;
  executed_at: string | null;
}

export interface PnLSnapshot {
  timestamp: string;
  total_value: number;
  pnl: number;
  pnl_percent: number;
  btc_return?: number | null;
  eth_return?: number | null;
}

export interface SessionDetail {
  session: TradingSession;
  trades: SessionTrade[];
  pnl_history: PnLSnapshot[];
  summary: {
    total_trades: number;
    buy_trades: number;
    sell_trades: number;
    total_volume: number;
    total_fees: number;
    avg_slippage: number;
    max_slippage: number;
  };
  assets: Array<{
    symbol: string;
    trade_count: number;
    buy_count: number;
    sell_count: number;
  }>;
}

export const sessionsApi = {
  getAll: (params?: { exchange?: string; mode?: string; limit?: number }) =>
    api.get<TradingSession[]>('/api/sessions', { params }).then(r => r.data),
  
  get: (sessionId: string) => 
    api.get<TradingSession>(`/api/sessions/${sessionId}`).then(r => r.data),
  
  getTrades: (sessionId: string, limit?: number) =>
    api.get<SessionTrade[]>(`/api/sessions/${sessionId}/trades`, { params: { limit } }).then(r => r.data),
  
  getPnL: (sessionId: string, limit?: number) =>
    api.get<PnLSnapshot[]>(`/api/sessions/${sessionId}/pnl`, { params: { limit } }).then(r => r.data),
  
  getDetail: (sessionId: string) =>
    api.get<SessionDetail>(`/api/sessions/${sessionId}/detail`).then(r => r.data),
  
  delete: (sessionId: string) =>
    api.delete(`/api/sessions/${sessionId}`).then(r => r.data),
};

// Logs API
export const logsApi = {
  get: (params?: { limit?: number; level?: string; module?: string }) =>
    api.get<{ logs: LogEntry[]; count: number }>('/api/logs', { params }).then(r => r.data),
};

// Health check
export const healthCheck = () => api.get('/api/health').then(r => r.data);

export default api;
