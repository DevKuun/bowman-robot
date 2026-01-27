import { useState, useEffect } from 'react';
import { Play, Square, RefreshCw, Sparkles, CheckCircle, AlertCircle } from 'lucide-react';
import { botApi } from '../api/client';
import type { BotStatus } from '../types';
import { formatNumber, formatDateTimeKST } from '../utils/format';

interface BotControlProps {
  status: BotStatus | null;
  onStatusChange: () => void;
}

export function BotControl({ status, onStatusChange }: BotControlProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [isOptimizing, setIsOptimizing] = useState(false);
  const [exchange, setExchange] = useState('bithumb');
  const [initialBalance, setInitialBalance] = useState(5000000);
  const [riskLevel, setRiskLevel] = useState(2);
  const [error, setError] = useState<string | null>(null);
  const [weightsInfo, setWeightsInfo] = useState<{
    exists: boolean;
    assetCount?: number;
    createdAt?: string;
  } | null>(null);

  const isRunning = status?.running ?? false;

  // Check portfolio weights when exchange or risk level changes
  useEffect(() => {
    checkWeights();
  }, [exchange, riskLevel]);

  // Poll optimization status while optimizing
  useEffect(() => {
    if (!isOptimizing) return;
    
    const interval = setInterval(async () => {
      try {
        const status = await botApi.getOptimizationStatus();
        if (!status.running) {
          setIsOptimizing(false);
          if (status.status === 'completed') {
            checkWeights();
          } else if (status.status === 'error') {
            setError(status.error || '포트폴리오 최적화 실패');
          }
        }
      } catch {
        // Ignore polling errors
      }
    }, 2000);
    
    return () => clearInterval(interval);
  }, [isOptimizing, exchange, riskLevel]);

  const checkWeights = async () => {
    try {
      const result = await botApi.getWeights(exchange, riskLevel);
      setWeightsInfo({
        exists: result.exists,
        assetCount: result.asset_count,
        createdAt: result.created_at || undefined,
      });
    } catch {
      setWeightsInfo(null);
    }
  };

  const handleOptimize = async () => {
    setIsOptimizing(true);
    setError(null);
    try {
      const result = await botApi.optimize({ exchange, force: true });
      if (result.status === 'skipped') {
        setIsOptimizing(false);
        checkWeights();
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || '포트폴리오 최적화 실패');
      setIsOptimizing(false);
    }
  };

  const handleStart = async (skipOptimization: boolean = false) => {
    setIsLoading(true);
    setError(null);
    try {
      await botApi.start({
        exchange,
        mode: 'paper',
        initial_balance: initialBalance,
        risk_level: riskLevel,
        realistic_execution: true,
        skip_optimization: skipOptimization,
      });
      onStatusChange();
    } catch (err: any) {
      setError(err.response?.data?.detail || '봇 시작에 실패했습니다');
    } finally {
      setIsLoading(false);
    }
  };

  const handleStop = async () => {
    setIsLoading(true);
    setError(null);
    try {
      await botApi.stop();
      onStatusChange();
    } catch (err: any) {
      setError(err.response?.data?.detail || '봇 중지에 실패했습니다');
    } finally {
      setIsLoading(false);
    }
  };

  const riskLabels = ['매우 안전', '안전', '보통', '공격적', '매우 공격적'];

  return (
    <div className="card">
      <h3 className="text-lg font-semibold text-gray-800 mb-5">봇 제어</h3>

      {!isRunning && (
        <div className="space-y-4 mb-5">
          <div>
            <label className="block text-sm font-medium text-gray-600 mb-2">
              거래소
            </label>
            <select
              value={exchange}
              onChange={(e) => setExchange(e.target.value)}
              className="input"
              disabled={isOptimizing}
            >
              <option value="upbit">업비트 (Upbit)</option>
              <option value="bithumb">빗썸 (Bithumb)</option>
              <option value="korbit">코빗 (Korbit)</option>
              <option value="binance">바이낸스 (Binance)</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-600 mb-2">
              초기 자본 ({exchange === 'binance' ? 'USDT' : 'KRW'})
            </label>
            <input
              type="text"
              value={formatNumber(initialBalance)}
              onChange={(e) => {
                const num = parseInt(e.target.value.replace(/[^0-9]/g, ''));
                if (!isNaN(num)) setInitialBalance(num);
              }}
              className="input tabular-nums"
              disabled={isOptimizing}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-600 mb-2">
              리스크 레벨
            </label>
            <input
              type="range"
              min="0"
              max="4"
              value={riskLevel}
              onChange={(e) => setRiskLevel(Number(e.target.value))}
              className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-500"
              disabled={isOptimizing}
            />
            <div className="flex justify-between mt-2">
              <span className="text-xs text-gray-400">안전</span>
              <span className="text-sm font-medium text-blue-600">{riskLabels[riskLevel]}</span>
              <span className="text-xs text-gray-400">공격적</span>
            </div>
          </div>

          {/* Portfolio Weights Status */}
          <div className="p-3 bg-gray-50 rounded-xl">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600">포트폴리오 가중치</span>
              {weightsInfo?.exists ? (
                <div className="flex items-center gap-1.5 text-emerald-600">
                  <CheckCircle className="w-4 h-4" />
                  <span className="text-sm font-medium">{weightsInfo.assetCount}개 자산</span>
                </div>
              ) : (
                <div className="flex items-center gap-1.5 text-amber-600">
                  <AlertCircle className="w-4 h-4" />
                  <span className="text-sm font-medium">없음</span>
                </div>
              )}
            </div>
            {weightsInfo?.createdAt && (
              <p className="text-xs text-gray-400 mt-1">
                생성: {formatDateTimeKST(weightsInfo.createdAt)}
              </p>
            )}
          </div>
        </div>
      )}

      {error && (
        <div className="mb-4 p-3 bg-red-50 text-red-600 rounded-xl text-sm border border-red-100">
          {error}
        </div>
      )}

      <div className="flex flex-col gap-3">
        {isRunning ? (
          <button
            onClick={handleStop}
            disabled={isLoading}
            className="btn btn-danger"
          >
            {isLoading ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Square className="w-4 h-4" />
            )}
            봇 중지
          </button>
        ) : (
          <>
            {/* Optimize Only Button */}
            <button
              onClick={handleOptimize}
              disabled={isLoading || isOptimizing}
              className="btn bg-purple-500 hover:bg-purple-600 text-white"
            >
              {isOptimizing ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  최적화 중...
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  포트폴리오 최적화
                </>
              )}
            </button>

            {/* Start with existing weights (if available) */}
            {weightsInfo?.exists && (
              <button
                onClick={() => handleStart(true)}
                disabled={isLoading || isOptimizing}
                className="btn btn-success"
              >
                {isLoading ? (
                  <RefreshCw className="w-4 h-4 animate-spin" />
                ) : (
                  <Play className="w-4 h-4" />
                )}
                모의투자 시작 (기존 가중치)
              </button>
            )}

            {/* Start with new optimization */}
            <button
              onClick={() => handleStart(false)}
              disabled={isLoading || isOptimizing}
              className="btn bg-blue-500 hover:bg-blue-600 text-white"
            >
              {isLoading ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <Play className="w-4 h-4" />
              )}
              모의투자 시작 (최적화 포함)
            </button>
          </>
        )}
      </div>
    </div>
  );
}
