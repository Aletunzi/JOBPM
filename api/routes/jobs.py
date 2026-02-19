from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, and_, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import require_api_key
from api.cache import cache_get, cache_set
from api.database import get_db
from api.models import Job
from api.schemas import JobOut, JobsResponse

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

GEO_VALUES = {"EU", "US", "UK", "REMOTE", "APAC", "LATAM", "OTHER"}
SENIORITY_VALUES = {"JUNIOR", "MID", "SENIOR", "STAFF", "LEAD", "LEADERSHIP", "INTERN"}


def _is_new(posted_date: Optional[datetime]) -> bool:
    if not posted_date:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(days=2)
    if posted_date.tzinfo is None:
        posted_date = posted_date.replace(tzinfo=timezone.utc)
    return posted_date >= cutoff


def _job_to_out(job: Job) -> JobOut:
    return JobOut(
        id=job.id,
        company_name=job.company_name,
        title=job.title,
        location_raw=job.location_raw,
        geo_region=job.geo_region,
        seniority=job.seniority,
        url=job.url,
        posted_date=job.posted_date,
        first_seen=job.first_seen,
        is_new=_is_new(job.posted_date),
        source=job.source,
    )


@router.get("", response_model=JobsResponse)
async def list_jobs(
    geo: Optional[str] = Query(None, description="Comma-separated: EU,US,REMOTE,..."),
    seniority: Optional[str] = Query(None, description="Comma-separated: SENIOR,STAFF,..."),
    vertical: Optional[str] = Query(None, description="Comma-separated: fintech,saas,..."),
    tier: Optional[str] = Query(None, description="Comma-separated: 1,2,3"),
    date: Optional[str] = Query(None, description="TODAY | 7D | 30D | ALL (default ALL)"),
    keyword: Optional[str] = Query(None, description="Full-text search on title"),
    city: Optional[str] = Query(None, description="City substring match on location_raw"),
    country: Optional[str] = Query(None, description="Country substring match on location_raw"),
    cursor: Optional[str] = Query(None, description="Cursor for pagination (first_seen ISO timestamp)"),
    limit: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(require_api_key),
):
    cache_key = f"jobs:{geo}:{seniority}:{vertical}:{tier}:{date}:{keyword}:{city}:{country}:{cursor}:{limit}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    conditions = [Job.is_active == True]

    if geo:
        geo_list = [g.strip().upper() for g in geo.split(",") if g.strip().upper() in GEO_VALUES]
        if geo_list:
            conditions.append(Job.geo_region.in_(geo_list))

    if seniority:
        sen_list = [s.strip().upper() for s in seniority.split(",") if s.strip().upper() in SENIORITY_VALUES]
        if sen_list:
            conditions.append(Job.seniority.in_(sen_list))

    if date and date != "ALL":
        delta_map = {"TODAY": 1, "7D": 7, "30D": 30}
        days = delta_map.get(date.upper(), 0)
        if days:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            conditions.append(Job.first_seen >= cutoff)

    if keyword and keyword.strip():
        conditions.append(
            Job.search_vector.op("@@")(func.plainto_tsquery("english", keyword.strip()))
        )

    if city and city.strip():
        conditions.append(Job.location_raw.ilike(f"%{city.strip()}%"))

    if country and country.strip():
        conditions.append(Job.location_raw.ilike(f"%{country.strip()}%"))

    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(cursor)
            conditions.append(Job.first_seen < cursor_dt)
        except ValueError:
            pass

    stmt = (
        select(Job)
        .where(and_(*conditions))
        .order_by(Job.first_seen.desc())
        .limit(limit + 1)
    )

    # If vertical or tier filter: join with Company
    if vertical or tier:
        from api.models import Company
        stmt = stmt.join(Company, Job.company_id == Company.id, isouter=True)
        if vertical:
            v_list = [v.strip().lower() for v in vertical.split(",")]
            stmt = stmt.where(Company.vertical.in_(v_list))
        if tier:
            t_list = [int(t.strip()) for t in tier.split(",") if t.strip().isdigit()]
            if t_list:
                stmt = stmt.where(Company.tier.in_(t_list))

    result = await db.execute(stmt)
    jobs = result.scalars().all()

    has_more = len(jobs) > limit
    items = jobs[:limit]
    next_cursor = items[-1].first_seen.isoformat() if has_more and items else None

    response = JobsResponse(
        items=[_job_to_out(j) for j in items],
        next_cursor=next_cursor,
        total_hint=None,
    )
    cache_set(cache_key, response)
    return response


@router.get("/new", response_model=JobsResponse)
async def new_jobs(
    geo: Optional[str] = Query(None),
    seniority: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(require_api_key),
):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    conditions = [Job.is_active == True, Job.first_seen >= cutoff]

    if geo:
        geo_list = [g.strip().upper() for g in geo.split(",") if g.strip().upper() in GEO_VALUES]
        if geo_list:
            conditions.append(Job.geo_region.in_(geo_list))

    if seniority:
        sen_list = [s.strip().upper() for s in seniority.split(",") if s.strip().upper() in SENIORITY_VALUES]
        if sen_list:
            conditions.append(Job.seniority.in_(sen_list))

    result = await db.execute(
        select(Job).where(and_(*conditions)).order_by(Job.first_seen.desc()).limit(limit)
    )
    jobs = result.scalars().all()
    return JobsResponse(
        items=[_job_to_out(j) for j in jobs],
        next_cursor=None,
        total_hint=len(jobs),
    )


@router.get("/{job_id}", response_model=JobOut)
async def get_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(require_api_key),
):
    from fastapi import HTTPException, status
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return _job_to_out(job)
