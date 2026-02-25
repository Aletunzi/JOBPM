"""
LLM-based career page scraper.
Fetches a company's career page, converts to markdown, and uses OpenAI GPT-4o-mini
to extract Product Manager job listings as structured JSON.
"""

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
        _openai_client = AsyncOpenAI()
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


async def _fetch_page(http: httpx.AsyncClient, url: str) -> httpx.Response:
    """Fetch a single page, raising on HTTP errors."""
    resp = await http.get(url)
    resp.raise_for_status()
    return resp


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

    # Resolve relative next_page_url
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
    """
    parsed = urlparse(career_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    async with httpx.AsyncClient(
        timeout=30,
        headers={"User-Agent": "JOBPM/1.0"},
        follow_redirects=True,
    ) as http:

        # ── Fetch first page ──────────────────────────────────────────────
        resp = await _fetch_page(http, career_url)

        # ── Change detection (first page only) ───────────────────────────
        new_hash = hashlib.sha256(resp.content).hexdigest()
        if page_hash and new_hash == page_hash:
            logger.debug("  %s: page unchanged, skipping LLM", company_name)
            return [], new_hash, "UNCHANGED"

        # ── HTML → Markdown ──────────────────────────────────────────────
        markdown = _h2t.handle(resp.text)
        if len(markdown) > MAX_MARKDOWN_CHARS:
            markdown = markdown[:MAX_MARKDOWN_CHARS]

        # ── SPA Detection ────────────────────────────────────────────────
        if _detect_spa(resp.text, markdown):
            logger.warning("  %s: career page likely SPA (%d chars), skipping LLM",
                           company_name, len(markdown.strip()))
            return [], new_hash, "SPA_DETECTED"

        # ── LLM extraction with pagination loop ──────────────────────────
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
                resp = await _fetch_page(http, next_url)
            except httpx.HTTPStatusError:
                logger.warning("  %s: pagination page %d returned error, stopping", company_name, page_num)
                break

            markdown = _h2t.handle(resp.text)
            if len(markdown) > MAX_MARKDOWN_CHARS:
                markdown = markdown[:MAX_MARKDOWN_CHARS]

            if len(markdown.strip()) < 100:
                break

            items, next_url = await _extract_page(client, markdown, company_name, next_url, base_url)
            all_jobs.extend(_items_to_jobs(items, company_name, base_url))

    logger.info("  %s: LLM extracted %d PM jobs across %d page(s)", company_name, len(all_jobs), page_num)
    return all_jobs, new_hash, "OK"
