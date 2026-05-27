from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from timing_strategy.operators import OPERATOR_REGISTRY
from timing_strategy.parser.ast import ASTNode
from timing_strategy.parser.expression_parser import ExpressionParseError, parse_expression


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    issues: list[str]
    ast: ASTNode | None
    node_count: int
    depth: int
    signature: str | None

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "issues": self.issues,
            "ast": self.ast.to_dict() if self.ast else None,
            "node_count": self.node_count,
            "depth": self.depth,
            "signature": self.signature,
        }


def validate_expression(
    expression: str,
    allowed_fields: Iterable[str],
    max_nodes: int = 40,
    max_depth: int = 8,
    min_window: int = 1,
    max_window: int = 252,
    existing_signatures: Iterable[str] | None = None,
) -> ValidationResult:
    issues: list[str] = []
    try:
        ast = parse_expression(expression)
    except ExpressionParseError as exc:
        return ValidationResult(False, [str(exc)], None, 0, 0, None)

    allowed = {field.lower() for field in allowed_fields}
    existing = set(existing_signatures or [])
    node_count = _count_nodes(ast)
    depth = _depth(ast)
    signature = ast.signature()

    if node_count > max_nodes:
        issues.append(f"表达式节点数量过多：{node_count} > {max_nodes}")
    if depth > max_depth:
        issues.append(f"表达式嵌套过深：{depth} > {max_depth}")
    if signature in existing:
        issues.append("表达式结构与已有因子完全重复")

    _validate_node(ast, allowed, issues, min_window, max_window)
    return ValidationResult(not issues, issues, ast, node_count, depth, signature)


def _validate_node(
    node: ASTNode,
    allowed_fields: set[str],
    issues: list[str],
    min_window: int,
    max_window: int,
) -> None:
    if node.node_type == "field":
        if str(node.value).lower() not in allowed_fields:
            issues.append(f"字段不在白名单中：{node.value}")
        return
    if node.node_type == "number":
        return
    if node.node_type != "call":
        issues.append(f"未知 AST 节点类型：{node.node_type}")
        return

    op = str(node.value).upper()
    spec = OPERATOR_REGISTRY.get(op)
    if not spec:
        issues.append(f"算子不在白名单中：{op}")
    else:
        arity = spec.get("arity")
        if isinstance(arity, tuple):
            min_arity, max_arity = arity
            if not min_arity <= len(node.args) <= max_arity:
                issues.append(f"算子 {op} 参数数量错误：需要 {min_arity}-{max_arity} 个，实际 {len(node.args)} 个")
        elif len(node.args) != arity:
            issues.append(f"算子 {op} 参数数量错误：需要 {arity} 个，实际 {len(node.args)} 个")

        for arg_index in spec.get("window_args", []):
            if arg_index < len(node.args):
                arg = node.args[arg_index]
                if arg.node_type != "number":
                    issues.append(f"算子 {op} 的窗口参数必须是常数")
                else:
                    window = int(float(arg.value))
                    if window < min_window or window > max_window:
                        issues.append(f"算子 {op} 的窗口参数越界：{window}")

    for child in node.args:
        _validate_node(child, allowed_fields, issues, min_window, max_window)


def _count_nodes(node: ASTNode) -> int:
    return 1 + sum(_count_nodes(child) for child in node.args)


def _depth(node: ASTNode) -> int:
    if not node.args:
        return 1
    return 1 + max(_depth(child) for child in node.args)

