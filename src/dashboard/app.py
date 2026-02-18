"""
Flask dashboard for monitoring SatoraXagent sessions.
"""

import json
import logging
import os
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Flask, jsonify, render_template, request

app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "templates"),
    static_folder=str(Path(__file__).parent / "static"),
)

logger = logging.getLogger(__name__)

LOG_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "session_log.json"
REPO_DIR = Path(__file__).resolve().parent.parent.parent

# Track in-flight run-once process
_run_once_proc: subprocess.Popen | None = None


def _load_log() -> dict:
    if not LOG_PATH.exists():
        return {"sessions": []}
    with open(LOG_PATH, "r") as f:
        return json.load(f)


def _check_secret(req) -> bool:
    """Validate WEBHOOK_SECRET from header or query param."""
    secret = os.environ.get("WEBHOOK_SECRET", "")
    if not secret:
        return True  # no secret configured — allow all
    provided = req.headers.get("X-Webhook-Secret") or req.args.get("secret", "")
    return provided == secret


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


@app.route("/api/health")
def api_health():
    """Health check: is the service up, last session info, bot process alive."""
    log = _load_log()
    sessions = log.get("sessions", [])

    last_session = sessions[-1] if sessions else None

    # Check if satora-bot systemd service is active
    bot_active = False
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "satora-bot"],
            capture_output=True, text=True, timeout=5,
        )
        bot_active = result.stdout.strip() == "active"
    except Exception:
        pass

    return jsonify({
        "status": "ok",
        "bot_active": bot_active,
        "total_sessions": len(sessions),
        "last_session": {
            "date": last_session["date"],
            "status": last_session["status"],
            "total_follows": last_session.get("total_follows", 0),
            "ended_at": last_session.get("ended_at"),
        } if last_session else None,
    })


@app.route("/api/update-env", methods=["POST"])
def api_update_env():
    """Update /root/.env-bot with new values and restart the dashboard.

    Requires current WEBHOOK_SECRET for auth. Accepts JSON body with
    key-value pairs to write into .env-bot.
    """
    if not _check_secret(request):
        return jsonify({"error": "Invalid or missing WEBHOOK_SECRET"}), 403

    new_vars = request.get_json(silent=True)
    if not new_vars or not isinstance(new_vars, dict):
        return jsonify({"error": "Expected JSON object with env vars"}), 400

    env_path = Path("/root/.env-bot")
    if not env_path.exists():
        return jsonify({"error": "/root/.env-bot not found"}), 500

    # Read existing env, update with new values
    existing = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            key, _, val = line.partition("=")
            existing[key.strip()] = val.strip()

    existing.update(new_vars)

    # Write back
    env_path.write_text(
        "\n".join(f"{k}={v}" for k, v in existing.items()) + "\n"
    )

    logger.info("Updated .env-bot with keys: %s", list(new_vars.keys()))
    return jsonify({"message": "Updated. Restart dashboard to apply.", "updated_keys": list(new_vars.keys())}), 200


@app.route("/api/run-once", methods=["POST"])
def api_run_once():
    """Trigger a single follow session in a background subprocess."""
    global _run_once_proc

    if not _check_secret(request):
        return jsonify({"error": "Invalid or missing WEBHOOK_SECRET"}), 403

    # Check if a run-once is already in progress
    if _run_once_proc is not None and _run_once_proc.poll() is None:
        return jsonify({"error": "A session is already running", "pid": _run_once_proc.pid}), 409

    # Spawn run-once as a subprocess
    venv_python = REPO_DIR / "venv" / "bin" / "python"
    python_bin = str(venv_python) if venv_python.exists() else sys.executable

    env = {**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":99")}

    # Use xvfb-run if available (headless server needs a virtual display)
    cmd = [python_bin, "-m", "src.main", "run-once"]
    xvfb = "/usr/bin/xvfb-run"
    if Path(xvfb).exists():
        cmd = [xvfb] + cmd

    _run_once_proc = subprocess.Popen(
        cmd,
        cwd=str(REPO_DIR),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    logger.info("run-once session started (PID %d)", _run_once_proc.pid)
    return jsonify({"message": "Session started", "pid": _run_once_proc.pid}), 202


@app.route("/api/run-once/status")
def api_run_once_status():
    """Check the status of the last run-once invocation."""
    if _run_once_proc is None:
        return jsonify({"status": "idle"})

    poll = _run_once_proc.poll()
    if poll is None:
        return jsonify({"status": "running", "pid": _run_once_proc.pid})

    return jsonify({"status": "finished", "exit_code": poll, "pid": _run_once_proc.pid})


def run_dashboard(host: str = "0.0.0.0", port: int = 5000):
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    run_dashboard()
