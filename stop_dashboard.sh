#!/bin/bash
# Navigate to the reporting directory
cd "$(dirname "$(readlink -f "$0")")"

# Ensure user binaries and project venv are in PATH
export PATH="$HOME/.local/bin:$PWD/venv/bin:$PATH"

echo "Stopping dashboard..."

# 1. Stop cast_media.py gracefully first (so it can clean up its cast session)
if [ -f .cast_media.pid ]; then
    PID=$(cat .cast_media.pid 2>/dev/null)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        kill -TERM "$PID" 2>/dev/null
    fi
fi
pkill -TERM -f "cast_media.py" 2>/dev/null

# Wait up to 3 seconds for cast_media.py to gracefully exit
for i in {1..15}; do
    if ! pgrep -f "cast_media.py" > /dev/null 2>&1; then
        break
    fi
    sleep 0.2
done

# If cast_media.py is still alive, force kill it
if pgrep -f "cast_media.py" > /dev/null 2>&1; then
    pkill -9 -f "cast_media.py" 2>/dev/null
fi
rm -f .cast_media.pid

# 2. Directly verify Chromecast app state:
# If cast_media.py had previously crashed/disconnected, or failed to quit DashCast,
# send an explicit quit_app to the smart display so it returns to Backdrop.
DEVICE_NAME="Lenovo Smart Display"
PYTHON_BIN="./venv/bin/python3"
if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi

timeout 6s "$PYTHON_BIN" -c '
import pychromecast, os
device = "'"$DEVICE_NAME"'"
try:
    chromecasts, browser = pychromecast.get_listed_chromecasts(friendly_names=[device], timeout=3)
    if chromecasts:
        cast = chromecasts[0]
        cast.wait(timeout=3)
        # Quit if any app other than ambient Backdrop is active
        if cast.app_id and cast.app_id != "E8C28D3C":
            cast.quit_app()
        pychromecast.discovery.stop_discovery(browser)
except Exception:
    pass
' 2>/dev/null || true

# 3. Stop background usage generator loop and any running instances
if [ -f .usage_loop.pid ]; then
    PID=$(cat .usage_loop.pid 2>/dev/null)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        pkill -P "$PID" 2>/dev/null
        kill -9 "$PID" 2>/dev/null
    fi
    rm -f .usage_loop.pid
fi

for pid in $(pgrep -f "start_dashboard.sh"); do
    if [ "$pid" != "$$" ] && [ "$pid" != "$PPID" ]; then
        pkill -P "$pid" 2>/dev/null
        kill -9 "$pid" 2>/dev/null
    fi
done
pkill -9 -f "unified_usage.py" 2>/dev/null

# 4. Stop native Caddy reverse proxy
if [ -f "./caddy" ]; then
    ./caddy stop > /dev/null 2>&1 || true
fi
if [ -f .caddy.pid ]; then
    PID=$(cat .caddy.pid 2>/dev/null)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        kill -TERM "$PID" 2>/dev/null
    fi
    rm -f .caddy.pid
fi
pkill -f "caddy run" 2>/dev/null || true
sleep 0.5
if pgrep -f "caddy run" > /dev/null 2>&1; then
    pkill -9 -f "caddy run" 2>/dev/null
fi

# 5. Clean up any remaining sockets on dashboard ports (8000 and 8443)
fuser -k 8000/tcp 2>/dev/null || true
fuser -k 8443/tcp 2>/dev/null || true

echo "Done."
