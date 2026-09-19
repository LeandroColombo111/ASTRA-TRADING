# Prueba con 2020 y 2021 (los tramos menos contaminados): configuracion congelada

Serie Binance USD-M como proxy de OKX. **2020 es completamente nuevo**: se bajo despues de la busqueda y ninguna prueba lo vio (incluye el crash de marzo de 2020 solo como calentamiento). 2021 fue solo calentamiento de la seleccion de v4, pero otras busquedas tocaron esa serie, asi que no es independiente del todo. Ningun parametro se cambia. Ventanas de 90d desde 2020-05-01 (121 dias de calentamiento), 7 ventanas hasta enero de 2022.

| activo | ventanas | Sharpe media / mediana | ganancia total | peor ventana | DD encadenado | % en mercado | HODL total | HODL peor ventana |
|---|---|---|---|---|---|---|---|---|
| BTC | 7 | 0.43 / 0.38 | 15.5% | -3.1% | 4.0% | 12.8% | 343.3% | -33.6% |
| BTC (solo ventanas 1-3, casi todo 2020) | 3 | 0.86 / 0.38 | 17.0% | -1.5% | - | 14.4% | 267.6% | 22.5% |
| ETH | 7 | -0.28 / -0.31 | -9.5% | -7.1% | 13.7% | 16.8% | 1225.4% | -25.1% |
| ETH (solo ventanas 1-3, casi todo 2020) | 3 | 0.06 / -0.31 | -2.6% | -3.8% | - | 14.2% | 524.8% | 26.3% |

Detalle por ventana:

| activo | inicio | Sharpe | ganancia | HODL | trades |
|---|---|---|---|---|---|
| BTC | 2020-05-01 | 0.38 | 1.0% | 27.6% | 6 |
| BTC | 2020-07-30 | -0.28 | -1.5% | 22.5% | 9 |
| BTC | 2020-10-28 | 2.47 | 17.7% | 135.3% | 18 |
| BTC | 2021-01-26 | -0.74 | -2.6% | 51.1% | 5 |
| BTC | 2021-04-26 | 0.97 | 1.7% | -32.8% | 3 |
| BTC | 2021-07-25 | -0.71 | -3.1% | 78.7% | 5 |
| BTC | 2021-10-23 | 0.92 | 2.8% | -33.6% | 5 |
| ETH | 2020-05-01 | 1.20 | 4.9% | 52.2% | 7 |
| ETH | 2020-07-30 | -0.71 | -3.8% | 26.3% | 5 |
| ETH | 2020-10-28 | -0.31 | -3.4% | 225.1% | 16 |
| ETH | 2021-01-26 | -1.32 | -7.1% | 69.5% | 9 |
| ETH | 2021-04-26 | 0.90 | 4.9% | -9.6% | 7 |
| ETH | 2021-07-25 | 0.49 | 2.1% | 84.8% | 10 |
| ETH | 2021-10-23 | -2.21 | -6.6% | -25.1% | 5 |

Limite: 7 ventanas por activo (unos 21 meses). Sirve para ver si el bot se rompe en un regimen distinto, no para estimar un Sharpe con precision.

## Lectura

- **No se rompe, pero la ventaja es mucho menor que en la muestra original.** BTC: Sharpe mediana 0.38 (contra 1.00 en 2022-2026), ganancia +15.5% en
  21 meses (unos 8% anual), 3 de 7 ventanas negativas y drawdown encadenado de 4.0%. ETH: Sharpe medio -0.28 y -9.5% de ganancia total.
- **Frente al HODL pierde por mucho en un mercado alcista extremo** (BTC +343%, ETH +1225% en el mismo periodo), como ya se sabia: solo esta
  en mercado el 13% a 17% del tiempo. Lo que si hizo fue proteger capital en las ventanas bajistas de 2021 (BTC +1.7% y +2.8% mientras el HODL
  perdia -32.8% y -33.6%).
- **Conclusion:** sobre datos que la busqueda nunca vio, el bot sigue siendo defensivo y de bajo riesgo, pero su rentabilidad propia es chica
  y en ETH incluso negativa. Esto refuerza que lo razonable es usarlo como capa tactica sobre una tenencia, y que las cifras de 2022-2026 (Sharpe
  0.52 / 1.00) deben leerse como un techo optimista.

