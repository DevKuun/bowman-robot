import { useEffect, useRef, useState } from 'react';
import { AlertCircle, Info, AlertTriangle, Bug, ChevronDown } from 'lucide-react';
import type { LogEntry } from '../types';
import { formatDateTimeKST } from '../utils/format';

interface LogViewerProps {
  logs: LogEntry[];
  isLoading: boolean;
}

const levelConfig: Record<string, { icon: React.ReactNode; color: string; bg: string }> = {
  INFO: { 
    icon: <Info className="w-3.5 h-3.5" />, 
    color: 'text-blue-400',
    bg: 'bg-blue-500/10'
  },
  WARNING: { 
    icon: <AlertTriangle className="w-3.5 h-3.5" />, 
    color: 'text-amber-400',
    bg: 'bg-amber-500/10'
  },
  ERROR: { 
    icon: <AlertCircle className="w-3.5 h-3.5" />, 
    color: 'text-red-400',
    bg: 'bg-red-500/10'
  },
  DEBUG: { 
    icon: <Bug className="w-3.5 h-3.5" />, 
    color: 'text-gray-500',
    bg: 'bg-gray-500/10'
  },
};

export function LogViewer({ logs, isLoading }: LogViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [isAtBottom, setIsAtBottom] = useState(true);

  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  const handleScroll = () => {
    if (containerRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
      const atBottom = scrollHeight - scrollTop - clientHeight < 50;
      setIsAtBottom(atBottom);
      setAutoScroll(atBottom);
    }
  };

  const scrollToBottom = () => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
      setAutoScroll(true);
    }
  };

  if (isLoading) {
    return (
      <div className="card animate-pulse">
        <div className="h-5 bg-gray-100 rounded w-1/4 mb-4"></div>
        <div className="h-64 bg-gray-50 rounded-xl"></div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-800">로그</h3>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-400">{logs.length}개</span>
          <label className="flex items-center gap-2 text-sm text-gray-500 cursor-pointer">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
              className="w-4 h-4 rounded border-gray-300 text-blue-500 focus:ring-blue-500/20"
            />
            자동 스크롤
          </label>
        </div>
      </div>

      <div className="relative">
        <div 
          ref={containerRef}
          onScroll={handleScroll}
          className="h-[40rem] overflow-y-auto bg-slate-900 rounded-xl p-4 font-mono text-xs leading-relaxed"
        >
          {logs.length === 0 ? (
            <div className="h-full flex items-center justify-center text-slate-500">
              로그가 없습니다
            </div>
          ) : (
            <div className="space-y-1">
              {logs.map((log, index) => {
                const config = levelConfig[log.level] || levelConfig.INFO;
                return (
                  <div 
                    key={index} 
                    className={`flex items-start gap-2 py-1.5 px-2 rounded-lg hover:bg-white/5 transition-colors ${config.bg}`}
                  >
                    <span className="text-slate-500 shrink-0 tabular-nums">
                      {formatDateTimeKST(log.timestamp)}
                    </span>
                    <span className={`shrink-0 ${config.color}`}>
                      {config.icon}
                    </span>
                    <span className="text-slate-400 shrink-0">{log.module}:</span>
                    <span className="text-slate-200 break-all">{log.message}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {!isAtBottom && (
          <button
            onClick={scrollToBottom}
            className="absolute bottom-2 right-2 p-2 bg-blue-500 text-white rounded-lg shadow-lg hover:bg-blue-600 transition-colors"
          >
            <ChevronDown className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  );
}
