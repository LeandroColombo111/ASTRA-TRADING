# Prueba con 2017-2019 (spot de Binance): configuracion congelada

Binance spot BTCUSDT, 2017-08-17 a 2019-12-31 (el contrato perpetuo no existia antes de septiembre de 2019, asi que se usa spot; sin funding). Ningun parametro se cambia. 120 dias de calentamiento y ventanas de 90 dias, como en OUT_OF_SAMPLE_2020_2021.md. **Aproximaciones:** (1) 139 velas horarias faltan en 13 pausas reales de Binance (la mas larga, 75 h) y se rellenan con velas planas (precio anterior, volumen cero); no se inventa ningun movimiento. (2) 43 velas reales de febrero de 2018 tienen la grilla corrida 28 minutos tras una pausa de Binance; se descartan (etiquetarlas por hora usaria informacion hasta 28 minutos antes) y ese tramo cuenta como hueco.

## Por ventanas

| ventanas | Sharpe media / mediana | ganancia total | peor ventana | DD encadenado | % en mercado | HODL total | HODL peor ventana |
|---|---|---|---|---|---|---|---|
| 8 | 0.44 / 0.59 | 36.6% | -8.1% | 8.1% | 11.1% | -58.5% | -54.2% |

| inicio | Sharpe | ganancia | HODL | trades |
|---|---|---|---|---|
| 2017-12-15 | 0.98 | 3.3% | -54.2% | 4 |
| 2018-03-15 | 0.20 | 0.5% | -17.1% | 7 |
| 2018-06-13 | -1.07 | -4.2% | -3.5% | 6 |
| 2018-09-11 | 4.26 | 22.6% | -43.8% | 7 |
| 2018-12-10 | -3.28 | -5.7% | 10.7% | 3 |
| 2019-03-10 | 1.90 | 13.9% | 102.2% | 13 |
| 2019-06-08 | 2.65 | 13.6% | 33.6% | 7 |
| 2019-09-06 | -2.14 | -8.1% | -32.4% | 5 |

## Corrida continua

| periodo | anios | ganancia total | **por anio (compuesto)** | Sharpe | DD max | trades | trades/anio | trades que tocan un hueco | HODL total | HODL por anio |
|---|---|---|---|---|---|---|---|---|---|---|
| 2017-12-15 a 2019-12-31 | 2.04 | 38.2% | **17.2%** | 0.96 | 12.3% | 49 | 24 | 2 | -58.2% | -34.7% |

Limites: spot en vez de perpetuo (sin funding porque el perpetuo no existia), 13 huecos rellenados con velas planas, y un solo activo en un solo ciclo. Sirve para ver si el bot se rompe en un mercado bajista largo, no para estimar un Sharpe con precision.

Confianza estadistica: PSR (probabilidad de que el Sharpe real sea > 0, sin descuento por pruebas multiples) = 0.93 con 49 operaciones. Con tan pocas operaciones y una sola serie, es una pista y no una prueba.
