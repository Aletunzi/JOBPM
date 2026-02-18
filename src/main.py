"""
Entry point: schedules and runs follow sessions with APScheduler.
"""

import asyncio
import logging
import os
import random
import re
import signal
import sys
import threading
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from src.actions import RateLimitError, CaptchaError, run_session
from src.browser import BrowserManager, load_config
from src.session_tracker import SessionRecord, can_run_session


class CredentialMaskingFilter(logging.Filter):
    """Scrub sensitive values from log records before they are emitted."""

    def __init__(self):
        super().__init__()
        self._patterns: list[re.Pattern] = []
        for key in ("X_PASSWORD", "X_EMAIL", "X_USERNAME"):
            val = os.environ.get(key, "")
            if val and len(val) >= 3:
                self._patterns.append(re.compile(re.escape(val)))

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for pat in self._patterns:
            msg = pat.sub("***REDACTED***", msg)
        record.msg = msg
        record.args = None
        return True


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/agent.log"),
    ],
)

# Install credential masking on all handlers
_mask_filter = CredentialMaskingFilter()
for handler in logging.root.handlers:
    handler.addFilter(_mask_filter)

logger = logging.getLogger(__name__)


def _random_time_in_window(window_start: str, window_end: str) -> datetime:
    """Pick a random datetime today within the given HH:MM window."""
    today = datetime.now().date()
    start = datetime.combine(today, datetime.strptime(window_start, "%H:%M").time())
    end = datetime.combine(today, datetime.strptime(window_end, "%H:%M").time())
    delta_seconds = int((end - start).total_seconds())
    offset = random.randint(0, max(delta_seconds, 0))
    chosen = start + timedelta(seconds=offset)

    # If the chosen time is already past, don't schedule it
    if chosen < datetime.now():
        return None
    return chosen


async def execute_session(config: dict) -> None:
    """Run a single follow session."""
    limits = config.get("limits", {})
    max_sessions = limits.get("max_sessions_per_day", 2)

    if not can_run_session(max_sessions):
        logger.info("Already reached %d sessions today — skipping.", max_sessions)
        return

    record = SessionRecord()
    logger.info("Starting session #%d", record.session_number)

    try:
        async with BrowserManager(config) as bm:
            page = await bm.page()
            await run_session(page, config, record)
    except RateLimitError as e:
        logger.warning("Session stopped due to rate limit: %s", e)
        # record.finish() already called inside run_session
    except CaptchaError as e:
        logger.warning("Session stopped due to captcha: %s", e)
    except Exception as e:
        logger.error("Session failed with unexpected error: %s", e, exc_info=True)
        if record.status == "running":
            record.finish(status="error", error=str(e))


def schedule_sessions(scheduler: AsyncIOScheduler, config: dict) -> None:
    """Schedule today's sessions at random times within configured windows."""
    schedule_cfg = config.get("schedule", {})

    for key in ("session_1", "session_2"):
        window = schedule_cfg.get(key, {})
        start = window.get("window_start", "09:00")
        end = window.get("window_end", "21:00")

        run_at = _random_time_in_window(start, end)
        if run_at is None:
            logger.info("Window for %s already passed today — skipping.", key)
            continue

        scheduler.add_job(
            execute_session,
            trigger=DateTrigger(run_date=run_at),
            args=[config],
            id=f"{key}_{datetime.now().date().isoformat()}",
            replace_existing=True,
        )
        logger.info("Scheduled %s at %s", key, run_at.strftime("%H:%M:%S"))


async def reschedule_daily(scheduler: AsyncIOScheduler, config: dict) -> None:
    """Every day at midnight, schedule the next day's sessions."""
    while True:
        now = datetime.now()
        tomorrow_midnight = datetime.combine(
            now.date() + timedelta(days=1),
            datetime.strptime("00:01", "%H:%M").time(),
        )
        wait_seconds = (tomorrow_midnight - now).total_seconds()
        logger.info("Next reschedule in %.0f seconds (at %s)", wait_seconds, tomorrow_midnight)
        await asyncio.sleep(wait_seconds)
        schedule_sessions(scheduler, config)


def _start_dashboard(config: dict) -> None:
    """Start the Flask dashboard in a background thread."""
    from src.dashboard.app import app

    dash_cfg = config.get("dashboard", {})
    host = dash_cfg.get("host", "0.0.0.0")
    port = int(dash_cfg.get("port", 5000))

    thread = threading.Thread(
        target=app.run,
        kwargs={"host": host, "port": port, "debug": False},
        daemon=True,
    )
    thread.start()
    logger.info("Dashboard running on http://%s:%d", host, port)


async def main() -> None:
    config = load_config()

    # Launch dashboard in background thread (skip if running as separate service)
    if not os.environ.get("DASHBOARD_EXTERNAL"):
        _start_dashboard(config)
    else:
        logger.info("DASHBOARD_EXTERNAL set — skipping embedded dashboard.")

    scheduler = AsyncIOScheduler()
    schedule_sessions(scheduler, config)
    scheduler.start()

    logger.info("SatoraXagent started. Press Ctrl+C to stop.")

    # Graceful shutdown
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def _signal_handler():
        logger.info("Shutdown requested.")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    # Run reschedule loop alongside the scheduler
    reschedule_task = asyncio.create_task(reschedule_daily(scheduler, config))

    await stop_event.wait()
    reschedule_task.cancel()
    scheduler.shutdown(wait=False)
    logger.info("Agent stopped.")


def cli():
    """CLI entry point."""
    if len(sys.argv) > 1 and sys.argv[1] == "run-once":
        # Run a single session immediately (useful for testing / first login)
        config = load_config()
        asyncio.run(execute_session(config))
    else:
        asyncio.run(main())


if __name__ == "__main__":
    cli()
