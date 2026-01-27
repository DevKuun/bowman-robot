"""
Binance exchange adapter.
"""
import logging
import hmac
import hashlib
import time
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime
from urllib.parse import urlencode

import requests
from requests.exceptions import RequestException

from src.core.models import (
    ExchangeType, OrderSide, OrderType, OrderStatus,
    Balance, AccountBalance, OrderBook, OrderBookLevel, Order,
    TradingPair, PriceData
)
from src.exchanges.base import BaseExchange

logger = logging.getLogger(__name__)


class BinanceExchange(BaseExchange):
    """
    Binance exchange adapter.
    
    Implements the BaseExchange interface for Binance API.
    """
    
    BASE_URL = "https://api.binance.com"
    
    def __init__(self, access_key: str, secret_key: str):
        super().__init__(access_key, secret_key)
        self._trading_pairs_cache = None
        self._exchange_info_cache = None
    
    @property
    def exchange_type(self) -> ExchangeType:
        return ExchangeType.BINANCE
    
    @property
    def quote_currencies(self) -> List[str]:
        return ['USDT', 'BTC', 'ETH', 'BNB']
    
    def _sign(self, params: Dict) -> str:
        """Generate HMAC SHA256 signature."""
        query_string = urlencode(params)
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        signed: bool = False
    ) -> Dict:
        """Make a request to the Binance API."""
        url = f"{self.BASE_URL}{endpoint}"
        headers = {}
        
        if params is None:
            params = {}
        
        if self.access_key:
            headers['X-MBX-APIKEY'] = self.access_key
        
        if signed:
            params['timestamp'] = int(time.time() * 1000)
            params['signature'] = self._sign(params)
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=10)
            elif method == 'POST':
                response = requests.post(url, headers=headers, params=params, timeout=10)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, params=params, timeout=10)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response.json()
            
        except RequestException as e:
            logger.error(f"Binance API request failed: {e}")
            raise
    
    def _get_exchange_info(self) -> Dict:
        """Get exchange information with caching."""
        if self._exchange_info_cache is None:
            self._exchange_info_cache = self._request('GET', '/api/v3/exchangeInfo')
        return self._exchange_info_cache
    
    def get_trading_pairs(self) -> List[TradingPair]:
        """Get all available trading pairs."""
        if self._trading_pairs_cache:
            return self._trading_pairs_cache
        
        info = self._get_exchange_info()
        pairs = []
        
        for symbol_info in info['symbols']:
            if symbol_info['status'] != 'TRADING':
                continue
            
            # Extract filter values
            min_qty = Decimal('0.00000001')
            max_qty = Decimal('100000000')
            qty_precision = 8
            price_precision = 8
            min_notional = Decimal('10')
            
            for f in symbol_info['filters']:
                if f['filterType'] == 'LOT_SIZE':
                    min_qty = Decimal(f['minQty'])
                    max_qty = Decimal(f['maxQty'])
                    step_size = Decimal(f['stepSize'])
                    if step_size > 0:
                        qty_precision = abs(step_size.as_tuple().exponent)
                elif f['filterType'] == 'PRICE_FILTER':
                    tick_size = Decimal(f['tickSize'])
                    if tick_size > 0:
                        price_precision = abs(tick_size.as_tuple().exponent)
                elif f['filterType'] in ['MIN_NOTIONAL', 'NOTIONAL']:
                    min_notional = Decimal(f.get('minNotional', '10'))
            
            pairs.append(TradingPair(
                symbol=symbol_info['symbol'],
                base_currency=symbol_info['baseAsset'],
                quote_currency=symbol_info['quoteAsset'],
                min_quantity=min_qty,
                max_quantity=max_qty,
                quantity_precision=qty_precision,
                price_precision=price_precision,
                min_notional=min_notional,
                is_active=True
            ))
        
        self._trading_pairs_cache = pairs
        return pairs
    
    def get_account_balance(self) -> AccountBalance:
        """Get account balance for all assets."""
        result = self._request('GET', '/api/v3/account', signed=True)
        balances = {}
        
        for balance in result['balances']:
            free = Decimal(balance['free'])
            locked = Decimal(balance['locked'])
            
            if free > 0 or locked > 0:
                balances[balance['asset']] = Balance(
                    currency=balance['asset'],
                    available=free,
                    locked=locked
                )
        
        return AccountBalance(balances=balances)
    
    def get_order_book(self, symbol: str, levels: int = 5) -> OrderBook:
        """Get order book for a trading pair."""
        result = self._request(
            'GET', '/api/v3/depth',
            params={'symbol': symbol, 'limit': levels}
        )
        
        bids = [
            OrderBookLevel(
                price=Decimal(bid[0]),
                quantity=Decimal(bid[1])
            )
            for bid in result['bids']
        ]
        
        asks = [
            OrderBookLevel(
                price=Decimal(ask[0]),
                quantity=Decimal(ask[1])
            )
            for ask in result['asks']
        ]
        
        return OrderBook(
            symbol=symbol,
            bids=bids,
            asks=asks,
            timestamp=datetime.utcnow()
        )
    
    def get_order_books(self, symbols: List[str], levels: int = 5) -> Dict[str, OrderBook]:
        """Get order books for multiple trading pairs."""
        result = {}
        for symbol in symbols:
            try:
                result[symbol] = self.get_order_book(symbol, levels)
            except Exception as e:
                logger.warning(f"Failed to get order book for {symbol}: {e}")
        return result
    
    def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: Decimal,
        price: Optional[Decimal] = None
    ) -> Order:
        """Place a new order."""
        params = {
            'symbol': symbol,
            'side': 'BUY' if side in [OrderSide.BUY, OrderSide.BID] else 'SELL',
            'type': order_type.value,
            'quantity': str(quantity),
        }
        
        if order_type == OrderType.LIMIT:
            params['timeInForce'] = 'GTC'
            if price:
                params['price'] = str(price)
        
        result = self._request('POST', '/api/v3/order', params=params, signed=True)
        
        return Order(
            id=str(result['orderId']),
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            status=self._map_order_status(result['status']),
            filled_quantity=Decimal(result.get('executedQty', '0')),
            created_at=datetime.fromtimestamp(result['transactTime'] / 1000)
        )
    
    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> bool:
        """Cancel an order."""
        if not symbol:
            raise ValueError("Symbol is required for Binance order cancellation")
        
        try:
            self._request(
                'DELETE', '/api/v3/order',
                params={'symbol': symbol, 'orderId': int(order_id)},
                signed=True
            )
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False
    
    def get_order(self, order_id: str, symbol: Optional[str] = None) -> Optional[Order]:
        """Get order details."""
        if not symbol:
            raise ValueError("Symbol is required for Binance order query")
        
        try:
            result = self._request(
                'GET', '/api/v3/order',
                params={'symbol': symbol, 'orderId': int(order_id)},
                signed=True
            )
            
            side = OrderSide.BUY if result['side'] == 'BUY' else OrderSide.SELL
            order_type = OrderType.LIMIT if result['type'] == 'LIMIT' else OrderType.MARKET
            
            return Order(
                id=str(result['orderId']),
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=Decimal(result['origQty']),
                price=Decimal(result['price']) if result.get('price') else None,
                status=self._map_order_status(result['status']),
                filled_quantity=Decimal(result.get('executedQty', '0')),
                created_at=datetime.fromtimestamp(result['time'] / 1000)
            )
        except Exception as e:
            logger.error(f"Failed to get order {order_id}: {e}")
            return None
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get all open orders."""
        params = {}
        if symbol:
            params['symbol'] = symbol
        
        results = self._request('GET', '/api/v3/openOrders', params=params, signed=True)
        orders = []
        
        for result in results:
            side = OrderSide.BUY if result['side'] == 'BUY' else OrderSide.SELL
            order_type = OrderType.LIMIT if result['type'] == 'LIMIT' else OrderType.MARKET
            
            orders.append(Order(
                id=str(result['orderId']),
                symbol=result['symbol'],
                side=side,
                order_type=order_type,
                quantity=Decimal(result['origQty']),
                price=Decimal(result['price']) if result.get('price') else None,
                status=self._map_order_status(result['status']),
                filled_quantity=Decimal(result.get('executedQty', '0')),
                created_at=datetime.fromtimestamp(result['time'] / 1000)
            ))
        
        return orders
    
    def get_all_tickers(self) -> Dict[str, PriceData]:
        """Get current prices for all trading pairs."""
        tickers = self._request('GET', '/api/v3/ticker/price')
        
        result = {}
        now = datetime.utcnow()
        for ticker in tickers:
            symbol = ticker['symbol']
            result[symbol] = PriceData(
                symbol=symbol,
                price=Decimal(ticker['price']),
                timestamp=now
            )
        
        return result
    
    def get_historical_candles(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 200
    ) -> List[Dict]:
        """Get historical candlestick data."""
        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': min(limit, 1000)
        }
        
        if start_time:
            params['startTime'] = int(start_time.timestamp() * 1000)
        if end_time:
            params['endTime'] = int(end_time.timestamp() * 1000)
        
        klines = self._request('GET', '/api/v3/klines', params=params)
        
        return [
            {
                'timestamp': datetime.fromtimestamp(k[0] / 1000).isoformat(),
                'open': float(k[1]),
                'high': float(k[2]),
                'low': float(k[3]),
                'close': float(k[4]),
                'volume': float(k[5])
            }
            for k in klines
        ]
    
    def _map_order_status(self, binance_status: str) -> OrderStatus:
        """Map Binance order status to internal status."""
        status_map = {
            'NEW': OrderStatus.OPEN,
            'PARTIALLY_FILLED': OrderStatus.PARTIALLY_FILLED,
            'FILLED': OrderStatus.FILLED,
            'CANCELED': OrderStatus.CANCELLED,
            'REJECTED': OrderStatus.REJECTED,
            'EXPIRED': OrderStatus.CANCELLED,
        }
        return status_map.get(binance_status, OrderStatus.PENDING)
    
    # Binance-specific methods
    def get_trade_fees(self) -> Dict[str, Dict[str, Decimal]]:
        """Get trading fees for all pairs."""
        result = self._request('GET', '/sapi/v1/asset/tradeFee', signed=True)
        
        fees = {}
        for item in result:
            fees[item['symbol']] = {
                'maker': Decimal(item['makerCommission']),
                'taker': Decimal(item['takerCommission'])
            }
        
        return fees
