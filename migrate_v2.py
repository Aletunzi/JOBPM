"""
One-shot migration: drops all tables and recreates with the new schema.
Run this ONCE before deploying the new LLM-based scraper architecture.

Usage:  python migrate_v2.py
"""

import asyncio
import os
from dotenv import load_dotenv

load_dotenv()


async def migrate():
    from sqlalchemy import text
    from api.database import engine
    from api.models import Base  # noqa: F401 — ensures all models are registered

    print("Dropping existing tables...")
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS jobs CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS companies CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS api_usage CASCADE"))

    print("Recreating tables with new schema...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("Done. Tables recreated. Run seed_companies.py next to populate companies.")


if __name__ == "__main__":
    asyncio.run(migrate())
