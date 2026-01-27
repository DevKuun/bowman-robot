"""
SQLAlchemy ORM models for the database.
Supports both PostgreSQL and SQLite.
"""
import uuid
import json
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, 
    ForeignKey, Text, Numeric, Index, CheckConstraint, TypeDecorator
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class GUID(TypeDecorator):
    """Platform-independent GUID type.
    Uses PostgreSQL's UUID type or CHAR(36) for SQLite.
    """
    impl = String(36)
    cache_ok = True
    
    def process_bind_param(self, value, dialect):
        if value is not None:
            if isinstance(value, uuid.UUID):
                return str(value)
            return str(uuid.UUID(value))
        return value
    
    def process_result_value(self, value, dialect):
        if value is not None:
            return uuid.UUID(value)
        return value


class JSONType(TypeDecorator):
    """Platform-independent JSON type.
    Uses PostgreSQL's JSONB or TEXT with JSON serialization for SQLite.
    """
    impl = Text
    cache_ok = True
    
    def process_bind_param(self, value, dialect):
        if value is not None:
            return json.dumps(value)
        return value
    
    def process_result_value(self, value, dialect):
        if value is not None:
            return json.loads(value)
        return value


class User(Base):
    """User model representing a trading account owner."""
    
    __tablename__ = "users"
    
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    exchange_accounts = relationship("ExchangeAccount", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, email={self.email})>"


class ExchangeAccount(Base):
    """Exchange account model storing API credentials and settings."""
    
    __tablename__ = "exchange_accounts"
    
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    exchange = Column(String(50), nullable=False)  # 'UPBIT', 'BINANCE', 'KORBIT'
    
    # Encrypted API keys
    access_key_encrypted = Column(Text, nullable=False)
    secret_key_encrypted = Column(Text, nullable=False)
    
    # Status flags
    is_active = Column(Boolean, default=True, nullable=False)
    is_valid_key = Column(Boolean, default=True, nullable=False)
    is_correct_ip = Column(Boolean, default=True, nullable=False)
    is_checked = Column(Boolean, default=True, nullable=False)
    
    # Trading settings
    risk_level = Column(Integer, default=1, nullable=False)
    cash_weight = Column(Numeric(5, 4), default=0.0, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="exchange_accounts")
    trades = relationship("Trade", back_populates="exchange_account", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_exchange_accounts_active", "is_active", "exchange"),
        CheckConstraint("risk_level >= 0 AND risk_level <= 4", name="check_risk_level"),
        {"schema": None}
    )
    
    def __repr__(self):
        return f"<ExchangeAccount(id={self.id}, exchange={self.exchange}, is_active={self.is_active})>"


class PortfolioWeight(Base):
    """Portfolio weight model storing optimized portfolio allocations."""
    
    __tablename__ = "portfolio_weights"
    
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    exchange = Column(String(50), nullable=False)
    risk_level = Column(Integer, nullable=False)
    weights = Column(JSONType, nullable=False)  # {"BTC": 0.3, "ETH": 0.2, ...}
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("idx_portfolio_weights_latest", "exchange", "risk_level", created_at.desc()),
    )
    
    def __repr__(self):
        return f"<PortfolioWeight(exchange={self.exchange}, risk_level={self.risk_level})>"


class TradingSession(Base):
    """Trading session model for grouping trades by bot run."""
    
    __tablename__ = "trading_sessions"
    
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    session_id = Column(String(100), unique=True, nullable=False)  # Human-readable session ID
    exchange = Column(String(50), nullable=False)
    mode = Column(String(20), nullable=False)  # 'paper', 'live'
    
    # Session settings
    risk_level = Column(Integer, default=2, nullable=False)
    initial_balance = Column(Numeric(20, 2), nullable=True)
    
    # Session state
    status = Column(String(20), default='running', nullable=False)  # 'running', 'stopped', 'completed'
    
    # Statistics
    total_trades = Column(Integer, default=0, nullable=False)
    total_fees = Column(Numeric(20, 8), default=0, nullable=False)
    final_pnl = Column(Numeric(20, 2), nullable=True)
    final_pnl_percent = Column(Numeric(10, 4), nullable=True)
    
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    
    # Relationships
    trades = relationship("Trade", back_populates="session", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_trading_sessions_exchange", "exchange", started_at.desc()),
    )
    
    def __repr__(self):
        return f"<TradingSession(session_id={self.session_id}, exchange={self.exchange}, mode={self.mode})>"
    
    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "session_id": self.session_id,
            "exchange": self.exchange,
            "mode": self.mode,
            "risk_level": self.risk_level,
            "initial_balance": float(self.initial_balance) if self.initial_balance else None,
            "status": self.status,
            "total_trades": self.total_trades,
            "total_fees": float(self.total_fees),
            "final_pnl": float(self.final_pnl) if self.final_pnl else None,
            "final_pnl_percent": float(self.final_pnl_percent) if self.final_pnl_percent else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
        }


class Trade(Base):
    """Trade model storing executed trade history."""
    
    __tablename__ = "trades"
    
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    exchange_account_id = Column(GUID(), ForeignKey("exchange_accounts.id", ondelete="SET NULL"), nullable=True)
    trading_session_id = Column(GUID(), ForeignKey("trading_sessions.id", ondelete="CASCADE"), nullable=True)
    
    symbol = Column(String(20), nullable=False)  # e.g., 'KRW-BTC', 'BTCUSDT'
    side = Column(String(10), nullable=False)  # 'BUY', 'SELL'
    quantity = Column(Numeric(20, 8), nullable=False)
    price = Column(Numeric(20, 8), nullable=False)
    value = Column(Numeric(20, 2), nullable=True)  # Trade value in quote currency
    fee = Column(Numeric(20, 8), default=0, nullable=False)
    status = Column(String(20), nullable=False)  # 'PENDING', 'FILLED', 'CANCELLED', 'SIMULATED'
    
    # Execution details
    exchange_order_id = Column(String(100), nullable=True)
    slippage_percent = Column(Numeric(10, 4), nullable=True)
    error_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    executed_at = Column(DateTime, nullable=True)
    
    # Relationships
    exchange_account = relationship("ExchangeAccount", back_populates="trades")
    session = relationship("TradingSession", back_populates="trades")
    
    __table_args__ = (
        Index("idx_trades_account", "exchange_account_id", created_at.desc()),
        Index("idx_trades_session", "trading_session_id", created_at.desc()),
    )
    
    def __repr__(self):
        return f"<Trade(symbol={self.symbol}, side={self.side}, quantity={self.quantity}, price={self.price})>"
    
    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "symbol": self.symbol,
            "side": self.side,
            "quantity": float(self.quantity),
            "price": float(self.price),
            "value": float(self.value) if self.value else None,
            "fee": float(self.fee),
            "status": self.status,
            "slippage_percent": float(self.slippage_percent) if self.slippage_percent else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
        }


class SystemConfig(Base):
    """System configuration model for storing global settings."""
    
    __tablename__ = "system_config"
    
    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f"<SystemConfig(key={self.key})>"


class PnLSnapshot(Base):
    """PnL snapshot model for storing portfolio value history."""
    
    __tablename__ = "pnl_snapshots"
    
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    exchange = Column(String(50), nullable=False)
    session_id = Column(String(50), nullable=False)  # To group snapshots by trading session
    total_value = Column(Numeric(20, 2), nullable=False)
    pnl = Column(Numeric(20, 2), nullable=False)
    pnl_percent = Column(Numeric(10, 4), nullable=False)
    initial_value = Column(Numeric(20, 2), nullable=True)
    
    # Benchmark prices for comparison
    btc_price = Column(Numeric(20, 2), nullable=True)
    eth_price = Column(Numeric(20, 2), nullable=True)
    btc_return = Column(Numeric(10, 4), nullable=True)  # BTC return since session start (%)
    eth_return = Column(Numeric(10, 4), nullable=True)  # ETH return since session start (%)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("idx_pnl_snapshots_session", "session_id", created_at.desc()),
        Index("idx_pnl_snapshots_exchange", "exchange", created_at.desc()),
    )
    
    def __repr__(self):
        return f"<PnLSnapshot(exchange={self.exchange}, pnl={self.pnl}, pnl_percent={self.pnl_percent})>"
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.created_at.isoformat(),
            "total_value": float(self.total_value),
            "pnl": float(self.pnl),
            "pnl_percent": float(self.pnl_percent),
            "btc_price": float(self.btc_price) if self.btc_price else None,
            "eth_price": float(self.eth_price) if self.eth_price else None,
            "btc_return": float(self.btc_return) if self.btc_return else None,
            "eth_return": float(self.eth_return) if self.eth_return else None,
        }
