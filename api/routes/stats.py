from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import require_api_key
from api.cache import cache_get, cache_set
from api.database import get_db
from api.models import Job, ApiUsage
from api.schemas import StatsOut

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
