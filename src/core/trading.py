"""
Trading engine for executing portfolio rebalancing trades.
"""
import logging
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from src.core.models import (
    ExchangeType, OrderSide, OrderType, Order, OrderBook,
    AccountBalance, Portfolio, PortfolioPosition, UserTradingContext
)
from src.exchanges.base import BaseExchange
from src.config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class TradeDecision:
    """A decision to execute a trade."""
    symbol: str
    side: OrderSide
    quantity: Decimal
    price: Decimal
    reason: str


class TradingEngine:
    """
    Trading engine for executing portfolio rebalancing.
    
    Handles order placement, cancellation, and price optimization
    based on order book analysis and reference prices.
    """
    
    def __init__(
        self,
        exchange: BaseExchange,
        th_trd_rate: float = 0.0001,
        fee: float = 0.0005
    ):
        """
        Initialize trading engine.
        
        Args:
            exchange: Exchange adapter instance
            th_trd_rate: Minimum trade rate threshold
            fee: Trading fee rate
        """
        self.exchange = exchange
        self.th_trd_rate = Decimal(str(th_trd_rate))
        self.fee = Decimal(str(fee))
    
    def calculate_spread_profit(
        self,
        order_book: OrderBook,
        ref_price: Optional[Decimal] = None,
        target_diff: Decimal = Decimal("0")
    ) -> Decimal:
        """
        Calculate potential spread profit.
        
        Args:
            order_book: Current order book
            ref_price: Reference price from Binance
            target_diff: Target weight difference (positive = buy, negative = sell)
            
        Returns:
            Spread profit as a decimal
        """
        if not order_book.best_bid or not order_book.best_ask:
            return Decimal("-1")
        
        bid = order_book.best_bid.price
        ask = order_book.best_ask.price
        
        if bid <= 0:
            return Decimal("-1")
        
        spread = ask / bid
        
        # Adjust spread based on reference price
        if ref_price is not None:
            if target_diff > 0:  # Buying
                spread = max(spread, ref_price / bid)
            elif target_diff < 0:  # Selling
                spread = max(spread, ask / ref_price)
        
        # Calculate profit after fees
        profit = spread * (1 - self.fee) / (1 + self.fee) - 1
        return profit
    
    def determine_order_price(
        self,
        order_book: OrderBook,
        side: OrderSide,
        ref_price: Optional[Decimal] = None,
        spread_profit: Decimal = Decimal("0"),
        quote_currency: str = "KRW"
    ) -> Tuple[Decimal, str]:
        """
        Determine optimal order price based on market conditions.
        
        Args:
            order_book: Current order book
            side: Order side (BUY/SELL)
            ref_price: Reference price
            spread_profit: Current spread profit
            quote_currency: Quote currency for tick size calculation
            
        Returns:
            Tuple of (price, strategy_name)
        """
        if not order_book.best_bid or not order_book.best_ask:
            raise ValueError("Order book is empty")
        
        bid = order_book.best_bid.price
        ask = order_book.best_ask.price
        mid = order_book.mid_price
        
        if side in [OrderSide.BUY, OrderSide.BID]:
            # Buying strategy
            if spread_profit >= 0 and (ref_price is None or bid <= ref_price):
                # High compete: match best bid
                price = bid
                strategy = "high_compete"
            elif len(order_book.bids) > 1:
                # Low compete: slightly above second best
                second_bid = order_book.bids[1].price
                tick = self.exchange.get_tick_size(quote_currency, second_bid)
                price = second_bid + tick
                if ref_price is not None:
                    price = min(price, ref_price)
                strategy = "low_compete"
            else:
                # Narrow spread: use mid price with fee adjustment
                price = mid / (1 + self.fee)
                if ref_price is not None:
                    price = min(price, ref_price)
                strategy = "narrow_spread"
            
            # Round down for buys
            price = self.exchange.round_price(quote_currency, price, round_down=True)
            
        else:
            # Selling strategy
            if spread_profit >= 0 and (ref_price is None or ask >= ref_price):
                # High compete: match best ask
                price = ask
                strategy = "high_compete"
            elif len(order_book.asks) > 1:
                # Low compete: slightly below second best
                second_ask = order_book.asks[1].price
                tick = self.exchange.get_tick_size(quote_currency, second_ask)
                price = second_ask - tick
                if ref_price is not None:
                    price = max(price, ref_price)
                strategy = "low_compete"
            else:
                # Narrow spread: use mid price with fee adjustment
                price = mid / (1 - self.fee)
                if ref_price is not None:
                    price = max(price, ref_price)
                strategy = "narrow_spread"
            
            # Round up for sells
            price = self.exchange.round_price(quote_currency, price, round_down=False)
        
        return price, strategy
    
    def calculate_order_quantity(
        self,
        side: OrderSide,
        target_diff: Decimal,
        total_value: Decimal,
        price: Decimal,
        available_balance: Decimal,
        min_trade: Decimal,
        lot_size: Decimal = Decimal("0.00000001")
    ) -> Decimal:
        """
        Calculate order quantity.
        
        Args:
            side: Order side
            target_diff: Target weight difference
            total_value: Total portfolio value
            price: Order price
            available_balance: Available balance
            min_trade: Minimum trade amount
            lot_size: Lot size for rounding
            
        Returns:
            Order quantity
        """
        if price <= 0:
            return Decimal("0")
        
        # Calculate target quantity based on weight difference
        target_value = abs(target_diff) * total_value
        target_qty = target_value / price
        
        if side in [OrderSide.BUY, OrderSide.BID]:
            # For buys, limit by available quote currency
            max_qty = (available_balance / (1 + self.fee)) / price
            qty = min(target_qty, max_qty)
        else:
            # For sells, limit by available base currency
            qty = min(target_qty, available_balance)
        
        # Round down to lot size
        qty = (qty // lot_size) * lot_size
        
        # Check minimum trade value
        if qty * price < min_trade:
            return Decimal("0")
        
        return qty
    
    def should_cancel_order(
        self,
        order: Order,
        target_diff: Decimal,
        ref_price: Optional[Decimal] = None
    ) -> Tuple[bool, str]:
        """
        Determine if an existing order should be cancelled.
        
        Args:
            order: Existing order
            target_diff: Current target weight difference
            ref_price: Reference price
            
        Returns:
            Tuple of (should_cancel, reason)
        """
        # Cancel opposite direction orders
        if target_diff > 0 and order.side in [OrderSide.SELL, OrderSide.ASK]:
            return True, "opposite_direction"
        if target_diff < 0 and order.side in [OrderSide.BUY, OrderSide.BID]:
            return True, "opposite_direction"
        if target_diff == 0:
            return True, "no_rebalance_needed"
        
        # Cancel orders outside reference price
        if ref_price is not None and order.price is not None:
            if order.side in [OrderSide.BUY, OrderSide.BID] and order.price > ref_price:
                return True, "above_ref_price"
            if order.side in [OrderSide.SELL, OrderSide.ASK] and order.price < ref_price:
                return True, "below_ref_price"
        
        return False, ""
    
    def generate_rebalance_trades(
        self,
        context: UserTradingContext,
        order_books: Dict[str, OrderBook],
        ref_prices: Dict[str, Decimal],
        min_trades: Dict[str, Decimal]
    ) -> List[TradeDecision]:
        """
        Generate trade decisions for portfolio rebalancing.
        
        Args:
            context: User trading context
            order_books: Order books for relevant pairs
            ref_prices: Reference prices from Binance
            min_trades: Minimum trade amounts per pair
            
        Returns:
            List of trade decisions
        """
        decisions = []
        
        if not context.portfolio or not context.target_weights:
            return decisions
        
        # Calculate current weights and differences
        for currency, target_weight in context.target_weights.items():
            current_weight = context.portfolio.get_weight(currency)
            target_diff = Decimal(str(target_weight)) - current_weight
            
            # Skip if difference is too small
            if abs(target_diff) < self.th_trd_rate:
                continue
            
            # Find the trading pair
            symbol = self._find_trading_symbol(currency, context.exchange)
            if not symbol or symbol not in order_books:
                continue
            
            order_book = order_books[symbol]
            ref_price = ref_prices.get(symbol)
            min_trade = min_trades.get(symbol, Decimal("0"))
            
            # Calculate spread profit
            spread_profit = self.calculate_spread_profit(
                order_book, ref_price, target_diff
            )
            
            # Determine order side
            side = OrderSide.BUY if target_diff > 0 else OrderSide.SELL
            
            # Get quote currency from symbol
            quote_currency = self._get_quote_currency(symbol)
            
            # Determine optimal price
            price, strategy = self.determine_order_price(
                order_book, side, ref_price, spread_profit, quote_currency
            )
            
            # Get available balance
            if side == OrderSide.BUY:
                available = context.current_balance.get_available(quote_currency)
            else:
                available = context.current_balance.get_available(currency)
            
            # Calculate quantity
            quantity = self.calculate_order_quantity(
                side=side,
                target_diff=target_diff,
                total_value=context.portfolio.total_value,
                price=price,
                available_balance=available,
                min_trade=min_trade
            )
            
            if quantity > 0:
                decisions.append(TradeDecision(
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    price=price,
                    reason=f"rebalance_{strategy}"
                ))
        
        return decisions
    
    def execute_trades(
        self,
        decisions: List[TradeDecision]
    ) -> List[Tuple[TradeDecision, Optional[Order], Optional[str]]]:
        """
        Execute trade decisions.
        
        Args:
            decisions: List of trade decisions
            
        Returns:
            List of (decision, order, error) tuples
        """
        results = []
        
        for decision in decisions:
            try:
                order = self.exchange.place_order(
                    symbol=decision.symbol,
                    side=decision.side,
                    order_type=OrderType.LIMIT,
                    quantity=decision.quantity,
                    price=decision.price
                )
                results.append((decision, order, None))
                logger.info(
                    f"Placed {decision.side} order for {decision.quantity} "
                    f"{decision.symbol} at {decision.price}"
                )
            except Exception as e:
                logger.error(f"Failed to place order: {e}")
                results.append((decision, None, str(e)))
        
        return results
    
    def cancel_stale_orders(
        self,
        context: UserTradingContext,
        ref_prices: Dict[str, Decimal]
    ) -> List[str]:
        """
        Cancel stale orders that are no longer valid.
        
        Args:
            context: User trading context
            ref_prices: Reference prices
            
        Returns:
            List of cancelled order IDs
        """
        cancelled = []
        
        for order in context.open_orders:
            # Get target diff for this currency
            currency = self._get_base_currency(order.symbol)
            target_weight = context.target_weights.get(currency, 0)
            current_weight = (
                context.portfolio.get_weight(currency)
                if context.portfolio else Decimal("0")
            )
            target_diff = Decimal(str(target_weight)) - current_weight
            
            ref_price = ref_prices.get(order.symbol)
            
            should_cancel, reason = self.should_cancel_order(
                order, target_diff, ref_price
            )
            
            if should_cancel:
                try:
                    self.exchange.cancel_order(order.id, order.symbol)
                    cancelled.append(order.id)
                    logger.info(f"Cancelled order {order.id}: {reason}")
                except Exception as e:
                    logger.error(f"Failed to cancel order {order.id}: {e}")
        
        return cancelled
    
    def _find_trading_symbol(
        self,
        currency: str,
        exchange: ExchangeType
    ) -> Optional[str]:
        """Find the trading symbol for a currency."""
        if exchange == ExchangeType.UPBIT:
            return f"KRW-{currency}"
        elif exchange == ExchangeType.BINANCE:
            return f"{currency}USDT"
        elif exchange == ExchangeType.KORBIT:
            return f"{currency.lower()}_krw"
        elif exchange == ExchangeType.BITHUMB:
            return f"{currency}_KRW"
        return None
    
    def _get_quote_currency(self, symbol: str) -> str:
        """Extract quote currency from symbol."""
        if '-' in symbol:  # Upbit format: KRW-BTC
            return symbol.split('-')[0]
        elif '_' in symbol:  # Korbit/Bithumb format: btc_krw, BTC_KRW
            return symbol.split('_')[1].upper()
        else:  # Binance format: BTCUSDT
            for quote in ['USDT', 'BTC', 'ETH', 'BNB']:
                if symbol.endswith(quote):
                    return quote
        return 'USDT'
    
    def _get_base_currency(self, symbol: str) -> str:
        """Extract base currency from symbol."""
        if '-' in symbol:  # Upbit format: KRW-BTC
            return symbol.split('-')[1]
        elif '_' in symbol:  # Korbit/Bithumb format: btc_krw, BTC_KRW
            return symbol.split('_')[0].upper()
        else:  # Binance format: BTCUSDT
            for quote in ['USDT', 'BTC', 'ETH', 'BNB']:
                if symbol.endswith(quote):
                    return symbol[:-len(quote)]
        return symbol


class RouletteWheelSelector:
    """
    Roulette wheel selection for choosing users based on portfolio value.
    """
    
    @staticmethod
    def select(
        users: List[UserTradingContext],
        fitness_values: Dict[str, Decimal]
    ) -> Optional[UserTradingContext]:
        """
        Select a user using roulette wheel selection.
        
        Args:
            users: List of user contexts
            fitness_values: Dictionary mapping user_id to fitness (portfolio value)
            
        Returns:
            Selected user context
        """
        import random
        
        if not users:
            return None
        
        if len(users) == 1:
            return users[0]
        
        # Calculate total fitness
        total_fitness = sum(
            fitness_values.get(str(u.user_id), Decimal("0"))
            for u in users
        )
        
        if total_fitness <= 0:
            return random.choice(users)
        
        # Random pick
        pick = Decimal(str(random.uniform(0, float(total_fitness))))
        current = Decimal("0")
        
        for user in users:
            fitness = fitness_values.get(str(user.user_id), Decimal("0"))
            current += fitness
            if current >= pick:
                return user
        
        return users[-1]
