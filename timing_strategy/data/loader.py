from __future__ import annotations

from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = ["date", "open", "high", "low", "close", "volume", "amount"]
COLUMN_ALIASES = {
    "trade_date": "date",
    "datetime": "date",
    "time": "date",
    "vol": "volume",
}


class DataValidationError(ValueError):
    """行情数据校验失败。"""


def _normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame.columns = [str(col).strip().lower() for col in frame.columns]
    frame = frame.rename(columns={source: target for source, target in COLUMN_ALIASES.items() if source in frame.columns})
    return frame


def load_market_file(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        frame = pd.read_csv(path)
    elif suffix in {".parquet", ".pq"}:
        frame = pd.read_parquet(path)
    else:
        raise DataValidationError(f"暂不支持的数据文件格式：{suffix}。请使用 CSV 或 Parquet。")
    return normalize_market_frame(frame)


def load_market_csv(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    return normalize_market_frame(frame)


def normalize_market_frame(frame: pd.DataFrame) -> pd.DataFrame:
    frame = _normalize_columns(frame)
    if "ts_code" in frame.columns and frame["ts_code"].dropna().nunique() > 1:
        raise DataValidationError("当前回测只支持单一指数/ETF时间序列，请先按 ts_code 拆分或过滤数据。")
    missing = [col for col in REQUIRED_COLUMNS if col not in frame.columns]
    if missing:
        raise DataValidationError(f"行情数据缺少字段：{', '.join(missing)}")

    frame = frame[REQUIRED_COLUMNS].copy()
    frame["date"] = _parse_date(frame["date"])
    frame = frame.sort_values("date").drop_duplicates("date").reset_index(drop=True)

    for col in REQUIRED_COLUMNS:
        if col != "date":
            frame[col] = pd.to_numeric(frame[col], errors="coerce")

    if frame[REQUIRED_COLUMNS[1:]].isna().any().any():
        raise DataValidationError("行情数据存在无法转换为数字的价格、成交量或成交额")

    return enrich_market_data(frame)


def _parse_date(values: pd.Series) -> pd.Series:
    text_values = values.astype(str).str.strip()
    if text_values.str.fullmatch(r"\d{8}").all():
        return pd.to_datetime(text_values, format="%Y%m%d")
    return pd.to_datetime(values)


def enrich_market_data(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["return_1d"] = frame["close"].pct_change()
    frame["future_return_1d"] = frame["close"].shift(-1) / frame["close"] - 1
    frame["dollar_volume"] = frame["amount"]
    return frame
