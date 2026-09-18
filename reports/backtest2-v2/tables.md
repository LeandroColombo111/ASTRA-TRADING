## 0. Base: bot original vs HODL (warmup 250d, 14 ventanas de 90d, parametros fijos)

**BTC**

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| v4_hourly original | 0.52 / 1.00 | 5/14 | 4 | 56.5% | -11.3% | 15.8% | 16.6% |
| HODL (mismas ventanas) | 0.79 / 0.61 | 6/14 | 6 | 191.6% | -27.1% | 50.0% | 100% |

BTC, ventanas donde BTC subio: HODL 34.5% prom, bot 3.1%. Donde bajo: HODL -17.5%, bot 4.0%.

**ETH**

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| v4_hourly original | -0.14 / 0.34 | 2/14 | 5 | 17.4% | -9.4% | 9.4% | 12.2% |
| HODL (mismas ventanas) | 0.27 / -0.53 | 6/14 | 8 | 5.6% | -50.1% | 64.2% | 100% |

**SOL**

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| v4_hourly original | -0.07 / 0.02 | 2/14 | 7 | 16.7% | -8.7% | 18.2% | 13.4% |
| HODL (mismas ventanas) | 0.68 / 0.71 | 4/14 | 6 | 237.9% | -46.2% | 67.8% | 100% |

## A. Objetivo realista y cartera hibrida

Cartera "manga": w en HODL y (1-w) en una cuenta del bot con su propio capital; se rebalancea al inicio de cada ventana. Las metricas encadenadas unen las 14 ventanas (retorno compuesto, Sharpe diario y DD sobre toda la cadena).

| activo | w HODL | Sharpe encadenado | ganancia encadenada | DD encadenado | peor ventana | ganancia / DD |
|---|---|---|---|---|---|---|
| BTC | solo HODL | 0.89 | 191.6% | 53.9% | -27.1% | 3.6 |
| BTC | 0.9 | 0.93 | 186.8% | 48.5% | -23.7% | 3.9 |
| BTC | 0.8 | 0.97 | 179.4% | 42.7% | -20.4% | 4.2 |
| BTC | 0.7 | 1.02 | 169.5% | 36.7% | -17.0% | 4.6 |
| BTC | 0.6 | 1.07 | 157.3% | 30.6% | -13.7% | 5.1 |
| BTC | 0.5 | 1.12 | 143.3% | 24.3% | -10.3% | 5.9 |
| BTC | solo bot | 0.89 | 56.5% | 19.5% | -11.3% | 2.9 |
| ETH | solo HODL | 0.34 | 5.6% | 69.3% | -50.1% | 0.1 |
| ETH | 0.9 | 0.36 | 15.6% | 65.1% | -45.4% | 0.2 |
| ETH | 0.8 | 0.37 | 24.0% | 60.5% | -40.6% | 0.4 |
| ETH | 0.7 | 0.39 | 30.7% | 55.5% | -35.8% | 0.6 |
| ETH | 0.6 | 0.42 | 35.4% | 50.1% | -31.0% | 0.7 |
| ETH | 0.5 | 0.45 | 37.9% | 44.2% | -26.3% | 0.9 |
| ETH | solo bot | 0.40 | 17.4% | 16.0% | -9.4% | 1.1 |
| SOL | solo HODL | 0.83 | 237.9% | 78.7% | -46.2% | 3.0 |
| SOL | 0.9 | 0.85 | 250.7% | 73.3% | -41.8% | 3.4 |
| SOL | 0.8 | 0.87 | 254.0% | 67.2% | -37.3% | 3.8 |
| SOL | 0.7 | 0.89 | 247.7% | 60.2% | -32.9% | 4.1 |
| SOL | 0.6 | 0.92 | 232.1% | 52.6% | -28.4% | 4.4 |
| SOL | 0.5 | 0.94 | 208.1% | 44.3% | -24.0% | 4.7 |
| SOL | solo bot | 0.35 | 16.7% | 26.5% | -8.7% | 0.6 |

Incertidumbre (bootstrap por bloques de 20 dias, 2000 remuestreos): diferencia de Sharpe = cartera - HODL.

| activo | cartera | diferencia Sharpe (IC 95%) | P(diferencia > 0) |
|---|---|---|---|
| BTC | 0.7 HODL + bot | 0.11 [-0.07, 0.32] | 89% |
| BTC | 0.5 HODL + bot | 0.21 [-0.17, 0.65] | 85% |
| ETH | 0.7 HODL + bot | 0.05 [-0.08, 0.19] | 76% |
| ETH | 0.5 HODL + bot | 0.11 [-0.17, 0.39] | 75% |
| SOL | 0.7 HODL + bot | 0.06 [-0.07, 0.20] | 79% |
| SOL | 0.5 HODL + bot | 0.10 [-0.16, 0.38] | 77% |

## B. Modo de exposicion fija: tenencia larga con salida a efectivo cuando el macro diario pasa a bajista

La entrada usa `exposure=1.0` (100% del capital); el unico cierre es la salida por macro o un stop de desastre del 25%. Con el freno de drawdown del 25% de produccion la estrategia se congela (`halted=True`) tras la primera caida; se reporta con y sin freno.

**BTC** (ventanas de 90d)

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| v4_hourly original | 0.52 / 1.00 | 5/14 | 4 | 56.5% | -11.3% | 15.8% | 16.6% |
| tenencia EMA 20/100, con freno 25% | 0.16 / -0.48 | 5/14 | 7 | 116.9% | -25.2% | 36.3% | 65.6% |
| tenencia EMA 20/100, sin freno | 0.16 / -0.48 | 5/14 | 7 | 122.9% | -23.2% | 34.6% | 66.6% |
| tenencia EMA 10/50, con freno 25% | -0.08 / -0.41 | 4/14 | 8 | 99.9% | -19.7% | 30.9% | 60.3% |
| tenencia EMA 10/50, sin freno | -0.08 / -0.41 | 4/14 | 8 | 99.9% | -19.7% | 30.9% | 60.3% |
| tenencia EMA 30/150, con freno 25% | 0.59 / 0.05 | 5/14 | 5 | 158.5% | -19.0% | 25.6% | 68.9% |
| tenencia EMA 30/150, sin freno | 0.55 / 0.05 | 5/14 | 5 | 146.2% | -19.0% | 29.1% | 69.8% |
| tenencia precio vs SMA 200, con freno 25% | 0.43 / 0.05 | 5/14 | 5 | 152.0% | -20.4% | 24.2% | 66.8% |
| tenencia precio vs SMA 200, sin freno | 0.37 / 0.05 | 5/14 | 5 | 127.5% | -26.5% | 26.5% | 67.5% |
| tenencia precio vs SMA 150, con freno 25% | 0.09 / -0.20 | 5/14 | 7 | 133.8% | -18.2% | 22.6% | 65.5% |
| tenencia precio vs SMA 150, sin freno | 0.09 / -0.20 | 5/14 | 7 | 131.9% | -18.9% | 22.6% | 65.5% |
| HODL (mismas ventanas) | 0.79 / 0.61 | 6/14 | 6 | 191.6% | -27.1% | 50.0% | 100% |

**ETH** (ventanas de 90d)

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| v4_hourly original | -0.14 / 0.34 | 2/14 | 5 | 17.4% | -9.4% | 9.4% | 12.2% |
| tenencia EMA 20/100, con freno 25% | -0.17 / -0.00 | 4/14 | 7 | 29.1% | -32.4% | 42.9% | 54.4% |
| tenencia EMA 20/100, sin freno | -0.16 / -0.00 | 4/14 | 7 | 19.8% | -32.4% | 42.9% | 56.3% |
| tenencia EMA 10/50, con freno 25% | -0.62 / -1.38 | 3/14 | 8 | -2.8% | -25.2% | 41.8% | 50.9% |
| tenencia EMA 10/50, sin freno | -0.63 / -1.38 | 3/14 | 8 | -6.2% | -27.9% | 41.8% | 51.0% |
| tenencia EMA 30/150, con freno 25% | -0.13 / -0.26 | 4/14 | 7 | 7.6% | -25.6% | 51.4% | 55.8% |
| tenencia EMA 30/150, sin freno | -0.08 / -0.26 | 4/14 | 7 | 0.6% | -37.7% | 45.4% | 58.9% |
| tenencia precio vs SMA 200, con freno 25% | 0.13 / -0.08 | 5/14 | 7 | 82.7% | -25.2% | 25.4% | 53.3% |
| tenencia precio vs SMA 200, sin freno | 0.06 / -0.08 | 5/14 | 7 | 41.0% | -42.3% | 42.3% | 55.6% |
| tenencia precio vs SMA 150, con freno 25% | 0.05 / -0.37 | 5/14 | 7 | 77.2% | -25.2% | 33.5% | 54.6% |
| tenencia precio vs SMA 150, sin freno | 0.05 / -0.37 | 5/14 | 7 | 64.4% | -30.6% | 33.5% | 56.6% |
| HODL (mismas ventanas) | 0.27 / -0.53 | 6/14 | 8 | 5.6% | -50.1% | 64.2% | 100% |

**SOL** (ventanas de 90d)

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| v4_hourly original | -0.07 / 0.02 | 2/14 | 7 | 16.7% | -8.7% | 18.2% | 13.4% |
| tenencia EMA 20/100, con freno 25% | -0.13 / -0.15 | 4/14 | 7 | 142.6% | -25.6% | 44.3% | 43.8% |
| tenencia EMA 20/100, sin freno | 0.06 / -0.15 | 4/14 | 7 | 100.4% | -31.0% | 48.9% | 53.6% |
| tenencia EMA 10/50, con freno 25% | -0.55 / -1.24 | 3/14 | 9 | 75.0% | -32.3% | 62.9% | 44.4% |
| tenencia EMA 10/50, sin freno | -0.55 / -0.98 | 3/14 | 9 | 43.2% | -34.8% | 70.5% | 49.6% |
| tenencia EMA 30/150, con freno 25% | -0.51 / -0.51 | 4/14 | 8 | 126.8% | -25.5% | 48.6% | 41.0% |
| tenencia EMA 30/150, sin freno | -0.42 / -0.66 | 4/14 | 8 | 63.6% | -34.7% | 54.2% | 52.3% |
| tenencia precio vs SMA 200, con freno 25% | -0.14 / -0.03 | 4/14 | 7 | 189.8% | -25.5% | 44.5% | 39.3% |
| tenencia precio vs SMA 200, sin freno | 0.02 / -0.12 | 4/14 | 7 | 92.9% | -38.8% | 57.2% | 51.7% |
| tenencia precio vs SMA 150, con freno 25% | -0.40 / -0.69 | 4/14 | 8 | 104.1% | -29.8% | 61.3% | 41.0% |
| tenencia precio vs SMA 150, sin freno | -0.23 / -0.60 | 4/14 | 8 | 35.5% | -46.3% | 63.7% | 55.5% |
| HODL (mismas ventanas) | 0.68 / 0.71 | 4/14 | 6 | 237.9% | -46.2% | 67.8% | 100% |

Corrida continua (una sola pasada desde el fin del warmup, sin cortes en ventanas), BTC:

| variante | Sharpe | ganancia | DD max | % en mercado | trades | congelado |
|---|---|---|---|---|---|---|
| HODL | 1.00 | 310.3% | 53.8% | 100% | - | - |
| v4_hourly original | 0.87 | 64.1% | 19.5% | 15.4% | 104 | False |
| tenencia EMA 20/100, con freno | 0.17 | 6.3% | 27.3% | 14.5% | 2 | True |
| tenencia EMA 20/100, sin freno | 0.74 | 121.7% | 42.9% | 59.0% | 9 | False |
| tenencia EMA 10/50, con freno | -0.67 | -22.9% | 26.8% | 0.8% | 1 | True |
| tenencia EMA 10/50, sin freno | 0.69 | 103.8% | 38.1% | 54.9% | 17 | False |
| tenencia EMA 30/150, con freno | 0.75 | 108.4% | 37.3% | 36.0% | 2 | True |
| tenencia EMA 30/150, sin freno | 0.82 | 160.4% | 37.3% | 61.4% | 5 | False |
| tenencia precio vs SMA 200, con freno | 0.85 | 129.4% | 26.5% | 33.3% | 3 | True |
| tenencia precio vs SMA 200, sin freno | 0.86 | 168.9% | 35.1% | 60.2% | 17 | False |
| tenencia precio vs SMA 150, con freno | 0.89 | 138.9% | 25.8% | 32.9% | 6 | True |
| tenencia precio vs SMA 150, sin freno | 0.93 | 189.3% | 30.2% | 58.7% | 20 | False |

## C. Mas tiempo en mercado: hipotesis fijadas antes de correr (un valor + vecinos, sin grilla)

- H1 tamano por volatilidad objetivo (Moskowitz/Ooi/Pedersen 2012; Harvey et al. 2018). Nota: con la config actual el tamano ya esta en el tope de 1x, asi que H1 solo puede BAJAR la exposicion; es una prueba de calidad, no de tiempo en mercado.
- H2 entrada cuando el precio esta a menos de X% del maximo de 720h, no solo al romperlo (efecto de cercania al maximo, George & Hwang 2004). Es la unica que sube el tiempo en mercado.
- H3 solo largos (deriva positiva estructural de BTC; los cortos pagan funding y sufren squeezes). Tampoco sube el tiempo en mercado.

**BTC**

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| v4_hourly original | 0.52 / 1.00 | 5/14 | 4 | 56.5% | -11.3% | 15.8% | 16.6% |
| H3 solo largos | -0.34 / -0.11 | 6/14 | 8 | 24.2% | -7.7% | 13.6% | 12.0% |
| H1 vol objetivo 20% | 0.54 / 0.50 | 6/14 | 3 | 33.5% | -6.8% | 9.4% | 16.6% |
| H1 vol objetivo 30% | 0.50 / 0.51 | 6/14 | 4 | 49.9% | -10.1% | 14.0% | 16.6% |
| H1 vol objetivo 40% | 0.45 / 0.57 | 5/14 | 4 | 58.0% | -13.3% | 18.5% | 16.6% |
| H2 cerca del maximo 1% | 0.75 / 1.00 | 6/14 | 4 | 82.4% | -11.3% | 11.3% | 20.9% |
| H2 cerca del maximo 3% | 0.44 / 0.63 | 5/14 | 7 | 77.6% | -6.3% | 11.5% | 33.5% |
| H2 cerca del maximo 5% | 0.33 / 0.92 | 5/14 | 5 | 72.2% | -11.8% | 18.5% | 44.0% |
| HODL (mismas ventanas) | 0.79 / 0.61 | 6/14 | 6 | 191.6% | -27.1% | 50.0% | 100% |

**ETH**

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| v4_hourly original | -0.14 / 0.34 | 2/14 | 5 | 17.4% | -9.4% | 9.4% | 12.2% |
| H3 solo largos | -0.53 / 0.00 | 2/14 | 6 | 12.2% | -4.0% | 7.5% | 8.3% |
| H1 vol objetivo 20% | -0.29 / 0.08 | 2/14 | 7 | 4.3% | -5.5% | 7.6% | 12.2% |
| H1 vol objetivo 30% | -0.41 / -0.16 | 2/14 | 8 | 3.6% | -8.2% | 12.8% | 12.2% |
| H1 vol objetivo 40% | -0.45 / -0.16 | 2/14 | 8 | 3.9% | -10.7% | 16.5% | 12.2% |
| H2 cerca del maximo 1% | -0.47 / 0.11 | 2/14 | 7 | -4.3% | -13.0% | 16.5% | 15.8% |
| H2 cerca del maximo 3% | -0.40 / -0.18 | 3/14 | 7 | -7.5% | -16.2% | 21.6% | 21.6% |
| H2 cerca del maximo 5% | -0.51 / -0.25 | 2/14 | 8 | -23.0% | -25.0% | 36.5% | 27.1% |
| HODL (mismas ventanas) | 0.27 / -0.53 | 6/14 | 8 | 5.6% | -50.1% | 64.2% | 100% |

**SOL**

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| v4_hourly original | -0.07 / 0.02 | 2/14 | 7 | 16.7% | -8.7% | 18.2% | 13.4% |
| H3 solo largos | -0.10 / 0.12 | 3/14 | 5 | 14.5% | -7.4% | 8.8% | 7.9% |
| H1 vol objetivo 20% | -0.29 / -0.43 | 2/14 | 7 | 9.0% | -6.0% | 13.9% | 13.5% |
| H1 vol objetivo 30% | -0.29 / -0.44 | 2/14 | 7 | 12.0% | -8.9% | 20.6% | 13.5% |
| H1 vol objetivo 40% | -0.30 / -0.46 | 2/14 | 7 | 13.9% | -11.8% | 26.9% | 13.4% |
| H2 cerca del maximo 1% | 0.33 / 0.77 | 4/14 | 6 | 37.3% | -7.0% | 13.4% | 16.0% |
| H2 cerca del maximo 3% | 0.30 / 0.21 | 2/14 | 6 | 49.8% | -7.9% | 9.9% | 18.7% |
| H2 cerca del maximo 5% | 0.18 / 0.34 | 2/14 | 6 | 40.1% | -9.7% | 9.7% | 23.4% |
| HODL (mismas ventanas) | 0.68 / 0.71 | 4/14 | 6 | 237.9% | -46.2% | 67.8% | 100% |

## D. Re-verificacion con warmup correcto: stop_atr/reward y min_trend

**stop_atr x reward, BTC** (Sharpe mediana / ganancia total con cada valor fijo en las 14 ventanas)

| valores | Sharpe media | Sharpe mediana | ganancia total |
|---|---|---|---|
| {'reward': 2.0, 'stop_atr': 2.0, 'trail_atr': 3.0} | -0.65 | -0.61 | -8.9% |
| {'reward': 3.0, 'stop_atr': 2.0, 'trail_atr': 3.0} | -0.15 | -0.22 | 10.8% |
| {'reward': 4.0, 'stop_atr': 2.0, 'trail_atr': 3.0} | -0.18 | 0.08 | -4.8% |
| {'reward': 6.0, 'stop_atr': 2.0, 'trail_atr': 3.0} | 0.13 | 0.29 | 15.4% |
| {'reward': 2.0, 'stop_atr': 3.0, 'trail_atr': 3.0} | 0.21 | 0.46 | 40.1% |
| {'reward': 3.0, 'stop_atr': 3.0, 'trail_atr': 3.0} **(produccion)** | 0.52 | 1.00 | 56.5% |
| {'reward': 4.0, 'stop_atr': 3.0, 'trail_atr': 3.0} | 0.42 | 0.63 | 44.1% |
| {'reward': 6.0, 'stop_atr': 3.0, 'trail_atr': 3.0} | 0.36 | 0.91 | 46.0% |
| {'reward': 2.0, 'stop_atr': 4.0, 'trail_atr': 4.0} | -0.06 | 0.63 | 16.3% |
| {'reward': 3.0, 'stop_atr': 4.0, 'trail_atr': 4.0} | -0.01 | 0.40 | 16.3% |
| {'reward': 4.0, 'stop_atr': 4.0, 'trail_atr': 4.0} | -0.18 | 0.22 | 8.4% |
| {'reward': 6.0, 'stop_atr': 4.0, 'trail_atr': 4.0} | -0.07 | 0.24 | 23.4% |
| {'reward': 2.0, 'stop_atr': 5.0, 'trail_atr': 5.0} | -0.11 | 0.23 | 10.9% |
| {'reward': 3.0, 'stop_atr': 5.0, 'trail_atr': 5.0} | -0.48 | 0.03 | -5.9% |
| {'reward': 4.0, 'stop_atr': 5.0, 'trail_atr': 5.0} | -0.34 | 0.18 | 1.8% |
| {'reward': 6.0, 'stop_atr': 5.0, 'trail_atr': 5.0} | -0.31 | 0.18 | 1.1% |

Re-eleccion por ventana (mejor Sharpe de los 365d previos): Sharpe -0.03 / 0.36, ganancia 29.4%, corr(IS, OOS) = -0.14. Valor fijo de produccion: 0.52 / 1.00, 56.5%.

**stop_atr x reward, ETH** (Sharpe mediana / ganancia total con cada valor fijo en las 14 ventanas)

| valores | Sharpe media | Sharpe mediana | ganancia total |
|---|---|---|---|
| {'reward': 2.0, 'stop_atr': 2.0, 'trail_atr': 3.0} | -0.12 | 0.21 | 18.1% |
| {'reward': 3.0, 'stop_atr': 2.0, 'trail_atr': 3.0} | -0.50 | -0.14 | 0.6% |
| {'reward': 4.0, 'stop_atr': 2.0, 'trail_atr': 3.0} | -0.65 | -0.32 | -10.1% |
| {'reward': 6.0, 'stop_atr': 2.0, 'trail_atr': 3.0} | -0.57 | -0.18 | -12.6% |
| {'reward': 2.0, 'stop_atr': 3.0, 'trail_atr': 3.0} | -0.23 | -0.23 | 17.8% |
| {'reward': 3.0, 'stop_atr': 3.0, 'trail_atr': 3.0} **(produccion)** | -0.14 | 0.34 | 17.4% |
| {'reward': 4.0, 'stop_atr': 3.0, 'trail_atr': 3.0} | -0.34 | 0.51 | 3.7% |
| {'reward': 6.0, 'stop_atr': 3.0, 'trail_atr': 3.0} | -0.19 | 0.53 | 19.5% |
| {'reward': 2.0, 'stop_atr': 4.0, 'trail_atr': 4.0} | 0.02 | -0.00 | 14.1% |
| {'reward': 3.0, 'stop_atr': 4.0, 'trail_atr': 4.0} | -0.17 | -0.01 | 0.8% |
| {'reward': 4.0, 'stop_atr': 4.0, 'trail_atr': 4.0} | -0.03 | 0.48 | 8.7% |
| {'reward': 6.0, 'stop_atr': 4.0, 'trail_atr': 4.0} | -0.24 | 0.56 | 9.3% |
| {'reward': 2.0, 'stop_atr': 5.0, 'trail_atr': 5.0} | -0.33 | -0.17 | -2.2% |
| {'reward': 3.0, 'stop_atr': 5.0, 'trail_atr': 5.0} | 0.24 | 1.10 | 22.9% |
| {'reward': 4.0, 'stop_atr': 5.0, 'trail_atr': 5.0} | 0.06 | 0.47 | 21.3% |
| {'reward': 6.0, 'stop_atr': 5.0, 'trail_atr': 5.0} | -0.15 | 0.46 | 7.6% |

Re-eleccion por ventana (mejor Sharpe de los 365d previos): Sharpe 0.00 / -0.02, ganancia 19.4%, corr(IS, OOS) = -0.03. Valor fijo de produccion: -0.14 / 0.34, 17.4%.

**stop_atr x reward, SOL** (Sharpe mediana / ganancia total con cada valor fijo en las 14 ventanas)

| valores | Sharpe media | Sharpe mediana | ganancia total |
|---|---|---|---|
| {'reward': 2.0, 'stop_atr': 2.0, 'trail_atr': 3.0} | -0.62 | -0.46 | -14.3% |
| {'reward': 3.0, 'stop_atr': 2.0, 'trail_atr': 3.0} | -0.27 | 0.51 | 13.5% |
| {'reward': 4.0, 'stop_atr': 2.0, 'trail_atr': 3.0} | -0.25 | -0.11 | 27.6% |
| {'reward': 6.0, 'stop_atr': 2.0, 'trail_atr': 3.0} | -0.18 | -0.08 | 25.1% |
| {'reward': 2.0, 'stop_atr': 3.0, 'trail_atr': 3.0} | 0.14 | 0.07 | 19.5% |
| {'reward': 3.0, 'stop_atr': 3.0, 'trail_atr': 3.0} **(produccion)** | -0.07 | 0.02 | 16.7% |
| {'reward': 4.0, 'stop_atr': 3.0, 'trail_atr': 3.0} | -0.01 | 0.10 | 15.1% |
| {'reward': 6.0, 'stop_atr': 3.0, 'trail_atr': 3.0} | -0.02 | 0.20 | 13.9% |
| {'reward': 2.0, 'stop_atr': 4.0, 'trail_atr': 4.0} | 0.38 | 0.81 | 39.3% |
| {'reward': 3.0, 'stop_atr': 4.0, 'trail_atr': 4.0} | 0.32 | 0.28 | 30.1% |
| {'reward': 4.0, 'stop_atr': 4.0, 'trail_atr': 4.0} | 0.29 | 0.91 | 24.1% |
| {'reward': 6.0, 'stop_atr': 4.0, 'trail_atr': 4.0} | 0.37 | 0.84 | 28.8% |
| {'reward': 2.0, 'stop_atr': 5.0, 'trail_atr': 5.0} | 0.23 | 0.29 | 25.0% |
| {'reward': 3.0, 'stop_atr': 5.0, 'trail_atr': 5.0} | 0.23 | 0.38 | 24.3% |
| {'reward': 4.0, 'stop_atr': 5.0, 'trail_atr': 5.0} | 0.12 | 0.21 | 21.1% |
| {'reward': 6.0, 'stop_atr': 5.0, 'trail_atr': 5.0} | 0.16 | 0.25 | 23.8% |

Re-eleccion por ventana (mejor Sharpe de los 365d previos): Sharpe 0.03 / 0.51, ganancia 13.4%, corr(IS, OOS) = -0.24. Valor fijo de produccion: -0.07 / 0.02, 16.7%.

**min_trend, BTC** (Sharpe mediana / ganancia total con cada valor fijo en las 14 ventanas)

| valores | Sharpe media | Sharpe mediana | ganancia total |
|---|---|---|---|
| {'min_trend': 0.0} **(produccion)** | 0.52 | 1.00 | 56.5% |
| {'min_trend': 0.005} | 0.18 | 0.57 | 36.8% |
| {'min_trend': 0.01} | 0.04 | 0.34 | 32.8% |
| {'min_trend': 0.02} | 0.10 | 0.42 | 38.9% |
| {'min_trend': 0.04} | -0.26 | 0.18 | 10.8% |

Re-eleccion por ventana (mejor Sharpe de los 365d previos): Sharpe 0.19 / 0.18, ganancia 25.2%, corr(IS, OOS) = -0.28. Valor fijo de produccion: 0.52 / 1.00, 56.5%.

**min_trend, ETH** (Sharpe mediana / ganancia total con cada valor fijo en las 14 ventanas)

| valores | Sharpe media | Sharpe mediana | ganancia total |
|---|---|---|---|
| {'min_trend': 0.0} **(produccion)** | -0.14 | 0.34 | 17.4% |
| {'min_trend': 0.005} | 0.09 | 0.45 | 29.8% |
| {'min_trend': 0.01} | 0.09 | 0.45 | 29.8% |
| {'min_trend': 0.02} | -0.22 | 0.21 | 24.5% |
| {'min_trend': 0.04} | -0.06 | 0.09 | 21.2% |

Re-eleccion por ventana (mejor Sharpe de los 365d previos): Sharpe 0.12 / 0.21, ganancia 28.0%, corr(IS, OOS) = -0.42. Valor fijo de produccion: -0.14 / 0.34, 17.4%.

**min_trend, SOL** (Sharpe mediana / ganancia total con cada valor fijo en las 14 ventanas)

| valores | Sharpe media | Sharpe mediana | ganancia total |
|---|---|---|---|
| {'min_trend': 0.0} **(produccion)** | -0.07 | 0.02 | 16.7% |
| {'min_trend': 0.005} | -0.24 | -0.40 | 9.3% |
| {'min_trend': 0.01} | -0.17 | -0.40 | 14.2% |
| {'min_trend': 0.02} | -0.34 | -0.17 | 4.3% |
| {'min_trend': 0.04} | -0.28 | -0.38 | 5.2% |

Re-eleccion por ventana (mejor Sharpe de los 365d previos): Sharpe -0.36 / -0.69, ganancia -2.2%, corr(IS, OOS) = -0.13. Valor fijo de produccion: -0.07 / 0.02, 16.7%.

## E. Calibracion de impact_k

Fills reales con `_reference_price` registrados desde el despliegue del logging: **0** (el estado tiene 6 eventos, todos de la prueba manual del 15/9, anteriores al registro; no hubo ninguna entrada de estrategia). No hay base para calibrar; no se inventa un valor. Sensibilidad del resultado a impact_k (BTC, original, 14 ventanas):

| impact_k | Sharpe media / mediana | ganancia total |
|---|---|---|
| 0.0 | 0.52 / 1.00 | 56.6% |
| 1.0 | 0.52 / 1.00 | 56.5% |
| 3.0 | 0.52 / 1.00 | 56.5% |
| 10.0 | 0.51 / 0.99 | 56.2% |

## F. Mas periodos y activos

**Ventanas adicionales.** Con parametros fijos no hace falta un ano de entrenamiento: las ventanas pueden empezar al terminar el warmup (250d). Eso suma ventanas de 2022 (mercado bajista). Aviso: los parametros de `selected.json` se eligieron con esta misma historia, asi que ninguna ventana es fuera de muestra en sentido estricto; esto mide estabilidad en el tiempo, no capacidad predictiva.

**BTC**, ventanas de 90d desde el fin del warmup

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| v4_hourly original | 0.49 / 1.07 | 5/15 | 4 | 51.8% | -8.1% | 11.5% | 15.8% |
| HODL (mismas ventanas) | 0.90 / 0.30 | 5/15 | 7 | 235.7% | -23.8% | 42.6% | 100% |

**ETH**, ventanas de 90d desde el fin del warmup

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| v4_hourly original | -0.10 / -0.01 | 4/15 | 8 | 25.8% | -7.7% | 8.1% | 12.4% |
| HODL (mismas ventanas) | 0.55 / 0.30 | 6/15 | 7 | 35.0% | -49.6% | 59.0% | 100% |

**SOL**, ventanas de 90d desde el fin del warmup

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| v4_hourly original | 0.32 / 0.59 | 2/15 | 4 | 31.1% | -10.5% | 10.5% | 12.4% |
| HODL (mismas ventanas) | 0.68 / 0.17 | 6/15 | 7 | 101.5% | -64.9% | 69.6% | 100% |

**Sensibilidad a la definicion de ventana (BTC, original).**

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| 60d / paso 60d | 0.44 / 0.63 | 8/22 | 10 | 68.9% | -7.8% | 12.9% | 15.8% |
| 90d / paso 90d | 0.52 / 1.00 | 5/14 | 4 | 56.5% | -11.3% | 15.8% | 16.6% |
| 180d / paso 180d | 0.77 / 1.08 | 2/7 | 1 | 54.7% | -11.9% | 11.9% | 16.5% |
| 90d desfase +30d | 0.50 / 0.80 | 6/14 | 5 | 44.9% | -6.3% | 10.5% | 15.8% |
| 90d desfase +60d | 0.42 / 0.54 | 5/14 | 4 | 64.3% | -7.7% | 8.1% | 15.8% |
