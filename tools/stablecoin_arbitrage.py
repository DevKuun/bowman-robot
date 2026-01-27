#!/usr/bin/env python3
"""
Stablecoin Arbitrage Scanner

Exploits 0% fee stablecoin trading on Binance to find arbitrage opportunities.

Strategy:
1. Stablecoin-to-Stablecoin trades have 0% fee
2. Find price differences across different stablecoin markets
3. Route trades through stablecoins to minimize fees
"""

import time
import requests
from decimal import Decimal
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional


@dataclass
class ArbitrageOpportunity:
    """Represents a stablecoin arbitrage opportunity."""
    asset: str
    buy_market: str      # e.g., 'USDC'
    sell_market: str     # e.g., 'USDT'
    buy_price: float
    sell_price: float
    spread_pct: float
    net_profit_pct: float
    path: str
    volume: float


class BinanceClient:
    """Simple Binance API client."""
    
    BASE_URL = "https://api.binance.com/api/v3"
    
    # Zero-fee stablecoin pairs
    ZERO_FEE_STABLES = {'USDT', 'USDC', 'TUSD', 'FDUSD', 'USDP'}
    
    def __init__(self):
        self.session = requests.Session()
        self._book_cache = {}
        self._cache_time = 0
        
    def get_all_book_tickers(self) -> Dict[str, Dict]:
        """Get best bid/ask for all symbols."""
        now = time.time()
        if now - self._cache_time < 1 and self._book_cache:
            return self._book_cache
            
        resp = self.session.get(f"{self.BASE_URL}/ticker/bookTicker")
        resp.raise_for_status()
        
        result = {}
        for t in resp.json():
            if float(t['bidPrice']) > 0 and float(t['askPrice']) > 0:
                result[t['symbol']] = {
                    'bid': float(t['bidPrice']),
                    'ask': float(t['askPrice']),
                    'bid_qty': float(t['bidQty']),
                    'ask_qty': float(t['askQty'])
                }
        
        self._book_cache = result
        self._cache_time = now
        return result
    
    def get_24h_tickers(self) -> Dict[str, float]:
        """Get 24h volumes."""
        resp = self.session.get(f"{self.BASE_URL}/ticker/24hr")
        resp.raise_for_status()
        return {t['symbol']: float(t['quoteVolume']) for t in resp.json()}


class StablecoinArbitrageScanner:
    """Scans for arbitrage using 0% stablecoin fees."""
    
    # Trading fee for non-stablecoin pairs
    TRADING_FEE = 0.001  # 0.1%
    
    # Stablecoins with 0% trading fee between them
    STABLECOINS = ['USDT', 'USDC', 'FDUSD', 'TUSD']
    
    def __init__(self, min_volume: float = 100000, min_profit: float = 0.01):
        self.client = BinanceClient()
        self.min_volume = min_volume
        self.min_profit = min_profit
        
    def get_stable_exchange_rates(self, book_tickers: Dict) -> Dict[Tuple[str, str], Dict]:
        """Get exchange rates between stablecoins."""
        rates = {}
        
        for stable1 in self.STABLECOINS:
            for stable2 in self.STABLECOINS:
                if stable1 == stable2:
                    continue
                
                # Check direct pair
                symbol = f"{stable1}{stable2}"
                if symbol in book_tickers:
                    rates[(stable1, stable2)] = {
                        'symbol': symbol,
                        'bid': book_tickers[symbol]['bid'],
                        'ask': book_tickers[symbol]['ask'],
                        'type': 'direct'
                    }
                
                # Check reverse pair
                reverse = f"{stable2}{stable1}"
                if reverse in book_tickers and (stable1, stable2) not in rates:
                    rates[(stable1, stable2)] = {
                        'symbol': reverse,
                        'bid': 1 / book_tickers[reverse]['ask'],
                        'ask': 1 / book_tickers[reverse]['bid'],
                        'type': 'reverse'
                    }
        
        return rates
    
    def find_opportunities(self) -> List[ArbitrageOpportunity]:
        """Find stablecoin arbitrage opportunities."""
        opportunities = []
        
        book_tickers = self.client.get_all_book_tickers()
        volumes = self.client.get_24h_tickers()
        stable_rates = self.get_stable_exchange_rates(book_tickers)
        
        # Find assets tradable against multiple stablecoins
        asset_markets = {}  # asset -> {stable: {bid, ask, volume}}
        
        for symbol, data in book_tickers.items():
            for stable in self.STABLECOINS:
                if symbol.endswith(stable) and not symbol[:-len(stable)] in self.STABLECOINS:
                    asset = symbol[:-len(stable)]
                    if asset not in asset_markets:
                        asset_markets[asset] = {}
                    
                    vol = volumes.get(symbol, 0)
                    
                    # Convert volume to USDT equivalent
                    if stable != 'USDT':
                        rate = stable_rates.get((stable, 'USDT'), {}).get('bid', 1)
                        vol *= rate
                    
                    if vol >= self.min_volume:
                        asset_markets[asset][stable] = {
                            'symbol': symbol,
                            'bid': data['bid'],
                            'ask': data['ask'],
                            'bid_qty': data['bid_qty'],
                            'ask_qty': data['ask_qty'],
                            'volume': vol
                        }
        
        # Find arbitrage between different stablecoin markets
        for asset, markets in asset_markets.items():
            if len(markets) < 2:
                continue
            
            # Compare all pairs of stablecoin markets
            stables = list(markets.keys())
            for i, buy_stable in enumerate(stables):
                for sell_stable in stables[i+1:]:
                    buy_market = markets[buy_stable]
                    sell_market = markets[sell_stable]
                    
                    # Get stablecoin conversion rate
                    if buy_stable == sell_stable:
                        continue
                    
                    stable_rate = stable_rates.get((sell_stable, buy_stable), {})
                    if not stable_rate:
                        continue
                    
                    # Strategy: Buy asset in buy_stable market, sell in sell_stable market
                    # Path: buy_stable -> asset -> sell_stable -> buy_stable
                    
                    # Cost to buy 1 unit of asset (in buy_stable)
                    buy_cost = buy_market['ask'] * (1 + self.TRADING_FEE)
                    
                    # Revenue from selling 1 unit of asset (in sell_stable)
                    sell_revenue_in_sell_stable = sell_market['bid'] * (1 - self.TRADING_FEE)
                    
                    # Convert sell_stable back to buy_stable (0% fee)
                    # Use bid rate (we're selling sell_stable)
                    final_revenue = sell_revenue_in_sell_stable * stable_rate['bid']
                    
                    profit_pct = (final_revenue / buy_cost - 1) * 100
                    spread_pct = (sell_market['bid'] / buy_market['ask'] - 1) * 100
                    
                    if profit_pct > self.min_profit:
                        path = f"{buy_stable} -> {asset} -> {sell_stable} -> {buy_stable}"
                        opportunities.append(ArbitrageOpportunity(
                            asset=asset,
                            buy_market=buy_stable,
                            sell_market=sell_stable,
                            buy_price=buy_market['ask'],
                            sell_price=sell_market['bid'],
                            spread_pct=spread_pct,
                            net_profit_pct=profit_pct,
                            path=path,
                            volume=min(buy_market['volume'], sell_market['volume'])
                        ))
                    
                    # Try reverse direction
                    buy_cost = sell_market['ask'] * (1 + self.TRADING_FEE)
                    sell_revenue_in_buy_stable = buy_market['bid'] * (1 - self.TRADING_FEE)
                    
                    # Convert buy_stable to sell_stable (0% fee)
                    stable_rate_rev = stable_rates.get((buy_stable, sell_stable), {})
                    if stable_rate_rev:
                        final_revenue = sell_revenue_in_buy_stable * stable_rate_rev['bid']
                        profit_pct = (final_revenue / buy_cost - 1) * 100
                        
                        if profit_pct > self.min_profit:
                            path = f"{sell_stable} -> {asset} -> {buy_stable} -> {sell_stable}"
                            opportunities.append(ArbitrageOpportunity(
                                asset=asset,
                                buy_market=sell_stable,
                                sell_market=buy_stable,
                                buy_price=sell_market['ask'],
                                sell_price=buy_market['bid'],
                                spread_pct=(buy_market['bid'] / sell_market['ask'] - 1) * 100,
                                net_profit_pct=profit_pct,
                                path=path,
                                volume=min(buy_market['volume'], sell_market['volume'])
                            ))
        
        return sorted(opportunities, key=lambda x: x.net_profit_pct, reverse=True)
    
    def find_stablecoin_triangles(self) -> List[Tuple[str, float]]:
        """Find pure stablecoin triangle arbitrage (all 0% fee)."""
        opportunities = []
        book_tickers = self.client.get_all_book_tickers()
        
        # Find triangles using actual book prices
        # Path: s1 -> s2 -> s3 -> s1
        # We need to properly handle buy/sell direction
        
        for s1 in self.STABLECOINS:
            for s2 in self.STABLECOINS:
                if s1 == s2:
                    continue
                for s3 in self.STABLECOINS:
                    if s3 in (s1, s2):
                        continue
                    
                    # Calculate each leg correctly
                    # Leg 1: s1 -> s2 (we have s1, want s2)
                    sym12 = f"{s2}{s1}"  # e.g., USDCUSDT if s1=USDT, s2=USDC
                    sym12_rev = f"{s1}{s2}"
                    
                    if sym12 in book_tickers:
                        # Buy s2: 1 s1 gets us (1/ask) s2
                        r1 = 1 / book_tickers[sym12]['ask']
                    elif sym12_rev in book_tickers:
                        # Sell s1: 1 s1 gets us bid s2
                        r1 = book_tickers[sym12_rev]['bid']
                    else:
                        continue
                    
                    # Leg 2: s2 -> s3 (we have s2, want s3)
                    sym23 = f"{s3}{s2}"
                    sym23_rev = f"{s2}{s3}"
                    
                    if sym23 in book_tickers:
                        r2 = 1 / book_tickers[sym23]['ask']
                    elif sym23_rev in book_tickers:
                        r2 = book_tickers[sym23_rev]['bid']
                    else:
                        continue
                    
                    # Leg 3: s3 -> s1 (we have s3, want s1)
                    sym31 = f"{s1}{s3}"
                    sym31_rev = f"{s3}{s1}"
                    
                    if sym31 in book_tickers:
                        r3 = 1 / book_tickers[sym31]['ask']
                    elif sym31_rev in book_tickers:
                        r3 = book_tickers[sym31_rev]['bid']
                    else:
                        continue
                    
                    final = r1 * r2 * r3
                    profit_pct = (final - 1) * 100
                    
                    path = f"{s1} -> {s2} -> {s3} -> {s1}"
                    opportunities.append((path, profit_pct))
        
        return sorted(opportunities, key=lambda x: x[1], reverse=True)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Stablecoin Arbitrage Scanner')
    parser.add_argument('--min-volume', '-v', type=float, default=100000,
                        help='Minimum 24h volume in USDT (default: 100000)')
    parser.add_argument('--min-profit', '-p', type=float, default=0.01,
                        help='Minimum profit percentage (default: 0.01)')
    parser.add_argument('--interval', '-i', type=int, default=5,
                        help='Scan interval in seconds (default: 5)')
    parser.add_argument('--once', action='store_true',
                        help='Run once and exit')
    
    args = parser.parse_args()
    
    scanner = StablecoinArbitrageScanner(
        min_volume=args.min_volume,
        min_profit=args.min_profit
    )
    
    print("=" * 70)
    print(" Stablecoin Arbitrage Scanner (0% Fee Exploitation)")
    print("=" * 70)
    print(f"Min Volume: {args.min_volume:,.0f} USDT")
    print(f"Min Profit: {args.min_profit}%")
    print(f"Stablecoins: {', '.join(scanner.STABLECOINS)}")
    print("=" * 70)
    
    try:
        while True:
            now = datetime.now()
            
            # Find pure stablecoin triangles
            print(f"\n[{now.strftime('%H:%M:%S')}] Pure Stablecoin Triangles (0% fee):")
            triangles = scanner.find_stablecoin_triangles()
            if triangles:
                for path, profit in triangles[:5]:
                    marker = "🟢" if profit > 0 else "🔴"
                    print(f"  {marker} {path}: {profit:+.4f}%")
            else:
                print("  No profitable triangles")
            
            # Find cross-market opportunities
            print(f"\n[{now.strftime('%H:%M:%S')}] Cross-Market Opportunities:")
            opportunities = scanner.find_opportunities()
            
            if opportunities:
                print(f"  Found {len(opportunities)} opportunities:\n")
                print(f"  {'Asset':8} | {'Path':40} | {'Spread':>10} | {'Net Profit':>10}")
                print("  " + "-" * 75)
                
                for opp in opportunities[:10]:
                    print(f"  {opp.asset:8} | {opp.path:40} | {opp.spread_pct:+9.4f}% | {opp.net_profit_pct:+9.4f}%")
                
                if opportunities:
                    best = opportunities[0]
                    print(f"\n  💰 Best: {best.asset} via {best.path}")
                    print(f"     Buy @ {best.buy_price:.6f}, Sell @ {best.sell_price:.6f}")
                    print(f"     Net Profit: {best.net_profit_pct:+.4f}%")
            else:
                print("  No profitable opportunities found")
            
            if args.once:
                break
            
            print(f"\n  Next scan in {args.interval} seconds...")
            time.sleep(args.interval)
            
    except KeyboardInterrupt:
        print("\n\nStopped.")


if __name__ == '__main__':
    main()
