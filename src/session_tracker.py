"""
Session tracker: reads/writes session_log.json and enforces daily limits.
"""

import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "session_log.json"


def _ensure_log_file() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not LOG_PATH.exists():
        LOG_PATH.write_text(json.dumps({"sessions": []}, indent=2))


def load_log() -> dict:
    _ensure_log_file()
    with open(LOG_PATH, "r") as f:
        return json.load(f)


def save_log(data: dict) -> None:
    _ensure_log_file()
    with open(LOG_PATH, "w") as f:
        json.dump(data, f, indent=2, default=str)


def sessions_today(log: dict | None = None) -> list[dict]:
    """Return all sessions for today."""
    if log is None:
        log = load_log()
    today = date.today().isoformat()
    return [s for s in log["sessions"] if s["date"] == today]


def can_run_session(max_per_day: int = 2) -> bool:
    """Check if we can still run a session today."""
    return len(sessions_today()) < max_per_day


def next_session_number() -> int:
    """Return the session number for the next session today (1-based)."""
    return len(sessions_today()) + 1


class SessionRecord:
    """Accumulates data for a single session, then persists it."""

    def __init__(self):
        self.date = date.today().isoformat()
        self.session_number = next_session_number()
        self.started_at = datetime.now().isoformat()
        self.ended_at: str | None = None
        self.status = "running"
        self.profiles_visited: list[dict] = []
        self.total_follows = 0
        self.error: str | None = None
        self._current_profile: dict | None = None

    def start_profile(self, handle: str) -> None:
        self._current_profile = {
            "handle": handle,
            "follows": [],
            "skipped": [],
            "follow_count": 0,
        }

    def record_follow(self, username: str) -> None:
        if self._current_profile is not None:
            self._current_profile["follows"].append(username)
            self._current_profile["follow_count"] += 1
        self.total_follows += 1

    def record_skip(self, username: str) -> None:
        if self._current_profile is not None:
            self._current_profile["skipped"].append(username)

    def finish_profile(self) -> None:
        if self._current_profile is not None:
            self.profiles_visited.append(self._current_profile)
            self._current_profile = None

    def finish(self, status: str = "completed", error: str | None = None) -> None:
        # Flush any in-progress profile
        if self._current_profile is not None:
            self.finish_profile()
        self.ended_at = datetime.now().isoformat()
        self.status = status
        self.error = error
        self._persist()

    def _persist(self) -> None:
        log = load_log()
        log["sessions"].append(self.to_dict())
        save_log(log)
        logger.info(
            "Session %s saved — status=%s, total_follows=%d",
            self.session_number,
            self.status,
            self.total_follows,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "session_number": self.session_number,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "status": self.status,
            "profiles_visited": self.profiles_visited,
            "total_follows": self.total_follows,
            "error": self.error,
        }
