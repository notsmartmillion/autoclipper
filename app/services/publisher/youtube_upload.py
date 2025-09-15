from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import os

# TODO: replace with real credential handling later
API_KEY = os.getenv("YT_API_KEY")

def yt_client():
    return build("youtube", "v3", developerKey=API_KEY)


def upload_short(clip: dict, visibility: str = "unlisted") -> dict:
    """
    Upload a rendered clip to YouTube.

    Args:
        clip: dict with {path, title, reason, ...}
        visibility: "unlisted" (default), "public", or "private"

    Returns:
        dict with {"video_id": "...", "url": "..."}
    """
    yt = yt_client()

    body = {
        "snippet": {
            "title": clip.get("title", "Untitled Clip"),
            "description": clip.get("reason", "") + "\n\n#shorts",
            "tags": ["shorts", "highlights", "clips"],
            "categoryId": "24",  # Entertainment
        },
        "status": {
            "privacyStatus": visibility,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(clip["path"], chunksize=-1, resumable=True)

    request = yt.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )
    response = request.execute()

    video_id = response["id"]
    return {
        "video_id": video_id,
        "url": f"https://youtu.be/{video_id}",
    }
