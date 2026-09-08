# Diagnósticos post pre-check v2.1 — resultados

**Estado: DIAGNOSTICS_COMPLETE. Intentos de optimización usados: 0. Gates modificados: ninguno. No habilitado para operar.**

Módulo: `src/astra/v21_diagnostics.py` · Comando: `astra diagnostics --repetitions 400` · Salidas: `reports/v2.1-sleeve1/diagnostics/`

Los tres diagnósticos leen los artefactos ya guardados del pre-check; no recomputan la señal, porque los pesos guardados son precisamente el objeto auditado.

## Verificación previa: equivalencia del simulador

Toda simulación pasa por `simulate_exec`. Bajo sus valores por defecto reproduce `simulate_raw` del pre-check con **diferencia máxima 0,0e+00** por fila y por agregado, y la identidad contable se verifica en cada escenario. Cualquier diferencia reportada abajo es atribuible al parámetro bajo prueba, no a una reimplementación.

Baseline reproducido: Sharpe bruto 0,961 · neto 0,368 · turnover 49,6% · bruto 2.563 USDT · fees 1.412 · spread 294 · funding 56.

---

## D1 — El control aleatorio: el percentil 0,0 era un artefacto

| Control | Sharpe neto mediano | Turnover diario | Ratio vs estrategia | Percentil de la estrategia |
|---|---:|---:|---:|---:|
| **Original (como venía)** | +4,152 | 1,178 | **2,38x** | 0,0 — **anulado** |
| Permutación transversal diaria | -2,462 | 1,697 | 3,42x | 99,5 — sesgado a favor |
| **Relabeling mensual (correcto)** | **-0,838** | **0,531** | **1,07x** | **92,8** |

El control original rota **2,38 veces más** que la estrategia y aun así reporta Sharpe 4,15: su contabilidad no es la de la estrategia. Su percentil no mide nada y queda anulado.

Mi primera corrección (permutar la asignación cada día) tenía **el defecto opuesto**: destruye la persistencia de la cartera, rota 3,4x y paga costos que la estrategia nunca paga. Da percentil 99,5, favorable a la estrategia por una razón mecánica. También queda descartado como control primario.

El control válido extrae **una sola reasignación de símbolos por mes** y la aplica a todos los días de ese mes: preserva la trayectoria de exposición —y por lo tanto el turnover, ratio 1,07— mientras corta el vínculo entre el símbolo y la señal que lo eligió.

**Resultado: la estrategia está en el percentil 92,8 contra su null correcto, con mediana del control en -0,838.**

Eso es mucho mejor que "peor que el azar", pero **no alcanza el percentil ≥95 que exige el gate del brief**. Falla por poco, y falla de verdad.

---

## D2 — El IC negativo y el P&L positivo no se contradicen

| Cartera | Bruto USDT | Sharpe bruto | Sharpe neto | Turnover |
|---|---:|---:|---:|---:|
| Estrategia completa | 2.563 | 0,961 | 0,368 | 0,496 |
| **Solo ranking, sin overlay** | **1.388** | 0,699 | **-0,000** | 0,459 |
| Aporte del overlay inverso a volatilidad | 1.175 | — | — | — |

El ranking aporta el **54%** del bruto; el overlay de volatilidad inversa, el **46%**.

**Auditoría de causalidad: estrictamente causal.** La volatilidad recalculada truncando en t-1 reproduce exactamente (diferencia máxima 0,0e+00, 15 fechas muestreadas) el valor con el que se construyeron los pesos de t. No hay look-ahead.

Cómo se resuelve la paradoja: el IC se calcula equiponderando todos los símbolos; el P&L los pondera por volatilidad inversa. La señal acierta más donde el overlay pone peso. No es un error de signo ni un bug — verifiqué que la correlación de rango entre score y peso es +0,968.

**Pero el dato que importa: el ranking solo, neto de costos, rinde exactamente cero.** El momentum transversal en este universo no paga sus propios costos. Lo que levanta la estrategia por encima de cero es la ponderación por volatilidad.

---

## D3 — Ejecución maker: el gate de costos pasa

| Escenario | Sharpe neto | Costos/bruto | Gate 30% |
|---|---:|---:|---|
| Taker, como se midió | 0,368 | 68,8% | falla |
| Taker + banda 20% | 0,423 | 62,9% | falla |
| **Maker, sin banda** | **0,755** | **24,2%** | **pasa** |
| **Maker + banda 20%** | **0,783** | **22,1%** | **pasa** |
| Maker + banda + fill 80% | 0,695 | 22,6% | pasa |
| Maker + banda + fill 60% | 0,596 | 24,7% | pasa |
| Maker + banda + fill 80% adverso | -10,379 | — | falla |
| Maker + banda + fill 60% adverso | **RUINA** | — | — |

Pasar de taker a maker es la diferencia entre fallar y pasar el gate de costos: **68,8% → 22,1%**, y el Sharpe neto **0,368 → 0,783**. La banda del 20% baja el turnover de 49,6% a 45,1% y aporta poco por sí sola.

**Sobre los escenarios adversos.** Están reportados por honestidad pero **no son una estimación utilizable**. El modo adverso descarta, *todos los días durante 549 días*, exactamente las órdenes que habrían sido más rentables — usando precios futuros para elegirlas. Es una cota máxima degenerada de probabilidad prácticamente nula, no un escenario. Que destruya la cartera dice poco sobre el riesgo real.

**Advertencia metodológica registrada en el código:** las velas diarias **no pueden determinar la tasa de llenado pasiva**, que depende de la posición en la cola dentro de la barra. La tasa de fill es un supuesto declarado, no una cantidad medida. Por eso se reporta un rango.

**Rango informativo: Sharpe neto 0,60 – 0,78** (fills aleatorios, 60% a 100%).

---

## Dónde queda el proyecto

Contra los tres bloqueos del documento de decisión:

| Bloqueo | Estado |
|---|---|
| Control aleatorio inválido | **Resuelto.** Control correcto construido; percentil real 92,8 (el gate pide ≥95). |
| ¿El P&L viene de la señal o del overlay? | **Resuelto.** 54% señal / 46% overlay, sin look-ahead. Pero el ranking solo rinde cero neto. |
| Gate de costos con el diseño completo | **Resuelto.** Con maker pasa: 22,1% vs límite 30%. |

Y contra el objetivo:

- Sharpe neto proyectado con el diseño completo: **0,60 – 0,78**. El objetivo es 1,5.
- Percentil contra el control: **92,8**, por debajo del 95 exigido.
- El componente de momentum —la hipótesis nominal del brief— **no paga sus costos por sí solo**.

Mi proyección previa era 0,4–0,75; el resultado medido es 0,60–0,78. La estrategia es real y mejor de lo que sugería el reporte original, pero está en la mitad del camino al objetivo, y la parte que funciona no es la que el brief dice estar investigando.

## Qué decidir ahora

Tres caminos, y la elección es tuya:

1. **Reorientar la hipótesis al efecto que sí paga.** Si el overlay de volatilidad aporta el 46% del bruto y el ranking neto rinde cero, la investigación debería girar alrededor de la ponderación por riesgo, con su propio pre-check. Es el camino que sigue la evidencia.
2. **Agregar el Sleeve 2 (carry).** La correlación medida entre carry y tendencia es 0,02. Sumar una pata descorrelacionada es la vía aritmética para subir el Sharpe combinado sin mejorar ninguna pata.
3. **Aceptar ~0,75 y pasar a demo prospectiva.** Renuncia explícita al 1,5, con la ventaja de que la validación forward empieza ya y corre en paralelo a tu acumulación de capital.

Lo que no recomiendo es abrir los 60 intentos de optimización sobre el ranking de momentum. La evidencia dice que ese componente no es el que paga.
