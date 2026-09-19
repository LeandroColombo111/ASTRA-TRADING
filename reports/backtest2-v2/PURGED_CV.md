# Validacion cruzada con purga y embargo (bloque del medio apartado)

Serie Binance 2020-05-01 a 2026-08-31 (unida con los datos nuevos de 2020), 8 bloques contiguos de unos 289 dias. Para cada bloque: se eligen los parametros con todo lo que queda **antes y despues**, dejando un embargo de 120 dias a cada lado (cubre el largo de los trades y la memoria de los indicadores), y se mide en el bloque apartado. Se compara con los parametros de produccion en los mismos bloques. Ojo: entrenar con datos posteriores al bloque no es una prueba hacia adelante; mide si los parametros generalizan a un periodo no visto.


## BTC, grilla: stop_atr x reward

| bloque | parametros elegidos | Sharpe en muestra | Sharpe fuera (elegido) | ganancia fuera (elegido) | Sharpe fuera (produccion) | ganancia fuera (produccion) | HODL |
|---|---|---|---|---|---|---|---|
| 2020-05-01 | {'stop_atr': 3.0, 'reward': 2.0} | 0.50 | 1.36 | 21.9% | 1.09 | 17.3% | 462.8% |
| 2021-02-14 | {'stop_atr': 3.0, 'reward': 2.0} | 0.49 | -0.44 | -5.5% | -0.91 | -9.1% | 17.9% |
| 2021-11-30 | {'stop_atr': 3.0, 'reward': 2.0} | 0.83 | 0.52 | 5.6% | 1.20 | 15.4% | -65.7% |
| 2022-09-15 | {'stop_atr': 3.0, 'reward': 2.0} | 0.71 | 0.15 | 0.8% | 0.14 | 0.8% | 54.8% |
| 2023-07-02 | {'stop_atr': 3.0, 'reward': 2.0} | 0.58 | 1.65 | 20.5% | 1.94 | 32.5% | 105.1% |
| 2024-04-16 | {'stop_atr': 3.0, 'reward': 6.0} | 0.98 | -1.53 | -20.3% | -1.43 | -19.1% | 66.6% |
| 2025-01-30 | {'stop_atr': 3.0, 'reward': 6.0} | 0.84 | 0.10 | 0.4% | 0.64 | 6.7% | -8.4% |
| 2025-11-15 | {'stop_atr': 3.0, 'reward': 6.0} | 0.57 | 1.21 | 16.2% | 1.72 | 24.6% | -18.2% |

Elegidos: Sharpe fuera media 0.38 / mediana 0.33, ganancia compuesta 37.6%. Produccion: 0.55 / 0.86, 76.4%. HODL: 801.1%. corr(Sharpe en muestra, fuera) = -0.63. Produccion fue la elegida en 0 de 8 bloques.

## BTC, grilla: largo del breakout

| bloque | parametros elegidos | Sharpe en muestra | Sharpe fuera (elegido) | ganancia fuera (elegido) | Sharpe fuera (produccion) | ganancia fuera (produccion) | HODL |
|---|---|---|---|---|---|---|---|
| 2020-05-01 | {'breakout': 240} | 0.73 | 0.47 | 6.3% | 1.09 | 17.3% | 462.8% |
| 2021-02-14 | {'breakout': 480} | 0.68 | -0.78 | -9.7% | -0.91 | -9.1% | 17.9% |
| 2021-11-30 | {'breakout': 480} | 0.84 | 1.15 | 15.5% | 1.20 | 15.4% | -65.7% |
| 2022-09-15 | {'breakout': 480} | 0.72 | -0.03 | -1.1% | 0.14 | 0.8% | 54.8% |
| 2023-07-02 | {'breakout': 960} | 0.67 | 1.56 | 25.1% | 1.94 | 32.5% | 105.1% |
| 2024-04-16 | {'breakout': 1200} | 1.13 | -1.42 | -16.1% | -1.43 | -19.1% | 66.6% |
| 2025-01-30 | {'breakout': 480} | 0.81 | 0.53 | 5.8% | 0.64 | 6.7% | -8.4% |
| 2025-11-15 | {'breakout': 480} | 0.65 | 1.85 | 27.3% | 1.72 | 24.6% | -18.2% |

Elegidos: Sharpe fuera media 0.42 / mediana 0.50, ganancia compuesta 54.8%. Produccion: 0.55 / 0.86, 76.4%. HODL: 801.1%. corr(Sharpe en muestra, fuera) = -0.61. Produccion fue la elegida en 0 de 8 bloques.

## ETH, grilla: stop_atr x reward

| bloque | parametros elegidos | Sharpe en muestra | Sharpe fuera (elegido) | ganancia fuera (elegido) | Sharpe fuera (produccion) | ganancia fuera (produccion) | HODL |
|---|---|---|---|---|---|---|---|
| 2020-05-01 | {'stop_atr': 5.0, 'reward': 3.0} | 0.86 | 1.30 | 16.9% | -0.27 | -6.7% | 782.8% |
| 2021-02-14 | {'stop_atr': 5.0, 'reward': 4.0} | 0.76 | 0.99 | 11.5% | -0.05 | -2.5% | 149.6% |
| 2021-11-30 | {'stop_atr': 5.0, 'reward': 3.0} | 0.77 | 1.10 | 10.7% | 0.94 | 11.9% | -67.2% |
| 2022-09-15 | {'stop_atr': 5.0, 'reward': 3.0} | 1.19 | 0.09 | 0.3% | -0.19 | -2.7% | 28.5% |
| 2023-07-02 | {'stop_atr': 5.0, 'reward': 3.0} | 1.01 | 0.77 | 8.5% | 0.69 | 7.1% | 58.6% |
| 2024-04-16 | {'stop_atr': 5.0, 'reward': 4.0} | 1.12 | -0.24 | -2.4% | 0.02 | -0.5% | 4.6% |
| 2025-01-30 | {'stop_atr': 5.0, 'reward': 4.0} | 0.99 | 0.88 | 7.8% | 1.65 | 21.5% | -0.1% |
| 2025-11-15 | {'stop_atr': 5.0, 'reward': 3.0} | 0.91 | 1.21 | 13.4% | 0.52 | 5.8% | -23.1% |

Elegidos: Sharpe fuera media 0.76 / mediana 0.93, ganancia compuesta 87.1%. Produccion: 0.41 / 0.27, 35.6%. HODL: 1083.8%. corr(Sharpe en muestra, fuera) = -0.83. Produccion fue la elegida en 0 de 8 bloques.

## ETH, grilla: largo del breakout

| bloque | parametros elegidos | Sharpe en muestra | Sharpe fuera (elegido) | ganancia fuera (elegido) | Sharpe fuera (produccion) | ganancia fuera (produccion) | HODL |
|---|---|---|---|---|---|---|---|
| 2020-05-01 | {'breakout': 960} | 0.49 | -0.27 | -6.7% | -0.27 | -6.7% | 782.8% |
| 2021-02-14 | {'breakout': 1200} | 0.69 | -0.58 | -10.0% | -0.05 | -2.5% | 149.6% |
| 2021-11-30 | {'breakout': 960} | 0.43 | 0.92 | 11.2% | 0.94 | 11.9% | -67.2% |
| 2022-09-15 | {'breakout': 720} | 0.46 | -0.19 | -2.7% | -0.19 | -2.7% | 28.5% |
| 2023-07-02 | {'breakout': 960} | 0.39 | 0.22 | 1.6% | 0.69 | 7.1% | 58.6% |
| 2024-04-16 | {'breakout': 960} | 0.29 | 0.04 | -0.1% | 0.02 | -0.5% | 4.6% |
| 2025-01-30 | {'breakout': 720} | 0.30 | 1.65 | 21.5% | 1.65 | 21.5% | -0.1% |
| 2025-11-15 | {'breakout': 720} | 0.31 | 0.52 | 5.8% | 0.52 | 5.8% | -23.1% |

Elegidos: Sharpe fuera media 0.29 / mediana 0.13, ganancia compuesta 18.6%. Produccion: 0.41 / 0.27, 35.6%. HODL: 1083.8%. corr(Sharpe en muestra, fuera) = -0.65. Produccion fue la elegida en 3 de 8 bloques.

## Lectura

- **Elegir parametros con datos de ambos lados no predice el rendimiento en el bloque apartado.** La correlacion entre el Sharpe en muestra y el Sharpe
  fuera del bloque es negativa en las cuatro busquedas (-0.61 a -0.83). Mejor Sharpe en muestra no significa mejor resultado afuera.
- **BTC:** los parametros elegidos por la validacion rinden peor que los de produccion en los mismos bloques (Sharpe 0.38 y 0.42 contra 0.55; ganancia
  +37.6% y +54.8% contra +76.4%). Esto es coherente con que los valores de produccion se ajustaron con estos mismos datos: los bloques desde 2022 no
  son independientes de esa eleccion. Los bloques nuevos de 2020-2021 (produccion: Sharpe 1.09, -0.91, 1.20; ganancia +17.3%, -9.1%, +15.4%) muestran
  el mismo perfil defensivo y modesto que la prueba fuera de muestra.
- **ETH:** la busqueda elige de forma estable un stop mas ancho (`stop_atr` 5) y ahi si supera a produccion (Sharpe 0.76 contra 0.41; ganancia
  +87.1% contra +35.6%). Coincide con lo visto en las 14 ventanas (stop 5 / reward 3: Sharpe mediana 1.10). Es una pista para ETH, no una razon para
  cambiar el bot (que opera solo BTC), y sigue siendo una ventaja chica frente al HODL (+1083.8%).
- **Ningun bloque muestra que el bot supere al HODL en ganancia total.** La conclusion de siempre se mantiene: es defensivo, no generador de retorno.
- **Hallazgo de infraestructura:** en la primera corrida una vela de Binance con volumen cero (pausa del exchange, 2024-10-28 20:00) hizo explotar el
  precio de fill del modelo de deslizamiento (dividia por el volumen de la vela) y aparecio un -100% falso. Se agrego un tope al impacto
  (`SlippageModel.max_impact`, 5%). Se re-corrio `ops/backtest2_research.py` completo con el arreglo: las tablas de `tables.md` quedaron **identicas**, es
  decir ningun informe anterior estaba afectado (las 9 velas de volumen cero de OKX del 2022-12-18 no cayeron sobre ninguna operacion).

