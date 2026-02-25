import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Boolean, DateTime, Integer, Text,
    UniqueConstraint, Index, ForeignKey,
)
from sqlalchemy.dialects.postgresql import UUID, TSVECTOR
from sqlalchemy.orm import relationship
from api.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Company(Base):
    __tablename__ = "companies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    website_url = Column(Text, nullable=True)             # Company homepage (e.g. https://stripe.com)
    career_url = Column(Text, nullable=True)              # URL to scrape (null = not yet configured)
    career_url_source = Column(String(20), nullable=False, default="auto", server_default="auto")
    # career_url_source values: "auto" | "yaml" | "manual"
    tier = Column(Integer, nullable=False, default=3)
    size = Column(String(50), nullable=True)              # startup | scaleup | mid | large
    vertical = Column(String(50), nullable=True)          # fintech | saas | ai | ...
    geo_primary = Column(String(20), nullable=True)       # US | EU | UK | GLOBAL | APAC | LATAM

    is_enabled = Column(Boolean, nullable=False, default=True)
    last_scraped = Column(DateTime(timezone=True), nullable=True)
    page_hash = Column(String(64), nullable=True)         # SHA-256 of last fetched page (change detection)
    scrape_interval_days = Column(Integer, nullable=False, default=5)
    last_discovery_attempt = Column(DateTime(timezone=True), nullable=True)
    scrape_status = Column(String(30), nullable=True)     # OK | HTTP_ERROR | EMPTY | SPA_DETECTED | TIMEOUT

    jobs = relationship("Job", back_populates="company", lazy="select")

    __table_args__ = (
        UniqueConstraint("name", name="uq_company_name"),
    )


class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True)
    company_name = Column(String(255), nullable=False)

    source = Column(String(50), nullable=False)     # custom | adzuna | ...
    source_id = Column(String(512), nullable=False) # stable ID within the source

    title = Column(String(512), nullable=False)
    location_raw = Column(String(255), nullable=True)
    geo_region = Column(String(20), nullable=False, default="OTHER")  # EU | US | UK | REMOTE | APAC | OTHER
    seniority = Column(String(20), nullable=False, default="MID")     # JUNIOR | MID | SENIOR | STAFF | LEAD | LEADERSHIP | INTERN
    url = Column(Text, nullable=False)
    posted_date = Column(DateTime(timezone=True), nullable=True)

    first_seen = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    last_seen = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    is_active = Column(Boolean, nullable=False, default=True)

    search_vector = Column(TSVECTOR, nullable=True)

    company = relationship("Company", back_populates="jobs", lazy="select")

    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_job_source"),
        Index("idx_jobs_geo_seniority_date", "geo_region", "seniority", "first_seen"),
        Index("idx_jobs_company", "company_id"),
        Index("idx_jobs_active_date", "is_active", "first_seen"),
        Index("idx_jobs_search", "search_vector", postgresql_using="gin"),
    )


class ApiUsage(Base):
    __tablename__ = "api_usage"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source = Column(String(50), nullable=False)
    date = Column(DateTime(timezone=True), nullable=False)
    call_count = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("source", "date", name="uq_api_usage_source_date"),
    )


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    started_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    companies_scraped = Column(Integer, nullable=True)
    jobs_upserted = Column(Integer, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    trigger = Column(String(50), nullable=True)  # "schedule" | "manual"
