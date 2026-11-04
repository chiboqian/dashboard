#!/usr/bin/env bash
# ==============================================================================
# monitor_election.sh - PM2 Entrypoint for 2026 Election Monitoring
#
# Usage with PM2 (data monitor & HTML generation):
#   pm2 start monitor_election.sh --name "election-monitor"
#
# Usage with live casting:
#   pm2 start monitor_election.sh --name "election-monitor" -- --cast
#
# Check logs:
#   pm2 logs election-monitor
#
# Stop:
#   pm2 stop election-monitor
# ==============================================================================

set -eo pipefail

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
cd "$SCRIPT_DIR"

# Ensure venv Python and user binaries are in PATH
export PATH="$SCRIPT_DIR/venv/bin:$HOME/.local/bin:$PATH"
export PYTHONUNBUFFERED=1

PYTHON_BIN="$SCRIPT_DIR/venv/bin/python3"
if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi

# Execute Python directly so PM2 manages the PID and signals natively
exec "$PYTHON_BIN" "$SCRIPT_DIR/monitor_election.py" "$@"
