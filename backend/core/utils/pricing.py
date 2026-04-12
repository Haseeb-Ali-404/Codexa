from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

_PRICING_PATH = Path(__file__).resolve().parent.parent / "config" / "pricing.json"


@lru_cache
def _load_pricing() -> dict[str, Any]:
    p = Path(os.getenv("CODEXA_PRICING_CONFIG", str(_PRICING_PATH)))
    if not p.is_file():
        return {"defaults": {}, "models": {}}
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def reload_pricing_cache() -> None:
    _load_pricing.cache_clear()


def _rates_for_model(model: str) -> tuple[float, float]:
    data = _load_pricing()
    models = data.get("models") or {}
    if model in models:
        m = models[model]
        return float(m["input_per_million_usd"]), float(m["output_per_million_usd"])
    for prefix, rates in models.items():
        if model.startswith(prefix):
            return float(rates["input_per_million_usd"]), float(rates["output_per_million_usd"])
    d = data.get("defaults") or {}
    return float(d.get("input_per_million_usd", 0.5)), float(d.get("output_per_million_usd", 1.5))


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    inp_r, out_r = _rates_for_model(model)
    return (input_tokens / 1_000_000.0) * inp_r + (output_tokens / 1_000_000.0) * out_r
