from collections import defaultdict
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import require_api_key
from api.cache import cache_get, cache_set
from api.database import get_db
from api.models import Job, ApiUsage, Company
from api.schemas import StatsOut, AdminStatsOut
from scrapers.normalizer import infer_continent, extract_country

KNOWN_SOURCES = ["custom"]

# GitHub Actions cron (must match .github/workflows/daily_scrape.yml)
SCRAPER_CRON = "0 7 * * *"
SCRAPER_RUNS_PER_DAY = 1

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("", response_model=StatsOut)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(require_api_key),
):
    cached = cache_get("stats")
    if cached:
        return cached

    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)

    total_active = await db.scalar(
        select(func.count()).where(Job.is_active == True)
    )
    new_today = await db.scalar(
        select(func.count()).where(and_(Job.is_active == True, Job.first_seen >= cutoff_24h))
    )

    geo_result = await db.execute(
        select(Job.geo_region, func.count().label("cnt"))
        .where(Job.is_active == True)
        .group_by(Job.geo_region)
    )
    by_geo = {row.geo_region: row.cnt for row in geo_result}

    sen_result = await db.execute(
        select(Job.seniority, func.count().label("cnt"))
        .where(Job.is_active == True)
        .group_by(Job.seniority)
    )
    by_seniority = {row.seniority: row.cnt for row in sen_result}

    last_scraped = await db.scalar(select(func.max(Company.last_scraped)))

    result = StatsOut(
        total_active=total_active or 0,
        new_today=new_today or 0,
        by_geo=by_geo,
        by_seniority=by_seniority,
        last_scraped=last_scraped,
    )
    cache_set("stats", result)
    return result


@router.get("/admin", response_model=AdminStatsOut)
async def get_admin_stats(
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(require_api_key),
):
    cached = cache_get("admin_stats")
    if cached:
        return cached

    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)

    # ── Job counts ──────────────────────────────────────────────────────────────
    total_active = await db.scalar(select(func.count()).where(Job.is_active == True))
    total_jobs = total_active
    new_24h = await db.scalar(
        select(func.count()).where(Job.first_seen >= cutoff_24h)
    )
    last_run = await db.scalar(select(func.max(Job.first_seen)))

    # ── By Source ───────────────────────────────────────────────────────────────
    src_rows = await db.execute(
        select(Job.source, func.count().label("cnt")).group_by(Job.source)
    )
    by_source: dict[str, int] = {src: 0 for src in KNOWN_SOURCES}
    for row in src_rows:
        by_source[row.source] = row.cnt

    # ── By Continent (active only) ───────────────────────────────────────────
    loc_geo_rows = await db.execute(
        select(Job.location_raw, Job.geo_region, func.count().label("cnt"))
        .where(Job.is_active == True)
        .group_by(Job.location_raw, Job.geo_region)
    )
    continent_counts: dict[str, int] = defaultdict(int)
    for row in loc_geo_rows:
        continent = infer_continent(row.location_raw, row.geo_region or "OTHER")
        continent_counts[continent] += row.cnt

    # ── Top Locations (active only) ──────────────────────────────────────────
    loc_rows = await db.execute(
        select(Job.location_raw, Job.geo_region, func.count().label("cnt"))
        .where(Job.is_active == True)
        .group_by(Job.location_raw, Job.geo_region)
    )
    country_counts: dict[str, int] = defaultdict(int)
    for row in loc_rows:
        country = extract_country(row.location_raw, row.geo_region or "OTHER")
        if country and country != "Remote":
            country_counts[country] += row.cnt

    top_locations = sorted(
        [{"name": k, "count": v} for k, v in country_counts.items()],
        key=lambda x: x["count"],
        reverse=True,
    )[:20]

    # ── Company stats ────────────────────────────────────────────────────────
    total_companies = await db.scalar(select(func.count()).select_from(Company))
    companies_with_url = await db.scalar(
        select(func.count()).select_from(Company).where(Company.career_url.is_not(None))
    )
    # Due = enabled, has career_url, and (never scraped OR interval elapsed)
    cutoff_interval = now - timedelta(days=5)
    companies_due = await db.scalar(
        select(func.count()).select_from(Company).where(
            and_(
                Company.is_enabled == True,
                Company.career_url.is_not(None),
                or_(
                    Company.last_scraped.is_(None),
                    Company.last_scraped < cutoff_interval,
                ),
            )
        )
    )

    result = AdminStatsOut(
        total_jobs=total_jobs or 0,
        total_active=total_active or 0,
        new_24h=new_24h or 0,
        last_run=last_run,
        runs_per_day=SCRAPER_RUNS_PER_DAY,
        schedule_cron=SCRAPER_CRON,
        by_source=by_source,
        by_continent=dict(continent_counts),
        top_locations=top_locations,
        total_companies=total_companies or 0,
        companies_with_url=companies_with_url or 0,
        companies_due=companies_due or 0,
    )
    cache_set("admin_stats", result)
    return result
