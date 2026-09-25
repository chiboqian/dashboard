#!/bin/bash
# Navigate to the reporting directory
cd /home/backtest01/reporting

# Terminate any previously running instances of the script (excluding this exact one)
for pid in $(pgrep -f "start_dashboard.sh"); do
    if [ "$pid" != "$$" ] && [ "$pid" != "$PPID" ]; then
        kill -9 $pid 2>/dev/null
    fi
done

# Kill any existing dashboard casting instances to prevent socket conflicts
pkill -TERM -f "cast_media.py" 2>/dev/null
pkill -f "unified_usage.py" 2>/dev/null

sleep 1

# 1. Start the cast_media server in the background
echo "Starting 3-pane dashboard cast..."
./cast_media.py -d "Lenovo Smart Display" \
    --left "https://dashboard.luna-strategy.com/account_status.html" \
    --right "usage_report.html" \
    --bottom-right "bloomberg_tv" \
    --ratio 60:40 &

# 2. Start an infinite loop to seamlessly regenerate the usage report every 60 seconds
echo "Starting background usage report generator..."
while true; do
    ./unified_usage.py --quiet
    sleep 60
done
