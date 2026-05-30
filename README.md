# gitsub — XUI Subscription Sync

Automatically syncs per-user subscription files from your **3x-ui** panel to a GitHub-hosted repo, with a clean web dashboard and full CLI control.

---

## How it works

1. Fetches all clients from your 3x-ui API
2. Gets each client's subscription links via subId
3. Writes links to a random-named `.txt` file in `subs/`
4. Pushes changes to GitHub (only if content changed)
5. The raw GitHub URL becomes the user's subscription link
6. Deleted users are cleaned up automatically
7. Runs on a timer or as a systemd daemon

**Security:** filenames are random (32-char alphanumeric). No email or subId is in the filename or URL. `config.json` and `submap.json` are never pushed to GitHub.

---

## Requirements

- Ubuntu 22.04+
- Python 3.10+
- Git
- 3x-ui panel with API access (Bearer token)
- A GitHub repository (public or private)

---

## Installation

```bash
git clone https://github.com/diginetizen/mewobey-sub.git
cd mewobey-sub
bash install.sh
```

The installer will ask you for:

| Prompt | Description |
|---|---|
| Panel URL | Your 3x-ui panel URL, e.g. `https://panel.example.com` |
| API Token | Bearer token from 3x-ui |
| GitHub username / repo | Where to push subscription files |
| Deploy method | **Token** (HTTPS) or **SSH key** |
| Web UI | Enable dashboard (recommended) |
| Nginx | Optional reverse proxy + domain |
| Sync interval | Seconds between syncs (default: 21600 = 6h) |

### Deploy methods

**Option 1 — Personal Access Token (easier)**
Paste a GitHub PAT with `repo` scope. Stored in `config.json` (chmod 600, never pushed).

**Option 2 — SSH Deploy Key (more secure)**
- If you have an existing SSH key: point to it
- If not: the installer generates one and shows you the public key
- Add the public key to your repo: **Settings → Deploy keys → Add deploy key → Allow write access**
- The installer gives you the exact URL to click

---

## Files installed

```
/opt/xui-subsync/
├── update.py        # sync engine + CLI
├── webui.py         # web dashboard
├── requirements.txt
├── install.sh
├── uninstall.sh
├── config.json      # your credentials (chmod 600, not in git)
├── submap.json      # email↔filename map (not in git)
├── subs/            # subscription files (pushed to GitHub)
│   └── <random>.txt
└── logs/
    ├── sync.log
    └── error.log
```

---

## CLI — `gitsub`

After install, `gitsub` is available system-wide:

```
gitsub sync                   sync now (one-time)
gitsub daemon                 run daemon (uses config interval)
gitsub daemon --interval 300  run daemon, sync every 5 minutes
gitsub lookup <email|subId>   find a user and show their URL
gitsub rotate <email|subId>   rotate URL (generates new filename)
gitsub status                 list all users and their raw URLs
gitsub webui                  start the web dashboard manually
gitsub help                   show all commands
```

---

## Systemd services

Both services are installed and started automatically:

```bash
# Sync daemon
systemctl status xui-subsync
systemctl restart xui-subsync
journalctl -u xui-subsync -f

# Web UI
systemctl status xui-webui
systemctl restart xui-webui
journalctl -u xui-webui -f
```

---

## Web Dashboard

Access at `http://YOUR_IP:2086` (or your domain if Nginx is configured).

Features:
- Live user table with subscription URLs
- One-click **Sync Now**
- **Copy URL** / **Copy all URLs**
- Per-user **Rotate** (generates new random URL)
- Search/filter by email or subId
- Shows last sync time and repo info

---

## Nginx + SSL (optional)

The installer can set up Nginx automatically. To add SSL after install:

```bash
apt install certbot python3-certbot-nginx
certbot --nginx -d your.domain.com
```

Manual Nginx config:

```nginx
server {
    listen 80;
    server_name your.domain.com;

    location / {
        proxy_pass       http://127.0.0.1:2086;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
ln -s /etc/nginx/sites-available/xui-webui /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

---

## Update / re-pull

If you want to pull a new version from GitHub without re-running the full installer:

```bash
cd /opt/xui-subsync
git pull origin main
systemctl restart xui-subsync
systemctl restart xui-webui
```

> **Note:** If you get a "diverged history" error (someone else pushed to the repo), the sync engine automatically does a `git fetch + rebase` before every push to handle this cleanly.

---

## Uninstall

```bash
bash /opt/xui-subsync/uninstall.sh
```

Removes services, nginx config, CLI command, and optionally the project directory.

---

## Logs

```bash
# Live sync log
tail -f /opt/xui-subsync/logs/sync.log

# Error log only
tail -f /opt/xui-subsync/logs/error.log

# Systemd journal
journalctl -u xui-subsync -f
```

---

## Troubleshooting

**Push fails with "Updates were rejected"**
The sync engine does a rebase automatically. If it still fails, the remote may have commits that conflict. Run:
```bash
cd /opt/xui-subsync && git fetch origin main && git reset --hard origin/main
```
Then trigger a sync: `gitsub sync`

**API returns empty list**
Check your panel URL (no trailing slash) and verify the Bearer token is valid.

**Web UI not accessible**
Check the service: `systemctl status xui-webui`. Make sure port 2086 is open in your firewall (`ufw allow 2086`).

**SSH key not working**
Test with: `ssh -T git@github.com` — you should see "successfully authenticated". Make sure the public key is added to your repo's Deploy Keys with write access.
