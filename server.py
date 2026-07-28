"""
HTTP server for QueueCTL — satisfies Railway/Render PORT requirement
and serves a premium live dashboard at / with JSON API endpoints.
"""
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

DB_PATH = Path(os.environ.get("QUEUECTL_DB_PATH", "/tmp/queuectl/queue.db"))


def get_jobs(state_filter=None, search=None, sort="newest", limit=500):
    try:
        from queuectl.database.db import get_connection, init_db
        init_db(DB_PATH)
        order = "DESC" if sort == "newest" else "ASC"
        with get_connection(DB_PATH) as conn:
            query = "SELECT id, command, state, attempts, max_retries, created_at, updated_at, worker_id FROM jobs"
            params = []
            conditions = []
            if state_filter and state_filter != "all":
                conditions.append("state = ?")
                params.append(state_filter)
            if search:
                conditions.append("(id LIKE ? OR command LIKE ?)")
                params.extend([f"%{search}%", f"%{search}%"])
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += f" ORDER BY created_at {order} LIMIT {limit};"
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows], None
    except Exception as e:
        return [], str(e)


def get_counts():
    try:
        from queuectl.database.db import get_connection, init_db
        init_db(DB_PATH)
        with get_connection(DB_PATH) as conn:
            rows = conn.execute("SELECT state, COUNT(*) as cnt FROM jobs GROUP BY state;").fetchall()
            total_row = conn.execute("SELECT COUNT(*) as cnt FROM jobs;").fetchone()
            counts = {r["state"]: r["cnt"] for r in rows}
            counts["total"] = total_row["cnt"] if total_row else 0
            return counts, None
    except Exception as e:
        return {}, str(e)


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>QueueCTL — Live Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet"/>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg:        #07070f;
  --surface:   #0e0e1a;
  --card:      #13131f;
  --card2:     #18182a;
  --border:    #1e1e32;
  --border2:   #2a2a45;
  --text:      #e2e8f0;
  --muted:     #4a5568;
  --muted2:    #64748b;
  --accent:    #6366f1;
  --accent2:   #818cf8;
  --green:     #10b981;
  --yellow:    #f59e0b;
  --blue:      #3b82f6;
  --red:       #ef4444;
  --purple:    #8b5cf6;
  --orange:    #f97316;
  --radius:    14px;
  --radius-sm: 8px;
  --shadow:    0 4px 24px rgba(0,0,0,.5);
}

html { scroll-behavior: smooth; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: 'Inter', sans-serif;
  min-height: 100vh;
  overflow-x: hidden;
}

/* ── noise/grid bg ── */
body::before {
  content: '';
  position: fixed; inset: 0; z-index: 0; pointer-events: none;
  background-image:
    radial-gradient(ellipse 80% 60% at 50% -10%, rgba(99,102,241,.18) 0%, transparent 60%),
    radial-gradient(ellipse 40% 40% at 90% 80%, rgba(139,92,246,.1) 0%, transparent 60%);
}

/* ── header ── */
header {
  position: sticky; top: 0; z-index: 100;
  background: rgba(7,7,15,.85);
  backdrop-filter: blur(20px);
  border-bottom: 1px solid var(--border);
  padding: 0 2rem;
  display: flex; align-items: center; justify-content: space-between;
  height: 64px;
}
.logo {
  display: flex; align-items: center; gap: .75rem;
  font-size: 1.25rem; font-weight: 800; letter-spacing: -.03em;
}
.logo-icon {
  width: 34px; height: 34px; border-radius: 10px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  display: grid; place-items: center; font-size: 1rem;
  box-shadow: 0 0 20px rgba(99,102,241,.4);
}
.logo-text {
  background: linear-gradient(90deg, #c7d2fe, #a5b4fc, #c4b5fd);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}

.header-right { display: flex; align-items: center; gap: 1rem; }

/* live indicator */
.live-pill {
  display: flex; align-items: center; gap: .45rem;
  background: rgba(16,185,129,.12);
  border: 1px solid rgba(16,185,129,.3);
  border-radius: 999px;
  padding: .3rem .85rem;
  font-size: .72rem; font-weight: 600; color: var(--green);
  text-transform: uppercase; letter-spacing: .08em;
}
.live-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--green);
  animation: blink 1.4s ease-in-out infinite;
}
@keyframes blink { 0%,100%{opacity:1;box-shadow:0 0 0 0 rgba(16,185,129,.4)} 50%{opacity:.4;box-shadow:0 0 0 5px rgba(16,185,129,0)} }

/* countdown ring */
#countdown-wrap {
  position: relative; width: 36px; height: 36px; cursor: pointer;
  title: "Click to refresh now";
}
#countdown-wrap:hover #countdown-svg circle.track { stroke: var(--accent2); }
#countdown-svg { transform: rotate(-90deg); }
#countdown-svg circle { fill: none; stroke-width: 3; }
#countdown-svg circle.bg    { stroke: var(--border2); }
#countdown-svg circle.track { stroke: var(--accent); transition: stroke-dashoffset .9s linear; }
#cd-label {
  position: absolute; inset: 0;
  display: grid; place-items: center;
  font-size: .65rem; font-weight: 700; color: var(--accent2);
}

/* ── main layout ── */
main { position: relative; z-index: 1; max-width: 1300px; margin: 0 auto; padding: 2rem; }

/* ── stat strip ── */
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: .875rem; margin-bottom: 2rem; }
.stat {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.2rem 1.4rem;
  position: relative; overflow: hidden;
  cursor: pointer;
  transition: transform .2s, border-color .25s, box-shadow .25s;
}
.stat::after {
  content: ''; position: absolute; inset: 0;
  background: radial-gradient(ellipse at top left, var(--glow, transparent) 0%, transparent 70%);
  pointer-events: none;
}
.stat:hover { transform: translateY(-3px); border-color: var(--c); box-shadow: 0 8px 32px rgba(0,0,0,.4); }
.stat.active { border-color: var(--c) !important; box-shadow: 0 0 0 1px var(--c), 0 8px 32px rgba(0,0,0,.4); }
.stat::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; background: var(--c); border-radius: var(--radius) var(--radius) 0 0; }
.stat-label { font-size: .68rem; text-transform: uppercase; letter-spacing: .09em; color: var(--muted2); margin-bottom: .5rem; }
.stat-value { font-size: 2.1rem; font-weight: 800; color: var(--c); line-height: 1; }
.stat-sub   { font-size: .7rem; color: var(--muted2); margin-top: .3rem; }

/* ── controls bar ── */
.controls {
  background: var(--card); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 1rem 1.2rem;
  margin-bottom: 1.25rem;
  display: flex; flex-wrap: wrap; align-items: center; gap: .75rem;
}

/* search */
.search-wrap { position: relative; flex: 1; min-width: 200px; }
.search-wrap svg { position: absolute; left: .85rem; top: 50%; transform: translateY(-50%); color: var(--muted2); pointer-events: none; }
#search-input {
  width: 100%; background: var(--surface); border: 1px solid var(--border2);
  border-radius: var(--radius-sm); color: var(--text);
  padding: .55rem .9rem .55rem 2.4rem; font-size: .85rem; font-family: inherit;
  transition: border-color .2s, box-shadow .2s;
  outline: none;
}
#search-input::placeholder { color: var(--muted); }
#search-input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(99,102,241,.2); }

/* filter pills */
.filter-group { display: flex; flex-wrap: wrap; gap: .4rem; }
.filter-pill {
  padding: .35rem .85rem; border-radius: 999px;
  font-size: .72rem; font-weight: 600; text-transform: uppercase; letter-spacing: .07em;
  border: 1px solid transparent; cursor: pointer;
  background: var(--surface); color: var(--muted2); border-color: var(--border2);
  transition: all .18s;
}
.filter-pill:hover { border-color: var(--pill-color); color: var(--pill-color); }
.filter-pill.active { background: var(--pill-color); color: #fff; border-color: var(--pill-color); box-shadow: 0 0 12px var(--pill-color-glow); }

/* sort */
.sort-wrap { display: flex; align-items: center; gap: .5rem; }
.sort-wrap label { font-size: .75rem; color: var(--muted2); white-space: nowrap; }
#sort-select {
  background: var(--surface); border: 1px solid var(--border2); border-radius: var(--radius-sm);
  color: var(--text); padding: .45rem .75rem; font-size: .8rem; font-family: inherit;
  outline: none; cursor: pointer;
}
#sort-select:focus { border-color: var(--accent); }

/* action buttons */
.btn {
  display: flex; align-items: center; gap: .4rem;
  padding: .5rem 1rem; border-radius: var(--radius-sm);
  font-size: .8rem; font-weight: 600; cursor: pointer;
  border: none; transition: all .18s; font-family: inherit;
}
.btn-primary { background: var(--accent); color: #fff; }
.btn-primary:hover { background: var(--accent2); box-shadow: 0 4px 16px rgba(99,102,241,.4); }
.btn-ghost { background: var(--surface); color: var(--muted2); border: 1px solid var(--border2); }
.btn-ghost:hover { color: var(--text); border-color: var(--border2); }

/* ── table card ── */
.table-card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: var(--radius); overflow: hidden;
}
.table-head-bar {
  padding: 1rem 1.5rem; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: .5rem;
}
.table-head-bar h2 { font-size: .95rem; font-weight: 700; }
#job-count { font-size: .78rem; color: var(--muted2); }

.table-scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: .83rem; }
thead { position: sticky; top: 64px; z-index: 10; }
th {
  padding: .8rem 1.1rem; text-align: left;
  font-size: .68rem; text-transform: uppercase; letter-spacing: .09em;
  color: var(--muted2); background: var(--card2);
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
  cursor: pointer; user-select: none;
}
th:hover { color: var(--accent2); }
th .sort-icon { opacity: .4; margin-left: .25rem; font-size: .7rem; }
th.sorted .sort-icon { opacity: 1; color: var(--accent2); }
td {
  padding: .8rem 1.1rem; border-bottom: 1px solid rgba(30,30,50,.8);
  vertical-align: middle;
}
tr:last-child td { border-bottom: none; }
tbody tr { transition: background .15s; }
tbody tr:hover td { background: rgba(99,102,241,.05); }

/* row animation */
@keyframes fadeIn { from { opacity:0; transform: translateY(6px); } to { opacity:1; transform: none; } }
tbody tr { animation: fadeIn .25s ease both; }

.job-id { font-family: 'JetBrains Mono', monospace; font-size: .75rem; color: var(--muted2); }
.cmd {
  font-family: 'JetBrains Mono', monospace; font-size: .78rem;
  color: #a5b4fc; background: rgba(99,102,241,.1);
  padding: .22rem .55rem; border-radius: 6px;
  max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  display: inline-block;
}
.attempts-bar { display: flex; align-items: center; gap: .5rem; }
.bar-track {
  width: 56px; height: 5px; background: var(--border2);
  border-radius: 999px; overflow: hidden;
}
.bar-fill { height: 100%; border-radius: 999px; background: var(--green); }
.ts { font-size: .72rem; color: var(--muted2); white-space: nowrap; }
.worker-id { font-family: 'JetBrains Mono', monospace; font-size: .72rem; color: var(--muted2); }

/* state badge */
.badge {
  display: inline-flex; align-items: center; gap: .3rem;
  padding: .22rem .65rem; border-radius: 999px;
  font-size: .68rem; font-weight: 700; text-transform: uppercase; letter-spacing: .07em;
  white-space: nowrap;
}
.badge::before { content:''; width:5px; height:5px; border-radius:50%; background:currentColor; }

/* empty */
.empty-state {
  text-align: center; padding: 5rem 2rem; color: var(--muted2);
}
.empty-state .big { font-size: 3rem; display:block; margin-bottom:1rem; filter: grayscale(1); }
.empty-state p { font-size: .9rem; }

/* ── toast ── */
#toast {
  position: fixed; bottom: 1.5rem; right: 1.5rem; z-index: 999;
  background: var(--card2); border: 1px solid var(--border2);
  border-radius: var(--radius-sm); padding: .75rem 1.2rem;
  font-size: .82rem; color: var(--text);
  box-shadow: var(--shadow);
  transform: translateY(120%); opacity: 0;
  transition: transform .3s, opacity .3s;
}
#toast.show { transform: none; opacity: 1; }

/* ── enqueue modal ── */
.modal-overlay {
  position: fixed; inset: 0; z-index: 200;
  background: rgba(0,0,0,.7); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
  opacity: 0; pointer-events: none; transition: opacity .2s;
}
.modal-overlay.open { opacity: 1; pointer-events: auto; }
.modal {
  background: var(--card); border: 1px solid var(--border2);
  border-radius: var(--radius); padding: 2rem; width: 100%; max-width: 480px;
  box-shadow: var(--shadow);
  transform: scale(.95); transition: transform .2s;
}
.modal-overlay.open .modal { transform: scale(1); }
.modal h3 { font-size: 1.1rem; font-weight: 700; margin-bottom: 1.25rem; }
.form-group { margin-bottom: 1rem; }
.form-group label { display: block; font-size: .75rem; color: var(--muted2); margin-bottom: .35rem; font-weight: 500; text-transform: uppercase; letter-spacing: .07em; }
.form-group input, .form-group select {
  width: 100%; background: var(--surface); border: 1px solid var(--border2);
  border-radius: var(--radius-sm); color: var(--text);
  padding: .6rem .9rem; font-size: .875rem; font-family: inherit; outline: none;
  transition: border-color .2s, box-shadow .2s;
}
.form-group input:focus, .form-group select:focus {
  border-color: var(--accent); box-shadow: 0 0 0 3px rgba(99,102,241,.2);
}
.modal-footer { display: flex; gap: .75rem; justify-content: flex-end; margin-top: 1.5rem; }

/* scrollbar */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 999px; }

@media (max-width: 640px) {
  main { padding: 1rem; }
  header { padding: 0 1rem; }
  .controls { gap: .5rem; }
}
</style>
</head>
<body>

<!-- Header -->
<header>
  <div class="logo">
    <div class="logo-icon">⚡</div>
    <span class="logo-text">QueueCTL</span>
  </div>
  <div class="header-right">
    <div class="live-pill"><div class="live-dot"></div> Live</div>
    <div id="countdown-wrap" title="Click to refresh now" onclick="fetchData(true)">
      <svg id="countdown-svg" width="36" height="36" viewBox="0 0 36 36">
        <circle class="bg"    cx="18" cy="18" r="15" stroke-dasharray="94.25" stroke-dashoffset="0"/>
        <circle class="track" cx="18" cy="18" r="15" id="cd-ring"
          stroke-dasharray="94.25" stroke-dashoffset="0"/>
      </svg>
      <div id="cd-label">5</div>
    </div>
  </div>
</header>

<main>
  <!-- Stats -->
  <div class="stats" id="stats-strip"></div>

  <!-- Controls -->
  <div class="controls">
    <div class="search-wrap">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
      <input id="search-input" type="text" placeholder="Search by job ID or command…" autocomplete="off"/>
    </div>

    <div class="filter-group" id="filter-pills"></div>

    <div class="sort-wrap">
      <label for="sort-select">Sort</label>
      <select id="sort-select">
        <option value="newest">Newest first</option>
        <option value="oldest">Oldest first</option>
      </select>
    </div>

    <button class="btn btn-primary" onclick="openModal()">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 5v14M5 12h14"/></svg>
      Enqueue Job
    </button>

    <button class="btn btn-ghost" onclick="fetchData(true)">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-.53-4.5"/></svg>
      Refresh
    </button>
  </div>

  <!-- Table -->
  <div class="table-card">
    <div class="table-head-bar">
      <h2>Jobs</h2>
      <span id="job-count"></span>
    </div>
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th onclick="sortBy('id')">Job ID <span class="sort-icon">↕</span></th>
            <th onclick="sortBy('command')">Command <span class="sort-icon">↕</span></th>
            <th onclick="sortBy('state')">State <span class="sort-icon">↕</span></th>
            <th onclick="sortBy('attempts')">Attempts <span class="sort-icon">↕</span></th>
            <th onclick="sortBy('worker_id')">Worker <span class="sort-icon">↕</span></th>
            <th onclick="sortBy('created_at')">Created <span class="sort-icon">↕</span></th>
          </tr>
        </thead>
        <tbody id="jobs-tbody">
          <tr><td colspan="6"><div class="empty-state"><span class="big">⏳</span><p>Loading…</p></div></td></tr>
        </tbody>
      </table>
    </div>
  </div>
</main>

<!-- Enqueue Modal -->
<div class="modal-overlay" id="modal-overlay" onclick="closeModalOutside(event)">
  <div class="modal">
    <h3>⚡ Enqueue New Job</h3>
    <div class="form-group">
      <label>Job ID</label>
      <input id="m-job-id" type="text" placeholder="e.g. job-001"/>
    </div>
    <div class="form-group">
      <label>Command</label>
      <input id="m-command" type="text" placeholder="e.g. echo hello world"/>
    </div>
    <div class="form-group">
      <label>Max Retries</label>
      <select id="m-retries">
        <option value="0">0 — No retry</option>
        <option value="1">1</option>
        <option value="2">2</option>
        <option value="3" selected>3 (default)</option>
        <option value="5">5</option>
        <option value="10">10</option>
      </select>
    </div>
    <div class="modal-footer">
      <button class="btn btn-ghost" onclick="closeModal()">Cancel</button>
      <button class="btn btn-primary" onclick="submitJob()">Submit Job</button>
    </div>
  </div>
</div>

<!-- Toast -->
<div id="toast"></div>

<script>
// ── config ────────────────────────────────────────────────────────────────────
const REFRESH_SEC = 5;
const STATE_META = {
  all:        { label: 'All',        color: '#818cf8', glow: 'rgba(129,140,248,.35)' },
  pending:    { label: 'Pending',    color: '#f59e0b', glow: 'rgba(245,158,11,.35)'  },
  processing: { label: 'Processing', color: '#3b82f6', glow: 'rgba(59,130,246,.35)'  },
  completed:  { label: 'Completed',  color: '#10b981', glow: 'rgba(16,185,129,.35)'  },
  failed:     { label: 'Failed',     color: '#ef4444', glow: 'rgba(239,68,68,.35)'   },
  dead:       { label: 'Dead',       color: '#8b5cf6', glow: 'rgba(139,92,246,.35)'  },
};

// ── state ─────────────────────────────────────────────────────────────────────
let activeFilter = 'all';
let searchTerm   = '';
let sortField    = 'created_at';
let sortDir      = 'desc';
let allJobs      = [];
let countdown    = REFRESH_SEC;
let timer        = null;

// ── DOM refs ──────────────────────────────────────────────────────────────────
const tbody     = document.getElementById('jobs-tbody');
const statsEl   = document.getElementById('stats-strip');
const jobCount  = document.getElementById('job-count');
const cdRing    = document.getElementById('cd-ring');
const cdLabel   = document.getElementById('cd-label');
const CIRC      = 94.25; // 2*PI*r

// ── countdown ring ─────────────────────────────────────────────────────────
function tickCountdown() {
  countdown--;
  cdLabel.textContent = countdown;
  cdRing.style.strokeDashoffset = CIRC * (1 - countdown / REFRESH_SEC);
  if (countdown <= 0) {
    fetchData(false);
  }
}
function resetCountdown() {
  clearInterval(timer);
  countdown = REFRESH_SEC;
  cdLabel.textContent = countdown;
  cdRing.style.strokeDashoffset = 0;
  timer = setInterval(tickCountdown, 1000);
}

// ── fetch ─────────────────────────────────────────────────────────────────────
async function fetchData(manual = false) {
  try {
    const params = new URLSearchParams({ limit: 500, sort: document.getElementById('sort-select').value });
    if (activeFilter !== 'all') params.set('state', activeFilter);
    if (searchTerm) params.set('search', searchTerm);

    const [jobsRes, statsRes] = await Promise.all([
      fetch('/api/jobs?' + params).then(r => r.json()),
      fetch('/api/stats').then(r => r.json()),
    ]);

    allJobs = jobsRes.jobs || [];
    renderStats(statsRes.counts || {});
    renderTable(allJobs);
    if (manual) showToast('✓ Refreshed');
  } catch (e) {
    showToast('⚠ Connection error');
  }
  resetCountdown();
}

// ── render stats ──────────────────────────────────────────────────────────────
function renderStats(counts) {
  statsEl.innerHTML = '';
  const order = ['total','pending','processing','completed','failed','dead'];
  order.forEach(key => {
    const meta  = STATE_META[key] || STATE_META.all;
    const val   = counts[key] ?? 0;
    const card  = document.createElement('div');
    card.className = 'stat' + (activeFilter === key ? ' active' : '');
    card.style.setProperty('--c', meta.color);
    card.style.setProperty('--glow', meta.color + '22');
    card.innerHTML = `
      <div class="stat-label">${meta.label}</div>
      <div class="stat-value">${val}</div>
      <div class="stat-sub">${key === 'total' ? 'all states' : 'jobs'}</div>`;
    if (key !== 'total') {
      card.style.cursor = 'pointer';
      card.onclick = () => setFilter(key);
    }
    statsEl.appendChild(card);
  });
}

// ── render table ──────────────────────────────────────────────────────────────
function renderTable(jobs) {
  jobCount.textContent = `${jobs.length} job${jobs.length !== 1 ? 's' : ''}`;
  if (!jobs.length) {
    tbody.innerHTML = `<tr><td colspan="6"><div class="empty-state">
      <span class="big">📭</span><p>No jobs match your filter.</p></div></td></tr>`;
    return;
  }

  // client-side sort
  const dir = sortDir === 'asc' ? 1 : -1;
  const sorted = [...jobs].sort((a, b) => {
    const av = a[sortField] ?? '', bv = b[sortField] ?? '';
    return av < bv ? -dir : av > bv ? dir : 0;
  });

  tbody.innerHTML = sorted.map((j, i) => {
    const m = STATE_META[j.state] || { color: '#64748b', glow: '' };
    const pct = j.max_retries > 0 ? Math.min(100, (j.attempts / j.max_retries) * 100) : 0;
    const barColor = pct >= 100 ? '#ef4444' : pct > 60 ? '#f59e0b' : '#10b981';
    const ts = j.created_at ? j.created_at.replace('T',' ').slice(0,19) : '—';
    return `<tr style="animation-delay:${i*18}ms">
      <td><span class="job-id">${esc(j.id)}</span></td>
      <td><span class="cmd" title="${esc(j.command)}">${esc(j.command)}</span></td>
      <td><span class="badge" style="background:${m.color}18;color:${m.color};border:1px solid ${m.color}44">${esc(j.state)}</span></td>
      <td>
        <div class="attempts-bar">
          <span style="font-size:.78rem;font-weight:600;color:${barColor}">${j.attempts}/${j.max_retries}</span>
          <div class="bar-track"><div class="bar-fill" style="width:${pct}%;background:${barColor}"></div></div>
        </div>
      </td>
      <td>${j.worker_id ? `<span class="worker-id">${esc(j.worker_id)}</span>` : '<span style="color:var(--muted)">—</span>'}</td>
      <td><span class="ts">${ts}</span></td>
    </tr>`;
  }).join('');

  // update sort icons
  document.querySelectorAll('th').forEach(th => {
    th.classList.remove('sorted');
    const icon = th.querySelector('.sort-icon');
    if (icon) icon.textContent = '↕';
  });
  const cols = ['id','command','state','attempts','worker_id','created_at'];
  const idx  = cols.indexOf(sortField);
  if (idx >= 0) {
    const ths = document.querySelectorAll('th');
    ths[idx].classList.add('sorted');
    const icon = ths[idx].querySelector('.sort-icon');
    if (icon) icon.textContent = sortDir === 'asc' ? '↑' : '↓';
  }
}

// ── helpers ───────────────────────────────────────────────────────────────────
function esc(s) { return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

function setFilter(f) {
  activeFilter = f;
  document.querySelectorAll('.filter-pill').forEach(p => {
    p.classList.toggle('active', p.dataset.state === f);
  });
  fetchData(false);
}

function sortBy(field) {
  if (sortField === field) sortDir = sortDir === 'asc' ? 'desc' : 'asc';
  else { sortField = field; sortDir = 'desc'; }
  renderTable(allJobs);
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

// ── filter pills init ─────────────────────────────────────────────────────────
function initPills() {
  const group = document.getElementById('filter-pills');
  Object.entries(STATE_META).forEach(([key, meta]) => {
    const btn = document.createElement('button');
    btn.className = 'filter-pill' + (key === 'all' ? ' active' : '');
    btn.dataset.state = key;
    btn.textContent = meta.label;
    btn.style.setProperty('--pill-color', meta.color);
    btn.style.setProperty('--pill-color-glow', meta.glow);
    btn.onclick = () => setFilter(key);
    group.appendChild(btn);
  });
}

// ── search ────────────────────────────────────────────────────────────────────
let searchTimer;
document.getElementById('search-input').addEventListener('input', e => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    searchTerm = e.target.value.trim();
    fetchData(false);
  }, 350);
});

document.getElementById('sort-select').addEventListener('change', () => fetchData(false));

// ── modal ─────────────────────────────────────────────────────────────────────
function openModal()  { document.getElementById('modal-overlay').classList.add('open'); }
function closeModal() { document.getElementById('modal-overlay').classList.remove('open'); }
function closeModalOutside(e) { if (e.target.id === 'modal-overlay') closeModal(); }

async function submitJob() {
  const id  = document.getElementById('m-job-id').value.trim();
  const cmd = document.getElementById('m-command').value.trim();
  const ret = document.getElementById('m-retries').value;
  if (!id || !cmd) { showToast('⚠ Job ID and Command are required'); return; }

  try {
    const res = await fetch('/api/enqueue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, command: cmd, max_retries: parseInt(ret) })
    });
    const data = await res.json();
    if (res.ok) {
      showToast('✓ Job enqueued: ' + id);
      closeModal();
      document.getElementById('m-job-id').value = '';
      document.getElementById('m-command').value = '';
      fetchData(false);
    } else {
      showToast('⚠ ' + (data.error || 'Failed'));
    }
  } catch(e) { showToast('⚠ Network error'); }
}

// ── init ──────────────────────────────────────────────────────────────────────
initPills();
fetchData(false);
</script>
</body>
</html>"""


def handle_api_jobs(qs):
    state  = qs.get("state",  [None])[0]
    search = qs.get("search", [None])[0]
    sort   = qs.get("sort",   ["newest"])[0]
    jobs, err = get_jobs(state_filter=state, search=search, sort=sort)
    payload = {"jobs": jobs}
    if err:
        payload["error"] = err
    return json.dumps(payload).encode()


def handle_api_stats():
    counts, err = get_counts()
    payload = {"counts": counts}
    if err:
        payload["error"] = err
    return json.dumps(payload).encode()


def handle_enqueue(body_bytes):
    try:
        data = json.loads(body_bytes)
        job_id  = str(data.get("id", "")).strip()
        command = str(data.get("command", "")).strip()
        retries = int(data.get("max_retries", 3))
        if not job_id:
            return 400, json.dumps({"error": "id is required"}).encode()
        if not command:
            return 400, json.dumps({"error": "command is required"}).encode()

        from queuectl.services.job_service import JobService
        svc = JobService(db_path=DB_PATH)
        job = svc.enqueue_job(job_id=job_id, command=command, max_retries=retries)
        return 201, json.dumps(job.to_dict()).encode()
    except ValueError as e:
        return 400, json.dumps({"error": str(e)}).encode()
    except Exception as e:
        return 500, json.dumps({"error": str(e)}).encode()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, content_type, body):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        path = parsed.path

        if path in ("/", "/dashboard"):
            self._send(200, "text/html; charset=utf-8", DASHBOARD_HTML.encode())
        elif path == "/api/jobs":
            self._send(200, "application/json", handle_api_jobs(qs))
        elif path == "/api/stats":
            self._send(200, "application/json", handle_api_stats())
        elif path == "/health":
            self._send(200, "text/plain", b"QueueCTL is running")
        else:
            self._send(404, "text/plain", b"Not found")

    def do_POST(self):
        if self.path == "/api/enqueue":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            code, resp = handle_enqueue(body)
            self._send(code, "application/json", resp)
        else:
            self._send(404, "text/plain", b"Not found")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        pass  # suppress access logs


def start_server(port):
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"[dashboard] Listening on port {port}", flush=True)
    server.serve_forever()


def main():
    port = int(os.environ.get("PORT", 8080))
    os.makedirs(DB_PATH.parent, exist_ok=True)
    os.makedirs(os.environ.get("QUEUECTL_LOG_DIR", "/tmp/queuectl/logs"), exist_ok=True)

    t = threading.Thread(target=start_server, args=(port,), daemon=True)
    t.start()

    print("[queuectl] Starting worker...", flush=True)
    result = subprocess.run(
        [sys.executable, "-m", "queuectl.cli.main", "worker", "run"],
        env=os.environ.copy(),
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
