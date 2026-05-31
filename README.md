# gitsub — XUI Subscription Sync

Syncs per-user VPN subscription files from your **3x-ui** panel to a GitHub-hosted repo. Users get a stable raw GitHub URL as their subscription link. Includes a web dashboard, interactive CLI menu, and full settings management.

---

## How it works

1. Fetches all clients from your 3x-ui panel API
2. Gets each client's sub links via their `subId`
3. Writes links to a file in `subs/` — either a random name or the user's email
4. Pushes changes to GitHub (only changed files)
5. The raw GitHub URL is the user's subscription link
6. Deleted clients are cleaned up automatically
7. Runs on a timer as a systemd daemon

`config.json` and `submap.json` are never pushed to GitHub.

---

## Requirements

- Ubuntu 22.04+
- Python 3.10+
- Git
- 3x-ui panel with API access
- A GitHub repository

---

## Install

```bash
git clone https://github.com/diginetizen/mewobey-sub.git
cd mewobey-sub
bash install.sh
```

The installer asks step by step:

| Step | What it asks |
|---|---|
| Panel | Full URL including port, e.g. `https://panel.example.com:2053` |
| API token | Your 3x-ui bearer token — input is masked with `*` |
| GitHub | Username, repo name, branch |
| Deploy method | Token (HTTPS) or SSH key |
| SSH key | Use existing path, paste key content, or generate new one |
| Web UI | Port (default 2086), username, password |
| Sync interval | Menu: 6h / 1h / 5min / custom |

At the end it shows:
```
Web UI access:
  http://YOUR_IP:2086
  http://your.domain:2086   (if domain was set)
```

---

## Usage

Type `gitsub` anywhere to open the interactive menu:

```
╔══════════════════════════════════════════════╗
║  gitsub — XUI Subscription Sync              ║
╠══════════════════════════════════════════════╣
║  Services:  sync   ● active                  ║
║             webui  ● active                  ║
╠══════════════════════════════════════════════╣
║                                              ║
║  1  Sync now                                 ║
║  2  Show all users & URLs                    ║
║  3  Lookup user                              ║
║  4  Rotate user URL                          ║
║  5  File map                                 ║
║  6  Live logs                                ║
║  7  Settings                                 ║
║  8  Enable SSL                               ║
║  9  Restart services                         ║
║  s  Service status detail                    ║
║  u  Check for updates                        ║
║  x  Uninstall                                ║
║  0  Exit                                     ║
╚══════════════════════════════════════════════╝
```

Direct commands:

```bash
gitsub                   interactive menu
gitsub sync              sync now
gitsub daemon            run as daemon
gitsub update            update script files
gitsub lookup <q>        find user by email or sub ID
gitsub rotate <q>        rotate URL (new filename)
gitsub status            list all users and URLs
gitsub settings          view settings
gitsub settings edit     change a setting
gitsub help              show all commands
```

---

## Web Dashboard — port 2086

Access at `http://YOUR_IP:2086` (or whatever port you chose).

The dashboard runs **directly on your chosen port** — no nginx, no port 80.

Tabs:
- **Users** — full table with sub URLs, copy button, rotate, search/filter
- **Services** — live systemd status for both services with start/stop/restart
- **Settings** — edit any config value directly from the browser, grouped by category

Password-type fields (API token, GitHub token, password) are never sent back to the browser — the field shows a placeholder and only saves if you type a new value.

---

## Subscription filenames

By default each user gets a random 32-character filename (e.g. `xK9mPqL2...txt`). You can change this to use the user's email instead:

**In the web UI:** Settings → Sync → Filename Mode → set to `email`

**In the terminal:** `gitsub settings edit` → choose Filename Mode

When set to `email`, new users get a file named like `user_at_example_com.txt`. Existing files are not renamed until you rotate them.

---

## Update

```bash
gitsub update
# or from the menu: u
```

Downloads the latest `update.py`, `webui.py`, and `requirements.txt` from GitHub, updates pip dependencies if needed, and restarts services automatically.

---

## Nginx + domain (optional, no SSL)

If you want to access the dashboard via a domain without SSL:

```nginx
server {
    listen 80;
    server_name your.domain.com;

    location / {
        proxy_pass           http://127.0.0.1:2086;
        proxy_set_header     Host $host;
        proxy_set_header     X-Real-IP $remote_addr;
        proxy_set_header     X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header     X-Forwarded-Proto $scheme;
        proxy_read_timeout   60;
    }
}
```

```bash
ln -s /etc/nginx/sites-available/your-config /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

SSL can be added later via `gitsub` menu → option `8`.

---

## Services

```bash
systemctl status xui-subsync    # sync daemon
systemctl status xui-webui      # web dashboard

journalctl -u xui-subsync -f    # live sync log
journalctl -u xui-webui -f      # live webui log
```

Log files also at `/opt/xui-subsync/logs/sync.log` and `error.log`.

---

## Uninstall

From the menu (option `x`) or directly:

```bash
bash /opt/xui-subsync/uninstall.sh
```

Type `yes` to confirm. Removes services, CLI command, and optionally all project files.

---

## Troubleshooting

**Web UI not opening on port 2086**
```bash
systemctl status xui-webui
journalctl -u xui-webui -n 50
# Check firewall:
ufw allow 2086/tcp
```

**"conflicting server name" nginx warning**
Another nginx site already uses that domain. Either remove the conflicting config from `/etc/nginx/sites-enabled/` or ignore it — it's a warning, not an error, and the gitsub config takes precedence.

**Push fails / git diverged history**
The sync engine does a `fetch + rebase` before every push. If it still fails:
```bash
cd /opt/xui-subsync
git fetch origin main && git reset --hard origin/main
gitsub sync
```

**SSH: "Could not read from remote repository"**
Check `~/.ssh/config` has the `github-gitsub` alias pointing to the right key, and that key is added to GitHub with write access:
```bash
ssh -i /root/.ssh/gitsub_deploy -T git@github.com
# should say: "Hi username! You've successfully authenticated"
```
