#!/bin/bash
# One-time server setup for SatoraXagent.
# Creates systemd services for the bot and auto-deploy.

set -e

REPO_DIR="/root/SatoraXagent"
VENV="$REPO_DIR/venv"

echo "=== SatoraXagent Server Setup ==="

# Ensure data directory exists
mkdir -p "$REPO_DIR/data"

# Make scripts executable
chmod +x "$REPO_DIR/scripts/auto-deploy.sh"

# --- 1. Create bot systemd service ---
cat > /etc/systemd/system/satora-bot.service << 'EOF'
[Unit]
Description=SatoraXagent Twitter Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/SatoraXagent
EnvironmentFile=/root/.env-bot
Environment=DISPLAY=:99
Environment=DASHBOARD_EXTERNAL=1
ExecStart=/usr/bin/xvfb-run /root/SatoraXagent/venv/bin/python -m src.main
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF

# --- 2. Create auto-deploy timer ---
cat > /etc/systemd/system/satora-deploy.service << 'EOF'
[Unit]
Description=SatoraXagent Auto-Deploy

[Service]
Type=oneshot
ExecStart=/root/SatoraXagent/scripts/auto-deploy.sh
EOF

cat > /etc/systemd/system/satora-deploy.timer << 'EOF'
[Unit]
Description=Check for SatoraXagent updates every 2 minutes

[Timer]
OnBootSec=30
OnUnitActiveSec=2min
Persistent=true

[Install]
WantedBy=timers.target
EOF

# --- 3. Create dashboard service (port 5000, independent from bot) ---
cat > /etc/systemd/system/satora-dashboard.service << 'EOF'
[Unit]
Description=SatoraXagent Dashboard
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/SatoraXagent
EnvironmentFile=/root/.env-bot
Environment=DISPLAY=:99
ExecStart=/root/SatoraXagent/venv/bin/python -m src.dashboard.app
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# --- 4. Create debug screenshot server (port 8080) ---
cat > /etc/systemd/system/satora-debug.service << 'EOF'
[Unit]
Description=SatoraXagent Debug Screenshot Server
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/SatoraXagent/data
ExecStart=/usr/bin/python3 -m http.server 8080
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

# --- 5. Enable and start everything ---
systemctl daemon-reload
systemctl enable satora-deploy.timer
systemctl start satora-deploy.timer
systemctl enable satora-dashboard.service
systemctl start satora-dashboard.service
systemctl enable satora-debug.service
systemctl start satora-debug.service

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Services installed:"
echo "  - satora-bot       : the Twitter bot (start with: systemctl start satora-bot)"
echo "  - satora-dashboard : web dashboard at http://YOUR-IP:5000/"
echo "  - satora-deploy    : auto-deploy every 2 min (already running)"
echo "  - satora-debug     : debug screenshots at http://YOUR-IP:8080/"
echo ""
echo "Useful commands:"
echo "  systemctl start satora-bot        # Start the bot"
echo "  systemctl stop satora-bot         # Stop the bot"
echo "  systemctl status satora-bot       # Check bot status"
echo "  journalctl -u satora-bot -f       # Live bot logs"
echo "  journalctl -u satora-dashboard -f # Dashboard logs"
echo "  cat data/deploy.log               # Deploy history"
echo ""
