from __future__ import annotations

import json
import math
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, desc
from sqlalchemy.orm import Session, sessionmaker

from timing_strategy.storage.models import AgentCall, Base, Evaluation, Factor, Lineage, Reflection, Run, RunStep


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _dumps(value: Any) -> str:
    return json.dumps(_sanitize(value), ensure_ascii=False, default=str)


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


class TraceRepository:
    """SQLite trace 仓库，保存每次运行、Agent 调用、因子和回测结果。"""

    def __init__(self, db_path: str | Path = "output/storage/timing_strategy.sqlite3"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def create_run(self, name: str, model: str, config: dict[str, Any]) -> str:
        run_id = _new_id("run")
        with self.SessionLocal() as session:
            session.add(
                Run(
                    id=run_id,
                    name=name,
                    status="running",
                    model=model,
                    config_json=_dumps(config),
                    summary_json="{}",
                )
            )
            session.commit()
        return run_id

    def finish_run(self, run_id: str, status: str, summary: dict[str, Any]) -> None:
        with self.SessionLocal() as session:
            run = session.get(Run, run_id)
            if run:
                run.status = status
                run.ended_at = datetime.now(UTC)
                run.summary_json = _dumps(summary)
                session.commit()

    def create_step(self, run_id: str, step_name: str, message: str = "") -> str:
        step_id = _new_id("step")
        with self.SessionLocal() as session:
            session.add(
                RunStep(
                    id=step_id,
                    run_id=run_id,
                    step_name=step_name,
                    status="running",
                    message=message,
                    detail_json="{}",
                )
            )
            session.commit()
        return step_id

    def finish_step(self, step_id: str, status: str, message: str = "", detail: dict[str, Any] | None = None) -> None:
        with self.SessionLocal() as session:
            step = session.get(RunStep, step_id)
            if step:
                step.status = status
                step.ended_at = datetime.now(UTC)
                step.message = message
                step.detail_json = _dumps(detail or {})
                session.commit()

    def add_agent_call(
        self,
        run_id: str,
        step_id: str | None,
        agent_name: str,
        prompt_name: str,
        prompt_version: str,
        full_prompt: str,
        input_payload: dict[str, Any],
        output_payload: dict[str, Any],
        raw_output: str,
        token_usage: dict[str, Any] | None = None,
    ) -> str:
        call_id = _new_id("call")
        with self.SessionLocal() as session:
            session.add(
                AgentCall(
                    id=call_id,
                    run_id=run_id,
                    step_id=step_id,
                    agent_name=agent_name,
                    prompt_name=prompt_name,
                    prompt_version=prompt_version,
                    full_prompt=full_prompt,
                    input_json=_dumps(input_payload),
                    output_json=_dumps(output_payload),
                    raw_output=raw_output,
                    token_usage_json=_dumps(token_usage or {}),
                )
            )
            session.commit()
        return call_id

    def add_factor(
        self,
        run_id: str,
        trajectory_id: str,
        factor_name: str,
        phase: str,
        hypothesis: str,
        expression: str,
        ast: dict[str, Any] | None,
        position_rule: dict[str, Any],
        status: str,
        validation: dict[str, Any],
    ) -> str:
        factor_id = _new_id("factor")
        with self.SessionLocal() as session:
            session.add(
                Factor(
                    id=factor_id,
                    run_id=run_id,
                    trajectory_id=trajectory_id,
                    factor_name=factor_name,
                    phase=phase,
                    hypothesis=hypothesis,
                    expression=expression,
                    ast_json=_dumps(ast or {}),
                    position_rule_json=_dumps(position_rule),
                    status=status,
                    validation_json=_dumps(validation),
                )
            )
            session.commit()
        return factor_id

    def add_evaluation(
        self,
        run_id: str,
        factor_id: str,
        metrics: dict[str, Any],
        equity_curve: list[dict[str, Any]],
    ) -> str:
        evaluation_id = _new_id("eval")
        with self.SessionLocal() as session:
            session.add(
                Evaluation(
                    id=evaluation_id,
                    run_id=run_id,
                    factor_id=factor_id,
                    score=metrics.get("score"),
                    metrics_json=_dumps(metrics),
                    equity_curve_json=_dumps(equity_curve),
                )
            )
            session.commit()
        return evaluation_id

    def add_reflection(self, run_id: str, factor_id: str, reflection: dict[str, Any]) -> str:
        reflection_id = _new_id("reflection")
        with self.SessionLocal() as session:
            session.add(
                Reflection(
                    id=reflection_id,
                    run_id=run_id,
                    factor_id=factor_id,
                    reflection_json=_dumps(reflection),
                )
            )
            session.commit()
        return reflection_id

    def add_lineage(
        self,
        run_id: str,
        child_factor_id: str,
        parent_factor_ids: list[str],
        relation_type: str,
    ) -> None:
        with self.SessionLocal() as session:
            if not parent_factor_ids:
                session.add(
                    Lineage(
                        id=_new_id("lineage"),
                        run_id=run_id,
                        child_factor_id=child_factor_id,
                        parent_factor_id=None,
                        relation_type=relation_type,
                    )
                )
            for parent_id in parent_factor_ids:
                session.add(
                    Lineage(
                        id=_new_id("lineage"),
                        run_id=run_id,
                        child_factor_id=child_factor_id,
                        parent_factor_id=parent_id,
                        relation_type=relation_type,
                    )
                )
            session.commit()

    def existing_signatures(self) -> list[str]:
        with self.SessionLocal() as session:
            factors = session.query(Factor).all()
            signatures: list[str] = []
            for factor in factors:
                validation = _loads(factor.validation_json, {})
                signature = validation.get("signature")
                if signature:
                    signatures.append(signature)
            return signatures

    def list_runs(self) -> list[dict[str, Any]]:
        with self.SessionLocal() as session:
            runs = session.query(Run).order_by(desc(Run.started_at)).all()
            return [self._run_summary(session, run) for run in runs]

    def get_run_detail(self, run_id: str) -> dict[str, Any] | None:
        with self.SessionLocal() as session:
            run = session.get(Run, run_id)
            if not run:
                return None
            factors = session.query(Factor).filter(Factor.run_id == run_id).order_by(Factor.created_at).all()
            factor_payloads = []
            for factor in factors:
                evaluation = session.query(Evaluation).filter(Evaluation.factor_id == factor.id).first()
                reflection = session.query(Reflection).filter(Reflection.factor_id == factor.id).first()
                factor_payloads.append(
                    {
                        "id": factor.id,
                        "trajectory_id": factor.trajectory_id,
                        "factor_name": factor.factor_name,
                        "phase": factor.phase,
                        "hypothesis": factor.hypothesis,
                        "expression": factor.expression,
                        "ast": _loads(factor.ast_json, {}),
                        "position_rule": _loads(factor.position_rule_json, {}),
                        "status": factor.status,
                        "validation": _loads(factor.validation_json, {}),
                        "evaluation": self._evaluation_payload(evaluation) if evaluation else None,
                        "reflection": _loads(reflection.reflection_json, {}) if reflection else None,
                        "created_at": factor.created_at.isoformat() if factor.created_at else None,
                    }
                )

            steps = session.query(RunStep).filter(RunStep.run_id == run_id).order_by(RunStep.started_at).all()
            calls = session.query(AgentCall).filter(AgentCall.run_id == run_id).order_by(AgentCall.created_at).all()
            lineage = session.query(Lineage).filter(Lineage.run_id == run_id).order_by(Lineage.created_at).all()
            return {
                **self._run_summary(session, run),
                "config": _loads(run.config_json, {}),
                "summary": _loads(run.summary_json, {}),
                "steps": [self._step_payload(step) for step in steps],
                "agent_calls": [self._agent_call_payload(call) for call in calls],
                "factors": factor_payloads,
                "lineage": [self._lineage_payload(item) for item in lineage],
            }

    def list_factor_pool(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.SessionLocal() as session:
            evaluations = session.query(Evaluation).order_by(desc(Evaluation.score)).limit(limit).all()
            pool = []
            for evaluation in evaluations:
                factor = session.get(Factor, evaluation.factor_id)
                if not factor:
                    continue
                pool.append(
                    {
                        "factor_id": factor.id,
                        "run_id": factor.run_id,
                        "factor_name": factor.factor_name,
                        "phase": factor.phase,
                        "hypothesis": factor.hypothesis,
                        "expression": factor.expression,
                        "metrics": _loads(evaluation.metrics_json, {}),
                    }
                )
            return pool

    def delete_run(self, run_id: str) -> bool:
        with self.SessionLocal() as session:
            run = session.get(Run, run_id)
            if not run:
                return False
            session.query(Lineage).filter(Lineage.run_id == run_id).delete(synchronize_session=False)
            session.query(Reflection).filter(Reflection.run_id == run_id).delete(synchronize_session=False)
            session.query(Evaluation).filter(Evaluation.run_id == run_id).delete(synchronize_session=False)
            session.query(Factor).filter(Factor.run_id == run_id).delete(synchronize_session=False)
            session.query(AgentCall).filter(AgentCall.run_id == run_id).delete(synchronize_session=False)
            session.query(RunStep).filter(RunStep.run_id == run_id).delete(synchronize_session=False)
            session.delete(run)
            session.commit()
            return True

    def clear_runs(self) -> None:
        with self.SessionLocal() as session:
            session.query(Lineage).delete(synchronize_session=False)
            session.query(Reflection).delete(synchronize_session=False)
            session.query(Evaluation).delete(synchronize_session=False)
            session.query(Factor).delete(synchronize_session=False)
            session.query(AgentCall).delete(synchronize_session=False)
            session.query(RunStep).delete(synchronize_session=False)
            session.query(Run).delete(synchronize_session=False)
            session.commit()

    def _run_summary(self, session: Session, run: Run) -> dict[str, Any]:
        factors = session.query(Factor).filter(Factor.run_id == run.id).all()
        evaluations = session.query(Evaluation).filter(Evaluation.run_id == run.id).all()
        best_score = None
        best_arr = None
        scored_evaluations = [item for item in evaluations if item.score is not None]
        if scored_evaluations:
            best_evaluation = max(scored_evaluations, key=lambda item: item.score)
            best_score = best_evaluation.score
            best_metrics = _loads(best_evaluation.metrics_json, {})
            best_arr = best_metrics.get("ARR")
        return {
            "id": run.id,
            "name": run.name,
            "status": run.status,
            "model": run.model,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "ended_at": run.ended_at.isoformat() if run.ended_at else None,
            "factor_count": len(factors),
            "best_score": best_score,
            "best_arr": best_arr,
            "summary": _loads(run.summary_json, {}),
        }

    @staticmethod
    def _step_payload(step: RunStep) -> dict[str, Any]:
        return {
            "id": step.id,
            "step_name": step.step_name,
            "status": step.status,
            "started_at": step.started_at.isoformat() if step.started_at else None,
            "ended_at": step.ended_at.isoformat() if step.ended_at else None,
            "message": step.message,
            "detail": _loads(step.detail_json, {}),
        }

    @staticmethod
    def _agent_call_payload(call: AgentCall) -> dict[str, Any]:
        return {
            "id": call.id,
            "step_id": call.step_id,
            "agent_name": call.agent_name,
            "prompt_name": call.prompt_name,
            "prompt_version": call.prompt_version,
            "full_prompt": call.full_prompt,
            "input": _loads(call.input_json, {}),
            "output": _loads(call.output_json, {}),
            "raw_output": call.raw_output,
            "token_usage": _loads(call.token_usage_json, {}),
            "created_at": call.created_at.isoformat() if call.created_at else None,
        }

    @staticmethod
    def _evaluation_payload(evaluation: Evaluation) -> dict[str, Any]:
        return {
            "id": evaluation.id,
            "score": evaluation.score,
            "metrics": _loads(evaluation.metrics_json, {}),
            "equity_curve": _loads(evaluation.equity_curve_json, []),
            "created_at": evaluation.created_at.isoformat() if evaluation.created_at else None,
        }

    @staticmethod
    def _lineage_payload(item: Lineage) -> dict[str, Any]:
        return {
            "id": item.id,
            "child_factor_id": item.child_factor_id,
            "parent_factor_id": item.parent_factor_id,
            "relation_type": item.relation_type,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }
