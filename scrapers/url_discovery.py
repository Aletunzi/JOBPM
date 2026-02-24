"""
Auto-discover career page URLs for companies.

Strategy:
  1. For companies with known ATS (from companies.yaml hints): build URL directly
  2. For others: try common career page URL patterns via HEAD requests
  3. Store discovered URL in company.career_url

Cost: $0.00 — only HTTP HEAD requests, no LLM calls.
"""

import asyncio
import logging
import re
from pathlib import Path
from typing import Optional

import httpx
import yaml

logger = logging.getLogger("scraper.discovery")

# ── ATS URL templates ────────────────────────────────────────────────────────

ATS_TEMPLATES = {
    "greenhouse": "https://boards.greenhouse.io/{slug}",
    "lever": "https://jobs.lever.co/{slug}",
    "ashby": "https://jobs.ashbyhq.com/{slug}",
    "smartrecruiters": "https://jobs.smartrecruiters.com/{slug}",
    "teamtailor": "https://{slug}.teamtailor.com/jobs",
}

# Generic career page patterns (tried when no ATS hint available)
GENERIC_PATTERNS = [
    "https://{slug}.com/careers",
    "https://www.{slug}.com/careers",
    "https://careers.{slug}.com",
    "https://{slug}.com/jobs",
    "https://www.{slug}.com/jobs",
    "https://jobs.{slug}.com",
    "https://{slug}.com/en/careers",
    "https://{slug}.com/company/careers",
]

# ATS patterns to try when we don't know which ATS (most common first)
ATS_BLIND_PATTERNS = [
    "https://boards.greenhouse.io/{slug}",
    "https://jobs.lever.co/{slug}",
    "https://jobs.ashbyhq.com/{slug}",
]

CONCURRENCY = 20
TIMEOUT = 8
USER_AGENT = "JOBPM/1.0 (career page discovery)"


def slugify(name: str) -> list[str]:
    """Generate slug variants from a company name.

    "Palo Alto Networks" → ["paloaltonetworks", "palo-alto-networks"]
    "monday.com" → ["monday", "mondaycom"]
    "Auth0" → ["auth0"]
    """
    # Remove common suffixes
    clean = re.sub(r'\.(com|io|ai|co|dev|app|tech)$', '', name.strip(), flags=re.IGNORECASE)
    clean = clean.strip()

    # Lowercase
    lower = clean.lower()

    # Variant 1: remove all non-alphanumeric
    v1 = re.sub(r'[^a-z0-9]', '', lower)

    # Variant 2: replace spaces/special with hyphens
    v2 = re.sub(r'[^a-z0-9]+', '-', lower).strip('-')

    slugs = []
    if v1:
        slugs.append(v1)
    if v2 and v2 != v1:
        slugs.append(v2)

    return slugs


def _load_yaml_hints() -> dict[str, dict]:
    """Load ATS/slug hints from companies.yaml.

    Returns: {company_name_lower: {"ats": ..., "slug": ...}}
    """
    yaml_path = Path(__file__).parent.parent / "companies.yaml"
    if not yaml_path.exists():
        return {}

    with open(yaml_path) as f:
        config = yaml.safe_load(f)

    hints = {}
    for c in config.get("companies", []):
        name = c.get("name", "").strip()
        if name:
            hints[name.lower()] = {
                "ats": c.get("ats"),
                "slug": c.get("slug"),
            }
    return hints


async def _check_url(client: httpx.AsyncClient, url: str) -> bool:
    """Check if a URL is reachable (returns 2xx/3xx)."""
    try:
        resp = await client.head(url)
        if resp.status_code < 400:
            return True
        # Some servers don't support HEAD, try GET
        if resp.status_code == 405:
            resp = await client.get(url)
            return resp.status_code < 400
        return False
    except (httpx.HTTPError, httpx.InvalidURL):
        return False


async def discover_url(
    client: httpx.AsyncClient,
    name: str,
    hints: dict[str, dict],
) -> Optional[str]:
    """Discover the career page URL for a single company.

    Returns the first working URL found, or None.
    """
    hint = hints.get(name.lower(), {})
    ats = hint.get("ats")
    slug = hint.get("slug")

    # ── Strategy 1: known ATS + slug → direct URL ────────────────────────
    if ats and slug and ats in ATS_TEMPLATES:
        url = ATS_TEMPLATES[ats].format(slug=slug)
        if await _check_url(client, url):
            return url

    # ── Strategy 2: known slug, try ATS blind patterns ────────────────────
    if slug:
        for pattern in ATS_BLIND_PATTERNS:
            url = pattern.format(slug=slug)
            if await _check_url(client, url):
                return url

    # ── Strategy 3: slugify name, try all patterns ────────────────────────
    slugs = slugify(name)

    # If we have a slug from YAML and it's not in our generated list, prepend it
    if slug and slug not in slugs:
        slugs.insert(0, slug)

    for s in slugs:
        # Try generic patterns
        for pattern in GENERIC_PATTERNS:
            url = pattern.format(slug=s)
            if await _check_url(client, url):
                return url

        # Try ATS blind patterns (if not already tried with YAML slug)
        if s != slug:
            for pattern in ATS_BLIND_PATTERNS:
                url = pattern.format(slug=s)
                if await _check_url(client, url):
                    return url

    return None


async def discover_all(
    companies: list,
    max_companies: int = 100,
) -> dict[str, str]:
    """Discover career URLs for a batch of companies.

    Args:
        companies: list of Company ORM objects (with .name, .career_url)
        max_companies: limit to avoid too many requests per run

    Returns:
        {company_name: discovered_url}
    """
    # Only process companies without a career_url
    to_discover = [c for c in companies if not c.career_url][:max_companies]

    if not to_discover:
        logger.info("All companies already have career URLs.")
        return {}

    logger.info("Discovering career URLs for %d companies...", len(to_discover))

    hints = _load_yaml_hints()
    discovered: dict[str, str] = {}
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async with httpx.AsyncClient(
        timeout=TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:

        async def _discover_one(company):
            async with semaphore:
                url = await discover_url(client, company.name, hints)
                if url:
                    discovered[company.name] = url
                    logger.info("  ✓ %s → %s", company.name, url)
                else:
                    logger.debug("  ✗ %s: no career URL found", company.name)

        tasks = [_discover_one(c) for c in to_discover]
        await asyncio.gather(*tasks, return_exceptions=True)

    logger.info("Discovery complete: %d/%d URLs found", len(discovered), len(to_discover))
    return discovered
