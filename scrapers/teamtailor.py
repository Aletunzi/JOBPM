"""
Teamtailor scraper — public jobs.json endpoint per company subdomain, no auth.
Endpoint: https://{slug}.teamtailor.com/jobs.json
Popular ATS among EU/Nordic tech companies.
"""
import logging
from typing import AsyncGenerator

import httpx

from scrapers.normalizer import NormalizedJob, infer_geo, infer_seniority, is_pm_role, normalize_date

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Fursa/1.0 (job aggregator)"}


async def fetch_teamtailor(slug: str, company_name: str) -> AsyncGenerator[NormalizedJob, None]:
    url = f"https://{slug}.teamtailor.com/jobs.json"
    try:
        async with httpx.AsyncClient(timeout=15, headers=HEADERS, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code in (404, 403):
                logger.warning("Teamtailor %d for slug=%s", resp.status_code, slug)
                return
            resp.raise_for_status()
            jobs = resp.json()
    except Exception as exc:
        logger.error("Teamtailor fetch error slug=%s: %s", slug, exc)
        return

    if not isinstance(jobs, list):
        jobs = jobs.get("jobs", []) if isinstance(jobs, dict) else []

    for job in jobs:
        title = job.get("title", "")
        if not is_pm_role(title):
            continue

        source_id = str(job.get("id", ""))
        if not source_id:
            continue

        location_raw = job.get("human-location") or job.get("location") or None
        url_apply = (
            job.get("apply-url")
            or job.get("career-page-url")
            or f"https://{slug}.teamtailor.com/jobs/{source_id}"
        )

        yield NormalizedJob(
            source_id=source_id,
            source="teamtailor",
            title=title,
            company_name=company_name,
            location_raw=location_raw,
            url=url_apply,
            posted_date=normalize_date(job.get("created-at")),
            geo_region=infer_geo(location_raw),
            seniority=infer_seniority(title),
        )
