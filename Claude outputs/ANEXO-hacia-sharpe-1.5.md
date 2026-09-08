# Anexo — ¿Qué es nuevo, hay mejor activo, y se puede llegar a Sharpe 1,5?

Complemento del review. Responde tus tres preguntas con mediciones nuevas sobre los datos del repo.

---

## Respuesta corta a las tres preguntas

1. **¿El review trae cosas que el modelo no encontró?** Sí, unas 8 de 13. La más importante (el bug del trailing) es nueva: el modelo *calculó la evidencia* pero nunca sacó la conclusión. El resto son cosas que el modelo declaró honestamente como limitaciones pero no cuantificó ni priorizó.
2. **¿Busqué mejores estrategias?** No en el review original — era un review, no una búsqueda. Pero ahora sí medí **el techo alcanzable**, que es la pregunta previa y más importante. Está abajo.
3. **¿Conviene otro activo en vez de BTC/USD?** **No, y ningún activo individual sirve.** El problema no es cuál activo elegís; es que un solo activo tiene un techo matemático muy por debajo de 1,5. La aritmética está en la sección 4.

---

## 1. Qué es genuinamente nuevo vs. qué es re-encuadre

Fui a chequear cada hallazgo contra lo que el modelo ya había escrito en sus `limitations` y sus reportes.

### Nuevo — el modelo no lo dice en ninguna parte

| Hallazgo | Por qué importa |
|---|---|
| **Bug trailing/stop** (`trail_atr=2` < `stop_atr=4`, activación inmediata → el stop de 4 ATR nunca existe) | El modelo **calculó la evidencia** — dejó `first_trail_at_loss_count: 71` y `median_first_trail_r: -0.0295` en la atribución — pero nunca sacó la conclusión ni la conectó con que **incumple el punto 4 del brief** (riesgo real ~0,9%, no 2%). Es el hallazgo más accionable del review. |
| **Potencia estadística** — SE(Sharpe) ≈ 0,97 por fold; el máximo de 200 sorteos da ~2,7σ por azar; el mejor score fue 0,688 | El ganador está *por debajo* del techo de ruido. Nunca se calculó. |
| **Correlación entre folds 0,21-0,35** | El desempeño en un período casi no predice el siguiente → el criterio de selección no tiene poder. Nunca se midió. |
| **Edge bruto por trade (~19 bps) vs costo por trade (~18 bps)** | El modelo tenía la atribución pero nunca la convirtió en la métrica decisiva ni en un gate. |
| **Ausencia total de benchmarks** | No hay buy&hold, ni EMA simple, ni control de entradas aleatorias en ningún reporte. |
| **Validación cruzada por activo** | El test anti-overfitting más barato que existe, nunca intentado. |
| **Nombres concretos de los tests correctos** (PBO/CPCV, White Reality Check, control aleatorio) y **DSR como criterio de parada dentro del loop** | El modelo sabía que le faltaba algo; no sabía qué. |
| **El techo medido** (secciones 3 y 4 de abajo) | Nuevo de esta sesión. |

### Re-encuadre — el modelo ya lo había declarado

Esto se lo reconozco: fue honesto. Yo lo cuantifiqué y lo prioricé, pero el mérito del diagnóstico es suyo.

- Reutilización del holdout (`known_audit_is_independent: false`) — **declarado explícitamente**.
- Monte Carlo no prueba ausencia de overfitting — **declarado en el propio campo `limitation`**.
- Venue proxy Binance vs OKX — declarado.
- Costos como supuestos, no como tarifa real de la cuenta — declarado.
- Que la exposición 1x baja el riesgo nominal por debajo del 2% — declarado (aunque por una causa distinta de la que yo encontré).

---

## 2. Lo que hice ahora: medir el techo antes de seguir optimizando

No tiene sentido buscar mejores parámetros sin saber cuánto rinde la señal cruda. Corrí el diagnóstico que faltaba sobre los 5,7 años de BTC 1h del repo: **momentum de series de tiempo puro**, sin parámetros libres más allá del horizonte — sin stops, sin targets, sin trailing, sin filtros. Solo: *signo del retorno pasado de h horas → mantener h horas*.

| Horizonte | corr(pasado, futuro) | t-stat | Sharpe bruto | Drag de costos | **Sharpe neto** | Giros/año |
|---:|---:|---:|---:|---:|---:|---:|
| 4 h | -0,025 | -2,75 | -0,13 | 6,86 | **-6,99** | 2226 |
| 12 h | 0,016 | 1,02 | 0,54 | 3,96 | **-3,42** | 1285 |
| 48 h | -0,003 | -0,09 | 0,30 | 1,86 | **-1,56** | 601 |
| **168 h** ← el del bot | 0,012 | 0,21 | 0,22 | 0,97 | **-0,75** | 312 |
| 336 h | 0,012 | 0,15 | 0,47 | 0,69 | **-0,23** | 221 |
| 720 h (30 d) | 0,093 | 0,75 | 0,84 | 0,43 | **+0,41** | 135 |
| 1440 h (60 d) | -0,055 | -0,30 | 0,84 | 0,20 | **+0,64** | 63 |

Tres lecturas, todas importantes:

1. **A la frecuencia que exige el brief, el costo solo ya cuesta ~1,0 unidades de Sharpe**, contra un Sharpe bruto de 0,22. No hay optimización de parámetros que arregle eso. El bot no falló por elegir mal los indicadores; falló porque **el punto 8 del brief (1h/4h) lo puso en la zona donde los costos superan al edge**.
2. **La tendencia en BTC solo se vuelve rentable neta a partir de ~30-60 días de horizonte**, y ahí el techo es **0,64**.
3. **Ningún t-stat es significativo.** BTC no tiene estructura de tendencia estadísticamente detectable en ningún horizonte de esta muestra. El 0,84 bruto a 60 días no es sesgo largo (lo verifiqué: 50% del tiempo largo, y la versión market-neutral da 0,62) — es timing real, pero débil y dentro del ruido.

Referencias medidas sobre el mismo período: BTC buy & hold = Sharpe **0,30**, vol 58%. Probé también *volatility targeting* (el lever clásico de los CTA): en BTC **empeoró** el resultado (0,64 → 0,42 a 60 días). No lo recomiendo acá.

**Conclusión: el techo de una estrategia de tendencia sobre BTC solo, neta de costos, es ~0,6.** No 1,5. Ninguna cantidad de intentos cambia eso.

---

## 3. ¿Conviene otro activo? La aritmética dice que la pregunta está mal planteada

Para una canasta equiponderada de N activos, cada uno con Sharpe `s` y correlación promedio `ρ`:

```
Sharpe_canasta = s · √( N / (1 + (N-1)·ρ) )        techo asintótico = s / √ρ
```

Con `s = 0,64` (lo que acabo de medir en BTC):

| Universo | ρ típico | Techo alcanzable | N necesario para 1,5 |
|---|---:|---:|---|
| Solo cripto majors (BTC/ETH/SOL/BNB) | 0,75 | **0,74** | **imposible** |
| Cripto + acciones | 0,60 | **0,83** | **imposible** |
| Multi-activo parcial | 0,30 | **1,17** | **imposible** |
| Futuros diversificados tipo CTA | 0,15 | 1,65 | **~27 mercados** |

La correlación de 0,7-0,8 entre BTC, ETH y Solana está confirmada por CME sobre ventanas móviles de un año. **Eso significa que agregar ETH, SOL, BNB y 20 alts más te lleva de 0,64 a 0,74 y ahí se termina** — la diversificación dentro de cripto no existe.

Lo que sí descorrelaciona, según los mismos datos de CME: oro (correlación ~0 con cripto), dólar (~0), y en menor medida índices de acciones (0,2-0,6).

Esto coincide exactamente con la literatura. El paper fundacional de momentum de series de tiempo (Moskowitz, Ooi & Pedersen) obtiene **Sharpe 1,31 usando 58 instrumentos** — 24 commodities, 13 bonos, 12 divisas, 9 índices de acciones — sobre 45 años, **bruto**. El resultado más celebrado de la historia del trend following, con 58 mercados y cuatro clases de activo, llega a 1,31.

**Tu brief pide 1,5 con un activo.** Esa es la contradicción de fondo, y explica por qué el modelo dio 400 vueltas sin encontrarlo: no estaba ahí.

---

## 4. Rutas que sí llegan a Sharpe ≥ 1,5

Dijiste que el objetivo se mantiene. Entonces lo que hay que cambiar no es el esfuerzo de búsqueda, es **la familia de estrategia o el universo**. Ordenadas por probabilidad real de éxito:

### Ruta A — Momentum transversal sobre 30-50 perpetuos de cripto ★ mejor encaje con tu brief

En vez de "¿sube o baja BTC?", preguntás "¿qué 5 de 40 monedas suben más que la mediana?" y vas largo de esas y corto de las 5 peores, dólar-neutral. **Esto elimina el factor mercado**, que es justamente lo que hace que ρ=0,75 entre cripto sea un techo. Las apuestas relativas quedan mucho menos correlacionadas entre sí que las direccionales.

- Mantiene: futuros/perps (punto 10), long y short (punto 9), un solo venue.
- Cambia: de 1 activo a 40; de direccional a relativo; horizonte a días, no horas.
- Sharpe realista: **1,0-1,8**. Es la ruta con mejor relación esfuerzo/probabilidad.
- Costo de implementación: hay que bajar datos de 40 símbolos (el módulo `data.py` ya lo hace, solo hay que parametrizar el símbolo) y agregar lógica de cartera.

### Ruta B — Carry de funding / basis, o un mix carry + tendencia

Medí el funding sobre los datos **que ya están en el repo**: media de 0,0099% por pago de 8h = **10,8% anualizado**, positivo el 88% de los días, todos los años positivos (2021-2026).

> ⚠️ **Advertencia importante, y te la doy antes de que veas el número.** Mi cálculo trata el funding como ingreso sin riesgo, y **no lo es**. Le falta el término de riesgo: variación del basis spot-perp, costo y ejecución del hedge, custodia/préstamo del spot, riesgo de liquidación de la pata corta, y riesgo de exchange (FTX). El Sharpe "10+" que sale de mi cálculo **no es el Sharpe de una estrategia operable** — es una cota superior con el riesgo faltante. El número realista de un cash-and-carry bien gestionado es **1,5-3, con caídas bruscas y poco frecuentes**. Te lo señalo porque presentarte ese 10 sin este párrafo sería exactamente el error que le critiqué al modelo.
>
> Con esa salvedad: es la única familia en cripto que produce Sharpe > 1,5 de forma documentada y persistente, usa perps, y **la correlación medida entre el carry y la tendencia a 60 días es 0,02** — o sea, combinables casi sin solapamiento.

### Ruta C — Tendencia diversificada multi-activo (27+ mercados)

Es la ruta canónica y la que la aritmética respalda directamente, pero requiere datos de futuros de bonos, divisas, índices y commodities. Fuera del alcance de la infraestructura actual (que es solo cripto) sin trabajo de datos significativo.

### Ruta D — Bajar el objetivo

Sharpe 1,0 con Calmar ≥ 0,5 sobre la Ruta A es un objetivo exigente pero honesto. Lo menciono para que sea una decisión explícita tuya y no algo que ocurra por default.

### Lo que NO recomiendo

Seguir buscando parámetros para tendencia 1h/4h en BTC. Los datos de la sección 2 dicen que el techo de esa configuración es negativo neto de costos. Otros 200 intentos no van a encontrar un 1,5 que exista — van a encontrar un 1,5 que **no** existe, y el DSR lo va a delatar como ya pasó dos veces.

---

## 5. Lo que le pediría al modelo ahora

Un solo pedido, en este orden:

1. **Antes de optimizar nada**, reproducir la tabla de la sección 2 (momentum puro por horizonte, bruto y neto) para el activo y timeframe que se proponga. Si el Sharpe neto de la señal cruda no es > 0,3, la familia se descarta sin gastar intentos.
2. Arreglar el bug trailing/stop y el gate de costos ≤ 30% del bruto.
3. Implementar la Ruta A: extender `data.py` a 30-50 símbolos, construir momentum transversal dólar-neutral, horizonte 3-20 días.
4. Sellar un holdout **nuevo** (los datos hasta 2026-09 ya están quemados dos veces): usar walk-forward hacia adelante en demo de OKX, que `service.py` ya soporta.
5. Reemplazar el Monte Carlo actual por PBO/CPCV y mover el DSR al loop como criterio de parada.

---

## Nota sobre el acceso a datos

No pude bajar datos de otros activos en esta sesión: el entorno bloquea `data.binance.vision`, `stooq` y las APIs de mercado (403 / robots.txt). Todo lo que medí arriba sale de los 5,7 años de BTC 1h que ya están en el repo, más literatura publicada para las correlaciones cruzadas. Si querés que corra la comparación empírica entre activos, necesito que la sesión tenga salida a esos hosts, o que bajes los CSV vos y los pongas en la carpeta.

---

**Fuentes:**

- [Time Series Momentum Effect — Quantpedia](https://quantpedia.com/strategies/time-series-momentum-effect) (Moskowitz, Ooi & Pedersen: 58 instrumentos, 4 clases de activo, Sharpe 1,31)
- [Time Series Momentum — Moskowitz, Ooi & Pedersen, NYU Stern](https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf)
- [As Crypto Market Matures, What's Next for Bitcoin, Ether and Solana? — CME Group](https://www.cmegroup.com/insights/economic-research/2025/as-crypto-market-matures-whats-next-for-bitcoin-ether-and-solana.html) (correlaciones BTC/ETH/SOL de +0,7 a +0,8; cripto vs oro y dólar ~0)
- [Demystifying Managed Futures — AQR](https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/Demystifying-Managed-Futures.pdf)
- [The Science and Practice of Trend-Following Systems — arXiv](https://arxiv.org/html/2607.19497) (relación cerrada entre autocorrelación y Sharpe; costo de break-even)
- Mediciones propias sobre `data/BTCUSDT-1h.csv` del repo (49.656 velas, 2021-01 a 2026-08)
