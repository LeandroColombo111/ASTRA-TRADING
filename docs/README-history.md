# ASTRA Trading

Bot de tendencia en Python para **OKX BTC-USDT-SWAP**, con señal de **1 hora**, ancla de **4 horas**, operaciones **long y short**, investigación reproducible y servicio contenedorizable.

## Segunda investigación completada

Se hicieron **200 intentos adicionales**, manteniendo BTC, futuros long/short, 1h/4h y riesgo nominal de 2%. La variante elegida en desarrollo cambia únicamente el objetivo de **2R a 1,5R**. En los 18 meses conocidos, el Sharpe pasa de −0,102 a 0,117 con Binance y de −0,001 a 0,229 con **precios y funding oficiales de OKX**. Sigue sin alcanzar 1,5 y no está aprobada para operar.

La pérdida original se explica contablemente por una ventaja bruta de 1.308 USDT, consumida por 1.077 USDT de comisiones, 539 USDT de deslizamiento y 9 USDT de funding. Los longs son débiles; retrasar el trailing, el ADX o la entrada por retroceso ensayada no ofrecieron una solución estable. Cambiar de venue o reutilizar el período conocido no constituye nueva evidencia temporal independiente.

Ver [informe de segunda ronda](reports/run-002/RESULTADOS.md), [gráfico de diagnóstico](reports/run-002/diagnostico.png) y [200 comparaciones registradas](reports/run-002/attempts.jsonl). Se mantuvo `configs/selected.json`; el candidato está separado en `reports/run-002/selected_research.json`.

```bash
python -m astra.second_research --budget 200 --output reports/run-002
python -m astra.okx_history
python -m astra.round_two_report
```

La búsqueda rechaza sobrescribir una ronda existente. Los dos últimos comandos descargan datos y reconstruyen la comparación de candidatos ya fijados; no abren una nueva búsqueda. Para generar gráficos, instalar `pip install -e '.[reports]'` o el lock actualizado. Los hashes y fuentes OKX están guardados junto al informe. Los archivos mensuales de funding usan límites UTC+8; el importador completa el extremo UTC con la API pública y exige cobertura sin gaps.

## Primera investigación, conservada como referencia

**Resultado de la primera ronda:** se completaron **200 configuraciones** y **2.000 simulaciones Monte Carlo**. La estrategia seleccionada **NO alcanzó Sharpe ≥ 1,5** en los **18 meses fuera de muestra**. La ejecución con dinero real está deshabilitada en el adaptador. El modo `observe` funciona sin órdenes; el modo `demo` está implementado, pero necesita una cuenta demo configurada para futuros y validación integral de órdenes.

| Evaluación final, marzo 2025–agosto 2026 | Resultado |
|---|---:|
| Sharpe anualizado | −0,102 |
| Retorno neto | −3,17% |
| Drawdown máximo | 15,64% |
| Operaciones long / short | 70 / 54 |
| Monte Carlo: Sharpe p05 / p95 | −1,571 / 1,135 |

Estos resultados corresponden a **futuros Binance como referencia**, no a ejecuciones ni historial de OKX. Ver [reporte completo](reports/run-001/RESULTADOS.md), [protocolo](reports/run-001/protocol.json) y [registro de 200 intentos](reports/run-001/attempts.jsonl).

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock
pip install --no-deps -e .
pytest -q
```

Probado con Python 3.14. El paquete declara Python ≥ 3.12; el lock captura exactamente el entorno utilizado en esta investigación. Docker y CI usan 3.14.

## Conexión OKX

Crear un `.env` local a partir de `.env.example` y completar `OKX_API_KEY`, `OKX_API_SECRET`, `OKX_PASSPHRASE` con claves **demo**. En esta instalación local se reutilizaron únicamente esas tres variables del proyecto anterior, con permiso del usuario. El archivo está excluido de Git y del contexto de Docker, con permisos 0600.

```bash
astra doctor
```

Este comando consulta contrato, configuración y cantidad de posiciones. No envía órdenes, no imprime claves y no modifica la cuenta. Las credenciales reutilizadas autenticaron correctamente en demo. La cuenta encontrada tiene `acctLv=1` (spot) y `posMode=net_mode`, sin posiciones SWAP. Para probar órdenes: usar una cuenta **demo dedicada**, seleccionar **Futures mode** (`acctLv=2`), **net mode**, y apalancamiento **isolated de 1x o 2x** en BTC-USDT-SWAP. No compartir esa cuenta con el bot anterior. El servicio rechaza modos incompatibles y no los cambia automáticamente.

El nombre del instrumento es `BTC-USDT-SWAP`, no `BTC-USDT` spot. La API expresa tamaños en **contratos**; el adaptador consulta `ctVal`, `ctMult`, `lotSz`, `minSz` y `tickSz` y convierte BTC a contratos, redondeando hacia abajo. No se asumen tamaños fijos en producción.

## Servicio

Primero observar señales con datos públicos de OKX:

```bash
astra serve --mode observe --state state/observe.db
# Un ciclo para comprobar arranque y datos:
astra serve --mode observe --state state/observe.db --once
astra health --state state/observe.db
```

Al arrancar se descargan al menos 1.200 velas cerradas para el calentamiento de indicadores. Se conserva el historial local; no se generan entradas retroactivas. Una señal se procesa una sola vez al cierre de la vela y la entrada demo solamente se permite durante los dos minutos siguientes. El estado y el historial se guardan en SQLite, con exclusión de otra instancia sobre el mismo archivo.

Con la cuenta demo preparada:

```bash
astra serve --mode demo --state state/demo.db
```

`demo` envía órdenes con fondos virtuales. Incluye stops y take profits adjuntos en OKX, cierre `reduceOnly`, trailing del stop al cierre horario, conciliación de órdenes/posiciones y freno persistente por drawdown. No se ha realizado una prueba integral de órdenes demo en esta sesión porque la cuenta disponible está en modo spot. `observe` no requiere permisos de trading.

Un timeout de una orden deja una intención persistida antes del envío. El servicio consulta esa orden por su `clOrdId`; nunca reenvía a ciegas. Una orden no encontrada, parcialmente ejecutada, una posición desconocida o la falta de protección requieren conciliación. No borrar el archivo de estado para resolver un incidente: primero revisar la posición y las órdenes en OKX. Los stops en el exchange permanecen cuando el proceso se apaga.

Los errores consecutivos detienen el proceso y dejan el estado. Una interrupción larga puede dejar gaps en el cache: se rechazan datos incompletos en lugar de inventar señales. La recuperación automática de gaps grandes no está implementada. La lógica demo requiere supervisión hasta validar su funcionamiento con órdenes reales de demo, fills parciales y reinicios durante ejecuciones.

## Estrategia y riesgo

1. Ancla de 4h: EMA rápida frente a EMA lenta; filtro opcional de distancia porcentual entre ambas.
2. Señal de 1h: cierre por encima del máximo previo de Donchian para long; por debajo del mínimo previo para short, alineado con el ancla.
3. Entrada en la apertura siguiente en el backtest; primera cotización disponible después del cierre en demo.
4. Stop inicial según ATR; objetivo como múltiplo de la distancia al stop; trailing calculado al cierre, efectivo en la siguiente vela. También se sale por cambio de ancla o duración máxima.
5. Se recalcula el tamaño con el capital disponible y ATR en cada operación. Se arriesga **hasta 2%** nominal al stop, configurable hasta **3%**. El límite de exposición de 1x el capital puede reducir el riesgo efectivo por debajo de ese porcentaje.

El 2% representa presupuesto de pérdida nominal, no porcentaje de dinero invertido ni de margen. Se reserva costo estimado de entrada y salida en el tamaño. Gaps, funding y deslizamientos mayores a lo supuesto pueden superar el presupuesto. Se usa una posición a la vez y un freno por drawdown del 25%; no es una garantía de pérdida máxima. El límite de exposición 1x es distinto del apalancamiento configurado en OKX.

La configuración seleccionada usa EMA 8/60 en 4h, ruptura de 168 velas de 1h, ATR 14, stop de 4 ATR, trailing de 2 ATR, objetivo de 2R y duración máxima de 240 horas. **Fue rechazada en validación.** Se conserva para auditar y probar la infraestructura, no como recomendación rentable.

La adaptación operación a operación se limita al tamaño, ATR, trailing y estadísticas de resultados. **No se reoptimizan parámetros después de cada pérdida** ni se aumenta el riesgo para recuperar. Cambiar reglas luego de observar una operación puede sobreajustar: requiere un nuevo protocolo y datos futuros independientes. Consultar el seguimiento:

```bash
astra review --trades reports/run-001/holdout_trades.csv
```

## Investigación y reproducibilidad

```bash
astra download --start 2021-01-01 --end 2026-09-01
# run-001 ya fue ejecutado y está sellado; este comando lo rechazará:
astra research --data data/BTCUSDT-1h.csv --output reports/run-001 --attempts 200
```

Los ZIP mensuales de velas y funding se verifican contra sus checksums SHA-256 oficiales. `data/manifest.json` registra fuentes, rango y hashes. Los datos grandes no se suben a GitHub; se descargan nuevamente con el comando anterior.

- Datos: enero 2021–agosto 2026; timestamps UTC y barras de 1h completas.
- Primeros 12 meses para calentamiento; desarrollo desde enero 2022 hasta febrero 2025, dividido en tres ventanas cronológicas independientes de simulación, con inicio plano en cada una.
- 200 combinaciones distintas y reproducibles de una familia de estrategia de tendencia (seed 42). No son 200 estrategias conceptualmente independientes.
- Elección exclusivamente con las tres ventanas de desarrollo. Se prefiere que todas tengan al menos 20 trades y no activen el freno. Score: mediana del Sharpe menos 0,25 veces su desvío entre ventanas.
- Prueba final **una sola vez** del 1 de marzo de 2025 al 1 de septiembre de 2026, fin exclusivo: 18 meses, 549 retornos diarios.
- Objetivo principal Sharpe ≥ 1,5. Filtros adicionales declarados antes de la prueba: mínimo de operaciones en ambos sentidos, drawdown, Monte Carlo, DSR aproximado y costos duplicados. Los umbrales se guardan en `protocol.json`.
- Sharpe con retornos diarios mark-to-market, anualización √365 y tasa libre de riesgo asumida cero. Incluye períodos sin operaciones.
- Costos base: 6 bps por lado de comisión y 3 bps por lado de deslizamiento, supuestos configurables y **no una afirmación de las tarifas de tu cuenta**. Funding histórico de Binance, aproximado con precio de apertura como base en vez de mark price.
- Salidas con gaps al peor precio de apertura; stop primero si stop y objetivo se tocan en la misma vela. No se usa una vela de 4h incompleta.
- Monte Carlo: 2.000 caminos de bootstrap por bloques circulares de siete días sobre retornos diarios netos. No es una simulación exacta de nueva ejecución ni reaplica el freno de capital en cada camino.
- Deflated Sharpe aproximado según Bailey y López de Prado, con dispersión de Sharpe de desarrollo, número de búsquedas y momentos no normales. Supone independencia entre intentos y no corrige autocorrelación; es diagnóstico, no certificación. El bootstrap aporta una comprobación adicional de dependencia temporal.

No se hizo selección walk-forward adaptativa que cambie de parámetros en cada ventana. Se evaluó estabilidad de parámetros fijos en ventanas cronológicas y luego un holdout sellado. Los indicadores dentro del holdout se actualizan de forma causal; nunca participan en la elección.

`holdout.lock` impide repetir accidentalmente el test final en la misma carpeta. Crear otra carpeta **no convierte el mismo período en datos independientes**. Los 200 intentos solicitados ya se consumieron; no continuar buscando sobre el holdout conocido. El resultado válido de esta búsqueda es **objetivo no alcanzado**.

Para auditar el mismo candidato sin afirmar una validación nueva:

```bash
astra replay --data data/BTCUSDT-1h.csv --selected configs/selected.json \
  --start 2025-03-01T00:00:00Z --end 2026-09-01T00:00:00Z \
  --output reports/replay
```

## Contenedor y GitHub

```bash
docker compose build
docker compose up -d
docker compose logs -f
docker compose down
```

El contenedor ejecuta `observe` por defecto, como usuario sin privilegios, con filesystem de solo lectura y volumen persistente. Para demo se deben cambiar comando y healthcheck al mismo archivo `state/demo.db`. Cloud: montar secretos como variables de entorno o archivo, mantener volumen persistente, sincronización horaria y una sola réplica por cuenta/estado. No incluir `.env` en imagen ni repositorio. El lock de SQLite solo protege instancias que comparten ese archivo; no coordina múltiples máquinas con distintos volúmenes.

El repositorio incluye pruebas y workflow de CI. Docker no estaba instalado en la máquina de trabajo, por lo que el build local queda sin verificar; el workflow lo construye en GitHub. No se creó ni publicó un repositorio remoto.

```bash
git add .
git diff --cached --stat
# Revisar, crear commit y agregar el remote elegido antes de publicar.
```

## Estructura

| Archivo | Función |
|---|---|
| `src/astra/data.py` | Descarga, checksums, validación de velas/funding |
| `src/astra/strategy.py` | Indicadores causales de 1h/4h |
| `src/astra/engine.py` | Riesgo y simulador con contabilidad neta |
| `src/astra/research.py` | 200 intentos, holdout, Monte Carlo, DSR y reportes |
| `src/astra/okx.py` | Firma V5, metadatos de contratos y órdenes demo |
| `src/astra/service.py` | Servicio, estado SQLite, conciliación y señales |
| `src/astra/cli.py` | Interfaz de comandos |
| `tests/` | Contabilidad, sesgo temporal, límites y resiliencia |

## Fuentes

- [Datos oficiales de futuros Binance](https://github.com/binance/binance-public-data).
- [API oficial OKX V5](https://www.okx.com/docs-v5): autenticación, demo, metadatos SWAP y órdenes.
- [Deflated Sharpe Ratio — Bailey y López de Prado](https://doi.org/10.2139/ssrn.2460551).

Ni Sharpe histórico ni Monte Carlo garantizan rentabilidad futura. Falta validación con datos/costos de OKX y pruebas de ejecución demo antes de considerar dinero real. La simulación no reproduce liquidaciones por mark price, fallos de exchange ni todos los recorridos intrabar.
