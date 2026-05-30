#!/usr/bin/env python3
"""
gitsub WebUI — Dashboard with login
"""

import os
import sys
import json
import hashlib
import secrets
import subprocess
import threading
from pathlib import Path
from datetime import datetime
from functools import wraps
from flask import Flask, jsonify, request, redirect, session, Response

BASE_DIR    = Path(__file__).resolve().parent
SUBMAP_FILE = BASE_DIR / "submap.json"
CONFIG_FILE = BASE_DIR / "config.json"

app = Flask(__name__)
PORT = int(os.getenv("PORT", 2086))

# ─────────────────────────────────────────
# Config helpers
# ─────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    with open(CONFIG_FILE) as f:
        return json.load(f)

def save_config_key(key, value):
    cfg = load_config()
    cfg[key] = value
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
    CONFIG_FILE.chmod(0o600)

def get_or_create_secret() -> str:
    """Persist Flask secret key in config so sessions survive restarts."""
    cfg = load_config()
    if cfg.get("flask_secret"):
        return cfg["flask_secret"]
    secret = secrets.token_hex(32)
    save_config_key("flask_secret", secret)
    return secret

def load_submap() -> dict:
    if not SUBMAP_FILE.exists():
        return {}
    with open(SUBMAP_FILE) as f:
        return json.load(f)

def format_ts(epoch):
    if not epoch:
        return "—"
    try:
        return datetime.utcfromtimestamp(int(epoch)).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return "—"

# Persistent secret key — sessions survive service restarts
app.secret_key = get_or_create_secret()
# SESSION_COOKIE_SECURE = False so cookie works whether accessed via HTTP or HTTPS
# (nginx handles TLS termination; Flask only sees plain HTTP internally)
app.config["SESSION_COOKIE_SECURE"]   = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# ProxyFix: trust X-Forwarded-Proto/Host from nginx (1 hop)
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1, x_for=1)

# ─────────────────────────────────────────
# Auth
# ─────────────────────────────────────────

def check_auth(username, password) -> bool:
    cfg = load_config()
    expected_user = cfg.get("ui_user", "admin")
    expected_pass = cfg.get("ui_pass", "")
    if not expected_pass:
        return True  # no password set — allow access
    return username == expected_user and password == expected_pass

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "unauthorized"}), 401
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated

# ─────────────────────────────────────────
# Background sync state
# ─────────────────────────────────────────

_sync_running = False
_sync_lock    = threading.Lock()

def trigger_sync() -> bool:
    global _sync_running
    with _sync_lock:
        if _sync_running:
            return False
        _sync_running = True
    def _run():
        global _sync_running
        try:
            subprocess.run(
                [sys.executable, str(BASE_DIR / "update.py"), "sync"],
                cwd=BASE_DIR
            )
        finally:
            _sync_running = False
    threading.Thread(target=_run, daemon=True).start()
    return True

# ─────────────────────────────────────────
# Login page HTML
# ─────────────────────────────────────────

LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>gitsub — login</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:#0d0f12;color:#c8d0e0;font-family:'IBM Plex Mono',monospace;
       min-height:100vh;display:flex;align-items:center;justify-content:center}
  .box{background:#14171d;border:1px solid #1e2330;border-radius:6px;
       padding:40px;width:340px}
  .logo{color:#00d4aa;font-size:20px;font-weight:600;margin-bottom:32px;
        text-align:center;letter-spacing:-0.5px}
  .logo span{color:#545e72;font-weight:400}
  label{display:block;font-size:10px;color:#545e72;text-transform:uppercase;
        letter-spacing:1px;margin-bottom:6px}
  input{width:100%;background:#0d0f12;border:1px solid #1e2330;color:#c8d0e0;
        font-family:'IBM Plex Mono',monospace;font-size:13px;padding:9px 12px;
        border-radius:4px;outline:none;transition:border-color 0.15s;margin-bottom:18px}
  input:focus{border-color:#00d4aa}
  button{width:100%;background:#00d4aa;border:none;color:#0d0f12;
         font-family:'IBM Plex Mono',monospace;font-size:13px;font-weight:600;
         padding:10px;border-radius:4px;cursor:pointer;transition:opacity 0.15s}
  button:hover{opacity:0.85}
  .err{color:#ff4d6d;font-size:12px;margin-bottom:16px;text-align:center}
</style>
</head>
<body>
<div class="box">
  <div class="logo">git<span>/</span>sub</div>
  {error}
  <form method="POST" action="/login">
    <label>Username</label>
    <input type="text" name="username" autocomplete="username" autofocus>
    <label>Password</label>
    <input type="password" name="password" autocomplete="current-password">
    <button type="submit">Sign in</button>
  </form>
</div>
</body>
</html>"""

# ─────────────────────────────────────────
# Dashboard HTML
# ─────────────────────────────────────────

DASH_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>gitsub dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
  :root{
    --bg:#0d0f12; --surface:#14171d; --border:#1e2330;
    --accent:#00d4aa; --accent2:#007aff; --warn:#ff9f43; --danger:#ff4d6d;
    --text:#c8d0e0; --muted:#545e72;
    --mono:'IBM Plex Mono',monospace; --sans:'IBM Plex Sans',sans-serif;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:14px;min-height:100vh}

  header{display:flex;align-items:center;justify-content:space-between;
         padding:16px 28px;border-bottom:1px solid var(--border);
         background:var(--surface);position:sticky;top:0;z-index:10}
  .logo{font-family:var(--mono);font-size:16px;font-weight:600;color:var(--accent)}
  .logo span{color:var(--muted);font-weight:400}
  .hdr-right{display:flex;gap:10px;align-items:center}

  button{font-family:var(--mono);font-size:12px;font-weight:500;
         border:1px solid var(--border);background:transparent;color:var(--text);
         padding:7px 14px;cursor:pointer;border-radius:4px;transition:all 0.15s}
  button:hover{border-color:var(--accent);color:var(--accent)}
  button.primary{background:var(--accent);border-color:var(--accent);color:#0d0f12}
  button.primary:hover{opacity:0.85}
  button:disabled{opacity:0.4;cursor:not-allowed}
  button.danger{color:var(--danger);border-color:rgba(255,77,109,0.3)}
  button.danger:hover{border-color:var(--danger)!important;color:var(--danger)!important}

  .stats{display:flex;gap:1px;background:var(--border);border-bottom:1px solid var(--border)}
  .stat{flex:1;background:var(--surface);padding:14px 24px}
  .stat-lbl{font-family:var(--mono);font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:4px}
  .stat-val{font-family:var(--mono);font-size:20px;font-weight:600;color:var(--accent)}
  .stat-val.sm{font-size:13px;padding-top:3px}

  .toolbar{display:flex;align-items:center;gap:10px;padding:12px 28px;border-bottom:1px solid var(--border)}
  .srch{flex:1;position:relative}
  .srch input{width:100%;background:var(--surface);border:1px solid var(--border);
              color:var(--text);font-family:var(--mono);font-size:12px;
              padding:8px 12px 8px 30px;border-radius:4px;outline:none;transition:border-color 0.15s}
  .srch input:focus{border-color:var(--accent)}
  .srch-ic{position:absolute;left:10px;top:50%;transform:translateY(-50%);color:var(--muted);font-size:13px}
  .cnt{font-family:var(--mono);font-size:11px;color:var(--muted);white-space:nowrap}

  /* ── Layout ── */
  .page-wrap{display:flex;flex-direction:column;min-height:100vh}

  table{width:100%;border-collapse:collapse}
  /* thead sticks below the toolbar — use scroll container instead of fixed offset */
  .table-scroll{overflow-x:auto;flex:1}
  thead th{font-family:var(--mono);font-size:10px;font-weight:500;text-transform:uppercase;
           letter-spacing:1px;color:var(--muted);text-align:left;padding:10px 28px;
           border-bottom:1px solid var(--border);background:var(--surface);
           white-space:nowrap}
  /* sticky header handled via JS scrolling the .table-scroll container, not position:sticky */
  tbody tr{border-bottom:1px solid var(--border);transition:background 0.1s}
  tbody tr:hover{background:var(--surface)}
  tbody td{padding:10px 28px;font-family:var(--mono);font-size:12px;vertical-align:top}

  .td-email{color:var(--text);font-weight:500}
  .td-sub{color:var(--muted);font-size:10px}
  .td-time{color:var(--muted);font-size:10px}

  .url-link{color:var(--accent2);text-decoration:none;border:1px solid rgba(0,122,255,.25);
            border-radius:3px;padding:3px 8px;font-size:11px;transition:all .1s}
  .url-link:hover{background:rgba(0,122,255,.1);border-color:var(--accent2)}

  .copy-btn{font-size:10px;padding:3px 8px;border-radius:3px;margin-left:5px}
  .copy-btn.ok{color:var(--accent);border-color:var(--accent)}

  .rot-btn{font-size:10px;padding:3px 8px;border-radius:3px;
           color:var(--warn);border-color:rgba(255,159,67,.3)}
  .rot-btn:hover{border-color:var(--warn)!important;color:var(--warn)!important}

  .empty{text-align:center;padding:60px 20px;color:var(--muted);font-family:var(--mono)}
  .empty h3{font-size:15px;margin-bottom:8px;color:var(--text)}

  .sync-dot{width:7px;height:7px;border-radius:50%;background:var(--muted);display:inline-block;margin-right:5px}
  .sync-dot.on{background:var(--warn);animation:pulse 1s infinite}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}

  .toast{position:fixed;bottom:22px;right:22px;background:var(--surface);
         border:1px solid var(--border);border-left:3px solid var(--accent);
         padding:11px 18px;font-family:var(--mono);font-size:12px;border-radius:4px;
         box-shadow:0 8px 24px rgba(0,0,0,.5);opacity:0;transform:translateY(8px);
         transition:all .2s;pointer-events:none;z-index:100}
  .toast.show{opacity:1;transform:translateY(0)}
  .toast.err{border-left-color:var(--danger)}

  @media(max-width:700px){
    header,thead th,tbody td,.toolbar{padding-left:14px;padding-right:14px}
    .stat{padding:10px 14px}
    .td-sub,.td-time{display:none}
  }
</style>
</head>
<body>

<header>
  <div class="logo">git<span>/</span>sub <span style="font-size:11px;margin-left:4px;color:var(--muted)">dashboard</span></div>
  <div class="hdr-right">
    <span><span class="sync-dot" id="sdot"></span><span id="sstat" style="font-family:var(--mono);font-size:11px;color:var(--muted)">idle</span></span>
    <button class="primary" id="sync-btn" onclick="doSync()">⟳ Sync Now</button>
    <a href="/logout" style="text-decoration:none"><button class="danger">logout</button></a>
  </div>
</header>

<div class="stats">
  <div class="stat"><div class="stat-lbl">Total Users</div><div class="stat-val" id="s-total">—</div></div>
  <div class="stat"><div class="stat-lbl">Active Files</div><div class="stat-val" id="s-files">—</div></div>
  <div class="stat"><div class="stat-lbl">GitHub Repo</div><div class="stat-val sm" id="s-repo">—</div></div>
  <div class="stat"><div class="stat-lbl">Last Sync</div><div class="stat-val sm" id="s-sync">—</div></div>
</div>

<div class="toolbar">
  <div class="srch">
    <span class="srch-ic">⌕</span>
    <input id="q" type="text" placeholder="filter by email or sub ID..." oninput="filter()">
  </div>
  <span class="cnt" id="cnt"></span>
  <button onclick="copyAll()">copy all URLs</button>
</div>

<div class="table-scroll">
<table>
  <thead><tr>
    <th>Email</th>
    <th>Sub ID</th>
    <th>File</th>
    <th>Raw URL</th>
    <th>Last Updated</th>
    <th></th>
  </tr></thead>
  <tbody id="tbody"><tr><td colspan="6"><div class="empty"><h3>Loading…</h3></div></td></tr></tbody>
</table>
</div>

<div class="toast" id="toast"></div>

<script>
let rows = [];
let pollTimer;

function toast(msg, type='') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'toast show' + (type ? ' ' + type : '');
  clearTimeout(el._t);
  el._t = setTimeout(() => el.className = 'toast', 3000);
}

function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

async function loadData() {
  const res = await fetch('/api/data');
  if (res.status === 401) { location = '/login'; return; }
  const d = await res.json();
  rows = d.entries;
  render(rows);
  document.getElementById('s-total').textContent = d.total;
  document.getElementById('s-files').textContent = d.total;
  document.getElementById('s-repo').textContent  = d.repo || '—';
  document.getElementById('s-sync').textContent  = d.last_sync || '—';
  document.getElementById('cnt').textContent = `${d.total} users`;
}

function render(data) {
  const tb = document.getElementById('tbody');
  if (!data.length) {
    tb.innerHTML = '<tr><td colspan="6"><div class="empty"><h3>No subscribers yet</h3><p>Run a sync to populate.</p></div></td></tr>';
    return;
  }
  tb.innerHTML = data.map(r => `
    <tr>
      <td class="td-email">${esc(r.email)}</td>
      <td class="td-sub">
        <div title="${esc(r.sub_id)}">${esc(r.sub_id.slice(0,16))}…</div>
      </td>
      <td class="td-sub" style="color:var(--muted)">${esc(r.filename)}</td>
      <td>
        <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
          <a class="url-link" href="${esc(r.raw_url)}" target="_blank">open ↗</a>
          <button class="copy-btn" onclick="copyURL('${esc(r.raw_url)}',this)">copy</button>
        </div>
        <div style="font-size:10px;color:var(--muted);margin-top:3px;word-break:break-all">${esc(r.raw_url)}</div>
      </td>
      <td class="td-time">${esc(r.updated)}</td>
      <td><button class="rot-btn" onclick="rotate('${esc(r.sub_id)}','${esc(r.email)}')">rotate</button></td>
    </tr>`).join('');
}

function filter() {
  const q = document.getElementById('q').value.toLowerCase();
  const filtered = q ? rows.filter(r => (r.email||'').toLowerCase().includes(q) || (r.sub_id||'').toLowerCase().includes(q)) : rows;
  render(filtered);
  document.getElementById('cnt').textContent = `${filtered.length} / ${rows.length} users`;
}

function copyURL(url, btn) {
  function fallback() {
    const ta = document.createElement('textarea');
    ta.value = url;
    ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0';
    document.body.appendChild(ta);
    ta.focus(); ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  }
  const done = () => {
    btn.textContent = '✓'; btn.classList.add('ok');
    setTimeout(() => { btn.textContent = 'copy'; btn.classList.remove('ok'); }, 1500);
  };
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(url).then(done).catch(fallback);
    done();
  } else {
    fallback(); done();
  }
}

function copyAll() {
  const urls = rows.map(r => r.raw_url).join('\n');
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(urls).then(() => toast('Copied all URLs'));
  } else {
    const ta = document.createElement('textarea');
    ta.value = urls;
    ta.style.cssText = 'position:fixed;opacity:0';
    document.body.appendChild(ta);
    ta.focus(); ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    toast('Copied all URLs');
  }
}

async function doSync() {
  document.getElementById('sync-btn').disabled = true;
  const res = await fetch('/api/sync', { method: 'POST' });
  if (res.status === 401) { location = '/login'; return; }
  const d = await res.json();
  if (d.ok) { toast('Sync started…'); pollSync(); }
  else { toast(d.msg || 'Already running', 'err'); document.getElementById('sync-btn').disabled = false; }
}

function pollSync() {
  clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    const res = await fetch('/api/sync/status');
    const d   = await res.json();
    const dot = document.getElementById('sdot');
    const st  = document.getElementById('sstat');
    const btn = document.getElementById('sync-btn');
    if (d.running) {
      dot.className = 'sync-dot on'; st.textContent = 'syncing';
    } else {
      dot.className = 'sync-dot'; st.textContent = 'idle';
      btn.disabled = false;
      clearInterval(pollTimer);
      loadData(); toast('Sync complete ✓');
    }
  }, 2000);
}

async function rotate(sub_id, email) {
  if (!confirm(`Rotate URL for ${email}?\nTheir subscription link will change and they need the new one.`)) return;
  const res = await fetch('/api/rotate', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({sub_id})
  });
  const d = await res.json();
  if (d.ok) { toast(`Rotated: ${email}`); loadData(); }
  else toast(d.msg || 'Failed', 'err');
}

loadData();
</script>
</body>
</html>"""

# ─────────────────────────────────────────
# Routes
# ─────────────────────────────────────────

@app.route("/login", methods=["GET"])
def login_page():
    return LOGIN_HTML.replace("{error}", "")

@app.route("/login", methods=["POST"])
def login_post():
    username = request.form.get("username", "")
    password = request.form.get("password", "")
    if check_auth(username, password):
        session["logged_in"] = True
        return redirect("/")
    return LOGIN_HTML.replace("{error}", '<div class="err">Invalid username or password.</div>')

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/")
@login_required
def index():
    return DASH_HTML

@app.route("/api/data")
@login_required
def api_data():
    submap = load_submap()
    cfg    = load_config()
    entries, last_ts = [], 0
    for sub_id, v in submap.items():
        entries.append({
            "sub_id":   sub_id,
            "email":    v.get("email", "—"),
            "filename": v.get("filename", ""),
            "raw_url":  v.get("raw_url", ""),
            "updated":  format_ts(v.get("updated")),
        })
        ts = v.get("updated", 0)
        if ts > last_ts:
            last_ts = ts
    entries.sort(key=lambda x: x["email"])
    return jsonify({
        "total":     len(entries),
        "entries":   entries,
        "repo":      f"{cfg.get('github_user','')}/{cfg.get('github_repo','')}",
        "last_sync": format_ts(last_ts) if last_ts else "never",
    })
@app.route("/api/sync", methods=["POST"])
@login_required
def api_sync():
    if trigger_sync():
        return jsonify({"ok": True})
    return jsonify({"ok": False, "msg": "Sync already running"}), 409

@app.route("/api/sync/status")
@login_required
def api_sync_status():
    return jsonify({"running": _sync_running})

@app.route("/api/rotate", methods=["POST"])
@login_required
def api_rotate():
    data   = request.get_json(silent=True) or {}
    sub_id = data.get("sub_id", "").strip()
    if not sub_id:
        return jsonify({"ok": False, "msg": "sub_id required"}), 400
    submap = load_submap()
    if sub_id not in submap:
        return jsonify({"ok": False, "msg": "Not found"}), 404
    email = submap[sub_id].get("email", sub_id)
    result = subprocess.run(
        [sys.executable, str(BASE_DIR / "update.py"), "rotate", email],
        cwd=BASE_DIR, capture_output=True, text=True
    )
    if result.returncode == 0:
        return jsonify({"ok": True})
    return jsonify({"ok": False, "msg": result.stderr or "Rotate failed"}), 500

# ─────────────────────────────────────────
# Run
# ─────────────────────────────────────────

if __name__ == "__main__":
    cfg = load_config()
    has_auth = bool(cfg.get("ui_pass", ""))
    print(f"  gitsub WebUI → http://0.0.0.0:{PORT}")
    print(f"  Auth: {'enabled' if has_auth else 'DISABLED (no password set)'}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
