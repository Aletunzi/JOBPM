/**
 * PM Job Tracker — Frontend App
 * Calls the FastAPI backend and renders job cards.
 * API key is stored here for personal use only.
 * Replace with env-aware approach when migrating to Lovable.
 */

const API_KEY = window.__API_KEY__ || "dev-insecure-key";
const API_BASE = "";   // same origin; update to full URL when Lovable takes over
const PAGE_SIZE = 40;

// ── State ─────────────────────────────────────────────────────────────────────

const state = {
  currentPage: 1,
  cursorHistory: [],   // cursorHistory[i] = cursor to fetch page i+2
  hasMore: false,
  loading: false,
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function getCheckedByName(name) {
  return [...document.querySelectorAll(`input[name="${name}"]:checked`)].map(el => el.value);
}

// For the date multi-select: pick the most inclusive date range
const DATE_DAYS = { "TODAY": 1, "7D": 7, "30D": 30, "ALL": Infinity };

function resolveMultiDate(values) {
  if (!values.length) return "7D";
  if (values.includes("ALL")) return "ALL";
  return values.reduce((best, v) => (DATE_DAYS[v] > DATE_DAYS[best] ? v : best), values[0]);
}

function buildParams(cursor = null) {
  const keyword   = document.getElementById("filter-keyword").value.trim();
  const rawCity   = document.getElementById("filter-city").value.trim();
  const dateVals  = getCheckedByName("date");
  const dateVal   = resolveMultiDate(dateVals);
  const seniority = getCheckedByName("seniority");
  const workType  = getCheckedByName("work_type");

  const { city: resolvedCity, geo: resolvedGeo } = resolveLocationFilter(rawCity);

  const p = new URLSearchParams();
  if (seniority.length) p.set("seniority", seniority.join(","));
  if (workType.length)  p.set("work_type", workType.join(","));
  if (keyword)          p.set("keyword",   keyword);
  if (resolvedGeo)      p.set("geo",       resolvedGeo);
  if (resolvedCity)     p.set("city",      resolvedCity);
  if (dateVal && dateVal !== "ALL") p.set("date", dateVal);
  p.set("limit", PAGE_SIZE);
  if (cursor) p.set("cursor", cursor);
  return p;
}

async function apiFetch(endpoint, params = null) {
  const url = params ? `${API_BASE}${endpoint}?${params}` : `${API_BASE}${endpoint}`;
  const res = await fetch(url, { headers: { "X-API-Key": API_KEY } });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}


// ── Rendering ─────────────────────────────────────────────────────────────────

// ── Location filter resolution ────────────────────────────────────────────────

// Continent / macro-region names (any language) → geo_region param values
const CONTINENT_TO_GEO = {
  "europe": "EU,UK",        "europa": "EU,UK",      "european": "EU,UK",
  "europäisch": "EU,UK",   "européen": "EU,UK",    "europeo": "EU,UK",
  "north america": "US",   "nordamerika": "US",    "nordamerica": "US",
  "amérique du nord": "US", "america del norte": "US",
  "asia": "APAC",           "asie": "APAC",          "asien": "APAC",
  "asia-pacific": "APAC",  "apac": "APAC",
  "latam": "LATAM",         "latin america": "LATAM", "latinoamérica": "LATAM",
  "latinoamerica": "LATAM", "south america": "LATAM", "südamerika": "LATAM",
  "amérique latine": "LATAM", "lateinamerika": "LATAM", "sudamérica": "LATAM",
  "sudamerica": "LATAM",    "america latina": "LATAM",
  "remote": "REMOTE",       "remoto": "REMOTE",     "à distance": "REMOTE",
  "heimarbeit": "REMOTE",   "telearbeit": "REMOTE",
  // Countries with dedicated geo_region
  "united kingdom": "UK",   "uk": "UK",             "great britain": "UK",
  "gb": "UK",               "england": "UK",        "britain": "UK",
  "united states": "US",    "usa": "US",
};

// Country → main cities that appear in job location_raw strings
const COUNTRY_CITIES = {
  "Italy":          ["Milan", "Rome", "Turin", "Bologna", "Florence", "Naples", "Genoa", "Venice", "Palermo", "Milano", "Roma", "Torino"],
  "Germany":        ["Berlin", "Munich", "Hamburg", "Frankfurt", "Cologne", "Stuttgart", "Düsseldorf", "Leipzig", "Nuremberg", "Dortmund", "Bremen"],
  "France":         ["Paris", "Lyon", "Marseille", "Toulouse", "Bordeaux", "Lille", "Nice", "Nantes", "Strasbourg", "Rennes"],
  "Spain":          ["Madrid", "Barcelona", "Valencia", "Seville", "Bilbao", "Málaga", "Zaragoza"],
  "Netherlands":    ["Amsterdam", "Rotterdam", "The Hague", "Utrecht", "Eindhoven", "Delft"],
  "Belgium":        ["Brussels", "Antwerp", "Ghent", "Leuven"],
  "Switzerland":    ["Zurich", "Geneva", "Basel", "Bern", "Lausanne", "Zug"],
  "Austria":        ["Vienna", "Graz", "Linz", "Salzburg"],
  "Sweden":         ["Stockholm", "Gothenburg", "Malmö", "Uppsala"],
  "Norway":         ["Oslo", "Bergen", "Trondheim"],
  "Denmark":        ["Copenhagen", "Aarhus"],
  "Finland":        ["Helsinki", "Tampere", "Espoo"],
  "Poland":         ["Warsaw", "Kraków", "Wrocław", "Gdańsk", "Poznan"],
  "Ireland":        ["Dublin", "Cork", "Galway"],
  "Portugal":       ["Lisbon", "Porto", "Braga"],
  "Czech Republic": ["Prague", "Brno", "Ostrava"],
  "Hungary":        ["Budapest"],
  "Romania":        ["Bucharest", "Cluj-Napoca", "Timisoara"],
  "Greece":         ["Athens", "Thessaloniki"],
  "Croatia":        ["Zagreb", "Split"],
  "Canada":         ["Toronto", "Vancouver", "Montreal", "Ottawa", "Calgary"],
  "Australia":      ["Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide"],
  "India":          ["Bangalore", "Bengaluru", "Mumbai", "Delhi", "Hyderabad", "Chennai", "Pune"],
  "Singapore":      ["Singapore"],
  "Japan":          ["Tokyo", "Osaka", "Yokohama"],
  "China":          ["Beijing", "Shanghai", "Shenzhen", "Guangzhou"],
  "Israel":         ["Tel Aviv", "Jerusalem", "Haifa", "Herzliya"],
  "UAE":            ["Dubai", "Abu Dhabi"],
  "Turkey":         ["Istanbul", "Ankara", "Izmir"],
  "Brazil":         ["São Paulo", "Rio de Janeiro", "Belo Horizonte", "Curitiba"],
  "Mexico":         ["Mexico City", "Monterrey", "Guadalajara"],
  "Argentina":      ["Buenos Aires", "Córdoba"],
  "Colombia":       ["Bogotá", "Medellín"],
  "Chile":          ["Santiago"],
};

// Multilingual location aliases → English (cities and countries)
const LOCATION_ALIAS = {
  // Cities — German
  "münchen": "Munich",      "muenchen": "Munich",
  "köln": "Cologne",        "koeln": "Cologne",
  "düsseldorf": "Dusseldorf", "duesseldorf": "Dusseldorf",
  "nürnberg": "Nuremberg",  "nuernberg": "Nuremberg",
  "frankfurt am main": "Frankfurt",
  "hannover": "Hanover",
  "wien": "Vienna",
  "zürich": "Zurich",       "zuerich": "Zurich",
  "genève": "Geneva",       "geneve": "Geneva",     "genf": "Geneva",
  "brüssel": "Brussels",    "brussel": "Brussels",
  "göteborg": "Gothenburg", "goteborg": "Gothenburg",
  "kopenhagen": "Copenhagen",
  "moskau": "Moscow",
  "warschau": "Warsaw",
  "prag": "Prague",
  "mailand": "Milan",
  "lissabon": "Lisbon",
  // Cities — Italian
  "berlino": "Berlin",      "amburgo": "Hamburg",
  "monaco di baviera": "Munich", "francoforte": "Frankfurt", "colonia": "Cologne",
  "varsavia": "Warsaw",     "praga": "Prague",
  "barcellona": "Barcelona", "siviglia": "Seville",
  "lisbona": "Lisbon",      "bruxelles": "Brussels",
  "stoccolma": "Stockholm",
  "mosca": "Moscow",        "moscou": "Moscow",     "moscú": "Moscow",
  "roma": "Rome",           "firenze": "Florence",
  "torino": "Turin",        "napoli": "Naples",     "venezia": "Venice",
  "milano": "Milan",
  // Cities — Spanish
  "berlín": "Berlin",       "múnich": "Munich",     "hamburgo": "Hamburg",
  "francfort": "Frankfurt", "ámsterdam": "Amsterdam",
  "copenhague": "Copenhagen",
  "varsovia": "Warsaw",
  // Cities — French
  "vienne": "Vienna",
  "varsovie": "Warsaw",
  "lisbonne": "Lisbon",
  "moscou": "Moscow",
  // Countries — German
  "deutschland": "Germany",    "frankreich": "France",    "spanien": "Spain",
  "italien": "Italy",          "niederlande": "Netherlands", "belgien": "Belgium",
  "schweiz": "Switzerland",    "österreich": "Austria",   "schweden": "Sweden",
  "norwegen": "Norway",        "dänemark": "Denmark",     "finnland": "Finland",
  "polen": "Poland",           "tschechien": "Czech Republic", "ungarn": "Hungary",
  "rumänien": "Romania",       "irland": "Ireland",       "griechenland": "Greece",
  "kroatien": "Croatia",       "grossbritannien": "United Kingdom",
  "vereinigtes königreich": "United Kingdom",
  "vereinigte staaten": "United States",
  "kanada": "Canada",          "australien": "Australia", "indien": "India",
  "brasilien": "Brazil",       "mexiko": "Mexico",        "argentinien": "Argentina",
  "singapur": "Singapore",     "japan": "Japan",
  // Countries — Italian
  "germania": "Germany",       "spagna": "Spain",
  "paesi bassi": "Netherlands", "belgio": "Belgium",
  "svizzera": "Switzerland",   "svezia": "Sweden",       "norvegia": "Norway",
  "danimarca": "Denmark",      "finlandia": "Finland",   "polonia": "Poland",
  "regno unito": "United Kingdom", "stati uniti": "United States",
  "brasile": "Brazil",         "messico": "Mexico",
  "giappone": "Japan",         "cina": "China",
  // Countries — French
  "allemagne": "Germany",      "espagne": "Spain",       "italie": "Italy",
  "pays-bas": "Netherlands",   "pays bas": "Netherlands",
  "autriche": "Austria",       "suisse": "Switzerland",  "suède": "Sweden",
  "suede": "Sweden",           "danemark": "Denmark",    "finlande": "Finland",
  "pologne": "Poland",         "irlande": "Ireland",     "grèce": "Greece",
  "royaume-uni": "United Kingdom", "royaume uni": "United Kingdom",
  "états-unis": "United States", "etats-unis": "United States",
  "états unis": "United States",
  "brésil": "Brazil",          "bresil": "Brazil",       "mexique": "Mexico",
  "japon": "Japan",             "chine": "China",         "inde": "India",
  // Countries — Spanish
  "alemania": "Germany",       "francia": "France",
  "países bajos": "Netherlands", "bélgica": "Belgium",   "belgica": "Belgium",
  "suecia": "Sweden",          "noruega": "Norway",      "dinamarca": "Denmark",
  "polonia": "Poland",         "irlanda": "Ireland",     "grecia": "Greece",
  "reino unido": "United Kingdom", "estados unidos": "United States",
  "japón": "Japan",             "china": "China",
};

// Resolve a raw filter input → { city, geo } params for the API
function resolveLocationFilter(raw) {
  if (!raw) return { city: null, geo: null };
  const lower = raw.toLowerCase().trim();

  // 1. Direct continent / macro-region check (handles "europe", "remote", "uk", "usa"…)
  if (CONTINENT_TO_GEO[lower]) return { city: null, geo: CONTINENT_TO_GEO[lower] };

  // 2. Translate non-English → English (exact then partial)
  let translated = LOCATION_ALIAS[lower];
  if (!translated) {
    for (const [alias, en] of Object.entries(LOCATION_ALIAS)) {
      if (lower.includes(alias)) { translated = raw.replace(new RegExp(alias, "gi"), en); break; }
    }
  }
  translated = translated || raw;

  // 3. Check translated value against geo map (e.g. "gran bretagna"→"United Kingdom"→geo=UK)
  if (CONTINENT_TO_GEO[translated.toLowerCase()]) {
    return { city: null, geo: CONTINENT_TO_GEO[translated.toLowerCase()] };
  }

  // 4. Country → expand to "Country,City1,City2,…" so backend ORs all terms
  const cities = COUNTRY_CITIES[translated];
  if (cities) return { city: [translated, ...cities].join(","), geo: null };

  return { city: translated, geo: null };
}

// ISO 2-letter country codes → English country name
const ISO_COUNTRY_CODES = {
  "de": "Germany",         "gb": "United Kingdom",  "us": "United States",
  "fr": "France",          "es": "Spain",            "it": "Italy",
  "nl": "Netherlands",     "be": "Belgium",          "ch": "Switzerland",
  "at": "Austria",         "se": "Sweden",           "no": "Norway",
  "dk": "Denmark",         "fi": "Finland",          "pl": "Poland",
  "ie": "Ireland",         "pt": "Portugal",         "cz": "Czech Republic",
  "hu": "Hungary",         "ro": "Romania",          "gr": "Greece",
  "hr": "Croatia",         "ca": "Canada",           "au": "Australia",
  "sg": "Singapore",       "jp": "Japan",            "cn": "China",
  "il": "Israel",          "ae": "United Arab Emirates", "tr": "Turkey",
  "br": "Brazil",          "mx": "Mexico",           "ar": "Argentina",
  "co": "Colombia",        "cl": "Chile",            "in": "India",
  "za": "South Africa",    "nz": "New Zealand",      "uk": "United Kingdom",
};

// Sub-regions that map to their parent country
const SUBREGION_TO_COUNTRY = {
  "england": "United Kingdom",       "scotland": "United Kingdom",
  "wales": "United Kingdom",         "northern ireland": "United Kingdom",
  "bavaria": "Germany",              "north rhine-westphalia": "Germany",
  "catalonia": "Spain",              "cataluña": "Spain",
  "île-de-france": "France",         "ile-de-france": "France",
  "lombardy": "Italy",               "lombardia": "Italy",
  "ontario": "Canada",               "british columbia": "Canada",
  "quebec": "Canada",                "new south wales": "Australia",
  "victoria": "Australia",           "queensland": "Australia",
};

// Display-only normalisation: formats location_raw as "City, Country" (English)
function formatLocation(raw) {
  if (!raw) return null;
  const parts = raw.split(",").map(s => s.trim()).filter(Boolean);
  if (parts.length === 0) return null;

  // Normalise city name (translate non-English aliases)
  let city = parts[0];
  const cityLower = city.toLowerCase();
  if (LOCATION_ALIAS[cityLower]) city = LOCATION_ALIAS[cityLower];

  if (parts.length === 1) return city;

  // Scan from the end to find the country
  let country = null;
  for (let i = parts.length - 1; i >= 1; i--) {
    const part = parts[i];
    const lower = part.toLowerCase();
    if (ISO_COUNTRY_CODES[lower]) {
      country = ISO_COUNTRY_CODES[lower];
      break;
    }
    if (SUBREGION_TO_COUNTRY[lower]) {
      if (!country) country = SUBREGION_TO_COUNTRY[lower];
      continue;
    }
    // Plain country name (translate if needed)
    country = LOCATION_ALIAS[lower] ? LOCATION_ALIAS[lower] : part;
    break;
  }

  return country ? `${city}, ${country}` : city;
}

function timeSince(isoString) {
  const diff = Date.now() - new Date(isoString).getTime();
  const h = Math.floor(diff / 3600000);
  const d = Math.floor(h / 24);
  if (d > 30) return "> 1 month";
  if (d > 0) return `${d}d ago`;
  if (h > 0) return `${h}h ago`;
  return "Just now";
}

function renderCard(job) {
  const isNew = job.is_new;
  return `
    <div class="job-card ${isNew ? "is-new" : ""}">
      <div class="flex items-start justify-between gap-2">
        <div class="flex-1 min-w-0">
          ${isNew ? '<span class="badge badge-new mb-1">&#9679; New</span>' : ""}
          <h3 class="font-semibold text-gray-900 text-base leading-snug truncate" title="${escHtml(job.title)}">${escHtml(job.title)}</h3>
          <p class="text-gray-500 text-xs mt-0.5 truncate">${escHtml(job.company_name)}</p>
        </div>
        <a href="${escHtml(job.url)}" target="_blank" rel="noopener noreferrer" class="btn-apply flex-shrink-0">
          Apply &#8599;
        </a>
      </div>
      <div class="flex items-center justify-between text-xs text-gray-400 pt-1 border-t border-gray-100">
        <span>${escHtml(formatLocation(job.location_raw) || "—")}</span>
        <span>${timeSince(job.posted_date || job.first_seen)}</span>
      </div>
    </div>
  `;
}

function escHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function showLoading() {
  document.getElementById("loading").classList.remove("hidden");
  document.getElementById("jobs-grid").innerHTML = "";
  document.getElementById("empty-state").classList.add("hidden");
  document.getElementById("pagination").classList.add("hidden");
}

function hideLoading() {
  document.getElementById("loading").classList.add("hidden");
}

function updateResultsCount(total) {
  const el = document.getElementById("results-count");
  if (!el) return;
  el.textContent = total != null ? `${total.toLocaleString()} jobs found` : "";
}

function updatePagination(hasMore) {
  const pagination = document.getElementById("pagination");
  const prevBtn    = document.getElementById("pagination-prev");
  const nextBtn    = document.getElementById("pagination-next");
  const info       = document.getElementById("pagination-info");

  if (!pagination) return;

  // Show pagination only if there are multiple pages or we're past page 1
  if (state.currentPage === 1 && !hasMore) {
    pagination.classList.add("hidden");
    return;
  }

  pagination.classList.remove("hidden");
  info.textContent = `Page ${state.currentPage}`;
  prevBtn.disabled = state.currentPage <= 1;
  nextBtn.disabled = !hasMore;
}

// ── Dropdown filter pills ──────────────────────────────────────────────────────

const FP_PANELS = ["date", "worktype", "seniority"];

function closePanels(except) {
  FP_PANELS.forEach(name => {
    if (name !== except) document.getElementById(`fpp-${name}`)?.classList.remove("open");
  });
}

function togglePanel(name) {
  const panel = document.getElementById(`fpp-${name}`);
  const isOpen = panel.classList.contains("open");
  closePanels();
  if (!isOpen) panel.classList.add("open");
}

// Close when clicking outside a fp-wrap
document.addEventListener("click", (e) => {
  if (!e.target.closest(".fp-wrap")) closePanels();
});

// Pill toggle buttons
FP_PANELS.forEach(name => {
  document.getElementById(`fpbtn-${name}`)?.addEventListener("click", (e) => {
    e.stopPropagation();
    togglePanel(name);
  });
});

// ── Pill label updates ────────────────────────────────────────────────────────

const DATE_LABELS = {
  "7D": "Past week", "TODAY": "Past 24 hours", "30D": "Past month", "ALL": "Anytime",
};

function updatePillLabels() {
  // Date (multi-select checkboxes)
  const dateVals = getCheckedByName("date");
  let dateLbl = "Date posted";
  if (dateVals.length === 1) {
    dateLbl = DATE_LABELS[dateVals[0]] || "Date posted";
  } else if (dateVals.length > 1) {
    dateLbl = `Date (${dateVals.length})`;
  }
  document.getElementById("fplbl-date").textContent = dateLbl;
  // Active state: anything other than just "7D" checked
  const isDefaultDate = dateVals.length === 1 && dateVals[0] === "7D";
  document.getElementById("fpbtn-date").classList.toggle("active", !isDefaultDate && dateVals.length > 0);

  // Location (work type)
  const wtCount = getCheckedByName("work_type").length;
  document.getElementById("fplbl-worktype").textContent = wtCount > 0 ? `Type (${wtCount})` : "Type";
  document.getElementById("fpbtn-worktype").classList.toggle("active", wtCount > 0);

  // Experience
  const senCount = getCheckedByName("seniority").length;
  document.getElementById("fplbl-seniority").textContent = senCount > 0 ? `Experience (${senCount})` : "Experience";
  document.getElementById("fpbtn-seniority").classList.toggle("active", senCount > 0);
}

// ── Fetch & render jobs ────────────────────────────────────────────────────────

async function loadPage(cursor = null) {
  if (state.loading) return;
  state.loading = true;
  showLoading();

  try {
    const data = await apiFetch("/api/jobs", buildParams(cursor));

    const grid = document.getElementById("jobs-grid");
    const items = data.items || [];

    if (items.length === 0) {
      grid.innerHTML = "";
      document.getElementById("empty-state").classList.remove("hidden");
      updateResultsCount(data.total_hint);
      updatePagination(false);
    } else {
      grid.innerHTML = items.map(renderCard).join("");
      document.getElementById("empty-state").classList.add("hidden");
      state.hasMore = !!data.next_cursor;
      // Store cursor for "next" navigation
      state.cursorHistory[state.currentPage - 1] = data.next_cursor || null;
      updateResultsCount(data.total_hint);
      updatePagination(state.hasMore);
    }
  } catch (err) {
    document.getElementById("jobs-grid").innerHTML =
      `<div class="col-span-full text-center py-12 text-red-400 text-sm">Error loading jobs: ${escHtml(err.message)}</div>`;
  } finally {
    state.loading = false;
    hideLoading();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
}

async function loadJobs() {
  state.currentPage = 1;
  state.cursorHistory = [];
  state.hasMore = false;
  await loadPage(null);
}

// ── Event listeners ───────────────────────────────────────────────────────────

let debounceTimer;
function debounce(fn, ms = 400) {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(fn, ms);
}

// Checkbox filter changes
document.addEventListener("change", (e) => {
  const name = e.target.name;
  if (["date", "seniority", "work_type"].includes(name)) {
    updatePillLabels();
    loadJobs();
  }
});

// Pagination buttons
document.getElementById("pagination-next")?.addEventListener("click", () => {
  if (!state.hasMore || state.loading) return;
  const cursor = state.cursorHistory[state.currentPage - 1];
  state.currentPage += 1;
  loadPage(cursor);
});

document.getElementById("pagination-prev")?.addEventListener("click", () => {
  if (state.currentPage <= 1 || state.loading) return;
  state.currentPage -= 1;
  const cursor = state.currentPage > 1 ? state.cursorHistory[state.currentPage - 2] : null;
  loadPage(cursor);
});

// Text input filters with debounce + clear button visibility
["filter-keyword", "filter-city"].forEach(id => {
  const input = document.getElementById(id);
  if (!input) return;
  const clearId = id === "filter-keyword" ? "clear-keyword" : "clear-city";
  const clearBtn = document.getElementById(clearId);
  input.addEventListener("input", () => {
    if (clearBtn) clearBtn.style.display = input.value ? "block" : "none";
    debounce(loadJobs);
  });
});

function fpClearInput(field) {
  const input = document.getElementById("filter-" + field);
  const btn   = document.getElementById("clear-" + field);
  if (input) { input.value = ""; input.focus(); }
  if (btn)   btn.style.display = "none";
  debounce(resetAndLoad);
}

// ── Init ──────────────────────────────────────────────────────────────────────

updatePillLabels();
loadJobs();
