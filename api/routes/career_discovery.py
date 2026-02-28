import asyncio
import os
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
        f"What is the official careers/jobs page URL for the company \"{company_name}\"{site_hint}? "
        "Return ONLY the full URL (starting with https://), nothing else. "
        "If you cannot find it, return exactly: NOT_FOUND"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
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
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"].strip()
            # Extract first URL-like token from response
            for token in text.split():
                if token.startswith("http"):
                    return ProviderResult(url=token.rstrip(".,;"))
            if text.upper() == "NOT_FOUND" or not text.startswith("http"):
                return ProviderResult(url=None)
            return ProviderResult(url=text)
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
        f"What is the official careers/jobs page URL for the company \"{company_name}\"{site_hint}? "
        "Return ONLY the full URL (starting with https://), nothing else. "
        "If you cannot find it, return exactly: NOT_FOUND"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "tools": [{"google_search": {}}],
                    "generationConfig": {
                        "maxOutputTokens": 300,
                        "temperature": 0.0,
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return ProviderResult(url=None)
            parts = candidates[0].get("content", {}).get("parts", [])
            text = " ".join(p.get("text", "") for p in parts).strip()
            # Extract first URL-like token
            for token in text.split():
                if token.startswith("http"):
                    return ProviderResult(url=token.rstrip(".,;"))
            if text.upper() == "NOT_FOUND" or not text.startswith("http"):
                return ProviderResult(url=None)
            return ProviderResult(url=text)
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
