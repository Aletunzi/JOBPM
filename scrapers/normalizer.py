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

APAC_KEYWORDS = {
    "australia", "sydney", "melbourne", "brisbane", "perth", "adelaide",
    "new zealand", "auckland", "singapore", "india", "mumbai", "bangalore",
    "bengaluru", "delhi", "hyderabad", "pune", "chennai", "japan", "tokyo",
    "osaka", "south korea", "seoul", "china", "beijing", "shanghai",
    "guangzhou", "shenzhen", "hong kong", "taiwan", "taipei", "thailand",
    "bangkok", "vietnam", "ho chi minh", "hanoi", "indonesia", "jakarta",
    "malaysia", "kuala lumpur", "philippines", "manila", "apac", "asia pacific",
}

LATAM_KEYWORDS = {
    "brazil", "são paulo", "sao paulo", "rio de janeiro", "bogota", "bogotá",
    "colombia", "argentina", "buenos aires", "chile", "santiago", "peru",
    "lima", "mexico", "ciudad de mexico", "venezuela", "ecuador", "quito",
    "costa rica", "uruguay", "montevideo", "panama", "latin america", "latam",
    "south america",
}

AFRICA_KEYWORDS = {
    "africa", "nigeria", "lagos", "abuja", "kenya", "nairobi", "south africa",
    "johannesburg", "cape town", "egypt", "cairo", "ghana", "accra", "ethiopia",
    "addis ababa", "tanzania", "dar es salaam", "uganda", "kampala", "mozambique",
    "angola", "zimbabwe", "senegal", "dakar", "ivory coast", "abidjan", "cameroon",
    "rwanda", "kigali", "morocco", "casablanca", "rabat", "tunisia", "algeria",
    "madagascar", "mauritius", "zambia", "botswana", "namibia",
}

OCEANIA_KEYWORDS = {
    "australia", "sydney", "melbourne", "brisbane", "perth", "adelaide", "canberra",
    "new zealand", "auckland", "wellington", "christchurch",
    "papua new guinea", "fiji", "pacific islands",
}

ASIA_KEYWORDS = {
    "india", "mumbai", "bangalore", "bengaluru", "delhi", "hyderabad", "pune",
    "chennai", "kolkata", "japan", "tokyo", "osaka", "south korea", "seoul", "busan",
    "china", "beijing", "shanghai", "guangzhou", "shenzhen", "taiwan", "taipei",
    "hong kong", "singapore", "thailand", "bangkok", "vietnam", "ho chi minh",
    "hanoi", "indonesia", "jakarta", "malaysia", "kuala lumpur", "philippines",
    "manila", "myanmar", "yangon", "cambodia", "phnom penh", "laos", "sri lanka",
    "colombo", "pakistan", "karachi", "islamabad", "lahore", "bangladesh", "dhaka",
    "nepal", "kathmandu", "israel", "tel aviv", "jerusalem", "uae", "dubai",
    "abu dhabi", "saudi arabia", "riyadh", "jeddah", "qatar", "doha", "kuwait",
    "bahrain", "oman", "muscat", "turkey", "istanbul", "ankara", "middle east",
    "asia", "southeast asia",
}

NORTH_AMERICA_KEYWORDS = {
    "canada", "toronto", "vancouver", "montreal", "calgary", "ottawa", "edmonton",
    "winnipeg", "quebec", "ontario", "british columbia", "alberta",
    "mexico", "ciudad de mexico", "monterrey", "guadalajara",
    "central america", "costa rica", "guatemala", "panama", "honduras", "nicaragua",
    "caribbean", "cuba", "jamaica", "dominican republic", "puerto rico",
    "north america",
}

SOUTH_AMERICA_KEYWORDS = {
    "brazil", "são paulo", "sao paulo", "rio de janeiro", "colombia", "bogota",
    "bogotá", "argentina", "buenos aires", "chile", "santiago", "peru", "lima",
    "venezuela", "caracas", "ecuador", "quito", "uruguay", "montevideo",
    "paraguay", "asuncion", "bolivia", "la paz",
}

ANTARCTICA_KEYWORDS = {"antarctica", "antarctic"}

# geo_region → continent fallback (when location_raw gives no match)
_GEO_TO_CONTINENT = {
    "REMOTE": "Remote",
    "US":     "North America",
    "UK":     "Europe",
    "EU":     "Europe",
    "APAC":   "Asia",
    "LATAM":  "South America",
    "OTHER":  "Other",
}

# location_raw keyword → canonical country name (ordered: specific first)
_LOCATION_TO_COUNTRY: list[tuple[str, str]] = [
    # ── Phrases that must be checked before shorter substrings ──
    ("united states", "United States"), ("united kingdom", "United Kingdom"),
    ("great britain", "United Kingdom"), ("new zealand", "New Zealand"),
    ("south africa", "South Africa"), ("south korea", "South Korea"),
    ("saudi arabia", "Saudi Arabia"), ("costa rica", "Costa Rica"),
    ("hong kong", "Hong Kong"), ("puerto rico", "Puerto Rico"),
    ("dominican republic", "Dominican Republic"),
    ("papua new guinea", "Papua New Guinea"),
    # ── Country names ──
    ("germany", "Germany"), ("france", "France"), ("spain", "Spain"),
    ("italy", "Italy"), ("netherlands", "Netherlands"), ("portugal", "Portugal"),
    ("belgium", "Belgium"), ("sweden", "Sweden"), ("norway", "Norway"),
    ("denmark", "Denmark"), ("finland", "Finland"), ("poland", "Poland"),
    ("austria", "Austria"), ("switzerland", "Switzerland"), ("ireland", "Ireland"),
    ("czech", "Czech Republic"), ("romania", "Romania"), ("hungary", "Hungary"),
    ("greece", "Greece"), ("croatia", "Croatia"), ("bulgaria", "Bulgaria"),
    ("estonia", "Estonia"), ("latvia", "Latvia"), ("lithuania", "Lithuania"),
    ("luxembourg", "Luxembourg"), ("malta", "Malta"), ("slovakia", "Slovakia"),
    ("slovenia", "Slovenia"), ("cyprus", "Cyprus"),
    ("canada", "Canada"), ("australia", "Australia"), ("india", "India"),
    ("brazil", "Brazil"), ("mexico", "Mexico"), ("argentina", "Argentina"),
    ("colombia", "Colombia"), ("chile", "Chile"), ("peru", "Peru"),
    ("venezuela", "Venezuela"), ("ecuador", "Ecuador"), ("uruguay", "Uruguay"),
    ("paraguay", "Paraguay"), ("bolivia", "Bolivia"),
    ("singapore", "Singapore"), ("japan", "Japan"), ("china", "China"),
    ("taiwan", "Taiwan"), ("indonesia", "Indonesia"), ("malaysia", "Malaysia"),
    ("philippines", "Philippines"), ("thailand", "Thailand"), ("vietnam", "Vietnam"),
    ("myanmar", "Myanmar"), ("cambodia", "Cambodia"),
    ("pakistan", "Pakistan"), ("bangladesh", "Bangladesh"),
    ("sri lanka", "Sri Lanka"), ("nepal", "Nepal"),
    ("israel", "Israel"), ("uae", "UAE"), ("turkey", "Turkey"),
    ("qatar", "Qatar"), ("kuwait", "Kuwait"), ("bahrain", "Bahrain"),
    ("oman", "Oman"),
    ("nigeria", "Nigeria"), ("kenya", "Kenya"), ("egypt", "Egypt"),
    ("ghana", "Ghana"), ("ethiopia", "Ethiopia"), ("tanzania", "Tanzania"),
    ("morocco", "Morocco"), ("tunisia", "Tunisia"), ("algeria", "Algeria"),
    ("senegal", "Senegal"), ("cameroon", "Cameroon"), ("rwanda", "Rwanda"),
    ("uganda", "Uganda"), ("angola", "Angola"), ("mozambique", "Mozambique"),
    ("zimbabwe", "Zimbabwe"), ("zambia", "Zambia"), ("namibia", "Namibia"),
    ("botswana", "Botswana"), ("mauritius", "Mauritius"),
    ("fiji", "Fiji"), ("panama", "Panama"), ("guatemala", "Guatemala"),
    ("honduras", "Honduras"), ("nicaragua", "Nicaragua"), ("cuba", "Cuba"),
    ("jamaica", "Jamaica"),
    # ── Short/ambiguous codes last ──
    ("uk", "United Kingdom"), ("u.k.", "United Kingdom"),
    ("usa", "United States"), ("u.s.a.", "United States"), ("u.s.", "United States"),
    # ── Well-known cities (mapped to country) ──
    ("london", "United Kingdom"), ("manchester", "United Kingdom"),
    ("birmingham", "United Kingdom"), ("glasgow", "United Kingdom"),
    ("edinburgh", "United Kingdom"), ("bristol", "United Kingdom"),
    ("berlin", "Germany"), ("munich", "Germany"), ("hamburg", "Germany"),
    ("frankfurt", "Germany"), ("cologne", "Germany"), ("münchen", "Germany"),
    ("paris", "France"), ("lyon", "France"), ("marseille", "France"),
    ("amsterdam", "Netherlands"), ("rotterdam", "Netherlands"),
    ("madrid", "Spain"), ("barcelona", "Spain"), ("valencia", "Spain"),
    ("milan", "Italy"), ("rome", "Italy"), ("turin", "Italy"), ("milano", "Italy"),
    ("stockholm", "Sweden"), ("gothenburg", "Sweden"),
    ("copenhagen", "Denmark"), ("oslo", "Norway"), ("helsinki", "Finland"),
    ("warsaw", "Poland"), ("krakow", "Poland"), ("wroclaw", "Poland"),
    ("lisbon", "Portugal"), ("porto", "Portugal"),
    ("brussels", "Belgium"), ("antwerp", "Belgium"),
    ("vienna", "Austria"), ("zurich", "Switzerland"), ("geneva", "Switzerland"),
    ("dublin", "Ireland"), ("prague", "Czech Republic"), ("budapest", "Hungary"),
    ("bucharest", "Romania"), ("athens", "Greece"),
    ("riga", "Latvia"), ("tallinn", "Estonia"), ("vilnius", "Lithuania"),
    ("toronto", "Canada"), ("vancouver", "Canada"), ("montreal", "Canada"),
    ("calgary", "Canada"), ("ottawa", "Canada"), ("edmonton", "Canada"),
    ("new york", "United States"), ("san francisco", "United States"),
    ("los angeles", "United States"), ("chicago", "United States"),
    ("seattle", "United States"), ("boston", "United States"),
    ("austin", "United States"), ("denver", "United States"),
    ("atlanta", "United States"), ("miami", "United States"),
    ("dallas", "United States"), ("houston", "United States"),
    ("washington dc", "United States"), ("nyc", "United States"),
    ("sydney", "Australia"), ("melbourne", "Australia"), ("brisbane", "Australia"),
    ("perth", "Australia"), ("adelaide", "Australia"), ("canberra", "Australia"),
    ("auckland", "New Zealand"), ("wellington", "New Zealand"),
    ("mumbai", "India"), ("bangalore", "India"), ("bengaluru", "India"),
    ("delhi", "India"), ("hyderabad", "India"), ("pune", "India"),
    ("chennai", "India"), ("kolkata", "India"),
    ("tokyo", "Japan"), ("osaka", "Japan"),
    ("beijing", "China"), ("shanghai", "China"), ("guangzhou", "China"),
    ("shenzhen", "China"), ("taipei", "Taiwan"),
    ("seoul", "South Korea"), ("busan", "South Korea"),
    ("jakarta", "Indonesia"), ("kuala lumpur", "Malaysia"),
    ("bangkok", "Thailand"), ("manila", "Philippines"),
    ("ho chi minh", "Vietnam"), ("hanoi", "Vietnam"),
    ("singapore city", "Singapore"),
    ("tel aviv", "Israel"), ("dubai", "UAE"), ("abu dhabi", "UAE"),
    ("riyadh", "Saudi Arabia"), ("jeddah", "Saudi Arabia"),
    ("doha", "Qatar"), ("istanbul", "Turkey"), ("ankara", "Turkey"),
    ("nairobi", "Kenya"), ("lagos", "Nigeria"), ("accra", "Ghana"),
    ("cairo", "Egypt"), ("casablanca", "Morocco"), ("addis ababa", "Ethiopia"),
    ("dar es salaam", "Tanzania"), ("johannesburg", "South Africa"),
    ("cape town", "South Africa"), ("kigali", "Rwanda"), ("kampala", "Uganda"),
    ("sao paulo", "Brazil"), ("são paulo", "Brazil"),
    ("rio de janeiro", "Brazil"), ("bogota", "Colombia"), ("bogotá", "Colombia"),
    ("buenos aires", "Argentina"), ("santiago", "Chile"), ("lima", "Peru"),
    ("montevideo", "Uruguay"), ("caracas", "Venezuela"), ("quito", "Ecuador"),
    ("guadalajara", "Mexico"), ("monterrey", "Mexico"),
]


def infer_continent(location_raw: Optional[str], geo_region: str = "OTHER") -> str:
    """Classify a job location into one of 7 continents (+ Remote / Other)."""
    if not location_raw:
        return _GEO_TO_CONTINENT.get(geo_region, "Other")
    loc = location_raw.lower()
    if any(kw in loc for kw in REMOTE_KEYWORDS):
        return "Remote"
    if any(kw in loc for kw in ANTARCTICA_KEYWORDS):
        return "Antarctica"
    if any(kw in loc for kw in AFRICA_KEYWORDS):
        return "Africa"
    if any(kw in loc for kw in OCEANIA_KEYWORDS):
        return "Oceania"
    # Asia checked before APAC fallback so Oceania above takes priority
    if any(kw in loc for kw in ASIA_KEYWORDS):
        return "Asia"
    if (any(kw in loc for kw in UK_KEYWORDS)
            or any(kw in loc for kw in EU_COUNTRIES)
            or any(kw in loc for kw in EU_CITIES)):
        return "Europe"
    if (any(kw in loc for kw in US_STATES)
            or any(kw in loc for kw in US_CITIES)
            or any(kw in loc for kw in NORTH_AMERICA_KEYWORDS)):
        return "North America"
    if any(kw in loc for kw in SOUTH_AMERICA_KEYWORDS):
        return "South America"
    return _GEO_TO_CONTINENT.get(geo_region, "Other")


def extract_country(location_raw: Optional[str], geo_region: str = "OTHER") -> Optional[str]:
    """Extract a canonical country name from a raw location string."""
    if not location_raw:
        return None
    loc = location_raw.lower()
    if any(kw in loc for kw in REMOTE_KEYWORDS):
        return "Remote"
    for kw, country in _LOCATION_TO_COUNTRY:
        if kw in loc:
            return country
    return None


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
    if any(kw in loc for kw in APAC_KEYWORDS):
        return "APAC"
    if any(kw in loc for kw in LATAM_KEYWORDS):
        return "LATAM"
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
