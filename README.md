# XUI Subscription Sync System

A production-ready automation tool that syncs 3x-ui v3 subscriptions to GitHub-hosted files. Each client gets a unique static subscription link via GitHub Raw.

## Features
- Auto-fetch clients from 3x-ui API
- Generates secure 32-character filenames
- Stores subscriptions in `/subs`
- Auto sync with change detection (no duplicate commits)
- Removes deleted users automatically
- Supports rotation of subscription links
- Lookup by email or subId
- Runs as daemon or systemd service
- GitHub Raw hosting support

## Project Structure
```
subs/
logs/
update.py
config.json
submap.json
install.sh
requirements.txt
```

## Installation

```bash
git clone git@github.com:diginetizen/mewobey-sub.git
cd mewobey-sub
bash install.sh
```

Installer will ask:
- 3x-ui panel URL
- API token
- GitHub repo info
- sync mode (daemon recommended)
- sync interval

## Usage

### Manual sync
```bash
python update.py sync
```

### Daemon mode (recommended)
```bash
python update.py daemon --interval 21600
```

(21600 = 6 hours)

Test mode:
```bash
python update.py daemon --interval 120
```

## Lookup
```bash
python update.py lookup user@example.com
```

## Rotate subscription
```bash
python update.py rotate user@example.com
```

## Systemd Service
```bash
systemctl start xui-subsync
systemctl enable xui-subsync
systemctl status xui-subsync
```

Logs:
```bash
journalctl -u xui-subsync -f
```

## Security
- config.json is not uploaded to GitHub
- submap.json is stored locally only
- API tokens are never exposed
- filenames contain no user info

## Example Output

Subscription file content:
```
vless://...
vmess://...
trojan://...
```

Public link:
```
https://raw.githubusercontent.com/diginetizen/mewobey-sub/main/subs/FILE.txt
```
