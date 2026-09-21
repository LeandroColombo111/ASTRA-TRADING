# Riesgo de perder las ganancias

Se reconstruye el retorno diario del bot (configuracion congelada, sin el freno del 25% para medir el riesgo puro) y se simulan 20.000 anos posibles remuestreando bloques de 20 dias. Es historia reordenada, no un pronostico: si el futuro es peor que el pasado, estas cifras son optimistas.


## BTC Binance 2020-05 a 2026-08 (6.3 anos, incluye 2020-2021 nuevos)

- Retorno anual promedio de la serie: 10.0%. Anos moviles de 365 dias (empirico, 1950 ventanas solapadas): 28.2% terminan en perdida, peor -21.9%, mejor 53.0%.
- Simulacion (20.000 anos): retorno medio 11.8%, mediana 9.0%, rango 90% [-15.5%, 48.1%].
- Probabilidad de terminar el ano en perdida: **30.0%**; de ganar menos de 5%: 41.0%.
- Probabilidad de una caida maxima dentro del ano mayor a 10%: 68.8%; mayor a 20%: 10.3%; mayor a 25% (el freno): 2.8%.
- De los anos que llegaron a estar +10% arriba en algun momento (69.1% de los anos): terminaron en 0% o peor el **8.9%** (devolvieron toda la ganancia) y en 5% o menos el 17.7%.

## BTC OKX 2022-09 a 2026-08 (4 anos)

- Retorno anual promedio de la serie: 13.4%. Anos moviles de 365 dias (empirico, 1074 ventanas solapadas): 21.3% terminan en perdida, peor -13.3%, mejor 48.7%.
- Simulacion (20.000 anos): retorno medio 15.3%, mediana 12.2%, rango 90% [-16.1%, 57.8%].
- Probabilidad de terminar el ano en perdida: **27.3%**; de ganar menos de 5%: 36.8%.
- Probabilidad de una caida maxima dentro del ano mayor a 10%: 67.4%; mayor a 20%: 11.4%; mayor a 25% (el freno): 3.2%.
- De los anos que llegaron a estar +10% arriba en algun momento (72.6% de los anos): terminaron en 0% o peor el **8.3%** (devolvieron toda la ganancia) y en 5% o menos el 15.7%.

## BTC Binance 2020-05 a 2021-12 solo datos nuevos (1.7 anos)

- Retorno anual promedio de la serie: 6.2%. Anos moviles de 365 dias (empirico, 247 ventanas solapadas): 4.0% terminan en perdida, peor -1.9%, mejor 24.6%.
- Simulacion (20.000 anos): retorno medio 7.9%, mediana 6.1%, rango 90% [-12.9%, 34.4%].
- Probabilidad de terminar el ano en perdida: **32.1%**; de ganar menos de 5%: 47.0%.
- Probabilidad de una caida maxima dentro del ano mayor a 10%: 59.7%; mayor a 20%: 3.9%; mayor a 25% (el freno): 0.5%.
- De los anos que llegaron a estar +10% arriba en algun momento (61.8% de los anos): terminaron en 0% o peor el **7.4%** (devolvieron toda la ganancia) y en 5% o menos el 18.4%.

## Por ano calendario y por fase del ciclo de Bitcoin (BTC Binance, corrida continua desde 2020-05)

Las fases del ciclo se marcaron a posteriori (fechas aproximadas de halvings y maximos/minimos): sirven para entender, no para operar, porque en tiempo real no se sabe en que fase se esta.

| periodo | bot | caida max | trades | BTC (comprar y mantener) |
|---|---|---|---|---|
| 2020 (mayo-dic) | 12.1% | 10.8% | 29 | 234.8% |
| 2021 | -1.3% | 13.3% | 20 | 62.1% |
| 2022 | 2.6% | 10.6% | 23 | -64.5% |
| 2023 | 30.9% | 10.3% | 23 | 156.5% |
| 2024 | -5.1% | 24.6% | 35 | 117.5% |
| 2025 | 6.2% | 10.8% | 26 | -6.5% |
| 2026 (ene-ago) | 22.7% | 10.2% | 17 | -11.2% |
| Fase: alza post-halving 2020-05 a 2021-11 | 12.6% | 10.9% | 45 | 664.8% |
| Fase: bajista 2021-11 a 2022-11 | 3.0% | 10.6% | 26 | -75.8% |
| Fase: recuperacion 2022-11 a 2024-04 | 44.6% | 10.6% | 34 | 285.5% |
| Fase: post-halving y alza 2024-04 a 2025-10 | -11.9% | 26.7% | 46 | 94.5% |
| Fase: correccion 2025-10 a 2026-08 | 26.9% | 10.2% | 21 | -36.8% |

Lectura: el bot termino en perdida en 2 de los 7 periodos anuales (2021 y 2024), coherente con el ~30% de la simulacion. Los malos periodos son las
expansiones alcistas volatiles (2021: -1.3%; 2024: -5.1%, y la fase 2024-04 a 2025-10: -11.9% con caida maxima de 26.7%, que habria activado el freno
del 25%). Los buenos son la recuperacion tras un minimo (2023: +30.9%) y las correcciones (2026: +22.7% en 8 meses). Solo hay ~1.5 ciclos de datos,
asi que las probabilidades tienen mucha incertidumbre, y el ciclo de 4 anos puede no repetirse igual.

