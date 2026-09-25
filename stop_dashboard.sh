#!/bin/bash
echo "Stopping dashboard..."
pkill -TERM -f "cast_media.py"
pkill -f "unified_usage.py"
pkill -f "start_dashboard.sh"
echo "Done."
