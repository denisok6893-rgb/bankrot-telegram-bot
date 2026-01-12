"""Test script for Case model and database operations."""
import asyncio
import logging
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bankrot_bot.database import init_db, get_session
from bankrot_bot.models.case import Case, CaseStage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_create_case():
    """Test creating a case."""
    logger.info("Testing case creation...")

    async with get_session() as session:
        # Create test case
        case = Case(
            user_id=123456789,
            debtor_name="Тестовый Должник ООО",
            debtor_inn="1234567890",
            case_number="А40-12345/2026",
            court="Арбитражный суд города Москвы",
            stage=CaseStage.OBSERVATION,
            manager_name="Иванов Иван Иванович",
        )
        session.add(case)
        await session.flush()

        logger.info(f"Created case: {case}")
        logger.info(f"Case ID: {case.id}")
        logger.info(f"\nFormatted card:\n{case.format_card()}")

        return case.id


async def test_list_cases(user_id: int):
    """Test listing cases."""
    logger.info(f"\nTesting case listing for user {user_id}...")

    from sqlalchemy import select

    async with get_session() as session:
        result = await session.execute(
            select(Case).where(Case.user_id == user_id).order_by(Case.id)
        )
        cases = result.scalars().all()

        logger.info(f"Found {len(cases)} cases:")
        for case in cases:
            logger.info(f"  - #{case.id}: {case.debtor_name} ({case.case_number})")


async def test_update_case(case_id: int):
    """Test updating a case."""
    logger.info(f"\nTesting case update for case #{case_id}...")

    from sqlalchemy import select

    async with get_session() as session:
        result = await session.execute(select(Case).where(Case.id == case_id))
        case = result.scalar_one_or_none()

        if not case:
            logger.error(f"Case #{case_id} not found")
            return

        # Update case
        case.stage = CaseStage.RESTRUCTURING
        case.manager_name = "Петров Петр Петрович"

        await session.flush()

        logger.info(f"Updated case #{case_id}")
        logger.info(f"\nUpdated card:\n{case.format_card()}")


async def test_delete_case(case_id: int):
    """Test deleting a case."""
    logger.info(f"\nTesting case deletion for case #{case_id}...")

    from sqlalchemy import select

    async with get_session() as session:
        result = await session.execute(select(Case).where(Case.id == case_id))
        case = result.scalar_one_or_none()

        if not case:
            logger.error(f"Case #{case_id} not found")
            return

        await session.delete(case)
        logger.info(f"Deleted case #{case_id}")


async def main():
    """Run all tests."""
    try:
        # Initialize database
        logger.info("Initializing database...")
        await init_db()
        logger.info("Database initialized\n")

        # Test create
        case_id = await test_create_case()

        # Test list
        await test_list_cases(123456789)

        # Test update
        await test_update_case(case_id)

        # Test delete
        # await test_delete_case(case_id)  # Uncomment to test deletion

        logger.info("\n✅ All tests completed successfully!")

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
