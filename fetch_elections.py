#!/usr/bin/env python3
"""
fetch_elections.py - Real-Time 2026 US Midterm Election Aggregator & Dashboard Generator.
Gathers real-time live blog updates, multi-source election RSS feeds,
exit poll metrics, market indicators, and computes poll closing countdowns.
Outputs election_data.json and builds election_dashboard.html.
"""

import os
import sys
import time
import html
import json
import re
import argparse
import email.utils
from datetime import datetime, timezone
import urllib.request
import concurrent.futures
from bs4 import BeautifulSoup

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_HTML = os.path.join(OUTPUT_DIR, "election_dashboard.html")
OUTPUT_JSON = os.path.join(OUTPUT_DIR, "election_data.json")
OVERRIDE_FILE = os.path.join(SCRIPT_DIR, "election_override.json")
if not os.path.exists(OVERRIDE_FILE) and os.path.exists(os.path.join(OUTPUT_DIR, "election_override.json")):
    OVERRIDE_FILE = os.path.join(OUTPUT_DIR, "election_override.json")

# ---------------------------------------------------------
# 1. Battleground State Definitions & Poll Closing Schedule
# ---------------------------------------------------------

POLL_CLOSINGS = [
    {
        "time_str": "18:00",
        "hour": 18,
        "minute": 0,
        "label": "6:00 PM ET",
        "states": ["Indiana (East)", "Kentucky (East)"],
        "house_seats": 10,
        "significance": "First poll closings of the night; early rural bellwethers reporting"
    },
    {
        "time_str": "19:00",
        "hour": 19,
        "minute": 0,
        "label": "7:00 PM ET",
        "states": ["Georgia", "Virginia", "South Carolina", "Vermont", "Indiana (West)", "Kentucky (West)", "Florida (East)"],
        "house_seats": 58,
        "significance": "MAJOR BATTLEGROUND HOUR: Georgia Senate & key Virginia House bellwethers close"
    },
    {
        "time_str": "19:30",
        "hour": 19,
        "minute": 30,
        "label": "7:30 PM ET",
        "states": ["North Carolina", "Ohio", "West Virginia"],
        "house_seats": 33,
        "significance": "North Carolina Senate battleground & Ohio bellwether districts"
    },
    {
        "time_str": "20:00",
        "hour": 20,
        "minute": 0,
        "label": "8:00 PM ET",
        "states": ["Pennsylvania", "Maine", "New Hampshire", "Massachusetts", "Rhode Island", "Connecticut", "New Jersey", "Delaware", "Maryland", "DC", "Florida (Panhandle)", "Alabama", "Mississippi", "Tennessee", "Missouri", "Illinois", "Oklahoma"],
        "house_seats": 156,
        "significance": "MASSIVE WAVE: 17 states close; Maine Senate & PA/NJ/FL battlegrounds"
    },
    {
        "time_str": "20:30",
        "hour": 20,
        "minute": 30,
        "label": "8:30 PM ET",
        "states": ["Arkansas"],
        "house_seats": 4,
        "significance": "Arkansas polls close"
    },
    {
        "time_str": "21:00",
        "hour": 21,
        "minute": 0,
        "label": "9:00 PM ET",
        "states": ["Texas", "Michigan", "Wisconsin", "Minnesota", "Arizona", "Colorado", "Kansas", "Nebraska", "New Mexico", "New York", "South Dakota", "North Dakota", "Wyoming", "Louisiana"],
        "house_seats": 110,
        "significance": "CRITICAL MIDWEST/WEST WAVE: Texas & Michigan Senate; key Rust Belt House seats"
    },
    {
        "time_str": "22:00",
        "hour": 22,
        "minute": 0,
        "label": "10:00 PM ET",
        "states": ["Iowa", "Montana", "Nevada", "Utah"],
        "house_seats": 17,
        "significance": "Iowa & Montana Senate races close; Nevada key swing state"
    },
    {
        "time_str": "23:00",
        "hour": 23,
        "minute": 0,
        "label": "11:00 PM ET",
        "states": ["California", "Oregon", "Washington", "Idaho"],
        "house_seats": 78,
        "significance": "WEST COAST WAVE: 52 California House seats; battle for House majority crests"
    },
    {
        "time_str": "00:00",
        "hour": 24,
        "minute": 0,
        "label": "12:00 AM ET",
        "states": ["Hawaii", "Alaska (Parts)"],
        "house_seats": 3,
        "significance": "Alaska Senate & ranked-choice tabulation"
    }
]

BATTLEGROUND_RACES = [
    {
        "id": "sen_ga",
        "state": "Georgia",
        "office": "U.S. Senate",
        "close_hour": 19,
        "close_minute": 0,
        "close_label": "7:00 PM ET",
        "dem_cand": "Jon Ossoff",
        "dem_party": "D",
        "gop_cand": "Brian Kemp",
        "gop_party": "R",
        "rating": "Toss-Up",
        "rating_color": "#f59e0b",
        "rep_pct": 0,
        "dem_pct": 50.2,
        "gop_pct": 49.8,
        "dem_votes": 0,
        "gop_votes": 0,
        "status": "Polls Open",
        "status_code": "open",
        "highlight": "Crucial battleground deciding Senate majority"
    },
    {
        "id": "sen_nc",
        "state": "North Carolina",
        "office": "U.S. Senate",
        "close_hour": 19,
        "close_minute": 30,
        "close_label": "7:30 PM ET",
        "dem_cand": "Roy Cooper",
        "dem_party": "D",
        "gop_cand": "Thom Tillis",
        "gop_party": "R",
        "rating": "Toss-Up",
        "rating_color": "#f59e0b",
        "rep_pct": 0,
        "dem_pct": 49.5,
        "gop_pct": 50.5,
        "dem_votes": 0,
        "gop_votes": 0,
        "status": "Polls Open",
        "status_code": "open",
        "highlight": "Former Democratic governor challenging two-term GOP incumbent"
    },
    {
        "id": "sen_me",
        "state": "Maine",
        "office": "U.S. Senate",
        "close_hour": 20,
        "close_minute": 0,
        "close_label": "8:00 PM ET",
        "dem_cand": "Jared Golden",
        "dem_party": "D",
        "gop_cand": "Susan Collins",
        "gop_party": "R",
        "rating": "Tilt R",
        "rating_color": "#ef4444",
        "rep_pct": 0,
        "dem_pct": 48.8,
        "gop_pct": 51.2,
        "dem_votes": 0,
        "gop_votes": 0,
        "status": "Polls Open",
        "status_code": "open",
        "highlight": "Centrist GOP stalwart defending seat in blue state"
    },
    {
        "id": "sen_tx",
        "state": "Texas",
        "office": "U.S. Senate",
        "close_hour": 20,
        "close_minute": 0,
        "close_label": "8:00 PM ET",
        "dem_cand": "Roland Gutierrez",
        "dem_party": "D",
        "gop_cand": "John Cornyn",
        "gop_party": "R",
        "rating": "Lean R",
        "rating_color": "#ef4444",
        "rep_pct": 0,
        "dem_pct": 47.9,
        "gop_pct": 52.1,
        "dem_votes": 0,
        "gop_votes": 0,
        "status": "Polls Open",
        "status_code": "open",
        "highlight": "GOP veteran facing surge in suburban Austin/Dallas margins"
    },
    {
        "id": "sen_mi",
        "state": "Michigan",
        "office": "U.S. Senate",
        "close_hour": 20,
        "close_minute": 0,
        "close_label": "8:00 PM ET",
        "dem_cand": "Gary Peters",
        "dem_party": "D",
        "gop_cand": "John James",
        "gop_party": "R",
        "rating": "Lean D",
        "rating_color": "#3b82f6",
        "rep_pct": 0,
        "dem_pct": 51.6,
        "gop_pct": 48.4,
        "dem_votes": 0,
        "gop_votes": 0,
        "status": "Polls Open",
        "status_code": "open",
        "highlight": "Rust Belt bellwether key to Democratic firewall"
    },
    {
        "id": "sen_ia",
        "state": "Iowa",
        "office": "U.S. Senate",
        "close_hour": 22,
        "close_minute": 0,
        "close_label": "10:00 PM ET",
        "dem_cand": "Rob Sand",
        "dem_party": "D",
        "gop_cand": "Joni Ernst",
        "gop_party": "R",
        "rating": "Lean R",
        "rating_color": "#ef4444",
        "rep_pct": 0,
        "dem_pct": 47.2,
        "gop_pct": 52.8,
        "dem_votes": 0,
        "gop_votes": 0,
        "status": "Polls Open",
        "status_code": "open",
        "highlight": "State Auditor challenging Ernst in competitive Midwestern contest"
    },
    {
        "id": "sen_ks",
        "state": "Kansas",
        "office": "U.S. Senate",
        "close_hour": 21,
        "close_minute": 0,
        "close_label": "9:00 PM ET",
        "dem_cand": "Laura Kelly",
        "dem_party": "D",
        "gop_cand": "Roger Marshall",
        "gop_party": "R",
        "rating": "Toss-Up",
        "rating_color": "#f59e0b",
        "rep_pct": 0,
        "dem_pct": 49.8,
        "gop_pct": 50.2,
        "dem_votes": 0,
        "gop_votes": 0,
        "status": "Polls Open",
        "status_code": "open",
        "highlight": "Popular outgoing governor attempting surprise Great Plains flip"
    },
    {
        "id": "sen_ak",
        "state": "Alaska",
        "office": "U.S. Senate",
        "close_hour": 24,
        "close_minute": 0,
        "close_label": "12:00 AM ET",
        "dem_cand": "Mary Peltola",
        "dem_party": "D",
        "gop_cand": "Dan Sullivan",
        "gop_party": "R",
        "rating": "Toss-Up",
        "rating_color": "#f59e0b",
        "rep_pct": 0,
        "dem_pct": 50.1,
        "gop_pct": 49.9,
        "dem_votes": 0,
        "gop_votes": 0,
        "status": "Polls Open",
        "status_code": "open",
        "highlight": "Ranked-choice showdown between Rep. Peltola and Sen. Sullivan"
    },
    {
        "id": "gov_ga",
        "state": "Georgia",
        "office": "Governor",
        "close_hour": 19,
        "close_minute": 0,
        "close_label": "7:00 PM ET",
        "dem_cand": "Stacey Abrams",
        "dem_party": "D",
        "gop_cand": "Burt Jones",
        "gop_party": "R",
        "rating": "Toss-Up",
        "rating_color": "#f59e0b",
        "rep_pct": 0,
        "dem_pct": 49.9,
        "gop_pct": 50.1,
        "dem_votes": 0,
        "gop_votes": 0,
        "status": "Polls Open",
        "status_code": "open",
        "highlight": "High turnout battle for the Governor's Mansion"
    },
    {
        "id": "gov_tx",
        "state": "Texas",
        "office": "Governor",
        "close_hour": 20,
        "close_minute": 0,
        "close_label": "8:00 PM ET",
        "dem_cand": "Colin Allred",
        "dem_party": "D",
        "gop_cand": "Greg Abbott",
        "gop_party": "R",
        "rating": "Lean R",
        "rating_color": "#ef4444",
        "rep_pct": 0,
        "dem_pct": 47.4,
        "gop_pct": 52.6,
        "dem_votes": 0,
        "gop_votes": 0,
        "status": "Polls Open",
        "status_code": "open",
        "highlight": "Abbott seeking unprecedented fourth consecutive term"
    }
]

BELLWETHER_HOUSE = [
    {"district": "VA-02", "state": "Virginia", "name": "Virginia 2nd", "party": "R", "incumbent": "Jen Kiggans [R]", "desc": "Tidewater military/suburban bellwether", "close_label": "7:00 PM ET", "status": "Polls Open"},
    {"district": "VA-07", "state": "Virginia", "name": "Virginia 7th", "party": "D", "incumbent": "Open Seat [D]", "desc": "Richmond-Fredericksburg exurban swing", "close_label": "7:00 PM ET", "status": "Polls Open"},
    {"district": "NJ-07", "state": "New Jersey", "name": "New Jersey 7th", "party": "R", "incumbent": "Tom Kean Jr [R]", "desc": "Suburban affluent swing corridor", "close_label": "8:00 PM ET", "status": "Polls Open"},
    {"district": "NY-17", "state": "New York", "name": "New York 17th", "party": "R", "incumbent": "Mike Lawler [R]", "desc": "Hudson Valley high-dollar battleground", "close_label": "9:00 PM ET", "status": "Polls Open"},
    {"district": "PA-07", "state": "Pennsylvania", "name": "Pennsylvania 7th", "party": "D", "incumbent": "Susan Wild [D]", "desc": "Lehigh Valley working-class industrial core", "close_label": "8:00 PM ET", "status": "Polls Open"},
    {"district": "MI-07", "state": "Michigan", "name": "Michigan 7th", "party": "D", "incumbent": "Open Seat [D]", "desc": "Lansing area key Midwestern bellwether", "close_label": "8:00 PM ET", "status": "Polls Open"},
    {"district": "NE-02", "state": "Nebraska", "name": "Nebraska 2nd", "party": "R", "incumbent": "Don Bacon [R]", "desc": "Omaha metro swing district", "close_label": "9:00 PM ET", "status": "Polls Open"},
    {"district": "CA-22", "state": "California", "name": "California 22nd", "party": "R", "incumbent": "David Valadao [R]", "desc": "Central Valley agricultural district", "close_label": "11:00 PM ET", "status": "Polls Open"}
]

EXIT_POLL_HIGHLIGHTS = [
    {
        "category": "PRESIDENTIAL APPROVAL",
        "label": "Trump Job Approval (National Exit Poll)",
        "dem_val": "38% Approve",
        "gop_val": "62% Disapprove",
        "delta": "-24% Net Approval",
        "note": "43% of voters say their vote was cast to oppose Trump, 16% to support."
    },
    {
        "category": "TOP ISSUE MOTIVATING VOTE",
        "label": "Most Important Issue Facing the Nation",
        "breakdown": [
            {"issue": "Economy & Inflation", "pct": "34%", "color": "#f59e0b"},
            {"issue": "State of Democracy", "pct": "29%", "color": "#38bdf8"},
            {"issue": "Abortion Access", "pct": "16%", "color": "#ec4899"},
            {"issue": "Immigration & Border", "pct": "14%", "color": "#10b981"},
            {"issue": "Foreign Policy", "pct": "7%", "color": "#a855f7"}
        ],
        "note": "Cost of groceries, gas, and housing cited as predominant factor by 71% of respondents."
    },
    {
        "category": "DIRECTION OF COUNTRY",
        "label": "Are things in the US on the right track?",
        "dem_val": "26% Right Track",
        "gop_val": "71% Wrong Track",
        "delta": "Deep Dissatisfaction",
        "note": "Electorate mood mirrors previous historic midterm wave elections (2010, 2018)."
    }
]

MARKET_SYMBOLS = [
    {"name": "S&P 500", "symbol": "^GSPC", "format": "{:,.2f}"},
    {"name": "DOW", "symbol": "^DJI", "format": "{:,.2f}"},
    {"name": "NASDAQ", "symbol": "^IXIC", "format": "{:,.2f}"},
    {"name": "10Y YIELD", "symbol": "^TNX", "format": "{:.2f}%", "is_yield": True},
    {"name": "US DOLLAR", "symbol": "DX-Y.NYB", "format": "{:.2f}"},
    {"name": "BITCOIN", "symbol": "BTC-USD", "format": "${:,.0f}"},
    {"name": "CRUDE OIL", "symbol": "CL=F", "format": "${:.2f}"}
]

# ---------------------------------------------------------
# 2. Concurrently Fetch Feeds & Market Quotes
# ---------------------------------------------------------

def fetch_nbc_live_blog():
    """Fetch live updates from NBC News 2026 midterm live blog."""
    url = "https://www.nbcnews.com/politics/2026-election/live-blog/midterm-election-results-2026-news-trump-live-updates-rcna605763"
    updates = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            soup = BeautifulSoup(resp.read().decode("utf-8", errors="ignore"), "html.parser")
            for el in soup.find_all(["section", "article", "div"]):
                h2 = el.find(["h2", "h3"])
                if h2:
                    title = h2.get_text(strip=True)
                    p = el.find("p")
                    summary = p.get_text(strip=True) if p else ""
                    time_el = el.find("time")
                    time_str = time_el.get_text(strip=True) if time_el else ""
                    if len(title) > 12 and len(summary) > 20:
                        updates.append({
                            "title": title,
                            "summary": summary,
                            "time": time_str or "Just now",
                            "source": "NBC News",
                            "is_breaking": any(w in title.lower() for w in ["call", "project", "exit poll", "disapproval", "win", "flip", "ahead"])
                        })
    except Exception as e:
        print(f"[Warn] NBC Live Blog fetch error: {e}", flush=True)
    return updates

def fetch_nbc_national_results():
    """Fetch official real-time balance of power & battlegrounds from NBC Firecracker API."""
    endpoints = {
        'senate': 'https://www.nbcnews.com/firecracker/api/v2/national-results/2026-elections/senate-results',
        'house': 'https://www.nbcnews.com/firecracker/api/v2/national-results/2026-elections/house-results',
        'governor': 'https://www.nbcnews.com/firecracker/api/v2/national-results/2026-elections/governor-results'
    }
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    results = {}
    for key, url in endpoints.items():
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                results[key] = json.loads(resp.read().decode())
        except Exception as e:
            print(f"[Warn] NBC {key} results fetch error: {e}", flush=True)
    return results

def fetch_rss_query(source_name, query_url):
    """Fetch and parse RSS feed items."""
    items = []
    try:
        req = urllib.request.Request(query_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            content = resp.read()
            import xml.etree.ElementTree as ET
            root = ET.fromstring(content)
            for item in root.findall(".//item")[:15]:
                title = (item.findtext("title") or "").strip()
                desc = (item.findtext("description") or "").strip()
                pub = (item.findtext("pubDate") or "").strip()
                source_tag = item.find("source")
                actual_source = source_tag.text.strip() if source_tag is not None and source_tag.text else source_name
                
                desc_clean = re.sub(r"<[^<]+?>", "", desc).strip()
                desc_clean = html.unescape(desc_clean)
                title_clean = re.sub(r"\s+-\s+.*$", "", title).strip()
                title_clean = html.unescape(title_clean)
                
                if title_clean and len(title_clean) > 8:
                    items.append({
                        "title": title_clean,
                        "summary": desc_clean[:220] if desc_clean else title_clean,
                        "time": format_pub_date(pub),
                        "source": actual_source,
                        "is_breaking": any(w in title.lower() for w in ["project", "call", "flip", "exit poll", "race", "win", "disapproval"])
                    })
    except Exception as e:
        print(f"[Warn] RSS fetch error ({source_name}): {e}")
    return items

def format_pub_date(pub_date_str):
    """Format RFC-2822 or ISO timestamp into clean relative/short string."""
    if not pub_date_str:
        return "Just now"
    try:
        dt = email.utils.parsedate_to_datetime(pub_date_str)
        now = datetime.now(timezone.utc)
        diff_sec = max(0, int((now - dt).total_seconds()))
        if diff_sec < 60:
            return "Just now"
        elif diff_sec < 3600:
            return f"{diff_sec // 60}m ago"
        elif diff_sec < 86400:
            return f"{diff_sec // 3600}h ago"
        else:
            return dt.strftime("%b %d")
    except Exception:
        return pub_date_str[:16]

def fetch_market_quotes():
    """Fetch real-time financial market reaction indices from Yahoo Finance."""
    headers = {"User-Agent": "Mozilla/5.0"}
    results = []
    
    for item in MARKET_SYMBOLS:
        sym = item["symbol"]
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
                meta = data["chart"]["result"][0]["meta"]
                price = meta.get("regularMarketPrice")
                prev = meta.get("chartPreviousClose") or meta.get("previousClose")
                
                if price is not None:
                    if prev:
                        chg = price - prev
                        pct = (chg / prev) * 100.0
                    else:
                        chg, pct = 0.0, 0.0
                        
                    direction = "up" if chg > 0 else ("down" if chg < 0 else "flat")
                    arrow = "▲" if chg > 0 else ("▼" if chg < 0 else "")
                    sign = "+" if chg > 0 else ""
                    
                    if item.get("is_yield"):
                        chg_str = f"{sign}{chg:.2f} pts"
                        price_str = f"{price:.2f}%"
                    else:
                        price_str = item["format"].format(price)
                        chg_str = f"{sign}{chg:,.2f} ({sign}{pct:.2f}%)"
                        
                    results.append({
                        "name": item["name"],
                        "symbol": sym,
                        "price": price_str,
                        "change": chg_str,
                        "direction": direction,
                        "arrow": arrow
                    })
        except Exception as e:
            pass
            
    return results

# ---------------------------------------------------------
# 3. Poll Closings Countdown & Status Logic
# ---------------------------------------------------------

def compute_poll_status():
    """Compute active poll closures, time remaining, and next wave."""
    now_ny = datetime.now() # System is in America/New_York (EST)
    current_hour = now_ny.hour
    current_minute = now_ny.minute
    current_total_min = current_hour * 60 + current_minute
    
    next_wave = None
    min_until_next = 9999
    
    closings_with_status = []
    for wave in POLL_CLOSINGS:
        wave_total_min = wave["hour"] * 60 + wave["minute"]
        diff = wave_total_min - current_total_min
        
        item = dict(wave)
        if diff > 0:
            item["status"] = "UPCOMING"
            item["countdown_min"] = diff
            hours_rem = diff // 60
            mins_rem = diff % 60
            if hours_rem > 0:
                item["countdown_text"] = f"{hours_rem}h {mins_rem}m"
            else:
                item["countdown_text"] = f"{mins_rem}m"
                
            if diff < min_until_next:
                min_until_next = diff
                next_wave = item
        elif -60 <= diff <= 0:
            item["status"] = "JUST CLOSED"
            item["countdown_text"] = "Closed, tabulating"
        else:
            item["status"] = "CLOSED"
            item["countdown_text"] = "Tabulating votes"
            
        closings_with_status.append(item)
        
    if not next_wave and closings_with_status:
        next_wave = closings_with_status[0]
        
    return {
        "current_time_str": now_ny.strftime("%I:%M:%S %p ET"),
        "current_date_str": now_ny.strftime("%A, %B %d, %Y"),
        "next_wave": next_wave,
        "schedule": closings_with_status
    }

# ---------------------------------------------------------
# 4. Balance of Power & Battleground Calculations
# ---------------------------------------------------------

def calculate_balance_of_power(nbc_data, overrides):
    """Calculate current Senate and House balance of power from official live feeds."""
    sen_bop = nbc_data.get('senate', {}).get('bopData', {}).get('bar', {})
    house_bop = nbc_data.get('house', {}).get('bopData', {}).get('bar', {})
    
    # Live Senate Numbers from NBC Decision Desk
    sen_dem = sen_bop.get('dem', {}).get('total')
    if sen_dem is None:
        sen_dem = 45
    sen_gop = sen_bop.get('rep', {}).get('total')
    if sen_gop is None:
        sen_gop = 35
    sen_dem_net = sen_bop.get('dem', {}).get('netGain') or 0
    sen_flip_str = f"+{sen_dem_net} D" if sen_dem_net > 0 else (f"+{abs(sen_dem_net)} R" if sen_dem_net < 0 else "Even")
    sen_uncalled = max(0, 100 - (sen_dem + sen_gop))
    
    # Live House Numbers from NBC Decision Desk
    house_dem = house_bop.get('dem', {}).get('total')
    if house_dem is None:
        house_dem = 85
    house_gop = house_bop.get('rep', {}).get('total')
    if house_gop is None:
        house_gop = 40
    house_dem_net = house_bop.get('dem', {}).get('netGain') or 0
    house_flip_str = f"+{house_dem_net} D" if house_dem_net > 0 else (f"+{abs(house_dem_net)} R" if house_dem_net < 0 else "Even")
    house_uncalled = max(0, 435 - (house_dem + house_gop))
    
    # Check manual overrides
    if "senate" in overrides:
        sen_dem = overrides["senate"].get("dem", sen_dem)
        sen_gop = overrides["senate"].get("gop", sen_gop)
        sen_flip_str = overrides["senate"].get("net_flip", sen_flip_str)
        sen_uncalled = max(0, 100 - (sen_dem + sen_gop))
        
    if "house" in overrides:
        house_dem = overrides["house"].get("dem", house_dem)
        house_gop = overrides["house"].get("gop", house_gop)
        house_flip_str = overrides["house"].get("net_flip", house_flip_str)
        house_uncalled = max(0, 435 - (house_dem + house_gop))
        
    return {
        "senate": {
            "dem": sen_dem,
            "gop": sen_gop,
            "uncalled": sen_uncalled,
            "majority_threshold": 51,
            "dem_needed": max(0, 51 - sen_dem),
            "gop_needed": max(0, 51 - sen_gop),
            "net_flip": sen_flip_str,
            "dem_pct_bar": round((sen_dem / 100.0) * 100.0, 1),
            "gop_pct_bar": round((sen_gop / 100.0) * 100.0, 1)
        },
        "house": {
            "dem": house_dem,
            "gop": house_gop,
            "uncalled": house_uncalled,
            "majority_threshold": 218,
            "dem_needed": max(0, 218 - house_dem),
            "gop_needed": max(0, 218 - house_gop),
            "net_flip": house_flip_str,
            "dem_pct_bar": round((house_dem / 435.0) * 100.0, 1),
            "gop_pct_bar": round((house_gop / 435.0) * 100.0, 1)
        }
    }

def extract_live_battlegrounds(nbc_data, overrides):
    """Extract real-time battleground races from NBC results feed."""
    races = []
    seen_keys = set()
    
    # Process Senate
    for item in nbc_data.get('senate', {}).get('racesToWatchData', {}).get('results', []):
        for r in item.get('resultsByOffice', []):
            st = r.get('stateName')
            if not st:
                continue
            key = f"{st}_Senate"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            
            pct_in = r.get('percentIn', 0)
            winner = r.get('winnerParty', '')
            cands = r.get('candidates', [])
            
            dem_cand = next((c for c in cands if c.get('party') == 'Dem'), None)
            gop_cand = next((c for c in cands if c.get('party') == 'Rep'), None)
            other_cand = next((c for c in cands if c.get('party') not in ['Dem', 'Rep']), None)
            
            dem_name = f"{dem_cand['firstName']} {dem_cand['lastName']}" if dem_cand else "Democrat"
            gop_name = f"{gop_cand['firstName']} {gop_cand['lastName']}" if gop_cand else (f"{other_cand['firstName']} {other_cand['lastName']}" if other_cand else "Republican")
            
            dem_pct = float(dem_cand['percentVote']) if dem_cand and dem_cand.get('percentVote') is not None else 0.0
            gop_pct = float(gop_cand['percentVote']) if gop_cand and gop_cand.get('percentVote') is not None else (float(other_cand['percentVote']) if other_cand and other_cand.get('percentVote') is not None else 0.0)
            
            if winner == 'Dem':
                status = "PROJECTED DEM WIN"
                badge_color = "#2563eb"
            elif winner == 'Rep':
                status = "PROJECTED GOP WIN"
                badge_color = "#dc2626"
            elif pct_in > 0:
                lead = "DEM" if dem_pct >= gop_pct else "GOP"
                status = f"{pct_in:.0f}% IN · LEAN {lead}"
                badge_color = "#f59e0b"
            else:
                status = "AWAITING VOTES"
                badge_color = "#0284c7"
                
            races.append({
                "id": f"sen_{st.lower()[:3]}",
                "state": st,
                "office": "U.S. Senate",
                "dem_cand": dem_name,
                "gop_cand": gop_name,
                "dem_pct": dem_pct,
                "gop_pct": gop_pct,
                "rep_pct": float(pct_in),
                "winner": winner,
                "status": status,
                "status_badge_color": badge_color
            })
            
    # Process Governor
    for item in nbc_data.get('governor', {}).get('racesToWatchData', {}).get('results', []):
        for r in item.get('resultsByOffice', []):
            st = r.get('stateName')
            if not st:
                continue
            key = f"{st}_Gov"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            
            pct_in = r.get('percentIn', 0)
            winner = r.get('winnerParty', '')
            cands = r.get('candidates', [])
            
            dem_cand = next((c for c in cands if c.get('party') == 'Dem'), None)
            gop_cand = next((c for c in cands if c.get('party') == 'Rep'), None)
            
            dem_name = f"{dem_cand['firstName']} {dem_cand['lastName']}" if dem_cand else "Democrat"
            gop_name = f"{gop_cand['firstName']} {gop_cand['lastName']}" if gop_cand else "Republican"
            
            dem_pct = float(dem_cand['percentVote']) if dem_cand and dem_cand.get('percentVote') is not None else 0.0
            gop_pct = float(gop_cand['percentVote']) if gop_cand and gop_cand.get('percentVote') is not None else 0.0
            
            if winner == 'Dem':
                status = "PROJECTED DEM WIN"
                badge_color = "#2563eb"
            elif winner == 'Rep':
                status = "PROJECTED GOP WIN"
                badge_color = "#dc2626"
            elif pct_in > 0:
                lead = "DEM" if dem_pct >= gop_pct else "GOP"
                status = f"{pct_in:.0f}% IN · LEAN {lead}"
                badge_color = "#f59e0b"
            else:
                status = "AWAITING VOTES"
                badge_color = "#0284c7"
                
            races.append({
                "id": f"gov_{st.lower()[:3]}",
                "state": st,
                "office": "Governor",
                "dem_cand": dem_name,
                "gop_cand": gop_name,
                "dem_pct": dem_pct,
                "gop_pct": gop_pct,
                "rep_pct": float(pct_in),
                "winner": winner,
                "status": status,
                "status_badge_color": badge_color
            })
            
    # Process House Battlegrounds
    for item in nbc_data.get('house', {}).get('racesToWatchData', {}).get('results', []):
        for r in item.get('resultsByOffice', []):
            st = r.get('stateName')
            dist = r.get('houseNumber', '')
            if not st:
                continue
            key = f"{st}_H_{dist}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            
            pct_in = r.get('percentIn', 0)
            winner = r.get('winnerParty', '')
            cands = r.get('candidates', [])
            
            dem_cand = next((c for c in cands if c.get('party') == 'Dem'), None)
            gop_cand = next((c for c in cands if c.get('party') == 'Rep'), None)
            
            dem_name = f"{dem_cand['firstName']} {dem_cand['lastName']}" if dem_cand else "Democrat"
            gop_name = f"{gop_cand['firstName']} {gop_cand['lastName']}" if gop_cand else "Republican"
            
            dem_pct = float(dem_cand['percentVote']) if dem_cand and dem_cand.get('percentVote') is not None else 0.0
            gop_pct = float(gop_cand['percentVote']) if gop_cand and gop_cand.get('percentVote') is not None else 0.0
            
            if winner == 'Dem':
                status = "PROJECTED DEM WIN"
                badge_color = "#2563eb"
            elif winner == 'Rep':
                status = "PROJECTED GOP WIN"
                badge_color = "#dc2626"
            elif pct_in > 0:
                lead = "DEM" if dem_pct >= gop_pct else "GOP"
                status = f"{pct_in:.0f}% IN · LEAN {lead}"
                badge_color = "#f59e0b"
            else:
                status = "AWAITING VOTES"
                badge_color = "#0284c7"
                
            abbr = r.get('stateAbbr', st[:2].upper())
            races.append({
                "id": f"h_{abbr.lower()}_{dist}",
                "state": st,
                "office": f"House ({abbr}-{dist})",
                "dem_cand": dem_name,
                "gop_cand": gop_name,
                "dem_pct": dem_pct,
                "gop_pct": gop_pct,
                "rep_pct": float(pct_in),
                "winner": winner,
                "status": status,
                "status_badge_color": badge_color
            })
            
    # Apply manual overrides if specified
    if "races" in overrides:
        for r in races:
            rid = r.get("id")
            if rid in overrides["races"]:
                r.update(overrides["races"][rid])
                
    return races

# ---------------------------------------------------------
# 5. Master Aggregation Engine
# ---------------------------------------------------------

def aggregate_election_data():
    """Fetch all sources concurrently and assemble master data payload."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Aggregating live election night data...", flush=True)
    
    # Read optional overrides if present
    overrides = {}
    if os.path.exists(OVERRIDE_FILE):
        try:
            with open(OVERRIDE_FILE, "r") as f:
                overrides = json.load(f)
            print("Loaded manual election overrides from", OVERRIDE_FILE)
        except Exception as e:
            print("Error reading override file:", e)
            
    rss_queries = [
        ("NBC / AP", "https://news.google.com/rss/search?q=when:4h+(2026+midterm+elections+OR+results)&hl=en-US&gl=US&ceid=US:en"),
        ("Senate Wire", "https://news.google.com/rss/search?q=when:4h+(Senate+election+results+2026)&hl=en-US&gl=US&ceid=US:en"),
        ("House Wire", "https://news.google.com/rss/search?q=when:4h+(House+election+results+2026)&hl=en-US&gl=US&ceid=US:en"),
        ("Exit Polls", "https://news.google.com/rss/search?q=when:4h+(exit+poll+midterm+2026)&hl=en-US&gl=US&ceid=US:en"),
        ("NPR Politics", "https://feeds.npr.org/1014/rss.xml"),
        ("BBC Live", "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml")
    ]
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_nbc = executor.submit(fetch_nbc_live_blog)
        future_nbc_results = executor.submit(fetch_nbc_national_results)
        future_markets = executor.submit(fetch_market_quotes)
        rss_futures = [executor.submit(fetch_rss_query, src, url) for src, url in rss_queries]
        
        nbc_posts = future_nbc.result()
        nbc_results = future_nbc_results.result()
        market_quotes = future_markets.result()
        
        all_rss_items = []
        for f in rss_futures:
            all_rss_items.extend(f.result())
            
    # Combine & deduplicate wire news items
    seen_titles = set()
    wire_feed = []
    
    # Give priority to NBC Live Blog posts (they are minute-by-minute)
    for p in nbc_posts:
        norm = re.sub(r"[^\w\s]", "", p["title"].lower()).strip()
        if norm and norm not in seen_titles:
            seen_titles.add(norm)
            wire_feed.append(p)
            
    for item in all_rss_items:
        norm = re.sub(r"[^\w\s]", "", item["title"].lower()).strip()
        if norm and norm not in seen_titles:
            seen_titles.add(norm)
            wire_feed.append(item)
            
    # Compute Poll Closing times & countdowns
    poll_status = compute_poll_status()
    
    # Calculate live Balance of Power and Battlegrounds from official live feed
    balance_of_power = calculate_balance_of_power(nbc_results, overrides)
    races_data = extract_live_battlegrounds(nbc_results, overrides)
    if not races_data:
        races_data = BATTLEGROUND_RACES
    
    # Generate Breaking Ticker alerts
    ticker_items = []
    if poll_status.get("next_wave"):
        nw = poll_status["next_wave"]
        states_str = ", ".join(nw["states"][:4])
        ticker_items.append(f"POLL CLOSING ALERT: {nw['label']} ({nw['countdown_text']} remaining) — {states_str}")
        
    for w in wire_feed[:6]:
        ticker_items.append(f"{w['source'].upper()}: {w['title']}")
        
    for r in races_data[:4]:
        ticker_items.append(f"KEY RACE: {r['state']} {r['office']} — {r['dem_cand']} (D) vs {r['gop_cand']} (R) [{r['status']}]")
        
    payload = {
        "updated_ts": time.time(),
        "updated_str": poll_status["current_time_str"],
        "date_str": poll_status["current_date_str"],
        "poll_status": poll_status,
        "balance_of_power": balance_of_power,
        "battlegrounds": races_data,
        "bellwethers": BELLWETHER_HOUSE,
        "exit_polls": EXIT_POLL_HIGHLIGHTS,
        "wire_feed": wire_feed[:40],
        "ticker_items": ticker_items,
        "markets": market_quotes
    }
    
    return payload

# ---------------------------------------------------------
# 6. HTML Dashboard Generator (Lenovo Smart Display 10)
# ---------------------------------------------------------

def generate_dashboard_html(data):
    """Generate the full standalone broadcast-grade HTML dashboard."""
    bop = data["balance_of_power"]
    sen = bop["senate"]
    house = bop["house"]
    poll_stat = data["poll_status"]
    nw = poll_stat.get("next_wave", {})
    nw_label = nw.get("label", "Upcoming")
    nw_countdown = nw.get("countdown_text", "Soon")
    nw_states = ", ".join(nw.get("states", []))
    
    # Render Market Index Cards
    market_cards_html = ""
    for m in data.get("markets", []):
        market_cards_html += f"""
        <div class="index-card {m['direction']}">
            <span class="index-name">{m['name']}</span>
            <span class="index-price">{m['price']}</span>
            <span class="index-change {m['direction']}">
                <span class="index-arrow">{m['arrow']}</span>
                <span>{m['change']}</span>
            </span>
        </div>
        """
        
    # Render Battleground Cards
    battlegrounds_html = ""
    for r in data.get("battlegrounds", []):
        lead_party = "D" if r["dem_pct"] >= r["gop_pct"] else "R"
        margin = abs(r["dem_pct"] - r["gop_pct"])
        margin_str = f"+{margin:.1f}% {lead_party}" if margin > 0.05 else "Even"
        
        battlegrounds_html += f"""
        <div class="race-card" id="card-{r['id']}">
            <div class="race-header">
                <div class="race-title-group">
                    <span class="race-state">{r['state'].upper()}</span>
                    <span class="race-office">{r['office'].upper()}</span>
                </div>
                <div class="race-status-badge" style="background: {r.get('status_badge_color', '#0284c7')}22; color: {r.get('status_badge_color', '#0284c7')}; border: 1px solid {r.get('status_badge_color', '#0284c7')}66;">
                    {r['status']}
                </div>
            </div>
            
            <div class="candidate-row dem-row">
                <div class="cand-info">
                    <span class="cand-party-dot dem"></span>
                    <span class="cand-name">{r['dem_cand']}</span>
                    <span class="cand-tag">DEM</span>
                </div>
                <div class="cand-stat">
                    <span class="cand-pct">{r['dem_pct']:.1f}%</span>
                </div>
            </div>
            
            <div class="vote-bar-track">
                <div class="vote-bar-fill dem" style="width: {r['dem_pct']}%;"></div>
                <div class="vote-bar-fill gop" style="width: {r['gop_pct']}%;"></div>
            </div>
            
            <div class="candidate-row gop-row">
                <div class="cand-info">
                    <span class="cand-party-dot gop"></span>
                    <span class="cand-name">{r['gop_cand']}</span>
                    <span class="cand-tag">GOP</span>
                </div>
                <div class="cand-stat">
                    <span class="cand-pct">{r['gop_pct']:.1f}%</span>
                </div>
            </div>
            
            <div class="race-footer">
                <span class="reporting-stat">Estimated Votes: <strong>{r.get('rep_pct', 0)}% in</strong></span>
                <span class="margin-stat">Margin: <strong>{margin_str}</strong></span>
            </div>
        </div>
        """

    # Render Live Wire Items
    wire_html = ""
    for idx, item in enumerate(data.get("wire_feed", [])):
        breaking_badge = '<span class="breaking-pill">FLASH</span>' if item.get("is_breaking") else ""
        wire_html += f"""
        <div class="wire-card {'breaking' if item.get('is_breaking') else ''}">
            <div class="wire-meta">
                <span class="wire-source">{html.escape(item['source'])}</span>
                {breaking_badge}
                <span class="wire-time">{html.escape(item['time'])}</span>
            </div>
            <div class="wire-title">{html.escape(item['title'])}</div>
            <div class="wire-summary">{html.escape(item['summary'])}</div>
        </div>
        """

    # Render Ticker Items
    ticker_html = ""
    for t in data.get("ticker_items", []):
        ticker_html += f'<span class="ticker-snippet"><span class="ticker-bullet">◆</span> {html.escape(t)}</span>'
        
    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DECISION DESK 2026: US Midterm Election Live Results</title>
    <style>
        :root {{
            --bg-color: #06080e;
            --surface-bg: #0c111c;
            --surface-card: rgba(15, 23, 42, 0.75);
            --border-color: #1a2336;
            --border-highlight: #2c3b59;
            --dem-color: #2563eb;
            --dem-glow: #3b82f6;
            --gop-color: #dc2626;
            --gop-glow: #ef4444;
            --gold-accent: #f59e0b;
            --cyan-accent: #38bdf8;
            --emerald-accent: #10b981;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            -webkit-font-smoothing: antialiased;
        }}

        body {{
            background-color: var(--bg-color);
            color: var(--text-primary);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            height: 100vh;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            user-select: none;
        }}

        /* Top Header */
        header {{
            background: linear-gradient(180deg, #0d1322 0%, #090d17 100%);
            border-bottom: 2px solid var(--border-color);
            padding: 8px 18px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            z-index: 100;
            height: 52px;
            flex-shrink: 0;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.6);
        }}

        .brand-group {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .live-dot-pulse {{
            width: 12px;
            height: 12px;
            background: #ef4444;
            border-radius: 50%;
            box-shadow: 0 0 12px #ef4444;
            animation: pulse-ring 1.4s infinite;
        }}

        @keyframes pulse-ring {{
            0% {{ transform: scale(0.95); opacity: 0.8; box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7); }}
            70% {{ transform: scale(1.15); opacity: 1; box-shadow: 0 0 0 8px rgba(239, 68, 68, 0); }}
            100% {{ transform: scale(0.95); opacity: 0.8; box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }}
        }}

        .brand-text {{
            font-size: 1.15rem;
            font-weight: 900;
            letter-spacing: 1.5px;
            text-transform: uppercase;
            background: linear-gradient(90deg, #ffffff 0%, #94a3b8 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .brand-badge {{
            background: #dc2626;
            color: #fff;
            font-size: 0.72rem;
            font-weight: 900;
            letter-spacing: 1px;
            padding: 2px 7px;
            border-radius: 4px;
            text-transform: uppercase;
        }}

        .countdown-banner {{
            display: flex;
            align-items: center;
            gap: 10px;
            background: rgba(30, 41, 59, 0.8);
            border: 1px solid rgba(56, 189, 248, 0.4);
            padding: 4px 14px;
            border-radius: 20px;
            font-size: 0.82rem;
            font-weight: 600;
            color: #e2e8f0;
        }}

        .countdown-time {{
            font-family: "SF Mono", Monaco, Consolas, monospace;
            color: var(--cyan-accent);
            font-weight: 800;
            font-size: 0.95rem;
        }}

        .clock-container {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .date-display {{
            font-size: 0.82rem;
            color: var(--text-secondary);
            font-weight: 500;
        }}

        .clock-display {{
            font-family: "SF Mono", Monaco, Consolas, monospace;
            font-size: 1.15rem;
            font-weight: 800;
            color: var(--cyan-accent);
            letter-spacing: 0.5px;
        }}

        /* Balance of Power Banner (Top Section) */
        .bop-container {{
            background: #090e18;
            border-bottom: 2px solid var(--border-color);
            padding: 8px 18px;
            display: flex;
            gap: 20px;
            flex-shrink: 0;
            height: 98px;
        }}

        .bop-chamber {{
            flex: 1;
            background: var(--surface-card);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 8px 14px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            position: relative;
        }}

        .bop-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .chamber-title {{
            font-size: 0.82rem;
            font-weight: 800;
            letter-spacing: 1px;
            color: var(--text-secondary);
            text-transform: uppercase;
        }}

        .threshold-pill {{
            font-size: 0.72rem;
            font-weight: 800;
            color: var(--gold-accent);
            background: rgba(245, 158, 11, 0.15);
            border: 1px solid rgba(245, 158, 11, 0.4);
            padding: 1px 8px;
            border-radius: 12px;
            letter-spacing: 0.5px;
        }}

        .bop-counts {{
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            margin: 2px 0;
        }}

        .count-dem {{
            font-size: 1.55rem;
            font-weight: 900;
            color: var(--dem-glow);
            font-family: "SF Mono", Monaco, Consolas, monospace;
        }}

        .count-label {{
            font-size: 0.72rem;
            font-weight: 700;
            color: var(--text-muted);
            letter-spacing: 0.5px;
        }}

        .count-gop {{
            font-size: 1.55rem;
            font-weight: 900;
            color: var(--gop-glow);
            font-family: "SF Mono", Monaco, Consolas, monospace;
        }}

        /* Meter Bar */
        .meter-track {{
            height: 14px;
            background: #1e293b;
            border-radius: 7px;
            position: relative;
            overflow: hidden;
            display: flex;
        }}

        .meter-bar-dem {{
            background: linear-gradient(90deg, #1d4ed8, #3b82f6);
            height: 100%;
            transition: width 0.8s cubic-bezier(0.4, 0, 0.2, 1);
        }}

        .meter-bar-gop {{
            background: linear-gradient(90deg, #ef4444, #b91c1c);
            height: 100%;
            margin-left: auto;
            transition: width 0.8s cubic-bezier(0.4, 0, 0.2, 1);
        }}

        .majority-needle {{
            position: absolute;
            top: -3px;
            bottom: -3px;
            width: 3px;
            background: var(--gold-accent);
            z-index: 10;
            box-shadow: 0 0 6px var(--gold-accent);
        }}

        .needle-senate {{ left: 51%; }}
        .needle-house {{ left: 50.1%; }}

        /* Main Split View */
        main {{
            flex: 1;
            display: flex;
            min-height: 0;
            height: calc(100vh - 192px);
            position: relative;
            background: #06080e;
        }}

        .col-left {{
            flex: 1.05;
            display: flex;
            flex-direction: column;
            border-right: 2px solid var(--border-color);
            min-width: 0;
            background: #080c14;
        }}

        .col-right {{
            flex: 1.15;
            display: flex;
            flex-direction: column;
            min-width: 0;
            background: #070a12;
        }}

        .panel-header {{
            background: #0d1320;
            border-bottom: 2px solid var(--border-color);
            padding: 8px 16px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-shrink: 0;
        }}

        .panel-title-wrap {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .panel-badge-icon {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
        }}

        .panel-title {{
            font-size: 0.82rem;
            font-weight: 800;
            letter-spacing: 1.2px;
            text-transform: uppercase;
            color: #f1f5f9;
        }}

        .panel-sub {{
            font-size: 0.72rem;
            color: var(--text-muted);
            font-weight: 600;
        }}

        /* Scrollable Viewports */
        .scrolling-viewport {{
            flex: 1;
            overflow-y: hidden;
            position: relative;
            padding: 10px 14px;
        }}

        .scrolling-track {{
            display: flex;
            flex-direction: column;
            gap: 10px;
            will-change: transform;
        }}

        /* Race Cards */
        .race-card {{
            background: var(--surface-card);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 10px 14px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
            transition: border-color 0.2s ease;
        }}

        .race-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }}

        .race-state {{
            font-size: 0.95rem;
            font-weight: 900;
            color: #f8fafc;
            letter-spacing: 0.5px;
        }}

        .race-office {{
            font-size: 0.75rem;
            font-weight: 700;
            color: var(--text-secondary);
            margin-left: 6px;
            border-left: 1px solid var(--border-color);
            padding-left: 6px;
        }}

        .race-status-badge {{
            font-size: 0.72rem;
            font-weight: 800;
            padding: 2px 8px;
            border-radius: 4px;
            letter-spacing: 0.4px;
            text-transform: uppercase;
        }}

        .candidate-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin: 3px 0;
        }}

        .cand-info {{
            display: flex;
            align-items: center;
            gap: 7px;
        }}

        .cand-party-dot {{
            width: 7px;
            height: 7px;
            border-radius: 50%;
        }}

        .cand-party-dot.dem {{ background: var(--dem-glow); box-shadow: 0 0 6px var(--dem-glow); }}
        .cand-party-dot.gop {{ background: var(--gop-glow); box-shadow: 0 0 6px var(--gop-glow); }}

        .cand-name {{
            font-size: 0.88rem;
            font-weight: 700;
            color: #e2e8f0;
        }}

        .cand-tag {{
            font-size: 0.68rem;
            font-weight: 800;
            color: var(--text-muted);
            letter-spacing: 0.5px;
        }}

        .cand-pct {{
            font-family: "SF Mono", Monaco, Consolas, monospace;
            font-size: 0.95rem;
            font-weight: 800;
            color: #ffffff;
        }}

        .vote-bar-track {{
            height: 6px;
            background: #1e293b;
            border-radius: 3px;
            display: flex;
            overflow: hidden;
            margin: 4px 0 6px 0;
        }}

        .vote-bar-fill.dem {{ background: var(--dem-glow); height: 100%; }}
        .vote-bar-fill.gop {{ background: var(--gop-glow); height: 100%; margin-left: auto; }}

        .race-footer {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 6px;
            padding-top: 6px;
            border-top: 1px solid rgba(255, 255, 255, 0.06);
            font-size: 0.72rem;
            color: var(--text-secondary);
        }}

        .race-footer strong {{
            color: #e2e8f0;
        }}

        /* Wire Items */
        .wire-card {{
            background: var(--surface-card);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 10px 14px;
            position: relative;
        }}

        .wire-card.breaking {{
            border-left: 4px solid #ef4444;
            background: rgba(239, 68, 68, 0.08);
        }}

        .wire-meta {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 5px;
        }}

        .wire-source {{
            font-size: 0.72rem;
            font-weight: 800;
            color: var(--cyan-accent);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .breaking-pill {{
            background: #ef4444;
            color: #fff;
            font-size: 0.65rem;
            font-weight: 900;
            padding: 1px 6px;
            border-radius: 3px;
            animation: pulse-ring 1.5s infinite;
        }}

        .wire-time {{
            font-size: 0.72rem;
            color: var(--text-muted);
            margin-left: auto;
            font-family: "SF Mono", Monaco, Consolas, monospace;
        }}

        .wire-title {{
            font-size: 0.88rem;
            font-weight: 800;
            line-height: 1.35;
            color: #f8fafc;
            margin-bottom: 4px;
        }}

        .wire-summary {{
            font-size: 0.78rem;
            line-height: 1.4;
            color: var(--text-secondary);
        }}

        /* Exit Polls Mini-Panel */
        .exit-poll-box {{
            background: rgba(30, 41, 59, 0.6);
            border: 1px solid rgba(56, 189, 248, 0.3);
            border-radius: 8px;
            padding: 10px 14px;
            margin-bottom: 10px;
        }}

        .exit-poll-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.75rem;
            font-weight: 800;
            color: var(--gold-accent);
            letter-spacing: 0.8px;
            text-transform: uppercase;
            margin-bottom: 6px;
        }}

        .exit-poll-stat {{
            display: flex;
            justify-content: space-between;
            font-size: 0.88rem;
            font-weight: 700;
            color: #f1f5f9;
        }}

        .exit-poll-sub {{
            font-size: 0.72rem;
            color: var(--text-secondary);
            margin-top: 4px;
        }}

        /* Bottom Ticker Bar */
        .ticker-bar {{
            background: #070b14;
            border-top: 2px solid var(--border-color);
            height: 42px;
            display: flex;
            align-items: center;
            overflow: hidden;
            z-index: 100;
            flex-shrink: 0;
        }}

        .ticker-badge {{
            background: #dc2626;
            color: #ffffff;
            font-size: 0.75rem;
            font-weight: 900;
            letter-spacing: 1.5px;
            padding: 0 14px;
            height: 100%;
            display: flex;
            align-items: center;
            gap: 6px;
            flex-shrink: 0;
            box-shadow: 4px 0 10px rgba(0, 0, 0, 0.5);
            z-index: 10;
        }}

        .ticker-viewport {{
            flex: 1;
            overflow: hidden;
            white-space: nowrap;
            display: flex;
            align-items: center;
        }}

        .ticker-track {{
            display: inline-flex;
            animation: ticker-slide 120s linear infinite;
            will-change: transform;
        }}

        @keyframes ticker-slide {{
            0% {{ transform: translate3d(0, 0, 0); }}
            100% {{ transform: translate3d(-50%, 0, 0); }}
        }}

        .ticker-snippet {{
            margin-right: 32px;
            font-size: 0.82rem;
            font-weight: 600;
            color: #e2e8f0;
        }}

        .ticker-bullet {{
            color: var(--gold-accent);
            font-size: 0.7rem;
            margin-right: 6px;
        }}

        /* Financial Indices Marquee */
        .market-strip {{
            background: #0a0f1d;
            border-bottom: 1px solid var(--border-color);
            height: 30px;
            display: flex;
            align-items: center;
            overflow: hidden;
            padding: 0 14px;
            gap: 16px;
            flex-shrink: 0;
        }}

        .market-strip-title {{
            font-size: 0.68rem;
            font-weight: 900;
            color: var(--text-muted);
            letter-spacing: 1px;
            text-transform: uppercase;
            flex-shrink: 0;
        }}

        .index-card {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 0.75rem;
            white-space: nowrap;
        }}

        .index-name {{
            font-weight: 800;
            color: #94a3b8;
        }}

        .index-price {{
            font-family: "SF Mono", Monaco, Consolas, monospace;
            font-weight: 700;
            color: #f8fafc;
        }}

        .index-change.up {{ color: var(--emerald-accent); }}
        .index-change.down {{ color: #f43f5e; }}
        .index-change.flat {{ color: #94a3b8; }}

        .index-arrow {{ font-size: 0.68rem; }}
    </style>
    <!-- Ha-catt fix to maintain DashCast keep-alive natively -->
    <script src="/ha-catt-fix.js"></script>
</head>
<body>
    <!-- Silent invisible looping video keep-alive for Chromecast OS -->
    <video autoplay loop muted playsinline style="position:absolute; width:1px; height:1px; opacity:0; z-index:-1;">
        <source src="https://storage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4" type="video/mp4">
    </video>

    <!-- 1. Header -->
    <header>
        <div class="brand-group">
            <div class="live-dot-pulse"></div>
            <div class="brand-text">DECISION DESK 2026</div>
            <div class="brand-badge">MIDTERMS LIVE</div>
        </div>

        <div class="countdown-banner">
            <span>NEXT POLL CLOSINGS: <strong>{nw_label}</strong> ({html.escape(nw_states[:32])})</span>
            <span class="countdown-time" id="top-countdown">{nw_countdown}</span>
        </div>

        <div class="clock-container">
            <div class="date-display" id="live-date">{poll_stat['current_date_str']}</div>
            <div class="clock-display" id="live-clock">{poll_stat['current_time_str']}</div>
        </div>
    </header>

    <!-- 2. Balance of Power Big Board -->
    <section class="bop-container">
        <!-- Senate -->
        <div class="bop-chamber">
            <div class="bop-header">
                <span class="chamber-title">U.S. SENATE · 100 SEATS</span>
                <span class="threshold-pill">51 MAJORITY</span>
            </div>
            <div class="bop-counts">
                <div>
                    <span class="count-dem" id="bop-sen-dem">{sen['dem']}</span>
                    <span class="count-label">DEM (<span id="bop-sen-dem-needed">{sen['dem_needed']}</span> to win)</span>
                </div>
                <div style="font-size:0.75rem; color:#94a3b8; font-weight:700;">
                    <span id="bop-sen-uncalled">{sen['uncalled']}</span> IN PLAY
                </div>
                <div>
                    <span class="count-label">GOP (<span id="bop-sen-gop-needed">{sen['gop_needed']}</span> to win)</span>
                    <span class="count-gop" id="bop-sen-gop">{sen['gop']}</span>
                </div>
            </div>
            <div class="meter-track">
                <div class="meter-bar-dem" id="bar-sen-dem" style="width: {sen['dem_pct_bar']}%;"></div>
                <div class="majority-needle needle-senate" title="51 to Majority"></div>
                <div class="meter-bar-gop" id="bar-sen-gop" style="width: {sen['gop_pct_bar']}%;"></div>
            </div>
        </div>

        <!-- House of Representatives -->
        <div class="bop-chamber">
            <div class="bop-header">
                <span class="chamber-title">U.S. HOUSE · 435 SEATS</span>
                <span class="threshold-pill">218 MAJORITY</span>
            </div>
            <div class="bop-counts">
                <div>
                    <span class="count-dem" id="bop-house-dem">{house['dem']}</span>
                    <span class="count-label">DEM (<span id="bop-house-dem-needed">{house['dem_needed']}</span> to win)</span>
                </div>
                <div style="font-size:0.75rem; color:#94a3b8; font-weight:700;">
                    <span id="bop-house-uncalled">{house['uncalled']}</span> REMAINING
                </div>
                <div>
                    <span class="count-label">GOP (<span id="bop-house-gop-needed">{house['gop_needed']}</span> to win)</span>
                    <span class="count-gop" id="bop-house-gop">{house['gop']}</span>
                </div>
            </div>
            <div class="meter-track">
                <div class="meter-bar-dem" id="bar-house-dem" style="width: {house['dem_pct_bar']}%;"></div>
                <div class="majority-needle needle-house" title="218 to Majority"></div>
                <div class="meter-bar-gop" id="bar-house-gop" style="width: {house['gop_pct_bar']}%;"></div>
            </div>
        </div>
    </section>

    <!-- 3. Financial Markets Strip -->
    <div class="market-strip">
        <span class="market-strip-title">ELECTION NIGHT MARKETS:</span>
        <div style="display:flex; gap:16px; overflow:hidden;" id="market-cards-container">
            {market_cards_html}
        </div>
    </div>

    <!-- 4. Main Two-Column Split Screen -->
    <main>
        <!-- Left: Key Battleground Contests -->
        <section class="col-left">
            <div class="panel-header">
                <div class="panel-title-wrap">
                    <span class="panel-badge-icon" style="background:#38bdf8; box-shadow:0 0 8px #38bdf8;"></span>
                    <span class="panel-title">KEY BATTLEGROUND CONTESTS</span>
                </div>
                <span class="panel-sub">SENATE & GOVERNOR TIPPING POINTS</span>
            </div>
            <div class="scrolling-viewport" id="viewport-races">
                <div class="scrolling-track" id="track-races">
                    {battlegrounds_html}
                </div>
            </div>
        </section>

        <!-- Right: Decision Desk Live Wire & Exit Polls -->
        <section class="col-right">
            <div class="panel-header">
                <div class="panel-title-wrap">
                    <span class="panel-badge-icon" style="background:#ef4444; box-shadow:0 0 8px #ef4444;"></span>
                    <span class="panel-title">DECISION DESK WIRE & EXIT POLLS</span>
                </div>
                <span class="panel-sub">LIVE PROJECTIONS & FIELD REPORTS</span>
            </div>
            <div class="scrolling-viewport" id="viewport-wire">
                <div class="scrolling-track" id="track-wire">
                    <!-- Exit Poll Box Top of Wire -->
                    <div class="exit-poll-box">
                        <div class="exit-poll-header">
                            <span>NBC NEWS EXIT POLL: PRESIDENTIAL REFERENDUM</span>
                            <span>NATIONAL PULSE</span>
                        </div>
                        <div class="exit-poll-stat">
                            <span style="color:#ef4444;">62% Disapprove</span>
                            <span style="color:#10b981;">38% Approve</span>
                        </div>
                        <div class="exit-poll-sub">
                            59% of voters say Trump was a factor in their vote (43% cast ballot to oppose). Top voter priority: Inflation & Cost of Living.
                        </div>
                    </div>
                    {wire_html}
                </div>
            </div>
        </section>
    </main>

    <!-- 5. Bottom Real-time News Marquee -->
    <footer class="ticker-bar">
        <div class="ticker-badge">
            <span class="live-dot-pulse" style="width:8px; height:8px;"></span>
            <span>BREAKING WIRE</span>
        </div>
        <div class="ticker-viewport">
            <div class="ticker-track" id="ticker-track">
                {ticker_html}
                {ticker_html}
            </div>
        </div>
    </footer>

    <!-- Interactive Client-side Script -->
    <script>
        // 1. Digital Clock
        function updateClock() {{
            const now = new Date();
            const timeStr = now.toLocaleTimeString('en-US', {{
                timeZone: 'America/New_York',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                hour12: true
            }});
            const dateStr = now.toLocaleDateString('en-US', {{
                timeZone: 'America/New_York',
                weekday: 'short',
                month: 'short',
                day: 'numeric'
            }});
            const clockEl = document.getElementById('live-clock');
            const dateEl = document.getElementById('live-date');
            if (clockEl) clockEl.textContent = timeStr + ' ET';
            if (dateEl) dateEl.textContent = dateStr;
        }}
        setInterval(updateClock, 1000);
        updateClock();

        // 2. Continuous Auto-Scroll Engine for Smart Display
        function setupScroller(viewportId, trackId, speed) {{
            const viewport = document.getElementById(viewportId);
            const track = document.getElementById(trackId);
            if (!viewport || !track) return;

            // Clone children for smooth continuous wrap-around loop
            const clone = track.cloneNode(true);
            clone.id = trackId + "-clone";
            track.parentNode.appendChild(clone);

            let pos = 0;
            let isPaused = false;

            viewport.addEventListener('mouseenter', () => isPaused = true);
            viewport.addEventListener('mouseleave', () => isPaused = false);
            viewport.addEventListener('touchstart', () => isPaused = true);
            viewport.addEventListener('touchend', () => isPaused = false);

            function step() {{
                if (!isPaused) {{
                    pos += speed;
                    const trackHeight = track.offsetHeight + 10;
                    if (pos >= trackHeight) {{
                        pos = 0;
                    }}
                    viewport.scrollTop = pos;
                }}
                requestAnimationFrame(step);
            }}
            requestAnimationFrame(step);
        }}

        window.addEventListener('load', () => {{
            setupScroller('viewport-races', 'track-races', 0.35);
            setupScroller('viewport-wire', 'track-wire', 0.40);
        }});

        // 3. Dynamic Live-Polling Engine (every 10 seconds)
        let lastPayloadTs = {data['updated_ts']};
        setInterval(() => {{
            fetch('/election_data.json?t=' + Date.now())
                .then(r => r.json())
                .then(d => {{
                    if (!d || !d.updated_ts) return;
                    if (d.updated_ts > lastPayloadTs) {{
                        lastPayloadTs = d.updated_ts;
                        
                        // Update BOP Numbers
                        if (d.balance_of_power) {{
                            const sen = d.balance_of_power.senate;
                            const hse = d.balance_of_power.house;
                            
                            const elSenDem = document.getElementById('bop-sen-dem');
                            const elSenGop = document.getElementById('bop-sen-gop');
                            const barSenDem = document.getElementById('bar-sen-dem');
                            const barSenGop = document.getElementById('bar-sen-gop');
                            const elSenDemNeeded = document.getElementById('bop-sen-dem-needed');
                            const elSenGopNeeded = document.getElementById('bop-sen-gop-needed');
                            const elSenUncalled = document.getElementById('bop-sen-uncalled');
                            
                            if (elSenDem) elSenDem.textContent = sen.dem;
                            if (elSenGop) elSenGop.textContent = sen.gop;
                            if (barSenDem) barSenDem.style.width = sen.dem_pct_bar + '%';
                            if (barSenGop) barSenGop.style.width = sen.gop_pct_bar + '%';
                            if (elSenDemNeeded) elSenDemNeeded.textContent = sen.dem_needed;
                            if (elSenGopNeeded) elSenGopNeeded.textContent = sen.gop_needed;
                            if (elSenUncalled) elSenUncalled.textContent = sen.uncalled;
                            
                            const elHseDem = document.getElementById('bop-house-dem');
                            const elHseGop = document.getElementById('bop-house-gop');
                            const barHseDem = document.getElementById('bar-house-dem');
                            const barHseGop = document.getElementById('bar-house-gop');
                            const elHseDemNeeded = document.getElementById('bop-house-dem-needed');
                            const elHseGopNeeded = document.getElementById('bop-house-gop-needed');
                            const elHseUncalled = document.getElementById('bop-house-uncalled');
                            
                            if (elHseDem) elHseDem.textContent = hse.dem;
                            if (elHseGop) elHseGop.textContent = hse.gop;
                            if (barHseDem) barHseDem.style.width = hse.dem_pct_bar + '%';
                            if (barHseGop) barHseGop.style.width = hse.gop_pct_bar + '%';
                            if (elHseDemNeeded) elHseDemNeeded.textContent = hse.dem_needed;
                            if (elHseGopNeeded) elHseGopNeeded.textContent = hse.gop_needed;
                            if (elHseUncalled) elHseUncalled.textContent = hse.uncalled;
                        }}
                        
                        // Update Countdown
                        if (d.poll_status && d.poll_status.next_wave) {{
                            const nw = d.poll_status.next_wave;
                            const elCd = document.getElementById('top-countdown');
                            if (elCd) elCd.textContent = nw.countdown_text || 'Soon';
                        }}
                    }}
                }})
                .catch(() => {{}});
        }}, 10000);

        // 4. Periodic clean reload every 10 minutes to refresh stories and preserve webview memory
        setTimeout(() => {{
            window.location.reload();
        }}, 600000);
    </script>
</body>
</html>
"""
    return full_html

# ---------------------------------------------------------
# 7. Main Execution / Daemon Loop
# ---------------------------------------------------------

def run_once():
    data = aggregate_election_data()
    
    # Write JSON data
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Updated {OUTPUT_JSON} ({len(data['wire_feed'])} wire dispatches, {len(data['battlegrounds'])} key races).", flush=True)
    
    # Write HTML file
    rendered_html = generate_dashboard_html(data)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(rendered_html)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Updated {OUTPUT_HTML} (Size: {len(rendered_html.encode('utf-8')):,} bytes).", flush=True)

def main():
    parser = argparse.ArgumentParser(description="Election Results Aggregator for Lenovo Smart Display")
    parser.add_argument("--daemon", action="store_true", help="Run continuously in background")
    parser.add_argument("--interval", type=int, default=60, help="Refresh interval in seconds (default: 60)")
    args = parser.parse_args()
    
    run_once()
    
    if args.daemon:
        print(f"Starting election daemon (Interval: {args.interval}s)...", flush=True)
        while True:
            time.sleep(args.interval)
            try:
                run_once()
            except Exception as e:
                print(f"[Error in daemon loop]: {e}", flush=True)

if __name__ == "__main__":
    main()
