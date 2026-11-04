"""
Notification Celery tasks — send WhatsApp messages asynchronously.
"""

import logging
from uuid import UUID

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.workers.tasks.notification_tasks.send_whatsapp_notification",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def send_whatsapp_notification(
    self,
    customer_id: str,
    phone_number: str,
    template_name: str,
    template_params: dict,
    related_transaction_id: str | None = None,
):
    """
    Send a WhatsApp notification via the WhatsApp Business Cloud API.
    This runs asynchronously after payment recording.
    """
    logger.info(
        "Queuing WhatsApp notification: template=%s, customer=%s",
        template_name,
        customer_id,
    )

    # WhatsApp service call will be implemented in Phase 8
    # For now, log the intent
    logger.info(
        "WhatsApp notification ready to send: %s to %s",
        template_name,
        phone_number,
    )
    return {
        "status": "queued",
        "customer_id": customer_id,
        "template_name": template_name,
    }
