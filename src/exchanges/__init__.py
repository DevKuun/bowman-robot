# Exchange adapters
from .base import BaseExchange, ExchangeType
from .upbit import UpbitExchange
from .binance import BinanceExchange
from .korbit import KorbitExchange
from .bithumb import BithumbExchange


def get_exchange(
    exchange_type: ExchangeType,
    access_key: str,
    secret_key: str
) -> BaseExchange:
    """
    Factory function to get exchange adapter.
    
    Args:
        exchange_type: Type of exchange
        access_key: API access key
        secret_key: API secret key
        
    Returns:
        Exchange adapter instance
    """
    adapters = {
        ExchangeType.UPBIT: UpbitExchange,
        ExchangeType.BINANCE: BinanceExchange,
        ExchangeType.KORBIT: KorbitExchange,
        ExchangeType.BITHUMB: BithumbExchange,
    }
    
    adapter_class = adapters.get(exchange_type)
    if not adapter_class:
        raise ValueError(f"Unsupported exchange type: {exchange_type}")
    
    return adapter_class(access_key, secret_key)


__all__ = [
    'BaseExchange',
    'ExchangeType',
    'UpbitExchange',
    'BinanceExchange',
    'KorbitExchange',
    'BithumbExchange',
    'get_exchange',
]
