#!/bin/bash

# Detached startup for Foundation CRM - bypasses OpenClaw process management
echo "🔧 Starting Foundation CRM with process detachment"

cd "$(dirname "$0")"

# Clean up any existing processes
pkill -f "streamlit.*crm_app" 2>/dev/null || true
sleep 2

# Activate virtual environment
source venv/bin/activate

# Start with nohup to detach from parent process management
nohup python3 -m streamlit run src/crm_app.py \
    --server.port 8506 \
    --server.headless true \
    --browser.gatherUsageStats false \
    --server.enableWebsocketCompression false \
    --server.runOnSave false \
    > streamlit.log 2>&1 &

STREAMLIT_PID=$!
echo "✅ Streamlit started with PID: $STREAMLIT_PID"
echo "📄 Log file: streamlit.log"
echo "🌐 URL: http://localhost:8506"

# Wait a moment to verify startup
sleep 3

if ps -p $STREAMLIT_PID > /dev/null; then
    echo "✅ Process confirmed running"
    echo "🔍 To check status: ps -p $STREAMLIT_PID"
    echo "🛑 To stop: pkill -f streamlit"
else
    echo "❌ Process failed to start"
    echo "📄 Check streamlit.log for errors"
    tail -20 streamlit.log
fi