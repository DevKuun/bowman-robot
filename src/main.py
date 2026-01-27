"""
Main entry point for the Bowman Robot trading bot.
"""
import argparse
import asyncio
import logging
import sys
from typing import Optional

from src.core.models import ExchangeType
from src.workers.scheduler import run_scheduler
from src.infrastructure.database.connection import db_manager
from src.infrastructure.database.models import Base
from src.infrastructure.messaging.slack import slack_notifier
from src.config.settings import settings


def start_dashboard_server(port: int = 8000):
    """Start the dashboard API server in a background thread."""
    import threading
    import uvicorn
    
    def run_server():
        from src.api.main import app
        config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
        server = uvicorn.Server(config)
        server.run()
    
    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    return thread


def setup_logging(level: str = "INFO"):
    """Configure logging."""
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO
    
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('bowman-robot.log')
        ]
    )
    
    # Suppress noisy loggers
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)


def init_database():
    """Initialize database tables."""
    from sqlalchemy import inspect
    
    engine = db_manager.engine
    inspector = inspect(engine)
    
    # Check if tables exist
    existing_tables = inspector.get_table_names()
    required_tables = ['users', 'exchange_accounts', 'portfolio_weights', 'trades']
    
    missing_tables = [t for t in required_tables if t not in existing_tables]
    
    if missing_tables:
        logging.info(f"Creating missing tables: {missing_tables}")
        Base.metadata.create_all(engine)
        logging.info("Database tables created successfully")
    else:
        logging.info("All database tables exist")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Bowman Robot - Cryptocurrency Auto-Trading Bot'
    )
    
    parser.add_argument(
        '--exchange',
        type=str,
        choices=['upbit', 'binance', 'korbit', 'bithumb'],
        required=True,
        help='Exchange to trade on'
    )
    
    parser.add_argument(
        '--log-level',
        type=str,
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Logging level'
    )
    
    parser.add_argument(
        '--init-db',
        action='store_true',
        help='Initialize database tables and exit'
    )
    
    parser.add_argument(
        '--optimize-only',
        action='store_true',
        help='Run portfolio optimization only and exit'
    )
    
    parser.add_argument(
        '--paper',
        action='store_true',
        help='Run in paper trading mode (simulation)'
    )
    
    parser.add_argument(
        '--initial-balance',
        type=float,
        default=1000000,
        help='Initial balance for paper trading (default: 1,000,000)'
    )
    
    parser.add_argument(
        '--realistic',
        action='store_true',
        default=True,
        help='Enable realistic execution with slippage (default: enabled)'
    )
    
    parser.add_argument(
        '--no-realistic',
        action='store_true',
        help='Disable realistic execution (simple mode without slippage)'
    )
    
    parser.add_argument(
        '--with-dashboard',
        action='store_true',
        help='Start web dashboard alongside the bot'
    )
    
    parser.add_argument(
        '--dashboard-port',
        type=int,
        default=8000,
        help='Port for the web dashboard (default: 8000)'
    )
    
    return parser.parse_args()


async def run_portfolio_optimization(exchange_type: ExchangeType):
    """Run portfolio optimization once."""
    from src.workers.portfolio_worker import PortfolioWorker
    
    worker = PortfolioWorker(exchange_type)
    
    try:
        weights = await worker.run_optimization()
        await worker.save_weights(weights)
        
        logging.info("Portfolio optimization completed successfully")
        
        for risk_level, weight_dict in weights.items():
            logging.info(f"Risk {risk_level}: {len(weight_dict)} assets")
            for asset, weight in sorted(weight_dict.items(), key=lambda x: -x[1])[:5]:
                logging.info(f"  {asset}: {weight:.4f}")
                
    except Exception as e:
        logging.error(f"Portfolio optimization failed: {e}")
        raise


def main():
    """Main entry point."""
    args = parse_args()
    
    # Setup logging
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)
    
    logger.info(f"Starting Bowman Robot in {settings.app_env} mode")
    logger.info(f"Exchange: {args.exchange}")
    logger.info(f"Database: {settings.db_type} ({settings.database_url})")
    
    # Map exchange argument to enum
    exchange_map = {
        'upbit': ExchangeType.UPBIT,
        'binance': ExchangeType.BINANCE,
        'korbit': ExchangeType.KORBIT,
        'bithumb': ExchangeType.BITHUMB
    }
    exchange_type = exchange_map[args.exchange.lower()]
    
    # Initialize database if requested
    if args.init_db:
        logger.info("Initializing database...")
        init_database()
        logger.info("Database initialization complete")
        return
    
    # Always ensure database tables exist
    init_database()
    
    # Run portfolio optimization only if requested
    if args.optimize_only:
        logger.info("Running portfolio optimization only...")
        asyncio.run(run_portfolio_optimization(exchange_type))
        return
    
    # Start dashboard if requested
    dashboard_thread = None
    if args.with_dashboard:
        dashboard_thread = start_dashboard_server(args.dashboard_port)
        logger.info(f"Dashboard started at http://localhost:{args.dashboard_port}")
    
    # Run the trading scheduler
    try:
        if args.paper:
            realistic = args.realistic and not args.no_realistic
            mode_str = "REALISTIC" if realistic else "SIMPLE"
            logger.info(f"Running in PAPER TRADING mode ({mode_str})")
            logger.info(f"Initial balance: {args.initial_balance}")
            asyncio.run(run_scheduler(
                exchange_type, 
                paper_trading=True,
                initial_balance=args.initial_balance,
                realistic_execution=realistic,
                with_dashboard=args.with_dashboard
            ))
        else:
            asyncio.run(run_scheduler(exchange_type, with_dashboard=args.with_dashboard))
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        slack_notifier.send_error(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        db_manager.dispose()
        logger.info("Bowman Robot stopped")


if __name__ == "__main__":
    main()
