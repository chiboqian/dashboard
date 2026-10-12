#!/bin/bash
# Navigate to the reporting directory
cd "$(dirname "$(readlink -f "$0")")"

# Ensure user binaries (~/.local/bin for claude, agy) and project venv are in PATH
# (cron runs with a minimal environment like /usr/bin:/bin)
export PATH="$HOME/.local/bin:$PWD/venv/bin:$PATH"

# Parse arguments
INCLUDE_VIDEO=false
for arg in "$@"; do
    if [ "$arg" == "--video" ] || [ "$arg" == "-v" ]; then
        INCLUDE_VIDEO=true
    fi
done

# Terminate any previously running instances cleanly
./stop_dashboard.sh > /dev/null 2>&1
sleep 1

# Extract domain and Cloudflare token from .env safely
if [ -f .env ]; then
    while IFS='=' read -r key value; do
        if [[ ! "$key" =~ ^# ]] && [[ -n "$key" ]]; then
            # Remove optional surrounding quotes
            value="${value%\"}"
            value="${value#\"}"
            export "$key=$value"
        fi
    done < .env
fi

if [ -n "$CADDY_CLOUDFLARE_API_TOKEN" ]; then
    export CLOUDFLARE_API_TOKEN=$CADDY_CLOUDFLARE_API_TOKEN
fi

# Start native Caddy reverse proxy
if [ -f "./caddy" ] && [ -n "$DOMAIN" ] && [ -n "$CLOUDFLARE_API_TOKEN" ]; then
    echo "Starting native Caddy reverse proxy for $DOMAIN on port 8443..."
    nohup ./caddy run --config Caddyfile > caddy.log 2>&1 &
    echo $! > .caddy.pid
    export PUBLIC_URL="https://$DOMAIN:8443"
else
    echo "Warning: Caddy requirements not met. Falling back to local HTTP IP."
    export PUBLIC_URL=""
fi

# Setup video argument
VIDEO_ARG=""
if [ "$INCLUDE_VIDEO" = true ]; then
    VIDEO_ARG="--bottom-right /bloomberg_tv"
    echo "Video mode ENABLED."
else
    echo "Video mode DISABLED. (Pass --video to enable)"
fi

# 1. Pre-generate a fresh usage report before casting so display has up-to-date data
echo "Pre-generating fresh usage report..."
./unified_usage.py --quiet

# 2. Start the cast_media server in the background
echo "----------------------------------------"
echo "Starting dashboard cast at $(date)"
echo "----------------------------------------"
if [ -n "$PUBLIC_URL" ]; then
    nohup ./venv/bin/python3 -u ./cast_media.py -d "Lenovo Smart Display" \
        --left "https://dashboard.luna-strategy.com/account_status.html" \
        --right "usage_report.html" \
        $VIDEO_ARG \
        --public-url "$PUBLIC_URL" \
        --ratio 55:45 > cast_media.log 2>&1 &
else
    nohup ./venv/bin/python3 -u ./cast_media.py -d "Lenovo Smart Display" \
        --left "https://dashboard.luna-strategy.com/account_status.html" \
        --right "usage_report.html" \
        $VIDEO_ARG \
        --ratio 55:45 > cast_media.log 2>&1 &
fi
echo $! > .cast_media.pid

# 3. Start an infinite loop to seamlessly regenerate the usage report every 60 seconds
echo "Starting background usage report generator..."
nohup bash -c '
while true; do
    ./unified_usage.py --quiet
    sleep 60
done
' > /dev/null 2>&1 &
echo $! > .usage_loop.pid

echo "Dashboard successfully launched in the background!"
