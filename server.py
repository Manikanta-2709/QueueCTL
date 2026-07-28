"""
Minimal HTTP health-check server for Render free tier.
Render requires a web service that binds to a PORT.
This runs alongside the QueueCTL worker in the same process.
"""
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import subprocess
import sys


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"QueueCTL is running\n")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Suppress access logs to keep output clean
        pass


def start_health_server(port: int):
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"[health] Listening on port {port}", flush=True)
    server.serve_forever()


def main():
    port = int(os.environ.get("PORT", 8080))

    # Start health-check HTTP server in background thread
    t = threading.Thread(target=start_health_server, args=(port,), daemon=True)
    t.start()

    # Ensure DB/log dirs exist
    db_path = os.environ.get("QUEUECTL_DB_PATH", "/tmp/queuectl/queue.db")
    log_dir = os.environ.get("QUEUECTL_LOG_DIR", "/tmp/queuectl/logs")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)

    print("[queuectl] Starting worker...", flush=True)

    # Run the worker in the foreground
    result = subprocess.run(
        [sys.executable, "-m", "queuectl.cli.main", "worker", "run"],
        env=os.environ.copy(),
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
