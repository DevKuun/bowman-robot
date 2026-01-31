import { useMemo, useState, useEffect, useRef } from 'react';
import type { Holding } from '../types';
import { formatNumber } from '../utils/format';

interface PortfolioPieChartProps {
  holdings: Holding[];
  isLoading: boolean;
  embedded?: boolean;
  quoteCurrency?: string;
}

// Diverse color palette
const COLORS = [
  '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
  '#ec4899', '#06b6d4', '#f97316', '#6366f1', '#14b8a6',
  '#a855f7', '#84cc16', '#0ea5e9', '#e11d48', '#7c3aed',
  '#059669', '#dc2626', '#2563eb', '#ca8a04', '#0891b2',
];

interface ChartItem {
  name: string;
  value: number;
  percent: number;
  color: string;
}


export function PortfolioPieChart({ holdings, isLoading, embedded = false, quoteCurrency = 'KRW' }: PortfolioPieChartProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [animationProgress, setAnimationProgress] = useState(0);
  const animationRef = useRef<number | null>(null);
  const prevHoldingsKey = useRef<string>('');

  // Animate donut drawing
  useEffect(() => {
    const holdingsKey = holdings.map(h => `${h.currency}:${h.value}`).join(',');
    
    // Only animate when holdings actually change
    if (holdingsKey === prevHoldingsKey.current) return;
    prevHoldingsKey.current = holdingsKey;
    
    // Reset and start animation
    setAnimationProgress(0);
    const startTime = performance.now();
    const duration = 800; // ms
    
    const animate = (currentTime: number) => {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);
      
      // Easing function (ease-out)
      const eased = 1 - Math.pow(1 - progress, 3);
      setAnimationProgress(eased);
      
      if (progress < 1) {
        animationRef.current = requestAnimationFrame(animate);
      }
    };
    
    animationRef.current = requestAnimationFrame(animate);
    
    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [holdings]);

  const { chartData, totalValue } = useMemo(() => {
    if (!holdings || holdings.length === 0) {
      return { chartData: [], totalValue: 0 };
    }

    // Group small holdings into "Others"
    const threshold = 0.02;
    const mainHoldings = holdings.filter(h => h.current_weight >= threshold);
    const otherHoldings = holdings.filter(h => h.current_weight < threshold);
    
    const data: ChartItem[] = mainHoldings.map((h, i) => ({
      name: h.currency,
      value: h.value,
      percent: h.current_weight * 100,
      color: COLORS[i % COLORS.length],
    }));

    if (otherHoldings.length > 0) {
      const othersValue = otherHoldings.reduce((sum, h) => sum + h.value, 0);
      const othersPercent = otherHoldings.reduce((sum, h) => sum + h.current_weight, 0) * 100;
      data.push({
        name: `기타 (${otherHoldings.length}개)`,
        value: othersValue,
        percent: othersPercent,
        color: COLORS[data.length % COLORS.length],
      });
    }

    const total = data.reduce((sum, item) => sum + item.value, 0);

    return { chartData: data, totalValue: total };
  }, [holdings]);

  // Build animated gradient
  const gradientStyle = useMemo(() => {
    if (chartData.length === 0 || totalValue === 0) {
      return { background: '#e5e7eb' };
    }

    const maxAngle = 360 * animationProgress;
    let currentAngle = 0;
    const gradientParts: string[] = [];
    
    for (const item of chartData) {
      const fullAngle = (item.value / totalValue) * 360;
      const visibleAngle = Math.min(fullAngle, Math.max(0, maxAngle - currentAngle));
      
      if (visibleAngle > 0) {
        gradientParts.push(`${item.color} ${currentAngle}deg ${currentAngle + visibleAngle}deg`);
      }
      currentAngle += fullAngle;
      
      if (currentAngle >= maxAngle) break;
    }

    // Fill remaining with gray during animation
    if (maxAngle < 360) {
      gradientParts.push(`#e5e7eb ${maxAngle}deg 360deg`);
    }

    return {
      background: `conic-gradient(${gradientParts.join(', ')})`,
    };
  }, [chartData, totalValue, animationProgress]);

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
        <div className="flex h-full items-center">
          {/* Donut Chart */}
          <div className="flex-1 flex justify-center">
            <div className="relative">
              {/* Outer ring with gradient */}
              <div
                className="w-52 h-52 rounded-full transition-transform duration-200"
                style={{
                  ...gradientStyle,
                  transform: hoveredIndex !== null ? 'scale(1.02)' : 'scale(1)',
                }}
              />
              {/* Inner circle (donut hole) */}
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="w-32 h-32 rounded-full bg-white flex items-center justify-center shadow-inner">
                  <div className="text-center">
                    <p className="text-xs text-gray-400">총 자산</p>
                    <p className="text-sm font-bold text-gray-800 tabular-nums">
                      {formatNumber(totalValue / 10000, { maximumFractionDigits: 0 })}만
                    </p>
                    <p className="text-xs text-gray-400">{quoteCurrency}</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
          
          {/* Legend */}
          <div className="w-36 flex flex-col justify-center gap-1.5 pl-2">
            {chartData.slice(0, 10).map((item, index) => (
              <div 
                key={item.name} 
                className={`flex items-center gap-1.5 cursor-pointer rounded px-1 py-0.5 transition-colors ${
                  hoveredIndex === index ? 'bg-gray-100' : ''
                }`}
                onMouseEnter={() => setHoveredIndex(index)}
                onMouseLeave={() => setHoveredIndex(null)}
              >
                <div 
                  className="w-2.5 h-2.5 rounded-sm shrink-0" 
                  style={{ backgroundColor: item.color }}
                />
                <span className="text-xs text-gray-600 truncate flex-1">{item.name}</span>
                <span className="text-xs text-gray-400 tabular-nums">{item.percent.toFixed(1)}%</span>
              </div>
            ))}
            {chartData.length > 10 && (
              <div className="text-xs text-gray-400 pl-4">+{chartData.length - 10}개 더</div>
            )}
          </div>

          {/* Tooltip on hover */}
          {hoveredIndex !== null && chartData[hoveredIndex] && (
            <div className="absolute top-4 left-4 bg-white/95 backdrop-blur-sm p-3 rounded-xl shadow-lg border border-gray-100 z-10">
              <p className="font-semibold text-gray-800">{chartData[hoveredIndex].name}</p>
              <p className="text-gray-600 tabular-nums">
                {formatNumber(chartData[hoveredIndex].value, { maximumFractionDigits: quoteCurrency === 'KRW' ? 0 : 2 })} {quoteCurrency}
              </p>
              <p className="text-sm text-gray-400 tabular-nums">{chartData[hoveredIndex].percent.toFixed(2)}%</p>
            </div>
          )}
        </div>
      ) : (
        <div className="h-full flex items-center justify-center text-gray-400 bg-gray-50/50 rounded-xl">
          보유 자산이 없습니다
        </div>
      )}
    </div>
  );

  if (embedded) {
    return <div className="relative">{chartContent}</div>;
  }

  return (
    <div className="card h-full relative">
      <h3 className="text-lg font-semibold text-gray-800 mb-4">포트폴리오 구성</h3>
      {chartContent}
    </div>
  );
}
