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
MAX_FULL_FILES_IN_PROMPT = 18


_KEYWORD_HINTS = {
    "navbar": ("nav", "header", "navigation", "topbar"),
    "footer": ("footer",),
    "header": ("header", "hero", "banner"),
    "hero": ("hero", "landing", "home", "index"),
    "login": ("auth", "login", "signin", "sign-in"),
    "register": ("auth", "register", "signup", "sign-up"),
    "button": ("button", "btn"),
    "color": ("theme", "style", "tailwind", "globals", "index.css"),
    "theme": ("theme", "tailwind", "globals", "index.css"),
    "dark": ("theme", "dark", "tailwind", "globals", "index.css"),
    "light": ("theme", "light", "tailwind", "globals", "index.css"),
    "pricing": ("pricing",),
    "dashboard": ("dashboard", "admin"),
    "route": ("route", "router", "app.tsx", "main.tsx"),
    "api": ("api", "route", "router", "endpoint"),
    "auth": ("auth", "login", "register", "jwt", "token"),
    "database": ("db", "database", "model", "schema", "mongo"),
    "logo": ("logo", "brand", "header", "nav"),
    "title": ("title", "head", "meta", "index.html", "app.tsx"),
}


def _strip_json_fence(raw: str) -> str:
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*```$", "", s)
    return s.strip()


def _rank_files(files: list[dict[str, Any]], user_message: str) -> list[dict[str, Any]]:
    """Score files by how likely they relate to the user's request; stable within bucket."""
    msg = (user_message or "").lower()

    wanted_substrings: set[str] = set()
    for kw, hints in _KEYWORD_HINTS.items():
        if kw in msg:
            wanted_substrings.update(hints)

    # Direct mentions of file/component names.
    for word in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", msg):
        wanted_substrings.add(word.lower())

    def score(f: dict[str, Any]) -> tuple[int, int]:
        path = (f.get("path") or "").lower()
        name = path.rsplit("/", 1)[-1]
        s = 0
        for sub in wanted_substrings:
            if sub and sub in path:
                s += 3 if sub in name else 1
        # Mild boost for top-level config / entry files always relevant to styling / routing.
        for anchor in ("app.tsx", "main.tsx", "index.html", "tailwind.config", "globals.css", "index.css", "router"):
            if anchor in path:
                s += 1
        return (-s, len(path))  # higher score first, shorter paths first

    return sorted(files, key=score)


class EditAgent:
    SYSTEM = """You are CODEXA's code editor. You MODIFY existing projects; you never rewrite the whole repo unless necessary.

You have access to:
  (a) the USER'S LATEST REQUEST
  (b) a compressed RECENT CONVERSATION so you can resolve pronouns and follow-ups (\"make it smaller\", \"no I meant the other one\")
  (c) a compact PROJECT MANIFEST listing every file path in the project
  (d) the FULL CONTENT of the files most likely to need changes

Respond with ONLY valid JSON (no markdown fences, no commentary). Schema:
{
  "summary": "one sentence describing what you changed",
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
- Include only files that must change. Do NOT touch unrelated files.
- For existing files, "before" MUST match the file content you were given verbatim.
- To add a new file: {"type": "add", "before": "", "after": "<full content>"}.
- To delete a file: {"type": "delete", "before": "<full current content>", "after": ""}.
- Preserve existing style, imports, and structure. Make minimal edits.
- If a file you need isn't included in FULL CONTENT but appears in the MANIFEST, ask for it by emitting a "summary" that says what you need — but first try to complete the edit with what you have.
- If the request is ambiguous, make the smallest reasonable change and explain the interpretation in "summary".
- NEVER regenerate the whole project. NEVER output conversational text.
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

        # (1) Full manifest of every file so the model knows what exists.
        parts.append("\n## Project manifest (all files)")
        manifest_lines: list[str] = []
        for f in files:
            path = (f.get("path") or "").strip()
            if not path:
                continue
            size = len(f.get("content") or "")
            manifest_lines.append(f"- {path} ({size} chars)")
        parts.append("\n".join(manifest_lines) if manifest_lines else "(no files)")

        # (2) Full content for the top-ranked files (relevance + anchors).
        ranked = _rank_files(files, user_message)
        parts.append("\n## Full content (most relevant files)")
        count = 0
        for f in ranked[:MAX_FULL_FILES_IN_PROMPT]:
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
        remaining = max(0, len(ranked) - count)
        if remaining:
            parts.append(f"\n({remaining} more files in manifest but content omitted. Reference them by path if needed.)\n")
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
