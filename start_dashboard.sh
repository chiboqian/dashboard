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
pkill -f "caddy run" 2>/dev/null

sleep 1

# Extract domain and Cloudflare token from .env
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

if [ -n "$CADDY_CLOUDFLARE_API_TOKEN" ]; then
    export CLOUDFLARE_API_TOKEN=$CADDY_CLOUDFLARE_API_TOKEN
fi

# Start native Caddy reverse proxy
if [ -f "./caddy" ] && [ -n "$DOMAIN" ] && [ -n "$CLOUDFLARE_API_TOKEN" ]; then
    echo "Starting native Caddy reverse proxy for $DOMAIN..."
    ./caddy run --config Caddyfile > caddy.log 2>&1 &
    export PUBLIC_URL="https://$DOMAIN"
else
    echo "Warning: Caddy requirements not met. Falling back to local HTTP IP."
    export PUBLIC_URL=""
fi

# 1. Start the cast_media server in the background
echo "----------------------------------------"
echo "Starting 3-pane dashboard cast at $(date)"
echo "----------------------------------------"
if [ -n "$PUBLIC_URL" ]; then
    ./cast_media.py -d "Lenovo Smart Display" \
        --left "https://dashboard.luna-strategy.com/account_status.html" \
        --right "usage_report.html" \
        --bottom-right "bloomberg_tv" \
        --public-url "$PUBLIC_URL" \
        --ratio 55:45 &
else
    ./cast_media.py -d "Lenovo Smart Display" \
        --left "https://dashboard.luna-strategy.com/account_status.html" \
        --right "usage_report.html" \
        --bottom-right "bloomberg_tv" \
        --ratio 55:45 &
fi

# 2. Start an infinite loop to seamlessly regenerate the usage report every 60 seconds
echo "Starting background usage report generator..."
(
while true; do
    ./unified_usage.py --quiet
    sleep 60
done
) &

echo "Dashboard successfully launched in the background!"
