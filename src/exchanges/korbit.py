"""
Korbit exchange adapter.
"""
import logging
import time
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


class KorbitExchange(BaseExchange):
    """
    Korbit exchange adapter.
    
    Implements the BaseExchange interface for Korbit API.
    """
    
    BASE_URL = "https://api.korbit.co.kr"
    
    def __init__(self, access_key: str, secret_key: str):
        super().__init__(access_key, secret_key)
        self._access_token = None
        self._token_expires = 0
        self._trading_pairs_cache = None
    
    @property
    def exchange_type(self) -> ExchangeType:
        return ExchangeType.KORBIT
    
    @property
    def quote_currencies(self) -> List[str]:
        return ['KRW']
    
    def _get_access_token(self) -> str:
        """Get or refresh access token."""
        current_time = time.time()
        
        if self._access_token and current_time < self._token_expires:
            return self._access_token
        
        # Request new token
        data = {
            'client_id': self.access_key,
            'client_secret': self.secret_key,
            'grant_type': 'client_credentials'
        }
        
        try:
            response = requests.post(
                f"{self.BASE_URL}/v1/oauth2/access_token",
                data=data,
                timeout=10
            )
            response.raise_for_status()
            result = response.json()
            
            self._access_token = result['access_token']
            self._token_expires = current_time + result['expires_in'] - 60
            
            return self._access_token
            
        except RequestException as e:
            logger.error(f"Failed to get Korbit access token: {e}")
            raise
    
    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        auth: bool = True
    ) -> Dict:
        """Make a request to the Korbit API."""
        url = f"{self.BASE_URL}{endpoint}"
        headers = {}
        
        if auth:
            token = self._get_access_token()
            headers['Authorization'] = f'Bearer {token}'
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=10)
            elif method == 'POST':
                response = requests.post(url, headers=headers, data=data, timeout=10)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response.json()
            
        except RequestException as e:
            logger.error(f"Korbit API request failed: {e}")
            raise
    
    def get_trading_pairs(self) -> List[TradingPair]:
        """Get all available trading pairs."""
        if self._trading_pairs_cache:
            return self._trading_pairs_cache
        
        # Korbit has a fixed set of pairs
        symbols = [
            'btc_krw', 'eth_krw', 'etc_krw', 'xrp_krw',
            'bch_krw', 'ltc_krw', 'eos_krw', 'xlm_krw',
            'trx_krw', 'ada_krw', 'bat_krw', 'zil_krw',
            'link_krw', 'sol_krw', 'dot_krw', 'matic_krw'
        ]
        
        pairs = []
        for symbol in symbols:
            base = symbol.split('_')[0].upper()
            pairs.append(TradingPair(
                symbol=symbol,
                base_currency=base,
                quote_currency='KRW',
                min_quantity=Decimal('0.0001'),
                max_quantity=Decimal('100000'),
                quantity_precision=4,
                price_precision=0,
                min_notional=Decimal('5000'),
                is_active=True
            ))
        
        self._trading_pairs_cache = pairs
        return pairs
    
    def get_account_balance(self) -> AccountBalance:
        """Get account balance for all assets."""
        result = self._request('GET', '/v1/user/balances')
        balances = {}
        
        for currency, data in result.items():
            available = Decimal(str(data.get('available', '0')))
            trade_in_use = Decimal(str(data.get('trade_in_use', '0')))
            
            if available > 0 or trade_in_use > 0:
                balances[currency.upper()] = Balance(
                    currency=currency.upper(),
                    available=available,
                    locked=trade_in_use
                )
        
        return AccountBalance(balances=balances)
    
    def get_order_book(self, symbol: str, levels: int = 5) -> OrderBook:
        """Get order book for a trading pair."""
        result = self._request(
            'GET', '/v1/orderbook',
            params={'currency_pair': symbol},
            auth=False
        )
        
        bids = [
            OrderBookLevel(
                price=Decimal(str(bid[0])),
                quantity=Decimal(str(bid[1]))
            )
            for bid in result.get('bids', [])[:levels]
        ]
        
        asks = [
            OrderBookLevel(
                price=Decimal(str(ask[0])),
                quantity=Decimal(str(ask[1]))
            )
            for ask in result.get('asks', [])[:levels]
        ]
        
        return OrderBook(
            symbol=symbol,
            bids=bids,
            asks=asks,
            timestamp=datetime.fromtimestamp(result['timestamp'] / 1000)
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
        if side in [OrderSide.BUY, OrderSide.BID]:
            endpoint = '/v1/user/orders/buy'
        else:
            endpoint = '/v1/user/orders/sell'
        
        data = {
            'currency_pair': symbol,
            'type': 'limit' if order_type == OrderType.LIMIT else 'market',
            'price': str(int(price)) if price else None,
            'coin_amount': str(quantity)
        }
        
        # Remove None values
        data = {k: v for k, v in data.items() if v is not None}
        
        result = self._request('POST', endpoint, data=data)
        
        return Order(
            id=str(result['orderId']),
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
            raise ValueError("Symbol is required for Korbit order cancellation")
        
        try:
            self._request(
                'POST', '/v1/user/orders/cancel',
                data={'currency_pair': symbol, 'id': order_id}
            )
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False
    
    def get_order(self, order_id: str, symbol: Optional[str] = None) -> Optional[Order]:
        """Get order details."""
        if not symbol:
            raise ValueError("Symbol is required for Korbit order query")
        
        try:
            orders = self._request(
                'GET', '/v1/user/orders',
                params={'currency_pair': symbol, 'id': order_id}
            )
            
            if not orders:
                return None
            
            result = orders[0] if isinstance(orders, list) else orders
            
            side = OrderSide.BUY if result['type'] == 'bid' else OrderSide.SELL
            
            return Order(
                id=str(result['id']),
                symbol=symbol,
                side=side,
                order_type=OrderType.LIMIT,
                quantity=Decimal(str(result['total'])),
                price=Decimal(str(result['price'])),
                status=self._map_order_status(result['status']),
                filled_quantity=Decimal(str(result.get('filled_total', '0'))),
                created_at=datetime.fromtimestamp(result['created_at'] / 1000)
            )
        except Exception as e:
            logger.error(f"Failed to get order {order_id}: {e}")
            return None
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get all open orders."""
        params = {'status': 'unfilled'}
        if symbol:
            params['currency_pair'] = symbol
        
        results = self._request('GET', '/v1/user/orders/open', params=params)
        orders = []
        
        for result in results:
            side = OrderSide.BUY if result['type'] == 'bid' else OrderSide.SELL
            
            orders.append(Order(
                id=str(result['id']),
                symbol=result['currency_pair'],
                side=side,
                order_type=OrderType.LIMIT,
                quantity=Decimal(str(result['total'])),
                price=Decimal(str(result['price'])),
                status=OrderStatus.OPEN,
                filled_quantity=Decimal(str(result.get('filled_total', '0'))),
                created_at=datetime.fromtimestamp(result['created_at'] / 1000)
            ))
        
        return orders
    
    def get_all_tickers(self) -> Dict[str, PriceData]:
        """Get current prices for all trading pairs."""
        result = self._request('GET', '/v1/ticker/detailed/all', auth=False)
        
        tickers = {}
        now = datetime.utcnow()
        
        for symbol, data in result.items():
            if symbol == 'timestamp':
                continue
            tickers[symbol] = PriceData(
                symbol=symbol,
                price=Decimal(str(data['last'])),
                timestamp=now
            )
        
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
        # Map interval to Korbit format
        interval_map = {
            '1m': '1',
            '3m': '3',
            '5m': '5',
            '15m': '15',
            '30m': '30',
            '1h': '60',
            '4h': '240',
            '1d': '1440',
        }
        
        params = {
            'currency_pair': symbol,
            'time': interval_map.get(interval, '1440')
        }
        
        result = self._request('GET', '/v1/ticker/detailed', params=params, auth=False)
        
        # Korbit doesn't have a full candle endpoint, return current data
        return [{
            'timestamp': datetime.fromtimestamp(result['timestamp'] / 1000).isoformat(),
            'open': float(result['open']),
            'high': float(result['high']),
            'low': float(result['low']),
            'close': float(result['last']),
            'volume': float(result['volume'])
        }]
    
    def _map_order_status(self, korbit_status: str) -> OrderStatus:
        """Map Korbit order status to internal status."""
        status_map = {
            'unfilled': OrderStatus.OPEN,
            'partially_filled': OrderStatus.PARTIALLY_FILLED,
            'filled': OrderStatus.FILLED,
            'cancelled': OrderStatus.CANCELLED,
        }
        return status_map.get(korbit_status, OrderStatus.PENDING)
