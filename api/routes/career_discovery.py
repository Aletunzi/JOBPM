import asyncio
import os
import re
from typing import Optional

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import require_api_key
from api.database import get_db
from api.models import Company

router = APIRouter(prefix="/api/career-discovery", tags=["career-discovery"])

# Matches any http/https URL; stops before citation brackets [1], parentheses, quotes etc.
_URL_RE = re.compile(r'https?://[^\s\)\]\[\'"<>,;]+')


def _extract_url(text: str) -> Optional[str]:
    """Return the first clean URL found in text, handling markdown links etc."""
    for match in _URL_RE.finditer(text):
        url = match.group(0).rstrip(".,;:)'\"")
        if url:
            return url
    return None


class SearchRequest(BaseModel):
    company_id: str
    company_name: str
    website_url: Optional[str] = None


class ProviderResult(BaseModel):
    url: Optional[str] = None
    error: Optional[str] = None


class SearchResult(BaseModel):
    company_id: str
    sonar: ProviderResult
    gemini: ProviderResult


@router.get("/companies")
async def get_all_companies(
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(require_api_key),
):
    """Return all companies with id, name and website_url for the career discovery page."""
    result = await db.execute(
        select(Company.id, Company.name, Company.website_url, Company.career_url)
        .order_by(Company.name.asc())
    )
    rows = result.all()
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "website_url": r.website_url,
            "current_career_url": r.career_url,
        }
        for r in rows
    ]


async def _search_sonar(company_name: str, website_url: Optional[str]) -> ProviderResult:
    api_key = os.environ.get("PERPLEXITY_API_KEY", "")
    if not api_key:
        return ProviderResult(error="PERPLEXITY_API_KEY not configured")

    site_hint = f" (company website: {website_url})" if website_url else ""
    prompt = (
        f"Find the URL of the page where \"{company_name}\"{site_hint} lists all their open job positions. "
        "I need the specific page that shows the full list of current vacancies or job openings — "
        "NOT the generic careers landing page, NOT the 'About us' or 'Work with us' overview page. "
        "The target page must contain actual job listings or a searchable jobs board with individual postings. "
        "Return ONLY the full URL (starting with https://), nothing else. "
        "If you cannot find it, return exactly: NOT_FOUND"
    )

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            for attempt in range(2):
                resp = await client.post(
                    "https://api.perplexity.ai/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "sonar",
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 300,
                        "temperature": 0.0,
                    },
                )
                if resp.status_code == 429 and attempt == 0:
                    await asyncio.sleep(4)
                    continue
                resp.raise_for_status()
                break
            data = resp.json()
            text = data["choices"][0]["message"]["content"].strip()
            url = _extract_url(text)
            if url:
                return ProviderResult(url=url)
            return ProviderResult(url=None)
    except httpx.HTTPStatusError as e:
        return ProviderResult(error=f"HTTP {e.response.status_code}: {e.response.text[:200]}")
    except Exception as e:
        return ProviderResult(error=str(e)[:300])


async def _search_gemini(company_name: str, website_url: Optional[str]) -> ProviderResult:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return ProviderResult(error="GEMINI_API_KEY not configured")

    site_hint = f" (company website: {website_url})" if website_url else ""
    prompt = (
        f"Find the URL of the page where \"{company_name}\"{site_hint} lists all their open job positions. "
        "I need the specific page that shows the full list of current vacancies or job openings — "
        "NOT the generic careers landing page, NOT the 'About us' or 'Work with us' overview page. "
        "The target page must contain actual job listings or a searchable jobs board with individual postings. "
        "Return ONLY the full URL (starting with https://), nothing else. "
        "If you cannot find it, return exactly: NOT_FOUND"
    )

    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={api_key}"
    )
    base_payload: dict = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 300, "temperature": 0.0},
    }

    async def _call(use_search: bool) -> httpx.Response:
        payload = {**base_payload}
        if use_search:
            payload["tools"] = [{"google_search": {}}]
        async with httpx.AsyncClient(timeout=45.0) as client:
            for attempt in range(2):
                r = await client.post(
                    endpoint,
                    headers={"Content-Type": "application/json"},
                    json=payload,
                )
                if r.status_code == 429 and attempt == 0:
                    await asyncio.sleep(4)
                    continue
                return r
        return r  # type: ignore[return-value]

    def _parse(resp: httpx.Response) -> Optional[str]:
        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return None
        parts = candidates[0].get("content", {}).get("parts", [])
        text = " ".join(p.get("text", "") for p in parts if "text" in p).strip()
        url = _extract_url(text)
        if url:
            return url
        # Fallback: grounding metadata (only present when google_search is used)
        grounding = candidates[0].get("groundingMetadata", {})
        for chunk in grounding.get("groundingChunks", []):
            uri = chunk.get("web", {}).get("uri", "")
            if uri.startswith("http"):
                return uri
        return None

    try:
        resp = await _call(use_search=True)
        resp.raise_for_status()
        return ProviderResult(url=_parse(resp))
    except httpx.HTTPStatusError as e:
        return ProviderResult(error=f"HTTP {e.response.status_code}: {e.response.text[:200]}")
    except Exception as e:
        return ProviderResult(error=str(e)[:300])


@router.post("/search", response_model=SearchResult)
async def search_career_url(
    req: SearchRequest,
    _key: str = Depends(require_api_key),
):
    """Run Sonar + Gemini searches in parallel for a single company and return career URL results."""
    sonar_result, gemini_result = await asyncio.gather(
        _search_sonar(req.company_name, req.website_url),
        _search_gemini(req.company_name, req.website_url),
    )
    return SearchResult(
        company_id=req.company_id,
        sonar=sonar_result,
        gemini=gemini_result,
    )
