import { ArrowUp, ArrowDown, Minus } from 'lucide-react';
import type { Holding } from '../types';
import { formatNumber } from '../utils/format';

interface PortfolioTableProps {
  holdings: Holding[];
  quoteCurrency: string;
  isLoading: boolean;
}

export function PortfolioTable({ holdings, quoteCurrency, isLoading }: PortfolioTableProps) {
  if (isLoading) {
    return (
      <div className="card animate-pulse">
        <div className="h-5 bg-gray-100 rounded w-1/4 mb-4"></div>
        <div className="space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-12 bg-gray-50 rounded-lg"></div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="card overflow-hidden">
      <h3 className="text-lg font-semibold text-gray-800 mb-4">보유 자산</h3>
      
      <div className="overflow-x-auto -mx-6">
        <table className="w-full min-w-[700px]">
          <thead>
            <tr className="border-b border-gray-100">
              <th className="text-left py-3 px-6 text-xs font-semibold text-gray-400">자산</th>
              <th className="text-right py-3 px-3 text-xs font-semibold text-gray-400">보유량</th>
              <th className="text-right py-3 px-3 text-xs font-semibold text-gray-400">현재가</th>
              <th className="text-right py-3 px-3 text-xs font-semibold text-gray-400">평가금액 ({quoteCurrency})</th>
              <th className="text-right py-3 px-3 text-xs font-semibold text-gray-400">현재 비중</th>
              <th className="text-right py-3 px-3 text-xs font-semibold text-gray-400">목표 비중</th>
              <th className="text-right py-3 px-6 text-xs font-semibold text-gray-400">차이</th>
            </tr>
          </thead>
          <tbody>
            {holdings.map((holding) => {
              const diff = (holding.current_weight - holding.target_weight) * 100;
              const isOverweight = diff > 0.5;
              const isUnderweight = diff < -0.5;
              
              return (
                <tr key={holding.currency} className="border-b border-gray-50 hover:bg-gray-50/50 transition-colors">
                  <td className="py-3 px-6">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-500 flex items-center justify-center text-white text-xs font-bold">
                        {holding.currency.slice(0, 2)}
                      </div>
                      <span className="font-semibold text-gray-800">{holding.currency}</span>
                    </div>
                  </td>
                  <td className="py-3 px-3 text-right text-sm text-gray-600 tabular-nums">
                    {holding.amount < 1 
                      ? holding.amount.toFixed(8) 
                      : formatNumber(holding.amount, { maximumFractionDigits: 4 })}
                  </td>
                  <td className="py-3 px-3 text-right text-sm text-gray-600 tabular-nums">
                    {formatNumber(holding.price, { maximumFractionDigits: 2 })}
                  </td>
                  <td className="py-3 px-3 text-right font-medium text-gray-800 tabular-nums">
                    {formatNumber(holding.value, { maximumFractionDigits: 0 })}
                  </td>
                  <td className="py-3 px-3 text-right text-sm text-gray-600 tabular-nums">
                    {(holding.current_weight * 100).toFixed(2)}%
                  </td>
                  <td className="py-3 px-3 text-right text-sm text-gray-600 tabular-nums">
                    {(holding.target_weight * 100).toFixed(2)}%
                  </td>
                  <td className="py-3 px-6 text-right">
                    <span className={`inline-flex items-center gap-1 text-sm font-medium tabular-nums ${
                      isOverweight ? 'text-red-500' : isUnderweight ? 'text-blue-500' : 'text-gray-400'
                    }`}>
                      {isOverweight && <ArrowUp className="w-3 h-3" />}
                      {isUnderweight && <ArrowDown className="w-3 h-3" />}
                      {!isOverweight && !isUnderweight && <Minus className="w-3 h-3" />}
                      {diff >= 0 ? '+' : ''}{diff.toFixed(2)}%
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {holdings.length === 0 && (
        <div className="text-center py-12 text-gray-400">
          보유 자산이 없습니다
        </div>
      )}
    </div>
  );
}
