"""
Bithumb exchange adapter.
"""
import logging
import hmac
import hashlib
import base64
import time
import urllib.parse
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime

import requests
from requests.exceptions import RequestException

from src.core.models import (
    ExchangeType, OrderSide, OrderType, OrderStatus,
    Balance, AccountBalance, OrderBook, OrderBookLevel, Order,
    TradingPair, PriceData
)
from src.exchanges.base import BaseExchange

logger = logging.getLogger(__name__)


class BithumbExchange(BaseExchange):
    """
    Bithumb exchange adapter.
    
    Implements the BaseExchange interface for Bithumb API.
    """
    
    BASE_URL = "https://api.bithumb.com"
    
    def __init__(self, access_key: str, secret_key: str):
        super().__init__(access_key, secret_key)
        self._trading_pairs_cache = None
    
    @property
    def exchange_type(self) -> ExchangeType:
        return ExchangeType.BITHUMB
    
    @property
    def quote_currencies(self) -> List[str]:
        # Only use KRW market for better liquidity
        return ['KRW']
    
    def _generate_signature(self, endpoint: str, params: Dict) -> Dict[str, str]:
        """Generate HMAC signature for authentication."""
        # Convert params to URL-encoded string
        encoded_params = urllib.parse.urlencode(params)
        
        # Create signature string
        nonce = str(int(time.time() * 1000))
        signature_string = f"{endpoint}\x00{encoded_params}\x00{nonce}"
        
        # Generate HMAC-SHA512 signature
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            signature_string.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()
        
        # Encode signature to base64
        signature_b64 = base64.b64encode(signature.encode('utf-8')).decode('utf-8')
        
        return {
            'Api-Key': self.access_key,
            'Api-Sign': signature_b64,
            'Api-Nonce': nonce,
            'Content-Type': 'application/x-www-form-urlencoded'
        }
    
    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        auth: bool = True
    ) -> Dict:
        """Make a request to the Bithumb API."""
        url = f"{self.BASE_URL}{endpoint}"
        
        if params is None:
            params = {}
        
        headers = {}
        
        try:
            if method == 'GET':
                response = requests.get(url, params=params, timeout=10)
            elif method == 'POST':
                if auth:
                    headers = self._generate_signature(endpoint, params)
                response = requests.post(
                    url, 
                    headers=headers, 
                    data=urllib.parse.urlencode(params),
                    timeout=10
                )
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            result = response.json()
            
            # Check Bithumb API status
            if result.get('status') != '0000':
                error_msg = result.get('message', 'Unknown error')
                raise Exception(f"Bithumb API error: {error_msg}")
            
            return result.get('data', result)
            
        except RequestException as e:
            logger.error(f"Bithumb API request failed: {e}")
            raise
    
    def get_trading_pairs(self) -> List[TradingPair]:
        """Get all available trading pairs."""
        if self._trading_pairs_cache:
            return self._trading_pairs_cache
        
        # Get ticker for all currencies
        result = self._request('GET', '/public/ticker/ALL_KRW', auth=False)
        
        pairs = []
        
        for currency, data in result.items():
            if currency in ['date', 'timestamp']:
                continue
            
            pairs.append(TradingPair(
                symbol=f"{currency}_KRW",
                base_currency=currency,
                quote_currency='KRW',
                min_quantity=Decimal('0.0001'),
                max_quantity=Decimal('100000000'),
                quantity_precision=4,
                price_precision=0,
                min_notional=Decimal('1000'),  # Bithumb minimum is 1000 KRW
                is_active=True
            ))
        
        # Also get BTC market pairs
        try:
            result_btc = self._request('GET', '/public/ticker/ALL_BTC', auth=False)
            for currency, data in result_btc.items():
                if currency in ['date', 'timestamp']:
                    continue
                
                pairs.append(TradingPair(
                    symbol=f"{currency}_BTC",
                    base_currency=currency,
                    quote_currency='BTC',
                    min_quantity=Decimal('0.0001'),
                    max_quantity=Decimal('100000'),
                    quantity_precision=4,
                    price_precision=8,
                    min_notional=Decimal('0.0001'),
                    is_active=True
                ))
        except Exception:
            pass  # BTC market may not be available
        
        self._trading_pairs_cache = pairs
        return pairs
    
    def get_account_balance(self) -> AccountBalance:
        """Get account balance for all assets."""
        result = self._request('POST', '/info/balance', params={'currency': 'ALL'})
        
        balances = {}
        
        # Parse balance data
        for key, value in result.items():
            if key.startswith('available_'):
                currency = key.replace('available_', '').upper()
                available = Decimal(str(value))
                
                # Get locked amount
                locked_key = f'total_{currency.lower()}'
                total = Decimal(str(result.get(locked_key, '0')))
                locked = total - available
                
                if available > 0 or locked > 0:
                    balances[currency] = Balance(
                        currency=currency,
                        available=available,
                        locked=max(Decimal('0'), locked)
                    )
        
        return AccountBalance(balances=balances)
    
    def get_order_book(self, symbol: str, levels: int = 5) -> OrderBook:
        """Get order book for a trading pair."""
        # Parse symbol (e.g., "BTC_KRW" -> order_currency=BTC, payment_currency=KRW)
        parts = symbol.split('_')
        if len(parts) != 2:
            raise ValueError(f"Invalid symbol format: {symbol}")
        
        order_currency, payment_currency = parts
        
        result = self._request(
            'GET', 
            f'/public/orderbook/{order_currency}_{payment_currency}',
            auth=False
        )
        
        bids = [
            OrderBookLevel(
                price=Decimal(str(bid['price'])),
                quantity=Decimal(str(bid['quantity']))
            )
            for bid in result.get('bids', [])[:levels]
        ]
        
        asks = [
            OrderBookLevel(
                price=Decimal(str(ask['price'])),
                quantity=Decimal(str(ask['quantity']))
            )
            for ask in result.get('asks', [])[:levels]
        ]
        
        return OrderBook(
            symbol=symbol,
            bids=bids,
            asks=asks,
            timestamp=datetime.fromtimestamp(int(result.get('timestamp', 0)) / 1000)
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
        parts = symbol.split('_')
        if len(parts) != 2:
            raise ValueError(f"Invalid symbol format: {symbol}")
        
        order_currency, payment_currency = parts
        
        # Determine order type
        if side in [OrderSide.BUY, OrderSide.BID]:
            bithumb_type = 'bid'
        else:
            bithumb_type = 'ask'
        
        params = {
            'order_currency': order_currency,
            'payment_currency': payment_currency,
            'units': str(quantity),
            'type': bithumb_type,
        }
        
        if order_type == OrderType.LIMIT and price:
            params['price'] = str(int(price)) if payment_currency == 'KRW' else str(price)
            endpoint = '/trade/place'
        else:
            endpoint = '/trade/market_buy' if bithumb_type == 'bid' else '/trade/market_sell'
        
        result = self._request('POST', endpoint, params=params)
        
        return Order(
            id=str(result.get('order_id', '')),
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            status=OrderStatus.OPEN,
            filled_quantity=Decimal('0'),
            created_at=datetime.utcnow()
        )
    
    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> bool:
        """Cancel an order."""
        if not symbol:
            raise ValueError("Symbol is required for Bithumb order cancellation")
        
        parts = symbol.split('_')
        if len(parts) != 2:
            raise ValueError(f"Invalid symbol format: {symbol}")
        
        order_currency, payment_currency = parts
        
        try:
            self._request('POST', '/trade/cancel', params={
                'type': 'bid',  # Will try both
                'order_id': order_id,
                'order_currency': order_currency,
                'payment_currency': payment_currency
            })
            return True
        except Exception:
            try:
                self._request('POST', '/trade/cancel', params={
                    'type': 'ask',
                    'order_id': order_id,
                    'order_currency': order_currency,
                    'payment_currency': payment_currency
                })
                return True
            except Exception as e:
                logger.error(f"Failed to cancel order {order_id}: {e}")
                return False
    
    def get_order(self, order_id: str, symbol: Optional[str] = None) -> Optional[Order]:
        """Get order details."""
        if not symbol:
            raise ValueError("Symbol is required for Bithumb order query")
        
        parts = symbol.split('_')
        if len(parts) != 2:
            raise ValueError(f"Invalid symbol format: {symbol}")
        
        order_currency, payment_currency = parts
        
        try:
            result = self._request('POST', '/info/order_detail', params={
                'order_id': order_id,
                'order_currency': order_currency,
                'payment_currency': payment_currency
            })
            
            if not result:
                return None
            
            order_data = result[0] if isinstance(result, list) else result
            
            side = OrderSide.BUY if order_data.get('type') == 'bid' else OrderSide.SELL
            
            return Order(
                id=order_id,
                symbol=symbol,
                side=side,
                order_type=OrderType.LIMIT,
                quantity=Decimal(str(order_data.get('units', '0'))),
                price=Decimal(str(order_data.get('price', '0'))),
                status=self._map_order_status(order_data.get('order_status', '')),
                filled_quantity=Decimal(str(order_data.get('units_remaining', '0'))),
                created_at=datetime.fromtimestamp(
                    int(order_data.get('order_date', 0)) / 1000
                )
            )
        except Exception as e:
            logger.error(f"Failed to get order {order_id}: {e}")
            return None
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get all open orders."""
        if not symbol:
            # Get for all currencies - need to iterate
            pairs = self.get_trading_pairs()
            all_orders = []
            for pair in pairs[:20]:  # Limit to avoid too many API calls
                try:
                    orders = self.get_open_orders(pair.symbol)
                    all_orders.extend(orders)
                except Exception:
                    continue
            return all_orders
        
        parts = symbol.split('_')
        if len(parts) != 2:
            raise ValueError(f"Invalid symbol format: {symbol}")
        
        order_currency, payment_currency = parts
        
        orders = []
        
        for order_type in ['bid', 'ask']:
            try:
                result = self._request('POST', '/info/orders', params={
                    'order_currency': order_currency,
                    'payment_currency': payment_currency,
                    'type': order_type
                })
                
                if not result:
                    continue
                
                for order_data in result:
                    side = OrderSide.BUY if order_type == 'bid' else OrderSide.SELL
                    
                    orders.append(Order(
                        id=str(order_data.get('order_id', '')),
                        symbol=symbol,
                        side=side,
                        order_type=OrderType.LIMIT,
                        quantity=Decimal(str(order_data.get('units', '0'))),
                        price=Decimal(str(order_data.get('price', '0'))),
                        status=OrderStatus.OPEN,
                        filled_quantity=Decimal('0'),
                        created_at=datetime.fromtimestamp(
                            int(order_data.get('order_date', 0)) / 1000
                        )
                    ))
            except Exception as e:
                logger.warning(f"Failed to get {order_type} orders for {symbol}: {e}")
        
        return orders
    
    def get_all_tickers(self) -> Dict[str, PriceData]:
        """Get current prices for all trading pairs."""
        result = self._request('GET', '/public/ticker/ALL_KRW', auth=False)
        
        tickers = {}
        timestamp = datetime.fromtimestamp(int(result.get('date', 0)) / 1000)
        
        for currency, data in result.items():
            if currency in ['date', 'timestamp']:
                continue
            
            symbol = f"{currency}_KRW"
            tickers[symbol] = PriceData(
                symbol=symbol,
                price=Decimal(str(data.get('closing_price', '0'))),
                timestamp=timestamp
            )
        
        # Also try BTC market
        try:
            result_btc = self._request('GET', '/public/ticker/ALL_BTC', auth=False)
            for currency, data in result_btc.items():
                if currency in ['date', 'timestamp']:
                    continue
                
                symbol = f"{currency}_BTC"
                tickers[symbol] = PriceData(
                    symbol=symbol,
                    price=Decimal(str(data.get('closing_price', '0'))),
                    timestamp=timestamp
                )
        except Exception:
            pass
        
        return tickers
    
    def get_historical_candles(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 200
    ) -> List[Dict]:
        """Get historical candlestick data."""
        parts = symbol.split('_')
        if len(parts) != 2:
            raise ValueError(f"Invalid symbol format: {symbol}")
        
        order_currency, payment_currency = parts
        
        # Map interval to Bithumb format
        interval_map = {
            '1m': '1m',
            '3m': '3m',
            '5m': '5m',
            '10m': '10m',
            '30m': '30m',
            '1h': '1h',
            '6h': '6h',
            '12h': '12h',
            '1d': '24h',
        }
        
        bithumb_interval = interval_map.get(interval, '24h')
        
        result = self._request(
            'GET',
            f'/public/candlestick/{order_currency}_{payment_currency}/{bithumb_interval}',
            auth=False
        )
        
        candles = []
        for candle in result[-limit:]:
            candles.append({
                'timestamp': datetime.fromtimestamp(candle[0] / 1000).isoformat(),
                'open': float(candle[1]),
                'close': float(candle[2]),
                'high': float(candle[3]),
                'low': float(candle[4]),
                'volume': float(candle[5])
            })
        
        return candles
    
    def _map_order_status(self, bithumb_status: str) -> OrderStatus:
        """Map Bithumb order status to internal status."""
        status_map = {
            'placed': OrderStatus.OPEN,
            'pending': OrderStatus.OPEN,
            'completed': OrderStatus.FILLED,
            'cancel': OrderStatus.CANCELLED,
        }
        return status_map.get(bithumb_status.lower(), OrderStatus.PENDING)
