# XUI Subscription Sync System

A production-ready automation system for **3x-ui v3.2** that generates GitHub-hosted subscription files for each client and keeps them automatically synced.

---

## 🚀 Features

### Core Features
- Auto-fetch all 3x-ui clients via API
- Generate per-user subscription files
- GitHub raw link distribution
- Automatic sync (daemon mode)
- Manual sync support
- Subscription rotation per user
- Lookup by email or subId
- Auto cleanup of deleted users

### Production Features
- Systemd service support (auto start on reboot)
- Change detection (no unnecessary Git commits)
- Secure random filenames (32 characters)
- Retry + timeout API handling
- Lock-safe execution (prevents duplicate runs)
- Logging support
- Git auto commit + push

---

## ⚙️ Installation

### 🟢 Automatic Installation (Recommended)

Run:

```bash
bash install.sh

It will:

Ask for panel URL
Ask for API token
Configure GitHub repository
Install dependencies
Setup systemd service
Enable auto-start
Run initial sync
🔵 Manual Installation
1. Clone repo
git clone git@github.com:diginetizen/mewobey-sub.git
cd mewobey-sub
2. Setup Python environment
python3 -m venv venv
source venv/bin/activate
pip install requests
3. Configure system

Create config.json:

{
  "panel_url": "https://YOUR_PANEL",
  "api_token": "YOUR_TOKEN",
  "github_username": "diginetizen",
  "github_repository": "mewobey-sub",
  "github_branch": "main",
  "filename_length": 32,
  "request_timeout": 20,
  "request_retries": 3
}
4. Run first sync
python update.py sync
🔄 Running Modes
🟢 Daemon Mode (Recommended)

Runs continuously and syncs automatically:

python update.py daemon

Custom interval:

python update.py daemon --interval 21600   # 6 hours (production)
python update.py daemon --interval 120      # 2 minutes (test)
🔵 Manual Sync

Run once:

python update.py sync
🔁 Subscription Rotation

Generate a new subscription file for a user:

python update.py rotate user@example.com
🔍 Lookup User

Find subscription details:

python update.py lookup user@example.com

or by subId:

python update.py lookup a68ykk383mnjqnp0
🧠 System Behavior
Sync Process
Fetch all clients from 3x-ui
Get subscription links per client
Generate or update subscription file
Detect changes (skip if unchanged)
Remove deleted users
Push updates to GitHub
🔗 Subscription URL Format

Each user gets:

https://raw.githubusercontent.com/diginetizen/mewobey-sub/main/subs/<random>.txt
🛠 Systemd Service (Auto Start)

Enable service:

systemctl enable xui-subsync
systemctl start xui-subsync

Check status:

systemctl status xui-subsync

Logs:

journalctl -u xui-subsync -f
🧪 Testing
Quick test sync:
python update.py sync
Test daemon (fast mode):
python update.py daemon --interval 120
⚠️ Security Notes
Never commit config.json
Never expose API token publicly
Keep submap.json local only
Use SSH Git authentication recommended
🔧 Troubleshooting
Service not found

Run:

systemctl daemon-reload
Sync not working

Check logs:

python update.py sync

or:

journalctl -u xui-subsync -n 50
📌 Summary

This system provides:

Fully automated subscription distribution
GitHub-hosted config files
Per-user isolation
Production-ready daemon mode
Easy installation and scaling
🚀 Done

---

# 👍 What you now have

You now have:

✔ full automation system  
✔ manual + auto modes  
✔ installer support  
✔ production daemon  
✔ clean documentation  
