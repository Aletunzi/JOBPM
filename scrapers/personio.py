"""
Personio scraper — public XML feed, no auth required.
Endpoint: https://{slug}.jobs.personio.de/xml?language=en
Apply URL: https://{slug}.jobs.personio.de/job/{id}
"""
import logging
import xml.etree.ElementTree as ET
from typing import AsyncGenerator

import httpx

from scrapers.normalizer import NormalizedJob, infer_geo, infer_seniority, is_pm_role, normalize_date

logger = logging.getLogger(__name__)

BASE_URL = "https://{slug}.jobs.personio.de/xml"
HEADERS = {"User-Agent": "PMJobTracker/1.0 (job aggregator, contact: hello@pmjobtracker.dev)"}


async def fetch_personio(slug: str, company_name: str) -> AsyncGenerator[NormalizedJob, None]:
    url = BASE_URL.format(slug=slug)
    try:
        async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
            resp = await client.get(url, params={"language": "en"})
            if resp.status_code in (404, 400):
                logger.warning("Personio %s for slug=%s", resp.status_code, slug)
                return
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
    except ET.ParseError as exc:
        logger.error("Personio XML parse error slug=%s: %s", slug, exc)
        return
    except Exception as exc:
        logger.error("Personio fetch error slug=%s: %s", slug, exc)
        return

    for position in root.findall(".//position"):
        title = (position.findtext("name") or "").strip()
        if not is_pm_role(title):
            continue

        source_id = position.findtext("id") or ""
        if not source_id:
            continue

        office = (position.findtext("office") or "").strip() or None
        created_at = position.findtext("createdAt") or position.findtext("updatedAt") or ""

        url_apply = f"https://{slug}.jobs.personio.de/job/{source_id}"

        yield NormalizedJob(
            source_id=str(source_id),
            source="personio",
            title=title,
            company_name=company_name,
            location_raw=office,
            url=url_apply,
            posted_date=normalize_date(created_at),
            geo_region=infer_geo(office),
            seniority=infer_seniority(title),
        )
