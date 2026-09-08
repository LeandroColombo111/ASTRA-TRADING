#!/bin/bash
# Runs on the VM host (systemd timer). Collects the same read-only diagnostic
# data as status_server.py and pushes it to docs/status/latest.json in the
# repo, so the cloud cron routine (which cannot reach this VM's IP directly)
# can read it via a normal git clone instead.
set -euo pipefail

REPO_DIR="/opt/astra/ASTRA-TRADING"
CONTAINER="astra-demo"
cd "$REPO_DIR"

# The cloud health-check routine also commits to this repo (docs/checks/).
# Sync to the tip of origin first so our snapshot commit is never rejected
# as non-fast-forward; this file is a pure overwrite each run, so discarding
# any uncommitted local state here is safe.
git fetch origin main -q
git reset --hard origin/main -q

STATE_SCRIPT='
import sqlite3, os, json
db = sqlite3.connect(os.environ["ASTRA_STATE"])
kv = dict(db.execute("SELECT key, value FROM kv").fetchall())
events_by_kind = dict(db.execute("SELECT kind, COUNT(*) FROM events GROUP BY kind").fetchall())
events_total = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
recent = db.execute("SELECT time, kind, payload FROM events ORDER BY id DESC LIMIT 20").fetchall()
print(json.dumps({"kv": kv, "events_by_kind": events_by_kind, "events_total": events_total, "recent_events": recent}))
'

OKX_SCRIPT='
import json
from astra.okx import OKX, load_env
load_env(".env")
c = OKX(demo=True)
print(json.dumps({"equity": c.equity(), "positions": c.positions(), "pending": c.pending(), "algos": c.algos()}))
'

DOCKER_PS=$(sudo docker ps -a --filter "name=${CONTAINER}" --format '{{.Names}}\t{{.Status}}\t{{.CreatedAt}}' || true)
HEALTH=$(sudo docker exec "$CONTAINER" sh -c 'astra health --state "$ASTRA_STATE" 2>&1; echo EXIT:$?' || true)
STATE=$(sudo docker exec "$CONTAINER" python -c "$STATE_SCRIPT" || echo '{}')
OKX=$(sudo docker exec "$CONTAINER" python -c "$OKX_SCRIPT" || echo '{}')
PERFORMANCE=$(sudo docker exec "$CONTAINER" sh -c 'astra performance --state "$ASTRA_STATE"' || echo '{}')
LOGS=$(sudo docker logs "$CONTAINER" --since 90m 2>&1 | tail -c 4000 || true)

mkdir -p docs/status
python3 - "$DOCKER_PS" "$HEALTH" "$STATE" "$OKX" "$PERFORMANCE" "$LOGS" > docs/status/latest.json <<'PYEOF'
import json, sys, datetime
docker_ps, health, state, okx, performance, logs = sys.argv[1:7]
print(json.dumps({
    "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "docker_ps": docker_ps,
    "health": health,
    "state": json.loads(state) if state.strip().startswith("{") else state,
    "okx": json.loads(okx) if okx.strip().startswith("{") else okx,
    "performance": json.loads(performance) if performance.strip().startswith("{") else performance,
    "logs_tail": logs,
}, indent=2))
PYEOF

git add docs/status/latest.json
if ! git diff --cached --quiet -- docs/status/latest.json; then
  git -c user.name="astra-demo-vm" -c user.email="astra-demo-vm@localhost" commit -m "status: $(date -u +%Y-%m-%dT%H:%M:%SZ)" -q
  for attempt in 1 2 3; do
    if git push origin main -q; then
      break
    fi
    echo "push rejected (attempt $attempt), resyncing" >&2
    git fetch origin main -q
    git rebase origin/main -q || { git rebase --abort -q; git reset --hard origin/main -q; break; }
  done
fi
