import { memo, useMemo } from 'react';
import { PieChart, Pie, Cell, Tooltip } from 'recharts';
import type { Holding } from '../types';
import { formatNumber } from '../utils/format';

interface PortfolioPieChartProps {
  holdings: Holding[];
  isLoading: boolean;
  embedded?: boolean;
  quoteCurrency?: string;
}

// Diverse color palette with better contrast
const COLORS = [
  '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
  '#ec4899', '#06b6d4', '#f97316', '#6366f1', '#14b8a6',
  '#a855f7', '#84cc16', '#0ea5e9', '#e11d48', '#7c3aed',
  '#059669', '#dc2626', '#2563eb', '#ca8a04', '#0891b2',
];

// Memoized tooltip component
const CustomTooltip = memo(({ active, payload, quoteCurrency }: any) => {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="bg-white/95 backdrop-blur-sm p-3 rounded-xl shadow-lg border border-gray-100">
        <p className="font-semibold text-gray-800">{data.name}</p>
        <p className="text-gray-600 tabular-nums">
          {formatNumber(data.value, { maximumFractionDigits: quoteCurrency === 'KRW' ? 0 : 2 })} {quoteCurrency}
        </p>
        <p className="text-sm text-gray-400 tabular-nums">{data.percent.toFixed(2)}%</p>
      </div>
    );
  }
  return null;
});

CustomTooltip.displayName = 'CustomTooltip';

function PortfolioPieChartInner({ holdings, isLoading, embedded = false, quoteCurrency = 'KRW' }: PortfolioPieChartProps) {
  // Memoize chart data calculation
  const { chartData, totalValue } = useMemo(() => {
    if (!holdings || holdings.length === 0) {
      return { chartData: [], totalValue: 0 };
    }

    // Group small holdings into "Others"
    const threshold = 0.02; // 2%
    const mainHoldings = holdings.filter(h => h.current_weight >= threshold);
    const otherHoldings = holdings.filter(h => h.current_weight < threshold);
    
    const data = mainHoldings.map(h => ({
      name: h.currency,
      value: h.value,
      percent: h.current_weight * 100,
    }));

    if (otherHoldings.length > 0) {
      const othersValue = otherHoldings.reduce((sum, h) => sum + h.value, 0);
      const othersPercent = otherHoldings.reduce((sum, h) => sum + h.current_weight, 0) * 100;
      data.push({
        name: `기타 (${otherHoldings.length}개)`,
        value: othersValue,
        percent: othersPercent,
      });
    }

    const total = data.reduce((sum, item) => sum + item.value, 0);
    return { chartData: data, totalValue: total };
  }, [holdings]);

  if (isLoading) {
    const content = (
      <div className="animate-pulse">
        {!embedded && <div className="h-5 bg-gray-100 rounded w-1/4 mb-4"></div>}
        <div className="h-56 bg-gray-50 rounded-xl"></div>
      </div>
    );
    return embedded ? content : <div className="card h-80">{content}</div>;
  }

  const chartContent = (
    <div className="h-72">
      {chartData.length > 0 ? (
        <div className="flex h-full">
          <div className="flex-1 relative flex items-center justify-center">
            {/* Fixed size instead of ResponsiveContainer for better performance */}
            <PieChart width={240} height={240}>
              <Pie
                data={chartData}
                cx="50%"
                cy="50%"
                innerRadius={70}
                outerRadius={105}
                paddingAngle={2}
                dataKey="value"
                animationBegin={0}
                animationDuration={1000}
                animationEasing="ease-out"
              >
                {chartData.map((_, index) => (
                  <Cell 
                    key={`cell-${index}`} 
                    fill={COLORS[index % COLORS.length]}
                    stroke="white"
                    strokeWidth={2}
                  />
                ))}
              </Pie>
              <Tooltip content={<CustomTooltip quoteCurrency={quoteCurrency} />} />
            </PieChart>
            {/* Center Label */}
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="text-center">
                <p className="text-xs text-gray-400">총 자산</p>
                <p className="text-sm font-bold text-gray-800 tabular-nums">
                  {formatNumber(totalValue / 10000, { maximumFractionDigits: 0 })}만
                </p>
              </div>
            </div>
          </div>
          
          {/* Legend */}
          <div className="w-32 flex flex-col justify-center gap-1.5 pl-2">
            {chartData.slice(0, 10).map((item, index) => (
              <div key={item.name} className="flex items-center gap-1.5">
                <div 
                  className="w-2.5 h-2.5 rounded-sm shrink-0" 
                  style={{ backgroundColor: COLORS[index % COLORS.length] }}
                />
                <span className="text-xs text-gray-600 truncate flex-1">{item.name}</span>
                <span className="text-xs text-gray-400 tabular-nums">{item.percent.toFixed(1)}%</span>
              </div>
            ))}
            {chartData.length > 10 && (
              <div className="text-xs text-gray-400 pl-4">+{chartData.length - 10}개 더</div>
            )}
          </div>
        </div>
      ) : (
        <div className="h-full flex items-center justify-center text-gray-400 bg-gray-50/50 rounded-xl">
          보유 자산이 없습니다
        </div>
      )}
    </div>
  );

  if (embedded) {
    return chartContent;
  }

  return (
    <div className="card h-full">
      <h3 className="text-lg font-semibold text-gray-800 mb-4">포트폴리오 구성</h3>
      {chartContent}
    </div>
  );
}

// Memoize the entire component to prevent unnecessary re-renders
export const PortfolioPieChart = memo(PortfolioPieChartInner, (prevProps, nextProps) => {
  // Custom comparison - only re-render if holdings actually changed significantly
  if (prevProps.isLoading !== nextProps.isLoading) return false;
  if (prevProps.holdings.length !== nextProps.holdings.length) return false;
  
  // Compare holdings by currency (ignore small value changes)
  const prevCurrencies = prevProps.holdings.map(h => h.currency).sort().join(',');
  const nextCurrencies = nextProps.holdings.map(h => h.currency).sort().join(',');
  if (prevCurrencies !== nextCurrencies) return false;
  
  // Check if any weight changed by more than 1%
  for (let i = 0; i < prevProps.holdings.length; i++) {
    const prev = prevProps.holdings.find(h => h.currency === nextProps.holdings[i]?.currency);
    const next = nextProps.holdings[i];
    if (prev && next && Math.abs(prev.current_weight - next.current_weight) > 0.01) {
      return false;
    }
  }
  
  return true; // Props are equal, don't re-render
});
