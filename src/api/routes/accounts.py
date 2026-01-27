"""
Accounts API routes.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from uuid import UUID

from src.infrastructure.database.connection import db_manager
from src.infrastructure.database.repositories import (
    UserRepository, ExchangeAccountRepository
)
from src.infrastructure.encryption.kms import get_encryptor

router = APIRouter()


class CreateAccountRequest(BaseModel):
    """Request to create a new exchange account."""
    exchange: str
    access_key: str
    secret_key: str
    risk_level: int = 2
    cash_weight: float = 0.0
    email: Optional[str] = None


class UpdateAccountRequest(BaseModel):
    """Request to update an exchange account."""
    risk_level: Optional[int] = None
    cash_weight: Optional[float] = None
    is_active: Optional[bool] = None


@router.get("")
async def get_accounts():
    """Get all registered exchange accounts."""
    with db_manager.session_scope() as session:
        repo = ExchangeAccountRepository(session)
        accounts = repo.get_all()
        
        return {
            "accounts": [
                {
                    "id": str(a.id),
                    "user_id": str(a.user_id),
                    "exchange": a.exchange,
                    "risk_level": a.risk_level,
                    "cash_weight": float(a.cash_weight),
                    "is_active": a.is_active,
                    "created_at": a.created_at.isoformat() if a.created_at else None
                }
                for a in accounts
            ]
        }


@router.get("/{account_id}")
async def get_account(account_id: str):
    """Get a specific exchange account."""
    with db_manager.session_scope() as session:
        repo = ExchangeAccountRepository(session)
        account = repo.get_by_id(UUID(account_id))
        
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        return {
            "id": str(account.id),
            "user_id": str(account.user_id),
            "exchange": account.exchange,
            "risk_level": account.risk_level,
            "cash_weight": float(account.cash_weight),
            "is_active": account.is_active,
            "created_at": account.created_at.isoformat() if account.created_at else None
        }


@router.post("")
async def create_account(request: CreateAccountRequest):
    """Create a new exchange account."""
    # Validate exchange
    valid_exchanges = ["upbit", "binance", "korbit", "bithumb"]
    if request.exchange.lower() not in valid_exchanges:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid exchange. Must be one of: {valid_exchanges}"
        )
    
    # Validate risk level
    if not 0 <= request.risk_level <= 4:
        raise HTTPException(
            status_code=400,
            detail="Risk level must be between 0 and 4"
        )
    
    with db_manager.session_scope() as session:
        user_repo = UserRepository(session)
        account_repo = ExchangeAccountRepository(session)
        
        # Create or get user
        if request.email:
            user = user_repo.get_by_email(request.email)
        else:
            user = None
        
        if not user:
            user = user_repo.create(email=request.email)
        
        # Encrypt API keys
        encryptor = get_encryptor()
        encrypted_access = encryptor.encrypt(request.access_key)
        encrypted_secret = encryptor.encrypt(request.secret_key)
        
        # Create account
        account = account_repo.create(
            user_id=user.id,
            exchange=request.exchange.upper(),
            access_key_encrypted=encrypted_access,
            secret_key_encrypted=encrypted_secret,
            risk_level=request.risk_level,
            cash_weight=request.cash_weight
        )
        
        return {
            "success": True,
            "account_id": str(account.id),
            "user_id": str(user.id),
            "exchange": account.exchange,
            "risk_level": account.risk_level
        }


@router.patch("/{account_id}")
async def update_account(account_id: str, request: UpdateAccountRequest):
    """Update an exchange account."""
    with db_manager.session_scope() as session:
        repo = ExchangeAccountRepository(session)
        account = repo.get_by_id(UUID(account_id))
        
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        # Update fields
        if request.risk_level is not None:
            if not 0 <= request.risk_level <= 4:
                raise HTTPException(
                    status_code=400,
                    detail="Risk level must be between 0 and 4"
                )
            account.risk_level = request.risk_level
        
        if request.cash_weight is not None:
            account.cash_weight = request.cash_weight
        
        if request.is_active is not None:
            account.is_active = request.is_active
        
        session.commit()
        
        return {
            "success": True,
            "account_id": str(account.id),
            "risk_level": account.risk_level,
            "cash_weight": float(account.cash_weight),
            "is_active": account.is_active
        }


@router.delete("/{account_id}")
async def delete_account(account_id: str):
    """Delete an exchange account."""
    with db_manager.session_scope() as session:
        repo = ExchangeAccountRepository(session)
        account = repo.get_by_id(UUID(account_id))
        
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        # Soft delete - just deactivate
        account.is_active = False
        session.commit()
        
        return {
            "success": True,
            "message": "Account deactivated"
        }
