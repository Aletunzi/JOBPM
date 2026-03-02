"""
Delete all companies with is_enabled = False from the database,
along with all their associated job listings.

Safe to run multiple times — if no disabled companies exist, exits cleanly.

Usage:  python cleanup_disabled.py
"""

import asyncio
import os

from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()


async def cleanup():
    from api.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        # Preview what will be deleted
        result = await session.execute(
            text("SELECT name FROM companies WHERE is_enabled = false ORDER BY name")
        )
        rows = result.fetchall()

        if not rows:
            print("No disabled companies found — nothing to clean up.")
            return

        print(f"Found {len(rows)} disabled companies:")
        for (name,) in rows:
            print(f"  - {name}")

        # Delete their jobs first (FK has no ON DELETE CASCADE)
        result = await session.execute(
            text("""
                DELETE FROM jobs
                WHERE company_id IN (
                    SELECT id FROM companies WHERE is_enabled = false
                )
            """)
        )
        jobs_deleted = result.rowcount

        # Delete the companies
        result = await session.execute(
            text("DELETE FROM companies WHERE is_enabled = false")
        )
        companies_deleted = result.rowcount

        await session.commit()
        print(f"Deleted {companies_deleted} companies and {jobs_deleted} associated jobs.")


if __name__ == "__main__":
    asyncio.run(cleanup())
