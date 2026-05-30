import os
import json
import time
import hashlib
import secrets
import string
import subprocess
import requests
import sys


# =========================
# CONFIG
# =========================

class Config:
    def __init__(self):
        with open("config.json", "r") as f:
            d = json.load(f)

        self.panel_url = d["panel_url"].rstrip("/")
        self.api_token = d["api_token"]

        self.github_user = d["github_user"]
        self.github_repo = d["github_repo"]
        self.github_token = d["github_token"]
        self.github_branch = d.get("github_branch", "main")

        self.filename_length = d.get("filename_length", 32)
        self.sync_interval = d.get("sync_interval", 21600)

        self.timeout = 20
        self.retries = 3


# =========================
# UTIL
# =========================

ALPHABET = string.ascii_letters + string.digits


def gen_filename(n):
    return "".join(secrets.choice(ALPHABET) for _ in range(n)) + ".txt"


def hash_links(links):
    return hashlib.sha256("\n".join(links).encode()).hexdigest()


# =========================
# API
# =========================

class API:
    def __init__(self, c: Config):
        self.c = c

    def headers(self):
        return {"Authorization": f"Bearer {self.c.api_token}"}

    def get_clients(self):
        url = f"{self.c.panel_url}/panel/api/clients/list"
        r = requests.get(url, headers=self.headers(), timeout=self.c.timeout)
        return r.json().get("obj", [])

    def get_sub(self, sub_id):
        url = f"{self.c.panel_url}/panel/api/clients/subLinks/{sub_id}"
        r = requests.get(url, headers=self.headers(), timeout=self.c.timeout)
        return r.json().get("obj", [])


# =========================
# STORAGE
# =========================

class Store:
    def __init__(self):
        self.map_file = "submap.json"
        self.sub_dir = "subs"

        os.makedirs(self.sub_dir, exist_ok=True)

        if not os.path.exists(self.map_file):
            json.dump({}, open(self.map_file, "w"))

    def load(self):
        return json.load(open(self.map_file))

    def save(self, data):
        json.dump(data, open(self.map_file, "w"), indent=2)

    def write_file(self, name, links):
        open(f"{self.sub_dir}/{name}", "w").write("\n".join(links))

    def delete_file(self, name):
        try:
            os.remove(f"{self.sub_dir}/{name}")
        except:
            pass


# =========================
# GIT (HTTPS TOKEN)
# =========================

class Git:
    def __init__(self, c: Config):
        self.c = c

    def push(self):
        subprocess.call(["git", "add", "."])

        status = subprocess.getoutput("git status --porcelain")
        if not status.strip():
            return

        subprocess.call(["git", "commit", "-m", "auto sync"])

        url = f"https://{self.c.github_token}@github.com/{self.c.github_user}/{self.c.github_repo}.git"

        subprocess.call(["git", "push", url, self.c.github_branch])


# =========================
# ENGINE
# =========================

class Engine:
    def __init__(self):
        self.c = Config()
        self.api = API(self.c)
        self.store = Store()
        self.git = Git(self.c)
        self.map = self.store.load()

    def sync(self):
        clients = self.api.get_clients()

        seen = set()
        new_map = {}

        for c in clients:
            sub_id = c.get("subId")
            email = c.get("email")

            if not sub_id:
                continue

            seen.add(sub_id)

            links = self.api.get_sub(sub_id)
            if not links:
                continue

            old = self.map.get(sub_id)

            if old:
                filename = old["filename"]
                old_hash = old.get("hash")
            else:
                filename = gen_filename(self.c.filename_length)
                old_hash = None

            new_hash = hash_links(links)

            if old_hash == new_hash:
                new_map[sub_id] = old
                continue

            self.store.write_file(filename, links)

            new_map[sub_id] = {
                "email": email,
                "filename": filename,
                "hash": new_hash,
                "updated": int(time.time())
            }

        # delete removed users
        for k in list(self.map.keys()):
            if k not in seen:
                self.store.delete_file(self.map[k]["filename"])

        self.map = new_map
        self.store.save(self.map)

        self.git.push()
        print("SYNC DONE")


# =========================
# DAEMON
# =========================

def daemon(interval):
    while True:
        try:
            Engine().sync()
        except Exception as e:
            print("ERROR:", e)

        time.sleep(interval)


# =========================
# CLI
# =========================

if __name__ == "__main__":

    if len(sys.argv) < 2:
        Engine().sync()

    elif sys.argv[1] == "sync":
        Engine().sync()

    elif sys.argv[1] == "daemon":
        interval = int(sys.argv[3]) if len(sys.argv) > 3 else 21600
        daemon(interval)
