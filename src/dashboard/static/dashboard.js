// SatoraXagent Dashboard

const API = {
    stats: "/api/stats",
    daily: "/api/daily-summary",
    sessions: "/api/sessions",
};

// ---- Helpers ----

function formatTime(isoString) {
    if (!isoString) return "-";
    const d = new Date(isoString);
    return d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function formatDate(dateStr) {
    if (!dateStr) return "-";
    const d = new Date(dateStr + "T00:00:00");
    return d.toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" });
}

function statusBadge(status) {
    const map = {
        completed: "badge-completed",
        rate_limited: "badge-rate-limited",
        captcha_blocked: "badge-captcha",
        error: "badge-error",
        running: "badge-running",
    };
    const cls = map[status] || "badge-error";
    const label = status.replace(/_/g, " ");
    return `<span class="badge ${cls}">${label}</span>`;
}

// ---- Stats cards ----

async function loadStats() {
    try {
        const res = await fetch(API.stats);
        const data = await res.json();
        document.getElementById("stat-today").textContent = data.today_follows;
        document.getElementById("stat-week").textContent = data.week_follows;
        document.getElementById("stat-total").textContent = data.total_follows;
        document.getElementById("stat-sessions").textContent = data.sessions_today;
    } catch (e) {
        console.error("Failed to load stats:", e);
    }
}

// ---- Daily chart ----

let chartInstance = null;

async function loadChart() {
    try {
        const res = await fetch(API.daily);
        const days = await res.json();

        // Take last 30 days, sorted ascending
        const sorted = days.slice(0, 30).reverse();

        const labels = sorted.map(d => formatDate(d.date));

        // Split follows by session number
        const session1 = sorted.map(d => {
            const s = d.sessions.find(s => s.session_number === 1);
            return s ? s.follows : 0;
        });
        const session2 = sorted.map(d => {
            const s = d.sessions.find(s => s.session_number === 2);
            return s ? s.follows : 0;
        });

        const ctx = document.getElementById("dailyChart").getContext("2d");

        if (chartInstance) chartInstance.destroy();

        chartInstance = new Chart(ctx, {
            type: "bar",
            data: {
                labels,
                datasets: [
                    {
                        label: "Session 1",
                        data: session1,
                        backgroundColor: "rgba(29, 155, 240, 0.7)",
                        borderRadius: 4,
                    },
                    {
                        label: "Session 2",
                        data: session2,
                        backgroundColor: "rgba(171, 71, 188, 0.7)",
                        borderRadius: 4,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        labels: { color: "#8888aa" },
                    },
                },
                scales: {
                    x: {
                        stacked: true,
                        ticks: { color: "#8888aa", maxRotation: 45 },
                        grid: { color: "rgba(42, 42, 74, 0.5)" },
                    },
                    y: {
                        stacked: true,
                        beginAtZero: true,
                        ticks: { color: "#8888aa", stepSize: 1 },
                        grid: { color: "rgba(42, 42, 74, 0.5)" },
                    },
                },
            },
        });
    } catch (e) {
        console.error("Failed to load chart:", e);
    }
}

// ---- Session table ----

async function loadTable() {
    try {
        const res = await fetch(API.daily);
        const days = await res.json();

        const tbody = document.querySelector("#session-table tbody");
        tbody.innerHTML = "";

        if (days.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No sessions recorded yet.</td></tr>';
            return;
        }

        for (const day of days) {
            for (const session of day.sessions) {
                const tr = document.createElement("tr");

                const details = session.error
                    ? session.error
                    : session.profiles.map(p => `@${p.handle}: ${p.follow_count} follows`).join(", ");

                tr.innerHTML = `
                    <td>${formatDate(day.date)}</td>
                    <td>#${session.session_number}</td>
                    <td>${formatTime(session.started_at)}</td>
                    <td>${formatTime(session.ended_at)}</td>
                    <td><strong>${session.follows}</strong></td>
                    <td>${statusBadge(session.status)}</td>
                    <td title="${details}">${truncate(details, 60)}</td>
                `;
                tbody.appendChild(tr);
            }
        }
    } catch (e) {
        console.error("Failed to load table:", e);
    }
}

function truncate(str, max) {
    if (!str) return "-";
    return str.length > max ? str.substring(0, max) + "..." : str;
}

// ---- Event log ----

async function loadEventLog() {
    try {
        const res = await fetch(API.sessions);
        const data = await res.json();
        const sessions = data.sessions || [];

        const container = document.getElementById("event-log");
        container.innerHTML = "";

        if (sessions.length === 0) {
            container.innerHTML = '<div class="empty-state">No events yet. Start the agent to see activity here.</div>';
            return;
        }

        // Build flat event list from sessions (most recent first)
        const events = [];

        for (const session of sessions.slice().reverse()) {
            events.push({
                time: session.started_at,
                type: "session",
                message: `Session #${session.session_number} started`,
            });

            for (const profile of session.profiles_visited || []) {
                for (const user of profile.follows || []) {
                    events.push({
                        time: session.started_at,
                        type: "follow",
                        message: `Followed @${user} (from @${profile.handle})`,
                    });
                }
                for (const user of profile.skipped || []) {
                    events.push({
                        time: session.started_at,
                        type: "skip",
                        message: `Skipped @${user} (already following, from @${profile.handle})`,
                    });
                }
            }

            if (session.error) {
                const type = session.status === "rate_limited" ? "rate-limit" : "error";
                events.push({
                    time: session.ended_at || session.started_at,
                    type,
                    message: session.error,
                });
            }

            events.push({
                time: session.ended_at || session.started_at,
                type: "session",
                message: `Session #${session.session_number} ended — ${session.status} (${session.total_follows} follows)`,
            });
        }

        // Show last 100 events
        for (const ev of events.slice(0, 100)) {
            const div = document.createElement("div");
            div.className = "log-entry";
            div.innerHTML = `
                <span class="log-time">${formatTime(ev.time)}</span>
                <span class="log-type log-type-${ev.type}">${ev.type.toUpperCase()}</span>
                <span class="log-message">${ev.message}</span>
            `;
            container.appendChild(div);
        }
    } catch (e) {
        console.error("Failed to load event log:", e);
    }
}

// ---- Run Now ----

let _runOncePolling = null;

async function triggerRunOnce() {
    const btn = document.getElementById("run-now-btn");
    btn.disabled = true;
    btn.className = "btn-run running";
    btn.textContent = "Starting...";

    try {
        const secret = localStorage.getItem("webhook_secret") || "";
        const res = await fetch("/api/run-once" + (secret ? `?secret=${encodeURIComponent(secret)}` : ""), {
            method: "POST",
        });
        const data = await res.json();

        if (res.status === 403) {
            // Need secret — prompt user
            const input = prompt("Enter WEBHOOK_SECRET to authorize:");
            if (input) {
                localStorage.setItem("webhook_secret", input);
                btn.disabled = false;
                btn.className = "btn-run";
                btn.textContent = "Run Now";
                return triggerRunOnce();
            }
            btn.className = "btn-run error";
            btn.textContent = "Unauthorized";
            setTimeout(() => resetRunBtn(), 3000);
            return;
        }

        if (res.status === 409) {
            btn.className = "btn-run running";
            btn.textContent = "Already running...";
            startPollingRunOnce();
            return;
        }

        if (!res.ok) {
            btn.className = "btn-run error";
            btn.textContent = "Error";
            setTimeout(() => resetRunBtn(), 3000);
            return;
        }

        btn.textContent = "Running...";
        startPollingRunOnce();
    } catch (e) {
        console.error("Run-once failed:", e);
        btn.className = "btn-run error";
        btn.textContent = "Error";
        setTimeout(() => resetRunBtn(), 3000);
    }
}

function startPollingRunOnce() {
    if (_runOncePolling) return;
    _runOncePolling = setInterval(async () => {
        try {
            const res = await fetch("/api/run-once/status");
            const data = await res.json();

            const btn = document.getElementById("run-now-btn");

            if (data.status === "finished") {
                clearInterval(_runOncePolling);
                _runOncePolling = null;

                if (data.exit_code === 0) {
                    btn.className = "btn-run success";
                    btn.textContent = "Done!";
                } else {
                    btn.className = "btn-run error";
                    btn.textContent = "Failed (exit " + data.exit_code + ")";
                }
                refresh();
                setTimeout(() => resetRunBtn(), 5000);
            }
        } catch (e) {
            console.error("Polling error:", e);
        }
    }, 3000);
}

function resetRunBtn() {
    const btn = document.getElementById("run-now-btn");
    btn.disabled = false;
    btn.className = "btn-run";
    btn.textContent = "Run Now";
}

// ---- Init ----

async function refresh() {
    await Promise.all([loadStats(), loadChart(), loadTable(), loadEventLog()]);
}

document.addEventListener("DOMContentLoaded", () => {
    refresh();
    // Auto-refresh every 30 seconds
    setInterval(refresh, 30000);

    // Check if a run-once is already running on load
    fetch("/api/run-once/status").then(r => r.json()).then(data => {
        if (data.status === "running") {
            const btn = document.getElementById("run-now-btn");
            btn.disabled = true;
            btn.className = "btn-run running";
            btn.textContent = "Running...";
            startPollingRunOnce();
        }
    }).catch(() => {});
});
