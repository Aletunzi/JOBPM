"""
PM Job Tracker — Daily scraper orchestrator (LLM rolling).
Run with: python run_scraper.py
Or triggered by GitHub Actions cron.

Architecture:
  Phase 1: LLM Rolling — scrape companies due for refresh via GPT-4o-mini
  Phase 2: Maintenance — mark stale jobs inactive, refresh search vectors
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from sqlalchemy import text, select, and_, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("scraper")

CONCURRENCY = 5       # max parallel LLM requests
MAX_PER_RUN = 200     # max companies per run (rolling window)
DELAY_BETWEEN = 2     # seconds between requests (rate limiting)


# ── Core: upsert jobs ────────────────────────────────────────────────────────

async def upsert_jobs(session, jobs: list, company_id=None):
    from api.models import Job
    from sqlalchemy import func

    if not jobs:
        return 0

    count = 0
    for job in jobs:
        if not job.url:
            continue

        posted_dt = None
        if job.posted_date:
            posted_dt = datetime.combine(job.posted_date, datetime.min.time()).replace(tzinfo=timezone.utc)

        stmt = pg_insert(Job).values(
            company_id=company_id,
            company_name=job.company_name,
            source=job.source,
            source_id=job.source_id,
            title=job.title,
            location_raw=job.location_raw,
            geo_region=job.geo_region,
            seniority=job.seniority,
            url=job.url,
            posted_date=posted_dt,
            first_seen=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
            is_active=True,
            search_vector=func.to_tsvector("english", job.title + " " + job.company_name),
        ).on_conflict_do_update(
            constraint="uq_job_source",
            set_={
                "last_seen": datetime.now(timezone.utc),
                "is_active": True,
                "search_vector": func.to_tsvector("english", job.title + " " + job.company_name),
            },
        )
        await session.execute(stmt)
        count += 1

    await session.commit()
    return count


# ── Scrape a single company via LLM ──────────────────────────────────────────

async def scrape_company(session, company, semaphore: asyncio.Semaphore):
    from scrapers.llm_career import fetch_custom

    async with semaphore:
        try:
            jobs, new_hash = await fetch_custom(
                career_url=company.career_url,
                company_name=company.name,
                page_hash=company.page_hash,
            )

            count = await upsert_jobs(session, jobs, company_id=company.id)

            # Update company scrape metadata
            company.last_scraped = datetime.now(timezone.utc)
            company.page_hash = new_hash
            await session.commit()

            if count:
                logger.info("  %s: %d PM jobs upserted", company.name, count)
            return count

        except Exception as exc:
            logger.error("  %s: error — %s", company.name, exc)
            return 0
        finally:
            await asyncio.sleep(DELAY_BETWEEN)


# ── Maintenance ───────────────────────────────────────────────────────────────

async def mark_inactive_jobs(session):
    """Jobs not seen in last 7 days are marked inactive."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    await session.execute(
        text("UPDATE jobs SET is_active = false WHERE last_seen < :cutoff AND is_active = true"),
        {"cutoff": cutoff},
    )
    await session.commit()


async def refresh_search_vectors(session):
    """Ensure search_vector is populated for all jobs."""
    await session.execute(
        text("""
            UPDATE jobs
            SET search_vector = to_tsvector('english', title || ' ' || company_name)
            WHERE search_vector IS NULL
        """)
    )
    await session.commit()


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    from api.database import AsyncSessionLocal
    from api.models import Company

    logger.info("=== Scrape starting (LLM rolling) ===")
    start = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        # ── Phase 1: LLM Rolling ──────────────────────────────────────────
        logger.info("--- Phase 1: LLM career page scraping ---")

        # Get companies due for scraping: enabled, has URL, and overdue
        # Use a fixed 5-day default since Column can't be used in timedelta directly
        cutoff_default = datetime.now(timezone.utc) - timedelta(days=5)
        result = await session.execute(
            select(Company)
            .where(
                and_(
                    Company.is_enabled == True,
                    Company.career_url.is_not(None),
                    or_(
                        Company.last_scraped.is_(None),
                        Company.last_scraped < cutoff_default,
                    ),
                )
            )
            .order_by(Company.last_scraped.asc().nulls_first())
            .limit(MAX_PER_RUN)
        )
        companies = result.scalars().all()
        logger.info("Companies due for scraping: %d", len(companies))

        if companies:
            semaphore = asyncio.Semaphore(CONCURRENCY)
            tasks = [scrape_company(session, c, semaphore) for c in companies]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            total_jobs = sum(r for r in results if isinstance(r, int))
            errors = sum(1 for r in results if isinstance(r, Exception))
            logger.info("Phase 1 done: %d jobs upserted, %d errors", total_jobs, errors)
        else:
            total_jobs = 0
            logger.info("No companies due for scraping today.")

        # ── Phase 2: Maintenance ──────────────────────────────────────────
        logger.info("--- Phase 2: Maintenance ---")
        await mark_inactive_jobs(session)
        await refresh_search_vectors(session)

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    logger.info("=== Done: %d jobs upserted in %.1fs ===", total_jobs, elapsed)


if __name__ == "__main__":
    asyncio.run(main())
