"""Reporting and fixed-candidate OKX comparison; never searches extra parameters."""
from dataclasses import asdict
from pathlib import Path
import json
import numpy as np
import pandas as pd
from .data import load
from .engine import Risk,metrics,daily_returns
from .legacy_strategy import Params
from .diagnostics import Intervention,simulate,attribution
from .research import dump


def paired_bootstrap(base,selected,seed=20260907,paths=2000,block=7):
    if not base.index.equals(selected.index):raise ValueError('Paired returns need the same dates')
    rng=np.random.default_rng(seed);n=len(base)
    starts=rng.integers(0,n,size=(paths,(n+block-1)//block))
    idx=((starts[:,:,None]+np.arange(block))%n).reshape(paths,-1)[:,:n]
    samples=[r.to_numpy()[idx] for r in (base,selected)]
    sharpes=[np.divide(s.mean(axis=1)*np.sqrt(365),s.std(axis=1,ddof=1),out=np.zeros(paths),where=s.std(axis=1,ddof=1)>1e-12) for s in samples]
    delta=sharpes[1]-sharpes[0]
    return {'paths':paths,'block_days':block,'seed':seed,'delta_sharpe_p05':float(np.quantile(delta,.05)),'delta_sharpe_p50':float(np.median(delta)),'delta_sharpe_p95':float(np.quantile(delta,.95)),'fraction_delta_positive':float((delta>0).mean()),'meaning':'Conditional paired resampling of known daily returns; not probability of future strategy superiority.'}


def build(directory='reports/run-002',okx_data='data/okx/BTC-USDT-SWAP-1h.csv'):
    out=Path(directory);report=json.loads((out/'report.json').read_text())
    candidate=json.loads((out/'selected_research.json').read_text())
    config=json.loads(Path('configs/selected.json').read_text())
    base=Intervention(params=Params(**config['params']))
    raw=candidate['spec'].copy();raw['params']=Params(**raw['params']);selected=Intervention(**raw)
    risk=Risk(**candidate['risk'])
    a,b='2025-03-01T00:00:00Z','2026-09-01T00:00:00Z'
    okx=load(okx_data)
    comparisons={}
    for name,spec in [('baseline',base),('selected',selected)]:
        e,t,_=simulate(okx,spec,risk,a,b)
        comparisons[name]=metrics(e,t,risk.capital)
        comparisons[name]['attribution']=attribution(t,risk.capital)
        e.to_csv(out/f'okx_{name}_equity.csv',index_label='time')
        pd.DataFrame(t).to_csv(out/f'okx_{name}_trades.csv',index=False)
    comparisons['role']='Fixed-candidate venue comparison; same known BTC dates, not independent temporal evidence.'
    comparisons['costs']={'fee_bps_per_side':risk.fee_bps,'slippage_bps_per_side':risk.slippage_bps,'funding':'Actual official OKX historical rates','quantity_step_btc':risk.quantity_step,'precision_note':'Same conservative sizing step as original comparison; not a replay of historical account contract filters.'}
    fee_file=Path('data/okx/demo_fees.json')
    if fee_file.exists():
        comparisons['current_demo_fee_snapshot']=json.loads(fee_file.read_text())
        comparisons['fee_snapshot_note']='Current DEMO taker metadata, not a historical fee series or live-account quote; no additional parameter search.'
    report['okx_comparison']=comparisons
    # Compare the same dates with the same blocks, including idle days.
    curves={name:pd.read_csv(out/f'{name}_equity.csv',index_col='time',parse_dates=True).equity for name in ['baseline','selected']}
    report['paired_bootstrap_improvement']=paired_bootstrap(*[daily_returns(curves[name],risk.capital) for name in ['baseline','selected']])
    initial=json.loads((out/'baseline_attribution.json').read_text())
    cost=initial['totals_usdt'];fees=cost['entry_fee']+cost['exit_fee']
    break_even=(cost['gross_before_execution_costs']-cost['slippage_cost']-cost['funding_cost'])/fees*risk.fee_bps
    report['fixed_trade_path_break_even_fee_bps_per_side']=break_even
    report['fee_break_even_note']='Accounting on the original trade path, not a new backtest: different fees can alter sizing, fills and subsequent trades.'
    dump(out/'report.json',report)
    manifest=Path(okx_data).parent/'manifest.json'
    (out/'okx_data_manifest.json').write_bytes(manifest.read_bytes())
    panel=json.loads((out/'component_diagnosis.json').read_text())
    old,new=report['baseline_known_audit'],report['selected_known_audit']
    mc=report['monte_carlo_by_block_days']['7'];pair=report['paired_bootstrap_improvement']
    text=f'''# Segunda investigación: qué vuelve negativa a la estrategia

**Se completaron 200 intentos en esta ronda (30 controles y cambios aislados + 170 configuraciones focalizadas). No se alcanzó Sharpe 1,5.** Los 200 intentos anteriores permanecen registrados; los 400 intentos acumulados incluyen controles repetidos entre rondas.

La comparación usa marzo de 2025–agosto de 2026, los mismos 18 meses ya observados. Es **investigación exploratoria**, no una nueva validación independiente. La comprobación adicional con OKX usa ese mismo período de BTC y tampoco es una muestra temporal independiente.

## Resultado principal

Se mantuvieron activo BTC, futuros perpetuos, ancla de 4h, señales de 1h, longs y shorts, ATR14, EMA8/60, ruptura de 168 horas, stop de 4 ATR, trailing de 2 ATR y presupuesto nominal de riesgo de 2%. La variante elegida cambia **solamente el objetivo de 2R a 1,5R**.

La elección del intento **#{report['selected_attempt']}** se hizo por estabilidad en las tres ventanas de desarrollo 2022–febrero de 2025. No se eligió el mejor Sharpe del período conocido; algunas variantes aisladas tienen un resultado mayor allí, lo que no autoriza a elegirlas mirando esa prueba.

| Métrica de los 18 meses conocidos | Original | Objetivo 1,5R |
|---|---:|---:|
| Sharpe — datos Binance | {old['sharpe']:.3f} | {new['sharpe']:.3f} |
| Retorno neto — datos Binance | {old['return']:.2%} | {new['return']:.2%} |
| Drawdown — datos Binance | {old['max_drawdown']:.2%} | {new['max_drawdown']:.2%} |
| Operaciones — datos Binance | {old['trades']} | {new['trades']} |
| Sharpe — precios y funding OKX | {comparisons['baseline']['sharpe']:.3f} | {comparisons['selected']['sharpe']:.3f} |
| Retorno neto — precios y funding OKX | {comparisons['baseline']['return']:.2%} | {comparisons['selected']['return']:.2%} |
| Drawdown — precios y funding OKX | {comparisons['baseline']['max_drawdown']:.2%} | {comparisons['selected']['max_drawdown']:.2%} |

![Diagnóstico y comparación](diagnostico.png)

## Qué explica la pérdida original

Sobre 10.000 USDT iniciales, la contabilidad exacta de las operaciones originales es:

| Componente | USDT |
|---|---:|
| P&L bruto antes de costos de ejecución | {cost['gross_before_execution_costs']:.2f} |
| Menos comisiones de entrada y salida | −{fees:.2f} |
| Menos deslizamiento | −{cost['slippage_cost']:.2f} |
| Menos funding neto | −{cost['funding_cost']:.2f} |
| P&L neto | {cost['net_pnl']:.2f} |

Esto es una descomposición del mismo camino de operaciones. Los backtests contrafactuales de costos cero pueden dar otra cifra porque cambian el tamaño y el capital de operaciones posteriores. **Eliminar todos los costos solo produce Sharpe 0,759**: por sí solo, abaratar la ejecución no lleva a 1,5.

El punto de equilibrio contable sería aproximadamente **{break_even:.2f} bps de comisión por lado**, conservando las mismas operaciones y el deslizamiento supuesto. La API de la cuenta demo informa actualmente **5 bps taker**, frente a los 6 bps conservadores del estudio. Esa diferencia ayuda, pero no alcanza el punto de equilibrio de la original bajo ese cálculo; no se han supuesto fills maker gratuitos ni se ha borrado el funding. La tarifa actual no prueba qué tarifa hubiese correspondido en todo el historial.

**Longs:** 70 operaciones, −901,39 USDT, acierto 24,3%. **Shorts:** 54 operaciones, +584,25 USDT, acierto 40,7%. Hay una asimetría a investigar, pero el diagnóstico short-only tiene Sharpe 0,467 y no cumple el objetivo ni la condición de operar ambos sentidos. No se eliminaron los longs.

**Trailing:** las 113 salidas por stop ocurrieron después de ajustes del trailing. En 68 operaciones, el primer ajuste se hizo con la posición perdiendo; la mediana fue −0,026R. Es un comportamiento confirmado, pero las intervenciones muestran que no es una solución universal retrasarlo: activar a 1R empeora el Sharpe conocido a −0,446, y quitarlo solo llega a 0,052. El trailing también evita pérdidas mayores. No se desactivó por intuición.

**Objetivo:** pasar de 2R a 1,5R permite cobrar algunos movimientos que antes terminaban devolviendo la ganancia. El resultado mejora modestamente, pero no en todos los semestres. Es la única modificación seleccionada; no es una estrategia aprobada.

**Entradas y filtros:** el retroceso con cruce de EMA20 ensayado da Sharpe −1,526; el filtro ADX20 no resuelve el problema, y acortar la ruptura a 72h tampoco. Se rechazaron esas variantes específicas. Esto no prueba que todas las estrategias de retrocesos fallen; sí evita incorporar esta sin evidencia.

**Riesgo:** subir el presupuesto de 2% a 3% deja Sharpe −0,023 en el diagnóstico y sigue sin lograr el objetivo. El riesgo nominal promedio de la original fue {initial['average_nominal_risk_fraction']:.2%}, por el límite de exposición 1x. Aumentar riesgo no crea una ventaja en las señales; se conserva 2%.

## Comparaciones cambiando un componente

Cada fila cambia únicamente lo indicado respecto de la original. Los controles con costos cero, un solo sentido o riesgo 3% sirven para diagnóstico y se excluyeron de la selección.

| Cambio | Score de desarrollo | Sharpe conocido | Retorno conocido | Trades | Seleccionable |
|---|---:|---:|---:|---:|---|
'''
    for row in panel:
        m=row['known_audit']
        text+=f"| {row['label']} | {row['development_score']:.3f} | {m['sharpe']:.3f} | {m['return']:.2%} | {m['trades']} | {'Sí' if row['selectable'] else 'Solo diagnóstico'} |\n"
    text+=f'''
## Robustez e incertidumbre

Se ejecutaron **6.000 caminos Monte Carlo**, 2.000 para cada longitud de bloque de 3, 7 y 14 días, sobre retornos diarios netos del candidato. Con bloques de 7 días, el intervalo percentil 5–95 del Sharpe es **[{mc['sharpe_p05']:.3f}, {mc['sharpe_p95']:.3f}]** y la fracción de caminos con pérdida es {mc['probability_loss']:.1%}. No respalda un Sharpe objetivo de 1,5.

Otros 2.000 caminos emparejados comparan candidato y original sobre los mismos bloques de fechas. El intervalo 5–95 de la diferencia de Sharpe es **[{pair['delta_sharpe_p05']:.3f}, {pair['delta_sharpe_p95']:.3f}]**. Esto describe la incertidumbre condicional en la mejora observada; no es una probabilidad de éxito futuro.

Con comisiones y deslizamiento duplicados, el candidato cae a Sharpe **{report['double_cost_stress']['sharpe']:.3f}** y retorno **{report['double_cost_stress']['return']:.2%}**. El DSR aproximado, contando las evaluaciones de ambas rondas, es {report['deflated_sharpe_approx_cumulative']:.2%}; no es una certificación y sus supuestos de independencia entre intentos son imperfectos.

Los semestres se evaluaron por separado, reiniciando capital y posición para comparar estabilidad; no se suman como si fueran una única cuenta continua:

| Período | Sharpe original | Sharpe candidato |
|---|---:|---:|
'''
    for row in report['six_month_stability']:
        text+=f"| {row['start'][:10]} → {row['end_exclusive'][:10]} | {row['baseline']['sharpe']:.3f} | {row['selected']['sharpe']:.3f} |\n"
    text+='''
## Decisión y próximos pasos

- **Mantener** activo, futuros, 1h/4h, ambos sentidos y presupuesto de riesgo. Estas restricciones no quedaron identificadas como causas mediante las pruebas realizadas; tampoco se demuestra que sean óptimas.
- **Conservar 1,5R solo como candidato de investigación**, sin reemplazar la configuración del servicio ni habilitar órdenes reales.
- **No incorporar** el retraso del trailing, ADX o pullback ensayados: no mostraron una mejora estable que justifique agregarlos.
- La evidencia apunta a **una ventaja bruta débil y sensible al régimen, consumida por costos**, con especial debilidad de los longs. Una futura ronda tendría que plantear una hipótesis verificable para distinguir entradas long con continuidad de falsas rupturas, con datos no usados para elegir esas reglas.
- Terminar esta ronda en sus 200 intentos. Un Sharpe aceptable requeriría evidencia futura independiente; reutilizar el período conocido o cambiar de Binance a OKX no la crea.

No se enviaron órdenes, no se modificó la cuenta OKX ni se cambió `configs/selected.json`.

## Reproducibilidad

```bash
python -m astra.second_research --output reports/run-002 --budget 200
python -m astra.okx_history
python -m astra.round_two_report
```

El primer comando rechaza sobrescribir una ronda ya iniciada; los otros reconstruyen datos/reportes de los candidatos ya fijados, sin búsqueda adicional. Los datos descargados quedan en `data/okx/`, fuera de Git; el manifiesto de fuentes y hashes está en `okx_data_manifest.json`.

El nuevo simulador de diagnóstico reproduce la curva original a precisión numérica y separa comisiones, funding, deslizamiento y motivo exacto del stop. Sus indicadores ADX y pullback se verifican con pruebas de invariancia al truncar datos futuros. No se modifica el simulador ni el servicio anterior.

Fuentes: [API y datos históricos oficiales OKX](https://www.okx.com/docs-v5/en/#public-data-rest-api-get-historical-market-data), [datos históricos OKX](https://www.okx.com/historical-data), [archivos oficiales Binance](https://github.com/binance/binance-public-data), [Bailey et al., backtest overfitting](https://www.davidhbailey.com/dhbpapers/overfitting.pdf).
'''
    (out/'RESULTADOS.md').write_text(text)
    figure(out,report,panel,curves)
    return report


def figure(out,r,panel,curves):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,ax=plt.subplots(2,2,figsize=(14,10),layout='constrained')
    fig.suptitle('Segunda investigación · cambios aislados, mismas reglas centrales',fontsize=18,fontweight='bold')
    cost=json.loads((out/'baseline_attribution.json').read_text())['totals_usdt']
    labels=['Bruto','Comisiones','Deslizamiento','Funding','Neto']
    vals=[cost['gross_before_execution_costs'],-cost['entry_fee']-cost['exit_fee'],-cost['slippage_cost'],-cost['funding_cost'],cost['net_pnl']]
    running=0
    for i,v in enumerate(vals):
        bottom=running if i not in (0,4) else 0
        ax[0,0].bar(i,v,bottom=bottom,color='#27816c' if v>=0 else '#bc5654',width=.65)
        top=bottom+v
        ax[0,0].text(i,max(bottom,top)+40,f'{v:+,.0f}',ha='center',fontsize=10)
        if i!=4:running+=v
    ax[0,0].set_xticks(range(5),labels,rotation=15);ax[0,0].axhline(0,color='#889096',linewidth=.8)
    ax[0,0].set_ylim(-470,1600);ax[0,0].set_ylabel('USDT · cuenta inicial 10.000')
    ax[0,0].set_title('Qué consume el resultado original (Binance)',loc='left',fontweight='bold')
    chosen=['baseline','zero_all_costs_diagnostic','trailing_off','trailing_activation_1.0R','ADX_20','pullback_EMA20']
    names=['Original','Sin costos (diagnóstico)','Sin trailing','Trailing desde +1R','Filtro ADX20','Retroceso EMA20']
    values=[next(x['known_audit']['sharpe'] for x in panel if x['label']==k) for k in chosen]
    names.append('Objetivo 1,5R (seleccionado)');values.append(r['selected_known_audit']['sharpe'])
    y=np.arange(len(values))
    colors=['#889096' if i==1 else ('#27816c' if v>=0 else '#bc5654') for i,v in enumerate(values)]
    ax[0,1].barh(y,values,color=colors);ax[0,1].set_yticks(y,names);ax[0,1].invert_yaxis()
    for i,v in enumerate(values):ax[0,1].text(v+(.04 if v>=0 else -.04),i,f'{v:.2f}',va='center',ha='left' if v>=0 else 'right',fontsize=9)
    ax[0,1].axvline(0,color='#889096',linewidth=.8);ax[0,1].axvline(1.5,color='#b78327',linestyle='--')
    ax[0,1].set_xlim(-1.95,1.7);ax[0,1].set_xlabel('Sharpe anualizado · línea punteada: objetivo 1,5')
    ax[0,1].set_title('No todos los cambios ayudan',loc='left',fontweight='bold')
    for name,color,label in [('baseline','#889096','Original, objetivo 2R'),('selected','#27816c','Candidato, objetivo 1,5R')]:
        curve=curves[name].resample('1D').last()
        ax[1,0].plot(curve.index,curve.values,color=color,label=label,linewidth=1.5)
        other=pd.read_csv(out/f'okx_{name}_equity.csv',index_col='time',parse_dates=True).equity.resample('1D').last()
        ax[1,1].plot(other.index,other.values,color=color,label=label,linewidth=1.5)
    for j,title in enumerate(['Cuenta simulada con precios/funding Binance','Cuenta simulada con precios/funding OKX']):
        ax[1,j].axhline(10000,color='#b78327',linestyle=':',linewidth=1)
        ax[1,j].set_title(title,loc='left',fontweight='bold');ax[1,j].set_ylabel('USDT, costos incluidos');ax[1,j].legend(frameon=False,fontsize=9)
        ax[1,j].tick_params(axis='x',rotation=20);ax[1,j].grid(axis='y',alpha=.15)
    fig.supxlabel('Marzo 2025–agosto 2026 · período ya observado: exploratorio, sin aprobación para operar',fontsize=11)
    fig.savefig(out/'diagnostico.png',dpi=170)
    plt.close(fig)

if __name__=='__main__':
    r=build()
    print(json.dumps({k:r['okx_comparison'][k]['sharpe'] for k in ['baseline','selected']},indent=2))
