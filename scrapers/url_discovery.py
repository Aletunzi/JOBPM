"""
Auto-discover career page URLs for companies.

Strategy (in priority order):
  1. Known ATS + slug (from companies.yaml hints): build URL directly
  2. Website URL-based: use company.website_url domain to generate career page candidates
  3. Slug-based fallback: slugify company name and try common patterns

Cost: $0.00 — only HTTP requests, no LLM calls.
Validation: each candidate URL is validated via HEAD + GET content check to ensure
it actually points to a careers page (not a homepage or login wall).
"""

import asyncio
import logging
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

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
TIMEOUT = 12
USER_AGENT = "JOBPM/1.0 (career page discovery)"

# ── Content validation constants ─────────────────────────────────────────────

# Known ATS domains — always accepted regardless of path
_ATS_DOMAINS = {
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "smartrecruiters.com",
    "teamtailor.com",
    "workday.com",
    "bamboohr.com",
    "workable.com",
    "icims.com",
    "taleo.net",
    "myworkdayjobs.com",
    "recruitee.com",
    "jobvite.com",
}

# Path segments that indicate a career page
_CAREER_PATH_SEGMENTS = {
    "/careers", "/jobs", "/join", "/work-with-us", "/work",
    "/positions", "/openings", "/hiring", "/vacancies", "/en/careers",
    "/company/careers", "/about/careers", "/about/jobs",
}

# HTML keywords that must appear in the page content
_CAREER_KEYWORDS = {
    "job", "apply", "position", "opening", "career",
    "hiring", "role", "vacanc",
}

_MIN_CONTENT_LENGTH = 500  # bytes — blank/loading pages are smaller


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


async def _validate_career_url(client: httpx.AsyncClient, url: str) -> bool:
    """Validate that a URL actually points to a career/jobs page.

    Checks (in order):
      1. HEAD → must return 2xx/3xx
      2. GET  → fetch content
      3. Final URL path or domain must look like a career page
      4. HTML must contain at least one career-related keyword
      5. Content must be longer than _MIN_CONTENT_LENGTH
    """
    try:
        # ── Step 1: cheap HEAD check ──────────────────────────────────────
        resp = await client.head(url)
        if resp.status_code >= 400:
            # Some servers don't support HEAD
            if resp.status_code != 405:
                return False
        elif resp.status_code >= 300:
            # HEAD returned redirect without following — rely on GET below
            pass

        # ── Step 2: GET for content validation ───────────────────────────
        resp = await client.get(url)
        if resp.status_code >= 400:
            return False

        # ── Step 3: path / domain check ──────────────────────────────────
        final = str(resp.url)
        parsed = urlparse(final.lower())
        host = parsed.netloc
        path = parsed.path

        # Accept any known ATS domain
        is_ats = any(ats in host for ats in _ATS_DOMAINS)

        # Check for career-related path segment
        has_career_path = any(seg in path for seg in _CAREER_PATH_SEGMENTS)

        if not is_ats and not has_career_path:
            logger.debug("  skip %s — path '%s' not career-related", url, path)
            return False

        # ── Step 4: keyword check ─────────────────────────────────────────
        html_lower = resp.text.lower()
        if not any(kw in html_lower for kw in _CAREER_KEYWORDS):
            logger.debug("  skip %s — no career keywords in content", url)
            return False

        # ── Step 5: content length check ─────────────────────────────────
        if len(resp.content) < _MIN_CONTENT_LENGTH:
            logger.debug("  skip %s — content too short (%d bytes)", url, len(resp.content))
            return False

        return True

    except (httpx.HTTPError, httpx.InvalidURL):
        return False


def _website_url_candidates(website_url: str) -> list[str]:
    """Generate career page candidate URLs from a known website URL.

    Given https://stripe.com, generates:
      - https://stripe.com/careers
      - https://stripe.com/jobs
      - https://careers.stripe.com
      - https://jobs.stripe.com
      - ATS blind patterns with domain slug
      - etc.
    """
    parsed = urlparse(website_url)
    domain = parsed.netloc.lower()  # e.g. "stripe.com" or "www.stripe.com"
    base = f"{parsed.scheme}://{domain}".rstrip("/")

    # Remove www. prefix for subdomain patterns
    bare_domain = domain.removeprefix("www.")

    # Extract slug from domain (first part before first dot)
    domain_slug = bare_domain.split(".")[0]  # "stripe" from "stripe.com"

    candidates = [
        f"{base}/careers",
        f"{base}/jobs",
        f"{base}/company/careers",
        f"{base}/en/careers",
        f"{base}/about/careers",
        f"{base}/work-with-us",
        f"https://careers.{bare_domain}",
        f"https://jobs.{bare_domain}",
    ]

    # Also try ATS blind patterns with domain-derived slug
    for pattern in ATS_BLIND_PATTERNS:
        candidates.append(pattern.format(slug=domain_slug))

    return candidates


async def discover_url(
    client: httpx.AsyncClient,
    name: str,
    hints: dict[str, dict],
    website_url: Optional[str] = None,
) -> Optional[str]:
    """Discover the career page URL for a single company.

    Priority:
      1. Known ATS + slug (YAML hint) → direct URL
      2. Website URL-based patterns → candidates from actual domain
      3. Slug-based fallback → candidates from slugified company name

    Returns the first working URL found, or None.
    """
    hint = hints.get(name.lower(), {})
    ats = hint.get("ats")
    slug = hint.get("slug")

    # ── Priority 1: known ATS + slug → direct URL ────────────────────────
    if ats and slug and ats in ATS_TEMPLATES:
        url = ATS_TEMPLATES[ats].format(slug=slug)
        if await _validate_career_url(client, url):
            return url

    # ── Priority 1b: known slug, try ATS blind patterns ──────────────────
    if slug:
        for pattern in ATS_BLIND_PATTERNS:
            url = pattern.format(slug=slug)
            if await _validate_career_url(client, url):
                return url

    # ── Priority 2: website URL-based candidates (NEW) ───────────────────
    if website_url:
        candidates = _website_url_candidates(website_url)
        for url in candidates:
            if await _validate_career_url(client, url):
                return url

    # ── Priority 3: slugify name, try all patterns (fallback) ────────────
    slugs = slugify(name)

    # If we have a slug from YAML and it's not in our generated list, prepend it
    if slug and slug not in slugs:
        slugs.insert(0, slug)

    for s in slugs:
        # Try generic patterns
        for pattern in GENERIC_PATTERNS:
            url = pattern.format(slug=s)
            if await _validate_career_url(client, url):
                return url

        # Try ATS blind patterns (if not already tried with YAML slug)
        if s != slug:
            for pattern in ATS_BLIND_PATTERNS:
                url = pattern.format(slug=s)
                if await _validate_career_url(client, url):
                    return url

    return None


async def discover_all(
    companies: list,
    max_companies: int = 100,
) -> dict[str, str]:
    """Discover career URLs for a batch of companies.

    Args:
        companies: list of Company ORM objects (with .name, .career_url, .website_url)
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
                url = await discover_url(
                    client,
                    company.name,
                    hints,
                    website_url=getattr(company, "website_url", None),
                )
                if url:
                    discovered[company.name] = url
                    logger.info("  ✓ %s → %s", company.name, url)
                else:
                    logger.debug("  ✗ %s: no career URL found", company.name)

        tasks = [_discover_one(c) for c in to_discover]
        await asyncio.gather(*tasks, return_exceptions=True)

    logger.info("Discovery complete: %d/%d URLs found", len(discovered), len(to_discover))
    return discovered
