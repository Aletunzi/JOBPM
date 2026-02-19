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
  newOnly: false,
  loading: false,
};

let scrollObserver = null;

// ── Helpers ───────────────────────────────────────────────────────────────────

function getChecked(containerId) {
  return [...document.querySelectorAll(`#${containerId} input:checked`)]
    .map(el => el.value);
}

function buildParams(cursor = null) {
  const continent = document.getElementById("filter-continent").value;
  const seniority = getChecked("filter-seniority");
  const vertical = getChecked("filter-vertical");
  const keyword = document.getElementById("filter-keyword").value.trim();
  const city = document.getElementById("filter-city").value.trim();
  const country = document.getElementById("filter-country").value.trim();
  const date = document.getElementById("filter-date").value;

  // mobile overrides (if sidebar hidden)
  const continentMobile = document.getElementById("filter-continent-mobile").value;
  const dateMobile = document.getElementById("filter-date-mobile").value;
  const keywordMobile = document.getElementById("filter-keyword-mobile").value.trim();

  const p = new URLSearchParams();
  const geoFinal = continent || continentMobile || null;
  if (geoFinal) p.set("geo", geoFinal);
  if (seniority.length) p.set("seniority", seniority.join(","));
  if (vertical.length) p.set("vertical", vertical.join(","));
  const kw = keyword || keywordMobile;
  if (kw) p.set("keyword", kw);
  if (city) p.set("city", city);
  if (country) p.set("country", country);
  const dateFinal = date !== "ALL" ? date : (dateMobile !== "ALL" ? dateMobile : null);
  if (dateFinal) p.set("date", dateFinal);
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
    document.getElementById("stat-total").innerHTML =
      `<span class="w-2 h-2 rounded-full bg-green-400 inline-block"></span> ${stats.total_active.toLocaleString()} active jobs`;
    if (stats.new_today > 0) {
      document.getElementById("stat-new").textContent = `+${stats.new_today} new today`;
    }
    if (stats.last_scraped) {
      const d = new Date(stats.last_scraped);
      document.getElementById("stat-scraped").textContent =
        `Last updated: ${d.toLocaleDateString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}`;
      document.getElementById("stat-scraped").classList.remove("hidden");
    }
  } catch {
    document.getElementById("stat-total").textContent = "—";
  }
}

// ── Rendering ─────────────────────────────────────────────────────────────────

const GEO_LABELS = { EU: "Europe", US: "USA", UK: "UK", REMOTE: "Remote", APAC: "APAC", LATAM: "LATAM", OTHER: "Other" };
const SENIORITY_COLORS = {
  JUNIOR: "bg-purple-100 text-purple-700",
  MID: "bg-gray-100 text-gray-600",
  SENIOR: "bg-blue-100 text-blue-700",
  STAFF: "bg-indigo-100 text-indigo-700",
  LEAD: "bg-orange-100 text-orange-700",
  LEADERSHIP: "bg-red-100 text-red-700",
  INTERN: "bg-pink-100 text-pink-700",
};

function geoBadge(geo) {
  const cls = geo === "REMOTE" ? "badge badge-remote" : "badge badge-geo";
  return `<span class="${cls}">${GEO_LABELS[geo] || geo}</span>`;
}

function seniorityBadge(sen) {
  const cls = SENIORITY_COLORS[sen] || "bg-gray-100 text-gray-500";
  return `<span class="badge ${cls}">${sen}</span>`;
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
      <div class="flex flex-wrap items-center gap-1.5">
        ${geoBadge(job.geo_region)}
        ${seniorityBadge(job.seniority)}
      </div>
      <div class="flex items-center justify-between text-xs text-gray-400 pt-1 border-t border-gray-100">
        <span>${job.location_raw ? escHtml(job.location_raw) : "—"}</span>
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
    let data;
    if (state.newOnly) {
      const continent = document.getElementById("filter-continent").value;
      const seniority = getChecked("filter-seniority").join(",") || null;
      const p = new URLSearchParams();
      if (continent) p.set("geo", continent);
      if (seniority) p.set("seniority", seniority);
      p.set("limit", 100);
      data = await apiFetch("/api/jobs/new", p);
    } else {
      data = await apiFetch("/api/jobs", buildParams());
    }

    const grid = document.getElementById("jobs-grid");
    const items = data.items || [];

    if (items.length === 0) {
      grid.innerHTML = "";
      document.getElementById("empty-state").classList.remove("hidden");
      document.getElementById("results-count").textContent = "No results";
    } else {
      grid.innerHTML = items.map(renderCard).join("");
      document.getElementById("empty-state").classList.add("hidden");
      document.getElementById("results-count").textContent =
        `${items.length} job${items.length !== 1 ? "s" : ""}`;

      state.nextCursor = data.next_cursor || null;
      state.hasMore = !!data.next_cursor;
      setupScrollObserver();
    }
  } catch (err) {
    document.getElementById("jobs-grid").innerHTML =
      `<div class="col-span-full text-center py-12 text-red-400 text-sm">Error loading jobs: ${escHtml(err.message)}</div>`;
    document.getElementById("results-count").textContent = "Error";
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

      const total = grid.querySelectorAll(".job-card").length;
      document.getElementById("results-count").textContent =
        `${total} job${total !== 1 ? "s" : ""}`;
    }

    state.nextCursor = data.next_cursor || null;
    state.hasMore = !!data.next_cursor;

    if (!state.hasMore && scrollObserver) {
      scrollObserver.disconnect();
    }
  } catch (err) {
    // silently fail on append — user can scroll up and retry
    console.error("Failed to load more jobs:", err);
  } finally {
    state.loading = false;
    hideLoadingMore();
  }
}

// ── New only toggle ────────────────────────────────────────────────────────────

document.getElementById("btn-new-only").addEventListener("click", () => {
  state.newOnly = !state.newOnly;
  document.getElementById("btn-new-only").classList.toggle("active", state.newOnly);
  resetAndLoad();
});

// ── Filters ───────────────────────────────────────────────────────────────────

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

// Checkbox filters
["filter-seniority", "filter-vertical"].forEach(id => {
  document.getElementById(id).addEventListener("change", resetAndLoad);
});

// Select filters
["filter-continent", "filter-date", "filter-continent-mobile", "filter-date-mobile"].forEach(id => {
  document.getElementById(id).addEventListener("change", resetAndLoad);
});

// Text inputs with debounce
["filter-keyword", "filter-keyword-mobile", "filter-city", "filter-country"].forEach(id => {
  document.getElementById(id).addEventListener("input", () => debounce(resetAndLoad));
});

// Reset button
document.getElementById("btn-reset").addEventListener("click", () => {
  document.querySelectorAll(".filter-check input").forEach(el => el.checked = false);
  document.getElementById("filter-keyword").value = "";
  document.getElementById("filter-city").value = "";
  document.getElementById("filter-country").value = "";
  document.getElementById("filter-continent").value = "";
  document.getElementById("filter-date").value = "7D";
  state.newOnly = false;
  document.getElementById("btn-new-only").classList.remove("active");
  resetAndLoad();
});

// ── Init ──────────────────────────────────────────────────────────────────────

loadStats();
loadJobs();
