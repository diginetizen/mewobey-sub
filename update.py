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

        self.panel_url = d.get("panel_url", "").rstrip("/")
        self.filename_length = d.get("filename_length", 32)


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
        return {"Authorization": "Bearer " + os.getenv("XUI_TOKEN", "")}

    def clients(self):
        r = requests.get(self.c.panel_url + "/panel/api/clients/list",
                         headers=self.headers(), timeout=20)
        return r.json().get("obj", [])

    def subs(self, sub_id):
        r = requests.get(
            self.c.panel_url + f"/panel/api/clients/subLinks/{sub_id}",
            headers=self.headers(),
            timeout=20
        )
        return r.json().get("obj", [])


# =========================
# STORAGE
# =========================

class Store:
    def __init__(self):
        os.makedirs("subs", exist_ok=True)
        if not os.path.exists("submap.json"):
            open("submap.json", "w").write("{}")

    def load(self):
        return json.load(open("submap.json"))

    def save(self, data):
        json.dump(data, open("submap.json", "w"), indent=2)

    def write(self, fn, links):
        open("subs/" + fn, "w").write("\n".join(links))

    def delete(self, fn):
        try:
            os.remove("subs/" + fn)
        except:
            pass


# =========================
# ENGINE
# =========================

class Engine:
    def __init__(self):
        self.c = Config()
        self.api = API(self.c)
        self.store = Store()
        self.map = self.store.load()

    def sync(self):
        clients = self.api.clients()

        seen = set()
        new_map = {}

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
            else:
                fn = gen_filename()

            new_hash = hash_content(links)

            if old and old.get("hash") == new_hash:
                new_map[sub_id] = old
                continue

            self.store.write(fn, links)

            new_map[sub_id] = {
                "email": email,
                "filename": fn,
                "github_url": f"https://raw.githubusercontent.com/{os.getenv('GIT_USER')}/{os.getenv('GIT_REPO')}/main/subs/{fn}",
                "hash": new_hash,
                "updated": int(time.time())
            }

        # delete removed
        for k in self.map:
            if k not in seen:
                self.store.delete(self.map[k]["filename"])

        self.map = new_map
        self.store.save(self.map)

        print("SYNC DONE")


# =========================
# DAEMON
# =========================

def daemon(interval=21600):
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
    if len(sys.argv) > 1 and sys.argv[1] == "daemon":
        interval = int(sys.argv[3]) if len(sys.argv) > 3 else 21600
        daemon(interval)
    else:
        Engine().sync()
