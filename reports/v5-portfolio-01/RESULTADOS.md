# ASTRA-TRADING — dónde quedó, con todos los números

**Estado: TARGET_NOT_MET.** Sharpe 1,127 contra objetivo 1,5. 120 de 200 intentos usados. No habilitado para operar.

Código: `v3_trend.py`, `v3_research.py`, `v4_hourly.py`, `v4_research.py`, `v5_portfolio.py` · Salidas: `reports/v3-trend-01/`, `reports/v4-hourly-01/`, `reports/v5-portfolio-01/`

---

## El arco completo

| | Sharpe | Anual | MaxDD | Costos/bruto | DSR | Punto 8 |
|---|---:|---:|---:|---:|---:|:---:|
| **v1** — 1h/4h original, 400 intentos | -0,102 | — | 15,6% | 94,2% | 0,032 | ✅ |
| **v2.1** — transversal 34 perps | 0,368 | — | — | 68,8% | 0,027 | ❌ |
| **v3** — 1D/4D | 1,046 | 4,4% | 5,2% | 0,6% | 0,858 | ❌ |
| **v4** — 1h/4h, rangos abiertos | 0,875 | 13,9% | 21,0% | — | 0,717 | ✅ |
| **v5** — cartera de dos patas | **1,127** | 5,8% | 6,1% | — | **0,866** | ✅ |

La v5 combina las dos patas. Sharpe 1,127, Calmar 0,945, volatilidad 5,1%, **Sharpe con costos taker 0,977** — sigue funcionando sin ejecución pasiva. Monte Carlo p05 de +0,193 en bloques de 7 días.

---

## Qué hizo funcionar esto, en orden de importancia

**1. El horizonte, no los indicadores.** El v1 fracasó porque a su frecuencia los costos se comían el 94% del bruto. Ninguna elección de indicadores arregla eso. Abrir el horizonte lo arregló solo.

**2. Tu punto 8 nunca fue el problema.** Fijaba el tamaño de barra, no el lookback ni la tenencia. El v1 topeaba la ruptura en 200 barras y la tenencia en 480 horas, así que jamás exploró el extremo lento *a resolución 1h/4h*. Al abrir esos rangos sin tocar el tamaño de barra, el Sharpe pasó de -0,10 a 0,875 con tu restricción intacta.

**3. La diversificación por horizonte.** Las dos patas tienen correlación **0,045** — misma familia, mismo activo, pero a horizontes lo bastante separados como para ser independientes. De ahí sale la mejora de 0,875 a 1,127, no de una señal mejor.

**4. Conjuntos en vez de ganadores únicos.** Cada pata es el promedio de sus 5 mejores configuraciones, no la mejor. El ganador del v3 apareció en el intento 56 de 60 saltando el score de 0,646 a 0,903 — firma de un outlier de muestreo. Promediar el tope del ranking subió el DSR de 0,717 a 0,866.

Los pesos entre patas son **inversa de volatilidad rodante a 90 días, rezagada un día**. Causales e implementables — no los pesos de sample completo, que serían look-ahead.

---

## Lo que falta para que sea plata

El problema ahora no es el Sharpe, es la utilización. La cartera corre a **5,1% de volatilidad** contra un presupuesto de drawdown del 25%.

| Escala | Vol | Retorno anual | MaxDD estimado | Sobre 3.000 USDT |
|---|---:|---:|---:|---:|
| Actual (1x) | 5,1% | 5,8% | 6,1% | 174 USD/año |
| 2x | 10,2% | ~11,9% | ~12,3% | 357 USD/año |
| **3x** | 15,4% | **~17,4%** | ~18,4% | **522 USD/año** |

A 3x seguís dentro del límite de drawdown del 25% y el Sharpe no cambia.

**Pero ojo con el punto 4 de tu brief.** La volatilidad es baja porque el capital se reparte entre 10 configuraciones, cada una arriesgando 2% de su porción — o sea 0,2% del total por trade. Escalar a 3x devuelve el riesgo por trade a ~0,6% del total, todavía por debajo de tu 2-3%. Dimensionar cada pata contra el capital completo, con un tope de riesgo de cartera, es un paso de diseño que **todavía no está hecho**.

---

## Lo que no está resuelto

- **Sharpe 1,127 contra 1,5.** La brecha bajó mucho pero sigue.
- **DSR 0,866 contra 0,95.** Mejoró desde 0,032 del v1, pero no pasa.
- **No existe holdout independiente.** Esta serie de precios fue buscada en run-001, run-002, v3 y v4. Los folds walk-forward reducen la contaminación; no la eliminan. El conjunto reduce el riesgo de selección; no crea evidencia fuera de muestra.
- **Venue proxy.** Serie de Binance como sustituto de OKX. Funding y basis difieren.
- **El dimensionamiento de riesgo a nivel cartera está pendiente.**

---

## La tercera pata, y por qué no la construí

El carry de funding tiene correlación **0,07 con la pata rápida y 0,12 con la lenta**. Es la única vía aritmética que queda para llegar a 1,5 sin mejorar ninguna pata.

No la construí porque **no se puede validar con los datos del repo**. Un cash-and-carry necesita precios spot o de índice para marcar el basis, y acá solo hay velas de perpetuos y tasas de funding. Contabilizar el funding como ingreso sin riesgo daría un Sharpe de dos dígitos y sería falso — es exactamente el error que este proyecto viene corrigiendo. Queda declarada como `NOT_BUILT` en el reporte, con el motivo.

Para construirla hace falta bajar precios spot o de índice de BTC del mismo período.

---

## Siguientes pasos, en orden

1. **Dimensionamiento de riesgo a nivel cartera.** Convierte 5,8% anual en ~17% sin cambiar nada más. Es el paso con mayor retorno por esfuerzo.
2. **Bajar datos spot/índice y construir la pata de carry.** Es lo único que puede cerrar la brecha hasta 1,5.
3. **Arrancar la demo prospectiva de OKX.** Cuesta $0, corre en paralelo, y es la única validación que todavía puede ser independiente. Los 3 meses que pide el brief corren mientras juntás capital.
4. Quedan **80 intentos** de tus 200. No los gastaría en buscar más parámetros: la evidencia dice que la mejora viene de agregar patas descorrelacionadas, no de afinar las que hay.
