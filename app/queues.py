from celery import Celery
from celery.schedules import crontab

from app.settings import Settings


settings = Settings()

celery_app = Celery(
    "autoclipper",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.workers.tasks",
    ],
)

celery_app.conf.update(
    task_routes={
        "app.workers.tasks.process_video": {"queue": "cpu"},
        "app.workers.tasks.publish_clip": {"queue": "cpu"},
        "app.workers.tasks.poll_creators": {"queue": "default"},
    },
    beat_schedule={
        "poll-creators-15min": {
            "task": "app.workers.tasks.poll_creators",
            "schedule": 15 * 60,
        }
    },
    timezone="UTC",
)
