"""Assembles one run's results into a flat schema for storage and cross-run comparison in BigQuery."""
from dataclasses import dataclass, asdict, is_dataclass
import json
import numpy as np
import pandas as pd

from ..engine import metrics


def _plain(value):
    """Recursively converts Timestamps/dataclasses/numpy scalars into JSON-safe plain Python values."""
    if is_dataclass(value) and not isinstance(value, type):
        return {k: _plain(v) for k, v in asdict(value).items()}
    if isinstance(value, (pd.Timestamp,)):
        return str(value)
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


@dataclass(frozen=True)
class ReportBuilder:

    def build(self, run_id: str, equity: pd.Series, trades: list[dict],
              mc_summary: dict, wf_results: pd.DataFrame | None, capital: float, params: dict) -> dict:
        """Equity curve, max drawdown, per-trade return distribution, Monte Carlo summary, and the params that produced them."""
        base = metrics(equity, trades, capital)
        wealth = np.r_[capital, equity.to_numpy()]
        drawdown = 1. - wealth / np.maximum.accumulate(wealth)
        return {
            "run_id": run_id,
            "generated_at": str(pd.Timestamp.now(tz="UTC")),
            "params": _plain(params),
            "capital": capital,
            "sharpe": base["sharpe"],
            "total_return": base["return"],
            "max_drawdown": float(drawdown.max()),
            "trade_count": base["trades"],
            "long_trades": base["long_trades"],
            "short_trades": base["short_trades"],
            "win_rate": base["win_rate"],
            "trade_returns": [t["net_pnl"] for t in trades],
            "equity_curve": {
                "timestamp": [str(ts) for ts in equity.index],
                "equity": equity.tolist(),
            },
            "monte_carlo": _plain(mc_summary),
            "walk_forward": _plain(wf_results.to_dict("records")) if wf_results is not None else [],
        }

    def to_bigquery_rows(self, report: dict) -> list[dict]:
        """Flattens build()'s output into one row matching a fixed BigQuery table schema, keyed by run_id."""
        return [{
            "run_id": report["run_id"],
            "generated_at": report["generated_at"],
            "params_json": json.dumps(report["params"]),
            "capital": report["capital"],
            "sharpe": report["sharpe"],
            "total_return": report["total_return"],
            "max_drawdown": report["max_drawdown"],
            "trade_count": report["trade_count"],
            "long_trades": report["long_trades"],
            "short_trades": report["short_trades"],
            "win_rate": report["win_rate"],
            "monte_carlo_p5": report["monte_carlo"].get("p5"),
            "monte_carlo_p50": report["monte_carlo"].get("p50"),
            "monte_carlo_p95": report["monte_carlo"].get("p95"),
            "monte_carlo_prob_below_threshold": report["monte_carlo"].get("prob_below_threshold"),
            "trade_returns_json": json.dumps(report["trade_returns"]),
            "equity_curve_json": json.dumps(report["equity_curve"]),
            "walk_forward_json": json.dumps(report["walk_forward"]),
        }]
