from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import require_api_key
from api.database import get_db
from api.models import Company
from api.schemas import CompanyOut

router = APIRouter(prefix="/api/companies", tags=["companies"])


@router.get("", response_model=list[CompanyOut])
async def list_companies(
    tier: Optional[str] = Query(None),
    vertical: Optional[str] = Query(None),
    ats: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(require_api_key),
):
    conditions = []
    if tier:
        t_list = [int(t.strip()) for t in tier.split(",") if t.strip().isdigit()]
        if t_list:
            from sqlalchemy import and_
            conditions.append(Company.tier.in_(t_list))
    if vertical:
        v_list = [v.strip().lower() for v in vertical.split(",")]
        conditions.append(Company.vertical.in_(v_list))
    if ats:
        a_list = [a.strip().lower() for a in ats.split(",")]
        conditions.append(Company.ats_type.in_(a_list))

    stmt = select(Company).order_by(Company.tier, Company.name)
    if conditions:
        from sqlalchemy import and_
        stmt = stmt.where(and_(*conditions))

    result = await db.execute(stmt)
    companies = result.scalars().all()
    return [
        CompanyOut(
            id=c.id,
            name=c.name,
            ats_type=c.ats_type,
            tier=c.tier,
            size=c.size,
            vertical=c.vertical,
            geo_primary=c.geo_primary,
        )
        for c in companies
    ]
