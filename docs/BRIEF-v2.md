# ASTRA-TRADING — Brief v2 (especificación de ejecución)

**Este documento reemplaza al brief original de 11 puntos.** Es una especificación, no una discusión: las decisiones ya están tomadas. Los documentos `REVIEW-ASTRA-TRADING.md` y `ANEXO-hacia-sharpe-1.5.md` van como anexo de contexto — leerlos primero, pero **las instrucciones vinculantes son las de acá**.

**Objetivo sin cambios: Sharpe ≥ 1,5 fuera de muestra, validado con Monte Carlo.**

---

## 0. Por qué cambia el diseño y no el esfuerzo

El brief v1 se ejecutó con rigor y falló en 400 configuraciones. La causa está medida, no supuesta:

- A la frecuencia que exigía el v1 (señal 1h, ruptura 168h), el **costo de transacción solo consume ~1,0 unidades de Sharpe** contra un Sharpe bruto de la señal cruda de 0,22.
- El techo medido de cualquier estrategia de tendencia sobre **BTC solo**, neta de costos, es **~0,64**.
- El techo de una canasta **solo de cripto** es `s/√ρ` = 0,64/√0,75 ≈ **0,74**. Sharpe 1,5 es inalcanzable con activos direccionales correlacionados, sin importar cuántos agregues.

**La palanca que destraba el objetivo es eliminar el factor mercado.** Una estrategia transversal (relativa) no apuesta a que el cripto suba o baje; apuesta a qué monedas rinden más que las otras. Eso baja la correlación efectiva entre apuestas de 0,75 a ~0,15-0,3 y sube el techo por encima de 1,5.

---

## 1. Estrategia a construir

### Sleeve 1 — Momentum transversal sobre perpetuos (núcleo)

- **Universo:** perpetuos USDT de OKX. Filtros de admisión, aplicados **de forma causal, recalculados cada mes con datos solo previos**:
  - ≥ 24 meses de historia continua
  - volumen diario mediano (últimos 90 días) ≥ 20M USDT
  - excluir stablecoins, tokens apalancados y duplicados del mismo subyacente
  - objetivo: **30-50 símbolos**; si quedan menos de 25, abortar y reportar
- **Señal:** momentum ajustado por volatilidad. Para cada símbolo *i* y cada lookback *k*: `mom_i,k = ret_i,k / vol_i,30d`. Rankear transversalmente. **Combinar k = 7, 14 y 30 días promediando los rangos**, no eligiendo el mejor k — el ensemble es una medida anti-overfitting, no un parámetro a optimizar.
- **Cartera:** largo el quintil superior, corto el quintil inferior. **Dólar-neutral** (exposición neta = 0) y **beta-neutral a BTC** (regresión de 60 días, exposición residual a BTC ≤ 0,1).
- **Ponderación:** inversa a la volatilidad dentro de cada pata, normalizada a un **objetivo de volatilidad de cartera de 15% anualizado**.
- **Rebalanceo:** diario, 00:00 UTC, sobre velas **cerradas**. Entrada en la apertura de la vela siguiente (mantener el retardo de una barra del motor v1).
- **Control de turnover:** banda de no-negociación — solo rebalancear un símbolo si su peso objetivo se desvía > 20% del actual. Turnover objetivo ≤ 15% del nocional por día.

### Sleeve 2 — Carry de funding (se agrega solo si el Sleeve 1 no llega solo)

No construir hasta que el Sleeve 1 esté medido y validado. Cuando se construya:

- Delta-neutral: corto perp / largo spot del mismo subyacente, sobre los símbolos con funding más alto.
- **Modelar explícitamente el riesgo, no solo el ingreso.** Es obligatorio incluir: variación del basis spot-perp marcada a mercado, costo de ejecución de ambas patas, costo de rebalanceo del hedge, y margen de la pata corta.
- **Prohibido reportar el Sharpe del funding tratándolo como ingreso sin riesgo.** Ese cálculo da > 10 y es falso. Si el reporte muestra un Sharpe de carry > 4, está mal modelado: revisar antes de seguir.
- Correlación medida entre carry y tendencia a 60 días: **0,02**. Combinan bien, pero solo con el término de riesgo puesto.

### Fuera de alcance — no construir

Tendencia direccional sobre un solo activo en cualquier timeframe. Ya está medido: techo negativo neto a alta frecuencia, 0,64 a baja frecuencia. No gastar intentos ahí.

---

## 2. Restricciones duras

| # | Restricción | Detalle |
|---|---|---|
| 1 | **Venue único: OKX** | Investigación y ejecución sobre los **mismos** datos. Se elimina el proxy de Binance. Si OKX no tiene historia suficiente para un símbolo, ese símbolo sale del universo — no se sustituye por otra fuente. |
| 2 | **Futuros perpetuos, no spot** | Salvo la pata larga del Sleeve 2. Funding real incorporado al P&L. |
| 3 | **Long y short** | Por construcción: la cartera es dólar-neutral. |
| 4 | **Parámetros libres ≤ 5** | Contar y declarar explícitamente cuáles son en `protocol.json`. Los lookbacks del ensemble (7/14/30) cuentan como **uno**, no tres. |
| 5 | **Presupuesto de búsqueda: 60 configuraciones** | No 200. Menos intentos = DSR más alto. El presupuesto es duro y no se amplía. |
| 6 | **Riesgo** | Dos niveles, ambos obligatorios: (a) riesgo por posición ≤ 2-3% del capital en el stop — medido contra el stop **efectivo**, no el nominal; (b) volatilidad de cartera objetivo 15% anualizado, tope 20%. |
| 7 | **Costos** | Taker OKX real por nivel de cuenta + slippage estimado por símbolo a partir del spread histórico, no una constante global. Documentar la fuente de cada número. |

---

## 3. Gates de aceptación — verificables por código

### 3a. Pre-check de señal — **antes de optimizar nada**

Reproducir la tabla de la sección 2 del anexo para la señal transversal cruda, sin stops, sin targets, sin filtros:

- Information Coefficient transversal (correlación de rango entre señal y retorno futuro) con su t-stat
- Sharpe bruto y neto de la señal cruda a cada horizonte de rebalanceo

**Criterio de muerte: si el Sharpe neto de la señal cruda no supera 0,3, la familia se descarta y se reporta el fracaso sin gastar un solo intento de optimización.** Este gate existe precisamente porque el v1 gastó 400 intentos sobre una señal cuyo Sharpe neto crudo era negativo.

### 3b. Gate de costos

`costos_totales / bruto_antes_de_costos ≤ 0,30`. En el v1 esta relación fue **0,942**. Cualquier configuración que la supere se rechaza automáticamente, sin evaluarla.

### 3c. Gates finales sobre holdout

Todos obligatorios y simultáneos:

| Gate | Umbral |
|---|---|
| Sharpe anualizado | **≥ 1,5** |
| Deflated Sharpe Ratio | ≥ 0,95 |
| Monte Carlo — Sharpe p05 (bootstrap por bloques 3/7/14 d) | > 0 |
| Probabilistic Backtest Overfitting (PBO vía CPCV) | ≤ 0,10 |
| Máximo drawdown | ≤ 25% |
| Calmar (retorno anual / MaxDD) | ≥ 0,5 |
| Operaciones | ≥ 200, ambos lados ≥ 40 |
| Sharpe con costos duplicados | > 0,5 |
| Sharpe vs control de entradas aleatorias | percentil ≥ 95 |
| Robustez: mismos parámetros sobre un slice de universo distinto | Sharpe > 0,8 |

### 3d. Benchmarks obligatorios en todo reporte

Ninguna métrica se reporta sola. Siempre contra: **buy & hold de BTC**, **una canasta equiponderada del universo**, y el **control de entradas aleatorias** (mismo número de operaciones, misma distribución de duración, mismo mix long/short, timestamps aleatorios, 1000 repeticiones).

---

## 4. Protocolo de investigación

1. **Walk-forward anclado con ≥ 6 folds**, no 3. Los folds del v1 de ~12,7 meses daban SE(Sharpe) ≈ 0,97 — el máximo de 200 sorteos con ese ruido produce 2,7σ por puro azar.
2. **Purga y embargo entre folds**: embargo ≥ el lookback más largo (30 días) + la duración máxima de posición.
3. **Mínimo 100 operaciones por fold** para que el fold sea elegible. El umbral de 20 del v1 era demasiado laxo.
4. **DSR calculado dentro del loop como criterio de parada.** Si con los intentos restantes el DSR proyectado no puede alcanzar 0,95, detener la búsqueda y reportar fracaso. No es una línea del reporte final; es la condición de continuación.
5. **Reemplazar el Monte Carlo actual como test de overfitting.** El bootstrap de retornos diarios ya realizados se conserva — está bien implementado y mide correctamente la variabilidad muestral — pero **no puede detectar overfitting**. Agregar: **CPCV → PBO** (Bailey & López de Prado) y **White Reality Check** sobre todas las series candidatas, no solo la ganadora.
6. **Holdout.** Los datos hasta 2026-09 están quemados dos veces; ninguna ventana histórica sirve ya como validación independiente. La validación real es **walk-forward hacia adelante en la demo de OKX**, que `service.py` ya soporta. Mínimo 3 meses de paper trading antes de cualquier conclusión.
7. **Criterio de muerte explícito.** Si tras las 60 configuraciones no se cumplen los gates: se reporta el fracaso, se archiva el run, y **no se abre una ronda 3 sobre los mismos datos**. Se cambia de hipótesis. Buscar hasta que dé es la definición operativa de overfitting, y es lo que produjo el resultado del v1.

---

## 5. Qué se reutiliza del repo (no reescribir)

Esto está bien hecho. Conservarlo tal cual salvo donde se indica:

| Módulo | Acción |
|---|---|
| `data.py` | **Conservar la arquitectura**, parametrizar el símbolo y apuntar a OKX. Mantener: verificación por checksum, validación de gaps, prohibición de relleno silencioso, manifest con hash. |
| `engine.py` | **Conservar la mecánica sin lookahead** (entrada en apertura de la barra siguiente, `previous = fvals[i-1]`) y `unit_risk` con costos incluidos. **Corregir el bug de la sección 6.** Extender de posición única a cartera. |
| `service.py` | **Conservar íntegro.** Idempotencia por `clOrdId`, intent persistido antes del POST, reconciliación de órdenes inciertas, halt ante posición no reconocida, verificación de SL en el exchange, modos observe/demo, `approved_for_live: false`. Es la mejor parte del repo. Extender a cartera multi-símbolo. |
| `research.py` | Conservar `monte_carlo()` y `deflated_sharpe()`. Conservar la disciplina de `holdout.lock` y `protocol.json` escrito antes de ver resultados. Reescribir el loop de búsqueda según la sección 4. |
| `diagnostics.py` | Conservar `attribution()` **con su assert de identidad contable**. |
| `strategy.py` | Reescribir por completo (señal transversal). |

---

## 6. Bug a corregir antes que nada

En `engine.py`, el trailing se activa incondicionalmente desde el primer cierre:

```python
trail = c - side*atr*p.trail_atr     # entrada − 2·ATR
stop  = max(stop, trail)             # el stop inicial era entrada − 4·ATR
```

Con `trail_atr=2.0 < stop_atr=4.0`, **el stop inicial nunca existe**: desde la primera vela el stop efectivo es 2 ATR. Evidencia en `reports/run-002`: 109 de 129 salidas por trailing, 71 de 128 primeros ajustes ocurren en pérdida, mediana del primer ajuste en **-0,03R**, ningún trade supera 1,5R en cierre completado.

Consecuencias: **el mandato de riesgo del 2% se incumple** (riesgo real ~0,9%), y `stop_atr` / `trail_atr` quedan no identificables, lo que invalida toda búsqueda sobre esos ejes.

Corrección requerida: exigir `trail_atr ≥ stop_atr`, **o** `trail_start_r ≥ 1,0` (trailing recién tras 1R a favor). Y en todos los reportes, medir el riesgo **efectivo** — distancia al stop activo al momento de la entrada — nunca el nominal.

---

## 7. Mapeo contra tu brief original

| Punto v1 | Estado en v2 |
|---|---|
| 1. Estrategia de tendencia sobre SPY o BTC | **Cambiado.** Transversal sobre 30-50 perps. Un solo activo tiene techo 0,64 — medido. |
| 2. Elegir indicadores que se acoplen | **Cambiado.** Hipótesis económica primero, ≤ 5 parámetros libres, ensemble de lookbacks en vez de selección. |
| 3. Sharpe ≥ 1,5 | **Se mantiene**, con Calmar ≥ 0,5, PBO ≤ 0,10 y control aleatorio agregados. |
| 4. Riesgo 2-3% por trade | **Se mantiene y se corrige**: contra el stop efectivo, más objetivo de volatilidad de cartera. |
| 5. Optimización trade a trade | **Cambiado.** Optimización a nivel cartera, con gate de costos y presupuesto de 60. |
| 6. Monte Carlo contra overfitting | **Corregido.** El MC se conserva pero no mide eso; PBO/CPCV + Reality Check hacen el trabajo. |
| 7. Seguir hasta cumplir | **Eliminado.** Reemplazado por criterio de muerte explícito. Era la instrucción que garantizaba overfitting. |
| 8. 1h señal / 4h ancla | **Eliminado.** Fue la restricción más cara del v1: puso al bot donde el costo supera al edge. Rebalanceo diario. |
| 9. Long y short | **Se mantiene**, ahora por construcción. |
| 10. Futuros, no spot | **Se mantiene.** Agregar modelado de margen aislado, mark price y liquidación. |
| 11. Límite 200 intentos | **Reducido a 60.** Menos intentos, DSR más alto. |

---

## 8. Orden de ejecución

1. **Prerrequisito:** verificar salida de red a `okx.com`. En el sandbox actual está bloqueada; ejecutar en la máquina local directamente.
2. Corregir el bug del trailing (sección 6).
3. Extender `data.py` a OKX multi-símbolo. Construir el universo con los filtros causales.
4. **Correr el pre-check de señal (3a). Si no pasa, parar acá y reportar.** ← este paso ahorra las 400 iteraciones del v1.
5. Extender el motor a cartera. Implementar el gate de costos (3b).
6. Walk-forward de 6 folds, 60 configuraciones, DSR como criterio de parada.
7. PBO/CPCV, Reality Check, control aleatorio, benchmarks.
8. Si pasan todos los gates: paper trading en demo OKX, mínimo 3 meses, antes de cualquier conclusión.
9. Si no pasan: reportar el fracaso y evaluar el Sleeve 2. **No abrir una ronda sobre los mismos datos.**

---

## 9. Nota para el modelo que ejecute esto

El trabajo del v1 fue metodológicamente honesto: selló el holdout antes de mirar, verificó los datos con checksums, escribió un motor sin lookahead, reportó `CRITERIA_NOT_MET` sin adornar y calculó el DSR que condenaba su propio resultado. **Ese estándar se mantiene.**

Lo que cambia no es el rigor, es la hipótesis y las restricciones. Si los gates no se cumplen, el resultado correcto sigue siendo reportar el fracaso — nunca ajustar hasta que el número aparezca.