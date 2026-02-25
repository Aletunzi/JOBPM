"""
ATS Router — detects the ATS platform from a career_url and routes to the
appropriate API scraper when llm_career returns SPA_DETECTED.

All supported ATS APIs are public and require no authentication.

Supported: Greenhouse, Lever, Ashby, SmartRecruiters, TeamTailor.
"""
import logging
import re
from typing import Optional

from scrapers.normalizer import NormalizedJob

logger = logging.getLogger("scraper.ats_router")

# Each entry: (ats_name, compiled_regex, slug_extractor)
# The regex is matched against the full career_url.
# The slug_extractor receives the Match object and returns the slug string.
_PATTERNS: list[tuple[str, re.Pattern, object]] = [
    # Greenhouse: boards.greenhouse.io/{slug}  or  boards.eu.greenhouse.io/{slug}
    (
        "greenhouse",
        re.compile(r"https?://boards(?:\.eu)?\.greenhouse\.io/([^/?#]+)", re.I),
        lambda m: m.group(1),
    ),
    # Lever: jobs.lever.co/{slug}
    (
        "lever",
        re.compile(r"https?://jobs\.lever\.co/([^/?#]+)", re.I),
        lambda m: m.group(1),
    ),
    # Ashby: jobs.ashbyhq.com/{slug}  or  jobs.ashby.com/{slug}
    (
        "ashby",
        re.compile(r"https?://jobs\.ashby(?:hq)?\.com/([^/?#]+)", re.I),
        lambda m: m.group(1),
    ),
    # SmartRecruiters: jobs.smartrecruiters.com/{slug}
    (
        "smartrecruiters",
        re.compile(r"https?://(?:jobs|careers)\.smartrecruiters\.com/([^/?#]+)", re.I),
        lambda m: m.group(1),
    ),
    # TeamTailor: {slug}.teamtailor.com
    (
        "teamtailor",
        re.compile(r"https?://([^.]+)\.teamtailor\.com", re.I),
        lambda m: m.group(1),
    ),
]


def detect_ats(career_url: str) -> Optional[tuple[str, str]]:
    """Return ``(ats_name, slug)`` if the URL matches a known ATS, else ``None``."""
    for ats_name, pattern, extract in _PATTERNS:
        m = pattern.match(career_url)
        if m:
            slug = extract(m)
            if slug:
                return ats_name, slug
    return None


async def try_ats_fallback(
    career_url: str,
    company_name: str,
) -> Optional[list[NormalizedJob]]:
    """Try to scrape via a known ATS JSON API.

    Returns:
        A list of ``NormalizedJob`` (possibly empty) when the ATS is recognised
        and the API call completes (even if no PM jobs were found).
        ``None`` when the career URL does not match any known ATS pattern.
    """
    result = detect_ats(career_url)
    if result is None:
        return None

    ats_name, slug = result
    logger.info("  %s: SPA resolved via %s API (slug=%s)", company_name, ats_name, slug)

    jobs: list[NormalizedJob] = []

    if ats_name == "greenhouse":
        from scrapers.greenhouse import fetch_greenhouse
        async for job in fetch_greenhouse(slug, company_name):
            jobs.append(job)

    elif ats_name == "lever":
        from scrapers.lever import fetch_lever
        async for job in fetch_lever(slug, company_name):
            jobs.append(job)

    elif ats_name == "ashby":
        from scrapers.ashby import fetch_ashby
        async for job in fetch_ashby(slug, company_name):
            jobs.append(job)

    elif ats_name == "smartrecruiters":
        from scrapers.smartrecruiters import fetch_smartrecruiters
        async for job in fetch_smartrecruiters(slug, company_name):
            jobs.append(job)

    elif ats_name == "teamtailor":
        from scrapers.teamtailor import fetch_teamtailor
        async for job in fetch_teamtailor(slug, company_name):
            jobs.append(job)

    logger.info(
        "  %s: ATS router (%s) found %d PM jobs",
        company_name, ats_name, len(jobs),
    )
    return jobs
