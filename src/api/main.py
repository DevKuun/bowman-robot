"""
FastAPI main application for Bowman Robot Dashboard.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

from src.api.routes import bot, portfolio, trades, accounts, logs, websocket, sessions
from src.api.state import app_state
from src.config.settings import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting Bowman Robot Dashboard API")
    yield
    logger.info("Shutting down Bowman Robot Dashboard API")
    # Stop bot if running
    if app_state.bot_task:
        app_state.stop_bot()


app = FastAPI(
    title="Bowman Robot Dashboard",
    description="Cryptocurrency Auto-Trading Bot Dashboard",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(bot.router, prefix="/api/bot", tags=["Bot"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["Portfolio"])
app.include_router(trades.router, prefix="/api/trades", tags=["Trades"])
app.include_router(accounts.router, prefix="/api/accounts", tags=["Accounts"])
app.include_router(sessions.router, prefix="/api", tags=["Sessions"])
app.include_router(logs.router, prefix="/api/logs", tags=["Logs"])
app.include_router(websocket.router, prefix="/api/ws", tags=["WebSocket"])


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }


# Serve static files (React build)
import os
static_path = os.path.join(os.path.dirname(__file__), "../../web/dist")
if os.path.exists(static_path):
    app.mount("/assets", StaticFiles(directory=os.path.join(static_path, "assets")), name="assets")
    
    @app.get("/favicon.svg")
    async def serve_favicon():
        """Serve favicon."""
        favicon_path = os.path.join(static_path, "favicon.svg")
        if os.path.exists(favicon_path):
            return FileResponse(favicon_path, media_type="image/svg+xml")
        return {"error": "Favicon not found"}
    
    @app.get("/vite.svg")
    async def serve_vite_svg():
        """Serve vite.svg."""
        vite_path = os.path.join(static_path, "vite.svg")
        if os.path.exists(vite_path):
            return FileResponse(vite_path, media_type="image/svg+xml")
        return {"error": "File not found"}
    
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve React SPA for all non-API routes."""
        # Check if it's a static file first
        file_path = os.path.join(static_path, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        
        # Otherwise serve index.html for SPA routing
        index_path = os.path.join(static_path, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"error": "Frontend not built"}


def run_server(host: str = "0.0.0.0", port: int = 8000):
    """Run the API server."""
    uvicorn.run(
        "src.api.main:app",
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )


if __name__ == "__main__":
    run_server()
