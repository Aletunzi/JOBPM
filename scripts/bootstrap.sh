#!/bin/bash
# Full automated setup for SatoraXagent on a fresh Ubuntu server.
# Usage: curl -sL <raw-url> | bash

set -e

echo "=== SatoraXagent Bootstrap ==="

# 1. System dependencies
echo "[1/7] Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq python3-pip python3-venv git xvfb > /dev/null 2>&1

# 2. Clone repository
REPO_DIR="/root/SatoraXagent"
BRANCH="claude/x-verified-followers-agent-6ncTJ"

if [ -d "$REPO_DIR" ]; then
    echo "[2/7] Repo exists — pulling latest..."
    cd "$REPO_DIR"
    git fetch origin "$BRANCH"
    git reset --hard "origin/$BRANCH"
else
    echo "[2/7] Cloning repository..."
    git clone -b "$BRANCH" https://github.com/Aletunzi/SatoraXagent.git "$REPO_DIR"
    cd "$REPO_DIR"
fi

# 3. Python virtual environment
echo "[3/7] Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# 4. Python dependencies
echo "[4/7] Installing Python dependencies..."
pip install --quiet -r requirements.txt

# 5. Playwright + Chromium
echo "[5/7] Installing Playwright Chromium..."
playwright install chromium
playwright install-deps chromium > /dev/null 2>&1

# 6. Create .env file (only if it doesn't exist)
if [ ! -f "$REPO_DIR/.env" ]; then
    echo "[6/7] Creating .env file..."
    cat > "$REPO_DIR/.env" << 'ENVEOF'
X_USERNAME=Satora_ai
X_EMAIL=info@satora.xyz
X_PASSWORD=Drrqswa333!
ENVEOF
    echo "  .env created."
else
    echo "[6/7] .env already exists — skipping."
fi

# 7. Setup systemd services
echo "[7/7] Installing systemd services..."
mkdir -p "$REPO_DIR/data"
bash "$REPO_DIR/scripts/setup-server.sh"

echo ""
echo "=== Bootstrap Complete ==="
echo ""
echo "To start the bot:"
echo "  systemctl start satora-bot"
echo ""
echo "To check logs:"
echo "  journalctl -u satora-bot -f"
echo ""
