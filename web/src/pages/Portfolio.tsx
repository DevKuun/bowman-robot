import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Wallet, TrendingUp, TrendingDown, PieChart as PieChartIcon, BarChart3, Target, ChevronDown, ChevronUp, RefreshCw, Clock, Settings } from 'lucide-react';
import { portfolioApi, botApi } from '../api/client';
import { PortfolioTable } from '../components/PortfolioTable';
import { PortfolioPieChart } from '../components/PortfolioPieChart';
import { formatNumber, formatPercent, formatDateTimeKST } from '../utils/format';
import { useRealtime } from '../contexts/RealtimeContext';

const RISK_LABELS = ['매우 안전', '안전', '보통', '공격적', '매우 공격적'];

export function Portfolio() {
  const [showTargetWeights, setShowTargetWeights] = useState(false);
  const [selectedRiskLevel, setSelectedRiskLevel] = useState<number | null>(null);
  
  // Real-time data from WebSocket
  const { status: realtimeStatus, portfolio: realtimePortfolio, portfolioSummary: realtimeSummary, isConnected } = useRealtime();
  
  // Fallback query - reduce polling when WebSocket is connected
  const statusQuery = useQuery({
    queryKey: ['bot-status'],
    queryFn: botApi.getStatus,
    refetchInterval: isConnected ? 30000 : 10000,
  });
  
  const isRunning = realtimeStatus?.running ?? statusQuery.data?.running ?? false;
  const currentRiskLevel = realtimeStatus?.risk_level ?? statusQuery.data?.risk_level ?? 2;
  
  // Set selected risk level to current running risk level
  useEffect(() => {
    if (selectedRiskLevel === null) {
      setSelectedRiskLevel(currentRiskLevel);
    }
  }, [currentRiskLevel, selectedRiskLevel]);
  
  const portfolioQuery = useQuery({
    queryKey: ['portfolio'],
    queryFn: portfolioApi.get,
    refetchInterval: isRunning ? (isConnected ? 30000 : 5000) : false,
  });

  const summaryQuery = useQuery({
    queryKey: ['portfolio-summary'],
    queryFn: portfolioApi.getSummary,
    refetchInterval: isRunning ? (isConnected ? 30000 : 5000) : false,
  });

  // Get target weights from optimization (by selected risk level)
  const effectiveRiskLevel = selectedRiskLevel ?? currentRiskLevel;
  const weightsQuery = useQuery({
    queryKey: ['target-weights', effectiveRiskLevel],
    queryFn: () => botApi.getWeights(statusQuery.data?.exchange || 'bithumb', effectiveRiskLevel),
    enabled: true,
  });

  // Get optimization status
  const optimizationStatusQuery = useQuery({
    queryKey: ['optimization-status'],
    queryFn: portfolioApi.getOptimizationStatus,
    refetchInterval: 60000, // Refresh every minute
  });

  // Use real-time data if available
  const portfolio = realtimePortfolio || portfolioQuery.data;
  const summary = realtimeSummary || summaryQuery.data;
  const targetWeights = weightsQuery.data;

  const isPositive = (portfolio?.pnl ?? 0) >= 0;

  // Calculate diversification metrics
  const holdings = portfolio?.holdings ?? [];
  const assetCount = holdings.filter(h => h.value > 0).length;
  
  // Calculate HHI (Herfindahl-Hirschman Index) for diversification
  // HHI = sum of squared weights, lower is more diversified
  // HHI ranges from 1/n (perfect diversification) to 1 (single asset)
  const hhi = holdings.reduce((sum, h) => sum + Math.pow(h.current_weight, 2), 0);
  const effectiveAssets = hhi > 0 ? 1 / hhi : 0;  // Effective number of assets
  
  // Top 3 concentration (what % do top 3 assets hold)
  const sortedHoldings = [...holdings].sort((a, b) => b.value - a.value);
  const top3Weight = sortedHoldings.slice(0, 3).reduce((sum, h) => sum + h.current_weight, 0);
  const top5Weight = sortedHoldings.slice(0, 5).reduce((sum, h) => sum + h.current_weight, 0);

  return (
    <div className="space-y-6 animate-fadeIn">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">포트폴리오</h1>
          <p className="text-gray-500 text-sm mt-1">
            자산 현황 및 배분
            {isConnected && (
              <span className="ml-2 inline-flex items-center gap-1 text-emerald-600">
                <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
                실시간
              </span>
            )}
          </p>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="card">
          <div className="flex items-start justify-between">
            <div className="stat-card">
              <span className="stat-label">총 평가금액</span>
              <span className="stat-value tabular-nums">
                {formatNumber(portfolio?.total_value ?? 0, { maximumFractionDigits: 0 })}
              </span>
              <span className="text-sm text-gray-400">{portfolio?.quote_currency}</span>
            </div>
            <div className="p-3 bg-blue-100 rounded-xl">
              <Wallet className="w-5 h-5 text-blue-600" />
            </div>
          </div>
        </div>

        <div className="card">
          <div className="flex items-start justify-between">
            <div className="stat-card">
              <span className="stat-label">손익 (PnL)</span>
              <span className={`stat-value tabular-nums ${isPositive ? 'text-emerald-600' : 'text-red-500'}`}>
                {isPositive ? '+' : ''}{formatNumber(portfolio?.pnl ?? 0, { maximumFractionDigits: 0 })}
              </span>
              <span className={`stat-change ${isPositive ? 'positive' : 'negative'}`}>
                {formatPercent(portfolio?.pnl_percent ?? 0)}
              </span>
            </div>
            <div className={`p-3 rounded-xl ${isPositive ? 'bg-emerald-100' : 'bg-red-100'}`}>
              {isPositive ? (
                <TrendingUp className="w-5 h-5 text-emerald-600" />
              ) : (
                <TrendingDown className="w-5 h-5 text-red-500" />
              )}
            </div>
          </div>
        </div>

        <div className="card">
          <div className="flex items-start justify-between">
            <div className="stat-card">
              <span className="stat-label">보유 자산</span>
              <span className="stat-value tabular-nums">{assetCount}</span>
              <span className="text-sm text-gray-400">종목</span>
            </div>
            <div className="p-3 bg-purple-100 rounded-xl">
              <PieChartIcon className="w-5 h-5 text-purple-600" />
            </div>
          </div>
        </div>

        <div className="card">
          <div className="flex items-start justify-between">
            <div className="stat-card">
              <span className="stat-label">총 거래 횟수</span>
              <span className="stat-value tabular-nums">{formatNumber(summary?.total_trades ?? 0)}</span>
              <span className="text-sm text-gray-400">회</span>
            </div>
            <div className="p-3 bg-amber-100 rounded-xl">
              <BarChart3 className="w-5 h-5 text-amber-600" />
            </div>
          </div>
        </div>
      </div>

      {/* Main Content: 2-Column Layout with Equal Height */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Left: Portfolio Composition (Chart + Stats) - 3 columns */}
        <div className="lg:col-span-3 card flex flex-col">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">포트폴리오 구성</h3>
          
          {/* Pie Chart */}
          <div className="flex-1">
            <PortfolioPieChart 
              holdings={portfolio?.holdings ?? []} 
              isLoading={portfolioQuery.isLoading && !realtimePortfolio}
              embedded={true}
              quoteCurrency={portfolio?.quote_currency ?? 'KRW'}
            />
          </div>

          {/* Bottom Stats Row */}
          {(summary?.allocation || holdings.length > 0) && (
            <div className="mt-4 pt-4 border-t border-gray-100 grid grid-cols-2 gap-4">
              {/* Asset Allocation */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-gray-600">자산 배분</span>
                </div>
                <div className="h-2.5 rounded-full overflow-hidden flex bg-gray-100 mb-2">
                  <div className="bg-gray-400" style={{ width: `${summary?.allocation?.cash_percent ?? 0}%` }} />
                  <div className="bg-blue-500" style={{ width: `${summary?.allocation?.stablecoins_percent ?? 0}%` }} />
                  <div className="bg-purple-500" style={{ width: `${summary?.allocation?.crypto_percent ?? 0}%` }} />
                </div>
                <div className="flex gap-3 text-xs">
                  <span className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-sm bg-gray-400" />
                    <span className="text-gray-500">현금</span>
                    <span className="font-medium tabular-nums">{(summary?.allocation?.cash_percent ?? 0).toFixed(0)}%</span>
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-sm bg-blue-500" />
                    <span className="text-gray-500">스테이블</span>
                    <span className="font-medium text-blue-600 tabular-nums">{(summary?.allocation?.stablecoins_percent ?? 0).toFixed(0)}%</span>
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-sm bg-purple-500" />
                    <span className="text-gray-500">암호화폐</span>
                    <span className="font-medium text-purple-600 tabular-nums">{(summary?.allocation?.crypto_percent ?? 0).toFixed(0)}%</span>
                  </span>
                </div>
              </div>

              {/* Diversification */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-gray-600">분산도</span>
                  <span className={`text-xs font-semibold ${
                    effectiveAssets >= 15 ? 'text-emerald-600' : 
                    effectiveAssets >= 8 ? 'text-amber-600' : 'text-red-500'
                  }`}>
                    {effectiveAssets >= 15 ? '높음' : effectiveAssets >= 8 ? '보통' : '낮음'}
                  </span>
                </div>
                <div className="h-2.5 rounded-full bg-gray-100 overflow-hidden mb-2">
                  <div 
                    className={`h-full ${
                      effectiveAssets >= 15 ? 'bg-emerald-500' : 
                      effectiveAssets >= 8 ? 'bg-amber-500' : 'bg-red-400'
                    }`}
                    style={{ width: `${Math.min(100, (effectiveAssets / 25) * 100)}%` }}
                  />
                </div>
                <div className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="text-gray-500">유효 자산 수</span>
                    <span className="font-medium tabular-nums">{effectiveAssets.toFixed(1)}개</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-gray-500">Top 3 비중</span>
                    <span className={`font-medium tabular-nums ${top3Weight > 0.7 ? 'text-amber-600' : 'text-gray-600'}`}>
                      {(top3Weight * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-gray-500">Top 5 비중</span>
                    <span className={`font-medium tabular-nums ${top5Weight > 0.85 ? 'text-amber-600' : 'text-gray-600'}`}>
                      {(top5Weight * 100).toFixed(1)}%
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right: Top Holdings - 2 columns */}
        <div className="lg:col-span-2 card flex flex-col">
          <h3 className="text-lg font-semibold text-gray-800 mb-3">상위 보유 자산</h3>
          <div className="flex-1 space-y-1.5">
            {(portfolio?.holdings ?? []).slice(0, 8).map((h, i) => (
              <div key={h.currency} className="flex items-center justify-between py-2 px-2.5 bg-gray-50/50 rounded-lg hover:bg-gray-100/50 transition-colors">
                <div className="flex items-center gap-2">
                  <span className="w-5 h-5 flex items-center justify-center bg-gray-200 rounded text-xs font-bold text-gray-500">
                    {i + 1}
                  </span>
                  <span className="font-medium text-gray-800 text-sm">{h.currency}</span>
                </div>
                <div className="text-right">
                  <p className="font-semibold text-gray-800 tabular-nums text-sm">
                    {formatNumber(h.value, { maximumFractionDigits: 0 })}
                  </p>
                  <p className="text-xs text-gray-400 tabular-nums">{(h.current_weight * 100).toFixed(1)}%</p>
                </div>
              </div>
            ))}
            {(portfolio?.holdings?.length ?? 0) === 0 && (
              <div className="h-full flex items-center justify-center text-gray-400 bg-gray-50 rounded-xl text-sm">
                보유 자산 없음
              </div>
            )}
          </div>
          {(portfolio?.holdings?.length ?? 0) > 8 && (
            <p className="text-xs text-gray-400 text-center mt-2 pt-2 border-t border-gray-100">
              +{(portfolio?.holdings?.length ?? 0) - 8}개 더 보유
            </p>
          )}
        </div>
      </div>

      {/* Portfolio Optimization Status */}
      {optimizationStatusQuery.data && (
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Settings className="w-5 h-5 text-blue-600" />
              <h3 className="text-lg font-semibold text-gray-800">포트폴리오 최적화</h3>
            </div>
            {optimizationStatusQuery.isRefetching && (
              <RefreshCw className="w-4 h-4 text-gray-400 animate-spin" />
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Last Optimization */}
            <div className="p-4 bg-gray-50 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <Clock className="w-4 h-4 text-gray-500" />
                <span className="text-sm font-medium text-gray-600">마지막 최적화</span>
              </div>
              {optimizationStatusQuery.data.last_optimization ? (
                <div>
                  <p className="text-sm font-semibold text-gray-800">
                    {formatDateTimeKST(optimizationStatusQuery.data.last_optimization)}
                  </p>
                  <p className="text-xs text-gray-400 mt-1">
                    {Math.round((new Date().getTime() - new Date(optimizationStatusQuery.data.last_optimization).getTime()) / (1000 * 60 * 60))}시간 전
                  </p>
                </div>
              ) : (
                <p className="text-sm text-gray-400">아직 실행되지 않음</p>
              )}
            </div>

            {/* Next Optimization */}
            <div className="p-4 bg-gray-50 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <RefreshCw className="w-4 h-4 text-gray-500" />
                <span className="text-sm font-medium text-gray-600">다음 최적화</span>
              </div>
              {optimizationStatusQuery.data.schedule.enabled ? (
                optimizationStatusQuery.data.next_optimization ? (
                  <div>
                    <p className="text-sm font-semibold text-gray-800">
                      {formatDateTimeKST(optimizationStatusQuery.data.next_optimization)}
                    </p>
                    <p className="text-xs text-gray-400 mt-1">
                      {optimizationStatusQuery.data.schedule.reoptimize_hours}시간마다 자동 실행
                    </p>
                  </div>
                ) : (
                  <p className="text-sm text-gray-400">예정 없음</p>
                )
              ) : (
                <p className="text-sm text-gray-400">자동 갱신 비활성화</p>
              )}
            </div>

            {/* Settings */}
            <div className="p-4 bg-gray-50 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <Settings className="w-4 h-4 text-gray-500" />
                <span className="text-sm font-medium text-gray-600">설정</span>
              </div>
              <div className="space-y-1">
                <p className="text-xs text-gray-600">
                  최소 거래량: {formatNumber(optimizationStatusQuery.data.schedule.min_daily_volume_krw / 1e9, { maximumFractionDigits: 1 })}B KRW
                </p>
                <p className="text-xs text-gray-600">
                  갱신 주기: {optimizationStatusQuery.data.schedule.enabled 
                    ? `${optimizationStatusQuery.data.schedule.reoptimize_hours}시간`
                    : '수동'}
                </p>
              </div>
            </div>
          </div>

          {/* Optimization History */}
          {optimizationStatusQuery.data.history.length > 0 && (
            <div className="mt-4 pt-4 border-t border-gray-100">
              <h4 className="text-sm font-medium text-gray-700 mb-2">최근 최적화 이력</h4>
              <div className="space-y-1.5">
                {optimizationStatusQuery.data.history.map((item, idx) => (
                  <div key={idx} className="flex items-center justify-between text-xs text-gray-600 py-1">
                    <span>{formatDateTimeKST(item.timestamp)}</span>
                    <span className="text-gray-400">{item.risk_levels}개 리스크 레벨</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Target Portfolio Weights */}
      {targetWeights?.exists && targetWeights?.weights && (
        <div className="card">
          <button
            onClick={() => setShowTargetWeights(!showTargetWeights)}
            className="w-full flex items-center justify-between"
          >
            <div className="flex items-center gap-2">
              <Target className="w-5 h-5 text-purple-500" />
              <h3 className="text-lg font-semibold text-gray-800">최적화된 포트폴리오</h3>
              <span className="text-sm text-gray-400">({targetWeights.asset_count}개 자산)</span>
            </div>
            <div className="flex items-center gap-2">
              {targetWeights.created_at && (
                <span className="text-xs text-gray-400">{formatDateTimeKST(targetWeights.created_at)}</span>
              )}
              {showTargetWeights ? (
                <ChevronUp className="w-5 h-5 text-gray-400" />
              ) : (
                <ChevronDown className="w-5 h-5 text-gray-400" />
              )}
            </div>
          </button>
          
          {showTargetWeights && (
            <div className="mt-4 pt-4 border-t border-gray-100">
              {/* Risk Level Selector */}
              <div className="mb-4">
                <div className="flex items-center gap-1 p-1 bg-gray-100 rounded-lg w-fit">
                  {RISK_LABELS.map((label, idx) => (
                    <button
                      key={idx}
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedRiskLevel(idx);
                      }}
                      className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                        effectiveRiskLevel === idx
                          ? 'bg-white text-purple-600 shadow-sm'
                          : 'text-gray-500 hover:text-gray-700'
                      } ${isRunning && currentRiskLevel === idx ? 'ring-2 ring-purple-300' : ''}`}
                      title={isRunning && currentRiskLevel === idx ? '현재 실행 중인 리스크 레벨' : undefined}
                    >
                      {label}
                      {isRunning && currentRiskLevel === idx && (
                        <span className="ml-1 inline-block w-1.5 h-1.5 bg-purple-500 rounded-full animate-pulse" />
                      )}
                    </button>
                  ))}
                </div>
              </div>
              
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2">
                {Object.entries(targetWeights.weights)
                  .sort(([, a], [, b]) => (b as number) - (a as number))
                  .map(([asset, weight]) => {
                    const currentHolding = portfolio?.holdings?.find(h => h.currency === asset);
                    const currentWeight = currentHolding?.current_weight ?? 0;
                    const targetWeight = weight as number;
                    const diff = currentWeight - targetWeight;
                    
                    return (
                      <div key={asset} className="p-2.5 bg-gray-50 rounded-lg">
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-medium text-gray-800 text-sm">{asset}</span>
                          {Math.abs(diff) > 0.005 && (
                            <span className={`text-xs ${diff > 0 ? 'text-emerald-500' : 'text-red-400'}`}>
                              {diff > 0 ? '+' : ''}{(diff * 100).toFixed(1)}%
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-1.5">
                          <div className="flex-1 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                            <div 
                              className="h-full bg-purple-500 rounded-full"
                              style={{ width: `${Math.min(100, targetWeight * 100 * 5)}%` }}
                            />
                          </div>
                          <span className="text-xs text-gray-500 tabular-nums w-10 text-right">
                            {(targetWeight * 100).toFixed(1)}%
                          </span>
                        </div>
                        {currentHolding && (
                          <p className="text-xs text-gray-400 mt-1">
                            현재: {(currentWeight * 100).toFixed(1)}%
                          </p>
                        )}
                      </div>
                    );
                  })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Full Holdings Table */}
      <PortfolioTable 
        holdings={portfolio?.holdings ?? []} 
        quoteCurrency={portfolio?.quote_currency ?? 'KRW'}
        isLoading={portfolioQuery.isLoading && !realtimePortfolio}
      />
    </div>
  );
}
