"""
Migration v5 — add URL timestamp columns (idempotent).

Adds two nullable columns to the companies table:
  - website_url_updated_at  TIMESTAMPTZ  (when website_url was last changed)
  - career_url_updated_at   TIMESTAMPTZ  (when career_url was last changed)

Safe to run multiple times: ALTER TABLE … ADD COLUMN IF NOT EXISTS is a no-op
when the column already exists.

Usage:  python migrate_v5_url_timestamps.py
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()


async def migrate():
    from sqlalchemy import text
    from api.database import engine

    async with engine.begin() as conn:
        await conn.execute(text("""
            ALTER TABLE companies
            ADD COLUMN IF NOT EXISTS website_url_updated_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS career_url_updated_at  TIMESTAMPTZ
        """))

    print("Migration v5 complete: website_url_updated_at and career_url_updated_at columns added.")


if __name__ == "__main__":
    asyncio.run(migrate())
