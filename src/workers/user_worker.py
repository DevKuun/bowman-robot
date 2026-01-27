"""
User worker for processing individual user trades.
"""
import logging
import asyncio
from decimal import Decimal
from typing import Dict, Optional
from uuid import UUID
from datetime import datetime

from src.core.models import (
    ExchangeType, UserTradingContext, AccountBalance, Portfolio,
    PortfolioPosition, ReferencePrices
)
from src.core.trading import TradingEngine
from src.core.portfolio import PortfolioCalculator
from src.exchanges import get_exchange, BaseExchange
from src.infrastructure.database.connection import db_manager
from src.infrastructure.database.repositories import (
    ExchangeAccountRepository, PortfolioWeightRepository, TradeRepository
)
from src.infrastructure.encryption.kms import kms_encryption
from src.infrastructure.messaging.slack import slack_notifier
from src.config.settings import settings

logger = logging.getLogger(__name__)


class UserWorker:
    """
    Worker process for handling trades for a single user.
    
    Each user has their own worker that manages their portfolio
    and executes trades based on target weights.
    """
    
    def __init__(
        self,
        user_id: UUID,
        exchange_type: ExchangeType,
        access_key: str,
        secret_key: str,
        risk_level: int,
        cash_weight: float
    ):
        """
        Initialize user worker.
        
        Args:
            user_id: User ID
            exchange_type: Exchange type
            access_key: Decrypted API access key
            secret_key: Decrypted API secret key
            risk_level: Risk level (0-4)
            cash_weight: Cash weight to hold (0-1)
        """
        self.user_id = user_id
        self.exchange_type = exchange_type
        self.risk_level = risk_level
        self.cash_weight = Decimal(str(cash_weight))
        
        # Initialize exchange adapter
        self.exchange = get_exchange(exchange_type, access_key, secret_key)
        
        # Initialize trading engine
        fee_map = {
            ExchangeType.UPBIT: settings.upbit_fee_krw,
            ExchangeType.BINANCE: 0.001,
            ExchangeType.KORBIT: 0.0005,
            ExchangeType.BITHUMB: settings.bithumb_fee,
        }
        fee = fee_map.get(exchange_type, 0.001)
        self.trading_engine = TradingEngine(
            exchange=self.exchange,
            th_trd_rate=settings.trading_th_trd_rate,
            fee=fee
        )
        
        # State
        self.context: Optional[UserTradingContext] = None
        self.target_weights: Dict[str, float] = {}
        self.last_update = datetime.utcnow()
        self.is_running = True
        self.error_count = 0
        self.max_errors = 10
    
    async def initialize(self):
        """Initialize worker state."""
        try:
            # Get account balance
            balance = self.exchange.get_account_balance()
            
            # Get target weights from database
            with db_manager.session_scope() as session:
                repo = PortfolioWeightRepository(session)
                weight = repo.get_latest(self.exchange_type.value, self.risk_level)
                if weight:
                    self.target_weights = weight.weights
            
            # Create trading context
            self.context = UserTradingContext(
                user_id=self.user_id,
                exchange=self.exchange_type,
                access_key=self.exchange.access_key,
                secret_key=self.exchange.secret_key,
                risk_level=self.risk_level,
                cash_weight=self.cash_weight,
                target_weights={
                    k: Decimal(str(v)) * (1 - self.cash_weight)
                    for k, v in self.target_weights.items()
                },
                current_balance=balance
            )
            
            logger.info(f"Initialized worker for user {self.user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize worker for user {self.user_id}: {e}")
            self.error_count += 1
            return False
    
    async def update_balance(self):
        """Update account balance."""
        try:
            balance = self.exchange.get_account_balance()
            if self.context:
                self.context.current_balance = balance
            return True
        except Exception as e:
            logger.error(f"Failed to update balance for user {self.user_id}: {e}")
            self.error_count += 1
            return False
    
    async def update_portfolio(
        self,
        order_books: Dict,
        ref_prices: Optional[ReferencePrices] = None
    ):
        """
        Update portfolio weights based on current balances.
        
        Args:
            order_books: Current order books
            ref_prices: Reference prices from Binance
        """
        if not self.context or not self.context.current_balance:
            return
        
        try:
            # Determine quote currency
            if self.exchange_type in [ExchangeType.UPBIT, ExchangeType.KORBIT, ExchangeType.BITHUMB]:
                quote_currency = 'KRW'
            elif self.exchange_type == ExchangeType.BINANCE:
                quote_currency = 'USDT'
            else:
                quote_currency = 'KRW'
            
            # Calculate asset values
            prices = {}
            for symbol, ob in order_books.items():
                if ob.mid_price:
                    prices[symbol] = ob.mid_price
            
            balances = {
                k: v.total for k, v in self.context.current_balance.balances.items()
            }
            
            values = PortfolioCalculator.calculate_asset_values(
                balances, prices, quote_currency
            )
            
            weights, total_value = PortfolioCalculator.calculate_weights(values)
            
            # Build portfolio
            positions = {}
            for currency, value in values.items():
                target = self.context.target_weights.get(currency, Decimal("0"))
                positions[currency] = PortfolioPosition(
                    currency=currency,
                    quantity=balances.get(currency, Decimal("0")),
                    value=value,
                    weight=weights.get(currency, Decimal("0")),
                    target_weight=target
                )
            
            self.context.portfolio = Portfolio(
                positions=positions,
                total_value=total_value,
                quote_currency=quote_currency
            )
            
        except Exception as e:
            logger.error(f"Failed to update portfolio for user {self.user_id}: {e}")
    
    async def execute_rebalance(
        self,
        order_books: Dict,
        ref_prices: Optional[ReferencePrices] = None,
        min_trades: Optional[Dict[str, Decimal]] = None
    ) -> int:
        """
        Execute portfolio rebalancing.
        
        Args:
            order_books: Current order books
            ref_prices: Reference prices from Binance
            min_trades: Minimum trade amounts per pair
            
        Returns:
            Number of trades executed
        """
        if not self.context:
            return 0
        
        try:
            # Update open orders
            self.context.open_orders = self.exchange.get_open_orders()
            
            # Cancel stale orders
            ref_price_dict = ref_prices.prices if ref_prices else {}
            cancelled = self.trading_engine.cancel_stale_orders(
                self.context, ref_price_dict
            )
            
            if cancelled:
                logger.info(f"Cancelled {len(cancelled)} stale orders for user {self.user_id}")
            
            # Generate trade decisions
            decisions = self.trading_engine.generate_rebalance_trades(
                context=self.context,
                order_books=order_books,
                ref_prices=ref_price_dict,
                min_trades=min_trades or {}
            )
            
            if not decisions:
                return 0
            
            # Execute trades
            results = self.trading_engine.execute_trades(decisions)
            
            # Record trades in database
            successful = 0
            with db_manager.session_scope() as session:
                trade_repo = TradeRepository(session)
                
                for decision, order, error in results:
                    if order:
                        trade_repo.create(
                            exchange_account_id=self.user_id,
                            symbol=decision.symbol,
                            side=decision.side.value,
                            quantity=float(decision.quantity),
                            price=float(decision.price),
                            status='PENDING',
                            exchange_order_id=order.id
                        )
                        successful += 1
                    else:
                        logger.warning(
                            f"Trade failed for user {self.user_id}: {error}"
                        )
            
            return successful
            
        except Exception as e:
            logger.error(f"Rebalance failed for user {self.user_id}: {e}")
            self.error_count += 1
            return 0
    
    async def run_iteration(
        self,
        order_books: Dict,
        ref_prices: Optional[ReferencePrices] = None,
        min_trades: Optional[Dict[str, Decimal]] = None
    ) -> bool:
        """
        Run a single trading iteration.
        
        Args:
            order_books: Current order books
            ref_prices: Reference prices
            min_trades: Minimum trade amounts
            
        Returns:
            True if successful
        """
        if not self.is_running:
            return False
        
        if self.error_count >= self.max_errors:
            logger.error(f"Too many errors for user {self.user_id}, stopping worker")
            self.is_running = False
            return False
        
        # Update balance periodically
        await self.update_balance()
        
        # Update portfolio
        await self.update_portfolio(order_books, ref_prices)
        
        # Execute rebalance
        trades = await self.execute_rebalance(order_books, ref_prices, min_trades)
        
        if trades > 0:
            logger.info(f"Executed {trades} trades for user {self.user_id}")
        
        self.last_update = datetime.utcnow()
        return True
    
    def stop(self):
        """Stop the worker."""
        self.is_running = False
        logger.info(f"Stopped worker for user {self.user_id}")


class UserWorkerFactory:
    """Factory for creating user workers."""
    
    @staticmethod
    def create_from_account(
        account_id: UUID,
        exchange: str,
        access_key_encrypted: str,
        secret_key_encrypted: str,
        risk_level: int,
        cash_weight: float
    ) -> UserWorker:
        """
        Create a user worker from database account.
        
        Args:
            account_id: Exchange account ID
            exchange: Exchange name
            access_key_encrypted: Encrypted access key
            secret_key_encrypted: Encrypted secret key
            risk_level: Risk level
            cash_weight: Cash weight
            
        Returns:
            Initialized UserWorker
        """
        # Decrypt keys
        access_key = kms_encryption.decrypt(access_key_encrypted)
        secret_key = kms_encryption.decrypt(secret_key_encrypted)
        
        # Map exchange type
        exchange_type = ExchangeType(exchange.upper())
        
        return UserWorker(
            user_id=account_id,
            exchange_type=exchange_type,
            access_key=access_key,
            secret_key=secret_key,
            risk_level=risk_level,
            cash_weight=cash_weight
        )
