#!/bin/bash
# Prueba en vivo de mayor riesgo (docs/FORWARD_TEST_HIGHER_RISK.md). Lo lanza systemd en la VM, una vez por dia.
# Corre el calculo en un contenedor DESCARTABLE de la imagen del bot (ya trae pandas/numpy/requests): no instala nada
# en el host, no reconstruye la imagen, no toca el servicio astra-demo ni la cuenta OKX. El resultado se REESCRIBE en
# $OUT/state.json (fuera del repo: no se commitea nada). Free tier: misma e2-micro, trafico solo entrante, unos MB de disco.
set -euo pipefail
if [ "$(id -u)" != 0 ]; then exec sudo "$0" "$@"; fi

REPO=/opt/astra/ASTRA-TRADING
OUT=/opt/astra/forward_higher_risk
IMAGE=astra-trading-astra:latest

mkdir -p "$OUT"
chown 10001:10001 "$OUT"
chmod 755 "$OUT"

# Mantener el codigo al dia sin depender del publicador de estado. El checkout es del usuario de deploy (tiene la clave).
# Si falla (red, lock de otro git), se corre con el codigo que ya esta en disco.
sudo -u leandrocolombo git -C "$REPO" fetch origin main -q \
  && sudo -u leandrocolombo git -C "$REPO" reset --hard origin/main -q \
  || echo "git sync failed; running with the code already on disk" >&2

# Tope de memoria y CPU: si algo sale mal, muere este contenedor, nunca el bot ni la VM.
# Sin --name a proposito: un contenedor viejo con el mismo nombre bloquearia todas las corridas siguientes en silencio.
exec docker run --rm \
  --user 10001:10001 --read-only --tmpfs /tmp \
  --cap-drop ALL --security-opt no-new-privileges:true \
  --memory 280m --memory-swap 560m --cpus 0.5 --pids-limit 64 \
  -e PYTHONPATH=/work/src -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 \
  -v "$REPO":/work:ro -v "$OUT":/out -w /work \
  --entrypoint python "$IMAGE" -m astra.forward_higher_risk --out-dir /out
