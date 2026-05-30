#!/bin/bash

set -e

echo "====================================="
echo " XUI SUBSYNC INSTALLER v4 (SSH MODE)"
echo "====================================="

# -------------------------
# INPUTS
# -------------------------

read -p "Panel URL: " PANEL_URL
read -p "API Token: " API_TOKEN

read -p "GitHub username: " GITHUB_USER
read -p "GitHub repo name: " GITHUB_REPO

read -p "GitHub email (for git config): " GIT_EMAIL
read -p "GitHub name (for git config): " GIT_NAME

read -p "Enable Web UI? (y/n): " ENABLE_UI
read -p "Web UI Port (default 2086): " UI_PORT
UI_PORT=${UI_PORT:-2086}

read -p "Sync interval seconds (default 21600): " INTERVAL
INTERVAL=${INTERVAL:-21600}

# -------------------------
# INSTALL PACKAGES
# -------------------------

apt update
apt install -y python3 python3-venv git nginx openssh-client

# -------------------------
# SSH KEY CHECK
# -------------------------

echo "Checking SSH key..."

if [ ! -f ~/.ssh/id_rsa ]; then
    echo "No SSH key found. Creating one..."
    ssh-keygen -t rsa -b 4096 -C "$GIT_EMAIL" -N "" -f ~/.ssh/id_rsa
fi

eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_rsa

echo ""
echo "👉 ADD THIS PUBLIC KEY TO GITHUB:"
echo "--------------------------------"
cat ~/.ssh/id_rsa.pub
echo "--------------------------------"
echo ""
read -p "Press ENTER after adding SSH key to GitHub..."

# Test SSH connection
ssh -T git@github.com || true

# -------------------------
# PYTHON ENV
# -------------------------

python3 -m venv venv
source venv/bin/activate
pip install requests flask

# -------------------------
# GIT CONFIG
# -------------------------

git config --global user.email "$GIT_EMAIL"
git config --global user.name "$GIT_NAME"

git remote remove origin 2>/dev/null || true
git remote add origin git@github.com:$GITHUB_USER/$GITHUB_REPO.git

# -------------------------
# CONFIG
# -------------------------

cat > config.json <<EOF
{
  "panel_url": "$PANEL_URL",
  "api_token": "$API_TOKEN",
  "github_user": "$GITHUB_USER",
  "github_repo": "$GITHUB_REPO",
  "github_branch": "main",
  "filename_length": 32,
  "sync_interval": $INTERVAL
}
EOF

# -------------------------
# SYSTEMD SYNC
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
# WEB UI
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

echo "====================================="
echo " INSTALL COMPLETE (SSH MODE)"
echo "====================================="
