from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from timing_strategy.agents import WorkflowRunner
from timing_strategy.config import load_app_config
from timing_strategy.data.loader import DataValidationError
from timing_strategy.data.loader import enrich_market_data
from timing_strategy.llm import LLMClient
from timing_strategy.llm.client import LLMResult
from timing_strategy.storage import TraceRepository


def test_workflow_requires_real_data_path(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = load_app_config()
    config["paths"]["storage_db"] = str(tmp_path / "trace.sqlite3")
    runner = WorkflowRunner(config=config)

    with pytest.raises(DataValidationError, match="未读取到行情数据"):
        runner.run()


def test_llm_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = LLMClient(model="gpt-5.5")

    with pytest.raises(RuntimeError, match="未接入 LLM"):
        client.complete_json(
            agent_name="MarketSummaryAgent",
            prompt_name="market_summary",
            full_prompt="测试 prompt",
            input_payload={},
        )


class FinalReportFailingLLM:
    model = "fake-model"

    def complete_json(self, agent_name, prompt_name, full_prompt, input_payload):
        if prompt_name == "market_summary":
            return LLMResult(
                output={
                    "market_regime": "测试行情",
                    "trend_summary": "测试趋势",
                    "volatility_summary": "测试波动",
                    "volume_summary": "测试成交量",
                    "risk_summary": "测试风险",
                    "reason_summary": "测试摘要",
                },
                raw_output="{}",
                token_usage={},
            )
        if prompt_name == "hypothesis_generation":
            return LLMResult(
                output={
                    "hypothesis": "当5日均线高于20日均线时提高仓位。",
                    "mechanism_type": "趋势",
                    "expected_mechanism": "短期趋势强于中期趋势。",
                    "risk_hint": "震荡行情可能失效。",
                    "reason_summary": "测试假设。",
                },
                raw_output="{}",
                token_usage={},
            )
        if prompt_name == "factor_generation":
            return LLMResult(
                output={
                    "factor_name": "测试趋势因子",
                    "hypothesis": "当5日均线高于20日均线时提高仓位。",
                    "expression": "SUB(TS_MEAN(close, 5), TS_MEAN(close, 20))",
                    "position_rule": {
                        "type": "threshold_long_cash",
                        "long_when": "factor_value > 0",
                        "long_position": 1.0,
                        "cash_position": 0.0,
                    },
                    "expected_mechanism": "短期趋势强于中期趋势。",
                    "reason_summary": "测试表达式。",
                },
                raw_output="{}",
                token_usage={},
            )
        if prompt_name == "semantic_verifier":
            return LLMResult(
                output={"passed": True, "decision_reason": "通过", "issues": [], "repair_hint": "无需修改", "reason_summary": "通过"},
                raw_output="{}",
                token_usage={},
            )
        if prompt_name == "backtest_reflection":
            return LLMResult(
                output={
                    "prediction_review": "测试预测评价",
                    "return_review": "测试收益评价",
                    "risk_review": "测试风险评价",
                    "failure_reason": "测试不足",
                    "next_action": "keep",
                    "mutation_hint": "",
                    "crossover_hint": "",
                    "reason_summary": "测试反思",
                },
                raw_output="{}",
                token_usage={},
            )
        if prompt_name == "final_report":
            raise ValueError("模型输出不是合法 JSON：测试错误")
        raise AssertionError(prompt_name)


def test_final_report_parse_failure_does_not_fail_run(tmp_path: Path) -> None:
    market = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=80, freq="B"),
            "open": range(100, 180),
            "high": range(101, 181),
            "low": range(99, 179),
            "close": range(100, 180),
            "volume": [10_000_000] * 80,
            "amount": [1_000_000_000] * 80,
        }
    )
    path = tmp_path / "market.parquet"
    enrich_market_data(market).to_parquet(path, index=False)

    config = load_app_config()
    config["paths"]["storage_db"] = str(tmp_path / "trace.sqlite3")
    config["paths"]["output_dir"] = str(tmp_path / "output")
    config["paths"]["reports_dir"] = str(tmp_path / "output" / "reports")
    config["run"]["initial_candidates"] = 1
    config["run"]["enable_mutation"] = False
    config["run"]["enable_crossover"] = False
    repo = TraceRepository(config["paths"]["storage_db"])

    runner = WorkflowRunner(config=config, repository=repo, llm_client=FinalReportFailingLLM())
    run_id = runner.run(data_path=str(path), run_name="final report fallback")
    detail = repo.get_run_detail(run_id)

    assert detail is not None
    assert detail["status"] == "completed"
    assert "report_error" in detail["summary"]["final_report"]
    assert detail["summary"]["report_paths"]["markdown"].endswith(".md")
