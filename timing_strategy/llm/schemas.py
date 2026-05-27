from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class PositionRule(BaseModel):
    type: Literal["threshold_long_cash"] = "threshold_long_cash"
    long_when: str = "factor_value > 0"
    long_position: float = Field(default=1.0, ge=0, le=1)
    cash_position: float = Field(default=0.0, ge=0, le=1)


class FactorProposal(BaseModel):
    factor_name: str
    hypothesis: str
    expression: str
    position_rule: PositionRule
    expected_mechanism: str
    reason_summary: str = ""


class VerifierOutput(BaseModel):
    passed: bool
    decision_reason: str
    issues: list[str] = []
    repair_hint: str = "无需修改"
    reason_summary: str = ""


class ReflectionOutput(BaseModel):
    prediction_review: str
    return_review: str
    risk_review: str
    failure_reason: str
    next_action: Literal["keep", "mutation", "crossover", "reject"]
    mutation_hint: str = ""
    crossover_hint: str = ""
    reason_summary: str = ""


class AgentPayload(BaseModel):
    payload: dict[str, Any]


def model_to_dict(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()

