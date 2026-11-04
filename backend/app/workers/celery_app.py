"""
Celery application instance.
"""

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "finance_chitti",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.APP_TIMEZONE,
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Rate limiting for WhatsApp API
    task_default_rate_limit="30/m",
)

# Auto-discover tasks
celery_app.autodiscover_tasks(["app.workers.tasks"])

# Beat schedule
celery_app.conf.beat_schedule = {
    "daily-reminder-check": {
        "task": "app.workers.tasks.reminder_tasks.send_due_reminders",
        "schedule": crontab(hour=8, minute=0),  # 08:00 IST
        "args": (),
    },
    "overdue-check": {
        "task": "app.workers.tasks.reminder_tasks.send_overdue_reminders",
        "schedule": crontab(hour=9, minute=0),  # 09:00 IST
        "args": (),
    },
    "schedule-maintenance": {
        "task": "app.workers.tasks.schedule_tasks.maintain_schedules",
        "schedule": crontab(hour=0, minute=30),  # 00:30 IST
        "args": (),
    },
    "daily-report": {
        "task": "app.workers.tasks.report_tasks.generate_daily_report",
        "schedule": crontab(hour=20, minute=0),  # 20:00 IST
        "args": (),
    },
}
