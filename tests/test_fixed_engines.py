from __future__ import annotations

import pandas as pd

from timing_strategy.backtest import run_backtest
from timing_strategy.data.loader import enrich_market_data, load_market_file
from timing_strategy.engine import FactorEngine, build_position
from timing_strategy.validation import validate_expression


def _market_data() -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=80, freq="B"),
            "open": range(100, 180),
            "high": range(101, 181),
            "low": range(99, 179),
            "close": range(100, 180),
            "volume": [10_000_000] * 80,
            "amount": [1_000_000_000] * 80,
        }
    )
    return enrich_market_data(frame)


def test_expression_validation_and_factor_engine_are_deterministic() -> None:
    expression = "SUB(TS_MEAN(close, 20), TS_MEAN(close, 60))"
    validation = validate_expression(
        expression,
        allowed_fields=["open", "high", "low", "close", "volume", "amount", "return_1d"],
    )
    assert validation.passed

    data = _market_data()
    first = FactorEngine(data).compute(expression)
    second = FactorEngine(data).compute(expression)
    pd.testing.assert_series_equal(first, second)


def test_and_operator_accepts_multiple_conditions() -> None:
    expression = "AND(GT(close, SMA(close, 5)), GT(volume, 0), LE(low, high))"
    validation = validate_expression(
        expression,
        allowed_fields=["open", "high", "low", "close", "volume", "amount", "return_1d"],
    )
    assert validation.passed

    result = FactorEngine(_market_data()).compute(expression)
    assert result.dropna().isin([0.0, 1.0]).all()


def test_position_is_clipped_to_long_cash_range() -> None:
    factor_value = pd.Series([-1.0, 0.5, 2.0])
    position = build_position(
        factor_value,
        {
            "type": "threshold_long_cash",
            "long_when": "factor_value > 0",
            "long_position": 1.0,
            "cash_position": 0.0,
        },
    )
    assert position.tolist() == [0.0, 1.0, 1.0]
    assert position.between(0, 1).all()


def test_backtest_uses_previous_day_position() -> None:
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=3, freq="B"),
            "open": [100, 110, 99],
            "high": [101, 111, 100],
            "low": [99, 109, 98],
            "close": [100, 110, 99],
            "volume": [1, 1, 1],
            "amount": [100, 110, 99],
        }
    )
    data = enrich_market_data(frame)
    factor = pd.Series([1.0, -1.0, -1.0])
    position = pd.Series([1.0, 0.0, 0.0])
    result = run_backtest(data, factor, position)

    assert result["effective_position"].tolist() == [0.0, 1.0, 0.0]
    assert result["benchmark_return"].round(4).tolist() == [0.0, 0.1, -0.1]
    assert result["strategy_return"].iloc[1] > 0
    assert result["strategy_return"].iloc[2] <= 0


def test_loader_accepts_tushare_style_parquet(tmp_path) -> None:
    frame = pd.DataFrame(
        {
            "trade_date": ["20240103", "20240102", "20240104"],
            "open": [101, 100, 102],
            "high": [102, 101, 103],
            "low": [100, 99, 101],
            "close": [101, 100, 102],
            "vol": [1000, 900, 1200],
            "amount": [101000, 90000, 122400],
        }
    )
    path = tmp_path / "tushare_index.parquet"
    frame.to_parquet(path)

    loaded = load_market_file(path)

    assert loaded["date"].dt.strftime("%Y%m%d").tolist() == ["20240102", "20240103", "20240104"]
    assert loaded["volume"].tolist() == [900, 1000, 1200]
    assert {"return_1d", "future_return_1d", "dollar_volume"}.issubset(loaded.columns)


def test_loader_rejects_multiple_ts_codes(tmp_path) -> None:
    frame = pd.DataFrame(
        {
            "ts_code": ["510300.SH", "510500.SH"],
            "trade_date": ["20240102", "20240102"],
            "open": [1, 2],
            "high": [1, 2],
            "low": [1, 2],
            "close": [1, 2],
            "vol": [1, 2],
            "amount": [1, 2],
        }
    )
    path = tmp_path / "mixed.parquet"
    frame.to_parquet(path)

    try:
        load_market_file(path)
    except Exception as exc:
        assert "单一指数/ETF" in str(exc)
    else:
        raise AssertionError("多标的数据必须被拒绝")
