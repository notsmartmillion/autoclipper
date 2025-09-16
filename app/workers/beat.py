# app/workers/beat.py
# -------------------------------------------------
# Celery Beat schedule: defines periodic tasks
# (what to run automatically, and how often).
# -------------------------------------------------

from datetime import timedelta
from pathlib import Path
import shutil
import time

from celery import shared_task
from app.queues import celery_app


# -------------------------------
# Periodic tasks
# -------------------------------

@shared_task
def cleanup_tmp(max_age_hours: int = 24) -> int:
    """
    Delete files older than `max_age_hours` from tmp/media and tmp/clips.
    Returns the count of deleted files.
    """
    cutoff = time.time() - (max_age_hours * 3600)
    base = Path("tmp")
    deleted = 0

    # Ensure expected subdirs exist
    for subdir in ("media", "clips"):
        d = base / subdir
        if not d.exists():
            continue

        for f in d.iterdir():
            try:
                # Delete old files
                if f.is_file() and f.stat().st_mtime < cutoff:
                    f.unlink()
                    deleted += 1
                # Delete old directories (e.g., per-clip folders if you create any)
                elif f.is_dir() and f.stat().st_mtime < cutoff:
                    shutil.rmtree(f)
                    deleted += 1
            except Exception as e:
                print(f"[cleanup_tmp] Failed to remove {f}: {e}")

    return deleted


# -------------------------------
# Celery Beat schedule
# -------------------------------

# Base schedule: you can keep both poll-only and auto-pipeline, or
# remove the poll job once auto-pipeline is stable.
celery_app.conf.beat_schedule = {
    # Run the allowlist poller every 10 minutes (debugging/visibility)
    "poll-creators-every-10-min": {
        "task": "app.workers.tasks.poll_creators",
        "schedule": timedelta(minutes=10),
    },
    # Cleanup old tmp files every 6 hours
    "cleanup-tmp-every-6h": {
        "task": "app.workers.beat.cleanup_tmp",
        "schedule": timedelta(hours=6),
        "args": (24,),  # delete files older than 24 hours
    },
}

# Add the end-to-end auto pipeline & campaign discovery
celery_app.conf.beat_schedule.update({
    # End-to-end: find new videos & enqueue full pipeline every 10 minutes
    "auto-pipeline-every-10-min": {
        "task": "app.workers.tasks.auto_pipeline",
        "schedule": timedelta(minutes=10),
    },
    # Discover new campaigns daily (writes proposals to tmp/state/)
    "discover-campaigns-every-day": {
        "task": "app.workers.tasks.discover_campaigns_task",
        "schedule": timedelta(days=1),
    },
})

# Use UTC unless you have a specific reason not to
celery_app.conf.timezone = "UTC"
