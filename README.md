# SatoraXagent

Agent that automatically follows verified followers of target X profiles.

## Features

- Visits up to 5 target profiles and follows their verified followers
- Max 6 follows per target profile, 2 sessions per day
- Human-like behavior: Bezier mouse movement, gaussian delays, realistic typing
- Stops gracefully on rate limit or captcha — resumes at next scheduled session
- Variable daily scheduling within configurable time windows
- Web dashboard to monitor follow activity, errors, and session history

## Setup

```bash
# Clone and enter the project
git clone <repo-url>
cd SatoraXagent

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

## Configuration

Edit `config/settings.yaml` with your target profiles and preferences:

```yaml
target_profiles:
  - "elonmusk"
  - "naval"
  - "balaboratory"
  - "jack"
  - "vaboratory"
```

Adjust time windows, follow limits, and delays as needed.

## Usage

### First run (login)

The first time the agent runs, it opens a visible browser window. Log in to your X account manually (including 2FA if enabled). The session is saved automatically — subsequent runs reuse the cookies.

```bash
python -m src.main run-once
```

### Start the scheduler

Runs the agent as a daemon with 2 daily sessions at random times within the configured windows:

```bash
python -m src.main
```

### Dashboard

Open the monitoring dashboard at `http://localhost:5000`:

```bash
python -m src.dashboard.app
```

The dashboard shows:
- Daily follow counts and session times
- Bar chart of follows over time (session 1 vs session 2)
- Full session history table with status and error details
- Scrollable event log with follow/skip/error entries
- Auto-refreshes every 30 seconds

## Project structure

```
config/settings.yaml       Target profiles, limits, schedule windows
src/main.py                Entry point + APScheduler (2 sessions/day)
src/browser.py             Playwright setup with stealth + persistent context
src/actions.py             Core logic: search, navigate, follow, rate limit detection
src/anti_detection.py      Human-like delays, Bezier mouse, realistic typing/scroll
src/session_tracker.py     Session logging + daily limit enforcement
src/dashboard/app.py       Flask API serving the dashboard
src/dashboard/templates/   HTML template
src/dashboard/static/      CSS + JS (Chart.js)
data/session_log.json      Persistent log of all sessions (auto-created)
data/browser_state/        Playwright persistent context (auto-created)
```
