# Prompts operativos — dejar corriendo y chequear

Dos prompts para Claude Code. El primero se corre una vez; el segundo, cada dos o tres días.

---

## Prompt A — Dejarlo corriendo

```
Contexto: repo ASTRA-TRADING, bot de futuros perpetuos BTC en OKX. Los smoke tests 1
y 2 ya pasaron. La cuenta demo está configurada (acctLv 2, net mode, apalancamiento
aislado 2x). El Dockerfile fue corregido: el modo y el archivo de estado ahora vienen
de las variables ASTRA_MODE y ASTRA_STATE, que el healthcheck y el proceso servido
leen igual.

Tu tarea es dejar el servicio corriendo en MODO DEMO de forma desatendida y registrar
una línea base para poder chequearlo después. No investigues, no optimices, no cambies
la estrategia ni la configuración.

PASOS
1. pytest -q. Esperado: 67 tests en verde. Si falla algo, PARÁ y reportá.
2. Reconstruir la imagen con el arreglo del healthcheck:
   docker compose build --no-cache
3. Confirmar que la cuenta sigue lista: astra doctor
   Esperado: ready_account_mode true, account_level "2", live_enabled false.
4. Levantar el servicio en demo:
   docker compose run -d --name astra-demo \
     -e ASTRA_MODE=demo -e ASTRA_STATE=/app/state/demo.db astra
5. Esperar el start_period del healthcheck (180s) y confirmar con docker ps que el
   contenedor figura "healthy". Verificá además, desde adentro, que el healthcheck
   y el proceso miran el MISMO archivo:
   docker exec astra-demo sh -c 'echo $ASTRA_STATE'
   docker exec astra-demo astra health --state "$(docker exec astra-demo sh -c 'echo $ASTRA_STATE')"
6. Escribir una línea base en docs/RUNTIME-BASELINE.json con:
   - timestamp UTC de arranque
   - nombre e id del contenedor, y el volumen usado
   - ASTRA_MODE y ASTRA_STATE efectivos
   - equity de la cuenta demo al arrancar (client.equity())
   - sha256 de configs/selected.json
   - último candle cerrado (last_closed del estado) y conteo inicial de eventos
   - la salida completa de astra doctor
7. Confirmar en el estado que NO hay ninguna posición abierta ni intent pendiente al
   arrancar. Si los hubiera, reportalo y no sigas.

ADVERTENCIA QUE DEBÉS DEJAR ESCRITA EN EL REPORTE
El servicio está diseñado para detenerse antes que operar a ciegas: el loop aborta
tras 3 ciclos fallidos consecutivos y compose reintenta 3 veces. Puede quedar
detenido sin aviso. Por eso hace falta el chequeo periódico.

PROHIBIDO
- Cambiar parámetros, umbrales, configuración de la cuenta o el modo de ejecución.
- Habilitar modo live o tocar approved_for_live.
- Imprimir o commitear el contenido de .env.
- Modificar reports/.

ENTREGABLE
Confirmación de cada paso, la ruta de la línea base escrita, y el comando exacto que
hay que correr para chequearlo después.
```

---

## Prompt B — Chequeo periódico (correr cada 2-3 días)

```
Contexto: repo ASTRA-TRADING. Hay un servicio corriendo en modo demo contra la cuenta
de prueba de OKX, arrancado según docs/RUNTIME-BASELINE.json.

Tu tarea es un chequeo de salud DE SOLO LECTURA. No arregles nada, no reinicies nada,
no cambies configuración. Si algo está mal, tu trabajo es diagnosticarlo y reportarlo,
no repararlo.

DATO CLAVE: la estrategia opera unas 26 veces por año, o sea ~2 por mes. Que no haya
ninguna operación entre chequeos es lo NORMAL. Nunca interpretes ausencia de trades
como una falla, y nunca toques parámetros para provocar una.

QUÉ VERIFICAR
1. Leé docs/RUNTIME-BASELINE.json para saber contra qué comparás.
2. ¿El contenedor sigue vivo? docker ps -a --filter name=astra-demo
   Registrá estado, uptime y estado del healthcheck.
3. ¿El heartbeat está fresco? astra health con el ASTRA_STATE del contenedor.
   Un heartbeat de más de 3 minutos significa proceso muerto o trabado.
4. ¿Está procesando velas? Compará last_closed contra la línea base. Debería haber
   avanzado aproximadamente una vela por hora transcurrida. Si el heartbeat está
   fresco pero last_closed no avanzó en horas, el servicio está vivo pero atascado:
   eso es peor que estar caído, reportalo con prioridad.
5. Eventos nuevos desde la línea base: contá por tipo (kind) en la tabla events.
   Prestá atención a cualquier evento de error, skipped_gap o exit_reason.
6. ¿Hubo alguna operación? Buscá order_intent, order_reconciled, flat_confirmed.
   - Si NO hubo: reportá "sin operaciones, comportamiento esperado".
   - Si SÍ hubo, verificá contra la API de OKX:
     * la posición existe y el tamaño coincide con el evento registrado
     * hay un algo order de stop-loss vivo con el clOrdId de la posición + sufijo 's'
     * el riesgo implícito (contratos x ctVal x distancia entrada-stop) está entre
       2% y 3% del equity que había al abrir, o por debajo si topó exposición
     * si ya cerró: el motivo de salida y el PnL neto
7. Equity actual de la cuenta demo contra la de la línea base. Reportalo como PnL de
   papel, NUNCA como validación de la estrategia.
8. Revisá docker compose logs desde el último chequeo por cualquier línea
   "Service cycle failed" o excepción.

SI EL SERVICIO ESTÁ CAÍDO
No lo reinicies. Diagnosticá primero: buscá en los logs la excepción que lo detuvo,
identificá cuál de las guardas de service.py se disparó, y reportá la causa raíz con
el número de línea. Recién después preguntá si querés que lo reinicie.

PROHIBIDO
- Reiniciar, reconstruir o modificar el servicio, la config o la cuenta.
- Cerrar posiciones o cancelar órdenes a mano.
- Cambiar parámetros para provocar una operación.
- Imprimir o commitear el contenido de .env.
- Interpretar la ausencia de trades como fallo.

ENTREGABLE
Un bloque de estado breve y comparable entre chequeos:

  ESTADO: OK | ATENCION | CAIDO
  Corriendo desde: <fecha>  (uptime)
  Heartbeat: <edad>
  Velas procesadas desde el último chequeo: N (esperadas ~M)
  Operaciones: N  (detalle si las hubo)
  Errores: N  (detalle si los hubo)
  Equity demo: <actual> vs <línea base>  (PnL de papel, no validación)
  Acción requerida: <ninguna | descripción>

Si todo está bien, que sea corto. Guardá el resultado en docs/checks/<fecha>.md para
tener el historial.
```

---

## Notas para vos, no para los prompts

- **El punto 4 del prompt B es el que detecta la falla silenciosa.** Un proceso vivo con heartbeat fresco pero que dejó de procesar velas se ve sano en cualquier monitoreo superficial. Comparar `last_closed` contra el reloj es lo único que lo revela.
- **El prompt B prohíbe reiniciar a propósito.** Si el bot se detuvo, se detuvo por una razón — alguna de las seis guardas. Reiniciar sin leer cuál fue tira la única evidencia que tenés.
- Podés automatizar el prompt B como tarea programada cada 2-3 días. Si preferís, decime y te lo armo.
