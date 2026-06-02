# gitsub — XUI Subscription Sync

Automatically syncs per-user VPN subscription links from your **3x-ui** panel to a public GitHub repository. Each user gets a stable raw GitHub URL as their subscription link. Includes a web dashboard, interactive CLI menu, and live settings management.

---

## How it works

1. Fetches all clients from your 3x-ui panel API
2. Gets each client's sub links via their `subId`
3. Writes links into a `.txt` file in your repo's `subs/` folder
4. Pushes only changed files to GitHub
5. The raw GitHub URL is the user's subscription link
6. Deleted clients are cleaned up automatically
7. Runs on a configurable timer as a systemd daemon

`config.json` and `submap.json` are never pushed to GitHub.

---

## Requirements

- Ubuntu 22.04+
- Python 3.10+
- Git
- 3x-ui panel with API access
- A **public** GitHub repository

> ⚠️ The repo must be **public**. If it is private, users will get a 404 when accessing their subscription URL.

---

## Install

```bash
git clone https://github.com/diginetizen/mewobey-sub.git
cd mewobey-sub
bash install.sh
```

The installer walks you through each step with hints:

| Step | What it asks |
|---|---|
| Panel | Full URL with port (and optional path): `https://panel.example.com:2053/path` |
| API token | From panel → Settings → Authentication → API token |
| GitHub | Username, repo name, branch |
| Deploy | Token (paste PAT) or SSH deploy key |
| Subs folder | Folder name in the repo (default: `subs`) |
| Filename mode | `random` (secure) or `email` (readable) |
| Dashboard | Port, username, password |
| Access mode | IP only, or IP + domain via nginx (HTTP) |
| Sync interval | 6h / 1h / 5min / custom |

At the end you see all working URLs:
```
Dashboard URLs:
  http://45.67.136.52:2086
  http://sub.example.com:2086    (if domain was set)
```

---

## Usage — interactive menu

Type `gitsub` from anywhere to open the menu:

```
╔══════════════════════════════════════════════╗
║  gitsub — XUI Subscription Sync              ║
╠══════════════════════════════════════════════╣
║  Services:  sync   ● active                  ║
║             webui  ● active                  ║
╠══════════════════════════════════════════════╣
║                                              ║
║   1  Sync now                                ║
║   2  Show all users & URLs                   ║
║   3  Lookup user                             ║
║   4  Rotate user URL                         ║
║   5  File map                                ║
║   6  Live logs                               ║
║   7  Settings                                ║
║   8  Nginx / domain setup                    ║
║   9  Restart services                        ║
║  10  Service status detail                   ║
║  11  Check for updates                       ║
║  12  Uninstall                               ║
║   0  Exit                                    ║
╚══════════════════════════════════════════════╝
```

Direct commands:

```bash
gitsub                    interactive menu
gitsub sync               sync now (one run)
gitsub daemon             run as background daemon
gitsub update             update script files from GitHub
gitsub lookup <q>         find user by email or sub ID
gitsub rotate <q>         give user a new random URL
gitsub status             list all users and their URLs
gitsub settings           view all settings
gitsub settings edit      change a setting
gitsub help               show all commands
```

---

## Web Dashboard

Access at `http://YOUR_IP:2086` (or your chosen port).

The dashboard runs **only on your chosen port** — no port 80 or 443 used unless you add a domain via nginx.

### Tabs

**Users**
- Full sortable table of all subscribers
- Copy URL per user or copy all URLs at once
- Search/filter by email or sub ID
- Rotate button — gives a user a new random URL

**Services**
- Sync daemon status: `● auto` (running) or `○ manual` (stopped)
- Live countdown to next sync
- Inline interval editor — change and apply without restarting manually
- Per-service start / stop / restart buttons with memory and PID info

**Settings**
- Edit any config value live, grouped by category:
  - Panel, GitHub, Sync, Web UI, Subscriptions, Nginx & Domain
- Password fields never sent back to the browser — only saved if you type a new value

---

## Subscription filenames

**Random mode** (default): each user gets a secure 32-character random filename like `xK9mPqL2...txt`. Nobody can guess who the file belongs to.

**Email mode**: filenames are derived from the user's email, like `user_at_example_com.txt`. Easier to manage but less private.

Switch mode any time in settings. When you switch, existing files are renamed on the next sync — no duplicates, no orphan files.

---

## Nginx + domain (HTTP only)

To reach the dashboard via a domain name (no SSL), the installer sets up nginx for you if you choose access mode 2. You can also configure it later from the menu (option 8):

```
Nginx / domain setup
  1  IP only — disable nginx for gitsub
  2  Set up domain → port 2086 (nginx HTTP proxy)
  3  Show current nginx config
  4  Reload nginx
  5  Test nginx config (nginx -t)
  6  Enable nginx service
```

Manual nginx config example:

```nginx
server {
    listen 80;
    server_name sub.example.com;
    location / {
        proxy_pass       http://127.0.0.1:2086;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 60;
    }
}
```

> SSL / HTTPS is not managed by gitsub. Add it separately with certbot after installation if needed.

---

## Services

```bash
systemctl status xui-subsync       # sync daemon
systemctl status xui-webui         # web dashboard
journalctl -u xui-subsync -f       # live sync log
journalctl -u xui-webui -f         # live webui log
```

Logs also at `/opt/xui-subsync/logs/sync.log` and `error.log`.

---

## Update

```bash
gitsub update
# or from the menu: option 11
```

Downloads the latest `update.py`, `webui.py`, and `requirements.txt` from GitHub, updates pip dependencies, and restarts services.

---

## Uninstall

From the menu (option 12) or directly:

```bash
bash /opt/xui-subsync/uninstall.sh
```

Confirm with `y`. You'll also be asked whether to remove all sub files from your GitHub repo (your users will lose their subscription links if you say yes).

---

## Troubleshooting

**Web UI not opening on port 2086**
```bash
systemctl status xui-webui
journalctl -u xui-webui -n 50
ufw allow 2086/tcp    # open firewall if blocked
```

**Internal Server Error in browser**
```bash
journalctl -u xui-webui -n 30 --no-pager
# Look for Python tracebacks
```

**Nginx fails to start with "bind() to 0.0.0.0:443 failed"**

A leftover SSL config from a previous install is still in nginx's config. Fix it:
```bash
# Find and remove any config with listen 443
grep -rl "listen.*443" /etc/nginx/sites-enabled/ /etc/nginx/conf.d/
# Remove the offending files, then:
nginx -t && systemctl start nginx
```

**Git push fails / diverged history**
The sync engine automatically does `fetch + rebase` before every push. If it still fails:
```bash
cd /opt/xui-subsync
git fetch origin main && git reset --hard origin/main
gitsub sync
```

**Wrong GitHub username or repo name**
Edit in the web UI (Settings → GitHub) or terminal (`gitsub settings edit`). The git remote URL updates immediately — no restart needed.

**SSH: "Could not read from remote repository"**
```bash
ssh -i /root/.ssh/gitsub_deploy -T git@github.com
# Should say: "Hi username! You've successfully authenticated"
```
Make sure the deploy key has **Allow write access** checked on GitHub.
