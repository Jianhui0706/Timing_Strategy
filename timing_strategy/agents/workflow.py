from __future__ import annotations

import json
import math
import re
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from timing_strategy.backtest import BacktestConfig, run_backtest
from timing_strategy.data import load_market_file
from timing_strategy.data.loader import DataValidationError
from timing_strategy.engine import FactorEngine, build_position
from timing_strategy.evolution import select_crossover_parents, select_mutation_parent
from timing_strategy.llm import LLMClient, PromptLoader
from timing_strategy.metrics import compute_metrics
from timing_strategy.operators import operator_names
from timing_strategy.storage import TraceRepository
from timing_strategy.validation import validate_expression


class WorkflowRunner:
    """多 Agent 择时挖掘工作流，计算和回测始终由固定 Python 内核完成。"""

    def __init__(
        self,
        config: dict[str, Any],
        repository: TraceRepository | None = None,
        llm_client: LLMClient | None = None,
        prompt_loader: PromptLoader | None = None,
        logger: Callable[[str], None] | None = None,
    ):
        self.config = config
        self.logger = logger
        db_path = config.get("paths", {}).get("storage_db", "storage/timing_strategy.sqlite3")
        self.repository = repository or TraceRepository(db_path)
        llm_cfg = config.get("llm", {})
        self.llm_client = llm_client or LLMClient(
            model=llm_cfg.get("model", "gpt-5.5"),
            request_timeout_seconds=float(llm_cfg.get("request_timeout_seconds", 60)),
            max_retries=int(llm_cfg.get("max_retries", 2)),
        )
        self.prompt_loader = prompt_loader or PromptLoader()

    def run(
        self,
        data_path: str | None = None,
        run_name: str | None = None,
        run_id: str | None = None,
        market_data: pd.DataFrame | None = None,
    ) -> str:
        self._log(f"读取行情数据：{data_path}")
        if market_data is None:
            market_data = self.load_market_data(data_path)
        name = run_name or "择时策略运行"
        if run_id is None:
            run_id = self.repository.create_run(name=name, model=self.llm_client.model, config=self.config)
            self._log(f"创建运行记录：{run_id}，模型：{self.llm_client.model}")
        else:
            self._log(f"使用已有运行记录：{run_id}，模型：{self.llm_client.model}")
        evaluated_factors: list[dict[str, Any]] = []

        try:
            market_summary = self._agent_call(
                run_id=run_id,
                step_name="市场状态摘要",
                agent_name="MarketSummaryAgent",
                prompt_name="market_summary",
                variables={"market_context": self._market_context(market_data)},
                input_payload={"market_context": self._market_context_dict(market_data)},
            )

            initial_count = int(self.config.get("run", {}).get("initial_candidates", 2))
            for idx in range(initial_count):
                phase = f"initialization_{idx + 1}"
                hypothesis = self._agent_call(
                    run_id=run_id,
                    step_name=f"初始假设生成 {idx + 1}",
                    agent_name="HypothesisAgent",
                    prompt_name="hypothesis_generation",
                    variables={
                        "market_summary": json.dumps(market_summary, ensure_ascii=False, indent=2),
                        "trajectory_context": "当前为首轮初始化，暂无历史轨迹。",
                        "phase": phase,
                    },
                    input_payload={"market_summary": market_summary, "trajectory_context": [], "phase": phase},
                )
                proposal = self._agent_call(
                    run_id=run_id,
                    step_name=f"表达式生成 {idx + 1}",
                    agent_name="FactorAgent",
                    prompt_name="factor_generation",
                    variables=self._factor_prompt_variables(hypothesis.get("hypothesis", "")),
                    input_payload={"hypothesis": hypothesis.get("hypothesis", ""), "phase": phase},
                )
                factor_result = self._evaluate_proposal(run_id, market_data, proposal, phase=phase, parent_ids=[])
                evaluated_factors.append(factor_result)

            if self.config.get("run", {}).get("enable_mutation", True):
                parent = select_mutation_parent(evaluated_factors)
                if parent:
                    mutation = self._agent_call(
                        run_id=run_id,
                        step_name="Mutation 轨迹变异",
                        agent_name="EvolutionAgent",
                        prompt_name="mutation",
                        variables={
                            "allowed_fields": self._allowed_fields_text(),
                            "allowed_operators": self._allowed_operators_text(),
                            "parent_trajectory": json.dumps(parent, ensure_ascii=False, indent=2),
                        },
                        input_payload={"parent_trajectory": parent},
                    )
                    evaluated_factors.append(
                        self._evaluate_proposal(
                            run_id,
                            market_data,
                            mutation,
                            phase="mutation",
                            parent_ids=[parent["factor_id"]],
                        )
                    )

            if self.config.get("run", {}).get("enable_crossover", True):
                parents = select_crossover_parents(evaluated_factors, count=2)
                if len(parents) >= 2:
                    crossover = self._agent_call(
                        run_id=run_id,
                        step_name="Crossover 轨迹组合",
                        agent_name="EvolutionAgent",
                        prompt_name="crossover",
                        variables={
                            "allowed_fields": self._allowed_fields_text(),
                            "allowed_operators": self._allowed_operators_text(),
                            "parent_trajectories": json.dumps(parents, ensure_ascii=False, indent=2),
                        },
                        input_payload={"parent_trajectories": parents},
                    )
                    evaluated_factors.append(
                        self._evaluate_proposal(
                            run_id,
                            market_data,
                            crossover,
                            phase="crossover",
                            parent_ids=[item["factor_id"] for item in parents],
                        )
                    )

            final_report = self._build_final_report(run_id, evaluated_factors)
            summary = {
                "factor_count": len(evaluated_factors),
                "best_factor": self._best_factor(evaluated_factors),
                "final_report": final_report,
            }
            summary["report_paths"] = self._export_run_report(run_id, name, summary, evaluated_factors)
            self.repository.finish_run(run_id, "completed", summary)
            self._log(f"运行完成：{run_id}")
            return run_id
        except Exception as exc:
            self.repository.finish_run(
                run_id,
                "failed",
                {
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                    "factor_count": len(evaluated_factors),
                },
            )
            self._log(f"运行失败：{exc}")
            raise

    def _build_final_report(self, run_id: str, evaluated_factors: list[dict[str, Any]]) -> dict[str, Any]:
        try:
            return self._agent_call(
                run_id=run_id,
                step_name="客户摘要报告",
                agent_name="ReportAgent",
                prompt_name="final_report",
                variables={"run_payload": json.dumps(evaluated_factors, ensure_ascii=False, indent=2)},
                input_payload={"run_payload": evaluated_factors},
            )
        except ValueError as exc:
            self._log(f"客户摘要报告使用 Python 保底生成：{exc}")
            best_factor = self._best_factor(evaluated_factors)
            best_name = best_factor.get("factor_name", "无") if best_factor else "无"
            best_metrics = best_factor.get("metrics", {}) if best_factor else {}
            return {
                "run_summary": f"本次运行完成 {len(evaluated_factors)} 个候选轨迹的生成、校验与回测。",
                "best_factor_summary": (
                    f"当前综合评分最高的因子是：{best_name}，"
                    f"score={best_metrics.get('score')}，"
                    f"ARR={best_metrics.get('ARR')}，"
                    f"MDD={best_metrics.get('MDD')}。"
                ),
                "risk_summary": "最终客户摘要由 Python 保底生成，因为模型返回的报告 JSON 格式不合法；因子和回测结果仍以固定 Python 输出为准。",
                "next_steps": ["查看前端中的因子详情和回测曲线", "复核被拒绝因子的校验原因", "继续扩大样本或增加标的做稳健性验证"],
                "reason_summary": "模型 final_report 输出格式异常，系统未中断已完成的策略结果，改用结构化保底摘要。",
                "report_error": str(exc),
            }

    def _agent_call(
        self,
        run_id: str,
        step_name: str,
        agent_name: str,
        prompt_name: str,
        variables: dict[str, Any],
        input_payload: dict[str, Any],
    ) -> dict[str, Any]:
        self._log(f"开始：{step_name}（{agent_name} / {prompt_name}）")
        step_id = self.repository.create_step(run_id, step_name)
        template = self.prompt_loader.load(prompt_name)
        full_prompt = template.render(variables)
        try:
            result = self.llm_client.complete_json(agent_name, prompt_name, full_prompt, input_payload)
            self.repository.add_agent_call(
                run_id=run_id,
                step_id=step_id,
                agent_name=agent_name,
                prompt_name=template.name,
                prompt_version=template.version,
                full_prompt=full_prompt,
                input_payload=input_payload,
                output_payload=result.output,
                raw_output=result.raw_output,
                token_usage=result.token_usage,
            )
            self.repository.finish_step(step_id, "completed", "Agent 调用完成", {"prompt_name": prompt_name})
            self._log(f"完成：{step_name}")
            return result.output
        except Exception as exc:
            self.repository.finish_step(step_id, "failed", str(exc), {"prompt_name": prompt_name})
            self._log(f"失败：{step_name}：{exc}")
            raise

    def _evaluate_proposal(
        self,
        run_id: str,
        market_data: pd.DataFrame,
        proposal: dict[str, Any],
        phase: str,
        parent_ids: list[str],
    ) -> dict[str, Any]:
        verifier = self._agent_call(
            run_id=run_id,
            step_name=f"{phase} 语义一致性审核",
            agent_name="VerifierAgent",
            prompt_name="semantic_verifier",
            variables={"factor_payload": json.dumps(proposal, ensure_ascii=False, indent=2)},
            input_payload={"factor_payload": proposal},
        )

        validation_step = self.repository.create_step(run_id, f"{phase} Python 表达式校验")
        self._log(f"开始：{phase} Python 表达式校验")
        validation = validate_expression(
            expression=proposal.get("expression", ""),
            allowed_fields=self.config.get("validation", {}).get("allowed_fields", []),
            max_nodes=int(self.config.get("validation", {}).get("max_nodes", 40)),
            max_depth=int(self.config.get("validation", {}).get("max_depth", 8)),
            min_window=int(self.config.get("validation", {}).get("min_window", 1)),
            max_window=int(self.config.get("validation", {}).get("max_window", 252)),
            existing_signatures=self.repository.existing_signatures(),
        )
        validation_payload = validation.to_dict()
        validation_payload["semantic_verifier"] = verifier
        passed = validation.passed and bool(verifier.get("passed", False))
        self.repository.finish_step(
            validation_step,
            "completed" if passed else "failed",
            "Python 校验完成" if passed else "候选因子未通过校验",
            validation_payload,
        )
        self._log(f"完成：{phase} Python 表达式校验，passed={passed}")

        factor_id = self.repository.add_factor(
            run_id=run_id,
            trajectory_id=f"traj_{uuid.uuid4().hex[:12]}",
            factor_name=proposal.get("factor_name", "未命名择时因子"),
            phase=phase,
            hypothesis=proposal.get("hypothesis", ""),
            expression=proposal.get("expression", ""),
            ast=validation.ast.to_dict() if validation.ast else None,
            position_rule=proposal.get("position_rule", self.config.get("position", {}).get("default_rule", {})),
            status="validated" if passed else "rejected",
            validation=validation_payload,
        )
        self.repository.add_lineage(run_id, factor_id, parent_ids, phase)

        if not passed:
            return {
                "factor_id": factor_id,
                "phase": phase,
                "factor_name": proposal.get("factor_name", "未命名择时因子"),
                "hypothesis": proposal.get("hypothesis", ""),
                "expression": proposal.get("expression", ""),
                "status": "rejected",
                "metrics": {"score": None},
                "validation": validation_payload,
            }

        backtest_step = self.repository.create_step(run_id, f"{phase} 固定 Python 回测")
        self._log(f"开始：{phase} 固定 Python 回测")
        try:
            factor_value = FactorEngine(market_data).compute(proposal["expression"])
            position = build_position(factor_value, proposal.get("position_rule"))
            bt_config = self._backtest_config()
            backtest = run_backtest(market_data, factor_value, position, bt_config)
            metrics = compute_metrics(backtest, annual_trading_days=bt_config.annual_trading_days)
            equity_curve = self._equity_curve_payload(backtest)
            self.repository.add_evaluation(run_id, factor_id, metrics, equity_curve)
            self.repository.finish_step(backtest_step, "completed", "固定 Python 回测完成", {"metrics": metrics})
            self._log(f"完成：{phase} 固定 Python 回测，score={metrics.get('score')}")
        except Exception as exc:
            self.repository.finish_step(backtest_step, "failed", str(exc), {})
            self._log(f"失败：{phase} 固定 Python 回测：{exc}")
            raise

        reflection = self._agent_call(
            run_id=run_id,
            step_name=f"{phase} 回测反思",
            agent_name="ReflectionAgent",
            prompt_name="backtest_reflection",
            variables={
                "evaluation_payload": json.dumps(
                    {
                        "proposal": proposal,
                        "metrics": metrics,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            },
            input_payload={"evaluation_payload": {"proposal": proposal, "metrics": metrics}},
        )
        self.repository.add_reflection(run_id, factor_id, reflection)
        return {
            "factor_id": factor_id,
            "phase": phase,
            "factor_name": proposal.get("factor_name", "未命名择时因子"),
            "hypothesis": proposal.get("hypothesis", ""),
            "expression": proposal.get("expression", ""),
            "position_rule": proposal.get("position_rule", {}),
            "status": "evaluated",
            "metrics": metrics,
            "reflection": reflection,
        }

    def load_market_data(self, data_path: str | None) -> pd.DataFrame:
        if not data_path:
            raise DataValidationError("未读取到行情数据：请提供本地 CSV 文件路径。")
        path = Path(data_path)
        if not path.exists():
            raise DataValidationError(f"未读取到行情数据：文件不存在 {path}")
        return load_market_file(path)

    def _log(self, message: str) -> None:
        if self.logger:
            self.logger(message)

    def _market_context_dict(self, market_data: pd.DataFrame) -> dict[str, Any]:
        recent = market_data.tail(60)
        close = market_data["close"]
        return {
            "start_date": str(market_data["date"].iloc[0].date()),
            "end_date": str(market_data["date"].iloc[-1].date()),
            "rows": int(len(market_data)),
            "last_close": float(close.iloc[-1]),
            "return_20d": float(close.iloc[-1] / close.iloc[-21] - 1) if len(close) > 21 else None,
            "return_60d": float(close.iloc[-1] / close.iloc[-61] - 1) if len(close) > 61 else None,
            "volatility_20d": float(market_data["return_1d"].tail(20).std(ddof=0)),
            "volatility_60d": float(recent["return_1d"].std(ddof=0)),
            "volume_ratio_20_60": float(recent["volume"].tail(20).mean() / recent["volume"].mean()),
        }

    def _market_context(self, market_data: pd.DataFrame) -> str:
        return json.dumps(self._market_context_dict(market_data), ensure_ascii=False, indent=2)

    def _factor_prompt_variables(self, hypothesis: str) -> dict[str, Any]:
        return {
            "allowed_fields": self._allowed_fields_text(),
            "allowed_operators": self._allowed_operators_text(),
            "hypothesis": hypothesis,
        }

    def _allowed_fields_text(self) -> str:
        return ", ".join(self.config.get("validation", {}).get("allowed_fields", []))

    def _allowed_operators_text(self) -> str:
        return ", ".join(operator_names())

    def _backtest_config(self) -> BacktestConfig:
        cfg = self.config.get("backtest", {})
        return BacktestConfig(
            annual_trading_days=int(cfg.get("annual_trading_days", 252)),
            buy_fee=float(cfg.get("buy_fee", 0.0005)),
            sell_fee=float(cfg.get("sell_fee", 0.0015)),
            slippage=float(cfg.get("slippage", 0.0002)),
            execution=str(cfg.get("execution", "next_close")),
        )

    @staticmethod
    def _equity_curve_payload(backtest: pd.DataFrame) -> list[dict[str, Any]]:
        columns = [
            "date",
            "strategy_equity",
            "benchmark_equity",
            "drawdown",
            "position",
            "factor_value",
            "turnover",
        ]
        payload = backtest[columns].copy()
        payload["date"] = payload["date"].dt.strftime("%Y-%m-%d")
        payload = payload.replace([float("inf"), float("-inf")], pd.NA)
        rows: list[dict[str, Any]] = []
        for record in payload.to_dict(orient="records"):
            clean = {}
            for key, value in record.items():
                if isinstance(value, float) and math.isnan(value):
                    clean[key] = None
                else:
                    clean[key] = value
            rows.append(clean)
        return rows

    @staticmethod
    def _best_factor(factors: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not factors:
            return None
        return sorted(factors, key=lambda item: item.get("metrics", {}).get("score") or -999, reverse=True)[0]

    def _export_run_report(
        self,
        run_id: str,
        run_name: str,
        summary: dict[str, Any],
        factors: list[dict[str, Any]],
    ) -> dict[str, str]:
        paths_config = self.config.get("paths", {})
        report_dir = Path(paths_config.get("reports_dir") or Path(paths_config.get("output_dir", "output")) / "reports")
        report_dir.mkdir(parents=True, exist_ok=True)
        report_stem = self._report_file_stem(run_id, run_name)
        json_path = report_dir / f"{report_stem}.json"
        md_path = report_dir / f"{report_stem}.md"
        report_paths = {
            "markdown": md_path.as_posix(),
            "json": json_path.as_posix(),
        }
        summary_with_paths = {**summary, "report_paths": report_paths}
        payload = {
            "run_id": run_id,
            "run_name": run_name,
            "summary": summary_with_paths,
            "factors": factors,
        }
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        md_path.write_text(self._render_markdown_report(run_id, run_name, summary_with_paths, factors), encoding="utf-8")
        self._log(f"报告已导出：{json_path}")
        self._log(f"报告已导出：{md_path}")
        return report_paths

    @staticmethod
    def _report_file_stem(run_id: str, run_name: str) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        readable_name = re.sub(r"[^\w\u4e00-\u9fff]+", "_", run_name, flags=re.UNICODE).strip("_")
        readable_name = readable_name[:48] or "择时策略运行"
        short_id = run_id.removeprefix("run_")[:8]
        return f"{timestamp}_{readable_name}_{short_id}"

    @staticmethod
    def _render_markdown_report(run_id: str, run_name: str, summary: dict[str, Any], factors: list[dict[str, Any]]) -> str:
        final_report = summary.get("final_report", {})
        best_factor = summary.get("best_factor") or {}
        lines = [
            f"# 择时策略运行报告",
            "",
            f"- Run ID：`{run_id}`",
            f"- 运行名称：{run_name}",
            f"- 因子数量：{summary.get('factor_count', 0)}",
            f"- 最佳因子：{best_factor.get('factor_name', '无')}",
            f"- 最佳分数：{best_factor.get('metrics', {}).get('score')}",
            f"- Markdown 报告：`{summary.get('report_paths', {}).get('markdown', '')}`",
            f"- JSON 报告：`{summary.get('report_paths', {}).get('json', '')}`",
            "",
            "## 客户摘要",
            "",
            str(final_report.get("run_summary", "")),
            "",
            "## 最佳因子说明",
            "",
            str(final_report.get("best_factor_summary", "")),
            "",
            "## 风险提示",
            "",
            str(final_report.get("risk_summary", "")),
            "",
            "## 后续建议",
            "",
        ]
        for item in final_report.get("next_steps", []):
            lines.append(f"- {item}")
        lines.extend(["", "## 因子列表", ""])
        for factor in factors:
            metrics = factor.get("metrics", {})
            lines.extend(
                [
                    f"### {factor.get('factor_name', '未命名因子')}",
                    "",
                    f"- 阶段：{factor.get('phase')}",
                    f"- 状态：{factor.get('status')}",
                    f"- 表达式：`{factor.get('expression')}`",
                    f"- Score：{metrics.get('score')}",
                    f"- ARR：{metrics.get('ARR')}",
                    f"- MDD：{metrics.get('MDD')}",
                    "",
                    str(factor.get("hypothesis", "")),
                    "",
                ]
            )
        return "\n".join(lines)
