"""
Edit agent: given current files + user instruction, returns JSON changes (before/after per file).
"""

from __future__ import annotations

import json
import re
from typing import Any

from core.providers.base import ChatMessage, LLMCallOptions
from core.utils.resilient import FallbackLLMClient, LLMAllProvidersFailed

MAX_PROMPT_CHARS_PER_FILE = 14000
MAX_FILES_IN_PROMPT = 12


def _strip_json_fence(raw: str) -> str:
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*```$", "", s)
    return s.strip()


class EditAgent:
    SYSTEM = """You are CODEXA's code editor. You MODIFY existing projects; you never rewrite the whole repo unless necessary.

Respond with ONLY valid JSON (no markdown fences). Schema:
{
  "summary": "one sentence",
  "changes": [
    {
      "file": "relative/path/from/project/root.tsx",
      "type": "modify",
      "before": "<exact current file content>",
      "after": "<full new file content>"
    }
  ]
}

Rules:
- Include only files that must change.
- For existing files, "before" MUST match the file content you were given (verbatim).
- To add a new file: "type": "add", "before": "", "after": "<full content>".
- Preserve style and structure; minimal edits when possible.
- If the request is unclear, make the smallest reasonable change and explain in "summary".
"""

    def __init__(
        self,
        llm_client: FallbackLLMClient,
        llm_options: LLMCallOptions,
    ) -> None:
        self._llm = llm_client
        self._opts = llm_options

    def _build_user_payload(
        self,
        files: list[dict[str, Any]],
        user_message: str,
        history_hint: str,
    ) -> str:
        parts: list[str] = []
        parts.append("## User request\n" + user_message.strip())
        if history_hint.strip():
            parts.append("\n## Recent conversation (compressed)\n" + history_hint.strip())
        parts.append("\n## Current files\n")
        count = 0
        for f in files[:MAX_FILES_IN_PROMPT]:
            path = f.get("path") or ""
            content = f.get("content") or ""
            if len(content) > MAX_PROMPT_CHARS_PER_FILE:
                content = (
                    content[: MAX_PROMPT_CHARS_PER_FILE // 2]
                    + "\n\n/* ... truncated ... */\n\n"
                    + content[-MAX_PROMPT_CHARS_PER_FILE // 2 :]
                )
            parts.append(f"### FILE: {path}\n```\n{content}\n```\n")
            count += 1
        if len(files) > count:
            parts.append(f"\n({len(files) - count} more files omitted — do not modify unless required.)\n")
        return "\n".join(parts)

    def run(
        self,
        project_id: str,
        files: list[dict[str, Any]],
        user_message: str,
        history_hint: str = "",
    ) -> dict[str, Any]:
        user_content = self._build_user_payload(files, user_message, history_hint)
        messages = [
            ChatMessage(role="system", content=self.SYSTEM),
            ChatMessage(role="user", content=user_content),
        ]
        try:
            result = self._llm.complete(messages, self._opts)
            raw = _strip_json_fence(result.text)
            data = json.loads(raw)
        except LLMAllProvidersFailed as e:
            return {"ok": False, "error": str(e), "summary": "", "changes": []}
        except json.JSONDecodeError as e:
            return {
                "ok": False,
                "error": f"Invalid JSON from model: {e}",
                "summary": "",
                "changes": [],
            }

        changes = data.get("changes") or []
        if not isinstance(changes, list):
            changes = []
        normalized: list[dict[str, Any]] = []
        for ch in changes:
            if not isinstance(ch, dict):
                continue
            path = (ch.get("file") or ch.get("path") or "").strip()
            if not path:
                continue
            normalized.append(
                {
                    "file": path,
                    "type": (ch.get("type") or "modify").lower(),
                    "before": ch.get("before") if ch.get("before") is not None else "",
                    "after": ch.get("after") if ch.get("after") is not None else "",
                }
            )

        return {
            "ok": True,
            "summary": (data.get("summary") or "").strip(),
            "changes": normalized,
            "project_id": project_id,
        }
