#!/usr/bin/env python3
"""
fetch_news.py - Multi-source Market & World News aggregator for Lenovo Smart Display.
Fetches RSS feeds concurrently, deduplicates headlines, and generates both
news_data.json and news_dashboard.html with a sleek Bloomberg-style dark theme.
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

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_HTML = os.path.join(SCRIPT_DIR, "news_dashboard.html")
OUTPUT_JSON = os.path.join(SCRIPT_DIR, "news_data.json")

FEEDS = [
    # Markets & Financial
    {
        "url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        "source": "WSJ",
        "category": "markets",
        "badge_color": "#d4af37"
    },
    {
        "url": "https://www.cnbc.com/id/10000664/device/rss/rss.html",
        "source": "CNBC",
        "category": "markets",
        "badge_color": "#0284c7"
    },
    {
        "url": "https://feeds.content.dowjones.io/public/rss/mw_marketpulse",
        "source": "MarketWatch",
        "category": "markets",
        "badge_color": "#10b981"
    },
    {
        "url": "https://news.google.com/rss/search?q=stock+market+economy+finance&hl=en-US&gl=US&ceid=US:en",
        "source": "Yahoo / Reuters",
        "category": "markets",
        "badge_color": "#8b5cf6"
    },
    # World News
    {
        "url": "http://feeds.bbci.co.uk/news/world/rss.xml",
        "source": "BBC",
        "category": "world",
        "badge_color": "#ef4444"
    },
    {
        "url": "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx1YlY4U0FtVnVHZ0pWVXlnQVAB?hl=en-US&gl=US&ceid=US:en",
        "source": "Reuters / AP",
        "category": "world",
        "badge_color": "#f97316"
    },
    {
        "url": "https://feeds.npr.org/1004/rss.xml",
        "source": "NPR",
        "category": "world",
        "badge_color": "#06b6d4"
    }
]

INDEX_SYMBOLS = [
    # US Stock Indexes
    {"name": "S&P 500", "symbol": "^GSPC", "format": "{:,.2f}"},
    {"name": "NASDAQ", "symbol": "^IXIC", "format": "{:,.2f}"},
    {"name": "DOW", "symbol": "^DJI", "format": "{:,.2f}"},
    {"name": "RUSSELL 2000", "symbol": "^RUT", "format": "{:,.2f}"},
    # Europe Stock Indexes
    {"name": "EURO STOXX 50", "symbol": "^STOXX50E", "format": "{:,.2f}"},
    {"name": "FTSE 100", "symbol": "^FTSE", "format": "{:,.2f}"},
    {"name": "DAX", "symbol": "^GDAXI", "format": "{:,.2f}"},
    {"name": "CAC 40", "symbol": "^FCHI", "format": "{:,.2f}"},
    # Asia-Pacific Stock Indexes
    {"name": "NIKKEI 225", "symbol": "^N225", "format": "{:,.2f}"},
    {"name": "HANG SENG", "symbol": "^HSI", "format": "{:,.2f}"},
    {"name": "SHANGHAI", "symbol": "000001.SS", "format": "{:,.2f}"},
    {"name": "KOSPI", "symbol": "^KS11", "format": "{:,.2f}"},
    {"name": "TAIEX", "symbol": "^TWII", "format": "{:,.2f}"},
    {"name": "NIFTY 50", "symbol": "^NSEI", "format": "{:,.2f}"},
    {"name": "ASX 200", "symbol": "^AXJO", "format": "{:,.2f}"},
    # Rates, Volatility, Crypto & Commodities
    {"name": "10Y YIELD", "symbol": "^TNX", "format": "{:.2f}%", "is_yield": True},
    {"name": "VIX", "symbol": "^VIX", "format": "{:.2f}", "is_vix": True},
    {"name": "BITCOIN", "symbol": "BTC-USD", "format": "${:,.0f}"},
    {"name": "CRUDE OIL", "symbol": "CL=F", "format": "${:.2f}"},
    {"name": "GOLD", "symbol": "GC=F", "format": "${:,.1f}"},
]

_INDEXES_CACHE = []

def get_cached_indexes():
    global _INDEXES_CACHE
    if _INDEXES_CACHE:
        return _INDEXES_CACHE
    if os.path.exists(OUTPUT_JSON):
        try:
            with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
                d = json.load(f)
                if "indexes" in d and d["indexes"]:
                    _INDEXES_CACHE = d["indexes"]
                    return _INDEXES_CACHE
        except Exception:
            pass
    return []

def fetch_single_index(cfg):
    symbol = cfg["symbol"]
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?interval=1d"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            meta = data["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice")
            prev = meta.get("chartPreviousClose") or meta.get("previousClose")
            if price is None:
                return None
            prev = prev if prev else price
            chg = price - prev
            pct = (chg / prev) * 100 if prev else 0.0

            fmt = cfg.get("format", "{:,.2f}")
            price_str = fmt.format(price)
            if cfg.get("is_yield"):
                chg_str = f"{chg:+.2f}%"
            elif price >= 1000:
                chg_str = f"{chg:+,.1f}"
            else:
                chg_str = f"{chg:+.2f}"
            pct_str = f"{pct:+.2f}%"

            direction = "up" if chg > 0.0001 else ("down" if chg < -0.0001 else "flat")
            arrow = "▲" if direction == "up" else ("▼" if direction == "down" else "―")

            return {
                "name": cfg["name"],
                "symbol": cfg["symbol"],
                "price": price,
                "price_str": price_str,
                "change": chg,
                "change_str": chg_str,
                "pct": pct,
                "pct_str": pct_str,
                "direction": direction,
                "arrow": arrow
            }
    except Exception:
        return None

def fetch_indexes():
    global _INDEXES_CACHE
    cached = {item["symbol"]: item for item in get_cached_indexes()}
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(INDEX_SYMBOLS)) as executor:
        futs = {executor.submit(fetch_single_index, cfg): cfg for cfg in INDEX_SYMBOLS}
        for fut in concurrent.futures.as_completed(futs):
            cfg = futs[fut]
            try:
                res = fut.result()
                if res:
                    results.append(res)
                elif cfg["symbol"] in cached:
                    results.append(cached[cfg["symbol"]])
            except Exception:
                if cfg["symbol"] in cached:
                    results.append(cached[cfg["symbol"]])

    symbol_order = {cfg["symbol"]: i for i, cfg in enumerate(INDEX_SYMBOLS)}
    results.sort(key=lambda x: symbol_order.get(x["symbol"], 999))
    if results:
        _INDEXES_CACHE = results
    return results

def clean_text(raw):
    if not raw:
        return ""
    text = html.unescape(raw)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def strip_source_suffix(title):
    # Removes trailing source markers like "- The Wall Street Journal", "- BBC News", "- The Guardian", etc.
    title = re.sub(r"\s+[-–|]\s+([A-Za-z0-9\s.']{2,30})$", "", title).strip()
    return re.sub(r"\s*-\s*(BBC|Reuters|The Wall Street Journal|WSJ|CNBC|Yahoo Finance|AP News|MarketWatch|NPR|Bloomberg|CNN|The Guardian|Forbes|Financial Times).*$", "", title, flags=re.IGNORECASE).strip()

def format_relative_time(dt_utc):
    now = datetime.now(timezone.utc)
    delta = (now - dt_utc).total_seconds()
    if delta < 60:
        return "Just now"
    elif delta < 3600:
        mins = int(delta / 60)
        return f"{mins}m ago"
    elif delta < 86400:
        hours = int(delta / 3600)
        return f"{hours}h ago"
    else:
        # Convert to local time for friendly display
        dt_local = dt_utc.astimezone()
        return dt_local.strftime("%b %d, %I:%M %p")

def parse_single_feed(feed_cfg):
    items = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        req = urllib.request.Request(feed_cfg["url"], headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read()
            import xml.etree.ElementTree as ET
            root = ET.fromstring(content)
            for item in root.findall(".//item")[:20]:
                title = clean_text(item.findtext("title"))
                clean_t = strip_source_suffix(title)
                if not clean_t or len(clean_t) < 10:
                    continue
                
                desc = clean_text(item.findtext("description"))
                if desc and clean_t.lower() in desc.lower():
                    # If description just repeats headline, truncate or remove
                    desc = desc.replace(clean_t, "").strip()
                
                if len(desc) > 180:
                    desc = desc[:177] + "..."
                
                pub_date = item.findtext("pubDate")
                ts = time.time()
                rel_time = "Recent"
                if pub_date:
                    try:
                        dt = email.utils.parsedate_to_datetime(pub_date)
                        ts = dt.timestamp()
                        rel_time = format_relative_time(dt)
                    except Exception:
                        pass
                
                link = item.findtext("link") or ""
                
                items.append({
                    "title": clean_t,
                    "desc": desc,
                    "source": feed_cfg["source"],
                    "category": feed_cfg["category"],
                    "badge_color": feed_cfg["badge_color"],
                    "timestamp": ts,
                    "time_str": rel_time,
                    "link": link
                })
    except Exception as e:
        # Silently fail single feed without stopping others
        pass
    return items

def deduplicate_and_sort(items):
    seen_titles = set()
    deduped = []
    
    # Sort first by timestamp descending
    items.sort(key=lambda x: x["timestamp"], reverse=True)
    
    for it in items:
        # Simple title simplification for collision detection
        norm = re.sub(r"[^a-zA-Z0-9]", "", it["title"].lower())[:45]
        if norm in seen_titles:
            continue
        seen_titles.add(norm)
        deduped.append(it)
        
    return deduped

def build_dashboard_html(markets, world, generated_time_str, indexes=None):
    if indexes is None:
        indexes = []

    def render_items(items):
        html_cards = []
        for it in items:
            desc_html = f'<div class="card-desc">{html.escape(it["desc"])}</div>' if it["desc"] else ""
            card = f"""
            <div class="news-card">
                <div class="card-meta">
                    <span class="source-badge" style="background: {it['badge_color']}20; color: {it['badge_color']}; border: 1px solid {it['badge_color']}50;">{it['source']}</span>
                    <span class="card-time">{it['time_str']}</span>
                </div>
                <div class="card-title">{html.escape(it['title'])}</div>
                {desc_html}
            </div>
            """
            html_cards.append(card)
        return "\n".join(html_cards)

    def render_indexes(indexes_list):
        if not indexes_list:
            return ""
        cards = []
        for idx in indexes_list:
            direction = idx.get("direction", "flat")
            arrow = idx.get("arrow", "―")
            card = f"""
            <div class="index-card {direction}">
                <span class="index-name">{html.escape(idx['name'])}</span>
                <span class="index-price">{html.escape(idx['price_str'])}</span>
                <span class="index-change {direction}">
                    <span class="index-arrow">{arrow}</span>
                    <span>{html.escape(idx['change_str'])} ({html.escape(idx['pct_str'])})</span>
                </span>
            </div>
            """
            cards.append(card)
        return "\n".join(cards)

    markets_cards = render_items(markets)
    world_cards = render_items(world)
    indexes_cards = render_indexes(indexes)
    ticker_duration = max(45, len(indexes) * 5)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Global Intelligence - Markets & World Desk</title>
    <style>
        :root {{
            --bg-color: #07090e;
            --header-bg: #0d121d;
            --border-color: #1a2234;
            --market-accent: #10b981;
            --world-accent: #38bdf8;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --card-bg: rgba(15, 23, 42, 0.7);
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
        }}

        /* Top Header */
        header {{
            background: var(--header-bg);
            border-bottom: 2px solid var(--border-color);
            padding: 12px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            z-index: 100;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
        }}

        .brand {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .live-dot {{
            width: 10px;
            height: 10px;
            background: #ef4444;
            border-radius: 50%;
            box-shadow: 0 0 10px #ef4444;
            animation: pulse 1.5s infinite;
        }}

        @keyframes pulse {{
            0% {{ transform: scale(0.95); opacity: 0.7; }}
            50% {{ transform: scale(1.15); opacity: 1; }}
            100% {{ transform: scale(0.95); opacity: 0.7; }}
        }}

        .brand-title {{
            font-size: 1.25rem;
            font-weight: 800;
            letter-spacing: 1.5px;
            text-transform: uppercase;
            background: linear-gradient(90deg, #ffffff, #94a3b8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .brand-sub {{
            font-size: 0.85rem;
            color: var(--text-secondary);
            font-weight: 500;
            letter-spacing: 0.5px;
            border-left: 2px solid var(--border-color);
            padding-left: 12px;
            margin-left: 4px;
        }}

        .clock-container {{
            display: flex;
            align-items: center;
            gap: 16px;
        }}

        .clock {{
            font-family: "SF Mono", Monaco, Consolas, monospace;
            font-size: 1.35rem;
            font-weight: 700;
            color: #38bdf8;
            letter-spacing: 0.5px;
        }}

        .date-badge {{
            font-size: 0.9rem;
            color: var(--text-secondary);
            font-weight: 500;
        }}

        /* Market Indexes Ticker Bar */
        .indices-bar {{
            display: flex;
            align-items: center;
            background: #090d16;
            border-bottom: 2px solid var(--border-color);
            height: 44px;
            overflow: hidden;
            position: relative;
            z-index: 50;
        }}

        .ticker-header-badge {{
            display: flex;
            align-items: center;
            gap: 7px;
            background: #0f172a;
            border-right: 2px solid var(--border-color);
            padding: 0 16px;
            height: 100%;
            font-size: 0.78rem;
            font-weight: 800;
            letter-spacing: 1.5px;
            color: #38bdf8;
            text-transform: uppercase;
            flex-shrink: 0;
            z-index: 10;
            box-shadow: 4px 0 12px rgba(0, 0, 0, 0.4);
        }}

        .badge-dot {{
            width: 8px;
            height: 8px;
            background: #10b981;
            border-radius: 50%;
            box-shadow: 0 0 8px #10b981;
            animation: pulse 1.5s infinite;
        }}

        .ticker-viewport {{
            flex: 1;
            overflow: hidden;
            position: relative;
            display: flex;
            align-items: center;
            height: 100%;
            mask-image: linear-gradient(to right, transparent, black 16px, black calc(100% - 16px), transparent);
            -webkit-mask-image: linear-gradient(to right, transparent, black 16px, black calc(100% - 16px), transparent);
        }}

        .ticker-track {{
            display: flex;
            align-items: center;
            width: max-content;
            animation: ticker-slide {ticker_duration}s linear infinite;
            will-change: transform;
        }}

        .ticker-viewport:hover .ticker-track,
        .ticker-viewport:active .ticker-track {{
            animation-play-state: paused;
        }}

        @keyframes ticker-slide {{
            0% {{ transform: translate3d(0, 0, 0); }}
            100% {{ transform: translate3d(-50%, 0, 0); }}
        }}

        .index-card {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: rgba(15, 23, 42, 0.65);
            border: 1px solid rgba(30, 41, 59, 0.9);
            border-radius: 6px;
            padding: 4px 12px;
            margin-right: 12px;
            white-space: nowrap;
            user-select: none;
            transition: background 0.15s ease, border-color 0.15s ease;
        }}

        .index-card:hover {{
            background: rgba(30, 41, 59, 0.9);
            border-color: rgba(56, 189, 248, 0.5);
        }}

        .index-name {{
            font-size: 0.76rem;
            font-weight: 800;
            letter-spacing: 0.6px;
            color: #94a3b8;
            text-transform: uppercase;
        }}

        .index-price {{
            font-family: "SF Mono", Monaco, Consolas, monospace;
            font-size: 0.88rem;
            font-weight: 700;
            color: #f8fafc;
            letter-spacing: 0.2px;
        }}

        .index-change {{
            display: inline-flex;
            align-items: center;
            gap: 3px;
            font-family: "SF Mono", Monaco, Consolas, monospace;
            font-size: 0.8rem;
            font-weight: 600;
        }}

        .index-change.up {{
            color: #10b981;
        }}

        .index-change.down {{
            color: #f43f5e;
        }}

        .index-change.flat {{
            color: #94a3b8;
        }}

        .index-arrow {{
            font-size: 0.72rem;
            line-height: 1;
        }}

        /* Main Split View */
        main {{
            flex: 1;
            display: flex;
            min-height: 0;
            height: calc(100vh - 109px);
            position: relative;
        }}

        .column {{
            flex: 1;
            display: flex;
            flex-direction: column;
            border-right: 2px solid var(--border-color);
            overflow: hidden;
            position: relative;
        }}

        .column:last-child {{
            border-right: none;
        }}

        .column-header {{
            background: rgba(13, 18, 29, 0.95);
            padding: 10px 20px;
            border-bottom: 2px solid var(--border-color);
            display: flex;
            align-items: center;
            justify-content: space-between;
            z-index: 20;
            backdrop-filter: blur(8px);
        }}

        .col-title {{
            font-size: 1rem;
            font-weight: 800;
            letter-spacing: 1.5px;
            text-transform: uppercase;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .col-title.markets {{
            color: var(--market-accent);
        }}

        .col-title.world {{
            color: var(--world-accent);
        }}

        .col-count {{
            font-size: 0.75rem;
            background: #1e293b;
            color: #94a3b8;
            padding: 2px 8px;
            border-radius: 12px;
            font-weight: 600;
        }}

        /* Smooth Auto-Scroll Viewport */
        .scroll-viewport {{
            flex: 1;
            overflow-y: hidden;
            position: relative;
            padding: 16px 20px;
        }}

        .cards-track {{
            display: flex;
            flex-direction: column;
            gap: 16px;
        }}

        /* News Card */
        .news-card {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 16px 20px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
            transition: border-color 0.2s ease;
        }}

        .card-meta {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 8px;
        }}

        .source-badge {{
            font-size: 0.75rem;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 4px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .card-time {{
            font-size: 0.8rem;
            color: var(--text-secondary);
            font-weight: 500;
            font-family: monospace;
        }}

        .card-title {{
            font-size: 1.25rem;
            font-weight: 700;
            line-height: 1.35;
            color: #f1f5f9;
            margin-bottom: 6px;
        }}

        .card-desc {{
            font-size: 0.95rem;
            line-height: 1.45;
            color: #94a3b8;
        }}
    </style>
    <!-- Ha-catt fix to maintain DashCast keep-alive natively -->
    <script src="/ha-catt-fix.js"></script>
</head>
<body>
    <!-- DashCast background video keep-alive -->
    <video autoplay loop muted playsinline style="position:absolute; width:1px; height:1px; opacity:0; z-index:-1;">
        <source src="https://storage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4" type="video/mp4">
    </video>

    <header>
        <div class="brand">
            <div class="live-dot"></div>
            <div class="brand-title">LUNA GLOBAL INTELLIGENCE</div>
            <div class="brand-sub">MARKETS & WORLD DESK</div>
        </div>
        <div class="clock-container">
            <div class="date-badge" id="live-date">--</div>
            <div class="clock" id="live-clock">--:--:-- ET</div>
        </div>
    </header>

    <div class="indices-bar">
        <div class="ticker-header-badge">
            <span class="badge-dot"></span>
            <span>INDEXES</span>
        </div>
        <div class="ticker-viewport">
            <div class="ticker-track">
                {indexes_cards}
                {indexes_cards}
            </div>
        </div>
    </div>

    <main>
        <!-- Left: Markets -->
        <section class="column">
            <div class="column-header">
                <div class="col-title markets">
                    <span>📈</span> MARKETS & FINANCE
                </div>
                <div class="col-count">{len(markets)} HEADLINES</div>
            </div>
            <div class="scroll-viewport" id="viewport-markets">
                <div class="cards-track" id="track-markets">
                    {markets_cards}
                </div>
            </div>
        </section>

        <!-- Right: World -->
        <section class="column">
            <div class="column-header">
                <div class="col-title world">
                    <span>🌍</span> WORLD & GEOPOLITICS
                </div>
                <div class="col-count">{len(world)} HEADLINES</div>
            </div>
            <div class="scroll-viewport" id="viewport-world">
                <div class="cards-track" id="track-world">
                    {world_cards}
                </div>
            </div>
        </section>
    </main>

    <script>
        // 1. Live Digital Clock (EDT)
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
            document.getElementById('live-clock').textContent = timeStr + ' EDT';
            document.getElementById('live-date').textContent = dateStr;
        }}
        setInterval(updateClock, 1000);
        updateClock();

        // 2. Smooth Continuous Auto-Scroll Engine
        function setupScroller(viewportId, trackId, speed) {{
            const viewport = document.getElementById(viewportId);
            const track = document.getElementById(trackId);
            if (!viewport || !track) return;

            // Clone track nodes for infinite seamless wrap-around loop
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
                    const trackHeight = track.offsetHeight + 16;
                    if (pos >= trackHeight) {{
                        pos = 0;
                    }}
                    viewport.scrollTop = pos;
                }}
                requestAnimationFrame(step);
            }}
            requestAnimationFrame(step);
        }}

        // Slightly different speeds so columns feel independent and dynamic
        window.addEventListener('load', () => {{
            setupScroller('viewport-markets', 'track-markets', 0.45);
            setupScroller('viewport-world', 'track-world', 0.40);
        }});

        // 3. Auto-Refresh: Check for fresh headlines and indexes every 60s
        setInterval(() => {{
            fetch('/news_data.json?t=' + Date.now())
                .then(r => r.json())
                .then(data => {{
                    if (data && data.updated_ts) {{
                        const pageTs = {time.time()};
                        if (data.updated_ts > pageTs + 45) {{
                            // Reload page smoothly to incorporate new items
                            window.location.reload();
                        }}
                    }}
                }})
                .catch(() => {{}});
        }}, 60000);
    </script>
</body>
</html>
"""

def fetch_and_generate():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Fetching RSS feeds & market indexes...")
    all_raw = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(parse_single_feed, cfg) for cfg in FEEDS]
        for f in concurrent.futures.as_completed(futures):
            try:
                all_raw.extend(f.result())
            except Exception:
                pass

    markets = [it for it in all_raw if it["category"] == "markets"]
    world = [it for it in all_raw if it["category"] == "world"]

    markets = deduplicate_and_sort(markets)[:35]
    world = deduplicate_and_sort(world)[:35]

    indexes = fetch_indexes()

    now_dt = datetime.now().astimezone()
    gen_time_str = now_dt.strftime("%I:%M %p %Z")

    data = {
        "updated_ts": time.time(),
        "updated_str": gen_time_str,
        "indexes": indexes,
        "markets_count": len(markets),
        "world_count": len(world),
        "markets": markets,
        "world": world
    }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    html_content = build_dashboard_html(markets, world, gen_time_str, indexes)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Successfully generated {OUTPUT_HTML} ({len(indexes)} indexes, {len(markets)} market, {len(world)} world items).")

def main():
    parser = argparse.ArgumentParser(description="Fetch market and world news RSS feeds.")
    parser.add_argument("--daemon", action="store_true", help="Run continuously in background.")
    parser.add_argument("--interval", type=int, default=300, help="Refresh interval in seconds (default: 300).")
    args = parser.parse_args()

    if not args.daemon:
        fetch_and_generate()
    else:
        print(f"Starting news generator daemon (refreshing every {args.interval}s)...")
        while True:
            try:
                fetch_and_generate()
            except Exception as e:
                print(f"Error in fetch cycle: {e}")
            time.sleep(args.interval)

if __name__ == "__main__":
    main()
