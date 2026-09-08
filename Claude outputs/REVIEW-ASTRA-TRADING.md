# Review técnico — ASTRA-TRADING

Revisión de código + resultados (`src/astra/*`, `reports/run-001`, `reports/run-002`) contra el brief de 11 puntos.
No se modificó nada del repo.

---

## 0. Veredicto

El sistema **no cumple el objetivo y el propio proyecto lo reporta correctamente**. Eso es lo mejor que tiene: no maquilló el fracaso.

| | run-001 (holdout sellado) | run-002 (misma ventana, reutilizada) |
|---|---:|---:|
| Sharpe fuera de muestra | **-0.102** | **+0.117** |
| Retorno neto 18m | -3.17% | +1.04% |
| Trades | 124 | 129 |
| Monte Carlo Sharpe p05 | -1.571 | -1.559 |
| Prob. de pérdida (MC) | 59.6% | 46.7% |
| DSR aproximado | **3.2%** | **2.7%** |
| Sharpe con costos ×2 | -1.367 | -0.793 |
| Intentos acumulados | 200 | 400 |

El objetivo era Sharpe ≥ 1.5. El resultado está en **cero, dentro del ruido**, y el DSR de 2.7% dice explícitamente que después de 400 configuraciones probadas no hay evidencia de que el Sharpe observado sea distinto de suerte.

**La conclusión correcta no es "seguir ajustando parámetros". Es que la hipótesis (breakout de tendencia 1h con ancla 4h en BTC perp) no sobrevive a los costos de transacción a esa frecuencia.** El punto 3 de abajo lo demuestra numéricamente.

---

## 1. Lo que está bien hecho (no romper esto)

Antes de las críticas, esto merece preservarse en cualquier iteración:

- **Sin lookahead.** Verificado línea por línea: `features()` usa `high.shift(1).rolling()` para el canal, el ancla 4h se reindexa a `bars.index + 1h` con `ffill` (usa solo velas 4h cerradas), y el motor entra con `previous = fvals[i-1]` en la **apertura** de la barra siguiente. Hay un bar completo de retardo. Correcto y conservador.
- **Disciplina de holdout.** `holdout.lock` escrito **antes** de calcular métricas finales, `protocol.json` que impide reiniciar o ampliar el presupuesto de intentos, criterios de gate declarados antes de mirar resultados. Esto es mejor que el 95% de los backtests que se ven.
- **Datos verificados.** Checksum SHA256 contra los archivos de Binance, validación de gaps horarios, `raise` en lugar de relleno silencioso, funding rate histórico real incorporado al P&L. `validate()` chequea coherencia OHLC.
- **Costos dentro del sizing.** `unit_risk = distance + entry*(2*fee + slip)/10000` — el tamaño de posición contempla la comisión, no solo la distancia al stop.
- **Contabilidad auditable.** `attribution()` tiene un `assert` de identidad: bruto − slippage − fees − funding = neto. Eso hace imposible el auto-engaño en la atribución.
- **La capa de ejecución es seria.** `service.py` tiene idempotencia por `clOrdId` determinístico, persiste el *intent* antes del POST, reconcilia órdenes de estado incierto en vez de reenviarlas, se detiene ante posiciones u órdenes no reconocidas, verifica que el SL exista en el exchange y cierra si falta, y bloquea live (`observe`/`demo` únicamente, `approved_for_live: false`). Está mejor construido que la estrategia que ejecuta.

---

## 2. P0 — Bug estructural: el trailing anula el stop inicial

**Este es el hallazgo más importante del review.**

Configuración seleccionada: `stop_atr = 4.0`, `trail_atr = 2.0`, `trail_start_r = 0.0`.

En `engine.py` el trailing se actualiza **de forma incondicional desde el primer cierre**:

```
trail = c - side*atr*p.trail_atr        # = entrada − 2·ATR
stop  = max(stop, trail)                 # el stop inicial era entrada − 4·ATR
```

Como `trail_atr < stop_atr` y la activación es inmediata, **el stop de 4 ATR nunca existe**. Desde la primera vela el stop efectivo es 2 ATR ≈ **0.5R**.

Evidencia en los trades de run-002:

| Métrica | Valor |
|---|---:|
| Salidas por trailing_stop | **109 / 129** |
| Salidas por target | 20 |
| Trades cuyo primer trailing ocurre **en pérdida** | **71 / 128** |
| Mediana del R al primer ajuste de trailing | **-0.03R** |
| Mediana del máximo R alcanzado (cierres completos) | **0.36R** |
| Trades que superan 1.5R en cierre completado | **0.0%** |
| P&L neto salidas por target | +5.261 USDT |
| P&L neto salidas por trailing | **-5.156 USDT** |

Consecuencias, en orden de gravedad:

1. **El punto 4 del brief (arriesgar 2-3% por trade) no se cumple.** El sizing calcula la cantidad asumiendo una pérdida de 2% a 4 ATR, pero la salida real ocurre a ~2 ATR. El riesgo real por trade es **~0.9-1%**, la mitad del mandato. `initial_risk_fraction` mediana reportada = 1.87%, pero es el riesgo *nominal* contra un stop que nunca se usa.
2. **El espacio de búsqueda es degenerado.** El optimizador no puede distinguir `stop_atr` de `trail_atr`: para el riesgo solo manda `min(stop_atr, trail_atr)`, mientras `stop_atr` sigue controlando el sizing y la distancia del target. Dos parámetros con efectos cruzados y no identificables. Todos los resultados de la búsqueda sobre esos dos ejes son interpretables solo por casualidad.
3. **Todo el P&L está determinado por la salida, no por la señal.** El sistema es, en la práctica, un stop de 0.5R con un target de 1.5R — un juego de relación riesgo/beneficio, no un sistema de tendencia.

**Qué pedirle al modelo:** o bien restringir el espacio a `trail_atr ≥ stop_atr`, o bien exigir `trail_start_r ≥ 1.0` (trailing recién después de 1R a favor), y **reportar el riesgo efectivo** (distancia al stop *activo* en el momento de la entrada), no el nominal. Y volver a correr el diagnóstico: `trailing_off` en el panel da dev 0.169 vs baseline 0.688, así que el trailing no es opcional en la configuración actual — es la estrategia.

---

## 3. P0 — Incoherencia de horizonte, y el edge no cubre los costos

### 3a. Entrada semanal, salida intradía

- Entrada: ruptura del canal de **168 horas** (7 días), filtrada por ancla EMA 8/60 en velas de 4h (≈ 1,3 / 10 días).
- Salida real: media **14,6 h**, mediana **12 h**, máximo 53 h, con un `max_hours` permitido de 240.
- Tiempo en mercado: **14,3%** de la ventana.

Se dispara con una señal de horizonte semanal y se cierra en medio día. Ningún ajuste de parámetro arregla eso; es una incoherencia de diseño entre la lógica de entrada y la de salida.

### 3b. Los costos se comen el 94% del bruto

Atribución de run-002 (129 trades, 18 meses, capital 10.000):

| Concepto | pp de capital inicial |
|---|---:|
| Bruto antes de costos de ejecución | **+18,02** |
| Slippage | -5,62 |
| Comisión de entrada | -5,62 |
| Comisión de salida | -5,61 |
| Funding | -0,13 |
| **Neto** | **+1,04** |

**Costos = 94,2% del bruto. Profit factor = 1,017.**

Por trade: nocional medio 7.262 USDT, costo ida y vuelta ~13,06 USDT ≈ **18 bps**; edge bruto ~14 USDT ≈ **19 bps**. El margen es **~1 bp por trade**. Con costos ×2 el Sharpe cae a -0,79 (run-002) / -1,37 (run-001).

Esto significa: **cualquier Sharpe positivo que salga de esta configuración es ruido de ejecución, no una señal.** Y explica por qué la "mejora" de run-002 fue cambiar `reward` de 2.0 a 1.5 — un ajuste de la relación de salida, es decir, mover el punto en la curva de costos, no encontrar edge.

**Qué pedirle al modelo:** el edge bruto tiene que ser ≥ 3-5× el costo por trade para ser explotable. Con 18 bps de costo, eso significa un edge bruto objetivo de **60-90 bps por trade**, lo que implica bajar la frecuencia ~5-10× o subir la duración media a 3-7 días. Alternativa: entradas límite/maker en vez de market (cambia el perfil de costos por completo, a cambio de fills perdidos que hay que modelar).

---

## 4. P0 — El holdout se quemó y se reutilizó

Secuencia real:

1. run-001: 200 intentos, holdout sellado 2025-03 → 2026-09. Resultado: **CRITERIA_NOT_MET**, Sharpe -0.10, DSR 3,2%.
2. run-002: diagnóstico + 200 intentos más, evaluados contra **exactamente la misma ventana** 2025-03 → 2026-09, ahora llamada `known_audit`.

El código es honesto al respecto (`known_audit_is_independent: false`, `independent_18month_target_met: false`, `holdout_rule` explícito en `protocol.json`). Eso está bien. **Pero el 0.117 de run-002 no es evidencia de nada**, y el DSR acumulado sobre 400 trials lo confirma: 2,7%.

Peor: en el panel de diagnóstico de run-002 se imprimió el Sharpe de la ventana de auditoría para las primeras 30 configuraciones **antes** de la búsqueda dirigida. Aunque la selección formal fue "solo development", la información de la ventana de auditoría ya estaba disponible al diseñar el espacio de búsqueda de la fase 2. Contaminación de segundo orden.

**Regla que hay que codificar:** una vez abierto un holdout, el único camino válido es **datos nuevos** — walk-forward real hacia adelante en el tiempo, otro activo, u otro venue. Nunca la misma ventana con otro nombre.

---

## 5. P1 — Poder estadístico: se está seleccionando ruido

Números de run-001 (200 intentos, 3 folds cronológicos de ~12,7 meses cada uno):

| Diagnóstico | Valor |
|---|---:|
| Mejor score de desarrollo | 0,742 (elegible: 0,688) |
| Desvío estándar del score entre los 200 intentos | 0,553 |
| Desvío entre folds dentro de un mismo intento (mediana) | 0,43 |
| Correlación de Sharpe entre fold 1 y fold 3 | **0,21** |
| Correlación fold 1↔2 / fold 2↔3 | 0,31 / 0,35 |
| Correlación de rango (dev score ↔ Sharpe fuera de muestra), panel n=22 | **0,34** |

Interpretación:

- Con folds de ~1,06 años, el error estándar de un Sharpe estimado es ≈ `sqrt(1/1.06)` ≈ **0,97**. Elegir el máximo de 200 sorteos con ese ruido produce ~2,7σ **por puro azar** aun con edge verdadero cero.
- El mejor score encontrado (0,688) está **por debajo** de lo que produciría el ruido puro con ese presupuesto de búsqueda. No hay señal que extraer.
- La correlación entre folds de 0,21-0,35 dice que el desempeño de una configuración en un período **casi no predice** su desempeño en el siguiente. El criterio de selección (mediana − 0,25·SD) opera sobre estimaciones que no persisten.
- El gate de elegibilidad `trades >= 20` por fold es demasiado laxo. Con 20 trades el Sharpe no tiene significado; debería ser ≥ 100 por fold, o pasar a walk-forward con muchas más ventanas.
- No hay purga ni embargo entre folds. Con posiciones de hasta 240h y EMAs de hasta 200 períodos en 4h (=800h de memoria), el estado cruza los bordes. Es menor comparado con el resto, pero conviene corregirlo.

---

## 6. P1 — El Monte Carlo no hace lo que el brief pide (punto 6)

El brief pide Monte Carlo "para asegurar que los resultados no están sobreajustados". La implementación es un **circular moving-block bootstrap de los retornos diarios ya realizados de la estrategia ya seleccionada**. Eso mide la variabilidad muestral de la curva que ya tenés — es útil y está bien implementado (bloques de 3/7/14 días, 2000 paths) — pero **es matemáticamente incapaz de detectar overfitting**, y el propio código lo declara en el campo `limitation`.

Lo que sí testea overfitting, en orden de valor:

1. **PBO / CPCV** (Bailey & López de Prado): resamplear el *procedimiento de selección completo* sobre combinaciones de folds y medir con qué frecuencia la configuración ganadora in-sample queda por debajo de la mediana out-of-sample. Es el test correcto y es directo de implementar sobre `attempts.jsonl`.
2. **White Reality Check / Hansen SPA** sobre las 200 series de retornos candidatas, no solo sobre la ganadora.
3. **Control de entradas aleatorias**: generar N sistemas con el mismo número de trades, la misma distribución de duración y el mismo mix long/short, pero timestamps de entrada aleatorios. Si la estrategia real no está en el percentil 95 de ese control, la señal no aporta nada sobre el sizing y el manejo de salidas.
4. **El DSR ya está implementado y ya dio la respuesta (2,7%).** Debería ser criterio de **parada** dentro del loop, no una línea del reporte final: si el DSR proyectado con el presupuesto de intentos restante no puede llegar al 95%, la búsqueda se detiene y se reporta fracaso de hipótesis.

---

## 7. P1 — Faltan benchmarks y validación cruzada

- **Sin benchmark.** No hay comparación contra nada. Referencia en la misma ventana: BTC buy & hold = **-6,8%, Sharpe 0,08, vol anualizada 44%**; la estrategia tiene vol **12,1%**. Sin esto, "Sharpe 0,117" no tiene marco de referencia. Hacen falta como mínimo: buy & hold, un cruce EMA simple long-only, y el control de entradas aleatorias del punto 6.
- **Un solo activo.** El punto 1 del brief permitía SPY o BTC; el modelo eligió BTC y nunca corrió el mismo código en otro activo. **Correr los mismos parámetros en ETH, SOL y SPY es el test anti-overfitting más barato que existe** y es la evidencia más convincente que se puede conseguir: si el mismo parámetro funciona en 3-4 activos correlacionados pero distintos, es mucho más probable que sea un efecto real. Es una omisión importante.
- **Venue proxy.** Datos de Binance USD-M, ejecución objetivo OKX SWAP. Está declarado, pero con 94% de sensibilidad a costos la diferencia de funding y basis entre venues no es cosmética — puede dar vuelta el signo del resultado.
- **Sharpe como métrica única.** Con 14% de tiempo en mercado y 12% de vol, un Sharpe de 1,5 es alcanzable con un retorno económicamente irrelevante. Agregar gates de Calmar (≥ 0,5), retorno anual mínimo, y reportar el Sharpe ajustado por tiempo en mercado.

---

## 8. Feedback sobre el brief mismo (esto es para vos, no para el modelo)

Varias de las fallas vienen de las instrucciones, no del ejecutor:

| Punto | Problema | Reemplazo sugerido |
|---|---|---|
| **3.** "Sharpe de al menos 1.5" | En un solo activo, una sola estrategia, neto de costos, es poco realista. El trend following en cripto neto de costos suele rendir 0,4-0,9. Un gate duro en 1,5 solo puede terminar en fracaso honesto (lo que pasó) o en overfitting. | Sharpe ≥ 0,8-1,0 **+** Calmar ≥ 0,5 **+** robustez: los mismos parámetros en ≥3 activos y ≥2 venues. |
| **7.** "Seguir buscando hasta cumplir los criterios" | Contradice el punto 11 y, sobre todo, contradice la estadística: *buscar hasta que cumpla* es la definición operativa de overfitting. Cada intento adicional degrada el DSR. | Presupuesto fijo + parada por DSR/PBO. Si no se cumple: se reporta el fracaso y se **cambia de hipótesis**, no de parámetros. |
| **6.** "Monte Carlo para asegurar que no está sobreajustado" | El Monte Carlo de retornos no hace eso (ver sección 6). | Especificar PBO/CPCV + reality check + control de entradas aleatorias. |
| **2.** "Elegir indicadores que se acoplen a la estrategia" | Invita a agregar indicadores hasta que funcione. | Fijar primero la **hipótesis económica** (¿por qué debería existir este edge? ¿quién está del otro lado?) y limitar a ≤3 parámetros libres. |
| **8.** 1h señal / 4h ancla | Fija la frecuencia **antes** de saber si el edge la soporta. Dado el hallazgo de la sección 3, es la restricción más cara del brief. | Dejar el timeframe como variable de investigación, con un gate de "costos ≤ 30% del bruto". |
| **10.** Futuros, no spot | Correcto y bien implementado (funding real incluido), pero falta modelar el **precio de liquidación por mark price** y el margen. | Agregar al motor: margen aislado, mark price, y liquidación. |
| — | **Falta en el brief:** benchmark obligatorio, límite de turnover / costo máximo como % del bruto, y un criterio explícito de "matar la hipótesis". | Agregarlos. |

---

## 9. Plan de acción, en orden

**Antes de cualquier otra optimización:**

1. Arreglar la interacción trailing/stop (sección 2) y volver a medir el riesgo **efectivo** por trade. Sin esto, ningún resultado de búsqueda es interpretable.
2. Agregar el gate de costos: rechazar cualquier configuración donde los costos superen el 30% del bruto. Habría eliminado la totalidad del espacio explorado y ahorrado 400 intentos.
3. Agregar los tres benchmarks (buy & hold, EMA simple, entradas aleatorias) al reporte.

**Después, replantear la hipótesis en vez de los parámetros:**

4. Bajar la frecuencia: probar el mismo esquema con ancla diaria y señal 4h, duración objetivo 3-7 días. Objetivo: edge bruto ≥ 60 bps por trade.
5. Correr los mismos parámetros en ETH, SOL y SPY como validación cruzada por activo.
6. Reemplazar el Monte Carlo actual por PBO/CPCV y mover el DSR al loop como criterio de parada.

**Solo entonces:**

7. Buscar datos genuinamente nuevos para validar — walk-forward hacia adelante en tiempo real (paper trading en demo OKX, que la infraestructura ya soporta), no otra pasada sobre 2025-2026.

---

## 10. Nota sobre la calidad de la ejecución del modelo

Merece decirse: el modelo hizo un trabajo **metodológicamente honesto y de infraestructura sólida**. Selló el holdout antes de mirar, verificó los datos con checksums, incorporó funding real, escribió un motor sin lookahead, construyó una capa de ejecución con reconciliación idempotente, reportó `CRITERIA_NOT_MET` sin adornar, calculó el DSR que condena su propio resultado y documentó todas las limitaciones.

El problema no es el rigor del ejecutor. Es que **la hipótesis de mercado era débil y el brief pedía un número inalcanzable con un mandato de "seguir hasta lograrlo"**. Ante esa contradicción, el modelo eligió reportar el fracaso en vez de fabricar un éxito — que es exactamente lo que debía hacer.

La corrección que sigue no es "buscar mejor". Es cambiar de hipótesis y de restricciones.
