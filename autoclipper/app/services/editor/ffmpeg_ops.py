import subprocess
import uuid
import os
from typing import Dict, Any


def render_clip(media_path: str, transcript_text: str, seg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Render a clip segment from a source video.

    Args:
        media_path: path to full video
        transcript_text: full transcript (optional, unused here but could be used for subtitles)
        seg: dict with keys start, end, title, reason

    Returns:
        dict with:
          - clip_id (uuid string for now)
          - path (output mp4 file)
          - start, end, dur
          - title
          - reason
    """
    start = int(seg["start"])
    end = int(seg["end"])
    dur = max(0, end - start)

    # Unique filename
    clip_id = str(uuid.uuid4())
    out_path = f"tmp/{clip_id}.mp4"
    os.makedirs("tmp", exist_ok=True)

    # ffmpeg trim + normalize + scale for Shorts
    vf = "loudnorm,scale=1080:-2, crop=1080:1920"

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-to", str(end),
        "-i", media_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-c:a", "aac", "-b:a", "128k",
        out_path
    ]

    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg failed: {e}")

    return {
        "clip_id": clip_id,
        "path": out_path,
        "start": start,
        "end": end,
        "dur": dur,
        "title": seg.get("title", "Untitled Clip"),
        "reason": seg.get("reason", ""),
    }
