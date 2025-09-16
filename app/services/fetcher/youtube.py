import httpx, re, subprocess
from pathlib import Path
from app.services.intake.allowlist_manager import iter_enabled_creators
from app.settings import S

STATE_DIR = Path("tmp/state"); STATE_DIR.mkdir(parents=True, exist_ok=True)
SEEN_FILE = STATE_DIR / "seen_videos.txt"

def _mark_seen(video_id: str): SEEN_FILE.write_text((SEEN_FILE.read_text() if SEEN_FILE.exists() else "") + video_id + "\n", encoding="utf-8")
def _already_seen(video_id: str) -> bool: return SEEN_FILE.exists() and video_id in SEEN_FILE.read_text(encoding="utf-8").splitlines()

def resolve_channel_id(url_or_handle: str) -> str:
    if "/channel/" in url_or_handle:
        m = re.search(r"/channel/([A-Za-z0-9_-]{10,})", url_or_handle); return m.group(1) if m else url_or_handle
    handle = url_or_handle.rsplit("/", 1)[-1].lstrip("@")
    r = httpx.get("https://www.googleapis.com/youtube/v3/search",
                  params={"part":"snippet","q":handle,"type":"channel","key":S.YT_API_KEY,"maxResults":1}, timeout=20)
    r.raise_for_status(); items = r.json().get("items", [])
    if not items: raise RuntimeError(f"Channel not found for {handle}")
    return items[0]["snippet"]["channelId"]

def get_uploads_playlist_id(channel_id: str) -> str:
    r = httpx.get("https://www.googleapis.com/youtube/v3/channels",
                  params={"part":"contentDetails","id":channel_id,"key":S.YT_API_KEY}, timeout=20)
    r.raise_for_status(); items = r.json().get("items", [])
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

def playlist_items(playlist_id: str, max_results: int = 10) -> list[dict]:
    r = httpx.get("https://www.googleapis.com/youtube/v3/playlistItems",
                  params={"part":"contentDetails","playlistId":playlist_id,"maxResults":max_results,"key":S.YT_API_KEY}, timeout=20)
    r.raise_for_status(); return r.json().get("items", [])

def list_new_videos() -> list[str]:
    out = []
    for c in iter_enabled_creators():
        if c.get("platform") != "youtube": continue
        ch = resolve_channel_id(c["source_url"])
        upl = get_uploads_playlist_id(ch)
        for it in playlist_items(upl, max_results=5):
            vid = it["contentDetails"]["videoId"]
            if not _already_seen(vid):
                _mark_seen(vid); out.append(vid)
    return out

def fetch_video_media(video_id: str) -> str:
    Path("tmp/media").mkdir(parents=True, exist_ok=True)
    out = f"tmp/media/{video_id}.mp4"
    if not Path(out).exists():
        subprocess.check_call(["yt-dlp","-f","mp4","-o",out,f"https://youtu.be/{video_id}"])
    return out
