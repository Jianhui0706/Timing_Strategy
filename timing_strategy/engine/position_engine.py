from __future__ import annotations

import re
from typing import Any

import pandas as pd


class PositionRuleError(ValueError):
    """仓位规则校验失败。"""


CONDITION_RE = re.compile(r"^\s*factor_value\s*(>=|<=|>|<|==)\s*(-?\d+(?:\.\d+)?)\s*$")


def build_position(factor_value: pd.Series, position_rule: dict[str, Any] | None = None) -> pd.Series:
    """将因子值映射为 [0, 1] 仓位，首版仅支持多头/空仓。"""

    rule = position_rule or {}
    rule_type = rule.get("type", "threshold_long_cash")
    if rule_type != "threshold_long_cash":
        raise PositionRuleError(f"首版仅支持 threshold_long_cash，实际为：{rule_type}")

    long_when = str(rule.get("long_when", "factor_value > 0"))
    long_position = float(rule.get("long_position", 1.0))
    cash_position = float(rule.get("cash_position", 0.0))
    if not 0 <= long_position <= 1 or not 0 <= cash_position <= 1:
        raise PositionRuleError("仓位必须位于 [0, 1]")

    mask = _evaluate_condition(factor_value, long_when)
    position = pd.Series(cash_position, index=factor_value.index, dtype=float)
    position.loc[mask.fillna(False)] = long_position
    return position.clip(0, 1).fillna(0)


def _evaluate_condition(factor_value: pd.Series, condition: str) -> pd.Series:
    match = CONDITION_RE.match(condition)
    if not match:
        raise PositionRuleError(f"无法解析仓位条件：{condition}")
    op, threshold_text = match.groups()
    threshold = float(threshold_text)
    if op == ">":
        return factor_value > threshold
    if op == ">=":
        return factor_value >= threshold
    if op == "<":
        return factor_value < threshold
    if op == "<=":
        return factor_value <= threshold
    return factor_value == threshold

