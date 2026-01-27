"""
Abstract base class for exchange adapters.
All exchange implementations must inherit from this class.
"""
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from src.core.models import (
    ExchangeType, OrderSide, OrderType, OrderStatus,
    Balance, AccountBalance, OrderBook, Order, Trade,
    TradingPair, PriceData
)


class BaseExchange(ABC):
    """
    Abstract base class for exchange adapters.
    
    Each exchange adapter must implement all abstract methods to provide
    a unified interface for trading operations.
    """
    
    def __init__(self, access_key: str, secret_key: str):
        """
        Initialize the exchange adapter.
        
        Args:
            access_key: API access key
            secret_key: API secret key
        """
        self.access_key = access_key
        self.secret_key = secret_key
        self._initialized = False
    
    @property
    @abstractmethod
    def exchange_type(self) -> ExchangeType:
        """Get the exchange type."""
        pass
    
    @property
    @abstractmethod
    def quote_currencies(self) -> List[str]:
        """Get supported quote currencies (e.g., ['KRW', 'BTC', 'USDT'])."""
        pass
    
    @abstractmethod
    def get_trading_pairs(self) -> List[TradingPair]:
        """
        Get all available trading pairs.
        
        Returns:
            List of trading pairs with their specifications
        """
        pass
    
    @abstractmethod
    def get_account_balance(self) -> AccountBalance:
        """
        Get account balance for all assets.
        
        Returns:
            AccountBalance object with all balances
        """
        pass
    
    @abstractmethod
    def get_order_book(self, symbol: str, levels: int = 5) -> OrderBook:
        """
        Get order book for a trading pair.
        
        Args:
            symbol: Trading pair symbol (e.g., 'KRW-BTC')
            levels: Number of price levels to retrieve
            
        Returns:
            OrderBook object
        """
        pass
    
    @abstractmethod
    def get_order_books(self, symbols: List[str], levels: int = 5) -> Dict[str, OrderBook]:
        """
        Get order books for multiple trading pairs.
        
        Args:
            symbols: List of trading pair symbols
            levels: Number of price levels to retrieve
            
        Returns:
            Dictionary mapping symbol to OrderBook
        """
        pass
    
    @abstractmethod
    def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: Decimal,
        price: Optional[Decimal] = None
    ) -> Order:
        """
        Place a new order.
        
        Args:
            symbol: Trading pair symbol
            side: Order side (BUY/SELL)
            order_type: Order type (LIMIT/MARKET)
            quantity: Order quantity
            price: Order price (required for LIMIT orders)
            
        Returns:
            Created Order object
        """
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> bool:
        """
        Cancel an order.
        
        Args:
            order_id: Order ID to cancel
            symbol: Optional symbol (required for some exchanges)
            
        Returns:
            True if cancellation was successful
        """
        pass
    
    @abstractmethod
    def get_order(self, order_id: str, symbol: Optional[str] = None) -> Optional[Order]:
        """
        Get order details.
        
        Args:
            order_id: Order ID
            symbol: Optional symbol (required for some exchanges)
            
        Returns:
            Order object or None if not found
        """
        pass
    
    @abstractmethod
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """
        Get all open orders.
        
        Args:
            symbol: Optional symbol to filter orders
            
        Returns:
            List of open orders
        """
        pass
    
    @abstractmethod
    def get_all_tickers(self) -> Dict[str, PriceData]:
        """
        Get current prices for all trading pairs.
        
        Returns:
            Dictionary mapping symbol to PriceData
        """
        pass
    
    @abstractmethod
    def get_historical_candles(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 200
    ) -> List[Dict]:
        """
        Get historical candlestick data.
        
        Args:
            symbol: Trading pair symbol
            interval: Candle interval (e.g., '1d', '1w')
            start_time: Start time for historical data
            end_time: End time for historical data
            limit: Maximum number of candles to retrieve
            
        Returns:
            List of candle data dictionaries
        """
        pass
    
    # Helper methods
    def get_tick_size(self, quote_currency: str, price: Decimal) -> Decimal:
        """
        Get tick size for a price level.
        
        Args:
            quote_currency: Quote currency (KRW, BTC, USDT)
            price: Current price
            
        Returns:
            Tick size for the price level
        """
        # Default implementation, can be overridden
        if quote_currency == 'KRW':
            if price < Decimal("0.1"):
                return Decimal("0.0001")
            elif price < Decimal("1"):
                return Decimal("0.001")
            elif price < Decimal("10"):
                return Decimal("0.01")
            elif price < Decimal("100"):
                return Decimal("0.1")
            elif price < Decimal("1000"):
                return Decimal("1")
            elif price < Decimal("10000"):
                return Decimal("5")
            elif price < Decimal("100000"):
                return Decimal("10")
            elif price < Decimal("500000"):
                return Decimal("50")
            elif price < Decimal("1000000"):
                return Decimal("100")
            elif price < Decimal("2000000"):
                return Decimal("500")
            else:
                return Decimal("1000")
        elif quote_currency == 'USDT':
            if price >= Decimal("10"):
                return Decimal("0.01")
            elif price >= Decimal("1"):
                return Decimal("0.001")
            elif price >= Decimal("0.1"):
                return Decimal("0.0001")
            elif price >= Decimal("0.01"):
                return Decimal("0.00001")
            elif price >= Decimal("0.001"):
                return Decimal("0.000001")
            elif price >= Decimal("0.0001"):
                return Decimal("0.0000001")
            else:
                return Decimal("0.00000001")
        else:  # BTC, ETH
            return Decimal("0.00000001")
    
    def round_price(self, quote_currency: str, price: Decimal, round_down: bool = True) -> Decimal:
        """
        Round price to valid tick size.
        
        Args:
            quote_currency: Quote currency
            price: Price to round
            round_down: If True, round down; otherwise round up
            
        Returns:
            Rounded price
        """
        tick_size = self.get_tick_size(quote_currency, price)
        if round_down:
            return (price // tick_size) * tick_size
        else:
            return ((price // tick_size) + 1) * tick_size
    
    def validate_order(
        self,
        pair: TradingPair,
        quantity: Decimal,
        price: Optional[Decimal]
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate an order before placing.
        
        Args:
            pair: Trading pair information
            quantity: Order quantity
            price: Order price
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if quantity < pair.min_quantity:
            return False, f"Quantity {quantity} below minimum {pair.min_quantity}"
        
        if quantity > pair.max_quantity:
            return False, f"Quantity {quantity} above maximum {pair.max_quantity}"
        
        if price is not None:
            notional = quantity * price
            if notional < pair.min_notional:
                return False, f"Order value {notional} below minimum {pair.min_notional}"
        
        return True, None


# Re-export ExchangeType for convenience
__all__ = ['BaseExchange', 'ExchangeType']
