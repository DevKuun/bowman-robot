"""
Application state management for the trading bot.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any
from collections import deque

from src.core.models import ExchangeType

logger = logging.getLogger(__name__)


@dataclass
class LogEntry:
    """Log entry for the dashboard."""
    timestamp: datetime
    level: str
    message: str
    module: str
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level,
            "message": self.message,
            "module": self.module
        }


@dataclass 
class PnLSnapshot:
    """PnL snapshot for charting with benchmark data."""
    timestamp: datetime
    total_value: Decimal
    pnl: Decimal
    pnl_percent: Decimal
    btc_price: Optional[Decimal] = None
    eth_price: Optional[Decimal] = None
    btc_return: Optional[Decimal] = None  # BTC return since session start (%)
    eth_return: Optional[Decimal] = None  # ETH return since session start (%)
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_value": float(self.total_value),
            "pnl": float(self.pnl),
            "pnl_percent": float(self.pnl_percent),
            "btc_price": float(self.btc_price) if self.btc_price else None,
            "eth_price": float(self.eth_price) if self.eth_price else None,
            "btc_return": float(self.btc_return) if self.btc_return else None,
            "eth_return": float(self.eth_return) if self.eth_return else None,
        }


class AppState:
    """
    Global application state for the trading bot.
    Manages bot status, logs, and real-time data.
    """
    
    def __init__(self):
        # Bot state
        self.bot_running: bool = False
        self.bot_mode: str = "stopped"  # stopped, paper, live
        self.bot_exchange: Optional[ExchangeType] = None
        self.bot_task: Optional[asyncio.Task] = None
        self.bot_start_time: Optional[datetime] = None
        self.session_id: Optional[str] = None  # Unique ID for each trading session
        
        # Scheduler reference
        self.scheduler = None
        
        # Logs (circular buffer)
        self.logs: deque = deque(maxlen=1000)
        self.log_subscribers: List[asyncio.Queue] = []
        
        # PnL history for charting (in-memory cache)
        self.pnl_history: List[PnLSnapshot] = []
        
        # Current portfolio state
        self.current_balances: Dict[str, Decimal] = {}
        self.current_prices: Dict[str, Decimal] = {}
        self.target_weights: Dict[str, float] = {}
        
        # Trade history
        self.trades: List[dict] = []
        
        # Statistics
        self.total_trades: int = 0
        self.total_fees: Decimal = Decimal("0")
        
        # Benchmark prices at session start (for calculating returns)
        self.initial_btc_price: Optional[Decimal] = None
        self.initial_eth_price: Optional[Decimal] = None
        self.initial_value: Optional[Decimal] = None
        
    def add_log(self, level: str, message: str, module: str = "system"):
        """Add a log entry and notify subscribers."""
        entry = LogEntry(
            timestamp=datetime.utcnow(),
            level=level,
            message=message,
            module=module
        )
        self.logs.append(entry)
        
        # Notify WebSocket subscribers
        for queue in self.log_subscribers:
            try:
                queue.put_nowait(entry)
            except asyncio.QueueFull:
                pass  # Skip if queue is full
    
    def add_pnl_snapshot(self, total_value: Decimal, pnl: Decimal, pnl_percent: Decimal):
        """Add a PnL snapshot to memory and DB with benchmark data."""
        # Get current BTC/ETH prices
        btc_price = self._get_benchmark_price('BTC')
        eth_price = self._get_benchmark_price('ETH')
        
        # Initialize benchmark prices if first snapshot (set return to 0% for first snapshot)
        is_first_btc = self.initial_btc_price is None and btc_price
        is_first_eth = self.initial_eth_price is None and eth_price
        
        if is_first_btc:
            self.initial_btc_price = btc_price
        if is_first_eth:
            self.initial_eth_price = eth_price
        
        # Calculate benchmark returns (0% for first snapshot, calculated for subsequent)
        btc_return = None
        eth_return = None
        if btc_price and self.initial_btc_price and self.initial_btc_price > 0:
            btc_return = Decimal("0") if is_first_btc else ((btc_price - self.initial_btc_price) / self.initial_btc_price) * 100
        if eth_price and self.initial_eth_price and self.initial_eth_price > 0:
            eth_return = Decimal("0") if is_first_eth else ((eth_price - self.initial_eth_price) / self.initial_eth_price) * 100
        
        snapshot = PnLSnapshot(
            timestamp=datetime.utcnow(),
            total_value=total_value,
            pnl=pnl,
            pnl_percent=pnl_percent,
            btc_price=btc_price,
            eth_price=eth_price,
            btc_return=btc_return,
            eth_return=eth_return
        )
        self.pnl_history.append(snapshot)
        
        # Keep last 1000 snapshots in memory
        if len(self.pnl_history) > 1000:
            self.pnl_history = self.pnl_history[-1000:]
        
        # Broadcast PnL via WebSocket
        self._broadcast_pnl(snapshot.to_dict())
        
        # Save to DB
        if self.session_id and self.bot_exchange:
            try:
                from src.infrastructure.database.connection import db_manager
                from src.infrastructure.database.repositories import PnLSnapshotRepository
                
                with db_manager.session_scope() as session:
                    repo = PnLSnapshotRepository(session)
                    repo.create(
                        exchange=self.bot_exchange.value,
                        session_id=self.session_id,
                        total_value=float(total_value),
                        pnl=float(pnl),
                        pnl_percent=float(pnl_percent),
                        initial_value=float(self.initial_value) if self.initial_value else None,
                        btc_price=float(btc_price) if btc_price else None,
                        eth_price=float(eth_price) if eth_price else None,
                        btc_return=float(btc_return) if btc_return else None,
                        eth_return=float(eth_return) if eth_return else None
                    )
            except Exception as e:
                logger.warning(f"Failed to save PnL snapshot to DB: {e}")
    
    def _get_benchmark_price(self, currency: str) -> Optional[Decimal]:
        """Get current price for a benchmark currency (BTC, ETH)."""
        if not self.current_prices:
            return None
        
        # Try different symbol formats based on exchange
        possible_symbols = [
            f"KRW-{currency}",  # Upbit format
            f"{currency.lower()}_krw",  # Korbit format
            f"{currency}USDT",  # Binance format
            f"{currency}KRW",  # Alternative format
        ]
        
        for symbol in possible_symbols:
            if symbol in self.current_prices:
                return self.current_prices[symbol]
        
        return None
    
    def _broadcast_pnl(self, pnl_data: dict):
        """Broadcast PnL to WebSocket clients."""
        try:
            import asyncio
            from src.api.routes.websocket import broadcast_pnl
            
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(broadcast_pnl(pnl_data))
            else:
                loop.run_until_complete(broadcast_pnl(pnl_data))
        except Exception as e:
            logger.debug(f"Failed to broadcast PnL: {e}")
    
    def add_trade(self, trade: dict):
        """Add a trade record."""
        self.trades.append(trade)
        self.total_trades += 1
        
        # Keep last 1000 trades
        if len(self.trades) > 1000:
            self.trades = self.trades[-1000:]
        
        # Broadcast trade via WebSocket
        self._broadcast_trade(trade)
    
    def _broadcast_trade(self, trade: dict):
        """Broadcast trade to WebSocket clients."""
        try:
            import asyncio
            from src.api.routes.websocket import broadcast_trade
            
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(broadcast_trade(trade))
            else:
                loop.run_until_complete(broadcast_trade(trade))
        except Exception as e:
            logger.debug(f"Failed to broadcast trade: {e}")
    
    def update_portfolio(self, balances: Dict[str, Decimal], prices: Dict[str, Decimal]):
        """Update current portfolio state."""
        self.current_balances = balances
        self.current_prices = prices
    
    def get_status(self) -> dict:
        """Get current bot status with real-time PnL."""
        uptime = None
        if self.bot_start_time:
            uptime = (datetime.utcnow() - self.bot_start_time).total_seconds()
        
        # Determine quote currency based on exchange
        quote_currency = "KRW"
        if self.bot_exchange == ExchangeType.BINANCE:
            quote_currency = "USDT"
        
        status = {
            "running": self.bot_running,
            "mode": self.bot_mode,
            "exchange": self.bot_exchange.value if self.bot_exchange else None,
            "start_time": self.bot_start_time.isoformat() if self.bot_start_time else None,
            "uptime_seconds": uptime,
            "total_trades": self.total_trades,
            "total_fees": float(self.total_fees) if self.total_fees else 0,
            "session_id": self.session_id,
            "quote_currency": quote_currency
        }
        
        # Add real-time PnL if bot is running
        if self.bot_running and self.scheduler and hasattr(self.scheduler, 'paper_account'):
            try:
                pnl, pnl_pct, total_value = self.scheduler.paper_account.calculate_pnl()
                status["current_pnl"] = float(pnl)
                status["current_pnl_percent"] = float(pnl_pct)
                status["total_value"] = float(total_value)
                status["initial_value"] = float(self.initial_value) if self.initial_value else float(total_value)
                if hasattr(self.scheduler, 'iteration_count'):
                    status["iteration_count"] = self.scheduler.iteration_count
                if hasattr(self.scheduler, 'risk_level'):
                    status["risk_level"] = self.scheduler.risk_level
            except Exception as e:
                logger.warning(f"Failed to get real-time PnL: {e}")
        
        return status
    
    def get_portfolio(self) -> dict:
        """Get current portfolio data."""
        import logging
        logger = logging.getLogger(__name__)
        
        quote_currency = "KRW"
        if self.bot_exchange == ExchangeType.BINANCE:
            quote_currency = "USDT"
        
        # Use scheduler's paper_account for accurate real-time values if available
        real_total_value = None
        real_pnl = None
        real_pnl_percent = None
        
        if self.scheduler and hasattr(self.scheduler, 'paper_account'):
            try:
                # Get all values from single calculation to ensure consistency
                real_pnl, real_pnl_percent, real_total_value = self.scheduler.paper_account.calculate_pnl()
            except Exception as e:
                logger.warning(f"Failed to get real-time portfolio values: {e}")
        
        # Debug logging
        if len(self.current_balances) > 0 and len(self.current_prices) > 0:
            logger.debug(f"[PORTFOLIO] Exchange: {self.bot_exchange}, Quote: {quote_currency}")
            logger.debug(f"[PORTFOLIO] Balances: {len(self.current_balances)}, Prices: {len(self.current_prices)}")
        
        # Calculate values and weights
        holdings = []
        total_value = Decimal("0")
        price_miss_count = 0
        
        for currency, amount in self.current_balances.items():
            if amount <= 0:
                continue
                
            if currency == quote_currency:
                value = amount
                price = Decimal("1")
            else:
                # Find price based on exchange format
                if self.bot_exchange == ExchangeType.UPBIT:
                    symbol = f"KRW-{currency}"
                elif self.bot_exchange == ExchangeType.BITHUMB:
                    symbol = f"{currency}_KRW"
                elif self.bot_exchange == ExchangeType.KORBIT:
                    symbol = f"{currency.lower()}_krw"
                else:  # BINANCE
                    symbol = f"{currency}USDT"
                
                price = self.current_prices.get(symbol, Decimal("0"))
                if price == 0 and price_miss_count < 3:
                    # Log first few price misses for debugging
                    available_symbols = [k for k in self.current_prices.keys() if currency in k.upper()]
                    logger.warning(f"[PORTFOLIO] Price not found for {symbol}, available with {currency}: {available_symbols[:3]}")
                    price_miss_count += 1
                value = amount * price
            
            total_value += value
            holdings.append({
                "currency": currency,
                "amount": float(amount),
                "price": float(price),
                "value": float(value),
                "target_weight": self.target_weights.get(currency, 0)
            })
        
        # Calculate current weights
        for h in holdings:
            h["current_weight"] = h["value"] / float(total_value) if total_value > 0 else 0
        
        # Sort by value descending
        holdings.sort(key=lambda x: x["value"], reverse=True)
        
        # Use real-time values from scheduler if available, otherwise calculate
        if real_total_value is not None:
            final_total_value = float(real_total_value)
            final_pnl = float(real_pnl)
            final_pnl_percent = float(real_pnl_percent)
        else:
            final_total_value = float(total_value)
            if self.initial_value and self.initial_value > 0:
                final_pnl = float(total_value - self.initial_value)
                final_pnl_percent = float((total_value - self.initial_value) / self.initial_value * 100)
            else:
                final_pnl = 0.0
                final_pnl_percent = 0.0
        
        return {
            "quote_currency": quote_currency,
            "total_value": final_total_value,
            "initial_value": float(self.initial_value) if self.initial_value else final_total_value,
            "pnl": final_pnl,
            "pnl_percent": final_pnl_percent,
            "holdings": holdings
        }
    
    def start_bot(self, exchange: ExchangeType, mode: str, session_id: Optional[str] = None):
        """Mark bot as started."""
        import uuid
        self.bot_running = True
        self.bot_mode = mode
        self.bot_exchange = exchange
        self.bot_start_time = datetime.utcnow()
        # Use provided session_id or generate a new one
        self.session_id = session_id or f"{exchange.value}_{mode}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        self.add_log("INFO", f"Bot started in {mode} mode for {exchange.value}", "bot")
    
    def stop_bot(self):
        """Mark bot as stopped."""
        if self.bot_task and not self.bot_task.done():
            self.bot_task.cancel()
        
        self.bot_running = False
        self.bot_mode = "stopped"
        self.bot_task = None
        self.scheduler = None
        self.add_log("INFO", "Bot stopped", "bot")
    
    def reset_stats(self):
        """Reset statistics for a new session."""
        self.pnl_history.clear()
        self.trades.clear()
        self.total_trades = 0
        self.total_fees = Decimal("0")
        self.initial_value = None
        self.current_balances.clear()
        self.current_prices.clear()
        self.initial_btc_price = None
        self.initial_eth_price = None


# Global state instance
app_state = AppState()


class DashboardLogHandler(logging.Handler):
    """Custom log handler that sends logs to the dashboard."""
    
    def emit(self, record):
        try:
            message = self.format(record)
            app_state.add_log(
                level=record.levelname,
                message=message,
                module=record.name
            )
        except Exception:
            self.handleError(record)
