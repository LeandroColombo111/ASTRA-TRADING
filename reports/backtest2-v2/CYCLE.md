# Ciclos de Bitcoin (halving): filtro de entradas

Halvings usados: 2016-07-09 (solo para la fase inicial de 2020), 2020-05-11 y 2024-04-20; fechas publicas y conocidas de antemano, sin mirar el futuro. **Aviso:** la ventana a evitar (6 a 18 meses despues del halving) se eligio despues de ver que los malos periodos del bot (2021 y 2024-25) caen ahi, asi que en los dos ciclos disponibles el resultado es favorable por construccion. Lo que informa de verdad es ETH y, si se consiguen, ciclos anteriores.

Ventanas de 90 dias desde 2020-05-01 (121 dias de calentamiento), serie Binance 2020-2026.


## BTC (25 ventanas)

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| original | 0.36 / 0.38 | 6/25 | 11 | 73.5% | -11.2% | 21.3% | 15.0% |
| C1 evitar meses 6 a 18 | 0.27 / 0.00 | 6/25 | 8 | 60.3% | -11.2% | 14.8% | 10.0% |
| C1 vecino: evitar meses 3 a 15 | 0.25 / 0.00 | 5/25 | 8 | 63.5% | -7.0% | 8.9% | 10.5% |
| C1 vecino: evitar meses 9 a 21 | 0.20 / 0.00 | 5/25 | 8 | 67.1% | -11.2% | 19.4% | 10.9% |
| Contraste: operar SOLO meses 6 a 18 | -0.04 / 0.00 | 1/25 | 6 | 6.9% | -4.7% | 14.3% | 5.1% |
| HODL | 0.77 / 0.75 | 10/25 | - | 539.4% | -43.7% | - | 100% |

## ETH (25 ventanas)

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| original | 0.07 / 0.47 | 4/25 | 11 | 22.4% | -9.6% | 13.7% | 14.6% |
| C1 evitar meses 6 a 18 | 0.01 / 0.00 | 3/25 | 7 | 12.9% | -9.6% | 13.1% | 8.5% |
| C1 vecino: evitar meses 3 a 15 | -0.04 / 0.00 | 3/25 | 7 | 9.8% | -9.6% | 13.6% | 9.1% |
| C1 vecino: evitar meses 9 a 21 | -0.01 / 0.00 | 3/25 | 9 | 11.1% | -9.6% | 13.1% | 8.8% |
| Contraste: operar SOLO meses 6 a 18 | 0.04 / 0.00 | 1/25 | 5 | 6.3% | -7.1% | 14.5% | 6.1% |
| HODL | 0.69 / 0.49 | 11/25 | - | 570.8% | -50.2% | - | 100% |

## Lectura

- **No mejora al bot, ni siquiera en los datos donde estaba favorecida.** En BTC (25 ventanas) evitar los meses 6 a 18 post-halving baja el Sharpe medio de 0.36 a 0.27
  y la ganancia total de 73.5% a 60.3%; los vecinos dan 63.5% y 67.1%, tambien menos que el original. Lo unico que mejora es el riesgo: la caida encadenada baja de 21.3% a
  14.8% y las ventanas negativas de 11 a 8. La mediana de Sharpe cae a 0.00 porque, al operar menos, muchas ventanas quedan sin trades.
- **En ETH empeora en todo** (ganancia 22.4% contra 12.9%; los vecinos 9.8% y 11.1%), asi que tampoco pasa la validacion cruzada. El contraste (operar solo en esa fase) es peor todavia
  (BTC +6.9%).
- **Por que:** la fase evitada ocupa cerca de 40% del tiempo y tambien contiene trades buenos (por ejemplo la alza de 2020-21, donde el bot gano). Evitarla se lleva ganancias junto con
  las perdidas, y el bot ya se adapta a la fase de forma indirecta con su filtro de tendencia.
- **Conclusion: no adoptar.** Como falla incluso donde estaba favorecida por construccion, no hace falta bajar ciclos anteriores (2017-2019) para una prueba fuera de muestra:
  no hay nada que confirmar. Suma 4 variantes al acumulado (unas 67 sobre BTC). `configs/selected.json` sin cambios.

