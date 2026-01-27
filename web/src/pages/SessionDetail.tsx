import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { 
  ArrowLeft, ArrowUpRight, ArrowDownRight, TrendingUp,
  DollarSign, Percent, Activity, Clock, PlayCircle, StopCircle
} from 'lucide-react';
import { sessionsApi } from '../api/client';
import { TradeTable } from '../components/TradeTable';
import { PerformanceCharts } from '../components/PerformanceCharts';
import { formatNumber, formatFullDateTimeKST } from '../utils/format';

interface SessionDetailProps {
  sessionId: string;
  onBack: () => void;
}

export function SessionDetail({ sessionId, onBack }: SessionDetailProps) {
  const [activeTab, setActiveTab] = useState<'overview' | 'trades'>('overview');
  
  const { data: detail, isLoading, error } = useQuery({
    queryKey: ['session-detail', sessionId],
    queryFn: () => sessionsApi.getDetail(sessionId),
  });

  const formatDateTime = (dateStr: string | null) => {
    if (!dateStr) return '-';
    return formatFullDateTimeKST(dateStr);
  };
  
  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'running':
        return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-700"><PlayCircle className="w-3 h-3" />실행중</span>;
      case 'stopped':
        return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600"><StopCircle className="w-3 h-3" />중지됨</span>;
      case 'completed':
        return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700">완료</span>;
      default:
        return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600">{status}</span>;
    }
  };
  
  const getModeBadge = (mode: string) => {
    return mode === 'paper' 
      ? <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700">Paper</span>
      : <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700">Live</span>;
  };

  if (isLoading) {
    return (
      <div className="space-y-6 animate-fadeIn">
        <div className="flex items-center gap-4">
          <button onClick={onBack} className="p-2 hover:bg-gray-100 rounded-lg">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div className="h-8 bg-gray-100 rounded w-64 animate-pulse"></div>
        </div>
        <div className="grid grid-cols-4 gap-4">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="card h-24 animate-pulse bg-gray-50"></div>
          ))}
        </div>
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-4">
          <button onClick={onBack} className="p-2 hover:bg-gray-100 rounded-lg">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <h1 className="text-2xl font-bold text-gray-900">세션을 찾을 수 없습니다</h1>
        </div>
      </div>
    );
  }

  const { session, trades, pnl_history, summary, assets } = detail;
  
  // Convert PnL history to chart format
  const pnlData = pnl_history.map(p => ({
    timestamp: p.timestamp,
    total_value: p.total_value,
    pnl: p.pnl,
    pnl_percent: p.pnl_percent,
    btc_return: p.btc_return ?? undefined,
    eth_return: p.eth_return ?? undefined,
  }));
  
  // Calculate duration
  const startTime = session.started_at ? new Date(session.started_at) : null;
  const endTime = session.ended_at ? new Date(session.ended_at) : null;
  let duration = '-';
  if (startTime && endTime) {
    const diffMs = endTime.getTime() - startTime.getTime();
    const hours = Math.floor(diffMs / (1000 * 60 * 60));
    const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
    duration = hours > 0 ? `${hours}시간 ${minutes}분` : `${minutes}분`;
  }

  return (
    <div className="space-y-6 animate-fadeIn">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button 
            onClick={onBack} 
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-gray-900">{session.exchange}</h1>
              {getModeBadge(session.mode)}
              {getStatusBadge(session.status)}
            </div>
            <p className="text-sm text-gray-500 font-mono mt-1">{session.session_id}</p>
          </div>
        </div>
        
        {/* Final PnL */}
        {session.final_pnl !== null && (
          <div className="text-right">
            <div className={`text-3xl font-bold ${session.final_pnl >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
              {session.final_pnl >= 0 ? '+' : ''}{formatNumber(session.final_pnl)}
              <span className="text-lg ml-1">
                ({session.final_pnl_percent?.toFixed(2)}%)
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Session Info */}
      <div className="card bg-gradient-to-r from-blue-50 to-indigo-50 border-blue-200">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <span className="text-gray-500">시작 시간</span>
            <p className="font-medium">{formatDateTime(session.started_at)}</p>
          </div>
          <div>
            <span className="text-gray-500">종료 시간</span>
            <p className="font-medium">{formatDateTime(session.ended_at)}</p>
          </div>
          <div>
            <span className="text-gray-500">진행 시간</span>
            <p className="font-medium">{duration}</p>
          </div>
          <div>
            <span className="text-gray-500">초기 자본</span>
            <p className="font-medium">{session.initial_balance ? formatNumber(session.initial_balance) : '-'}</p>
          </div>
        </div>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
        <div className="card p-4">
          <div className="stat-card">
            <span className="stat-label">총 거래</span>
            <span className="text-xl font-bold text-gray-800 tabular-nums">{formatNumber(summary.total_trades)}</span>
          </div>
        </div>
        <div className="card p-4">
          <div className="stat-card">
            <div className="flex items-center gap-1.5 text-emerald-600 mb-1">
              <ArrowUpRight className="w-4 h-4" />
              <span className="stat-label text-emerald-600">매수</span>
            </div>
            <span className="text-xl font-bold text-emerald-600 tabular-nums">{formatNumber(summary.buy_trades)}</span>
          </div>
        </div>
        <div className="card p-4">
          <div className="stat-card">
            <div className="flex items-center gap-1.5 text-red-500 mb-1">
              <ArrowDownRight className="w-4 h-4" />
              <span className="stat-label text-red-500">매도</span>
            </div>
            <span className="text-xl font-bold text-red-500 tabular-nums">{formatNumber(summary.sell_trades)}</span>
          </div>
        </div>
        <div className="card p-4">
          <div className="stat-card">
            <div className="flex items-center gap-1.5 mb-1">
              <TrendingUp className="w-4 h-4 text-blue-500" />
              <span className="stat-label">거래량</span>
            </div>
            <span className="text-lg font-bold text-gray-800 tabular-nums">
              {(() => {
                const vol = summary.total_volume;
                if (vol >= 1000000) return `${formatNumber(vol / 1000000, { maximumFractionDigits: 1 })}M`;
                if (vol >= 1000) return `${formatNumber(vol / 1000, { maximumFractionDigits: 1 })}K`;
                return formatNumber(vol, { maximumFractionDigits: 0 });
              })()}
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
              {formatNumber(summary.total_fees, { maximumFractionDigits: 0 })}
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
              {summary.avg_slippage.toFixed(3)}%
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
              {summary.max_slippage.toFixed(3)}%
            </span>
          </div>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-2 border-b border-gray-200">
        <button
          onClick={() => setActiveTab('overview')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'overview' 
              ? 'border-blue-500 text-blue-600' 
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          수익률 추이
        </button>
        <button
          onClick={() => setActiveTab('trades')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'trades' 
              ? 'border-blue-500 text-blue-600' 
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          거래 내역 ({trades.length})
        </button>
      </div>

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* Performance Charts */}
          {pnlData.length > 0 ? (
            <PerformanceCharts 
              data={pnlData}
              isLoading={false}
              initialValue={session.initial_balance || undefined}
              quoteCurrency={session.exchange?.toLowerCase() === 'binance' ? 'USDT' : 'KRW'}
            />
          ) : (
            <div className="card p-8 text-center text-gray-500">
              <Clock className="w-12 h-12 mx-auto mb-3 text-gray-300" />
              <p>수익률 데이터가 없습니다.</p>
              <p className="text-sm mt-1">세션 진행 중에 기록된 스냅샷이 없습니다.</p>
            </div>
          )}

          {/* Assets Breakdown */}
          {assets && assets.length > 0 && (
            <div className="card">
              <h3 className="text-lg font-semibold text-gray-800 mb-4">자산별 거래</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
                {assets.slice(0, 12).map((asset) => (
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
        </div>
      )}

      {activeTab === 'trades' && (
        <TradeTable 
          trades={trades.map(t => ({
            ...t,
            timestamp: t.created_at || t.executed_at || '',
          })) as any} 
          isLoading={false}
        />
      )}
    </div>
  );
}
