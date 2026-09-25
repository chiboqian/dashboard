import urllib.request
import xml.etree.ElementTree as ET
import time
import os

RSS_URL = "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"
OUTPUT_FILE = "news.html"

def fetch_and_generate():
    try:
        req = urllib.request.Request(RSS_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            xml_data = response.read()
            
        root = ET.fromstring(xml_data)
        
        items = root.findall('./channel/item')[:10] # Get top 10
        
        headlines_html = ""
        for item in items:
            title = item.find('title').text if item.find('title') is not None else ""
            desc = item.find('description').text if item.find('description') is not None else ""
            if desc:
                # Truncate description
                if len(desc) > 120:
                    desc = desc[:117] + "..."
            
            headlines_html += f'''
            <div class="news-item">
                <div class="title">{title}</div>
                <div class="desc">{desc}</div>
            </div>
            '''
            
        html_template = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="300">
<style>
    body {{
        background-color: #000;
        color: #fff;
        font-family: Consolas, Monaco, monospace;
        margin: 0;
        padding: 20px;
        overflow: hidden;
    }}
    .header {{
        font-size: 3vw;
        color: #00ff00;
        border-bottom: 2px solid #333;
        padding-bottom: 10px;
        margin-bottom: 20px;
        text-transform: uppercase;
        letter-spacing: 2px;
    }}
    .news-container {{
        height: 100vh;
        overflow: hidden;
        position: relative;
    }}
    .scroller {{
        position: absolute;
        top: 0;
        animation: scroll 40s linear infinite;
    }}
    .news-item {{
        margin-bottom: 30px;
        padding-left: 10px;
        border-left: 4px solid #444;
    }}
    .title {{
        font-size: 2.5vw;
        font-weight: bold;
        color: #fff;
        margin-bottom: 8px;
    }}
    .desc {{
        font-size: 1.8vw;
        color: #aaa;
        line-height: 1.4;
    }}
    @keyframes scroll {{
        0% {{ transform: translateY(100vh); }}
        100% {{ transform: translateY(-100%); }}
    }}
</style>
</head>
<body>
    <div class="header">LIVE MARKETS NEWS</div>
    <div class="news-container">
        <div class="scroller">
            {headlines_html}
        </div>
    </div>
</body>
</html>
'''
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write(html_template)
            
        print(f"Generated {OUTPUT_FILE} with {len(items)} headlines.")
        
    except Exception as e:
        print(f"Error fetching news: {{e}}")

if __name__ == "__main__":
    print("Starting background news generator...")
    while True:
        fetch_and_generate()
        time.sleep(300) # Update every 5 mins
