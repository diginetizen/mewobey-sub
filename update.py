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
SUBS_DIR    = BASE_DIR / "subs"
LOG_DIR     = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
SUBS_DIR.mkdir(exist_ok=True)

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
        self._raw         = d
        self.panel_api_url= d.get("panel_api_url", d.get("panel_url","")).rstrip("/")
        self.api_token    = d.get("api_token","")
        self.github_user  = d.get("github_user","")
        self.github_repo  = d.get("github_repo","")
        self.github_branch= d.get("github_branch","main")
        self.deploy_method= d.get("deploy_method","token")
        self.github_token = d.get("github_token","")
        self.ssh_key_path = d.get("ssh_key_path","/root/.ssh/gitsub_deploy")
        self.filename_len = d.get("filename_length",32)
        self.sync_interval= d.get("sync_interval",21600)
        self.ui_user      = d.get("ui_user","admin")
        self.ui_pass      = d.get("ui_pass","")
        self.ui_port      = d.get("ui_port",2086)
        self.domain       = d.get("domain","")
        self.access_mode  = d.get("access_mode","1")
        self.ssl_mode     = d.get("ssl_mode","none")
        self.ssl_cert     = d.get("ssl_cert","")
        self.ssl_key      = d.get("ssl_key","")
        self.ssl_email    = d.get("ssl_email","")
        self.timeout      = 20
        self.retries      = 3

    @property
    def raw_base_url(self):
        return f"https://raw.githubusercontent.com/{self.github_user}/{self.github_repo}/{self.github_branch}/subs"

def save_config(data: dict):
    with open(CONFIG_FILE,"w") as f: json.dump(data,f,indent=2)
    CONFIG_FILE.chmod(0o600)

def load_config() -> dict:
    if not CONFIG_FILE.exists(): return {}
    with open(CONFIG_FILE) as f: return json.load(f)

# ── Utils ──────────────────────────────────────────────────────────────────
ALPHABET = string.ascii_letters + string.digits
def gen_filename(n): return "".join(secrets.choice(ALPHABET) for _ in range(n)) + ".txt"
def hash_content(links): return hashlib.sha256("\n".join(links).encode()).hexdigest()

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
    def load(self):
        if not SUBMAP_FILE.exists(): return {}
        with open(SUBMAP_FILE) as f: return json.load(f)
    def save(self, data):
        with open(SUBMAP_FILE,"w") as f: json.dump(data,f,indent=2)
    def write_sub(self, fn, links): (SUBS_DIR/fn).write_text("\n".join(links))
    def delete_sub(self, fn):
        p = SUBS_DIR/fn
        if p.exists(): p.unlink(); log.info(f"Deleted: {fn}")

# ── Git ────────────────────────────────────────────────────────────────────
class Git:
    def __init__(self, cfg): self.cfg = cfg
    def _run(self, args, check=True):
        r = subprocess.run(args, cwd=BASE_DIR, capture_output=True, text=True)
        if check and r.returncode != 0: raise RuntimeError(f"git: {r.stderr.strip()}")
        return r
    def _remote_url(self):
        if self.cfg.deploy_method == "ssh":
            return f"git@github-gitsub:{self.cfg.github_user}/{self.cfg.github_repo}.git"
        return f"https://{self.cfg.github_token}@github.com/{self.cfg.github_user}/{self.cfg.github_repo}.git"
    def _ensure_remote(self):
        url = self._remote_url()
        r = self._run(["git","remote","get-url","origin"], check=False)
        if r.returncode != 0: self._run(["git","remote","add","origin",url])
        else:                  self._run(["git","remote","set-url","origin",url])
    def pull_rebase(self):
        try:
            self._run(["git","fetch","origin",self.cfg.github_branch])
            r = self._run(["git","rebase",f"origin/{self.cfg.github_branch}"], check=False)
            if r.returncode != 0:
                self._run(["git","rebase","--abort"], check=False)
                self._run(["git","reset","--soft",f"origin/{self.cfg.github_branch}"], check=False)
        except Exception as e: log.warning(f"Rebase skipped: {e}")
    def push(self):
        self._ensure_remote()
        self._run(["git","add","subs/"])
        if not self._run(["git","status","--porcelain"],check=False).stdout.strip():
            log.info("Nothing to push"); return False
        self.pull_rebase()
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        self._run(["git","commit","-m",f"sync {ts}"])
        r = subprocess.run(["git","push",self._remote_url(),self.cfg.github_branch],
                           cwd=BASE_DIR, capture_output=True, text=True)
        if r.returncode != 0: raise RuntimeError(f"Push failed: {r.stderr.strip()}")
        log.info("Git push OK"); return True

# ── Engine ─────────────────────────────────────────────────────────────────
class Engine:
    def __init__(self):
        self.cfg=Config(); self.api=API(self.cfg)
        self.store=Store(); self.git=Git(self.cfg)
    def sync(self):
        log.info("─── Sync started ───")
        submap=self.store.load(); clients=self.api.get_clients()
        log.info(f"Found {len(clients)} clients")
        seen=set(); new_map={}
        for c in clients:
            sub_id=c.get("subId","").strip(); email=c.get("email","unknown")
            if not sub_id: continue
            seen.add(sub_id)
            try: links=self.api.get_sub_links(sub_id)
            except Exception as e:
                log.error(f"Links failed for {email}: {e}")
                if sub_id in submap: new_map[sub_id]=submap[sub_id]
                continue
            if not links: continue
            old=submap.get(sub_id)
            if old:
                fn=old["filename"]
            else:
                cfg_raw=load_config()
                if cfg_raw.get("filename_mode")=="email" and email and email!="unknown":
                    # sanitize email for use as filename
                    safe=email.replace("@","_at_").replace(".","_").replace("/","_")
                    fn=safe+".txt"
                else:
                    fn=gen_filename(self.cfg.filename_len)
            nh=hash_content(links)
            if old and old.get("hash")==nh: new_map[sub_id]=old; continue
            self.store.write_sub(fn,links)
            new_map[sub_id]={"email":email,"filename":fn,"hash":nh,
                             "raw_url":f"{self.cfg.raw_base_url}/{fn}",
                             "updated":int(time.time()),
                             "updated_ts":datetime.utcnow().isoformat()}
            log.info(f"Updated: {email}")
        for sid,v in submap.items():
            if sid not in seen: self.store.delete_sub(v["filename"]); log.info(f"Removed: {v.get('email',sid)}")
        self.store.save(new_map)
        try: self.git.push()
        except Exception as e: log.error(f"Push failed: {e}")
        log.info("─── Sync complete ───")
        return new_map
    def lookup(self, q):
        q=q.strip().lower()
        return [(k,v) for k,v in self.store.load().items()
                if q in v.get("email","").lower() or q in k.lower()]
    def rotate(self, q):
        submap=self.store.load(); q=q.strip().lower(); rotated=[]
        for sid,v in submap.items():
            if q in v.get("email","").lower() or q in sid.lower():
                old=SUBS_DIR/v["filename"]; nf=gen_filename(Config().filename_len)
                if old.exists(): (SUBS_DIR/nf).write_text(old.read_text()); old.unlink()
                v["filename"]=nf; v["raw_url"]=f"{Config().raw_base_url}/{nf}"; v["hash"]=""
                submap[sid]=v; rotated.append((sid,v))
        if rotated: self.store.save(submap); Git(Config()).push()
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
    "domain":          "Domain Name",
    "access_mode":     "Access Mode (1=IP / 2=IP+domain / 3=+HTTPS / 4=IP+HTTPS)",
    "ssl_mode":        "SSL Mode (none / certbot / manual / later)",
    "ssl_cert":        "SSL Certificate Path (fullchain.pem)",
    "ssl_key":         "SSL Key Path (privkey.pem)",
    "ssl_email":       "SSL Email (for Let's Encrypt)",
    "filename_length": "Filename Random Length",
    "filename_mode":   "Filename Mode (random / email)",
}
NUMERIC = {"sync_interval","ui_port","filename_length"}
FILENAME_MODES = {"random","email"}
SECRET  = {"api_token","github_token","ui_pass"}

def show_settings():
    cfg = load_config()
    print(f"\n{bold('Current Settings')}  {dim(str(CONFIG_FILE))}\n")
    for i,(k,label) in enumerate(SETTINGS.items(),1):
        v = str(cfg.get(k,""))
        if k in SECRET and v: v = v[:4]+"●●●●" if len(v)>4 else "●●●●"
        print(f"  {dim(str(i).rjust(2))}  {cyan(label):<42} {v or dim('(not set)')}")
    print()

def edit_settings():
    cfg = load_config()
    keys   = list(SETTINGS.keys())
    labels = list(SETTINGS.values())
    print(f"\n{bold('Edit Settings')}\n")
    for i,(k,label) in enumerate(SETTINGS.items(),1):
        v = str(cfg.get(k,""))
        if k in SECRET and v: v = v[:4]+"●●●"
        print(f"  {cyan(str(i).rjust(2))}  {label:<42} {dim(v)}")
    print(f"  {cyan(' 0')}  Cancel\n")
    raw = input("  Choose: ").strip()
    if not raw.isdigit() or int(raw)==0 or int(raw)>len(keys):
        print("Cancelled."); return
    idx=int(raw)-1; k=keys[idx]; label=labels[idx]
    print(f"\n  Changing: {bold(label)}\n  Current : {dim(str(cfg.get(k,'')))}\n")
    if k in SECRET:
        import getpass; v=getpass.getpass("  New value (hidden): ")
    else:
        v=input("  New value: ").strip()
    if not v: print("  No change."); return
    if k in NUMERIC:
        try: v=int(v)
        except: print(red("  Must be a number.")); return
    cfg[k]=v; save_config(cfg)
    print(green("\n  Saved."))
    _offer_restart(k)

def _offer_restart(changed_key=""):
    # Decide which services are affected
    if changed_key in ("sync_interval","panel_api_url","api_token","github_user","github_repo",
                        "github_branch","deploy_method","github_token","ssh_key_path","filename_mode"):
        suggestion = "1"  # sync daemon
    elif changed_key in ("ui_port","ui_user","ui_pass","ssl_cert","ssl_key",
                         "domain","access_mode","ssl_mode","ssl_email"):
        suggestion = "3"  # webui
    else:
        suggestion = "1"
    print(f"\n  Restart services?  (suggested: {cyan(suggestion)})")
    print(f"  {cyan('1')}  Both   {cyan('2')}  Sync only   {cyan('3')}  Web UI only   {cyan('0')}  Skip")
    c=input("\n  Choose: ").strip()
    if c=="1": subprocess.run(["systemctl","restart","xui-subsync","xui-webui"],check=False); print(green("  Restarted both."))
    elif c=="2": subprocess.run(["systemctl","restart","xui-subsync"],check=False); print(green("  Sync restarted."))
    elif c=="3": subprocess.run(["systemctl","restart","xui-webui"],check=False); print(green("  Web UI restarted."))

# ── SSL setup from menu ─────────────────────────────────────────────────────
def _write_nginx_conf(domain, port):
    """Write nginx config that proxies domain:80 → localhost:port. No SSL."""
    import os
    nginx_conf = "/etc/nginx/sites-available/xui-webui"
    # Remove conflicting configs
    r = subprocess.run(["grep","-rl",f"server_name.*{domain}","/etc/nginx/sites-enabled/"],
                        capture_output=True,text=True)
    for f in r.stdout.strip().splitlines():
        if f and "xui-webui" not in f:
            subprocess.run(["rm","-f",f],check=False)
    conf = f"""server {{
    listen 80;
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
    Path(nginx_conf).write_text(conf)
    os.makedirs("/etc/nginx/sites-enabled",exist_ok=True)
    link = Path("/etc/nginx/sites-enabled/xui-webui")
    if not link.exists(): link.symlink_to(nginx_conf)
    subprocess.run(["nginx","-t","-q"],check=False)
    subprocess.run(["systemctl","reload","nginx"],check=False)


def setup_ssl_menu():
    cfg = load_config()
    port = cfg.get("ui_port",2086)

    print(f"\n{bold('Access / SSL Setup')}\n")
    print(f"  Current mode : {cyan(cfg.get('access_mode','1'))} — {cfg.get('domain','no domain')}")
    print()
    print(f"  {cyan('1')}  IP only           http://IP:{port}")
    print(f"  {cyan('2')}  IP + domain HTTP  http://IP:{port}  +  http://domain:{port}")
    print(f"  {cyan('3')}  IP + domain + HTTPS  (adds https://domain on port 443)")
    print(f"  {cyan('4')}  IP + HTTPS via cert  https://IP:{port}")
    print(f"  {cyan('0')}  Back\n")
    choice = input("  Choose: ").strip()
    if choice == "0": return

    if choice == "1":
        cfg["access_mode"]="1"; cfg["domain"]=""; cfg["ssl_mode"]="none"
        save_config(cfg)
        subprocess.run(["systemctl","restart","xui-webui"],check=False)
        print(green(f"\n  Done. Access: http://SERVER_IP:{port}"))
        return

    if choice in ("2","3"):
        domain = input("  Domain name: ").strip()
        if not domain: print(red("  Domain required.")); return
        cfg["domain"] = domain; cfg["access_mode"] = choice

        # Install nginx
        if subprocess.run(["which","nginx"],capture_output=True).returncode != 0:
            print("  Installing nginx...")
            subprocess.run(["apt-get","install","-y","-qq","nginx"],check=False)

        _write_nginx_conf(domain, port)
        print(green(f"  Nginx: {domain} → port {port}"))

        if choice == "2":
            cfg["ssl_mode"]="none"; save_config(cfg)
            print(green(f"\n  Done. Access:\n    http://SERVER_IP:{port}\n    http://{domain}:{port}"))
            return

        # choice == "3" — add HTTPS
        print()
        print(f"  SSL source:")
        print(f"  {cyan('1')}  Certbot / Let's Encrypt (auto)")
        print(f"  {cyan('2')}  I have cert files")
        print(f"  {cyan('3')}  Skip SSL for now\n")
        ssl_src = input("  Choose: ").strip()

        if ssl_src == "1":
            # Install certbot if needed
            if subprocess.run(["which","certbot"],capture_output=True).returncode != 0:
                subprocess.run(["apt-get","install","-y","-qq","certbot","python3-certbot-nginx"],check=False)
            email = input(f"  Email [{cfg.get('github_user','admin')}@{domain}]: ").strip()
            email = email or f"{cfg.get('github_user','admin')}@{domain}"
            r = subprocess.run(["certbot","--nginx","-d",domain,"--non-interactive","--agree-tos","-m",email])
            if r.returncode==0:
                cfg["ssl_mode"]="certbot"; cfg["ssl_email"]=email; save_config(cfg)
                print(green(f"\n  Done. Access:\n    http://SERVER_IP:{port}\n    http://{domain}:{port}\n    https://{domain}"))
            else:
                print(red("  Certbot failed. Check DNS and try again."))
        elif ssl_src == "2":
            cert = input("  Path to certificate (fullchain.pem): ").strip()
            key  = input("  Path to private key  (privkey.pem): ").strip()
            if not Path(cert).exists() or not Path(key).exists():
                print(red("  File not found.")); return
            # Append SSL block to nginx config
            nginx_conf = "/etc/nginx/sites-available/xui-webui"
            extra = f"""
server {{
    listen 443 ssl;
    server_name {domain};
    ssl_certificate     {cert};
    ssl_certificate_key {key};
    location / {{
        proxy_pass           http://127.0.0.1:{port};
        proxy_set_header     Host $host;
        proxy_set_header     X-Forwarded-Proto https;
        proxy_read_timeout   60;
    }}
}}"""
            with open(nginx_conf,"a") as f: f.write(extra)
            subprocess.run(["nginx","-t","-q"],check=False)
            subprocess.run(["systemctl","reload","nginx"],check=False)
            cfg["ssl_mode"]="manual"; cfg["ssl_cert"]=cert; cfg["ssl_key"]=key; save_config(cfg)
            print(green(f"\n  Done. Access:\n    http://SERVER_IP:{port}\n    http://{domain}:{port}\n    https://{domain}"))
        else:
            cfg["ssl_mode"]="later"; save_config(cfg)
            print(yellow("  SSL skipped. Run this menu again to add it later."))
        return

    if choice == "4":
        print()
        print(f"  {cyan('1')}  Enter cert file paths")
        print(f"  {cyan('2')}  Paste cert content\n")
        src = input("  Choose: ").strip()
        cert_dir = BASE_DIR/"ssl"; cert_dir.mkdir(exist_ok=True)

        if src == "2":
            cert = str(cert_dir/"cert.pem"); key = str(cert_dir/"key.pem")
            print("  Paste certificate (fullchain.pem), Ctrl+D when done:")
            import sys as _sys
            Path(cert).write_text(_sys.stdin.read())
            print("  Paste private key (privkey.pem), Ctrl+D when done:")
            Path(key).write_text(_sys.stdin.read())
            Path(key).chmod(0o600)
        else:
            cert = input("  Certificate path: ").strip()
            key  = input("  Key path: ").strip()
            if not Path(cert).exists() or not Path(key).exists():
                print(red("  File not found.")); return

        cfg["access_mode"]="4"; cfg["ssl_mode"]="manual"
        cfg["ssl_cert"]=cert; cfg["ssl_key"]=key; save_config(cfg)
        subprocess.run(["systemctl","restart","xui-webui"],check=False)
        print(green(f"\n  Done. Access: https://SERVER_IP:{port}"))

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
        # If no local version file, we can't compare — treat as updatable
        if not local:
            return {"available":True,"local":"not installed","remote":remote}
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
            if dest.exists() and dest.read_text()==nc: log.info(f"Up to date: {fname}"); continue
            if dest.exists(): dest.rename(str(dest)+".bak")
            dest.write_text(nc); changed.append(fname); log.info(f"Updated: {fname}")
        except Exception as e:
            errors.append(f"{fname}: {e}"); log.error(f"Update failed {fname}: {e}")
    # Version marker
    try:
        r=requests.get(f"{GITHUB_RAW}/version.txt",timeout=10)
        if r.status_code==200: (BASE_DIR/"version.txt").write_text(r.text.strip())
        else:
            r2=requests.get("https://api.github.com/repos/diginetizen/mewobey-sub/commits/main",timeout=10)
            if r2.status_code==200: (BASE_DIR/"version.txt").write_text(r2.json()["sha"][:8])
    except: pass
    # pip update
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
    if input("  Install now? [y/n]: ").strip().lower() != "y":
        print("  Cancelled."); return
    print("  Downloading...")
    ok, changed = do_self_update()
    if not changed: print(green("\n  Nothing changed.")); return
    print(green(f"\n  Updated: {', '.join(changed)}"))
    if ok:
        print(f"\n  {yellow('Restart needed.')}")
        if input("  Restart now? [y/n]: ").strip().lower() == "y":
            subprocess.run(["systemctl","restart","xui-subsync","xui-webui"],check=False)
            print(green("  Restarted."))

# ── Service status helper ──────────────────────────────────────────────────
def svc_info(name):
    """Return (colored_status, is_active, visible_len)"""
    r=subprocess.run(["systemctl","is-active",name],capture_output=True,text=True)
    s=r.stdout.strip()
    if s=="active":   return green("● active"),  True,  len("● active")
    if s=="inactive": return dim("○ inactive"), False, len("○ inactive")
    if s=="failed":   return red("✗ failed"),   False, len("✗ failed")
    return dim(f"○ {s}"), False, len(f"○ {s}")

# ── Menu box drawing ───────────────────────────────────────────────────────
# W = total inner width (between ║ and ║), including the 2 leading spaces
W = 46

def _box_line(content_with_ansi):
    """Pad content to fill W chars of visible width, wrap in ║ ║"""
    vis = _vlen(content_with_ansi)
    pad = " " * max(0, W - vis)
    return f"{B}║{RS}{content_with_ansi}{pad}{B}║{RS}"

def _blank(): return f"{B}║{RS}{' '*W}{B}║{RS}"
def _sep():   return f"{B}╠{'═'*W}╣{RS}"
def _top():   return f"{B}╔{'═'*W}╗{RS}"
def _bot():   return f"{B}╚{'═'*W}╝{RS}"

def _mrow(key, label):
    content = f"  {cyan(key)}  {label}"
    return _box_line(content)

def _srow(prefix, colored_val, vlen_val):
    content = f"  {prefix}{colored_val}"
    vis = len(_strip(prefix)) + vlen_val + 2
    pad = " " * max(0, W - vis)
    return f"{B}║{RS}  {prefix}{colored_val}{pad}{B}║{RS}"

# ── Interactive Menu ───────────────────────────────────────────────────────
def interactive_menu():
    while True:
        sync_col, sync_active, sync_vl = svc_info("xui-subsync")
        ui_col,   ui_active,   ui_vl   = svc_info("xui-webui")

        # Title line — "  gitsub — XUI Subscription Sync  "
        title_raw = f"  {cyan('gitsub')} {dim('—')} XUI Subscription Sync  "
        title_vis = 2 + len("gitsub") + 3 + len("XUI Subscription Sync  ")

        print()
        print(_top())
        print(_box_line(title_raw))
        print(_sep())
        print(_srow("Services:  sync   ", sync_col, sync_vl))
        print(_srow("           webui  ", ui_col,   ui_vl))
        print(_sep())
        print(_blank())
        print(_mrow("1", "Sync now"))
        print(_mrow("2", "Show all users & URLs"))
        print(_mrow("3", "Lookup user"))
        print(_mrow("4", "Rotate user URL"))
        print(_mrow("5", "File map"))
        print(_mrow("6", "Live logs"))
        print(_mrow("7", "Settings"))
        print(_mrow("8", "Enable SSL"))
        print(_mrow("9", "Restart services"))
        print(_mrow("s", "Service status detail"))
        print(_mrow("u", "Check for updates"))
        print(_mrow("x", "Uninstall"))
        print(_mrow("0", "Exit"))
        print(_blank())
        print(_bot())
        print()

        choice = input("  Choose: ").strip().lower()

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
                cfg = Config()
                print(f"\n  {bold('File Map')}  ({len(submap)} files in {SUBS_DIR})\n")
                print(f"  {'Email':<28}  {'OK'}  {'File':<34}  Updated")
                print(f"  {'-'*28}  {'--'}  {'-'*34}  {'-'*16}")
                for _,v in sorted(submap.items(), key=lambda x: x[1].get("email","")):
                    fp = SUBS_DIR/v.get("filename","")
                    ok = green("✓") if fp.exists() else red("✗")
                    ts = (v.get("updated_ts") or "—")[:16]
                    print(f"  {v.get('email','?'):<28}  {ok}   {v.get('filename','?'):<34}  {dim(ts)}")
                print(f"\n  {dim(cfg.raw_base_url)}")
            input("\n  ENTER to continue...")

        elif choice == "6":
            print(f"\n  {dim('Ctrl+C to stop')}\n")
            try: subprocess.run(["tail","-f",str(LOG_DIR/"sync.log")])
            except KeyboardInterrupt: pass

        elif choice == "7":
            print(f"\n  {cyan('a')}  View all settings")
            print(f"  {cyan('b')}  Edit a setting")
            print(f"  {cyan('0')}  Back")
            sub=input("\n  Choose: ").strip()
            if sub=="a": show_settings(); input("\n  ENTER to continue...")
            elif sub=="b": edit_settings(); input("\n  ENTER to continue...")

        elif choice == "8":
            setup_ssl_menu()
            input("\n  ENTER to continue...")

        elif choice == "9":
            print(f"\n  {cyan('1')}  Both   {cyan('2')}  Sync   {cyan('3')}  Web UI   {cyan('0')}  Back")
            sub=input("\n  Choose: ").strip()
            if sub=="1": subprocess.run(["systemctl","restart","xui-subsync","xui-webui"],check=False); print(green("  Restarted both."))
            elif sub=="2": subprocess.run(["systemctl","restart","xui-subsync"],check=False); print(green("  Sync restarted."))
            elif sub=="3": subprocess.run(["systemctl","restart","xui-webui"],check=False); print(green("  Web UI restarted."))
            input("\n  ENTER to continue...")

        elif choice == "s":
            subprocess.run(["systemctl","status","xui-subsync","xui-webui","--no-pager"])
            input("\n  ENTER to continue...")

        elif choice == "u":
            self_update_interactive()
            input("\n  ENTER to continue...")

        elif choice == "x":
            print(f"\n  {red('Uninstall gitsub?')} This will remove all services and files.")
            confirm = input("  Type 'yes' to confirm: ").strip().lower()
            if confirm == "yes":
                uninstall_path = BASE_DIR/"uninstall.sh"
                if uninstall_path.exists():
                    subprocess.run(["bash",str(uninstall_path)])
                else:
                    print(red("  uninstall.sh not found."))
                print(green("\n  Uninstall complete. Exiting."))
                sys.exit(0)
            else:
                print("  Cancelled.")
                input("\n  ENTER to continue...")

        else:
            print(yellow("  Unknown choice."))

# ── Daemon ─────────────────────────────────────────────────────────────────
def run_daemon(interval):
    log.info(f"Daemon started — interval: {interval}s")
    while True:
        try: Engine().sync()
        except Exception as e: log.error(f"Sync error: {e}")
        log.info(f"Next sync in {interval}s")
        time.sleep(interval)

# ── Main ───────────────────────────────────────────────────────────────────
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
              f"  {cyan('gitsub update')}         update script\n"
              f"  {cyan('gitsub lookup')} <q>     find user\n"
              f"  {cyan('gitsub rotate')} <q>     rotate URL\n"
              f"  {cyan('gitsub status')}         list users\n"
              f"  {cyan('gitsub settings')}       view settings\n"
              f"  {cyan('gitsub settings edit')}  change setting\n"
              f"  {cyan('gitsub webui')}          start web UI\n")
    else:
        print(f"Unknown: {args[0]}. Run 'gitsub help'."); sys.exit(1)
