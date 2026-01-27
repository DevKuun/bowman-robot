#!/bin/bash

# Bowman Robot Dashboard Control Script
# Usage: ./dashboard.sh [start|stop|status|restart]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/.dashboard.pid"
LOG_FILE="$SCRIPT_DIR/logs/dashboard.log"
PORT="${DASHBOARD_PORT:-8002}"

# Ensure logs directory exists
mkdir -p "$SCRIPT_DIR/logs"

start() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Dashboard is already running (PID: $PID)"
            echo "Access: http://localhost:$PORT"
            return 1
        else
            rm -f "$PID_FILE"
        fi
    fi

    echo "Starting Bowman Dashboard API server..."
    cd "$SCRIPT_DIR"
    
    # Start API server in background
    nohup python3 -m src.api.run --port "$PORT" > "$LOG_FILE" 2>&1 &
    PID=$!
    echo $PID > "$PID_FILE"
    
    # Wait a moment and check if it started
    sleep 2
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "✓ Dashboard started successfully!"
        echo ""
        echo "  URL: http://localhost:$PORT"
        echo "  PID: $PID"
        echo "  Log: $LOG_FILE"
        echo ""
        echo "Use './dashboard.sh stop' to stop the server."
    else
        echo "✗ Failed to start dashboard. Check logs:"
        echo "  $LOG_FILE"
        rm -f "$PID_FILE"
        return 1
    fi
}

stop() {
    if [ ! -f "$PID_FILE" ]; then
        echo "Dashboard is not running (no PID file)"
        return 1
    fi

    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "Stopping Dashboard (PID: $PID)..."
        kill "$PID"
        
        # Wait for process to stop
        for i in {1..10}; do
            if ! ps -p "$PID" > /dev/null 2>&1; then
                break
            fi
            sleep 0.5
        done
        
        # Force kill if still running
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Force killing..."
            kill -9 "$PID"
        fi
        
        rm -f "$PID_FILE"
        echo "✓ Dashboard stopped"
    else
        echo "Dashboard is not running (process not found)"
        rm -f "$PID_FILE"
    fi
}

status() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "✓ Dashboard is running"
            echo "  PID:  $PID"
            echo "  URL:  http://localhost:$PORT"
            echo "  Log:  $LOG_FILE"
            
            # Check if API is responding
            if command -v curl &> /dev/null; then
                if curl -s "http://localhost:$PORT/api/health" > /dev/null 2>&1; then
                    echo "  API:  Healthy"
                else
                    echo "  API:  Not responding (may be starting up)"
                fi
            fi
        else
            echo "✗ Dashboard is not running (stale PID file)"
            rm -f "$PID_FILE"
        fi
    else
        echo "✗ Dashboard is not running"
    fi
}

restart() {
    stop
    sleep 1
    start
}

logs() {
    if [ -f "$LOG_FILE" ]; then
        tail -f "$LOG_FILE"
    else
        echo "No log file found: $LOG_FILE"
    fi
}

case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    status)
        status
        ;;
    restart)
        restart
        ;;
    logs)
        logs
        ;;
    *)
        echo "Bowman Robot Dashboard Control"
        echo ""
        echo "Usage: $0 {start|stop|status|restart|logs}"
        echo ""
        echo "Commands:"
        echo "  start   - Start the dashboard API server"
        echo "  stop    - Stop the dashboard API server"
        echo "  status  - Check if dashboard is running"
        echo "  restart - Restart the dashboard"
        echo "  logs    - View dashboard logs (tail -f)"
        echo ""
        echo "Environment:"
        echo "  DASHBOARD_PORT - Port number (default: 8002)"
        echo ""
        echo "Example:"
        echo "  ./dashboard.sh start"
        echo "  DASHBOARD_PORT=8080 ./dashboard.sh start"
        ;;
esac
