"""
Run the Bowman Robot Dashboard API server.
"""
import argparse
import logging
import uvicorn

from src.config.settings import settings


def setup_logging():
    """Configure logging."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    )
    # Suppress noisy loggers
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)


def main():
    parser = argparse.ArgumentParser(description='Bowman Robot Dashboard API Server')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Host to bind')
    parser.add_argument('--port', type=int, default=8000, help='Port to bind')
    parser.add_argument('--reload', action='store_true', help='Enable auto-reload')
    
    args = parser.parse_args()
    
    setup_logging()
    
    print(f"""
╔═══════════════════════════════════════════════════════════╗
║           Bowman Robot Dashboard API Server               ║
╠═══════════════════════════════════════════════════════════╣
║  API:       http://{args.host}:{args.port}                          
║  Database:  {settings.db_type}                                       
║  Reload:    {args.reload}                                         
╚═══════════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(
        "src.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info"
    )


if __name__ == "__main__":
    main()
