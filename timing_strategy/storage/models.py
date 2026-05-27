from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import declarative_base


Base = declarative_base()


def utc_now() -> datetime:
    return datetime.now(UTC)


class Run(Base):
    __tablename__ = "runs"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    status = Column(String, nullable=False)
    model = Column(String, nullable=False)
    started_at = Column(DateTime, default=utc_now)
    ended_at = Column(DateTime, nullable=True)
    config_json = Column(Text, nullable=False, default="{}")
    summary_json = Column(Text, nullable=False, default="{}")


class RunStep(Base):
    __tablename__ = "run_steps"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("runs.id"), nullable=False)
    step_name = Column(String, nullable=False)
    status = Column(String, nullable=False)
    started_at = Column(DateTime, default=utc_now)
    ended_at = Column(DateTime, nullable=True)
    message = Column(Text, nullable=False, default="")
    detail_json = Column(Text, nullable=False, default="{}")


class AgentCall(Base):
    __tablename__ = "agent_calls"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("runs.id"), nullable=False)
    step_id = Column(String, ForeignKey("run_steps.id"), nullable=True)
    agent_name = Column(String, nullable=False)
    prompt_name = Column(String, nullable=False)
    prompt_version = Column(String, nullable=False)
    full_prompt = Column(Text, nullable=False)
    input_json = Column(Text, nullable=False, default="{}")
    output_json = Column(Text, nullable=False, default="{}")
    raw_output = Column(Text, nullable=False, default="")
    token_usage_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=utc_now)


class Factor(Base):
    __tablename__ = "factors"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("runs.id"), nullable=False)
    trajectory_id = Column(String, nullable=False)
    factor_name = Column(String, nullable=False)
    phase = Column(String, nullable=False)
    hypothesis = Column(Text, nullable=False)
    expression = Column(Text, nullable=False)
    ast_json = Column(Text, nullable=False, default="{}")
    position_rule_json = Column(Text, nullable=False, default="{}")
    status = Column(String, nullable=False)
    validation_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=utc_now)


class Evaluation(Base):
    __tablename__ = "evaluations"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("runs.id"), nullable=False)
    factor_id = Column(String, ForeignKey("factors.id"), nullable=False)
    score = Column(Float, nullable=True)
    metrics_json = Column(Text, nullable=False, default="{}")
    equity_curve_json = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, default=utc_now)


class Reflection(Base):
    __tablename__ = "reflections"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("runs.id"), nullable=False)
    factor_id = Column(String, ForeignKey("factors.id"), nullable=False)
    reflection_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=utc_now)


class Lineage(Base):
    __tablename__ = "lineage"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("runs.id"), nullable=False)
    child_factor_id = Column(String, ForeignKey("factors.id"), nullable=False)
    parent_factor_id = Column(String, ForeignKey("factors.id"), nullable=True)
    relation_type = Column(String, nullable=False)
    created_at = Column(DateTime, default=utc_now)
