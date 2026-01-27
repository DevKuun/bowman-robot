"""
Repository pattern implementation for data access.
"""
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc

from .models import User, ExchangeAccount, PortfolioWeight, Trade, PnLSnapshot, TradingSession


class BaseRepository:
    """Base repository with common CRUD operations."""
    
    def __init__(self, session: Session):
        self.session = session


class UserRepository(BaseRepository):
    """Repository for User operations."""
    
    def create(self, email: Optional[str] = None) -> User:
        """Create a new user."""
        user = User(email=email)
        self.session.add(user)
        self.session.flush()
        return user
    
    def get_by_id(self, user_id: UUID) -> Optional[User]:
        """Get user by ID."""
        return self.session.query(User).filter(User.id == user_id).first()
    
    def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        return self.session.query(User).filter(User.email == email).first()
    
    def get_all(self) -> List[User]:
        """Get all users."""
        return self.session.query(User).all()
    
    def delete(self, user_id: UUID) -> bool:
        """Delete a user."""
        user = self.get_by_id(user_id)
        if user:
            self.session.delete(user)
            return True
        return False


class ExchangeAccountRepository(BaseRepository):
    """Repository for ExchangeAccount operations."""
    
    def create(
        self,
        user_id: UUID,
        exchange: str,
        access_key_encrypted: str,
        secret_key_encrypted: str,
        risk_level: int = 1,
        cash_weight: float = 0.0
    ) -> ExchangeAccount:
        """Create a new exchange account."""
        account = ExchangeAccount(
            user_id=user_id,
            exchange=exchange.upper(),
            access_key_encrypted=access_key_encrypted,
            secret_key_encrypted=secret_key_encrypted,
            risk_level=risk_level,
            cash_weight=cash_weight
        )
        self.session.add(account)
        self.session.flush()
        return account
    
    def get_by_id(self, account_id: UUID) -> Optional[ExchangeAccount]:
        """Get exchange account by ID."""
        return self.session.query(ExchangeAccount).filter(
            ExchangeAccount.id == account_id
        ).first()
    
    def get_all(self) -> List[ExchangeAccount]:
        """Get all exchange accounts."""
        return self.session.query(ExchangeAccount).all()
    
    def get_by_user_and_exchange(self, user_id: UUID, exchange: str) -> Optional[ExchangeAccount]:
        """Get exchange account by user and exchange."""
        return self.session.query(ExchangeAccount).filter(
            ExchangeAccount.user_id == user_id,
            ExchangeAccount.exchange == exchange.upper()
        ).first()
    
    def get_active_accounts(self, exchange: Optional[str] = None) -> List[ExchangeAccount]:
        """Get all active exchange accounts, optionally filtered by exchange."""
        query = self.session.query(ExchangeAccount).filter(
            ExchangeAccount.is_active == True,
            ExchangeAccount.is_valid_key == True,
            ExchangeAccount.is_correct_ip == True,
            ExchangeAccount.is_checked == True
        )
        if exchange:
            query = query.filter(ExchangeAccount.exchange == exchange.upper())
        return query.all()
    
    def update_status(
        self,
        account_id: UUID,
        is_active: Optional[bool] = None,
        is_valid_key: Optional[bool] = None,
        is_correct_ip: Optional[bool] = None,
        is_checked: Optional[bool] = None
    ) -> Optional[ExchangeAccount]:
        """Update account status flags."""
        account = self.get_by_id(account_id)
        if account:
            if is_active is not None:
                account.is_active = is_active
            if is_valid_key is not None:
                account.is_valid_key = is_valid_key
            if is_correct_ip is not None:
                account.is_correct_ip = is_correct_ip
            if is_checked is not None:
                account.is_checked = is_checked
            return account
        return None
    
    def update_settings(
        self,
        account_id: UUID,
        risk_level: Optional[int] = None,
        cash_weight: Optional[float] = None
    ) -> Optional[ExchangeAccount]:
        """Update account trading settings."""
        account = self.get_by_id(account_id)
        if account:
            if risk_level is not None:
                account.risk_level = risk_level
            if cash_weight is not None:
                account.cash_weight = cash_weight
            return account
        return None
    
    def delete(self, account_id: UUID) -> bool:
        """Delete an exchange account."""
        account = self.get_by_id(account_id)
        if account:
            self.session.delete(account)
            return True
        return False


class PortfolioWeightRepository(BaseRepository):
    """Repository for PortfolioWeight operations."""
    
    def create(
        self,
        exchange: str,
        risk_level: int,
        weights: Dict[str, float]
    ) -> PortfolioWeight:
        """Create a new portfolio weight record."""
        portfolio_weight = PortfolioWeight(
            exchange=exchange.upper(),
            risk_level=risk_level,
            weights=weights
        )
        self.session.add(portfolio_weight)
        self.session.flush()
        return portfolio_weight
    
    def get_latest(self, exchange: str, risk_level: int) -> Optional[PortfolioWeight]:
        """Get the latest portfolio weight for an exchange and risk level."""
        return self.session.query(PortfolioWeight).filter(
            PortfolioWeight.exchange == exchange.upper(),
            PortfolioWeight.risk_level == risk_level
        ).order_by(desc(PortfolioWeight.created_at)).first()
    
    def get_all_latest(self, exchange: str) -> Dict[int, PortfolioWeight]:
        """Get the latest portfolio weights for all risk levels of an exchange."""
        result = {}
        for risk_level in range(5):  # 0-4
            weight = self.get_latest(exchange, risk_level)
            if weight:
                result[risk_level] = weight
        return result
    
    def bulk_create(
        self,
        exchange: str,
        weights_by_risk: Dict[int, Dict[str, float]]
    ) -> List[PortfolioWeight]:
        """Bulk create portfolio weights for multiple risk levels."""
        created = []
        for risk_level, weights in weights_by_risk.items():
            pw = self.create(exchange, risk_level, weights)
            created.append(pw)
        return created


class TradingSessionRepository(BaseRepository):
    """Repository for TradingSession operations."""
    
    def create(
        self,
        session_id: str,
        exchange: str,
        mode: str,
        risk_level: int = 2,
        initial_balance: Optional[float] = None
    ) -> TradingSession:
        """Create a new trading session."""
        session = TradingSession(
            session_id=session_id,
            exchange=exchange.upper(),
            mode=mode.lower(),
            risk_level=risk_level,
            initial_balance=initial_balance,
            status='running'
        )
        self.session.add(session)
        self.session.flush()
        return session
    
    def get_by_id(self, id: UUID) -> Optional[TradingSession]:
        """Get session by UUID."""
        return self.session.query(TradingSession).filter(
            TradingSession.id == id
        ).first()
    
    def get_by_session_id(self, session_id: str) -> Optional[TradingSession]:
        """Get session by human-readable session ID."""
        return self.session.query(TradingSession).filter(
            TradingSession.session_id == session_id
        ).first()
    
    def get_all(
        self,
        exchange: Optional[str] = None,
        mode: Optional[str] = None,
        limit: int = 50
    ) -> List[TradingSession]:
        """Get all sessions with optional filters."""
        query = self.session.query(TradingSession)
        if exchange:
            query = query.filter(TradingSession.exchange == exchange.upper())
        if mode:
            query = query.filter(TradingSession.mode == mode.lower())
        return query.order_by(desc(TradingSession.started_at)).limit(limit).all()
    
    def update_status(
        self,
        session_id: str,
        status: str,
        final_pnl: Optional[float] = None,
        final_pnl_percent: Optional[float] = None,
        total_trades: Optional[int] = None,
        total_fees: Optional[float] = None
    ) -> Optional[TradingSession]:
        """Update session status and final statistics."""
        session = self.get_by_session_id(session_id)
        if session:
            session.status = status
            if status in ['stopped', 'completed']:
                session.ended_at = datetime.utcnow()
            if final_pnl is not None:
                session.final_pnl = final_pnl
            if final_pnl_percent is not None:
                session.final_pnl_percent = final_pnl_percent
            if total_trades is not None:
                session.total_trades = total_trades
            if total_fees is not None:
                session.total_fees = total_fees
            return session
        return None
    
    def increment_trades(self, session_id: str, fee: float = 0) -> Optional[TradingSession]:
        """Increment trade count and add fee."""
        session = self.get_by_session_id(session_id)
        if session:
            session.total_trades += 1
            session.total_fees = float(session.total_fees) + fee
            return session
        return None


class TradeRepository(BaseRepository):
    """Repository for Trade operations."""
    
    def create(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        status: str = "PENDING",
        value: Optional[float] = None,
        fee: float = 0,
        slippage_percent: Optional[float] = None,
        exchange_account_id: Optional[UUID] = None,
        trading_session_id: Optional[UUID] = None,
        exchange_order_id: Optional[str] = None
    ) -> Trade:
        """Create a new trade record."""
        trade = Trade(
            exchange_account_id=exchange_account_id,
            trading_session_id=trading_session_id,
            symbol=symbol,
            side=side.upper(),
            quantity=quantity,
            price=price,
            value=value,
            fee=fee,
            slippage_percent=slippage_percent,
            status=status.upper(),
            exchange_order_id=exchange_order_id,
            executed_at=datetime.utcnow() if status.upper() in ['FILLED', 'SIMULATED'] else None
        )
        self.session.add(trade)
        self.session.flush()
        return trade
    
    def get_by_id(self, trade_id: UUID) -> Optional[Trade]:
        """Get trade by ID."""
        return self.session.query(Trade).filter(Trade.id == trade_id).first()
    
    def get_by_exchange_order_id(self, exchange_order_id: str) -> Optional[Trade]:
        """Get trade by exchange order ID."""
        return self.session.query(Trade).filter(
            Trade.exchange_order_id == exchange_order_id
        ).first()
    
    def get_by_account(
        self,
        exchange_account_id: UUID,
        limit: int = 100
    ) -> List[Trade]:
        """Get trades for an exchange account."""
        return self.session.query(Trade).filter(
            Trade.exchange_account_id == exchange_account_id
        ).order_by(desc(Trade.created_at)).limit(limit).all()
    
    def get_by_session(
        self,
        trading_session_id: UUID,
        limit: int = 1000
    ) -> List[Trade]:
        """Get trades for a trading session."""
        return self.session.query(Trade).filter(
            Trade.trading_session_id == trading_session_id
        ).order_by(desc(Trade.created_at)).limit(limit).all()
    
    def get_by_session_id(
        self,
        session_id: str,
        limit: int = 1000
    ) -> List[Trade]:
        """Get trades for a trading session by session_id string."""
        session = self.session.query(TradingSession).filter(
            TradingSession.session_id == session_id
        ).first()
        if session:
            return self.get_by_session(session.id, limit)
        return []
    
    def get_pending_trades(self, exchange_account_id: UUID) -> List[Trade]:
        """Get pending trades for an exchange account."""
        return self.session.query(Trade).filter(
            Trade.exchange_account_id == exchange_account_id,
            Trade.status == "PENDING"
        ).all()
    
    def update_status(
        self,
        trade_id: UUID,
        status: str,
        executed_at: Optional[datetime] = None,
        error_message: Optional[str] = None
    ) -> Optional[Trade]:
        """Update trade status."""
        trade = self.get_by_id(trade_id)
        if trade:
            trade.status = status.upper()
            if executed_at:
                trade.executed_at = executed_at
            if error_message:
                trade.error_message = error_message
            return trade
        return None


class PnLSnapshotRepository(BaseRepository):
    """Repository for PnL snapshot operations."""
    
    def create(
        self,
        exchange: str,
        session_id: str,
        total_value: float,
        pnl: float,
        pnl_percent: float,
        initial_value: Optional[float] = None,
        btc_price: Optional[float] = None,
        eth_price: Optional[float] = None,
        btc_return: Optional[float] = None,
        eth_return: Optional[float] = None
    ) -> PnLSnapshot:
        """Create a new PnL snapshot with optional benchmark data."""
        snapshot = PnLSnapshot(
            exchange=exchange,
            session_id=session_id,
            total_value=total_value,
            pnl=pnl,
            pnl_percent=pnl_percent,
            initial_value=initial_value,
            btc_price=btc_price,
            eth_price=eth_price,
            btc_return=btc_return,
            eth_return=eth_return
        )
        self.session.add(snapshot)
        self.session.flush()
        return snapshot
    
    def get_by_session(
        self,
        session_id: str,
        limit: int = 1000
    ) -> List[PnLSnapshot]:
        """Get snapshots for a trading session."""
        return self.session.query(PnLSnapshot).filter(
            PnLSnapshot.session_id == session_id
        ).order_by(PnLSnapshot.created_at).limit(limit).all()
    
    def get_by_exchange(
        self,
        exchange: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[PnLSnapshot]:
        """Get snapshots for an exchange within a time range."""
        query = self.session.query(PnLSnapshot).filter(
            PnLSnapshot.exchange == exchange
        )
        
        if start_time:
            query = query.filter(PnLSnapshot.created_at >= start_time)
        if end_time:
            query = query.filter(PnLSnapshot.created_at <= end_time)
        
        return query.order_by(PnLSnapshot.created_at).limit(limit).all()
    
    def get_recent(
        self,
        exchange: str,
        hours: int = 24,
        limit: int = 1000
    ) -> List[PnLSnapshot]:
        """Get recent snapshots within specified hours."""
        from datetime import timedelta
        start_time = datetime.utcnow() - timedelta(hours=hours)
        return self.get_by_exchange(exchange, start_time=start_time, limit=limit)
    
    def delete_old_snapshots(self, days: int = 30) -> int:
        """Delete snapshots older than specified days."""
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=days)
        deleted = self.session.query(PnLSnapshot).filter(
            PnLSnapshot.created_at < cutoff
        ).delete()
        return deleted
