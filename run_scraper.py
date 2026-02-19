"""
PM Job Tracker — Daily scraper orchestrator.
Run with: python run_scraper.py
Or triggered by GitHub Actions cron.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone

import yaml
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("scraper")

CONCURRENCY = 10  # max concurrent ATS requests


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


async def ensure_company(session, company_data: dict):
    from api.models import Company
    from sqlalchemy import select

    ats_type = company_data["ats"]
    ats_slug = company_data.get("slug")

    result = await session.execute(
        select(Company).where(
            Company.ats_type == ats_type,
            Company.ats_slug == ats_slug,
        )
    )
    company = result.scalar_one_or_none()

    if not company:
        company = Company(
            name=company_data["name"],
            ats_type=ats_type,
            ats_slug=ats_slug,
            tier=company_data.get("tier", 3),
            size=company_data.get("size"),
            vertical=company_data.get("vertical"),
            geo_primary=company_data.get("geo_primary"),
        )
        session.add(company)
        await session.commit()
        await session.refresh(company)

    return company


async def scrape_company(session, company_data: dict, semaphore: asyncio.Semaphore):
    ats = company_data["ats"]
    name = company_data["name"]
    slug = company_data.get("slug", "")

    async with semaphore:
        company_obj = await ensure_company(session, company_data)
        jobs = []

        if ats == "greenhouse":
            from scrapers.greenhouse import fetch_greenhouse
            async for job in fetch_greenhouse(slug, name):
                jobs.append(job)
        elif ats == "lever":
            from scrapers.lever import fetch_lever
            async for job in fetch_lever(slug, name):
                jobs.append(job)
        elif ats == "ashby":
            from scrapers.ashby import fetch_ashby
            async for job in fetch_ashby(slug, name):
                jobs.append(job)
        elif ats == "smartrecruiters":
            from scrapers.smartrecruiters import fetch_smartrecruiters
            async for job in fetch_smartrecruiters(slug, name):
                jobs.append(job)
        elif ats == "teamtailor":
            from scrapers.teamtailor import fetch_teamtailor
            async for job in fetch_teamtailor(slug, name):
                jobs.append(job)
        else:
            return 0

        count = await upsert_jobs(session, jobs, company_id=company_obj.id)
        if count:
            logger.info("  %s (%s): %d PM jobs", name, ats.upper(), count)
        return count


async def mark_inactive_jobs(session):
    """Jobs not seen in last 7 days are marked inactive."""
    from datetime import timedelta
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


async def main():
    from api.database import AsyncSessionLocal

    logger.info("=== Fursa scrape starting ===")
    start = datetime.now(timezone.utc)

    yaml_path = os.path.join(os.path.dirname(__file__), "companies.yaml")
    with open(yaml_path) as f:
        config = yaml.safe_load(f)
    companies = config.get("companies", [])
    logger.info("Loaded %d companies from companies.yaml", len(companies))

    semaphore = asyncio.Semaphore(CONCURRENCY)
    total_jobs = 0

    async with AsyncSessionLocal() as session:
        # ── ATS scrapers (Greenhouse, Lever, Ashby) ──
        logger.info("--- Phase 1: ATS scrapers ---")
        tasks = [scrape_company(session, c, semaphore) for c in companies]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, int):
                total_jobs += r
            elif isinstance(r, Exception):
                logger.error("Scrape task error: %s", r)

        # ── Adzuna ──
        logger.info("--- Phase 2: Adzuna ---")
        try:
            from scrapers.adzuna import fetch_adzuna
            adzuna_jobs = []
            async for job in fetch_adzuna():
                adzuna_jobs.append(job)
            count = await upsert_jobs(session, adzuna_jobs)
            logger.info("  Adzuna: %d PM jobs", count)
            total_jobs += count
        except Exception as exc:
            logger.error("Adzuna error: %s", exc)

        # ── Proxycurl / LinkedIn ──
        logger.info("--- Phase 3: Proxycurl (LinkedIn) ---")
        try:
            from scrapers.proxycurl import fetch_proxycurl
            proxycurl_jobs = []
            async for job in fetch_proxycurl(session):
                proxycurl_jobs.append(job)
            count = await upsert_jobs(session, proxycurl_jobs)
            logger.info("  Proxycurl: %d PM jobs", count)
            total_jobs += count
        except Exception as exc:
            logger.error("Proxycurl error: %s", exc)

        # ── Remotive ──
        logger.info("--- Phase 4: Remotive ---")
        try:
            from scrapers.remotive import fetch_remotive
            remotive_jobs = []
            async for job in fetch_remotive():
                remotive_jobs.append(job)
            count = await upsert_jobs(session, remotive_jobs)
            logger.info("  Remotive: %d PM jobs", count)
            total_jobs += count
        except Exception as exc:
            logger.error("Remotive error: %s", exc)

        # ── Maintenance ──
        logger.info("--- Phase 5: Maintenance ---")
        await mark_inactive_jobs(session)
        await refresh_search_vectors(session)

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    logger.info("=== Done: %d jobs upserted in %.1fs ===", total_jobs, elapsed)


if __name__ == "__main__":
    asyncio.run(main())
