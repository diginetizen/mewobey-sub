#!/usr/bin/env python3
"""gitsub WebUI — Dashboard with settings, mobile-friendly"""

import os, sys, json, secrets, subprocess, threading, time
from pathlib import Path
from datetime import datetime
from functools import wraps
from flask import Flask, jsonify, request, redirect, session, Response

BASE_DIR    = Path(__file__).resolve().parent
SUBMAP_FILE = BASE_DIR / "submap.json"
CONFIG_FILE = BASE_DIR / "config.json"

app  = Flask(__name__)
PORT = int(os.getenv("PORT", 2086))

# ── Config ─────────────────────────────────────────────────────────────────
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

# Flask config
app.secret_key = get_or_create_secret()
app.config.update(SESSION_COOKIE_SECURE=False, SESSION_COOKIE_HTTPONLY=True,
                   SESSION_COOKIE_SAMESITE="Lax")
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1, x_for=1)

# ── Auth ───────────────────────────────────────────────────────────────────
def check_auth(u, p) -> bool:
    cfg = load_cfg()
    eu  = cfg.get("ui_user","admin")
    ep  = cfg.get("ui_pass","")
    if not ep: return True  # no password set = open
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

# ── Sync state ─────────────────────────────────────────────────────────────
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

# ── Service status ─────────────────────────────────────────────────────────
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
    # Get memory in MB if available
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
    """Return current sync mode, interval, last/next sync times."""
    cfg    = load_cfg()
    submap = load_submap()
    interval = int(cfg.get("sync_interval", 21600))

    # Find last sync time from submap
    last_ts = max((v.get("updated",0) for v in submap.values()), default=0)

    # Check if daemon is running
    r = subprocess.run(["systemctl","is-active","xui-subsync"], capture_output=True, text=True)
    daemon_active = r.stdout.strip() == "active"

    mode = "daemon (auto)" if daemon_active else "manual only"

    # Next sync = last_ts + interval (only meaningful if daemon running)
    next_ts = (last_ts + interval) if (daemon_active and last_ts) else None

    # Time until next sync
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
        "mode":          mode,
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

# ── HTML ───────────────────────────────────────────────────────────────────
LOGIN_HTML = """<!DOCTYPE html><html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>gitsub login</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d0f12;color:#c8d0e0;font-family:'IBM Plex Mono',monospace;
     min-height:100vh;display:flex;align-items:center;justify-content:center;padding:16px}
.box{background:#14171d;border:1px solid #1e2330;border-radius:8px;padding:36px 32px;width:100%;max-width:340px}
.logo{color:#00d4aa;font-size:20px;font-weight:600;margin-bottom:28px;text-align:center}
.logo span{color:#545e72;font-weight:400}
label{display:block;font-size:10px;color:#545e72;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}
input{width:100%;background:#0d0f12;border:1px solid #1e2330;color:#c8d0e0;
      font-family:'IBM Plex Mono',monospace;font-size:13px;padding:9px 12px;
      border-radius:4px;outline:none;transition:border-color .15s;margin-bottom:18px}
input:focus{border-color:#00d4aa}
button{width:100%;background:#00d4aa;border:none;color:#0d0f12;
       font-family:'IBM Plex Mono',monospace;font-size:13px;font-weight:600;
       padding:11px;border-radius:4px;cursor:pointer;transition:opacity .15s}
button:hover{opacity:.85}
.err{color:#ff4d6d;font-size:12px;margin-bottom:14px;text-align:center}
</style></head>
<body><div class="box">
<div class="logo">git<span>/</span>sub</div>
{error}
<form method="POST" action="/login">
  <label>Username</label><input type="text" name="username" autocomplete="username" autofocus>
  <label>Password</label><input type="password" name="password" autocomplete="current-password">
  <button type="submit">Sign in</button>
</form>
</div></body></html>"""

DASH_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>gitsub</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#0d0f12;--surf:#14171d;--brd:#1e2330;
  --acc:#00d4aa;--acc2:#007aff;--warn:#ff9f43;--err:#ff4d6d;
  --txt:#c8d0e0;--mut:#545e72;
  --mono:'IBM Plex Mono',monospace;--sans:'IBM Plex Sans',sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--txt);font-family:var(--sans);font-size:14px;min-height:100vh}

/* Nav */
nav{display:flex;align-items:center;justify-content:space-between;padding:14px 20px;
    background:var(--surf);border-bottom:1px solid var(--brd);position:sticky;top:0;z-index:20}
.logo{font-family:var(--mono);font-size:15px;font-weight:600;color:var(--acc)}
.logo span{color:var(--mut);font-weight:400}
.nav-r{display:flex;align-items:center;gap:8px}
.pill{font-family:var(--mono);font-size:11px;padding:5px 12px;border-radius:20px;
      border:1px solid var(--brd);background:transparent;color:var(--txt);cursor:pointer;transition:all .15s}
.pill:hover{border-color:var(--acc);color:var(--acc)}
.pill.primary{background:var(--acc);border-color:var(--acc);color:#0d0f12}
.pill.primary:hover{opacity:.85}
.pill.danger{color:var(--err);border-color:rgba(255,77,109,.3)}
.pill.danger:hover{border-color:var(--err)!important;color:var(--err)!important}
.pill:disabled{opacity:.35;cursor:not-allowed}

/* Tab bar */
.tabs{display:flex;border-bottom:1px solid var(--brd);background:var(--surf);overflow-x:auto}
.tab{font-family:var(--mono);font-size:12px;padding:12px 20px;cursor:pointer;
     border:none;background:transparent;color:var(--mut);white-space:nowrap;
     border-bottom:2px solid transparent;transition:all .15s}
.tab.active{color:var(--acc);border-bottom-color:var(--acc)}
.tab:hover:not(.active){color:var(--txt)}

/* Panels */
.panel{display:none;padding:0}.panel.active{display:block}

/* Stats */
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:1px;background:var(--brd)}
.stat{background:var(--surf);padding:14px 18px}
.stat-l{font-family:var(--mono);font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:1px;margin-bottom:4px}
.stat-v{font-family:var(--mono);font-size:20px;font-weight:600;color:var(--acc)}
.stat-v.sm{font-size:12px;padding-top:2px;line-height:1.4}

/* Services */
.svc-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;padding:16px 20px}
.svc-card{background:var(--surf);border:1px solid var(--brd);border-radius:6px;padding:16px}
.svc-name{font-family:var(--mono);font-size:12px;color:var(--mut);margin-bottom:8px;text-transform:uppercase;letter-spacing:1px}
.svc-state{font-family:var(--mono);font-size:16px;font-weight:600;margin-bottom:6px}
.svc-state.active{color:var(--acc)}
.svc-state.inactive,.svc-state.failed{color:var(--err)}
.svc-state.other{color:var(--warn)}
.svc-since{font-family:var(--mono);font-size:10px;color:var(--mut)}
.svc-actions{display:flex;gap:8px;margin-top:12px}

/* Toolbar */
.toolbar{display:flex;align-items:center;gap:10px;padding:12px 20px;border-bottom:1px solid var(--brd);flex-wrap:wrap}
.srch{flex:1;min-width:180px;position:relative}
.srch input{width:100%;background:var(--surf);border:1px solid var(--brd);
            color:var(--txt);font-family:var(--mono);font-size:12px;
            padding:8px 10px 8px 28px;border-radius:4px;outline:none;transition:border-color .15s}
.srch input:focus{border-color:var(--acc)}
.srch-ic{position:absolute;left:9px;top:50%;transform:translateY(-50%);color:var(--mut);font-size:12px;pointer-events:none}
.cnt{font-family:var(--mono);font-size:11px;color:var(--mut);white-space:nowrap}

/* Table */
.tbl-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{width:100%;border-collapse:collapse;min-width:520px}
thead th{font-family:var(--mono);font-size:10px;font-weight:500;text-transform:uppercase;
         letter-spacing:1px;color:var(--mut);text-align:left;padding:9px 16px;
         border-bottom:1px solid var(--brd);background:var(--surf);white-space:nowrap}
tbody tr{border-bottom:1px solid var(--brd);transition:background .1s}
tbody tr:hover{background:var(--surf)}
tbody td{padding:10px 16px;font-family:var(--mono);font-size:12px;vertical-align:top}
.td-email{font-weight:500;color:var(--txt)}
.td-meta{color:var(--mut);font-size:10px;margin-top:2px}
.url-wrap{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.url-link{color:var(--acc2);text-decoration:none;border:1px solid rgba(0,122,255,.25);
          border-radius:3px;padding:2px 8px;font-size:10px;transition:all .1s;white-space:nowrap}
.url-link:hover{background:rgba(0,122,255,.1);border-color:var(--acc2)}
.url-text{font-size:10px;color:var(--mut);margin-top:3px;word-break:break-all}
.cp{font-size:10px;padding:2px 8px;border-radius:3px;border:1px solid var(--brd);
    background:transparent;color:var(--txt);cursor:pointer;transition:all .1s;font-family:var(--mono)}
.cp:hover{border-color:var(--acc);color:var(--acc)}
.cp.ok{color:var(--acc);border-color:var(--acc)}
.rot{font-size:10px;padding:2px 8px;border-radius:3px;border:1px solid rgba(255,159,67,.3);
     background:transparent;color:var(--warn);cursor:pointer;font-family:var(--mono);transition:all .1s}
.rot:hover{border-color:var(--warn)}

/* Settings */
.settings-wrap{max-width:680px;padding:20px}
.set-group{margin-bottom:24px}
.set-group-title{font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:1px;
                 color:var(--mut);margin-bottom:12px;padding-bottom:6px;border-bottom:1px solid var(--brd)}
.set-row{display:grid;grid-template-columns:1fr 1fr auto;gap:10px;align-items:center;
         padding:10px 0;border-bottom:1px solid rgba(30,35,48,.5)}
.set-row:last-child{border:none}
.set-label{font-family:var(--mono);font-size:12px;color:var(--txt)}
.set-input{background:var(--bg);border:1px solid var(--brd);color:var(--txt);
           font-family:var(--mono);font-size:12px;padding:6px 10px;border-radius:4px;
           outline:none;width:100%;transition:border-color .15s}
.set-input:focus{border-color:var(--acc)}
.set-save{font-family:var(--mono);font-size:11px;padding:6px 14px;border-radius:4px;
          border:1px solid var(--acc);background:transparent;color:var(--acc);
          cursor:pointer;white-space:nowrap;transition:all .15s}
.set-save:hover{background:var(--acc);color:#0d0f12}
.set-note{font-size:10px;color:var(--mut);margin-top:3px}

/* Sync dot */
.dot{width:7px;height:7px;border-radius:50%;background:var(--mut);display:inline-block;margin-right:5px}
.dot.on{background:var(--warn);animation:pulse 1s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}

/* Toast */
.toast{position:fixed;bottom:20px;right:20px;background:var(--surf);border:1px solid var(--brd);
       border-left:3px solid var(--acc);padding:10px 16px;font-family:var(--mono);font-size:12px;
       border-radius:4px;box-shadow:0 8px 24px rgba(0,0,0,.5);opacity:0;transform:translateY(8px);
       transition:all .2s;pointer-events:none;z-index:100;max-width:calc(100vw - 40px)}
.toast.show{opacity:1;transform:translateY(0)}
.toast.err{border-left-color:var(--err)}

/* Empty */
.empty{text-align:center;padding:48px 20px;color:var(--mut);font-family:var(--mono)}
.empty h3{font-size:14px;margin-bottom:6px;color:var(--txt)}

/* Mobile */
@media(max-width:600px){
  nav{padding:12px 14px}
  .pill{padding:5px 10px;font-size:10px}
  thead th,tbody td{padding:8px 12px}
  .toolbar{padding:10px 12px}
  .settings-wrap{padding:14px}
  .set-row{grid-template-columns:1fr;gap:6px}
  .svc-grid{padding:12px}
  .stat-v{font-size:16px}
  .url-text{display:none}
}
</style>
</head>
<body>

<nav>
  <div class="logo">git<span>/</span>sub</div>
  <div class="nav-r">
    <span style="font-family:var(--mono);font-size:11px;color:var(--mut)">
      <span class="dot" id="sdot"></span><span id="sstat">idle</span>
    </span>
    <button class="pill primary" id="sync-btn" onclick="doSync()">⟳ Sync</button>
    <a href="/logout"><button class="pill danger">logout</button></a>
  </div>
</nav>

<div class="tabs">
  <button class="tab active" onclick="showTab('users',this)">Users</button>
  <button class="tab" onclick="showTab('services',this)">Services</button>
  <button class="tab" onclick="showTab('settings',this)">Settings</button>
</div>

<!-- USERS TAB -->
<div class="panel active" id="tab-users">
  <div class="stats" id="stats-bar">
    <div class="stat"><div class="stat-l">Total Users</div><div class="stat-v" id="s-tot">—</div></div>
    <div class="stat"><div class="stat-l">GitHub Repo</div><div class="stat-v sm" id="s-repo">—</div></div>
    <div class="stat"><div class="stat-l">Last Sync</div><div class="stat-v sm" id="s-sync">—</div></div>
  </div>
  <div class="toolbar">
    <div class="srch"><span class="srch-ic">⌕</span>
      <input id="q" type="text" placeholder="filter by email or sub ID…" oninput="filter()">
    </div>
    <span class="cnt" id="cnt"></span>
    <button class="pill" onclick="copyAll()">copy all URLs</button>
  </div>
  <div class="tbl-wrap">
    <table>
      <thead><tr>
        <th>Email</th><th>Sub ID · File</th><th>Raw URL</th><th>Updated</th><th></th>
      </tr></thead>
      <tbody id="tbody"><tr><td colspan="5"><div class="empty"><h3>Loading…</h3></div></td></tr></tbody>
    </table>
  </div>
</div>

<!-- SERVICES TAB -->
<div class="panel" id="tab-services">
  <!-- Sync status panel -->
  <div id="sync-panel" style="padding:16px 20px;border-bottom:1px solid var(--brd);background:var(--surf)">
    <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px">
      <div>
        <div style="font-family:var(--mono);font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:1px;margin-bottom:6px">Sync Daemon</div>
        <div id="sync-mode-badge" style="font-family:var(--mono);font-size:14px;font-weight:600">—</div>
        <div id="sync-next" style="font-family:var(--mono);font-size:11px;color:var(--mut);margin-top:4px"></div>
      </div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <div style="font-family:var(--mono);font-size:11px;color:var(--mut)">Interval:</div>
        <input id="interval-input" type="number" min="60"
               style="width:90px;background:var(--bg);border:1px solid var(--brd);color:var(--txt);
                      font-family:var(--mono);font-size:12px;padding:6px 8px;border-radius:4px;outline:none">
        <span style="font-family:var(--mono);font-size:11px;color:var(--mut)">seconds</span>
        <button class="pill" onclick="saveInterval()">Apply</button>
        <button class="pill primary" onclick="doSync()">⟳ Sync Now</button>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:1px;background:var(--brd);margin-top:14px;border-radius:4px;overflow:hidden">
      <div style="background:var(--bg);padding:10px 14px">
        <div style="font-family:var(--mono);font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:1px;margin-bottom:3px">Last sync</div>
        <div id="si-last" style="font-family:var(--mono);font-size:12px">—</div>
      </div>
      <div style="background:var(--bg);padding:10px 14px">
        <div style="font-family:var(--mono);font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:1px;margin-bottom:3px">Next sync</div>
        <div id="si-next" style="font-family:var(--mono);font-size:12px">—</div>
      </div>
      <div style="background:var(--bg);padding:10px 14px">
        <div style="font-family:var(--mono);font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:1px;margin-bottom:3px">Interval</div>
        <div id="si-interval" style="font-family:var(--mono);font-size:12px">—</div>
      </div>
      <div style="background:var(--bg);padding:10px 14px">
        <div style="font-family:var(--mono);font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:1px;margin-bottom:3px">Status now</div>
        <div id="si-now" style="font-family:var(--mono);font-size:12px">—</div>
      </div>
    </div>
  </div>
  <div class="svc-grid" id="svc-grid">
    <div class="empty"><h3>Loading…</h3></div>
  </div>
</div>

<!-- SETTINGS TAB -->
<div class="panel" id="tab-settings">
  <div class="settings-wrap" id="settings-wrap">
    <div class="empty"><h3>Loading…</h3></div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
let rows=[], pollTimer;

// ── Tabs ──────────────────────────────────────
function showTab(id, btn) {
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.getElementById('tab-'+id).classList.add('active');
  btn.classList.add('active');
  if(id==='services') loadServices();
  if(id==='settings') loadSettings();
}

// ── Toast ─────────────────────────────────────
function toast(msg,type=''){
  const el=document.getElementById('toast');
  el.textContent=msg; el.className='toast show'+(type?' '+type:'');
  clearTimeout(el._t); el._t=setTimeout(()=>el.className='toast',3000);
}

function esc(s){
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Users ─────────────────────────────────────
async function loadData(){
  const r=await fetch('/api/data');
  if(r.status===401){location='/login';return;}
  const d=await r.json();
  rows=d.entries; render(rows);
  document.getElementById('s-tot').textContent=d.total;
  document.getElementById('s-repo').textContent=d.repo||'—';
  document.getElementById('s-sync').textContent=d.last_sync||'—';
  document.getElementById('cnt').textContent=`${d.total} users`;
}

function render(data){
  const tb=document.getElementById('tbody');
  if(!data.length){tb.innerHTML='<tr><td colspan="5"><div class="empty"><h3>No users yet</h3><p>Run a sync.</p></div></td></tr>';return;}
  tb.innerHTML=data.map(r=>`
    <tr>
      <td class="td-email">${esc(r.email)}</td>
      <td>
        <div class="td-meta" title="${esc(r.sub_id)}">${esc(r.sub_id.slice(0,14))}…</div>
        <div class="td-meta">${esc(r.filename)}</div>
      </td>
      <td>
        <div class="url-wrap">
          <a class="url-link" href="${esc(r.raw_url)}" target="_blank">open ↗</a>
          <button class="cp" onclick="cpURL('${esc(r.raw_url)}',this)">copy</button>
        </div>
        <div class="url-text">${esc(r.raw_url)}</div>
      </td>
      <td style="color:var(--mut);font-size:11px">${esc(r.updated)}</td>
      <td><button class="rot" onclick="rotate('${esc(r.sub_id)}','${esc(r.email)}')">rotate</button></td>
    </tr>`).join('');
}

function filter(){
  const q=document.getElementById('q').value.toLowerCase();
  const f=q?rows.filter(r=>(r.email||'').toLowerCase().includes(q)||(r.sub_id||'').toLowerCase().includes(q)):rows;
  render(f);
  document.getElementById('cnt').textContent=`${f.length}/${rows.length} users`;
}

function cpURL(url,btn){
  const done=()=>{btn.textContent='✓';btn.classList.add('ok');setTimeout(()=>{btn.textContent='copy';btn.classList.remove('ok')},1500)};
  if(navigator.clipboard&&window.isSecureContext) navigator.clipboard.writeText(url).then(done);
  else{const t=document.createElement('textarea');t.value=url;t.style.cssText='position:fixed;opacity:0';document.body.appendChild(t);t.focus();t.select();document.execCommand('copy');document.body.removeChild(t);done();}
}

function copyAll(){
  const urls=rows.map(r=>r.raw_url).join('\n');
  if(navigator.clipboard&&window.isSecureContext) navigator.clipboard.writeText(urls).then(()=>toast('Copied all URLs'));
  else{const t=document.createElement('textarea');t.value=urls;t.style.cssText='position:fixed;opacity:0';document.body.appendChild(t);t.focus();t.select();document.execCommand('copy');document.body.removeChild(t);toast('Copied all URLs');}
}

async function doSync(){
  document.getElementById('sync-btn').disabled=true;
  const r=await fetch('/api/sync',{method:'POST'});
  if(r.status===401){location='/login';return;}
  const d=await r.json();
  if(d.ok){toast('Sync started…');pollSync();}
  else{toast(d.msg||'Already running','err');document.getElementById('sync-btn').disabled=false;}
}

function pollSync(){
  clearInterval(pollTimer);
  pollTimer=setInterval(async()=>{
    const r=await fetch('/api/sync/status');
    const d=await r.json();
    const dot=document.getElementById('sdot'),st=document.getElementById('sstat'),btn=document.getElementById('sync-btn');
    if(d.running){dot.className='dot on';st.textContent='syncing';}
    else{dot.className='dot';st.textContent='idle';btn.disabled=false;clearInterval(pollTimer);loadData();toast('Sync complete ✓');}
  },2000);
}

async function rotate(sub_id,email){
  if(!confirm(`Rotate URL for ${email}?\nThey will need the new subscription link.`))return;
  const r=await fetch('/api/rotate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sub_id})});
  const d=await r.json();
  if(d.ok){toast(`Rotated: ${email}`);loadData();}else toast(d.msg||'Failed','err');
}

// ── Services ──────────────────────────────────
async function loadSyncInfo(){
  const r=await fetch('/api/sync/info');
  if(r.status===401){location='/login';return;}
  const d=await r.json();
  const badge=document.getElementById('sync-mode-badge');
  const inp=document.getElementById('interval-input');
  badge.textContent=d.daemon_active?'● Auto (daemon running)':'○ Manual only';
  badge.style.color=d.daemon_active?'var(--acc)':'var(--warn)';
  document.getElementById('sync-next').textContent=
    d.daemon_active?(d.syncing_now?'Syncing now…':'Next in: '+d.countdown):'Daemon not running — syncs are manual only';
  document.getElementById('si-last').textContent=d.last_sync||'never';
  document.getElementById('si-next').textContent=d.daemon_active?d.next_sync:'—';
  document.getElementById('si-interval').textContent=d.interval_fmt+' ('+d.interval+'s)';
  document.getElementById('si-now').textContent=d.syncing_now?'🔄 Syncing…':'Idle';
  if(inp&&!inp.dataset.dirty) inp.value=d.interval;
}

async function saveInterval(){
  const val=parseInt(document.getElementById('interval-input').value);
  if(!val||val<60){toast('Minimum 60 seconds','err');return;}
  const r=await fetch('/api/settings',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({key:'sync_interval',value:String(val)})});
  const d=await r.json();
  if(d.ok){
    toast('Interval saved. Restarting sync daemon…');
    await fetch('/api/service',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({action:'restart',name:'xui-subsync'})});
    setTimeout(loadSyncInfo,2000);
  } else toast(d.msg||'Save failed','err');
}

async function loadServices(){
  loadSyncInfo();
  const r=await fetch('/api/services');
  if(r.status===401){location='/login';return;}
  const d=await r.json();
  const grid=document.getElementById('svc-grid');
  grid.innerHTML=d.services.map(s=>`
    <div class="svc-card">
      <div class="svc-name">${esc(s.name)}</div>
      <div class="svc-state ${s.active?'active':s.state==='failed'?'failed':'other'}">
        ${s.active?'● active':'○ '+esc(s.state)}
      </div>
      <div class="svc-since">${s.active?'Since: ':''} ${esc(s.since)}</div>
      <div class="svc-actions">
        <button class="pill" onclick="svcAction('restart','${esc(s.name)}')">restart</button>
        <button class="pill" onclick="svcAction(s.active?'stop':'start','${esc(s.name)}')">
          ${s.active?'stop':'start'}
        </button>
      </div>
    </div>`).join('');
}

async function svcAction(action,name){
  const r=await fetch('/api/service',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,name})});
  const d=await r.json();
  if(d.ok){toast(`${action} ${name}`);setTimeout(loadServices,1500);}else toast(d.msg||'Failed','err');
}

// ── Settings ──────────────────────────────────
const SETTINGS_GROUPS = [
  {title:'Panel', fields:[
    {k:'panel_api_url', label:'Panel API Base URL', type:'text'},
    {k:'api_token',     label:'API Token',          type:'password'},
  ]},
  {title:'GitHub', fields:[
    {k:'github_user',   label:'Username',   type:'text'},
    {k:'github_repo',   label:'Repo',       type:'text'},
    {k:'github_branch', label:'Branch',     type:'text'},
    {k:'deploy_method', label:'Method (token/ssh)', type:'text'},
    {k:'github_token',  label:'Token',      type:'password'},
    {k:'ssh_key_path',  label:'SSH Key Path', type:'text'},
  ]},
  {title:'Sync', fields:[
    {k:'sync_interval', label:'Sync Interval (seconds)', type:'number', note:'Or change live in the Services tab'},
  ]},
  {title:'Web UI', fields:[
    {k:'ui_port', label:'Port',     type:'number', note:'Requires service restart'},
    {k:'ui_user', label:'Username', type:'text'},
    {k:'ui_pass', label:'Password', type:'password'},
    {k:'certbot_port', label:'Certbot challenge port', type:'text', note:'Port used when requesting Let\'s Encrypt cert (default 80)'},
  ]},
  {title:'Subscriptions', fields:[
    {k:'subs_dir',      label:'Subs folder name in repo', type:'text', note:'Folder where .txt files are stored (e.g. subs)'},
    {k:'filename_mode', label:'Filename mode',             type:'text', note:'random — secure random string   |   email — user email as filename'},
    {k:'filename_length',label:'Random filename length',  type:'number'},
  ]},
  {title:'Access & Domain', fields:[
    {k:'access_mode', label:'Access Mode', type:'text',
     note:'1=IP only  2=IP+domain HTTP  3=IP+domain+HTTPS  4=IP+HTTPS'},
    {k:'domain',      label:'Domain Name', type:'text',   note:'e.g. sub.example.com (used for modes 2 and 3)'},
    {k:'ssl_mode',    label:'SSL Mode',    type:'text',   note:'none / certbot / manual / later'},
    {k:'ssl_cert',    label:'SSL Cert Path (fullchain.pem)', type:'text'},
    {k:'ssl_key',     label:'SSL Key Path (privkey.pem)',    type:'text'},
    {k:'ssl_email',   label:'SSL Email (Let\'s Encrypt)',    type:'text'},
  ]},

];

async function loadSettings(){
  const r=await fetch('/api/settings');
  if(r.status===401){location='/login';return;}
  const d=await r.json();
  const wrap=document.getElementById('settings-wrap');
  wrap.innerHTML=SETTINGS_GROUPS.map(g=>`
    <div class="set-group">
      <div class="set-group-title">${g.title}</div>
      ${g.fields.map(f=>`
        <div class="set-row">
          <div>
            <div class="set-label">${f.label}</div>
            ${f.note?`<div class="set-note">${f.note}</div>`:''}
          </div>
          <input class="set-input" id="s_${f.k}" type="${f.type||'text'}"
                 value="${f.type==='password'?'':esc(d.cfg[f.k]||'')}"
                 placeholder="${f.type==='password'?'(unchanged)':''}">
          <button class="set-save" onclick="saveSetting('${f.k}','${f.type}')">Save</button>
        </div>`).join('')}
    </div>`).join('');
}

async function saveSetting(key, type){
  const input=document.getElementById('s_'+key);
  let val=input.value;
  if(type==='password'&&!val){toast('No change (empty)');return;}
  const r=await fetch('/api/settings',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({key,value:val})});
  const d=await r.json();
  if(d.ok) toast(`Saved: ${key}`);
  else toast(d.msg||'Save failed','err');
}

loadData();
</script>
</body></html>"""

# ── Routes ─────────────────────────────────────────────────────────────────
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
    if trigger_sync():
        return jsonify({"ok": True})
    return jsonify({"ok": False, "msg": "Already running"}), 409

@app.route("/api/sync/status")
@login_required
def api_sync_status(): return jsonify({"running":_syncing})
@app.route("/api/sync/info")
@login_required
def api_sync_info():
    return jsonify(sync_info())



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
    svcs=["xui-subsync","xui-webui"]
    return jsonify({"services":[svc_status(s) for s in svcs]})

@app.route("/api/service", methods=["POST"])
@login_required
def api_service():
    data=request.get_json(silent=True) or {}
    action=data.get("action",""); name=data.get("name","")
    allowed={"start","stop","restart"}
    svc_allowed={"xui-subsync","xui-webui"}
    if action not in allowed or name not in svc_allowed:
        return jsonify({"ok":False,"msg":"Not allowed"}),400
    r=subprocess.run(["systemctl",action,name],capture_output=True,text=True)
    return jsonify({"ok":r.returncode==0,"msg":r.stderr.strip() or None})

EDITABLE = {"panel_api_url","api_token","github_user","github_repo","github_branch",
            "deploy_method","github_token","ssh_key_path","sync_interval","ui_port",
            "ui_user","ui_pass","filename_length","filename_mode",
            "domain","access_mode","ssl_mode","ssl_cert","ssl_key","ssl_email","subs_dir","certbot_port"}
NUMERIC  = {"sync_interval","ui_port","filename_length"}

@app.route("/api/settings")
@login_required
def api_settings():
    cfg=load_cfg()
    # Mask secrets before sending to browser
    safe=dict(cfg)
    for k in ("api_token","github_token","ui_pass","flask_secret"):
        if safe.get(k): safe[k]=""  # send empty — frontend shows placeholder
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

# ── Run ────────────────────────────────────────────────────────────────────
if __name__=="__main__":
    print(f"  gitsub WebUI → http://0.0.0.0:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
