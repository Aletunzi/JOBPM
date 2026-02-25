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

            # Build values for insert
            values = dict(
                name=name,
                tier=c.get("tier", 3),
                size=c.get("size"),
                vertical=c.get("vertical"),
                geo_primary=c.get("geo_primary"),
                career_url=c.get("career_url"),
                is_enabled=True,
                scrape_interval_days=5,
            )

            # Include website_url if provided in YAML
            if c.get("website_url"):
                values["website_url"] = c["website_url"]

            # If career_url is explicitly set in YAML, mark source as "yaml"
            if c.get("career_url"):
                values["career_url_source"] = "yaml"

            # Build update set for upsert
            update_set = {
                "tier": c.get("tier", 3),
                "size": c.get("size"),
                "vertical": c.get("vertical"),
                "geo_primary": c.get("geo_primary"),
            }

            # Only overwrite website_url if explicitly provided
            if c.get("website_url"):
                update_set["website_url"] = c["website_url"]

            # Only overwrite career_url if explicitly provided
            if c.get("career_url"):
                update_set["career_url"] = c["career_url"]
                update_set["career_url_source"] = "yaml"

            stmt = pg_insert(Company).values(**values).on_conflict_do_update(
                constraint="uq_company_name",
                set_=update_set,
            )

            result = await session.execute(stmt)
            if result.rowcount:
                inserted += 1
            else:
                updated += 1

        await session.commit()

    print(f"Seeded: {inserted} companies inserted/updated, {updated} unchanged.")
    print("Note: website_url and career_url are discovered automatically if not set in YAML.")


if __name__ == "__main__":
    asyncio.run(seed())
