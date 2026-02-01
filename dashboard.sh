#!/bin/bash

# Bowman Robot Dashboard Control Script
# Usage: ./dashboard.sh [start|stop|status|restart|update|logs]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/.dashboard.pid"
LOG_FILE="$SCRIPT_DIR/logs/dashboard.log"
PORT="${DASHBOARD_PORT:-8002}"

# Ensure logs directory exists
mkdir -p "$SCRIPT_DIR/logs"

start() {
    # Kill any existing process
    pkill -9 -f "src.api.run" 2>/dev/null || true
    sudo pkill -9 -f "src.api.run" 2>/dev/null || true
    rm -f "$PID_FILE"
    sleep 1

    echo "Starting Bowman Dashboard API server..."
    cd "$SCRIPT_DIR"
    
    # Activate virtual environment (create if not exists)
    if [ ! -d "$SCRIPT_DIR/venv" ]; then
        echo "Creating virtual environment..."
        python3 -m venv "$SCRIPT_DIR/venv"
        source "$SCRIPT_DIR/venv/bin/activate"
        echo "Installing dependencies..."
        pip install --upgrade pip > /dev/null 2>&1
        pip install -r "$SCRIPT_DIR/requirements.txt" > /dev/null 2>&1
    else
        source "$SCRIPT_DIR/venv/bin/activate"
    fi
    
    # Start API server in background (no sudo for local)
    nohup "$SCRIPT_DIR/venv/bin/python3" -m src.api.run --port "$PORT" > "$LOG_FILE" 2>&1 &
    PID=$!
    echo $PID > "$PID_FILE"
    
    # Wait a moment and check if it started
    sleep 3
    
    # Check health
    result=$(curl -s "http://localhost:$PORT/api/health" 2>/dev/null || echo "")
    if [[ "$result" == *"healthy"* ]]; then
        echo "✓ Dashboard started successfully!"
        echo ""
        echo "  URL: http://localhost:$PORT"
        echo "  Log: $LOG_FILE"
        echo ""
    else
        echo "✗ Failed to start dashboard. Check logs:"
        tail -20 "$LOG_FILE"
        return 1
    fi
}

stop() {
    echo "Stopping Dashboard..."
    pkill -9 -f "src.api.run" 2>/dev/null || true
    sudo pkill -9 -f "src.api.run" 2>/dev/null || true
    rm -f "$PID_FILE"
    sleep 1
    echo "✓ Dashboard stopped"
}

status() {
    result=$(curl -s "http://localhost:$PORT/api/health" 2>/dev/null || echo "")
    
    if [[ "$result" == *"healthy"* ]]; then
        echo "✓ Dashboard is running"
        echo "  URL: http://localhost:$PORT"
        echo "  API: Healthy"
        echo "$result" | python3 -m json.tool 2>/dev/null || echo "$result"
    else
        echo "✗ Dashboard is not running"
    fi
}

restart() {
    stop
    start
}

update() {
    echo "Pulling latest code..."
    cd "$SCRIPT_DIR"
    git pull
    
    echo ""
    restart
}

logs() {
    lines="${2:-50}"
    if [ -f "$LOG_FILE" ]; then
        if [ "$1" == "-f" ]; then
            tail -f "$LOG_FILE"
        else
            tail -n "$lines" "$LOG_FILE"
        fi
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
    update)
        update
        ;;
    logs)
        logs "$2" "$3"
        ;;
    *)
        echo "Bowman Robot Dashboard Control"
        echo ""
        echo "Usage: $0 {start|stop|status|restart|update|logs}"
        echo ""
        echo "Commands:"
        echo "  start   - Start the dashboard API server"
        echo "  stop    - Stop the dashboard API server"
        echo "  status  - Check if dashboard is running"
        echo "  restart - Restart the dashboard"
        echo "  update  - Git pull and restart"
        echo "  logs    - Show last 50 lines of logs"
        echo "  logs -f - Tail logs in real-time"
        echo ""
        echo "Environment:"
        echo "  DASHBOARD_PORT - Port number (default: 8002)"
        ;;
esac
