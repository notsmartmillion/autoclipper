import httpx, datetime as dt
from app.db import Session
from app.models import Creator, Video

API = "https://www.googleapis.com/youtube/v3"

def list_new_videos():
    # for each creator in allowlist, hit the uploads playlist and diff
    with Session() as s:
        creators = s.query(Creator).filter_by(platform="youtube", enabled=True).all()
    for c in creators:
        channel_id = resolve_channel_id(c.source_url)
        uploads_pl = get_uploads_playlist_id(channel_id)
        items = playlist_items(uploads_pl, max_results=20)
        for it in items:
            vid_id = it["contentDetails"]["videoId"]
            if not exists_in_db(vid_id):
                v = Video(creator_id=c.id, source_id=vid_id, status="queued")
                s.add(v); s.commit()
                from app.workers.tasks import enqueue_video_pipeline
                enqueue_video_pipeline(v.id)

def fetch_video_media(video_id:int)->str:
    # use yt-dlp with permission/license in place
    import subprocess, os, tempfile
    with Session() as s:
        v = s.get(Video, video_id)
    out = f"tmp/{v.source_id}.mp4"
    subprocess.check_call(["yt-dlp","-f","mp4","-o",out,f"https://youtu.be/{v.source_id}"])
    return out
