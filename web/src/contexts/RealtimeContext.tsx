import { createContext, useContext, useEffect, useState, useRef, useCallback, type ReactNode } from 'react';
import type { BotStatus, Portfolio, Trade, LogEntry, PnLDataPoint, TradeSummary, PortfolioSummary } from '../types';

// Get WebSocket URL from current host
const getWsUrl = (): string => {
  if (typeof window === 'undefined') {
    return 'ws://localhost:8002';
  }
  const { protocol, hostname, port } = window.location;
  const wsProtocol = protocol === 'https:' ? 'wss:' : 'ws:';
  // For Vite dev server, redirect to API port
  if (port === '5173') {
    return `${wsProtocol}//${hostname}:8002`;
  }
  // Use same host:port as current page
  return port ? `${wsProtocol}//${hostname}:${port}` : `${wsProtocol}//${hostname}`;
};

interface RealtimeState {
  // Connection state
  isConnected: boolean;
  
  // Real-time data
  status: BotStatus | null;
  portfolio: Portfolio | null;
  trades: Trade[];
  logs: LogEntry[];
  pnlHistory: PnLDataPoint[];
  tradesSummary: TradeSummary | null;
  portfolioSummary: PortfolioSummary | null;
  
  // Last update timestamps
  lastStatusUpdate: Date | null;
  lastPortfolioUpdate: Date | null;
  lastTradeUpdate: Date | null;
}

interface RealtimeContextValue extends RealtimeState {
  reconnect: () => void;
}

const RealtimeContext = createContext<RealtimeContextValue | null>(null);

export function RealtimeProvider({ children }: { children: ReactNode }) {
  const [isConnected, setIsConnected] = useState(false);
  const [status, setStatus] = useState<BotStatus | null>(null);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [pnlHistory, setPnlHistory] = useState<PnLDataPoint[]>([]);
  const [tradesSummary, setTradesSummary] = useState<TradeSummary | null>(null);
  const [portfolioSummary, setPortfolioSummary] = useState<PortfolioSummary | null>(null);
  const [lastStatusUpdate, setLastStatusUpdate] = useState<Date | null>(null);
  const [lastPortfolioUpdate, setLastPortfolioUpdate] = useState<Date | null>(null);
  const [lastTradeUpdate, setLastTradeUpdate] = useState<Date | null>(null);
  
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retriesRef = useRef(0);
  const maxRetries = 10;
  const reconnectInterval = 3000;
  const prevSessionIdRef = useRef<string | null>(null);
  
  // Clear data when session changes
  useEffect(() => {
    const currentSessionId = status?.session_id || null;
    if (prevSessionIdRef.current !== null && currentSessionId !== prevSessionIdRef.current) {
      // Session changed, clear previous session data
      console.log('[WebSocket] Session changed, clearing data');
      setPnlHistory([]);
      setTrades([]);
      setLogs([]);
      setTradesSummary(null);
    }
    prevSessionIdRef.current = currentSessionId;
  }, [status?.session_id]);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    if (wsRef.current?.readyState === WebSocket.CONNECTING) return;

    const wsUrl = `${getWsUrl()}/api/ws`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      setIsConnected(true);
      retriesRef.current = 0;
      console.log('[WebSocket] Connected to real-time feed');
    };

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        const { type, data } = message;
        
        switch (type) {
          case 'init':
            // Initial state from server
            if (data.status) {
              setStatus(data.status);
              setLastStatusUpdate(new Date());
            }
            if (data.portfolio) {
              setPortfolio(data.portfolio);
              setLastPortfolioUpdate(new Date());
            }
            if (data.trades) {
              // Reverse to show newest first
              setTrades([...data.trades].reverse());
            }
            break;
            
          case 'status':
            setStatus(data);
            setLastStatusUpdate(new Date());
            break;
            
          case 'portfolio':
            setPortfolio(data);
            setLastPortfolioUpdate(new Date());
            break;
            
          case 'trade':
            setTrades(prev => {
              // Add new trade at the beginning (newest first)
              const newTrades = [data, ...prev];
              // Keep first 200 trades (newest)
              return newTrades.slice(0, 200);
            });
            setLastTradeUpdate(new Date());
            break;
            
          case 'pnl':
            setPnlHistory(prev => {
              const newHistory = [...prev, data];
              // Keep last 1000 data points
              return newHistory.slice(-1000);
            });
            break;
            
          case 'log':
            setLogs(prev => {
              const newLogs = [...prev, data];
              // Keep last 500 logs
              return newLogs.slice(-500);
            });
            break;
            
          case 'trades_summary':
            setTradesSummary(data);
            break;
            
          case 'portfolio_summary':
            setPortfolioSummary(data);
            break;
        }
      } catch (e) {
        // Ignore parse errors
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      wsRef.current = null;
      
      // Attempt reconnect
      if (retriesRef.current < maxRetries) {
        retriesRef.current++;
        console.log(`[WebSocket] Disconnected. Reconnecting in ${reconnectInterval}ms... (attempt ${retriesRef.current}/${maxRetries})`);
        reconnectTimeoutRef.current = setTimeout(connect, reconnectInterval);
      } else {
        console.log('[WebSocket] Max retries reached. Call reconnect() to try again.');
      }
    };

    ws.onerror = () => {
      // Error handling is done in onclose
    };

    wsRef.current = ws;
  }, []);

  const reconnect = useCallback(() => {
    retriesRef.current = 0;
    if (wsRef.current) {
      wsRef.current.close();
    }
    connect();
  }, [connect]);

  // Connect on mount
  useEffect(() => {
    connect();
    
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  const value: RealtimeContextValue = {
    isConnected,
    status,
    portfolio,
    trades,
    logs,
    pnlHistory,
    tradesSummary,
    portfolioSummary,
    lastStatusUpdate,
    lastPortfolioUpdate,
    lastTradeUpdate,
    reconnect,
  };

  return (
    <RealtimeContext.Provider value={value}>
      {children}
    </RealtimeContext.Provider>
  );
}

export function useRealtime() {
  const context = useContext(RealtimeContext);
  if (!context) {
    throw new Error('useRealtime must be used within a RealtimeProvider');
  }
  return context;
}

// Convenience hooks for specific data
export function useRealtimeStatus() {
  const { status, lastStatusUpdate, isConnected } = useRealtime();
  return { status, lastUpdate: lastStatusUpdate, isConnected };
}

export function useRealtimePortfolio() {
  const { portfolio, lastPortfolioUpdate, isConnected } = useRealtime();
  return { portfolio, lastUpdate: lastPortfolioUpdate, isConnected };
}

export function useRealtimeTrades() {
  const { trades, lastTradeUpdate, isConnected } = useRealtime();
  return { trades, lastUpdate: lastTradeUpdate, isConnected };
}

export function useRealtimeLogs() {
  const { logs, isConnected } = useRealtime();
  return { logs, isConnected };
}

export function useRealtimePnL() {
  const { pnlHistory, isConnected } = useRealtime();
  return { pnlHistory, isConnected };
}

export function useRealtimeTradesSummary() {
  const { tradesSummary, isConnected } = useRealtime();
  return { tradesSummary, isConnected };
}

export function useRealtimePortfolioSummary() {
  const { portfolioSummary, isConnected } = useRealtime();
  return { portfolioSummary, isConnected };
}
