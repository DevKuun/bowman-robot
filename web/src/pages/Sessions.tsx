import { useQuery } from '@tanstack/react-query';
import { useState, useEffect } from 'react';
import { Clock, ChevronRight, PlayCircle, StopCircle, Trash2, RefreshCw } from 'lucide-react';
import { sessionsApi, type TradingSession } from '../api/client';
import { SessionDetail } from './SessionDetail';
import { formatNumber, formatDateTimeKST, formatDuration } from '../utils/format';

export function Sessions() {
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [now, setNow] = useState(() => new Date());
  
  // Update current time every second for running sessions
  useEffect(() => {
    const interval = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(interval);
  }, []);
  
  const sessionsQuery = useQuery({
    queryKey: ['sessions'],
    queryFn: () => sessionsApi.getAll(),
    refetchInterval: 10000,
  });

  const sessions: TradingSession[] = sessionsQuery.data ?? [];
  
  const formatDateTime = (dateStr: string | null) => {
    if (!dateStr) return '-';
    return formatDateTimeKST(dateStr);
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

  const handleDeleteSession = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    if (confirm('이 세션을 삭제하시겠습니까? 관련된 모든 거래 기록도 삭제됩니다.')) {
      try {
        await sessionsApi.delete(sessionId);
        sessionsQuery.refetch();
      } catch (err) {
        console.error('Failed to delete session:', err);
      }
    }
  };

  // Show session detail view
  if (selectedSessionId) {
    return (
      <SessionDetail 
        sessionId={selectedSessionId}
        onBack={() => setSelectedSessionId(null)}
      />
    );
  }

  return (
    <div className="space-y-6 animate-fadeIn">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">세션 히스토리</h1>
          <p className="text-gray-500 text-sm mt-1">
            과거 거래 세션 기록 및 분석
          </p>
        </div>
        
        <button
          onClick={() => sessionsQuery.refetch()}
          disabled={sessionsQuery.isFetching}
          className="px-4 py-2 text-sm font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors flex items-center gap-2 disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${sessionsQuery.isFetching ? 'animate-spin' : ''}`} />
          새로고침
        </button>
      </div>

      {/* Session List */}
      <div className="card">
        <h3 className="text-lg font-semibold text-gray-800 mb-4 flex items-center gap-2">
          <Clock className="w-5 h-5" />
          거래 세션 목록
          {sessions.length > 0 && (
            <span className="text-sm font-normal text-gray-500">({sessions.length}개)</span>
          )}
        </h3>
        
        {sessionsQuery.isLoading ? (
          <div className="py-8 text-center">
            <div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full mx-auto mb-2"></div>
            <p className="text-gray-500">로딩 중...</p>
          </div>
        ) : sessions.length === 0 ? (
          <div className="py-12 text-center">
            <Clock className="w-12 h-12 mx-auto mb-3 text-gray-300" />
            <p className="text-gray-500">저장된 세션이 없습니다.</p>
            <p className="text-sm text-gray-400 mt-1">봇을 실행하면 세션이 자동으로 생성됩니다.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="text-left py-3 px-4 font-medium text-gray-500">세션</th>
                  <th className="text-left py-3 px-4 font-medium text-gray-500">거래소</th>
                  <th className="text-left py-3 px-4 font-medium text-gray-500">모드</th>
                  <th className="text-left py-3 px-4 font-medium text-gray-500">상태</th>
                  <th className="text-right py-3 px-4 font-medium text-gray-500">거래수</th>
                  <th className="text-right py-3 px-4 font-medium text-gray-500">손익</th>
                  <th className="text-left py-3 px-4 font-medium text-gray-500">시작</th>
                  <th className="text-left py-3 px-4 font-medium text-gray-500">종료</th>
                  <th className="text-right py-3 px-4 font-medium text-gray-500">진행 시간</th>
                  <th className="py-3 px-4"></th>
                </tr>
              </thead>
              <tbody>
                {sessions.map((session) => (
                  <tr 
                    key={session.id} 
                    className="border-b border-gray-50 hover:bg-gray-50/80 cursor-pointer transition-colors group"
                    onClick={() => setSelectedSessionId(session.session_id)}
                  >
                    <td className="py-3 px-4 font-mono text-xs text-gray-600">
                      {session.session_id.length > 35 
                        ? session.session_id.slice(0, 35) + '...' 
                        : session.session_id}
                    </td>
                    <td className="py-3 px-4 font-medium">{session.exchange}</td>
                    <td className="py-3 px-4">{getModeBadge(session.mode)}</td>
                    <td className="py-3 px-4">{getStatusBadge(session.status)}</td>
                    <td className="py-3 px-4 text-right tabular-nums">{session.total_trades}</td>
                    <td className="py-3 px-4 text-right">
                      {session.final_pnl !== null ? (
                        <span className={session.final_pnl >= 0 ? 'text-emerald-600' : 'text-red-500'}>
                          {session.final_pnl >= 0 ? '+' : ''}{formatNumber(session.final_pnl)}
                          <span className="text-xs ml-1">({session.final_pnl_percent?.toFixed(2)}%)</span>
                        </span>
                      ) : '-'}
                    </td>
                    <td className="py-3 px-4 text-gray-500">{formatDateTime(session.started_at)}</td>
                    <td className="py-3 px-4 text-gray-500">{formatDateTime(session.ended_at)}</td>
                    <td className="py-3 px-4 text-right text-gray-500 tabular-nums">
                      {session.started_at ? (() => {
                        // Parse timestamps as UTC (server stores in UTC without Z suffix)
                        const parseUTC = (s: string) => {
                          if (!s.endsWith('Z') && !s.includes('+')) return new Date(s + 'Z');
                          return new Date(s);
                        };
                        const start = parseUTC(session.started_at);
                        const end = session.ended_at ? parseUTC(session.ended_at) : now;
                        return formatDuration((end.getTime() - start.getTime()) / 1000);
                      })() : '-'}
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={(e) => handleDeleteSession(e, session.session_id)}
                          className="p-1 text-gray-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
                          title="세션 삭제"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                        <ChevronRight className="w-4 h-4 text-gray-400" />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Summary Stats */}
      {sessions.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="card p-4">
            <p className="text-sm text-gray-500">총 세션</p>
            <p className="text-2xl font-bold text-gray-800">{sessions.length}</p>
          </div>
          <div className="card p-4">
            <p className="text-sm text-gray-500">총 거래</p>
            <p className="text-2xl font-bold text-gray-800">
              {sessions.reduce((sum, s) => sum + s.total_trades, 0)}
            </p>
          </div>
          <div className="card p-4">
            <p className="text-sm text-gray-500">누적 손익</p>
            <p className={`text-2xl font-bold ${
              sessions.reduce((sum, s) => sum + (s.final_pnl || 0), 0) >= 0 
                ? 'text-emerald-600' 
                : 'text-red-500'
            }`}>
              {formatNumber(sessions.reduce((sum, s) => sum + (s.final_pnl || 0), 0))}
            </p>
          </div>
          <div className="card p-4">
            <p className="text-sm text-gray-500">총 수수료</p>
            <p className="text-2xl font-bold text-gray-800">
              {formatNumber(sessions.reduce((sum, s) => sum + s.total_fees, 0))}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
