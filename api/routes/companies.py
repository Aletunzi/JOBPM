import io
import math
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import require_api_key
from api.cache import cache_get, cache_set
from api.database import get_db
from api.models import Company, Job
from api.schemas import CompanyOut, CompaniesResponse

router = APIRouter(prefix="/api/companies", tags=["companies"])

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


async def _company_to_out(c: Company, active_jobs: int) -> CompanyOut:
    return CompanyOut(
        id=c.id,
        name=c.name,
        website_url=getattr(c, "website_url", None),
        career_url=c.career_url,
        career_url_source=getattr(c, "career_url_source", "auto"),
        tier=c.tier,
        size=c.size,
        vertical=c.vertical,
        geo_primary=c.geo_primary,
        is_enabled=c.is_enabled,
        last_scraped=c.last_scraped,
        scrape_status=getattr(c, "scrape_status", None),
        active_jobs=active_jobs,
    )


@router.get("", response_model=CompaniesResponse)
async def list_companies(
    page: int = Query(1, ge=1),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    search: Optional[str] = Query(None, description="Filter by company name (substring)"),
    vertical: Optional[str] = Query(None, description="Comma-separated verticals"),
    geo: Optional[str] = Query(None, description="Comma-separated geo_primary values"),
    tier: Optional[str] = Query(None, description="Comma-separated tiers: 1,2,3"),
    enabled: Optional[bool] = Query(None, description="Filter by is_enabled"),
    has_url: Optional[bool] = Query(None, description="Filter to companies with/without career_url"),
    status: Optional[str] = Query(None, description="Filter by scrape_status (OK, EMPTY, HTTP_ERROR, SPA_DETECTED)"),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(require_api_key),
):
    cache_key = f"companies:{page}:{limit}:{search}:{vertical}:{geo}:{tier}:{enabled}:{has_url}:{status}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    conditions = []

    if search and search.strip():
        conditions.append(Company.name.ilike(f"%{search.strip()}%"))

    if vertical:
        v_list = [v.strip().lower() for v in vertical.split(",") if v.strip()]
        if v_list:
            conditions.append(Company.vertical.in_(v_list))

    if geo:
        g_list = [g.strip().upper() for g in geo.split(",") if g.strip()]
        if g_list:
            conditions.append(Company.geo_primary.in_(g_list))

    if tier:
        t_list = [int(t.strip()) for t in tier.split(",") if t.strip().isdigit()]
        if t_list:
            conditions.append(Company.tier.in_(t_list))

    if enabled is not None:
        conditions.append(Company.is_enabled == enabled)

    if has_url is True:
        conditions.append(Company.career_url.is_not(None))
    elif has_url is False:
        conditions.append(Company.career_url.is_(None))

    if status:
        conditions.append(Company.scrape_status == status.upper())

    where_clause = and_(*conditions) if conditions else True

    # Total count
    total = await db.scalar(
        select(func.count()).select_from(Company).where(where_clause)
    )
    total = total or 0
    pages = math.ceil(total / limit) if total > 0 else 1
    offset = (page - 1) * limit

    # Active jobs count per company via correlated subquery
    active_jobs_subq = (
        select(func.count(Job.id))
        .where(and_(Job.company_id == Company.id, Job.is_active == True))
        .correlate(Company)
        .scalar_subquery()
    )

    stmt = (
        select(Company, active_jobs_subq.label("active_jobs"))
        .where(where_clause)
        .order_by(Company.tier.asc(), Company.name.asc())
        .offset(offset)
        .limit(limit)
    )

    result = await db.execute(stmt)
    rows = result.all()

    items = [
        await _company_to_out(company, active_jobs or 0)
        for company, active_jobs in rows
    ]

    response = CompaniesResponse(items=items, total=total, page=page, pages=pages)
    cache_set(cache_key, response)
    return response


@router.get("/export")
async def export_companies_excel(
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(require_api_key),
):
    """Export all companies as an Excel (.xlsx) file."""
    active_jobs_subq = (
        select(func.count(Job.id))
        .where(and_(Job.company_id == Company.id, Job.is_active == True))
        .correlate(Company)
        .scalar_subquery()
    )

    stmt = (
        select(Company, active_jobs_subq.label("active_jobs"))
        .order_by(Company.tier.asc(), Company.name.asc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Companies"
    ws.append(["Name", "Vertical", "Geo", "Tier", "Size", "Website URL", "Career URL", "Source",
               "Status", "Last Scraped", "Active Jobs", "Enabled"])

    for company, active_jobs in rows:
        ws.append([
            company.name,
            company.vertical or "",
            company.geo_primary or "",
            company.tier,
            company.size or "",
            getattr(company, "website_url", "") or "",
            company.career_url or "",
            getattr(company, "career_url_source", "auto"),
            getattr(company, "scrape_status", "") or "",
            company.last_scraped.strftime("%Y-%m-%d %H:%M") if company.last_scraped else "",
            active_jobs or 0,
            "Yes" if company.is_enabled else "No",
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=fursa_companies.xlsx"},
    )
