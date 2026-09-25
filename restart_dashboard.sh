#!/bin/bash
cd /home/backtest01/reporting

echo "Restarting dashboard services..."
./stop_dashboard.sh
sleep 2
./start_dashboard.sh
echo "Restart complete!"
