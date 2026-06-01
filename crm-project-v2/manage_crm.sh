#!/bin/bash

# Foundation CRM Management Script
# Usage: ./manage_crm.sh [start|stop|status|restart|logs]

CRM_DIR="$(dirname "$0")"
PID_FILE="$CRM_DIR/crm.pid"
LOG_FILE="$CRM_DIR/streamlit.log"
PORT=8506

cd "$CRM_DIR"

start_crm() {
    if is_running; then
        echo "✅ Foundation CRM is already running (PID: $(cat $PID_FILE))"
        echo "🌐 URL: http://localhost:$PORT"
        return 0
    fi
    
    echo "🚀 Starting Foundation CRM..."
    
    # Clean up any orphaned processes
    pkill -f "streamlit.*crm_app" 2>/dev/null || true
    sleep 2
    
    # Start detached process
    source venv/bin/activate
    nohup python3 -m streamlit run src/crm_app.py \
        --server.port $PORT \
        --server.headless true \
        --browser.gatherUsageStats false \
        --server.enableWebsocketCompression false \
        --server.runOnSave false \
        > "$LOG_FILE" 2>&1 &
    
    echo $! > "$PID_FILE"
    
    # Verify startup
    sleep 3
    if is_running; then
        echo "✅ Foundation CRM started successfully!"
        echo "   PID: $(cat $PID_FILE)"
        echo "   🌐 URL: http://localhost:$PORT"
        echo "   📄 Logs: $LOG_FILE"
    else
        echo "❌ Failed to start CRM"
        show_logs
        return 1
    fi
}

stop_crm() {
    if ! is_running; then
        echo "ℹ️  Foundation CRM is not running"
        return 0
    fi
    
    PID=$(cat $PID_FILE)
    echo "🛑 Stopping Foundation CRM (PID: $PID)..."
    
    kill $PID 2>/dev/null
    sleep 2
    
    if ps -p $PID > /dev/null 2>&1; then
        echo "   Force killing process..."
        kill -9 $PID 2>/dev/null
        sleep 1
    fi
    
    rm -f "$PID_FILE"
    echo "✅ Foundation CRM stopped"
}

is_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat $PID_FILE)
        if ps -p $PID > /dev/null 2>&1; then
            return 0
        else
            rm -f "$PID_FILE"
        fi
    fi
    return 1
}

show_status() {
    if is_running; then
        PID=$(cat $PID_FILE)
        echo "✅ Foundation CRM is RUNNING"
        echo "   PID: $PID"
        echo "   🌐 URL: http://localhost:$PORT"
        echo "   📊 Status: $(curl -s -o /dev/null -w "%{http_code}" http://localhost:$PORT)"
        echo "   📄 Logs: $LOG_FILE"
        
        # Show database status
        if [ -f "database/louisiana_foundations.db" ]; then
            source venv/bin/activate
            python3 -c "
import sqlite3
conn = sqlite3.connect('database/louisiana_foundations.db')
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM foundations WHERE investment_assets >= 2000000')
count = cursor.fetchone()[0]
cursor.execute('SELECT SUM(investment_assets) FROM foundations WHERE investment_assets >= 2000000')
assets = cursor.fetchone()[0] or 0
print(f'   📊 Database: {count} foundations, \${assets/1e6:.0f}M assets')
conn.close()
"
        fi
    else
        echo "❌ Foundation CRM is NOT RUNNING"
        echo "   Use: ./manage_crm.sh start"
    fi
}

show_logs() {
    if [ -f "$LOG_FILE" ]; then
        echo "📄 Recent logs:"
        tail -20 "$LOG_FILE"
    else
        echo "📄 No log file found"
    fi
}

case "$1" in
    start)
        start_crm
        ;;
    stop)
        stop_crm
        ;;
    status)
        show_status
        ;;
    restart)
        stop_crm
        sleep 2
        start_crm
        ;;
    logs)
        show_logs
        ;;
    *)
        echo "Foundation CRM Management"
        echo "Usage: $0 {start|stop|status|restart|logs}"
        echo ""
        show_status
        ;;
esac