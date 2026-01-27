import { Activity, Clock, Zap, BarChart3 } from 'lucide-react';
import type { BotStatus } from '../types';
import { formatDuration, formatNumber } from '../utils/format';

interface StatusCardProps {
  status: BotStatus | null;
  isLoading: boolean;
}

export function StatusCard({ status, isLoading }: StatusCardProps) {
  if (isLoading) {
    return (
      <div className="card animate-pulse">
        <div className="h-5 bg-gray-100 rounded w-1/3 mb-6"></div>
        <div className="grid grid-cols-2 gap-6">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-16 bg-gray-50 rounded-xl"></div>
          ))}
        </div>
      </div>
    );
  }

  const isRunning = status?.running ?? false;

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-lg font-semibold text-gray-800">봇 상태</h3>
        <span className={`badge ${isRunning ? 'badge-success' : 'badge-neutral'}`}>
          <span className={`w-2 h-2 rounded-full ${isRunning ? 'bg-green-500 animate-pulse' : 'bg-gray-400'}`}></span>
          {isRunning ? '실행 중' : '정지됨'}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="p-4 bg-gradient-to-br from-blue-50 to-blue-100/50 rounded-xl">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-blue-500 rounded-lg shadow-sm">
              <Activity className="w-4 h-4 text-white" />
            </div>
            <div>
              <p className="text-xs text-blue-600/70 font-medium">모드</p>
              <p className="font-semibold text-gray-800 capitalize">{status?.mode || '-'}</p>
            </div>
          </div>
        </div>

        <div className="p-4 bg-gradient-to-br from-purple-50 to-purple-100/50 rounded-xl">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-purple-500 rounded-lg shadow-sm">
              <Zap className="w-4 h-4 text-white" />
            </div>
            <div>
              <p className="text-xs text-purple-600/70 font-medium">거래소</p>
              <p className="font-semibold text-gray-800 uppercase">{status?.exchange || '-'}</p>
            </div>
          </div>
        </div>

        <div className="p-4 bg-gradient-to-br from-amber-50 to-amber-100/50 rounded-xl">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-amber-500 rounded-lg shadow-sm">
              <Clock className="w-4 h-4 text-white" />
            </div>
            <div>
              <p className="text-xs text-amber-600/70 font-medium">실행 시간</p>
              <p className="font-semibold text-gray-800">
                {status?.uptime_seconds ? formatDuration(status.uptime_seconds) : '-'}
              </p>
            </div>
          </div>
        </div>

        <div className="p-4 bg-gradient-to-br from-emerald-50 to-emerald-100/50 rounded-xl">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-emerald-500 rounded-lg shadow-sm">
              <BarChart3 className="w-4 h-4 text-white" />
            </div>
            <div>
              <p className="text-xs text-emerald-600/70 font-medium">거래 횟수</p>
              <p className="font-semibold text-gray-800 tabular-nums">{formatNumber(status?.total_trades ?? 0)}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
