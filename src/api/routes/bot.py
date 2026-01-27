"""
Bot control API routes.
"""
import asyncio
import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.api.state import app_state, DashboardLogHandler
from src.core.models import ExchangeType
from src.workers.scheduler import run_scheduler, PaperTradingScheduler
from src.workers.portfolio_worker import (
    PortfolioWorker, 
    request_cancellation, 
    reset_cancellation,
    is_cancelled
)
from src.config.settings import settings
from src.infrastructure.database.connection import db_manager
from src.infrastructure.database.repositories import (
    TradingSessionRepository, 
    TradeRepository,
    PortfolioWeightRepository
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Current trading session info
_current_session_id: Optional[str] = None
_current_session_uuid: Optional[uuid.UUID] = None

# Track ongoing optimization task
_optimization_task: Optional[asyncio.Task] = None
_optimization_cancelled: bool = False


class StartBotRequest(BaseModel):
    """Request to start the bot."""
    exchange: str
    mode: str = "paper"  # paper or live
    initial_balance: float = 5000000
    risk_level: int = 2
    realistic_execution: bool = True
    skip_optimization: bool = False  # Skip portfolio optimization if weights exist


class OptimizeRequest(BaseModel):
    """Request to run portfolio optimization."""
    exchange: str
    force: bool = False  # Force re-optimization even if recent weights exist


class StopBotResponse(BaseModel):
    """Response after stopping the bot."""
    success: bool
    message: str


@router.get("/status")
async def get_bot_status():
    """Get current bot status with real-time PnL."""
    # get_status() now includes PnL calculation
    return app_state.get_status()


@router.post("/start")
async def start_bot(request: StartBotRequest):
    """Start the trading bot."""
    global _current_session_id, _current_session_uuid
    
    if app_state.bot_running:
        raise HTTPException(status_code=400, detail="Bot is already running")
    
    # Map exchange string to enum
    exchange_map = {
        "upbit": ExchangeType.UPBIT,
        "binance": ExchangeType.BINANCE,
        "korbit": ExchangeType.KORBIT,
        "bithumb": ExchangeType.BITHUMB
    }
    
    exchange = exchange_map.get(request.exchange.lower())
    if not exchange:
        raise HTTPException(status_code=400, detail=f"Invalid exchange: {request.exchange}")
    
    # Create trading session
    session_id = f"{exchange.value}_{request.mode}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    
    with db_manager.session_scope() as session:
        session_repo = TradingSessionRepository(session)
        trading_session = session_repo.create(
            session_id=session_id,
            exchange=exchange.value,
            mode=request.mode,
            risk_level=request.risk_level,
            initial_balance=request.initial_balance if request.mode == "paper" else None
        )
        _current_session_id = session_id
        _current_session_uuid = trading_session.id
        logger.info(f"Created trading session: {session_id}")
    
    # Setup dashboard log handler
    dashboard_handler = DashboardLogHandler()
    dashboard_handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(dashboard_handler)
    
    # Reset stats for new session
    app_state.reset_stats()
    
    # Start bot in background
    async def run_bot():
        global _current_session_id, _current_session_uuid
        try:
            from decimal import Decimal
            from src.simulation.paper_trading import PaperTradingAccount, PaperTradingExchange
            from src.exchanges.upbit import UpbitExchange
            from src.exchanges.bithumb import BithumbExchange
            from src.exchanges.korbit import KorbitExchange
            from src.exchanges.binance import BinanceExchange
            from src.workers.portfolio_worker import PortfolioWorker
            
            if request.mode == "paper":
                # Create scheduler with skip_optimization option
                scheduler = PaperTradingScheduler(
                    exchange_type=exchange,
                    initial_balance=request.initial_balance,
                    risk_level=request.risk_level,
                    realistic_execution=request.realistic_execution,
                    skip_optimization=request.skip_optimization
                )
                
                app_state.scheduler = scheduler
                app_state.initial_value = Decimal(str(request.initial_balance))
                
                logger.info(f"Starting paper trading: skip_optimization={request.skip_optimization}")
                
                # Run with dashboard updates
                await run_bot_with_updates(scheduler, _current_session_uuid)
            elif request.mode == "live":
                # Live trading mode
                await run_live_trading(exchange, request.risk_level, _current_session_uuid)
            else:
                raise HTTPException(status_code=400, detail=f"Invalid mode: {request.mode}")
                
        except asyncio.CancelledError:
            logger.info("Bot task cancelled")
        except Exception as e:
            logger.error(f"Bot error: {e}")
            app_state.add_log("ERROR", f"Bot error: {e}", "bot")
        finally:
            app_state.bot_running = False
            app_state.bot_mode = "stopped"
            
            # Update session status
            if _current_session_id:
                await finalize_session(_current_session_id)
    
    # Start the bot task
    app_state.bot_task = asyncio.create_task(run_bot())
    app_state.start_bot(exchange, request.mode, session_id)
    
    return {
        "success": True,
        "message": f"Bot started in {request.mode} mode for {request.exchange}",
        "exchange": request.exchange,
        "mode": request.mode,
        "session_id": session_id
    }


async def run_bot_with_updates(scheduler: PaperTradingScheduler, session_uuid: Optional[uuid.UUID] = None):
    """Run the bot while updating dashboard state."""
    from decimal import Decimal
    
    logger.info(f"Starting PAPER TRADING (REALISTIC) for {scheduler.exchange_type.value}")
    
    try:
        while scheduler.is_running:
            # Run iteration
            await scheduler.run_iteration()
            
            # Update dashboard state
            if scheduler.paper_account:
                # Update balances
                app_state.current_balances = dict(scheduler.paper_account.balances)
                app_state.current_prices = dict(scheduler.paper_account.current_prices)
                app_state.target_weights = dict(scheduler.target_weights) if scheduler.target_weights else {}
                app_state.total_fees = scheduler.paper_account.total_fees
                
                # Add PnL snapshot every 60 iterations
                if scheduler.iteration_count % 60 == 0:
                    pnl, pnl_pct, total_value = scheduler.paper_account.calculate_pnl()
                    app_state.add_pnl_snapshot(total_value, pnl, pnl_pct)
                
                # Record trades
                if scheduler.paper_account.total_trades > app_state.total_trades:
                    # New trades added
                    new_trades = scheduler.paper_account.trades[app_state.total_trades:]
                    for trade in new_trades:
                        app_state.add_trade(trade.to_dict())
                        
                        # Save to database
                        if session_uuid:
                            save_trade_to_db(trade, session_uuid)
                    
                    app_state.total_trades = scheduler.paper_account.total_trades
            
            await asyncio.sleep(1)
            
    except asyncio.CancelledError:
        logger.info("Bot stopped by user")
    finally:
        scheduler.is_running = False


def parse_slippage(value) -> Optional[float]:
    """Parse slippage value from string or number."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        # Remove % sign and parse
        cleaned = value.replace('%', '').strip()
        if cleaned:
            try:
                return float(cleaned)
            except ValueError:
                return None
    return None


def save_trade_to_db(trade, session_uuid: uuid.UUID, exchange_account_id: Optional[uuid.UUID] = None):
    """Save a trade to the database."""
    try:
        with db_manager.session_scope() as session:
            trade_repo = TradeRepository(session)
            session_repo = TradingSessionRepository(session)
            
            # Get trade data
            trade_dict = trade.to_dict() if hasattr(trade, 'to_dict') else trade
            
            # Parse value and fee
            value_str = trade_dict.get('value', 0)
            if isinstance(value_str, str):
                value_str = value_str.replace(',', '')
            fee_str = trade_dict.get('fee', 0)
            if isinstance(fee_str, str):
                fee_str = fee_str.replace(',', '')
            
            trade_repo.create(
                symbol=trade_dict.get('symbol', ''),
                side=trade_dict.get('side', 'BUY'),
                quantity=float(trade_dict.get('quantity', 0)),
                price=float(trade_dict.get('price', 0)),
                value=float(value_str) if value_str else None,
                fee=float(fee_str) if fee_str else 0,
                slippage_percent=parse_slippage(trade_dict.get('slippage_percent')),
                status='SIMULATED' if not exchange_account_id else 'FILLED',
                trading_session_id=session_uuid,
                exchange_account_id=exchange_account_id
            )
            
            # Increment session trade count
            from src.infrastructure.database.models import TradingSession
            trading_session = session.query(TradingSession).filter_by(id=session_uuid).first()
            if trading_session:
                session_repo.increment_trades(trading_session.session_id, float(fee_str) if fee_str else 0)
    except Exception as e:
        logger.error(f"Failed to save trade to DB: {e}")


async def run_live_trading(exchange: ExchangeType, risk_level: int, session_uuid: uuid.UUID):
    """Run live trading with real exchange accounts."""
    from decimal import Decimal
    from src.exchanges.binance import BinanceExchange
    from src.exchanges.upbit import UpbitExchange
    from src.infrastructure.database.repositories import ExchangeAccountRepository
    from src.infrastructure.encryption.kms import get_encryptor
    
    logger.info(f"Starting LIVE TRADING for {exchange.value}")
    
    # Get active accounts for this exchange
    with db_manager.session_scope() as session:
        account_repo = ExchangeAccountRepository(session)
        accounts = account_repo.get_active_accounts(exchange.value)
        
        if not accounts:
            raise ValueError(f"No active accounts found for {exchange.value}")
        
        logger.info(f"Found {len(accounts)} active account(s) for {exchange.value}")
    
    # Get target weights
    with db_manager.session_scope() as session:
        weight_repo = PortfolioWeightRepository(session)
        weights = weight_repo.get_latest(exchange.value, risk_level)
        
        if not weights:
            raise ValueError(f"No portfolio weights found for {exchange.value} at risk level {risk_level}")
        
        target_weights = weights.weights
        logger.info(f"Loaded target weights: {len(target_weights)} assets")
    
    # Initialize exchange client
    encryptor = get_encryptor()
    
    if exchange == ExchangeType.BINANCE:
        # Use first account's credentials
        with db_manager.session_scope() as session:
            account_repo = ExchangeAccountRepository(session)
            account = account_repo.get_active_accounts(exchange.value)[0]
            
            access_key = encryptor.decrypt(account.access_key_encrypted)
            secret_key = encryptor.decrypt(account.secret_key_encrypted)
            account_id = account.id
        
        exchange_client = BinanceExchange(access_key, secret_key)
    elif exchange == ExchangeType.UPBIT:
        with db_manager.session_scope() as session:
            account_repo = ExchangeAccountRepository(session)
            account = account_repo.get_active_accounts(exchange.value)[0]
            
            access_key = encryptor.decrypt(account.access_key_encrypted)
            secret_key = encryptor.decrypt(account.secret_key_encrypted)
            account_id = account.id
        
        exchange_client = UpbitExchange(access_key, secret_key)
    else:
        raise ValueError(f"Exchange {exchange.value} not supported for live trading yet")
    
    app_state.initial_value = None
    iteration = 0
    
    try:
        while app_state.bot_running:
            iteration += 1
            
            # Get current balances
            balances = await exchange_client.get_balances()
            prices = await exchange_client.get_all_prices()
            
            # Calculate portfolio value
            total_value = Decimal("0")
            current_weights = {}
            
            for asset, balance in balances.items():
                if balance > 0:
                    if asset in ["USDT", "KRW", "USD"]:
                        value = balance
                    else:
                        # Find price
                        price_key = f"{asset}USDT" if exchange == ExchangeType.BINANCE else f"KRW-{asset}"
                        price = prices.get(price_key, Decimal("0"))
                        value = balance * price
                    
                    total_value += value
                    current_weights[asset] = value
            
            # Convert to percentages
            if total_value > 0:
                current_weights = {k: float(v / total_value) for k, v in current_weights.items()}
            
            # Set initial value
            if app_state.initial_value is None:
                app_state.initial_value = total_value
                logger.info(f"Initial portfolio value: {total_value}")
            
            # Update dashboard state
            app_state.current_balances = {k: float(v) for k, v in balances.items()}
            app_state.current_prices = {k: float(v) for k, v in prices.items()}
            app_state.target_weights = target_weights
            
            # Calculate PnL
            pnl = total_value - app_state.initial_value
            pnl_pct = float(pnl / app_state.initial_value * 100) if app_state.initial_value > 0 else 0
            
            # Add PnL snapshot every 60 iterations
            if iteration % 60 == 0:
                app_state.add_pnl_snapshot(float(total_value), float(pnl), pnl_pct)
            
            # Check if rebalancing is needed
            rebalance_threshold = 0.05  # 5%
            needs_rebalance = False
            
            for asset, target_weight in target_weights.items():
                current_weight = current_weights.get(asset, 0)
                if abs(current_weight - target_weight) > rebalance_threshold:
                    needs_rebalance = True
                    break
            
            if needs_rebalance and iteration > 1:
                logger.info("Rebalancing needed, executing trades...")
                
                # Calculate orders
                orders = calculate_rebalance_orders(
                    current_weights, target_weights, total_value, prices, exchange
                )
                
                # Execute orders
                for order in orders:
                    try:
                        result = await exchange_client.place_order(
                            symbol=order['symbol'],
                            side=order['side'],
                            quantity=order['quantity'],
                            order_type='MARKET'
                        )
                        
                        logger.info(f"Order executed: {order['side']} {order['quantity']} {order['symbol']}")
                        
                        # Save trade to DB
                        with db_manager.session_scope() as session:
                            trade_repo = TradeRepository(session)
                            trade_repo.create(
                                symbol=order['symbol'],
                                side=order['side'],
                                quantity=order['quantity'],
                                price=float(prices.get(order['symbol'], 0)),
                                value=order.get('value'),
                                fee=order.get('fee', 0),
                                status='FILLED',
                                trading_session_id=session_uuid,
                                exchange_account_id=account_id,
                                exchange_order_id=result.get('orderId')
                            )
                        
                        app_state.add_trade({
                            'symbol': order['symbol'],
                            'side': order['side'],
                            'quantity': order['quantity'],
                            'price': float(prices.get(order['symbol'], 0)),
                            'timestamp': datetime.utcnow().isoformat()
                        })
                        
                    except Exception as e:
                        logger.error(f"Order failed: {e}")
            
            await asyncio.sleep(10)  # Check every 10 seconds for live trading
            
    except asyncio.CancelledError:
        logger.info("Live trading stopped by user")
    except Exception as e:
        logger.error(f"Live trading error: {e}")
        raise


def calculate_rebalance_orders(
    current_weights: dict, 
    target_weights: dict, 
    total_value: "Decimal",
    prices: dict,
    exchange: ExchangeType
) -> list:
    """Calculate orders needed to rebalance portfolio."""
    from decimal import Decimal
    
    orders = []
    
    for asset, target_weight in target_weights.items():
        current_weight = current_weights.get(asset, 0)
        weight_diff = target_weight - current_weight
        
        if abs(weight_diff) < 0.01:  # Less than 1% difference
            continue
        
        # Calculate value to trade
        trade_value = float(total_value) * weight_diff
        
        # Get price
        if exchange == ExchangeType.BINANCE:
            symbol = f"{asset}USDT"
        else:
            symbol = f"KRW-{asset}"
        
        price = prices.get(symbol, 0)
        if price == 0:
            continue
        
        quantity = abs(trade_value) / float(price)
        
        # Round to appropriate precision
        if exchange == ExchangeType.BINANCE:
            quantity = round(quantity, 6)
        else:
            quantity = round(quantity, 8)
        
        if quantity > 0:
            orders.append({
                'symbol': symbol,
                'side': 'BUY' if weight_diff > 0 else 'SELL',
                'quantity': quantity,
                'value': abs(trade_value)
            })
    
    return orders


async def finalize_session(session_id: str):
    """Finalize a trading session with final statistics."""
    try:
        # Get final PnL from app_state
        pnl = 0
        pnl_pct = 0
        total_trades = app_state.total_trades
        total_fees = float(app_state.total_fees) if app_state.total_fees else 0
        
        if app_state.pnl_history:
            last_snapshot = app_state.pnl_history[-1]
            pnl = last_snapshot.pnl if hasattr(last_snapshot, 'pnl') else last_snapshot.get('pnl', 0)
            pnl_pct = last_snapshot.pnl_percent if hasattr(last_snapshot, 'pnl_percent') else last_snapshot.get('pnl_percent', 0)
        
        with db_manager.session_scope() as session:
            session_repo = TradingSessionRepository(session)
            session_repo.update_status(
                session_id=session_id,
                status='stopped',
                final_pnl=pnl,
                final_pnl_percent=pnl_pct,
                total_trades=total_trades,
                total_fees=total_fees
            )
        
        logger.info(f"Session {session_id} finalized: PnL={pnl:.2f} ({pnl_pct:.2f}%), Trades={total_trades}")
        
    except Exception as e:
        logger.error(f"Failed to finalize session: {e}")


@router.post("/stop")
async def stop_bot():
    """Stop the trading bot."""
    global _current_session_id
    
    if not app_state.bot_running:
        raise HTTPException(status_code=400, detail="Bot is not running")
    
    # Stop the scheduler
    if app_state.scheduler:
        app_state.scheduler.is_running = False
    
    session_id = _current_session_id
    
    # Finalize session before stopping
    if session_id:
        await finalize_session(session_id)
    
    app_state.stop_bot()
    _current_session_id = None
    
    return {
        "success": True,
        "message": "Bot stopped successfully",
        "session_id": session_id
    }


@router.get("/session")
async def get_current_session():
    """Get current trading session info."""
    global _current_session_id
    
    if not _current_session_id:
        return {"session_id": None, "running": False}
    
    with db_manager.session_scope() as session:
        session_repo = TradingSessionRepository(session)
        trading_session = session_repo.get_by_session_id(_current_session_id)
        
        if trading_session:
            return {
                "session_id": _current_session_id,
                "running": app_state.bot_running,
                "session": trading_session.to_dict()
            }
    
    return {"session_id": _current_session_id, "running": app_state.bot_running}


@router.post("/optimize")
async def optimize_portfolio(request: OptimizeRequest):
    """
    Run portfolio optimization.
    This generates optimal weights for all risk levels.
    """
    global _optimization_task
    
    # Check if optimization is already running
    if _optimization_task and not _optimization_task.done():
        raise HTTPException(status_code=400, detail="Portfolio optimization is already running")
    
    # Map exchange string to enum
    exchange_map = {
        "upbit": ExchangeType.UPBIT,
        "binance": ExchangeType.BINANCE,
        "korbit": ExchangeType.KORBIT,
        "bithumb": ExchangeType.BITHUMB
    }
    
    exchange = exchange_map.get(request.exchange.lower())
    if not exchange:
        raise HTTPException(status_code=400, detail=f"Invalid exchange: {request.exchange}")
    
    # Check if recent weights exist (unless force=True)
    if not request.force:
        from src.infrastructure.database.connection import db_manager
        from src.infrastructure.database.repositories import PortfolioWeightRepository
        from datetime import datetime, timedelta
        
        with db_manager.session_scope() as session:
            repo = PortfolioWeightRepository(session)
            latest = repo.get_latest(exchange.value, 2)  # Check risk level 2 as reference
            
            if latest and latest.created_at:
                age = datetime.utcnow() - latest.created_at
                if age < timedelta(hours=1):
                    return {
                        "success": True,
                        "message": "Recent portfolio weights exist (less than 1 hour old)",
                        "exchange": request.exchange,
                        "status": "skipped",
                        "last_optimized": latest.created_at.isoformat()
                    }
    
    # Setup dashboard log handler for root logger only (propagates to all child loggers)
    dashboard_handler = DashboardLogHandler()
    dashboard_handler.setLevel(logging.INFO)
    
    root_logger = logging.getLogger()
    has_dashboard_handler = any(isinstance(h, DashboardLogHandler) for h in root_logger.handlers)
    if not has_dashboard_handler:
        root_logger.addHandler(dashboard_handler)
    
    # Ensure child loggers propagate to root
    for logger_name in ['src.workers.portfolio_worker', 'src.core.portfolio']:
        child_logger = logging.getLogger(logger_name)
        child_logger.propagate = True
    
    global _optimization_cancelled
    _optimization_cancelled = False
    reset_cancellation()  # Reset worker cancellation flag
    
    app_state.add_log("INFO", f"Starting portfolio optimization for {exchange.value}", "optimizer")
    
    # Run optimization in background thread to avoid blocking event loop
    async def run_optimization():
        global _optimization_cancelled
        import concurrent.futures
        loop = asyncio.get_event_loop()
        
        def sync_optimize():
            """Synchronous optimization wrapper."""
            global _optimization_cancelled
            import time
            start = time.time()
            
            try:
                # Check cancellation before starting
                if _optimization_cancelled:
                    return {"success": False, "cancelled": True}
                
                # Create worker
                worker = PortfolioWorker(exchange)
                worker.is_running = True
                
                # This runs synchronously
                import asyncio as aio
                
                # Run the async parts in a new event loop
                def run_async():
                    new_loop = aio.new_event_loop()
                    aio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(worker.run_optimization())
                    finally:
                        new_loop.close()
                
                weights = run_async()
                
                # Check cancellation before saving
                if _optimization_cancelled:
                    return {"success": False, "cancelled": True}
                
                # Save weights
                def save_async():
                    new_loop = aio.new_event_loop()
                    aio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(worker.save_weights(weights))
                    finally:
                        new_loop.close()
                
                save_async()
                
                elapsed = time.time() - start
                return {"success": True, "elapsed": elapsed, "weights_count": len(weights.get(2, {}))}
            except asyncio.CancelledError:
                return {"success": False, "cancelled": True}
            except Exception as e:
                # Check if it's a cancellation wrapped in another exception
                if "cancelled" in str(e).lower():
                    return {"success": False, "cancelled": True}
                return {"success": False, "error": str(e)}
        
        try:
            app_state.add_log("INFO", "Fetching market data and optimizing... (this may take a while)", "optimizer")
            
            # Run in thread pool executor
            with concurrent.futures.ThreadPoolExecutor() as executor:
                result = await loop.run_in_executor(executor, sync_optimize)
            
            if result.get("cancelled"):
                app_state.add_log("WARNING", "Portfolio optimization was cancelled (results discarded)", "optimizer")
            elif result["success"]:
                app_state.add_log("INFO", f"Portfolio optimization completed in {result['elapsed']:.1f}s ({result['weights_count']} assets)", "optimizer")
            else:
                app_state.add_log("ERROR", f"Optimization failed: {result.get('error', 'Unknown error')}", "optimizer")
                
        except asyncio.CancelledError:
            app_state.add_log("WARNING", "Portfolio optimization cancelled", "optimizer")
            raise
        except Exception as e:
            logger.error(f"Optimization error: {e}")
            app_state.add_log("ERROR", f"Optimization error: {e}", "optimizer")
    
    _optimization_task = asyncio.create_task(run_optimization())
    
    return {
        "success": True,
        "message": f"Portfolio optimization started for {request.exchange}",
        "exchange": request.exchange,
        "status": "started"
    }


@router.get("/optimize/status")
async def get_optimization_status():
    """Get portfolio optimization status."""
    global _optimization_task
    
    if _optimization_task is None:
        return {"status": "idle", "running": False}
    
    if _optimization_task.done():
        # Check if it completed with error
        try:
            _optimization_task.result()
            return {"status": "completed", "running": False}
        except asyncio.CancelledError:
            return {"status": "cancelled", "running": False}
        except Exception as e:
            return {"status": "error", "running": False, "error": str(e)}
    
    return {"status": "running", "running": True}


@router.post("/optimize/cancel")
async def cancel_optimization():
    """Cancel running portfolio optimization."""
    global _optimization_task, _optimization_cancelled
    
    if _optimization_task is None or _optimization_task.done():
        return {"success": False, "message": "No optimization running"}
    
    # Set cancellation flags (both local and worker module)
    _optimization_cancelled = True
    request_cancellation()  # This will be checked in the data fetching loop
    
    # Also cancel the asyncio task
    _optimization_task.cancel()
    
    app_state.add_log("WARNING", "Portfolio optimization cancelled by user", "optimizer")
    
    return {"success": True, "message": "Optimization cancelled"}


@router.get("/weights")
async def get_portfolio_weights(exchange: str, risk_level: int = 2):
    """Get current portfolio weights."""
    exchange_map = {
        "upbit": ExchangeType.UPBIT,
        "binance": ExchangeType.BINANCE,
        "korbit": ExchangeType.KORBIT,
        "bithumb": ExchangeType.BITHUMB
    }
    
    ex = exchange_map.get(exchange.lower())
    if not ex:
        raise HTTPException(status_code=400, detail=f"Invalid exchange: {exchange}")
    
    from src.infrastructure.database.connection import db_manager
    from src.infrastructure.database.repositories import PortfolioWeightRepository
    
    with db_manager.session_scope() as session:
        repo = PortfolioWeightRepository(session)
        weights = repo.get_latest(ex.value, risk_level)
        
        if not weights:
            return {
                "exists": False,
                "exchange": exchange,
                "risk_level": risk_level,
                "weights": None
            }
        
        return {
            "exists": True,
            "exchange": exchange,
            "risk_level": risk_level,
            "weights": weights.weights,
            "asset_count": len(weights.weights),
            "created_at": weights.created_at.isoformat() if weights.created_at else None
        }
