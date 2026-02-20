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
    ats_type: str
    tier: int
    size: Optional[str]
    vertical: Optional[str]
    geo_primary: Optional[str]

    model_config = {"from_attributes": True}


class StatsOut(BaseModel):
    total_active: int
    new_today: int
    by_geo: dict[str, int]
    by_seniority: dict[str, int]
    last_scraped: Optional[datetime]


class AdminStatsOut(BaseModel):
    total_jobs: int           # all records ever scraped (active + inactive)
    total_active: int         # currently active
    new_24h: int              # added in last 24h
    last_run: Optional[datetime]   # max first_seen — proxy for last scraper run
    runs_per_day: int         # from GitHub Actions cron config
    by_source: dict[str, int]     # count by scraper source (all records)
    by_geo: dict[str, int]        # count by geo_region (active only)
    top_locations: list[dict]     # [{name, count}] top 20 location_raw values (active)


class JobsResponse(BaseModel):
    items: list[JobOut]
    next_cursor: Optional[str]
    total_hint: Optional[int]
