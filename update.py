#!/usr/bin/env python3
"""
gitsub - XUI Subscription Sync Engine
Syncs 3x-ui client subscriptions to GitHub-hosted files.
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
import requests
from pathlib import Path
from datetime import datetime

# ─────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"
SUBMAP_FILE = BASE_DIR / "submap.json"
SUBS_DIR = BASE_DIR / "subs"
LOG_DIR = BASE_DIR / "logs"

# ─────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────

LOG_DIR.mkdir(exist_ok=True)
SUBS_DIR.mkdir(exist_ok=True)

log = logging.getLogger("gitsub")
log.setLevel(logging.DEBUG)

_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")

_fh = logging.FileHandler(LOG_DIR / "sync.log")
_fh.setFormatter(_fmt)
log.addHandler(_fh)

_eh = logging.FileHandler(LOG_DIR / "error.log")
_eh.setLevel(logging.ERROR)
_eh.setFormatter(_fmt)
log.addHandler(_eh)

_sh = logging.StreamHandler()
_sh.setFormatter(_fmt)
log.addHandler(_sh)


# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────

class Config:
    def __init__(self):
        if not CONFIG_FILE.exists():
            print("ERROR: config.json not found. Run install.sh first.")
            sys.exit(1)

        with open(CONFIG_FILE) as f:
            d = json.load(f)

        self.panel_url     = d["panel_url"].rstrip("/")
        self.api_token     = d["api_token"]

        self.github_user   = d["github_user"]
        self.github_repo   = d["github_repo"]
        self.github_branch = d.get("github_branch", "main")

        # deploy method: "token" or "ssh"
        self.deploy_method = d.get("deploy_method", "token")
        self.github_token  = d.get("github_token", "")

        self.filename_length = d.get("filename_length", 32)
        self.sync_interval   = d.get("sync_interval", 21600)

        self.timeout = 20
        self.retries = 3

    @property
    def raw_base_url(self):
        return f"https://raw.githubusercontent.com/{self.github_user}/{self.github_repo}/{self.github_branch}/subs"


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
        raise RuntimeError(f"All {self.cfg.retries} attempts failed: {last_err}")

    def get_clients(self) -> list:
        data = self._get(f"{self.cfg.panel_url}/panel/api/clients/list")
        return data.get("obj", [])

    def get_sub_links(self, sub_id: str) -> list:
        data = self._get(f"{self.cfg.panel_url}/panel/api/clients/subLinks/{sub_id}")
        return data.get("obj", [])


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
            raise RuntimeError(f"git {args[1]} failed: {result.stderr.strip()}")
        return result

    def _remote_url(self) -> str:
        if self.cfg.deploy_method == "ssh":
            return f"git@github.com:{self.cfg.github_user}/{self.cfg.github_repo}.git"
        else:
            return f"https://{self.cfg.github_token}@github.com/{self.cfg.github_user}/{self.cfg.github_repo}.git"

    def _ensure_remote(self):
        """Make sure the remote is set correctly."""
        result = self._run(["git", "remote", "get-url", "origin"], check=False)
        url = self._remote_url()
        if result.returncode != 0:
            self._run(["git", "remote", "add", "origin", url])
        else:
            self._run(["git", "remote", "set-url", "origin", url])

    def pull_rebase(self):
        """Pull remote changes before pushing to avoid diverged history."""
        try:
            self._run(["git", "fetch", "origin", self.cfg.github_branch])
            self._run(["git", "rebase", f"origin/{self.cfg.github_branch}"], check=False)
            log.info("Git pull/rebase OK")
        except Exception as e:
            log.warning(f"Rebase skipped (may be new repo): {e}")

    def push(self) -> bool:
        """Stage, commit, and push all changes. Returns True if something was pushed."""
        self._ensure_remote()

        self._run(["git", "add", "subs/"])

        status = self._run(["git", "status", "--porcelain"], check=False)
        if not status.stdout.strip():
            log.info("Nothing to push (no changes)")
            return False

        self.pull_rebase()

        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        self._run(["git", "commit", "-m", f"auto sync {ts}"])

        url = self._remote_url()
        result = subprocess.run(
            ["git", "push", url, self.cfg.github_branch],
            cwd=BASE_DIR,
            capture_output=True,
            text=True
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
        submap = self.store.load()
        clients = self.api.get_clients()
        log.info(f"Found {len(clients)} clients from panel")

        seen_ids = set()
        new_map = {}

        for client in clients:
            sub_id = client.get("subId", "").strip()
            email  = client.get("email", "unknown")

            if not sub_id:
                continue

            seen_ids.add(sub_id)

            try:
                links = self.api.get_sub_links(sub_id)
            except Exception as e:
                log.error(f"Failed to fetch links for {email} ({sub_id}): {e}")
                if sub_id in submap:
                    new_map[sub_id] = submap[sub_id]
                continue

            if not links:
                log.warning(f"No links for {email} ({sub_id}), skipping")
                continue

            old = submap.get(sub_id)
            filename = old["filename"] if old else gen_filename(self.cfg.filename_length)
            old_hash = old.get("hash") if old else None
            new_hash = hash_content(links)

            if old_hash == new_hash:
                new_map[sub_id] = old
                log.debug(f"No change for {email}")
                continue

            self.store.write_sub(filename, links)
            raw_url = f"{self.cfg.raw_base_url}/{filename}"

            new_map[sub_id] = {
                "email":      email,
                "filename":   filename,
                "hash":       new_hash,
                "raw_url":    raw_url,
                "updated":    int(time.time()),
                "updated_ts": datetime.utcnow().isoformat()
            }
            log.info(f"Updated: {email} → {filename}")

        # Remove deleted clients
        for sub_id in list(submap.keys()):
            if sub_id not in seen_ids:
                self.store.delete_sub(submap[sub_id]["filename"])
                log.info(f"Removed deleted client: {submap[sub_id].get('email', sub_id)}")

        self.store.save(new_map)

        try:
            self.git.push()
        except Exception as e:
            log.error(f"Git push failed: {e}")

        log.info("─── Sync complete ───")
        return new_map

    def lookup(self, query: str):
        submap = self.store.load()
        query = query.strip().lower()
        results = []
        for sub_id, v in submap.items():
            if query in v.get("email", "").lower() or query in sub_id.lower():
                results.append((sub_id, v))
        return results

    def rotate(self, query: str):
        submap = self.store.load()
        query = query.strip().lower()
        rotated = []
        for sub_id, v in submap.items():
            if query in v.get("email", "").lower() or query in sub_id.lower():
                old_file = v["filename"]
                new_file = gen_filename(self.cfg.filename_length)
                # rename file content
                old_path = SUBS_DIR / old_file
                if old_path.exists():
                    content = old_path.read_text()
                    (SUBS_DIR / new_file).write_text(content)
                    old_path.unlink()
                v["filename"] = new_file
                v["raw_url"]  = f"{self.cfg.raw_base_url}/{new_file}"
                v["hash"]     = ""  # force re-push
                submap[sub_id] = v
                rotated.append((sub_id, v))
        self.store.save(submap)
        if rotated:
            self.git.push()
        return rotated


# ─────────────────────────────────────────
# DAEMON
# ─────────────────────────────────────────

def run_daemon(interval: int):
    log.info(f"Daemon started (interval: {interval}s)")
    while True:
        try:
            Engine().sync()
        except Exception as e:
            log.error(f"Sync error: {e}")
        log.info(f"Next sync in {interval}s")
        time.sleep(interval)


# ─────────────────────────────────────────
# CLI HELP
# ─────────────────────────────────────────

HELP = """
╔═══════════════════════════════════════════════╗
║          gitsub — XUI Subscription Sync       ║
╠═══════════════════════════════════════════════╣
║  Commands:                                    ║
║                                               ║
║  gitsub sync                sync now          ║
║  gitsub daemon              run as daemon     ║
║  gitsub daemon --interval N set sync every Ns ║
║  gitsub lookup <email|id>   find a user       ║
║  gitsub rotate <email|id>   rotate URL        ║
║  gitsub status              show submap stats ║
║  gitsub webui               start web UI      ║
║  gitsub help                show this         ║
╠═══════════════════════════════════════════════╣
║  Management:                                  ║
║                                               ║
║  bash install.sh            install           ║
║  bash uninstall.sh          uninstall         ║
╚═══════════════════════════════════════════════╝
"""


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]

    if not args or args[0] in ("help", "--help", "-h"):
        print(HELP)

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
        results = Engine().lookup(args[1])
        if not results:
            print("Not found.")
        for sub_id, v in results:
            print(f"\n  Email   : {v.get('email')}")
            print(f"  SubID   : {sub_id}")
            print(f"  URL     : {v.get('raw_url')}")
            print(f"  Updated : {v.get('updated_ts', 'N/A')}")

    elif args[0] == "rotate":
        if len(args) < 2:
            print("Usage: gitsub rotate <email or subId>")
            sys.exit(1)
        results = Engine().rotate(args[1])
        if not results:
            print("Not found.")
        for sub_id, v in results:
            print(f"  Rotated: {v.get('email')} → new URL: {v.get('raw_url')}")

    elif args[0] == "status":
        submap = Store().load()
        print(f"\n  Total users: {len(submap)}")
        for sub_id, v in submap.items():
            print(f"  • {v.get('email', sub_id):30s}  {v.get('raw_url', 'N/A')}")

    elif args[0] == "webui":
        os.execv(sys.executable, [sys.executable, str(BASE_DIR / "webui.py")])

    else:
        print(f"Unknown command: {args[0]}")
        print(HELP)
        sys.exit(1)
