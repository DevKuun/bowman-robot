import { 
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, 
  ResponsiveContainer, ReferenceLine 
} from 'recharts';
import type { PnLDataPoint } from '../types';
import { formatShortTimeKST, formatNumber, formatPercent } from '../utils/format';

interface PnLChartProps {
  data: PnLDataPoint[];
  isLoading: boolean;
}

export function PnLChart({ data, isLoading }: PnLChartProps) {
  if (isLoading) {
    return (
      <div className="card h-80 animate-pulse">
        <div className="h-5 bg-gray-100 rounded w-1/4 mb-6"></div>
        <div className="h-56 bg-gray-50 rounded-xl"></div>
      </div>
    );
  }

  const chartData = data.map(d => ({
    ...d,
    time: formatShortTimeKST(d.timestamp),
    pnl_display: d.pnl,
  }));

  const latestPnL = data.length > 0 ? data[data.length - 1].pnl : 0;
  const latestPnLPercent = data.length > 0 ? data[data.length - 1].pnl_percent : 0;
  const latestTotalValue = data.length > 0 ? data[data.length - 1].total_value : 0;
  const isPositive = latestPnL >= 0;

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      const pnlValue = payload[0].value;
      const totalValue = payload[0].payload?.total_value || 0;
      return (
        <div className="bg-white/95 backdrop-blur-sm p-3 rounded-lg shadow-lg border border-gray-100">
          <p className="text-xs text-gray-500 mb-2">{label} KST</p>
          <div className="space-y-1">
            <p className="text-sm text-gray-600">
              총액: <span className="font-semibold">{formatNumber(totalValue, { maximumFractionDigits: 0 })}</span> KRW
            </p>
            <p className={`text-sm ${pnlValue >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
              손익: <span className="font-semibold">{pnlValue >= 0 ? '+' : ''}{formatNumber(pnlValue, { maximumFractionDigits: 0 })}</span> KRW
            </p>
          </div>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="card h-full flex flex-col">
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-lg font-semibold text-gray-800">손익 현황</h3>
        <div className="flex items-center gap-8">
          <div className="text-right">
            <p className="text-xs text-gray-400 mb-0.5">총 평가금액</p>
            <p className="text-xl font-bold tabular-nums text-gray-800">
              {formatNumber(latestTotalValue, { maximumFractionDigits: 0 })}
              <span className="text-xs font-normal text-gray-400 ml-1">KRW</span>
            </p>
          </div>
          <div className="text-right">
            <p className="text-xs text-gray-400 mb-0.5">손익 (PnL)</p>
            <p className={`text-xl font-bold tabular-nums ${isPositive ? 'text-emerald-600' : 'text-red-500'}`}>
              {isPositive ? '+' : ''}{formatNumber(latestPnL, { maximumFractionDigits: 0 })}
              <span className="text-xs font-normal text-gray-400 ml-1">KRW</span>
            </p>
            <p className={`text-xs font-medium ${isPositive ? 'text-emerald-500' : 'text-red-400'}`}>
              {formatPercent(latestPnLPercent)}
            </p>
          </div>
        </div>
      </div>

      <div className="flex-1 min-h-[200px]">
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={isPositive ? '#10b981' : '#ef4444'} stopOpacity={0.3} />
                  <stop offset="100%" stopColor={isPositive ? '#10b981' : '#ef4444'} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
              <XAxis 
                dataKey="time" 
                tick={{ fontSize: 11, fill: '#94a3b8' }}
                tickLine={false}
                axisLine={false}
              />
              <YAxis 
                tick={{ fontSize: 11, fill: '#94a3b8' }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
                width={45}
              />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine y={0} stroke="#cbd5e1" strokeDasharray="3 3" />
              <Area 
                type="monotone" 
                dataKey="pnl_display" 
                stroke={isPositive ? '#10b981' : '#ef4444'}
                strokeWidth={2}
                fill="url(#pnlGradient)"
                dot={false}
                activeDot={{ r: 4, fill: isPositive ? '#10b981' : '#ef4444' }}
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-full flex items-center justify-center text-gray-400 bg-gray-50/50 rounded-xl">
            <p>데이터가 없습니다</p>
          </div>
        )}
      </div>
    </div>
  );
}
