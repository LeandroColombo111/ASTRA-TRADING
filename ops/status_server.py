"""Read-only HTTP status endpoint for the astra-demo container.

Runs on the VM host (not inside the trading container), so it can call
`docker` directly. Exposes GET /status protected by a bearer token; every
value it returns comes from the same read-only commands used for manual
SSH health checks (docker ps, docker exec astra health, docker logs, and
the container's own OKX credentials for read-only account queries).

This process has no ability to submit orders, change config, or restart
anything -- it only shells out to inspection subcommands.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import os
import subprocess
import sys

TOKEN = os.environ["STATUS_TOKEN"]
CONTAINER = "astra-demo"
PORT = int(os.environ.get("STATUS_PORT", "8787"))

STATE_SCRIPT = (
    "import sqlite3, os\n"
    "db = sqlite3.connect(os.environ['ASTRA_STATE'])\n"
    "kv = dict(db.execute('SELECT key, value FROM kv').fetchall())\n"
    "events_by_kind = dict(db.execute('SELECT kind, COUNT(*) FROM events GROUP BY kind').fetchall())\n"
    "events_total = db.execute('SELECT COUNT(*) FROM events').fetchone()[0]\n"
    "recent = db.execute('SELECT time, kind, payload FROM events ORDER BY id DESC LIMIT 20').fetchall()\n"
    "import json as j\n"
    "print(j.dumps({'kv': kv, 'events_by_kind': events_by_kind, 'events_total': events_total, 'recent_events': recent}))\n"
)

OKX_SCRIPT = (
    "import json\n"
    "from astra.okx import OKX, load_env\n"
    "load_env('.env')\n"
    "c = OKX(demo=True)\n"
    "print(json.dumps({'equity': c.equity(), 'positions': c.positions(), 'pending': c.pending(), 'algos': c.algos()}))\n"
)


def run(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {"exit_code": r.returncode, "stdout": r.stdout.strip(), "stderr": r.stderr.strip()}
    except Exception as exc:
        return {"exit_code": None, "stdout": "", "stderr": f"{type(exc).__name__}: {exc}"}


def collect_status(since):
    return {
        "docker_ps": run(["docker", "ps", "-a", "--filter", f"name={CONTAINER}",
                           "--format", "{{.Names}}\t{{.Status}}\t{{.CreatedAt}}"]),
        "health": run(["docker", "exec", CONTAINER, "sh", "-c",
                        'astra health --state "$ASTRA_STATE"; echo EXIT:$?']),
        "state": run(["docker", "exec", CONTAINER, "python", "-c", STATE_SCRIPT]),
        "okx": run(["docker", "exec", CONTAINER, "python", "-c", OKX_SCRIPT]),
        "logs": run(["docker", "logs", CONTAINER, "--since", since]),
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def do_GET(self):
        if self.path.split("?")[0] != "/status":
            self.send_response(404)
            self.end_headers()
            return
        auth = self.headers.get("Authorization", "")
        expected = f"Bearer {TOKEN}"
        if not hmac.compare_digest(auth, expected):
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error":"unauthorized"}')
            return
        since = "24h"
        if "since=" in self.path:
            since = self.path.split("since=")[1].split("&")[0]
        body = json.dumps(collect_status(since)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
