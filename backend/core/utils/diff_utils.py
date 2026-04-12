"""
Helpers for structured before/after diffs (and optional unified diff text).
"""

from __future__ import annotations

import difflib
from typing import Any


def unified_diff_text(before: str, after: str, path: str = "file") -> str:
    a = before.splitlines(keepends=True)
    b = after.splitlines(keepends=True)
    return "".join(difflib.unified_diff(a, b, fromfile=path, tofile=path, lineterm=""))


def normalize_change(
    file_path: str,
    before: str,
    after: str,
    change_type: str = "modify",
) -> dict[str, Any]:
    return {
        "file": file_path,
        "type": change_type,
        "before": before,
        "after": after,
    }


def enrich_change_with_diff(change: dict[str, Any]) -> dict[str, Any]:
    out = dict(change)
    path = out.get("file") or "file"
    out["unified_diff"] = unified_diff_text(
        str(out.get("before") or ""),
        str(out.get("after") or ""),
        path,
    )
    return out
