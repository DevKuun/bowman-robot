#!/bin/bash
#
# Bowman Robot Server Control Script (Run on EC2)
# Usage: ./server.sh [command]
#
# Commands:
#   start    - Start the API server
#   stop     - Stop the API server
#   restart  - Restart the API server
#   status   - Check server health
#   update   - Git pull and restart
#   logs     - Show server logs
#   tail     - Tail server logs (live)
#

set -e

# Configuration
APP_PATH="/home/bowman-robot"
VENV_PYTHON="$APP_PATH/venv/bin/python3"
LOG_FILE="/tmp/bowman-api.log"
PORT=8002

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Start server
start_server() {
    if pgrep -f "src.api.run" > /dev/null; then
        log_warn "Server is already running"
        check_status
        return 0
    fi
    
    log_info "Starting server..."
    cd "$APP_PATH"
    nohup sudo "$VENV_PYTHON" -m src.api.run --port $PORT > "$LOG_FILE" 2>&1 &
    
    sleep 2
    check_status
}

# Stop server
stop_server() {
    log_info "Stopping server..."
    sudo pkill -9 -f "src.api.run" 2>/dev/null || true
    sleep 1
    
    if pgrep -f "src.api.run" > /dev/null; then
        log_error "Failed to stop server"
        return 1
    else
        log_info "Server stopped"
    fi
}

# Restart server
restart_server() {
    stop_server
    start_server
}

# Check status
check_status() {
    log_info "Checking server health..."
    
    result=$(curl -s "http://localhost:$PORT/api/health" 2>/dev/null || echo "FAILED")
    
    if [[ "$result" == *"healthy"* ]]; then
        echo -e "${GREEN}✅ Server is healthy${NC}"
        echo "$result" | python3 -m json.tool 2>/dev/null || echo "$result"
        return 0
    else
        echo -e "${RED}❌ Server is not responding${NC}"
        
        if pgrep -f "src.api.run" > /dev/null; then
            log_warn "Process is running but not responding"
        else
            log_error "Process is not running"
        fi
        return 1
    fi
}

# Update and restart
update_server() {
    log_info "Pulling latest code..."
    cd "$APP_PATH"
    git pull
    
    log_info "Restarting server..."
    restart_server
}

# Show logs
show_logs() {
    lines=${1:-50}
    log_info "Showing last $lines lines..."
    tail -n "$lines" "$LOG_FILE"
}

# Tail logs
tail_logs() {
    log_info "Tailing logs (Ctrl+C to stop)..."
    tail -f "$LOG_FILE"
}

# Main
case "${1:-help}" in
    start)
        start_server
        ;;
    stop)
        stop_server
        ;;
    restart)
        restart_server
        ;;
    status)
        check_status
        ;;
    update)
        update_server
        ;;
    logs)
        show_logs "${2:-50}"
        ;;
    tail)
        tail_logs
        ;;
    *)
        echo "Bowman Robot Server Control"
        echo ""
        echo "Usage: $0 {start|stop|restart|status|update|logs|tail}"
        echo ""
        echo "Commands:"
        echo "  start    - Start the API server"
        echo "  stop     - Stop the API server"
        echo "  restart  - Restart the API server"
        echo "  status   - Check server health"
        echo "  update   - Git pull and restart"
        echo "  logs [n] - Show last n lines of logs (default: 50)"
        echo "  tail     - Tail logs in real-time"
        exit 1
        ;;
esac
