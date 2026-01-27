import { useQuery } from '@tanstack/react-query';
import { useState, useMemo } from 'react';
import { botApi, portfolioApi } from '../api/client';
import { BotPanel } from '../components/BotPanel';
import { PerformanceCharts } from '../components/PerformanceCharts';
import { LogViewer } from '../components/LogViewer';
import { useRealtime } from '../contexts/RealtimeContext';

// Time range options (in hours)
const TIME_RANGES = [
  { label: '1시간', hours: 1 },
  { label: '6시간', hours: 6 },
  { label: '1일', hours: 24 },
  { label: '7일', hours: 24 * 7 },
  { label: '1달', hours: 24 * 30 },
  { label: '3달', hours: 24 * 90 },
  { label: '6달', hours: 24 * 180 },
  { label: '1년', hours: 24 * 365 },
  { label: '전체', hours: undefined },
];

export function Dashboard() {
  const [timeRange, setTimeRange] = useState<number | undefined>(undefined);
  
  // Real-time data from WebSocket
  const { status: realtimeStatus, logs: realtimeLogs, pnlHistory, isConnected } = useRealtime();

  // Fallback status query - only poll when WebSocket is not connected
  const statusQuery = useQuery({
    queryKey: ['bot-status'],
    queryFn: botApi.getStatus,
    refetchInterval: (query) => {
      if (query.state.error) return false;
      // Reduce polling when WebSocket is connected
      return isConnected ? 30000 : 5000;
    },
    retry: 0,
  });

  // Use real-time status if available, otherwise fall back to polling
  const status = realtimeStatus || statusQuery.data || null;
  const isRunning = status?.running ?? false;
  const hasError = statusQuery.isError && !isConnected;
  const currentSessionId = status?.session_id;

  // PnL history query (for historical data with time range)
  // Include session_id in queryKey to invalidate cache when session changes
  const pnlQuery = useQuery({
    queryKey: ['pnl-history', timeRange, currentSessionId],
    queryFn: () => portfolioApi.getPnLHistory(1000, timeRange),
    refetchInterval: isRunning && !hasError ? (isConnected ? 30000 : 5000) : false,
    enabled: !hasError,
    retry: 0,
  });

  // Combine real-time PnL with historical data (deduplicated and sorted)
  const pnlData = useMemo(() => {
    const apiData = pnlQuery.data?.data || [];
    
    if (timeRange) {
      // Use API data when filtering by time
      return apiData;
    }
    
    // Combine and deduplicate by timestamp
    const combined = [...apiData];
    const existingTimestamps = new Set(apiData.map(d => d.timestamp));
    
    for (const item of pnlHistory) {
      if (!existingTimestamps.has(item.timestamp)) {
        combined.push(item);
        existingTimestamps.add(item.timestamp);
      }
    }
    
    // Sort by timestamp
    return combined.sort((a, b) => 
      new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    );
  }, [pnlQuery.data?.data, pnlHistory, timeRange]);

  const handleStatusChange = () => {
    statusQuery.refetch();
    pnlQuery.refetch();
  };

  return (
    <div className="space-y-6 animate-fadeIn">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">대시보드</h1>
          <p className="text-gray-500 text-sm mt-1">
            실시간 트레이딩 모니터링
            {isConnected && (
              <span className="ml-2 inline-flex items-center gap-1 text-emerald-600">
                <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
                실시간
              </span>
            )}
          </p>
        </div>
      </div>

      {/* API Connection Error */}
      {hasError && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
          <div className="flex items-start gap-3">
            <div className="p-2 bg-amber-100 rounded-lg">
              <svg className="w-5 h-5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <div>
              <h3 className="font-semibold text-amber-800">API 서버에 연결할 수 없습니다</h3>
              <p className="text-sm text-amber-600 mt-1">
                API 서버를 먼저 실행해주세요:
              </p>
              <code className="block mt-2 p-2 bg-amber-100 rounded text-xs text-amber-800 font-mono">
                python -m src.api.run --port 8002
              </code>
              <p className="text-xs text-gray-500 mt-2">
                웹에서 모든 기능(포트폴리오 최적화, 봇 시작/중지)을 제어할 수 있습니다.
              </p>
              <button 
                onClick={() => statusQuery.refetch()}
                className="mt-3 px-3 py-1.5 bg-amber-200 hover:bg-amber-300 text-amber-800 rounded-lg text-sm font-medium transition-colors"
              >
                다시 연결
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-5 items-stretch">
        {/* Bot Panel - Left Sidebar */}
        <div className="lg:col-span-1 flex">
          <BotPanel 
            status={status}
            isLoading={statusQuery.isLoading && !realtimeStatus}
            onStatusChange={handleStatusChange}
          />
        </div>

        {/* Performance Charts - Main Area */}
        <div className="lg:col-span-4 flex">
          <PerformanceCharts 
            data={pnlData} 
            isLoading={pnlQuery.isLoading && pnlHistory.length === 0}
            initialValue={status?.initial_value}
            currentPnL={status?.current_pnl}
            currentPnLPercent={status?.current_pnl_percent}
            currentTotalValue={status?.total_value}
            timeRange={timeRange}
            onTimeRangeChange={setTimeRange}
            timeRangeOptions={TIME_RANGES}
            quoteCurrency={status?.quote_currency || 'KRW'}
          />
        </div>
      </div>

      {/* Logs - Full Width (use real-time logs) */}
      <LogViewer 
        logs={realtimeLogs} 
        isLoading={false} 
      />
    </div>
  );
}
