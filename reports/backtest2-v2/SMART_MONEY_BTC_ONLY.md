# "Smart money" (SM2) evaluado solo en BTC, sin exigir que se sostenga en ETH/SOL

El bot solo opera BTC; ETH/SOL se usan en el resto del proyecto como control contra el sobreajuste, no porque el bot los necesite. Si BTC tiene una estructura mas sostenida en el tiempo que justifique tratarlo distinto, la prueba que corresponde no es "relajar la regla", es una validacion mas exigente DENTRO de BTC: elegir el valor de divergencia con datos que no incluyen el tramo que se mide, en vez de con el valor que ya vimos que funciona en todo el historial.

## 1. Corrida continua (todo el historial de una pasada, no por ventanas)

| variante | Sharpe | ganancia total | DD max | trades | % en mercado |
|---|---|---|---|---|---|
| original | 0.43 | 37.2% | 26.4% | 125 | 12.1% |
| SM2 divergencia >= 1.0 | 0.74 | 66.2% | 26.5% | 81 | 8.8% |
| SM2 divergencia >= 1.1 | 0.79 | 67.6% | 26.3% | 73 | 8.2% |
| SM2 divergencia >= 1.25 | 0.68 | 47.3% | 26.2% | 51 | 7.1% |

## 2. Validacion cruzada con purga y embargo, solo en BTC (8 bloques, embargo 120 dias a cada lado)

Para cada bloque: se elige la divergencia con el Sharpe pooled de TODO lo que queda antes y despues del bloque (nunca con el bloque que se mide), con un margen de 120 dias a cada lado para no filtrar informacion por la memoria de los indicadores ni por trades que cruzan el borde. Se compara contra el valor fijo de produccion (sin filtro) en los mismos bloques.

| bloque | divergencia elegida | Sharpe en muestra | Sharpe fuera (elegido) | ganancia fuera (elegido) | Sharpe fuera (produccion) | ganancia fuera (produccion) |
|---|---|---|---|---|---|---|
| 2020-09-07 | 1.25 | 0.73 | 1.45 | 3.8% | 1.34 | 20.9% |
| 2021-06-07 | 1.0 | 0.81 | -0.65 | -5.1% | -0.33 | -3.8% |
| 2022-03-07 | 1.1 | 0.64 | 1.23 | 7.5% | 0.15 | 0.9% |
| 2022-12-05 | 1.0 | 0.48 | 1.14 | 11.5% | 0.94 | 9.3% |
| 2023-09-04 | 1.1 | 1.15 | 2.58 | 44.5% | 2.15 | 36.5% |
| 2024-06-03 | 1.1 | 1.65 | -1.87 | -21.5% | -1.86 | -21.6% |
| 2025-03-03 | 1.1 | 1.20 | 1.04 | 11.0% | 0.84 | 8.7% |
| 2025-12-01 | 1.1 | 0.87 | 2.21 | 31.9% | 1.70 | 22.7% |

Elegido por bloque: Sharpe fuera media 0.89 / mediana 1.19, ganancia compuesta 96.3%. Produccion (sin filtro): 0.62 / 0.89, 82.9%. corr(Sharpe en muestra, fuera) = -0.46.

## Lectura

- **Si, el % de ganancia mejora, y no es un artefacto.** Corrida continua: 37.2% original contra 66.2%-67.6% con el
  filtro (divergencia 1.0 o 1.1). Se corrigio ademas un error propio antes de confiar en el numero: el relleno hacia
  adelante del dato diario no tenia limite, asi que durante el hueco real de Binance (316 dias, 2021-12-31 a
  2022-12-13) el filtro usaba un valor de hasta casi un año de antiguedad. Con el limite corregido (2 dias de
  vigencia, despues se trata como sin dato) el resultado casi no cambio, asi que la mejora no dependia de ese error.
- **La validacion cruzada DENTRO de BTC (purga + embargo, 8 bloques) tambien favorece al filtro.** Eligiendo la
  divergencia con datos de antes y despues de cada bloque (nunca con el bloque que se mide): gana en 6 de 8 bloques
  o empata, con ganancia compuesta de 96.3% contra 82.9% de produccion sin filtro en los mismos bloques. Es la
  prueba mas parecida a "fuera de muestra" que se puede hacer sin otro activo.
- **Pero hay una señal de alarma que no desaparece.** La correlacion entre el Sharpe en muestra (con el que se elige
  la divergencia) y el Sharpe fuera del bloque es NEGATIVA (-0.46), el mismo patron que ya aparecio en
  PURGED_CV.md para stop_atr/reward y min_trend. Eso sugiere que la mejora no viene de "elegir bien" la divergencia
  especifica, sino de que CUALQUIERA de los tres valores probados (1.0, 1.1, 1.25) tiende a ayudar la mayoria de las
  veces. Es una distincion importante: el filtro parece aportar algo, pero no se puede confiar en el mecanismo de
  seleccion del valor exacto.
- **Sigue sin tener una explicacion economica verificada, solo plausible.** La hipotesis de que BTC tiene mas
  participacion institucional real (y por eso el posicionamiento de los grandes traders significa algo distinto que
  en ETH/SOL) es razonable, pero no se verifico con ningun dato independiente -- es una historia que explicaria el
  resultado, no una prueba de que sea la causa real.
- **Conclusion: es el candidato mas solido de los ~160 probados en todo el proyecto, pero no alcanza para
  implementarlo en el bot en produccion todavia.** No paso por ETH/SOL (que siguen siendo el control mas fuerte
  contra el azar), la correlacion negativa de la validacion cruzada pide cautela sobre el mecanismo, y no hay
  ninguna confirmacion con operaciones reales. Camino recomendado si se quiere seguir: tratarlo como una SEGUNDA
  prueba en vivo, pre-registrada por separado (misma disciplina que docs/FORWARD_TEST.md: configuracion congelada,
  sin tocar el bot de produccion), corriendo en paralelo sin arriesgar nada del v4_hourly actual.

