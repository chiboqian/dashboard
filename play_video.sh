#!/bin/bash
cd /home/backtest01/reporting
# Kill any background dashboards so they don't fight for the screen
./stop_dashboard.sh > /dev/null 2>&1
sleep 1

# If a URL is passed, play it. Otherwise, default to Bloomberg TV HLS stream
URL=${1:-"https://www.bloomberg.com/media-manifest/streams/us.m3u8"}

echo "Starting full-screen video stream..."
python3 play_video.py "$URL"
