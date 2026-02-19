import logging
from typing import AsyncGenerator

import httpx

from scrapers.normalizer import NormalizedJob, infer_geo, infer_seniority, is_pm_role, normalize_date

logger = logging.getLogger(__name__)

BASE_URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"
HEADERS = {"User-Agent": "PMJobTracker/1.0 (job aggregator, contact: hello@pmjobtracker.dev)"}


async def fetch_ashby(slug: str, company_name: str) -> AsyncGenerator[NormalizedJob, None]:
    url = BASE_URL.format(slug=slug)
    try:
        async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
            resp = await client.get(url, params={"includeCompensation": "false"})
            if resp.status_code in (404, 400):
                logger.warning("Ashby %s for slug=%s", resp.status_code, slug)
                return
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.error("Ashby fetch error slug=%s: %s", slug, exc)
        return

    for job in data.get("jobs", []):
        title = job.get("title", "")
        if not is_pm_role(title):
            continue

        location_raw = job.get("location") or (job.get("locationName"))
        source_id = job.get("id", "")
        url_apply = job.get("jobUrl", "")
        posted_date = normalize_date(job.get("publishedAt") or job.get("updatedAt"))

        yield NormalizedJob(
            source_id=source_id,
            source="ashby",
            title=title,
            company_name=company_name,
            location_raw=location_raw,
            url=url_apply,
            posted_date=posted_date,
            geo_region=infer_geo(location_raw),
            seniority=infer_seniority(title),
        )
