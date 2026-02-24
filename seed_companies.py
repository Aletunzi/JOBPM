"""
Seed the companies table from companies.yaml.
Safe to run multiple times (upserts by name).

Usage:  python seed_companies.py
"""

import asyncio
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from sqlalchemy.dialects.postgresql import insert as pg_insert

load_dotenv()


async def seed():
    from api.database import AsyncSessionLocal
    from api.models import Company

    yaml_path = Path(__file__).parent / "companies.yaml"
    with open(yaml_path) as f:
        config = yaml.safe_load(f)

    companies = config.get("companies", [])
    print(f"Loaded {len(companies)} companies from companies.yaml")

    inserted = 0
    updated = 0

    async with AsyncSessionLocal() as session:
        for c in companies:
            name = c.get("name")
            if not name:
                continue

            stmt = pg_insert(Company).values(
                name=name,
                tier=c.get("tier", 3),
                size=c.get("size"),
                vertical=c.get("vertical"),
                geo_primary=c.get("geo_primary"),
                career_url=c.get("career_url"),  # None for most
                is_enabled=True,
                scrape_interval_days=5,
            ).on_conflict_do_update(
                constraint="uq_company_name",
                set_={
                    "tier": c.get("tier", 3),
                    "size": c.get("size"),
                    "vertical": c.get("vertical"),
                    "geo_primary": c.get("geo_primary"),
                },
            )

            result = await session.execute(stmt)
            if result.rowcount:
                inserted += 1
            else:
                updated += 1

        await session.commit()

    print(f"Seeded: {inserted} companies inserted/updated, {updated} unchanged.")
    print("Note: career_url is NULL for most companies. Add URLs to enable LLM scraping.")


if __name__ == "__main__":
    asyncio.run(seed())
