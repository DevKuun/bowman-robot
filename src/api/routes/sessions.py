"""
Trading session API routes.
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.infrastructure.database.connection import db_manager
from src.infrastructure.database.repositories import (
    TradingSessionRepository, 
    TradeRepository,
    PnLSnapshotRepository
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionResponse(BaseModel):
    id: str
    session_id: str
    exchange: str
    mode: str
    risk_level: int
    initial_balance: Optional[float]
    status: str
    total_trades: int
    total_fees: float
    final_pnl: Optional[float]
    final_pnl_percent: Optional[float]
    started_at: Optional[str]
    ended_at: Optional[str]


class TradeResponse(BaseModel):
    id: str
    symbol: str
    side: str
    quantity: float
    price: float
    value: Optional[float]
    fee: float
    status: str
    slippage_percent: Optional[float]
    created_at: Optional[str]
    executed_at: Optional[str]


@router.get("", response_model=List[SessionResponse])
async def get_sessions(
    exchange: Optional[str] = None,
    mode: Optional[str] = None,
    limit: int = 50
):
    """Get all trading sessions."""
    with db_manager.session_scope() as session:
        repo = TradingSessionRepository(session)
        sessions = repo.get_all(exchange=exchange, mode=mode, limit=limit)
        return [s.to_dict() for s in sessions]


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """Get a specific trading session."""
    with db_manager.session_scope() as session:
        repo = TradingSessionRepository(session)
        trading_session = repo.get_by_session_id(session_id)
        if not trading_session:
            raise HTTPException(status_code=404, detail="Session not found")
        return trading_session.to_dict()


@router.get("/{session_id}/trades", response_model=List[TradeResponse])
async def get_session_trades(session_id: str, limit: int = 1000):
    """Get all trades for a trading session."""
    with db_manager.session_scope() as session:
        trade_repo = TradeRepository(session)
        trades = trade_repo.get_by_session_id(session_id, limit=limit)
        return [t.to_dict() for t in trades]


class PnLSnapshotResponse(BaseModel):
    timestamp: str
    total_value: float
    pnl: float
    pnl_percent: float


class SessionDetailResponse(BaseModel):
    session: SessionResponse
    trades: List[TradeResponse]
    pnl_history: List[PnLSnapshotResponse]
    summary: dict


@router.get("/{session_id}/pnl", response_model=List[PnLSnapshotResponse])
async def get_session_pnl(session_id: str, limit: int = 1000):
    """Get PnL history for a trading session."""
    with db_manager.session_scope() as session:
        pnl_repo = PnLSnapshotRepository(session)
        snapshots = pnl_repo.get_by_session(session_id, limit=limit)
        return [s.to_dict() for s in snapshots]


@router.get("/{session_id}/detail")
async def get_session_detail(session_id: str):
    """Get complete session detail including trades, PnL history, and summary."""
    from src.api.state import app_state
    
    with db_manager.session_scope() as session:
        session_repo = TradingSessionRepository(session)
        trade_repo = TradeRepository(session)
        pnl_repo = PnLSnapshotRepository(session)
        
        # Get session
        trading_session = session_repo.get_by_session_id(session_id)
        if not trading_session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Check if this is the current running session
        is_current_session = (
            app_state.session_id == session_id and 
            app_state.bot_running
        )
        
        # Get trades - use real-time data for current session
        if is_current_session and app_state.trades:
            trades_data = app_state.trades
        else:
            db_trades = trade_repo.get_by_session_id(session_id, limit=1000)
            trades_data = [t.to_dict() for t in db_trades]
        
        # Get PnL snapshots - combine DB and real-time for current session
        db_snapshots = pnl_repo.get_by_session(session_id, limit=1000)
        pnl_data = [s.to_dict() for s in db_snapshots]
        
        # For current session, also include in-memory snapshots (deduplicated by timestamp)
        if is_current_session and app_state.pnl_history:
            existing_timestamps = set(s.get('timestamp') for s in pnl_data)
            
            for snapshot in app_state.pnl_history:
                snap_dict = snapshot.to_dict() if hasattr(snapshot, 'to_dict') else {
                    'timestamp': snapshot.timestamp.isoformat() if hasattr(snapshot.timestamp, 'isoformat') else str(snapshot.timestamp),
                    'total_value': float(snapshot.total_value) if hasattr(snapshot, 'total_value') else snapshot.get('total_value', 0),
                    'pnl': float(snapshot.pnl) if hasattr(snapshot, 'pnl') else snapshot.get('pnl', 0),
                    'pnl_percent': float(snapshot.pnl_percent) if hasattr(snapshot, 'pnl_percent') else snapshot.get('pnl_percent', 0),
                }
                # Only add if timestamp not already in pnl_data
                if snap_dict.get('timestamp') not in existing_timestamps:
                    pnl_data.append(snap_dict)
                    existing_timestamps.add(snap_dict.get('timestamp'))
            
            # Sort by timestamp
            pnl_data.sort(key=lambda x: x.get('timestamp', ''))
        
        # Calculate summary
        buy_trades = [t for t in trades_data if t.get('side', '').upper() == 'BUY']
        sell_trades = [t for t in trades_data if t.get('side', '').upper() == 'SELL']
        total_volume = sum(float(t.get('value') or 0) for t in trades_data)
        total_fees = sum(float(t.get('fee') or 0) for t in trades_data)
        
        # Parse slippage values - handle both string ("0.1234%") and number formats
        slippages = []
        for t in trades_data:
            slip_val = t.get('slippage_percent')
            if slip_val is not None:
                if isinstance(slip_val, (int, float)):
                    slippages.append(float(slip_val))
                elif isinstance(slip_val, str):
                    cleaned = slip_val.replace('%', '').strip()
                    if cleaned:
                        try:
                            slippages.append(float(cleaned))
                        except ValueError:
                            pass
        avg_slippage = sum(slippages) / len(slippages) if slippages else 0
        max_slippage = max(slippages) if slippages else 0
        
        # Assets breakdown
        assets = {}
        for t in trades_data:
            symbol = t.get('symbol', '')
            if symbol not in assets:
                assets[symbol] = {'symbol': symbol, 'trade_count': 0, 'buy_count': 0, 'sell_count': 0}
            assets[symbol]['trade_count'] += 1
            if t.get('side', '').upper() == 'BUY':
                assets[symbol]['buy_count'] += 1
            else:
                assets[symbol]['sell_count'] += 1
        
        # Update session status for current running session
        session_dict = trading_session.to_dict()
        if is_current_session:
            session_dict['status'] = 'running'
            # Add current PnL
            if app_state.pnl_history:
                last_snapshot = app_state.pnl_history[-1]
                session_dict['final_pnl'] = float(last_snapshot.pnl) if hasattr(last_snapshot, 'pnl') else last_snapshot.get('pnl', 0)
                session_dict['final_pnl_percent'] = float(last_snapshot.pnl_percent) if hasattr(last_snapshot, 'pnl_percent') else last_snapshot.get('pnl_percent', 0)
        
        return {
            "session": session_dict,
            "trades": trades_data,
            "pnl_history": pnl_data,
            "is_current": is_current_session,
            "summary": {
                "total_trades": len(trades_data),
                "buy_trades": len(buy_trades),
                "sell_trades": len(sell_trades),
                "total_volume": total_volume,
                "total_fees": total_fees,
                "avg_slippage": avg_slippage,
                "max_slippage": max_slippage,
            },
            "assets": list(assets.values())
        }


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """Delete a trading session and all its trades."""
    with db_manager.session_scope() as session:
        repo = TradingSessionRepository(session)
        trading_session = repo.get_by_session_id(session_id)
        if not trading_session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        session.delete(trading_session)
        return {"message": "Session deleted", "session_id": session_id}
