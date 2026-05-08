#!/bin/bash

# Simple startup script for Foundation CRM
echo "🏛️  Louisiana Foundation CRM"
echo "================================"

# Change to correct directory
cd "$(dirname "$0")"

# Kill any existing streamlit processes
echo "🧹 Cleaning up existing processes..."
pkill -f streamlit 2>/dev/null || true
pkill -f crm_app.py 2>/dev/null || true
sleep 2

# Check database
echo "📊 Checking database..."
if [ ! -f "database/louisiana_foundations.db" ]; then
    echo "❌ Database not found!"
    exit 1
fi

# Activate virtual environment and start
echo "🚀 Starting CRM on port 8504..."
source venv/bin/activate

# Start streamlit with minimal config
streamlit run src/crm_app.py \
    --server.port 8504 \
    --server.headless true \
    --browser.gatherUsageStats false \
    --server.enableWebsocketCompression false \
    --server.runOnSave false

echo "👋 CRM stopped"