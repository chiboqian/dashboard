#!/bin/bash
# One-time (and re-runnable) setup: creates the venv, installs dependencies,
# and checks .env for the settings the dashboard scripts expect.
set -e
cd "$(dirname "$(readlink -f "$0")")"

# 1. Create the venv if it doesn't exist yet
if [ ! -x venv/bin/python3 ]; then
    echo "Creating virtualenv in $PWD/venv..."
    python3 -m venv venv
else
    echo "Virtualenv already exists at $PWD/venv."
fi

# 2. Install / update dependencies
echo "Installing dependencies from requirements.txt..."
venv/bin/pip install -q --upgrade pip
venv/bin/pip install -q -r requirements.txt

# 3. Check .env for expected keys
echo "----------------------------------------"
if [ ! -f .env ]; then
    echo "Warning: .env not found. Create it with the keys listed below."
fi
MISSING=0
for key in CLOUDFLARE_ACCOUNT_ID CLOUDFLARE_API_TOKEN CLOUDFLARE_D1_DATABASE_ID \
           R2_BUCKET_NAME R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY \
           TRADING_ENV_FILE DOMAIN CADDY_CLOUDFLARE_API_TOKEN; do
    if ! grep -q "^$key=" .env 2>/dev/null; then
        echo "Warning: $key is not set in .env"
        MISSING=1
    fi
done
[ "$MISSING" -eq 0 ] && echo ".env contains all expected keys."

# 4. Optional binaries used by start_dashboard.sh
[ -x ./caddy ] || echo "Note: ./caddy not found; start_dashboard.sh will fall back to local HTTP."

# 5. Suggested crontab entries
echo "----------------------------------------"
echo "Setup complete. To schedule the dashboard, add these to 'crontab -e':"
echo "0 7 * * * $PWD/start_dashboard.sh > /dev/null 2>&1"
echo "0 17 * * * $PWD/stop_dashboard.sh > /dev/null 2>&1"
