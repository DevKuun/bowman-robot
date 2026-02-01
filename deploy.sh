#!/bin/bash
#
# Bowman Robot Deploy Script
# Usage: ./deploy.sh [command]
#
# Commands:
#   build    - Build frontend only
#   push     - Git add, commit, push
#   deploy   - Pull code on server and restart
#   restart  - Restart server only
#   status   - Check server health
#   logs     - Show server logs
#   all      - Build + Push + Deploy (default)
#

set -e

# Configuration
KEY="/Users/kuun/development/dev-key.pem"
HOST="ubuntu@13.125.106.122"
REMOTE_PATH="/home/bowman-robot"
LOCAL_PATH="/Users/kuun/development/bowman-robot"
WEB_PATH="$LOCAL_PATH/web"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Build frontend
build_frontend() {
    log_info "Building frontend..."
    cd "$WEB_PATH"
    npm run build
    log_info "Frontend build complete!"
}

# Git push
git_push() {
    cd "$LOCAL_PATH"
    
    # Check if there are changes
    if [[ -z $(git status --porcelain) ]]; then
        log_warn "No changes to commit"
        return 0
    fi
    
    log_info "Committing changes..."
    git add -A
    
    # Get commit message
    read -p "Commit message (or press Enter for default): " msg
    if [[ -z "$msg" ]]; then
        msg="Update $(date '+%Y-%m-%d %H:%M')"
    fi
    
    git commit -m "$msg"
    
    log_info "Pushing to remote..."
    git push
    log_info "Push complete!"
}

# Deploy to server
deploy_server() {
    log_info "Pulling latest code on server..."
    ssh -i "$KEY" "$HOST" "cd $REMOTE_PATH && git pull"
    
    restart_server
}

# Restart server only
restart_server() {
    log_info "Stopping old server..."
    ssh -i "$KEY" "$HOST" "sudo pkill -9 -f 'src.api.run' 2>/dev/null || true"
    
    log_info "Starting new server..."
    ssh -f -i "$KEY" "$HOST" "cd $REMOTE_PATH && sudo $REMOTE_PATH/venv/bin/python3 -m src.api.run --port 8002 > /tmp/bowman-api.log 2>&1"
    
    sleep 2
    check_status
}

# Check server status
check_status() {
    log_info "Checking server health..."
    result=$(ssh -i "$KEY" "$HOST" "curl -s http://localhost:8002/api/health" 2>/dev/null || echo "FAILED")
    
    if [[ "$result" == *"healthy"* ]]; then
        echo -e "${GREEN}✅ Server is healthy${NC}"
        echo "$result" | python3 -m json.tool 2>/dev/null || echo "$result"
    else
        echo -e "${RED}❌ Server is not responding${NC}"
        log_error "Check logs with: ./deploy.sh logs"
        return 1
    fi
}

# Show logs
show_logs() {
    lines=${1:-50}
    log_info "Showing last $lines lines of server logs..."
    ssh -i "$KEY" "$HOST" "tail -$lines /tmp/bowman-api.log"
}

# Full deployment
full_deploy() {
    build_frontend
    git_push
    deploy_server
}

# Main
case "${1:-all}" in
    build)
        build_frontend
        ;;
    push)
        git_push
        ;;
    deploy)
        deploy_server
        ;;
    restart)
        restart_server
        ;;
    status)
        check_status
        ;;
    logs)
        show_logs "${2:-50}"
        ;;
    all)
        full_deploy
        ;;
    *)
        echo "Usage: $0 {build|push|deploy|restart|status|logs|all}"
        echo ""
        echo "Commands:"
        echo "  build    - Build frontend only"
        echo "  push     - Git add, commit, push"
        echo "  deploy   - Pull code on server and restart"
        echo "  restart  - Restart server only"
        echo "  status   - Check server health"
        echo "  logs [n] - Show last n lines of server logs (default: 50)"
        echo "  all      - Build + Push + Deploy (default)"
        exit 1
        ;;
esac
