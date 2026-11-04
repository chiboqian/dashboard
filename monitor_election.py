#!/usr/bin/env python3
"""
monitor_election.py - Continuous Election Monitoring Daemon for PM2.
Aggregates live election results, balance of power, battleground calls,
and live wire dispatches every N seconds, keeping election_data.json
and election_dashboard.html updated with zero downtime.

Designed specifically for process managers like PM2:
- Clean graceful shutdown on SIGINT / SIGTERM (exit code 0).
- Immediate, unbuffered console output structured for `pm2 logs`.
- Optional integrated casting to Smart Display via `--cast`.
- Automatic retry on transient network/API hiccups.
"""

import os
import sys
import time
import json
import signal
import argparse
import subprocess
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# Force unbuffered stdout/stderr for PM2 log streaming
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

import fetch_elections

running = True
cast_proc = None

def handle_signal(sig, frame):
    global running, cast_proc
    sig_name = signal.Signals(sig).name
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [PM2:election-monitor] Received {sig_name}, initiating clean shutdown...", flush=True)
    running = False
    
    if cast_proc and cast_proc.poll() is None:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [PM2:election-monitor] Terminating cast_media process (PID: {cast_proc.pid})...", flush=True)
        try:
            cast_proc.terminate()
            cast_proc.wait(timeout=4)
        except Exception:
            try:
                cast_proc.kill()
            except Exception:
                pass
    
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [PM2:election-monitor] Shutdown complete. Exiting.", flush=True)
    sys.exit(0)

# Register signal traps for PM2
signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)
if hasattr(signal, "SIGHUP"):
    signal.signal(signal.SIGHUP, handle_signal)

def perform_election_cycle():
    """Run one aggregation cycle, update files, and output clear summary."""
    t0 = time.time()
    data = fetch_elections.aggregate_election_data()
    
    # 1. Save election_data.json
    with open(fetch_elections.OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        
    # 2. Save election_dashboard.html
    rendered_html = fetch_elections.generate_dashboard_html(data)
    with open(fetch_elections.OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(rendered_html)
        
    elapsed = time.time() - t0
    now_str = datetime.now().strftime("%H:%M:%S")
    
    # Extract high-level summary metrics
    bop = data.get("balance_of_power", {})
    sen = bop.get("senate", {})
    house = bop.get("house", {})
    nw = data.get("poll_status", {}).get("next_wave") or {}
    wires = len(data.get("wire_feed", []))
    battlegrounds = len(data.get("battlegrounds", []))
    
    sen_str = f"DEM {sen.get('dem', '-')} | GOP {sen.get('gop', '-')}"
    if sen.get('uncalled'):
        sen_str += f" (Uncalled: {sen.get('uncalled')})"
        
    house_str = f"DEM {house.get('dem', '-')} | GOP {house.get('gop', '-')}"
    if house.get('uncalled'):
        house_str += f" (Uncalled: {house.get('uncalled')})"
        
    wave_str = f"{nw.get('label', 'N/A')} ({nw.get('countdown_text', 'Active')})" if nw else "Final calls"

    print(f"[{now_str}] [PM2:election-monitor] ✓ Cycle finished in {elapsed:.1f}s", flush=True)
    print(f"  ├─ Senate:        {sen_str}", flush=True)
    print(f"  ├─ House:         {house_str}", flush=True)
    print(f"  ├─ Battlegrounds: {battlegrounds} key races tracked", flush=True)
    print(f"  ├─ Wire Feed:     {wires} live dispatches", flush=True)
    print(f"  └─ Next Wave:     {wave_str}", flush=True)

def main():
    global running, cast_proc
    
    parser = argparse.ArgumentParser(description="Election Monitoring Service for PM2")
    parser.add_argument("--interval", "-i", type=int, default=45, help="Refresh interval in seconds (default: 45)")
    parser.add_argument("--once", action="store_true", help="Run once and exit (e.g. for testing)")
    parser.add_argument("--cast", action="store_true", help="Also start and manage cast_media.py for smart display")
    parser.add_argument("--device", "-d", default="Lenovo Smart Display", help="Cast device name (default: 'Lenovo Smart Display')")
    parser.add_argument("--port", "-p", type=int, default=8888, help="Local HTTP port for casting (default: 8888)")
    args = parser.parse_args()
    
    print("=" * 65, flush=True)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting Election Monitor under PID {os.getpid()}", flush=True)
    print(f"Mode: {'Single Run' if args.once else f'Continuous Loop ({args.interval}s interval)'}", flush=True)
    print(f"Output: {fetch_elections.OUTPUT_JSON} & {fetch_elections.OUTPUT_HTML}", flush=True)
    if args.cast:
        print(f"Casting: Enabled -> '{args.device}' on port {args.port}", flush=True)
    print("=" * 65, flush=True)
    
    # Initial fetch
    try:
        perform_election_cycle()
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [Error in initial cycle]: {e}", file=sys.stderr, flush=True)
        
    if args.once:
        sys.exit(0)
        
    # Start cast process if requested
    cmd = []
    if args.cast:
        python_bin = sys.executable
        cast_script = os.path.join(SCRIPT_DIR, "cast_media.py")
        target_dashboard = os.path.join(SCRIPT_DIR, "output", "election_dashboard.html")
        cmd = [python_bin, "-u", cast_script, "-d", args.device, "-p", str(args.port), target_dashboard]
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Spawning cast process: {' '.join(cmd)}", flush=True)
        try:
            cast_proc = subprocess.Popen(cmd, cwd=SCRIPT_DIR)
        except Exception as e:
            print(f"[Error launching cast process]: {e}", file=sys.stderr, flush=True)

    # Main monitoring loop
    while running:
        # Sleep in 1s increments so PM2 signal delivery is immediate
        for _ in range(args.interval):
            if not running:
                break
            time.sleep(1)
            
        if not running:
            break
            
        # Check cast health if casting
        if args.cast and cast_proc and cast_proc.poll() is not None:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [Warn] Cast process exited (code: {cast_proc.returncode}). Restarting...", flush=True)
            try:
                cast_proc = subprocess.Popen(cmd, cwd=SCRIPT_DIR)
            except Exception as e:
                print(f"[Error restarting cast process]: {e}", file=sys.stderr, flush=True)
                
        try:
            perform_election_cycle()
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [Error in cycle]: {e}", file=sys.stderr, flush=True)

if __name__ == "__main__":
    main()
