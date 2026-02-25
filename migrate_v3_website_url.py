"""
Additive migration: add website_url and scrape-tracking columns to companies.
Safe to run multiple times (IF NOT EXISTS).

Usage:  python migrate_v3_website_url.py
"""

import asyncio
import os
from dotenv import load_dotenv

load_dotenv()


async def migrate():
    from sqlalchemy import text
    from api.database import engine

    statements = [
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS website_url TEXT",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS career_url_source VARCHAR(20) NOT NULL DEFAULT 'auto'",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS last_discovery_attempt TIMESTAMPTZ",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS scrape_status VARCHAR(30)",
    ]

    async with engine.begin() as conn:
        for stmt in statements:
            await conn.execute(text(stmt))
            print(f"  OK: {stmt.split('IF NOT EXISTS ')[1] if 'IF NOT EXISTS' in stmt else stmt}")

    print("Migration v3 complete: website_url + tracking columns added.")


if __name__ == "__main__":
    asyncio.run(migrate())
