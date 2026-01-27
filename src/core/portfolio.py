"""
Portfolio optimization using Minimum Variance Portfolio theory.
"""
import logging
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from cvxopt import matrix, solvers
from sklearn.covariance import LedoitWolf

from src.config.settings import settings
from src.core.models import ExchangeType

# Suppress cvxopt output
solvers.options['show_progress'] = False

logger = logging.getLogger(__name__)


class PortfolioOptimizer:
    """
    Minimum Variance Portfolio optimizer using Ledoit-Wolf covariance estimation.
    """
    
    def __init__(
        self,
        window_years: int = 2,
        risk_levels: int = 5,
        th_ptf_rate: float = 0.001
    ):
        """
        Initialize the portfolio optimizer.
        
        Args:
            window_years: Rolling window size in years for historical data
            risk_levels: Number of risk levels (0 to risk_levels-1)
            th_ptf_rate: Threshold portfolio rate for filtering small weights
        """
        self.window_years = window_years
        self.risk_levels = risk_levels
        self.th_ptf_rate = th_ptf_rate
        
        # Stablecoin identifiers from settings
        self.stablecoins = settings.stablecoins
        
        # Core assets that should have minimum allocation
        self.core_assets = ['BTC', 'ETH']
        
        # Stablecoin upper bounds by risk level (0 = conservative, 4 = aggressive)
        self.stable_upper_bounds = {
            0: 0.50,  # 50% max stablecoins
            1: 0.40,
            2: 0.30,
            3: 0.20,
            4: 0.10   # 10% max stablecoins
        }
        
        # Core asset minimum bounds by risk level
        self.core_min_bounds = {
            'BTC': {0: 0.05, 1: 0.08, 2: 0.10, 3: 0.12, 4: 0.15},
            'ETH': {0: 0.03, 1: 0.05, 2: 0.07, 3: 0.10, 4: 0.12}
        }
    
    def calculate_log_returns(self, df_price: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate log returns from price data.
        
        Args:
            df_price: DataFrame with price data (index=date, columns=assets)
            
        Returns:
            DataFrame with log returns
        """
        df_log_ret = np.log(df_price).diff()
        df_log_ret.dropna(inplace=True)
        return df_log_ret
    
    def estimate_covariance(self, df_log_ret: pd.DataFrame) -> np.ndarray:
        """
        Estimate covariance matrix using Ledoit-Wolf shrinkage.
        
        Args:
            df_log_ret: DataFrame with log returns
            
        Returns:
            Shrunk covariance matrix
        """
        lw = LedoitWolf(assume_centered=True)
        cov = lw.fit(df_log_ret.values).covariance_
        return cov
    
    def optimize_portfolio(
        self,
        df_log_ret: pd.DataFrame,
        cov: np.ndarray,
        lower_bounds: Optional[Dict[str, float]] = None,
        upper_bounds: Optional[Dict[str, float]] = None
    ) -> Dict[int, Dict[str, float]]:
        """
        Optimize portfolio for all risk levels.
        
        Args:
            df_log_ret: DataFrame with log returns
            cov: Covariance matrix
            lower_bounds: Optional lower bounds for specific assets
            upper_bounds: Optional upper bounds for specific assets
            
        Returns:
            Dictionary mapping risk_level to asset weights
        """
        n_assets = len(df_log_ret.columns)
        columns = df_log_ret.columns.tolist()
        
        # Identify stablecoins in portfolio
        is_stable = np.zeros(n_assets)
        for i, col in enumerate(columns):
            if col in self.stablecoins:
                is_stable[i] = 1
        
        # Build constraint matrices
        Aeq = matrix(1.0, (1, n_assets))  # Sum of weights = 1
        beq = matrix(1.0)
        q = -matrix(np.zeros((n_assets, 1)))  # No linear term in objective
        
        # Build inequality constraints: -I (lower), I (upper), stablecoin sum
        G = matrix(np.concatenate((
            -np.eye(n_assets),  # Lower bounds
            np.eye(n_assets),   # Upper bounds
            [is_stable]         # Stablecoin sum upper bound
        ), axis=0))
        
        # Default bounds
        lbs = np.zeros((n_assets, 1))
        ubs = np.ones((n_assets, 1))
        
        # Apply custom lower bounds
        if lower_bounds:
            for asset, lb in lower_bounds.items():
                if asset in columns:
                    idx = columns.index(asset)
                    lbs[idx] = lb
        
        # Apply custom upper bounds
        if upper_bounds:
            for asset, ub in upper_bounds.items():
                if asset in columns:
                    idx = columns.index(asset)
                    ubs[idx] = ub
        
        # Optimize for each risk level
        results = {}
        
        for risk in range(self.risk_levels):
            # Reset bounds for each risk level
            risk_lbs = lbs.copy()
            risk_ubs = ubs.copy()
            
            # Apply core asset minimum bounds
            for asset, bounds in self.core_min_bounds.items():
                if asset in columns:
                    idx = columns.index(asset)
                    risk_lbs[idx] = bounds.get(risk, 0.05)
            
            # Get stablecoin upper bound for this risk level
            ub_stable = self.stable_upper_bounds.get(risk, 0.30)
            
            # Apply individual stablecoin upper bounds (distribute evenly)
            max_per_stable = ub_stable / max(1, sum(1 for s in self.stablecoins if s in columns))
            for stable in self.stablecoins:
                if stable in columns:
                    idx = columns.index(stable)
                    risk_ubs[idx] = min(risk_ubs[idx][0], max_per_stable * 2)  # Allow 2x average
            
            # Build constraint vector
            h = matrix(np.concatenate((risk_lbs, risk_ubs, [[ub_stable]]), axis=0))
            
            try:
                # Solve quadratic program
                sol = solvers.qp(matrix(cov), q, G, h, Aeq, beq)
                weights = np.array(sol['x']).flatten()
                
                # Store weights
                weight_dict = {}
                for i, col in enumerate(columns):
                    if weights[i] >= self.th_ptf_rate:
                        weight_dict[col] = float(max(0, weights[i]))
                
                results[risk] = weight_dict
                
                # Log stablecoin sum for debugging
                stable_sum = sum(
                    weights[i] for i, col in enumerate(columns)
                    if col in self.stablecoins
                )
                logger.info(f"Risk {risk}: stablecoin sum = {stable_sum:.2%}, target max = {ub_stable:.0%}")
                    
            except Exception as e:
                logger.error(f"Portfolio optimization failed for risk level {risk}: {e}")
                results[risk] = {}
        
        return results
    
    def apply_illiquidity_adjustment(
        self,
        weights: Dict[int, Dict[str, float]]
    ) -> Dict[int, Dict[str, float]]:
        """
        Apply adjustment for illiquid stablecoins (DAI, USDP, TUSD).
        
        Args:
            weights: Dictionary mapping risk_level to weights
            
        Returns:
            Adjusted weights
        """
        adjusted = {}
        for risk, weight_dict in weights.items():
            adjustment = 1 - (self.risk_levels - risk) / 500
            adjusted[risk] = {
                asset: w * adjustment
                for asset, w in weight_dict.items()
            }
        return adjusted
    
    def filter_small_weights(
        self,
        weights: Dict[int, Dict[str, float]],
        threshold: float = None
    ) -> Dict[int, Dict[str, float]]:
        """
        Filter out weights below threshold.
        
        Args:
            weights: Dictionary mapping risk_level to weights
            threshold: Minimum weight threshold
            
        Returns:
            Filtered weights
        """
        if threshold is None:
            threshold = self.th_ptf_rate
        
        filtered = {}
        for risk, weight_dict in weights.items():
            filtered[risk] = {
                asset: w for asset, w in weight_dict.items()
                if w >= threshold
            }
        return filtered
    
    def run_optimization(
        self,
        df_price: pd.DataFrame,
        lower_bounds: Optional[Dict[str, float]] = None,
        upper_bounds: Optional[Dict[str, float]] = None
    ) -> Dict[int, Dict[str, float]]:
        """
        Run full portfolio optimization pipeline.
        
        Args:
            df_price: DataFrame with historical prices
            lower_bounds: Optional lower bounds for assets
            upper_bounds: Optional upper bounds for assets
            
        Returns:
            Dictionary mapping risk_level to optimized weights
        """
        # Calculate log returns
        df_log_ret = self.calculate_log_returns(df_price)
        
        if len(df_log_ret) < 30:
            raise ValueError(
                f"Not enough data points ({len(df_log_ret)}) "
                "for reliable covariance estimation (need at least 30)"
            )
        
        if len(df_log_ret) < 100:
            logger.warning(
                f"Limited data points ({len(df_log_ret)}). "
                "Results may be less reliable. Recommended: 100+"
            )
        
        logger.info(f"Optimizing portfolio with {len(df_log_ret)} data points")
        
        # Estimate covariance
        cov = self.estimate_covariance(df_log_ret)
        
        # Optimize portfolio
        weights = self.optimize_portfolio(
            df_log_ret, cov,
            lower_bounds=lower_bounds,
            upper_bounds=upper_bounds
        )
        
        # Apply adjustments
        weights = self.apply_illiquidity_adjustment(weights)
        weights = self.filter_small_weights(weights)
        
        return weights


class PortfolioCalculator:
    """
    Calculate portfolio metrics and target weights.
    """
    
    @staticmethod
    def calculate_asset_values(
        balances: Dict[str, Decimal],
        prices: Dict[str, Decimal],
        quote_currency: str = 'KRW'
    ) -> Dict[str, Decimal]:
        """
        Calculate asset values in quote currency.
        
        Args:
            balances: Dictionary of currency to balance
            prices: Dictionary of symbol to price
            quote_currency: Quote currency for valuation
            
        Returns:
            Dictionary of currency to value in quote currency
        """
        values = {}
        for currency, balance in balances.items():
            if balance <= 0:
                continue
                
            if currency == quote_currency:
                values[currency] = balance
            else:
                symbol = f"{quote_currency}-{currency}"
                if symbol in prices:
                    values[currency] = balance * prices[symbol]
                elif f"{currency}{quote_currency}" in prices:
                    values[currency] = balance * prices[f"{currency}{quote_currency}"]
        
        return values
    
    @staticmethod
    def calculate_weights(
        values: Dict[str, Decimal]
    ) -> Tuple[Dict[str, Decimal], Decimal]:
        """
        Calculate portfolio weights from asset values.
        
        Args:
            values: Dictionary of currency to value
            
        Returns:
            Tuple of (weights dict, total value)
        """
        total = sum(values.values())
        if total <= 0:
            return {}, Decimal("0")
        
        weights = {
            currency: value / total
            for currency, value in values.items()
        }
        return weights, total
    
    @staticmethod
    def calculate_target_diff(
        current_weights: Dict[str, Decimal],
        target_weights: Dict[str, float],
        cash_weight: float = 0.0
    ) -> Dict[str, Decimal]:
        """
        Calculate difference between target and current weights.
        
        Args:
            current_weights: Current portfolio weights
            target_weights: Target portfolio weights
            cash_weight: Cash weight to hold
            
        Returns:
            Dictionary of currency to weight difference
        """
        # Adjust target weights for cash weight
        adjusted_targets = {
            currency: Decimal(str(weight)) * (1 - Decimal(str(cash_weight)))
            for currency, weight in target_weights.items()
        }
        
        # Calculate differences
        diffs = {}
        all_currencies = set(current_weights.keys()) | set(adjusted_targets.keys())
        
        for currency in all_currencies:
            current = current_weights.get(currency, Decimal("0"))
            target = adjusted_targets.get(currency, Decimal("0"))
            diff = target - current
            if abs(diff) > Decimal("0.0001"):  # Filter tiny differences
                diffs[currency] = diff
        
        return diffs


# Convenience function for backward compatibility
def run_portfolio_optimization(
    df_price: pd.DataFrame,
    window_years: int = 2,
    risk_levels: int = 5
) -> Dict[int, Dict[str, float]]:
    """
    Run portfolio optimization with default settings.
    
    Args:
        df_price: Historical price data
        window_years: Rolling window size
        risk_levels: Number of risk levels
        
    Returns:
        Optimized weights for each risk level
    """
    optimizer = PortfolioOptimizer(
        window_years=window_years,
        risk_levels=risk_levels
    )
    return optimizer.run_optimization(df_price)
