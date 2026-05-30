# gitsub — XUI Subscription Sync v3

Syncs per-user subscription files from your **3x-ui** panel to a GitHub repo, with a web dashboard, login protection, interactive CLI menu, and full settings manager.

---

## Install

```bash
git clone https://github.com/diginetizen/mewobey-sub.git
cd mewobey-sub
bash install.sh
```

The installer asks step by step:
- Panel URL + API token
- GitHub username / repo / branch
- Deploy method: **Token** or **SSH key**
  - SSH: generates a key if you don't have one, shows the public key, gives you the exact GitHub link to add it, then tests the connection
- Web UI: port, **username + password**
- Nginx + domain (optional) + **SSL certificate via Certbot** (optional, installs right now)
- Sync interval (menu: 6h / 1h / 5min / custom)
- Confirmation summary before anything is written

Git commit identity is set automatically from your GitHub username — no separate email prompt.

---

## Usage

Type `gitsub` with no arguments to open the interactive menu:

```
╔══════════════════════════════════════════╗
║  gitsub — XUI Subscription Sync          ║
╠══════════════════════════════════════════╣
║  Services:  sync  ● active               ║
║             webui ● active               ║
╠══════════════════════════════════════════╣
║  1  Sync now (manual run)                ║
║  2  Show all users & URLs                ║
║  3  Lookup user by email / sub ID        ║
║  4  Rotate user URL                      ║
║  5  View logs (live)                     ║
║  6  Settings — view & change             ║
║  7  Restart services                     ║
║  8  Service status details               ║
║  0  Exit                                 ║
╚══════════════════════════════════════════╝
```

Or use direct commands:

```bash
gitsub sync                    # sync now
gitsub daemon --interval 3600  # run daemon
gitsub lookup <email|subId>    # find user
gitsub rotate <email|subId>    # rotate URL
gitsub status                  # list all users
gitsub settings                # view settings
gitsub settings edit           # change a setting
gitsub webui                   # start web UI manually
gitsub help                    # all commands
```

---

## Settings manager

From the menu → **6 → b** (or `gitsub settings edit`) you can change any setting live:

- Panel URL / API token
- GitHub username, repo, branch
- Switch deploy method (token ↔ SSH)
- GitHub token or SSH key path
- Web UI port, username, password
- Sync interval
- Filename length

After saving, it offers to restart the affected services immediately.

---

## Web Dashboard

Access at `http://YOUR_IP:PORT` (default port 2086).

- Login with the username/password set during install
- Live sync status indicator
- Table of all users with their raw subscription URLs
- **Sync Now** button with live progress
- **Copy URL** per user or **Copy all URLs**
- **Rotate** button per user
- Search/filter by email or sub ID

---

## SSH deploy key — fixing "Permission denied" errors

The most common SSH issue is the wrong host being used. This project uses a **named SSH alias** (`github-gitsub`) in `~/.ssh/config` so it can use a specific key. Make sure:

1. `/root/.ssh/config` contains:
   ```
   Host github-gitsub
       HostName github.com
       User git
       IdentityFile /root/.ssh/gitsub_deploy
       IdentitiesOnly yes
       StrictHostKeyChecking no
   ```
2. The public key (`/root/.ssh/gitsub_deploy.pub`) is added to your repo under **Settings → Deploy keys** with **Allow write access** checked.
3. Test with: `ssh -i /root/.ssh/gitsub_deploy -T git@github.com` — should say "successfully authenticated"

If you get "Could not read from remote repository" after all that, run:
```bash
gitsub settings edit   # change deploy method or key path
# then choose to restart services
```

---

## Nginx + SSL

The installer sets up Nginx and optionally runs Certbot automatically. To do it manually after install:

```bash
apt install certbot python3-certbot-nginx
certbot --nginx -d your.domain.com
```

---

## Logs

```bash
# From the menu → option 5
# Or directly:
tail -f /opt/xui-subsync/logs/sync.log
tail -f /opt/xui-subsync/logs/error.log
journalctl -u xui-subsync -f
journalctl -u xui-webui -f
```

---

## Services

```bash
systemctl status xui-subsync
systemctl status xui-webui
systemctl restart xui-subsync xui-webui
```

---

## Uninstall

```bash
bash /opt/xui-subsync/uninstall.sh
```
