import { ArrowUpRight, ArrowDownRight } from 'lucide-react';
import type { Trade } from '../types';
import { formatDateTimeKST, formatNumber } from '../utils/format';

interface TradeTableProps {
  trades: Trade[];
  isLoading: boolean;
}

export function TradeTable({ trades, isLoading }: TradeTableProps) {
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
      <h3 className="text-lg font-semibold text-gray-800 mb-4">최근 거래</h3>
      
      <div className="overflow-x-auto -mx-6">
        <table className="w-full min-w-[850px]">
          <thead>
            <tr className="border-b border-gray-100">
              <th className="text-left py-3 px-6 text-xs font-semibold text-gray-400">시간 (KST)</th>
              <th className="text-left py-3 px-3 text-xs font-semibold text-gray-400">심볼</th>
              <th className="text-left py-3 px-3 text-xs font-semibold text-gray-400">유형</th>
              <th className="text-right py-3 px-3 text-xs font-semibold text-gray-400">수량</th>
              <th className="text-right py-3 px-3 text-xs font-semibold text-gray-400">가격</th>
              <th className="text-right py-3 px-3 text-xs font-semibold text-gray-400">금액</th>
              <th className="text-right py-3 px-3 text-xs font-semibold text-gray-400">수수료</th>
              <th className="text-right py-3 px-6 text-xs font-semibold text-gray-400">슬리피지</th>
            </tr>
          </thead>
          <tbody>
            {trades.slice(0, 50).map((trade, index) => {
              const isBuy = (trade.side || '').toUpperCase() === 'BUY' || (trade.side || '').toUpperCase() === 'BID';
              // Handle both string ("0.1234%") and number formats for slippage
              let slippage = 0;
              if (trade.slippage_percent != null) {
                if (typeof trade.slippage_percent === 'string') {
                  slippage = parseFloat(trade.slippage_percent.replace('%', '')) || 0;
                } else {
                  slippage = trade.slippage_percent;
                }
              }
              // Handle both string and number formats for fee
              const fee = trade.fee != null ? (typeof trade.fee === 'string' ? parseFloat(trade.fee) : trade.fee) : 0;
              const isBelowMinimum = trade.below_minimum === true;
              const isSlippageReduced = trade.slippage_reduced === true;
              
              // Determine tooltip message
              let tooltipMessage: string | undefined;
              if (isBelowMinimum) {
                if (isSlippageReduced) {
                  tooltipMessage = '최소 거래금액 미만 (슬리피지로 인해 체결금액 감소)';
                } else {
                  tooltipMessage = '최소 거래금액 미만';
                }
              }
              
              return (
                <tr 
                  key={index} 
                  className={`border-b border-gray-50 hover:bg-gray-50/50 transition-colors ${
                    isBelowMinimum ? 'opacity-40' : ''
                  }`}
                  title={tooltipMessage}
                >
                  <td className="py-3 px-6 text-sm text-gray-500 tabular-nums">
                    {formatDateTimeKST(trade.timestamp)}
                  </td>
                  <td className="py-3 px-3">
                    <span className="font-medium text-gray-800">{trade.symbol}</span>
                  </td>
                  <td className="py-3 px-3">
                    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold ${
                      isBuy 
                        ? 'bg-emerald-50 text-emerald-600' 
                        : 'bg-red-50 text-red-600'
                    }`}>
                      {isBuy ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                      {isBuy ? '매수' : '매도'}
                      {isBelowMinimum && (
                        <span className={`ml-1 ${isSlippageReduced ? 'text-amber-500' : 'text-gray-400'}`}>
                          {isSlippageReduced ? '📉' : '⚠'}
                        </span>
                      )}
                    </span>
                  </td>
                  <td className="py-3 px-3 text-right text-sm text-gray-600 tabular-nums">
                    {(typeof trade.quantity === 'number' ? trade.quantity : parseFloat(trade.quantity || '0')).toFixed(8)}
                  </td>
                  <td className="py-3 px-3 text-right text-sm text-gray-600 tabular-nums">
                    {formatNumber(typeof trade.price === 'number' ? trade.price : parseFloat(trade.price || '0'), { maximumFractionDigits: 2 })}
                  </td>
                  <td className="py-3 px-3 text-right font-medium text-gray-800 tabular-nums">
                    {formatNumber(typeof trade.value === 'number' ? trade.value : parseFloat(trade.value || '0'), { maximumFractionDigits: 0 })}
                  </td>
                  <td className="py-3 px-3 text-right text-sm text-purple-600 tabular-nums">
                    {fee < 1 && fee > 0 
                      ? fee.toFixed(4)
                      : formatNumber(fee, { maximumFractionDigits: 2 })}
                  </td>
                  <td className={`py-3 px-6 text-right text-sm tabular-nums ${
                    slippage > 0.1 ? 'text-amber-600' : 'text-gray-400'
                  }`}>
                    {slippage.toFixed(3)}%
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {trades.length === 0 && (
        <div className="text-center py-12 text-gray-400">
          거래 내역이 없습니다
        </div>
      )}
      
      {trades.length > 50 && (
        <div className="text-center py-3 text-sm text-gray-400 border-t border-gray-100">
          최근 50건 표시 중 (총 {trades.length}건)
        </div>
      )}
    </div>
  );
}
