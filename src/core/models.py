"""
Domain models for the trading system.
These are pure Python dataclasses, independent of database models.
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional
from uuid import UUID


class ExchangeType(str, Enum):
    """Supported exchange types."""
    UPBIT = "UPBIT"
    BINANCE = "BINANCE"
    KORBIT = "KORBIT"
    BITHUMB = "BITHUMB"


class OrderSide(str, Enum):
    """Order side (buy/sell)."""
    BUY = "BUY"
    SELL = "SELL"
    BID = "bid"  # Upbit style
    ASK = "ask"  # Upbit style


class OrderStatus(str, Enum):
    """Order status."""
    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class OrderType(str, Enum):
    """Order type."""
    LIMIT = "LIMIT"
    MARKET = "MARKET"


@dataclass
class Balance:
    """Account balance for a single asset."""
    currency: str
    available: Decimal  # Free balance
    locked: Decimal  # In orders
    
    @property
    def total(self) -> Decimal:
        """Total balance (available + locked)."""
        return self.available + self.locked


@dataclass
class AccountBalance:
    """Full account balance."""
    balances: Dict[str, Balance] = field(default_factory=dict)
    
    def get(self, currency: str) -> Optional[Balance]:
        """Get balance for a specific currency."""
        return self.balances.get(currency)
    
    def get_available(self, currency: str) -> Decimal:
        """Get available balance for a currency."""
        balance = self.balances.get(currency)
        return balance.available if balance else Decimal("0")
    
    def get_total(self, currency: str) -> Decimal:
        """Get total balance for a currency."""
        balance = self.balances.get(currency)
        return balance.total if balance else Decimal("0")


@dataclass
class OrderBookLevel:
    """Single level in an order book."""
    price: Decimal
    quantity: Decimal


@dataclass
class OrderBook:
    """Order book for a trading pair."""
    symbol: str
    bids: List[OrderBookLevel]  # Sorted by price descending
    asks: List[OrderBookLevel]  # Sorted by price ascending
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def best_bid(self) -> Optional[OrderBookLevel]:
        """Best bid (highest buy price)."""
        return self.bids[0] if self.bids else None
    
    @property
    def best_ask(self) -> Optional[OrderBookLevel]:
        """Best ask (lowest sell price)."""
        return self.asks[0] if self.asks else None
    
    @property
    def mid_price(self) -> Optional[Decimal]:
        """Mid price between best bid and ask."""
        if self.best_bid and self.best_ask:
            return (self.best_bid.price + self.best_ask.price) / 2
        return None
    
    @property
    def spread(self) -> Optional[Decimal]:
        """Spread between best bid and ask."""
        if self.best_bid and self.best_ask:
            return self.best_ask.price - self.best_bid.price
        return None
    
    def get_depth(self, side: str) -> Decimal:
        """
        Get total depth (volume) available on one side of the book.
        
        Args:
            side: 'buy' (use asks - we'd be taking from sellers) or 
                  'sell' (use bids - we'd be taking from buyers)
        
        Returns:
            Total quantity available at all price levels
        """
        levels = self.asks if side == 'buy' else self.bids
        return sum(level.quantity for level in levels) if levels else Decimal('0')
    
    def get_depth_value(self, side: str) -> Decimal:
        """
        Get total depth value (price * quantity) on one side.
        
        Returns:
            Total value available at all price levels
        """
        levels = self.asks if side == 'buy' else self.bids
        return sum(level.price * level.quantity for level in levels) if levels else Decimal('0')
    
    def estimate_fill_price(self, side: str, quantity: Decimal) -> Optional[tuple[Decimal, Decimal]]:
        """
        Estimate the average fill price for a given quantity.
        
        Args:
            side: 'buy' or 'sell'
            quantity: Amount to trade
        
        Returns:
            Tuple of (average_fill_price, filled_quantity) or None if insufficient liquidity
        """
        # Buy: consume asks (ascending price), Sell: consume bids (descending price)
        levels = self.asks if side == 'buy' else self.bids
        
        if not levels:
            return None
        
        remaining = quantity
        total_cost = Decimal('0')
        filled = Decimal('0')
        
        for level in levels:
            if remaining <= 0:
                break
            
            fill_qty = min(remaining, level.quantity)
            total_cost += fill_qty * level.price
            filled += fill_qty
            remaining -= fill_qty
        
        if filled == 0:
            return None
        
        avg_price = total_cost / filled
        return (avg_price, filled)
    
    def estimate_slippage(self, side: str, quantity: Decimal) -> Optional[Decimal]:
        """
        Estimate slippage percentage for a given quantity.
        
        Returns:
            Slippage as a decimal (e.g., 0.01 = 1%) or None if insufficient data
        """
        if side == 'buy':
            best_price = self.best_ask.price if self.best_ask else None
        else:
            best_price = self.best_bid.price if self.best_bid else None
        
        if not best_price or best_price == 0:
            return None
        
        result = self.estimate_fill_price(side, quantity)
        if not result:
            return None
        
        avg_price, _ = result
        
        if side == 'buy':
            # Slippage is how much more we pay vs best price
            slippage = (avg_price - best_price) / best_price
        else:
            # Slippage is how much less we receive vs best price
            slippage = (best_price - avg_price) / best_price
        
        return slippage
    
    def has_sufficient_liquidity(self, side: str, quantity: Decimal, max_slippage: Decimal = Decimal('0.05')) -> bool:
        """
        Check if there's sufficient liquidity for the order with acceptable slippage.
        
        Args:
            side: 'buy' or 'sell'
            quantity: Amount to trade
            max_slippage: Maximum acceptable slippage (default 5%)
        
        Returns:
            True if order can be filled within slippage tolerance
        """
        # Check if we can fill the entire quantity
        depth = self.get_depth(side)
        if depth < quantity:
            return False
        
        # Check slippage
        slippage = self.estimate_slippage(side, quantity)
        if slippage is None:
            return False
        
        return slippage <= max_slippage


@dataclass
class Order:
    """A trading order."""
    id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    price: Optional[Decimal]  # None for market orders
    status: OrderStatus
    filled_quantity: Decimal = Decimal("0")
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    
    @property
    def remaining_quantity(self) -> Decimal:
        """Remaining quantity to be filled."""
        return self.quantity - self.filled_quantity
    
    @property
    def is_open(self) -> bool:
        """Check if order is still open."""
        return self.status in [OrderStatus.PENDING, OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]


@dataclass
class Trade:
    """An executed trade."""
    id: str
    order_id: str
    symbol: str
    side: OrderSide
    quantity: Decimal
    price: Decimal
    fee: Decimal
    fee_currency: str
    executed_at: datetime


@dataclass
class TradingPair:
    """Information about a trading pair."""
    symbol: str
    base_currency: str  # e.g., BTC
    quote_currency: str  # e.g., KRW
    min_quantity: Decimal
    max_quantity: Decimal
    quantity_precision: int
    price_precision: int
    min_notional: Decimal  # Minimum order value
    is_active: bool = True


@dataclass
class PortfolioPosition:
    """A position in the portfolio."""
    currency: str
    quantity: Decimal
    value: Decimal  # In quote currency
    weight: Decimal  # Portfolio weight (0-1)
    target_weight: Decimal  # Target weight (0-1)
    
    @property
    def weight_diff(self) -> Decimal:
        """Difference between target and current weight."""
        return self.target_weight - self.weight


@dataclass
class Portfolio:
    """User portfolio state."""
    positions: Dict[str, PortfolioPosition] = field(default_factory=dict)
    total_value: Decimal = Decimal("0")
    quote_currency: str = "KRW"
    
    def get_position(self, currency: str) -> Optional[PortfolioPosition]:
        """Get position for a currency."""
        return self.positions.get(currency)
    
    def get_weight(self, currency: str) -> Decimal:
        """Get current weight for a currency."""
        position = self.positions.get(currency)
        return position.weight if position else Decimal("0")


@dataclass
class UserTradingContext:
    """Trading context for a user."""
    user_id: UUID
    exchange: ExchangeType
    access_key: str
    secret_key: str
    risk_level: int
    cash_weight: Decimal
    target_weights: Dict[str, Decimal] = field(default_factory=dict)
    current_balance: Optional[AccountBalance] = None
    portfolio: Optional[Portfolio] = None
    open_orders: List[Order] = field(default_factory=list)


@dataclass
class PriceData:
    """Price data for an asset."""
    symbol: str
    price: Decimal
    timestamp: datetime = field(default_factory=datetime.utcnow)
    volume_24h: Optional[Decimal] = None  # 24h trading volume in quote currency


@dataclass
class ReferencePrices:
    """Reference prices from Binance for price validation."""
    prices: Dict[str, Decimal] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def get_price(self, symbol: str) -> Optional[Decimal]:
        """Get reference price for a symbol."""
        return self.prices.get(symbol)
