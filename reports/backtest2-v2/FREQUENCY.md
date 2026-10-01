# Mas operaciones: hacia donde va el P&L

Dos caminos para subir la frecuencia sin inventar reglas nuevas: (1) acortar la ruptura de entrada de v4_hourly (el parametro que mas controla cuanto opera), (2) operar BTC, ETH y SOL a la vez en vez de solo BTC. Mismas reglas de siempre: parametros fijos (nada se re-optimiza mirando el resultado), warmup 250d, 14 ventanas de 90d, comparacion contra HODL. Aviso de entrada: ya se sabe que acortar la ruptura a 240h mejora SOLO en BTC y empeora en ETH/SOL (reports/backtest2-v2/README.md, seccion C); este barrido muestra el patron completo, no busca un ganador nuevo.

## 1. Barrido del largo de ruptura (trades/año en funcion del parametro)


**BTC**

| ruptura (horas) | trades/año | Sharpe media / mediana | ventanas >=1.5 | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| 720 (produccion) | 21 | 0.52 / 1.00 | 5/14 | 56.5% | -11.3% | 15.8% | 16.6% |
| 120 | 35 | 0.73 / 0.64 | 5/14 | 84.1% | -8.7% | 8.7% | 26.4% |
| 180 | 30 | 1.00 / 1.51 | 7/14 | 104.4% | -4.2% | 5.6% | 23.4% |
| 240 | 27 | 0.80 / 1.38 | 7/14 | 79.7% | -5.3% | 6.1% | 20.9% |
| 320 | 26 | 0.57 / 0.79 | 5/14 | 56.9% | -6.1% | 6.3% | 20.2% |
| 400 | 25 | 0.57 / 0.80 | 4/14 | 54.1% | -5.2% | 8.6% | 19.7% |
| 480 | 24 | 0.68 / 1.09 | 6/14 | 60.8% | -5.3% | 5.7% | 19.5% |
| 600 | 22 | 0.82 / 1.33 | 7/14 | 70.6% | -8.0% | 10.9% | 17.3% |
| 720 **(produccion)** | 21 | 0.52 / 1.00 | 5/14 | 56.5% | -11.3% | 15.8% | 16.6% |
| 840 | 19 | 0.74 / 1.00 | 4/14 | 62.2% | -7.6% | 8.2% | 15.5% |
| 960 | 19 | 0.51 / 0.87 | 3/14 | 43.8% | -7.6% | 11.9% | 15.8% |
| 1200 | 17 | 0.07 / -0.00 | 3/14 | 28.7% | -4.1% | 10.5% | 14.6% |
| 1500 | 15 | 0.02 / -0.10 | 4/14 | 27.4% | -5.4% | 10.7% | 11.9% |
| HODL | - | 0.79 / 0.61 | 6/14 | 191.6% | -27.1% | - | 100% |

**ETH**

| ruptura (horas) | trades/año | Sharpe media / mediana | ventanas >=1.5 | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| 720 (produccion) | 18 | -0.14 / 0.34 | 2/14 | 17.4% | -9.4% | 9.4% | 12.2% |
| 120 | 35 | -0.19 / -0.92 | 2/14 | 1.9% | -10.8% | 19.4% | 22.7% |
| 180 | 30 | -0.08 / -0.33 | 3/14 | 4.7% | -11.1% | 18.9% | 18.6% |
| 240 | 28 | -0.48 / -0.49 | 4/14 | -6.6% | -13.5% | 20.4% | 16.4% |
| 320 | 26 | -0.42 / -0.04 | 3/14 | -4.7% | -11.8% | 15.6% | 15.5% |
| 400 | 24 | -0.40 / -0.38 | 3/14 | -0.4% | -9.4% | 13.1% | 14.7% |
| 480 | 22 | -0.08 / 0.08 | 3/14 | 19.6% | -9.4% | 11.8% | 13.1% |
| 600 | 19 | -0.19 / 0.22 | 2/14 | 18.3% | -9.4% | 10.0% | 12.7% |
| 720 **(produccion)** | 18 | -0.14 / 0.34 | 2/14 | 17.4% | -9.4% | 9.4% | 12.2% |
| 840 | 18 | -0.05 / 0.44 | 2/14 | 14.6% | -9.4% | 9.7% | 11.4% |
| 960 | 17 | -0.01 / 0.44 | 2/14 | 16.9% | -9.4% | 9.7% | 11.4% |
| 1200 | 17 | -0.18 / 0.44 | 2/14 | 11.6% | -7.7% | 10.8% | 10.9% |
| 1500 | 15 | -0.10 / 0.55 | 2/14 | 19.6% | -7.7% | 9.7% | 10.1% |
| HODL | - | 0.27 / -0.53 | 6/14 | 5.6% | -50.1% | - | 100% |

**SOL**

| ruptura (horas) | trades/año | Sharpe media / mediana | ventanas >=1.5 | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| 720 (produccion) | 21 | -0.07 / 0.02 | 2/14 | 16.7% | -8.7% | 18.2% | 13.4% |
| 120 | 37 | -0.11 / -0.35 | 4/14 | 5.7% | -14.0% | 25.7% | 24.9% |
| 180 | 32 | -0.04 / -0.29 | 4/14 | 13.1% | -13.9% | 20.1% | 22.0% |
| 240 | 29 | -0.14 / -0.33 | 3/14 | 4.2% | -13.0% | 23.5% | 19.0% |
| 320 | 26 | 0.06 / 0.28 | 3/14 | 17.5% | -9.3% | 18.6% | 16.3% |
| 400 | 25 | -0.14 / 0.22 | 2/14 | 9.6% | -9.3% | 20.5% | 16.2% |
| 480 | 24 | -0.06 / -0.26 | 2/14 | 16.6% | -7.4% | 15.6% | 15.6% |
| 600 | 23 | -0.16 / 0.21 | 3/14 | 12.6% | -15.8% | 24.0% | 14.5% |
| 720 **(produccion)** | 21 | -0.07 / 0.02 | 2/14 | 16.7% | -8.7% | 18.2% | 13.4% |
| 840 | 20 | -0.17 / 0.30 | 3/14 | 12.3% | -7.9% | 21.2% | 12.5% |
| 960 | 19 | -0.00 / 0.30 | 4/14 | 21.9% | -6.0% | 16.2% | 12.0% |
| 1200 | 18 | -0.18 / -0.17 | 4/14 | 18.6% | -9.6% | 16.5% | 11.1% |
| 1500 | 14 | 0.16 / 0.18 | 4/14 | 34.4% | -5.9% | 9.0% | 8.9% |
| HODL | - | 0.68 / 0.71 | 4/14 | 237.9% | -46.2% | - | 100% |

## 2. Cartera BTC + ETH + SOL a la vez (mismo capital total, un tercio por activo)

No se cambia ningun parametro: es el bot original corriendo en los tres activos en simultaneo, cada uno con un tercio del capital. Sube la frecuencia de trades porque hay tres fuentes de senales independientes, no porque se opere distinto.

| variante | trades totales (14 ventanas) | Sharpe media / mediana | ganancia total | peor ventana | DD peor ventana |
|---|---|---|---|---|---|
| Cartera BTC+ETH+SOL (1/3 cada uno) | 278 | 0.52 / 0.45 | 32.0% | -4.9% | 7.8% |
| Solo BTC (produccion) | 95 | 0.52 / 1.00 | 56.5% | -11.3% | 12.7% |
| HODL BTC (mismo capital) | - | 0.79 / 0.61 | 191.6% | -27.1% | 35.6% |

## Lectura

- **Hay un punto donde mas operaciones SI mejoran el resultado en BTC, pero es un pico aislado, no una tendencia.**
  Bajar la ruptura de 720h a 180h sube los trades/año de 21 a 30 y el resultado en BTC mejora con claridad (Sharpe
  mediana 1.51 vs 1.00, ganancia 104.4% vs 56.5%, caida encadenada 5.6% vs 15.8%). Pero 120h (mas operaciones todavia)
  es PEOR que 180h (84.1% de ganancia), y subir a 1200-1500h destruye el resultado. No es "mas operaciones = mejor
  P&L" de forma monotona: hay un maximo local en algun punto entre 120h y 720h, y ese tipo de pico aislado es
  exactamente la firma de sobreajuste que el proyecto viene encontrando en cada parametro (ver README.md seccion D).
- **Falla la prueba cruzada.** En ETH, achicar la ruptura empeora casi siempre (240h da -6.6% contra 17.4% del
  original); en SOL el patron es ruidoso y sin tendencia clara. El "mejor" punto de BTC (180h) da en ETH apenas 4.7%
  (peor que el original) y en SOL 13.1% (tambien peor). Es la misma historia que la ruptura de 240h ya descartada:
  funciona en BTC porque ahi se eligio mirando BTC, no porque acortar la ruptura sea una ventaja real.
- **La cartera BTC+ETH+SOL sube la cantidad de operaciones (95 a 278 en las mismas 14 ventanas) pero NO sube el
  resultado.** Gana menos en total (32.0% contra 56.5% de BTC solo) porque reparte capital en ETH y SOL, que ya
  sabiamos que casi no tienen ventaja. Lo que si logra es bajar el riesgo: la peor ventana pasa de -11.3% a -4.9% y
  el drawdown de 12.7% a 7.8%. Es diversificacion, no una ventaja nueva: reduce varianza, no aumenta el retorno
  esperado.
- **Respuesta directa a "hacia donde va el P&L":** no hacia arriba de forma confiable. Mas operaciones en BTC solo
  (via ruptura mas corta) puede mejorar o empeorar segun el punto exacto elegido, sin un patron fiable entre activos.
  Mas operaciones via diversificacion (cartera de 3 activos) baja el riesgo pero tambien el retorno total, porque
  reparte capital en activos sin ventaja propia.
- **Conclusion: no adoptar ningun punto de la grilla.** Ninguno pasa la regla de sostenerse en BTC, ETH y SOL a la
  vez. La produccion (720h) sigue siendo una eleccion razonable: no es la mejor en ningun activo individualmente,
  pero tampoco es un extremo fragil como el 180h de BTC o el 1500h que arruina todo.

