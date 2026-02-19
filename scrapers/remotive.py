"""
Remotive scraper — free public API, no auth required.
Endpoint: https://remotive.com/api/remote-jobs?category=product
All jobs are remote by definition.
"""
import logging
from typing import AsyncGenerator

import httpx

from scrapers.normalizer import NormalizedJob, infer_seniority, is_pm_role, normalize_date

logger = logging.getLogger(__name__)

API_URL = "https://remotive.com/api/remote-jobs"
HEADERS = {"User-Agent": "Fursa/1.0 (job aggregator)"}


async def fetch_remotive() -> AsyncGenerator[NormalizedJob, None]:
    try:
        async with httpx.AsyncClient(timeout=20, headers=HEADERS) as client:
            resp = await client.get(API_URL, params={"category": "product"})
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.error("Remotive fetch error: %s", exc)
        return

    jobs = data.get("jobs", [])
    logger.info("Remotive: fetched %d raw jobs", len(jobs))

    for job in jobs:
        title = job.get("title", "")
        if not is_pm_role(title):
            continue

        source_id = str(job.get("id", ""))
        company_name = job.get("company_name", "")
        url = job.get("url", "")
        location_raw = job.get("candidate_required_location") or "Remote"
        posted_date = normalize_date(job.get("publication_date"))

        if not url:
            continue

        yield NormalizedJob(
            source_id=source_id,
            source="remotive",
            title=title,
            company_name=company_name,
            location_raw=location_raw,
            url=url,
            posted_date=posted_date,
            geo_region="REMOTE",
            seniority=infer_seniority(title),
        )
