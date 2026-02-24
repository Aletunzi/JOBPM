from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel


class JobOut(BaseModel):
    id: UUID
    company_name: str
    title: str
    location_raw: Optional[str]
    geo_region: str
    seniority: str
    url: str
    posted_date: Optional[datetime]
    first_seen: datetime
    is_new: bool           # True if first_seen within last 24h
    source: str

    model_config = {"from_attributes": True}


class CompanyOut(BaseModel):
    id: UUID
    name: str
    career_url: Optional[str]
    tier: int
    size: Optional[str]
    vertical: Optional[str]
    geo_primary: Optional[str]
    is_enabled: bool
    last_scraped: Optional[datetime]
    active_jobs: int = 0

    model_config = {"from_attributes": True}


class CompaniesResponse(BaseModel):
    items: list[CompanyOut]
    total: int
    page: int
    pages: int


class StatsOut(BaseModel):
    total_active: int
    new_today: int
    by_geo: dict[str, int]
    by_seniority: dict[str, int]
    last_scraped: Optional[datetime]


class AdminStatsOut(BaseModel):
    total_jobs: int
    total_active: int
    new_24h: int
    last_run: Optional[datetime]
    runs_per_day: int
    schedule_cron: str
    by_source: dict[str, int]
    by_continent: dict[str, int]
    top_locations: list[dict]
    total_companies: int          # total companies in DB
    companies_with_url: int       # companies with career_url configured
    companies_due: int            # companies due for scraping today


class JobsResponse(BaseModel):
    items: list[JobOut]
    next_cursor: Optional[str]
    total_hint: Optional[int]
