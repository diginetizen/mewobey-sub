#!/usr/bin/env python3
"""
gitsub - XUI Subscription Sync Engine
"""

import os
import sys
import json
import time
import hashlib
import secrets
import string
import subprocess
import logging
from pathlib import Path
from datetime import datetime

import requests

# ─────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────

BASE_DIR    = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"
SUBMAP_FILE = BASE_DIR / "submap.json"
SUBS_DIR    = BASE_DIR / "subs"
LOG_DIR     = BASE_DIR / "logs"

LOG_DIR.mkdir(exist_ok=True)
SUBS_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────

log = logging.getLogger("gitsub")
log.setLevel(logging.DEBUG)
_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
for handler, level, path in [
    (logging.FileHandler, logging.DEBUG, LOG_DIR / "sync.log"),
    (logging.FileHandler, logging.ERROR, LOG_DIR / "error.log"),
]:
    h = handler(path)
    h.setLevel(level)
    h.setFormatter(_fmt)
    log.addHandler(h)

_sh = logging.StreamHandler()
_sh.setFormatter(_fmt)
log.addHandler(_sh)

# ─────────────────────────────────────────
# COLORS
# ─────────────────────────────────────────

C  = "\033[0;36m"   # cyan
G  = "\033[0;32m"   # green
Y  = "\033[1;33m"   # yellow
R  = "\033[0;31m"   # red
B  = "\033[1m"      # bold
DIM= "\033[2m"      # dim
RS = "\033[0m"      # reset

def cyan(s):   return f"{C}{s}{RS}"
def green(s):  return f"{G}{s}{RS}"
def yellow(s): return f"{Y}{s}{RS}"
def red(s):    return f"{R}{s}{RS}"
def bold(s):   return f"{B}{s}{RS}"
def dim(s):    return f"{DIM}{s}{RS}"

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────

class Config:
    def __init__(self):
        if not CONFIG_FILE.exists():
            print(red("config.json not found. Run install.sh first."))
            sys.exit(1)
        with open(CONFIG_FILE) as f:
            d = json.load(f)
        self._raw = d
        self.panel_api_url  = d.get("panel_api_url", d.get("panel_url", "")).rstrip("/")
        self.api_token      = d["api_token"]
        self.github_user    = d["github_user"]
        self.github_repo    = d["github_repo"]
        self.github_branch  = d.get("github_branch", "main")
        self.deploy_method  = d.get("deploy_method", "token")
        self.github_token   = d.get("github_token", "")
        self.ssh_key_path   = d.get("ssh_key_path", "/root/.ssh/gitsub_deploy")
        self.filename_length= d.get("filename_length", 32)
        self.sync_interval  = d.get("sync_interval", 21600)
        self.ui_user        = d.get("ui_user", "admin")
        self.ui_pass        = d.get("ui_pass", "")
        self.ui_port        = d.get("ui_port", 2086)
        self.timeout        = 20
        self.retries        = 3

    @property
    def raw_base_url(self):
        return f"https://raw.githubusercontent.com/{self.github_user}/{self.github_repo}/{self.github_branch}/subs"


def save_config(data: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)
    CONFIG_FILE.chmod(0o600)


# ─────────────────────────────────────────
# UTILS
# ─────────────────────────────────────────

ALPHABET = string.ascii_letters + string.digits

def gen_filename(n: int) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(n)) + ".txt"

def hash_content(links: list) -> str:
    return hashlib.sha256("\n".join(links).encode()).hexdigest()

# ─────────────────────────────────────────
# API
# ─────────────────────────────────────────

class API:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def _headers(self):
        return {"Authorization": f"Bearer {self.cfg.api_token}"}

    def _get(self, url: str):
        last_err = None
        for attempt in range(1, self.cfg.retries + 1):
            try:
                r = requests.get(url, headers=self._headers(), timeout=self.cfg.timeout)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                last_err = e
                log.warning(f"Attempt {attempt} failed for {url}: {e}")
                time.sleep(2 * attempt)
        raise RuntimeError(f"All {self.cfg.retries} retries failed: {last_err}")

    def get_clients(self) -> list:
        return self._get(f"{self.cfg.panel_api_url}/panel/api/clients/list").get("obj", [])

    def get_sub_links(self, sub_id: str) -> list:
        return self._get(f"{self.cfg.panel_api_url}/panel/api/clients/subLinks/{sub_id}").get("obj", [])


# ─────────────────────────────────────────
# STORE
# ─────────────────────────────────────────

class Store:
    def load(self) -> dict:
        if not SUBMAP_FILE.exists():
            return {}
        with open(SUBMAP_FILE) as f:
            return json.load(f)

    def save(self, data: dict):
        with open(SUBMAP_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def write_sub(self, filename: str, links: list):
        (SUBS_DIR / filename).write_text("\n".join(links))

    def delete_sub(self, filename: str):
        p = SUBS_DIR / filename
        if p.exists():
            p.unlink()
            log.info(f"Deleted sub file: {filename}")


# ─────────────────────────────────────────
# GIT
# ─────────────────────────────────────────

class Git:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def _run(self, args: list, check=True) -> subprocess.CompletedProcess:
        result = subprocess.run(args, cwd=BASE_DIR, capture_output=True, text=True)
        if check and result.returncode != 0:
            raise RuntimeError(f"git {args[1]}: {result.stderr.strip()}")
        return result

    def _remote_url(self) -> str:
        if self.cfg.deploy_method == "ssh":
            # Use the SSH alias defined in ~/.ssh/config
            return f"git@github-gitsub:{self.cfg.github_user}/{self.cfg.github_repo}.git"
        return f"https://{self.cfg.github_token}@github.com/{self.cfg.github_user}/{self.cfg.github_repo}.git"

    def _ensure_remote(self):
        url = self._remote_url()
        r = self._run(["git", "remote", "get-url", "origin"], check=False)
        if r.returncode != 0:
            self._run(["git", "remote", "add", "origin", url])
        else:
            self._run(["git", "remote", "set-url", "origin", url])

    def pull_rebase(self):
        """Fetch + rebase before push to handle diverged history."""
        try:
            self._run(["git", "fetch", "origin", self.cfg.github_branch])
            result = self._run(
                ["git", "rebase", f"origin/{self.cfg.github_branch}"], check=False
            )
            if result.returncode != 0:
                # Abort rebase and try reset — for the subs-only repo this is safe
                self._run(["git", "rebase", "--abort"], check=False)
                self._run(["git", "reset", "--soft", f"origin/{self.cfg.github_branch}"], check=False)
                log.warning("Rebase conflict resolved with reset")
        except Exception as e:
            log.warning(f"Pull/rebase skipped (may be new repo): {e}")

    def push(self) -> bool:
        self._ensure_remote()
        self._run(["git", "add", "subs/"])
        status = self._run(["git", "status", "--porcelain"], check=False)
        if not status.stdout.strip():
            log.info("Nothing to push")
            return False
        self.pull_rebase()
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        self._run(["git", "commit", "-m", f"sync {ts}"])
        url = self._remote_url()
        result = subprocess.run(
            ["git", "push", url, self.cfg.github_branch],
            cwd=BASE_DIR, capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"Push failed: {result.stderr.strip()}")
        log.info("Git push OK")
        return True


# ─────────────────────────────────────────
# ENGINE
# ─────────────────────────────────────────

class Engine:
    def __init__(self):
        self.cfg   = Config()
        self.api   = API(self.cfg)
        self.store = Store()
        self.git   = Git(self.cfg)

    def sync(self):
        log.info("─── Sync started ───")
        submap  = self.store.load()
        clients = self.api.get_clients()
        log.info(f"Found {len(clients)} clients from panel")

        seen_ids = set()
        new_map  = {}

        for client in clients:
            sub_id = client.get("subId", "").strip()
            email  = client.get("email", "unknown")
            if not sub_id:
                continue
            seen_ids.add(sub_id)

            try:
                links = self.api.get_sub_links(sub_id)
            except Exception as e:
                log.error(f"Failed links for {email}: {e}")
                if sub_id in submap:
                    new_map[sub_id] = submap[sub_id]
                continue

            if not links:
                continue

            old      = submap.get(sub_id)
            filename = old["filename"] if old else gen_filename(self.cfg.filename_length)
            old_hash = old.get("hash") if old else None
            new_hash = hash_content(links)

            if old_hash == new_hash:
                new_map[sub_id] = old
                continue

            self.store.write_sub(filename, links)
            new_map[sub_id] = {
                "email":      email,
                "filename":   filename,
                "hash":       new_hash,
                "raw_url":    f"{self.cfg.raw_base_url}/{filename}",
                "updated":    int(time.time()),
                "updated_ts": datetime.utcnow().isoformat(),
            }
            log.info(f"Updated: {email}")

        for sub_id, v in submap.items():
            if sub_id not in seen_ids:
                self.store.delete_sub(v["filename"])
                log.info(f"Removed: {v.get('email', sub_id)}")

        self.store.save(new_map)

        try:
            self.git.push()
        except Exception as e:
            log.error(f"Git push failed: {e}")

        log.info("─── Sync complete ───")
        return new_map

    def lookup(self, query: str):
        q = query.strip().lower()
        return [
            (k, v) for k, v in self.store.load().items()
            if q in v.get("email", "").lower() or q in k.lower()
        ]

    def rotate(self, query: str):
        submap  = self.store.load()
        q       = query.strip().lower()
        rotated = []
        for sub_id, v in submap.items():
            if q in v.get("email", "").lower() or q in sub_id.lower():
                old_path = SUBS_DIR / v["filename"]
                new_file = gen_filename(Config().filename_length)
                if old_path.exists():
                    (SUBS_DIR / new_file).write_text(old_path.read_text())
                    old_path.unlink()
                v["filename"] = new_file
                v["raw_url"]  = f"{Config().raw_base_url}/{new_file}"
                v["hash"]     = ""
                submap[sub_id] = v
                rotated.append((sub_id, v))
        if rotated:
            self.store.save(submap)
            Git(Config()).push()
        return rotated


# ─────────────────────────────────────────
# SETTINGS MANAGER
# ─────────────────────────────────────────

SETTING_LABELS = {
    "panel_api_url":   "Panel API Base URL",
    "api_token":       "API Token",
    "github_user":     "GitHub Username",
    "github_repo":     "GitHub Repo",
    "github_branch":   "GitHub Branch",
    "deploy_method":   "Deploy Method (token/ssh)",
    "github_token":    "GitHub Personal Access Token",
    "ssh_key_path":    "SSH Key Path",
    "sync_interval":   "Sync Interval (seconds)",
    "ui_port":         "Web UI Port",
    "ui_user":         "Web UI Username",
    "ui_pass":         "Web UI Password",
    "filename_length": "Filename Length",
}

def show_settings():
    if not CONFIG_FILE.exists():
        print(red("config.json not found."))
        return
    with open(CONFIG_FILE) as f:
        cfg = json.load(f)
    print(f"\n{bold('Current Settings')}  ({dim(str(CONFIG_FILE))})\n")
    for i, (key, label) in enumerate(SETTING_LABELS.items(), 1):
        val = cfg.get(key, dim("(not set)"))
        # Mask passwords/tokens
        if key in ("api_token", "github_token", "ui_pass") and val:
            val = val[:4] + "●●●●●●●●" if len(str(val)) > 4 else "●●●●"
        print(f"  {dim(str(i).rjust(2))}  {cyan(label):<38} {val}")
    print()

def edit_settings():
    if not CONFIG_FILE.exists():
        print(red("config.json not found."))
        return
    with open(CONFIG_FILE) as f:
        cfg = json.load(f)

    keys   = list(SETTING_LABELS.keys())
    labels = list(SETTING_LABELS.values())

    print(f"\n{bold('Edit Settings')} — which do you want to change?\n")
    for i, label in enumerate(labels, 1):
        key = keys[i-1]
        val = cfg.get(key, "")
        if key in ("api_token", "github_token", "ui_pass") and val:
            val = val[:4] + "●●●"
        print(f"  {cyan(str(i).rjust(2))}  {label:<38} {dim(str(val))}")

    print(f"  {cyan('0')}  Cancel")
    print()

    raw = input("  Choose number: ").strip()
    if not raw.isdigit() or int(raw) == 0 or int(raw) > len(keys):
        print("Cancelled.")
        return

    idx = int(raw) - 1
    key = keys[idx]
    label = labels[idx]

    current = cfg.get(key, "")
    print(f"\n  Changing: {bold(label)}")
    print(f"  Current:  {dim(str(current))}\n")

    if key in ("api_token", "github_token", "ui_pass"):
        import getpass
        new_val = getpass.getpass(f"  New value (hidden): ")
    else:
        new_val = input(f"  New value: ").strip()

    if not new_val:
        print("  No change (empty input).")
        return

    # Type coerce for numeric fields
    if key in ("sync_interval", "ui_port", "filename_length"):
        try:
            new_val = int(new_val)
        except ValueError:
            print(red("  Must be a number."))
            return

    cfg[key] = new_val
    save_config(cfg)
    print(green(f"\n  Saved. Restart services for changes to take effect."))

    # Offer restart
    print(f"\n  Restart services now?")
    print(f"  {cyan('1')}  Restart both (sync + webui)")
    print(f"  {cyan('2')}  Restart sync daemon only")
    print(f"  {cyan('3')}  Restart web UI only")
    print(f"  {cyan('0')}  No restart")
    choice = input("\n  Choose: ").strip()
    if choice == "1":
        subprocess.run(["systemctl", "restart", "xui-subsync", "xui-webui"], check=False)
        print(green("  Services restarted."))
    elif choice == "2":
        subprocess.run(["systemctl", "restart", "xui-subsync"], check=False)
        print(green("  Sync daemon restarted."))
    elif choice == "3":
        subprocess.run(["systemctl", "restart", "xui-webui"], check=False)
        print(green("  Web UI restarted."))


# ─────────────────────────────────────────
# INTERACTIVE MENU
# ─────────────────────────────────────────

def interactive_menu():
    # Box width in visible chars (not counting ANSI codes)
    W = 44  # inner width between ║ borders including spaces

    def pad(text, visible_len, total=W):
        """Pad text so the visible portion fills total chars."""
        # Strip ANSI to measure visible length
        import re
        ansi_re = re.compile(r'\x1b\[[0-9;]*m')
        visible = len(ansi_re.sub('', text))
        extra   = visible_len - visible
        return text + " " * max(0, extra)

    def row(content, content_visible_len):
        # content should fit in W-2 chars (leaving '  ' prefix and ' ║' suffix handled)
        padding = W - 2 - content_visible_len
        return f"\033[1m║\033[0m  {content}{' ' * max(0, padding)}\033[1m║\033[0m"

    def blank():
        return f"\033[1m║\033[0m{' ' * W}\033[1m║\033[0m"

    def svc_status(name):
        r = subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True)
        s = r.stdout.strip()
        return (green("● " + s), len("● " + s)) if s == "active" else (dim("○ " + s), len("○ " + s))

    while True:
        sync_colored, sync_vlen = svc_status("xui-subsync")
        ui_colored,   ui_vlen   = svc_status("xui-webui")

        # Build status lines manually so padding is right
        # "  sync   " + status + padding to W-2
        sync_prefix = "Services:  sync  "
        sync_pad = W - 2 - len(sync_prefix) - sync_vlen
        sync_line = f"\033[1m║\033[0m  {sync_prefix}{sync_colored}{' ' * max(0, sync_pad)}\033[1m║\033[0m"

        ui_prefix = "           webui "
        ui_pad = W - 2 - len(ui_prefix) - ui_vlen
        ui_line = f"\033[1m║\033[0m  {ui_prefix}{ui_colored}{' ' * max(0, ui_pad)}\033[1m║\033[0m"

        def mrow(num, label):
            # num is cyan, label is plain
            content = f"\033[0;36m{num}\033[0m  {label}"
            visible = len(num) + 2 + len(label)
            pad = W - 2 - visible
            return f"\033[1m║\033[0m  {content}{' ' * max(0, pad)}\033[1m║\033[0m"

        print()
        print(bold("╔" + "═" * W + "╗"))
        print(bold("║") + f"  {cyan('gitsub')} — XUI Subscription Sync" + " " * (W - 29) + bold("║"))
        print(bold("╠" + "═" * W + "╣"))
        print(sync_line)
        print(ui_line)
        print(bold("╠" + "═" * W + "╣"))
        print(blank())
        print(mrow("1", "Sync now (manual run)"))
        print(mrow("2", "Show all users & URLs"))
        print(mrow("3", "Lookup user by email / sub ID"))
        print(mrow("4", "Rotate user URL"))
        print(mrow("5", "View file map (all subs)"))
        print(mrow("6", "View logs (live)"))
        print(mrow("7", "Settings — view & change"))
        print(mrow("8", "Restart services"))
        print(mrow("9", "Service status details"))
        print(mrow("0", "Exit"))
        print(blank())
        print(bold("╚" + "═" * W + "╝"))
        print()

        choice = input("  Choose [0-9]: ").strip()

        if choice == "0":
            break

        elif choice == "1":
            print()
            try:
                result = Engine().sync()
                print(green(f"\n  Sync done — {len(result)} users."))
            except Exception as e:
                print(red(f"\n  Sync error: {e}"))
            input("\n  Press ENTER to continue...")

        elif choice == "2":
            submap = Store().load()
            if not submap:
                print(yellow("\n  No users yet. Run a sync first."))
            else:
                print(f"\n  {bold('Users')}  ({len(submap)} total)\n")
                print(f"  {'Email':<35} {'Raw URL'}")
                print(f"  {'-'*35} {'-'*60}")
                for sub_id, v in sorted(submap.items(), key=lambda x: x[1].get("email", "")):
                    print(f"  {v.get('email', '?'):<35} {dim(v.get('raw_url', '—'))}")
            input("\n  Press ENTER to continue...")

        elif choice == "3":
            q = input("\n  Email or sub ID to search: ").strip()
            if q:
                results = Engine().lookup(q)
                if not results:
                    print(yellow("  Not found."))
                for sub_id, v in results:
                    print(f"\n  Email    : {v.get('email')}")
                    print(f"  Sub ID   : {sub_id}")
                    print(f"  File     : {v.get('filename')}")
                    print(f"  URL      : {cyan(v.get('raw_url', '—'))}")
                    print(f"  Updated  : {v.get('updated_ts', '—')}")
            input("\n  Press ENTER to continue...")

        elif choice == "4":
            q = input("\n  Email or sub ID to rotate: ").strip()
            if q:
                confirm = input(f"  Rotate URL for '{q}'? Their link will change. [y/n]: ").strip()
                if confirm == "y":
                    results = Engine().rotate(q)
                    if not results:
                        print(yellow("  Not found."))
                    for _, v in results:
                        print(green(f"\n  Rotated: {v.get('email')} → {v.get('raw_url')}"))
            input("\n  Press ENTER to continue...")

        elif choice == "5":
            # File map
            submap = Store().load()
            if not submap:
                print(yellow("\n  No subs yet. Run a sync first."))
            else:
                cfg = Config()
                print(f"\n  {bold('File Map')}  ({len(submap)} subs in {SUBS_DIR})\n")
                print(f"  {'Email':<30} {'File':<36} {'Updated'}")
                print(f"  {'-'*30} {'-'*36} {'-'*20}")
                for sub_id, v in sorted(submap.items(), key=lambda x: x[1].get("email", "")):
                    fpath = SUBS_DIR / v.get("filename", "")
                    exists = green("✓") if fpath.exists() else red("✗")
                    size   = f"{fpath.stat().st_size}B" if fpath.exists() else "missing"
                    ts     = v.get("updated_ts", "—")[:16] if v.get("updated_ts") else "—"
                    print(f"  {v.get('email','?'):<30} {exists} {v.get('filename','?'):<34} {dim(ts)}")
                print(f"\n  {dim('Repo subs dir: ' + str(SUBS_DIR))}")
                print(f"  {dim('Raw base URL : ' + cfg.raw_base_url)}")
            input("\n  Press ENTER to continue...")

        elif choice == "6":
            print(f"\n  {dim('Press Ctrl+C to stop')}\n")
            try:
                subprocess.run(["tail", "-f", str(LOG_DIR / "sync.log")])
            except KeyboardInterrupt:
                pass

        elif choice == "7":
            print(f"\n  {cyan('a')}  View settings")
            print(f"  {cyan('b')}  Edit a setting")
            print(f"  {cyan('0')}  Back")
            sub = input("\n  Choose: ").strip()
            if sub == "a":
                show_settings()
                input("\n  Press ENTER to continue...")
            elif sub == "b":
                edit_settings()
                input("\n  Press ENTER to continue...")

        elif choice == "8":
            print(f"\n  {cyan('1')}  Restart both")
            print(f"  {cyan('2')}  Restart sync daemon")
            print(f"  {cyan('3')}  Restart web UI")
            print(f"  {cyan('0')}  Back")
            sub = input("\n  Choose: ").strip()
            if sub == "1":
                subprocess.run(["systemctl", "restart", "xui-subsync", "xui-webui"], check=False)
                print(green("  Restarted both services."))
            elif sub == "2":
                subprocess.run(["systemctl", "restart", "xui-subsync"], check=False)
                print(green("  Sync daemon restarted."))
            elif sub == "3":
                subprocess.run(["systemctl", "restart", "xui-webui"], check=False)
                print(green("  Web UI restarted."))
            input("\n  Press ENTER to continue...")

        elif choice == "9":
            subprocess.run(["systemctl", "status", "xui-subsync", "xui-webui", "--no-pager"])
            input("\n  Press ENTER to continue...")

        else:
            print(yellow("  Unknown choice."))


# ─────────────────────────────────────────
# DAEMON
# ─────────────────────────────────────────

def run_daemon(interval: int):
    log.info(f"Daemon started — interval: {interval}s")
    while True:
        try:
            Engine().sync()
        except Exception as e:
            log.error(f"Sync error: {e}")
        log.info(f"Next sync in {interval}s")
        time.sleep(interval)


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]

    # No args → interactive menu
    if not args:
        interactive_menu()

    elif args[0] == "sync":
        Engine().sync()

    elif args[0] == "daemon":
        interval = 21600
        if "--interval" in args:
            idx = args.index("--interval")
            interval = int(args[idx + 1])
        run_daemon(interval)

    elif args[0] == "lookup":
        if len(args) < 2:
            print("Usage: gitsub lookup <email or subId>")
            sys.exit(1)
        for sub_id, v in Engine().lookup(args[1]):
            print(f"\n  Email   : {v.get('email')}")
            print(f"  Sub ID  : {sub_id}")
            print(f"  URL     : {v.get('raw_url')}")
            print(f"  Updated : {v.get('updated_ts', '—')}")

    elif args[0] == "rotate":
        if len(args) < 2:
            print("Usage: gitsub rotate <email or subId>")
            sys.exit(1)
        for _, v in Engine().rotate(args[1]):
            print(f"  Rotated {v.get('email')} → {v.get('raw_url')}")

    elif args[0] == "status":
        submap = Store().load()
        print(f"\n  Total users: {len(submap)}")
        for sub_id, v in submap.items():
            print(f"  • {v.get('email','?'):<35} {v.get('raw_url','—')}")

    elif args[0] == "settings":
        if len(args) > 1 and args[1] == "edit":
            edit_settings()
        else:
            show_settings()

    elif args[0] == "webui":
        os.execv(sys.executable, [sys.executable, str(BASE_DIR / "webui.py")])

    elif args[0] in ("help", "--help", "-h"):
        print(f"""
{bold('gitsub')} — XUI Subscription Sync

  {cyan('gitsub')}                      interactive menu
  {cyan('gitsub sync')}                 sync now
  {cyan('gitsub daemon')}               run as background daemon
  {cyan('gitsub daemon --interval N')}  set interval to N seconds
  {cyan('gitsub lookup')} <email|id>    find a user
  {cyan('gitsub rotate')} <email|id>    rotate URL
  {cyan('gitsub status')}               list all users
  {cyan('gitsub settings')}             view settings
  {cyan('gitsub settings edit')}        change a setting
  {cyan('gitsub webui')}                start web dashboard
  {cyan('gitsub help')}                 this help
""")

    else:
        print(f"Unknown command: {args[0]}\nRun 'gitsub help' for usage.")
        sys.exit(1)
