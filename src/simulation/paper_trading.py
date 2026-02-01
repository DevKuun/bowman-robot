"""
Paper Trading simulation module.
Simulates trades without real execution, tracks virtual portfolio and PnL.

Features:
- Realistic order execution with order book depth consideration
- Ask/Bid spread simulation
- Slippage calculation based on order size and liquidity
- Partial fill support for low liquidity scenarios
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.core.models import (
    ExchangeType, OrderSide, OrderType, OrderStatus,
    Balance, AccountBalance, Order, OrderBook, OrderBookLevel
)
from src.exchanges.base import BaseExchange

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result of a realistic order execution."""
    filled_quantity: Decimal
    avg_price: Decimal
    total_cost: Decimal  # filled_quantity * avg_price
    slippage_percent: Decimal  # vs best price
    unfilled_quantity: Decimal
    best_price: Decimal  # Reference price (best ask/bid)
    fee: Decimal
    levels_consumed: int  # Number of order book levels consumed
    
    @property
    def is_fully_filled(self) -> bool:
        return self.unfilled_quantity <= Decimal("0.00000001")
    
    def to_dict(self) -> dict:
        return {
            'filled_quantity': str(self.filled_quantity),
            'avg_price': str(self.avg_price),
            'total_cost': str(self.total_cost),
            'slippage_percent': f"{self.slippage_percent:.4f}",
            'unfilled_quantity': str(self.unfilled_quantity),
            'best_price': str(self.best_price),
            'fee': str(self.fee),
            'levels_consumed': self.levels_consumed
        }


class RealisticOrderExecutor:
    """
    Realistic order execution simulator that considers:
    - Order book depth (liquidity)
    - Ask/Bid spread
    - Slippage based on order size
    - Partial fills when liquidity is insufficient
    """
    
    def __init__(self, fee_rate: Decimal = Decimal("0.0005")):
        """
        Initialize executor.
        
        Args:
            fee_rate: Trading fee rate (default 0.05%)
        """
        self.fee_rate = fee_rate
    
    def calculate_execution(
        self,
        order_book: OrderBook,
        side: OrderSide,
        quantity: Decimal
    ) -> ExecutionResult:
        """
        Calculate realistic execution by consuming order book levels.
        
        For BUY orders: consume ASK levels (we pay asking price)
        For SELL orders: consume BID levels (we receive bid price)
        
        Args:
            order_book: Current order book with bid/ask levels
            side: Order side (BUY or SELL)
            quantity: Desired order quantity
            
        Returns:
            ExecutionResult with avg price, slippage, etc.
        """
        # Select appropriate side of order book
        if side in [OrderSide.BUY, OrderSide.BID]:
            levels = order_book.asks  # We buy at ask prices
        else:
            levels = order_book.bids  # We sell at bid prices
        
        if not levels:
            # No liquidity available
            return ExecutionResult(
                filled_quantity=Decimal("0"),
                avg_price=Decimal("0"),
                total_cost=Decimal("0"),
                slippage_percent=Decimal("0"),
                unfilled_quantity=quantity,
                best_price=Decimal("0"),
                fee=Decimal("0"),
                levels_consumed=0
            )
        
        best_price = levels[0].price
        remaining = quantity
        total_cost = Decimal("0")
        filled = Decimal("0")
        levels_consumed = 0
        
        for level in levels:
            if remaining <= Decimal("0"):
                break
            
            # Take as much as available at this level
            take = min(remaining, level.quantity)
            total_cost += take * level.price
            filled += take
            remaining -= take
            levels_consumed += 1
        
        # Calculate average price and slippage
        if filled > 0:
            avg_price = total_cost / filled
            # Slippage is the difference from best price
            if side in [OrderSide.BUY, OrderSide.BID]:
                # For buys, higher avg price = negative slippage (we pay more)
                slippage = (avg_price / best_price - 1) * 100
            else:
                # For sells, lower avg price = negative slippage (we receive less)
                slippage = (1 - avg_price / best_price) * 100
        else:
            avg_price = Decimal("0")
            slippage = Decimal("0")
        
        fee = total_cost * self.fee_rate
        
        return ExecutionResult(
            filled_quantity=filled,
            avg_price=avg_price,
            total_cost=total_cost,
            slippage_percent=slippage,
            unfilled_quantity=remaining,
            best_price=best_price,
            fee=fee,
            levels_consumed=levels_consumed
        )
    
    def estimate_slippage(
        self,
        order_book: OrderBook,
        side: OrderSide,
        value: Decimal
    ) -> Tuple[Decimal, Decimal]:
        """
        Estimate slippage for a given trade value.
        
        Args:
            order_book: Current order book
            side: Order side
            value: Trade value in quote currency
            
        Returns:
            Tuple of (estimated_slippage_percent, estimated_quantity)
        """
        levels = order_book.asks if side in [OrderSide.BUY, OrderSide.BID] else order_book.bids
        
        if not levels:
            return Decimal("100"), Decimal("0")  # 100% slippage = no liquidity
        
        best_price = levels[0].price
        # Estimate quantity based on best price
        estimated_qty = value / best_price
        
        # Calculate actual execution
        result = self.calculate_execution(order_book, side, estimated_qty)
        
        return result.slippage_percent, result.filled_quantity


@dataclass
class SimulatedTrade:
    """Record of a simulated trade with realistic execution details."""
    timestamp: datetime
    symbol: str
    side: OrderSide
    quantity: Decimal
    price: Decimal  # Average execution price
    value: Decimal  # quantity * price
    fee: Decimal
    # New fields for realistic simulation
    best_price: Decimal = Decimal("0")  # Best ask/bid at time of execution
    slippage_percent: Decimal = Decimal("0")
    levels_consumed: int = 0
    partially_filled: bool = False
    below_minimum: bool = False  # Trade value is below minimum trade amount
    slippage_reduced: bool = False  # True if below_minimum was caused by slippage
    original_value: Decimal = Decimal("0")  # Original requested trade value (before slippage)
    
    def to_dict(self) -> dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'symbol': self.symbol,
            'side': self.side.value,
            'quantity': str(self.quantity),
            'price': str(self.price),
            'value': str(self.value),
            'fee': str(self.fee),
            'best_price': str(self.best_price),
            'slippage_percent': f"{self.slippage_percent:.4f}%",
            'levels_consumed': self.levels_consumed,
            'partially_filled': self.partially_filled,
            'below_minimum': self.below_minimum,
            'slippage_reduced': self.slippage_reduced,
            'original_value': str(self.original_value)
        }


@dataclass
class PortfolioSnapshot:
    """Snapshot of portfolio at a point in time."""
    timestamp: datetime
    balances: Dict[str, Decimal]
    prices: Dict[str, Decimal]
    total_value: Decimal
    pnl: Decimal
    pnl_percent: Decimal
    
    def to_dict(self) -> dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'balances': {k: str(v) for k, v in self.balances.items()},
            'total_value': str(self.total_value),
            'pnl': str(self.pnl),
            'pnl_percent': str(self.pnl_percent)
        }


class PaperTradingAccount:
    """
    Virtual trading account for paper trading.
    Tracks balances, executes simulated trades, and calculates PnL.
    
    Supports realistic order execution with:
    - Order book depth consideration
    - Ask/Bid spread
    - Slippage calculation
    - Partial fills
    """
    
    def __init__(
        self,
        exchange_type: ExchangeType,
        initial_balance: Dict[str, Decimal] = None,
        fee_rate: Decimal = Decimal("0.0005"),
        data_dir: str = "data/paper_trading",
        realistic_execution: bool = True
    ):
        """
        Initialize paper trading account.
        
        Args:
            exchange_type: Type of exchange to simulate
            initial_balance: Starting balances (default: 1,000,000 KRW)
            fee_rate: Trading fee rate
            data_dir: Directory to save trading data
            realistic_execution: Enable realistic order execution with slippage
        """
        self.exchange_type = exchange_type
        self.fee_rate = fee_rate
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.realistic_execution = realistic_execution
        
        # Realistic order executor
        self.executor = RealisticOrderExecutor(fee_rate=fee_rate)
        
        # Initialize balances
        if initial_balance:
            self.balances = {k: Decimal(str(v)) for k, v in initial_balance.items()}
        else:
            # Default: 1,000,000 KRW
            quote = self._get_quote_currency()
            self.balances = {quote: Decimal("1000000")}
        
        self.initial_balances = self.balances.copy()
        self.initial_value: Optional[Decimal] = None
        
        # Trading history
        self.trades: List[SimulatedTrade] = []
        self.snapshots: List[PortfolioSnapshot] = []
        
        # Current prices cache
        self.current_prices: Dict[str, Decimal] = {}
        
        # Stats
        self.total_trades = 0
        self.total_fees = Decimal("0")
        self.total_slippage_cost = Decimal("0")  # Total cost due to slippage
        self.partial_fills = 0  # Count of partial fills
        self.start_time = datetime.utcnow()
        
        mode = "REALISTIC" if realistic_execution else "SIMPLE"
        logger.info(f"Paper trading account initialized ({mode} mode): {self.balances}")
    
    def _get_quote_currency(self) -> str:
        """Get the default quote currency for this exchange."""
        if self.exchange_type in [ExchangeType.UPBIT, ExchangeType.KORBIT, ExchangeType.BITHUMB]:
            return "KRW"
        return "USDT"
    
    def _get_quote_currency_from_symbol(self, symbol: str) -> str:
        """Extract quote currency from symbol."""
        if '-' in symbol:  # Upbit: KRW-BTC, BTC-ETH, USDT-BTC
            return symbol.split('-')[0]
        elif '_' in symbol:  # Korbit/Bithumb: btc_krw
            return symbol.split('_')[1].upper()
        else:  # Binance: BTCUSDT
            for quote in ['USDT', 'BTC', 'ETH']:
                if symbol.endswith(quote):
                    return quote
        return self._get_quote_currency()
    
    def _get_base_currency(self, symbol: str) -> str:
        """Extract base currency from symbol."""
        if '-' in symbol:  # Upbit: KRW-BTC
            return symbol.split('-')[1]
        elif '_' in symbol:  # Korbit/Bithumb: btc_krw, BTC_KRW
            return symbol.split('_')[0].upper()
        else:  # Binance: BTCUSDT
            for quote in ['USDT', 'BTC', 'ETH']:
                if symbol.endswith(quote):
                    return symbol[:-len(quote)]
        return symbol
    
    def get_account_balance(self) -> AccountBalance:
        """Get current virtual balance."""
        balances = {}
        for currency, amount in self.balances.items():
            if amount > 0:
                balances[currency] = Balance(
                    currency=currency,
                    available=amount,
                    locked=Decimal("0")
                )
        return AccountBalance(balances=balances)
    
    def update_prices(self, prices: Dict[str, Decimal]):
        """Update current price cache."""
        self.current_prices.update(prices)
    
    def execute_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        price: Decimal
    ) -> Optional[Order]:
        """
        Execute a simulated order (simple mode - no slippage).
        
        Args:
            symbol: Trading pair symbol
            side: Buy or sell
            quantity: Order quantity
            price: Order price
            
        Returns:
            Simulated order result
        """
        base_currency = self._get_base_currency(symbol)
        quote_currency = self._get_quote_currency_from_symbol(symbol)
        
        value = quantity * price
        fee = value * self.fee_rate
        
        # Check if we have enough balance
        if side in [OrderSide.BUY, OrderSide.BID]:
            required = value + fee
            if self.balances.get(quote_currency, Decimal("0")) < required:
                logger.warning(f"Insufficient {quote_currency} balance for buy order")
                return None
            
            # Execute buy
            self.balances[quote_currency] = self.balances.get(quote_currency, Decimal("0")) - required
            self.balances[base_currency] = self.balances.get(base_currency, Decimal("0")) + quantity
            
        else:  # SELL
            if self.balances.get(base_currency, Decimal("0")) < quantity:
                logger.warning(f"Insufficient {base_currency} balance for sell order")
                return None
            
            # Execute sell
            self.balances[base_currency] = self.balances.get(base_currency, Decimal("0")) - quantity
            self.balances[quote_currency] = self.balances.get(quote_currency, Decimal("0")) + value - fee
        
        # Record trade
        trade = SimulatedTrade(
            timestamp=datetime.utcnow(),
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            value=value,
            fee=fee,
            best_price=price,
            slippage_percent=Decimal("0"),
            levels_consumed=1,
            partially_filled=False
        )
        self.trades.append(trade)
        self.total_trades += 1
        self.total_fees += fee
        
        # Clean up zero balances
        self.balances = {k: v for k, v in self.balances.items() if v > Decimal("0.00000001")}
        
        logger.info(f"[PAPER] {side.value} {quantity} {base_currency} @ {price} = {value} {quote_currency} (fee: {fee})")
        
        return Order(
            id=f"paper_{self.total_trades}",
            symbol=symbol,
            side=side,
            order_type=OrderType.LIMIT,
            quantity=quantity,
            price=price,
            status=OrderStatus.FILLED,
            filled_quantity=quantity,
            created_at=datetime.utcnow()
        )
    
    def execute_order_realistic(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        order_book: OrderBook
    ) -> Optional[Order]:
        """
        Execute a simulated order with realistic slippage and order book consumption.
        
        Args:
            symbol: Trading pair symbol
            side: Buy or sell
            quantity: Order quantity
            order_book: Current order book for the symbol
            
        Returns:
            Simulated order result (may be partially filled)
        """
        # Validate order book has data
        if side in [OrderSide.BUY, OrderSide.BID]:
            if not order_book.asks or not order_book.best_ask or order_book.best_ask.price <= 0:
                logger.warning(f"[Invalid Market] {symbol}: No valid ask prices - skipping trade")
                return None
        else:
            if not order_book.bids or not order_book.best_bid or order_book.best_bid.price <= 0:
                logger.warning(f"[Invalid Market] {symbol}: No valid bid prices - skipping trade")
                return None
        
        base_currency = self._get_base_currency(symbol)
        quote_currency = self._get_quote_currency_from_symbol(symbol)
        
        # Calculate realistic execution
        result = self.executor.calculate_execution(order_book, side, quantity)
        
        if result.filled_quantity <= 0:
            logger.warning(f"No liquidity available for {symbol}")
            return None
        
        # Check if we have enough balance
        if side in [OrderSide.BUY, OrderSide.BID]:
            required = result.total_cost + result.fee
            available = self.balances.get(quote_currency, Decimal("0"))
            
            if available < required:
                # Recalculate with available balance
                max_value = available / (1 + self.fee_rate)
                max_qty = max_value / result.best_price if result.best_price > 0 else Decimal("0")
                
                if max_qty <= 0:
                    logger.warning(
                        f"Insufficient {quote_currency} balance for buy order: "
                        f"{symbol} - need {required:.0f} {quote_currency}, "
                        f"available {available:.0f} {quote_currency}"
                    )
                    return None
                
                # Recalculate execution with reduced quantity
                result = self.executor.calculate_execution(order_book, side, max_qty)
                if result.filled_quantity <= 0:
                    return None
            
            # Execute buy
            self.balances[quote_currency] = self.balances.get(quote_currency, Decimal("0")) - result.total_cost - result.fee
            self.balances[base_currency] = self.balances.get(base_currency, Decimal("0")) + result.filled_quantity
            
        else:  # SELL
            available = self.balances.get(base_currency, Decimal("0"))
            
            if available < quantity:
                # Use available balance
                if available <= 0:
                    logger.warning(
                        f"Insufficient {base_currency} balance for sell order: "
                        f"{symbol} - need {quantity:.8f} {base_currency}, "
                        f"available {available:.8f} {base_currency}"
                    )
                    return None
                
                # Recalculate with available quantity
                result = self.executor.calculate_execution(order_book, side, available)
                if result.filled_quantity <= 0:
                    return None
            
            # Execute sell
            self.balances[base_currency] = self.balances.get(base_currency, Decimal("0")) - result.filled_quantity
            self.balances[quote_currency] = self.balances.get(quote_currency, Decimal("0")) + result.total_cost - result.fee
        
        # Calculate slippage cost (what we lost due to slippage)
        ideal_cost = result.filled_quantity * result.best_price
        if side in [OrderSide.BUY, OrderSide.BID]:
            slippage_cost = result.total_cost - ideal_cost  # Paid more than ideal
        else:
            slippage_cost = ideal_cost - result.total_cost  # Received less than ideal
        
        # Record trade
        partially_filled = not result.is_fully_filled
        trade = SimulatedTrade(
            timestamp=datetime.utcnow(),
            symbol=symbol,
            side=side,
            quantity=result.filled_quantity,
            price=result.avg_price,
            value=result.total_cost,
            fee=result.fee,
            best_price=result.best_price,
            slippage_percent=result.slippage_percent,
            levels_consumed=result.levels_consumed,
            partially_filled=partially_filled
        )
        self.trades.append(trade)
        self.total_trades += 1
        self.total_fees += result.fee
        self.total_slippage_cost += slippage_cost
        
        if partially_filled:
            self.partial_fills += 1
        
        # Clean up zero balances
        self.balances = {k: v for k, v in self.balances.items() if v > Decimal("0.00000001")}
        
        # Log with slippage info
        slippage_str = f", slippage: {result.slippage_percent:.2f}%" if result.slippage_percent != 0 else ""
        partial_str = " [PARTIAL]" if partially_filled else ""
        logger.info(
            f"[PAPER] {side.value} {result.filled_quantity:.8f} {base_currency} "
            f"@ avg {result.avg_price:.2f} (best: {result.best_price:.2f}) "
            f"= {result.total_cost:.0f} {quote_currency} "
            f"(fee: {result.fee:.2f}{slippage_str}){partial_str}"
        )
        
        return Order(
            id=f"paper_{self.total_trades}",
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,  # Realistic execution is like market order
            quantity=result.filled_quantity,
            price=result.avg_price,
            status=OrderStatus.FILLED if result.is_fully_filled else OrderStatus.PARTIALLY_FILLED,
            filled_quantity=result.filled_quantity,
            created_at=datetime.utcnow()
        )
    
    def calculate_portfolio_value(self, prices: Dict[str, Decimal] = None) -> Decimal:
        """Calculate total portfolio value in primary quote currency (KRW for Korean exchanges)."""
        if prices:
            self.update_prices(prices)
        
        quote_currency = self._get_quote_currency()
        total = self.balances.get(quote_currency, Decimal("0"))
        
        # Get cross rates for multi-market support (Upbit)
        cross_rates = {}
        if self.exchange_type == ExchangeType.UPBIT:
            if 'KRW-BTC' in self.current_prices:
                cross_rates['BTC'] = self.current_prices['KRW-BTC']
            if 'KRW-USDT' in self.current_prices:
                cross_rates['USDT'] = self.current_prices['KRW-USDT']
        
        for currency, amount in self.balances.items():
            if currency == quote_currency:
                continue
            
            # Find price for this currency (convert to primary quote currency)
            price_in_quote = None
            
            if self.exchange_type == ExchangeType.UPBIT:
                # Try KRW market first
                if f"KRW-{currency}" in self.current_prices:
                    price_in_quote = self.current_prices[f"KRW-{currency}"]
                # Try USDT market and convert to KRW
                elif f"USDT-{currency}" in self.current_prices and 'USDT' in cross_rates:
                    usdt_price = self.current_prices[f"USDT-{currency}"]
                    price_in_quote = usdt_price * cross_rates['USDT']
                # Try BTC market and convert to KRW
                elif f"BTC-{currency}" in self.current_prices and 'BTC' in cross_rates:
                    btc_price = self.current_prices[f"BTC-{currency}"]
                    price_in_quote = btc_price * cross_rates['BTC']
            elif self.exchange_type == ExchangeType.BITHUMB:
                price_in_quote = self.current_prices.get(f"{currency}_KRW")
            elif self.exchange_type == ExchangeType.BINANCE:
                price_in_quote = self.current_prices.get(f"{currency}USDT")
            
            if price_in_quote:
                total += amount * price_in_quote
        
        return total
    
    def calculate_pnl(self, prices: Dict[str, Decimal] = None) -> tuple[Decimal, Decimal, Decimal]:
        """
        Calculate profit and loss.
        
        Returns:
            Tuple of (absolute PnL, percentage PnL, total_value)
        """
        current_value = self.calculate_portfolio_value(prices)
        
        # Set initial value on first calculation
        if self.initial_value is None:
            self.initial_value = current_value
        
        pnl = current_value - self.initial_value
        pnl_percent = (pnl / self.initial_value * 100) if self.initial_value > 0 else Decimal("0")
        
        return pnl, pnl_percent, current_value
    
    def take_snapshot(self, prices: Dict[str, Decimal] = None):
        """Take a snapshot of current portfolio state."""
        if prices:
            self.update_prices(prices)
        
        # Get all values from single calculation
        pnl, pnl_percent, total_value = self.calculate_pnl()
        
        snapshot = PortfolioSnapshot(
            timestamp=datetime.utcnow(),
            balances=self.balances.copy(),
            prices=self.current_prices.copy(),
            total_value=total_value,
            pnl=pnl,
            pnl_percent=pnl_percent
        )
        self.snapshots.append(snapshot)
        
        return snapshot
    
    def get_summary(self) -> dict:
        """Get trading summary including slippage statistics."""
        pnl, pnl_percent, current_value = self.calculate_pnl()
        
        # Calculate average slippage from trades
        if self.trades:
            avg_slippage = sum(t.slippage_percent for t in self.trades) / len(self.trades)
            max_slippage = max(t.slippage_percent for t in self.trades)
        else:
            avg_slippage = Decimal("0")
            max_slippage = Decimal("0")
        
        return {
            'exchange': self.exchange_type.value,
            'start_time': self.start_time.isoformat(),
            'duration_hours': (datetime.utcnow() - self.start_time).total_seconds() / 3600,
            'initial_value': str(self.initial_value or current_value),
            'current_value': str(current_value),
            'pnl': str(pnl),
            'pnl_percent': f"{pnl_percent:.2f}%",
            'total_trades': self.total_trades,
            'total_fees': str(self.total_fees),
            'total_slippage_cost': str(self.total_slippage_cost),
            'avg_slippage_percent': f"{avg_slippage:.4f}%",
            'max_slippage_percent': f"{max_slippage:.4f}%",
            'partial_fills': self.partial_fills,
            'realistic_mode': self.realistic_execution,
            'current_balances': {k: str(v) for k, v in self.balances.items()}
        }
    
    def print_summary(self):
        """Print trading summary to console."""
        summary = self.get_summary()
        
        print("\n" + "=" * 60)
        print("PAPER TRADING SUMMARY")
        print("=" * 60)
        print(f"Exchange: {summary['exchange']}")
        print(f"Mode: {'REALISTIC' if summary['realistic_mode'] else 'SIMPLE'}")
        print(f"Duration: {summary['duration_hours']:.1f} hours")
        print("-" * 60)
        print(f"Initial Value: {summary['initial_value']}")
        print(f"Current Value: {summary['current_value']}")
        print(f"PnL: {summary['pnl']} ({summary['pnl_percent']})")
        print("-" * 60)
        print(f"Total Trades: {summary['total_trades']}")
        print(f"Partial Fills: {summary['partial_fills']}")
        print(f"Total Fees: {summary['total_fees']}")
        print(f"Total Slippage Cost: {summary['total_slippage_cost']}")
        print(f"Avg Slippage: {summary['avg_slippage_percent']}")
        print(f"Max Slippage: {summary['max_slippage_percent']}")
        print("-" * 60)
        print("Current Balances:")
        for currency, amount in summary['current_balances'].items():
            print(f"  {currency}: {amount}")
        print("=" * 60 + "\n")
    
    def save_to_file(self):
        """Save trading history to file."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = self.data_dir / f"paper_trading_{self.exchange_type.value}_{timestamp}.json"
        
        data = {
            'summary': self.get_summary(),
            'trades': [t.to_dict() for t in self.trades],
            'snapshots': [s.to_dict() for s in self.snapshots[-100:]]  # Last 100 snapshots
        }
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Paper trading data saved to {filename}")
        return filename


class PaperTradingExchange(BaseExchange):
    """
    Exchange wrapper for paper trading.
    Wraps a real exchange for market data but executes trades virtually.
    
    Supports two execution modes:
    - Simple: Uses single price (fast but unrealistic)
    - Realistic: Uses order book depth with slippage calculation
    """
    
    def __init__(
        self,
        real_exchange: BaseExchange,
        paper_account: PaperTradingAccount
    ):
        """
        Initialize paper trading exchange.
        
        Args:
            real_exchange: Real exchange for market data
            paper_account: Paper trading account for virtual trades
        """
        super().__init__("", "")  # No real credentials needed
        self.real_exchange = real_exchange
        self.paper_account = paper_account
        
        # Cache order books for realistic execution
        self._order_book_cache: Dict[str, OrderBook] = {}
    
    @property
    def exchange_type(self) -> ExchangeType:
        return self.real_exchange.exchange_type
    
    @property
    def quote_currencies(self) -> list:
        return self.real_exchange.quote_currencies
    
    # Market data methods - delegate to real exchange
    def get_trading_pairs(self):
        return self.real_exchange.get_trading_pairs()
    
    def get_order_book(self, symbol: str, levels: int = 5):
        order_book = self.real_exchange.get_order_book(symbol, levels)
        # Cache for realistic execution
        self._order_book_cache[symbol] = order_book
        return order_book
    
    def get_order_books(self, symbols: list, levels: int = 5):
        order_books = self.real_exchange.get_order_books(symbols, levels)
        # Cache for realistic execution
        self._order_book_cache.update(order_books)
        return order_books
    
    def update_order_book_cache(self, order_books: Dict[str, OrderBook]):
        """Update order book cache with pre-fetched data."""
        self._order_book_cache.update(order_books)
    
    def get_all_tickers(self):
        tickers = self.real_exchange.get_all_tickers()
        # Update paper account prices
        prices = {symbol: data.price for symbol, data in tickers.items()}
        self.paper_account.update_prices(prices)
        return tickers
    
    def get_historical_candles(self, symbol: str, interval: str, **kwargs):
        return self.real_exchange.get_historical_candles(symbol, interval, **kwargs)
    
    # Account methods - use paper account
    def get_account_balance(self) -> AccountBalance:
        return self.paper_account.get_account_balance()
    
    # Order methods - simulate via paper account
    def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        order_book: Optional[OrderBook] = None
    ) -> Order:
        """
        Place a simulated order.
        
        Args:
            symbol: Trading pair symbol
            side: Buy or sell
            order_type: Order type (LIMIT or MARKET)
            quantity: Order quantity
            price: Order price (optional for realistic mode)
            order_book: Order book for realistic execution (optional)
            
        Returns:
            Simulated order result
        """
        # Use realistic execution if enabled and order book is available
        if self.paper_account.realistic_execution:
            # Get order book from cache or fetch
            if order_book is None:
                order_book = self._order_book_cache.get(symbol)
            
            if order_book is None:
                # Fetch order book with more levels for accurate slippage
                try:
                    order_book = self.get_order_book(symbol, levels=10)
                except Exception as e:
                    logger.warning(f"Could not get order book for {symbol}: {e}")
                    order_book = None
            
            if order_book and (order_book.asks or order_book.bids):
                return self.paper_account.execute_order_realistic(
                    symbol, side, quantity, order_book
                )
        
        # Fallback to simple execution
        if price is None:
            # Get current price from order book
            try:
                ob = self.get_order_book(symbol, levels=1)
                if side in [OrderSide.BUY, OrderSide.BID]:
                    price = ob.asks[0].price if ob.asks else Decimal("0")
                else:
                    price = ob.bids[0].price if ob.bids else Decimal("0")
            except Exception:
                logger.warning(f"Could not get price for {symbol}")
                return None
        
        return self.paper_account.execute_order(symbol, side, quantity, price)
    
    def place_order_realistic(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        order_book: OrderBook
    ) -> Optional[Order]:
        """
        Place a simulated order with realistic execution.
        
        This method directly uses the order book for slippage calculation.
        
        Args:
            symbol: Trading pair symbol
            side: Buy or sell
            quantity: Order quantity
            order_book: Current order book
            
        Returns:
            Simulated order result
        """
        return self.paper_account.execute_order_realistic(
            symbol, side, quantity, order_book
        )
    
    def cancel_order(self, order_id: str, symbol: str = None) -> bool:
        """Paper trading orders are always filled immediately."""
        return True
    
    def get_order(self, order_id: str, symbol: str = None) -> Optional[Order]:
        """Paper trading orders are always filled."""
        return None
    
    def get_open_orders(self, symbol: str = None) -> list:
        """No open orders in paper trading (all filled immediately)."""
        return []
