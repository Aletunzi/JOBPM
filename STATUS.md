# PM Job Tracker — Status

## Completato

### Backend
- [x] `requirements.txt` — dipendenze Python (FastAPI, SQLAlchemy async, httpx, pyyaml, asyncpg, alembic, pydantic)
- [x] `.env.example` — template variabili d'ambiente con documentazione
- [x] `companies.yaml` — 75 company seed (Tier 1+2, EU+US): Greenhouse, Lever, Ashby
- [x] `api/database.py` — engine async PostgreSQL (asyncpg), session factory
- [x] `api/models.py` — ORM models: `Company`, `Job`, `ApiUsage` con indici composti + TSVECTOR
- [x] `api/schemas.py` — Pydantic response schemas (JobOut, CompanyOut, StatsOut, JobsResponse)
- [x] `api/auth.py` — API Key middleware (`X-API-Key` header)
- [x] `api/cache.py` — In-memory TTL cache (5 min) per query comuni
- [x] `api/routes/jobs.py` — `GET /api/jobs` (filtri: geo, seniority, vertical, tier, date, keyword, cursor), `GET /api/jobs/new`, `GET /api/jobs/{id}`
- [x] `api/routes/companies.py` — `GET /api/companies`
- [x] `api/routes/stats.py` — `GET /api/stats`
- [x] `api/main.py` — FastAPI app + CORS + StaticFiles mount + `/api/scrape` endpoint

### Scrapers
- [x] `scrapers/normalizer.py` — `NormalizedJob` dataclass, geo inference (EU/US/UK/REMOTE/APAC/OTHER), seniority inference (JUNIOR/MID/SENIOR/STAFF/LEAD/LEADERSHIP/INTERN), PM relevance filter
- [x] `scrapers/base.py` — `BaseJobScraper` ABC
- [x] `scrapers/greenhouse.py` — Greenhouse JSON API (`boards-api.greenhouse.io`)
- [x] `scrapers/lever.py` — Lever JSON API (`api.lever.co/v0/postings`)
- [x] `scrapers/ashby.py` — Ashby JSON API (`api.ashbyhq.com/posting-api`)
- [x] `scrapers/adzuna.py` — Adzuna API (EU: UK/DE/NL/FR + US, 3 pagine per keyword)
- [x] `scrapers/proxycurl.py` — LinkedIn via Proxycurl API con soft cap giornaliero (tabella `api_usage`)
- [x] `run_scraper.py` — Orchestratore async: `asyncio.gather` parallelo, upsert `ON CONFLICT`, mark inactive jobs dopo 7 giorni, refresh search vectors

### Frontend (temporaneo, da sostituire con Lovable)
- [x] `frontend/index.html` — Layout: header stats, sidebar filtri, grid card, paginazione
- [x] `frontend/style.css` — Stili custom (Tailwind CDN + job card, badge, skeleton, apply button)
- [x] `frontend/app.js` — Vanilla JS: fetch API, render card, filtri checkbox/select/keyword (debounce 400ms), paginazione cursor-based, "new only" toggle, stats bar

### Deploy & CI/CD
- [x] `.github/workflows/daily_scrape.yml` — Cron 07:00 UTC + `workflow_dispatch`, timeout 15 min, error notice on failure
- [x] `render.yaml` — Blueprint: Web Service (FastAPI) + PostgreSQL managed, env vars auto-injected
- [x] `README.md` — Istruzioni setup locale, API reference, deploy Render, GitHub Secrets

---

## Da Fare

### Priorità Alta
- [ ] **Alembic init** — Aggiungere `migrations/` con `alembic.ini` e script iniziale (ora le tabelle vengono create con `Base.metadata.create_all` al boot, che va bene per dev ma non per prod)
- [ ] **Test scraper con dati reali** — Eseguire `python run_scraper.py` con DATABASE_URL locale e verificare che le tabelle si popolino correttamente
- [ ] **Validare ATS slug** — Alcuni slug in `companies.yaml` potrebbero essere errati; verificare 404s nei log del primo run
- [ ] **Deploy Render** — Connettere repo, copiare `API_KEY` generato, aggiungere secrets manuali

### Priorità Media
- [ ] **Aggiungere Alembic migrations** per gestire schema changes in produzione
- [ ] **Espandere `companies.yaml`** — Aggiungere Tier 3 companies (300+ aziende) man mano che gli slug vengono verificati
- [ ] **Workday scraper (Fase 2)** — Playwright headless per aziende enterprise (Salesforce, SAP, McKinsey, Bain)
- [ ] **Migrazione frontend → Lovable** — Rimuovere `frontend/`, aggiornare CORS con dominio Lovable, stessa API

### Priorità Bassa
- [ ] **Rate limiting** sull'API FastAPI (es. `slowapi`) per prevenire abusi
- [ ] **Webhook su scrape failure** — Notifica Telegram/email se GitHub Actions fallisce
- [ ] **Dashboard admin** — Pagina separata per visualizzare `api_usage`, status scrapers, company con 0 PM jobs
- [ ] **JSearch integration** — Aggregatore aggiuntivo se si vuole coprire Indeed/Glassdoor ($50/mese)

---

## Note Tecniche

| Componente | Scelta | Motivo |
|---|---|---|
| Backend | FastAPI + asyncpg | Async nativo, type safety con Pydantic |
| DB | PostgreSQL (Render managed) | Persistenza, full-text search, TSVECTOR |
| Scraping | httpx async | Non-blocking, connection pooling |
| Scheduling | GitHub Actions cron | Gratuito, zero server, affidabile |
| Deploy | Render | Zero configurazione server, auto-deploy da push |
| Frontend | Vanilla JS + Tailwind CDN | Nessun build step, temporaneo prima di Lovable |
| Costi stimati | ~$9/mese | Solo Proxycurl (LinkedIn) |
