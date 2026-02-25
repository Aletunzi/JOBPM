"""
Auto-discover company website URLs via GPT-4o-mini.

Strategy:
  1. Batch company names into groups of ~25
  2. Ask GPT-4o-mini to infer the official website URL for each
  3. Validate each URL with HEAD request
  4. Return {company_name: website_url}

Cost: ~$0.05-0.10 for 1000 companies (batched LLM calls).
"""

import asyncio
import json
import logging
from typing import Optional

import httpx
from openai import AsyncOpenAI

logger = logging.getLogger("scraper.website_discovery")

_openai_client: Optional[AsyncOpenAI] = None

BATCH_SIZE = 25           # companies per LLM call
LLM_CONCURRENCY = 5      # parallel LLM requests
VALIDATION_CONCURRENCY = 20
TIMEOUT = 10
USER_AGENT = "JOBPM/1.0 (website discovery)"

SYSTEM_PROMPT = """You are a company information lookup tool. For each company name provided, return its official website URL.

Return ONLY a JSON object with this format:
{"results": [{"name": "Company Name", "url": "https://example.com"}, ...]}

Rules:
- Return the main company homepage URL (NOT the careers page, NOT a product page)
- Use https:// prefix
- If you are not sure about a company, return null for the url
- Do NOT invent URLs — only return URLs you are confident about
- For well-known companies return their primary domain (e.g. google.com, stripe.com)
- Include www. only if the company's canonical URL uses it"""


def _get_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI()
    return _openai_client


async def _validate_url(client: httpx.AsyncClient, url: str) -> Optional[str]:
    """Validate a URL with HEAD then GET fallback. Returns the final URL or None."""
    try:
        resp = await client.head(url)
        if resp.status_code < 400:
            return str(resp.url)  # follow redirects
        # Some servers don't support HEAD
        if resp.status_code == 405:
            resp = await client.get(url)
            if resp.status_code < 400:
                return str(resp.url)
    except (httpx.HTTPError, httpx.InvalidURL):
        pass

    # Try www variant
    if "://www." not in url:
        www_url = url.replace("://", "://www.", 1)
        try:
            resp = await client.head(www_url)
            if resp.status_code < 400:
                return str(resp.url)
        except (httpx.HTTPError, httpx.InvalidURL):
            pass

    # Try without www
    if "://www." in url:
        no_www = url.replace("://www.", "://", 1)
        try:
            resp = await client.head(no_www)
            if resp.status_code < 400:
                return str(resp.url)
        except (httpx.HTTPError, httpx.InvalidURL):
            pass

    return None


async def _infer_batch(names: list[str]) -> dict[str, Optional[str]]:
    """Ask LLM to infer website URLs for a batch of company names."""
    client = _get_client()

    names_text = "\n".join(f"- {name}" for name in names)
    try:
        completion = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Find the official website URL for each company:\n\n{names_text}"},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=2048,
        )

        raw = completion.choices[0].message.content or "{}"
        data = json.loads(raw)
        results = data.get("results", [])

        mapping: dict[str, Optional[str]] = {}
        for item in results:
            name = item.get("name", "").strip()
            url = (item.get("url") or "").strip() or None
            if name and url:
                # Match back to original name (case-insensitive)
                for orig in names:
                    if orig.lower() == name.lower():
                        mapping[orig] = url
                        break
                else:
                    # Fuzzy match: try partial matching
                    for orig in names:
                        if name.lower() in orig.lower() or orig.lower() in name.lower():
                            if orig not in mapping:
                                mapping[orig] = url
                                break
        return mapping

    except Exception as exc:
        logger.error("LLM batch inference failed: %s", exc)
        return {}


async def discover_websites(
    companies: list,
    max_companies: int = 500,
) -> dict[str, str]:
    """Discover website URLs for companies that don't have one.

    Args:
        companies: list of Company ORM objects (with .name, .website_url)
        max_companies: limit per run

    Returns:
        {company_name: website_url}
    """
    to_discover = [c for c in companies if not c.website_url][:max_companies]

    if not to_discover:
        logger.info("All companies already have website URLs.")
        return {}

    logger.info("Discovering website URLs for %d companies via LLM...", len(to_discover))

    # ── Step 1: Batch LLM inference ──────────────────────────────────────────
    names = [c.name for c in to_discover]
    batches = [names[i:i + BATCH_SIZE] for i in range(0, len(names), BATCH_SIZE)]

    llm_semaphore = asyncio.Semaphore(LLM_CONCURRENCY)
    raw_urls: dict[str, Optional[str]] = {}

    async def _run_batch(batch):
        async with llm_semaphore:
            result = await _infer_batch(batch)
            raw_urls.update(result)

    await asyncio.gather(*[_run_batch(b) for b in batches], return_exceptions=True)
    logger.info("LLM inferred %d URLs from %d companies", len(raw_urls), len(names))

    # ── Step 2: Validate with HEAD requests ──────────────────────────────────
    validated: dict[str, str] = {}
    val_semaphore = asyncio.Semaphore(VALIDATION_CONCURRENCY)

    async with httpx.AsyncClient(
        timeout=TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as http:

        async def _validate_one(name: str, url: str):
            async with val_semaphore:
                final = await _validate_url(http, url)
                if final:
                    validated[name] = final
                    logger.info("  ✓ %s → %s", name, final)
                else:
                    logger.debug("  ✗ %s: %s failed validation", name, url)

        tasks = []
        for name, url in raw_urls.items():
            if url:
                tasks.append(_validate_one(name, url))

        await asyncio.gather(*tasks, return_exceptions=True)

    logger.info("Website discovery complete: %d/%d URLs validated", len(validated), len(to_discover))
    return validated
