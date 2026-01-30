"""
Upbit exchange adapter.
"""
import logging
import hashlib
import uuid
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime
from urllib.parse import urlencode

import jwt
import requests
from requests.exceptions import RequestException

from src.core.models import (
    ExchangeType, OrderSide, OrderType, OrderStatus,
    Balance, AccountBalance, OrderBook, OrderBookLevel, Order,
    TradingPair, PriceData
)
from src.exchanges.base import BaseExchange
from src.config.settings import settings

logger = logging.getLogger(__name__)


class UpbitExchange(BaseExchange):
    """
    Upbit exchange adapter.
    
    Implements the BaseExchange interface for Upbit API.
    Supports multiple markets: KRW, BTC, USDT.
    """
    
    BASE_URL = "https://api.upbit.com/v1"
    
    # Market priority for trading (prefer lower fee markets)
    MARKET_PRIORITY = ['KRW', 'USDT', 'BTC']
    
    # Fee rates by market
    MARKET_FEES = {
        'KRW': 0.0005,   # 0.05%
        'BTC': 0.0025,   # 0.25%
        'USDT': 0.0025,  # 0.25%
    }
    
    def __init__(self, access_key: str, secret_key: str):
        super().__init__(access_key, secret_key)
        self._trading_pairs_cache = None
    
    def get_symbol(self, base_currency: str, quote_currency: str) -> str:
        """Generate Upbit symbol from base and quote currencies."""
        return f"{quote_currency}-{base_currency}"
    
    def parse_symbol(self, symbol: str) -> tuple[str, str]:
        """Parse Upbit symbol into (base_currency, quote_currency)."""
        parts = symbol.split('-')
        if len(parts) != 2:
            raise ValueError(f"Invalid Upbit symbol: {symbol}")
        return parts[1], parts[0]  # base, quote
    
    def get_trading_pairs_by_market(self, quote_currency: str) -> List[TradingPair]:
        """Get trading pairs for a specific market."""
        all_pairs = self.get_trading_pairs()
        return [p for p in all_pairs if p.quote_currency == quote_currency]
    
    def get_best_market_for_currency(self, base_currency: str) -> Optional[str]:
        """
        Find the best market for a currency based on priority.
        Returns the quote currency of the best available market.
        """
        all_pairs = self.get_trading_pairs()
        available_markets = {
            p.quote_currency for p in all_pairs 
            if p.base_currency == base_currency
        }
        
        # Return first available market based on priority
        for market in self.MARKET_PRIORITY:
            if market in available_markets and market in settings.upbit_markets:
                return market
        return None
    
    def get_fee_rate(self, quote_currency: str) -> float:
        """Get fee rate for a specific market."""
        return self.MARKET_FEES.get(quote_currency, 0.0025)
    
    @property
    def exchange_type(self) -> ExchangeType:
        return ExchangeType.UPBIT
    
    @property
    def quote_currencies(self) -> List[str]:
        """Get enabled quote currencies from settings."""
        return settings.upbit_markets
    
    def _generate_token(self, query_params: Optional[Dict] = None) -> str:
        """Generate JWT token for authentication."""
        payload = {
            'access_key': self.access_key,
            'nonce': str(uuid.uuid4()),
        }
        
        if query_params:
            query_string = urlencode(query_params).encode()
            m = hashlib.sha512()
            m.update(query_string)
            payload['query_hash'] = m.hexdigest()
            payload['query_hash_alg'] = 'SHA512'
        
        return jwt.encode(payload, self.secret_key, algorithm='HS256')
    
    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        auth: bool = True
    ) -> Dict:
        """Make a request to the Upbit API."""
        url = f"{self.BASE_URL}{endpoint}"
        headers = {}
        
        if auth:
            token = self._generate_token(params or data)
            headers['Authorization'] = f'Bearer {token}'
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=10)
            elif method == 'POST':
                response = requests.post(url, headers=headers, json=data, timeout=10)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, params=params, timeout=10)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response.json()
            
        except RequestException as e:
            logger.error(f"Upbit API request failed: {e}")
            raise
    
    def get_trading_pairs(self) -> List[TradingPair]:
        """Get all available trading pairs."""
        if self._trading_pairs_cache:
            return self._trading_pairs_cache
        
        markets = self._request('GET', '/market/all', auth=False)
        pairs = []
        
        for market in markets:
            symbol = market['market']
            parts = symbol.split('-')
            if len(parts) != 2:
                continue
            
            quote_currency, base_currency = parts
            
            # Determine min notional based on quote currency
            if quote_currency == 'KRW':
                min_notional = Decimal('5000')
            elif quote_currency == 'BTC':
                min_notional = Decimal('0.00005')
            elif quote_currency == 'USDT':
                min_notional = Decimal('0.5')
            else:
                min_notional = Decimal('0')
            
            pairs.append(TradingPair(
                symbol=symbol,
                base_currency=base_currency,
                quote_currency=quote_currency,
                min_quantity=Decimal('0.00000001'),
                max_quantity=Decimal('100000000'),
                quantity_precision=8,
                price_precision=8,
                min_notional=min_notional,
                is_active=True
            ))
        
        self._trading_pairs_cache = pairs
        return pairs
    
    def get_account_balance(self) -> AccountBalance:
        """Get account balance for all assets."""
        accounts = self._request('GET', '/accounts')
        balances = {}
        
        for account in accounts:
            currency = account['currency']
            balances[currency] = Balance(
                currency=currency,
                available=Decimal(account['balance']),
                locked=Decimal(account['locked'])
            )
        
        return AccountBalance(balances=balances)
    
    def get_order_book(self, symbol: str, levels: int = 5) -> OrderBook:
        """Get order book for a trading pair."""
        orderbooks = self._request(
            'GET', '/orderbook',
            params={'markets': symbol},
            auth=False
        )
        
        if not orderbooks:
            return OrderBook(symbol=symbol, bids=[], asks=[])
        
        ob = orderbooks[0]
        units = ob.get('orderbook_units', [])[:levels]
        
        bids = [
            OrderBookLevel(
                price=Decimal(str(u['bid_price'])),
                quantity=Decimal(str(u['bid_size']))
            )
            for u in units
        ]
        
        asks = [
            OrderBookLevel(
                price=Decimal(str(u['ask_price'])),
                quantity=Decimal(str(u['ask_size']))
            )
            for u in units
        ]
        
        return OrderBook(
            symbol=symbol,
            bids=bids,
            asks=asks,
            timestamp=datetime.utcnow()
        )
    
    def get_order_books(self, symbols: List[str], levels: int = 5) -> Dict[str, OrderBook]:
        """Get order books for multiple trading pairs."""
        orderbooks = self._request(
            'GET', '/orderbook',
            params={'markets': ','.join(symbols)},
            auth=False
        )
        
        result = {}
        for ob in orderbooks:
            symbol = ob['market']
            units = ob.get('orderbook_units', [])[:levels]
            
            bids = [
                OrderBookLevel(
                    price=Decimal(str(u['bid_price'])),
                    quantity=Decimal(str(u['bid_size']))
                )
                for u in units
            ]
            
            asks = [
                OrderBookLevel(
                    price=Decimal(str(u['ask_price'])),
                    quantity=Decimal(str(u['ask_size']))
                )
                for u in units
            ]
            
            result[symbol] = OrderBook(
                symbol=symbol,
                bids=bids,
                asks=asks,
                timestamp=datetime.utcnow()
            )
        
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
        # Convert side to Upbit format
        if side in [OrderSide.BUY, OrderSide.BID]:
            upbit_side = 'bid'
        else:
            upbit_side = 'ask'
        
        # Determine order type
        if order_type == OrderType.LIMIT:
            ord_type = 'limit'
        else:
            ord_type = 'price' if upbit_side == 'bid' else 'market'
        
        data = {
            'market': symbol,
            'side': upbit_side,
            'ord_type': ord_type,
            'volume': str(quantity),
        }
        
        if order_type == OrderType.LIMIT and price:
            data['price'] = str(price)
        
        result = self._request('POST', '/orders', data=data)
        
        return Order(
            id=result['uuid'],
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            status=self._map_order_status(result['state']),
            filled_quantity=Decimal(result.get('executed_volume', '0')),
            created_at=datetime.fromisoformat(result['created_at'].replace('Z', '+00:00'))
        )
    
    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> bool:
        """Cancel an order."""
        try:
            self._request('DELETE', '/order', params={'uuid': order_id})
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False
    
    def get_order(self, order_id: str, symbol: Optional[str] = None) -> Optional[Order]:
        """Get order details."""
        try:
            result = self._request('GET', '/order', params={'uuid': order_id})
            
            side = OrderSide.BUY if result['side'] == 'bid' else OrderSide.SELL
            order_type = OrderType.LIMIT if result['ord_type'] == 'limit' else OrderType.MARKET
            
            return Order(
                id=result['uuid'],
                symbol=result['market'],
                side=side,
                order_type=order_type,
                quantity=Decimal(result['volume']),
                price=Decimal(result['price']) if result.get('price') else None,
                status=self._map_order_status(result['state']),
                filled_quantity=Decimal(result.get('executed_volume', '0')),
                created_at=datetime.fromisoformat(result['created_at'].replace('Z', '+00:00'))
            )
        except Exception as e:
            logger.error(f"Failed to get order {order_id}: {e}")
            return None
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get all open orders."""
        params = {'state': 'wait'}
        if symbol:
            params['market'] = symbol
        
        results = self._request('GET', '/orders', params=params)
        orders = []
        
        for result in results:
            side = OrderSide.BUY if result['side'] == 'bid' else OrderSide.SELL
            order_type = OrderType.LIMIT if result['ord_type'] == 'limit' else OrderType.MARKET
            
            orders.append(Order(
                id=result['uuid'],
                symbol=result['market'],
                side=side,
                order_type=order_type,
                quantity=Decimal(result['volume']),
                price=Decimal(result['price']) if result.get('price') else None,
                status=self._map_order_status(result['state']),
                filled_quantity=Decimal(result.get('executed_volume', '0')),
                created_at=datetime.fromisoformat(result['created_at'].replace('Z', '+00:00'))
            ))
        
        return orders
    
    def get_all_tickers(self) -> Dict[str, PriceData]:
        """Get current prices for all trading pairs."""
        pairs = self.get_trading_pairs()
        symbols = [p.symbol for p in pairs]
        
        tickers = self._request(
            'GET', '/ticker',
            params={'markets': ','.join(symbols)},
            auth=False
        )
        
        result = {}
        for ticker in tickers:
            symbol = ticker['market']
            result[symbol] = PriceData(
                symbol=symbol,
                price=Decimal(str(ticker['trade_price'])),
                timestamp=datetime.fromtimestamp(ticker['timestamp'] / 1000)
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
        # Map interval to Upbit endpoint
        interval_map = {
            '1d': '/candles/days',
            '1w': '/candles/weeks',
            '1M': '/candles/months',
        }
        
        endpoint = interval_map.get(interval, '/candles/days')
        
        params = {
            'market': symbol,
            'count': min(limit, 200)
        }
        
        if end_time:
            params['to'] = end_time.strftime('%Y-%m-%dT%H:%M:%S')
        
        candles = self._request('GET', endpoint, params=params, auth=False)
        
        return [
            {
                'timestamp': candle['candle_date_time_utc'],
                'open': candle['opening_price'],
                'high': candle['high_price'],
                'low': candle['low_price'],
                'close': candle['trade_price'],
                'volume': candle['candle_acc_trade_volume']
            }
            for candle in candles
        ]
    
    def _map_order_status(self, upbit_status: str) -> OrderStatus:
        """Map Upbit order status to internal status."""
        status_map = {
            'wait': OrderStatus.OPEN,
            'watch': OrderStatus.OPEN,
            'done': OrderStatus.FILLED,
            'cancel': OrderStatus.CANCELLED,
        }
        return status_map.get(upbit_status, OrderStatus.PENDING)
