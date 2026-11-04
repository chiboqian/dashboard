#!/bin/bash
# Navigate to the reporting directory
cd "$(dirname "$(readlink -f "$0")")"

# Ensure output and logs directories exist
mkdir -p output logs

# Ensure user binaries (~/.local/bin for claude, agy) and project venv are in PATH
export PATH="$HOME/.local/bin:$PWD/venv/bin:$PATH"

# Terminate any previously running instances cleanly
./stop_dashboard.sh --force > /dev/null 2>&1
sleep 1

# Enable election night mode so scheduled 22:00 auto-stop does not kill it
touch .election_mode

# Extract domain and Cloudflare token from .env safely
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

if [ -n "$CADDY_CLOUDFLARE_API_TOKEN" ]; then
    export CLOUDFLARE_API_TOKEN=$CADDY_CLOUDFLARE_API_TOKEN
fi

# Start native Caddy reverse proxy
if [ -f "./caddy" ] && [ -n "$DOMAIN" ] && [ -n "$CLOUDFLARE_API_TOKEN" ]; then
    echo "Starting native Caddy reverse proxy for $DOMAIN on port 8443..."
    ./caddy start --config Caddyfile > logs/caddy.log 2>&1
    export PUBLIC_URL="https://$DOMAIN:8443"
else
    echo "Warning: Caddy requirements not met. Falling back to local HTTP IP."
    export PUBLIC_URL=""
fi

# 1. Pre-generate fresh 2026 election results & wire dispatches before casting
echo "Pre-generating fresh 2026 midterm election results & live wire dispatches..."
PYTHON_BIN="./venv/bin/python3"
if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi

"$PYTHON_BIN" ./fetch_elections.py

# 2. Start background election fetcher daemon (updates every 45s)
echo "Starting background election fetcher daemon..."
setsid "$PYTHON_BIN" -u ./fetch_elections.py --daemon --interval 45 > logs/election.log 2>&1 < /dev/null &
echo $! > .election_fetcher.pid

# 3. Start cast_media streaming election_dashboard.html via fast reliable local IP
echo "----------------------------------------"
echo "Starting election display cast to Lenovo Smart Display at $(date)"
echo "----------------------------------------"
setsid "$PYTHON_BIN" -u ./cast_media.py -d "Lenovo Smart Display" \
    "output/election_dashboard.html" > logs/cast_media.log 2>&1 < /dev/null &
echo $! > .cast_media.pid
disown -a 2>/dev/null || true

LOCAL_IP=$(hostname -I | awk '{print $1}')
echo "Election dashboard successfully launched in the background!"
echo "Viewing on Lenovo Smart Display via http://$LOCAL_IP:8888/election_dashboard.html"
