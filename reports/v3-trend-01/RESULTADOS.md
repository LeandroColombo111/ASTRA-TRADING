# v3 — BTC diario/4D: el mejor resultado del proyecto, y por qué todavía no es plata

**Estado: TARGET_NOT_MET.** 6 de 8 gates pasan. Sharpe 1,046 contra objetivo 1,5. 60 intentos de 200 permitidos. No habilitado para operar.

Código: `src/astra/v3_trend.py`, `src/astra/v3_research.py` · Salidas: `reports/v3-trend-01/`

Brief conservado íntegro salvo el punto 8: señal y ancla escaladas de 1h/4h a **1D/4D**, manteniendo tu razón 1:4.

---

## Los números

| Métrica | v1 (1h/4h) | v2.1 transversal | **v3 (1D/4D)** |
|---|---:|---:|---:|
| Sharpe | -0,102 | 0,368 (0,78 maker) | **1,046** |
| Máximo drawdown | 15,6% | — | **5,2%** |
| Costos / bruto | **94,2%** | 68,8% | **0,6%** |
| Sharpe con costos taker | -1,367 | — | **1,026** |
| Monte Carlo p05 | -1,571 | -1,559 | **+0,314** |
| Probabilidad de pérdida (MC) | 59,6% | 46,7% | **1,0%** |
| DSR | 0,032 | 0,027 | **0,858** |
| Riesgo efectivo por trade | ~0,9% | — | **1,96%** |

Tres cosas que nunca habían pasado en este proyecto:

1. **Los costos dejaron de importar.** 0,6% del bruto contra 94% del v1. El Sharpe con costos taker (1,026) es casi idéntico al maker (1,046): la estrategia ya no depende de la ejecución para sobrevivir.
2. **El Monte Carlo da positivo.** p05 de +0,31 en los tres tamaños de bloque, probabilidad de pérdida 1%, probabilidad de drawdown >25% igual a **cero**.
3. **El mandato de riesgo se cumple.** Riesgo efectivo medio 1,96%, máximo 1,99% — contra el 0,9% real del v1. La corrección del trailing funcionó.

Parámetros: EMA 6/32 sobre barras de 4 días, ruptura de 40 días, ATR 14, stop 4·ATR, trailing 5·ATR activado a 1R, objetivo 6R, salida forzada a 30 días.

---

## Los tres problemas, en orden de gravedad

### 1. Sharpe 1,05 no es plata a tu capital

| | |
|---|---:|
| Retorno anualizado | **4,38%** |
| Volatilidad anualizada | 4,2% |
| Tiempo en mercado | 34% |
| Sobre 10.000 USDT | 473 USD/año |
| **Sobre 3.000 USDT** | **142 USD/año** |
| **Sobre 1.000 USDT** | **44 USD/año** |

Dijiste que la idea es ganar plata, así que este es el número que importa: **44 dólares por año** con tu capital actual, **142** cuando llegues al piso técnico.

El Sharpe es bueno; el problema es que la estrategia usa una fracción mínima del presupuesto de riesgo. Corre a 4,2% de volatilidad contra un límite de drawdown del 25%, y está fuera del mercado dos tercios del tiempo. Hay margen para escalar, pero escalar una muestra de 21 trades es exactamente como se funde una cuenta.

### 2. Las salidas son el reloj, no la estrategia

| Motivo de salida | Trades | P&L | Días |
|---|---:|---:|---:|
| Timeout / reversión de ancla | 17 | +3.060 | 30,0 |
| Stop | 4 | -894 | 14,2 |

**17 de 21 salidas ocurren exactamente al día 30**, el límite `max_hours`. El objetivo de 6R nunca se toca. El trailing nunca se toca. La reversión del ancla casi nunca llega primero.

O sea: la regla real que está generando el retorno es *"entrá en la ruptura de 40 días a favor del ancla y mantené 30 días"*. Es una apuesta de horizonte fijo, no un seguimiento de tendencia.

Peor: **30 era el valor más bajo de la grilla** {30, 60, 90, 120}. La búsqueda eligió el borde, lo que suele significar que el óptimo está fuera de la grilla. No gasté más intentos para averiguarlo, pero hay que hacerlo antes de creerle al número.

Es el mismo patrón que ya vimos dos veces: en el v1 el trailing era toda la estrategia, en el v2.1 era el overlay de volatilidad. Acá es el temporizador. El componente que paga nunca es el que el brief dice estar investigando.

### 3. Veintiún trades no alcanzan

Con 4,6 años de muestra, el error estándar de un Sharpe anualizado es ≈0,47. Un Sharpe medido de 1,046 está a ~2,2 desvíos de cero. Es sugestivo, no concluyente.

El DSR lo dice con precisión: **0,858**. Falta para el 0,95 del gate, aunque está a otra escala que el 0,032 del v1. Y el ganador apareció recién en el intento 56 de 60, saltando el score de 0,646 a 0,903 — un salto tardío es la firma típica de un outlier de muestreo.

Advertencia registrada en `protocol.json`: **no existe holdout independiente**. Esta serie fue buscada en run-001, en run-002, y el barrido de horizontes que motivó esta configuración también se midió sobre ella. Los folds walk-forward reducen la contaminación pero no la eliminan.

---

## Qué haría ahora

**Primero, barato y decisivo:** extender la grilla de `max_hours` hacia abajo (10, 15, 20, 25) y comprobar si el óptimo está en el borde o fuera. Si el mejor resultado se corre a 15 días, la estrategia es momentum de horizonte fijo y hay que investigarla como tal, no como trend following con stops. Cuesta ~20 intentos de los 140 que te quedan.

**Segundo, para que sea plata:** el camino a más retorno no es más apalancamiento sobre 21 trades. Es **más trades descorrelacionados**. Dos vías compatibles con tu brief:
- Subir la fracción de riesgo de 2% a 3% (tu punto 4 lo permite): pasa de 4,4% a ~6,6% anual. Sigue siendo poco.
- Agregar la pata de carry de funding, correlación medida 0,02 con la tendencia. Es lo único que sube el Sharpe combinado sin tocar ninguna pata.

**Tercero, en paralelo y desde ya:** arrancar la demo prospectiva de OKX. Es la única validación que todavía puede ser independiente, cuesta $0, y necesita 3 meses que corren mientras juntás capital.

---

## Lo honesto

Esto es lo mejor que produjo el proyecto y por bastante margen. La estrategia es real: sobrevive a los costos, el Monte Carlo la respalda, respeta el mandato de riesgo, y el drawdown es chico.

Pero no llega a 1,5, y a tu capital genera entre 44 y 142 dólares al año. La brecha con el objetivo ya no es de dirección — es de escala y de muestra.

Y queda pendiente el mismo problema de los tres intentos: el retorno viene de un componente que no es el que el brief nombra.
