import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import type { Holding } from '../types';
import { formatNumber } from '../utils/format';

interface PortfolioPieChartProps {
  holdings: Holding[];
  isLoading: boolean;
  embedded?: boolean;  // When true, renders without card wrapper
  quoteCurrency?: string;
}

// Diverse color palette with better contrast
const COLORS = [
  '#3b82f6', // blue
  '#10b981', // emerald
  '#f59e0b', // amber
  '#ef4444', // red
  '#8b5cf6', // violet
  '#ec4899', // pink
  '#06b6d4', // cyan
  '#f97316', // orange
  '#6366f1', // indigo
  '#14b8a6', // teal
  '#a855f7', // purple
  '#84cc16', // lime
  '#0ea5e9', // sky
  '#e11d48', // rose
  '#7c3aed', // violet dark
  '#059669', // emerald dark
  '#dc2626', // red dark
  '#2563eb', // blue dark
  '#ca8a04', // yellow dark
  '#0891b2', // cyan dark
];

export function PortfolioPieChart({ holdings, isLoading, embedded = false, quoteCurrency = 'KRW' }: PortfolioPieChartProps) {
  if (isLoading) {
    const content = (
      <div className="animate-pulse">
        {!embedded && <div className="h-5 bg-gray-100 rounded w-1/4 mb-4"></div>}
        <div className="h-56 bg-gray-50 rounded-xl"></div>
      </div>
    );
    return embedded ? content : <div className="card h-80">{content}</div>;
  }

  // Group small holdings into "Others"
  const threshold = 0.02; // 2%
  const mainHoldings = holdings.filter(h => h.current_weight >= threshold);
  const otherHoldings = holdings.filter(h => h.current_weight < threshold);
  
  const chartData = mainHoldings.map(h => ({
    name: h.currency,
    value: h.value,
    percent: h.current_weight * 100,
  }));

  if (otherHoldings.length > 0) {
    const othersValue = otherHoldings.reduce((sum, h) => sum + h.value, 0);
    const othersPercent = otherHoldings.reduce((sum, h) => sum + h.current_weight, 0) * 100;
    chartData.push({
      name: `기타 (${otherHoldings.length}개)`,
      value: othersValue,
      percent: othersPercent,
    });
  }

  const CustomTooltip = ({ active, payload }: any) => {
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
  };

  // Calculate total value for center display
  const totalValue = chartData.reduce((sum, item) => sum + item.value, 0);

  const chartContent = (
    <div className="h-72">
      {chartData.length > 0 ? (
        <div className="flex h-full">
          <div className="flex-1 relative">
            <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={chartData}
                    cx="50%"
                    cy="50%"
                    innerRadius={75}
                    outerRadius={110}
                    paddingAngle={2}
                    dataKey="value"
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
                <Tooltip content={<CustomTooltip />} />
              </PieChart>
            </ResponsiveContainer>
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
