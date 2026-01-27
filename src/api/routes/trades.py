"""
Trades API routes.
"""
from fastapi import APIRouter, Query
from typing import Optional

from src.api.state import app_state

router = APIRouter()


@router.get("")
async def get_trades(
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
    symbol: Optional[str] = None,
    side: Optional[str] = None
):
    """
    Get trade history.
    
    Args:
        limit: Maximum number of trades to return
        offset: Number of trades to skip
        symbol: Filter by trading symbol
        side: Filter by side (BUY/SELL)
        
    Returns:
        List of trades with pagination info
    """
    trades = app_state.trades.copy()
    
    # Apply filters
    if symbol:
        trades = [t for t in trades if t.get("symbol", "").upper() == symbol.upper()]
    if side:
        trades = [t for t in trades if t.get("side", "").upper() == side.upper()]
    
    # Sort by timestamp descending (most recent first)
    trades.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    
    # Paginate
    total = len(trades)
    trades = trades[offset:offset + limit]
    
    return {
        "trades": trades,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/summary")
async def get_trades_summary():
    """
    Get trading summary statistics.
    """
    trades = app_state.trades
    
    if not trades:
        return {
            "total_trades": 0,
            "buy_trades": 0,
            "sell_trades": 0,
            "total_volume": 0,
            "total_fees": 0,
            "avg_slippage": 0,
            "max_slippage": 0
        }
    
    buy_trades = [t for t in trades if t.get("side", "").upper() in ["BUY", "BID"]]
    sell_trades = [t for t in trades if t.get("side", "").upper() in ["SELL", "ASK"]]
    
    total_volume = sum(float(t.get("value", 0)) for t in trades)
    total_fees = sum(float(t.get("fee", 0)) for t in trades)
    
    # Calculate slippage stats
    slippages = []
    for t in trades:
        slip_str = t.get("slippage_percent", "0%")
        if isinstance(slip_str, str):
            slip_str = slip_str.replace("%", "")
        try:
            slippages.append(float(slip_str))
        except:
            pass
    
    avg_slippage = sum(slippages) / len(slippages) if slippages else 0
    max_slippage = max(slippages) if slippages else 0
    
    return {
        "total_trades": len(trades),
        "buy_trades": len(buy_trades),
        "sell_trades": len(sell_trades),
        "total_volume": total_volume,
        "total_fees": total_fees,
        "avg_slippage": avg_slippage,
        "max_slippage": max_slippage
    }


@router.get("/by-asset")
async def get_trades_by_asset():
    """
    Get trade count and volume by asset.
    """
    trades = app_state.trades
    
    asset_stats = {}
    for trade in trades:
        symbol = trade.get("symbol", "UNKNOWN")
        
        if symbol not in asset_stats:
            asset_stats[symbol] = {
                "symbol": symbol,
                "trade_count": 0,
                "buy_count": 0,
                "sell_count": 0,
                "total_volume": 0,
                "total_fees": 0
            }
        
        asset_stats[symbol]["trade_count"] += 1
        asset_stats[symbol]["total_volume"] += float(trade.get("value", 0))
        asset_stats[symbol]["total_fees"] += float(trade.get("fee", 0))
        
        side = trade.get("side", "").upper()
        if side in ["BUY", "BID"]:
            asset_stats[symbol]["buy_count"] += 1
        else:
            asset_stats[symbol]["sell_count"] += 1
    
    # Sort by trade count
    result = sorted(asset_stats.values(), key=lambda x: x["trade_count"], reverse=True)
    
    return {"assets": result}
