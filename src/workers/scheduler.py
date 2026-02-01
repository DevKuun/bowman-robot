"""
Main scheduler for orchestrating all workers.
"""
import logging
import asyncio
import signal
from typing import Dict, List, Optional
from datetime import datetime
from uuid import UUID

from src.core.models import ExchangeType, ReferencePrices
from src.workers.user_worker import UserWorker, UserWorkerFactory
from src.workers.portfolio_worker import PortfolioWorker
from src.exchanges import get_exchange
from src.exchanges.binance import BinanceExchange
from src.infrastructure.database.connection import db_manager
from src.infrastructure.database.repositories import ExchangeAccountRepository
from src.infrastructure.messaging.slack import slack_notifier
from src.config.settings import settings

logger = logging.getLogger(__name__)


class TradingScheduler:
    """
    Main scheduler that orchestrates all trading operations.
    
    Manages:
    - User workers for each active account
    - Portfolio optimization workers
    - Reference price updates from Binance
    - Order book fetching
    """
    
    def __init__(self, exchange_type: ExchangeType):
        """
        Initialize the scheduler.
        
        Args:
            exchange_type: Exchange to trade on
        """
        self.exchange_type = exchange_type
        self.is_running = True
        
        # Workers
        self.user_workers: Dict[UUID, UserWorker] = {}
        self.portfolio_worker = PortfolioWorker(exchange_type)
        
        # Reference prices from Binance
        self.ref_prices: Optional[ReferencePrices] = None
        self.binance = BinanceExchange('', '')  # Public API only
        
        # Timing
        self.last_db_refresh = datetime.min
        self.last_ref_price_update = datetime.min
        
        # Statistics
        self.iteration_count = 0
        self.start_time = datetime.utcnow()
    
    async def load_active_users(self):
        """Load active users from database and create/update workers."""
        with db_manager.session_scope() as session:
            repo = ExchangeAccountRepository(session)
            accounts = repo.get_active_accounts(self.exchange_type.value)
            
            # Track current account IDs
            current_ids = set(self.user_workers.keys())
            new_ids = set()
            
            for account in accounts:
                account_id = account.id
                new_ids.add(account_id)
                
                # Create new worker if needed
                if account_id not in self.user_workers:
                    try:
                        worker = UserWorkerFactory.create_from_account(
                            account_id=account_id,
                            exchange=account.exchange,
                            access_key_encrypted=account.access_key_encrypted,
                            secret_key_encrypted=account.secret_key_encrypted,
                            risk_level=account.risk_level,
                            cash_weight=float(account.cash_weight)
                        )
                        
                        # Initialize worker
                        if await worker.initialize():
                            self.user_workers[account_id] = worker
                            logger.info(f"Created worker for account {account_id}")
                        
                    except Exception as e:
                        logger.error(f"Failed to create worker for account {account_id}: {e}")
            
            # Stop workers for deactivated accounts
            for account_id in current_ids - new_ids:
                worker = self.user_workers.pop(account_id, None)
                if worker:
                    worker.stop()
                    logger.info(f"Removed worker for deactivated account {account_id}")
    
    async def update_reference_prices(self):
        """Update reference prices from Binance."""
        try:
            tickers = self.binance.get_all_tickers()
            self.ref_prices = ReferencePrices(
                prices={k: v.price for k, v in tickers.items()},
                timestamp=datetime.utcnow()
            )
        except Exception as e:
            logger.warning(f"Failed to update reference prices: {e}")
    
    async def get_order_books(self, symbols: List[str]) -> Dict:
        """
        Get order books for symbols.
        
        Args:
            symbols: List of trading pair symbols
            
        Returns:
            Dictionary of symbol to OrderBook
        """
        if not symbols:
            return {}
        
        # Create a public exchange instance
        if self.exchange_type == ExchangeType.UPBIT:
            from src.exchanges.upbit import UpbitExchange
            exchange = UpbitExchange('', '')
        elif self.exchange_type == ExchangeType.BINANCE:
            exchange = self.binance
        elif self.exchange_type == ExchangeType.KORBIT:
            from src.exchanges.korbit import KorbitExchange
            exchange = KorbitExchange('', '')
        elif self.exchange_type == ExchangeType.BITHUMB:
            from src.exchanges.bithumb import BithumbExchange
            exchange = BithumbExchange('', '')
        else:
            from src.exchanges.korbit import KorbitExchange
            exchange = KorbitExchange('', '')
        
        try:
            return exchange.get_order_books(symbols, levels=2)
        except Exception as e:
            logger.error(f"Failed to get order books: {e}")
            return {}
    
    async def run_iteration(self):
        """Run a single scheduler iteration."""
        now = datetime.utcnow()
        
        # Refresh users from DB periodically
        if (now - self.last_db_refresh).seconds >= settings.worker_db_refresh_interval:
            await self.load_active_users()
            self.last_db_refresh = now
        
        # Update reference prices periodically
        if (now - self.last_ref_price_update).seconds >= settings.worker_binance_refresh_interval:
            await self.update_reference_prices()
            self.last_ref_price_update = now
        
        # Run portfolio optimization (weekly)
        await self.portfolio_worker.run_iteration()
        
        if not self.user_workers:
            return
        
        # Collect all symbols needed
        all_symbols = set()
        for worker in self.user_workers.values():
            if worker.target_weights:
                for currency in worker.target_weights.keys():
                    if self.exchange_type == ExchangeType.UPBIT:
                        # Add symbols for all enabled markets
                        for market in settings.upbit_markets:
                            all_symbols.add(f"{market}-{currency}")
                    elif self.exchange_type == ExchangeType.BINANCE:
                        all_symbols.add(f"{currency}USDT")
                    elif self.exchange_type == ExchangeType.BITHUMB:
                        all_symbols.add(f"{currency}_KRW")
                    else:
                        all_symbols.add(f"{currency.lower()}_krw")
        
        # Get order books
        order_books = await self.get_order_books(list(all_symbols))
        
        # Calculate minimum trade amounts
        min_trades = {}
        if self.exchange_type == ExchangeType.UPBIT:
            # Upbit: Multiple markets (KRW, BTC, USDT)
            for symbol in all_symbols:
                if symbol.startswith('KRW-'):
                    min_trades[symbol] = settings.upbit_min_trade_krw
                elif symbol.startswith('BTC-'):
                    min_trades[symbol] = settings.upbit_min_trade_btc
                elif symbol.startswith('USDT-'):
                    min_trades[symbol] = settings.upbit_min_trade_usdt
                else:
                    min_trades[symbol] = settings.upbit_min_trade_krw
        elif self.exchange_type == ExchangeType.BITHUMB:
            # Bithumb: KRW market only
            for symbol in all_symbols:
                min_trades[symbol] = settings.bithumb_min_trade_krw
        elif self.exchange_type == ExchangeType.BINANCE:
            # Binance: Use settings for USDT minimum
            for symbol in all_symbols:
                if symbol.endswith('USDT'):
                    min_trades[symbol] = settings.binance_min_trade_usdt
                elif symbol.endswith('BTC'):
                    min_trades[symbol] = 0.0001  # 0.0001 BTC minimum
                elif symbol.endswith('ETH'):
                    min_trades[symbol] = 0.001  # 0.001 ETH minimum
                else:
                    min_trades[symbol] = settings.binance_min_trade_usdt  # Default to USDT setting
        elif self.exchange_type == ExchangeType.KORBIT:
            # Korbit: KRW market only - use settings
            for symbol in all_symbols:
                min_trades[symbol] = settings.korbit_min_trade_krw
        
        # Run all user workers concurrently
        tasks = []
        for worker in self.user_workers.values():
            if worker.is_running:
                tasks.append(
                    worker.run_iteration(
                        order_books=order_books,
                        ref_prices=self.ref_prices,
                        min_trades=min_trades
                    )
                )
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        self.iteration_count += 1
    
    async def run(self):
        """Main run loop."""
        logger.info(f"Starting scheduler for {self.exchange_type.value}")
        
        # Send startup notification
        slack_notifier.send_info(
            f"Trading bot started for {self.exchange_type.value}"
        )
        
        try:
            while self.is_running:
                iteration_start = datetime.utcnow()
                
                await self.run_iteration()
                
                # Calculate time taken
                iteration_time = (datetime.utcnow() - iteration_start).total_seconds()
                
                # Log statistics periodically
                if self.iteration_count % 100 == 0:
                    logger.info(
                        f"Iteration {self.iteration_count}: "
                        f"{len(self.user_workers)} active users, "
                        f"took {iteration_time:.2f}s"
                    )
                
                # Small delay between iterations
                await asyncio.sleep(0.1)
                
        except asyncio.CancelledError:
            logger.info("Scheduler cancelled")
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
            slack_notifier.send_error(
                f"Scheduler error for {self.exchange_type.value}",
                context=str(e)
            )
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Gracefully shutdown the scheduler."""
        logger.info("Shutting down scheduler...")
        
        self.is_running = False
        self.portfolio_worker.stop()
        
        # Stop all user workers
        for worker in self.user_workers.values():
            worker.stop()
        
        self.user_workers.clear()
        
        # Send shutdown notification
        runtime = datetime.utcnow() - self.start_time
        slack_notifier.send_info(
            f"Trading bot stopped for {self.exchange_type.value}\n"
            f"Runtime: {runtime}\n"
            f"Iterations: {self.iteration_count}"
        )
        
        logger.info("Scheduler shutdown complete")
    
    def stop(self):
        """Signal the scheduler to stop."""
        self.is_running = False


class PaperTradingScheduler:
    """
    Scheduler for paper trading simulation.
    Uses a single virtual account instead of loading from database.
    
    Supports realistic execution mode with:
    - Order book depth consideration
    - Ask/Bid spread simulation
    - Slippage calculation
    """
    
    def __init__(
        self,
        exchange_type: ExchangeType,
        initial_balance: float = 1000000,
        risk_level: int = 2,
        realistic_execution: bool = True,
        with_dashboard: bool = False,
        skip_optimization: bool = False
    ):
        from decimal import Decimal
        from src.simulation.paper_trading import PaperTradingAccount, PaperTradingExchange
        
        self.exchange_type = exchange_type
        self.is_running = True
        self.realistic_execution = realistic_execution
        self.with_dashboard = with_dashboard
        self.skip_optimization = skip_optimization
        
        # Import exchanges
        from src.exchanges.upbit import UpbitExchange
        from src.exchanges.bithumb import BithumbExchange
        from src.exchanges.korbit import KorbitExchange
        
        # Create real exchange for market data and set fee rate
        if exchange_type == ExchangeType.UPBIT:
            self.real_exchange = UpbitExchange('', '')
            quote = 'KRW'
            fee_rate = Decimal(str(settings.upbit_fee_krw))  # 0.05%
        elif exchange_type == ExchangeType.BINANCE:
            self.real_exchange = BinanceExchange('', '')
            quote = 'USDT'
            fee_rate = Decimal('0.001')  # 0.1% (default Binance fee)
        elif exchange_type == ExchangeType.BITHUMB:
            self.real_exchange = BithumbExchange('', '')
            quote = 'KRW'
            fee_rate = Decimal(str(settings.bithumb_fee))  # 0.04% (event)
        else:
            self.real_exchange = KorbitExchange('', '')
            quote = 'KRW'
            fee_rate = Decimal('0.002')  # 0.2% (Korbit default)
        
        # Create paper trading account with exchange-specific fee rate
        self.paper_account = PaperTradingAccount(
            exchange_type=exchange_type,
            initial_balance={quote: Decimal(str(initial_balance))},
            fee_rate=fee_rate,
            realistic_execution=realistic_execution
        )
        
        # Set initial value explicitly (before any trades happen)
        self.paper_account.initial_value = Decimal(str(initial_balance))
        
        # Create paper trading exchange
        self.paper_exchange = PaperTradingExchange(
            real_exchange=self.real_exchange,
            paper_account=self.paper_account
        )
        
        # Portfolio worker
        self.portfolio_worker = PortfolioWorker(exchange_type)
        
        # Reference prices
        self.ref_prices: Optional[ReferencePrices] = None
        self.binance = BinanceExchange('', '')
        
        # Timing
        self.risk_level = risk_level
        self.target_weights: Dict[str, float] = {}
        self.last_ref_price_update = datetime.min
        self.last_snapshot = datetime.min
        
        # Cross rates for multi-market price comparison
        self._cross_rates: Dict[str, Decimal] = {}
        
        # Statistics
        self.iteration_count = 0
        self.start_time = datetime.utcnow()
        
        # Initialize dashboard state if enabled
        if self.with_dashboard:
            self._init_dashboard_state(initial_balance)
    
    def _init_dashboard_state(self, initial_balance: float):
        """Initialize dashboard app state."""
        from decimal import Decimal
        try:
            from src.api.state import app_state, DashboardLogHandler
            
            # Setup log handler for dashboard
            handler = DashboardLogHandler()
            handler.setLevel(logging.INFO)
            logging.getLogger().addHandler(handler)
            
            # Initialize state
            app_state.bot_running = True
            app_state.bot_mode = "paper"
            app_state.bot_exchange = self.exchange_type
            app_state.bot_start_time = self.start_time
            app_state.scheduler = self
            app_state.reset_stats()
            # Set initial_value AFTER reset_stats (which clears it)
            app_state.initial_value = Decimal(str(initial_balance))
            
            logger.info("Dashboard state initialized")
        except ImportError:
            logger.warning("Dashboard module not available")
            self.with_dashboard = False
    
    def _update_dashboard_state(self, prices: dict):
        """Update dashboard state with current data."""
        if not self.with_dashboard:
            return
        
        try:
            from src.api.state import app_state
            from decimal import Decimal
            
            # Update paper_account prices first
            self.paper_account.update_prices(prices)
            
            # Debug: Log first update
            if self.iteration_count == 1:
                logger.info(f"[DEBUG] Dashboard update - Exchange: {self.exchange_type.value}")
                logger.info(f"[DEBUG] Balances count: {len(self.paper_account.balances)}")
                logger.info(f"[DEBUG] Prices count: {len(prices)}")
                # Log sample prices
                sample_prices = list(prices.items())[:5]
                for sym, price in sample_prices:
                    logger.info(f"[DEBUG] Price sample: {sym} = {price}")
                # Log sample balances
                sample_balances = list(self.paper_account.balances.items())[:5]
                for cur, amt in sample_balances:
                    logger.info(f"[DEBUG] Balance sample: {cur} = {amt}")
            
            # Update balances and prices
            app_state.current_balances = dict(self.paper_account.balances)
            app_state.current_prices = dict(prices)
            app_state.target_weights = dict(self.target_weights) if self.target_weights else {}
            app_state.total_fees = self.paper_account.total_fees
            
            # Add PnL snapshot every 60 iterations
            if self.iteration_count % 60 == 0 and self.iteration_count > 0:
                pnl, pnl_pct, total_value = self.paper_account.calculate_pnl()
                app_state.add_pnl_snapshot(total_value, pnl, pnl_pct)
                logger.info(f"[DEBUG] PnL snapshot added: value={total_value}, pnl={pnl}")
            
            # Sync trades
            if self.paper_account.total_trades > app_state.total_trades:
                new_trades = self.paper_account.trades[app_state.total_trades:]
                for trade in new_trades:
                    app_state.add_trade(trade.to_dict())
                app_state.total_trades = self.paper_account.total_trades
                
        except ImportError as e:
            logger.error(f"[DEBUG] ImportError in dashboard update: {e}")
        except Exception as e:
            logger.error(f"[DEBUG] Failed to update dashboard state: {e}")
            import traceback
            traceback.print_exc()
    
    async def update_reference_prices(self):
        """Update reference prices from Binance."""
        try:
            tickers = self.binance.get_all_tickers()
            self.ref_prices = ReferencePrices(
                prices={k: v.price for k, v in tickers.items()},
                timestamp=datetime.utcnow()
            )
        except Exception as e:
            logger.warning(f"Failed to update reference prices: {e}")
    
    async def update_target_weights(self):
        """Update target weights from portfolio optimization."""
        from src.infrastructure.database.repositories import PortfolioWeightRepository
        
        with db_manager.session_scope() as session:
            repo = PortfolioWeightRepository(session)
            weight = repo.get_latest(self.exchange_type.value, self.risk_level)
            
            if weight:
                self.target_weights = weight.weights
                logger.info(f"Loaded target weights: {len(self.target_weights)} assets")
    
    async def run_iteration(self):
        """Run a single paper trading iteration."""
        from decimal import Decimal
        from src.core.models import OrderSide, OrderType
        
        now = datetime.utcnow()
        
        # Update reference prices periodically
        if (now - self.last_ref_price_update).seconds >= settings.worker_binance_refresh_interval:
            await self.update_reference_prices()
            self.last_ref_price_update = now
        
        # Run portfolio optimization (unless skipped or already have weights)
        if not self.skip_optimization and not self.target_weights:
            await self.portfolio_worker.run_iteration()
        
        # Update target weights from database
        if not self.target_weights:
            await self.update_target_weights()
        
        if not self.target_weights:
            logger.info("No target weights available. Run portfolio optimization first.")
            return
        
        # Get current prices
        try:
            tickers = self.paper_exchange.get_all_tickers()
            prices = {k: v.price for k, v in tickers.items()}
            
            # Calculate cross rates for multi-market price comparison (Upbit)
            if self.exchange_type == ExchangeType.UPBIT:
                self._cross_rates = self.real_exchange._calculate_cross_rates(prices)
            else:
                self._cross_rates = {}
        except Exception as e:
            logger.error(f"Failed to get prices: {e}")
            return
        
        # Get current balance
        balance = self.paper_exchange.get_account_balance()
        
        # Calculate portfolio value and current weights
        quote_currency = 'KRW' if self.exchange_type != ExchangeType.BINANCE else 'USDT'
        total_value = Decimal('0')
        current_values = {}
        
        # Collect symbols for order book fetching
        symbols_to_trade = []
        
        for currency, bal in balance.balances.items():
            if currency == quote_currency:
                # Primary quote currency (KRW)
                current_values[currency] = bal.available
                total_value += bal.available
            elif currency in ['USDT', 'BTC'] and self.exchange_type == ExchangeType.UPBIT:
                # Secondary quote currencies - convert to KRW using cross rates
                if currency in self._cross_rates and self._cross_rates[currency] > 0:
                    value_in_krw = bal.available * self._cross_rates[currency]
                    current_values[currency] = value_in_krw
                    total_value += value_in_krw
            else:
                # Coins - find price and convert to KRW
                symbol = None
                price = None
                price_in_krw = None
                
                if self.exchange_type == ExchangeType.UPBIT:
                    # Try markets in priority order, convert to KRW
                    for market in ['KRW', 'USDT', 'BTC']:
                        if market in settings.upbit_markets:
                            test_symbol = f"{market}-{currency}"
                            if test_symbol in prices:
                                symbol = test_symbol
                                price = prices[test_symbol]
                                # Convert to KRW for portfolio valuation
                                if market == 'KRW':
                                    price_in_krw = price
                                elif market in self._cross_rates and self._cross_rates[market] > 0:
                                    price_in_krw = price * self._cross_rates[market]
                                if price_in_krw:
                                    break
                elif self.exchange_type == ExchangeType.BITHUMB:
                    symbol = f"{currency}_KRW"
                    price = prices.get(symbol)
                    price_in_krw = price
                else:
                    symbol = f"{currency}USDT"
                    price = prices.get(symbol)
                    price_in_krw = price  # USDT is quote for Binance
                
                if price_in_krw:
                    value = bal.available * price_in_krw
                    current_values[currency] = value
                    total_value += value
        
        if total_value <= 0:
            return
        
        # Calculate current weights
        current_weights = {k: v / total_value for k, v in current_values.items()}
        
        # Calculate differences and collect symbols that need trading
        th_trd_rate = Decimal(str(settings.trading_th_trd_rate))  # From settings (default 0.01%)
        trades_to_execute = []
        
        # Pre-fetch order books for accurate market selection (ask/bid + spread)
        market_selection_order_books = {}
        if self.exchange_type == ExchangeType.UPBIT and self.realistic_execution:
            try:
                # Collect all possible symbols for currencies that need rebalancing
                symbols_for_ob = set()
                # Add cross-market symbols for spread calculation
                symbols_for_ob.add('KRW-USDT')
                symbols_for_ob.add('KRW-BTC')
                
                # Quote currencies (cannot be base currency in their own market)
                quote_currencies = {'KRW', 'BTC', 'USDT'}
                
                for currency, target_weight in self.target_weights.items():
                    current_weight = current_weights.get(currency, Decimal('0'))
                    if abs(Decimal(str(target_weight)) - current_weight) >= th_trd_rate:
                        for market in settings.upbit_markets:
                            # Skip invalid markets:
                            # 1. Same currency (BTC-BTC, USDT-USDT)
                            # 2. Quote currency as base in non-KRW market (BTC-USDT, USDT-BTC)
                            if market == currency:
                                continue
                            if currency in quote_currencies and market != 'KRW':
                                continue
                            symbols_for_ob.add(f"{market}-{currency}")
                
                # Fetch order books with more levels for accurate slippage estimation
                if symbols_for_ob:
                    market_selection_order_books = self.paper_exchange.get_order_books(
                        list(symbols_for_ob), levels=15
                    )
            except Exception as e:
                logger.debug(f"Could not fetch order books for market selection: {e}")
        
        for currency, target_weight in self.target_weights.items():
            current_weight = current_weights.get(currency, Decimal('0'))
            target_w = Decimal(str(target_weight))
            diff = target_w - current_weight
            
            # Skip small differences
            if abs(diff) < th_trd_rate:
                continue
            
            # Calculate estimated trade quantity first (for liquidity/slippage check)
            trade_value = abs(diff) * total_value
            
            # Get approximate price in KRW for quantity estimation
            krw_symbol = f"KRW-{currency}"
            approx_price = prices.get(krw_symbol)
            if not approx_price:
                # Fall back to BTC market price converted to KRW
                btc_symbol = f"BTC-{currency}"
                if btc_symbol in prices and 'BTC' in self._cross_rates:
                    approx_price = prices[btc_symbol] * self._cross_rates['BTC']
                else:
                    usdt_symbol = f"USDT-{currency}"
                    if usdt_symbol in prices and 'USDT' in self._cross_rates:
                        approx_price = prices[usdt_symbol] * self._cross_rates['USDT']
            
            estimated_quantity = trade_value / approx_price if approx_price and approx_price > 0 else Decimal('0')
            
            # Find symbol and price - find best market by effective price for Upbit
            symbol = None
            price = None
            selected_market = None
            
            if self.exchange_type == ExchangeType.UPBIT:
                # Use price comparison to find best market (including fees, spread, and slippage)
                # Pass available balances for dynamic fee calculation
                available_balances = {
                    curr: bal.available 
                    for curr, bal in balance.balances.items() 
                    if bal.available > 0
                }
                
                side_str = 'buy' if diff > 0 else 'sell'
                best_result = self.real_exchange.find_best_market_by_price(
                    base_currency=currency,
                    side=side_str,
                    prices=prices,
                    cross_rates=self._cross_rates,
                    available_balances=available_balances,
                    order_books=market_selection_order_books,
                    trade_quantity=estimated_quantity,
                    max_slippage=Decimal('0.03')  # 3% max acceptable slippage
                )
                
                if best_result:
                    symbol, effective_price, selected_market = best_result
                    price = prices.get(symbol)
                    
                    # IMPORTANT: Convert price to KRW for quantity calculation
                    # if using BTC or USDT market
                    price_in_krw = price
                    if selected_market == 'BTC' and 'BTC' in self._cross_rates:
                        price_in_krw = price * self._cross_rates['BTC']
                    elif selected_market == 'USDT' and 'USDT' in self._cross_rates:
                        price_in_krw = price * self._cross_rates['USDT']
                    
                    # Log market selection if not using default KRW
                    if selected_market != 'KRW' and self.iteration_count % 60 == 1:
                        comparison = self.real_exchange.compare_market_prices(currency, prices, self._cross_rates)
                        if len(comparison) > 1:
                            logger.info(f"[Market Selection] {currency} {side_str}: chose {selected_market} market")
                            for mkt, info in comparison.items():
                                eff_key = 'buy_effective' if side_str == 'buy' else 'sell_effective'
                                logger.info(f"  {mkt}: {info[eff_key]:.0f} KRW (fee {info['fee_rate']*100:.2f}%)")
            elif self.exchange_type == ExchangeType.BITHUMB:
                symbol = f"{currency}_KRW"
                price = prices.get(symbol)
                price_in_krw = price
                selected_market = 'KRW'
            else:
                symbol = f"{currency}USDT"
                price = prices.get(symbol)
                price_in_krw = price  # USDT is quote currency for Binance
                selected_market = 'USDT'
            
            if not symbol or not price or price <= 0:
                continue
            
            # trade_value already calculated above for estimated_quantity
            # Use KRW-converted price for final quantity calculation
            quantity = trade_value / price_in_krw
            
            # Minimum trade check using settings
            # Convert all min_trade values to KRW for consistent comparison
            # (trade_value is always in KRW)
            if self.exchange_type == ExchangeType.UPBIT and symbol:
                if symbol.startswith('KRW-'):
                    min_trade_krw = Decimal(str(settings.upbit_min_trade_krw))  # Already KRW
                elif symbol.startswith('BTC-'):
                    # Convert BTC minimum to KRW
                    min_trade_btc = Decimal(str(settings.upbit_min_trade_btc))
                    btc_rate = self._cross_rates.get('BTC', Decimal('150000000'))
                    min_trade_krw = min_trade_btc * btc_rate
                elif symbol.startswith('USDT-'):
                    # Convert USDT minimum to KRW
                    min_trade_usdt = Decimal(str(settings.upbit_min_trade_usdt))
                    usdt_rate = self._cross_rates.get('USDT', Decimal('1400'))
                    min_trade_krw = min_trade_usdt * usdt_rate
                else:
                    min_trade_krw = Decimal(str(settings.upbit_min_trade_krw))
            elif quote_currency == 'KRW':
                if self.exchange_type == ExchangeType.BITHUMB:
                    min_trade_krw = Decimal(str(settings.bithumb_min_trade_krw))
                elif self.exchange_type == ExchangeType.KORBIT:
                    min_trade_krw = Decimal(str(settings.korbit_min_trade_krw))
                else:
                    min_trade_krw = Decimal('5000')  # Default for KRW
            else:
                # USDT (Binance) - keep as is since trade_value is in USDT
                min_trade_krw = Decimal(str(settings.binance_min_trade_usdt))
            
            if trade_value < min_trade_krw:
                continue
            
            # Determine side and check available balance
            two_step_trade = None  # For 2-step trades: KRW→USDT→Coin
            
            if diff > 0:
                side = OrderSide.BUY
                
                # For Upbit: Check the selected market's quote currency balance
                # If not available, consider 2-step trade or fallback to KRW market
                if self.exchange_type == ExchangeType.UPBIT and selected_market:
                    required_quote = selected_market  # BTC, USDT, or KRW
                    available_quote = balance.balances.get(required_quote)
                    
                    # If no balance in selected market and it's not KRW
                    if (not available_quote or available_quote.available <= 0) and required_quote != 'KRW':
                        # Check if 2-step trade is still better than direct KRW trade
                        krw_symbol = f"KRW-{currency}"
                        krw_quote_symbol = f"KRW-{required_quote}"  # KRW-USDT or KRW-BTC
                        
                        if krw_symbol in prices and krw_quote_symbol in prices:
                            # Compare: 2-step (KRW→USDT→Coin) vs 1-step (KRW→Coin)
                            # effective_price already includes 2-step fees+spread
                            krw_direct_price = prices[krw_symbol]
                            krw_fee = Decimal(str(self.real_exchange.get_fee_rate('KRW')))
                            krw_effective = krw_direct_price * (1 + krw_fee)
                            
                            # If 2-step is still better (effective_price < krw_effective)
                            if effective_price < krw_effective:
                                # Execute 2-step trade
                                krw_balance = balance.balances.get('KRW')
                                if krw_balance and krw_balance.available > 0:
                                    two_step_trade = {
                                        'step1_symbol': krw_quote_symbol,  # KRW-USDT
                                        'step1_quote': required_quote,      # USDT
                                        'step2_symbol': symbol,             # USDT-ETH
                                    }
                                    available_quote = krw_balance
                                    selected_market = 'KRW'  # We're using KRW to buy
                                    logger.info(f"[2-Step Trade] {currency}: KRW→{required_quote}→{currency} "
                                               f"(saves {((krw_effective - effective_price) / krw_effective * 100):.2f}%)")
                            else:
                                # KRW direct is better, use fallback
                                logger.debug(f"[Fallback] {currency}: KRW direct is better than 2-step")
                                symbol = krw_symbol
                                price = prices[symbol]
                                price_in_krw = price
                                selected_market = 'KRW'
                                available_quote = balance.balances.get('KRW')
                                min_trade_krw = Decimal(str(settings.upbit_min_trade_krw))
                        else:
                            # No KRW market available, skip
                            continue
                    
                    if not available_quote or available_quote.available <= 0:
                        continue
                    
                    # Calculate max buy value in KRW terms
                    if selected_market == 'KRW' or two_step_trade:
                        max_buy_value = available_quote.available * Decimal('0.95')
                    else:
                        # Convert BTC/USDT balance to KRW for comparison
                        cross_rate = self._cross_rates.get(selected_market, Decimal('1'))
                        max_buy_value = available_quote.available * cross_rate * Decimal('0.95')
                else:
                    # Non-Upbit exchanges: use default quote_currency
                    available_quote = balance.balances.get(quote_currency)
                    if not available_quote:
                        continue
                    max_buy_value = available_quote.available * Decimal('0.95')
                
                if trade_value > max_buy_value:
                    trade_value = max_buy_value
                    quantity = trade_value / price_in_krw
                if trade_value < min_trade_krw:
                    continue
            else:
                side = OrderSide.SELL
                # Check coin balance for sell
                available_coin = balance.balances.get(currency)
                if available_coin:
                    if quantity > available_coin.available:
                        quantity = available_coin.available * Decimal('0.95')
                        trade_value = quantity * price_in_krw
                    if trade_value < min_trade_krw:
                        continue
                else:
                    continue
            
            trades_to_execute.append({
                'symbol': symbol,
                'currency': currency,
                'side': side,
                'quantity': quantity,
                'price': price,
                'min_trade_krw': min_trade_krw,
                'original_trade_value': trade_value,  # Store original value for slippage check
                'two_step_trade': two_step_trade  # None or {step1_symbol, step1_quote, step2_symbol}
            })
            symbols_to_trade.append(symbol)
            # Also add KRW market for fallback
            if not symbol.startswith('KRW-'):
                krw_fallback = f"KRW-{currency}"
                if krw_fallback not in symbols_to_trade:
                    symbols_to_trade.append(krw_fallback)
            if two_step_trade:
                symbols_to_trade.append(two_step_trade['step1_symbol'])
        
        # Sort trades: SELL first, then BUY
        # This ensures we have funds from sales before making purchases
        trades_to_execute.sort(key=lambda t: (0 if t['side'] == OrderSide.SELL else 1))
        
        # Log rebalancing summary
        if trades_to_execute:
            trade_summary = ", ".join([
                f"{t['currency']}({'매수' if t['side'] == OrderSide.BUY else '매도'} {t['original_trade_value']:.0f}원)"
                for t in trades_to_execute
            ])
            logger.info(f"Rebalancing needed: {len(trades_to_execute)} trades - {trade_summary}")
        
        # Fetch order books for realistic execution (including KRW fallbacks)
        order_books = {}
        if self.realistic_execution and symbols_to_trade:
            try:
                # Fetch order books with 15 levels for accurate slippage calculation
                order_books = self.paper_exchange.get_order_books(symbols_to_trade, levels=15)
            except Exception as e:
                logger.warning(f"Failed to get order books for realistic execution: {e}")
        
        # Execute trades
        for trade in trades_to_execute:
            symbol = trade['symbol']
            side = trade['side']
            quantity = trade['quantity']
            min_trade_krw = trade['min_trade_krw']
            two_step = trade.get('two_step_trade')
            
            # Handle 2-step trade: KRW → USDT/BTC → Coin
            if two_step and side == OrderSide.BUY:
                step1_symbol = two_step['step1_symbol']  # e.g., KRW-USDT
                step1_quote = two_step['step1_quote']    # e.g., USDT
                step2_symbol = two_step['step2_symbol']  # e.g., USDT-ETH
                
                # PRE-CHECK: Verify both steps have acceptable slippage
                max_2step_slippage = Decimal('0.02')  # 2% per step for 2-step trades
                skip_2step = False
                
                if self.realistic_execution:
                    # Check step 1 (KRW → USDT/BTC)
                    step2_price = prices.get(step2_symbol, Decimal('0'))
                    if step2_price > 0:
                        step1_quantity = quantity * step2_price * Decimal('1.01')
                        
                        if step1_symbol in order_books:
                            step1_ob = order_books[step1_symbol]
                            step1_slippage = step1_ob.estimate_slippage('buy', step1_quantity)
                            if step1_slippage and step1_slippage > max_2step_slippage:
                                logger.info(f"[2-Step] Step 1 slippage {step1_slippage*100:.2f}% > 2% - fallback to KRW direct")
                                skip_2step = True
                        
                        # Check step 2 (USDT/BTC → Coin)
                        if not skip_2step and step2_symbol in order_books:
                            step2_ob = order_books[step2_symbol]
                            step2_slippage = step2_ob.estimate_slippage('buy', quantity)
                            if step2_slippage and step2_slippage > max_2step_slippage:
                                logger.info(f"[2-Step] Step 2 slippage {step2_slippage*100:.2f}% > 2% - fallback to KRW direct")
                                skip_2step = True
                
                if skip_2step:
                    # Fallback to KRW market
                    krw_symbol = f"KRW-{trade['currency']}"
                    if krw_symbol in prices:
                        symbol = krw_symbol
                        trade['symbol'] = krw_symbol
                        two_step = None  # Clear 2-step flag
                        logger.info(f"[2-Step] Fallback to {krw_symbol}")
                    else:
                        logger.warning(f"[2-Step] No KRW fallback available for {trade['currency']} - skipping")
                        continue
                
                # Execute 2-step if not skipped
                if two_step:
                    step2_price = prices.get(step2_symbol, Decimal('0'))
                    if step2_price > 0:
                        step1_quantity = quantity * step2_price * Decimal('1.01')  # 1% buffer for fees
                        
                        logger.info(f"[2-Step] Step 1: Buying {step1_quantity:.4f} {step1_quote}")
                        
                        if self.realistic_execution and step1_symbol in order_books:
                            step1_order = self.paper_exchange.place_order_realistic(
                                symbol=step1_symbol,
                                side=OrderSide.BUY,
                                quantity=step1_quantity,
                                order_book=order_books[step1_symbol]
                            )
                        else:
                            step1_price = prices.get(step1_symbol, Decimal('0'))
                            step1_order = self.paper_exchange.place_order(
                                symbol=step1_symbol,
                                side=OrderSide.BUY,
                                order_type=OrderType.LIMIT,
                                quantity=step1_quantity,
                                price=step1_price
                            )
                        
                        if not step1_order or step1_order.filled_quantity <= 0:
                            logger.warning(f"[2-Step] Step 1 failed for {trade['currency']} - fallback to KRW")
                            krw_symbol = f"KRW-{trade['currency']}"
                            if krw_symbol in prices:
                                symbol = krw_symbol
                                trade['symbol'] = krw_symbol
                            else:
                                continue
                        else:
                            logger.info(f"[2-Step] Step 1 completed: {step1_order.filled_quantity:.4f} {step1_quote}")
                            
                            # Step 2: Buy Coin with USDT/BTC
                            symbol = step2_symbol
                            logger.info(f"[2-Step] Step 2: Buying {quantity:.8f} {trade['currency']}")
            
            # For BTC/USDT markets, order book is REQUIRED
            # Skip if no order book available for non-KRW markets
            order = None
            
            if self.realistic_execution:
                if symbol not in order_books:
                    if not symbol.startswith('KRW-'):
                        logger.warning(f"[No OrderBook] {symbol}: BTC/USDT market requires order book - skipping")
                        continue
                    # KRW market without order book - use simple execution
                    order = self.paper_exchange.place_order(
                        symbol=symbol,
                        side=side,
                        order_type=OrderType.LIMIT,
                        quantity=quantity,
                        price=trade['price']
                    )
                else:
                    ob = order_books[symbol]
                    side_str = 'buy' if side == OrderSide.BUY else 'sell'
                    
                    # PRE-EXECUTION LIQUIDITY/SLIPPAGE CHECK
                    max_exec_slippage = Decimal('0.03')  # 3% max
                    skip_trade = False
                    
                    # Check order book validity first
                    if side_str == 'buy' and (not ob.asks or not ob.best_ask or ob.best_ask.price <= 0):
                        logger.warning(f"[Invalid Market] {symbol}: No valid ask prices - skipping")
                        skip_trade = True
                    elif side_str == 'sell' and (not ob.bids or not ob.best_bid or ob.best_bid.price <= 0):
                        logger.warning(f"[Invalid Market] {symbol}: No valid bid prices - skipping")
                        skip_trade = True
                    
                    # Check liquidity
                    if not skip_trade:
                        depth = ob.get_depth(side_str)
                        if depth < quantity * Decimal('0.3'):
                            logger.warning(f"[Liquidity] {symbol}: Insufficient depth {depth:.6f} for {quantity:.6f} - skipping")
                            skip_trade = True
                    
                    # Check slippage
                    if not skip_trade:
                        estimated_slippage = ob.estimate_slippage(side_str, quantity)
                        if estimated_slippage and estimated_slippage > max_exec_slippage:
                            # Try KRW market instead if available
                            krw_symbol = f"KRW-{trade['currency']}"
                            if not symbol.startswith('KRW-') and krw_symbol in order_books:
                                krw_ob = order_books[krw_symbol]
                                krw_slippage = krw_ob.estimate_slippage(side_str, quantity)
                                if krw_slippage is None or krw_slippage <= max_exec_slippage:
                                    logger.info(f"[Slippage] {symbol}: {estimated_slippage*100:.2f}% > 3% - fallback to {krw_symbol}")
                                    symbol = krw_symbol
                                    ob = krw_ob
                                else:
                                    logger.warning(f"[Slippage] {symbol}: {estimated_slippage*100:.2f}% too high, KRW also high - skipping")
                                    skip_trade = True
                            else:
                                logger.warning(f"[Slippage] {symbol}: {estimated_slippage*100:.2f}% > 3% - skipping")
                                skip_trade = True
                    
                    if skip_trade:
                        continue
                    
                    # Use realistic execution with order book
                    order = self.paper_exchange.place_order_realistic(
                        symbol=symbol,
                        side=side,
                        quantity=quantity,
                        order_book=ob
                    )
            else:
                # Fallback to simple execution
                order = self.paper_exchange.place_order(
                    symbol=symbol,
                    side=side,
                    order_type=OrderType.LIMIT,
                    quantity=quantity,
                    price=trade['price']
                )
            
            # Post-execution minimum trade check
            if order and order.filled_quantity > 0 and order.price:
                # Convert filled_value to KRW for comparison
                filled_value = order.filled_quantity * order.price
                if symbol.startswith('BTC-') and 'BTC' in self._cross_rates:
                    filled_value_krw = filled_value * self._cross_rates['BTC']
                elif symbol.startswith('USDT-') and 'USDT' in self._cross_rates:
                    filled_value_krw = filled_value * self._cross_rates['USDT']
                else:
                    filled_value_krw = filled_value
                
                original_value = trade['original_trade_value']
                
                if self.paper_account.trades:
                    last_trade = self.paper_account.trades[-1]
                    # Store original value in the trade
                    last_trade.original_value = original_value
                    
                    if filled_value_krw < min_trade_krw:
                        # Mark the last trade as below minimum
                        last_trade.below_minimum = True
                        
                        # Check if it's actually due to slippage:
                        # 1. Original value was >= min_trade
                        # 2. Actual slippage occurred (slippage_percent > 0)
                        actual_slippage = last_trade.slippage_percent > 0
                        was_above_min = original_value >= min_trade_krw
                        
                        if was_above_min and actual_slippage:
                            last_trade.slippage_reduced = True
                            logger.warning(
                                f"Trade below minimum (slippage {last_trade.slippage_percent:.2f}%): {symbol} {side.value} "
                                f"original={original_value:.0f} -> filled={filled_value_krw:.0f} < min={min_trade_krw:.0f}"
                            )
                        else:
                            logger.warning(
                                f"Trade below minimum: {symbol} {side.value} "
                                f"filled={filled_value_krw:.0f} < min={min_trade_krw:.0f}"
                            )
        
        # Auto-convert USDT/BTC to KRW after trades (if enabled)
        # BUT: Skip if BTC/USDT is a target asset in the portfolio
        if self.exchange_type == ExchangeType.UPBIT and settings.upbit_auto_convert_to_krw:
            updated_balance = self.paper_exchange.get_account_balance()
            
            for quote_currency in ['USDT', 'BTC']:
                # Skip if this currency is a target asset in the portfolio
                if quote_currency in self.target_weights:
                    target_weight = Decimal(str(self.target_weights[quote_currency]))
                    if target_weight > Decimal('0.001'):  # Has meaningful weight
                        # Calculate how much to keep based on target weight
                        target_value = total_value * target_weight
                        if quote_currency in self._cross_rates:
                            target_quantity = target_value / self._cross_rates[quote_currency]
                            quote_bal = updated_balance.balances.get(quote_currency)
                            if quote_bal:
                                # Only convert EXCESS beyond target
                                excess = quote_bal.available - target_quantity
                                if excess > Decimal('0.0001'):
                                    convert_quantity = excess
                                    convert_symbol = f"KRW-{quote_currency}"
                                    value_in_krw = convert_quantity * self._cross_rates[quote_currency]
                                    if value_in_krw >= Decimal('5000'):
                                        logger.info(f"[Auto-Convert] Selling excess {convert_quantity:.4f} {quote_currency} to KRW (keeping {target_quantity:.4f})")
                                        if self.realistic_execution and convert_symbol in order_books:
                                            self.paper_exchange.place_order_realistic(
                                                symbol=convert_symbol,
                                                side=OrderSide.SELL,
                                                quantity=convert_quantity,
                                                order_book=order_books[convert_symbol]
                                            )
                                        else:
                                            convert_price = prices.get(convert_symbol, Decimal('0'))
                                            if convert_price > 0:
                                                self.paper_exchange.place_order(
                                                    symbol=convert_symbol,
                                                    side=OrderSide.SELL,
                                                    order_type=OrderType.LIMIT,
                                                    quantity=convert_quantity,
                                                    price=convert_price
                                                )
                        continue  # Skip full conversion for target assets
                
                quote_bal = updated_balance.balances.get(quote_currency)
                if quote_bal and quote_bal.available > Decimal('0.0001'):
                    convert_symbol = f"KRW-{quote_currency}"
                    convert_quantity = quote_bal.available
                    
                    # Check minimum trade value
                    if quote_currency in self._cross_rates:
                        value_in_krw = convert_quantity * self._cross_rates[quote_currency]
                        if value_in_krw >= Decimal('5000'):  # Min KRW trade
                            logger.info(f"[Auto-Convert] Selling {convert_quantity:.4f} {quote_currency} to KRW")
                            
                            if self.realistic_execution and convert_symbol in order_books:
                                self.paper_exchange.place_order_realistic(
                                    symbol=convert_symbol,
                                    side=OrderSide.SELL,
                                    quantity=convert_quantity,
                                    order_book=order_books[convert_symbol]
                                )
                            else:
                                convert_price = prices.get(convert_symbol, Decimal('0'))
                                if convert_price > 0:
                                    self.paper_exchange.place_order(
                                        symbol=convert_symbol,
                                        side=OrderSide.SELL,
                                        order_type=OrderType.LIMIT,
                                        quantity=convert_quantity,
                                        price=convert_price
                                    )
        
        # Take snapshot periodically
        if (now - self.last_snapshot).seconds >= 60:
            self.paper_account.take_snapshot(prices)
            self.last_snapshot = now
        
        # Update dashboard state
        self._update_dashboard_state(prices)
        
        self.iteration_count += 1
    
    async def run(self):
        """Main paper trading loop."""
        mode_str = "REALISTIC" if self.realistic_execution else "SIMPLE"
        logger.info(f"Starting PAPER TRADING ({mode_str}) for {self.exchange_type.value}")
        logger.info(f"Initial balance: {self.paper_account.balances}")
        
        print("\n" + "=" * 60)
        print(f"PAPER TRADING MODE ({mode_str})")
        print("=" * 60)
        print(f"Exchange: {self.exchange_type.value}")
        print(f"Initial: {self.paper_account.balances}")
        print(f"Risk Level: {self.risk_level}")
        if self.realistic_execution:
            print("Realistic execution: Ask/Bid spread, slippage, order book depth")
        print("Press Ctrl+C to stop and see results")
        print("=" * 60 + "\n")
        
        try:
            while self.is_running:
                await self.run_iteration()
                
                # Log summary periodically
                if self.iteration_count % 60 == 0:
                    pnl, pnl_pct, _ = self.paper_account.calculate_pnl()
                    logger.info(
                        f"Iteration {self.iteration_count}: "
                        f"PnL={pnl:.0f} ({pnl_pct:.2f}%), "
                        f"Trades={self.paper_account.total_trades}"
                    )
                
                await asyncio.sleep(1)  # 1 second between iterations
                
        except asyncio.CancelledError:
            logger.info("Paper trading cancelled")
        except Exception as e:
            logger.error(f"Paper trading error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Shutdown and show results."""
        self.is_running = False
        self.portfolio_worker.stop()
        
        # Final snapshot
        try:
            tickers = self.paper_exchange.get_all_tickers()
            prices = {k: v.price for k, v in tickers.items()}
            self.paper_account.take_snapshot(prices)
        except Exception:
            pass
        
        # Update dashboard state on shutdown
        if self.with_dashboard:
            try:
                from src.api.state import app_state
                app_state.bot_running = False
                app_state.bot_mode = "stopped"
            except ImportError:
                pass
        
        # Print summary
        self.paper_account.print_summary()
        
        # Save to file
        try:
            filename = self.paper_account.save_to_file()
            print(f"Results saved to: {filename}")
        except Exception as e:
            logger.error(f"Failed to save results: {e}")
    
    def stop(self):
        """Signal to stop."""
        self.is_running = False


async def run_scheduler(
    exchange_type: ExchangeType,
    paper_trading: bool = False,
    initial_balance: float = 1000000,
    realistic_execution: bool = True,
    with_dashboard: bool = False
):
    """
    Run the trading scheduler.
    
    Args:
        exchange_type: Exchange to trade on
        paper_trading: Whether to run in paper trading mode
        initial_balance: Initial balance for paper trading
        realistic_execution: Enable realistic order execution with slippage
        with_dashboard: Whether to sync state with dashboard
    """
    if paper_trading:
        scheduler = PaperTradingScheduler(
            exchange_type=exchange_type,
            initial_balance=initial_balance,
            realistic_execution=realistic_execution,
            with_dashboard=with_dashboard
        )
    else:
        scheduler = TradingScheduler(exchange_type)
    
    # Setup signal handlers
    loop = asyncio.get_event_loop()
    
    def signal_handler():
        scheduler.stop()
    
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)
    
    await scheduler.run()
