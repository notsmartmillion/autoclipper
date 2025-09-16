Project Context: Autoclipper
============================

Purpose
-------
Autonomous pipeline to ingest approved creator videos, find highlight moments with AI, render Shorts-ready clips, and publish them (YouTube first) with claims governance and basic analytics.

High-level flow
---------------
1) Discovery: read `config/allowlist.yaml`, find new uploads via YouTube Data API (API key for discovery only).
2) Ingest: download media with `yt-dlp` (where licensed/allowed).
3) Analysis: transcribe (Whisper/WhisperX), detect scenes, fuse transcript/audio hotspots, score candidates.
4) Selection: LLM ranks top moments and proposes titles.
5) Editing: ffmpeg renders vertical 9:16 clips (static framing; subtitles/thumbnail stubs exist).
6) Publishing: upload Unlisted, then flip Public after clean claim window (stubbed).
7) Scheduling/beat: periodic polling and cleanup via Celery Beat.

Repo layout (top-level)
-----------------------
- `app/` source package
  - `main.py` FastAPI app; routes mounted; `/health`, `/healthz`
  - `queues.py` Celery app, routing, beat schedule
  - `workers/` tasks & beat tasks: `tasks.py`, `beat.py`
  - `routes/` admin + webhooks
  - `services/` intake, fetcher, analyze, clipper, editor, publisher, monitor
  - `settings.py`, `db.py`, `models.py`, `schemas.py` (DB optional in v1)
- `config/` allowlist and presets
- `prompts/` LLM prompts
- `infra/` migrations (DB optional)
- `docs/` architecture/API/ops (stubs)
- `tests/` smoke tests
- `tmp/` scratch/state (gitignored)

Key modules and responsibilities
--------------------------------
- `app/workers/tasks.py`
  - `ping()` smoke test
  - `poll_creators()` finds new video IDs (no-DB state in `tmp/state/seen_videos.txt`)
  - `process_video(video_id)` → returns `[clip_dict...]`
  - `publish_clip(clip)` uploads Unlisted and schedules claim check
  - `publish_many([clip_dict...])` fan-out uploader
  - `enqueue_video_pipeline(video_id)` chains `process_video → publish_many`
  - `auto_pipeline()` periodic end-to-end orchestration (guarded by env)
- `app/workers/beat.py` periodic cleanup and schedules
- `app/services/fetcher/youtube.py` discovery + `yt-dlp` download
- `app/services/analyze/transcribe.py` WhisperX JSON load/exec
- `app/services/analyze/scenes.py` scene detection (PySceneDetect)
- `app/services/analyze/scoring.py` candidate scoring (keywords, energy, sentiment, pace, cohesion, length fit)
- `app/services/clipper/candidate_maker.py` fuse scene + transcript + audio hotspots
- `app/services/clipper/ranker_llm.py` LLM-based final selection & titles
- `app/services/editor/ffmpeg_ops.py` trimming, loudnorm, scaling, vertical crop
- `app/services/publisher/youtube_upload.py` upload (API key client creation for now)
- `app/services/monitor/claims.py` stub: delayed flip to public
- `app/services/intake/allowlist_manager.py` `load_allowlist`, `iter_enabled_creators`
- `app/routes/admin.py` `/admin/ping`, `/admin/rescan` (stub), `/admin/creators` (stub)
- `app/routes/webhooks.py` placeholder webhook

Environment & running
---------------------
- `.env.example` → copy to `.env`. Minimal vars to run pipeline up to rendering:
  - `REDIS_URL=redis://redis:6379/0`
  - `OPENAI_API_KEY=...`
  - `YT_API_KEY=...` (discovery only; real uploads require OAuth later)
- Local:
  - `uvicorn app.main:app --reload`
  - `celery -A app.queues.celery_app worker -l INFO --concurrency=4`
  - `celery -A app.queues.celery_app beat -l INFO`
- Docker: `docker compose up --build` (requires Docker Desktop / Compose v2)

Smoke tests
-----------
- Health: `GET /healthz`, `GET /admin/ping`
- Celery: `python -c "from app.workers.tasks import ping; print(ping.delay().get(timeout=10))"`
- Pipeline: `python -c "from app.workers.tasks import enqueue_video_pipeline; enqueue_video_pipeline('<video_id>')"`

Design notes & guardrails
-------------------------
- 1:1 clip channel per creator; strict allowlist.
- Upload Unlisted; flip Public after clean window; auto-pause if claims spike (future).
- Static images only in outputs; no Ken Burns (no zoom/pan animations).
- Script/prompt generation omits image descriptions (handled by a separate LLM).
- Before adding new classes, scan project to avoid duplicates.
- Activate Python venv before running Python locally.

What’s intentionally stubbed for v1
-----------------------------------
- YouTube OAuth upload flow (replace API key client with OAuth2 + refresh token).
- Claim polling and flip logic (currently delays and returns clean).
- Subtitles renderer and thumbnails (stubs exist; wire simple implementations).
- DB usage (models/migrations present; no-DB file state used in v1).

Next steps
----------
- Implement OAuth upload and claim polling.
- Wire subtitles/thumbnails for better outputs.
- Optional: Admin CRUD for creators/campaigns; dashboard.


