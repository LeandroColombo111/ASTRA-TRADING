#!/bin/bash
# Runs on the VM host (systemd timer). Collects read-only diagnostics about the
# bot and OVERWRITES one file in place (/opt/astra/status/latest.json). Nothing
# is committed or pushed: the repo must not grow a commit every 30 minutes.
# Read it with:  gcloud compute ssh astra-demo ... --command "cat /opt/astra/status/latest.json"
set -euo pipefail

OUT_DIR="${ASTRA_STATUS_DIR:-/opt/astra/status}"
CONTAINER="astra-demo"
mkdir -p "$OUT_DIR"

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

python3 - "$DOCKER_PS" "$HEALTH" "$STATE" "$OKX" "$PERFORMANCE" "$LOGS" > "$OUT_DIR/latest.json.tmp" <<'PYEOF'
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

mv "$OUT_DIR/latest.json.tmp" "$OUT_DIR/latest.json"

# One compact row per run so the track record survives without git history.
python3 - "$OUT_DIR" <<'PYEOF'
import csv, json, os, sys
d = json.load(open(os.path.join(sys.argv[1], "latest.json")))
st, ok = d.get("state"), d.get("okx")
if isinstance(st, dict) and isinstance(ok, dict) and st and ok.get("equity") is not None:
    k = st.get("events_by_kind", {})
    path = os.path.join(sys.argv[1], "history.csv")
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["t", "equity", "events_total", "order_intents", "exit_reasons", "in_position"])
        w.writerow([d["generated_at_utc"], ok["equity"], st.get("events_total"), k.get("order_intent", 0), k.get("exit_reason", 0), 1 if st["kv"].get("position") else 0])
PYEOF
