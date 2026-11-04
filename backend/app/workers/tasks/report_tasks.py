"""
Report generation tasks.
"""

import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.tasks.report_tasks.generate_daily_report")
def generate_daily_report():
    """
    Generate and distribute daily collection report.
    Runs at 20:00 IST.
    """
    logger.info("Generating daily report...")
    # Implementation in Phase 7
    return {"status": "completed"}
