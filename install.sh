#!/bin/bash

set -e

echo "====================================="
echo "  XUI Subscription Sync Installer"
echo "====================================="

read -p "GitHub repo (e.g. diginetizen/mewobey-sub): " GITHUB_REPO
read -p "Panel URL (https://domain/path): " PANEL_URL
read -p "API Token: " API_TOKEN
read -p "Sync mode (daemon recommended): " MODE

read -p "Interval seconds (default 21600 = 6h, test 120): " INTERVAL
INTERVAL=${INTERVAL:-21600}

echo "[1/6] Installing dependencies..."
apt update && apt install -y python3 python3-venv git

echo "[2/6] Setting up venv..."
python3 -m venv venv
source venv/bin/activate
pip install requests

echo "[3/6] Writing config..."

cat > config.json <<EOF
{
  "panel_url": "$PANEL_URL",
  "api_token": "$API_TOKEN",
  "github_username": "diginetizen",
  "github_repository": "$(echo $GITHUB_REPO | cut -d'/' -f2)",
  "github_branch": "main",
  "filename_length": 32,
  "request_timeout": 20,
  "request_retries": 3
}
EOF

echo "[4/6] Creating systemd service..."

cat > /etc/systemd/system/xui-subsync.service <<EOF
[Unit]
Description=XUI Subscription Sync
After=network.target

[Service]
WorkingDirectory=/opt/xui-subsync
ExecStart=/opt/xui-subsync/venv/bin/python update.py daemon --interval $INTERVAL
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF

echo "[5/6] Enabling service..."
systemctl daemon-reload
systemctl enable xui-subsync

echo "[6/6] Done."

echo "Start with:"
echo "systemctl start xui-subsync"
