#!/bin/bash
# Navigate to the reporting directory
cd "$(dirname "$(readlink -f "$0")")"

# Ensure output and logs directories exist
mkdir -p output logs

# Ensure user binaries (~/.local/bin for claude, agy) and project venv are in PATH
# (cron runs with a minimal environment like /usr/bin:/bin)
export PATH="$HOME/.local/bin:$PWD/venv/bin:$PATH"

# Parse arguments
INCLUDE_VIDEO=false
ROTATE=90
while [ $# -gt 0 ]; do
    case "$1" in
        --video|-v)
            INCLUDE_VIDEO=true
            ;;
        --landscape)
            ROTATE=0
            ;;
        --portrait)
            ROTATE=90
            ;;
        --rotate)
            shift
            if [ -n "$1" ]; then
                ROTATE="$1"
            fi
            ;;
    esac
    shift
done

# Terminate any previously running instances cleanly
./stop_dashboard.sh --force > /dev/null 2>&1
sleep 1

# Extract domain and Cloudflare token from .env safely
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

if [ -n "$CADDY_CLOUDFLARE_API_TOKEN" ]; then
    export CLOUDFLARE_API_TOKEN=$CADDY_CLOUDFLARE_API_TOKEN
fi

# 1. Pre-generate a fresh usage report before casting so display has up-to-date data
echo "Pre-generating fresh usage report..."
./unified_usage.py --quiet

# 2. Start the cast_media server in the background (using fast, reliable local IP)
echo "----------------------------------------"
echo "Starting dashboard cast at $(date)"
echo "----------------------------------------"
if [ "$INCLUDE_VIDEO" = true ]; then
    echo "Video mode ENABLED (rotate=${ROTATE}deg)."
    setsid ./venv/bin/python3 -u ./cast_media.py -d "Lenovo Smart Display" \
        --left "https://dashboard.luna-strategy.com/account_status.html" \
        --right "output/usage_report.html" \
        --bottom-right /bloomberg_tv \
        --ratio 60:40 \
        --rotate "$ROTATE" > logs/cast_media.log 2>&1 < /dev/null &
else
    echo "Video mode DISABLED (portrait rotate=${ROTATE}deg; pass --landscape or --rotate 270 to adjust)."
    setsid ./venv/bin/python3 -u ./cast_media.py -d "Lenovo Smart Display" \
        --top "https://dashboard.luna-strategy.com/account_status.html" \
        --bottom "output/usage_report.html" \
        --ratio 91:9 \
        --rotate "$ROTATE" > logs/cast_media.log 2>&1 < /dev/null &
fi
echo $! > .cast_media.pid

# 3. Start an infinite loop to seamlessly regenerate Cloudflare usage every 2 minutes
echo "Starting background usage report generator..."
setsid bash -c '
while true; do
    ./unified_usage.py --quiet
    sleep 120
done
' > /dev/null 2>&1 < /dev/null &
echo $! > .usage_loop.pid
disown -a 2>/dev/null || true

echo "Dashboard successfully launched in the background!"
