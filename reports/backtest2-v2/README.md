# backtest2-v2: como mejorar la ganancia frente a HODL

Todo sale de `ops/backtest2_research.py` (reproducible: `python3 ops/backtest2_research.py`). Las tablas completas
estan en [tables.md](tables.md) y los datos crudos en `summary.json`. `configs/selected.json` y `approved_for_live`
**no se tocaron**. Punto de partida: `reports/backtest2-v1/CORRECTION_2026-09-18.md`.

## Metodologia (las cuatro reglas)

1. **Like-for-like:** mismo warmup de 250 dias para todas las variantes; siempre contra HODL en las mismas ventanas.
2. **Parametros fijos** por variante, nunca re-optimizados por ventana.
3. **Validacion cruzada:** toda idea se corre en BTC, ETH y SOL y con valores vecinos del parametro.
4. **Se reporta siempre:** Sharpe media/mediana, ventanas >=1.5, ganancia total, peor ventana, % en mercado y HODL.

Ventanas: 14 de 90 dias (train 365d / test 90d / paso 90d), cada una arranca con capital fresco; "encadenado" une las
14 ventanas (retorno compuesto, Sharpe diario y drawdown sobre toda la cadena).

**Reproduccion del punto de partida (BTC):** bot original Sharpe 0.52 / 1.00, 5/14 ventanas >=1.5, +56.5%, peor
ventana -11.3%, 16.6% del tiempo en mercado: identico al handoff. HODL da 0.79 / 0.61 y +191.6% (el handoff decia
0.77 / 0.63 y +183.4%); la diferencia es de convencion al recortar la ventana y no cambia ninguna conclusion.

**Comparaciones multiples.** Antes de esta ronda se habian probado ~13 variantes sobre BTC. Esta ronda agrego unas 31
(5 de tenencia, 7 de hipotesis C, 19 combinaciones de stop/reward/min_trend), asi que el acumulado ronda **44**. Cualquier
"ganador" sobre BTC debe leerse con ese descuento; por eso se exige que se sostenga en ETH/SOL y en los vecinos.

## Aviso que condiciona todo

Los parametros de `selected.json` se eligieron con esta misma historia. Ninguna ventana es fuera de muestra en sentido
estricto: el walk-forward con parametros fijos mide **estabilidad en el tiempo**, no capacidad predictiva. Ademas, en la
seccion D los valores de produccion (`stop_atr=3`, `reward=3`, `min_trend=0`) resultan ser un **pico en BTC**: los
vecinos rinden bastante peor (Sharpe mediana 0.46 a 0.91 con ganancia 40% a 46% en stop=3, y hasta -0.22 con stop=2).
Es la firma de un valor elegido sobre estos datos, y hay que esperar un rendimiento futuro menor al de estas tablas.

## Resumen y recomendaciones

| idea | resultado | recomendacion |
|---|---|---|
| **A. Objetivo** | (3) superar al HODL en ganancia total no es alcanzable (56% contra 192% en BTC, con 17% del tiempo en mercado). (1) Sharpe y drawdown: en BTC el bot solo iguala el Sharpe encadenado del HODL (0.89 contra 0.89) con un tercio del drawdown (19.5% contra 53.9%); en ETH lo supera (0.40 contra 0.34) y en SOL queda por debajo (0.35 contra 0.83). (2) La cartera hibrida es el objetivo realista. | **Perseguir el objetivo (2)** |
| **A. Cartera hibrida** (HODL + bot) | BTC 50/50: Sharpe encadenado 0.89 a 1.12, drawdown 53.9% a 24.3%, ganancia 192% a 143%. Mejora en los 3 activos. Pero el IC 95% de la diferencia de Sharpe incluye 0 en todos los casos (P(mejora) 75% a 89%). | **Adoptar como marco de trabajo, no como evidencia concluyente.** No cambia el bot |
| **B. Tenencia + salida a efectivo por macro** | Peor que HODL en Sharpe en los 3 activos (BTC, Sharpe media de ventanas: -0.08 a 0.59 contra 0.79). Baja el drawdown (BTC continua, sin freno: 30% a 43% contra 54%) pero el retorno cae en proporcion. Con el freno de drawdown del 25% queda congelada (`halted=True`). | **No adoptar** |
| **C-H1** vol objetivo | Baja drawdown y retorno en proporcion; Sharpe sin mejora (BTC 0.45 a 0.54 contra 0.52). | **No adoptar** |
| **C-H2** entrada cerca del maximo | BTC mejora en los 3 valores (ganancia 72% a 82% contra 56.5%; Sharpe mediana 1.00 / 0.63 / 0.92), SOL mejora, **ETH empeora en los 3** (ganancia -23% a -4% contra +17%). Sube el tiempo en mercado (17% a 21% / 34% / 44%). | **No adoptar; seguir observando** (falla la regla 3 en ETH) |
| **C-H3** solo largos | BTC empeora (Sharpe -0.34 contra 0.52). Los cortos aportan valor: sin ellos el Sharpe medio cae de 0.52 a -0.34. | **No adoptar** |
| **D. Re-optimizar por ventana** | Confirmado con warmup correcto: no ayuda. BTC 0.52 a -0.03 (stop/reward) y a 0.19 (min_trend); corr(IS, OOS) negativa en las 6 pruebas. | **No re-optimizar; mantener valores fijos** |
| **E. impact_k** | 0 fills reales con `_reference_price`; no se calibra. El resultado es casi insensible a impact_k (56.6% con k=0, 56.2% con k=10). | **Dejar 1.0; baja prioridad;** recalibrar con >=30 fills |
| **F. Mas periodos y activos** | Con 15 ventanas (suma 2022) el bot sigue igual: 0.49 / 1.07, +51.8% (BTC). No cambia con otras definiciones de ventana (60d, 180d, desfases). ETH y SOL: el bot casi no tiene ventaja ajustada por riesgo. | Sin cambios |

## Detalle por tarea

### A. Objetivo realista

BTC, 14 ventanas: bot Sharpe 0.52 / 1.00, +56.5%, peor -11.3%. HODL 0.79 / 0.61, +191.6%, peor -27.1%.
El bot captura poco de la suba y protege bien en las bajas (ventanas alcistas: HODL +34.5%, bot +3.1%;
bajistas: HODL -17.5%, bot +4.0%).

Cartera hibrida con el bot original (capital propio para cada mitad), BTC:

| w HODL | Sharpe encadenado | ganancia | DD encadenado | peor ventana | ganancia / DD |
|---|---|---|---|---|---|
| 100% | 0.89 | 191.6% | 53.9% | -27.1% | 3.6 |
| 70% | 1.02 | 169.5% | 36.7% | -17.0% | 4.6 |
| 60% | 1.07 | 157.3% | 30.6% | -13.7% | 5.1 |
| 50% | 1.12 | 143.3% | 24.3% | -10.3% | 5.9 |
| 0% (solo bot) | 0.89 | 56.5% | 19.5% | -11.3% | 2.9 |

ETH y SOL mejoran igual en Sharpe encadenado (ETH 0.34 a 0.45; SOL 0.83 a 0.94, ambos con 50/50) y en drawdown.
Aviso: el Sharpe medio por ventana de la cartera *baja* (0.79 a 0.66) porque las ventanas cortas de HODL alcista tienen
Sharpes muy altos que la mezcla diluye; la medida encadenada y el drawdown son las relevantes para una tenencia real.

**Recomendacion:** perseguir (2). El bot como capa tactica reduce el drawdown a la mitad pagando una parte del retorno,
que es la unica mejora consistente en los 3 activos. No es concluyente estadisticamente (IC incluye 0), asi que se
necesita mas historia o operacion real antes de asignar capital.

### B. Modo de dimensionamiento por exposicion

Implementado en `ExecutionSimulator` (`target_exposure` o columna `exposure` en la senal; por defecto `None`, el modo de
riesgo actual queda intacto y verificado por test). Estrategias en `src/astra/backtest2/exposure_strategies.py`.

Hallazgo operativo: el freno de drawdown del 25% que usa produccion **congela** una estrategia de tenencia despues de la
primera caida grande (BTC continuo, EMA 20/100: `halted=True`, 2 trades, +6.3%). Sin freno (mismos datos): +121.7%,
drawdown 42.9%, Sharpe 0.74. Cualquier estrategia tipo HODL exigiria repensar ese freno, que no se toco.

BTC, corrida continua desde el fin del warmup (una sola pasada):

| variante | Sharpe | ganancia | DD max |
|---|---|---|---|
| HODL | 1.00 | 310.3% | 53.8% |
| bot original | 0.87 | 64.1% | 19.5% |
| tenencia precio vs SMA 200, sin freno | 0.86 | 168.9% | 35.1% |
| tenencia precio vs SMA 150, sin freno | 0.93 | 189.3% | 30.2% |
| tenencia EMA 30/150, sin freno | 0.82 | 160.4% | 37.3% |

En la corrida continua la SMA 150 sin freno parece rozar el Sharpe del HODL con menos drawdown, pero en ventanas de 90d
es peor (Sharpe mediana -0.20) y en ETH/SOL no supera al HODL. Es un solo camino historico con 20 trades: no es evidencia
para adoptarla. **No adoptar.**

### C. Mas tiempo en mercado

Las tres hipotesis y su justificacion se fijaron antes de correrlas (ver `tables.md`, seccion C). H1 y H3 no pueden
subir el tiempo en mercado con la config actual (el tamano ya esta en el tope de 1x). Solo H2 lo sube, y es la unica con
resultado mixto: mejora BTC y SOL pero empeora ETH en todos los valores. Bajo la regla 3, no se adopta.

### D. Re-verificacion con warmup correcto

Re-eleccion por ventana (mejor Sharpe de los 365d previos), 14 ventanas:

| grilla | activo | re-elegido: Sharpe media / mediana | ganancia | fijo produccion | corr(IS, OOS) |
|---|---|---|---|---|---|
| stop x reward | BTC | -0.03 / 0.36 | 29.4% | 0.52 / 1.00, 56.5% | -0.14 |
| stop x reward | ETH | 0.00 / -0.02 | 19.4% | -0.14 / 0.34, 17.4% | -0.03 |
| stop x reward | SOL | 0.03 / 0.51 | 13.4% | -0.07 / 0.02, 16.7% | -0.24 |
| min_trend | BTC | 0.19 / 0.18 | 25.2% | 0.52 / 1.00, 56.5% | -0.28 |
| min_trend | ETH | 0.12 / 0.21 | 28.0% | -0.14 / 0.34, 17.4% | -0.42 |
| min_trend | SOL | -0.36 / -0.69 | -2.2% | -0.07 / 0.02, 16.7% | -0.13 |

La conclusion previa ("re-tunear por ventana no ayuda") se **confirma con warmup correcto**. El mejor valor cambia de
activo a activo (BTC prefiere stop 3; SOL, stop 4; ETH, stop 5), lo que tambien es una senal de que no hay un optimo
estable.

### E. Calibracion de impact_k

0 fills utilizables. El estado del bot tiene 6 eventos, todos de la prueba manual del 15/9, anteriores al registro de
`_reference_price`; desde el despliegue no hubo entradas de estrategia. Sensibilidad medida: k=0 / 1 / 3 / 10 da
+56.6% / +56.5% / +56.5% / +56.2%. Con tamano de 1x sobre BTC el impacto es despreciable, asi que calibrar este valor
no cambia ninguna conclusion de este informe.

### F. Mas periodos y activos

15 ventanas empezando al terminar el warmup (suma 2022 bajista): BTC 0.49 / 1.07, +51.8% contra HODL 0.90 / 0.30,
+235.7%. Otras definiciones de ventana (60d, 180d, desfases de 30d y 60d): Sharpe mediana 0.54 a 1.08, ganancia 45% a
69%, siempre con drawdown encadenado por debajo del 16%. Con 14 ventanas la incertidumbre sigue siendo alta: los
intervalos del bootstrap en A incluyen 0.

## Que se hizo en el codigo

- `src/astra/backtest2/research.py` (nuevo): arnes like-for-like, HODL, cadena de ventanas, cartera manga.
- `src/astra/backtest2/exposure_strategies.py` (nuevo): tenencia con macro, vol objetivo, cerca del maximo, solo largos.
- `src/astra/backtest2/execution.py`: modo de exposicion opcional; el modo por defecto queda igual (resultados
  identicos antes y despues; test agregado en `tests/test_backtest2_smoke.py`).
- `ops/backtest2_research.py` (nuevo): la corrida completa.

## Limites

- Ventanas de 90 dias con capital fresco cortan las posiciones largas al final de cada una.
- Las tablas de cartera hibrida usan el bot en su propio capital sin rebalanceo intra-ventana y no incluyen rendimiento
  del efectivo ni costos de rebalanceo.
- Los numeros de HODL no incluyen comisiones ni funding (favorece levemente al HODL).
