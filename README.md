Autoclipper
===========

Autonomous video clipping and publishing pipeline. Ingests approved creator videos, finds highlights with AI, edits/brands clips, and publishes to dedicated clip channels with claims governance and basic analytics.

## What this app does
- Ingest new videos from allowlisted creators (YouTube first).
- Transcribe audio (Whisper/WhisperX), detect scenes, fuse hotspots, score candidates.
- Let an LLM pick top moments and propose titles.
- Render Shorts-ready vertical clips with ffmpeg.
- Upload as Unlisted; later flip Public after a clean window.

## Repo layout
```
app/                # source package (FastAPI, Celery, services)
  routes/           # admin + webhooks routers
  services/         # intake, fetcher, analyze, clipper, editor, publisher, monitor
  workers/          # Celery tasks and beat schedule
config/             # allowlist + presets
docs/               # architecture, API, ops runbook
infra/              # migrations and infra (optional)
prompts/            # LLM prompts
tests/              # smoke tests
tmp/                # scratch (gitignored)
```

## Tech stack
- Python 3.11+/3.12, FastAPI, Celery + Redis
- WhisperX, PySceneDetect, OpenAI API
- ffmpeg, yt-dlp, Google API client (YouTube Data API)

## Quickstart (local without Docker)
1) Create a venv and activate:
```
python -m venv .venv
. .venv/Scripts/activate  # Windows PowerShell: .\.venv\Scripts\Activate.ps1
```
2) Install deps:
```
pip install -e .
```
3) Copy env and set required values:
```
cp .env.example .env
# minimally set: REDIS_URL, OPENAI_API_KEY, (YT_API_KEY for discovery)
```
4) Run API, worker, beat (separate shells):
```
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
celery -A app.queues.celery_app worker -l INFO --concurrency=4
celery -A app.queues.celery_app beat -l INFO
```

Smoke test Celery:
```
python -c "from app.workers.tasks import ping; print(ping.delay().get(timeout=10))"
```

## Quickstart (Docker)
Install Docker Desktop (Compose v2). Then:
```
docker compose up --build
```
API: `http://localhost:8000/healthz`, `http://localhost:8000/admin/ping`

## Environment (.env)
```
POSTGRES_URL=postgresql+psycopg://autoclipper:autoclipper@db:5432/autoclipper
REDIS_URL=redis://redis:6379/0
OPENAI_API_KEY=...
YT_API_KEY=...                # for discovery (uploads will require OAuth later)
S3_ENDPOINT=...
S3_BUCKET=autoclipper
S3_KEY=...
S3_SECRET=...
APP_ENV=development
LOG_LEVEL=INFO
```

## How the pipeline runs (no‑DB v1)
1) `poll_creators` reads `config/allowlist.yaml`, queries YouTube uploads, dedupes via `tmp/state/seen_videos.txt`.
2) For each new video id, `enqueue_video_pipeline(video_id)` runs:
   - `process_video(video_id)` → returns `[clip_dict...]`
   - `publish_many([clip_dict...])` → schedules one upload per clip
3) `publish_clip` uploads Unlisted and schedules a claim check task to flip Public later (stub for now).

Key modules:
- `app/workers/tasks.py`: Orchestrates the chain; has `ping`, `poll_creators`, `process_video`, `publish_many`, `publish_clip`, `auto_pipeline`.
- `app/services/fetcher/youtube.py`: Channel/playlist discovery (API key), download via `yt-dlp`.
- `app/services/analyze/*`: Transcribe, scene detect, candidate scoring.
- `app/services/clipper/*`: Candidate fusion and LLM ranking.
- `app/services/editor/ffmpeg_ops.py`: Clip rendering (static framing, no Ken Burns).
- `app/services/publisher/youtube_upload.py`: Upload Unlisted (API key client creation; replace with OAuth for real uploads).
- `app/services/monitor/claims.py`: Stubbed claim flip.
- `app/queues.py` and `app/workers/beat.py`: Celery app, routing, schedules.

## Current limitations / TODO
- YouTube uploads need OAuth (client id/secret + refresh token). API key is only for discovery.
- Claim checking is a stub; implement polling + flip.
- Optional DB path exists (models/migrations), but v1 operates file‑state only.
- Subtitles/thumbnail stubs to be wired for nicer outputs.

## Admin / Health
- `/health` and `/healthz` for probes
- `/admin/ping` sanity check
- `/admin/rescan` to trigger allowlist poll (stub)

## Notes
- Static images only in outputs; avoid Ken Burns (no zoom/pan).
- No image descriptions in prompts (handled elsewhere).


