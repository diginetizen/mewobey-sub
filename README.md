# XUI Subscription Sync (GitHub Edition)

A simple automation tool for **3x-ui v3.2** that generates GitHub-hosted subscription links per user and keeps them synced automatically.

---

## 🚀 What it does

- Fetches all users from 3x-ui API
- Gets subscription links per user
- Creates a unique `.txt` file for each user
- Uploads to GitHub (raw links)
- Auto updates when subscriptions change
- Removes deleted users automatically

---

## 🔗 Output Example

Each user gets a link like:


https://raw.githubusercontent.com/diginetizen/mewobey-sub/main/subs/AbC123XyZ987.txt


---

## ⚙️ Installation (EASY MODE)

### 1. Run installer

```bash
bash install.sh

It will ask:

Panel URL
API token
GitHub repo
Sync mode (daemon recommended)
🧠 Run manually (optional)
Sync once
python update.py sync
Run continuously (recommended)
python update.py daemon

Test mode (fast sync every 2 min):

python update.py daemon --interval 120

Production mode (every 6 hours):

python update.py daemon --interval 21600
🔍 Lookup user

Find subscription info:

python update.py lookup user@example.com

or by subId:

python update.py lookup SUB_ID
🔁 Rotate subscription

Generate new link for a user:

python update.py rotate user@example.com
🛠 System Service (Auto Start)

Start service:

systemctl start xui-subsync

Enable on boot:

systemctl enable xui-subsync

Check status:

systemctl status xui-subsync

Logs:

journalctl -u xui-subsync -f
📁 Project Files
update.py        → main script
config.json      → settings (DO NOT SHARE)
submap.json      → local mapping (DO NOT SHARE)
subs/            → generated subscription files
logs/            → system logs
install.sh       → auto installer
⚠️ Important
Never commit config.json
Never expose API token
Use SSH Git (recommended)
Keep VPS secure
🧪 Quick Test
python update.py sync

If files appear in subs/ → system is working.
