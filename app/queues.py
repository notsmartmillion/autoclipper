# app/queues.py
# -------------------------------------------------
# Celery application singleton, task routing, and Beat schedule.
# Centralizes all periodic schedules here to avoid duplication.
# -------------------------------------------------

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.settings import Settings

settings = Settings()

# Create Celery app using Redis from your Settings
celery_app = Celery(
    "autoclipper",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

# Autodiscover tasks inside app.workers.* so you don't need to list modules manually
celery_app.autodiscover_tasks(["app.workers"])

# Task routing: keep your CPU queue for heavy steps, default for light steps
celery_app.conf.task_routes = {
    # Heavy CPU-ish tasks (ffmpeg, ASR, etc.)
    "app.workers.tasks.process_video": {"queue": "cpu"},
    "app.workers.tasks.publish_clip": {"queue": "cpu"},

    # Light tasks / orchestration
    "app.workers.tasks.poll_creators": {"queue": "default"},
    "app.workers.tasks.auto_pipeline": {"queue": "default"},
    "app.workers.tasks.discover_campaigns_task": {"queue": "default"},

    # Cleanup task lives in app.workers.beat
    "app.workers.beat.cleanup_tmp": {"queue": "default"},
}

# -------- Celery Beat (periodic tasks) --------
# Keep ALL schedules here, so Beat only needs this module.
celery_app.conf.beat_schedule = {
    # (Debug/visibility) Poll allowlisted creators every 15 minutes.
    # If you enable auto_pipeline below, you can remove this to avoid duplicate work.
    "poll-creators-15min": {
        "task": "app.workers.tasks.poll_creators",
        "schedule": 15 * 60,  # seconds
    },

    # End-to-end automation: discover new videos and enqueue full pipeline every 10 minutes.
    "auto-pipeline-every-10-min": {
        "task": "app.workers.tasks.auto_pipeline",
        "schedule": 10 * 60,  # seconds
    },

    # Cleanup tmp files (media/clips) older than 24h, every 6 hours.
    "cleanup-tmp-every-6h": {
        "task": "app.workers.beat.cleanup_tmp",
        "schedule": 6 * 60 * 60,  # seconds
        "args": (24,),            # max_age_hours
    },

    # Discover new campaigns daily at 06:00 UTC and write proposals to tmp/state/.
    "discover-campaigns-daily-06z": {
        "task": "app.workers.tasks.discover_campaigns_task",
        "schedule": crontab(minute=0, hour=6),
        # "args": (True,)  # set to True if you want to auto-merge proposals into allowlist (kept False by default)
    },
}

celery_app.conf.timezone = "UTC"
