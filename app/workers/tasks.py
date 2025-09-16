from celery import shared_task, chain
from app.services.fetcher.youtube import list_new_videos, fetch_video_media
from app.services.analyze.transcribe import transcribe_or_load
from app.services.analyze.scenes import find_candidate_segments
from app.services.analyze.scoring import score_candidates, ScoreConfig
from app.services.clipper.ranker_llm import pick_top_segments
from app.services.editor.ffmpeg_ops import render_clip
from app.services.publisher.youtube_upload import upload_short
from app.services.monitor.claims import check_claim_then_publish


@shared_task
def poll_creators():
    # iterate allowlist → enqueue new video ids
    return list_new_videos()


@shared_task
def ping() -> str:
    return "pong"


@shared_task
def process_video(video_id: int):
    """
    Main pipeline for one video:
      - download
      - transcribe
      - detect scenes / candidate segments
      - score segments
      - LLM ranking
      - render clips
    """
    # 1. Download
    media_path = fetch_video_media(video_id)

    # 2. Transcribe
    asr_path, transcript = transcribe_or_load(media_path, video_id)

    # 3. Scene detection → candidate windows
    candidates = find_candidate_segments(media_path, transcript)

    # 4. Score candidates
    scored = score_candidates(media_path, asr_path, candidates, cfg=ScoreConfig())

    # Narrow to best ~20 before LLM
    top_scored = scored[:20]

    # 5. Rank with LLM (adds human-like highlight sense + titles)
    selected = pick_top_segments(transcript, top_scored, top_n=5)

    # 6. Render
    clip_records = []
    for seg in selected:
        clip = render_clip(media_path, transcript, seg)
        clip_records.append(clip)

    return clip_records



@shared_task
def publish_clip(clip_id: int):
    upload_id = upload_short(clip_id, visibility="unlisted")
    # hold unlisted briefly; then check claims & flip public
    return check_claim_then_publish.s(upload_id).apply_async(countdown=1800)  # 30 min

@shared_task
def publish_clip(clip: dict):
    """
    Upload one clip dict (with path/title/reason) to YouTube.
    """
    uploaded = upload_short(clip, visibility="unlisted")

    # hold unlisted briefly, then schedule claim check → public
    return check_claim_then_publish.s(uploaded["video_id"]).apply_async(countdown=1800)


@shared_task
def publish_many(clips: list[dict]) -> list[str]:
    video_ids: list[str] = []
    for clip in clips:
        res = publish_clip.delay(clip)
        video_ids.append(res.id)
    return video_ids



def enqueue_video_pipeline(video_id: int):
    chain(process_video.s(video_id), publish_many.s())()
