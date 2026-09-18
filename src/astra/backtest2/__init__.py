"""Realistic-friction backtest engine v2: funding, book-aware slippage, fees, liquidation, Monte Carlo, walk-forward.

Does not replace engine.py; it is an independent execution path that reuses
data.py (ingestion) and directional_strategy.py (signal) unchanged.
"""
