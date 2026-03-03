"""
Workday public API scraper.

Workday career pages (*.myworkdayjobs.com) are SPAs, but Workday exposes a
public REST endpoint that returns job listings as JSON without requiring
JavaScript rendering or authentication.

API: POST https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{path}/jobs
Body: {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}
"""
import logging
from typing import AsyncGenerator

import httpx

from scrapers.normalizer import NormalizedJob, infer_geo, infer_seniority, is_pm_role, normalize_date

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "PMJobTracker/1.0 (job aggregator, contact: hello@pmjobtracker.dev)",
    "Accept": "application/json",
}
PAGE_SIZE = 20


def _build_api_url(slug: str) -> tuple[str, str]:
    """From 'tenant.wd5.myworkdayjobs.com/Path' return (base_url, api_url).

    Args:
        slug: '{host}/{path}' e.g. 'osv-accolade.wd5.myworkdayjobs.com/External_Careers'

    Returns:
        (base_url, api_url) where base_url is 'https://{host}' and
        api_url is the full POST endpoint.
    """
    host, path = slug.split("/", 1)
    tenant = host.split(".")[0]
    api_url = f"https://{host}/wday/cxs/{tenant}/{path}/jobs"
    base_url = f"https://{host}"
    return base_url, api_url


async def fetch_workday(slug: str, company_name: str) -> AsyncGenerator[NormalizedJob, None]:
    """Yield PM jobs from a Workday career page via the public JSON API.

    Args:
        slug: '{host}/{path}' e.g. 'osv-accolade.wd5.myworkdayjobs.com/External_Careers'
        company_name: Human-readable company name.
    """
    try:
        base_url, api_url = _build_api_url(slug)
    except (ValueError, IndexError) as exc:
        logger.error("Invalid Workday slug '%s': %s", slug, exc)
        return

    offset = 0
    total: int | None = None

    async with httpx.AsyncClient(timeout=20, headers=HEADERS) as client:
        while total is None or offset < total:
            payload = {
                "appliedFacets": {},
                "limit": PAGE_SIZE,
                "offset": offset,
                "searchText": "",
            }
            try:
                resp = await client.post(api_url, json=payload)
                if resp.status_code == 404:
                    logger.warning("Workday 404 for slug=%s", slug)
                    return
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.error("Workday fetch error slug=%s: %s", slug, exc)
                return

            if total is None:
                total = data.get("total", 0)
                if total == 0:
                    return
                logger.debug("  %s (workday): total listings=%d", company_name, total)

            postings = data.get("jobPostings", [])
            if not postings:
                break

            for posting in postings:
                title = posting.get("title", "")
                if not is_pm_role(title):
                    continue

                external_path = posting.get("externalPath", "")
                job_url = f"{base_url}{external_path}" if external_path else f"https://{slug}"

                location_raw = posting.get("locationsText") or None
                posted_date = normalize_date(posting.get("postedOn"))
                source_id = posting.get("jobReqId") or external_path or title

                yield NormalizedJob(
                    source_id=source_id,
                    source="workday",
                    title=title,
                    company_name=company_name,
                    location_raw=location_raw,
                    url=job_url,
                    posted_date=posted_date,
                    geo_region=infer_geo(location_raw),
                    seniority=infer_seniority(title),
                )

            offset += len(postings)
            if len(postings) < PAGE_SIZE:
                break
