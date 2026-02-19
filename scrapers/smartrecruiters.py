"""
SmartRecruiters scraper — public job board API, no auth required.
Endpoint: https://api.smartrecruiters.com/v1/companies/{slug}/postings
"""
import logging
from typing import AsyncGenerator

import httpx

from scrapers.normalizer import NormalizedJob, infer_geo, infer_seniority, is_pm_role, normalize_date

logger = logging.getLogger(__name__)

BASE_URL = "https://api.smartrecruiters.com/v1/companies/{slug}/postings"
HEADERS = {"User-Agent": "Fursa/1.0 (job aggregator)"}


async def fetch_smartrecruiters(slug: str, company_name: str) -> AsyncGenerator[NormalizedJob, None]:
    url = BASE_URL.format(slug=slug)
    try:
        async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
            resp = await client.get(url, params={"limit": 100})
            if resp.status_code == 404:
                logger.warning("SmartRecruiters 404 for slug=%s", slug)
                return
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.error("SmartRecruiters fetch error slug=%s: %s", slug, exc)
        return

    for job in data.get("content", []):
        title = job.get("name", "")
        if not is_pm_role(title):
            continue

        source_id = job.get("id", "")
        if not source_id:
            continue

        # Build location string
        loc = job.get("location") or {}
        if loc.get("remote"):
            location_raw = "Remote"
        else:
            parts = [loc.get("city"), loc.get("country")]
            location_raw = ", ".join(p for p in parts if p) or None

        # Apply URL — SmartRecruiters uses a standard pattern
        ref = job.get("ref") or f"https://jobs.smartrecruiters.com/{slug}/{source_id}"

        yield NormalizedJob(
            source_id=str(source_id),
            source="smartrecruiters",
            title=title,
            company_name=company_name,
            location_raw=location_raw,
            url=ref,
            posted_date=normalize_date(job.get("releasedDate")),
            geo_region=infer_geo(location_raw),
            seniority=infer_seniority(title),
        )
