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
  const city      = document.getElementById("filter-city").value.trim();
  const dateVal   = getRadioValue("date") || "7D";
  const seniority = getCheckedByName("seniority");
  const workType  = getCheckedByName("work_type");

  const p = new URLSearchParams();
  if (seniority.length) p.set("seniority", seniority.join(","));
  if (workType.length)  p.set("work_type", workType.join(","));
  if (keyword)          p.set("keyword",   keyword);
  if (city)             p.set("city",      city);
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

// ── Stats bar ─────────────────────────────────────────────────────────────────

async function loadStats() {
  try {
    const stats = await apiFetch("/api/stats");
    if (stats.last_scraped) {
      const d = new Date(stats.last_scraped);
      document.getElementById("stat-scraped").textContent =
        `Last updated: ${d.toLocaleDateString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}`;
      document.getElementById("stat-scraped").classList.remove("hidden");
    }
  } catch { /* stats are decorative */ }
}

// ── Rendering ─────────────────────────────────────────────────────────────────

// City name normalisation — maps non-English variants to English
const CITY_NAME_EN = {
  "münchen": "Munich",     "muenchen": "Munich",
  "köln": "Cologne",       "koeln": "Cologne",
  "düsseldorf": "Dusseldorf",
  "nürnberg": "Nuremberg", "nuernberg": "Nuremberg",
  "frankfurt am main": "Frankfurt",
  "wien": "Vienna",
  "zürich": "Zurich",      "zuerich": "Zurich",
  "genève": "Geneva",      "geneve": "Geneva",      "genf": "Geneva",
  "milano": "Milan",       "roma": "Rome",          "firenze": "Florence",
  "torino": "Turin",       "napoli": "Naples",      "venezia": "Venice",
  "berlino": "Berlin",     "amburgo": "Hamburg",
  "varsavia": "Warsaw",    "praga": "Prague",
  "barcellona": "Barcelona", "siviglia": "Seville",
  "lisbona": "Lisbon",
  "bruxelles": "Brussels", "brüssel": "Brussels",   "brussel": "Brussels",
  "københavn": "Copenhagen", "kobenhavn": "Copenhagen", "copenhague": "Copenhagen",
  "göteborg": "Gothenburg",  "goteborg": "Gothenburg",
  "stoccolma": "Stockholm",
  "mosca": "Moscow",       "moskau": "Moscow",      "moscou": "Moscow",  "moscú": "Moscow",
};

function normalizeLocationCity(raw) {
  if (!raw) return null;
  const lower = raw.toLowerCase().trim();
  const cityPart = lower.split(",")[0].trim();
  if (CITY_NAME_EN[cityPart]) {
    const rest = raw.includes(",") ? raw.substring(raw.indexOf(",")) : "";
    return CITY_NAME_EN[cityPart] + rest;
  }
  for (const [nonEn, en] of Object.entries(CITY_NAME_EN)) {
    if (lower.includes(nonEn)) {
      return raw.replace(new RegExp(nonEn, "i"), en);
    }
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
        <span>${timeSince(job.first_seen)}</span>
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
loadStats();
loadJobs();
