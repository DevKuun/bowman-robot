"""
Account management CLI for Bowman Robot.
"""
import argparse
import sys
import uuid
from typing import Optional

from src.infrastructure.database.connection import db_manager
from src.infrastructure.database.models import Base
from src.infrastructure.database.repositories import UserRepository, ExchangeAccountRepository
from src.infrastructure.encryption.kms import kms_encryption
from src.config.settings import settings


def init_database():
    """Ensure database tables exist."""
    from sqlalchemy import inspect
    
    engine = db_manager.engine
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    
    if 'users' not in existing_tables:
        Base.metadata.create_all(engine)
        print("Database tables created.")


def add_account(
    exchange: str,
    access_key: str,
    secret_key: str,
    risk_level: int = 2,
    cash_weight: float = 0.0,
    email: Optional[str] = None
):
    """Add a new exchange account."""
    init_database()
    
    # Encrypt API keys
    access_key_encrypted = kms_encryption.encrypt(access_key)
    secret_key_encrypted = kms_encryption.encrypt(secret_key)
    
    with db_manager.session_scope() as session:
        user_repo = UserRepository(session)
        account_repo = ExchangeAccountRepository(session)
        
        # Find or create user
        if email:
            user = user_repo.get_by_email(email)
            if not user:
                user = user_repo.create(email=email)
                print(f"Created user: {user.id} ({email})")
        else:
            # Create anonymous user
            user = user_repo.create()
            print(f"Created user: {user.id}")
        
        # Check if account already exists
        existing = account_repo.get_by_user_and_exchange(user.id, exchange)
        if existing:
            print(f"Error: Account already exists for {exchange}")
            print(f"  Account ID: {existing.id}")
            print(f"  Use --update to modify existing account")
            return False
        
        # Create account
        account = account_repo.create(
            user_id=user.id,
            exchange=exchange.upper(),
            access_key_encrypted=access_key_encrypted,
            secret_key_encrypted=secret_key_encrypted,
            risk_level=risk_level,
            cash_weight=cash_weight
        )
        
        print(f"Account created successfully!")
        print(f"  Account ID: {account.id}")
        print(f"  User ID: {user.id}")
        print(f"  Exchange: {account.exchange}")
        print(f"  Risk Level: {account.risk_level}")
        print(f"  Cash Weight: {account.cash_weight}")
        
        return True


def list_accounts(exchange: Optional[str] = None):
    """List all exchange accounts."""
    init_database()
    
    with db_manager.session_scope() as session:
        account_repo = ExchangeAccountRepository(session)
        
        if exchange:
            accounts = account_repo.get_active_accounts(exchange)
        else:
            # Get all accounts
            from src.infrastructure.database.models import ExchangeAccount
            accounts = session.query(ExchangeAccount).all()
        
        if not accounts:
            print("No accounts found.")
            return
        
        print(f"\n{'ID':<36} | {'Exchange':<10} | {'Risk':<4} | {'Active':<6} | {'Valid':<5}")
        print("-" * 80)
        
        for acc in accounts:
            print(f"{acc.id} | {acc.exchange:<10} | {acc.risk_level:<4} | {acc.is_active!s:<6} | {acc.is_valid_key!s:<5}")


def update_account(
    account_id: str,
    risk_level: Optional[int] = None,
    cash_weight: Optional[float] = None,
    is_active: Optional[bool] = None
):
    """Update an existing account."""
    init_database()
    
    with db_manager.session_scope() as session:
        account_repo = ExchangeAccountRepository(session)
        
        account = account_repo.get_by_id(uuid.UUID(account_id))
        if not account:
            print(f"Error: Account not found: {account_id}")
            return False
        
        # Update settings
        if risk_level is not None:
            account_repo.update_settings(account.id, risk_level=risk_level)
        if cash_weight is not None:
            account_repo.update_settings(account.id, cash_weight=cash_weight)
        if is_active is not None:
            account_repo.update_status(account.id, is_active=is_active)
        
        print(f"Account updated: {account_id}")
        return True


def delete_account(account_id: str, force: bool = False):
    """Delete an account."""
    init_database()
    
    with db_manager.session_scope() as session:
        account_repo = ExchangeAccountRepository(session)
        
        account = account_repo.get_by_id(uuid.UUID(account_id))
        if not account:
            print(f"Error: Account not found: {account_id}")
            return False
        
        if not force:
            confirm = input(f"Delete account {account_id} ({account.exchange})? [y/N]: ")
            if confirm.lower() != 'y':
                print("Cancelled.")
                return False
        
        account_repo.delete(account.id)
        print(f"Account deleted: {account_id}")
        return True


def verify_account(account_id: str):
    """Verify an account's API keys work."""
    init_database()
    
    with db_manager.session_scope() as session:
        account_repo = ExchangeAccountRepository(session)
        
        account = account_repo.get_by_id(uuid.UUID(account_id))
        if not account:
            print(f"Error: Account not found: {account_id}")
            return False
        
        # Decrypt keys
        try:
            access_key = kms_encryption.decrypt(account.access_key_encrypted)
            secret_key = kms_encryption.decrypt(account.secret_key_encrypted)
        except Exception as e:
            print(f"Error decrypting keys: {e}")
            return False
        
        # Test connection
        from src.exchanges import get_exchange
        from src.core.models import ExchangeType
        
        try:
            exchange_type = ExchangeType(account.exchange)
            exchange = get_exchange(exchange_type, access_key, secret_key)
            balance = exchange.get_account_balance()
            
            print(f"Account verified successfully!")
            print(f"  Exchange: {account.exchange}")
            print(f"  Balances: {len(balance.balances)} assets")
            
            # Show some balances
            for currency, bal in list(balance.balances.items())[:5]:
                print(f"    {currency}: {bal.available}")
            
            # Update status
            account_repo.update_status(account.id, is_valid_key=True, is_checked=True)
            return True
            
        except Exception as e:
            print(f"Verification failed: {e}")
            account_repo.update_status(account.id, is_valid_key=False)
            return False


def main():
    parser = argparse.ArgumentParser(
        description='Bowman Robot - Account Management'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Add account
    add_parser = subparsers.add_parser('add', help='Add a new exchange account')
    add_parser.add_argument('--exchange', '-e', required=True,
                          choices=['upbit', 'binance', 'korbit', 'bithumb'],
                          help='Exchange name')
    add_parser.add_argument('--access-key', '-a', required=True,
                          help='API access key')
    add_parser.add_argument('--secret-key', '-s', required=True,
                          help='API secret key')
    add_parser.add_argument('--risk-level', '-r', type=int, default=2,
                          choices=[0, 1, 2, 3, 4],
                          help='Risk level (0=conservative, 4=aggressive)')
    add_parser.add_argument('--cash-weight', '-c', type=float, default=0.0,
                          help='Cash weight (0.0-1.0)')
    add_parser.add_argument('--email', help='User email (optional)')
    
    # List accounts
    list_parser = subparsers.add_parser('list', help='List all accounts')
    list_parser.add_argument('--exchange', '-e',
                           choices=['upbit', 'binance', 'korbit', 'bithumb'],
                           help='Filter by exchange')
    
    # Update account
    update_parser = subparsers.add_parser('update', help='Update an account')
    update_parser.add_argument('account_id', help='Account ID')
    update_parser.add_argument('--risk-level', '-r', type=int,
                             choices=[0, 1, 2, 3, 4])
    update_parser.add_argument('--cash-weight', '-c', type=float)
    update_parser.add_argument('--active', type=lambda x: x.lower() == 'true',
                             help='Set active status (true/false)')
    
    # Delete account
    delete_parser = subparsers.add_parser('delete', help='Delete an account')
    delete_parser.add_argument('account_id', help='Account ID')
    delete_parser.add_argument('--force', '-f', action='store_true',
                             help='Skip confirmation')
    
    # Verify account
    verify_parser = subparsers.add_parser('verify', help='Verify account API keys')
    verify_parser.add_argument('account_id', help='Account ID')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    print(f"Database: {settings.db_type} ({settings.database_url})")
    print(f"Encryption: {settings.encryption_type}")
    print()
    
    if args.command == 'add':
        add_account(
            exchange=args.exchange,
            access_key=args.access_key,
            secret_key=args.secret_key,
            risk_level=args.risk_level,
            cash_weight=args.cash_weight,
            email=args.email
        )
    
    elif args.command == 'list':
        list_accounts(args.exchange)
    
    elif args.command == 'update':
        update_account(
            account_id=args.account_id,
            risk_level=args.risk_level,
            cash_weight=args.cash_weight,
            is_active=args.active
        )
    
    elif args.command == 'delete':
        delete_account(args.account_id, args.force)
    
    elif args.command == 'verify':
        verify_account(args.account_id)


if __name__ == "__main__":
    main()
