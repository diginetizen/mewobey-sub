# 📡 XUI Subscription Sync System

A production-ready automation system for 3x-ui v3.2 that generates and distributes per-user GitHub-hosted subscription files with auto sync, cleanup, rotation, and a lightweight web dashboard.

---

# 🚀 Features

- Automatic client discovery from 3x-ui API
- Per-user subscription file generation
- Secure random filenames (no email/subId exposure)
- GitHub raw hosting distribution
- Smart change detection (no spam commits)
- Auto cleanup of deleted users
- Subscription rotation system
- Lightweight Flask web dashboard
- Systemd daemon mode (auto-start on reboot)
- Nginx + Cloudflare domain support
- Local mapping database (submap.json)
- Logging system
- Auto installer + uninstaller

---

# 🏗 Project Structure

/opt/xui-subsync
├── update.py
├── webui.py
├── install.sh
├── uninstall.sh
├── config.json
├── submap.json
├── requirements.txt
├── logs/
│   ├── sync.log
│   ├── error.log
│   └── rotation.log
├── subs/
│   └── random.txt
└── venv/

---

# ⚙️ Requirements

- Ubuntu 22.04+
- Python 3.11+
- Git
- 3x-ui v3.2 API access (Bearer token)
- GitHub repository
- Optional: Nginx + Cloudflare

---

# ⚡ Installation

## Clone repo
git clone https://github.com/diginetizen/mewobey-sub.git
cd mewobey-sub

## Run installer
bash install.sh

Installer will ask:
- Panel URL
- API Token
- GitHub repo
- Web UI enable (y/n)
- Web UI port (default 2086)
- Domain (optional)
- Sync mode (daemon recommended)
- Sync interval

---

# 🚀 Running

## Manual sync
python update.py sync

## Daemon mode (recommended)
python update.py daemon --interval 21600

21600 = 6 hours (production)
120 = 2 minutes (testing)

## Systemd service
systemctl start xui-subsync
systemctl enable xui-subsync
systemctl status xui-subsync

---

# 🌐 Web Dashboard

## Run manually
python webui.py

## Access
http://YOUR_SERVER_IP:2086

---

# 🌍 Domain Setup (Nginx)

server {
    listen 80;
    server_name bt.moshakshop.tr;

    location / {
        proxy_pass http://127.0.0.1:2086;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}

Enable:
ln -s /etc/nginx/sites-available/xui-webui /etc/nginx/sites-enabled/
systemctl restart nginx

---

# 🔐 SSL (Cloudflare / Certbot)
certbot --nginx -d bt.moshakshop.tr

---

# 🔁 Commands

## Sync
python update.py sync

## Daemon
python update.py daemon

## Lookup
python update.py lookup email@example.com
python update.py lookup subId

## Rotate
python update.py rotate email@example.com

---

# 🧠 How it works

1. Fetch clients from 3x-ui API
2. Get subscription links per subId
3. Generate secure random filename
4. Save to /subs
5. Push to GitHub
6. Generate raw URL
7. Store mapping in submap.json
8. Remove deleted users automatically
9. Update only if changes detected

---

# 🔐 Security

- API token stored locally only
- No email/subId in filenames
- submap.json NOT uploaded to GitHub
- Random cryptographic filenames
- Optional domain reverse proxy

---

# 🧨 Uninstall

bash uninstall.sh

Will:
- Stop services
- Remove systemd
- Remove nginx config
- Optionally delete project

# 👨‍💻 Author

Automated 3x-ui subscription system
