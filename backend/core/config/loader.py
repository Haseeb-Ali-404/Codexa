from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = CONFIG_DIR / "agents.config.json"


def load_agents_config(path: str | None = None) -> dict[str, Any]:
    p = Path(path or os.getenv("CODEXA_AGENTS_CONFIG", str(DEFAULT_CONFIG_PATH)))
    if not p.is_file():
        raise FileNotFoundError(f"agents config not found: {p}")
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def merge_agent_overrides(base: dict[str, Any], overrides: dict[str, Any] | None) -> dict[str, Any]:
    if not overrides:
        return dict(base)
    merged = dict(base)
    for k, v in overrides.items():
        if k == "fallbacks" and isinstance(v, list) and isinstance(base.get("fallbacks"), list):
            merged["fallbacks"] = v
        else:
            merged[k] = v
    return merged


def get_agent_llm_spec(
    agent_type: str,
    overrides: dict[str, Any] | None = None,
    config_path: str | None = None,
) -> dict[str, Any]:
    data = load_agents_config(config_path)
    agents = data.get("agents") or {}
    if agent_type not in agents:
        raise KeyError(f"Unknown agent type in config: {agent_type!r}")
    raw = agents[agent_type]
    merged = merge_agent_overrides(raw, overrides)
    defaults = data.get("defaults") or {}
    if "timeout_seconds" not in merged and "timeout_seconds" in defaults:
        merged["timeout_seconds"] = defaults["timeout_seconds"]
    return merged
