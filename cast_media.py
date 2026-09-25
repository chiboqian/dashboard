#!/usr/bin/env python3
import argparse
import os
import socket
import threading
import time
import http.server
import socketserver

def get_local_ip():
    """Get the local IP address of the machine to serve the file."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def start_local_server(directory, port, font_size="1.5vw", top=None, bottom=None, left=None, right=None, bottom_left=None, bottom_right=None, scale1=1.0, scale2=1.0, ratio="50:50", quiet=True):
    """Start a temporary HTTP server to host local files or a dynamic dashboard."""
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)
            
        def log_message(self, format, *args):
            if not quiet:
                super().log_message(format, *args)
            
        def do_GET(self):
            from urllib.parse import urlparse, parse_qs
            import html
            parsed = urlparse(self.path)
            
            # Dynamically serve a split-screen dashboard if requested
            if parsed.path == '/dashboard':
                first_src = left if left and left.startswith('http') else ('/' + os.path.basename(left) if left else '')
                second_src = right if right and right.startswith('http') else ('/' + os.path.basename(right) if right else '')
                first_bot_src = bottom_left if bottom_left and bottom_left.startswith('http') else ('/' + os.path.basename(bottom_left) if bottom_left else '')
                second_bot_src = bottom_right if bottom_right and bottom_right.startswith('http') else ('/' + os.path.basename(bottom_right) if bottom_right else '')
                
                # If they didn't use left/right, fallback to top/bottom
                if not (left or right or bottom_left or bottom_right):
                    first_src = top if top and top.startswith('http') else ('/' + os.path.basename(top) if top else '')
                    second_src = bottom if bottom and bottom.startswith('http') else ('/' + os.path.basename(bottom) if bottom else '')
                    flex_dir = "column"
                    divider_css = "width: 100%; height: 2px;"
                else:
                    flex_dir = "row"
                    divider_css = "width: 2px; height: 100%;"
                
                # Parse main ratio safely
                import re
                try:
                    r1, r2 = map(float, re.split(r'[:,/]', ratio))
                except:
                    r1, r2 = 50, 50

                width_pct1 = 100 / scale1
                width_pct2 = 100 / scale2
                
                html_content = f"""<!DOCTYPE html>
                <html><head>
                <meta charset="utf-8">
                <style>
                    body {{ margin: 0; padding: 0; background: #000; display: flex; flex-direction: {flex_dir}; height: 100vh; overflow: hidden; }}
                    
                    /* Left/Top Container */
                    .half-container-1 {{ flex: {r1}; display: flex; flex-direction: column; position: relative; overflow: hidden; }}
                    .pane-top-left {{ flex: 1; position: relative; overflow: hidden; }}
                    .pane-bottom-left {{ flex: 1; position: relative; overflow: hidden; border-top: 2px solid #333; }}
                    
                    /* Right/Bottom Container */
                    .half-container-2 {{ flex: {r2}; display: flex; flex-direction: column; position: relative; overflow: hidden; }}
                    .pane-top-right {{ flex: 1; position: relative; overflow: hidden; }}
                    .pane-bottom-right {{ flex: 1; position: relative; overflow: hidden; border-top: 2px solid #333; }}
                    
                    iframe {{
                        position: absolute;
                        top: 0; left: 0;
                        width: 100%; height: 100%;
                        border: none;
                    }}
                    .scaled-iframe-1 {{
                        width: {width_pct1}%; height: {width_pct1}%;
                        transform: scale({scale1}); transform-origin: 0 0;
                    }}
                    .scaled-iframe-2 {{
                        width: {width_pct2}%; height: {width_pct2}%;
                        transform: scale({scale2}); transform-origin: 0 0;
                    }}
                    
                    .divider {{ background: #333; {divider_css} z-index: 10; }}
                </style>
                <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
                <script>
                    // Silently force-refresh webpages every 30 seconds, but deliberately ignore video streams so they don't stutter
                    setInterval(() => {{
                        document.querySelectorAll('iframe').forEach(f => {{
                            try {{
                                let urlStr = f.src.toLowerCase();
                                if (urlStr.includes('youtube') || urlStr.includes('.mp4')) {{
                                    return;
                                }}
                                let url = new URL(f.src);
                                url.searchParams.set('forceRefresh', Date.now());
                                f.src = url.toString();
                            }} catch (e) {{
                                f.src = f.src;
                            }}
                        }});
                    }}, 30000);
                    
                    // Native HLS Player Initialization
                    function initBloomberg() {{
                        var video = document.getElementById('bloomberg-video');
                        if (!video) return;
                        var videoSrc = 'https://www.bloomberg.com/media-manifest/streams/us.m3u8';
                        function startPlay() {{
                            video.play().catch(function(error) {{
                                console.log("Autoplay blocked, forcing mute...");
                                video.muted = true;
                                video.play();
                            }});
                        }}
                        if (Hls.isSupported()) {{
                            var hls = new Hls();
                            hls.loadSource(videoSrc);
                            hls.attachMedia(video);
                            hls.on(Hls.Events.MANIFEST_PARSED, function() {{ startPlay(); }});
                        }} else if (video.canPlayType('application/vnd.apple.mpegurl')) {{
                            video.src = videoSrc;
                            video.addEventListener('loadedmetadata', function() {{ startPlay(); }});
                        }}
                        
                        // Allow user to tap the screen to unmute (bypasses iframe autoplay restrictions)
                        video.addEventListener('click', function() {{
                            video.muted = false;
                            video.play();
                            var overlay = document.getElementById('unmute-overlay');
                            if(overlay) overlay.style.display = 'none';
                        }});
                    }}
                    window.addEventListener('DOMContentLoaded', initBloomberg);
                </script>
                </head><body>
                <!-- Silent invisible video stream trick as an absolute fallback in case no visible video panes are active -->
                <video autoplay loop muted playsinline style="position:absolute; width:1px; height:1px; opacity:0; z-index:-1;">
                    <source src="https://storage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4" type="video/mp4">
                </video>
                """
                
                def render_pane(src, scale_class):
                    if src == '/bloomberg_tv':
                        return f'''
                        <div style="position:relative; width:100%; height:100%;">
                            <video id="bloomberg-video" muted autoplay style="width: 100%; height: 100%; object-fit: cover; cursor: pointer;"></video>
                            <div id="unmute-overlay" style="position:absolute; top:10px; right:10px; background:rgba(0,0,0,0.7); color:white; padding:5px 10px; border-radius:5px; font-family:sans-serif; pointer-events:none; font-size:1.5vw;">
                                🔊 Tap Video to Unmute
                            </div>
                        </div>
                        '''
                    return f'<iframe class="{scale_class}" src="{src}"></iframe>'
                
                # Build Left Side
                if first_src or first_bot_src:
                    html_content += f'<div class="half-container-1">\n'
                    if first_src:
                        html_content += f'  <div class="pane-top-left">{render_pane(first_src, "scaled-iframe-1")}</div>\n'
                    if first_bot_src:
                        html_content += f'  <div class="pane-bottom-left">{render_pane(first_bot_src, "scaled-iframe-1")}</div>\n'
                    html_content += f'</div>\n'
                    
                if (first_src or first_bot_src) and (second_src or second_bot_src):
                    html_content += f'<div class="divider"></div>\n'
                    
                # Build Right Side
                if second_src or second_bot_src:
                    html_content += f'<div class="half-container-2">\n'
                    if second_src:
                        html_content += f'  <div class="pane-top-right">{render_pane(second_src, "scaled-iframe-2")}</div>\n'
                    if second_bot_src:
                        html_content += f'  <div class="pane-bottom-right">{render_pane(second_bot_src, "scaled-iframe-2")}</div>\n'
                    html_content += f'</div>\n'
                
                html_content += "</body></html>"
                
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(html_content.encode('utf-8'))))
                self.end_headers()
                self.wfile.write(html_content.encode('utf-8'))
                return

            # Native HLS Stream Player (Bypasses YouTube's strict embed restrictions)
            if parsed.path == '/bloomberg_tv':
                html_content = """<!DOCTYPE html>
                <html><head>
                <meta charset="utf-8">
                <style>body { margin: 0; background: #000; overflow: hidden; }</style>
                <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
                </head><body>
                <video id="video" autoplay style="width: 100vw; height: 100vh; object-fit: cover;"></video>
                <script>
                  var video = document.getElementById('video');
                  var videoSrc = 'https://www.bloomberg.com/media-manifest/streams/us.m3u8';
                  
                  function startPlay() {
                      video.play().catch(function(error) {
                          console.log("Autoplay blocked, attempting to force unmute...");
                          video.muted = false;
                          video.play();
                      });
                  }

                  if (Hls.isSupported()) {
                    var hls = new Hls();
                    hls.loadSource(videoSrc);
                    hls.attachMedia(video);
                    hls.on(Hls.Events.MANIFEST_PARSED, function() { startPlay(); });
                  } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
                    video.src = videoSrc;
                    video.addEventListener('loadedmetadata', function() { startPlay(); });
                  }
                </script>
                </body></html>
                """
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(html_content.encode('utf-8'))))
                self.end_headers()
                self.wfile.write(html_content.encode('utf-8'))
                return

            # Intercept .txt files and wrap them in HTML for better TV readability
            if parsed.path.endswith('.txt'):
                local_path = os.path.join(directory, parsed.path.lstrip('/'))
                if os.path.exists(local_path):
                    with open(local_path, 'r', encoding='utf-8') as f:
                        text_content = f.read()
                    
                    query = parse_qs(parsed.query)
                    if 'raw' in query:
                        # Serve raw text for the background auto-updater
                        self.send_response(200)
                        self.send_header('Content-type', 'text/plain; charset=utf-8')
                        self.send_header('Content-Length', str(len(text_content.encode('utf-8'))))
                        self.end_headers()
                        self.wfile.write(text_content.encode('utf-8'))
                        return
                    
                    escaped_text = html.escape(text_content)
                    html_content = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <meta charset="utf-8">
                        <style>
                            body {{
                                background-color: #121212;
                                color: #e0e0e0;
                                font-family: 'Courier New', Courier, monospace;
                                font-size: {font_size};
                                padding: 3vw;
                                margin: 0;
                            }}
                            pre {{
                                white-space: pre;
                                overflow: hidden;
                            }}
                        </style>
                        <script>
                            // Seamlessly auto-refresh the text content every 3 seconds without screen flashing
                            setInterval(() => {{
                                fetch(window.location.pathname + "?raw=true")
                                    .then(response => response.text())
                                    .then(text => {{
                                        document.getElementById("content").textContent = text;
                                    }});
                            }}, 3000);
                        </script>
                    </head>
                    <body>
                        <!-- Silent invisible video stream trick to force the Chromecast OS to stay awake forever without beeps or flashes -->
                        <video autoplay loop muted playsinline style="position:absolute; width:1px; height:1px; opacity:0; z-index:-1;">
                            <source src="https://storage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4" type="video/mp4">
                        </video>
                        <pre id="content">{escaped_text}</pre>
                    </body>
                    </html>
                    """
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html; charset=utf-8')
                    self.send_header('Content-Length', str(len(html_content.encode('utf-8'))))
                    self.end_headers()
                    self.wfile.write(html_content.encode('utf-8'))
                    return
            # Fallback to default behavior for all other files (videos, images)
            super().do_GET()
            
    # Use a custom TCPServer that allows address reuse to prevent "Address already in use" errors on quick restarts
    class ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True
        
    httpd = ReusableTCPServer(("", port), Handler)
    
    # Run in a daemon thread so it shuts down when the script exits
    thread = threading.Thread(target=httpd.serve_forever)
    thread.daemon = True
    thread.start()
    
    return httpd

def cast_local_file(filepath=None, device_name=None, port=8000, content_type=None, font_size="1.5vw", top=None, bottom=None, left=None, right=None, bottom_left=None, bottom_right=None, scale1=1.0, scale2=1.0, ratio="50:50", quiet=True, public_url=None):
    try:
        import pychromecast
    except ImportError:
        print("Error: The 'pychromecast' module is required but not installed.")
        print("Please install it using: pip install pychromecast")
        return

    is_dashboard = bool(top or bottom or left or right or bottom_left or bottom_right)
    
    if not is_dashboard:
        if not filepath:
            print("Error: You must provide a file to cast, or use the layout flags to create a dashboard.")
            return
        filepath = os.path.abspath(filepath)
        if not os.path.exists(filepath):
            print(f"Error: File '{filepath}' does not exist.")
            return
        serve_dir = os.path.dirname(filepath)
        target_filename = os.path.basename(filepath)
    else:
        # Determine the directory to serve based on the files provided
        serve_dir = os.getcwd()
        if top and not top.startswith('http'):
            serve_dir = os.path.dirname(os.path.abspath(top)) or serve_dir
        elif bottom and not bottom.startswith('http'):
            serve_dir = os.path.dirname(os.path.abspath(bottom)) or serve_dir
        elif left and not left.startswith('http'):
            serve_dir = os.path.dirname(os.path.abspath(left)) or serve_dir
        elif right and not right.startswith('http'):
            serve_dir = os.path.dirname(os.path.abspath(right)) or serve_dir
        elif bottom_left and not bottom_left.startswith('http'):
            serve_dir = os.path.dirname(os.path.abspath(bottom_left)) or serve_dir
        elif bottom_right and not bottom_right.startswith('http'):
            serve_dir = os.path.dirname(os.path.abspath(bottom_right)) or serve_dir
        target_filename = "dashboard"

    import mimetypes
    if is_dashboard:
        content_type = "text/html"
    elif not content_type:
        content_type, _ = mimetypes.guess_type(filepath)
        if not content_type:
            content_type = "video/mp4"

    print("Searching for cast-enabled devices on your network (this may take a few seconds)...")
    if device_name:
        chromecasts, browser = pychromecast.get_listed_chromecasts(friendly_names=[device_name])
    else:
        chromecasts, browser = pychromecast.get_chromecasts()
        
    if not chromecasts:
        if device_name:
            print(f"Could not find a device named '{device_name}'.")
        else:
            print("No cast devices found on the network.")
        pychromecast.discovery.stop_discovery(browser)
        return

    cast = chromecasts[0]
    print(f"Connected to device: {cast.cast_info.friendly_name}")
    
    local_ip = get_local_ip()
    httpd = start_local_server(serve_dir, port, font_size, top, bottom, left, right, bottom_left, bottom_right, scale1, scale2, ratio, quiet)
    
    # URL escape the filename for the cast device
    from urllib.parse import quote
    
    if public_url:
        public_url = public_url.rstrip('/')
        media_url = f"{public_url}/{quote(target_filename)}"
        print(f"\nServing securely via Caddy Reverse Proxy: {public_url}")
        print("DashCast will natively bypass the sleep timeout without restarts!")
        force_mode = False
    else:
        media_url = f"http://{local_ip}:{port}/{quote(target_filename)}"
        print(f"\nServing local directory at: http://{local_ip}:{port}/")
        force_mode = True
        
    print(f"Preparing to cast '{target_filename}' (Type: {content_type})...")
    
    # Wait for the cast device to be fully ready
    cast.wait()
    
    if content_type.startswith("text/"):
        # Use DashCast for text files to render them in a browser view
        # We must use force=True to bypass iframe embedding which blocks local HTTP traffic
        from pychromecast.controllers.dashcast import DashCastController
        d = DashCastController()
        cast.register_handler(d)
        d.load_url(media_url, force=force_mode)
        mc = None
    else:
        # Use default media receiver for audio/video/images
        mc = cast.media_controller
        mc.play_media(media_url, content_type)
        mc.block_until_active()
    
    print(f"\n>> PLAYING on {cast.cast_info.friendly_name} <<")
    print("Press Ctrl+C (or send SIGTERM) to stop playback and exit.")

    import signal
    import sys
    import threading
    
    def cleanup(signum, frame):
        print("\nStopping playback...")
        if mc:
            mc.stop()
        else:
            cast.quit_app()
        httpd.shutdown()
        pychromecast.discovery.stop_discovery(browser)
        print("Exited.")
        sys.exit(0)
        
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    
    if not mc and force_mode:
        # DashCast Keep-Alive Loop: Lenovo Smart Displays ruthlessly kill the browser after 10 minutes if using force=True
        def keep_alive_loop():
            time.sleep(570) # 9.5 minutes
            while True:
                print("\n[Keep-Alive] 9.5 minutes elapsed. Silently refreshing DashCast to prevent sleep timeout...")
                try:
                    # 1. Store current volume and mute the device to prevent the loud boot chime
                    cast.update_status()
                    current_vol = cast.status.volume_level if cast.status else 0.5
                    cast.set_volume(0.0)
                    
                    # 2. Quit the app and force-reload it
                    cast.quit_app()
                    time.sleep(1.5)
                    d.load_url(media_url, force=True)
                    
                    # 3. Wait for connection to establish and restore volume
                    time.sleep(4)
                    cast.set_volume(current_vol)
                except Exception as e:
                    print(f"[Keep-Alive Error] {e}")
                
                time.sleep(570)
                
        threading.Thread(target=keep_alive_loop, daemon=True).start()
    
    while True:
        time.sleep(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stream a local media or text file to a Smart Display or Smart TV via Google Cast.")
    parser.add_argument("file", nargs="?", help="Path to the local file (e.g., video.mp4, document.txt). Optional if using --top/--bottom.")
    parser.add_argument("-d", "--device", help="Name of the cast device (e.g., 'Lenovo Smart Display', 'Living Room TV'). If omitted, casts to the first device found.", default=None)
    parser.add_argument("-p", "--port", type=int, default=8000, help="Local HTTP port to serve the file on (default: 8000)")
    parser.add_argument("-c", "--content-type", default=None, help="Force a MIME type (e.g. video/mp4). If omitted, it will automatically detect the correct type.")
    parser.add_argument("--font-size", default="1.5vw", help="Font size for text files (e.g. '12px', '2em', '3vw'). Default is 1.5vw.")
    parser.add_argument("--top", help="URL or local file to display on the top half of a dynamically generated split-screen dashboard.")
    parser.add_argument("--bottom", help="URL or local file to display on the bottom half of a dynamically generated split-screen dashboard.")
    parser.add_argument("--left", help="URL or local file to display on the left half of a dynamically generated split-screen dashboard.")
    parser.add_argument("--right", help="URL or local file to display on the right half of a dynamically generated split-screen dashboard.")
    parser.add_argument("--bottom-left", help="URL or local file to display on the bottom of the left half.")
    parser.add_argument("--bottom-right", help="URL or local file to display on the bottom of the right half.")
    parser.add_argument("--scale1", type=float, default=1.0, help="Scale factor for the first frame (left or top). e.g., 0.5")
    parser.add_argument("--scale2", type=float, default=1.0, help="Scale factor for the second frame (right or bottom). e.g., 1.0")
    parser.add_argument("--ratio", default="50:50", help="Ratio of the first frame to the second frame (e.g., '70:30' or '60/40'). Default is 50:50.")
    
    # Quiet mode is True by default. Allow the user to explicitly enable or disable it.
    parser.add_argument("--quiet", dest="quiet", action="store_true", default=True, help="Suppress HTTP access logs (Default: True)")
    parser.add_argument("--verbose", dest="quiet", action="store_false", help="Show HTTP access logs")
    parser.add_argument("--public-url", default=None, help="Public HTTPS URL (e.g. https://tv.luna-strategy.com) when running behind a reverse proxy like Caddy")
    
    args = parser.parse_args()
    cast_local_file(args.file, args.device, args.port, args.content_type, args.font_size, args.top, args.bottom, args.left, args.right, args.bottom_left, args.bottom_right, args.scale1, args.scale2, args.ratio, args.quiet, args.public_url)
