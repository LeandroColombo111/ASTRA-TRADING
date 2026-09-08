# ASTRA Trading — Brief v2

**Estado: `UNIVERSE_GATE_FAILED`. Ronda cerrada, 0/60 configuraciones.**

La admisión mensual con datos oficiales de OKX produjo entre 18 y 33 perpetuos elegibles. En septiembre de 2026 quedan 19, por debajo del mínimo de 25. El brief exige abortar: no se ejecutaron el pre-check de rentabilidad, optimización ni paper trading del Sleeve 1. Esto no demuestra que el momentum transversal sea negativo.

Ver [informe completo](reports/v2-sleeve1/RESULTADOS.md), [protocolo previo](reports/v2-sleeve1/protocol.json) y [especificación vinculante](docs/BRIEF-v2.md).

## Implementado y verificado

- Descarga multi-símbolo de velas diarias OKX, volumen cotizado en USDT y admisión causal mensual: 24 meses continuos, mediana de volumen de 90 días ≥ 20M, exclusiones y deduplicación.
- Inventarios históricos reconstruidos desde archivos oficiales de funding, incluyendo contratos retirados; exclusión explícita de historias no disponibles, sin sustitución por Binance.
- Caché con SHA256 local y CRC de ZIP; manifiesto y detalle de exclusiones por mes.
- Corrección del trailing direccional conservado: una distancia menor que el stop inicial exige activación ≥ 1R; el ajuste se aplica a la vela siguiente. Riesgo de entrada reportado contra el stop efectivo y costos.
- Funciones preparatorias de rangos transversales y pesos neutrales, con pruebas sintéticas. No constituyen un backtest validado.
- Barreras que impiden optimizar antes del pre-check o reabrir una ronda archivada; máximo de 60 configuraciones y cinco parámetros.

## Etapas no alcanzadas

El motor y servicio operativos conservados siguen siendo de posición única. La extensión a cartera, costos de spread histórico, pre-check, búsqueda walk-forward, CPCV/PBO, Reality Check, controles aleatorios y demo prospectiva quedan pendientes por el aborto previo. No hay un bot transversal listo para desplegar. El Sleeve 2 requiere primero un Sleeve 1 medido y validado.

## Verificación local

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q
.venv/bin/astra v2-status
.venv/bin/astra research --attempts 60
```

El último comando debe rechazar la ronda archivada, sin consumir intentos. Los datos descargados están en `data/v2`, excluidos de Git por tamaño; sus fuentes y hashes quedan en el manifiesto. `python -m astra.v2_data` reproduce la auditoría de admisión usando esa caché y metadatos locales, no abre una optimización.

Las credenciales se cargan desde `.env`, excluido de Git y Docker. No publicar ese archivo. Las pruebas no envían órdenes. Los archivos Docker y el servicio `observe/demo` corresponden a la infraestructura direccional heredada; no iniciar `demo` como si fuese el Sleeve 1. No se desplegó un servicio cloud ni se habilitó operativa real.

## Auditoría histórica

Las rondas `reports/run-001` y `reports/run-002` se conservan con sus resultados originales. Los módulos `legacy_*` preservan su lógica para auditoría; `replay` usa el trailing corregido y no reproduce exactamente los fills antiguos. El historial hasta septiembre de 2026 está consumido y no es un holdout independiente. Ninguna búsqueda adicional fue ejecutada sobre ese período.

La [documentación histórica](docs/README-history.md) registra el estado anterior; sus comandos y resultados no son la especificación activa.
