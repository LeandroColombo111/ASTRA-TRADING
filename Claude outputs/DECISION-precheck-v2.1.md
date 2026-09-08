# Decisión sobre el pre-check v2.1 — no avanzar todavía

**Estado: el pre-check reporta `SIGNAL_PRECHECK_PASSED` pero no debe habilitar la fase de optimización.** Tres bloqueos, uno de ellos invalida una conclusión del propio reporte. Ninguno requiere aflojar un gate; los tres son diagnósticos que faltan.

---

## Resumen de lo medido

| Métrica | h=1 día | h=2 | h=7 | h=14 |
|---|---:|---:|---:|---:|
| IC medio | **-0,0185** | -0,0109 | +0,0003 | -0,0040 |
| IC t-stat (HAC) | **-2,15** | -0,94 | 0,02 | -0,16 |
| Sharpe bruto | **+0,961** | +0,503 | -0,315 | -0,084 |
| Sharpe neto | **+0,368** | +0,032 | -0,585 | -0,322 |
| Turnover diario | **49,6%** | 34,5% | 18,2% | 12,1% |

Costos sobre bruto: **68,8%** (gate: ≤30%). Sensibilidad: con costos de ejecución ×2 el Sharpe neto es **-0,21**.

---

## Bloqueo 1 — El control aleatorio es inválido; su conclusión debe descartarse

El reporte registra `strategy_percentile: 0.0` contra 1.000 cohortes aleatorias, lo que leído literalmente diría que la estrategia es peor que el 100% de las asignaciones al azar. **Esa conclusión no es utilizable**, porque el control no es comparable:

```
random_cohorts:  median_net_sharpe = 4,167   p95 = 5,341   (n=1000, sd=0,68)
```

Un Sharpe neto mediano de **4,17** en carteras aleatorias no es físicamente plausible para una estrategia con costos. Que sea la *mediana* de 1.000 repeticiones — no un máximo afortunado — indica un efecto sistemático de construcción, no azar. La causa casi segura: el control no rota posiciones a la tasa de la estrategia y, por lo tanto, no paga sus costos. La estrategia rota **49,6% del equity por día** y paga 1.763 USDT; el control aparentemente no.

El propio archivo lo insinúa: `"final-engine position-duration benchmark remains a later stage"`.

**Requisito:** reconstruir el control igualando **turnover, frecuencia de rebalanceo y modelo de costos** con la estrategia. Solo se aleatoriza la *asignación* de símbolos, nada más. Hasta entonces, `strategy_percentile` no se reporta ni se usa para ninguna decisión.

> Nota de método: un benchmark que hace ver mal a la estrategia es tan sospechoso como uno que la hace ver bien. Se audita igual.

---

## Bloqueo 2 — El P&L no viene de la señal que se está investigando

Es el hallazgo más importante. A h=1, el IC es **negativo y estadísticamente significativo** (t = -2,15) mientras el Sharpe bruto es **+0,96**. Verifiqué que no es un error de signo: la correlación de rango entre score y peso es **+0,968**, con exposición neta 0,0000 y 44 posiciones promedio. La cartera está efectivamente larga de score alto y corta de score bajo.

Entonces: **el ranking predice en la dirección equivocada, y aun así la cartera gana bruto.** Solo hay una explicación estructural: el IC pondera todos los activos por igual, pero el P&L los pondera por volatilidad inversa. La ganancia viene de **la ponderación, no del ranking**.

Eso importa mucho: si el edge está en el overlay de volatilidad, todo el programa de investigación —los 60 intentos, los lookbacks 7/14/30, el ensemble— está optimizando el objeto equivocado.

**Diagnóstico requerido, antes de cualquier optimización:**

1. Calcular el P&L de la cartera **equiponderada por rango**, sin overlay de volatilidad. Si es negativo (consistente con el IC), el alfa está en la ponderación y hay que investigarla a ella.
2. Descomponer: P&L total = P&L(ranking equiponderado) + P&L(overlay de volatilidad). Reportar ambos por separado.
3. Verificar que la estimación de volatilidad usada en los pesos sea **estrictamente causal** — un look-ahead ahí produciría exactamente este patrón.

---

## Bloqueo 3 — El pre-check no midió el diseño especificado

El gate de costos falla (68,8% vs ≤30%). Eso es real. Pero la medición se hizo **sin dos mecanismos que el parche ya especificaba por escrito antes de esta corrida**:

- **6d — órdenes límite post-only.** Se midió todo a taker (5 bps). Con maker (2 bps) y sin cruzar el spread, las comisiones caen de 1.412 a ~565 USDT y el costo de spread de 294 a ~0.
- **Banda de no-negociación del 20%.** El turnover medido es 49,6% diario. El brief especificaba ≤15%. Se midió 3,3x por encima del diseño.

Proyección con ejecución maker, manteniendo todo lo demás igual:

| | Actual (taker) | Con maker |
|---|---:|---:|
| Costos totales | 1.763 USDT | ~621 USDT |
| Costos / bruto | 68,8% ❌ | **~24%** ✅ |
| P&L neto | 799 USDT | ~1.941 USDT |
| Sharpe neto | 0,368 | **~0,75** |

**Esto no es aflojar el gate.** Ambos mecanismos estaban especificados antes de medir; el pre-check simplemente no los implementó. Re-medir con el diseño completo es completar la prueba, no cambiarla.

**Advertencia sobre la proyección:** el ~0,75 es un techo optimista que asume que **todas** las órdenes post-only se llenan. No es así, y en una estrategia de reversión a 1 día los fills perdidos sufren selección adversa: te llenan justo cuando estás equivocado. El rango honesto es **0,4 – 0,75**, y el punto exacto depende del modelo de fills. Por eso el parche exige modelar los fills no ejecutados: asumir llenado total es la forma más común de inflar un backtest de ejecución pasiva.

---

## Lo que en realidad se encontró

Vale la pena nombrarlo con precisión, porque cambia la investigación:

El beneficio existe **solo a horizonte de 1 día**. A 7 y 14 días el Sharpe bruto es negativo. Un edge que vive únicamente en el horizonte más corto, con 50% de turnover diario, **no es momentum: es reversión de corto plazo / provisión de liquidez.**

Esto tiene dos consecuencias, y una es buena:

- **Mala:** el brief está especificado para momentum transversal. Los lookbacks 7/14/30 y el ensemble están construidos para un efecto que, según el IC, no está presente. La hipótesis nominal no se sostiene.
- **Buena:** la reversión de corto plazo es precisamente una estrategia de **maker**, y es la única familia donde operar chico es una **ventaja** en vez de una limitación. Con órdenes pasivas no cruzás el spread: lo cobrás. Tu restricción de capital y esta familia encajan.

---

## Qué hacer, en orden

1. **Reconstruir el control aleatorio** igualando turnover y costos. Descartar el `strategy_percentile` actual.
2. **Descomposición equiponderado vs. ponderado por volatilidad**, y auditoría de causalidad del estimador de volatilidad.
3. **Re-correr el pre-check con el diseño completo**: post-only con modelo explícito de fills perdidos, más la banda de no-negociación del 20%.
4. **Recién entonces** evaluar los gates. Si el ratio de costos baja de 30% y la descomposición muestra que el P&L viene del ranking y no del overlay, se habilita la fase de optimización.
5. Si el P&L viene del overlay de volatilidad: **no optimizar el momentum.** Se reescribe la hipótesis alrededor del efecto que realmente está pagando, con su propio pre-check.

**Ninguno de estos pasos consume intentos del presupuesto de 60.** Son diagnósticos, no búsqueda.

---

## Lo que hay que decir sobre el objetivo

Con la evidencia actual, la proyección honesta de este diseño es **Sharpe neto 0,4 – 0,9**, no 1,5. El gate de 1,5 sigue en pie y no lo estoy bajando, pero conviene que sepas hacia dónde apuntan los números antes de invertir más meses.

Contexto para dimensionarlo: es la primera vez en todo el proyecto que aparece un **Sharpe bruto positivo y consistente** (0,96) con costos y funding reales medidos, no estimados. El v1 tenía 0,22 bruto y -0,75 neto. Eso es progreso real, aunque no alcance el objetivo.

Si tras los tres diagnósticos el resultado se estabiliza cerca de 0,8, la decisión —seguir con eso, agregar el Sleeve 2 de carry para complementar, o parar— es tuya, y conviene tomarla con el número a la vista y no después de otros seis meses de ajustes.
