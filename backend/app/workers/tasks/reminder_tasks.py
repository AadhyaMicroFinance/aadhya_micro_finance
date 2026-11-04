"""
Reminder Celery tasks — due and overdue notifications.
"""

import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.tasks.reminder_tasks.send_due_reminders")
def send_due_reminders():
    """
    Check for accounts due tomorrow and send reminder notifications.
    Runs daily at 08:00 IST.
    Prevents duplicate notifications by checking whatsapp_message_logs.
    """
    logger.info("Running due reminder check...")
    # Implementation in Phase 8 (WhatsApp) + Phase 9 (Scheduler)
    return {"status": "completed", "reminders_sent": 0}


@celery_app.task(name="app.workers.tasks.reminder_tasks.send_overdue_reminders")
def send_overdue_reminders():
    """
    Check for overdue accounts and send overdue notifications.
    Runs daily at 09:00 IST.
    """
    logger.info("Running overdue reminder check...")
    # Implementation in Phase 8 + Phase 9
    return {"status": "completed", "overdue_notifications_sent": 0}
