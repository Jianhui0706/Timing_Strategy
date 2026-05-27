from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


def load_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_app_config() -> dict[str, Any]:
    load_dotenv()
    default_config = load_yaml("configs/default.yaml")
    llm_config = load_yaml("configs/llm.yaml")
    llm_config["model"] = os.getenv("OPENAI_MODEL", llm_config.get("model", "gpt-5.5"))
    default_config["llm"] = llm_config
    if os.getenv("TIMING_STRATEGY_DB"):
        default_config.setdefault("paths", {})["storage_db"] = os.getenv("TIMING_STRATEGY_DB")
    return default_config
