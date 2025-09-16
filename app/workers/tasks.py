# app/workers/tasks.py
# -----------------------------------------------
# Celery tasks that orchestrate the end-to-end pipeline:
# fetch → transcribe → find/make candidates → score → LLM pick → render → upload → flip public
# -----------------------------------------------

from __future__ import annotations

import os
from celery import shared_task, chain
from app.settings import S
from app.queues import celery_app  # noqa: F401  (import for side effects)

# Fetching & ingest
from app.services.fetcher.youtube import list_new_videos, fetch_video_media

# Analysis (ASR + scenes + scoring)
from app.services.analyze.transcribe import transcribe_or_load
from app.services.analyze.scenes import find_candidate_segments
from app.services.analyze.scoring import score_candidates, ScoreConfig

# Candidate fusion (scene cuts + transcript hotspots + optional audio peaks)
from app.services.clipper.candidate_maker import make_candidates, CandidateConfig

# LLM ranking (choose best highlights, add titles/reasons)
from app.services.clipper.ranker_llm import pick_top_segments

# Rendering & publishing
from app.services.editor.ffmpeg_ops import render_clip
from app.services.publisher.youtube_upload import upload_short
from app.services.monitor.claims import check_claim_then_publish

# Campaign discovery (proposes allowlist entries)
from app.services.intake.campaign_watcher import propose_allowlist_updates


@shared_task
def ping() -> str:
    """Simple smoke test to verify worker is alive."""
    return "pong"


@shared_task
def poll_creators() -> list[str]:
    """
    Discover NEW video IDs from the allowlisted creators (no-DB mode).
    - Reads config/allowlist.yaml
    - Hits YouTube Data API to find recent uploads
    - Returns only unseen IDs (tracked in tmp/state/seen_videos.txt)
    """
    return list_new_videos()


@shared_task
def process_video(video_id: str) -> list[dict]:
    """
    Process a single source video and return a list of rendered clip records.

    Steps:
      1) Download the source media (with permission) → mp4 path
      2) Transcribe (Whisper/WhisperX) → transcript JSON + text
      3) Detect scene cuts → coarse candidates
      4) Fuse candidates (scene + transcript hotspots + audio peaks)
      5) Score candidates (energy/keywords/sentiment/pace/len-fit)
      6) Ask LLM to pick top N highlights & suggest titles
      7) Render each chosen segment with ffmpeg (vertical, subs later)
    Returns:
      A list of clip dicts: [{"clip_id","path","start","end","dur","title","reason"}, ...]
    """
    # 1) Download
    media_path = fetch_video_media(video_id)

    # 2) Transcribe
    asr_json_path, transcript_text = transcribe_or_load(media_path, video_id)

    # 3) Scene detection (visual cuts) → coarse windows
    scene_candidates = find_candidate_segments(media_path, transcript_text)

    # 4) Fuse with transcript hotspots (+ optional audio peaks via pydub)
    candidates = make_candidates(
        media_path,
        asr_json_path,
        scene_candidates,
        cfg=CandidateConfig(),  # override per-creator later if needed
    )

    # 5) Score all candidates and prune to the best ~20 for the LLM
    scored = score_candidates(
        media_path,
        asr_json_path,
        candidates,
        cfg=ScoreConfig(),  # override per-creator later if needed
    )
    top_scored = scored[:20]

    # 6) LLM: choose final highlights & generate titles
    selected = pick_top_segments(
        transcript_text,
        top_scored,
        top_n=3,        # render up to 3 clips per source video
    )

    # 7) Render each selected segment → final mp4s
    clip_records: list[dict] = []
    for seg in selected:
        clip = render_clip(media_path, transcript_text, seg)
        clip_records.append(clip)

    if not S.publish_enabled:
        print(f"[SAFE MODE] Finished processing {video_id}, rendered {len(clip_records)} clips. Upload skipped.")
    else:
        print(f"[LIVE MODE] Finished processing {video_id}, rendered {len(clip_records)} clips. Upload will be enqueued.")

    return clip_records


@shared_task
def publish_clip(clip: dict) -> dict:
    """
    Upload one rendered clip to YouTube as UNLISTED, then schedule a flip to PUBLIC.
    Respects publish_enabled flag (safe mode).
    """
    if not S.publish_enabled:
        print(f"[SAFE MODE] Skipping upload for clip {clip.get('clip_id')} ({clip.get('path')})")
        return {"status": "skipped", "clip": clip}

    uploaded = upload_short(clip, visibility="unlisted")

    # Schedule a claim check / flip to public after a 30 min hold.
    check_claim_then_publish.apply_async(args=[uploaded["video_id"]], countdown=1800)
    return uploaded

@shared_task
def publish_many(clips: list[dict]) -> list[str]:
    """
    Fan-out: enqueue one publish task per rendered clip.
    Returns a list of Celery task IDs (not YouTube video IDs).
    """
    task_ids: list[str] = []
    for clip in clips:
        async_res = publish_clip.delay(clip)
        task_ids.append(async_res.id)
    return task_ids


def enqueue_video_pipeline(video_id: str) -> None:
    """
    Orchestrates the pipeline for a single video:
      process_video(video_id) → returns [clip_dict...]
      publish_many([clip_dict...]) → enqueues uploads per clip
    """
    print(f"[pipeline] enqueue video_id={video_id}")
    chain(
        process_video.s(video_id),
        publish_many.s(),
    )()


# -------------------------------
# Periodic wrappers (used by Beat)
# -------------------------------

@shared_task
def auto_pipeline() -> dict:
    """
    Periodic: fetch new video IDs and kick the full pipeline for each.
    Controlled by AUTO_PIPELINE_ENABLED env var (default: on).

    Returns a summary:
      {"found": <int>, "enqueued": <int>, "video_ids": [...]}
    """
    ids = poll_creators.apply().get()  # run inline for visible logs
    enqueued = 0

    if os.getenv("AUTO_PIPELINE_ENABLED", "1") not in ("1", "true", "True"):
        return {"found": len(ids), "enqueued": 0, "video_ids": ids}

    for vid in ids:
        try:
            enqueue_video_pipeline(vid)
            enqueued += 1
        except Exception as e:
            print(f"[auto_pipeline] failed to enqueue {vid}: {e}")

    return {"found": len(ids), "enqueued": enqueued, "video_ids": ids}


@shared_task
def discover_campaigns_task(auto_merge: bool = False) -> dict:
    """
    Periodic: discover new campaign opportunities from configured providers.
    Writes proposals to tmp/state/campaign_inbox.json.
    If auto_merge=True, appends proposals (disabled) to config/allowlist.yaml.
    """
    return propose_allowlist_updates(auto_merge=auto_merge)
