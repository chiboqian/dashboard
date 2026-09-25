#!/bin/bash
cd /app

# 1. Start the cast_media server in the background
echo "----------------------------------------"
echo "Starting 3-pane dashboard cast from Docker at $(date)"
echo "----------------------------------------"

# We must NOT use force=True because we will have valid HTTPS now!
# We also assume the user passes the PUBLIC URL via an environment variable.
PUBLIC_URL=${PUBLIC_URL:-"http://localhost:8000"}

# Wait for usage_report to generate the first time so the server doesn't 404
./unified_usage.py --quiet

# Launch cast_media.py (we will modify cast_media.py to accept --base-url)
./cast_media.py -d "Lenovo Smart Display" \
    --left "https://dashboard.luna-strategy.com/account_status.html" \
    --right "usage_report.html" \
    --bottom-right "bloomberg_tv" \
    --public-url "$PUBLIC_URL" \
    --ratio 55:45 &
CAST_PID=$!

# 2. Regenerate usage report every 60 seconds
while true; do
    ./unified_usage.py --quiet
    sleep 60
done
