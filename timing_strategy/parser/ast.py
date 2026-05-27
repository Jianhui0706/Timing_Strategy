from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ASTNode:
    """表达式 AST 节点，只描述结构，不包含可执行代码。"""

    node_type: str
    value: str | float
    args: tuple["ASTNode", ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_type": self.node_type,
            "value": self.value,
            "args": [arg.to_dict() for arg in self.args],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ASTNode":
        return cls(
            node_type=payload["node_type"],
            value=payload["value"],
            args=tuple(cls.from_dict(arg) for arg in payload.get("args", [])),
        )

    def signature(self) -> str:
        if not self.args:
            return f"{self.node_type}:{self.value}"
        child = ",".join(arg.signature() for arg in self.args)
        return f"{self.node_type}:{self.value}({child})"

