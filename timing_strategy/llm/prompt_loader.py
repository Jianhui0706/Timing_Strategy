from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    version: str
    language: str
    content: str

    def render(self, variables: dict[str, Any]) -> str:
        rendered = self.content
        for key, value in variables.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
        return rendered


class PromptLoader:
    """加载中文 prompt 模板，并保留版本信息。"""

    def __init__(self, prompt_dir: str | Path = "timing_strategy/prompts"):
        self.prompt_dir = Path(prompt_dir)

    def load(self, prompt_name: str) -> PromptTemplate:
        path = self.prompt_dir / f"{prompt_name}.md"
        if not path.exists():
            raise FileNotFoundError(f"找不到 prompt 文件：{path}")
        text = path.read_text(encoding="utf-8")
        metadata, content = self._split_frontmatter(text)
        return PromptTemplate(
            name=metadata.get("prompt_name", prompt_name),
            version=metadata.get("version", "v1"),
            language=metadata.get("language", "zh-CN"),
            content=content.strip(),
        )

    @staticmethod
    def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
        if not text.startswith("---"):
            return {}, text
        parts = text.split("---", 2)
        if len(parts) < 3:
            return {}, text
        raw_meta = parts[1]
        content = parts[2]
        metadata: dict[str, str] = {}
        for line in raw_meta.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()
        return metadata, content

