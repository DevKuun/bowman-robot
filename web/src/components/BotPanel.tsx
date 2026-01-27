import { useState, useEffect, useMemo } from 'react';
import { 
  Play, Square, RefreshCw, Sparkles, CheckCircle, AlertCircle,
  Activity, Clock, Zap, BarChart3, TrendingUp, TrendingDown,
  ChevronDown, ChevronUp, Wallet, Target, X, XCircle, Percent, ArrowUpDown
} from 'lucide-react';
import { botApi } from '../api/client';
import type { BotStatus } from '../types';
import { formatNumber, formatDateTimeKST, formatDuration, formatPercent } from '../utils/format';
import { useRealtime } from '../contexts/RealtimeContext';

interface BotPanelProps {
  status: BotStatus | null;
  isLoading: boolean;
  onStatusChange: () => void;
}

// Load saved settings from localStorage
const loadSavedSettings = () => {
  try {
    const saved = localStorage.getItem('bowman-bot-settings');
    if (saved) {
      return JSON.parse(saved);
    }
  } catch {
    // Ignore parse errors
  }
  return { exchange: 'bithumb', initialBalance: 100000000, riskLevel: 2, tradingMode: 'paper' };
};

export function BotPanel({ status, isLoading, onStatusChange }: BotPanelProps) {
  const savedSettings = loadSavedSettings();
  const [isStarting, setIsStarting] = useState(false);
  const [isOptimizing, setIsOptimizing] = useState(false);
  const [exchange, setExchange] = useState(savedSettings.exchange);
  const [initialBalance, setInitialBalance] = useState(savedSettings.initialBalance);
  const [riskLevel, setRiskLevel] = useState(savedSettings.riskLevel);
  const [tradingMode, setTradingMode] = useState<'paper' | 'live'>(savedSettings.tradingMode || 'paper');
  const [error, setError] = useState<string | null>(null);
  const [showWeightsDetail, setShowWeightsDetail] = useState(false);
  const [weightsDetail, setWeightsDetail] = useState<Record<string, number> | null>(null);
  const [weightsInfo, setWeightsInfo] = useState<{
    exists: boolean;
    assetCount?: number;
    createdAt?: string;
  } | null>(null);

  // Get real-time data for statistics
  const { trades, portfolioSummary, tradesSummary } = useRealtime();

  const isRunning = status?.running ?? false;
  const currentPnL = status?.current_pnl ?? 0;
  const currentPnLPercent = status?.current_pnl_percent ?? 0;
  const isPositive = currentPnL >= 0;

  // Use WebSocket summary if available, otherwise calculate from trades
  const tradeStats = useMemo(() => {
    // Use real-time summary from WebSocket (same calculation as backend)
    if (tradesSummary && tradesSummary.total_trades > 0) {
      const total = tradesSummary.buy_trades + tradesSummary.sell_trades;
      const buyRatio = total > 0 ? (tradesSummary.buy_trades / total) * 100 : 50;
      return {
        avgSlippage: tradesSummary.avg_slippage,
        maxSlippage: tradesSummary.max_slippage,
        buyCount: tradesSummary.buy_trades,
        sellCount: tradesSummary.sell_trades,
        buyRatio
      };
    }
    
    // Fallback: calculate from trades
    if (!trades || trades.length === 0) {
      return { avgSlippage: 0, maxSlippage: 0, buyCount: 0, sellCount: 0, buyRatio: 0 };
    }

    const slippages: number[] = [];
    let buyCount = 0;
    let sellCount = 0;

    trades.forEach(t => {
      // Parse slippage - handle both string and number formats
      const slipValue = t.slippage_percent;
      if (slipValue !== undefined && slipValue !== null) {
        let slip: number;
        if (typeof slipValue === 'string') {
          slip = parseFloat(slipValue.replace('%', ''));
        } else {
          slip = slipValue;
        }
        if (!isNaN(slip)) slippages.push(slip);
      }
      // Count buy/sell
      const side = (t.side || '').toUpperCase();
      if (side === 'BUY' || side === 'BID') buyCount++;
      else if (side === 'SELL' || side === 'ASK') sellCount++;
    });

    const avgSlippage = slippages.length > 0 
      ? slippages.reduce((a, b) => a + b, 0) / slippages.length 
      : 0;
    const maxSlippage = slippages.length > 0 ? Math.max(...slippages) : 0;
    const total = buyCount + sellCount;
    const buyRatio = total > 0 ? (buyCount / total) * 100 : 50;

    return { avgSlippage, maxSlippage, buyCount, sellCount, buyRatio };
  }, [trades, tradesSummary]);

  // Cash weight from portfolio summary
  const cashWeight = portfolioSummary?.allocation?.cash_percent ?? 0;

  // Save settings to localStorage when they change
  useEffect(() => {
    localStorage.setItem('bowman-bot-settings', JSON.stringify({
      exchange,
      initialBalance,
      riskLevel,
      tradingMode
    }));
  }, [exchange, initialBalance, riskLevel, tradingMode]);

  // Check portfolio weights and optimization status on mount and when exchange/risk changes
  useEffect(() => {
    checkWeights();
    checkOptimizationStatus();
  }, [exchange, riskLevel]);

  const checkOptimizationStatus = async () => {
    try {
      const result = await botApi.getOptimizationStatus();
      setIsOptimizing(result.running);
    } catch {
      // Ignore errors
    }
  };

  // Poll optimization status while optimizing
  useEffect(() => {
    if (!isOptimizing) return;
    
    const interval = setInterval(async () => {
      try {
        const result = await botApi.getOptimizationStatus();
        if (!result.running) {
          setIsOptimizing(false);
          if (result.status === 'completed') {
            checkWeights();
          } else if (result.status === 'cancelled') {
            // Cancelled - just update status, no error
          } else if (result.status === 'error') {
            setError(result.error || '포트폴리오 최적화 실패');
          }
        }
      } catch {
        // Ignore polling errors
      }
    }, 2000);
    
    return () => clearInterval(interval);
  }, [isOptimizing]);

  const checkWeights = async () => {
    try {
      const result = await botApi.getWeights(exchange, riskLevel);
      setWeightsInfo({
        exists: result.exists,
        assetCount: result.asset_count,
        createdAt: result.created_at || undefined,
      });
      if (result.weights) {
        setWeightsDetail(result.weights);
      }
    } catch {
      setWeightsInfo(null);
      setWeightsDetail(null);
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

  const handleCancelOptimize = async () => {
    try {
      await botApi.cancelOptimization();
      setIsOptimizing(false);
    } catch (err: any) {
      setError(err.response?.data?.detail || '최적화 취소 실패');
    }
  };

  const handleStart = async (skipOptimization: boolean = false) => {
    setIsStarting(true);
    setError(null);
    try {
      await botApi.start({
        exchange,
        mode: tradingMode,
        initial_balance: tradingMode === 'paper' ? initialBalance : undefined,
        risk_level: riskLevel,
        realistic_execution: true,
        skip_optimization: skipOptimization,
      });
      onStatusChange();
    } catch (err: any) {
      setError(err.response?.data?.detail || '봇 시작에 실패했습니다');
    } finally {
      setIsStarting(false);
    }
  };

  const handleStop = async () => {
    setIsStarting(true);
    setError(null);
    try {
      await botApi.stop();
      onStatusChange();
    } catch (err: any) {
      setError(err.response?.data?.detail || '봇 중지에 실패했습니다');
    } finally {
      setIsStarting(false);
    }
  };

  const riskLabels = ['매우 안전', '안전', '보통', '공격적', '매우 공격적'];

  if (isLoading) {
    return (
      <div className="card animate-pulse">
        <div className="h-6 bg-gray-100 rounded w-1/3 mb-4"></div>
        <div className="space-y-4">
          <div className="h-20 bg-gray-50 rounded-xl"></div>
          <div className="h-32 bg-gray-50 rounded-xl"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="card w-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <h3 className="text-lg font-semibold text-gray-800">트레이딩 봇</h3>
        <span className={`badge ${isRunning ? 'badge-success' : 'badge-neutral'}`}>
          <span className={`w-2 h-2 rounded-full ${isRunning ? 'bg-green-500 animate-pulse' : 'bg-gray-400'}`}></span>
          {isRunning ? '실행 중' : '정지됨'}
        </span>
      </div>

      {isRunning ? (
        /* Running State */
        <div className="space-y-3 flex-1 flex flex-col">
          {/* Status Grid */}
          <div className="grid grid-cols-2 gap-2">
            <div className="p-2.5 bg-gradient-to-br from-blue-50 to-blue-100/50 rounded-lg">
              <div className="flex items-center gap-1.5">
                <Activity className="w-3.5 h-3.5 text-blue-500" />
                <span className="text-xs text-blue-600/70">모드</span>
              </div>
              <p className="font-semibold text-gray-800 capitalize text-sm mt-0.5">{status?.mode || 'paper'}</p>
            </div>
            <div className="p-2.5 bg-gradient-to-br from-purple-50 to-purple-100/50 rounded-lg">
              <div className="flex items-center gap-1.5">
                <Zap className="w-3.5 h-3.5 text-purple-500" />
                <span className="text-xs text-purple-600/70">거래소</span>
              </div>
              <p className="font-semibold text-gray-800 uppercase text-sm mt-0.5">{status?.exchange || '-'}</p>
            </div>
            <div className="p-2.5 bg-gradient-to-br from-amber-50 to-amber-100/50 rounded-lg">
              <div className="flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-amber-500" />
                <span className="text-xs text-amber-600/70">실행 시간</span>
              </div>
              <p className="font-semibold text-gray-800 text-sm mt-0.5">
                {status?.uptime_seconds ? formatDuration(status.uptime_seconds) : '-'}
              </p>
            </div>
            <div className="p-2.5 bg-gradient-to-br from-emerald-50 to-emerald-100/50 rounded-lg">
              <div className="flex items-center gap-1.5">
                <BarChart3 className="w-3.5 h-3.5 text-emerald-500" />
                <span className="text-xs text-emerald-600/70">거래 횟수</span>
              </div>
              <p className="font-semibold text-gray-800 tabular-nums text-sm mt-0.5">{formatNumber(status?.total_trades ?? 0)}</p>
            </div>
          </div>

          {/* Current PnL */}
          <div className={`p-3 rounded-xl ${isPositive ? 'bg-emerald-50' : 'bg-red-50'}`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {isPositive ? (
                  <TrendingUp className="w-5 h-5 text-emerald-500" />
                ) : (
                  <TrendingDown className="w-5 h-5 text-red-500" />
                )}
                <span className={`text-sm font-medium ${isPositive ? 'text-emerald-600' : 'text-red-600'}`}>
                  현재 손익
                </span>
              </div>
              <div className="text-right">
                <p className={`text-lg font-bold tabular-nums ${isPositive ? 'text-emerald-600' : 'text-red-500'}`}>
                  {isPositive ? '+' : ''}{formatNumber(currentPnL, { maximumFractionDigits: 0 })}
                  <span className="text-xs font-normal ml-1">{status?.quote_currency || 'KRW'}</span>
                </p>
                <p className={`text-xs ${isPositive ? 'text-emerald-500' : 'text-red-400'}`}>
                  {formatPercent(currentPnLPercent)}
                </p>
              </div>
            </div>
          </div>

          {/* Additional Stats */}
          <div className="grid grid-cols-2 gap-2">
            <div className="p-2.5 bg-gray-50 rounded-lg">
              <div className="flex items-center gap-1.5">
                <Wallet className="w-3.5 h-3.5 text-gray-500" />
                <span className="text-xs text-gray-500">초기 자본</span>
              </div>
              <p className="font-semibold text-gray-800 tabular-nums text-sm mt-0.5">
                {formatNumber(status?.initial_value ?? initialBalance, { maximumFractionDigits: 0 })}
              </p>
            </div>
            <div className="p-2.5 bg-gray-50 rounded-lg">
              <div className="flex items-center gap-1.5">
                <Target className="w-3.5 h-3.5 text-gray-500" />
                <span className="text-xs text-gray-500">리스크 레벨</span>
              </div>
              <p className="font-semibold text-gray-800 text-sm mt-0.5">
                {riskLabels[status?.risk_level ?? 2]}
              </p>
            </div>
          </div>

          {/* More Stats */}
          <div className="grid grid-cols-2 gap-2">
            <div className="p-2.5 bg-gray-50 rounded-lg">
              <div className="flex items-center gap-1.5">
                <Target className="w-3.5 h-3.5 text-gray-500" />
                <span className="text-xs text-gray-500">포트폴리오</span>
              </div>
              <p className="font-semibold text-gray-800 text-sm mt-0.5">
                {weightsInfo?.assetCount ?? '-'}개 자산
              </p>
            </div>
            <div className="p-2.5 bg-gray-50 rounded-lg">
              <div className="flex items-center gap-1.5">
                <BarChart3 className="w-3.5 h-3.5 text-gray-500" />
                <span className="text-xs text-gray-500">총 수수료</span>
              </div>
              <p className="font-semibold text-gray-800 tabular-nums text-sm mt-0.5">
                {formatNumber(status?.total_fees ?? 0, { maximumFractionDigits: 0 })}
              </p>
            </div>
          </div>

          {/* Slippage & Trade Ratio Stats */}
          <div className="grid grid-cols-2 gap-2">
            <div className="p-2.5 bg-gray-50 rounded-lg">
              <div className="flex items-center gap-1.5">
                <Percent className="w-3.5 h-3.5 text-gray-500" />
                <span className="text-xs text-gray-500">평균 슬리피지</span>
              </div>
              <p className="font-semibold text-gray-800 tabular-nums text-sm mt-0.5">
                {tradeStats.avgSlippage.toFixed(3)}%
              </p>
            </div>
            <div className="p-2.5 bg-gray-50 rounded-lg">
              <div className="flex items-center gap-1.5">
                <Percent className="w-3.5 h-3.5 text-gray-500" />
                <span className="text-xs text-gray-500">최대 슬리피지</span>
              </div>
              <p className="font-semibold text-gray-800 tabular-nums text-sm mt-0.5">
                {tradeStats.maxSlippage.toFixed(3)}%
              </p>
            </div>
          </div>

          {/* Buy/Sell Ratio & Cash Weight */}
          <div className="grid grid-cols-2 gap-2">
            <div className="p-2.5 bg-gray-50 rounded-lg">
              <div className="flex items-center gap-1.5">
                <ArrowUpDown className="w-3.5 h-3.5 text-gray-500" />
                <span className="text-xs text-gray-500">매수/매도</span>
              </div>
              <div className="flex items-center gap-1 mt-0.5">
                <span className="text-xs text-emerald-600 font-semibold">{tradeStats.buyCount}</span>
                <span className="text-xs text-gray-400">/</span>
                <span className="text-xs text-red-500 font-semibold">{tradeStats.sellCount}</span>
                <span className="text-xs text-gray-400 ml-1">({tradeStats.buyRatio.toFixed(0)}%)</span>
              </div>
            </div>
            <div className="p-2.5 bg-gray-50 rounded-lg">
              <div className="flex items-center gap-1.5">
                <Wallet className="w-3.5 h-3.5 text-gray-500" />
                <span className="text-xs text-gray-500">현금 비중</span>
              </div>
              <p className="font-semibold text-gray-800 tabular-nums text-sm mt-0.5">
                {cashWeight.toFixed(1)}%
              </p>
            </div>
          </div>

          {/* Iteration Info */}
          <div className="p-2.5 bg-gradient-to-br from-slate-50 to-slate-100/50 rounded-lg">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <Activity className="w-3.5 h-3.5 text-slate-500" />
                <span className="text-xs text-slate-500">반복 횟수</span>
              </div>
              <p className="font-semibold text-gray-800 tabular-nums text-sm">
                #{formatNumber(status?.iteration_count ?? 0)}
              </p>
            </div>
          </div>

          {/* Stop Button */}
          <button
            onClick={handleStop}
            disabled={isStarting}
            className="btn btn-danger w-full mt-auto"
          >
            {isStarting ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Square className="w-4 h-4" />
            )}
            봇 중지
          </button>
        </div>
      ) : (
        /* Stopped State - Configuration */
        <div className="space-y-4 flex-1 flex flex-col">
          {/* Quick Settings */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5">거래소</label>
              <select
                value={exchange}
                onChange={(e) => setExchange(e.target.value)}
                className="input text-sm py-2"
                disabled={isOptimizing}
              >
                <option value="upbit">업비트</option>
                <option value="bithumb">빗썸</option>
                <option value="korbit">코빗</option>
                <option value="binance">바이낸스</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5">모드</label>
              <div className="flex gap-1">
                <button
                  onClick={() => setTradingMode('paper')}
                  className={`flex-1 py-2 text-xs font-medium rounded-lg transition-colors ${
                    tradingMode === 'paper'
                      ? 'bg-amber-100 text-amber-700 border border-amber-300'
                      : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                  }`}
                  disabled={isOptimizing}
                >
                  Paper
                </button>
                <button
                  onClick={() => setTradingMode('live')}
                  className={`flex-1 py-2 text-xs font-medium rounded-lg transition-colors ${
                    tradingMode === 'live'
                      ? 'bg-red-100 text-red-700 border border-red-300'
                      : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                  }`}
                  disabled={isOptimizing}
                >
                  Live
                </button>
              </div>
            </div>
          </div>
          
          {/* Initial Balance (only for Paper mode) */}
          {tradingMode === 'paper' && (
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5">
                초기 자본 ({exchange === 'binance' ? 'USDT' : 'KRW'})
              </label>
              <input
                type="text"
                value={formatNumber(initialBalance)}
                onChange={(e) => {
                  const num = parseInt(e.target.value.replace(/[^0-9]/g, ''));
                  if (!isNaN(num)) setInitialBalance(num);
                }}
                className="input text-sm py-2 tabular-nums"
                disabled={isOptimizing}
              />
            </div>
          )}
          
          {/* Live Mode Warning */}
          {tradingMode === 'live' && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-xs text-red-700 font-medium">
                ⚠️ 실제 자산으로 거래합니다. 등록된 API 키의 계정에서 실제 매매가 실행됩니다.
              </p>
            </div>
          )}

          {/* Risk Level */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-xs font-medium text-gray-500">리스크</label>
              <span className="text-xs font-semibold text-blue-600">{riskLabels[riskLevel]}</span>
            </div>
            <input
              type="range"
              min="0"
              max="4"
              value={riskLevel}
              onChange={(e) => setRiskLevel(Number(e.target.value))}
              className="w-full h-1.5 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-500"
              disabled={isOptimizing}
            />
          </div>

          {/* Portfolio Weights Status */}
          <button
            onClick={() => weightsInfo?.exists && setShowWeightsDetail(!showWeightsDetail)}
            disabled={!weightsInfo?.exists}
            className={`w-full flex items-center justify-between p-3 bg-gray-50 rounded-xl transition-colors ${
              weightsInfo?.exists ? 'hover:bg-gray-100 cursor-pointer' : 'cursor-default'
            }`}
          >
            <div className="text-left">
              <span className="text-sm text-gray-600">포트폴리오</span>
              {weightsInfo?.createdAt && (
                <p className="text-xs text-gray-400">{formatDateTimeKST(weightsInfo.createdAt)}</p>
              )}
            </div>
            {weightsInfo?.exists ? (
              <div className="flex items-center gap-1.5 text-emerald-600">
                <CheckCircle className="w-4 h-4" />
                <span className="text-sm font-medium">{weightsInfo.assetCount}개</span>
                {showWeightsDetail ? (
                  <ChevronUp className="w-4 h-4 text-gray-400" />
                ) : (
                  <ChevronDown className="w-4 h-4 text-gray-400" />
                )}
              </div>
            ) : (
              <div className="flex items-center gap-1.5 text-amber-600">
                <AlertCircle className="w-4 h-4" />
                <span className="text-sm font-medium">없음</span>
              </div>
            )}
          </button>

          {/* Weights Detail Panel */}
          {showWeightsDetail && weightsDetail && (
            <div className="p-3 bg-gray-50 rounded-xl max-h-48 overflow-y-auto">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium text-gray-500">최적화된 포트폴리오 비중</span>
                <button 
                  onClick={() => setShowWeightsDetail(false)}
                  className="p-1 hover:bg-gray-200 rounded"
                >
                  <X className="w-3 h-3 text-gray-400" />
                </button>
              </div>
              <div className="space-y-1">
                {Object.entries(weightsDetail)
                  .sort(([, a], [, b]) => b - a)
                  .map(([asset, weight]) => (
                    <div key={asset} className="flex items-center justify-between py-1 text-xs">
                      <span className="text-gray-700 font-medium">{asset}</span>
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                          <div 
                            className="h-full bg-blue-500 rounded-full"
                            style={{ width: `${Math.min(100, weight * 100 * 5)}%` }}
                          />
                        </div>
                        <span className="text-gray-500 tabular-nums w-12 text-right">
                          {(weight * 100).toFixed(2)}%
                        </span>
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {error && (
            <div className="p-2.5 bg-red-50 text-red-600 rounded-lg text-xs border border-red-100">
              {error}
            </div>
          )}

          {/* Action Buttons */}
          <div className="space-y-2">
            {isOptimizing ? (
              <div className="flex gap-2">
                <div className="flex-1 btn bg-purple-500 text-white text-sm py-2.5 cursor-default">
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  최적화 중...
                </div>
                <button
                  onClick={handleCancelOptimize}
                  className="btn bg-red-500 hover:bg-red-600 text-white px-3"
                  title="최적화 취소"
                >
                  <XCircle className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <button
                onClick={handleOptimize}
                disabled={isStarting}
                className="btn bg-purple-500 hover:bg-purple-600 text-white w-full text-sm py-2.5"
              >
                <Sparkles className="w-4 h-4" />
                포트폴리오 최적화
              </button>
            )}

            {weightsInfo?.exists && (
              <button
                onClick={() => handleStart(true)}
                disabled={isStarting || isOptimizing}
                className="btn btn-success w-full text-sm py-2.5"
              >
                {isStarting ? (
                  <RefreshCw className="w-4 h-4 animate-spin" />
                ) : (
                  <Play className="w-4 h-4" />
                )}
                모의투자 시작
              </button>
            )}

            {!weightsInfo?.exists && (
              <button
                onClick={() => handleStart(false)}
                disabled={isStarting || isOptimizing}
                className="btn bg-blue-500 hover:bg-blue-600 text-white w-full text-sm py-2.5"
              >
                {isStarting ? (
                  <RefreshCw className="w-4 h-4 animate-spin" />
                ) : (
                  <Play className="w-4 h-4" />
                )}
                최적화 후 시작
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
