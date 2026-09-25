import sys
import time
import pychromecast

def play_video(url, content_type="application/x-mpegurl", device_name="Lenovo Smart Display"):
    print(f"Searching for {device_name}...")
    chromecasts, browser = pychromecast.get_listed_chromecasts(friendly_names=[device_name])
    
    if not chromecasts:
        print(f"Device '{device_name}' not found.")
        return
        
    cast = chromecasts[0]
    cast.wait()
    print(f"Connected to {cast.cast_info.friendly_name}")
    
    mc = cast.media_controller
    print(f"Playing media: {url}")
    mc.play_media(url, content_type)
    mc.block_until_active()
    
    print("Media is now playing. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping playback...")
        mc.stop()
        pychromecast.discovery.stop_discovery(browser)

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.bloomberg.com/media-manifest/streams/us.m3u8"
    
    if ".m3u8" in url:
        content_type = "application/x-mpegurl"
    elif ".mp4" in url:
        content_type = "video/mp4"
    else:
        content_type = "video/mp4"
        
    play_video(url, content_type)
