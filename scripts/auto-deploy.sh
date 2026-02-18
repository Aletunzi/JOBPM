#!/bin/bash
# Auto-deploy: checks git for updates every 2 minutes.
# If code changed, pulls and restarts the bot.

REPO_DIR="/root/SatoraXagent"
BRANCH="claude/x-verified-followers-agent-6ncTJ"
LOG_FILE="/root/SatoraXagent/data/deploy.log"

cd "$REPO_DIR" || exit 1

# Fetch latest from remote
git fetch origin "$BRANCH" 2>/dev/null

# Check if there are new commits
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$BRANCH")

if [ "$LOCAL" != "$REMOTE" ]; then
    echo "$(date): New changes detected — deploying..." >> "$LOG_FILE"

    # Pull latest changes
    git reset --hard "origin/$BRANCH" >> "$LOG_FILE" 2>&1

    # Update dependencies if requirements changed
    source "$REPO_DIR/venv/bin/activate"
    pip install -q -r requirements.txt >> "$LOG_FILE" 2>&1

    # Restart services
    systemctl restart satora-dashboard.service
    systemctl restart satora-bot.service

    echo "$(date): Deploy complete." >> "$LOG_FILE"
else
    echo "$(date): No changes." >> "$LOG_FILE"
fi
