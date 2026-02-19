# PM Job Tracker

Daily-updated directory of Product Management openings across EU and US, scraped from Greenhouse, Lever, Ashby, Adzuna, and LinkedIn (via Proxycurl).

## Architecture

```
GitHub Actions (cron 07:00 UTC)
        │
        ▼
  Python Scraper ──── Greenhouse / Lever / Ashby (free JSON APIs)
        │         ──── Adzuna API (free)
        │         ──── Proxycurl API (LinkedIn, ~$9/mo)
        │
        ▼
  Render PostgreSQL
        │
        ▼
  FastAPI (Render Web Service) ── X-API-Key ──► Frontend / Lovable
```

## Local Development

```bash
# 1. Copy env file and fill in values
cp .env.example .env

# 2. Start a local Postgres (Docker example)
docker run -d -p 5432:5432 -e POSTGRES_DB=pmjobs -e POSTGRES_USER=pmjobs -e POSTGRES_PASSWORD=pmjobs postgres:16

# 3. Set DATABASE_URL in .env
DATABASE_URL=postgresql+asyncpg://pmjobs:pmjobs@localhost:5432/pmjobs

# 4. Install dependencies
pip install -r requirements.txt

# 5. Run scraper (populates the DB)
python run_scraper.py

# 6. Start API + frontend
uvicorn api.main:app --reload

# 7. Open http://localhost:8000
```

## API Usage

All endpoints require header: `X-API-Key: <your-key>`

| Endpoint | Description |
|---|---|
| `GET /api/jobs` | List jobs. Params: `geo`, `seniority`, `vertical`, `tier`, `date`, `keyword`, `cursor`, `limit` |
| `GET /api/jobs/new` | Jobs added in last 24h |
| `GET /api/jobs/{id}` | Single job detail |
| `GET /api/companies` | Tracked companies |
| `GET /api/stats` | Totals and counts |
| `POST /api/scrape` | Manually trigger scrape |

**Example:**
```bash
curl -H "X-API-Key: your-key" \
  "https://your-render-url.onrender.com/api/jobs?geo=EU&seniority=SENIOR,STAFF&date=7D"
```

## Deploy on Render (one-time setup)

1. Push this repo to GitHub
2. Go to [render.com](https://render.com) → New → Blueprint → connect repo
3. Render reads `render.yaml` and creates the Web Service + PostgreSQL automatically
4. Copy the generated `API_KEY` from Render dashboard → use in your frontend / Lovable
5. Add secrets manually: `PROXYCURL_API_KEY`, `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`

## GitHub Actions Setup (daily scraper)

Add these as **GitHub Secrets** in your repo settings:

| Secret | Value |
|---|---|
| `DATABASE_URL` | Connection string from Render PostgreSQL (use **External** URL) |
| `PROXYCURL_API_KEY` | Your Proxycurl API key |
| `ADZUNA_APP_ID` | Adzuna app ID (optional) |
| `ADZUNA_APP_KEY` | Adzuna app key (optional) |

The scraper runs automatically every day at 07:00 UTC. You can also trigger it manually from the **Actions** tab.

## Adding Companies

Edit `companies.yaml` to add new companies:

```yaml
- name: Acme Corp
  ats: greenhouse    # greenhouse | lever | ashby
  slug: acmecorp     # ATS board slug
  tier: 2
  size: scaleup
  vertical: saas
  geo_primary: US
```

## Spending Cap

Proxycurl calls are capped at `PROXYCURL_DAILY_CAP` per day (default: 100 calls ≈ $0.30/day ≈ $9/mo).
Set a hard cap in the Proxycurl dashboard as a second layer of protection.
