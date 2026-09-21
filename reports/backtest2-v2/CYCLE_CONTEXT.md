# Ciclo del halving como contexto (no como interruptor)

El bot sigue tomando todas sus senales; entre los 6 y 18 meses despues de cada halving (2020-05-11 y 2024-04-20) actua con mas cautela. **R1** opera con una fraccion del tamano normal. **R2** aleja los stops y objetivos (el tamano baja solo, porque se dimensiona por riesgo). Valores fijados antes de correr, con vecinos. **Aviso:** la ventana se eligio mirando los malos periodos del bot, asi que en los dos ciclos disponibles el resultado esta favorecido por construccion; ETH es la verificacion informativa.


## BTC (25 ventanas de 90d, calentamiento 120d)

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| original | 0.36 / 0.38 | 6/25 | 11 | 73.5% | -11.2% | 21.3% | 15.0% |
| R1 tamano x0.33 | 0.31 / 0.38 | 5/25 | 11 | 66.0% | -11.2% | 16.7% | 15.0% |
| R1 tamano x0.5 | 0.33 / 0.38 | 6/25 | 11 | 67.9% | -11.2% | 17.9% | 15.0% |
| R1 tamano x0.75 | 0.35 / 0.38 | 6/25 | 11 | 71.5% | -11.2% | 19.5% | 15.0% |
| R2 stops y objetivos x1.25 | 0.45 / 0.38 | 6/25 | 10 | 100.6% | -11.2% | 12.6% | 16.4% |
| R2 stops y objetivos x1.5 | 0.29 / 0.23 | 6/25 | 12 | 55.9% | -11.2% | 19.6% | 17.6% |
| R2 stops y objetivos x2.0 | 0.27 / 0.38 | 5/25 | 10 | 60.1% | -11.2% | 22.0% | 19.0% |
| HODL | 0.77 / 0.75 | 10/25 | - | 539.4% | -43.7% | - | 100% |

## ETH (25 ventanas de 90d, calentamiento 120d)

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| original | 0.07 / 0.47 | 4/25 | 11 | 22.4% | -9.6% | 13.7% | 14.6% |
| R1 tamano x0.33 | 0.13 / 0.47 | 4/25 | 10 | 18.4% | -9.6% | 13.1% | 14.6% |
| R1 tamano x0.5 | 0.11 / 0.47 | 4/25 | 11 | 19.7% | -9.6% | 13.1% | 14.6% |
| R1 tamano x0.75 | 0.08 / 0.47 | 4/25 | 11 | 21.3% | -9.6% | 13.1% | 14.6% |
| R2 stops y objetivos x1.25 | 0.09 / 0.47 | 5/25 | 11 | 26.2% | -9.6% | 13.1% | 15.7% |
| R2 stops y objetivos x1.5 | 0.22 / 0.47 | 6/25 | 10 | 35.3% | -9.6% | 13.1% | 16.6% |
| R2 stops y objetivos x2.0 | 0.32 / 0.71 | 5/25 | 9 | 47.0% | -9.6% | 13.1% | 19.9% |
| HODL | 0.69 / 0.49 | 11/25 | - | 570.8% | -50.2% | - | 100% |

## Lectura

- **R1 (menos tamano en la fase): no mejora, solo escala el riesgo.** Achicar el tamano en los meses 6 a 18 baja la ganancia y la caida en proporcion, sin mejorar el Sharpe (BTC: 0.31 a 0.35
  contra 0.36; ganancia 66.0% a 71.5% contra 73.5%; caida encadenada 16.7% a 19.5% contra 21.3%). En ETH el efecto casi no existe. Es el mismo intercambio de siempre: menos riesgo por menos retorno.
- **R2 (mas margen en la fase): resultado inconsistente entre activos.** En BTC solo el valor 1.25 mejora con claridad (ganancia 100.6% contra 73.5%, Sharpe 0.45, caida 12.6%), pero sus vecinos empeoran:
  1.5 da 55.9% y 2.0 da 60.1%, ambos por debajo del original. Es un pico aislado. En ETH mejora de forma monotona (26.2%, 35.3%, 47.0% contra 22.4%), lo que coincide con lo visto antes: en ETH los stops
  anchos rinden mejor, y eso parece una propiedad del activo mas que del ciclo. Falla la regla de validacion cruzada.
- **Conclusion: no adoptar ninguna.** Darle el ciclo como contexto en vez de interruptor da un resultado menos malo que el interruptor, pero no supera al bot original de forma robusta. Suma 6 variantes (unas
  73 sobre BTC). Se corrigio en el camino un defecto de la primera version de R1 (fijaba exposicion absoluta en vez de una fraccion del tamano normal). `configs/selected.json` sin cambios.

