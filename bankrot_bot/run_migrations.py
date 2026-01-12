"""Script to run database migrations."""
import asyncio
import logging
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alembic import command
from alembic.config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migrations():
    """Run Alembic migrations."""
    try:
        # Get alembic configuration
        alembic_cfg = Config("alembic.ini")

        # Run migrations
        logger.info("Running database migrations...")
        command.upgrade(alembic_cfg, "head")
        logger.info("Migrations completed successfully!")

    except Exception as e:
        logger.error(f"Error running migrations: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    run_migrations()
