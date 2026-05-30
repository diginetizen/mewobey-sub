#!/bin/bash

set -e

echo "===================================="
echo "  XUI SUBSYNC AUTO INSTALLER v2"
echo "===================================="

# -------------------------
# INPUT SECTION (SAFE DEFAULTS)
# -------------------------

read -p "Panel URL: " PANEL_URL
read -p "API Token: " API_TOKEN

echo ""
echo "GitHub setup:"
echo "1) user/repo (recommended)"
echo "2) full https URL"
read -p "Choose (1/2): " GIT_MODE

if [ "$GIT_MODE" = "1" ]; then
    read -p "GitHub repo (e.g. diginetizen/mewobey-sub): " GITHUB_REPO
    GITHUB_URL=""
else
    read -p "GitHub full URL: " GITHUB_URL
    GITHUB_REPO=""
fi

read -p "Enable Web UI? (y/n): " ENABLE_UI
read -p "Web UI Port (default 2086): " UI_PORT
UI_PORT=${UI_PORT:-2086}

read -p "Sync interval seconds (default 21600 = 6h): " INTERVAL
INTERVAL=${INTERVAL:-21600}

# -------------------------
# INSTALL DEPENDENCIES
# -------------------------

apt update
apt install -y python3 python3-venv git nginx

python3 -m venv venv
source venv/bin/activate
pip install requests flask

# -------------------------
# CONFIG BUILD
# -------------------------

cat > config.json <<EOF
{
  "panel_url": "$PANEL_URL",
  "api_token": "$API_TOKEN",
  "github_repo": "$GITHUB_REPO",
  "github_repo_url": "$GITHUB_URL",
  "github_branch": "main",
  "filename_length": 32,
  "request_timeout": 20,
  "request_retries": 3,
  "sync_interval": $INTERVAL
}
EOF

# -------------------------
# SYSTEMD SYNC SERVICE (DAEMON)
# -------------------------

cat > /etc/systemd/system/xui-subsync.service <<EOF
[Unit]
Description=XUI Subscription Sync
After=network.target

[Service]
WorkingDirectory=/opt/xui-subsync
ExecStart=/opt/xui-subsync/venv/bin/python /opt/xui-subsync/update.py daemon --interval $INTERVAL
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable xui-subsync

# -------------------------
# WEB UI SERVICE (OPTIONAL)
# -------------------------

if [ "$ENABLE_UI" = "y" ]; then

cat > /etc/systemd/system/xui-webui.service <<EOF
[Unit]
Description=XUI Web UI
After=network.target

[Service]
WorkingDirectory=/opt/xui-subsync
Environment=PORT=$UI_PORT
ExecStart=/opt/xui-subsync/venv/bin/python /opt/xui-subsync/webui.py
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable xui-webui
systemctl start xui-webui

fi

echo "===================================="
echo " INSTALL COMPLETE"
echo "===================================="

echo "Start sync:"
echo "systemctl start xui-subsync"

if [ "$ENABLE_UI" = "y" ]; then
    echo "Web UI: http://SERVER_IP:$UI_PORT"
fi
