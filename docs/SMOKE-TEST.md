# Prompt de smoke test — ASTRA-TRADING

Pegar en Claude Code, parado en la raíz del repo.

---

```
Contexto: este repo es ASTRA-TRADING, un bot de trading de futuros perpetuos sobre
BTC en OKX. La investigación ya está hecha y cerrada. Tu tarea es SOLO verificar que
el servicio levanta y funciona correctamente en modo observación. No investigues, no
optimices, no cambies la estrategia.

La configuración activa es configs/selected.json (estrategia v4_hourly: señal 1h,
ancla 4h). configs/selected_v1_deprecated.json es una versión vieja y fallida que se
conserva solo para auditoría; no debe usarse.

OBJETIVO
Dejar el servicio corriendo en modo observe (no manda órdenes) y confirmar con
evidencia que funciona. Al final, un reporte de PASA/FALLA por cada punto.

FASE 1 — Entorno y código
1. Crear/activar el venv, instalar: pip install -r requirements.lock && pip install --no-deps -e .
2. Correr pytest -q. Esperado: 47 tests en verde.
3. Verificar que .env está ignorado por git: git check-ignore -v .env debe devolver
   una coincidencia. NUNCA imprimas el contenido de .env ni sus valores.
4. Verificar que no hay secretos en lo versionado: git add -A --dry-run y revisar que
   no aparezca .env ni ningún archivo con credenciales.

FASE 2 — Configuración
5. Cargar configs/selected.json y confirmar exactamente:
   - strategy = "v4_hourly"
   - params = fast 40, slow 300, breakout 720, atr_period 24, stop_atr 3.0,
     trail_atr 3.0, reward 3.0, min_trend 0.0, max_hours 480, trail_start_r 2.0
   - risk = fraction 0.02, fee_bps 5.0, slippage_bps 3.0, max_drawdown 0.25
   - approved_for_live = false
   Si algo no coincide, PARÁ y reportá. No lo "arregles".
6. Confirmar que astra.service.strategy_for("v4_hourly") devuelve HourlyParams y
   astra.v4_hourly.features, y que strategy_for("cualquier-cosa") lanza ValueError.

FASE 3 — Backtest de verificación
7. Correr el backtest con la config de producción sobre data/BTCUSDT-1h.csv en el
   rango de reports/v4-hourly-01/protocol.json (fold_bounds primero y último).
   Esperado, con tolerancia de ±0.01:
   - Sharpe 0.739, retorno total 61.6%, MaxDD 22.0%, 121 trades, halted = False
   - riesgo efectivo por trade: medio 1.94%, máximo 2.00%
   Estos números son con costos taker. Si difieren, reportá la diferencia; NO ajustes
   nada para que coincidan.

FASE 4 — Conectividad OKX (requiere credenciales DEMO en .env)
8. Correr: astra doctor
   Debe reportar ready_account_mode true, orders_sent 0, live_enabled false.
   Si el modo de cuenta no está listo, reportá qué falta. NO cambies configuración
   de la cuenta.

FASE 5 — Servicio en modo observe
9. Correr un tick único: astra serve --state state/smoke.db --mode observe --once
   Debe descargar el warmup (1600 velas horarias), calcular la señal y salir sin error.
10. Verificar en state/smoke.db que la tabla events NO contiene ninguna fila de tipo
    'order_intent' ni 'order_reconciled'. En observe no se manda nada. Si hay alguna,
    es un fallo grave: pará y reportá.
11. Levantar el servicio en background y esperar ~90 segundos:
    astra serve --state state/smoke.db --mode observe
12. Correr: astra health --state state/smoke.db. Debe imprimir "healthy".
13. Verificar el lock de instancia única: con el servicio corriendo, lanzar un segundo
    astra serve sobre el MISMO --state. Debe fallar (fcntl.flock). Si arrancan dos
    instancias, es un fallo grave.
14. Frenar el servicio con SIGTERM y confirmar que cierra limpio.

FASE 6 — Contenedor
15. docker build -t astra-test .
16. docker compose up -d, esperar el start_period del healthcheck (180s) y verificar
    que el contenedor queda "healthy": docker compose ps
17. docker compose logs para confirmar que registra señales y no errores.
18. docker compose down (el volumen astra-state persiste, está bien).

PROHIBIDO
- Cambiar umbrales, gates, parámetros de la estrategia o el modelo de costos.
- Habilitar modo live o tocar el flag approved_for_live.
- Imprimir, copiar o commitear el contenido de .env.
- Modificar los reportes en reports/ (son registro de auditoría).
- "Arreglar" un check que falla relajándolo. Si algo falla, reportalo tal cual.
- Mandar órdenes reales. El servicio está bloqueado en demo por construcción
  (run() usa OKX(demo=True) hardcodeado); no intentes puentearlo.

ENTREGABLE
Una tabla con PASA/FALLA por cada punto del 1 al 18, los valores medidos donde
aplique, y una lista de lo que haga falta resolver antes de dejarlo corriendo
desatendido. Si algo falla, explicá la causa; no propongas bajar el estándar.
```

---

## Notas para vos, no para el prompt

- Los puntos 8 en adelante necesitan credenciales **demo** de OKX en `.env`. Si todavía no las generaste, el smoke test se corta ahí y las fases 1 a 3 igual son útiles.
- El punto 13 (lock de instancia única) es el que importa para la nube: confirma que no vas a poder correr dos réplicas peleándose por el estado.
- El punto 10 es la garantía de que observe no manda nada.
