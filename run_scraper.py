"""
PM Job Tracker — Daily scraper orchestrator (LLM rolling).
Run with: python run_scraper.py
Or triggered by GitHub Actions cron.

Architecture:
  Phase 0a: Website URL Discovery — auto-discover company homepages via LLM
  Phase 0b: Career URL Discovery — auto-discover career page URLs using website_url
  Phase 1:  LLM Rolling — scrape companies due for refresh via GPT-4o-mini
  Phase 2:  Maintenance — mark stale jobs inactive, refresh search vectors, health report
"""

import asyncio
import logging
import os
from collections import Counter
from datetime import datetime, timedelta, timezone

import httpx
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
MAX_PER_RUN = 200     # max companies per scrape run (rolling window)
DISCOVERY_BATCH = 250  # max companies per discovery run
WEBSITE_BATCH = 500    # max companies per website discovery run
DELAY_BETWEEN = 2     # seconds between LLM requests (rate limiting)
DISCOVERY_COOLDOWN_DAYS = 30  # min days between re-discovery attempts


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

async def scrape_company(session, company, semaphore: asyncio.Semaphore) -> tuple[int, str]:
    """Scrape one company. Returns (job_count, status_string)."""
    from scrapers.llm_career import fetch_custom

    now = datetime.now(timezone.utc)

    async with semaphore:
        try:
            jobs, new_hash, status = await fetch_custom(
                career_url=company.career_url,
                company_name=company.name,
                page_hash=company.page_hash,
            )

            count = await upsert_jobs(session, jobs, company_id=company.id)

            # ── Status tracking ──────────────────────────────────────────
            if status == "SPA_DETECTED":
                company.scrape_status = "SPA_DETECTED"
            elif status == "UNCHANGED":
                # Page hash unchanged — keep previous scrape_status
                pass
            elif count > 0:
                company.scrape_status = "OK"
            else:
                company.scrape_status = "EMPTY"  # tracking only, does NOT trigger re-discovery

            # Update company scrape metadata
            company.last_scraped = now
            company.page_hash = new_hash
            await session.commit()

            if count:
                logger.info("  %s: %d PM jobs upserted", company.name, count)
            return count, status

        except httpx.HTTPStatusError as exc:
            # ── Self-healing: only on BROKEN pages (HTTP errors) ─────────
            if exc.response.status_code in (404, 410):
                company.scrape_status = "HTTP_ERROR"

                if getattr(company, "career_url_source", "auto") == "auto":
                    # Check cooldown before resetting
                    can_rediscover = (
                        not company.last_discovery_attempt
                        or company.last_discovery_attempt < now - timedelta(days=DISCOVERY_COOLDOWN_DAYS)
                    )
                    if can_rediscover:
                        logger.warning("  %s: career URL returned %d — resetting for rediscovery",
                                       company.name, exc.response.status_code)
                        company.career_url = None
                        company.page_hash = None
                        company.last_discovery_attempt = now
                    else:
                        logger.info("  %s: career URL returned %d — rediscovery cooldown active",
                                    company.name, exc.response.status_code)
                else:
                    # YAML/manual: log warning, NEVER auto-reset
                    logger.warning("  %s: career URL returned %d but source=%s, keeping URL",
                                   company.name, exc.response.status_code,
                                   getattr(company, "career_url_source", "auto"))

                company.last_scraped = now
                await session.commit()
            else:
                company.scrape_status = "HTTP_ERROR"
                company.last_scraped = now
                await session.commit()
                logger.error("  %s: HTTP %d — %s", company.name, exc.response.status_code, exc)
            return 0, "HTTP_ERROR"

        except Exception as exc:
            logger.error("  %s: error — %s", company.name, exc)
            return 0, "ERROR"

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
    from scrapers.url_discovery import discover_all
    from scrapers.website_discovery import discover_websites

    logger.info("=== Scrape starting ===")
    start = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:

        # ── Phase 0a: Website URL Discovery (NEW) ────────────────────────
        logger.info("--- Phase 0a: Website URL Discovery ---")
        all_enabled = await session.execute(
            select(Company).where(Company.is_enabled == True)
        )
        all_companies = all_enabled.scalars().all()

        missing_website = [c for c in all_companies if not c.website_url]
        logger.info("Companies without website URL: %d / %d", len(missing_website), len(all_companies))

        if missing_website:
            websites = await discover_websites(missing_website, max_companies=WEBSITE_BATCH)

            for company in missing_website:
                url = websites.get(company.name)
                if url:
                    company.website_url = url

            if websites:
                await session.commit()
                logger.info("Phase 0a done: %d website URLs discovered", len(websites))
            else:
                logger.info("Phase 0a done: no new website URLs found")
        else:
            logger.info("All enabled companies have website URLs.")

        # ── Phase 0b: Career URL Discovery ───────────────────────────────
        logger.info("--- Phase 0b: Career URL Discovery ---")
        missing_url = [c for c in all_companies if not c.career_url]
        logger.info("Companies without career URL: %d / %d", len(missing_url), len(all_companies))

        if missing_url:
            discovered = await discover_all(missing_url, max_companies=DISCOVERY_BATCH)

            for company in missing_url:
                url = discovered.get(company.name)
                if url:
                    company.career_url = url

            if discovered:
                await session.commit()
                logger.info("Phase 0b done: %d career URLs discovered", len(discovered))
            else:
                logger.info("Phase 0b done: no new career URLs found")
        else:
            logger.info("All enabled companies have career URLs.")

        # ── Phase 1: LLM Rolling ─────────────────────────────────────────
        logger.info("--- Phase 1: LLM career page scraping ---")

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

        status_counts = Counter()
        total_jobs = 0

        if companies:
            semaphore = asyncio.Semaphore(CONCURRENCY)
            tasks = [scrape_company(session, c, semaphore) for c in companies]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for r in results:
                if isinstance(r, Exception):
                    status_counts["ERROR"] += 1
                else:
                    job_count, status = r
                    total_jobs += job_count
                    status_counts[status] += 1

            logger.info("Phase 1 done: %d jobs upserted, %d errors",
                        total_jobs, status_counts.get("ERROR", 0) + status_counts.get("HTTP_ERROR", 0))
        else:
            logger.info("No companies due for scraping today.")

        # ── Phase 2: Maintenance ─────────────────────────────────────────
        logger.info("--- Phase 2: Maintenance ---")
        await mark_inactive_jobs(session)
        await refresh_search_vectors(session)

    # ── Health Report ────────────────────────────────────────────────────
    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    logger.info("=== Scrape Health Report ===")
    for status, count in sorted(status_counts.items()):
        logger.info("  %s: %d companies", status, count)
    logger.info("=== Done: %d jobs upserted in %.1fs ===", total_jobs, elapsed)


if __name__ == "__main__":
    asyncio.run(main())
