"""
Application lifecycle events.
"""

import logging

logger = logging.getLogger("app.events")


async def on_startup():
    """Run on application startup."""
    logger.info("Application starting up...")


async def on_shutdown():
    """Run on application shutdown."""
    logger.info("Application shutting down...")
