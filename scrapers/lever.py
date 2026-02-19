import logging
from typing import AsyncGenerator

import httpx

from scrapers.normalizer import NormalizedJob, infer_geo, infer_seniority, is_pm_role, normalize_date

logger = logging.getLogger(__name__)

BASE_URL = "https://api.lever.co/v0/postings/{slug}"
HEADERS = {"User-Agent": "PMJobTracker/1.0 (job aggregator, contact: hello@pmjobtracker.dev)"}


async def fetch_lever(slug: str, company_name: str) -> AsyncGenerator[NormalizedJob, None]:
    url = BASE_URL.format(slug=slug)
    try:
        async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
            resp = await client.get(url, params={"mode": "json", "limit": 500})
            if resp.status_code == 404:
                logger.warning("Lever 404 for slug=%s", slug)
                return
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.error("Lever fetch error slug=%s: %s", slug, exc)
        return

    # Lever returns a list of postings
    postings = data if isinstance(data, list) else data.get("data", [])

    for job in postings:
        title = job.get("text", "")
        if not is_pm_role(title):
            continue

        cats = job.get("categories") or {}
        location_raw = cats.get("location") or cats.get("allLocations", [None])[0]
        source_id = job.get("id", "")
        url_apply = job.get("hostedUrl", "")
        posted_date = normalize_date(job.get("createdAt"))

        yield NormalizedJob(
            source_id=source_id,
            source="lever",
            title=title,
            company_name=company_name,
            location_raw=location_raw,
            url=url_apply,
            posted_date=posted_date,
            geo_region=infer_geo(location_raw),
            seniority=infer_seniority(title),
        )
