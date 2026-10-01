# Segunda prueba en vivo: filtro "smart money" (SM2) sobre v4_hourly, solo BTC

Pre-registro, escrito antes de que exista ningun dato de este tramo. Corre en paralelo al bot de produccion
(`docs/FORWARD_TEST.md`), sin tocarlo y sin arriesgar nada de el. Origen de la idea y de toda la evidencia previa:
`reports/backtest2-v2/SMART_MONEY_FILTERS.md` y `SMART_MONEY_BTC_ONLY.md`.

## Que se congela

- Estrategia: `v4_hourly` con el filtro de entradas `smart_money_signal` (`src/astra/backtest2/exposure_strategies.py`),
  `divergence_min = 1.1`. Elegido por ser el valor con mejor Sharpe en la corrida continua (0.79) y el mas elegido
  (5 de 8 bloques) en la validacion cruzada con purga; no es el que mas gano en total, para no elegir mirando el
  resultado.
- Parametros base: los mismos de `configs/selected.json` (stop_atr, reward, trail, etc.), sin cambios.
- Activo: BTC unicamente. No paso la validacion en ETH/SOL (ver SMART_MONEY_FILTERS.md); esta prueba es la forma
  correcta de seguir evaluandolo sin esa confirmacion, con evidencia que todavia no existe en vez de relajar la regla.
- Inicio de la medicion: **2026-10-01 23:00 UTC**. Todo lo anterior a esta fecha es backtest ya conocido (contexto,
  no evidencia nueva): corrida continua +67.6%, Sharpe 0.79 (SMART_MONEY_BTC_ONLY.md). Solo cuenta lo que pase
  despues de esta fecha.
- **Numero de pruebas (trials) = 1.** Cualquier cambio de la divergencia, del activo o de la logica reinicia esta
  prueba con un pre-registro nuevo.

## Como se mide (distinto del bot real, y por que)

Esta prueba **no usa la cuenta demo de OKX ni modifica el bot**. Es un replay del motor de backtest ya validado
(`ExecutionSimulator`, los mismos tests que protegen el resto del proyecto) sobre datos reales de Binance USD-M
(BTCUSDT, el mismo origen de toda esta rama de investigacion). **Corre en la VM, una vez por dia (04:30 UTC), y no
commitea nada**: el resultado se reescribe en `/opt/astra/forward_smart_money/state.json` (fuera del repo).

- **Por que archivos y no la API en vivo:** `fapi.binance.com` devuelve HTTP 451 desde IPs de EE.UU. (la VM esta en
  Iowa) y el entorno de las rutinas en la nube lo bloquea; `data.binance.vision` (archivos publicos con checksum) responde
  desde ambos. Los archivos de un dia D aparecen despues de que D termina, y el filtro ya usaba el dato de D recien desde
  D+1, asi que el retraso de ~1 dia coincide con la regla del backtest. La prueba se actualiza una vez por dia.
- **Como corre:** `ops/smart_money_forward_run.sh` lanza un contenedor descartable con la imagen del bot (ya trae
  pandas y el resto): no instala nada en el host, no reconstruye la imagen, no toca el servicio `astra-demo`. Tope de 280 MB
  de memoria y 0.5 CPU: si algo sale mal muere ese contenedor, no el bot. Logica en `src/astra/forward_smart_money.py`.
- **Que hace cada corrida:** baja (y cachea, verificando checksum) las velas horarias y el posicionamiento diario que falten,
  arma la serie completa y **vuelve a correr el simulador desde el inicio de la medicion**; solo cuenta lo que pasa desde
  2026-10-01 23:00 UTC. No guarda estado que se pueda corromper: si una corrida falla o se saltea un dia, la siguiente
  se pone al dia sola. Si falta un dia en el medio de la serie de precios, falla fuerte y deja el archivo anterior intacto
  (nunca se rellena un hueco).
- **Free tier de GCP:** misma e2-micro, sin VM/disco/IP nuevos; solo trafico entrante (gratis) y unos pocos MB de cache.
- **Ver el resultado:** `cat /opt/astra/forward_smart_money/state.json` en la VM (equity, retorno, Sharpe, drawdown, lista
  completa de trades, curva diaria) y `log.csv` con una linea por corrida.

Diferencia a favor frente al bot real: no depende de que OKX este arriba, ni de apalancamiento de cuenta ni de rechazos de
ordenes -- mide la estrategia, no la ejecucion. En contra: no es una cuenta ejecutandose en un exchange, es una cuenta
virtual recalculada. Las dos pruebas se complementan, no se reemplazan.

## Aproximaciones conocidas (dichas antes, no descubiertas despues)

- **Funding:** se usa el real de los archivos mensuales de Binance para los meses ya completos y publicados; el mes en curso
  usa funding=0 (todavia no hay archivo) y se corrige solo cuando el mes se completa. Efecto esperado: minimo.
- **Precio:** el del archivo de Binance (el mismo que el backtest), no el de OKX.
- Deslizamiento y comisiones: mismo modelo que el resto de `backtest2` (`impact_k=1.0`, sin calibrar con fills reales).

## Hitos y reglas de decision

| Hito | Que se revisa | Regla |
|---|---|---|
| 10 trades | Que el replay siga corriendo sin errores y el Sharpe no sea muy negativo | Si el Sharpe es negativo con 10 trades, se seguir observando, no se concluye nada todavia |
| 25 trades (~1.5 a 2 años con esta frecuencia reducida) | Primera lectura seria | Si el Sharpe en vivo es negativo, se da por no confirmado y se descarta |
| 50 trades | Evaluacion | Solo si el Sharpe fuera de muestra (este tramo) es positivo y comparable al de la validacion cruzada se vuelve a considerar un camino hacia produccion -- nunca automatico, siempre con revision manual |

Con ~15 trades/año en el backtest (divergencia 1.1, corrida continua), 25 trades son unos 20 meses. Es mas lento
todavia que la prueba del bot principal: por eso corre en paralelo, no en secuencia.

## Reglas no negociables

- Nadie ajusta `divergence_min` ni nada mas mirando estos resultados. Una idea nueva se pre-registra aparte.
- Esto no autoriza nada por si solo. No se despliega en la VM ni se toca `configs/selected.json` aunque el resultado
  sea bueno: haria falta, ademas, pasar por el mismo proceso de revision que cualquier cambio real (tests, revision
  explicita, aprobacion).
