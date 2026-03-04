"""
LLM-based career page scraper.
Fetches a company's career page, converts to markdown, and uses OpenAI GPT-4o-mini
to extract Product Manager job listings as structured JSON.

Fetch strategy (cascade):
  1. httpx with browser-like headers  — fast, handles most sites
  2. cloudscraper                     — bypasses Cloudflare JS challenges
  3. Playwright headless              — full browser, last resort

Steps 2 and 3 are only attempted for anti-bot HTTP errors (403, 429, 5xx Cloudflare).
Genuine broken URLs (404, 410) raise immediately so the caller can self-heal.
"""

import asyncio
import hashlib
import json
import logging
from typing import Optional
from urllib.parse import urlparse

import html2text
import httpx
from openai import AsyncOpenAI

from scrapers.normalizer import (
    NormalizedJob, is_pm_role, infer_geo, infer_seniority, normalize_date,
)

logger = logging.getLogger("scraper.llm")

_openai_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(max_retries=5)
    return _openai_client


SYSTEM_PROMPT = """You are a job listing extractor. Extract all Product Manager job listings from this career page.

Return ONLY a JSON object with these keys:
- "jobs": array of job objects, each with:
  - "title": the exact job title (string)
  - "location": office location or "Remote" (string, empty string if unknown)
  - "url": direct link to the job posting (string, must be an absolute URL starting with http)
  - "posted_date": posting date in ISO format YYYY-MM-DD if visible (string or null)
- "next_page_url": if the page has pagination (e.g. "Next", "Page 2", "Load more", ">" links), return the absolute URL of the next page. If there is no next page or no pagination, return null.

Include ONLY these PM-related roles: Product Manager, Product Owner, Head of Product, VP Product, Director of Product, CPO, Group PM, Staff PM, Principal PM, Technical PM, Growth PM, AI PM, Product Lead, Product Strategy, Digital Product Manager, Associate PM.

Exclude: Product Marketing, Product Analyst, Data Analyst, Software Engineer, Engineering Manager, Designer, Project Manager.

If no PM jobs are found, return {"jobs": [], "next_page_url": null}.
Do NOT invent or hallucinate job listings. Only extract what is actually on the page."""

# HTML → Markdown converter config
_h2t = html2text.HTML2Text()
_h2t.ignore_links = False
_h2t.ignore_images = True
_h2t.body_width = 0
_h2t.ignore_emphasis = True

MAX_MARKDOWN_CHARS = 15000  # ~3500 tokens
MAX_PAGES = 20              # max pagination depth

# ── HTTP fetch cascade ─────────────────────────────────────────────────────────

# Headers that make requests look like a real Chrome browser
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

# HTTP status codes that indicate bot/anti-scraping protection (worth escalating).
# 404/410 are genuine broken URLs and should NOT be retried.
_ANTI_BOT_CODES = {403, 429, 503, 520, 521, 522, 523, 524, 525, 526}


class _PageResult:
    __slots__ = ("text", "content")

    def __init__(self, text: str, content: bytes) -> None:
        self.text = text
        self.content = content


async def _fetch_with_httpx(url: str) -> _PageResult:
    """Step 1: plain httpx with browser-like headers."""
    async with httpx.AsyncClient(
        timeout=30,
        headers=_BROWSER_HEADERS,
        follow_redirects=True,
    ) as http:
        resp = await http.get(url)
        resp.raise_for_status()
        return _PageResult(resp.text, resp.content)


def _cloudscraper_get(url: str) -> tuple[str, bytes]:
    """Synchronous cloudscraper fetch (run in executor)."""
    import cloudscraper  # lazy import — only needed as fallback
    scraper = cloudscraper.create_scraper()
    resp = scraper.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text, resp.content


async def _fetch_with_cloudscraper(url: str) -> _PageResult:
    """Step 2: cloudscraper — bypasses Cloudflare JS challenges."""
    loop = asyncio.get_event_loop()
    text, content = await loop.run_in_executor(None, _cloudscraper_get, url)
    return _PageResult(text, content)


async def _fetch_with_playwright(url: str) -> _PageResult:
    """Step 3: Playwright headless Chromium — full browser rendering."""
    from playwright.async_api import async_playwright  # lazy import
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            page = await browser.new_page(user_agent=_BROWSER_HEADERS["User-Agent"])
            await page.goto(url, timeout=30000, wait_until="networkidle")
            html = await page.content()
            return _PageResult(html, html.encode())
        finally:
            await browser.close()


async def _fetch_cascade(url: str, company_name: str) -> _PageResult:
    """
    Try httpx → cloudscraper → Playwright.

    Escalation only happens for anti-bot status codes (403, 429, 5xx Cloudflare).
    For 404/410 the original httpx error is re-raised immediately so the caller
    can apply self-healing logic (URL reset / rediscovery).
    """
    # Step 1 — httpx
    try:
        return await _fetch_with_httpx(url)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code not in _ANTI_BOT_CODES:
            raise  # genuine broken URL, let the caller handle it
        logger.warning(
            "  %s: httpx HTTP %d (bot protection?), trying cloudscraper…",
            company_name, exc.response.status_code,
        )

    # Step 2 — cloudscraper
    try:
        result = await _fetch_with_cloudscraper(url)
        logger.info("  %s: cloudscraper succeeded", company_name)
        return result
    except Exception as exc:
        logger.warning(
            "  %s: cloudscraper failed (%s), trying Playwright…",
            company_name, exc,
        )

    # Step 3 — Playwright
    logger.info("  %s: launching Playwright headless browser…", company_name)
    result = await _fetch_with_playwright(url)
    logger.info("  %s: Playwright succeeded", company_name)
    return result


# ── LLM extraction helpers ────────────────────────────────────────────────────

async def _extract_page(
    client,
    markdown: str,
    company_name: str,
    page_url: str,
    base_url: str,
) -> tuple[list[dict], Optional[str]]:
    """Run LLM extraction on a single page. Returns (raw_items, next_page_url)."""
    completion = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Company: {company_name}\n"
                    f"Career page URL: {page_url}\n"
                    f"Base URL for relative links: {base_url}\n\n"
                    f"--- PAGE CONTENT ---\n{markdown}"
                ),
            },
        ],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=4096,
    )

    raw = completion.choices[0].message.content or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("  %s: LLM returned invalid JSON", company_name)
        return [], None

    items = data.get("jobs", [])
    next_url = (data.get("next_page_url") or "").strip() or None

    if next_url and next_url.startswith("/"):
        next_url = base_url + next_url

    return items, next_url


def _items_to_jobs(
    items: list[dict],
    company_name: str,
    base_url: str,
) -> list[NormalizedJob]:
    """Convert raw LLM items to NormalizedJob list."""
    jobs: list[NormalizedJob] = []
    for item in items:
        title = (item.get("title") or "").strip()
        url = (item.get("url") or "").strip()
        if not title or not url:
            continue

        if url.startswith("/"):
            url = base_url + url

        if not is_pm_role(title):
            continue

        location_raw = (item.get("location") or "").strip() or None
        source_id = hashlib.sha256(url.encode()).hexdigest()[:32]

        jobs.append(NormalizedJob(
            source_id=source_id,
            source="custom",
            title=title,
            company_name=company_name,
            location_raw=location_raw,
            url=url,
            posted_date=normalize_date(item.get("posted_date")),
            geo_region=infer_geo(location_raw),
            seniority=infer_seniority(title),
        ))
    return jobs


# SPA detection signals
_SPA_SIGNALS = {"loading", "please wait", "enable javascript", "requires javascript",
                "javascript is required", "loading...", "please enable"}


def _detect_spa(html: str, markdown: str) -> bool:
    """Detect if a page is a client-side SPA that didn't render server-side."""
    if len(markdown.strip()) < 100:
        return True
    html_lower = html.lower()
    return any(sig in html_lower for sig in _SPA_SIGNALS) and len(markdown.strip()) < 300


# ── Public entry point ────────────────────────────────────────────────────────

async def fetch_custom(
    career_url: str,
    company_name: str,
    page_hash: Optional[str] = None,
) -> tuple[list[NormalizedJob], str, str]:
    """Fetch career page (with pagination), extract PM jobs via LLM.

    Returns (jobs, new_page_hash, status).
    Status values: "OK" | "UNCHANGED" | "SPA_DETECTED"
    If page hasn't changed (same hash), returns ([], same_hash, "UNCHANGED") without calling LLM.
    Follows up to MAX_PAGES pages when the LLM detects pagination links.
    Raises httpx.HTTPStatusError for genuine broken URLs (404, 410) so the
    caller's self-healing logic can kick in.
    """
    parsed = urlparse(career_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    # ── Fetch first page ──────────────────────────────────────────────────────
    result = await _fetch_cascade(career_url, company_name)

    # ── Change detection (first page only) ───────────────────────────────────
    new_hash = hashlib.sha256(result.content).hexdigest()
    if page_hash and new_hash == page_hash:
        logger.debug("  %s: page unchanged, skipping LLM", company_name)
        return [], new_hash, "UNCHANGED"

    # ── HTML → Markdown ───────────────────────────────────────────────────────
    markdown = _h2t.handle(result.text)
    if len(markdown) > MAX_MARKDOWN_CHARS:
        markdown = markdown[:MAX_MARKDOWN_CHARS]

    # ── SPA Detection ─────────────────────────────────────────────────────────
    if _detect_spa(result.text, markdown):
        logger.warning("  %s: career page likely SPA (%d chars), skipping LLM",
                       company_name, len(markdown.strip()))
        return [], new_hash, "SPA_DETECTED"

    # ── LLM extraction with pagination loop ───────────────────────────────────
    client = _get_client()
    all_jobs: list[NormalizedJob] = []
    visited: set[str] = {career_url}

    items, next_url = await _extract_page(client, markdown, company_name, career_url, base_url)
    all_jobs.extend(_items_to_jobs(items, company_name, base_url))

    page_num = 1
    while next_url and page_num < MAX_PAGES and next_url not in visited:
        page_num += 1
        visited.add(next_url)
        logger.info("  %s: following pagination → page %d (%s)", company_name, page_num, next_url)

        try:
            result = await _fetch_cascade(next_url, company_name)
        except Exception:
            logger.warning("  %s: pagination page %d failed, stopping", company_name, page_num)
            break

        markdown = _h2t.handle(result.text)
        if len(markdown) > MAX_MARKDOWN_CHARS:
            markdown = markdown[:MAX_MARKDOWN_CHARS]

        if len(markdown.strip()) < 100:
            break

        items, next_url = await _extract_page(client, markdown, company_name, next_url, base_url)
        all_jobs.extend(_items_to_jobs(items, company_name, base_url))

    logger.info("  %s: LLM extracted %d PM jobs across %d page(s)", company_name, len(all_jobs), page_num)
    return all_jobs, new_hash, "OK"
