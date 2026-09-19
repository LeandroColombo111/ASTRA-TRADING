# Prueba en vivo (papel) con configuracion congelada: pre-registro

Escrito antes de que existan los datos que la juzgan. Es el unico examen realmente independiente que le queda al bot
(ver `reports/v4-hourly-01/protocol.json`: "None exists ... Only forward paper trading can still be independent").

## Que se congela

- Estrategia `v4_hourly`, config `configs/selected.json` (sha256 `930b0e7d8d7191977adedff94bf47c9e7664cadf41c399588a1f8041aa196fa4`).
- Codigo desplegado en la VM: commit `77e74fc` (entradas post-only, logging de `_reference_price`).
- Inicio de la medicion: 2026-09-18 17:05 UTC (contenedor estable en la VM e2-small).
- **Numero de pruebas (trials) = 1.** Cualquier cambio de parametros, reglas de entrada/salida o del activo **reinicia** la prueba
  con otro pre-registro. Cambios de infraestructura (VM, logging, despliegue) se permiten y se anotan al pie.

## Que se mide (todo con el script `ops/forward_track.py`, solo lectura)

- Sharpe anual sobre el equity diario, y PSR (probabilidad de que el Sharpe real sea > 0). Sin descuento por trials: es una sola configuracion.
- Cantidad de trades, mezcla de salidas (stop / objetivo), tasa de fills maker, y diferencia entre precio de referencia y fill real
  (para calibrar `impact_k`, hoy un valor supuesto).

## Ritmo esperado (para no impacientarse)

El backtest da unos 30 trades por ano en BTC. Por lo tanto: 10 trades ~ 4 meses, 30 trades ~ 1 ano, 60 trades ~ 2 anos.
Con un Sharpe real de 0.78 (el del backtest) llegar a PSR >= 0.95 llevaria unos 3.8 anos; con un Sharpe real de 0.4, unos 15 anos.
Por eso este camino sirve para descartar o confirmar problemas de ejecucion, no para aprobar el bot en pocos meses.

## Hitos y reglas de decision (fijadas ahora)

| Hito | Que se revisa | Regla |
|---|---|---|
| 10 trades | Ejecucion: fills maker, deslizamiento real, salidas por stop/objetivo, funding | Si el deslizamiento real supera 5x el supuesto o los fills maker fallan sistematicamente, se pausa y se corrige la ejecucion (no la estrategia) |
| 30 trades | Calibrar `impact_k` con fills reales; primera lectura del Sharpe | Si el Sharpe en vivo es negativo con >= 30 trades, se revisa la hipotesis completa; no se ajustan parametros para arreglarlo |
| 60 trades | Evaluacion: Sharpe, PSR, drawdown | `approved_for_live` solo se considera con PSR >= 0.95 **y** drawdown en vivo dentro de lo modelado (< 25%) |

- El freno de drawdown del 25% no se desactiva ni durante esta prueba.
- Nadie retoca parametros mirando estos resultados. Si se quiere probar una idea nueva, se pre-registra aparte y corre en paralelo.

## Notas de infraestructura

- 2026-09-18: VM pasada de e2-micro a e2-small (falta de memoria) e IP externa reservada. Sin cambios de estrategia.
