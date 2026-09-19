# Limite de tiempo dinamico

## 1. Cuanto pesa hoy el limite de tiempo (bot original, corrida continua, sin cortes)

| activo | trades | salen por stop | por objetivo | por tendencia o tiempo | duracion mediana (h) | trades con >= 480h |
|---|---|---|---|---|---|---|
| BTC | 104 | 74 | 29 | 1 | 24 | 1 |
| ETH | 91 | 69 | 22 | 0 | 28 | 0 |
| SOL | 98 | 76 | 22 | 0 | 22 | 0 |

## 2. Limite dinamico (14 ventanas de 90d, warmup 250d, valores fijos y vecinos)

Hipotesis fijadas antes de correr. Limite = 480h x ratio^(-gamma), ratio = vol de 7d / vol de 60d, acotado a [240h, 960h]; stops y objetivos sin tocar.

- **D1 (gamma > 0):** volatilidad alta acorta el limite, calma lo alarga. Justificacion: el clustering dura 10 a 20 dias, en un regimen agitado la tesis del trade se resuelve antes; en calma la tendencia necesita mas tiempo.
- **D2 (gamma < 0), contraste:** el efecto opuesto.


**BTC**

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| original (480h fijo) | 0.52 / 1.00 | 5/14 | 4 | 56.5% | -11.3% | 15.8% | 16.6% |
| D1 gamma=0.5 | 0.51 / 1.00 | 5/14 | 4 | 56.1% | -11.3% | 15.8% | 16.5% |
| D1 gamma=1.0 | 0.43 / 1.00 | 5/14 | 4 | 49.8% | -11.3% | 15.8% | 16.3% |
| D1 gamma=1.5 | 0.43 / 1.00 | 5/14 | 4 | 49.4% | -11.3% | 15.8% | 16.1% |
| D2 gamma=-0.5 | 0.53 / 1.00 | 5/14 | 4 | 57.0% | -11.3% | 15.8% | 16.6% |
| D2 gamma=-1.0 | 0.50 / 1.00 | 5/14 | 4 | 55.6% | -11.3% | 15.8% | 16.7% |
| D2 gamma=-1.5 | 0.52 / 1.03 | 5/14 | 4 | 56.7% | -11.3% | 15.8% | 16.7% |
| HODL | 0.79 / 0.61 | 6/14 | - | 191.6% | -27.1% | - | 100% |

**ETH**

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| original (480h fijo) | -0.14 / 0.34 | 2/14 | 5 | 17.4% | -9.4% | 9.4% | 12.2% |
| D1 gamma=0.5 | -0.14 / 0.34 | 2/14 | 5 | 17.4% | -9.4% | 9.4% | 12.2% |
| D1 gamma=1.0 | -0.14 / 0.34 | 2/14 | 5 | 17.4% | -9.4% | 9.4% | 12.2% |
| D1 gamma=1.5 | -0.14 / 0.34 | 2/14 | 5 | 17.4% | -9.4% | 9.4% | 12.2% |
| D2 gamma=-0.5 | -0.14 / 0.34 | 2/14 | 5 | 17.4% | -9.4% | 9.4% | 12.2% |
| D2 gamma=-1.0 | -0.14 / 0.34 | 2/14 | 5 | 17.4% | -9.4% | 9.4% | 12.2% |
| D2 gamma=-1.5 | -0.14 / 0.34 | 2/14 | 5 | 17.4% | -9.4% | 9.4% | 12.2% |
| HODL | 0.27 / -0.53 | 6/14 | - | 5.6% | -50.1% | - | 100% |

**SOL**

| variante | Sharpe media / mediana | ventanas >=1.5 | negativas | ganancia total | peor ventana | DD encadenado | % en mercado |
|---|---|---|---|---|---|---|---|
| original (480h fijo) | -0.07 / 0.02 | 2/14 | 7 | 16.7% | -8.7% | 18.2% | 13.4% |
| D1 gamma=0.5 | -0.07 / 0.02 | 2/14 | 7 | 16.7% | -8.7% | 18.2% | 13.4% |
| D1 gamma=1.0 | -0.07 / 0.02 | 2/14 | 7 | 16.7% | -8.7% | 18.2% | 13.4% |
| D1 gamma=1.5 | -0.07 / 0.02 | 2/14 | 7 | 16.7% | -8.7% | 18.2% | 13.4% |
| D2 gamma=-0.5 | -0.07 / 0.02 | 2/14 | 7 | 16.7% | -8.7% | 18.2% | 13.4% |
| D2 gamma=-1.0 | -0.07 / 0.02 | 2/14 | 7 | 16.7% | -8.7% | 18.2% | 13.4% |
| D2 gamma=-1.5 | -0.07 / 0.02 | 2/14 | 7 | 16.7% | -8.7% | 18.2% | 13.4% |
| HODL | 0.68 / 0.71 | 4/14 | - | 237.9% | -46.2% | - | 100% |

## 3. Conclusiones

- **El limite de tiempo no actua.** En la corrida continua los trades duran 22 a 28 horas de mediana y solo 1 de 104
  (BTC), 0 de 91 (ETH) y 0 de 98 (SOL) llegan a las 480h. Casi todo cierra por stop (71% a 78%) o por objetivo (22% a 29%).
  Hacer dinamico un limite que casi nunca se alcanza no puede cambiar el resultado.
- **Resultado medido:** ETH y SOL identicos al original en las 6 variantes; BTC cambia en +-7 puntos de ganancia total por
  un unico trade (49.4% a 57.0% contra 56.5%), sin patron entre D1 y D2 y sin tocar la mediana de Sharpe. **No adoptar.**
- **Para liberar capital no hace falta:** el bot esta fuera del mercado 83% a 88% del tiempo y cada trade libera el capital
  en aproximadamente un dia por stop u objetivo.
- **Lo que si seria una pregunta distinta:** un limite MUCHO mas corto (por ejemplo 24 a 96h) que cierre trades que se
  quedan sin moverse. No se probo aca para no sumar mas variantes sin necesidad; se puede hacer si se quiere.

