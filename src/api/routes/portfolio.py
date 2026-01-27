"""
Portfolio API routes.
"""
from datetime import datetime
from fastapi import APIRouter
from typing import List, Optional

from src.api.state import app_state
from src.config.settings import settings

router = APIRouter()


@router.get("")
async def get_portfolio():
    """
    Get current portfolio data.
    
    Returns holdings with:
    - Currency symbol
    - Amount held
    - Current price
    - Value in quote currency
    - Current weight (%)
    - Target weight (%)
    """
    return app_state.get_portfolio()


@router.get("/pnl")
async def get_pnl_history(
    limit: int = 1000,
    hours: Optional[int] = None,
    session_id: Optional[str] = None
):
    """
    Get PnL history for charting.
    
    For Dashboard: Returns CURRENT SESSION data only.
    For specific session lookup, use session_id parameter.
    
    Args:
        limit: Maximum number of data points to return
        hours: Filter to last N hours (1, 6, 24, 168 for 1w, etc.)
        session_id: Filter by specific trading session
        
    Returns:
        List of PnL snapshots with timestamp, total_value, pnl, pnl_percent
    """
    from datetime import timedelta
    from src.infrastructure.database.connection import db_manager
    from src.infrastructure.database.repositories import PnLSnapshotRepository
    
    # If session_id specified, get from DB
    if session_id:
        try:
            with db_manager.session_scope() as session:
                repo = PnLSnapshotRepository(session)
                snapshots = repo.get_by_session(session_id, limit=limit)
                return {
                    "data": [s.to_dict() for s in snapshots],
                    "count": len(snapshots),
                    "source": "db"
                }
        except Exception as e:
            # Fall back to memory
            pass
    
    # For dashboard: use CURRENT SESSION data only
    # Get current session ID from app_state
    current_session_id = app_state.session_id
    
    # If we have a current session, get data from DB for that session
    if current_session_id:
        try:
            with db_manager.session_scope() as session:
                repo = PnLSnapshotRepository(session)
                snapshots = repo.get_by_session(current_session_id, limit=limit)
                
                # Apply hours filter if specified
                if hours and snapshots:
                    cutoff = datetime.utcnow() - timedelta(hours=hours)
                    snapshots = [s for s in snapshots if s.created_at >= cutoff]
                
                if snapshots:
                    return {
                        "data": [s.to_dict() for s in snapshots],
                        "count": len(snapshots),
                        "source": "db",
                        "session_id": current_session_id
                    }
        except Exception as e:
            # Fall back to memory
            pass
    
    # Fall back to in-memory data (current session only)
    history = app_state.pnl_history[-limit:] if app_state.pnl_history else []
    
    # Apply hours filter to in-memory data if specified
    if hours and history:
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        history = [s for s in history if s.timestamp >= cutoff]
    
    return {
        "data": [s.to_dict() for s in history],
        "count": len(history),
        "source": "memory",
        "session_id": current_session_id
    }


@router.get("/weights")
async def get_portfolio_weights():
    """
    Get portfolio weights comparison.
    
    Returns current vs target weights for each asset.
    """
    portfolio = app_state.get_portfolio()
    
    weights = []
    for holding in portfolio["holdings"]:
        weights.append({
            "currency": holding["currency"],
            "current_weight": holding["current_weight"] * 100,  # Convert to percentage
            "target_weight": holding["target_weight"] * 100,
            "difference": (holding["current_weight"] - holding["target_weight"]) * 100
        })
    
    return {
        "quote_currency": portfolio["quote_currency"],
        "total_value": portfolio["total_value"],
        "weights": weights
    }


@router.get("/summary")
async def get_portfolio_summary():
    """
    Get portfolio summary statistics.
    """
    portfolio = app_state.get_portfolio()
    status = app_state.get_status()
    
    # Count assets by type (use stablecoins from settings)
    stable_value = sum(
        h["value"] for h in portfolio["holdings"] 
        if h["currency"] in settings.stablecoins
    )
    crypto_value = sum(
        h["value"] for h in portfolio["holdings"]
        if h["currency"] not in settings.stablecoins and h["currency"] != portfolio["quote_currency"]
    )
    cash_value = sum(
        h["value"] for h in portfolio["holdings"]
        if h["currency"] == portfolio["quote_currency"]
    )
    
    total = portfolio["total_value"]
    
    return {
        "total_value": total,
        "initial_value": portfolio["initial_value"],
        "pnl": portfolio["pnl"],
        "pnl_percent": portfolio["pnl_percent"],
        "allocation": {
            "cash": cash_value,
            "cash_percent": (cash_value / total * 100) if total > 0 else 0,
            "stablecoins": stable_value,
            "stablecoins_percent": (stable_value / total * 100) if total > 0 else 0,
            "crypto": crypto_value,
            "crypto_percent": (crypto_value / total * 100) if total > 0 else 0
        },
        "asset_count": len(portfolio["holdings"]),
        "total_trades": status["total_trades"],
        "total_fees": status["total_fees"]
    }
