# Clustering de volatilidad: diagnostico y filtro de regimen

## 1. Diagnostico (no agrega variantes)

Autocorrelacion del |retorno diario| (persistencia de la volatilidad) y del retorno mismo:

| activo | rezago 1 | 2 | 5 | 10 | 20 | autocorr del retorno (rezago 1) |
|---|---|---|---|---|---|---|
| BTC | 0.18 | 0.09 | 0.09 | 0.03 | 0.01 | -0.025 |
| ETH | 0.17 | 0.12 | 0.08 | 0.04 | 0.03 | -0.016 |
| SOL | 0.29 | 0.16 | 0.14 | 0.03 | 0.00 | -0.025 |

Resultado de las operaciones del bot (corrida continua) segun el regimen de volatilidad al entrar (vol de 7d / vol de 60d, terciles). Ojo: pocos trades por grupo.

| activo | regimen al entrar | trades | ganancia media por trade | % ganadores |
|---|---|---|---|---|
| BTC | calma | 35 | 1.0% | 46% |
| BTC | media | 34 | 0.5% | 35% |
| BTC | alta | 35 | -0.1% | 37% |
| ETH | calma | 31 | 1.8% | 48% |
| ETH | media | 30 | 1.0% | 43% |
| ETH | alta | 30 | -2.1% | 20% |
| SOL | calma | 33 | -0.7% | 24% |
| SOL | media | 32 | -0.9% | 28% |
| SOL | alta | 33 | 2.0% | 45% |

## 2. Filtro de entradas por regimen (valores fijos y vecinos; ventanas de 90d, warmup 250d)

Hipotesis fijadas antes de correr: **alta** = solo entrar con volatilidad en expansion (la persistencia de la volatilidad haria que los quiebres tengan continuidad); **calma** = solo entrar con volatilidad comprimida (contraste: es lo que sugiere el diagnostico, que se miro sobre los mismos trades, asi que es la de mayor riesgo de sobreajuste).


**BTC**

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| v4_hourly original | 0.52 / 1.00 | 5/14 | 4 | 56.5% | -11.3% | 15.8% | 16.6% |
| alta: ratio >= 0.8 | -0.49 / -0.44 | 4/14 | 8 | 0.0% | -9.5% | 28.1% | 14.0% |
| alta: ratio >= 1.0 | -0.72 / -0.10 | 1/14 | 7 | -11.0% | -7.7% | 21.2% | 10.2% |
| alta: ratio >= 1.2 | -0.78 / -0.19 | 1/14 | 7 | -6.5% | -5.8% | 8.3% | 5.4% |
| calma: ratio <= 0.8 | 0.61 / 1.55 | 7/14 | 4 | 43.1% | -3.4% | 5.3% | 3.3% |
| calma: ratio <= 1.0 | 0.75 / 1.46 | 7/14 | 3 | 54.0% | -4.0% | 7.4% | 6.7% |
| calma: ratio <= 1.2 | 0.64 / 1.09 | 5/14 | 4 | 58.1% | -9.5% | 16.6% | 11.6% |
| HODL | 0.79 / 0.61 | 6/14 | - | 191.6% | -27.1% | - | 100% |

**ETH**

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| v4_hourly original | -0.14 / 0.34 | 2/14 | 5 | 17.4% | -9.4% | 9.4% | 12.2% |
| alta: ratio >= 0.8 | -0.34 / 0.22 | 3/14 | 6 | 13.0% | -9.4% | 14.8% | 11.5% |
| alta: ratio >= 1.0 | -1.35 / -1.04 | 2/14 | 8 | -18.5% | -9.6% | 19.8% | 7.3% |
| alta: ratio >= 1.2 | -1.08 / -1.94 | 2/14 | 8 | -15.0% | -7.7% | 16.5% | 4.1% |
| calma: ratio <= 0.8 | -0.08 / 0.00 | 2/14 | 3 | 7.8% | -2.0% | 5.9% | 0.8% |
| calma: ratio <= 1.0 | 0.57 / 1.21 | 4/14 | 4 | 44.4% | -5.8% | 6.7% | 4.9% |
| calma: ratio <= 1.2 | 0.43 / 0.85 | 4/14 | 3 | 43.1% | -11.6% | 11.6% | 8.7% |
| HODL | 0.27 / -0.53 | 6/14 | - | 5.6% | -50.1% | - | 100% |

**SOL**

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| v4_hourly original | -0.07 / 0.02 | 2/14 | 7 | 16.7% | -8.7% | 18.2% | 13.4% |
| alta: ratio >= 0.8 | -0.54 / -0.31 | 3/14 | 8 | 25.2% | -6.8% | 15.0% | 11.1% |
| alta: ratio >= 1.0 | -0.86 / -0.48 | 2/14 | 8 | -0.1% | -7.8% | 24.4% | 6.6% |
| alta: ratio >= 1.2 | -0.08 / 0.00 | 3/14 | 6 | 11.7% | -4.0% | 5.9% | 3.8% |
| calma: ratio <= 0.8 | -0.43 / 0.00 | 1/14 | 5 | -5.9% | -6.0% | 12.2% | 2.5% |
| calma: ratio <= 1.0 | -0.11 / 0.09 | 2/14 | 7 | 9.2% | -4.7% | 12.9% | 6.6% |
| calma: ratio <= 1.2 | 0.20 / 0.20 | 4/14 | 7 | 25.9% | -6.9% | 14.3% | 9.0% |
| HODL | 0.68 / 0.71 | 4/14 | - | 237.9% | -46.2% | - | 100% |

## 3. Estabilidad temporal del filtro de calma (primeras 7 ventanas vs ultimas 7)

| activo | variante | ventanas 1-7: Sharpe mediana / ganancia | ventanas 8-14: Sharpe mediana / ganancia |
|---|---|---|---|
| BTC | original | 0.90 / 29.1% | 1.10 / 21.2% |
| BTC | calma <= 1.0 | 1.07 / 25.9% | 1.54 / 22.3% |
| BTC | calma <= 1.2 | 1.07 / 30.5% | 1.10 / 21.2% |
| ETH | original | 0.43 / -0.7% | 0.26 / 18.2% |
| ETH | calma <= 1.0 | 0.48 / 9.2% | 1.33 / 32.2% |
| ETH | calma <= 1.2 | 0.67 / 10.4% | 1.03 / 29.6% |
| SOL | original | -0.75 / 6.0% | 0.62 / 10.1% |
| SOL | calma <= 1.0 | -1.12 / 3.6% | 0.25 / 5.3% |
| SOL | calma <= 1.2 | -0.41 / 10.4% | 1.21 / 14.0% |

## 4. Conclusiones

- El clustering existe pero es corto: la autocorrelacion de la volatilidad diaria es 0.17 a 0.29 al dia siguiente y casi
  desaparece a los 10 a 20 dias. Los retornos en si no tienen autocorrelacion, asi que la volatilidad ayuda a estimar
  riesgo, no direccion.
- **Filtro "alta" (usar la persistencia de volatilidad alta para entrar): no adoptar.** Empeora BTC (mediana 1.00 a -0.44 / -0.10 / -0.19)
  y ETH, y en SOL es mixto. Con los datos, entrar cuando la volatilidad ya se disparo llega tarde.
- **Filtro "calma" (solo entrar con volatilidad comprimida): candidato, no adoptar todavia.** En BTC y ETH mejora la
  mediana de Sharpe y baja mucho el drawdown y el tiempo en mercado (BTC <= 1.0: 1.46 contra 1.00, DD 7.4% contra 15.8%,
  6.7% del tiempo contra 16.6%), con ganancia total parecida (54.0% contra 56.5%); es decir, la misma ganancia con menos
  exposicion, no una ganancia mayor. Se sostiene en ambas mitades de las ventanas en BTC y ETH; en SOL es mixto y el valor
  estricto (<= 0.8) empeora en ETH y SOL por casi no operar.
- **Riesgo de sobreajuste:** la direccion se miro sobre los mismos trades y esta prueba suma 6 variantes al acumulado
  (~50 sobre BTC). Necesita confirmarse con operacion real en demo o datos nuevos antes de tocar el bot.
- El tamano por volatilidad objetivo (ya probado como H1 en `README.md`) no mejoro el Sharpe.

