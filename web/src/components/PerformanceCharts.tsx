import { useState } from 'react';
import { 
  AreaChart, Area, LineChart, Line, BarChart, Bar, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, ComposedChart
} from 'recharts';
import type { PnLDataPoint } from '../types';
import { formatNumber, formatPercent, formatChartTime } from '../utils/format';

interface TimeRangeOption {
  label: string;
  hours: number | undefined;
}

interface PerformanceChartsProps {
  data: PnLDataPoint[];
  isLoading: boolean;
  initialValue?: number;
  // Real-time values from bot status (more accurate than chart data)
  currentPnL?: number;
  currentPnLPercent?: number;
  currentTotalValue?: number;
  // Time range selection
  timeRange?: number;
  onTimeRangeChange?: (hours: number | undefined) => void;
  timeRangeOptions?: TimeRangeOption[];
  // Currency
  quoteCurrency?: string;
}

export function PerformanceCharts({ 
  data, 
  isLoading, 
  initialValue = 5000000,
  currentPnL,
  currentPnLPercent,
  currentTotalValue,
  timeRange,
  onTimeRangeChange,
  timeRangeOptions = [],
  quoteCurrency = 'KRW'
}: PerformanceChartsProps) {
  // Tab state for bottom-right chart
  const [bottomRightTab, setBottomRightTab] = useState<'period' | 'drawdown'>('period');

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="card animate-pulse">
          <div className="h-5 bg-gray-100 rounded w-1/4 mb-4"></div>
          <div className="h-48 bg-gray-50 rounded-xl"></div>
        </div>
      </div>
    );
  }

  // Determine max data points based on time range
  const getMaxDataPoints = (forBarChart: boolean = false) => {
    if (forBarChart) {
      if (!timeRange) return 100;
      if (timeRange <= 1) return 60;
      if (timeRange <= 6) return 60;
      if (timeRange <= 24) return 80;
      if (timeRange <= 24 * 7) return 100;
      return 100;
    } else {
      if (!timeRange) return 500;
      if (timeRange <= 24) return data.length;
      if (timeRange <= 24 * 7) return 500;
      return 500;
    }
  };

  // Sample data if too many points
  const sampleData = <T,>(arr: T[], maxPoints: number): T[] => {
    if (arr.length <= maxPoints) return arr;
    const step = Math.ceil(arr.length / maxPoints);
    const sampled: T[] = [];
    for (let i = 0; i < arr.length; i += step) {
      sampled.push(arr[i]);
    }
    if (sampled[sampled.length - 1] !== arr[arr.length - 1]) {
      sampled.push(arr[arr.length - 1]);
    }
    return sampled;
  };

  // Calculate drawdown for each point
  let maxValue = initialValue;
  const chartData = data.map((d, idx) => {
    maxValue = Math.max(maxValue, d.total_value);
    const drawdown = maxValue > 0 ? ((d.total_value - maxValue) / maxValue) * 100 : 0;
    
    return {
      ...d,
      time: formatChartTime(d.timestamp, timeRange),
      pnl_display: d.pnl,
      return_percent: d.pnl_percent,
      btc_return: d.btc_return ?? null,
      eth_return: d.eth_return ?? null,
      // For split area chart: separate positive and negative values
      pnl_positive: d.pnl >= 0 ? d.pnl : 0,
      pnl_negative: d.pnl < 0 ? d.pnl : 0,
      // Period return (difference from previous)
      period_return: idx > 0 ? d.pnl - data[idx - 1].pnl : 0,
      // Drawdown (always <= 0)
      drawdown,
    };
  });

  // Sampled data for different chart types
  const lineChartData = sampleData(chartData, getMaxDataPoints(false));
  const barChartData = sampleData(chartData, getMaxDataPoints(true));

  // Real-time values
  const latestPnL = currentPnL ?? (data.length > 0 ? data[data.length - 1].pnl : 0);
  const latestPnLPercent = currentPnLPercent ?? (data.length > 0 ? data[data.length - 1].pnl_percent : 0);
  const latestTotalValue = currentTotalValue ?? (data.length > 0 ? data[data.length - 1].total_value : initialValue);
  const isPositive = latestPnL >= 0;

  // Calculate stats
  const maxPnL = Math.max(...data.map(d => d.pnl), 0);
  const minPnL = Math.min(...data.map(d => d.pnl), 0);
  const maxDrawdown = Math.min(...chartData.map(d => d.drawdown), 0);
  const volatility = data.length > 1 
    ? Math.sqrt(data.reduce((acc, d, i) => {
        if (i === 0) return 0;
        const periodReturn = d.pnl_percent - data[i-1].pnl_percent;
        return acc + periodReturn * periodReturn;
      }, 0) / (data.length - 1))
    : 0;

  // Check if benchmark data is available
  const hasBenchmarkData = data.some(d => d.btc_return != null || d.eth_return != null);

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-white/95 backdrop-blur-sm p-3 rounded-lg shadow-lg border border-gray-100">
          <p className="text-xs text-gray-500 mb-2">{label} KST</p>
          <div className="space-y-1 text-sm">
            {payload.map((p: any, i: number) => (
              <p key={i} style={{ color: p.color }}>
                {p.name}: <span className="font-semibold">
                  {p.name.includes('%') || p.name.includes('수익률') || p.name.includes('BTC') || p.name.includes('ETH') || p.name.includes('Drawdown')
                    ? `${p.value >= 0 ? '+' : ''}${p.value?.toFixed(2) ?? 0}%`
                    : formatNumber(p.value, { maximumFractionDigits: 0 })}
                </span>
              </p>
            ))}
          </div>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="space-y-4 w-full flex flex-col">
      {/* Summary Stats - Inline */}
      <div className="grid grid-cols-5 gap-3">
        <div className="card p-3">
          <p className="text-xs text-gray-500">총 평가금액</p>
          <p className="text-lg font-bold tabular-nums text-gray-800">
            {formatNumber(latestTotalValue, { maximumFractionDigits: quoteCurrency === 'KRW' ? 0 : 2 })}
          </p>
          <p className="text-xs text-gray-400">{quoteCurrency}</p>
        </div>
        <div className="card p-3">
          <p className="text-xs text-gray-500">손익 (PnL)</p>
          <p className={`text-lg font-bold tabular-nums ${isPositive ? 'text-emerald-600' : 'text-red-500'}`}>
            {isPositive ? '+' : ''}{formatNumber(latestPnL, { maximumFractionDigits: 0 })}
          </p>
          <p className={`text-xs ${isPositive ? 'text-emerald-500' : 'text-red-400'}`}>
            {formatPercent(latestPnLPercent)}
          </p>
        </div>
        <div className="card p-3">
          <p className="text-xs text-gray-500">최고/최저</p>
          <div className="flex items-baseline gap-1.5">
            <span className="text-sm font-semibold text-emerald-600 tabular-nums">
              +{formatNumber(maxPnL, { maximumFractionDigits: quoteCurrency === 'KRW' ? 0 : 2 })}
            </span>
            <span className="text-gray-300">/</span>
            <span className="text-sm font-semibold text-red-500 tabular-nums">
              {formatNumber(minPnL, { maximumFractionDigits: quoteCurrency === 'KRW' ? 0 : 2 })}
            </span>
          </div>
          <p className="text-xs text-gray-400">{quoteCurrency}</p>
        </div>
        <div className="card p-3">
          <p className="text-xs text-gray-500">최대 낙폭</p>
          <p className="text-lg font-bold tabular-nums text-red-500">
            {maxDrawdown.toFixed(2)}%
          </p>
          <p className="text-xs text-gray-400">MDD</p>
        </div>
        <div className="card p-3">
          <p className="text-xs text-gray-500">변동성</p>
          <p className="text-lg font-bold tabular-nums text-gray-800">
            {volatility.toFixed(2)}%
          </p>
          <p className="text-xs text-gray-400">표준편차</p>
        </div>
      </div>

      {/* Time Range Selector */}
      {timeRangeOptions.length > 0 && onTimeRangeChange && (
        <div className="flex items-center justify-end gap-1 mb-2">
          <span className="text-xs text-gray-500 mr-2">기간:</span>
          {timeRangeOptions.map((option) => (
            <button
              key={option.label}
              onClick={() => onTimeRangeChange(option.hours)}
              className={`px-2.5 py-1 text-xs font-medium rounded-lg transition-colors ${
                timeRange === option.hours
                  ? 'bg-blue-500 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      )}

      {/* Charts Grid - 2x2 */}
      <div className="grid grid-cols-2 gap-4">
        {/* Total Value Chart */}
        <div className="card p-4">
          <h3 className="text-sm font-semibold text-gray-800 mb-3">자산 가치 추이</h3>
          <div className="h-52">
            {lineChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={lineChartData}>
                  <defs>
                    <linearGradient id="valueGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                  <XAxis 
                    dataKey="time" 
                    tick={{ fontSize: 9, fill: '#94a3b8' }}
                    tickLine={false}
                    axisLine={false}
                    interval="preserveStartEnd"
                    allowDuplicatedCategory={false}
                  />
                  <YAxis 
                    tick={{ fontSize: 9, fill: '#94a3b8' }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v) => `${(v / 1000000).toFixed(1)}M`}
                    width={36}
                    domain={['dataMin - 50000', 'dataMax + 50000']}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <ReferenceLine y={initialValue} stroke="#94a3b8" strokeDasharray="3 3" />
                  <Area 
                    type="monotone" 
                    dataKey="total_value" 
                    name="총 자산"
                    stroke="#3b82f6"
                    strokeWidth={2}
                    fill="url(#valueGradient)"
                    dot={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-gray-400 bg-gray-50/50 rounded-lg text-sm">
                데이터 없음
              </div>
            )}
          </div>
        </div>

        {/* PnL Chart - Split Positive/Negative */}
        <div className="card p-4">
          <h3 className="text-sm font-semibold text-gray-800 mb-3">손익 변화</h3>
          <div className="h-52">
            {lineChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={lineChartData}>
                  <defs>
                    <linearGradient id="pnlGradientPos" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#10b981" stopOpacity={0.4} />
                      <stop offset="100%" stopColor="#10b981" stopOpacity={0.1} />
                    </linearGradient>
                    <linearGradient id="pnlGradientNeg" x1="0" y1="1" x2="0" y2="0">
                      <stop offset="0%" stopColor="#ef4444" stopOpacity={0.4} />
                      <stop offset="100%" stopColor="#ef4444" stopOpacity={0.1} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                  <XAxis 
                    dataKey="time" 
                    tick={{ fontSize: 9, fill: '#94a3b8' }}
                    tickLine={false}
                    axisLine={false}
                    interval="preserveStartEnd"
                    allowDuplicatedCategory={false}
                  />
                  <YAxis 
                    tick={{ fontSize: 9, fill: '#94a3b8' }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
                    width={36}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <ReferenceLine y={0} stroke="#cbd5e1" strokeWidth={2} />
                  {/* Positive area (above 0) */}
                  <Area 
                    type="monotone" 
                    dataKey="pnl_positive" 
                    name="이익"
                    stroke="#10b981"
                    strokeWidth={0}
                    fill="url(#pnlGradientPos)"
                    dot={false}
                    baseValue={0}
                  />
                  {/* Negative area (below 0) */}
                  <Area 
                    type="monotone" 
                    dataKey="pnl_negative" 
                    name="손실"
                    stroke="#ef4444"
                    strokeWidth={0}
                    fill="url(#pnlGradientNeg)"
                    dot={false}
                    baseValue={0}
                  />
                  {/* Main PnL line */}
                  <Line 
                    type="monotone" 
                    dataKey="pnl_display" 
                    name="손익"
                    stroke={isPositive ? '#10b981' : '#ef4444'}
                    strokeWidth={2}
                    dot={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-gray-400 bg-gray-50/50 rounded-lg text-sm">
                데이터 없음
              </div>
            )}
          </div>
        </div>

        {/* Return Rate Chart with Benchmarks */}
        <div className="card p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-800">수익률 비교</h3>
            {hasBenchmarkData && (
              <div className="flex items-center gap-3 text-xs">
                <span className="flex items-center gap-1">
                  <span className="w-3 h-0.5 bg-violet-500"></span>
                  포트폴리오
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-3 h-0.5 bg-amber-500 border-dashed"></span>
                  BTC
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-3 h-0.5 bg-sky-500 border-dashed"></span>
                  ETH
                </span>
              </div>
            )}
          </div>
          <div className="h-52">
            {lineChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={lineChartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                  <XAxis 
                    dataKey="time" 
                    tick={{ fontSize: 9, fill: '#94a3b8' }}
                    tickLine={false}
                    axisLine={false}
                    interval="preserveStartEnd"
                    allowDuplicatedCategory={false}
                  />
                  <YAxis 
                    tick={{ fontSize: 9, fill: '#94a3b8' }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v) => `${v.toFixed(1)}%`}
                    width={40}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <ReferenceLine y={0} stroke="#cbd5e1" strokeDasharray="3 3" />
                  {/* Portfolio return - solid line */}
                  <Line 
                    type="monotone" 
                    dataKey="return_percent" 
                    name="포트폴리오 수익률"
                    stroke="#8b5cf6"
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4 }}
                  />
                  {/* BTC return - dashed line */}
                  {hasBenchmarkData && (
                    <Line 
                      type="monotone" 
                      dataKey="btc_return" 
                      name="BTC 수익률"
                      stroke="#f59e0b"
                      strokeWidth={1.5}
                      strokeDasharray="5 5"
                      dot={false}
                      connectNulls
                    />
                  )}
                  {/* ETH return - dashed line */}
                  {hasBenchmarkData && (
                    <Line 
                      type="monotone" 
                      dataKey="eth_return" 
                      name="ETH 수익률"
                      stroke="#0ea5e9"
                      strokeWidth={1.5}
                      strokeDasharray="5 5"
                      dot={false}
                      connectNulls
                    />
                  )}
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-gray-400 bg-gray-50/50 rounded-lg text-sm">
                데이터 없음
              </div>
            )}
          </div>
        </div>

        {/* Period Returns / Drawdown - Tab Switchable */}
        <div className="card p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <button
                onClick={() => setBottomRightTab('period')}
                className={`text-sm font-semibold px-2 py-0.5 rounded transition-colors ${
                  bottomRightTab === 'period' 
                    ? 'text-gray-800 bg-gray-100' 
                    : 'text-gray-400 hover:text-gray-600'
                }`}
              >
                구간별 손익
              </button>
              <span className="text-gray-300">|</span>
              <button
                onClick={() => setBottomRightTab('drawdown')}
                className={`text-sm font-semibold px-2 py-0.5 rounded transition-colors ${
                  bottomRightTab === 'drawdown' 
                    ? 'text-gray-800 bg-gray-100' 
                    : 'text-gray-400 hover:text-gray-600'
                }`}
              >
                Drawdown
              </button>
            </div>
            <span className="text-xs text-gray-400">
              {bottomRightTab === 'period' ? '이전 구간 대비 증감' : '고점 대비 하락률'}
            </span>
          </div>
          <div className="h-52">
            {chartData.length > 1 ? (
              bottomRightTab === 'period' ? (
                /* Period Returns Bar Chart */
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={barChartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                    <XAxis 
                      dataKey="time" 
                      tick={{ fontSize: 8, fill: '#94a3b8' }}
                      tickLine={false}
                      axisLine={false}
                      interval="preserveStartEnd"
                    />
                    <YAxis 
                      tick={{ fontSize: 9, fill: '#94a3b8' }}
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
                      width={36}
                    />
                    <Tooltip content={<CustomTooltip />} />
                    <ReferenceLine y={0} stroke="#cbd5e1" />
                    <Bar 
                      dataKey="period_return" 
                      name="구간 손익"
                      radius={[2, 2, 0, 0]}
                    >
                      {barChartData.map((entry, index) => (
                        <Cell 
                          key={index} 
                          fill={entry.period_return >= 0 ? '#86efac' : '#fca5a5'} 
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                /* Drawdown Area Chart */
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={lineChartData}>
                    <defs>
                      <linearGradient id="drawdownGradient" x1="0" y1="1" x2="0" y2="0">
                        <stop offset="0%" stopColor="#ef4444" stopOpacity={0.3} />
                        <stop offset="100%" stopColor="#ef4444" stopOpacity={0.05} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                    <XAxis 
                      dataKey="time" 
                      tick={{ fontSize: 9, fill: '#94a3b8' }}
                      tickLine={false}
                      axisLine={false}
                      interval="preserveStartEnd"
                      allowDuplicatedCategory={false}
                    />
                    <YAxis 
                      tick={{ fontSize: 9, fill: '#94a3b8' }}
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={(v) => `${v.toFixed(1)}%`}
                      width={40}
                      domain={['dataMin - 0.5', 0.5]}
                    />
                    <Tooltip content={<CustomTooltip />} />
                    <ReferenceLine y={0} stroke="#10b981" strokeWidth={2} />
                    <Area 
                      type="monotone" 
                      dataKey="drawdown" 
                      name="Drawdown"
                      stroke="#ef4444"
                      strokeWidth={1.5}
                      fill="url(#drawdownGradient)"
                      dot={false}
                      baseValue={0}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              )
            ) : (
              <div className="h-full flex items-center justify-center text-gray-400 bg-gray-50/50 rounded-lg text-sm">
                데이터 없음
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
