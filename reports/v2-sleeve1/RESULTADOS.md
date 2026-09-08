# Resultado Brief v2 — aborto en admisión del universo

**UNIVERSE_GATE_FAILED. 0 de 60 configuraciones utilizadas. No aprobado para operar.**

El universo no cumple el mínimo de 25 contratos: quedan 19 en septiembre de 2026 y entre 18 y 23 durante los ocho meses desde febrero. Se cerró esta ronda antes del pre-check de señal, siguiendo el criterio explícito del brief. No se modificaron los filtros para aumentar la cantidad de activos.

Este resultado rechaza la viabilidad del universo especificado con la historia OKX disponible; **no demuestra rentabilidad negativa del momentum transversal**. El objetivo Sharpe ≥ 1,5 no fue evaluado ni alcanzado.

## Admisión mensual

| Corte UTC | Contratos admitidos | Mínimo 25 |
|---|---:|---|
| 2025-03-01 | 32 | Pasa |
| 2025-04-01 | 26 | Pasa |
| 2025-05-01 | 25 | Pasa |
| 2025-06-01 | 27 | Pasa |
| 2025-07-01 | 28 | Pasa |
| 2025-08-01 | 29 | Pasa |
| 2025-09-01 | 33 | Pasa |
| 2025-10-01 | 33 | Pasa |
| 2025-11-01 | 32 | Pasa |
| 2025-12-01 | 31 | Pasa |
| 2026-01-01 | 27 | Pasa |
| 2026-02-01 | 23 | Falla |
| 2026-03-01 | 21 | Falla |
| 2026-04-01 | 21 | Falla |
| 2026-05-01 | 19 | Falla |
| 2026-06-01 | 19 | Falla |
| 2026-07-01 | 18 | Falla |
| 2026-08-01 | 18 | Falla |
| 2026-09-01 | 19 | Falla |

Cada corte exige 24 meses calendario completos y consecutivos de velas previas, mediana de volumen diario cotizado de los últimos 90 días ≥ 20M USDT, exclusión de stablecoins/tokens apalancados y un contrato por subyacente. Se admiten como máximo los 50 más líquidos. El corte no incorpora la vela del día de admisión.

## Qué restringe el universo

| Corte | Motivo de exclusión | Cantidad |
|---|---|---:|
| 2026-02-01 | Menos de 24 meses continuos o gaps | 24 |
| 2026-02-01 | Mediana de volumen inferior a 20M USDT | 82 |
| 2026-02-01 | Historia OKX ausente o no consultada por antigüedad insuficiente comprobada | 124 |
| 2026-02-01 | Stablecoin | 1 |
| 2026-09-01 | Menos de 24 meses continuos o gaps | 3 |
| 2026-09-01 | Mediana de volumen inferior a 20M USDT | 108 |
| 2026-09-01 | Historia OKX ausente o no consultada por antigüedad insuficiente comprobada | 312 |
| 2026-09-01 | Stablecoin | 1 |

Las exclusiones se asignan en orden: exclusión de tipo, disponibilidad/continuidad y después volumen. Estos conteos no son efectos independientes ni una prueba de causalidad sobre retornos. La falta de datos también reduce el universo comprobable; no se imputó historia faltante.

### Contratos admitidos en septiembre

| Perpetuo | Mediana diaria previa, millones USDT |
|---|---:|
| ETH-USDT-SWAP | 6548.94 |
| BTC-USDT-SWAP | 5452.86 |
| SOL-USDT-SWAP | 680.39 |
| DOGE-USDT-SWAP | 225.68 |
| XRP-USDT-SWAP | 165.46 |
| WLD-USDT-SWAP | 95.80 |
| PEPE-USDT-SWAP | 76.36 |
| ADA-USDT-SWAP | 46.97 |
| SUI-USDT-SWAP | 46.82 |
| BNB-USDT-SWAP | 41.50 |
| NEAR-USDT-SWAP | 35.42 |
| UNI-USDT-SWAP | 32.22 |
| LINK-USDT-SWAP | 29.09 |
| AAVE-USDT-SWAP | 28.52 |
| FIL-USDT-SWAP | 28.05 |
| BCH-USDT-SWAP | 26.00 |
| ONDO-USDT-SWAP | 25.57 |
| LTC-USDT-SWAP | 21.19 |
| AVAX-USDT-SWAP | 20.99 |

## Fuentes e integridad

Se solicitaron historias de 231 contratos; 130 devolvieron velas utilizables para comprobar admisión y 101 registraron errores de disponibilidad. Tener velas no implica cumplir 24 meses ni el umbral de liquidez.

La pertenencia histórica se reconstruyó con eventos de funding del día anterior a cada corte, extraídos de archivos oficiales diarios. Se incluyeron instrumentos retirados cuando aparecen en esos inventarios y se verificaron inconsistencias de fechas de relistado. La lista actual no se utilizó como universo histórico de supervivientes. Este método depende de la cobertura de los archivos de funding; no equivale a disponer de un registro maestro completo de todas las altas y bajas.

Las velas provienen de `/api/v5/market/history-candles`, `1Dutc`, completas (`confirm=1`), y el volumen de `volCcyQuote`, expresado en USDT para estos contratos. Fuente: [documentación oficial OKX](https://app.okx.com/docs-v5/en/#order-book-trading-market-data-get-candlesticks-history). Los inventarios proceden de `/api/v5/public/market-data-history` y archivos de `static.okx.com`; las URL exactas están en `historical_inventories.json`.

Los ZIP pasan CRC; cada descarga queda fijada por SHA256 local y se verifica al leer la caché. OKX no publica un checksum firmado independiente para estos archivos: los hashes verifican integridad local, no autenticación adicional del proveedor. No hubo sustitución por datos Binance ni relleno silencioso. Los archivos de funding usados aquí acreditan inventarios, no cobertura completa para calcular P&L.

## Corrección previa del trailing

El motor conservado exige `trail_atr >= stop_atr` o `trail_start_r >= 1`. Con trail más estrecho, espera un cierre a favor de al menos 1R y actualiza el stop para la vela siguiente. Los eventos de operaciones registran el stop efectivo de entrada, considerando el límite de drawdown, y la fracción de riesgo con costos. El servicio conserva sus mecanismos de intención persistente y reconciliación, y aplica el mismo umbral de activación.

Precisión sobre el diagnóstico anterior: el stop inicial sí existía durante la primera vela; el problema era que podía estrecharse prematuramente desde su cierre, incluso en pérdida. Un riesgo efectivo menor que 2% no viola por sí solo un límite máximo de riesgo. Las pruebas verifican posiciones largas y cortas, activación causal, costos y límite efectivo. Los reportes históricos se conservan sin recalcularlos con la corrección.

## Etapas y benchmarks

| Evaluación | Estado |
|---|---|
| IC transversal y t-stat | No ejecutado: universo insuficiente |
| Sharpe bruto/neto por horizonte | No ejecutado: universo insuficiente |
| BTC buy & hold | No ejecutado en esta ronda |
| Canasta equiponderada | No ejecutado en esta ronda |
| Control aleatorio, 1000 repeticiones | No ejecutado: no hay operaciones candidatas |
| Costos/bruto, DSR, walk-forward | No ejecutado |
| Monte Carlo 3/7/14 días, CPCV/PBO, Reality Check | No ejecutado |
| Extensión del motor/servicio a cartera | Pendiente; etapa no alcanzada |
| Demo prospectiva ≥ 3 meses | No iniciada |

No se reportan métricas de rendimiento sin sus benchmarks ni se interpretan valores ausentes como cero. Las funciones transversales de rangos y pesos están preparadas y probadas con datos sintéticos, pero no validadas como estrategia. No se recopiló spread histórico ni se calculó P&L con funding porque el gate previo falló. El optimizador completo y las pruebas finales siguen siendo etapas pendientes.

## Cierre

El protocolo se fijó antes de medir el universo; declara cinco parámetros, ensemble fijo 7/14/30 y máximo de 60 configuraciones. La ronda queda archivada y el comando de investigación rechaza reabrirla. No se enviaron órdenes, no se habilitó operativa real y no se desplegó un servicio cloud.

El Sleeve 2 no se construyó: el brief exige que el Sleeve 1 esté medido y validado antes de agregarlo. No se cumple esa condición tras el aborto de admisión. Una continuación de investigación requiere una nueva hipótesis o una revisión explícita de las restricciones; esta entrega no las relaja automáticamente.

Los datos hasta septiembre de 2026 están consumidos. Ninguna reevaluación histórica constituye un holdout independiente; cualquier futura estrategia admisible necesitará su validación prospectiva en demo. Tampoco se toman las estimaciones de techos de Sharpe de los anexos como límites universales demostrados.

Archivos de auditoría: `protocol.json`, `universe_gate.json`, `monthly_universes.json`, `universe_summary.csv`, `symbol_fetch_plan.json`, `unavailable_history.json`, `listing_date_conflicts.json`, `data_manifest.json`, `report.json`, `verification.json` y `code_manifest.json`.
