import logging
import os
from typing import AsyncGenerator

import httpx

from scrapers.normalizer import NormalizedJob, infer_geo, infer_seniority, is_pm_role, normalize_date

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "PMJobTracker/1.0 (job aggregator, contact: hello@pmjobtracker.dev)"}

SEARCH_CONFIGS = [
    # Europe
    {"country": "gb", "geo_hint": "UK"},
    {"country": "de", "geo_hint": "EU"},
    {"country": "nl", "geo_hint": "EU"},
    {"country": "fr", "geo_hint": "EU"},
    {"country": "it", "geo_hint": "EU"},
    {"country": "pl", "geo_hint": "EU"},
    {"country": "at", "geo_hint": "EU"},
    # North America
    {"country": "us", "geo_hint": "US"},
    {"country": "ca", "geo_hint": "US"},
    # APAC
    {"country": "au", "geo_hint": "APAC"},
    {"country": "sg", "geo_hint": "APAC"},
    {"country": "in", "geo_hint": "APAC"},
    {"country": "nz", "geo_hint": "APAC"},
    # LATAM
    {"country": "br", "geo_hint": "LATAM"},
    {"country": "mx", "geo_hint": "LATAM"},
    # Africa
    {"country": "za", "geo_hint": "OTHER"},
]

KEYWORDS = ["product manager", "product management"]


async def fetch_adzuna() -> AsyncGenerator[NormalizedJob, None]:
    app_id = os.environ.get("ADZUNA_APP_ID", "")
    app_key = os.environ.get("ADZUNA_APP_KEY", "")

    if not app_id or not app_key:
        logger.warning("Adzuna credentials not set — skipping")
        return

    seen_ids: set[str] = set()

    async with httpx.AsyncClient(timeout=20, headers=HEADERS) as client:
        for config in SEARCH_CONFIGS:
            country = config["country"]
            for keyword in KEYWORDS:
                for page in range(1, 4):   # max 3 pages per country/keyword
                    url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
                    params = {
                        "app_id": app_id,
                        "app_key": app_key,
                        "what": keyword,
                        "what_exclude": "marketing analyst engineer designer",
                        "results_per_page": 50,
                        "content-type": "application/json",
                    }
                    try:
                        resp = await client.get(url, params=params)
                        resp.raise_for_status()
                        data = resp.json()
                    except Exception as exc:
                        logger.error("Adzuna error country=%s keyword=%s page=%d: %s", country, keyword, page, exc)
                        break

                    results = data.get("results", [])
                    if not results:
                        break

                    for job in results:
                        title = job.get("title", "")
                        if not is_pm_role(title):
                            continue

                        source_id = str(job.get("id", ""))
                        if source_id in seen_ids:
                            continue
                        seen_ids.add(source_id)

                        company_name = (job.get("company") or {}).get("display_name", "Unknown")
                        location_raw = (job.get("location") or {}).get("display_name")
                        url_apply = job.get("redirect_url", "")
                        posted_date = normalize_date(job.get("created"))

                        yield NormalizedJob(
                            source_id=source_id,
                            source="adzuna",
                            title=title,
                            company_name=company_name,
                            location_raw=location_raw,
                            url=url_apply,
                            posted_date=posted_date,
                            geo_region=infer_geo(location_raw),
                            seniority=infer_seniority(title),
                        )
