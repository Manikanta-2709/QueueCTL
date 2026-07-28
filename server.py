"""
HTTP server for QueueCTL — satisfies Render/Railway PORT requirement
and exposes a live dashboard at / and JSON API at /api/jobs.
"""
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# ── resolve DB path ────────────────────────────────────────────────────────────
DB_PATH = Path(os.environ.get("QUEUECTL_DB_PATH", "/tmp/queuectl/queue.db"))


def get_jobs():
    """Query jobs directly from SQLite — no worker process needed."""
    try:
        from queuectl.database.db import get_connection, init_db
        init_db(DB_PATH)
        with get_connection(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT id, command, state, attempts, max_retries, created_at, updated_at, worker_id "
                "FROM jobs ORDER BY created_at DESC LIMIT 200;"
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        return [{"error": str(e)}]


def get_counts():
    try:
        from queuectl.database.db import get_connection, init_db
        init_db(DB_PATH)
        with get_connection(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT state, COUNT(*) as cnt FROM jobs GROUP BY state;"
            ).fetchall()
            return {r["state"]: r["cnt"] for r in rows}
    except Exception:
        return {}


STATE_COLORS = {
    "pending":  "#f59e0b",
    "running":  "#3b82f6",
    "done":     "#10b981",
    "failed":   "#ef4444",
    "dead":     "#8b5cf6",
}

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>QueueCTL Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet"/>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg: #0a0a0f;
    --surface: #12121a;
    --card: #1a1a26;
    --border: #2a2a3d;
    --text: #e2e8f0;
    --muted: #64748b;
    --accent: #6366f1;
  }}
  body {{ background: var(--bg); color: var(--text); font-family: 'Inter', sans-serif; min-height: 100vh; }}

  /* ── header ── */
  header {{
    background: linear-gradient(135deg, #1e1b4b 0%, #0f172a 100%);
    border-bottom: 1px solid var(--border);
    padding: 1.5rem 2rem;
    display: flex; align-items: center; justify-content: space-between;
  }}
  header h1 {{ font-size: 1.5rem; font-weight: 700; letter-spacing: -0.02em;
    background: linear-gradient(90deg, #818cf8, #c084fc); -webkit-background-clip: text;
    -webkit-text-fill-color: transparent; }}
  .live-badge {{
    display: flex; align-items: center; gap: 0.4rem; font-size: 0.75rem;
    color: #10b981; font-weight: 500;
  }}
  .dot {{ width: 8px; height: 8px; border-radius: 50%; background: #10b981;
    animation: pulse 1.5s ease-in-out infinite; }}
  @keyframes pulse {{ 0%,100% {{ opacity:1; transform:scale(1); }} 50% {{ opacity:.5; transform:scale(1.3); }} }}

  /* ── layout ── */
  main {{ max-width: 1200px; margin: 0 auto; padding: 2rem; }}

  /* ── stat cards ── */
  .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
  .stat {{
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    padding: 1.2rem 1.4rem; position: relative; overflow: hidden;
    transition: transform .2s, border-color .2s;
  }}
  .stat:hover {{ transform: translateY(-2px); border-color: var(--accent); }}
  .stat::before {{ content:''; position:absolute; top:0; left:0; right:0; height:3px; background: var(--accent-color, var(--accent)); }}
  .stat-label {{ font-size: 0.7rem; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); margin-bottom: .4rem; }}
  .stat-value {{ font-size: 2rem; font-weight: 700; }}

  /* ── table ── */
  .table-wrap {{
    background: var(--card); border: 1px solid var(--border); border-radius: 16px; overflow: hidden;
  }}
  .table-header {{
    padding: 1.2rem 1.5rem; border-bottom: 1px solid var(--border);
    display: flex; align-items: center; justify-content: space-between;
  }}
  .table-header h2 {{ font-size: 1rem; font-weight: 600; }}
  .refresh-btn {{
    background: var(--accent); color: #fff; border: none; border-radius: 8px;
    padding: .45rem 1rem; font-size: .8rem; font-weight: 500; cursor: pointer;
    transition: opacity .2s;
  }}
  .refresh-btn:hover {{ opacity: .85; }}

  table {{ width: 100%; border-collapse: collapse; font-size: .85rem; }}
  th {{ padding: .85rem 1.2rem; text-align: left; font-size: .7rem; text-transform: uppercase;
       letter-spacing: .07em; color: var(--muted); border-bottom: 1px solid var(--border); }}
  td {{ padding: .85rem 1.2rem; border-bottom: 1px solid #1e1e2e; vertical-align: top; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: rgba(99,102,241,.06); }}

  .badge {{
    display: inline-block; padding: .2rem .65rem; border-radius: 999px;
    font-size: .7rem; font-weight: 600; text-transform: uppercase; letter-spacing: .06em;
  }}
  .cmd {{ font-family: monospace; font-size:.8rem; color: #a5b4fc;
    background: rgba(99,102,241,.1); padding: .2rem .5rem; border-radius: 6px;
    max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .job-id {{ font-family: monospace; font-size: .8rem; color: var(--muted); }}
  .ts {{ font-size: .75rem; color: var(--muted); }}

  .empty {{ text-align: center; padding: 4rem; color: var(--muted); }}
  .empty span {{ font-size: 2.5rem; display:block; margin-bottom: 1rem; }}
</style>
</head>
<body>
<header>
  <h1>⚡ QueueCTL Dashboard</h1>
  <div class="live-badge"><span class="dot"></span> Live</div>
</header>
<main>
  <div class="stats" id="stats">__STATS__</div>
  <div class="table-wrap">
    <div class="table-header">
      <h2>Jobs</h2>
      <button class="refresh-btn" onclick="location.reload()">↻ Refresh</button>
    </div>
    __TABLE__
  </div>
</main>
<script>setTimeout(() => location.reload(), 10000);</script>
</body>
</html>"""


def render_stat(label, value, color):
    return (
        f'<div class="stat" style="--accent-color:{color}">'
        f'<div class="stat-label">{label}</div>'
        f'<div class="stat-value" style="color:{color}">{value}</div>'
        f'</div>'
    )


def render_badge(state):
    color = STATE_COLORS.get(state, "#64748b")
    return f'<span class="badge" style="background:{color}22;color:{color}">{state}</span>'


def build_html():
    jobs = get_jobs()
    counts = get_counts()

    total = sum(counts.values())
    stat_html = render_stat("Total", total, "#818cf8")
    for state, color in STATE_COLORS.items():
        stat_html += render_stat(state.capitalize(), counts.get(state, 0), color)

    if not jobs or "error" in jobs[0]:
        err = jobs[0].get("error", "No jobs yet") if jobs else "No jobs yet"
        table_html = f'<div class="empty"><span>📭</span>{err}</div>'
    else:
        rows = ""
        for j in jobs:
            rows += (
                f"<tr>"
                f'<td><span class="job-id">{j["id"]}</span></td>'
                f'<td><span class="cmd" title="{j["command"]}">{j["command"]}</span></td>'
                f'<td>{render_badge(j["state"])}</td>'
                f'<td>{j["attempts"]}/{j["max_retries"]}</td>'
                f'<td>{j.get("worker_id") or "<span style=color:#374151>—</span>"}</td>'
                f'<td><span class="ts">{j["created_at"][:19].replace("T"," ")}</span></td>'
                f"</tr>"
            )
        table_html = (
            "<table><thead><tr>"
            "<th>Job ID</th><th>Command</th><th>State</th>"
            "<th>Attempts</th><th>Worker</th><th>Created</th>"
            "</tr></thead><tbody>" + rows + "</tbody></table>"
        )

    return (
        DASHBOARD_HTML
        .replace("__STATS__", stat_html)
        .replace("__TABLE__", table_html)
    )


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/dashboard"):
            body = build_html().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/api/jobs":
            body = json.dumps(get_jobs(), indent=2).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/api/stats":
            body = json.dumps(get_counts()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/health":
            body = b"QueueCTL is running"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(body)

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # suppress access logs


def start_server(port: int):
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"[dashboard] http://0.0.0.0:{port}", flush=True)
    server.serve_forever()


def main():
    port = int(os.environ.get("PORT", 8080))

    # Ensure DB dirs exist
    os.makedirs(DB_PATH.parent, exist_ok=True)
    log_dir = os.environ.get("QUEUECTL_LOG_DIR", "/tmp/queuectl/logs")
    os.makedirs(log_dir, exist_ok=True)

    # HTTP dashboard in background thread
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
