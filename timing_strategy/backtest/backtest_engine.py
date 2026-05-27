from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class BacktestConfig:
    annual_trading_days: int = 252
    buy_fee: float = 0.0005
    sell_fee: float = 0.0015
    slippage: float = 0.0002
    execution: str = "next_close"


def run_backtest(
    market_data: pd.DataFrame,
    factor_value: pd.Series,
    position: pd.Series,
    config: BacktestConfig | None = None,
) -> pd.DataFrame:
    """固定回测：第 t 日信号只能影响第 t+1 日收益。"""

    cfg = config or BacktestConfig()
    if cfg.execution != "next_close":
        raise ValueError("首版固定支持 next_close 执行方式")

    frame = market_data[["date", "close", "future_return_1d"]].copy()
    frame["factor_value"] = factor_value.astype(float)
    frame["position"] = position.astype(float).clip(0, 1)
    frame["effective_position"] = frame["position"].shift(1).fillna(0)
    frame["benchmark_return"] = frame["close"].pct_change().fillna(0)

    position_delta = frame["position"].diff().fillna(frame["position"])
    buy_turnover = position_delta.clip(lower=0)
    sell_turnover = (-position_delta.clip(upper=0))
    frame["turnover"] = position_delta.abs()
    frame["cost"] = (
        buy_turnover * cfg.buy_fee
        + sell_turnover * cfg.sell_fee
        + frame["turnover"] * cfg.slippage
    )
    frame["strategy_return"] = frame["effective_position"] * frame["benchmark_return"] - frame["cost"]
    frame["excess_return"] = frame["strategy_return"] - frame["benchmark_return"]
    frame["strategy_equity"] = (1 + frame["strategy_return"]).cumprod()
    frame["benchmark_equity"] = (1 + frame["benchmark_return"]).cumprod()
    frame["drawdown"] = frame["strategy_equity"] / frame["strategy_equity"].cummax() - 1
    frame["benchmark_drawdown"] = frame["benchmark_equity"] / frame["benchmark_equity"].cummax() - 1
    return frame

