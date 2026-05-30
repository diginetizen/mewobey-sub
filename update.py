import os
import json
import time
import secrets
import string
import subprocess
import requests
from pathlib import Path
from typing import Dict, List, Any, Optional


# =========================
# CONFIG
# =========================

class Config:
    def __init__(self):
        with open("config.json", "r") as f:
            data = json.load(f)

        self.panel_url = data["panel_url"].rstrip("/")
        self.api_token = data["api_token"]

        self.github_username = data["github_username"]
        self.github_repo = data["github_repository"]
        self.branch = data["github_branch"]

        self.filename_length = data.get("filename_length", 32)

        self.timeout = data.get("request_timeout", 20)
        self.retries = data.get("request_retries", 3)


# =========================
# UTIL
# =========================

ALPHABET = string.ascii_letters + string.digits


def random_filename(length: int = 32) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length)) + ".txt"


# =========================
# API CLIENT
# =========================

class XUIClient:
    def __init__(self, config: Config):
        self.config = config

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.config.api_token}"
        }

    def get_clients(self) -> List[Dict[str, Any]]:
        url = f"{self.config.panel_url}/panel/api/clients/list"

        for _ in range(self.config.retries):
            try:
                r = requests.get(
                    url,
                    headers=self._headers(),
                    timeout=self.config.timeout
                )
                data = r.json()

                if data.get("success"):
                    return data.get("obj", [])

            except Exception:
                time.sleep(1)

        return []

    def get_sub_links(self, sub_id: str) -> List[str]:
        url = f"{self.config.panel_url}/panel/api/clients/subLinks/{sub_id}"

        try:
            r = requests.get(
                url,
                headers=self._headers(),
                timeout=self.config.timeout
            )
            data = r.json()

            if data.get("success"):
                return data.get("obj", [])

        except Exception:
            pass

        return []


# =========================
# STORAGE
# =========================

class Storage:
    def __init__(self):
        self.subs_dir = Path("subs")
        self.subs_dir.mkdir(exist_ok=True)

        self.map_file = Path("submap.json")

        if not self.map_file.exists():
            self.map_file.write_text("{}")

    def load_map(self) -> Dict:
        return json.loads(self.map_file.read_text())

    def save_map(self, data: Dict):
        self.map_file.write_text(json.dumps(data, indent=2))

    def write_sub(self, filename: str, links: List[str]):
        path = self.subs_dir / filename
        path.write_text("\n".join(links))

    def delete_file(self, filename: str):
        path = self.subs_dir / filename
        if path.exists():
            path.unlink()


# =========================
# GIT MANAGER
# =========================

class GitManager:
    def commit_and_push(self, message: str):
        subprocess.run(["git", "add", "."], check=False)
        result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)

        if not result.stdout.strip():
            return

        subprocess.run(["git", "commit", "-m", message], check=False)
        subprocess.run(["git", "push", "origin", "main"], check=False)
class SyncEngine:
    def __init__(self, config: Config, api: XUIClient, storage: Storage):
        self.config = config
        self.api = api
        self.storage = storage

        self.map = self.storage.load_map()

    def build_github_url(self, filename: str) -> str:
        return (
            f"https://raw.githubusercontent.com/"
            f"{self.config.github_username}/"
            f"{self.config.github_repo}/"
            f"{self.config.branch}/subs/{filename}"
        )

    def sync(self):
        clients = self.api.get_clients()
        current_subids = set()

        updated_map = self.map.copy()

        # -------------------------
        # Process active clients
        # -------------------------
        for c in clients:
            email = c.get("email")
            sub_id = c.get("subId")

            if not email or not sub_id:
                continue

            current_subids.add(sub_id)

            links = self.api.get_sub_links(sub_id)

            # If no links, skip safely
            if not links:
                continue

            # Existing record?
            existing = updated_map.get(sub_id)

            if existing:
                filename = existing["filename"]
            else:
                filename = random_filename(self.config.filename_length)

            # Write subscription file
            self.storage.write_sub(filename, links)

            github_url = self.build_github_url(filename)

            updated_map[sub_id] = {
                "email": email,
                "filename": filename,
                "github_url": github_url,
                "updated_at": int(time.time())
            }

        # -------------------------
        # Remove deleted users
        # -------------------------
        to_delete = []

        for sub_id in updated_map:
            if sub_id not in current_subids:
                to_delete.append(sub_id)

        for sub_id in to_delete:
            record = updated_map[sub_id]
            self.storage.delete_file(record["filename"])
            del updated_map[sub_id]

        # Save map
        self.storage.save_map(updated_map)
        self.map = updated_map

def run_sync():
    config = Config()
    api = XUIClient(config)
    storage = Storage()

    engine = SyncEngine(config, api, storage)
    engine.sync()

    print("Sync completed successfully.")


def rotate(email: str):
    config = Config()
    api = XUIClient(config)
    storage = Storage()

    data = storage.load_map()

    # find subId by email
    target = None
    for sub_id, info in data.items():
        if info["email"] == email:
            target = sub_id
            break

    if not target:
        print("User not found")
        return

    links = api.get_sub_links(target)

    if not links:
        print("No subscription links found")
        return

    old = data[target]

    # delete old file
    storage.delete_file(old["filename"])

    # new file
    new_file = random_filename(config.filename_length)
    storage.write_sub(new_file, links)

    new_url = f"https://raw.githubusercontent.com/{config.github_username}/{config.github_repo}/{config.branch}/subs/{new_file}"

    data[target]["filename"] = new_file
    data[target]["github_url"] = new_url
    data[target]["rotated_at"] = int(time.time())

    storage.save_map(data)

    print("Rotation completed")


def lookup(email: str):
    storage = Storage()
    data = storage.load_map()

    for sub_id, info in data.items():
        if info["email"] == email:
            print("Email:", email)
            print("SubID:", sub_id)
            print("File:", info["filename"])
            print("URL:", info["github_url"])
            return

    print("User not found")

if __name__ == "__main__":
    import sys

    if len(sys.argv) == 1:
        run_sync()

    elif sys.argv[1] == "rotate":
        rotate(sys.argv[2])

    elif sys.argv[1] == "lookup":
        lookup(sys.argv[2])

    elif sys.argv[1] == "sync":
        run_sync()

    else:
        print("Usage:")
        print("  python update.py sync")
        print("  python update.py rotate email")
        print("  python update.py lookup email")


