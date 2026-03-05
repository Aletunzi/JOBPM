"""
Migration v6: add scrape_error column to companies table.

Run with:
    python migrate_v6_scrape_error.py
"""

import asyncio
from dotenv import load_dotenv

load_dotenv()


async def main():
    from api.database import engine
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.execute(text("""
            ALTER TABLE companies
            ADD COLUMN IF NOT EXISTS scrape_error TEXT
        """))
    print("Migration v6 done: scrape_error column added to companies.")


if __name__ == "__main__":
    asyncio.run(main())
