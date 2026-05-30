import os
import json
import time
import hashlib
import secrets
import string
import subprocess
import requests
import sys
from typing import Dict, List


# =========================
# CONFIG
# =========================

class Config:
    def __init__(self):
        with open("config.json") as f:
            d = json.load(f)

        self.panel_url = d["panel_url"].rstrip("/")
        self.api_token = d["api_token"]
        self.repo = d["github_repository"]
        self.user = d["github_username"]
        self.branch = d["github_branch"]

        self.filename_length = d.get("filename_length", 32)
        self.timeout = d.get("request_timeout", 20)
        self.retries = d.get("request_retries", 3)


# =========================
# UTIL
# =========================

ALPHABET = string.ascii_letters + string.digits


def gen_filename(n=32):
    return "".join(secrets.choice(ALPHABET) for _ in range(n)) + ".txt"


def hash_content(data: List[str]) -> str:
    return hashlib.sha256("\n".join(data).encode()).hexdigest()


# =========================
# API
# =========================

class API:
    def __init__(self, c: Config):
        self.c = c

    def headers(self):
        return {"Authorization": f"Bearer {self.c.api_token}"}

    def clients(self):
        url = f"{self.c.panel_url}/panel/api/clients/list"
        r = requests.get(url, headers=self.headers(), timeout=self.c.timeout)
        return r.json().get("obj", [])

    def subs(self, sub_id):
        url = f"{self.c.panel_url}/panel/api/clients/subLinks/{sub_id}"
        r = requests.get(url, headers=self.headers(), timeout=self.c.timeout)
        return r.json().get("obj", [])


# =========================
# STORAGE
# =========================

class Store:
    def __init__(self):
        self.map_file = "submap.json"
        self.subs_dir = "subs"

        os.makedirs(self.subs_dir, exist_ok=True)

        if not os.path.exists(self.map_file):
            with open(self.map_file, "w") as f:
                json.dump({}, f)

    def load(self):
        return json.load(open(self.map_file))

    def save(self, data):
        json.dump(data, open(self.map_file, "w"), indent=2)

    def write(self, fn, links):
        open(f"{self.subs_dir}/{fn}", "w").write("\n".join(links))

    def delete(self, fn):
        try:
            os.remove(f"{self.subs_dir}/{fn}")
        except:
            pass


# =========================
# GIT
# =========================

class Git:
    def commit(self, msg):
        subprocess.call(["git", "add", "."])
        status = subprocess.getoutput("git status --porcelain")

        if not status.strip():
            return

        subprocess.call(["git", "commit", "-m", msg])
        subprocess.call(["git", "push", "origin", "main"])


# =========================
# ENGINE
# =========================

class Engine:
    def __init__(self):
        self.c = Config()
        self.api = API(self.c)
        self.store = Store()
        self.git = Git()

        self.map = self.store.load()

    def sync(self):
        clients = self.api.clients()

        seen = set()
        updated = {}

        for c in clients:
            email = c.get("email")
            sub_id = c.get("subId")

            if not sub_id:
                continue

            seen.add(sub_id)

            links = self.api.subs(sub_id)
            if not links:
                continue

            old = self.map.get(sub_id)

            if old:
                fn = old["filename"]
                old_hash = old.get("hash")
            else:
                fn = gen_filename(self.c.filename_length)
                old_hash = None

            new_hash = hash_content(links)

            # skip if no change
            if old_hash == new_hash:
                updated[sub_id] = old
                continue

            self.store.write(fn, links)

            url = f"https://raw.githubusercontent.com/{self.c.user}/{self.c.repo}/{self.c.branch}/subs/{fn}"

            updated[sub_id] = {
                "email": email,
                "filename": fn,
                "github_url": url,
                "hash": new_hash,
                "updated": int(time.time())
            }

        # delete removed users
        for k in list(self.map.keys()):
            if k not in seen:
                self.store.delete(self.map[k]["filename"])

        self.map = updated
        self.store.save(self.map)

        self.git.commit("sync subscriptions")

        print("sync done")


# =========================
# DAEMON
# =========================

def daemon(interval=21600):
    while True:
        try:
            Engine().sync()
        except Exception as e:
            print("error:", e)

        time.sleep(interval)


# =========================
# CLI
# =========================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        Engine().sync()

    elif sys.argv[1] == "daemon":
        interval = int(sys.argv[3]) if len(sys.argv) > 3 else 21600
        daemon(interval)

    elif sys.argv[1] == "sync":
        Engine().sync()

    elif sys.argv[1] == "lookup":
        email = sys.argv[2]
        data = json.load(open("submap.json"))

        for k, v in data.items():
            if v["email"] == email or k == email:
                print(v)
                break
