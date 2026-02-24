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

Return ONLY a JSON object with key "jobs" containing an array of objects. Each object must have:
- "title": the exact job title (string)
- "location": office location or "Remote" (string, empty string if unknown)
- "url": direct link to the job posting (string, must be an absolute URL starting with http)
- "posted_date": posting date in ISO format YYYY-MM-DD if visible (string or null)

Include ONLY these PM-related roles: Product Manager, Product Owner, Head of Product, VP Product, Director of Product, CPO, Group PM, Staff PM, Principal PM, Technical PM, Growth PM, AI PM, Product Lead, Product Strategy, Digital Product Manager, Associate PM.

Exclude: Product Marketing, Product Analyst, Data Analyst, Software Engineer, Engineering Manager, Designer, Project Manager.

If no PM jobs are found, return {"jobs": []}.
Do NOT invent or hallucinate job listings. Only extract what is actually on the page."""

# HTML → Markdown converter config
_h2t = html2text.HTML2Text()
_h2t.ignore_links = False
_h2t.ignore_images = True
_h2t.body_width = 0
_h2t.ignore_emphasis = True

MAX_MARKDOWN_CHARS = 15000  # ~3500 tokens


async def fetch_custom(
    career_url: str,
    company_name: str,
    page_hash: Optional[str] = None,
) -> tuple[list[NormalizedJob], str]:
    """Fetch career page, extract PM jobs via LLM.

    Returns (jobs, new_page_hash).
    If page hasn't changed (same hash), returns ([], same_hash) without calling LLM.
    """
    # ── Fetch page ────────────────────────────────────────────────────────
    async with httpx.AsyncClient(
        timeout=30,
        headers={"User-Agent": "JOBPM/1.0"},
        follow_redirects=True,
    ) as http:
        resp = await http.get(career_url)
        resp.raise_for_status()

    # ── Change detection ──────────────────────────────────────────────────
    new_hash = hashlib.sha256(resp.content).hexdigest()
    if page_hash and new_hash == page_hash:
        logger.debug("  %s: page unchanged, skipping LLM", company_name)
        return [], new_hash

    # ── HTML → Markdown ───────────────────────────────────────────────────
    markdown = _h2t.handle(resp.text)
    if len(markdown) > MAX_MARKDOWN_CHARS:
        markdown = markdown[:MAX_MARKDOWN_CHARS]

    if len(markdown.strip()) < 100:
        logger.warning("  %s: career page too short (%d chars), skipping", company_name, len(markdown))
        return [], new_hash

    # ── Base URL for resolving relative links ─────────────────────────────
    parsed = urlparse(career_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    # ── LLM extraction ────────────────────────────────────────────────────
    client = _get_client()
    completion = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Company: {company_name}\n"
                    f"Career page URL: {career_url}\n"
                    f"Base URL for relative links: {base_url}\n\n"
                    f"--- PAGE CONTENT ---\n{markdown}"
                ),
            },
        ],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=4096,
    )

    # ── Parse response ────────────────────────────────────────────────────
    raw = completion.choices[0].message.content or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("  %s: LLM returned invalid JSON", company_name)
        return [], new_hash

    jobs: list[NormalizedJob] = []
    for item in data.get("jobs", []):
        title = (item.get("title") or "").strip()
        url = (item.get("url") or "").strip()
        if not title or not url:
            continue

        # Resolve relative URLs
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

    logger.info("  %s: LLM extracted %d PM jobs", company_name, len(jobs))
    return jobs, new_hash
