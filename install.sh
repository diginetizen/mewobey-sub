#!/bin/bash

set -e

echo "INSTALL XUI SYSTEM"

read -p "GitHub user/repo (e.g. name/repo): " REPO
read -p "Panel URL: " PANEL
read -p "API Token: " TOKEN
read -p "Domain (optional): " DOMAIN

apt update
apt install -y git python3 python3-venv nginx certbot python3-certbot-nginx

# SSH
ssh-keygen -t rsa -b 4096 -N "" -f ~/.ssh/id_rsa || true

echo "ADD THIS TO GITHUB:"
cat ~/.ssh/id_rsa.pub
read -p "Press ENTER after adding SSH key"

# clone
rm -rf /opt/xui-subsync
git clone git@github.com:$REPO.git /opt/xui-subsync

cd /opt/xui-subsync

python3 -m venv venv
source venv/bin/activate
pip install requests flask

cat > config.json <<EOF
{
  "panel_url": "$PANEL",
  "filename_length": 32
}
EOF

# ENV
export GIT_USER=$(echo $REPO | cut -d'/' -f1)
export GIT_REPO=$(echo $REPO | cut -d'/' -f2)
export XUI_TOKEN="$TOKEN"

# SYSTEMD SYNC
cat > /etc/systemd/system/xui-subsync.service <<EOF
[Unit]
Description=XUI Sync
After=network.target

[Service]
WorkingDirectory=/opt/xui-subsync
Environment=XUI_TOKEN=$TOKEN
Environment=GIT_USER=$GIT_USER
Environment=GIT_REPO=$GIT_REPO
ExecStart=/opt/xui-subsync/venv/bin/python update.py daemon --interval 21600
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF

# WEB UI
cat > /etc/systemd/system/xui-webui.service <<EOF
[Unit]
Description=XUI WebUI
After=network.target

[Service]
WorkingDirectory=/opt/xui-subsync
Environment=PORT=2086
ExecStart=/opt/xui-subsync/venv/bin/python webui.py
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable xui-subsync
systemctl enable xui-webui
systemctl start xui-subsync
systemctl start xui-webui

# NGINX
if [ ! -z "$DOMAIN" ]; then
cat > /etc/nginx/sites-available/xui <<EOF
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:2086;
    }
}
EOF

ln -sf /etc/nginx/sites-available/xui /etc/nginx/sites-enabled/
systemctl restart nginx

certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m admin@$DOMAIN || true
fi

echo "DONE"
