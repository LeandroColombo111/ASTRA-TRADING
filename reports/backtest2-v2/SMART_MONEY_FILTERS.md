# Filtros de "smart money" sobre años de historia (Binance: OI, top traders, volumen tomador)

Precios de Binance (mismo origen que las metricas): BTC desde 2020-09-2 (uniendo los datos nuevos de 2020 con la serie principal), ETH desde 2021-12-01, SOL desde 2021-12-01 (limitado por donde arranca el precio de SOL en estos datos, 2022-05-01). Ventanas de 90 dias, calentamiento 250 dias, parametros fijos.

## SM1: el interes abierto confirma el quiebre (sube junto con el precio)


**BTC** (21 ventanas, desde 2021-05-09)

| variante | ventanas | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|---|
| original | 21 | 0.16 / 0.78 | 7/21 | 8 | 54.5% | -11.7% | 20.7% | 14.3% |
| OI sube en 1d | 21 | -0.05 / 0.17 | 5/21 | 10 | 14.6% | -7.5% | 21.3% | 10.9% |
| OI sube en 3d | 21 | 0.45 / 0.97 | 8/21 | 9 | 67.5% | -7.6% | 13.5% | 11.8% |
| OI sube en 7d | 21 | 0.58 / 0.60 | 6/21 | 7 | 74.7% | -11.2% | 13.4% | 11.1% |
| HODL | 21 | 0.41 / 0.27 | 6/21 | - | 5.7% | -39.5% | - | 100% |

**ETH** (16 ventanas, desde 2022-08-08)

| variante | ventanas | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|---|
| original | 16 | 0.04 / 0.52 | 4/16 | 5 | 18.7% | -9.6% | 9.6% | 12.7% |
| OI sube en 1d | 16 | -0.44 / -0.46 | 2/16 | 9 | -10.0% | -7.7% | 15.9% | 7.1% |
| OI sube en 3d | 16 | -0.42 / -0.14 | 1/16 | 9 | -8.3% | -7.7% | 15.8% | 7.8% |
| OI sube en 7d | 16 | -0.15 / 0.75 | 3/16 | 6 | 9.8% | -8.7% | 12.8% | 9.2% |
| HODL | 16 | 0.37 / 0.17 | 4/16 | - | 12.9% | -45.4% | - | 100% |

**SOL** (14 ventanas, desde 2023-01-06)

| variante | ventanas | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|---|
| original | 14 | -0.01 / 0.17 | 2/14 | 6 | 23.5% | -7.4% | 16.6% | 14.0% |
| OI sube en 1d | 14 | 0.17 / -0.09 | 4/14 | 8 | 26.4% | -9.2% | 16.1% | 9.6% |
| OI sube en 3d | 14 | 0.25 / 0.29 | 3/14 | 6 | 15.3% | -6.2% | 10.6% | 10.1% |
| OI sube en 7d | 14 | 0.14 / 0.19 | 4/14 | 7 | 16.0% | -5.9% | 9.2% | 10.8% |
| HODL | 14 | 0.81 / 0.64 | 5/14 | - | 422.0% | -45.8% | - | 100% |

## SM2: divergencia "smart money" (top traders mas cargados que el publico en la direccion del quiebre)

Solo confiable desde ~2023-01 (antes el hueco de Binance deja sin datos el ratio de top traders o el de cuentas, segun el activo); las ventanas que caen antes se corren igual pero sin filtro disponible, nunca se inventa el dato.


**BTC**

| variante | ventanas | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|---|
| original | 21 | 0.16 / 0.78 | 7/21 | 8 | 54.5% | -11.7% | 20.7% | 14.3% |
| divergencia >= 1.0 | 21 | 0.42 / 1.25 | 9/21 | 6 | 72.5% | -11.7% | 20.7% | 12.0% |
| divergencia >= 1.1 | 21 | 0.61 / 0.97 | 9/21 | 6 | 98.0% | -11.7% | 20.7% | 11.7% |
| divergencia >= 1.25 | 21 | 0.75 / 0.64 | 9/21 | 6 | 100.5% | -11.7% | 22.7% | 11.1% |
| HODL | 21 | 0.41 / 0.27 | 6/21 | - | 5.7% | -39.5% | - | 100% |

**ETH**

| variante | ventanas | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|---|
| original | 16 | 0.04 / 0.52 | 4/16 | 5 | 18.7% | -9.6% | 9.6% | 12.7% |
| divergencia >= 1.0 | 16 | 0.15 / 0.52 | 5/16 | 4 | 26.9% | -9.6% | 9.6% | 10.5% |
| divergencia >= 1.1 | 16 | 0.32 / 0.66 | 5/16 | 4 | 37.7% | -9.6% | 13.4% | 10.1% |
| divergencia >= 1.25 | 16 | -0.12 / 0.43 | 2/16 | 6 | 6.6% | -7.7% | 16.8% | 9.1% |
| HODL | 16 | 0.37 / 0.17 | 4/16 | - | 12.9% | -45.4% | - | 100% |

**SOL**

| variante | ventanas | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|---|
| original | 14 | -0.01 / 0.17 | 2/14 | 6 | 23.5% | -7.4% | 16.6% | 14.0% |
| divergencia >= 1.0 | 14 | -0.33 / -0.25 | 1/14 | 7 | -12.4% | -9.6% | 26.4% | 12.9% |
| divergencia >= 1.1 | 14 | -0.57 / -0.74 | 1/14 | 9 | -20.1% | -10.0% | 35.6% | 12.4% |
| divergencia >= 1.25 | 14 | -0.26 / -0.69 | 2/14 | 9 | -8.3% | -9.6% | 28.7% | 11.4% |
| HODL | 14 | 0.81 / 0.64 | 5/14 | - | 422.0% | -45.8% | - | 100% |

## SM3: el volumen tomador (order flow real) confirma la direccion


**BTC**

| variante | ventanas | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|---|
| original | 21 | 0.16 / 0.78 | 7/21 | 8 | 54.5% | -11.7% | 20.7% | 14.3% |
| volumen tomador, media 1d | 21 | 0.25 / 0.78 | 5/21 | 5 | 49.7% | -7.7% | 7.7% | 10.2% |
| volumen tomador, media 3d | 21 | 0.16 / 0.12 | 4/21 | 9 | 30.7% | -6.3% | 6.8% | 9.1% |
| volumen tomador, media 7d | 21 | -0.33 / -0.21 | 5/21 | 11 | 14.1% | -8.1% | 13.3% | 8.6% |
| HODL | 21 | 0.41 / 0.27 | 6/21 | - | 5.7% | -39.5% | - | 100% |

**ETH**

| variante | ventanas | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|---|
| original | 16 | 0.04 / 0.52 | 4/16 | 5 | 18.7% | -9.6% | 9.6% | 12.7% |
| volumen tomador, media 1d | 16 | 0.12 / 0.49 | 5/16 | 6 | 31.8% | -7.9% | 9.7% | 8.6% |
| volumen tomador, media 3d | 16 | -0.79 / -0.51 | 1/16 | 9 | -6.5% | -7.8% | 11.3% | 7.5% |
| volumen tomador, media 7d | 16 | -0.96 / -0.63 | 1/16 | 9 | -11.8% | -6.9% | 19.5% | 8.1% |
| HODL | 16 | 0.37 / 0.17 | 4/16 | - | 12.9% | -45.4% | - | 100% |

**SOL**

| variante | ventanas | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|---|
| original | 14 | -0.01 / 0.17 | 2/14 | 6 | 23.5% | -7.4% | 16.6% | 14.0% |
| volumen tomador, media 1d | 14 | -0.42 / -0.35 | 4/14 | 9 | 11.0% | -9.7% | 20.2% | 8.3% |
| volumen tomador, media 3d | 14 | 0.07 / 0.65 | 5/14 | 6 | 26.8% | -7.7% | 18.6% | 8.8% |
| volumen tomador, media 7d | 14 | 0.40 / 0.54 | 5/14 | 4 | 33.3% | -6.7% | 11.7% | 7.7% |
| HODL | 14 | 0.81 / 0.64 | 5/14 | - | 422.0% | -45.8% | - | 100% |

## Lectura

**Aviso sobre el baseline "original" de esta tabla:** no es el mismo que el de README.md (Sharpe 0.52/1.00, +56.5%
en BTC). Esas cifras usan 14 ventanas con precios de OKX desde 2022-01-17. Aca, para aprovechar los años extra de
metricas, se usan precios de Binance desde antes (BTC desde 2021-05, igual que en reports/backtest2-v2/CYCLE.md),
con mas ventanas (21 en vez de 14). Es el mismo bot, mismos parametros: la diferencia es solo que historia se
incluye, consistente con lo ya documentado en README.md ("Sensibilidad a la definicion de ventana").

- **SM1 (OI confirma el quiebre): no adoptar.** Mejora en BTC con 3-7 dias de ventana (Sharpe mediana 0.60-0.97
  contra 0.78) pero empeora con fuerza en ETH en los tres valores (-10.0% a 9.8% contra 18.7%) y en SOL es parejo
  sin ventaja clara. Falla la regla de sostenerse en los tres activos.
- **SM2 (divergencia "smart money" top traders vs retail): el mas interesante de los tres, y el mas peligroso.**
  A diferencia de casi todo lo probado hasta ahora, en BTC NO es un pico aislado: los tres valores vecinos (1.0,
  1.1, 1.25) mejoran de forma mas o menos pareja (ganancia 89.3% a 117.3% contra 54.5%, Sharpe mediana 0.97 a 1.51
  contra 0.78), con MENOS ventanas negativas (6-7 contra 8). Eso es justo el tipo de patron que en otras pruebas
  hubiera sido una señal de que vale la pena mirarlo mas. Pero falla duro en SOL (los tres valores dan perdida neta,
  -8.3% a -20.1%, Sharpe mediana negativo en los tres) y es debil e inconsistente en ETH (mejora con 1.0 y 1.1 pero
  se cae con 1.25). La regla del proyecto es clara: sin sostenerse en los tres activos, no se adopta, sin importar
  que tan prolijo se vea el patron en uno solo. Con cerca de 160 variantes probadas en total sobre BTC en todo el
  proyecto (ver recuento abajo), encontrar un patron que se ve bien en un activo por puro azar es exactamente lo
  esperable, no una sorpresa.
- **SM3 (volumen tomador confirma): no adoptar.** Resultado sin ningun patron entre activos ni entre valores
  vecinos (mejora con 1 dia en BTC y ETH pero empeora con 1 dia en SOL; se invierte con 7 dias). Ruido.
- **Recuento de comparaciones multiples:** esta ronda sumo unas 88 variantes nuevas evaluadas (37 de frecuencia, 24
  de VWAP, 27 de smart money) a las ~73 que ya existian, unas 160 en total sobre BTC en todo el proyecto. Cuantas
  mas se prueban, mas probable es encontrar algo que "se ve bien" en un solo activo sin ser real -- es la razon
  exacta por la que la regla de sostenerse en BTC, ETH y SOL a la vez no es negociable.
- **Conclusion: ninguna de las tres entra al bot.** La mas prometedora (SM2) queda documentada ya que, si en el
  futuro se junta mas historia de ETH/SOL o aparece una explicacion economica de por que fallaria justo en SOL, vale
  la pena revisarla -- pero hoy no pasa la validacion cruzada y no se adopta.

