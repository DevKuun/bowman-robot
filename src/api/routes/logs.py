"""
Logs API routes with WebSocket support.
"""
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from typing import Optional

from src.api.state import app_state

router = APIRouter()


@router.get("")
async def get_logs(
    limit: int = Query(default=100, le=1000),
    level: Optional[str] = None,
    module: Optional[str] = None
):
    """
    Get recent logs.
    
    Args:
        limit: Maximum number of logs to return
        level: Filter by log level (INFO, WARNING, ERROR)
        module: Filter by module name
    """
    logs = list(app_state.logs)
    
    # Apply filters
    if level:
        logs = [l for l in logs if l.level.upper() == level.upper()]
    if module:
        logs = [l for l in logs if module.lower() in l.module.lower()]
    
    # Get most recent
    logs = logs[-limit:]
    
    # Reverse to show most recent first
    logs.reverse()
    
    return {
        "logs": [l.to_dict() for l in logs],
        "count": len(logs)
    }


@router.websocket("/ws")
async def websocket_logs(websocket: WebSocket):
    """
    WebSocket endpoint for real-time log streaming.
    
    Sends new log entries as they occur.
    """
    await websocket.accept()
    
    # Create a queue for this subscriber
    queue = asyncio.Queue(maxsize=100)
    app_state.log_subscribers.append(queue)
    
    try:
        while True:
            # Wait for new log entry
            log_entry = await queue.get()
            
            # Send to client
            await websocket.send_json(log_entry.to_dict())
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        pass
    finally:
        # Remove subscriber
        if queue in app_state.log_subscribers:
            app_state.log_subscribers.remove(queue)


@router.websocket("/ws/status")
async def websocket_status(websocket: WebSocket):
    """
    WebSocket endpoint for real-time status updates.
    
    Sends bot status and portfolio updates every second.
    """
    await websocket.accept()
    
    try:
        while True:
            # Get current status
            status = app_state.get_status()
            portfolio = app_state.get_portfolio()
            
            # Send combined update
            await websocket.send_json({
                "type": "status_update",
                "status": status,
                "portfolio": {
                    "total_value": portfolio["total_value"],
                    "pnl": portfolio["pnl"],
                    "pnl_percent": portfolio["pnl_percent"]
                }
            })
            
            await asyncio.sleep(1)
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        pass
