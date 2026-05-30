#!/usr/bin/env python3
"""
gitsub WebUI — Subscription map dashboard
"""

import os
import sys
import json
import subprocess
import threading
from pathlib import Path
from datetime import datetime
from flask import Flask, jsonify, request, redirect

BASE_DIR = Path(__file__).resolve().parent
SUBMAP_FILE = BASE_DIR / "submap.json"
CONFIG_FILE = BASE_DIR / "config.json"

app = Flask(__name__)

PORT = int(os.getenv("PORT", 2086))


# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────

def load_submap() -> dict:
    if not SUBMAP_FILE.exists():
        return {}
    with open(SUBMAP_FILE) as f:
        return json.load(f)


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    with open(CONFIG_FILE) as f:
        return json.load(f)


def format_ts(epoch):
    if not epoch:
        return "—"
    try:
        return datetime.utcfromtimestamp(int(epoch)).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return "—"


_sync_running = False
_sync_lock = threading.Lock()


def trigger_sync():
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
# HTML (single-file, no templates dir needed)
# ─────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>gitsub dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --bg:      #0d0f12;
    --surface: #14171d;
    --border:  #1e2330;
    --accent:  #00d4aa;
    --accent2: #007aff;
    --warn:    #ff9f43;
    --danger:  #ff4d6d;
    --text:    #c8d0e0;
    --muted:   #545e72;
    --mono:    'IBM Plex Mono', monospace;
    --sans:    'IBM Plex Sans', sans-serif;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--sans);
    font-size: 14px;
    min-height: 100vh;
  }

  /* ── Header ── */
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 18px 28px;
    border-bottom: 1px solid var(--border);
    background: var(--surface);
    position: sticky;
    top: 0;
    z-index: 10;
  }

  .logo {
    font-family: var(--mono);
    font-size: 17px;
    font-weight: 600;
    color: var(--accent);
    letter-spacing: -0.5px;
  }
  .logo span { color: var(--muted); font-weight: 400; }

  .header-actions { display: flex; gap: 10px; align-items: center; }

  /* ── Buttons ── */
  button {
    font-family: var(--mono);
    font-size: 12px;
    font-weight: 500;
    border: 1px solid var(--border);
    background: transparent;
    color: var(--text);
    padding: 7px 16px;
    cursor: pointer;
    border-radius: 4px;
    transition: all 0.15s;
    letter-spacing: 0.3px;
  }
  button:hover { border-color: var(--accent); color: var(--accent); }
  button.primary {
    background: var(--accent);
    border-color: var(--accent);
    color: #0d0f12;
  }
  button.primary:hover { opacity: 0.85; }
  button:disabled { opacity: 0.4; cursor: not-allowed; }

  /* ── Stats bar ── */
  .stats {
    display: flex;
    gap: 1px;
    background: var(--border);
    border-bottom: 1px solid var(--border);
  }
  .stat {
    flex: 1;
    background: var(--surface);
    padding: 14px 24px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .stat-label {
    font-family: var(--mono);
    font-size: 10px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 1px;
  }
  .stat-value {
    font-family: var(--mono);
    font-size: 22px;
    font-weight: 600;
    color: var(--accent);
  }

  /* ── Search / filter bar ── */
  .toolbar {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 14px 28px;
    border-bottom: 1px solid var(--border);
  }
  .search-wrap {
    flex: 1;
    position: relative;
  }
  .search-wrap input {
    width: 100%;
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text);
    font-family: var(--mono);
    font-size: 13px;
    padding: 8px 12px 8px 32px;
    border-radius: 4px;
    outline: none;
    transition: border-color 0.15s;
  }
  .search-wrap input:focus { border-color: var(--accent); }
  .search-icon {
    position: absolute;
    left: 10px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--muted);
    font-size: 13px;
  }
  .filter-count {
    font-family: var(--mono);
    font-size: 12px;
    color: var(--muted);
    white-space: nowrap;
  }

  /* ── Table ── */
  .table-wrap { overflow-x: auto; }

  table {
    width: 100%;
    border-collapse: collapse;
  }
  thead th {
    font-family: var(--mono);
    font-size: 10px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--muted);
    text-align: left;
    padding: 10px 28px;
    border-bottom: 1px solid var(--border);
    background: var(--surface);
    position: sticky;
    top: 61px;
    z-index: 5;
  }
  tbody tr {
    border-bottom: 1px solid var(--border);
    transition: background 0.1s;
  }
  tbody tr:hover { background: var(--surface); }
  tbody td {
    padding: 12px 28px;
    font-family: var(--mono);
    font-size: 12px;
    vertical-align: middle;
  }

  .td-email { color: var(--text); font-weight: 500; }
  .td-subid { color: var(--muted); font-size: 11px; }
  .td-file  { color: var(--muted); font-size: 11px; }
  .td-time  { color: var(--muted); font-size: 11px; }

  .url-cell a {
    color: var(--accent2);
    text-decoration: none;
    font-size: 11px;
    border: 1px solid rgba(0,122,255,0.25);
    border-radius: 3px;
    padding: 3px 8px;
    display: inline-block;
    transition: all 0.1s;
  }
  .url-cell a:hover {
    background: rgba(0,122,255,0.1);
    border-color: var(--accent2);
  }

  .copy-btn {
    font-family: var(--mono);
    font-size: 10px;
    padding: 3px 8px;
    margin-left: 6px;
    border-radius: 3px;
  }
  .copy-btn.copied {
    color: var(--accent);
    border-color: var(--accent);
  }

  .rotate-btn {
    font-size: 10px;
    padding: 3px 8px;
    border-radius: 3px;
    color: var(--warn);
    border-color: rgba(255,159,67,0.3);
  }
  .rotate-btn:hover { border-color: var(--warn) !important; color: var(--warn) !important; }

  /* ── Empty state ── */
  .empty {
    text-align: center;
    padding: 60px 20px;
    color: var(--muted);
    font-family: var(--mono);
  }
  .empty h3 { font-size: 16px; margin-bottom: 8px; color: var(--text); }
  .empty p { font-size: 12px; }

  /* ── Toast ── */
  .toast {
    position: fixed;
    bottom: 24px;
    right: 24px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent);
    padding: 12px 20px;
    font-family: var(--mono);
    font-size: 12px;
    border-radius: 4px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.4);
    opacity: 0;
    transform: translateY(8px);
    transition: all 0.2s;
    pointer-events: none;
    z-index: 100;
  }
  .toast.show { opacity: 1; transform: translateY(0); }
  .toast.error { border-left-color: var(--danger); }

  /* ── Sync indicator ── */
  .sync-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--muted);
    display: inline-block;
    margin-right: 6px;
  }
  .sync-dot.running {
    background: var(--warn);
    animation: pulse 1s infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
  }

  /* ── Responsive ── */
  @media (max-width: 700px) {
    header { padding: 14px 16px; }
    thead th, tbody td { padding: 10px 16px; }
    .toolbar { padding: 12px 16px; }
    .stat { padding: 12px 16px; }
    .td-file, .td-subid { display: none; }
  }
</style>
</head>
<body>

<header>
  <div class="logo">git<span>/</span>sub <span style="font-size:11px;margin-left:4px">dashboard</span></div>
  <div class="header-actions">
    <span id="sync-indicator"><span class="sync-dot" id="sync-dot"></span><span id="sync-status">idle</span></span>
    <button class="primary" id="sync-btn" onclick="doSync()">⟳ Sync Now</button>
  </div>
</header>

<div class="stats" id="stats-bar">
  <div class="stat">
    <div class="stat-label">Total Users</div>
    <div class="stat-value" id="stat-total">—</div>
  </div>
  <div class="stat">
    <div class="stat-label">Active Files</div>
    <div class="stat-value" id="stat-files">—</div>
  </div>
  <div class="stat">
    <div class="stat-label">GitHub Repo</div>
    <div class="stat-value" style="font-size:14px;padding-top:4px" id="stat-repo">—</div>
  </div>
  <div class="stat">
    <div class="stat-label">Last Sync</div>
    <div class="stat-value" style="font-size:13px;padding-top:4px" id="stat-lastsync">—</div>
  </div>
</div>

<div class="toolbar">
  <div class="search-wrap">
    <span class="search-icon">⌕</span>
    <input type="text" id="search-input" placeholder="filter by email or sub ID..." oninput="filterTable()">
  </div>
  <span class="filter-count" id="filter-count"></span>
  <button onclick="copyAll()">copy all URLs</button>
</div>

<div class="table-wrap">
  <table id="main-table">
    <thead>
      <tr>
        <th>Email</th>
        <th>Sub ID</th>
        <th>File</th>
        <th>Raw URL</th>
        <th>Updated</th>
        <th></th>
      </tr>
    </thead>
    <tbody id="table-body">
      <tr><td colspan="6"><div class="empty"><h3>Loading...</h3></div></td></tr>
    </tbody>
  </table>
</div>

<div class="toast" id="toast"></div>

<script>
let tableData = [];
let syncPollTimer = null;

function toast(msg, type='') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'toast show' + (type ? ' ' + type : '');
  clearTimeout(el._t);
  el._t = setTimeout(() => el.className = 'toast', 3000);
}

async function loadData() {
  const res = await fetch('/api/data');
  const d = await res.json();
  tableData = d.entries;
  renderTable(tableData);
  document.getElementById('stat-total').textContent = d.total;
  document.getElementById('stat-files').textContent = d.total;
  document.getElementById('stat-repo').textContent = d.repo || '—';
  document.getElementById('stat-lastsync').textContent = d.last_sync || '—';
  document.getElementById('filter-count').textContent = `${d.total} users`;
}

function renderTable(rows) {
  const tbody = document.getElementById('table-body');
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="6"><div class="empty"><h3>No subscribers yet</h3><p>Run a sync to populate.</p></div></td></tr>`;
    return;
  }
  tbody.innerHTML = rows.map(r => `
    <tr>
      <td class="td-email">${esc(r.email)}</td>
      <td class="td-subid">${esc(r.sub_id.slice(0,16))}…</td>
      <td class="td-file">${esc(r.filename)}</td>
      <td class="url-cell">
        <a href="${esc(r.raw_url)}" target="_blank">open ↗</a>
        <button class="copy-btn" onclick="copyURL('${esc(r.raw_url)}', this)">copy</button>
      </td>
      <td class="td-time">${esc(r.updated)}</td>
      <td>
        <button class="rotate-btn" onclick="rotateUser('${esc(r.sub_id)}', '${esc(r.email)}')">rotate</button>
      </td>
    </tr>
  `).join('');
}

function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function filterTable() {
  const q = document.getElementById('search-input').value.toLowerCase();
  const filtered = q ? tableData.filter(r =>
    (r.email || '').toLowerCase().includes(q) ||
    (r.sub_id || '').toLowerCase().includes(q)
  ) : tableData;
  renderTable(filtered);
  document.getElementById('filter-count').textContent = `${filtered.length} / ${tableData.length} users`;
}

function copyURL(url, btn) {
  navigator.clipboard.writeText(url).then(() => {
    btn.textContent = '✓';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = 'copy'; btn.classList.remove('copied'); }, 1500);
  });
}

function copyAll() {
  const urls = tableData.map(r => r.raw_url).join('\n');
  navigator.clipboard.writeText(urls).then(() => toast('Copied all URLs'));
}

async function doSync() {
  const btn = document.getElementById('sync-btn');
  btn.disabled = true;
  const res = await fetch('/api/sync', { method: 'POST' });
  const d = await res.json();
  if (d.ok) {
    toast('Sync started...');
    pollSync();
  } else {
    toast(d.msg || 'Already running', 'error');
    btn.disabled = false;
  }
}

async function pollSync() {
  clearInterval(syncPollTimer);
  syncPollTimer = setInterval(async () => {
    const res = await fetch('/api/sync/status');
    const d = await res.json();
    const dot = document.getElementById('sync-dot');
    const status = document.getElementById('sync-status');
    const btn = document.getElementById('sync-btn');
    if (d.running) {
      dot.className = 'sync-dot running';
      status.textContent = 'syncing';
    } else {
      dot.className = 'sync-dot';
      status.textContent = 'idle';
      btn.disabled = false;
      clearInterval(syncPollTimer);
      loadData();
      toast('Sync complete ✓');
    }
  }, 2000);
}

async function rotateUser(sub_id, email) {
  if (!confirm(`Rotate URL for ${email}? Their subscription link will change.`)) return;
  const res = await fetch('/api/rotate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sub_id })
  });
  const d = await res.json();
  if (d.ok) {
    toast(`Rotated: ${email}`);
    loadData();
  } else {
    toast(d.msg || 'Rotate failed', 'error');
  }
}

// Init
loadData();
</script>
</body>
</html>
"""


# ─────────────────────────────────────────
# API Routes
# ─────────────────────────────────────────

@app.route("/")
def index():
    return HTML


@app.route("/api/data")
def api_data():
    submap = load_submap()
    cfg = load_config()

    entries = []
    last_ts = 0
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

    repo = f"{cfg.get('github_user', '')}/{cfg.get('github_repo', '')}"
    last_sync = format_ts(last_ts) if last_ts else "never"

    entries.sort(key=lambda x: x["email"])

    return jsonify({
        "total":     len(entries),
        "entries":   entries,
        "repo":      repo,
        "last_sync": last_sync,
    })


@app.route("/api/sync", methods=["POST"])
def api_sync():
    started = trigger_sync()
    if started:
        return jsonify({"ok": True})
    return jsonify({"ok": False, "msg": "Sync already running"}), 409


@app.route("/api/sync/status")
def api_sync_status():
    return jsonify({"running": _sync_running})


@app.route("/api/rotate", methods=["POST"])
def api_rotate():
    data = request.get_json(silent=True) or {}
    sub_id = data.get("sub_id", "").strip()
    if not sub_id:
        return jsonify({"ok": False, "msg": "sub_id required"}), 400

    submap = load_submap()
    if sub_id not in submap:
        return jsonify({"ok": False, "msg": "Not found"}), 404

    # Trigger rotate via update.py
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
    print(f"  gitsub WebUI → http://0.0.0.0:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
