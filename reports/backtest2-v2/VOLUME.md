# Volumen como confirmacion de entradas

Datos: solo la columna `volume` horaria de OKX (contratos por vela). No hay separacion entre compras y ventas agresivas, asi que el "volumen acumulado" se aproxima con OBV (volumen acumulado con el signo de cada vela), que es un proxy tosco del order flow.

## 1. Diagnostico: resultado de los trades del bot segun el volumen al entrar (corrida continua; terciles)

Volumen relativo = promedio de 24h / promedio de 30 dias. Pocos trades por grupo.

| activo | volumen al entrar | trades | ganancia media por trade | % ganadores |
|---|---|---|---|---|
| BTC | bajo | 35 | 0.1% | 34% |
| BTC | medio | 34 | 0.3% | 35% |
| BTC | alto | 35 | 1.0% | 49% |
| ETH | bajo | 31 | 0.9% | 42% |
| ETH | medio | 30 | -0.7% | 23% |
| ETH | alto | 30 | 0.5% | 47% |
| SOL | bajo | 33 | 0.6% | 33% |
| SOL | medio | 32 | 0.3% | 31% |
| SOL | alto | 33 | -0.5% | 33% |

## 2. Filtros de entrada (14 ventanas de 90d, warmup 250d, valores fijos y vecinos)

Hipotesis fijadas antes de correr:

- **V1 quiebre confirmado por volumen:** entrar solo si el volumen de 24h supera su promedio de 30 dias por un factor k (k=1.0, vecinos 0.8 y 1.2). Los quiebres con participacion tienen mas continuidad (Karpoff 1987; Gervais et al. 2001). Contraste: volumen bajo (<= 1.0).
- **V2 volumen acumulado (OBV):** largos solo con OBV sobre su media, cortos solo con OBV bajo su media (acumulacion / distribucion); media de 30 dias, vecinos 20 y 60.


**BTC**

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| original | 0.52 / 1.00 | 5/14 | 4 | 56.5% | -11.3% | 15.8% | 16.6% |
| V1 volumen >= 0.8x | 0.58 / 1.11 | 5/14 | 3 | 55.6% | -7.8% | 10.7% | 16.2% |
| V1 volumen >= 1.0x | 0.48 / 0.42 | 4/14 | 3 | 44.3% | -7.8% | 8.8% | 16.2% |
| V1 volumen >= 1.2x | 0.62 / 0.63 | 5/14 | 5 | 41.0% | -5.9% | 10.7% | 13.8% |
| V1 contraste: volumen <= 1.0x | -0.06 / 0.04 | 3/14 | 5 | 13.5% | -3.8% | 6.3% | 2.3% |
| V2 OBV vs media 20d | 0.60 / 1.00 | 5/14 | 4 | 62.2% | -11.3% | 15.8% | 16.5% |
| V2 OBV vs media 30d | 0.60 / 1.00 | 5/14 | 4 | 62.2% | -11.3% | 15.8% | 16.5% |
| V2 OBV vs media 60d | 0.60 / 1.00 | 5/14 | 3 | 62.1% | -11.3% | 14.1% | 16.4% |
| HODL | 0.79 / 0.61 | 6/14 | - | 191.6% | -27.1% | - | 100% |

**ETH**

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| original | -0.14 / 0.34 | 2/14 | 5 | 17.4% | -9.4% | 9.4% | 12.2% |
| V1 volumen >= 0.8x | -0.21 / 0.47 | 2/14 | 6 | 13.8% | -9.4% | 12.9% | 12.1% |
| V1 volumen >= 1.0x | -0.04 / 0.45 | 3/14 | 6 | 19.5% | -7.7% | 8.5% | 11.3% |
| V1 volumen >= 1.2x | -0.49 / -0.03 | 2/14 | 7 | -11.6% | -7.8% | 17.1% | 8.9% |
| V1 contraste: volumen <= 1.0x | -0.60 / -0.50 | 3/14 | 7 | -2.0% | -7.8% | 12.9% | 2.6% |
| V2 OBV vs media 20d | -0.11 / 0.34 | 2/14 | 6 | 18.6% | -7.7% | 8.1% | 12.1% |
| V2 OBV vs media 30d | -0.06 / 0.45 | 2/14 | 5 | 21.1% | -7.7% | 8.1% | 12.0% |
| V2 OBV vs media 60d | -0.29 / 0.47 | 3/14 | 6 | 12.2% | -9.5% | 15.9% | 11.9% |
| HODL | 0.27 / -0.53 | 6/14 | - | 5.6% | -50.1% | - | 100% |

**SOL**

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| original | -0.07 / 0.02 | 2/14 | 7 | 16.7% | -8.7% | 18.2% | 13.4% |
| V1 volumen >= 0.8x | 0.02 / 0.43 | 2/14 | 6 | 21.5% | -8.7% | 18.1% | 13.1% |
| V1 volumen >= 1.0x | 0.10 / 0.66 | 3/14 | 6 | 33.0% | -7.4% | 11.9% | 12.0% |
| V1 volumen >= 1.2x | -0.24 / 0.20 | 3/14 | 6 | 3.5% | -11.0% | 24.9% | 10.0% |
| V1 contraste: volumen <= 1.0x | -0.11 / 0.26 | 6/14 | 7 | 13.5% | -5.9% | 7.6% | 2.5% |
| V2 OBV vs media 20d | -0.30 / -0.45 | 2/14 | 9 | -1.3% | -8.7% | 25.3% | 13.4% |
| V2 OBV vs media 30d | -0.28 / -0.46 | 2/14 | 9 | 1.8% | -8.7% | 25.9% | 13.2% |
| V2 OBV vs media 60d | -0.77 / -0.61 | 2/14 | 9 | -4.4% | -8.7% | 26.4% | 12.7% |
| HODL | 0.68 / 0.71 | 4/14 | - | 237.9% | -46.2% | - | 100% |

## 3. Conclusiones

- **V1 (quiebre con volumen alto): no adoptar.** No hay patron monotono: en BTC la ganancia baja al subir el umbral (55.6% / 44.3% / 41.0%
  contra 56.5%) y la Sharpe mediana cae de 1.11 a 0.42 y 0.63; en ETH el 1.2x pasa a -11.6%; en SOL el 1.0x mejora (33.0%) pero el 1.2x
  empeora (3.5%). Lo unico consistente es que operar solo con volumen bajo (contraste) rinde peor en BTC y ETH (13.5% y -2.0%), pero a costa
  de casi no operar (2% a 3% del tiempo), asi que informa poco.
- **V2 (OBV): no adoptar.** En BTC casi no filtra (62.2% contra 56.5%, mismo resultado con 20, 30 y 60 dias), en ETH es neutro y en SOL empeora
  con claridad (-4.4% a 1.8% contra 16.7%; Sharpe mediana -0.61 a -0.45). Falla la validacion cruzada en SOL.
- **Alcance:** solo se probo el volumen por vela. El OBV es un proxy tosco del order flow, asi que esto NO demuestra que el order flow real
  (compras contra ventas agresivas) no sirva; solo que el volumen agregado no agrega senal robusta a estas entradas.
- Suma 7 variantes al acumulado (~63 sobre BTC). `configs/selected.json` sin cambios.

