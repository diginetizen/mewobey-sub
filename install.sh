#!/bin/bash

set -e

echo "====================================="
echo " XUI SUBSYNC INSTALLER v3 (HTTPS ONLY)"
echo "====================================="

# -------------------------
# INPUTS
# -------------------------

read -p "Panel URL: " PANEL_URL
read -p "API Token: " API_TOKEN

read -p "GitHub username: " GITHUB_USER
read -p "GitHub repo name: " GITHUB_REPO

echo ""
echo "We use HTTPS token authentication (NO SSH required)"
read -p "GitHub Personal Access Token (optional test push): " GITHUB_TOKEN

read -p "Enable Web UI? (y/n): " ENABLE_UI
read -p "Web UI Port (default 2086): " UI_PORT
UI_PORT=${UI_PORT:-2086}

read -p "Sync interval seconds (default 21600 = 6h): " INTERVAL
INTERVAL=${INTERVAL:-21600}

# -------------------------
# INSTALL PACKAGES
# -------------------------

apt update
apt install -y python3 python3-venv git nginx

python3 -m venv venv
source venv/bin/activate
pip install requests flask

# -------------------------
# CONFIG FILE
# -------------------------

cat > config.json <<EOF
{
  "panel_url": "$PANEL_URL",
  "api_token": "$API_TOKEN",
  "github_user": "$GITHUB_USER",
  "github_repo": "$GITHUB_REPO",
  "github_token": "$GITHUB_TOKEN",
  "github_branch": "main",
  "filename_length": 32,
  "sync_interval": $INTERVAL
}
EOF

# -------------------------
# SYNC SERVICE
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
# WEB UI SERVICE
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

# -------------------------
# DONE
# -------------------------

echo "====================================="
echo " INSTALL COMPLETE"
echo "====================================="
echo "Start sync: systemctl start xui-subsync"

if [ "$ENABLE_UI" = "y" ]; then
    echo "Web UI: http://SERVER_IP:$UI_PORT"
fi
