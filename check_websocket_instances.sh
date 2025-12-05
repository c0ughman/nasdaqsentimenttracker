#!/bin/bash
# Simple script to check and stop duplicate WebSocket collector instances

echo "🔍 Checking for running WebSocket collector instances..."
echo ""

# Find all processes running the websocket collector
PIDS=$(ps aux | grep "run_websocket_collector_v2" | grep -v grep | awk '{print $2}')

if [ -z "$PIDS" ]; then
    echo "✅ No instances found running"
    exit 0
fi

echo "⚠️  Found the following instances:"
ps aux | grep "run_websocket_collector_v2" | grep -v grep
echo ""

# Count instances
COUNT=$(echo "$PIDS" | wc -l | tr -d ' ')
echo "📊 Total instances found: $COUNT"
echo ""

if [ "$COUNT" -gt 1 ]; then
    echo "⚠️  Multiple instances detected! This can cause duplicate logging."
    echo ""
    read -p "Do you want to stop all instances? (y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "$PIDS" | xargs kill
        echo "🛑 Stopped all instances"
        sleep 2
        echo ""
        echo "Verifying..."
        REMAINING=$(ps aux | grep "run_websocket_collector_v2" | grep -v grep | wc -l | tr -d ' ')
        if [ "$REMAINING" -eq 0 ]; then
            echo "✅ All instances stopped successfully"
        else
            echo "⚠️  Some instances may still be running. Try: kill -9 $PIDS"
        fi
    else
        echo "❌ Cancelled. Instances still running."
    fi
else
    echo "✅ Only one instance running (this is normal)"
fi

