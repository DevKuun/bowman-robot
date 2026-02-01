"""
Portfolio optimization worker.
Runs periodic portfolio optimization and stores results in database.
"""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd

from src.core.models import ExchangeType
from src.core.portfolio import PortfolioOptimizer
from src.exchanges import get_exchange
from src.infrastructure.database.connection import db_manager
from src.infrastructure.database.repositories import PortfolioWeightRepository
from src.infrastructure.messaging.slack import slack_notifier
from src.config.settings import settings

logger = logging.getLogger(__name__)

# Global cancellation flag (set by API)
_cancel_requested = False


def request_cancellation():
    """Request cancellation of ongoing optimization."""
    global _cancel_requested
    _cancel_requested = True


def reset_cancellation():
    """Reset cancellation flag."""
    global _cancel_requested
    _cancel_requested = False


def is_cancelled() -> bool:
    """Check if cancellation was requested."""
    return _cancel_requested


class PortfolioWorker:
    """
    Worker for periodic portfolio optimization.
    
    Runs once per week (typically on Monday) to recalculate
    optimal portfolio weights for all risk levels.
    """
    
    def __init__(self, exchange_type: ExchangeType):
        """
        Initialize portfolio worker.
        
        Args:
            exchange_type: Exchange to optimize for
        """
        self.exchange_type = exchange_type
        self.optimizer = PortfolioOptimizer(
            window_years=settings.trading_window_years,
            risk_levels=settings.risk_levels,
            th_ptf_rate=settings.trading_th_ptf_rate
        )
        
        # Stablecoin identifiers from settings
        self.stablecoins = settings.stablecoins
        
        # Key currencies for portfolio (major assets)
        self.key_currencies = ['BTC', 'ETH']
        
        self.last_optimization = None
        self.is_running = True
    
    async def get_historical_prices(self) -> pd.DataFrame:
        """
        Fetch historical price data for optimization.
        
        Returns:
            DataFrame with weekly prices for all assets
        """
        import time
        
        # Create an exchange instance without authentication for public data
        if self.exchange_type == ExchangeType.UPBIT:
            from src.exchanges.upbit import UpbitExchange
            exchange = UpbitExchange('', '')
        elif self.exchange_type == ExchangeType.BINANCE:
            from src.exchanges.binance import BinanceExchange
            exchange = BinanceExchange('', '')
        elif self.exchange_type == ExchangeType.KORBIT:
            from src.exchanges.korbit import KorbitExchange
            exchange = KorbitExchange('', '')
        elif self.exchange_type == ExchangeType.BITHUMB:
            from src.exchanges.bithumb import BithumbExchange
            exchange = BithumbExchange('', '')
        else:
            raise ValueError(f"Unsupported exchange: {self.exchange_type}")
        
        # Get trading pairs - filter based on exchange
        all_pairs = exchange.get_trading_pairs()
        
        if self.exchange_type == ExchangeType.UPBIT:
            # Upbit: Use KRW market ONLY for portfolio optimization
            # (BTC/USDT markets don't have enough historical data for 2-year analysis)
            # Trading will still use all enabled markets for best price
            pairs = [p for p in all_pairs if p.quote_currency == 'KRW']
            
            logger.info(f"Using KRW market for optimization: {len(pairs)} pairs")
        elif self.exchange_type == ExchangeType.BITHUMB:
            # Bithumb: KRW market only
            pairs = [p for p in all_pairs if p.symbol.endswith('_KRW')]
        elif self.exchange_type == ExchangeType.KORBIT:
            # Korbit: KRW market only (format: btc_krw)
            pairs = [p for p in all_pairs if p.symbol.endswith('_krw')]
        elif self.exchange_type == ExchangeType.BINANCE:
            # Binance: All markets (USDT, BTC, ETH, BNB) - prioritize USDT pairs
            usdt_pairs = [p for p in all_pairs if p.symbol.endswith('USDT')]
            other_pairs = [p for p in all_pairs if not p.symbol.endswith('USDT')]
            pairs = usdt_pairs + other_pairs[:50]  # USDT pairs + limited others
        else:
            pairs = all_pairs[:50]  # Default limit
        
        logger.info(f"Fetching data for {len(pairs)} trading pairs")
        
        # Calculate date range
        today = datetime.utcnow().date()
        start_date = today - timedelta(days=today.weekday())  # Monday
        start_date -= timedelta(days=settings.trading_window_years * 52 * 7)
        
        # Determine if exchange supports weekly candles
        # Bithumb and Korbit only support up to daily candles
        use_daily_resample = self.exchange_type in [ExchangeType.BITHUMB, ExchangeType.KORBIT]
        interval = '1d' if use_daily_resample else '1w'
        limit = settings.trading_window_years * 365 + 10 if use_daily_resample else settings.trading_window_years * 52 + 10
        min_candles = 200 if use_daily_resample else 50  # Need more daily candles
        
        if use_daily_resample:
            logger.info(f"Using daily candles with weekly resampling for {self.exchange_type.value}")
        
        # Collect data in dict first, then concat (more efficient)
        price_data = {}
        success_count = 0
        
        for i, pair in enumerate(pairs):
            # Check for cancellation
            if is_cancelled():
                logger.info("Optimization cancelled by user")
                raise asyncio.CancelledError("Optimization cancelled by user")
            
            try:
                candles = exchange.get_historical_candles(
                    symbol=pair.symbol,
                    interval=interval,
                    start_time=datetime.combine(start_date, datetime.min.time()),
                    limit=limit
                )
                
                if candles and len(candles) >= min_candles:
                    prices = [c['open'] for c in candles]
                    dates = [datetime.fromisoformat(c['timestamp'].replace('Z', '')) for c in candles]
                    series = pd.Series(prices, index=pd.DatetimeIndex(dates))
                    
                    # Resample daily data to weekly if needed
                    if use_daily_resample:
                        # Resample to weekly (Monday start), take first price of the week
                        series = series.resample('W-MON').first().dropna()
                    
                    if len(series) >= 50:  # Need enough weekly data points
                        price_data[pair.base_currency] = series
                        success_count += 1
                
                # Rate limit: sleep between API calls
                if i % 5 == 4:  # Every 5 requests
                    time.sleep(2.0)  # Longer pause
                else:
                    time.sleep(0.35)  # 350ms between each call
                
                # Progress log
                if (i + 1) % 20 == 0:
                    logger.info(f"Progress: {i + 1}/{len(pairs)} pairs, {success_count} successful")
                    
            except Exception as e:
                logger.warning(f"Failed to fetch data for {pair.symbol}: {e}")
                time.sleep(3)  # Extra delay on error (rate limit recovery)
                continue
        
        logger.info(f"Fetched data for {success_count} pairs")
        
        # Create DataFrame from dict
        if price_data:
            df_price = pd.concat(price_data, axis=1)
            df_price = df_price.copy()  # Defragment
            return df_price
        
        return pd.DataFrame()
    
    async def run_optimization(self) -> Dict[int, Dict[str, float]]:
        """
        Run portfolio optimization.
        
        Returns:
            Optimized weights for each risk level
        """
        logger.info(f"Starting portfolio optimization for {self.exchange_type.value}")
        
        # Fetch historical prices
        df_price = await self.get_historical_prices()
        
        if df_price.empty:
            raise ValueError("No price data available for optimization")
        
        # Fill missing stablecoin prices with median
        stablecoins_in_data = [c for c in self.stablecoins if c in df_price.columns]
        if stablecoins_in_data:
            ser_med = df_price[stablecoins_in_data].median(axis=1)
            for ccy in stablecoins_in_data:
                ser_na = df_price[ccy].isna()
                df_price.loc[ser_na, ccy] = ser_med[ser_na]
        
        # Define bounds for KRW market portfolio
        lower_bounds = {}
        upper_bounds = {}
        
        # Allow small short positions for major assets
        if 'BTC' in df_price.columns:
            lower_bounds['BTC'] = -0.03  # -3%
        if 'ETH' in df_price.columns:
            lower_bounds['ETH'] = -0.02  # -2%
        
        # Run optimization
        weights = self.optimizer.run_optimization(
            df_price,
            lower_bounds=lower_bounds,
            upper_bounds=upper_bounds
        )
        
        logger.info(f"Optimization complete for {self.exchange_type.value}")
        return weights
    
    async def save_weights(self, weights: Dict[int, Dict[str, float]]):
        """
        Save optimized weights to database.
        
        Args:
            weights: Optimized weights by risk level
        """
        with db_manager.session_scope() as session:
            repo = PortfolioWeightRepository(session)
            
            for risk_level, weight_dict in weights.items():
                repo.create(
                    exchange=self.exchange_type.value,
                    risk_level=risk_level,
                    weights=weight_dict
                )
            
        logger.info(f"Saved portfolio weights for {self.exchange_type.value}")
    
    async def run_iteration(self) -> bool:
        """
        Run a single optimization iteration.
        
        Returns:
            True if optimization was performed
        """
        if not self.is_running:
            return False
        
        now = datetime.utcnow()
        
        # Check if optimization is needed
        # Run on Monday after 1:00 UTC, or if never run
        should_run = (
            self.last_optimization is None or
            (now.weekday() == 0 and now.hour >= 1 and
             (now - self.last_optimization).days >= 6)
        )
        
        if not should_run:
            return False
        
        try:
            # Run optimization
            weights = await self.run_optimization()
            
            # Save to database
            await self.save_weights(weights)
            
            # Send notification
            slack_notifier.send_info(
                f"Portfolio optimization completed for {self.exchange_type.value}\n"
                f"Generated weights for {len(weights)} risk levels"
            )
            
            self.last_optimization = now
            return True
            
        except Exception as e:
            logger.error(f"Portfolio optimization failed: {e}")
            slack_notifier.send_error(
                f"Portfolio optimization failed for {self.exchange_type.value}",
                context=str(e)
            )
            return False
    
    def stop(self):
        """Stop the worker."""
        self.is_running = False
        logger.info(f"Stopped portfolio worker for {self.exchange_type.value}")
