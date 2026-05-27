from __future__ import annotations

import pandas as pd

from timing_strategy.operators import OPERATOR_REGISTRY
from timing_strategy.parser.ast import ASTNode
from timing_strategy.parser.expression_parser import parse_expression


class FactorEngine:
    """固定因子计算引擎，只执行 AST 与白名单算子。"""

    def __init__(self, market_data: pd.DataFrame):
        self.market_data = market_data.copy()
        self.index = self.market_data.index

    def compute(self, expression: str) -> pd.Series:
        ast = parse_expression(expression)
        result = self.evaluate(ast)
        if not isinstance(result, pd.Series):
            result = pd.Series(float(result), index=self.index)
        return result.replace([float("inf"), float("-inf")], pd.NA).astype(float)

    def evaluate(self, node: ASTNode) -> pd.Series | float:
        if node.node_type == "number":
            return float(node.value)
        if node.node_type == "field":
            field = str(node.value).lower()
            if field not in self.market_data.columns:
                raise KeyError(f"行情数据不存在字段：{field}")
            return self.market_data[field].astype(float)
        if node.node_type != "call":
            raise ValueError(f"未知 AST 节点类型：{node.node_type}")

        op = str(node.value).upper()
        spec = OPERATOR_REGISTRY.get(op)
        if spec is None:
            raise ValueError(f"未知算子：{op}")
        args = [self.evaluate(arg) for arg in node.args]
        if spec.get("needs_index"):
            args.append(self.index)
        return spec["func"](*args)

