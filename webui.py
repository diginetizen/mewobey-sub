#!/usr/bin/env python3
"""gitsub WebUI — Dashboard with settings, mobile-friendly"""

import os, sys, json, secrets, subprocess, threading, time
from pathlib import Path
from datetime import datetime
from functools import wraps
from flask import Flask, jsonify, request, redirect, session

BASE_DIR    = Path(__file__).resolve().parent
SUBMAP_FILE = BASE_DIR / "submap.json"
CONFIG_FILE = BASE_DIR / "config.json"

app  = Flask(__name__)
PORT = int(os.getenv("PORT", 2086))

def load_cfg() -> dict:
    if not CONFIG_FILE.exists(): return {}
    with open(CONFIG_FILE) as f: return json.load(f)

def save_cfg(d: dict):
    with open(CONFIG_FILE,"w") as f: json.dump(d,f,indent=2)
    CONFIG_FILE.chmod(0o600)

def load_submap() -> dict:
    if not SUBMAP_FILE.exists(): return {}
    with open(SUBMAP_FILE) as f: return json.load(f)

def fmtts(epoch):
    try: return datetime.utcfromtimestamp(int(epoch)).strftime("%Y-%m-%d %H:%M UTC")
    except: return "—"

def get_or_create_secret() -> str:
    cfg = load_cfg()
    if cfg.get("flask_secret"): return cfg["flask_secret"]
    s = secrets.token_hex(32); cfg["flask_secret"]=s; save_cfg(cfg); return s

app.secret_key = get_or_create_secret()
app.config.update(SESSION_COOKIE_SECURE=False, SESSION_COOKIE_HTTPONLY=True,
                   SESSION_COOKIE_SAMESITE="Lax")
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1, x_for=1)

def check_auth(u, p) -> bool:
    cfg = load_cfg()
    eu  = cfg.get("ui_user","admin")
    ep  = cfg.get("ui_pass","")
    if not ep: return True
    return u==eu and p==ep

def login_required(f):
    @wraps(f)
    def dec(*a, **kw):
        if not session.get("ok"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "unauthorized"}), 401
            return redirect("/login")
        return f(*a, **kw)
    return dec

_syncing = False
_sync_lock = threading.Lock()

def trigger_sync():
    global _syncing
    with _sync_lock:
        if _syncing: return False
        _syncing = True
    def _r():
        global _syncing
        try: subprocess.run([sys.executable, str(BASE_DIR/"update.py"),"sync"], cwd=BASE_DIR)
        finally: _syncing = False
    threading.Thread(target=_r,daemon=True).start(); return True

def svc_status(name) -> dict:
    r = subprocess.run(["systemctl","is-active",name], capture_output=True, text=True)
    active = r.stdout.strip() == "active"
    r2 = subprocess.run(
        ["systemctl","show",name,"--no-page",
         "--property=ActiveState,SubState,ActiveEnterTimestamp,ExecMainPID,MemoryCurrent"],
        capture_output=True, text=True)
    props = {}
    for line in r2.stdout.strip().splitlines():
        if "=" in line: k,v = line.split("=",1); props[k] = v
    mem = props.get("MemoryCurrent","")
    try:    mem_mb = f"{int(mem)/1024/1024:.1f} MB"
    except: mem_mb = "—"
    return {
        "name":   name,
        "active": active,
        "state":  r.stdout.strip(),
        "since":  props.get("ActiveEnterTimestamp","").replace("n/a","").strip() or "—",
        "pid":    props.get("ExecMainPID","—"),
        "memory": mem_mb,
    }

def sync_info() -> dict:
    cfg    = load_cfg()
    submap = load_submap()
    interval = int(cfg.get("sync_interval", 21600))
    last_ts = max((v.get("updated",0) for v in submap.values()), default=0)
    r = subprocess.run(["systemctl","is-active","xui-subsync"], capture_output=True, text=True)
    daemon_active = r.stdout.strip() == "active"
    next_ts = (last_ts + interval) if (daemon_active and last_ts) else None
    now = int(time.time())
    if next_ts and next_ts > now:
        remaining = next_ts - now
        h, m = divmod(remaining // 60, 60)
        countdown = f"{h}h {m}m" if h else f"{m}m {remaining%60}s"
    elif daemon_active and last_ts:
        countdown = "syncing soon"
    else:
        countdown = "—"
    return {
        "mode":          "daemon (auto)" if daemon_active else "manual only",
        "daemon_active": daemon_active,
        "interval":      interval,
        "interval_fmt":  _fmt_interval(interval),
        "last_sync":     fmtts(last_ts) if last_ts else "never",
        "last_ts":       last_ts,
        "next_sync":     fmtts(next_ts) if next_ts else "—",
        "countdown":     countdown,
        "syncing_now":   _syncing,
    }

def _fmt_interval(s):
    s = int(s)
    if s >= 3600: return f"{s//3600}h {(s%3600)//60}m" if s%3600 else f"{s//3600}h"
    if s >= 60:   return f"{s//60}m"
    return f"{s}s"


# ────────────────────────────────────────────────────────────────────────────
# HTML
# ────────────────────────────────────────────────────────────────────────────

LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>gitsub</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#080b10;--card:#0f1318;--brd:#1a2030;
  --acc:#3ECFCF;--txt:#dde3ee;--sub:#5a6478;
  --err:#f05;--font-mono:'DM Mono',monospace;--font-sans:'DM Sans',sans-serif;
}
body{
  background:var(--bg);color:var(--txt);font-family:var(--font-sans);
  min-height:100vh;display:flex;align-items:center;justify-content:center;
  padding:20px;
}
/* Subtle grid background */
body::before{
  content:'';position:fixed;inset:0;
  background-image:linear-gradient(var(--brd) 1px,transparent 1px),
                   linear-gradient(90deg,var(--brd) 1px,transparent 1px);
  background-size:40px 40px;opacity:.35;pointer-events:none;z-index:0;
}
.card{
  position:relative;z-index:1;
  background:var(--card);border:1px solid var(--brd);
  border-radius:12px;padding:40px 36px;width:100%;max-width:360px;
  box-shadow:0 24px 64px rgba(0,0,0,.6);
}
.brand{
  display:flex;align-items:center;gap:10px;margin-bottom:32px;
}
.brand-icon{
  width:36px;height:36px;background:var(--acc);border-radius:8px;
  display:flex;align-items:center;justify-content:center;
  font-family:var(--font-mono);font-size:14px;font-weight:500;color:#080b10;
  flex-shrink:0;
}
.brand-name{font-family:var(--font-mono);font-size:18px;font-weight:500;color:var(--txt)}
.brand-name span{color:var(--sub)}
.field{margin-bottom:18px}
label{
  display:block;font-size:11px;font-weight:500;letter-spacing:.06em;
  color:var(--sub);text-transform:uppercase;margin-bottom:6px;
}
input{
  width:100%;background:#060a0f;border:1px solid var(--brd);
  color:var(--txt);font-family:var(--font-mono);font-size:13px;
  padding:10px 14px;border-radius:8px;outline:none;
  transition:border-color .2s,box-shadow .2s;
}
input:focus{border-color:var(--acc);box-shadow:0 0 0 3px rgba(62,207,207,.12)}
.btn{
  width:100%;margin-top:4px;padding:11px;
  background:var(--acc);border:none;border-radius:8px;
  font-family:var(--font-sans);font-size:14px;font-weight:600;
  color:#080b10;cursor:pointer;transition:opacity .15s,transform .1s;
  letter-spacing:.01em;
}
.btn:hover{opacity:.88}
.btn:active{transform:scale(.98)}
.err{
  font-size:12px;color:var(--err);background:rgba(255,0,85,.08);
  border:1px solid rgba(255,0,85,.2);border-radius:6px;
  padding:9px 12px;margin-bottom:16px;text-align:center;
}
.divider{height:1px;background:var(--brd);margin:24px 0}
</style>
</head>
<body>
<div class="card">
  <div class="brand">
    <div class="brand-icon">gs</div>
    <div class="brand-name">git<span>/</span>sub</div>
  </div>
  {error}
  <form method="POST" action="/login">
    <div class="field">
      <label>Username</label>
      <input type="text" name="username" autocomplete="username" autofocus>
    </div>
    <div class="field">
      <label>Password</label>
      <input type="password" name="password" autocomplete="current-password">
    </div>
    <button class="btn" type="submit">Sign in</button>
  </form>
</div>
</body>
</html>"""


DASH_HTML = r"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>gitsub dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
/* ─── Tokens ─────────────────────────────────── */
:root{
  --bg:#080b10;
  --surf:#0f1318;
  --surf2:#141920;
  --brd:#1a2030;
  --brd2:#222a38;
  --acc:#3ECFCF;
  --acc-dim:rgba(62,207,207,.12);
  --acc-glow:rgba(62,207,207,.25);
  --blue:#4D9FFF;
  --blue-dim:rgba(77,159,255,.12);
  --warn:#F5A623;
  --err:#FF3366;
  --green:#2ECC8D;
  --txt:#dde3ee;
  --txt2:#8a95a8;
  --txt3:#5a6478;
  --mono:'DM Mono',monospace;
  --sans:'DM Sans',sans-serif;
  --r:8px;
  --r-sm:5px;
  --shadow:0 4px 24px rgba(0,0,0,.5);
  --shadow-lg:0 16px 64px rgba(0,0,0,.6);
}
[data-theme="light"]{
  --bg:#f0f2f5;--surf:#ffffff;--surf2:#f7f8fa;--brd:#e0e4ec;--brd2:#d0d5e0;
  --txt:#1a2030;--txt2:#4a5568;--txt3:#8a95a8;--shadow:0 2px 12px rgba(0,0,0,.08);
}

/* ─── Reset ──────────────────────────────────── */
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{
  background:var(--bg);color:var(--txt);font-family:var(--sans);
  font-size:14px;min-height:100vh;line-height:1.5;
  -webkit-font-smoothing:antialiased;
}

/* Grid bg for dark mode */
body::before{
  content:'';position:fixed;inset:0;
  background-image:linear-gradient(var(--brd) 1px,transparent 1px),
                   linear-gradient(90deg,var(--brd) 1px,transparent 1px);
  background-size:48px 48px;opacity:.2;pointer-events:none;z-index:0;
  transition:opacity .3s;
}
[data-theme="light"] body::before{opacity:0}

/* ─── Layout shell ───────────────────────────── */
#app{position:relative;z-index:1;display:flex;flex-direction:column;min-height:100vh}

/* ─── Top bar ────────────────────────────────── */
.topbar{
  display:flex;align-items:center;justify-content:space-between;
  padding:0 24px;height:56px;
  background:rgba(15,19,24,.8);
  backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);
  border-bottom:1px solid var(--brd);
  position:sticky;top:0;z-index:100;
  transition:background .3s;
}
[data-theme="light"] .topbar{background:rgba(255,255,255,.9)}

.brand{display:flex;align-items:center;gap:10px;text-decoration:none}
.brand-icon{
  width:28px;height:28px;background:var(--acc);border-radius:6px;
  display:flex;align-items:center;justify-content:center;
  font-family:var(--mono);font-size:11px;font-weight:500;color:#080b10;flex-shrink:0;
}
.brand-name{font-family:var(--mono);font-size:14px;font-weight:500;color:var(--txt)}
.brand-name em{color:var(--txt3);font-style:normal}

.topbar-center{display:flex;align-items:center;gap:4px}
.tab-btn{
  font-family:var(--sans);font-size:13px;font-weight:500;
  padding:6px 14px;border-radius:var(--r-sm);border:none;
  background:transparent;color:var(--txt2);cursor:pointer;
  transition:all .15s;white-space:nowrap;
}
.tab-btn:hover{background:var(--surf2);color:var(--txt)}
.tab-btn.active{background:var(--acc-dim);color:var(--acc)}

.topbar-right{display:flex;align-items:center;gap:6px}
/* All topbar controls same height */
.topbar-right .btn,
.topbar-right .theme-toggle,
.topbar-right .sync-indicator{height:32px}

/* Sync pulse indicator */
.sync-indicator{
  display:flex;align-items:center;gap:6px;
  font-family:var(--mono);font-size:11px;color:var(--txt3);
  padding:0 10px;border-radius:var(--r-sm);
  border:1px solid var(--brd);background:var(--surf);
  white-space:nowrap;
}
.pulse{
  width:6px;height:6px;border-radius:50%;background:var(--txt3);
  transition:background .3s;
}
.pulse.active{background:var(--warn);animation:blink 1.2s ease-in-out infinite}
.pulse.ok{background:var(--green)}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}

/* ─── Buttons ────────────────────────────────── */
.btn{
  font-family:var(--sans);font-size:13px;font-weight:500;
  padding:0 16px;height:32px;border-radius:var(--r-sm);border:1px solid var(--brd);
  background:var(--surf2);color:var(--txt);cursor:pointer;
  transition:all .15s;white-space:nowrap;display:inline-flex;align-items:center;gap:6px;
}
.btn:hover{border-color:var(--brd2);background:var(--surf);color:var(--txt)}
.btn.primary{background:var(--acc);border-color:var(--acc);color:#080b10;font-weight:600}
.btn.primary:hover{opacity:.88}
.btn.danger{color:var(--err);border-color:rgba(255,51,102,.25);background:transparent}
.btn.danger:hover{background:rgba(255,51,102,.08);border-color:var(--err)}
.btn.ghost{background:transparent;border-color:transparent;color:var(--txt2)}
.btn.ghost:hover{background:var(--surf2);color:var(--txt)}
.btn.sm{padding:0 12px;height:28px;font-size:12px;border-radius:4px}
.btn.xs{padding:0 8px;height:24px;font-size:11px;border-radius:4px;font-family:var(--mono)}
.btn:disabled{opacity:.35;cursor:not-allowed}
.btn.ok-flash{color:var(--green);border-color:var(--green)!important}

/* ─── Panels ─────────────────────────────────── */
.panel{display:none}.panel.active{display:block}

/* ─── Stat strip ─────────────────────────────── */
.stat-strip{
  display:grid;
  grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
  gap:0;background:var(--brd);border-bottom:1px solid var(--brd);
}
.stat-cell{
  background:var(--surf);padding:14px 20px;
  transition:background .15s;
}
.stat-cell:hover{background:var(--surf2)}
.stat-label{
  font-family:var(--mono);font-size:10px;color:var(--txt3);
  text-transform:uppercase;letter-spacing:.08em;margin-bottom:5px;
}
.stat-val{
  font-family:var(--mono);font-size:18px;font-weight:500;color:var(--acc);
}
.stat-val.text{font-size:12px;line-height:1.4;color:var(--txt)}

/* ─── Toolbar ────────────────────────────────── */
.toolbar{
  display:flex;align-items:center;gap:10px;flex-wrap:wrap;
  padding:12px 20px;border-bottom:1px solid var(--brd);
  background:var(--surf);
}
.search-wrap{flex:1;min-width:200px;position:relative}
.search-wrap input{
  width:100%;background:var(--bg);border:1px solid var(--brd);
  color:var(--txt);font-family:var(--mono);font-size:12px;
  padding:8px 12px 8px 32px;border-radius:var(--r-sm);outline:none;
  transition:border-color .2s,box-shadow .2s;
}
.search-wrap input:focus{border-color:var(--acc);box-shadow:0 0 0 3px var(--acc-glow)}
.search-icon{
  position:absolute;left:10px;top:50%;transform:translateY(-50%);
  color:var(--txt3);font-size:13px;pointer-events:none;
}
.count-badge{
  font-family:var(--mono);font-size:11px;color:var(--txt3);
  white-space:nowrap;
}

/* ─── Table ──────────────────────────────────── */
.tbl-wrap{
  overflow-x:auto;-webkit-overflow-scrolling:touch;
  /* Max height so thead can stick within this container */
  max-height:calc(100vh - 200px);overflow-y:auto;
}
table{width:100%;border-collapse:collapse;min-width:560px}
thead{position:sticky;top:0;z-index:10}
thead th{
  font-family:var(--mono);font-size:10px;font-weight:500;
  text-transform:uppercase;letter-spacing:.08em;color:var(--txt3);
  text-align:left;padding:10px 20px;
  background:var(--surf2);border-bottom:1px solid var(--brd);
  white-space:nowrap;
}
tbody tr{border-bottom:1px solid var(--brd);transition:background .1s}
tbody tr:hover{background:var(--surf2)}
tbody td{padding:11px 20px;vertical-align:middle}

.cell-email{
  font-family:var(--sans);font-size:13px;font-weight:500;color:var(--txt);
}
.cell-meta{
  font-family:var(--mono);font-size:10px;color:var(--txt3);margin-top:2px;
}
.url-actions{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.url-anchor{
  font-family:var(--mono);font-size:11px;color:var(--blue);
  text-decoration:none;border:1px solid var(--blue-dim);
  padding:3px 9px;border-radius:4px;white-space:nowrap;
  transition:all .15s;
}
.url-anchor:hover{background:var(--blue-dim);border-color:var(--blue)}
.url-text{
  font-family:var(--mono);font-size:10px;color:var(--txt3);
  margin-top:3px;word-break:break-all;max-width:320px;
}
.updated-cell{
  font-family:var(--mono);font-size:11px;color:var(--txt3);
  white-space:nowrap;
}
.rotate-btn{color:var(--warn);border-color:rgba(245,166,35,.25)}
.rotate-btn:hover{border-color:var(--warn);background:rgba(245,166,35,.08)}

/* Empty state */
.empty{
  text-align:center;padding:64px 20px;color:var(--txt3);
}
.empty-icon{font-size:32px;margin-bottom:12px;opacity:.5}
.empty h3{font-size:15px;font-weight:500;color:var(--txt2);margin-bottom:6px}
.empty p{font-size:13px}

/* ─── Services tab ───────────────────────────── */
.services-wrap{padding:20px;max-width:900px}

.sync-hero{
  background:var(--surf);border:1px solid var(--brd);border-radius:var(--r);
  padding:20px 24px;margin-bottom:20px;
}
.sync-hero-header{
  display:flex;align-items:flex-start;justify-content:space-between;
  flex-wrap:wrap;gap:16px;margin-bottom:16px;
}
.sync-mode-label{
  font-family:var(--mono);font-size:10px;text-transform:uppercase;
  letter-spacing:.08em;color:var(--txt3);margin-bottom:6px;
}
.sync-mode-val{
  font-family:var(--mono);font-size:15px;font-weight:500;
  display:flex;align-items:center;gap:8px;
}
.sync-mode-sub{
  font-size:12px;color:var(--txt3);margin-top:4px;font-family:var(--mono);
}
.interval-row{
  display:flex;align-items:center;gap:8px;flex-wrap:wrap;
}
.interval-label{font-size:12px;color:var(--txt3);font-family:var(--mono)}
.interval-input{
  width:88px;background:var(--bg);border:1px solid var(--brd);
  color:var(--txt);font-family:var(--mono);font-size:12px;
  padding:6px 10px;border-radius:var(--r-sm);outline:none;
  transition:border-color .2s,box-shadow .2s;
}
.interval-input:focus{border-color:var(--acc);box-shadow:0 0 0 3px var(--acc-glow)}
input[type=number]::-webkit-inner-spin-button,
input[type=number]::-webkit-outer-spin-button{-webkit-appearance:none;margin:0}
input[type=number]{-moz-appearance:textfield}

.sync-stats{
  display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));
  gap:1px;background:var(--brd);border-radius:var(--r-sm);overflow:hidden;
}
.sync-stat{background:var(--surf2);padding:10px 14px}
.sync-stat-label{font-family:var(--mono);font-size:10px;color:var(--txt3);text-transform:uppercase;letter-spacing:.06em;margin-bottom:3px}
.sync-stat-val{font-family:var(--mono);font-size:12px;color:var(--txt)}

.svc-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}
.svc-card{
  background:var(--surf);border:1px solid var(--brd);border-radius:var(--r);
  padding:18px 20px;transition:border-color .15s;
}
.svc-card:hover{border-color:var(--brd2)}
.svc-card-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
.svc-name{font-family:var(--mono);font-size:11px;color:var(--txt3);text-transform:uppercase;letter-spacing:.06em}
.svc-dot{width:8px;height:8px;border-radius:50%;background:var(--txt3)}
.svc-dot.running{background:var(--green);box-shadow:0 0 0 3px rgba(46,204,141,.2)}
.svc-dot.failed{background:var(--err)}
.svc-status{font-family:var(--mono);font-size:14px;font-weight:500;margin-bottom:4px}
.svc-status.running{color:var(--green)}
.svc-status.stopped{color:var(--txt3)}
.svc-status.failed{color:var(--err)}
.svc-detail{font-family:var(--mono);font-size:10px;color:var(--txt3);line-height:1.6}
.svc-actions{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap}

/* ─── Settings tab ───────────────────────────── */
.settings-wrap{
  display:grid;grid-template-columns:200px 1fr;min-height:calc(100vh - 120px);
}
.settings-nav{
  border-right:1px solid var(--brd);padding:20px 0;
  background:var(--surf);position:sticky;top:56px;align-self:start;
}
.settings-nav-item{
  display:block;width:100%;text-align:left;padding:9px 20px;border:none;
  background:transparent;font-family:var(--sans);font-size:13px;font-weight:400;
  color:var(--txt2);cursor:pointer;transition:all .15s;border-left:2px solid transparent;
}
.settings-nav-item:hover{background:var(--surf2);color:var(--txt)}
.settings-nav-item.active{color:var(--acc);border-left-color:var(--acc);background:var(--acc-dim);font-weight:500}
.settings-content{padding:24px;max-width:640px}

.settings-section{display:none}.settings-section.active{display:block}
.settings-section h3{
  font-size:16px;font-weight:600;color:var(--txt);
  margin-bottom:6px;padding-bottom:10px;
  border-bottom:1px solid var(--brd);
}
.settings-section .section-desc{
  font-size:13px;color:var(--txt3);margin-bottom:18px;margin-top:10px;
}
.field-group{
  background:var(--surf);border:1px solid var(--brd);border-radius:var(--r);
  overflow:hidden;margin-bottom:16px;
}
.field-row{
  display:grid;grid-template-columns:1fr 1fr 80px;gap:12px;align-items:start;
  padding:14px 16px;border-bottom:1px solid var(--brd);
}
.field-row:last-child{border-bottom:none}
.field-label{font-size:13px;font-weight:500;color:var(--txt);padding-top:2px}
.field-note{font-size:11px;color:var(--txt3);margin-top:3px;line-height:1.4}
.field-input{
  background:var(--bg);border:1px solid var(--brd);
  color:var(--txt);font-family:var(--mono);font-size:12px;
  padding:7px 11px;border-radius:var(--r-sm);outline:none;width:100%;
  transition:border-color .2s,box-shadow .2s;
}
.field-input:focus{border-color:var(--acc);box-shadow:0 0 0 3px var(--acc-glow)}
.field-save{
  align-self:start;padding:7px 14px;font-size:12px;
  background:transparent;border:1px solid var(--brd2);border-radius:var(--r-sm);
  color:var(--txt2);font-family:var(--sans);font-weight:500;
  cursor:pointer;transition:all .15s;white-space:nowrap;
}
.field-save:hover{border-color:var(--acc);color:var(--acc);background:var(--acc-dim)}
.field-save.saved{border-color:var(--green);color:var(--green);background:rgba(46,204,141,.08)}

/* ─── Theme toggle ───────────────────────────── */
.theme-toggle{
  width:32px;height:32px;border-radius:var(--r-sm);border:1px solid var(--brd);
  background:var(--surf2);color:var(--txt2);cursor:pointer;
  display:flex;align-items:center;justify-content:center;font-size:14px;
  transition:all .15s;flex-shrink:0;
}
.theme-toggle:hover{border-color:var(--acc);color:var(--acc);background:var(--acc-dim)}

/* ─── Toast ──────────────────────────────────── */
.toast{
  position:fixed;bottom:24px;right:24px;
  background:var(--surf);border:1px solid var(--brd);
  border-left:3px solid var(--acc);
  padding:12px 18px;border-radius:var(--r);
  font-family:var(--mono);font-size:12px;color:var(--txt);
  box-shadow:var(--shadow-lg);
  opacity:0;transform:translateY(10px) scale(.98);
  transition:all .2s cubic-bezier(.16,1,.3,1);
  pointer-events:none;z-index:9999;max-width:340px;
}
.toast.show{opacity:1;transform:translateY(0) scale(1)}
.toast.err{border-left-color:var(--err)}
.toast.ok{border-left-color:var(--green)}

/* ─── Mobile ─────────────────────────────────── */
@media(max-width:700px){
  .topbar{padding:0 14px}
  .topbar-center{display:none}
  thead th,tbody td{padding:9px 12px}
  .toolbar{padding:10px 12px}
  .url-text{display:none}
  .services-wrap{padding:14px}
  .settings-wrap{grid-template-columns:1fr}
  .settings-nav{border-right:none;border-bottom:1px solid var(--brd);
    display:flex;overflow-x:auto;padding:0;position:static;}
  .settings-nav-item{border-left:none;border-bottom:2px solid transparent;white-space:nowrap}
  .settings-nav-item.active{border-left:none;border-bottom-color:var(--acc)}
  .settings-content{padding:14px}
  .field-row{grid-template-columns:1fr;gap:8px}
  .sync-hero-header{flex-direction:column}
  .svc-cards{grid-template-columns:1fr}
  .mobile-tabs{
    display:flex!important;overflow-x:auto;border-bottom:1px solid var(--brd);
    background:var(--surf);padding:0;
  }
  .stat-strip{grid-template-columns:1fr 1fr}
}
@media(min-width:701px){.mobile-tabs{display:none!important}}
</style>
</head>
<body>
<div id="app">

<!-- ── Top bar ── -->
<header class="topbar">
  <a class="brand" href="/">
    <div class="brand-icon">gs</div>
    <div class="brand-name">git<em>/</em>sub</div>
  </a>

  <!-- Desktop tabs -->
  <nav class="topbar-center">
    <button class="tab-btn active" onclick="switchTab('users',this)">Users</button>
    <button class="tab-btn" onclick="switchTab('services',this)">Services</button>
    <button class="tab-btn" onclick="switchTab('settings',this)">Settings</button>
  </nav>

  <div class="topbar-right">
    <div class="sync-indicator">
      <div class="pulse" id="pulse"></div>
      <span id="sync-label" style="font-family:var(--mono);font-size:11px">idle</span>
    </div>
    <button class="btn primary" id="sync-btn" onclick="doSync()">
      <span>⟳</span><span>Sync</span>
    </button>
    <button class="theme-toggle" onclick="toggleTheme()" title="Toggle theme">☾</button>
    <a href="/logout"><button class="btn danger sm">logout</button></a>
  </div>
</header>

<!-- Mobile tabs -->
<nav class="mobile-tabs">
  <button class="tab-btn active" onclick="switchTab('users',this)">Users</button>
  <button class="tab-btn" onclick="switchTab('services',this)">Services</button>
  <button class="tab-btn" onclick="switchTab('settings',this)">Settings</button>
</nav>

<!-- ════════════════════════════════════════════ -->
<!-- USERS PANEL                                  -->
<!-- ════════════════════════════════════════════ -->
<div class="panel active" id="panel-users">
  <div class="stat-strip" id="stat-strip">
    <div class="stat-cell">
      <div class="stat-label">Total users</div>
      <div class="stat-val" id="stat-total">—</div>
    </div>
    <div class="stat-cell">
      <div class="stat-label">GitHub repo</div>
      <div class="stat-val text" id="stat-repo">—</div>
    </div>
    <div class="stat-cell">
      <div class="stat-label">Last sync</div>
      <div class="stat-val text" id="stat-sync">—</div>
    </div>
  </div>

  <div class="toolbar">
    <div class="search-wrap">
      <span class="search-icon">⌕</span>
      <input type="text" id="search" placeholder="Search by email or sub ID…" oninput="filterTable()">
    </div>
    <span class="count-badge" id="count-badge"></span>
    <button class="btn sm" id="sort-btn" onclick="toggleSort()">↑↓ A–Z</button>
    <button class="btn sm" onclick="copyAllURLs()">copy all URLs</button>
  </div>

  <div class="tbl-wrap" id="tbl-wrap">
    <table>
      <thead>
        <tr>
          <th>Email</th>
          <th>Sub ID / File</th>
          <th>Subscription URL</th>
          <th>Updated</th>
          <th></th>
        </tr>
      </thead>
      <tbody id="tbl-body">
        <tr><td colspan="5"><div class="empty">
          <div class="empty-icon">⟳</div>
          <h3>Loading users…</h3>
        </div></td></tr>
      </tbody>
    </table>
  </div>
</div>

<!-- ════════════════════════════════════════════ -->
<!-- SERVICES PANEL                               -->
<!-- ════════════════════════════════════════════ -->
<div class="panel" id="panel-services">
  <div class="services-wrap">

    <!-- Sync hero card -->
    <div class="sync-hero">
      <div class="sync-hero-header">
        <div>
          <div class="sync-mode-label">Sync daemon</div>
          <div class="sync-mode-val" id="daemon-mode">—</div>
          <div class="sync-mode-sub" id="daemon-next"></div>
        </div>
        <div class="interval-row">
          <span class="interval-label">Interval</span>
          <input class="interval-input" id="interval-val" type="number" min="60">
          <span class="interval-label">sec</span>
          <button class="btn sm" onclick="applyInterval()">Apply</button>
          <button class="btn primary sm" onclick="doSync()">⟳ Sync now</button>
        </div>
      </div>
      <div class="sync-stats">
        <div class="sync-stat">
          <div class="sync-stat-label">Last sync</div>
          <div class="sync-stat-val" id="si-last">—</div>
        </div>
        <div class="sync-stat">
          <div class="sync-stat-label">Next sync</div>
          <div class="sync-stat-val" id="si-next">—</div>
        </div>
        <div class="sync-stat">
          <div class="sync-stat-label">Interval</div>
          <div class="sync-stat-val" id="si-interval">—</div>
        </div>
        <div class="sync-stat">
          <div class="sync-stat-label">Right now</div>
          <div class="sync-stat-val" id="si-now">Idle</div>
        </div>
      </div>
    </div>

    <!-- Service cards -->
    <div class="svc-cards" id="svc-cards">
      <div class="empty"><p>Loading services…</p></div>
    </div>
  </div>
</div>

<!-- ════════════════════════════════════════════ -->
<!-- SETTINGS PANEL                               -->
<!-- ════════════════════════════════════════════ -->
<div class="panel" id="panel-settings">
  <div class="settings-wrap">
    <nav class="settings-nav" id="settings-nav">
      <button class="settings-nav-item active" onclick="switchSection('panel',this)">Panel</button>
      <button class="settings-nav-item" onclick="switchSection('github',this)">GitHub</button>
      <button class="settings-nav-item" onclick="switchSection('sync',this)">Sync</button>
      <button class="settings-nav-item" onclick="switchSection('webui',this)">Web UI</button>
      <button class="settings-nav-item" onclick="switchSection('subs',this)">Subscriptions</button>
      <button class="settings-nav-item" onclick="switchSection('nginx',this)">Nginx</button>
    </nav>

    <div class="settings-content" id="settings-content">
      <!-- dynamically rendered -->
    </div>
  </div>
</div>

</div><!-- #app -->
<div class="toast" id="toast"></div>

<script>
// ── State ────────────────────────────────────
let rows=[], sortDir='asc', pollTimer=null;

// ── Theme ────────────────────────────────────
function initTheme(){
  const saved = localStorage.getItem('gs-theme') || 'dark';
  document.documentElement.dataset.theme = saved;
  document.querySelector('.theme-toggle').textContent = saved==='dark' ? '☾' : '☀';
}
function toggleTheme(){
  const cur = document.documentElement.dataset.theme;
  const next = cur==='dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  localStorage.setItem('gs-theme', next);
  document.querySelector('.theme-toggle').textContent = next==='dark' ? '☾' : '☀';
}
initTheme();

// ── Tabs ─────────────────────────────────────
function switchTab(id, btn){
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  document.getElementById('panel-'+id).classList.add('active');
  document.querySelectorAll('.tab-btn').forEach(b=>{
    if(b.textContent.trim().toLowerCase()===id) b.classList.add('active');
  });
  if(id==='services') loadServices();
  if(id==='settings') initSettings();
}

// ── Toast ────────────────────────────────────
function toast(msg,type=''){
  const el=document.getElementById('toast');
  el.textContent=msg;
  el.className='toast show'+(type?' '+type:'');
  clearTimeout(el._t);
  el._t=setTimeout(()=>el.className='toast',3200);
}

function esc(s){
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Users ────────────────────────────────────
async function loadUsers(){
  const r = await fetch('/api/data');
  if(r.status===401){location='/login';return;}
  const d = await r.json();
  rows = d.entries;
  applySortAndRender();
  document.getElementById('stat-total').textContent = d.total;
  document.getElementById('stat-repo').textContent  = d.repo || '—';
  document.getElementById('stat-sync').textContent  = d.last_sync || 'never';
  document.getElementById('count-badge').textContent= `${d.total} users`;
}

function applySortAndRender(){
  rows.sort((a,b)=> sortDir==='asc'
    ? (a.email||'').localeCompare(b.email||'')
    : (b.email||'').localeCompare(a.email||''));
  filterTable();
}

function filterTable(){
  const q = document.getElementById('search').value.toLowerCase();
  const filtered = q
    ? rows.filter(r=>(r.email||'').toLowerCase().includes(q)||(r.sub_id||'').toLowerCase().includes(q))
    : rows;
  renderRows(filtered);
  document.getElementById('count-badge').textContent =
    q ? `${filtered.length} of ${rows.length}` : `${rows.length} users`;
}

function renderRows(data){
  const tbody = document.getElementById('tbl-body');
  if(!data.length){
    tbody.innerHTML=`<tr><td colspan="5"><div class="empty">
      <div class="empty-icon">◦</div>
      <h3>No users found</h3>
      <p>Run a sync to populate</p>
    </div></td></tr>`;
    return;
  }
  tbody.innerHTML = data.map(r=>`
    <tr>
      <td><div class="cell-email">${esc(r.email)}</div></td>
      <td>
        <div class="cell-meta" title="${esc(r.sub_id)}">${esc(r.sub_id.slice(0,14))}…</div>
        <div class="cell-meta">${esc(r.filename)}</div>
      </td>
      <td>
        <div class="url-actions">
          <a class="url-anchor" href="${esc(r.raw_url)}" target="_blank">open ↗</a>
          <button class="btn xs" onclick="cpURL('${esc(r.raw_url)}',this)">copy</button>
        </div>
        <div class="url-text">${esc(r.raw_url)}</div>
      </td>
      <td class="updated-cell">${esc(r.updated)}</td>
      <td>
        <button class="btn xs rotate-btn" onclick="rotateUser('${esc(r.sub_id)}','${esc(r.email)}')">rotate</button>
      </td>
    </tr>`).join('');
}

function toggleSort(){
  sortDir = sortDir==='asc' ? 'desc' : 'asc';
  document.getElementById('sort-btn').textContent = sortDir==='asc' ? '↑↓ A–Z' : '↑↓ Z–A';
  applySortAndRender();
}

function cpURL(url,btn){
  const done=()=>{
    btn.textContent='✓'; btn.classList.add('ok-flash');
    setTimeout(()=>{btn.textContent='copy';btn.classList.remove('ok-flash')},1600);
  };
  if(navigator.clipboard&&window.isSecureContext)
    navigator.clipboard.writeText(url).then(done);
  else{
    const t=document.createElement('textarea');t.value=url;
    t.style.cssText='position:fixed;opacity:0';
    document.body.appendChild(t);t.focus();t.select();
    document.execCommand('copy');document.body.removeChild(t);done();
  }
}

function copyAllURLs(){
  const urls=rows.map(r=>r.raw_url).join('\n');
  if(navigator.clipboard&&window.isSecureContext)
    navigator.clipboard.writeText(urls).then(()=>toast('Copied all URLs','ok'));
  else{
    const t=document.createElement('textarea');t.value=urls;
    t.style.cssText='position:fixed;opacity:0';
    document.body.appendChild(t);t.focus();t.select();
    document.execCommand('copy');document.body.removeChild(t);
    toast('Copied all URLs','ok');
  }
}

async function rotateUser(sub_id,email){
  if(!confirm(`Rotate URL for ${email}?\n\nThey will need the new link to reconnect.`)) return;
  const r=await fetch('/api/rotate',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({sub_id})});
  const d=await r.json();
  if(d.ok){toast(`Rotated: ${email}`,'ok');loadUsers();}
  else toast(d.msg||'Rotate failed','err');
}

// ── Sync ─────────────────────────────────────
async function doSync(){
  const btn=document.getElementById('sync-btn');
  btn.disabled=true;
  const r=await fetch('/api/sync',{method:'POST'});
  if(r.status===401){location='/login';return;}
  const d=await r.json();
  if(d.ok){
    toast('Sync started…');
    setSyncPulse('syncing');
    pollForSyncEnd();
  } else {
    toast(d.msg||'Already running','err');
    btn.disabled=false;
  }
}

function setSyncPulse(state){
  const p=document.getElementById('pulse');
  const l=document.getElementById('sync-label');
  if(state==='syncing'){p.className='pulse active';l.textContent='syncing';}
  else if(state==='ok'){p.className='pulse ok';l.textContent='idle';setTimeout(()=>{p.className='pulse';},3000);}
  else{p.className='pulse';l.textContent='idle';}
}

function pollForSyncEnd(){
  clearInterval(pollTimer);
  pollTimer=setInterval(async()=>{
    const r=await fetch('/api/sync/status');
    const d=await r.json();
    if(!d.running){
      clearInterval(pollTimer);
      document.getElementById('sync-btn').disabled=false;
      setSyncPulse('ok');
      loadUsers();
      toast('Sync complete ✓','ok');
      // Refresh service info if tab visible
      if(document.getElementById('panel-services').classList.contains('active'))
        loadSyncInfo();
    }
  },2000);
}

// ── Services ─────────────────────────────────
async function loadSyncInfo(){
  const r=await fetch('/api/sync/info');
  if(r.status===401){location='/login';return;}
  const d=await r.json();

  const modeEl=document.getElementById('daemon-mode');
  modeEl.innerHTML = d.daemon_active
    ? `<span style="color:var(--green)">● auto</span> <span style="color:var(--txt3);font-size:12px">daemon running</span>`
    : `<span style="color:var(--warn)">○ manual</span> <span style="color:var(--txt3);font-size:12px">daemon not running</span>`;

  document.getElementById('daemon-next').textContent = d.daemon_active
    ? (d.syncing_now ? '⟳ syncing right now…' : `next sync in ${d.countdown}`)
    : 'start xui-subsync to enable automatic syncing';

  document.getElementById('si-last').textContent     = d.last_sync||'never';
  document.getElementById('si-next').textContent     = d.daemon_active ? d.next_sync : '—';
  document.getElementById('si-interval').textContent = `${d.interval_fmt} (${d.interval}s)`;
  document.getElementById('si-now').textContent      = d.syncing_now ? '⟳ Syncing…' : 'Idle';

  const inp=document.getElementById('interval-val');
  if(inp&&!inp.dataset.touched) inp.value=d.interval;
}

async function applyInterval(){
  const val=parseInt(document.getElementById('interval-val').value);
  if(!val||val<60){toast('Minimum is 60 seconds','err');return;}
  const r=await fetch('/api/settings',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({key:'sync_interval',value:String(val)})});
  const d=await r.json();
  if(d.ok){
    toast('Interval saved — restarting sync daemon…','ok');
    await fetch('/api/service',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({action:'restart',name:'xui-subsync'})});
    setTimeout(loadSyncInfo,1800);
  } else toast(d.msg||'Save failed','err');
}

async function loadServices(){
  await loadSyncInfo();
  const r=await fetch('/api/services');
  if(r.status===401){location='/login';return;}
  const d=await r.json();
  const wrap=document.getElementById('svc-cards');
  wrap.innerHTML=d.services.map(s=>{
    const st=s.active?'running':(s.state==='failed'?'failed':'stopped');
    return `
    <div class="svc-card">
      <div class="svc-card-header">
        <span class="svc-name">${esc(s.name)}</span>
        <span class="svc-dot ${s.active?'running':(s.state==='failed'?'failed':'')}"></span>
      </div>
      <div class="svc-status ${st}">${s.active?'● running':(s.state==='failed'?'✗ failed':'○ stopped')}</div>
      <div class="svc-detail">
        ${s.active?`Since ${esc(s.since)}<br>`:''}
        PID ${esc(s.pid)} · Memory ${esc(s.memory)}
      </div>
      <div class="svc-actions">
        <button class="btn sm" onclick="svcAct('restart','${esc(s.name)}')">restart</button>
        <button class="btn sm ${s.active?'danger':''}" onclick="svcAct('${s.active?'stop':'start'}','${esc(s.name)}')">${s.active?'stop':'start'}</button>
      </div>
    </div>`;
  }).join('');
}

async function svcAct(action,name){
  const r=await fetch('/api/service',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({action,name})});
  const d=await r.json();
  if(d.ok){toast(`${name}: ${action}`,'ok');setTimeout(loadServices,1200);}
  else toast(d.msg||'Failed','err');
}

// ── Settings ─────────────────────────────────
const SECTIONS = {
  panel:{
    title:'Panel Connection',
    desc:'Your 3x-ui panel API credentials.',
    fields:[
      {k:'panel_api_url',label:'Panel base URL',type:'text',
       note:'Full URL with port and optional path. e.g. https://panel.example.com:2053/path'},
      {k:'api_token',label:'API bearer token',type:'password',
       note:'Panel → Settings → Authentication → API token'},
    ]
  },
  github:{
    title:'GitHub Repository',
    desc:'Where subscription files are pushed.',
    fields:[
      {k:'github_user',label:'Username',type:'text',note:'Your GitHub account name'},
      {k:'github_repo',label:'Repository',type:'text',note:'Must be a public repository'},
      {k:'github_branch',label:'Branch',type:'text',note:'Default: main'},
      {k:'deploy_method',label:'Deploy method',type:'text',note:'token — GitHub PAT   /   ssh — deploy key'},
      {k:'github_token',label:'Personal access token',type:'password',note:'Scope: repo (full)'},
      {k:'ssh_key_path',label:'SSH key path',type:'text',note:'Path to private key on this server'},
    ]
  },
  sync:{
    title:'Sync Schedule',
    desc:'How often gitsub fetches from the panel.',
    fields:[
      {k:'sync_interval',label:'Sync interval (seconds)',type:'number',
       note:'Change live in the Services tab too. Restart sync daemon to apply.'},
    ]
  },
  webui:{
    title:'Web UI',
    desc:'Dashboard access credentials and port.',
    fields:[
      {k:'ui_port',label:'Port',type:'number',note:'Service restart required'},
      {k:'ui_user',label:'Username',type:'text'},
      {k:'ui_pass',label:'Password',type:'password'},
    ]
  },
  subs:{
    title:'Subscriptions',
    desc:'Control how subscription files are named and stored.',
    fields:[
      {k:'subs_dir',label:'Folder name in repo',type:'text',
       note:'The GitHub folder holding all .txt files (default: subs)'},
      {k:'filename_mode',label:'Filename mode',type:'text',
       note:'random — secure random string (recommended)   |   email — user\'s email'},
      {k:'filename_length',label:'Random filename length',type:'number',
       note:'Characters in the random part (default: 32)'},
    ]
  },
  nginx:{
    title:'Nginx & Domain',
    desc:'Configure nginx to serve the dashboard via a custom domain.',
    fields:[
      {k:'access_mode',label:'Access mode',type:'text',
       note:'1 = IP address only   |   2 = domain via nginx proxy'},
      {k:'domain',label:'Domain name',type:'text',
       note:'e.g. sub.example.com — must point to this server via DNS A record'},
    ]
  },
};

let cfgCache={}, activeSection='panel';

async function initSettings(){
  const r=await fetch('/api/settings');
  if(r.status===401){location='/login';return;}
  const d=await r.json();
  cfgCache=d.cfg;
  renderSection(activeSection);
}

function switchSection(id,btn){
  activeSection=id;
  document.querySelectorAll('.settings-nav-item').forEach(b=>b.classList.remove('active'));
  if(btn) btn.classList.add('active');
  renderSection(id);
}

function renderSection(id){
  const sec=SECTIONS[id];
  if(!sec) return;
  const content=document.getElementById('settings-content');
  content.innerHTML=`
    <h3>${sec.title}</h3>
    <p class="section-desc">${sec.desc}</p>
    <div class="field-group">
      ${sec.fields.map(f=>`
        <div class="field-row">
          <div>
            <div class="field-label">${f.label}</div>
            ${f.note?`<div class="field-note">${f.note}</div>`:''}
          </div>
          <input class="field-input" id="fi_${f.k}"
            type="${f.type||'text'}"
            value="${f.type==='password'?'':esc(cfgCache[f.k]||'')}"
            placeholder="${f.type==='password'?'(unchanged)':''}">
          <button class="field-save" id="fs_${f.k}"
            onclick="saveSetting('${f.k}','${f.type}')">Save</button>
        </div>`).join('')}
    </div>`;
}

async function saveSetting(key,type){
  const inp=document.getElementById('fi_'+key);
  const btn=document.getElementById('fs_'+key);
  let val=inp.value.trim();
  if(type==='password'&&!val){toast('No change — field is empty');return;}
  const r=await fetch('/api/settings',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({key,value:val})});
  const d=await r.json();
  if(d.ok){
    toast(`Saved: ${key}`,'ok');
    btn.textContent='Saved ✓';btn.classList.add('saved');
    setTimeout(()=>{btn.textContent='Save';btn.classList.remove('saved')},2000);
    if(type!=='password') cfgCache[key]=val;
  } else toast(d.msg||'Save failed','err');
}

// ── Init ─────────────────────────────────────
document.getElementById('interval-val').addEventListener('input',()=>{
  document.getElementById('interval-val').dataset.touched='1';
});
loadUsers();
</script>
</body>
</html>"""


# ── Routes ──────────────────────────────────────────────────────────────────
@app.route("/login", methods=["GET"])
def login_page(): return LOGIN_HTML.replace("{error}","")

@app.route("/login", methods=["POST"])
def login_post():
    u=request.form.get("username",""); p=request.form.get("password","")
    if check_auth(u,p): session["ok"]=True; return redirect("/")
    return LOGIN_HTML.replace("{error}",'<div class="err">Invalid credentials.</div>')

@app.route("/logout")
def logout(): session.clear(); return redirect("/login")

@app.route("/")
@login_required
def index(): return DASH_HTML

@app.route("/api/data")
@login_required
def api_data():
    sm=load_submap(); cfg=load_cfg()
    entries=[]; last=0
    for sid,v in sm.items():
        entries.append({"sub_id":sid,"email":v.get("email","—"),
                        "filename":v.get("filename",""),"raw_url":v.get("raw_url",""),
                        "updated":fmtts(v.get("updated"))})
        if v.get("updated",0)>last: last=v["updated"]
    entries.sort(key=lambda x:x["email"])
    return jsonify({"total":len(entries),"entries":entries,
                    "repo":f"{cfg.get('github_user','')}/{cfg.get('github_repo','')}",
                    "last_sync":fmtts(last) if last else "never"})

@app.route("/api/sync", methods=["POST"])
@login_required
def api_sync():
    if trigger_sync(): return jsonify({"ok":True})
    return jsonify({"ok":False,"msg":"Already running"}), 409

@app.route("/api/sync/status")
@login_required
def api_sync_status(): return jsonify({"running":_syncing})

@app.route("/api/sync/info")
@login_required
def api_sync_info(): return jsonify(sync_info())

@app.route("/api/rotate", methods=["POST"])
@login_required
def api_rotate():
    data=request.get_json(silent=True) or {}; sid=data.get("sub_id","").strip()
    if not sid: return jsonify({"ok":False,"msg":"sub_id required"}),400
    sm=load_submap()
    if sid not in sm: return jsonify({"ok":False,"msg":"Not found"}),404
    email=sm[sid].get("email",sid)
    r=subprocess.run([sys.executable,str(BASE_DIR/"update.py"),"rotate",email],
                     cwd=BASE_DIR,capture_output=True,text=True)
    return jsonify({"ok":r.returncode==0,"msg":r.stderr or None})

@app.route("/api/services")
@login_required
def api_services():
    return jsonify({"services":[svc_status(s) for s in ["xui-subsync","xui-webui"]]})

@app.route("/api/service", methods=["POST"])
@login_required
def api_service():
    data=request.get_json(silent=True) or {}
    action=data.get("action",""); name=data.get("name","")
    if action not in {"start","stop","restart"} or name not in {"xui-subsync","xui-webui"}:
        return jsonify({"ok":False,"msg":"Not allowed"}),400
    r=subprocess.run(["systemctl",action,name],capture_output=True,text=True)
    return jsonify({"ok":r.returncode==0,"msg":r.stderr.strip() or None})

EDITABLE={"panel_api_url","api_token","github_user","github_repo","github_branch",
          "deploy_method","github_token","ssh_key_path","sync_interval","ui_port",
          "ui_user","ui_pass","filename_length","filename_mode","domain","access_mode","subs_dir"}
NUMERIC ={"sync_interval","ui_port","filename_length"}

@app.route("/api/settings")
@login_required
def api_settings():
    cfg=load_cfg(); safe=dict(cfg)
    for k in ("api_token","github_token","ui_pass","flask_secret"):
        if safe.get(k): safe[k]=""
    return jsonify({"cfg":safe})

@app.route("/api/settings", methods=["POST"])
@login_required
def api_settings_save():
    data=request.get_json(silent=True) or {}
    key=data.get("key",""); val=data.get("value","")
    if key not in EDITABLE: return jsonify({"ok":False,"msg":"Not editable"}),400
    cfg=load_cfg()
    if key in NUMERIC:
        try: val=int(val)
        except: return jsonify({"ok":False,"msg":"Must be a number"}),400
    cfg[key]=val; save_cfg(cfg)
    return jsonify({"ok":True})

if __name__=="__main__":
    print(f"  gitsub WebUI → http://0.0.0.0:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
