#!/bin/bash
cd /home/backtest01/reporting

echo "============================================="
echo "   CHOOSE A LIVE VIDEO STREAM TO CAST"
echo "============================================="
echo ""
echo "--- FINANCIAL NEWS ---"
echo "1) Bloomberg TV (US Markets)"
echo "2) Cheddar News (Finance/Tech)"
echo ""
echo "--- US NEWS ---"
echo "3) CBS News Live (24/7)"
echo ""
echo "--- UNBIASED WORLD NEWS ---"
echo "4) Al Jazeera English (Global News)"
echo "5) France 24 English (International News)"
echo ""
echo "--- WEATHER & OTHER ---"
echo "6) Sky News Weather Loop"
echo "7) NASA TV (Live Space Station)"
echo "8) Custom URL..."
echo ""
echo "q) Quit"
echo "============================================="
read -p "Select an option [1-8, q]: " choice

URL=""
case $choice in
    1) URL="https://www.bloomberg.com/media-manifest/streams/us.m3u8" ;;
    2) URL="https://hls.livecdn.io/cheddar.com/cheddar/playlist.m3u8" ;;
    3) URL="https://cbsn-us.cbsnstream.cbsnews.com/out/v1/55a8648e8f134e82a470f83d562deeca/master.m3u8" ;;
    4) URL="https://live-hls-web-aje.getaj.net/AJE/index.m3u8" ;;
    5) URL="https://static.france24.com/live/F24_EN_HI_HLS/live_web.m3u8" ;;
    6) URL="https://distro001-gb-hls1-prd.delivery.skycdp.com/easel_cdn/ngrp:weather_loop.stream_all/playlist.m3u8" ;;
    7) URL="https://ntv1.akamaized.net/hls/live/2014075/NASA-NTV1-HLS/master.m3u8" ;;
    8) 
        read -p "Enter custom M3U8 or MP4 URL: " URL
        ;;
    q|Q) 
        echo "Exiting."
        exit 0
        ;;
    *)
        echo "Invalid option. Exiting."
        exit 1
        ;;
esac

if [ -z "$URL" ]; then
    echo "No URL provided. Exiting."
    exit 1
fi

echo ""
echo "Stopping any currently running dashboard..."
./stop_dashboard.sh > /dev/null 2>&1
sleep 1

echo "Starting stream: $URL"
python3 play_video.py "$URL"
