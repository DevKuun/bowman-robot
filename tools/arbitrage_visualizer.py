#!/usr/bin/env python3
"""
Binance Arbitrage Opportunity Visualizer

Real-time visualization of arbitrage opportunities across Binance's
diverse quote currency markets (USDT, BTC, ETH, BNB, FDUSD, EUR, etc.)
"""

import time
import requests
import numpy as np
from decimal import Decimal
from datetime import datetime
from typing import Dict, List, Tuple, Set
from collections import defaultdict
from dataclasses import dataclass
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.patches import FancyBboxPatch
import networkx as nx

# Suppress matplotlib debug messages
import logging
logging.getLogger('matplotlib').setLevel(logging.WARNING)


@dataclass
class ArbitrageEdge:
    """Represents an arbitrage edge between two currencies."""
    from_currency: str
    to_currency: str
    symbol: str
    rate: Decimal
    implied_rate: Decimal
    spread_pct: float
    volume_24h: float


class BinanceDataFetcher:
    """Fetches real-time data from Binance."""
    
    BASE_URL = "https://api.binance.com/api/v3"
    
    def __init__(self):
        self.session = requests.Session()
        self._exchange_info = None
        self._symbols_by_quote = defaultdict(list)
        self._symbols_by_base = defaultdict(list)
        
    def get_exchange_info(self) -> Dict:
        """Get exchange info and cache it."""
        if self._exchange_info is None:
            resp = self.session.get(f"{self.BASE_URL}/exchangeInfo")
            resp.raise_for_status()
            self._exchange_info = resp.json()
            
            # Index by quote and base
            for sym in self._exchange_info['symbols']:
                if sym['status'] == 'TRADING':
                    self._symbols_by_quote[sym['quoteAsset']].append(sym)
                    self._symbols_by_base[sym['baseAsset']].append(sym)
        
        return self._exchange_info
    
    def get_quote_currencies(self) -> List[str]:
        """Get all quote currencies sorted by number of pairs."""
        self.get_exchange_info()
        sorted_quotes = sorted(
            self._symbols_by_quote.items(),
            key=lambda x: len(x[1]),
            reverse=True
        )
        return [q[0] for q in sorted_quotes]
    
    def get_all_tickers(self) -> Dict[str, Dict]:
        """Get all ticker prices and volumes."""
        resp = self.session.get(f"{self.BASE_URL}/ticker/24hr")
        resp.raise_for_status()
        
        result = {}
        for t in resp.json():
            if float(t['lastPrice']) > 0:
                result[t['symbol']] = {
                    'price': float(t['lastPrice']),
                    'bid': float(t['bidPrice']),
                    'ask': float(t['askPrice']),
                    'volume': float(t['quoteVolume']),  # Volume in quote currency
                    'base_volume': float(t['volume'])
                }
        return result
    
    def get_book_tickers(self) -> Dict[str, Dict]:
        """Get best bid/ask for all symbols."""
        resp = self.session.get(f"{self.BASE_URL}/ticker/bookTicker")
        resp.raise_for_status()
        
        result = {}
        for t in resp.json():
            result[t['symbol']] = {
                'bid': float(t['bidPrice']),
                'ask': float(t['askPrice']),
                'bid_qty': float(t['bidQty']),
                'ask_qty': float(t['askQty'])
            }
        return result


class ArbitrageGraphBuilder:
    """Builds and analyzes currency exchange graph."""
    
    def __init__(self, min_volume: float = 100000):
        self.fetcher = BinanceDataFetcher()
        self.min_volume = min_volume
        self.graph = nx.DiGraph()
        
    def build_graph(self, tickers: Dict[str, Dict]) -> nx.DiGraph:
        """Build directed graph of exchange rates."""
        self.graph.clear()
        info = self.fetcher.get_exchange_info()
        
        # Get USDT rates for volume normalization
        usdt_rates = {'USDT': 1.0}
        for sym in ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']:
            if sym in tickers:
                base = sym.replace('USDT', '')
                usdt_rates[base] = tickers[sym]['price']
        
        for sym_info in info['symbols']:
            if sym_info['status'] != 'TRADING':
                continue
                
            symbol = sym_info['symbol']
            base = sym_info['baseAsset']
            quote = sym_info['quoteAsset']
            
            if symbol not in tickers:
                continue
            
            ticker = tickers[symbol]
            
            # Normalize volume to USDT equivalent
            volume = ticker['volume']
            if quote in usdt_rates:
                volume_usdt = volume * usdt_rates[quote]
            else:
                volume_usdt = volume  # Assume ~1 USDT for unknown quotes
            
            # Filter by normalized volume
            if volume_usdt < self.min_volume:
                continue
            
            price = ticker['price']
            bid = ticker['bid']
            ask = ticker['ask']
            
            if price <= 0 or bid <= 0 or ask <= 0:
                continue
            
            # Add edges: quote -> base (buy) and base -> quote (sell)
            # Buy: spend quote, get base at ask price
            # Sell: spend base, get quote at bid price
            
            self.graph.add_edge(
                quote, base,
                symbol=symbol,
                rate=1/ask,  # How much base per quote
                type='buy',
                volume=volume_usdt
            )
            
            self.graph.add_edge(
                base, quote,
                symbol=symbol,
                rate=bid,  # How much quote per base
                type='sell',
                volume=volume_usdt
            )
        
        return self.graph
    
    def find_arbitrage_cycles(
        self, 
        start_currency: str = 'USDT',
        min_length: int = 3,
        max_length: int = 5,
        fee_rate: float = 0.001
    ) -> List[Tuple[List[str], float]]:
        """Find profitable arbitrage cycles."""
        if start_currency not in self.graph:
            return []
        
        opportunities = []
        fee_multiplier = 1 - fee_rate
        
        # Use DFS to find cycles
        def dfs(path, current_value):
            current = path[-1]
            
            if len(path) > max_length:
                return
            
            for neighbor in self.graph.neighbors(current):
                edge = self.graph[current][neighbor]
                new_value = current_value * edge['rate'] * fee_multiplier
                
                if neighbor == start_currency and len(path) >= min_length:
                    # Found a cycle with minimum length
                    profit_pct = (new_value - 1) * 100
                    if profit_pct > -1.0:  # Show paths with loss up to 1%
                        opportunities.append((path + [neighbor], profit_pct))
                elif neighbor not in path:
                    dfs(path + [neighbor], new_value)
        
        dfs([start_currency], 1.0)
        
        # Sort by profit
        return sorted(opportunities, key=lambda x: x[1], reverse=True)
    
    def find_spread_opportunities(
        self,
        base_currency: str = 'USDT'
    ) -> List[Dict]:
        """Find spread opportunities between different quote markets."""
        opportunities = []
        
        # Quote currencies to check for indirect paths
        intermediate_quotes = ['BTC', 'ETH', 'BNB']
        
        # Get quote-to-base_currency rates
        quote_rates = {}
        for quote in intermediate_quotes:
            if quote in self.graph and base_currency in self.graph[quote]:
                quote_rates[quote] = self.graph[quote][base_currency]['rate']
        
        # Find all assets in the graph
        for asset in self.graph.nodes():
            # Skip quote currencies
            if asset in [base_currency] + intermediate_quotes:
                continue
            
            # Check if asset has direct path to base_currency
            if base_currency not in self.graph[asset]:
                continue
            
            direct_rate = self.graph[asset][base_currency]['rate']
            
            # Check indirect paths via each quote currency
            for quote, quote_rate in quote_rates.items():
                if quote not in self.graph[asset]:
                    continue
                
                # Calculate indirect rate
                asset_to_quote = self.graph[asset][quote]['rate']
                indirect_rate = asset_to_quote * quote_rate
                
                if indirect_rate <= 0 or direct_rate <= 0:
                    continue
                
                spread_pct = ((direct_rate - indirect_rate) / indirect_rate) * 100
                
                if abs(spread_pct) > 0.01:  # > 0.01% spread
                    opportunities.append({
                        'asset': asset,
                        'base': base_currency,
                        'via': quote,
                        'direct_rate': direct_rate,
                        'indirect_rate': indirect_rate,
                        'spread_pct': spread_pct
                    })
        
        return sorted(opportunities, key=lambda x: abs(x['spread_pct']), reverse=True)


class ArbitrageVisualizer:
    """Real-time visualization of arbitrage opportunities."""
    
    def __init__(self, min_volume: float = 50000):
        self.fetcher = BinanceDataFetcher()
        self.graph_builder = ArbitrageGraphBuilder(min_volume)
        
        # Data storage
        self.history = {
            'timestamps': [],
            'best_triangle': [],
            'best_spread': [],
            'opportunities_count': []
        }
        self.max_history = 100
        
        # Setup figure
        plt.style.use('dark_background')
        self.fig = plt.figure(figsize=(16, 10))
        self.fig.suptitle('Binance Arbitrage Monitor', fontsize=14, fontweight='bold')
        
        # Subplots
        self.ax_graph = self.fig.add_subplot(2, 2, 1)
        self.ax_triangle = self.fig.add_subplot(2, 2, 2)
        self.ax_spread = self.fig.add_subplot(2, 2, 3)
        self.ax_history = self.fig.add_subplot(2, 2, 4)
        
        # Quote currency stats
        self.quote_stats = None
        
    def update(self, frame):
        """Update function for animation."""
        try:
            # Fetch data
            tickers = self.fetcher.get_all_tickers()
            self.graph_builder.build_graph(tickers)
            
            # Find opportunities
            triangle_opps = self.graph_builder.find_arbitrage_cycles('USDT', max_length=4)
            spread_opps = self.graph_builder.find_spread_opportunities('USDT')
            
            # Store history
            now = datetime.now()
            self.history['timestamps'].append(now)
            self.history['best_triangle'].append(
                triangle_opps[0][1] if triangle_opps else 0
            )
            self.history['best_spread'].append(
                abs(spread_opps[0]['spread_pct']) if spread_opps else 0
            )
            self.history['opportunities_count'].append(
                len(triangle_opps) + len(spread_opps)
            )
            
            # Trim history
            if len(self.history['timestamps']) > self.max_history:
                for key in self.history:
                    self.history[key] = self.history[key][-self.max_history:]
            
            # Clear axes
            for ax in [self.ax_graph, self.ax_triangle, self.ax_spread, self.ax_history]:
                ax.clear()
            
            # 1. Draw currency graph (top-left)
            self._draw_graph(self.ax_graph)
            
            # 2. Draw triangle opportunities (top-right)
            self._draw_triangle_table(self.ax_triangle, triangle_opps[:10])
            
            # 3. Draw spread opportunities (bottom-left)
            self._draw_spread_table(self.ax_spread, spread_opps[:10])
            
            # 4. Draw history chart (bottom-right)
            self._draw_history(self.ax_history)
            
            # Update timestamp
            self.fig.suptitle(
                f'Binance Arbitrage Monitor - {now.strftime("%Y-%m-%d %H:%M:%S")}',
                fontsize=14, fontweight='bold'
            )
            
            plt.tight_layout()
            
        except Exception as e:
            print(f"Update error: {e}")
    
    def _draw_graph(self, ax):
        """Draw currency relationship graph."""
        ax.set_title('Quote Currency Network', fontsize=11)
        
        # Get quote currencies with most pairs
        quotes = self.fetcher.get_quote_currencies()[:10]
        
        # Create subgraph of quote currencies
        G = nx.DiGraph()
        
        for q1 in quotes:
            for q2 in quotes:
                if q1 != q2 and q1 in self.graph_builder.graph and q2 in self.graph_builder.graph[q1]:
                    edge = self.graph_builder.graph[q1][q2]
                    G.add_edge(q1, q2, weight=edge['rate'])
        
        if len(G.nodes()) == 0:
            ax.text(0.5, 0.5, 'No data', ha='center', va='center', fontsize=12)
            ax.axis('off')
            return
        
        # Layout
        pos = nx.spring_layout(G, k=2, iterations=50)
        
        # Node sizes based on number of connections
        node_sizes = []
        for node in G.nodes():
            size = len(list(self.graph_builder.graph.neighbors(node))) * 50 + 500
            node_sizes.append(min(size, 3000))
        
        # Draw
        nx.draw_networkx_nodes(G, pos, ax=ax, node_color='#4CAF50', 
                               node_size=node_sizes, alpha=0.8)
        nx.draw_networkx_labels(G, pos, ax=ax, font_size=9, font_color='white')
        nx.draw_networkx_edges(G, pos, ax=ax, edge_color='#888888', 
                               alpha=0.5, arrows=True, arrowsize=10)
        
        ax.axis('off')
    
    def _draw_triangle_table(self, ax, opportunities):
        """Draw triangle arbitrage opportunities table."""
        ax.set_title('Triangle Arbitrage Opportunities', fontsize=11)
        ax.axis('off')
        
        if not opportunities:
            ax.text(0.5, 0.5, 'No profitable triangles found', 
                    ha='center', va='center', fontsize=11, color='gray')
            return
        
        # Table data
        headers = ['#', 'Path', 'Profit %']
        rows = []
        for i, (path, profit) in enumerate(opportunities[:10], 1):
            path_str = ' → '.join(path)
            if len(path_str) > 30:
                path_str = path_str[:27] + '...'
            rows.append([str(i), path_str, f'{profit:.4f}%'])
        
        # Draw table
        table = ax.table(
            cellText=rows,
            colLabels=headers,
            cellLoc='left',
            loc='center',
            colWidths=[0.08, 0.70, 0.22]
        )
        
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1, 1.5)
        
        # Style header
        for i in range(len(headers)):
            table[(0, i)].set_facecolor('#2E7D32')
            table[(0, i)].set_text_props(weight='bold', color='white')
        
        # Color rows by profit
        for i, (_, profit) in enumerate(opportunities[:10], 1):
            if profit > 0.5:
                color = '#1B5E20'
            elif profit > 0.2:
                color = '#2E7D32'
            else:
                color = '#333333'
            for j in range(len(headers)):
                table[(i, j)].set_facecolor(color)
                table[(i, j)].set_text_props(color='white')
    
    def _draw_spread_table(self, ax, opportunities):
        """Draw spread opportunities table."""
        ax.set_title('Cross-Market Spread Opportunities', fontsize=11)
        ax.axis('off')
        
        if not opportunities:
            ax.text(0.5, 0.5, 'No significant spreads found',
                    ha='center', va='center', fontsize=11, color='gray')
            return
        
        # Table data
        headers = ['#', 'Asset', 'Via', 'Spread %']
        rows = []
        for i, opp in enumerate(opportunities[:10], 1):
            rows.append([
                str(i),
                opp['asset'],
                f"USDT/{opp['via']}",
                f"{opp['spread_pct']:+.3f}%"
            ])
        
        # Draw table
        table = ax.table(
            cellText=rows,
            colLabels=headers,
            cellLoc='left',
            loc='center',
            colWidths=[0.08, 0.30, 0.32, 0.30]
        )
        
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1, 1.5)
        
        # Style header
        for i in range(len(headers)):
            table[(0, i)].set_facecolor('#1565C0')
            table[(0, i)].set_text_props(weight='bold', color='white')
        
        # Color rows
        for i, opp in enumerate(opportunities[:10], 1):
            spread = abs(opp['spread_pct'])
            if spread > 1.0:
                color = '#0D47A1'
            elif spread > 0.5:
                color = '#1565C0'
            else:
                color = '#333333'
            for j in range(len(headers)):
                table[(i, j)].set_facecolor(color)
                table[(i, j)].set_text_props(color='white')
    
    def _draw_history(self, ax):
        """Draw history chart."""
        ax.set_title('Profit History (Last 100 Updates)', fontsize=11)
        
        if len(self.history['timestamps']) < 2:
            ax.text(0.5, 0.5, 'Collecting data...', 
                    ha='center', va='center', fontsize=11, color='gray')
            return
        
        x = range(len(self.history['timestamps']))
        
        # Plot triangle profits
        ax.plot(x, self.history['best_triangle'], 
                label='Triangle', color='#4CAF50', linewidth=1.5)
        
        # Plot spread profits
        ax.plot(x, self.history['best_spread'], 
                label='Spread', color='#2196F3', linewidth=1.5)
        
        ax.set_xlabel('Updates', fontsize=9)
        ax.set_ylabel('Profit %', fontsize=9)
        ax.legend(loc='upper right', fontsize=8)
        ax.grid(True, alpha=0.3)
        
        # Show latest values
        if self.history['best_triangle']:
            latest_tri = self.history['best_triangle'][-1]
            latest_spread = self.history['best_spread'][-1]
            ax.axhline(y=latest_tri, color='#4CAF50', linestyle='--', alpha=0.5)
            ax.axhline(y=latest_spread, color='#2196F3', linestyle='--', alpha=0.5)
    
    def run(self, interval: int = 5000):
        """Run the visualizer."""
        print("Starting Binance Arbitrage Visualizer...")
        print(f"Update interval: {interval}ms")
        print("Close the window to stop.\n")
        
        # Initial data fetch
        print("Fetching initial data...")
        quotes = self.fetcher.get_quote_currencies()
        print(f"Found {len(quotes)} quote currencies:")
        for i, q in enumerate(quotes[:15], 1):
            count = len(self.fetcher._symbols_by_quote[q])
            print(f"  {i:2}. {q}: {count} pairs")
        print()
        
        # Start animation
        ani = animation.FuncAnimation(
            self.fig, 
            self.update,
            interval=interval,
            cache_frame_data=False
        )
        
        plt.show()


def print_quote_currencies():
    """Print all quote currencies and their pair counts."""
    fetcher = BinanceDataFetcher()
    fetcher.get_exchange_info()
    
    print("\n" + "=" * 50)
    print(" Binance Quote Currencies")
    print("=" * 50)
    
    quotes = fetcher.get_quote_currencies()
    
    for i, q in enumerate(quotes, 1):
        count = len(fetcher._symbols_by_quote[q])
        bar = "█" * min(count // 10, 30)
        print(f"{i:2}. {q:8} : {count:4} pairs {bar}")
    
    print("=" * 50)
    print(f"Total: {len(quotes)} quote currencies")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Binance Arbitrage Visualizer')
    parser.add_argument(
        '--interval', '-i',
        type=int,
        default=5000,
        help='Update interval in milliseconds (default: 5000)'
    )
    parser.add_argument(
        '--min-volume', '-v',
        type=float,
        default=50000,
        help='Minimum 24h volume in quote currency (default: 50000)'
    )
    parser.add_argument(
        '--list-quotes',
        action='store_true',
        help='List all quote currencies and exit'
    )
    parser.add_argument(
        '--no-gui',
        action='store_true',
        help='Run in console mode without GUI'
    )
    
    args = parser.parse_args()
    
    if args.list_quotes:
        print_quote_currencies()
        return
    
    if args.no_gui:
        # Console mode
        import sys
        fetcher = BinanceDataFetcher()
        builder = ArbitrageGraphBuilder(args.min_volume)
        
        print("Running in console mode. Press Ctrl+C to stop.\n", flush=True)
        
        while True:
            try:
                print("Fetching tickers...", flush=True)
                tickers = fetcher.get_all_tickers()
                print(f"Got {len(tickers)} tickers, building graph...", flush=True)
                builder.build_graph(tickers)
                
                print("Finding triangle arbitrage...", flush=True)
                triangle_opps = builder.find_arbitrage_cycles('USDT', max_length=4)
                print("Finding spread opportunities...", flush=True)
                spread_opps = builder.find_spread_opportunities('USDT')
                
                print(f"\n{'='*60}", flush=True)
                print(f" {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
                print(f"{'='*60}", flush=True)
                
                print(f"\n[Triangle/Multi-hop Arbitrage] (found {len(triangle_opps)})", flush=True)
                if triangle_opps:
                    # Group by path length
                    by_length = {}
                    for path, profit in triangle_opps:
                        steps = len(path) - 1
                        if steps not in by_length:
                            by_length[steps] = []
                        by_length[steps].append((path, profit))
                    
                    for steps in sorted(by_length.keys()):
                        paths = by_length[steps]
                        print(f"  {steps}-step ({len(paths):,} paths):", flush=True)
                        for i, (path, profit) in enumerate(paths[:3], 1):
                            marker = "+" if profit > 0 else ""
                            print(f"    {i}. {' → '.join(path)}: {marker}{profit:.4f}%", flush=True)
                else:
                    print("  No opportunities found", flush=True)
                
                print(f"\n[Cross-Market Spread - Top 5] (found {len(spread_opps)})", flush=True)
                if spread_opps:
                    for i, opp in enumerate(spread_opps[:5], 1):
                        print(f"  {i}. {opp['asset']} (USDT vs {opp['via']}): {opp['spread_pct']:+.3f}%", flush=True)
                else:
                    print("  No significant spreads found", flush=True)
                
                sys.stdout.flush()
                time.sleep(args.interval / 1000)
                
            except KeyboardInterrupt:
                print("\nStopped.", flush=True)
                break
            except Exception as e:
                print(f"Error: {e}", flush=True)
                import traceback
                traceback.print_exc()
                time.sleep(5)
    else:
        # GUI mode
        viz = ArbitrageVisualizer(min_volume=args.min_volume)
        viz.run(interval=args.interval)


if __name__ == '__main__':
    main()
