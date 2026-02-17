"""
Flask dashboard for monitoring SatoraXagent sessions.
"""

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Flask, jsonify, render_template

app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "templates"),
    static_folder=str(Path(__file__).parent / "static"),
)

LOG_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "session_log.json"


def _load_log() -> dict:
    if not LOG_PATH.exists():
        return {"sessions": []}
    with open(LOG_PATH, "r") as f:
        return json.load(f)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/sessions")
def api_sessions():
    """Return all session data."""
    log = _load_log()
    return jsonify(log)


@app.route("/api/daily-summary")
def api_daily_summary():
    """Return per-day aggregated stats."""
    log = _load_log()
    days: dict[str, dict] = defaultdict(lambda: {
        "date": "",
        "sessions": [],
        "total_follows": 0,
        "had_error": False,
        "error_details": [],
    })

    for session in log.get("sessions", []):
        d = session["date"]
        day = days[d]
        day["date"] = d
        day["sessions"].append({
            "session_number": session["session_number"],
            "started_at": session.get("started_at"),
            "ended_at": session.get("ended_at"),
            "status": session.get("status"),
            "follows": session.get("total_follows", 0),
            "error": session.get("error"),
            "profiles": session.get("profiles_visited", []),
        })
        day["total_follows"] += session.get("total_follows", 0)
        if session.get("status") not in ("completed", "running"):
            day["had_error"] = True
            if session.get("error"):
                day["error_details"].append({
                    "session": session["session_number"],
                    "status": session["status"],
                    "error": session["error"],
                })

    # Sort by date descending
    result = sorted(days.values(), key=lambda x: x["date"], reverse=True)
    return jsonify(result)


@app.route("/api/stats")
def api_stats():
    """Return high-level stats: today, this week, total."""
    log = _load_log()
    sessions = log.get("sessions", [])
    today_str = date.today().isoformat()

    today_follows = sum(
        s.get("total_follows", 0) for s in sessions if s["date"] == today_str
    )

    # This week (Monday to Sunday)
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    week_follows = sum(
        s.get("total_follows", 0)
        for s in sessions
        if s["date"] >= monday.isoformat()
    )

    total_follows = sum(s.get("total_follows", 0) for s in sessions)
    total_sessions = len(sessions)

    # Next scheduled session info
    today_sessions = [s for s in sessions if s["date"] == today_str]
    sessions_today_count = len(today_sessions)

    return jsonify({
        "today_follows": today_follows,
        "week_follows": week_follows,
        "total_follows": total_follows,
        "total_sessions": total_sessions,
        "sessions_today": sessions_today_count,
    })


def run_dashboard(host: str = "0.0.0.0", port: int = 5000):
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    run_dashboard()
