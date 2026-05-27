from __future__ import annotations

from typing import Any


def select_mutation_parent(factors: list[dict[str, Any]]) -> dict[str, Any] | None:
    """选择最需要局部修复的父轨迹，首版按综合评分最低选择。"""

    if not factors:
        return None
    return sorted(factors, key=lambda item: item.get("metrics", {}).get("score") or -999)[0]


def select_crossover_parents(factors: list[dict[str, Any]], count: int = 2) -> list[dict[str, Any]]:
    """选择表现较好的父轨迹做机制组合。"""

    return sorted(factors, key=lambda item: item.get("metrics", {}).get("score") or -999, reverse=True)[:count]

