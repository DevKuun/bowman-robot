"""
Environment-based configuration settings using pydantic-settings.
All sensitive data should be loaded from environment variables.
"""
from functools import lru_cache
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Application
    app_name: str = "bowman-robot"
    app_env: str = Field(default="development", description="development, staging, production")
    debug: bool = Field(default=False)
    
    # Database settings
    db_type: str = Field(default="sqlite", description="Database type: sqlite or postgresql")
    db_path: str = Field(default="data/bowman.db", description="SQLite database file path")
    
    # PostgreSQL Database (used when db_type=postgresql)
    db_host: str = Field(default="localhost")
    db_port: int = Field(default=5432)
    db_name: str = Field(default="bowmandb")
    db_user: str = Field(default="postgres")
    db_password: str = Field(default="")
    db_pool_size: int = Field(default=5)
    db_max_overflow: int = Field(default=10)
    
    @property
    def database_url(self) -> str:
        """Get the database connection URL."""
        if self.db_type == "sqlite":
            return f"sqlite:///{self.db_path}"
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
    
    @property
    def async_database_url(self) -> str:
        """Get the async database connection URL."""
        if self.db_type == "sqlite":
            return f"sqlite+aiosqlite:///{self.db_path}"
        return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
    
    @property
    def is_sqlite(self) -> bool:
        """Check if using SQLite."""
        return self.db_type == "sqlite"
    
    # Encryption settings
    encryption_type: str = Field(default="auto", description="Encryption type: kms, local, none, or auto")
    encryption_key: str = Field(default="", description="Fernet key for local encryption (32 bytes, base64)")
    encryption_secret: str = Field(default="", description="Secret to derive encryption key from")
    
    # AWS KMS for encryption (used when encryption_type=kms)
    aws_access_key_id: str = Field(default="")
    aws_secret_access_key: str = Field(default="")
    aws_region: str = Field(default="ap-northeast-2")
    kms_key_id: str = Field(default="")
    kms_encrypt_algorithm: str = Field(default="RSAES_OAEP_SHA_256")
    
    # Slack notifications
    slack_token: str = Field(default="")
    slack_channel_id: str = Field(default="")
    slack_enabled: bool = Field(default=True)
    
    # Trading parameters
    trading_window_years: int = Field(default=2, description="Rolling window size in years")
    trading_th_trd_rate: float = Field(default=0.0001, description="Threshold trade rate (0.01%)")
    trading_th_ptf_rate: float = Field(default=0.001, description="Threshold portfolio rate (0.1%)")
    trading_max_period_seconds: int = Field(default=60, description="Max period for roulette selection")
    
    # Exchange-specific settings
    upbit_fee_krw: float = Field(default=0.0005, description="Upbit KRW market fee (0.05%)")
    upbit_fee_btc: float = Field(default=0.0025, description="Upbit BTC/USDT market fee (0.25%)")
    upbit_min_trade_krw: int = Field(default=5000, description="Minimum trade amount in KRW")
    upbit_min_trade_btc: float = Field(default=0.00005, description="Minimum trade amount in BTC")
    upbit_min_trade_usdt: float = Field(default=0.5, description="Minimum trade amount in USDT")
    
    # Upbit multi-market settings
    upbit_markets: List[str] = Field(
        default=["KRW"],
        description="Upbit markets to include: KRW, BTC, USDT"
    )
    upbit_primary_market: str = Field(
        default="KRW",
        description="Primary market for portfolio valuation"
    )
    upbit_auto_convert_to_krw: bool = Field(
        default=True,
        description="Automatically convert USDT/BTC to KRW after selling (reduces currency risk)"
    )
    
    binance_fee_discount: float = Field(default=0.25, description="Binance BNB fee discount")
    binance_referral_kickback: float = Field(default=0.2, description="Binance referral kickback")
    
    # Bithumb Exchange Settings
    bithumb_fee: float = Field(default=0.0004, description="Bithumb trading fee (0.04% event)")
    bithumb_min_trade_krw: int = Field(default=5000, description="Minimum trade amount in KRW")
    
    # Korbit Exchange Settings
    korbit_min_trade_krw: int = Field(default=5000, description="Minimum trade amount in KRW")
    
    # Binance Exchange Settings
    binance_min_trade_usdt: float = Field(default=10.0, description="Minimum trade amount in USDT")
    
    # Worker settings
    worker_db_refresh_interval: int = Field(default=5, description="DB refresh interval in seconds")
    worker_binance_refresh_interval: int = Field(default=3, description="Binance price refresh interval")
    worker_max_concurrent_users: int = Field(default=100, description="Maximum concurrent user workers")
    
    # Risk levels
    risk_levels: int = Field(default=5, description="Number of risk levels (0-4)")
    
    # Portfolio optimization settings
    portfolio_min_daily_volume_krw: int = Field(
        default=1_000_000_000,  # 10억원
        description="Minimum 24h trading volume in KRW to include in portfolio"
    )
    portfolio_reoptimize_hours: int = Field(
        default=24,
        description="Hours between automatic portfolio re-optimization (0 to disable)"
    )
    
    # Stablecoin identifiers (used for portfolio constraints and UI)
    stablecoins: List[str] = Field(
        default=["USDT", "USDC", "USDS", "USD1", "DAI", "TUSD", "BUSD", "USDP", "FDUSD", "EUR", "AEUR", "EURI"],
        description="List of stablecoin symbols (including fiat-pegged assets)"
    )
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore"
    }


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()
