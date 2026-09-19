# Triple barrera con volatilidad dinamica

## 1. Lo que el bot ya hace

Stop = `stop_atr` (3) x ATR de 24h; objetivo = `reward` (3) x la distancia del stop; limite de tiempo = `max_hours` (480h); ademas trailing y salida por cambio de tendencia. Distancia real del stop como % del precio al momento de las senales de entrada:

| activo | mediana | p10 | p90 |
|---|---|---|---|
| BTC | 2.4% | 1.6% | 4.4% |
| ETH | 3.3% | 2.3% | 5.7% |
| SOL | 4.7% | 2.9% | 7.8% |

## 2. Memoria de la volatilidad: que tan lejos llega

Correlacion entre la volatilidad de hoy y la de N dias despues (vol realizada de 7 dias contra la de los 7 dias que empiezan N dias despues) y entre |retorno| de un dia y el de N dias despues:

| activo | vol 7d, +7d | +30d | +60d | \|ret\| diario, +1d | +20d | +60d |
|---|---|---|---|---|---|---|
| BTC | 0.27 | 0.11 | 0.11 | 0.18 | 0.01 | -0.00 |
| ETH | 0.25 | 0.18 | 0.11 | 0.17 | 0.03 | 0.04 |
| SOL | 0.29 | 0.06 | 0.09 | 0.29 | 0.00 | 0.03 |

## 3. Barreras con estimador de volatilidad de mayor memoria (valores fijos y vecinos; 14 ventanas, warmup 250d)

Hipotesis fijadas antes de correr (multiplicos stop/objetivo/tiempo de produccion, sin tocar):

- **T1 memoria mas larga:** ATR de 168h (7d), con vecinos 72h y 720h, en lugar de 24h.
- **T2 pronostico mezclado:** distancia = sqrt(w * ATR24^2 + (1-w) * ATR720^2), w=0.5 y vecinos 0.3/0.7. Estructura tipo GARCH(1,1): la volatilidad se agrupa a corto plazo y revierte a su nivel de largo plazo.


**BTC**

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| original (ATR 24h) | 0.52 / 1.00 | 5/14 | 4 | 56.5% | -11.3% | 15.8% | 16.6% |
| T1 ATR 72h | 0.27 / 1.13 | 4/14 | 5 | 37.4% | -11.3% | 11.3% | 11.5% |
| T1 ATR 168h | 0.18 / 0.57 | 4/14 | 6 | 28.0% | -11.3% | 11.3% | 10.2% |
| T1 ATR 720h | 0.26 / 0.25 | 4/14 | 6 | 30.4% | -11.4% | 18.1% | 8.8% |
| T2 mezcla w=0.3 | 0.22 / 0.65 | 3/14 | 4 | 26.4% | -11.4% | 11.4% | 10.1% |
| T2 mezcla w=0.5 | 0.14 / 0.25 | 4/14 | 6 | 23.1% | -11.4% | 18.3% | 11.9% |
| T2 mezcla w=0.7 | 0.28 / 0.31 | 4/14 | 4 | 28.1% | -11.4% | 17.5% | 14.1% |
| HODL | 0.79 / 0.61 | 6/14 | - | 191.6% | -27.1% | - | 100% |

**ETH**

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| original (ATR 24h) | -0.14 / 0.34 | 2/14 | 5 | 17.4% | -9.4% | 9.4% | 12.2% |
| T1 ATR 72h | -0.37 / -0.06 | 3/14 | 7 | 9.9% | -10.0% | 18.8% | 10.1% |
| T1 ATR 168h | -0.14 / 0.28 | 2/14 | 7 | 21.4% | -9.2% | 12.7% | 10.0% |
| T1 ATR 720h | -0.45 / -0.05 | 1/14 | 7 | -4.4% | -9.3% | 13.2% | 8.8% |
| T2 mezcla w=0.3 | -0.19 / 0.33 | 3/14 | 6 | 13.3% | -9.4% | 12.0% | 10.2% |
| T2 mezcla w=0.5 | -0.24 / 0.28 | 2/14 | 6 | 12.6% | -9.4% | 10.4% | 11.2% |
| T2 mezcla w=0.7 | -0.24 / 0.29 | 2/14 | 5 | 11.9% | -9.5% | 10.4% | 11.8% |
| HODL | 0.27 / -0.53 | 6/14 | - | 5.6% | -50.1% | - | 100% |

**SOL**

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| original (ATR 24h) | -0.07 / 0.02 | 2/14 | 7 | 16.7% | -8.7% | 18.2% | 13.4% |
| T1 ATR 72h | -0.41 / -0.48 | 1/14 | 8 | 2.6% | -11.3% | 28.5% | 11.4% |
| T1 ATR 168h | -0.57 / -0.65 | 2/14 | 9 | -4.8% | -12.9% | 33.0% | 10.0% |
| T1 ATR 720h | -0.15 / -0.41 | 5/14 | 8 | 34.5% | -11.3% | 27.1% | 10.9% |
| T2 mezcla w=0.3 | -0.41 / -0.20 | 2/14 | 8 | 5.4% | -13.0% | 28.1% | 11.9% |
| T2 mezcla w=0.5 | -0.31 / -0.23 | 2/14 | 8 | 10.7% | -13.8% | 26.7% | 12.1% |
| T2 mezcla w=0.7 | -0.34 / -0.47 | 1/14 | 8 | 5.8% | -11.3% | 26.0% | 12.7% |
| HODL | 0.68 / 0.71 | 4/14 | - | 237.9% | -46.2% | - | 100% |
