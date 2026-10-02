# Tercera prueba en vivo: v4_hourly con mas riesgo (3 % por operacion, freno de caida 40 %)

Pre-registro, escrito antes de que exista ningun dato de este tramo. Corre en paralelo al bot de produccion (`docs/FORWARD_TEST.md`) y a la prueba del
filtro smart-money (`docs/FORWARD_TEST_SMART_MONEY.md`), sin tocar el bot ni la cuenta demo.

## Que se congela

- Estrategia: `v4_hourly` con los parametros de `configs/selected.json`, sin cambios (sin filtro smart-money, sin otras reglas).
- **Riesgo por operacion: 3 %** del capital (el actual es 2 %; 3 % es el maximo que acepta la validacion de `Risk`).
- **Freno de caida: 40 %** (el actual es 25 %). El bot deja de operar si la caida desde el maximo supera ese valor.
- Activo: BTC unicamente. Inicio de la medicion: **2026-10-02 06:00 UTC**. Solo cuenta lo que pase despues.
- **Numero de pruebas (trials) = 1.** Cualquier cambio de estos valores reinicia la prueba con un pre-registro nuevo.

## Origen y advertencias

Salio de `reports/backtest2-v2/` (barrido de riesgo, 2026-10-02): 3 % con freno 40 % dio ~13,8 % anual en 2020-2026 (contra 5,4 % del actual) con caida maxima
de 31,5 %, y ~21,8 % anual en 2017-2019 con 17,7 % de caida. Advertencias: la mejora viene sobre todo del freno (un solo episodio de caida en 2020-2026, no robusto),
las variantes se miraron sobre los mismos datos de siempre, y mas riesgo por operacion escala retorno y caida, no agrega ventaja. **No es evidencia hasta que haya
operaciones en vivo.**

## Como se mide

Igual que la segunda prueba: replay del motor de backtest (`ExecutionSimulator`) sobre archivos de Binance USD-M (BTCUSDT), una vez por dia (04:50 UTC) en la VM, en un
contenedor descartable (280 MB de memoria, 0,5 CPU), **sin commits**. Resultado reescrito en `/opt/astra/forward_higher_risk/state.json` y una linea por corrida en
`log.csv`. Codigo: `src/astra/forward_higher_risk.py`. Cada corrida calcula tambien un **control**: la configuracion actual (2 %, freno 25 %) sobre los mismos datos,
para comparar sin depender del mercado.

## Hitos y reglas

- 10 / 25 / 50 operaciones. Con menos de 10 no se saca ninguna conclusion de rendimiento.
- No se ajusta nada segun resultados en vivo. Si la caida de esta variante supera 30 %, se anota, no se cambia el limite.
- Para considerarla mejor que la actual debe superar al control en el mismo periodo **y** mantener la caida dentro de lo modelado (< 35 %). Aun asi, cualquier paso al
  bot real exige un pre-registro nuevo y la revision completa (`approved_for_live` sigue en false).
- Costo: misma e2-micro del free tier, trafico solo entrante, unos MB de disco.
