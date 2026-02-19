from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

# ── Geo inference ──────────────────────────────────────────────────────────────

REMOTE_KEYWORDS = {
    "remote", "worldwide", "anywhere", "distributed", "global",
    "fully remote", "work from home", "wfh", "location flexible",
}

EU_COUNTRIES = {
    "germany", "france", "netherlands", "spain", "italy", "sweden",
    "denmark", "finland", "norway", "poland", "portugal", "belgium",
    "austria", "switzerland", "ireland", "czech republic", "czechia",
    "romania", "hungary", "greece", "slovakia", "croatia", "bulgaria",
    "estonia", "latvia", "lithuania", "luxembourg", "malta", "cyprus",
    "slovenia", "europe", "european union",
}

EU_CITIES = {
    "berlin", "munich", "hamburg", "frankfurt", "cologne", "düsseldorf",
    "paris", "lyon", "marseille", "bordeaux",
    "amsterdam", "rotterdam", "utrecht", "the hague",
    "madrid", "barcelona", "valencia", "seville",
    "milan", "rome", "florence", "turin",
    "stockholm", "gothenburg", "malmö",
    "copenhagen", "aarhus",
    "helsinki", "oslo",
    "warsaw", "krakow", "wroclaw",
    "lisbon", "porto",
    "brussels", "antwerp",
    "vienna", "zurich", "geneva", "bern",
    "dublin",
    "prague",
    "budapest",
    "bucharest",
    "riga", "tallinn", "vilnius",
    "luxembourg city",
}

US_STATES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york", "north carolina",
    "north dakota", "ohio", "oklahoma", "oregon", "pennsylvania",
    "rhode island", "south carolina", "south dakota", "tennessee", "texas",
    "utah", "vermont", "virginia", "washington", "west virginia",
    "wisconsin", "wyoming", "district of columbia",
}

US_CITIES = {
    "new york", "san francisco", "los angeles", "chicago", "seattle",
    "boston", "austin", "denver", "atlanta", "miami", "dallas",
    "houston", "phoenix", "portland", "san jose", "san diego",
    "minneapolis", "detroit", "washington dc", "nyc", "sf", "la",
    "united states", "usa", "u.s.", "u.s.a.",
}

UK_KEYWORDS = {
    "london", "manchester", "birmingham", "leeds", "glasgow", "edinburgh",
    "bristol", "liverpool", "united kingdom", "uk", "england", "scotland",
    "wales", "great britain",
}


def infer_geo(location_raw: Optional[str]) -> str:
    if not location_raw:
        return "OTHER"
    loc = location_raw.lower()

    if any(kw in loc for kw in REMOTE_KEYWORDS):
        return "REMOTE"
    if any(kw in loc for kw in UK_KEYWORDS):
        return "UK"
    if any(kw in loc for kw in EU_COUNTRIES) or any(kw in loc for kw in EU_CITIES):
        return "EU"
    if any(kw in loc for kw in US_STATES) or any(kw in loc for kw in US_CITIES):
        return "US"
    return "OTHER"


# ── Seniority inference ────────────────────────────────────────────────────────

LEADERSHIP_KW = {"director", "vp", "vice president", "head of", "cpo", "chief product"}
STAFF_KW = {"staff", "principal", "distinguished"}
LEAD_KW = {"lead", "group", "group product"}
SENIOR_KW = {"senior", "sr."}
JUNIOR_KW = {"junior", "associate", "entry", "entry-level", "entry level", "jr."}
INTERN_KW = {"intern", "internship", "apprentice"}


def infer_seniority(title: str) -> str:
    t = title.lower()
    if any(kw in t for kw in INTERN_KW):
        return "INTERN"
    if any(kw in t for kw in LEADERSHIP_KW):
        return "LEADERSHIP"
    if any(kw in t for kw in STAFF_KW):
        return "STAFF"
    if any(kw in t for kw in LEAD_KW):
        return "LEAD"
    if any(kw in t for kw in SENIOR_KW):
        return "SENIOR"
    if any(kw in t for kw in JUNIOR_KW):
        return "JUNIOR"
    return "MID"


# ── PM relevance filter ────────────────────────────────────────────────────────

PM_TITLE_KEYWORDS = {
    "product manager", "product management", "group product", "staff pm",
    "senior pm", "principal pm", "product lead", "vp product", "vp of product",
    "head of product", "chief product", "cpo", "product owner",
    "technical product", "growth pm", "platform pm", "ai pm",
}

PM_EXCLUDE_KEYWORDS = {
    "product marketing", "product analyst", "data analyst",
    "software engineer", "engineering manager", "designer",
    "product operations analyst",
}


def is_pm_role(title: str) -> bool:
    t = title.lower()
    if any(excl in t for excl in PM_EXCLUDE_KEYWORDS):
        return False
    return any(kw in t for kw in PM_TITLE_KEYWORDS)


# ── NormalizedJob ──────────────────────────────────────────────────────────────

@dataclass
class NormalizedJob:
    source_id: str
    source: str
    title: str
    company_name: str
    location_raw: Optional[str]
    url: str
    posted_date: Optional[date]
    geo_region: str
    seniority: str


def normalize_date(raw) -> Optional[date]:
    """Parse various date formats into a date object."""
    if raw is None:
        return None
    if isinstance(raw, (date, datetime)):
        return raw.date() if isinstance(raw, datetime) else raw
    if isinstance(raw, (int, float)):
        # Unix timestamp in milliseconds
        if raw > 1e12:
            raw = raw / 1000
        return datetime.fromtimestamp(raw, tz=timezone.utc).date()
    if isinstance(raw, str):
        for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(raw[:19], fmt[:len(raw[:19])]).date()
            except ValueError:
                continue
    return None
