/**
 * PM Job Tracker — Frontend App
 * Calls the FastAPI backend and renders job cards.
 * API key is stored here for personal use only.
 * Replace with env-aware approach when migrating to Lovable.
 */

const API_KEY = window.__API_KEY__ || "dev-insecure-key";
const API_BASE = "";   // same origin; update to full URL when Lovable takes over
const FETCH_SIZE = 50;

// ── State ─────────────────────────────────────────────────────────────────────

const state = {
  nextCursor: null,
  hasMore: false,
  loading: false,
};

let scrollObserver = null;

// ── Helpers ───────────────────────────────────────────────────────────────────

function getCheckedByName(name) {
  return [...document.querySelectorAll(`input[name="${name}"]:checked`)].map(el => el.value);
}

function getRadioValue(name) {
  return document.querySelector(`input[name="${name}"]:checked`)?.value || "";
}

function buildParams(cursor = null) {
  const keyword   = document.getElementById("filter-keyword").value.trim();
  const rawCity   = document.getElementById("filter-city").value.trim();
  const dateVal   = getRadioValue("date") || "7D";
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
  p.set("limit", FETCH_SIZE);
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

// Display-only normalisation of location_raw (for card rendering)
function normalizeLocationCity(raw) {
  if (!raw) return null;
  const lower = raw.toLowerCase().trim();
  const cityPart = lower.split(",")[0].trim();
  if (LOCATION_ALIAS[cityPart]) {
    const rest = raw.includes(",") ? raw.substring(raw.indexOf(",")) : "";
    return LOCATION_ALIAS[cityPart] + rest;
  }
  for (const [alias, en] of Object.entries(LOCATION_ALIAS)) {
    if (lower.includes(alias)) return raw.replace(new RegExp(alias, "gi"), en);
  }
  return raw;
}

function timeSince(isoString) {
  const diff = Date.now() - new Date(isoString).getTime();
  const h = Math.floor(diff / 3600000);
  const d = Math.floor(h / 24);
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
          <h3 class="font-semibold text-gray-900 text-sm leading-snug truncate" title="${escHtml(job.title)}">${escHtml(job.title)}</h3>
          <p class="text-gray-500 text-xs mt-0.5 truncate">${escHtml(job.company_name)}</p>
        </div>
        <a href="${escHtml(job.url)}" target="_blank" rel="noopener noreferrer" class="btn-apply flex-shrink-0">
          Apply &#8599;
        </a>
      </div>
      <div class="flex items-center justify-between text-xs text-gray-400 pt-1 border-t border-gray-100">
        <span>${escHtml(normalizeLocationCity(job.location_raw) || "—")}</span>
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
}

function hideLoading() {
  document.getElementById("loading").classList.add("hidden");
}

function showLoadingMore() {
  document.getElementById("loading-more").classList.remove("hidden");
}

function hideLoadingMore() {
  document.getElementById("loading-more").classList.add("hidden");
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
  // Date
  const dateVal = getRadioValue("date") || "7D";
  document.getElementById("fplbl-date").textContent = DATE_LABELS[dateVal] || "Date posted";
  document.getElementById("fpbtn-date").classList.toggle("active", dateVal !== "7D");

  // Location (work type)
  const wtCount = getCheckedByName("work_type").length;
  document.getElementById("fplbl-worktype").textContent = wtCount > 0 ? `Location (${wtCount})` : "Location";
  document.getElementById("fpbtn-worktype").classList.toggle("active", wtCount > 0);

  // Experience
  const senCount = getCheckedByName("seniority").length;
  document.getElementById("fplbl-seniority").textContent = senCount > 0 ? `Experience (${senCount})` : "Experience";
  document.getElementById("fpbtn-seniority").classList.toggle("active", senCount > 0);
}

// ── Scroll observer ────────────────────────────────────────────────────────────

function setupScrollObserver() {
  if (scrollObserver) scrollObserver.disconnect();
  const sentinel = document.getElementById("scroll-sentinel");
  if (!sentinel) return;
  scrollObserver = new IntersectionObserver(
    (entries) => {
      if (entries[0].isIntersecting && state.hasMore && !state.loading) {
        appendJobs();
      }
    },
    { rootMargin: "300px" }
  );
  scrollObserver.observe(sentinel);
}

// ── Fetch & render jobs ────────────────────────────────────────────────────────

async function loadJobs() {
  if (state.loading) return;
  state.loading = true;
  state.nextCursor = null;
  state.hasMore = false;
  showLoading();

  try {
    const data = await apiFetch("/api/jobs", buildParams());

    const grid = document.getElementById("jobs-grid");
    const items = data.items || [];

    if (items.length === 0) {
      grid.innerHTML = "";
      document.getElementById("empty-state").classList.remove("hidden");
    } else {
      grid.innerHTML = items.map(renderCard).join("");
      document.getElementById("empty-state").classList.add("hidden");
      state.nextCursor = data.next_cursor || null;
      state.hasMore = !!data.next_cursor;
      setupScrollObserver();
    }
  } catch (err) {
    document.getElementById("jobs-grid").innerHTML =
      `<div class="col-span-full text-center py-12 text-red-400 text-sm">Error loading jobs: ${escHtml(err.message)}</div>`;
  } finally {
    state.loading = false;
    hideLoading();
  }
}

async function appendJobs() {
  if (state.loading || !state.nextCursor) return;
  state.loading = true;
  showLoadingMore();

  try {
    const data = await apiFetch("/api/jobs", buildParams(state.nextCursor));
    const items = data.items || [];

    if (items.length > 0) {
      const grid = document.getElementById("jobs-grid");
      grid.insertAdjacentHTML("beforeend", items.map(renderCard).join(""));
    }

    state.nextCursor = data.next_cursor || null;
    state.hasMore = !!data.next_cursor;

    if (!state.hasMore && scrollObserver) {
      scrollObserver.disconnect();
    }
  } catch (err) {
    console.error("Failed to load more jobs:", err);
  } finally {
    state.loading = false;
    hideLoadingMore();
  }
}

// ── Event listeners ───────────────────────────────────────────────────────────

let debounceTimer;
function debounce(fn, ms = 400) {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(fn, ms);
}

function resetAndLoad() {
  state.nextCursor = null;
  state.hasMore = false;
  loadJobs();
}

// Radio/checkbox filter changes
document.addEventListener("change", (e) => {
  const name = e.target.name;
  if (["date", "seniority", "work_type"].includes(name)) {
    updatePillLabels();
    resetAndLoad();
    if (e.target.type === "radio") closePanels();
  }
});

// Text input filters with debounce
["filter-keyword", "filter-city"].forEach(id => {
  document.getElementById(id)?.addEventListener("input", () => debounce(resetAndLoad));
});

// Reset button
document.getElementById("btn-reset").addEventListener("click", () => {
  document.querySelectorAll('input[name="seniority"], input[name="work_type"]').forEach(el => el.checked = false);
  const defaultDate = document.querySelector('input[name="date"][value="7D"]');
  if (defaultDate) defaultDate.checked = true;
  document.getElementById("filter-keyword").value = "";
  document.getElementById("filter-city").value = "";
  closePanels();
  updatePillLabels();
  resetAndLoad();
});

// ── Init ──────────────────────────────────────────────────────────────────────

updatePillLabels();
loadJobs();
