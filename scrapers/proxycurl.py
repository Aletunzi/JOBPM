import logging
import os
from datetime import date, datetime, timezone
from typing import AsyncGenerator

import httpx

from scrapers.normalizer import NormalizedJob, infer_geo, infer_seniority, is_pm_role, normalize_date

logger = logging.getLogger(__name__)

DAILY_CAP = int(os.environ.get("PROXYCURL_DAILY_CAP", "100"))
HEADERS = {"Authorization": f"Bearer {os.environ.get('PROXYCURL_API_KEY', '')}"}

SEARCH_QUERIES = [
    {"keyword": "Product Manager", "geo_id": "101165590"},   # European Union
    {"keyword": "Product Manager", "geo_id": "103644278"},   # United States
    {"keyword": "Senior Product Manager", "geo_id": "101165590"},
    {"keyword": "Senior Product Manager", "geo_id": "103644278"},
    {"keyword": "Staff Product Manager", "geo_id": "103644278"},
    {"keyword": "Group Product Manager", "geo_id": "103644278"},
]


async def _count_today_calls(db_session) -> int:
    from sqlalchemy import select, func, and_
    from api.models import ApiUsage
    today = datetime.now(timezone.utc).date()
    result = await db_session.scalar(
        select(func.coalesce(func.sum(ApiUsage.call_count), 0))
        .where(and_(
            ApiUsage.source == "proxycurl",
            ApiUsage.date >= datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc),
        ))
    )
    return int(result or 0)


async def _increment_call_count(db_session, count: int = 1):
    from sqlalchemy.dialects.postgresql import insert
    from api.models import ApiUsage
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    stmt = insert(ApiUsage).values(
        source="proxycurl",
        date=today_start,
        call_count=count,
    ).on_conflict_do_update(
        constraint="uq_api_usage_source_date",
        set_={"call_count": ApiUsage.call_count + count},
    )
    await db_session.execute(stmt)
    await db_session.commit()


async def fetch_proxycurl(db_session) -> AsyncGenerator[NormalizedJob, None]:
    api_key = os.environ.get("PROXYCURL_API_KEY", "")
    if not api_key:
        logger.warning("Proxycurl API key not set — skipping LinkedIn scraping")
        return

    calls_today = await _count_today_calls(db_session)
    if calls_today >= DAILY_CAP:
        logger.warning("Proxycurl daily cap reached (%d calls). Skipping.", calls_today)
        return

    remaining = DAILY_CAP - calls_today
    calls_made = 0

    async with httpx.AsyncClient(timeout=30, headers=HEADERS) as client:
        for query in SEARCH_QUERIES:
            if calls_made >= remaining:
                logger.info("Proxycurl cap reached mid-run. Stopping.")
                break

            params = {
                "keyword": query["keyword"],
                "geo_id": query["geo_id"],
                "type": "full-time",
                "experience": "mid-senior level,director",
            }

            try:
                resp = await client.get(
                    "https://nubela.co/proxycurl/api/v2/linkedin/company/job",
                    params=params,
                )
                calls_made += 1
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPStatusError as exc:
                logger.error("Proxycurl HTTP error %s for query=%s", exc.response.status_code, query)
                break
            except Exception as exc:
                logger.error("Proxycurl error query=%s: %s", query, exc)
                break

            for job in data.get("job", []):
                title = job.get("job_title", "")
                if not is_pm_role(title):
                    continue

                company_name = job.get("company", "Unknown")
                location_raw = job.get("location")
                source_id = job.get("linkedin_job_url_cleaned", job.get("job_url", ""))
                # Proxycurl uses the job URL as stable ID
                if not source_id:
                    continue
                url_apply = job.get("linkedin_job_url_cleaned") or job.get("job_url", "")
                posted_date = normalize_date(job.get("listed_at"))

                yield NormalizedJob(
                    source_id=source_id,
                    source="proxycurl",
                    title=title,
                    company_name=company_name,
                    location_raw=location_raw,
                    url=url_apply,
                    posted_date=posted_date,
                    geo_region=infer_geo(location_raw),
                    seniority=infer_seniority(title),
                )

    if calls_made > 0:
        await _increment_call_count(db_session, calls_made)
        logger.info("Proxycurl: %d calls made today (total: %d)", calls_made, calls_today + calls_made)
