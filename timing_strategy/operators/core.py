from __future__ import annotations

import numpy as np
import pandas as pd


def _series(value: pd.Series | float | int, index: pd.Index) -> pd.Series:
    if isinstance(value, pd.Series):
        return value.astype(float)
    return pd.Series(float(value), index=index)


def _window(value: float | int) -> int:
    window = int(value)
    if window < 1:
        raise ValueError("窗口参数必须大于等于 1")
    return window


def _safe_div(a: pd.Series | float, b: pd.Series | float, index: pd.Index) -> pd.Series:
    left = _series(a, index)
    right = _series(b, index).replace(0, np.nan)
    result = left / right
    return result.replace([np.inf, -np.inf], np.nan)


def ts_mean(x: pd.Series, window: float) -> pd.Series:
    return x.rolling(_window(window), min_periods=_window(window)).mean()


def ts_std(x: pd.Series, window: float) -> pd.Series:
    return x.rolling(_window(window), min_periods=_window(window)).std(ddof=0)


def ts_max(x: pd.Series, window: float) -> pd.Series:
    return x.rolling(_window(window), min_periods=_window(window)).max()


def ts_min(x: pd.Series, window: float) -> pd.Series:
    return x.rolling(_window(window), min_periods=_window(window)).min()


def ts_rank(x: pd.Series, window: float) -> pd.Series:
    size = _window(window)
    return x.rolling(size, min_periods=size).apply(
        lambda values: pd.Series(values).rank(pct=True).iloc[-1],
        raw=False,
    )


def ts_zscore(x: pd.Series, window: float) -> pd.Series:
    mean = ts_mean(x, window)
    std = ts_std(x, window).replace(0, np.nan)
    return (x - mean) / std


def ret(x: pd.Series, window: float) -> pd.Series:
    return x.pct_change(_window(window))


def delta(x: pd.Series, window: float) -> pd.Series:
    return x.diff(_window(window))


def sma(x: pd.Series, window: float) -> pd.Series:
    return ts_mean(x, window)


def ema(x: pd.Series, window: float) -> pd.Series:
    return x.ewm(span=_window(window), adjust=False, min_periods=_window(window)).mean()


def rsi(close: pd.Series, window: float) -> pd.Series:
    size = _window(window)
    diff = close.diff()
    gain = diff.clip(lower=0).rolling(size, min_periods=size).mean()
    loss = (-diff.clip(upper=0)).rolling(size, min_periods=size).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: float) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return ts_mean(tr, window)


def macd(close: pd.Series, fast: float = 12, slow: float = 26, signal: float = 9) -> pd.Series:
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = ema(macd_line, signal)
    return macd_line - signal_line


def bb_upper(close: pd.Series, window: float, k: float = 2) -> pd.Series:
    return ts_mean(close, window) + float(k) * ts_std(close, window)


def bb_lower(close: pd.Series, window: float, k: float = 2) -> pd.Series:
    return ts_mean(close, window) - float(k) * ts_std(close, window)


def add(a: pd.Series | float, b: pd.Series | float, index: pd.Index) -> pd.Series:
    return _series(a, index) + _series(b, index)


def sub(a: pd.Series | float, b: pd.Series | float, index: pd.Index) -> pd.Series:
    return _series(a, index) - _series(b, index)


def mul(a: pd.Series | float, b: pd.Series | float, index: pd.Index) -> pd.Series:
    return _series(a, index) * _series(b, index)


def div(a: pd.Series | float, b: pd.Series | float, index: pd.Index) -> pd.Series:
    return _safe_div(a, b, index)


def abs_(a: pd.Series | float, index: pd.Index) -> pd.Series:
    return _series(a, index).abs()


def sign(a: pd.Series | float, index: pd.Index) -> pd.Series:
    return np.sign(_series(a, index))


def log(a: pd.Series | float, index: pd.Index) -> pd.Series:
    return np.log(_series(a, index).replace(0, np.nan))


def gt(a: pd.Series | float, b: pd.Series | float, index: pd.Index) -> pd.Series:
    return (_series(a, index) > _series(b, index)).astype(float)


def ge(a: pd.Series | float, b: pd.Series | float, index: pd.Index) -> pd.Series:
    return (_series(a, index) >= _series(b, index)).astype(float)


def lt(a: pd.Series | float, b: pd.Series | float, index: pd.Index) -> pd.Series:
    return (_series(a, index) < _series(b, index)).astype(float)


def le(a: pd.Series | float, b: pd.Series | float, index: pd.Index) -> pd.Series:
    return (_series(a, index) <= _series(b, index)).astype(float)


def and_(*args: pd.Series | float | pd.Index) -> pd.Series:
    index = args[-1]
    if not isinstance(index, pd.Index):
        raise TypeError("AND 算子缺少索引参数")
    values = args[:-1]
    result = pd.Series(True, index=index)
    for value in values:
        result = result & (_series(value, index) > 0)
    return result.astype(float)


def or_(*args: pd.Series | float | pd.Index) -> pd.Series:
    index = args[-1]
    if not isinstance(index, pd.Index):
        raise TypeError("OR 算子缺少索引参数")
    values = args[:-1]
    result = pd.Series(False, index=index)
    for value in values:
        result = result | (_series(value, index) > 0)
    return result.astype(float)


def where(cond: pd.Series | float, a: pd.Series | float, b: pd.Series | float, index: pd.Index) -> pd.Series:
    return pd.Series(np.where(_series(cond, index) > 0, _series(a, index), _series(b, index)), index=index)


OPERATOR_REGISTRY = {
    "TS_MEAN": {"func": ts_mean, "arity": 2, "window_args": [1]},
    "TS_STD": {"func": ts_std, "arity": 2, "window_args": [1]},
    "TS_MAX": {"func": ts_max, "arity": 2, "window_args": [1]},
    "TS_MIN": {"func": ts_min, "arity": 2, "window_args": [1]},
    "TS_RANK": {"func": ts_rank, "arity": 2, "window_args": [1]},
    "TS_ZSCORE": {"func": ts_zscore, "arity": 2, "window_args": [1]},
    "RET": {"func": ret, "arity": 2, "window_args": [1]},
    "DELTA": {"func": delta, "arity": 2, "window_args": [1]},
    "SMA": {"func": sma, "arity": 2, "window_args": [1]},
    "EMA": {"func": ema, "arity": 2, "window_args": [1]},
    "RSI": {"func": rsi, "arity": 2, "window_args": [1]},
    "ATR": {"func": atr, "arity": 4, "window_args": [3]},
    "MACD": {"func": macd, "arity": (1, 4), "window_args": [1, 2, 3]},
    "BB_UPPER": {"func": bb_upper, "arity": (2, 3), "window_args": [1]},
    "BB_LOWER": {"func": bb_lower, "arity": (2, 3), "window_args": [1]},
    "ADD": {"func": add, "arity": 2, "needs_index": True},
    "SUB": {"func": sub, "arity": 2, "needs_index": True},
    "MUL": {"func": mul, "arity": 2, "needs_index": True},
    "DIV": {"func": div, "arity": 2, "needs_index": True},
    "ABS": {"func": abs_, "arity": 1, "needs_index": True},
    "SIGN": {"func": sign, "arity": 1, "needs_index": True},
    "LOG": {"func": log, "arity": 1, "needs_index": True},
    "GT": {"func": gt, "arity": 2, "needs_index": True},
    "GE": {"func": ge, "arity": 2, "needs_index": True},
    "LT": {"func": lt, "arity": 2, "needs_index": True},
    "LE": {"func": le, "arity": 2, "needs_index": True},
    "AND": {"func": and_, "arity": (2, 8), "needs_index": True},
    "OR": {"func": or_, "arity": (2, 8), "needs_index": True},
    "WHERE": {"func": where, "arity": 3, "needs_index": True},
}


def operator_names() -> list[str]:
    return sorted(OPERATOR_REGISTRY.keys())
