from __future__ import annotations

import math

import numpy as np
import pandas as pd


def compute_metrics(backtest: pd.DataFrame, annual_trading_days: int = 252) -> dict:
    valid = backtest.dropna(subset=["factor_value", "future_return_1d"]).copy()
    tsic = _corr(valid["factor_value"], valid["future_return_1d"])
    rank_tsic = _corr(valid["factor_value"].rank(), valid["future_return_1d"].rank())
    direction_accuracy = _direction_accuracy(valid["factor_value"], valid["future_return_1d"])

    strategy_return = backtest["strategy_return"].fillna(0)
    benchmark_return = backtest["benchmark_return"].fillna(0)
    excess_return = backtest["excess_return"].fillna(0)

    arr = _annual_return(backtest["strategy_equity"].iloc[-1], len(backtest), annual_trading_days)
    benchmark_arr = _annual_return(backtest["benchmark_equity"].iloc[-1], len(backtest), annual_trading_days)
    excess_arr = arr - benchmark_arr
    sharpe = _annual_sharpe(strategy_return, annual_trading_days)
    ir = _annual_sharpe(excess_return, annual_trading_days)
    mdd = float(backtest["drawdown"].min())
    calmar = arr / abs(mdd) if mdd < 0 else math.nan

    return {
        "TSIC": tsic,
        "Rank_TSIC": rank_tsic,
        "direction_accuracy": direction_accuracy,
        "ARR": arr,
        "benchmark_ARR": benchmark_arr,
        "excess_ARR": excess_arr,
        "Sharpe": sharpe,
        "IR": ir,
        "MDD": mdd,
        "Calmar": calmar,
        "turnover": float(backtest["turnover"].mean()),
        "average_exposure": float(backtest["position"].mean()),
        "win_rate": float((strategy_return > 0).mean()),
        "score": _score(arr, sharpe, mdd, tsic),
    }


def _corr(a: pd.Series, b: pd.Series) -> float:
    joined = pd.concat([a, b], axis=1).dropna()
    if len(joined) < 3:
        return math.nan
    value = joined.iloc[:, 0].corr(joined.iloc[:, 1])
    return float(value) if pd.notna(value) else math.nan


def _direction_accuracy(factor_value: pd.Series, future_return: pd.Series) -> float:
    joined = pd.concat([factor_value, future_return], axis=1).dropna()
    if joined.empty:
        return math.nan
    signal_direction = np.sign(joined.iloc[:, 0])
    future_direction = np.sign(joined.iloc[:, 1])
    return float((signal_direction == future_direction).mean())


def _annual_return(total_equity: float, periods: int, annual_trading_days: int) -> float:
    if periods <= 0 or total_equity <= 0:
        return math.nan
    return float(total_equity ** (annual_trading_days / periods) - 1)


def _annual_sharpe(returns: pd.Series, annual_trading_days: int) -> float:
    std = returns.std(ddof=0)
    if std == 0 or pd.isna(std):
        return math.nan
    return float(returns.mean() / std * math.sqrt(annual_trading_days))


def _score(arr: float, sharpe: float, mdd: float, tsic: float) -> float:
    safe_arr = 0 if math.isnan(arr) else arr
    safe_sharpe = 0 if math.isnan(sharpe) else sharpe
    safe_mdd = 0 if math.isnan(mdd) else abs(mdd)
    safe_tsic = 0 if math.isnan(tsic) else tsic
    return float(safe_arr + 0.2 * safe_sharpe + 2.0 * safe_tsic - 0.5 * safe_mdd)

