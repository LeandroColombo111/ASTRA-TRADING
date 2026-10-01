# VWAP (precio ponderado por volumen) como filtro de entradas

VWAP calculado sobre las barras horarias (precio tipico x volumen, ventana movil de 7 dias = 168h, con vecinos 72h y 336h). Hipotesis fijadas antes de correr:

- **V1 confirmar el quiebre:** solo entrar si el precio ya esta `dev_min` o mas alejado del VWAP en la direccion del quiebre (el movimiento tiene conviccion ponderada por volumen, no es solo precio). dev_min = 1%, 2%, 3%.
- **V2 bloquear si esta muy extendido:** no entrar si el precio esta a mas de `dev_max` del VWAP (perseguir algo que ya se alejo mucho del promedio con volumen). dev_max = 5%, 8%, 12%.


**BTC**

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| original | 0.52 / 1.00 | 5/14 | 4 | 56.5% | -11.3% | 15.8% | 16.6% |
| V1 confirmar, dev>=1%, VWAP 168h | 0.52 / 1.00 | 5/14 | 4 | 56.5% | -11.3% | 15.8% | 16.6% |
| V1 confirmar, dev>=2%, VWAP 168h | 0.56 / 1.00 | 5/14 | 4 | 59.0% | -11.3% | 15.8% | 16.5% |
| V1 confirmar, dev>=3%, VWAP 168h | 0.48 / 1.06 | 4/14 | 4 | 53.0% | -11.3% | 15.8% | 16.6% |
| V1 confirmar, VWAP 72h, dev>=2% | 0.52 / 1.00 | 4/14 | 3 | 56.4% | -11.3% | 14.0% | 16.3% |
| V1 confirmar, VWAP 336h, dev>=2% | 0.52 / 1.00 | 5/14 | 4 | 56.5% | -11.3% | 15.8% | 16.6% |
| V2 bloquear si dev>5%, VWAP 168h | 0.34 / 1.22 | 6/14 | 5 | 20.7% | -5.7% | 9.0% | 4.8% |
| V2 bloquear si dev>8%, VWAP 168h | 0.50 / 1.25 | 6/14 | 3 | 44.4% | -9.5% | 11.4% | 11.2% |
| V2 bloquear si dev>12%, VWAP 168h | 0.52 / 0.74 | 5/14 | 4 | 59.1% | -9.5% | 12.3% | 16.3% |
| HODL | 0.79 / 0.61 | 6/14 | - | 191.6% | -27.1% | - | 100% |

**ETH**

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| original | -0.14 / 0.34 | 2/14 | 5 | 17.4% | -9.4% | 9.4% | 12.2% |
| V1 confirmar, dev>=1%, VWAP 168h | -0.14 / 0.34 | 2/14 | 5 | 17.4% | -9.4% | 9.4% | 12.2% |
| V1 confirmar, dev>=2%, VWAP 168h | -0.14 / 0.34 | 2/14 | 5 | 17.4% | -9.4% | 9.4% | 12.2% |
| V1 confirmar, dev>=3%, VWAP 168h | -0.10 / 0.47 | 2/14 | 5 | 19.9% | -9.4% | 9.4% | 12.1% |
| V1 confirmar, VWAP 72h, dev>=2% | -0.10 / 0.47 | 2/14 | 5 | 19.9% | -9.4% | 9.4% | 12.1% |
| V1 confirmar, VWAP 336h, dev>=2% | -0.14 / 0.34 | 2/14 | 5 | 17.4% | -9.4% | 9.4% | 12.2% |
| V2 bloquear si dev>5%, VWAP 168h | 0.20 / 0.00 | 3/14 | 3 | 17.1% | -2.1% | 4.1% | 1.6% |
| V2 bloquear si dev>8%, VWAP 168h | -0.21 / 0.56 | 2/14 | 5 | 11.6% | -9.4% | 9.4% | 6.0% |
| V2 bloquear si dev>12%, VWAP 168h | -0.22 / 0.47 | 3/14 | 5 | 6.0% | -9.4% | 9.4% | 9.3% |
| HODL | 0.27 / -0.53 | 6/14 | - | 5.6% | -50.1% | - | 100% |

**SOL**

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| original | -0.07 / 0.02 | 2/14 | 7 | 16.7% | -8.7% | 18.2% | 13.4% |
| V1 confirmar, dev>=1%, VWAP 168h | -0.07 / 0.02 | 2/14 | 7 | 16.7% | -8.7% | 18.2% | 13.4% |
| V1 confirmar, dev>=2%, VWAP 168h | -0.07 / 0.02 | 2/14 | 7 | 16.7% | -8.7% | 18.2% | 13.4% |
| V1 confirmar, dev>=3%, VWAP 168h | -0.07 / 0.02 | 2/14 | 7 | 16.7% | -8.7% | 18.2% | 13.4% |
| V1 confirmar, VWAP 72h, dev>=2% | -0.07 / 0.02 | 2/14 | 7 | 16.7% | -8.7% | 18.2% | 13.4% |
| V1 confirmar, VWAP 336h, dev>=2% | -0.07 / 0.02 | 2/14 | 7 | 16.7% | -8.7% | 18.2% | 13.4% |
| V2 bloquear si dev>5%, VWAP 168h | -0.26 / 0.00 | 1/14 | 2 | 1.5% | -2.0% | 4.0% | 0.2% |
| V2 bloquear si dev>8%, VWAP 168h | -0.18 / -0.37 | 4/14 | 7 | 4.3% | -5.8% | 12.4% | 3.9% |
| V2 bloquear si dev>12%, VWAP 168h | 0.50 / 0.71 | 4/14 | 6 | 44.4% | -4.9% | 8.7% | 9.3% |
| HODL | 0.68 / 0.71 | 4/14 | - | 237.9% | -46.2% | - | 100% |

## Lectura

- **V1 (confirmar el quiebre con VWAP) casi no cambia nada.** En BTC y SOL los resultados son identicos o casi
  identicos al original en la mayoria de los valores: un quiebre de 720h ya implica que el precio se movio bastante
  respecto de cualquier promedio reciente, asi que exigir ademas una distancia al VWAP es casi siempre redundante con
  la condicion que ya existe. No aporta informacion nueva.
- **V2 (bloquear si esta muy extendido) es ruidoso, no una ventaja.** Baja mucho el tiempo en mercado (hasta 0.2% en
  SOL con el umbral mas estricto) y los resultados saltan sin patron entre activos y entre umbrales vecinos: en SOL
  el 5% da -0.26 de Sharpe y el 12% da +0.50 con el mismo mecanismo, solo cambiando el numero. Eso es la firma de
  ruido estadistico sobre pocos trades, no de una señal real.
- **Conclusion: no adoptar.** Ninguna de las dos hipotesis mejora al original de forma consistente en los tres
  activos. El VWAP con los datos horarios que tenemos no aporta algo que el quiebre y la tendencia no esten
  capturando ya.

