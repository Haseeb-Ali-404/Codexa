from __future__ import annotations

import json
import logging
import os
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable

from core.providers.base import TokenUsage
from core.utils.pricing import estimate_cost_usd

log = logging.getLogger("codexa.usage")

_agg_lock = Lock()
_agg: dict[str, dict[str, float | int]] = {}

trace_id_var: ContextVar[str | None] = ContextVar("codexa_trace_id", default=None)
chat_id_var: ContextVar[str | None] = ContextVar("codexa_chat_id", default=None)


@dataclass
class UsageLogRecord:
    timestamp_utc: str
    agent_type: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    streaming: bool
    trace_id: str | None = None
    chat_id: str | None = None
    extra: dict[str, Any] | None = None


def _append_file_line(path: str, payload: dict[str, Any]) -> None:
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError as e:
        log.warning("usage log file write failed: %s", e)


def log_llm_usage(
    *,
    agent_type: str,
    provider: str,
    model: str,
    usage: TokenUsage,
    streaming: bool,
    extra: dict[str, Any] | None = None,
    file_writer: Callable[[str, dict[str, Any]], None] | None = None,
) -> UsageLogRecord:
    """Structured token + cost logging (logger + optional JSONL file)."""

    inp = int(usage.input_tokens)
    out = int(usage.output_tokens)
    total = int(usage.normalized_total())
    cost = estimate_cost_usd(model, inp, out)
    rec = UsageLogRecord(
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        agent_type=agent_type,
        provider=provider,
        model=model,
        input_tokens=inp,
        output_tokens=out,
        total_tokens=total,
        estimated_cost_usd=round(cost, 8),
        streaming=streaming,
        trace_id=trace_id_var.get(),
        chat_id=chat_id_var.get(),
        extra=extra,
    )
    payload = asdict(rec)
    log.info("llm_usage %s", json.dumps(payload, ensure_ascii=False))

    path = os.getenv("CODEXA_USAGE_LOG_FILE", "").strip()
    if path:
        writer = file_writer or _append_file_line
        writer(path, payload)

    with _agg_lock:
        b = _agg.setdefault(
            agent_type,
            {
                "estimated_cost_usd": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
                "requests": 0,
            },
        )
        b["estimated_cost_usd"] = float(b["estimated_cost_usd"]) + cost
        b["input_tokens"] = int(b["input_tokens"]) + inp
        b["output_tokens"] = int(b["output_tokens"]) + out
        b["requests"] = int(b["requests"]) + 1

    return rec


def get_usage_aggregates() -> dict[str, dict[str, float | int]]:
    with _agg_lock:
        return {k: dict(v) for k, v in _agg.items()}


def reset_usage_aggregates() -> None:
    with _agg_lock:
        _agg.clear()


def approximate_usage_from_text(prompt: str, completion: str) -> TokenUsage:
    """Rough heuristic when APIs omit usage (~4 chars per token)."""

    def est(s: str) -> int:
        return max(1, len(s) // 4)

    inp = est(prompt)
    out = est(completion)
    return TokenUsage(input_tokens=inp, output_tokens=out, total_tokens=inp + out)
