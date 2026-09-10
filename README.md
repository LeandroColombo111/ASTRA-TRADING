# ASTRA Trading

Bot de trading sistemático para futuros perpetuos de BTC, actualmente en **modo demo (paper trading)** contra la API de OKX. Sin capital real. `approved_for_live: false`.

## La estrategia activa: `v4_hourly`

Sistema de tendencia + ruptura en dos escalas de tiempo (config en [configs/selected.json](configs/selected.json), lógica en [src/astra/v4_hourly.py](src/astra/v4_hourly.py)):

- **Filtro de tendencia (velas de 4h)**: cruce de EMA(40) vs EMA(300). Define sesgo alcista, bajista o neutro.
- **Señal de entrada (velas de 1h)**: solo dispara si el precio rompe el máximo/mínimo de los últimos 720h (30 días) alineado con la tendencia de 4h.
- **Gestión de riesgo**: stop a 3x ATR(24), objetivo 3:1, trailing stop desde 2R de ganancia, cierre forzado a las 480h, 2% de riesgo por operación.

## Resultados del research (backtest, walk-forward, 4 folds, ~4.6 años de datos)

Ver [reports/v4-hourly-01/](reports/v4-hourly-01/) para el detalle completo.

| Métrica | Valor |
|---|---|
| Sharpe (taker) | 0.7385 |
| Sharpe (maker) | 0.8750 |
| Retorno anualizado | 13.9% |
| Retorno total (costos taker) | 61.6% |
| Max drawdown | 22.0% |
| Trades | 121 (73 long, 48 short) |
| Win rate | 38% |
| Calmar | 0.66 |
| Deflated Sharpe Ratio | 0.717 |
| Monte Carlo (bloques 7d) Sharpe p05–p95 | 0.03 – 1.65 |

## Por qué NO está en modo live todavía

El propio research documenta sus límites, no los esconde:

- **DSR 0.717, por debajo del gate de 0.95** que el proyecto exige antes de considerar un resultado no-producto-del-azar (120 configuraciones probadas en esta ronda; el DSR penaliza por eso).
- **Sin holdout independiente**: toda la serie de precios ya fue usada para buscar la estrategia en rondas anteriores (v1 a v4).
- **Research hecho con Binance USD-M como proxy de OKX**; funding y basis difieren entre exchanges.
- Monte Carlo mide variabilidad de camino sobre retornos ya observados, **no** es prueba contra overfitting — para eso está el DSR.

Ver `disclosures` en [configs/selected.json](configs/selected.json) para el detalle completo.

## Infraestructura y guardas de seguridad

El servicio (`src/astra/service.py`) corre 24/7 en una VM de GCP (free tier), con:

- **Reconciliación de órdenes a prueba de caídas**: una orden de resultado incierto tras un crash nunca se reenvía — se verifica contra el exchange primero.
- **Lock de instancia única** (`fcntl.flock`) sobre el archivo de estado.
- **Kill-switch de drawdown ajustado por depósitos** ([src/astra/accounting.py](src/astra/accounting.py)): un depósito no puede enmascarar una pérdida real inflando el pico de referencia.
- **Guardas adicionales**: apalancamiento máximo 2x, detección de posiciones/órdenes no reconocidas, verificación de stop-loss confirmado en el exchange antes de operar, chequeo de antigüedad de cotización, detección de huecos en la caché de velas.
- **Monitoreo automatizado**: un timer en la VM publica el estado a [docs/status/latest.json](docs/status/latest.json); una rutina en la nube lo audita periódicamente y deja registro en [docs/checks/](docs/checks/).

Línea base del despliegue actual: [docs/RUNTIME-BASELINE.json](docs/RUNTIME-BASELINE.json).

## Verificación local

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/pip install --no-deps -e .
.venv/bin/pytest -q
.venv/bin/astra doctor
```

`astra doctor` requiere credenciales demo de OKX en `.env` (ver `.env.example`). `.env` está excluido de Git y de Docker; nunca commitear ese archivo.

## Auditoría histórica

Antes de `v4_hourly` hubo tres rondas de research (v1, v2, v3) y un intento de portfolio transversal (v2/v2.1) que fue abortado por no alcanzar el universo mínimo de símbolos elegibles — ver [docs/README-history.md](docs/README-history.md) para ese historial. Los reportes de todas las rondas se conservan en `reports/` sin modificar, como registro de auditoría.
