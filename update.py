#!/usr/bin/env python3
"""gitsub — XUI Subscription Sync Engine"""

import os, sys, json, time, hashlib, secrets, string, subprocess, logging, re
from pathlib import Path
from datetime import datetime
import requests

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"
SUBMAP_FILE = BASE_DIR / "submap.json"
LOG_DIR     = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# ── Logging ────────────────────────────────────────────────────────────────
log = logging.getLogger("gitsub")
log.setLevel(logging.DEBUG)
_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
for _path, _lvl in [(LOG_DIR/"sync.log", logging.DEBUG), (LOG_DIR/"error.log", logging.ERROR)]:
    _h = logging.FileHandler(_path); _h.setLevel(_lvl); _h.setFormatter(_fmt); log.addHandler(_h)
_sh = logging.StreamHandler(); _sh.setFormatter(_fmt); log.addHandler(_sh)

# ── Colors ─────────────────────────────────────────────────────────────────
_ANSI = re.compile(r'\x1b\[[0-9;]*m')
def _strip(s): return _ANSI.sub('', s)
def _vlen(s):  return len(_strip(s))
C="\033[0;36m"; G="\033[0;32m"; Y="\033[1;33m"; R="\033[0;31m"
B="\033[1m";    D="\033[2m";    RS="\033[0m"
def cyan(s):   return f"{C}{s}{RS}"
def green(s):  return f"{G}{s}{RS}"
def yellow(s): return f"{Y}{s}{RS}"
def red(s):    return f"{R}{s}{RS}"
def bold(s):   return f"{B}{s}{RS}"
def dim(s):    return f"{D}{s}{RS}"

# ── Config ─────────────────────────────────────────────────────────────────
class Config:
    def __init__(self):
        if not CONFIG_FILE.exists():
            print(red("config.json not found. Run install.sh first.")); sys.exit(1)
        with open(CONFIG_FILE) as f: d = json.load(f)
        self._raw          = d
        self.panel_api_url = d.get("panel_api_url", d.get("panel_url","")).rstrip("/")
        self.api_token     = d.get("api_token","")
        self.github_user   = d.get("github_user","")
        self.github_repo   = d.get("github_repo","")
        self.github_branch = d.get("github_branch","main")
        self.deploy_method = d.get("deploy_method","token")
        self.github_token  = d.get("github_token","")
        self.ssh_key_path  = d.get("ssh_key_path","/root/.ssh/gitsub_deploy")
        self.filename_len  = int(d.get("filename_length", 32))
        self.filename_mode = d.get("filename_mode","random")
        self.subs_dir      = d.get("subs_dir","subs")
        self.sync_interval = int(d.get("sync_interval", 21600))
        self.ui_user       = d.get("ui_user","admin")
        self.ui_pass       = d.get("ui_pass","")
        self.ui_port       = int(d.get("ui_port", 2086))
        self.domain        = d.get("domain","")
        self.access_mode   = d.get("access_mode","1")
        self.timeout       = 20
        self.retries       = 3

    @property
    def subs_path(self): return BASE_DIR / self.subs_dir

    @property
    def raw_base_url(self):
        return f"https://raw.githubusercontent.com/{self.github_user}/{self.github_repo}/{self.github_branch}/{self.subs_dir}"

def save_config(data: dict):
    with open(CONFIG_FILE,"w") as f: json.dump(data,f,indent=2)
    CONFIG_FILE.chmod(0o600)

def load_config() -> dict:
    if not CONFIG_FILE.exists(): return {}
    with open(CONFIG_FILE) as f: return json.load(f)

# ── Utils ──────────────────────────────────────────────────────────────────
ALPHABET = string.ascii_letters + string.digits

def gen_filename(n: int) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(n)) + ".txt"

def hash_content(links: list) -> str:
    return hashlib.sha256("\n".join(sorted(links)).encode()).hexdigest()

def email_to_filename(email: str) -> str:
    safe = re.sub(r'[^a-zA-Z0-9._-]', '_', email.lower())
    safe = safe.replace("@","_at_")
    return safe + ".txt"

# ── API ────────────────────────────────────────────────────────────────────
class API:
    def __init__(self, cfg):
        self.cfg = cfg
    def _get(self, url):
        hdrs = {"Authorization": f"Bearer {self.cfg.api_token}"}
        last = None
        for i in range(1, self.cfg.retries+1):
            try:
                r = requests.get(url, headers=hdrs, timeout=self.cfg.timeout)
                r.raise_for_status(); return r.json()
            except Exception as e:
                last = e; log.warning(f"Attempt {i}: {e}"); time.sleep(2*i)
        raise RuntimeError(f"All retries failed: {last}")
    def get_clients(self):
        return self._get(f"{self.cfg.panel_api_url}/panel/api/clients/list").get("obj",[])
    def get_sub_links(self, sub_id):
        return self._get(f"{self.cfg.panel_api_url}/panel/api/clients/subLinks/{sub_id}").get("obj",[])

# ── Store ──────────────────────────────────────────────────────────────────
class Store:
    def __init__(self, cfg=None):
        subs_name = cfg.subs_dir if cfg else load_config().get("subs_dir","subs")
        self._subs = BASE_DIR / subs_name
        self._subs.mkdir(exist_ok=True)

    def load(self) -> dict:
        if not SUBMAP_FILE.exists(): return {}
        with open(SUBMAP_FILE) as f: return json.load(f)

    def save(self, data: dict):
        with open(SUBMAP_FILE,"w") as f: json.dump(data,f,indent=2)

    def write_sub(self, fn: str, links: list):
        (self._subs/fn).write_text("\n".join(links))

    def delete_sub(self, fn: str):
        p = self._subs/fn
        if p.exists(): p.unlink(); log.info(f"Deleted file: {fn}")

    def rename_sub(self, old_fn: str, new_fn: str):
        old = self._subs/old_fn; new = self._subs/new_fn
        if old.exists():
            new.write_text(old.read_text()); old.unlink()
            log.info(f"Renamed: {old_fn} → {new_fn}")

# ── Git ────────────────────────────────────────────────────────────────────
class Git:
    def __init__(self, cfg): self.cfg = cfg

    def _run(self, args, check=True):
        r = subprocess.run(args, cwd=BASE_DIR, capture_output=True, text=True)
        if check and r.returncode != 0:
            raise RuntimeError(f"git {args[1]}: {(r.stderr or r.stdout).strip()}")
        return r

    def _remote_url(self):
        if self.cfg.deploy_method == "ssh":
            return f"git@github-gitsub:{self.cfg.github_user}/{self.cfg.github_repo}.git"
        token = self.cfg.github_token
        user  = self.cfg.github_user
        repo  = self.cfg.github_repo
        if not token:
            raise RuntimeError("GitHub token is empty. Set it in settings.")
        if not user or not repo:
            raise RuntimeError("GitHub username or repo name is empty. Check settings.")
        return f"https://{token}@github.com/{user}/{repo}.git"

    def ensure_remote(self):
        """Always re-set remote URL in case user/repo/token changed."""
        url = self._remote_url()
        r = self._run(["git","remote","get-url","origin"], check=False)
        if r.returncode != 0:
            self._run(["git","remote","add","origin",url])
        else:
            self._run(["git","remote","set-url","origin",url])

    def pull_rebase(self):
        try:
            self._run(["git","fetch","origin",self.cfg.github_branch])
            r = self._run(["git","rebase",f"origin/{self.cfg.github_branch}"], check=False)
            if r.returncode != 0:
                self._run(["git","rebase","--abort"], check=False)
                # Hard reset to remote — safe for subs-only repo
                self._run(["git","reset","--hard",f"origin/{self.cfg.github_branch}"])
                log.warning("Rebase conflict: reset to remote HEAD")
        except Exception as e:
            log.warning(f"pull_rebase skipped: {e}")

    def push(self) -> bool:
        self.ensure_remote()
        subs_dir = self.cfg.subs_dir
        self._run(["git","add",f"{subs_dir}/"])
        if not self._run(["git","status","--porcelain"],check=False).stdout.strip():
            log.info("Nothing to push"); return False
        self.pull_rebase()
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        self._run(["git","commit","-m",f"sync {ts}"])
        result = subprocess.run(
            ["git","push",self._remote_url(),self.cfg.github_branch],
            cwd=BASE_DIR, capture_output=True, text=True
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout).strip()
            raise RuntimeError(f"Push failed: {err or 'no error message — check token/repo name'}")
        log.info("Git push OK"); return True

# ── Engine ─────────────────────────────────────────────────────────────────
class Engine:
    def __init__(self):
        self.cfg   = Config()
        self.api   = API(self.cfg)
        self.store = Store(self.cfg)
        self.git   = Git(self.cfg)

    def _desired_filename(self, email: str, existing: str | None) -> str:
        """
        Determine the correct filename for a user.
        If mode is 'email': use email-based name.
        If mode is 'random': use existing if present, else generate.
        Also handles mode switch: if existing filename doesn't match
        the current mode, return the new desired name so it gets renamed.
        """
        mode = self.cfg.filename_mode
        if mode == "email" and email and email != "unknown":
            desired = email_to_filename(email)
        else:
            desired = existing if existing else gen_filename(self.cfg.filename_len)

        # If existing doesn't match desired (mode was switched), rename
        if existing and existing != desired:
            self.store.rename_sub(existing, desired)
            log.info(f"Mode switch rename: {existing} → {desired}")

        return desired

    def sync(self):
        log.info("─── Sync started ───")
        submap  = self.store.load()
        clients = self.api.get_clients()
        log.info(f"Found {len(clients)} clients")

        seen    = set()
        new_map = {}
        # Track filenames to detect duplicates
        used_filenames: dict[str, str] = {}  # filename → sub_id

        for client in clients:
            sub_id = client.get("subId","").strip()
            email  = client.get("email","unknown")
            if not sub_id: continue
            seen.add(sub_id)

            try:
                links = self.api.get_sub_links(sub_id)
            except Exception as e:
                log.error(f"Links failed for {email}: {e}")
                if sub_id in submap: new_map[sub_id] = submap[sub_id]
                continue

            if not links: continue

            old      = submap.get(sub_id)
            old_fn   = old["filename"] if old else None
            new_fn   = self._desired_filename(email, old_fn)

            # Duplicate check: if another sub_id already claimed this filename
            if new_fn in used_filenames and used_filenames[new_fn] != sub_id:
                log.warning(f"Filename collision for {email}: {new_fn} already used — generating random name")
                new_fn = gen_filename(self.cfg.filename_len)

            used_filenames[new_fn] = sub_id

            new_hash = hash_content(links)
            # Only rewrite file if content changed OR filename changed
            if old and old.get("hash") == new_hash and old_fn == new_fn:
                new_map[sub_id] = old
                continue

            self.store.write_sub(new_fn, links)
            new_map[sub_id] = {
                "email":      email,
                "filename":   new_fn,
                "hash":       new_hash,
                "raw_url":    f"{self.cfg.raw_base_url}/{new_fn}",
                "updated":    int(time.time()),
                "updated_ts": datetime.utcnow().isoformat(),
                "filename_mode": self.cfg.filename_mode,
            }
            log.info(f"Updated: {email} → {new_fn}")

        # Remove deleted clients — delete both map entry and file
        for sid, v in submap.items():
            if sid not in seen:
                self.store.delete_sub(v["filename"])
                log.info(f"Removed: {v.get('email', sid)}")

        self.store.save(new_map)

        try:
            self.git.push()
        except Exception as e:
            log.error(f"Push failed: {e}")
            print(red(f"\n  Push error: {e}"))
            print(yellow("  Tip: run 'gitsub settings edit' and check github_user, github_repo, github_token"))

        log.info("─── Sync complete ───")
        return new_map

    def lookup(self, q):
        q = q.strip().lower()
        return [(k,v) for k,v in self.store.load().items()
                if q in v.get("email","").lower() or q in k.lower()]

    def rotate(self, q):
        submap = self.store.load(); q = q.strip().lower(); rotated = []
        for sid, v in submap.items():
            if q in v.get("email","").lower() or q in sid.lower():
                new_fn = gen_filename(self.cfg.filename_len)
                self.store.rename_sub(v["filename"], new_fn)
                v["filename"] = new_fn
                v["raw_url"]  = f"{self.cfg.raw_base_url}/{new_fn}"
                v["hash"]     = ""
                submap[sid]   = v
                rotated.append((sid, v))
        if rotated:
            self.store.save(submap)
            try: self.git.push()
            except Exception as e: log.error(f"Push after rotate failed: {e}")
        return rotated

# ── Settings ───────────────────────────────────────────────────────────────
SETTINGS = {
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
    "domain":          "Domain Name (for nginx)",
    "access_mode":     "Access Mode (1=IP  2=IP+domain)",
    "subs_dir":        "Subs Folder Name in Repo",
    "filename_length": "Filename Random Length",
    "filename_mode":   "Filename Mode (random / email)",
}
NUMERIC = {"sync_interval","ui_port","filename_length"}
SECRET  = {"api_token","github_token","ui_pass"}

def show_settings():
    cfg = load_config()
    print(f"\n{bold('Current Settings')}  {dim(str(CONFIG_FILE))}\n")
    for i,(k,label) in enumerate(SETTINGS.items(),1):
        v = str(cfg.get(k,""))
        if k in SECRET and v: v = v[:4]+"●●●●" if len(v)>4 else "●●●●"
        print(f"  {dim(str(i).rjust(2))}  {label:<38}  {v or dim('(not set)')}")
    print()

def edit_settings():
    cfg  = load_config()
    keys = list(SETTINGS.keys())
    print(f"\n{bold('Edit Settings')}\n")
    for i,(k,label) in enumerate(SETTINGS.items(),1):
        v = str(cfg.get(k,""))
        if k in SECRET and v: v = v[:4]+"●●●"
        print(f"  {cyan(str(i).rjust(2))}  {label:<38}  {dim(v)}")
    print(f"  {cyan(' 0')}  Cancel\n")
    raw = input("  Choose: ").strip()
    if not raw.isdigit() or int(raw)==0 or int(raw)>len(keys):
        print("Cancelled."); return
    idx=int(raw)-1; k=keys[idx]; label=SETTINGS[k]
    print(f"\n  Changing : {bold(label)}\n  Current  : {dim(str(cfg.get(k,'')))} \n")
    if k in SECRET:
        import getpass; v=getpass.getpass("  New value (hidden): ")
    else:
        v=input("  New value: ").strip()
    if not v: print("  No change."); return
    if k in NUMERIC:
        try: v=int(v)
        except: print(red("  Must be a number.")); return
    cfg[k]=v; save_config(cfg)
    # If GitHub repo details changed, update git remote immediately
    if k in ("github_user","github_repo","github_token","deploy_method","ssh_key_path"):
        try:
            cfg_obj = Config()
            Git(cfg_obj).ensure_remote()
            print(green("  Git remote updated."))
        except Exception as e:
            print(yellow(f"  Git remote update failed: {e}"))
    print(green("\n  Saved."))
    _offer_restart(k)

def _offer_restart(changed_key=""):
    if changed_key in ("sync_interval","panel_api_url","api_token","github_user","github_repo",
                       "github_branch","deploy_method","github_token","ssh_key_path","filename_mode","subs_dir"):
        sug = "2"
    elif changed_key in ("ui_port","ui_user","ui_pass","domain","access_mode"):
        sug = "3"
    else:
        sug = "1"
    print(f"\n  Restart needed? (suggested: {cyan(sug)})")
    print(f"  {cyan(' 1')}  Restart both services")
    print(f"  {cyan(' 2')}  Restart sync daemon only")
    print(f"  {cyan(' 3')}  Restart web UI only")
    print(f"  {cyan(' 0')}  Skip\n")
    c = input("  Choose: ").strip()
    if c=="1": subprocess.run(["systemctl","restart","xui-subsync","xui-webui"],check=False); print(green("  Restarted both."))
    elif c=="2": subprocess.run(["systemctl","restart","xui-subsync"],check=False); print(green("  Sync daemon restarted."))
    elif c=="3": subprocess.run(["systemctl","restart","xui-webui"],check=False); print(green("  Web UI restarted."))

# ── Nginx config menu ───────────────────────────────────────────────────────
def nginx_menu():
    cfg       = load_config()
    port      = cfg.get("ui_port", 2086)
    http_port = cfg.get("nginx_http_port", 80)
    NGINX_CONF = "/etc/nginx/sites-available/xui-webui"

    print(f"\n{bold('Nginx / Domain Setup')}\n")
    print(f"  Current: mode {cfg.get('access_mode','1')}  domain: {cfg.get('domain','none')}  nginx port: {http_port}\n")
    print(f"  {cyan(' 1')}  IP only — disable nginx for gitsub")
    print(f"  {cyan(' 2')}  Add domain name  (nginx alias on port {port})")
    print(f"  {cyan(' 3')}  Show current nginx config")
    print(f"  {cyan(' 4')}  Reload nginx")
    print(f"  {cyan(' 5')}  Test nginx config (nginx -t)")
    print(f"  {cyan(' 6')}  Enable nginx service")
    print(f"  {cyan(' 0')}  Back\n")
    choice = input("  Choose: ").strip()

    if choice == "0": return

    elif choice == "1":
        cfg["access_mode"]="1"; cfg["domain"]=""; save_config(cfg)
        link = Path("/etc/nginx/sites-enabled/xui-webui")
        if link.exists(): link.unlink()
        subprocess.run(["systemctl","reload","nginx"],check=False)
        print(green(f"\n  Done. Dashboard: http://SERVER_IP:{port}"))

    elif choice == "2":
        domain = input("  Domain name (e.g. sub.example.com): ").strip()
        if not domain: print(red("  Domain required.")); return


        if subprocess.run(["which","nginx"],capture_output=True).returncode != 0:
            print("  Installing nginx...")
            subprocess.run(["apt-get","install","-y","-qq","nginx"],check=False)

        # Remove default site and conflicts
        Path("/etc/nginx/sites-enabled/default").unlink(missing_ok=True)
        r = subprocess.run(["grep","-rl",f"server_name.*{domain}","/etc/nginx/sites-enabled/"],
                            capture_output=True,text=True)
        for f in r.stdout.strip().splitlines():
            if f and "xui-webui" not in f: subprocess.run(["rm","-f",f])

        # Listen on the same port as the dashboard — no port 80
        conf = f"""server {{
    listen {port};
    server_name {domain};
    location / {{
        proxy_pass           http://127.0.0.1:{port};
        proxy_set_header     Host $host;
        proxy_set_header     X-Real-IP $remote_addr;
        proxy_set_header     X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header     X-Forwarded-Proto $scheme;
        proxy_read_timeout   60;
        proxy_http_version   1.1;
        proxy_buffering      off;
    }}
}}"""
        Path(NGINX_CONF).write_text(conf)
        link = Path("/etc/nginx/sites-enabled/xui-webui")
        if not link.exists(): link.symlink_to(NGINX_CONF)

        subprocess.run(["systemctl","enable","nginx","--quiet"],check=False)
        subprocess.run(["systemctl","start","nginx"],check=False)

        r = subprocess.run(["nginx","-t"], capture_output=True, text=True)
        if r.returncode == 0:
            subprocess.run(["systemctl","reload","nginx"],check=False)
            cfg["access_mode"]="2"; cfg["domain"]=domain; save_config(cfg)
            print(green(f"\n  Done. Dashboard:\n    http://SERVER_IP:{port}\n    http://{domain}:{port}    (domain, same port)"))
        else:
            print(red(f"  Nginx config error:\n{r.stderr}"))

    elif choice == "3":
        if Path(NGINX_CONF).exists():
            print(f"\n{dim(NGINX_CONF)}\n")
            print(Path(NGINX_CONF).read_text())
        else:
            print(yellow("  No config file found."))

    elif choice == "4":
        r = subprocess.run(["systemctl","reload","nginx"], capture_output=True, text=True)
        print(green("  Reloaded.") if r.returncode==0 else red(f"  Failed: {r.stderr.strip()}"))

    elif choice == "5":
        subprocess.run(["nginx","-t"])

    elif choice == "6":
        subprocess.run(["systemctl","enable","nginx","--quiet"],check=False)
        subprocess.run(["systemctl","start","nginx"])
        print(green("  Nginx enabled and started."))

# ── Self update ────────────────────────────────────────────────────────────
GITHUB_RAW   = "https://raw.githubusercontent.com/diginetizen/mewobey-sub/main"
UPDATE_FILES = ["update.py","webui.py","requirements.txt"]

def check_for_updates():
    try:
        r=requests.get(f"{GITHUB_RAW}/version.txt",timeout=10)
        remote=r.text.strip() if r.status_code==200 else None
        if not remote:
            r2=requests.get("https://api.github.com/repos/diginetizen/mewobey-sub/commits/main",timeout=10)
            remote=r2.json()["sha"][:8] if r2.status_code==200 else None
        if not remote: return {"available":False,"error":"Cannot reach GitHub"}
        lf=BASE_DIR/"version.txt"
        local=lf.read_text().strip() if lf.exists() else None
        if not local: return {"available":True,"local":"unknown","remote":remote}
        return {"available":remote!=local,"local":local,"remote":remote}
    except Exception as e:
        return {"available":False,"error":str(e)}

def do_self_update():
    changed=[]; errors=[]
    for fname in UPDATE_FILES:
        dest=BASE_DIR/fname
        try:
            r=requests.get(f"{GITHUB_RAW}/{fname}",timeout=30); r.raise_for_status()
            nc=r.text
            if dest.exists() and dest.read_text()==nc: continue
            if dest.exists(): dest.rename(str(dest)+".bak")
            dest.write_text(nc); changed.append(fname)
        except Exception as e:
            errors.append(f"{fname}: {e}")
    try:
        r=requests.get(f"{GITHUB_RAW}/version.txt",timeout=10)
        if r.status_code==200: (BASE_DIR/"version.txt").write_text(r.text.strip())
        else:
            r2=requests.get("https://api.github.com/repos/diginetizen/mewobey-sub/commits/main",timeout=10)
            if r2.status_code==200: (BASE_DIR/"version.txt").write_text(r2.json()["sha"][:8])
    except: pass
    if "requirements.txt" in changed:
        pip=BASE_DIR/"venv"/"bin"/"pip"
        if pip.exists():
            subprocess.run([str(pip),"install","--quiet","-r",str(BASE_DIR/"requirements.txt")],check=False)
    if errors: print(red(f"  Errors: {'; '.join(errors)}"))
    return bool(changed), changed

def self_update_interactive():
    print(f"\n  {bold('Checking for updates...')}")
    info=check_for_updates()
    if "error" in info and not info.get("available"):
        print(yellow(f"\n  Could not check: {info['error']}")); return
    if not info.get("available"):
        print(green(f"\n  Already up to date ({info.get('local','?')})")); return
    print(f"\n  {yellow('Update available!')}")
    print(f"  Current : {dim(info.get('local','?'))}")
    print(f"  Latest  : {cyan(info.get('remote','?'))}\n")
    print(f"  {cyan(' 1')}  Install update now")
    print(f"  {cyan(' 0')}  Cancel\n")
    if input("  Choose: ").strip() != "1": print("  Cancelled."); return
    print("  Downloading...")
    ok, changed = do_self_update()
    if not changed: print(green("\n  Nothing changed.")); return
    print(green(f"\n  Updated: {', '.join(changed)}"))
    if ok:
        print(f"\n  {yellow('Restart needed.')}")
        print(f"  {cyan(' 1')}  Restart now")
        print(f"  {cyan(' 0')}  Skip\n")
        if input("  Choose: ").strip() == "1":
            subprocess.run(["systemctl","restart","xui-subsync","xui-webui"],check=False)
            print(green("  Restarted."))

# ── Service status ──────────────────────────────────────────────────────────
def svc_info(name):
    r=subprocess.run(["systemctl","is-active",name],capture_output=True,text=True)
    s=r.stdout.strip()
    if s=="active":   return green("● active"),  True,  len("● active")
    if s=="inactive": return dim("○ inactive"), False, len("○ inactive")
    if s=="failed":   return red("✗ failed"),   False, len("✗ failed")
    return dim(f"○ {s}"), False, len(f"○ {s}")

# ── Menu box drawing ────────────────────────────────────────────────────────
W = 46

def _box_line(content):
    vis = _vlen(content)
    pad = " " * max(0, W - vis)
    return f"{B}║{RS}{content}{pad}{B}║{RS}"

def _blank(): return f"{B}║{RS}{' '*W}{B}║{RS}"
def _sep():   return f"{B}╠{'═'*W}╣{RS}"
def _top():   return f"{B}╔{'═'*W}╗{RS}"
def _bot():   return f"{B}╚{'═'*W}╝{RS}"

def _mrow(key, label):
    k = key.rjust(2)
    return _box_line(f"  {cyan(k)}  {label}")

def _srow(prefix, colored_val, vlen_val):
    vis = len(_strip(prefix)) + vlen_val + 2
    pad = " " * max(0, W - vis)
    return f"{B}║{RS}  {prefix}{colored_val}{pad}{B}║{RS}"

# ── Interactive menu ────────────────────────────────────────────────────────
def interactive_menu():
    while True:
        sc, sa, sv = svc_info("xui-subsync")
        uc, ua, uv = svc_info("xui-webui")

        print()
        print(_top())
        print(_box_line(f"  {cyan('gitsub')} {dim('—')} XUI Subscription Sync"))
        print(_sep())
        print(_srow("Services:  sync   ", sc, sv))
        print(_srow("           webui  ", uc, uv))
        print(_sep())
        print(_blank())
        print(_mrow( "1", "Sync now"))
        print(_mrow( "2", "Show all users & URLs"))
        print(_mrow( "3", "Lookup user"))
        print(_mrow( "4", "Rotate user URL"))
        print(_mrow( "5", "File map"))
        print(_mrow( "6", "Live logs"))
        print(_mrow( "7", "Settings"))
        print(_mrow( "8", "Nginx / domain setup"))
        print(_mrow( "9", "Restart services"))
        print(_mrow("10", "Service status detail"))
        print(_mrow("11", "Check for updates"))
        print(_mrow("12", "Uninstall"))
        print(_mrow( "0", "Exit"))
        print(_blank())
        print(_bot())
        print()

        choice = input("  Choose: ").strip()

        if choice == "0":
            break

        elif choice == "1":
            print()
            try:
                result = Engine().sync()
                print(green(f"\n  Done — {len(result)} users synced."))
            except Exception as e:
                print(red(f"\n  Error: {e}"))
            input("\n  ENTER to continue...")

        elif choice == "2":
            submap = Store().load()
            if not submap:
                print(yellow("\n  No users yet — run a sync first."))
            else:
                print(f"\n  {bold('All Users')}  ({len(submap)} total)\n")
                print(f"  {'Email':<34}  Raw URL")
                print(f"  {'-'*34}  {'-'*55}")
                for _,v in sorted(submap.items(), key=lambda x: x[1].get("email","")):
                    print(f"  {v.get('email','?'):<34}  {dim(v.get('raw_url','—'))}")
            input("\n  ENTER to continue...")

        elif choice == "3":
            q = input("\n  Email or sub ID: ").strip()
            results = Engine().lookup(q) if q else []
            if not results: print(yellow("  Not found."))
            for sid,v in results:
                print(f"\n  Email   : {v.get('email')}")
                print(f"  Sub ID  : {sid}")
                print(f"  File    : {v.get('filename')}")
                print(f"  URL     : {cyan(v.get('raw_url','—'))}")
                print(f"  Updated : {v.get('updated_ts','—')}")
            input("\n  ENTER to continue...")

        elif choice == "4":
            q = input("\n  Email or sub ID to rotate: ").strip()
            if q and input(f"  Rotate URL for '{q}'? [y/n]: ").strip().lower() == "y":
                r = Engine().rotate(q)
                if not r: print(yellow("  Not found."))
                for _,v in r: print(green(f"\n  Rotated: {v.get('email')} → {v.get('raw_url')}"))
            input("\n  ENTER to continue...")

        elif choice == "5":
            submap = Store().load()
            if not submap:
                print(yellow("\n  No subs yet."))
            else:
                cfg  = Config()
                sdir = cfg.subs_path
                print(f"\n  {bold('File Map')}  ({len(submap)} files in {sdir})\n")
                print(f"  {'Email':<28}  OK  {'File':<34}  Updated")
                print(f"  {'-'*28}  --  {'-'*34}  {'-'*16}")
                for _,v in sorted(submap.items(), key=lambda x: x[1].get("email","")):
                    fp  = sdir / v.get("filename","")
                    ok  = green("✓") if fp.exists() else red("✗")
                    ts  = (v.get("updated_ts") or "—")[:16]
                    print(f"  {v.get('email','?'):<28}  {ok}   {v.get('filename','?'):<34}  {dim(ts)}")
                print(f"\n  {dim(cfg.raw_base_url)}")
            input("\n  ENTER to continue...")

        elif choice == "6":
            print(f"\n  {dim('Ctrl+C to stop')}\n")
            try: subprocess.run(["tail","-f",str(LOG_DIR/"sync.log")])
            except KeyboardInterrupt: pass

        elif choice == "7":
            print(f"\n  {cyan(' 1')}  View all settings")
            print(f"  {cyan(' 2')}  Edit a setting")
            print(f"  {cyan(' 0')}  Back")
            sub = input("\n  Choose: ").strip()
            if sub=="1": show_settings(); input("\n  ENTER to continue...")
            elif sub=="2": edit_settings(); input("\n  ENTER to continue...")

        elif choice == "8":
            nginx_menu()
            input("\n  ENTER to continue...")

        elif choice == "9":
            print(f"\n  {cyan(' 1')}  Restart both services")
            print(f"  {cyan(' 2')}  Restart sync daemon only")
            print(f"  {cyan(' 3')}  Restart web UI only")
            print(f"  {cyan(' 0')}  Back")
            sub = input("\n  Choose: ").strip()
            if sub=="1": subprocess.run(["systemctl","restart","xui-subsync","xui-webui"],check=False); print(green("  Restarted both."))
            elif sub=="2": subprocess.run(["systemctl","restart","xui-subsync"],check=False); print(green("  Sync daemon restarted."))
            elif sub=="3": subprocess.run(["systemctl","restart","xui-webui"],check=False); print(green("  Web UI restarted."))
            input("\n  ENTER to continue...")

        elif choice == "10":
            subprocess.run(["systemctl","status","xui-subsync","xui-webui","--no-pager"])
            input("\n  ENTER to continue...")

        elif choice == "11":
            self_update_interactive()
            input("\n  ENTER to continue...")

        elif choice == "12":
            print(f"\n  {red('Uninstall gitsub?')}")
            print("  This will stop and remove all services, the CLI, and optionally project files.\n")
            if input("  Are you sure? [y/n]: ").strip().lower() not in ("y","yes"):
                print("  Cancelled."); input("\n  ENTER to continue..."); continue

            # Ask about clearing GitHub repo
            print()
            print(f"  {yellow('Clear GitHub repo?')}")
            print("  Remove all subscription files from your GitHub repo?")
            print("  Your users will lose access to their subscription links.\n")
            if input("  Remove subs from GitHub too? [y/n]: ").strip().lower() in ("y","yes"):
                try:
                    cfg = Config(); sdir = cfg.subs_dir
                    import shutil
                    subs_path = BASE_DIR / sdir
                    if subs_path.exists():
                        shutil.rmtree(subs_path); subs_path.mkdir()
                        (subs_path/".gitkeep").touch()
                    git = Git(cfg); git.ensure_remote()
                    subprocess.run(["git","add","-A"], cwd=BASE_DIR, check=False)
                    subprocess.run(["git","commit","-m","uninstall: remove all subs"], cwd=BASE_DIR, check=False)
                    subprocess.run(["git","push",git._remote_url(),cfg.github_branch], cwd=BASE_DIR, check=False)
                    print(green("  GitHub repo cleared."))
                except Exception as e:
                    print(red(f"  Could not clear GitHub: {e}"))

            uninstall_path = BASE_DIR/"uninstall.sh"
            if uninstall_path.exists():
                subprocess.run(["bash",str(uninstall_path)])
            else:
                print(red("  uninstall.sh not found."))
            print(green("\n  Uninstall complete."))
            sys.exit(0)

        else:
            print(yellow("  Unknown choice."))

# ── Daemon ──────────────────────────────────────────────────────────────────
def run_daemon(interval):
    log.info(f"Daemon started — interval: {interval}s")
    while True:
        try: Engine().sync()
        except Exception as e: log.error(f"Sync error: {e}")
        log.info(f"Next sync in {interval}s")
        time.sleep(interval)

# ── Main ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        interactive_menu()
    elif args[0]=="update":
        info=check_for_updates()
        if info.get("error") and not info.get("available"):
            print(yellow(f"Cannot check: {info['error']}")); sys.exit(1)
        if not info.get("available"):
            print(green(f"Up to date ({info.get('local','?')})")); sys.exit(0)
        print(f"Update: {info.get('local')} → {info.get('remote')}")
        ok,changed=do_self_update()
        print(f"Updated: {', '.join(changed) or 'nothing'}")
        if ok: subprocess.run(["systemctl","restart","xui-subsync","xui-webui"],check=False)
    elif args[0]=="sync":
        Engine().sync()
    elif args[0]=="daemon":
        interval=21600
        if "--interval" in args: interval=int(args[args.index("--interval")+1])
        run_daemon(interval)
    elif args[0]=="lookup":
        if len(args)<2: print("Usage: gitsub lookup <email|subId>"); sys.exit(1)
        for sid,v in Engine().lookup(args[1]):
            print(f"\n  Email  : {v.get('email')}\n  Sub ID : {sid}\n  URL    : {v.get('raw_url')}")
    elif args[0]=="rotate":
        if len(args)<2: print("Usage: gitsub rotate <email|subId>"); sys.exit(1)
        for _,v in Engine().rotate(args[1]): print(f"  Rotated {v.get('email')} → {v.get('raw_url')}")
    elif args[0]=="status":
        sm=Store().load(); print(f"\n  Users: {len(sm)}")
        for sid,v in sm.items(): print(f"  • {v.get('email','?'):<34} {v.get('raw_url','—')}")
    elif args[0]=="settings":
        edit_settings() if len(args)>1 and args[1]=="edit" else show_settings()
    elif args[0]=="webui":
        os.execv(sys.executable,[sys.executable,str(BASE_DIR/"webui.py")])
    elif args[0] in ("help","--help","-h"):
        print(f"\n{bold('gitsub')} commands:\n"
              f"  {cyan('gitsub')}               interactive menu\n"
              f"  {cyan('gitsub sync')}           sync now\n"
              f"  {cyan('gitsub daemon')}         run daemon\n"
              f"  {cyan('gitsub update')}         update scripts\n"
              f"  {cyan('gitsub lookup')} <q>     find user\n"
              f"  {cyan('gitsub rotate')} <q>     rotate URL\n"
              f"  {cyan('gitsub status')}         list all users\n"
              f"  {cyan('gitsub settings')}       view settings\n"
              f"  {cyan('gitsub settings edit')}  change a setting\n"
              f"  {cyan('gitsub webui')}          start web UI\n")
    else:
        print(f"Unknown: {args[0]}. Run 'gitsub help'."); sys.exit(1)
