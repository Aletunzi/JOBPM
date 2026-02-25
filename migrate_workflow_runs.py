"""
Additive migration: create workflow_runs table to track each scraper execution.
Safe to run multiple times (CREATE TABLE IF NOT EXISTS).

Usage:  python migrate_workflow_runs.py
"""

import asyncio
import os
from dotenv import load_dotenv

load_dotenv()


async def migrate():
    from sqlalchemy import text
    from api.database import engine

    statements = [
        """
        CREATE TABLE IF NOT EXISTS workflow_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            companies_scraped INTEGER,
            jobs_upserted INTEGER,
            duration_seconds INTEGER,
            trigger VARCHAR(50)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_workflow_runs_started_at ON workflow_runs (started_at DESC)",
    ]

    async with engine.begin() as conn:
        for stmt in statements:
            await conn.execute(text(stmt))

    print("Migration workflow_runs complete.")


if __name__ == "__main__":
    asyncio.run(migrate())
