# "Smart money": diagnostico de posicionamiento (OI, long/short, volumen tomador)

**Esto NO es un backtest con la metodologia del proyecto.** Los endpoints publicos de OKX para open interest, ratio long/short y volumen tomador tienen muy poca historia (72 a 180 dias, topeados del lado del servidor; se confirmo probando la paginacion). Con eso no alcanza para warmup de 250 dias ni para 14 ventanas de 90 dias, y ni siquiera cubre un ciclo completo de mercado. Lo que sigue son correlaciones simples sobre la ventana disponible, para ver si hay algo que valga la pena seguir midiendo, NO una señal lista para usar.

Datos: OI 100 dias (2026-06-24 a 2026-10-01), ratio long/short cuentas 180 dias (2026-04-05 a 2026-10-01), top traders 100 dias, volumen tomador 72 dias.

## 1. El ratio long/short de cuentas retail, hoy, es contrarian o confirma la tendencia?

Hipotesis "smart money" clasica: cuando el publico esta muy cargado de un lado (ratio extremo), suele ser señal de reversion, no de continuidad. Se mide la correlacion entre el ratio de HOY y el retorno del dia SIGUIENTE (para que sea causal, nunca mirar el futuro).

- Observaciones: 148 dias
- Correlacion ratio(t) vs retorno(t+1): -0.07

| ratio long/short (tercil) | retorno medio del dia siguiente | dias |
|---|---|---|
| bajo (mas cortos) | 0.41% | 51 |
| medio | -0.07% | 49 |
| alto (mas largos) | -0.03% | 48 |

## 2. Variacion del open interest: confirma o contradice el movimiento del precio?

Hipotesis clasica de futuros: precio sube + OI sube = posiciones nuevas entrando (conviccion real); precio sube + OI baja = cierre de cortos (short covering, menos solido). Se mide sobre el mismo dia (no es una señal de entrada causal, es diagnostico de que paso).

- Correlacion variacion OI vs variacion precio (mismo dia): 0.09

| | precio sube | precio baja |
|---|---|---|
| OI sube | 21 dias | 13 dias |
| OI baja | 16 dias | 18 dias |

## 3. Volumen tomador: compradores vs vendedores agresivos

Esto SI es order flow real (lado agresor), pero solo hay 72 dias. Se mide si el desbalance comprador/vendedor de HOY se relaciona con el retorno de MAÑANA.

- Observaciones: 40 dias
- Correlacion desbalance tomador(t) vs retorno(t+1): 0.22

## Conclusion

Con 72 a 180 dias de historia ninguna de estas correlaciones es confiable: son 2 a 6 meses de un unico tramo de
mercado, sin ciclos alcistas y bajistas distintos, muy lejos del minimo que el proyecto exige en cualquier otro
hallazgo (14 ventanas de 90 dias, 3 activos, valores vecinos). No se puede ni sugerir una regla a partir de esto, y
mucho menos probarla con la disciplina habitual -- este diagnostico no reemplaza eso, solo muestra si hay algo
minimamente interesante para seguir acumulando.

**Camino recomendado si esto interesa:** empezar a archivar estos tres endpoints a diario (igual que se hizo con
`_reference_price` para calibrar el deslizamiento) y recien evaluar una regla real cuando haya 1 a 2 anos de historia
propia. Pedirle una señal de entrada a 2-6 meses de datos de un instrumento que ya mostro ser sensible a sobreajuste
con AÑOS de historia (ver reports/backtest2-v2/README.md y PURGED_CV.md) seria repetir el mismo error, agravado.

