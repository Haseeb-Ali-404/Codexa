from __future__ import annotations

import json
import logging
import os
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
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


def _default_usage_log_path() -> Path:
    return Path(__file__).resolve().parents[2] / "usage.jsonl"


def resolve_usage_log_path() -> Path:
    configured = os.getenv("CODEXA_USAGE_LOG_FILE", "").strip()
    return Path(configured) if configured else _default_usage_log_path()


def _new_bucket() -> dict[str, float | int]:
    return {
        "estimated_cost_usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "requests": 0,
    }


def _increment_bucket(bucket: dict[str, float | int], payload: dict[str, Any]) -> None:
    bucket["estimated_cost_usd"] = float(bucket["estimated_cost_usd"]) + float(
        payload.get("estimated_cost_usd") or 0.0
    )
    bucket["input_tokens"] = int(bucket["input_tokens"]) + int(payload.get("input_tokens") or 0)
    bucket["output_tokens"] = int(bucket["output_tokens"]) + int(payload.get("output_tokens") or 0)
    bucket["requests"] = int(bucket["requests"]) + 1


def _merge_bucket(bucket: dict[str, float | int], payload: dict[str, float | int]) -> None:
    bucket["estimated_cost_usd"] = float(bucket["estimated_cost_usd"]) + float(
        payload.get("estimated_cost_usd") or 0.0
    )
    bucket["input_tokens"] = int(bucket["input_tokens"]) + int(payload.get("input_tokens") or 0)
    bucket["output_tokens"] = int(bucket["output_tokens"]) + int(payload.get("output_tokens") or 0)
    bucket["requests"] = int(bucket["requests"]) + int(payload.get("requests") or 0)


def _copy_bucket(bucket: dict[str, float | int]) -> dict[str, float | int]:
    return {
        "estimated_cost_usd": round(float(bucket.get("estimated_cost_usd") or 0.0), 8),
        "input_tokens": int(bucket.get("input_tokens") or 0),
        "output_tokens": int(bucket.get("output_tokens") or 0),
        "requests": int(bucket.get("requests") or 0),
    }


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

    path = resolve_usage_log_path()
    if path:
        writer = file_writer or _append_file_line
        writer(str(path), payload)

    with _agg_lock:
        b = _agg.setdefault(agent_type, _new_bucket())
        _increment_bucket(b, payload)

    return rec


def get_usage_aggregates() -> dict[str, dict[str, float | int]]:
    with _agg_lock:
        return {k: _copy_bucket(v) for k, v in _agg.items()}


def get_usage_metrics() -> dict[str, Any]:
    log_path = resolve_usage_log_path()
    by_agent: dict[str, dict[str, float | int]] = {}
    by_day: dict[str, dict[str, Any]] = {}

    if log_path.exists():
        try:
            with log_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        entry = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    agent_type = str(entry.get("agent_type") or "unknown").strip() or "unknown"
                    timestamp_utc = str(entry.get("timestamp_utc") or "").strip()
                    if timestamp_utc:
                        try:
                            day_key = datetime.fromisoformat(timestamp_utc).date().isoformat()
                        except ValueError:
                            day_key = "unknown"
                    else:
                        day_key = "unknown"

                    agent_bucket = by_agent.setdefault(agent_type, _new_bucket())
                    _increment_bucket(agent_bucket, entry)

                    day_bucket = by_day.setdefault(
                        day_key,
                        {
                            "date": day_key,
                            "by_agent": {},
                        },
                    )
                    day_agent_bucket = day_bucket["by_agent"].setdefault(agent_type, _new_bucket())
                    _increment_bucket(day_agent_bucket, entry)
        except OSError as e:
            log.warning("usage log file read failed: %s", e)

    if not by_agent:
        by_agent = get_usage_aggregates()

    day_rows = []
    for day_key in sorted(by_day.keys()):
        day_agents = {
            agent_name: _copy_bucket(agent_bucket)
            for agent_name, agent_bucket in by_day[day_key]["by_agent"].items()
        }
        totals = _new_bucket()
        for agent_bucket in day_agents.values():
            _merge_bucket(totals, agent_bucket)

        day_rows.append(
            {
                "date": day_key,
                "requests": int(totals["requests"]),
                "input_tokens": int(totals["input_tokens"]),
                "output_tokens": int(totals["output_tokens"]),
                "total_tokens": int(totals["input_tokens"]) + int(totals["output_tokens"]),
                "cost": round(float(totals["estimated_cost_usd"]), 8),
                "by_agent": day_agents,
            }
        )

    return {
        "by_agent": {agent_name: _copy_bucket(agent_bucket) for agent_name, agent_bucket in by_agent.items()},
        "by_day": day_rows,
        "available_dates": [row["date"] for row in day_rows],
    }


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
