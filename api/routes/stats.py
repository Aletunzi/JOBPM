from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import require_api_key
from api.cache import cache_get, cache_set
from api.database import get_db
from api.models import Job, ApiUsage
from api.schemas import StatsOut, AdminStatsOut

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

    last_usage = await db.scalar(
        select(ApiUsage.date).order_by(ApiUsage.date.desc()).limit(1)
    )

    result = StatsOut(
        total_active=total_active or 0,
        new_today=new_today or 0,
        by_geo=by_geo,
        by_seniority=by_seniority,
        last_scraped=last_usage,
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

    # Total jobs (all, including inactive)
    total_jobs = await db.scalar(select(func.count()).select_from(Job))
    total_active = await db.scalar(select(func.count()).where(Job.is_active == True))
    new_24h = await db.scalar(
        select(func.count()).where(Job.first_seen >= cutoff_24h)
    )

    # Last scraper run: most recently scraped job
    last_run = await db.scalar(select(func.max(Job.first_seen)))

    # By source (all records, not just active)
    src_rows = await db.execute(
        select(Job.source, func.count().label("cnt"))
        .group_by(Job.source)
        .order_by(func.count().desc())
    )
    by_source = {row.source: row.cnt for row in src_rows}

    # By geo region (active only)
    geo_rows = await db.execute(
        select(Job.geo_region, func.count().label("cnt"))
        .where(Job.is_active == True)
        .group_by(Job.geo_region)
        .order_by(func.count().desc())
    )
    by_geo = {row.geo_region: row.cnt for row in geo_rows}

    # Top locations by raw string (active, non-null, top 20)
    loc_rows = await db.execute(
        select(Job.location_raw, func.count().label("cnt"))
        .where(Job.is_active == True, Job.location_raw.isnot(None))
        .group_by(Job.location_raw)
        .order_by(func.count().desc())
        .limit(20)
    )
    top_locations = [{"name": row.location_raw, "count": row.cnt} for row in loc_rows]

    result = AdminStatsOut(
        total_jobs=total_jobs or 0,
        total_active=total_active or 0,
        new_24h=new_24h or 0,
        last_run=last_run,
        runs_per_day=1,
        by_source=by_source,
        by_geo=by_geo,
        top_locations=top_locations,
    )
    cache_set("admin_stats", result)
    return result
