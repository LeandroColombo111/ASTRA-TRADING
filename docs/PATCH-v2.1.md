# Parche v2.1 al Brief — corrección del umbral de liquidez

**Aplicar sobre `BRIEF-V2-ASTRA.md`. Cambia exactamente un número y agrega una mejora de diseño. Todo lo demás del brief queda igual.**

---

## 0. Qué pasó y de quién es el error

El gate de universo funcionó como debía: cortó en horas, antes del pre-check de señal, sin tocar los filtros para forzar el resultado. Eso es exactamente el comportamiento que el brief pedía y es lo opuesto a lo que pasó en el v1, donde se gastaron 400 configuraciones sobre una hipótesis muerta.

**El número que falló es mío.** Puse "mediana de volumen diario ≥ 20M USDT" sin derivarlo de nada. Es un umbral de tamaño institucional aplicado a una cuenta de 10.000 USDT. Está mal por un factor de ~25.

---

## 1. Derivación correcta del umbral

El umbral de liquidez debe salir del tamaño de posición, no de una intuición.

```
Capital                                    10.000 USDT
Objetivo de vol de cartera                 15% anualizado
Exposición bruta resultante                ~0,5x – 1,5x capital = 5.000 – 15.000 USDT
Posiciones simultáneas (largas + cortas)   ~16
Nocional máximo por posición               ~900 USDT
```

Regla de impacto de mercado: **nocional máximo por posición ≤ 0,5% del volumen diario mediano**.

```
900 USDT / 0,005  =  180.000 USDT/día de volumen requerido
```

Con eso, **1M USDT/día ya da 5x de colchón**. El umbral de 20M daba 110x de colchón — no es prudencia, es una restricción sin fundamento que elimina la estrategia antes de poder medirla.

**Nuevo umbral: 5M USDT/día.** Sigue siendo ~25x más estricto de lo que la aritmética de impacto exige. Lo fijo en 5M y no en 1M precisamente para conservar margen sobre la estimación de exposición bruta.

### Sobre el riesgo de estar racionalizando

Hay una diferencia entre corregir un parámetro mal derivado y aflojar un gate porque falló. La distingo así, y el modelo debe hacerla cumplir:

- La derivación de arriba **no usa el resultado del gate**: sale de capital, vol objetivo y regla de impacto. Da ~1M como mínimo defendible.
- El umbral se fija **ahora, por escrito, antes de re-correr**, y **no se vuelve a tocar**. Si una ronda futura falla, no se baja de nuevo.
- **Es el único número que cambia.** El mínimo de 25 contratos, los 24 meses de historia, la exclusión de stablecoins y todos los gates de aceptación quedan intactos.

---

## 2. Efecto medido sobre los propios datos del run abortado

Recalculado sobre `monthly_universes.json`, mismos filtros de historia y tipo, variando solo el umbral de volumen:

| Corte | ≥20M (v2) | ≥10M | **≥5M (v2.1)** | ≥2M | ≥1M |
|---|---:|---:|---:|---:|---:|
| 2025-03 | 32 | 48 | **64** | 81 | 81 |
| 2025-09 | 33 | 42 | **51** | 72 | 83 |
| 2026-02 | 23 ❌ | 33 | **44** | 75 | 93 |
| 2026-05 | 19 ❌ | 30 | **37** | 62 | 82 |
| 2026-07 | 18 ❌ | 28 | **39** | 60 | 78 |
| 2026-09 | 19 ❌ | 23 ❌ | **34** | 53 | 69 |
| **Mínimo del período** | **18** | **23** | **34** | **53** | **69** |

A 5M el universo nunca baja de 34 contratos y pasa el mínimo de 25 en los 19 cortes. El resultado del gate es **consecuencia** de la corrección, no su criterio.

### Hallazgo secundario que conviene registrar

El universo se contrae de forma monótona en 2026 a todos los umbrales por encima de 1M (a 20M: 33→19; a 5M: 64→34; a 2M: 81→53), mientras que a 0,5M **crece** (81→91). Es decir: se listan más contratos pero el volumen se concentra en menos. Eso es información real sobre el mercado y afecta la capacidad futura de la estrategia. Registrarlo en el reporte; no bloquea nada.

---

## 3. Mejora de diseño: pesos continuos en vez de quintiles

Con 34-64 activos, los quintiles dejan ~7 largos y ~7 cortos y desperdician el resto del universo. Cambiar a **pesos continuos por rango**:

```
w_i  ∝  rank_i − mean(rank)        normalizado a suma bruta 1, dólar-neutral
```

Todos los activos admitidos contribuyen, ponderados por convicción. Reduce el ruido idiosincrático de forma sustancial en universos chicos y es práctica estándar en momentum transversal. Mantener la ponderación inversa a volatilidad **encima** de estos pesos, y el objetivo de vol de cartera de 15%.

Esto **no agrega un parámetro libre**: reemplaza el corte de quintil, que era uno.

---

## 4. Correcciones al review que el modelo hizo bien

Dos, y ambas son correctas. Van reconocidas por escrito:

1. **Sobre el trailing.** Escribí que "el stop de 4 ATR nunca existe". Es una exageración y el modelo tiene razón: el stop inicial **sí está activo durante la vela de entrada** — el motor evalúa `l <= active_stop` en esa misma barra antes de cualquier ajuste. Lo que ocurre es que puede estrecharse desde el cierre de esa vela, incluso estando en pérdida. La evidencia sustantiva no cambia (109 de 129 salidas por trailing, mediana del primer ajuste en -0,03R, 71 de 128 primeros ajustes en pérdida) y la corrección aplicada es la adecuada, pero mi formulación fue más absoluta que los hechos.

2. **Sobre el riesgo.** Es correcto que un riesgo efectivo menor al 2% no viola por sí solo un límite **máximo**. La objeción real es más angosta y la reformulo así: el sizing se calcula contra una distancia (4·ATR) que no es la distancia de salida efectiva, de modo que el riesgo pretendido y el realizado divergen sistemáticamente. Es un problema de consistencia interna, no de violación de un techo. Con `trail_atr ≥ stop_atr` o `trail_start_r ≥ 1` queda resuelto.

Que el modelo haya corregido al revisor sobre los hechos del código es la clase de comportamiento que hay que conservar.

---

## 5. Qué hacer ahora

1. Aplicar el umbral de 5M en el filtro de admisión. **Ningún otro cambio de filtros ni de gates.**
2. Cambiar quintiles por pesos continuos por rango (sección 3).
3. Abrir un run nuevo (`v2.1-sleeve1`), con `protocol.json` fijado antes de medir, declarando el umbral y su derivación.
4. **Ir directo al pre-check de señal (gate 3a del brief).** Es el paso que decide si esta hipótesis vive: IC transversal con t-stat, Sharpe bruto y neto de la señal cruda a cada horizonte de rebalanceo, sin stops, sin targets, sin filtros.
5. Si el Sharpe neto de la señal cruda no supera 0,3: **la hipótesis muere ahí**, se reporta el fracaso y no se toca ningún umbral más. Esa es la respuesta real y llega con dos órdenes de magnitud menos de trabajo que en el v1.

---

## 6. Nota sobre el trabajo del run abortado

Merece decirse: la reconstrucción de la pertenencia histórica del universo a partir de los inventarios de funding, en vez de usar la lista de símbolos actual, evita **sesgo de supervivencia** — el error más común y más destructivo en backtests transversales, y uno que el brief no había pedido explícitamente. Junto con el registro de conflictos de fechas de relistado, la separación de motivos de exclusión con conteos, y la negativa a imputar historia faltante, es trabajo de datos de nivel alto.

Ese estándar se mantiene. Lo único que cambia es un umbral mal derivado por el revisor.