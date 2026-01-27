#!/usr/bin/env python3
"""
Cryptocurrency Arbitrage Opportunity Scanner

Scans for:
1. Triangle Arbitrage - within same exchange (e.g., KRW→BTC→ETH→KRW)
2. Cross-Market Spread - between different quote markets (e.g., KRW vs USDT market)

Supports: Upbit, Binance
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from itertools import permutations

import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class ArbitrageOpportunity:
    """Represents an arbitrage opportunity."""
    exchange: str
    type: str  # 'triangle' or 'spread'
    path: List[str]
    profit_rate: Decimal
    profit_amount: Decimal
    details: str
    timestamp: datetime


class UpbitClient:
    """Simple Upbit API client for public endpoints."""
    
    BASE_URL = "https://api.upbit.com/v1"
    
    def __init__(self):
        self.session = requests.Session()
        self._ticker_cache = {}
        self._cache_time = 0
        self._cache_ttl = 1  # 1 second cache
    
    def get_markets(self) -> List[Dict]:
        """Get all available markets."""
        resp = self.session.get(f"{self.BASE_URL}/market/all")
        resp.raise_for_status()
        return resp.json()
    
    def get_tickers(self, markets: List[str]) -> Dict[str, Dict]:
        """Get ticker data for multiple markets."""
        now = time.time()
        if now - self._cache_time < self._cache_ttl and self._ticker_cache:
            return self._ticker_cache
        
        # Upbit allows up to 100 markets per request
        result = {}
        for i in range(0, len(markets), 100):
            batch = markets[i:i+100]
            resp = self.session.get(
                f"{self.BASE_URL}/ticker",
                params={"markets": ",".join(batch)}
            )
            resp.raise_for_status()
            for ticker in resp.json():
                # Calculate 24h volume in quote currency
                vol_quote = Decimal(str(ticker['acc_trade_price_24h']))
                result[ticker['market']] = {
                    'price': Decimal(str(ticker['trade_price'])),
                    'bid': Decimal(str(ticker['trade_price'])),
                    'ask': Decimal(str(ticker['trade_price'])),
                    'volume': vol_quote  # Use quote volume for filtering
                }
            time.sleep(0.1)  # Rate limit delay
        
        self._ticker_cache = result
        self._cache_time = now
        return result
    
    def get_orderbook(self, market: str) -> Dict:
        """Get orderbook for a market."""
        resp = self.session.get(
            f"{self.BASE_URL}/orderbook",
            params={"markets": market}
        )
        resp.raise_for_status()
        data = resp.json()[0]
        return {
            'bid': Decimal(str(data['orderbook_units'][0]['bid_price'])),
            'ask': Decimal(str(data['orderbook_units'][0]['ask_price'])),
            'bid_size': Decimal(str(data['orderbook_units'][0]['bid_size'])),
            'ask_size': Decimal(str(data['orderbook_units'][0]['ask_size']))
        }


class BinanceClient:
    """Simple Binance API client for public endpoints."""
    
    BASE_URL = "https://api.binance.com/api/v3"
    
    def __init__(self):
        self.session = requests.Session()
        self._ticker_cache = {}
        self._cache_time = 0
        self._cache_ttl = 1
    
    def get_exchange_info(self) -> Dict:
        """Get exchange information including all symbols."""
        resp = self.session.get(f"{self.BASE_URL}/exchangeInfo")
        resp.raise_for_status()
        return resp.json()
    
    def get_all_tickers(self) -> Dict[str, Dict]:
        """Get all ticker prices."""
        now = time.time()
        if now - self._cache_time < self._cache_ttl and self._ticker_cache:
            return self._ticker_cache
        
        resp = self.session.get(f"{self.BASE_URL}/ticker/24hr")
        resp.raise_for_status()
        
        result = {}
        for ticker in resp.json():
            result[ticker['symbol']] = {
                'price': Decimal(ticker['lastPrice']),
                'bid': Decimal(ticker['bidPrice']),
                'ask': Decimal(ticker['askPrice']),
                'volume': Decimal(ticker['volume'])
            }
        
        self._ticker_cache = result
        self._cache_time = now
        return result
    
    def get_orderbook(self, symbol: str, limit: int = 5) -> Dict:
        """Get orderbook for a symbol."""
        resp = self.session.get(
            f"{self.BASE_URL}/depth",
            params={"symbol": symbol, "limit": limit}
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            'bid': Decimal(data['bids'][0][0]) if data['bids'] else Decimal('0'),
            'ask': Decimal(data['asks'][0][0]) if data['asks'] else Decimal('0'),
            'bid_size': Decimal(data['bids'][0][1]) if data['bids'] else Decimal('0'),
            'ask_size': Decimal(data['asks'][0][1]) if data['asks'] else Decimal('0')
        }


class TriangleArbitrageScanner:
    """Scans for triangle arbitrage opportunities within an exchange."""
    
    def __init__(
        self, 
        exchange: str, 
        fee_rate: Decimal = Decimal('0.001'),
        min_volume: Decimal = Decimal('100000')  # Minimum 24h volume
    ):
        self.exchange = exchange
        self.fee_rate = fee_rate
        self.fee_multiplier = Decimal('1') - fee_rate
        self.min_volume = min_volume
        
        if exchange == 'upbit':
            self.client = UpbitClient()
            self.quote_currencies = ['KRW', 'BTC', 'USDT']
        else:  # binance
            self.client = BinanceClient()
            self.quote_currencies = ['USDT', 'BTC', 'ETH', 'BNB']
    
    def _parse_symbol(self, symbol: str) -> Tuple[str, str]:
        """Parse symbol into base and quote currency."""
        if self.exchange == 'upbit':
            # Format: KRW-BTC, BTC-ETH
            parts = symbol.split('-')
            return parts[1], parts[0]  # base, quote
        else:
            # Binance format: BTCUSDT, ETHBTC
            for quote in self.quote_currencies:
                if symbol.endswith(quote):
                    base = symbol[:-len(quote)]
                    return base, quote
            return None, None
    
    def _build_symbol(self, base: str, quote: str) -> str:
        """Build symbol from base and quote."""
        if self.exchange == 'upbit':
            return f"{quote}-{base}"
        else:
            return f"{base}{quote}"
    
    def find_triangles(self) -> List[Tuple[str, str, str]]:
        """Find all possible triangle paths."""
        if self.exchange == 'upbit':
            markets = self.client.get_markets()
            pairs = {}
            for m in markets:
                symbol = m['market']
                base, quote = self._parse_symbol(symbol)
                if base and quote:
                    if quote not in pairs:
                        pairs[quote] = set()
                    pairs[quote].add(base)
        else:
            info = self.client.get_exchange_info()
            pairs = {}
            for s in info['symbols']:
                if s['status'] != 'TRADING':
                    continue
                base, quote = s['baseAsset'], s['quoteAsset']
                if quote not in pairs:
                    pairs[quote] = set()
                pairs[quote].add(base)
        
        triangles = []
        
        # Find triangles: A → B → C → A
        for start_quote in self.quote_currencies:
            if start_quote not in pairs:
                continue
            
            for mid_base in pairs.get(start_quote, []):
                # mid_base is also a quote currency?
                if mid_base not in pairs:
                    continue
                
                for end_base in pairs.get(mid_base, []):
                    # Can we get back to start_quote?
                    if end_base in pairs.get(start_quote, []):
                        triangles.append((start_quote, mid_base, end_base))
        
        return triangles
    
    def calculate_profit(
        self, 
        path: Tuple[str, str, str],
        tickers: Dict[str, Dict],
        initial_amount: Decimal = Decimal('1000000')
    ) -> Optional[ArbitrageOpportunity]:
        """Calculate profit for a triangle path."""
        start, mid, end = path
        
        # Build symbols
        sym1 = self._build_symbol(mid, start)   # Buy mid with start
        sym2 = self._build_symbol(end, mid)     # Buy end with mid
        sym3 = self._build_symbol(end, start)   # Sell end for start
        
        if sym1 not in tickers or sym2 not in tickers or sym3 not in tickers:
            return None
        
        # Check minimum volume (filter out illiquid markets)
        for sym in [sym1, sym2, sym3]:
            vol = tickers[sym].get('volume', Decimal('0'))
            if vol < self.min_volume:
                return None
        
        # Get prices (use ask for buy, bid for sell)
        price1 = tickers[sym1]['ask'] or tickers[sym1]['price']
        price2 = tickers[sym2]['ask'] or tickers[sym2]['price']
        price3 = tickers[sym3]['bid'] or tickers[sym3]['price']
        
        if price1 <= 0 or price2 <= 0 or price3 <= 0:
            return None
        
        # Calculate: start → mid → end → start
        # Step 1: Buy mid with start
        mid_amount = (initial_amount / price1) * self.fee_multiplier
        
        # Step 2: Buy end with mid
        end_amount = (mid_amount / price2) * self.fee_multiplier
        
        # Step 3: Sell end for start
        final_amount = (end_amount * price3) * self.fee_multiplier
        
        profit = final_amount - initial_amount
        profit_rate = (profit / initial_amount) * 100
        
        # Filter unrealistic profits (> 5% is suspicious)
        if profit_rate > Decimal('5'):
            return None
        
        if profit_rate > Decimal('0.01'):  # > 0.01% profit threshold
            return ArbitrageOpportunity(
                exchange=self.exchange.upper(),
                type='triangle',
                path=[start, mid, end, start],
                profit_rate=profit_rate,
                profit_amount=profit,
                details=f"{start}→{mid}({sym1})→{end}({sym2})→{start}({sym3})",
                timestamp=datetime.now()
            )
        
        return None
    
    def scan(self, initial_amount: Decimal = Decimal('1000000')) -> List[ArbitrageOpportunity]:
        """Scan for all triangle arbitrage opportunities."""
        opportunities = []
        
        triangles = self.find_triangles()
        logger.info(f"[{self.exchange.upper()}] Found {len(triangles)} potential triangle paths")
        
        if self.exchange == 'upbit':
            # Get all market symbols
            markets = self.client.get_markets()
            symbols = [m['market'] for m in markets]
            tickers = self.client.get_tickers(symbols)
        else:
            tickers = self.client.get_all_tickers()
        
        for path in triangles:
            opp = self.calculate_profit(path, tickers, initial_amount)
            if opp:
                opportunities.append(opp)
        
        return sorted(opportunities, key=lambda x: x.profit_rate, reverse=True)


class CrossMarketSpreadScanner:
    """Scans for spread opportunities between different quote markets."""
    
    def __init__(
        self, 
        exchange: str, 
        fee_rate: Decimal = Decimal('0.001'),
        min_volume: Decimal = Decimal('100000')
    ):
        self.exchange = exchange
        self.fee_rate = fee_rate
        self.fee_multiplier = Decimal('1') - fee_rate
        self.min_volume = min_volume
        
        if exchange == 'upbit':
            self.client = UpbitClient()
            self.quote_currencies = ['KRW', 'BTC', 'USDT']
        else:
            self.client = BinanceClient()
            self.quote_currencies = ['USDT', 'BTC', 'ETH', 'BNB']
    
    def _parse_symbol(self, symbol: str) -> Tuple[str, str]:
        """Parse symbol into base and quote currency."""
        if self.exchange == 'upbit':
            parts = symbol.split('-')
            return parts[1], parts[0]
        else:
            for quote in self.quote_currencies:
                if symbol.endswith(quote):
                    base = symbol[:-len(quote)]
                    return base, quote
            return None, None
    
    def _build_symbol(self, base: str, quote: str) -> str:
        """Build symbol from base and quote."""
        if self.exchange == 'upbit':
            return f"{quote}-{base}"
        else:
            return f"{base}{quote}"
    
    def scan(self, initial_amount: Decimal = Decimal('1000000')) -> List[ArbitrageOpportunity]:
        """
        Scan for cross-market spread opportunities.
        
        Example: If KRW-ETH and BTC-ETH both exist, and KRW-BTC exists:
        - Calculate ETH price in KRW via direct market
        - Calculate ETH price in KRW via BTC market (KRW→BTC→ETH)
        - Compare and find spread
        """
        opportunities = []
        
        if self.exchange == 'upbit':
            markets = self.client.get_markets()
            symbols = [m['market'] for m in markets]
            tickers = self.client.get_tickers(symbols)
        else:
            tickers = self.client.get_all_tickers()
        
        # Build currency→markets map
        base_markets = {}  # base_currency -> {quote: price}
        for symbol, data in tickers.items():
            base, quote = self._parse_symbol(symbol)
            if base and quote:
                if base not in base_markets:
                    base_markets[base] = {}
                base_markets[base][quote] = data
        
        # Find cross rates
        primary_quote = 'KRW' if self.exchange == 'upbit' else 'USDT'
        
        for base, markets in base_markets.items():
            if len(markets) < 2:
                continue
            
            # Get direct price in primary quote
            if primary_quote not in markets:
                continue
            
            direct_price = markets[primary_quote]['price']
            
            # Check volume for direct market
            direct_vol = markets[primary_quote].get('volume', Decimal('0'))
            if direct_vol < self.min_volume:
                continue
            
            # Check indirect prices via other quote currencies
            for intermediate_quote, intermediate_data in markets.items():
                if intermediate_quote == primary_quote:
                    continue
                
                # Check volume for intermediate market
                inter_vol = intermediate_data.get('volume', Decimal('0'))
                if inter_vol < self.min_volume:
                    continue
                
                # Need intermediate_quote/primary_quote rate
                bridge_symbol = self._build_symbol(intermediate_quote, primary_quote)
                if bridge_symbol not in tickers:
                    continue
                
                # Check volume for bridge market
                bridge_vol = tickers[bridge_symbol].get('volume', Decimal('0'))
                if bridge_vol < self.min_volume:
                    continue
                
                bridge_price = tickers[bridge_symbol]['price']
                
                # Calculate indirect price
                # base/intermediate × intermediate/primary = base/primary (implied)
                indirect_price = intermediate_data['price'] * bridge_price
                
                if direct_price <= 0 or indirect_price <= 0:
                    continue
                
                # Calculate spread
                spread = ((direct_price - indirect_price) / indirect_price) * 100
                
                # Filter unrealistic spreads (> 5% is suspicious)
                if abs(spread) > Decimal('5'):
                    continue
                
                # Account for fees (2 trades for indirect vs 1 for direct)
                fee_adjusted_spread = abs(spread) - (self.fee_rate * 100 * 2)
                
                if fee_adjusted_spread > Decimal('0.05'):  # > 0.05% after fees
                    if spread > 0:
                        # Direct is more expensive → sell direct, buy indirect
                        action = f"Sell {base} on {primary_quote} market, Buy via {intermediate_quote}"
                    else:
                        # Indirect is more expensive → buy direct, sell indirect
                        action = f"Buy {base} on {primary_quote} market, Sell via {intermediate_quote}"
                    
                    opportunities.append(ArbitrageOpportunity(
                        exchange=self.exchange.upper(),
                        type='spread',
                        path=[base, primary_quote, intermediate_quote],
                        profit_rate=Decimal(str(abs(spread))),
                        profit_amount=(abs(spread) / 100) * initial_amount,
                        details=f"{base}: Direct({primary_quote})={direct_price:.2f}, "
                               f"Indirect({intermediate_quote})={indirect_price:.2f}, "
                               f"Spread={spread:.3f}% | {action}",
                        timestamp=datetime.now()
                    ))
        
        return sorted(opportunities, key=lambda x: x.profit_rate, reverse=True)


class ArbitrageBot:
    """Main arbitrage scanning bot."""
    
    def __init__(
        self, 
        exchanges: List[str] = None, 
        initial_amount: Decimal = Decimal('1000000'),
        min_volume: Decimal = Decimal('10000')  # 10K minimum volume
    ):
        self.exchanges = exchanges or ['upbit', 'binance']
        self.initial_amount = initial_amount
        self.min_volume = min_volume
        
        self.triangle_scanners = {}
        self.spread_scanners = {}
        
        for ex in self.exchanges:
            fee = Decimal('0.0005') if ex == 'upbit' else Decimal('0.001')
            self.triangle_scanners[ex] = TriangleArbitrageScanner(ex, fee, min_volume)
            self.spread_scanners[ex] = CrossMarketSpreadScanner(ex, fee, min_volume)
    
    def scan_all(self) -> Dict[str, List[ArbitrageOpportunity]]:
        """Scan all exchanges for arbitrage opportunities."""
        results = {
            'triangle': [],
            'spread': []
        }
        
        for ex in self.exchanges:
            try:
                logger.info(f"Scanning {ex.upper()} for triangle arbitrage...")
                triangle_opps = self.triangle_scanners[ex].scan(self.initial_amount)
                results['triangle'].extend(triangle_opps)
                logger.info(f"  Found {len(triangle_opps)} opportunities")
                
                # Small delay between scans to avoid rate limits
                time.sleep(0.5)
                
                logger.info(f"Scanning {ex.upper()} for cross-market spread...")
                spread_opps = self.spread_scanners[ex].scan(self.initial_amount)
                results['spread'].extend(spread_opps)
                logger.info(f"  Found {len(spread_opps)} opportunities")
                
                # Delay between exchanges
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error scanning {ex}: {e}")
                time.sleep(2)  # Extra delay on error
        
        # Sort by profit rate
        results['triangle'] = sorted(results['triangle'], key=lambda x: x.profit_rate, reverse=True)
        results['spread'] = sorted(results['spread'], key=lambda x: x.profit_rate, reverse=True)
        
        return results
    
    def print_opportunities(self, results: Dict[str, List[ArbitrageOpportunity]], top_n: int = 10):
        """Print arbitrage opportunities."""
        print("\n" + "=" * 80)
        print(f" ARBITRAGE OPPORTUNITIES - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f" Initial Amount: {self.initial_amount:,.0f}")
        print("=" * 80)
        
        # Triangle Arbitrage
        print("\n[TRIANGLE ARBITRAGE]")
        print("-" * 80)
        if results['triangle']:
            for i, opp in enumerate(results['triangle'][:top_n], 1):
                print(f"{i:2}. [{opp.exchange}] {' → '.join(opp.path)}")
                print(f"    Profit: {opp.profit_rate:.4f}% ({opp.profit_amount:,.0f})")
                print(f"    Path: {opp.details}")
                print()
        else:
            print("   No profitable triangle arbitrage found.")
        
        # Cross-Market Spread
        print("\n[CROSS-MARKET SPREAD]")
        print("-" * 80)
        if results['spread']:
            for i, opp in enumerate(results['spread'][:top_n], 1):
                print(f"{i:2}. [{opp.exchange}] {opp.path[0]} ({opp.path[1]} vs {opp.path[2]})")
                print(f"    Spread: {opp.profit_rate:.4f}% ({opp.profit_amount:,.0f})")
                print(f"    {opp.details}")
                print()
        else:
            print("   No profitable spread arbitrage found.")
        
        print("=" * 80)
    
    def run_continuous(self, interval: int = 5, top_n: int = 10):
        """Run continuous scanning."""
        print(f"\nStarting continuous arbitrage scan (interval: {interval}s)")
        print("Press Ctrl+C to stop\n")
        
        try:
            while True:
                results = self.scan_all()
                self.print_opportunities(results, top_n)
                
                # Summary
                total_triangle = len(results['triangle'])
                total_spread = len(results['spread'])
                
                if total_triangle > 0:
                    best_tri = results['triangle'][0]
                    print(f"Best Triangle: {best_tri.exchange} {best_tri.profit_rate:.4f}%")
                
                if total_spread > 0:
                    best_spread = results['spread'][0]
                    print(f"Best Spread: {best_spread.exchange} {best_spread.profit_rate:.4f}%")
                
                print(f"\nNext scan in {interval} seconds...")
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n\nStopped by user.")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Cryptocurrency Arbitrage Scanner')
    parser.add_argument(
        '--exchanges', '-e',
        nargs='+',
        default=['upbit', 'binance'],
        choices=['upbit', 'binance'],
        help='Exchanges to scan'
    )
    parser.add_argument(
        '--amount', '-a',
        type=float,
        default=1000000,
        help='Initial amount for calculation (default: 1,000,000)'
    )
    parser.add_argument(
        '--interval', '-i',
        type=int,
        default=10,
        help='Scan interval in seconds (default: 10)'
    )
    parser.add_argument(
        '--top', '-t',
        type=int,
        default=10,
        help='Number of top opportunities to show (default: 10)'
    )
    parser.add_argument(
        '--once',
        action='store_true',
        help='Run once and exit'
    )
    
    args = parser.parse_args()
    
    bot = ArbitrageBot(
        exchanges=args.exchanges,
        initial_amount=Decimal(str(args.amount))
    )
    
    if args.once:
        results = bot.scan_all()
        bot.print_opportunities(results, args.top)
    else:
        bot.run_continuous(interval=args.interval, top_n=args.top)


if __name__ == '__main__':
    main()
