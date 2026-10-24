#!/bin/bash
# Navigate to the reporting directory
cd "$(dirname "$(readlink -f "$0")")"

# Ensure user binaries (~/.local/bin for claude, agy) and project venv are in PATH
export PATH="$HOME/.local/bin:$PWD/venv/bin:$PATH"

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

# 1. Pre-generate fresh market & world news before casting
echo "Pre-generating fresh market & world news headlines..."
PYTHON_BIN="./venv/bin/python3"
if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi

"$PYTHON_BIN" ./fetch_news.py

# 2. Start background news updater daemon (every 2 minutes / 120s)
echo "Starting background news fetcher daemon..."
nohup "$PYTHON_BIN" -u ./fetch_news.py --daemon --interval 120 > news.log 2>&1 &
echo $! > .news_fetcher.pid

# 3. Start cast_media streaming news_dashboard.html
echo "----------------------------------------"
echo "Starting news display cast at $(date)"
echo "----------------------------------------"
if [ -n "$PUBLIC_URL" ]; then
    nohup "$PYTHON_BIN" -u ./cast_media.py -d "Lenovo Smart Display" \
        "news_dashboard.html" \
        --public-url "$PUBLIC_URL" > cast_media.log 2>&1 &
else
    nohup "$PYTHON_BIN" -u ./cast_media.py -d "Lenovo Smart Display" \
        "news_dashboard.html" > cast_media.log 2>&1 &
fi
echo $! > .cast_media.pid
disown -a 2>/dev/null || true

echo "News dashboard successfully launched in the background!"
