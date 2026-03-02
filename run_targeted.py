"""
Targeted scraper: run career URL discovery + scraping for specific companies only.

Usage:
    TARGET_COMPANIES="Nokia,Autodesk,VMware" python run_targeted.py

The TARGET_COMPANIES env var is a comma-separated list of exact company names
as they appear in the database (case-sensitive).
"""

import asyncio
import logging
import os
from collections import Counter
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import select

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("targeted_scraper")

CONCURRENCY = 5


async def main():
    from api.database import AsyncSessionLocal
    from api.models import Company
    from scrapers.url_discovery import discover_all
    from run_scraper import scrape_company

    raw = os.environ.get("TARGET_COMPANIES", "").strip()
    if not raw:
        logger.error(
            "TARGET_COMPANIES env var is required. "
            'Set it to comma-separated company names, e.g. "Nokia,Autodesk,VMware"'
        )
        return

    target_names = [n.strip() for n in raw.split(",") if n.strip()]
    logger.info("=== Targeted scrape starting for %d companies ===", len(target_names))
    logger.info("Companies: %s", ", ".join(target_names))
    start = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:

        result = await session.execute(
            select(Company).where(
                Company.is_enabled == True,
                Company.name.in_(target_names),
            )
        )
        companies = result.scalars().all()

        found_names = {c.name for c in companies}
        missing = [n for n in target_names if n not in found_names]
        if missing:
            logger.warning("Not found in DB (skipped): %s", ", ".join(missing))

        logger.info("Processing %d companies", len(companies))

        # ── Phase 0b: Career URL Discovery ───────────────────────────────
        missing_url = [c for c in companies if not c.career_url]
        if missing_url:
            logger.info("--- Phase 0b: Career URL Discovery for %d companies ---", len(missing_url))
            discovered = await discover_all(missing_url, max_companies=len(missing_url))

            for company in missing_url:
                url = discovered.get(company.name)
                if url:
                    company.career_url = url

            if discovered:
                await session.commit()
                logger.info("Phase 0b done: %d URLs discovered", len(discovered))
            else:
                logger.info("Phase 0b done: no new URLs found")
        else:
            logger.info("All target companies already have career URLs.")

        # ── Phase 1: Scrape companies that have a career_url ─────────────
        to_scrape = [c for c in companies if c.career_url]
        no_url = [c.name for c in companies if not c.career_url]

        if no_url:
            logger.warning("Skipped (no career URL found): %s", ", ".join(no_url))

        if not to_scrape:
            logger.warning("No companies have a career URL — nothing to scrape.")
            return

        logger.info("--- Phase 1: Scraping %d companies ---", len(to_scrape))

        semaphore = asyncio.Semaphore(CONCURRENCY)
        tasks = [
            scrape_company(
                AsyncSessionLocal,
                c.id,
                {"career_url": c.career_url, "name": c.name, "page_hash": c.page_hash},
                semaphore,
            )
            for c in to_scrape
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        status_counts = Counter()
        total_jobs = 0
        for r in results:
            if isinstance(r, Exception):
                status_counts["ERROR"] += 1
            else:
                job_count, status = r
                total_jobs += job_count
                status_counts[status] += 1

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    logger.info("=== Done: %d jobs upserted in %.1fs ===", total_jobs, elapsed)
    for status, count in sorted(status_counts.items()):
        logger.info("  %s: %d companies", status, count)


if __name__ == "__main__":
    asyncio.run(main())
