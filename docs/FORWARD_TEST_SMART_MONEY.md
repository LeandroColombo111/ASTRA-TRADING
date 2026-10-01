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

Esta prueba **no usa la cuenta demo de OKX ni la VM**. Es un reemplazo (replay) del motor de backtest ya validado
(`ExecutionSimulator`, los mismos 143 tests que protegen el resto del proyecto), alimentado con precios y datos de
posicionamiento reales y actualizados de Binance (BTC-USDT, el mismo origen usado en toda esta rama de
investigacion). En cada corrida:
1. Se arma la serie de precios horaria completa (archivo historico + las velas que falten hasta la hora actual,
   bajadas en vivo de la API publica de Binance Futures).
2. Se arma la serie de posicionamiento diario (archivo historico + el dato de hoy, bajado en vivo de los endpoints
   publicos `topLongShortPositionRatio` y `globalLongShortAccountRatio` de Binance).
3. Se corre el simulador desde bastante antes del inicio de la medicion (para que los indicadores ya esten
   convergidos) pero **solo se cuenta como resultado lo que pasa desde el 2026-10-01 23:00 UTC en adelante**.
4. El resultado (equity, posicion abierta si la hay, trades) se guarda en `reports/forward_smart_money/state.json`
   y se commitea.

Diferencia a favor de esta prueba frente al bot real: no depende de que OKX este arriba, de apalancamiento de cuenta
ni de rechazos de ordenes -- mide la estrategia, no la ejecucion. Diferencia en contra: no es dinero (ni siquiera
demo) ejecutandose en un exchange real, es una cuenta virtual recalculada cada hora. Las dos pruebas se complementan,
no se reemplazan.

## Aproximaciones conocidas (dichas antes, no descubiertas despues)

- Las velas mas recientes (las que todavia no estan en el archivo historico descargado) no tienen funding real
  todavia disponible de la API publica usada aqui; se usa funding=0 para esas pocas velas. Efecto esperado:
  minimo (el funding ya se vio que es un costo chico comparado con el resto).
- Deslizamiento y comisiones: mismo modelo que el resto de `backtest2` (`impact_k=1.0`, sin calibrar con fills
  reales), igual que el bot principal.

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
