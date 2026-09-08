# Resultado de investigación

Estado: **CRITERIA_NOT_MET**. 200 intentos; seleccionado #171.

Datos: futuros Binance BTCUSDT; referencia para OKX, no resultados de OKX.

Holdout: 2025-03-01 a 2026-09-01 (fin exclusivo), 18 meses.

| Métrica fuera de muestra | Valor |
|---|---:|
| Sharpe anualizado, retornos diarios, RF=0 | -0.102 |
| Retorno neto | -3.17% |
| Máximo drawdown | 15.64% |
| Operaciones | 124 |
| Long / short | 70 / 54 |
| Sharpe Monte Carlo p05 / p50 / p95 | -1.571 / -0.151 / 1.135 |
| DSR aproximado | 3.23% |
| Sharpe con costos duplicados | -1.367 |

No habilitado para capital real.

## Criterios

- PASS: development_eligible
- FAIL: sharpe_at_least_1_5
- PASS: at_least_18_months
- PASS: at_least_50_trades
- PASS: both_sides
- PASS: drawdown_under_25pct
- PASS: not_halted
- FAIL: bootstrap_lower_bound_positive
- FAIL: dsr_at_least_95pct
- FAIL: double_costs_positive_sharpe

## Límites

- Historical venue is Binance, not OKX. OKX validation remains required.
- Fees/slippage are explicit assumptions, not your account fee tier.
- Risk is a target at the stop, not a guaranteed maximum loss; gaps and funding can exceed it.
- OHLC simulation cannot model exchange outages, queue position, mark-price liquidation or all intrabar paths.
- Monte Carlo and approximate DSR cannot guarantee future Sharpe or absence of overfitting.
