"""
Unified WebSocket endpoint for real-time data streaming.
"""
import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Set
from decimal import Decimal

from src.api.state import app_state
from src.config.settings import settings

router = APIRouter()

# Global set of connected WebSocket clients
connected_clients: Set[WebSocket] = set()


def _calculate_trades_summary() -> dict:
    """Calculate trades summary for WebSocket broadcast."""
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


def _calculate_portfolio_summary(portfolio: dict, status: dict) -> dict:
    """Calculate portfolio summary for WebSocket broadcast."""
    quote_currency = portfolio.get("quote_currency", "KRW")
    holdings = portfolio.get("holdings", [])
    
    stable_value = sum(
        h["value"] for h in holdings 
        if h["currency"] in settings.stablecoins
    )
    crypto_value = sum(
        h["value"] for h in holdings
        if h["currency"] not in settings.stablecoins and h["currency"] != quote_currency
    )
    cash_value = sum(
        h["value"] for h in holdings
        if h["currency"] == quote_currency
    )
    
    total = portfolio.get("total_value", 0)
    
    return {
        "total_value": total,
        "initial_value": portfolio.get("initial_value", total),
        "pnl": portfolio.get("pnl", 0),
        "pnl_percent": portfolio.get("pnl_percent", 0),
        "allocation": {
            "cash": cash_value,
            "cash_percent": (cash_value / total * 100) if total > 0 else 0,
            "stablecoins": stable_value,
            "stablecoins_percent": (stable_value / total * 100) if total > 0 else 0,
            "crypto": crypto_value,
            "crypto_percent": (crypto_value / total * 100) if total > 0 else 0
        },
        "asset_count": len(holdings),
        "total_trades": status.get("total_trades", 0),
        "total_fees": status.get("total_fees", 0)
    }


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal types."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


async def broadcast_message(message_type: str, data: dict):
    """Broadcast a message to all connected clients."""
    if not connected_clients:
        return
    
    message = json.dumps({
        "type": message_type,
        "data": data
    }, cls=DecimalEncoder)
    
    disconnected = set()
    for client in connected_clients:
        try:
            await client.send_text(message)
        except Exception:
            disconnected.add(client)
    
    # Remove disconnected clients
    for client in disconnected:
        connected_clients.discard(client)


@router.websocket("")
async def websocket_unified(websocket: WebSocket):
    """
    Unified WebSocket endpoint for real-time updates.
    
    Sends all types of events:
    - status: Bot status updates
    - portfolio: Portfolio value and holdings
    - trade: New trade executed
    - pnl: PnL snapshot
    - log: Log entry
    """
    await websocket.accept()
    connected_clients.add(websocket)
    
    # Create a queue for log messages
    log_queue = asyncio.Queue(maxsize=100)
    app_state.log_subscribers.append(log_queue)
    
    try:
        # Send initial state
        initial_data = {
            "status": app_state.get_status(),
            "portfolio": app_state.get_portfolio(),
            "trades": [t for t in app_state.trades[-50:]],  # Last 50 trades
        }
        await websocket.send_text(json.dumps({
            "type": "init",
            "data": initial_data
        }, cls=DecimalEncoder))
        
        # Create tasks for sending updates
        async def send_status_updates():
            """Periodically send status and portfolio updates."""
            while True:
                try:
                    status = app_state.get_status()
                    portfolio = app_state.get_portfolio()
                    trades_summary = _calculate_trades_summary()
                    portfolio_summary = _calculate_portfolio_summary(portfolio, status)
                    
                    await websocket.send_text(json.dumps({
                        "type": "status",
                        "data": status
                    }, cls=DecimalEncoder))
                    
                    await websocket.send_text(json.dumps({
                        "type": "portfolio",
                        "data": portfolio
                    }, cls=DecimalEncoder))
                    
                    await websocket.send_text(json.dumps({
                        "type": "trades_summary",
                        "data": trades_summary
                    }, cls=DecimalEncoder))
                    
                    await websocket.send_text(json.dumps({
                        "type": "portfolio_summary",
                        "data": portfolio_summary
                    }, cls=DecimalEncoder))
                    
                    await asyncio.sleep(1)  # Update every second
                except Exception:
                    break
        
        async def send_log_updates():
            """Send log updates as they arrive."""
            while True:
                try:
                    log_entry = await log_queue.get()
                    await websocket.send_text(json.dumps({
                        "type": "log",
                        "data": log_entry.to_dict()
                    }, cls=DecimalEncoder))
                except Exception:
                    break
        
        async def receive_messages():
            """Handle incoming messages (for ping/pong)."""
            while True:
                try:
                    data = await websocket.receive_text()
                    # Handle ping messages
                    if data == "ping":
                        await websocket.send_text("pong")
                except Exception:
                    break
        
        # Run all tasks concurrently
        await asyncio.gather(
            send_status_updates(),
            send_log_updates(),
            receive_messages(),
            return_exceptions=True
        )
        
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        connected_clients.discard(websocket)
        if log_queue in app_state.log_subscribers:
            app_state.log_subscribers.remove(log_queue)


# Functions to broadcast specific events (called from other parts of the app)
async def broadcast_trade(trade: dict):
    """Broadcast a new trade to all clients."""
    await broadcast_message("trade", trade)


async def broadcast_pnl(pnl_data: dict):
    """Broadcast PnL update to all clients."""
    await broadcast_message("pnl", pnl_data)
