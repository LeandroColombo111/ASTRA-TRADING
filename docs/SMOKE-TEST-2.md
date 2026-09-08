# Prompt de smoke test 2 — modo demo con órdenes

Pegar en Claude Code, parado en la raíz del repo. Presupone que el smoke test 1 pasó y que la cuenta demo de OKX ya está en modo Spot y futuros.

---

```
Contexto: repo ASTRA-TRADING, bot de futuros perpetuos BTC en OKX. La investigación
está cerrada. El smoke test 1 ya validó código, config, modo observe y contenedor.
La cuenta demo de OKX ya fue configurada en modo Spot y futuros (acctLv 2).

Tu tarea es verificar el MODO DEMO, donde el servicio SÍ manda órdenes contra el
capital de prueba de OKX. No investigues, no optimices, no cambies la estrategia.

Config activa: configs/selected.json (v4_hourly, señal 1h, ancla 4h).

DATO CLAVE ANTES DE EMPEZAR: esta estrategia opera ~26 veces por año. Es
esperable que NO se abra ninguna posición durante el test. Ausencia de trades es
comportamiento correcto, no un fallo. Nunca modifiques parámetros para forzar una
entrada.

OBJETIVO
Confirmar que el servicio puede operar en demo de forma segura y desatendida, y
documentar exactamente qué quedó verificado y qué no. Reporte final PASA/FALLA/NO
EJERCITADO por punto.

FASE 0 — Regresión del smoke test 1
1. pytest -q. Esperado: 57 tests en verde (47 originales + 10 de ruteo de config).
2. astra replay --data data/BTCUSDT-1h.csv --output reports/replay-check2 \
     --start "2022-02-05 03:00:00+00:00" --end "2026-09-01 00:00:00+00:00"
   Esperado ±0.01: Sharpe 0.7385, retorno 61.61%, MaxDD 21.97%, 121 trades.
   (Este comando estaba roto en el smoke test 1 y fue corregido; confirmá el arreglo.)

FASE 1 — Cuenta OKX lista
3. astra doctor. Ahora debe dar ready_account_mode: true, account_level "2",
   position_mode "net_mode", orders_sent 0, live_enabled false.
   Reportá contract_value_btc y lot_contracts, los vamos a usar en la fase 2.
   NO cambies ninguna configuración de la cuenta.

FASE 2 — Construcción de órdenes SIN enviar
4. Llamá a astra.okx.entry_plan directamente con la config de producción, el
   instrumento real (client.instrument()) y el equity real de la cuenta demo,
   para side=+1 y side=-1, usando un ATR y un precio actuales. Verificá:
   - ordType "market", tdMode "isolated", posSide "net", instId "BTC-USDT-SWAP"
   - trae attachAlgoOrds con slTriggerPx Y tpTriggerPx (stop y target adjuntos)
   - para largo: stop < precio < target; para corto: target < precio < stop
   - sz es múltiplo de lotSz y >= minSz
   - el riesgo implícito (contratos x ctVal x distancia al stop) está entre 2% y 3%
     del equity, o por debajo si topa el límite de exposición
   NO envíes ninguna de estas órdenes. Es verificación de construcción.
5. Confirmá que entry_plan levanta ValueError si el tamaño queda por debajo del
   mínimo de OKX (probá con un equity artificialmente chico, por ejemplo 50 USDT).

FASE 3 — Demo en vivo
6. astra serve --state state/demo.db --mode demo --once
   Debe completar sin error. Usá un archivo de estado DISTINTO al de observe: el
   servicio calcula un fingerprint con params, riesgo, modo y host y rechaza un
   estado que pertenezca a otra combinación. Confirmá ese rechazo intentando
   --mode demo sobre state/observe.db: debe fallar con ValueError.
7. Dejalo corriendo en background 15 minutos: astra serve --state state/demo.db --mode demo
8. Durante esa ventana verificá:
   - astra health --state state/demo.db devuelve healthy
   - la tabla events registra actividad y CERO errores
   - si no hubo señal, no debe existir ninguna fila order_intent. Reportá como
     "NO EJERCITADO" el envío de órdenes, no como fallo.
   - si SÍ hubo una entrada: verificá contra la API de OKX que la posición existe,
     que hay un algo order de stop-loss asociado con el mismo clOrdId + sufijo 's',
     y que el tamaño coincide con lo que registró el evento.

FASE 4 — Seguridad de reinicio (la ruta de código de mayor riesgo)
9. Con el servicio corriendo, matalo con SIGKILL (no SIGTERM) para simular una
   caída sucia. Reiniciálo sobre el mismo estado y confirmá que:
   - arranca sin intervención manual
   - si había un intent pendiente, ejecuta reconcile_intent y resuelve el estado
     de la orden contra OKX en vez de reenviarla
   - no duplica ninguna orden (comparar clOrdId en events con los fills de OKX)
10. Confirmá que el lock de instancia única sigue funcionando con el estado de demo.

FASE 5 — Guardas de seguridad
Verificá por LECTURA DE CÓDIGO, no provocándolas, que estas condiciones detienen
el servicio, y reportá el número de línea de cada una en src/astra/service.py:
11. apalancamiento aislado mayor a 2x
12. posición encontrada que el bot no registró como propia
13. orden abierta externa (clOrdId que no empieza con 'ast')
14. posición sin stop-loss confirmado en el exchange
15. cotización de OKX con más de 30 segundos de antigüedad
16. hueco en la caché de velas

FASE 6 — Contenedor en modo demo
17. docker compose run -d --name astra-demo astra serve --mode demo --state /app/state/demo.db
18. Esperar el healthcheck, confirmar "healthy" y logs sin errores. Después bajarlo.

FASE 7 — Brechas conocidas, confirmar que siguen abiertas
19. Confirmá por lectura de código que estas dos siguen SIN implementar, y explicá
    en una línea por qué cada una importa antes de poner dinero real:
    - el corte por drawdown usa el equity crudo del exchange, así que un depósito
      infla el pico y desactiva el kill switch (service.py, cálculo de peak/halted)
    - no hay medición time-weighted; con aportes periódicos el saldo sube aunque
      la estrategia pierda
    NO las implementes en este test. Solo confirmá y documentá.

PROHIBIDO
- Modificar parámetros de la estrategia, umbrales o el modelo de costos para
  provocar una entrada. Si no hay señal, se reporta NO EJERCITADO.
- Desactivar, saltear o "ablandar" cualquier guarda de seguridad para que una fase
  pase.
- Cambiar configuración de la cuenta de OKX.
- Imprimir, copiar o commitear el contenido de .env.
- Habilitar modo live o tocar approved_for_live. El servicio está bloqueado en demo
  por construcción (run() usa OKX(demo=True) hardcodeado); no lo puentees.
- Modificar reports/ (registro de auditoría).
- Cerrar posiciones a mano si el bot abrió alguna: dejalas y reportá.

ENTREGABLE
Tabla PASA / FALLA / NO EJERCITADO por cada punto del 1 al 19, con los valores
medidos. Separá explícitamente lo que quedó verificado de lo que no se pudo
ejercitar por falta de señal. Cerrá con la lista de lo que falta antes de dejarlo
corriendo desatendido con dinero real. Si algo falla, explicá la causa; no propongas
bajar el estándar.
```

---

## Notas para vos, no para el prompt

- **La fase 2 es la importante.** Como la estrategia opera poco, probablemente no veas una orden real durante el test. Verificar `entry_plan` sin enviar te da la garantía de que cuando llegue la señal, la orden va a salir con stop y target adjuntos y con el tamaño correcto.
- **La fase 4 es la de mayor riesgo real.** Un `SIGKILL` a mitad de un POST es el escenario que rompe los bots: reenviar una orden que ya se ejecutó. El código persiste el intent antes de la escritura de red y reconcilia en vez de reintentar; esto lo verifica.
- **La fase 19 no es burocracia.** Son las dos brechas que ya conocemos, y quiero que queden escritas en el reporte del test para que no se olviden cuando pases a plata real.
