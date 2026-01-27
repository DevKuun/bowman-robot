import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { ArrowUpRight, ArrowDownRight, Filter, TrendingUp, DollarSign, Percent, Activity } from 'lucide-react';
import { tradesApi, botApi } from '../api/client';
import { TradeTable } from '../components/TradeTable';
import { formatNumber } from '../utils/format';
import { useRealtime } from '../contexts/RealtimeContext';

export function Trades() {
  const [sideFilter, setSideFilter] = useState<string>('');
  
  // Real-time data from WebSocket
  const { status: realtimeStatus, trades: realtimeTrades, tradesSummary: realtimeSummary, isConnected } = useRealtime();
  
  // Fallback query
  const statusQuery = useQuery({
    queryKey: ['bot-status'],
    queryFn: botApi.getStatus,
    refetchInterval: isConnected ? 30000 : 10000,
  });
  
  const isRunning = realtimeStatus?.running ?? statusQuery.data?.running ?? false;
  
  const tradesQuery = useQuery({
    queryKey: ['trades', sideFilter],
    queryFn: () => tradesApi.get({ limit: 200, side: sideFilter || undefined }),
    refetchInterval: isRunning ? (isConnected ? 30000 : 5000) : false,
  });

  const summaryQuery = useQuery({
    queryKey: ['trades-summary'],
    queryFn: tradesApi.getSummary,
    refetchInterval: isRunning ? (isConnected ? 30000 : 10000) : false,
  });

  const assetQuery = useQuery({
    queryKey: ['trades-by-asset'],
    queryFn: tradesApi.getByAsset,
    refetchInterval: isRunning ? (isConnected ? 30000 : 10000) : false,
  });

  // Use real-time summary if available
  const summary = realtimeSummary || summaryQuery.data;
  
  // Use real-time trades if available, otherwise fall back to API
  let trades = realtimeTrades.length > 0 ? realtimeTrades : (tradesQuery.data?.trades ?? []);
  if (sideFilter) {
    trades = trades.filter((t: any) => t.side.toUpperCase() === sideFilter.toUpperCase());
  }

  return (
    <div className="space-y-6 animate-fadeIn">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">거래 내역</h1>
          <p className="text-gray-500 text-sm mt-1">
            현재 세션 거래 기록 및 통계
            {isConnected && (
              <span className="ml-2 inline-flex items-center gap-1 text-emerald-600">
                <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
                실시간
              </span>
            )}
          </p>
        </div>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
        <div className="card p-4">
          <div className="stat-card">
            <span className="stat-label">총 거래</span>
            <span className="text-xl font-bold text-gray-800 tabular-nums">{formatNumber(summary?.total_trades ?? trades.length)}</span>
          </div>
        </div>
        <div className="card p-4">
          <div className="stat-card">
            <div className="flex items-center gap-1.5 text-emerald-600 mb-1">
              <ArrowUpRight className="w-4 h-4" />
              <span className="stat-label text-emerald-600">매수</span>
            </div>
            <span className="text-xl font-bold text-emerald-600 tabular-nums">{formatNumber(summary?.buy_trades ?? 0)}</span>
          </div>
        </div>
        <div className="card p-4">
          <div className="stat-card">
            <div className="flex items-center gap-1.5 text-red-500 mb-1">
              <ArrowDownRight className="w-4 h-4" />
              <span className="stat-label text-red-500">매도</span>
            </div>
            <span className="text-xl font-bold text-red-500 tabular-nums">{formatNumber(summary?.sell_trades ?? 0)}</span>
          </div>
        </div>
        <div className="card p-4">
          <div className="stat-card">
            <div className="flex items-center gap-1.5 mb-1">
              <TrendingUp className="w-4 h-4 text-blue-500" />
              <span className="stat-label">거래량</span>
            </div>
            <span className="text-lg font-bold text-gray-800 tabular-nums">
              {formatNumber((summary?.total_volume ?? 0) / 1000000, { maximumFractionDigits: 1 })}M
            </span>
          </div>
        </div>
        <div className="card p-4">
          <div className="stat-card">
            <div className="flex items-center gap-1.5 mb-1">
              <DollarSign className="w-4 h-4 text-purple-500" />
              <span className="stat-label">총 수수료</span>
            </div>
            <span className="text-lg font-bold text-gray-800 tabular-nums">
              {formatNumber(summary?.total_fees ?? 0, { maximumFractionDigits: 0 })}
            </span>
          </div>
        </div>
        <div className="card p-4">
          <div className="stat-card">
            <div className="flex items-center gap-1.5 mb-1">
              <Percent className="w-4 h-4 text-amber-500" />
              <span className="stat-label">평균 슬리피지</span>
            </div>
            <span className="text-lg font-bold text-amber-600 tabular-nums">
              {(summary?.avg_slippage ?? 0).toFixed(3)}%
            </span>
          </div>
        </div>
        <div className="card p-4">
          <div className="stat-card">
            <div className="flex items-center gap-1.5 mb-1">
              <Activity className="w-4 h-4 text-red-500" />
              <span className="stat-label">최대 슬리피지</span>
            </div>
            <span className="text-lg font-bold text-red-500 tabular-nums">
              {(summary?.max_slippage ?? 0).toFixed(3)}%
            </span>
          </div>
        </div>
      </div>

      {/* Trades by Asset */}
      {assetQuery.data?.assets && assetQuery.data.assets.length > 0 && (
        <div className="card">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">자산별 거래</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            {assetQuery.data.assets.slice(0, 12).map((asset: any) => (
              <div key={asset.symbol} className="p-4 bg-gray-50/80 rounded-xl hover:bg-gray-100/80 transition-colors">
                <p className="font-semibold text-gray-800 mb-1">{asset.symbol}</p>
                <p className="text-sm text-gray-500">{asset.trade_count}회</p>
                <div className="flex gap-3 text-xs mt-2">
                  <span className="text-emerald-600 font-medium">{asset.buy_count} 매수</span>
                  <span className="text-red-500 font-medium">{asset.sell_count} 매도</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Filter */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-gray-400" />
          <span className="text-sm text-gray-600">필터:</span>
        </div>
        <select
          value={sideFilter}
          onChange={(e) => setSideFilter(e.target.value)}
          className="input w-auto"
        >
          <option value="">전체 거래</option>
          <option value="BUY">매수만</option>
          <option value="SELL">매도만</option>
        </select>
      </div>

      {/* Trade Table */}
      <TradeTable 
        trades={trades} 
        isLoading={tradesQuery.isLoading && realtimeTrades.length === 0}
      />
    </div>
  );
}
