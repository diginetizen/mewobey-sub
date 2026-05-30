#!/bin/bash

set -e

echo "====================================="
echo " XUI SUB SYNC FULL INSTALLER"
echo "====================================="

read -p "GitHub repo (diginetizen/mewobey-sub): " GITHUB_REPO
read -p "Panel URL: " PANEL_URL
read -p "API Token: " API_TOKEN

read -p "Enable Web UI? (y/n): " ENABLE_UI
read -p "Web UI Port (default 2086): " UI_PORT
UI_PORT=${UI_PORT:-2086}

read -p "Domain (optional): " DOMAIN

echo "[1/6] Installing system packages..."
apt update
apt install -y python3 python3-venv git nginx

echo "[2/6] Python setup..."
python3 -m venv venv
source venv/bin/activate
pip install requests flask

echo "[3/6] Config file..."
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

echo "[4/6] Creating Web UI service..."

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

echo "[5/6] Creating nginx (if domain provided)..."

if [ ! -z "$DOMAIN" ]; then

cat > /etc/nginx/sites-available/xui-webui <<EOF
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:$UI_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
EOF

ln -sf /etc/nginx/sites-available/xui-webui /etc/nginx/sites-enabled/
systemctl restart nginx

fi

echo "[6/6] Done!"

echo "Start sync:"
echo "python update.py sync"

echo "Start web:"
echo "systemctl start xui-webui"
