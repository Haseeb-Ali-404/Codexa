from __future__ import annotations

import json
import re
from typing import Any


_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def _candidate_json_strings(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []

    candidates: list[str] = [text]
    candidates.extend(match.group(1).strip() for match in _CODE_FENCE_RE.finditer(text))

    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        candidates.append(text[brace_start : brace_end + 1].strip())

    bracket_start = text.find("[")
    bracket_end = text.rfind("]")
    if bracket_start != -1 and bracket_end > bracket_start:
        candidates.append(text[bracket_start : bracket_end + 1].strip())

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate and candidate not in seen:
            deduped.append(candidate)
            seen.add(candidate)
    return deduped


def parse_json_block(raw: str, default: Any = None) -> Any:
    for candidate in _candidate_json_strings(raw):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return default
