from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LLMResult:
    output: dict[str, Any]
    raw_output: str
    token_usage: dict[str, Any]


class LLMClient:
    """GPT API 网关。没有 API Key 时明确报错，不做假输出。"""

    def __init__(
        self,
        model: str = "gpt-5.5",
        api_key: str | None = None,
        request_timeout_seconds: float = 60,
        max_retries: int = 2,
    ):
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.request_timeout_seconds = request_timeout_seconds
        self.max_retries = max_retries

    def complete_json(
        self,
        agent_name: str,
        prompt_name: str,
        full_prompt: str,
        input_payload: dict[str, Any],
    ) -> LLMResult:
        if not self.api_key:
            raise RuntimeError("未接入 LLM：未检测到 OPENAI_API_KEY，请先在 .env 中配置 GPT API Key。")

        from openai import OpenAI

        client = OpenAI(api_key=self.api_key, timeout=self.request_timeout_seconds)
        last_error: Exception | None = None
        last_raw_output = ""
        token_usage: dict[str, Any] = {}
        input_messages = [
            {"role": "system", "content": full_prompt},
            {"role": "user", "content": json.dumps(input_payload, ensure_ascii=False)},
        ]

        for attempt in range(self.max_retries + 1):
            response = client.responses.create(model=self.model, input=input_messages)
            raw_output = getattr(response, "output_text", "") or ""
            last_raw_output = raw_output
            usage = getattr(response, "usage", None)
            token_usage = usage.model_dump() if hasattr(usage, "model_dump") else (dict(usage) if usage else {})
            try:
                output = self._parse_json(raw_output)
                token_usage["json_retry_attempt"] = attempt
                return LLMResult(output=output, raw_output=raw_output, token_usage=token_usage)
            except ValueError as exc:
                last_error = exc
                input_messages = [
                    {"role": "system", "content": "你是 JSON 修复器。请把用户提供的内容修复成严格合法 JSON，不要输出 Markdown，不要输出解释。"},
                    {
                        "role": "user",
                        "content": (
                            "下面内容不是合法 JSON。请只返回修复后的 JSON 对象，保持原字段语义不变。\n\n"
                            f"错误信息：{exc}\n\n"
                            f"原始内容：\n{raw_output}"
                        ),
                    },
                ]

        snippet = last_raw_output[:800].replace("\n", "\\n")
        raise ValueError(f"模型输出不是合法 JSON，已重试 {self.max_retries} 次：{last_error}。原始输出片段：{snippet}")

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError(f"模型输出不是合法 JSON：{exc}") from exc
