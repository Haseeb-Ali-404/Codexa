from __future__ import annotations

from typing import Any

from core.factory.agent_factory import create_agent


class EditAgent:
    def __init__(self, **kwargs: Any) -> None:
        self._inner = create_agent("edit", **kwargs)

    def run(
        self,
        project_id: str,
        files: list[dict[str, Any]],
        user_message: str,
        history_hint: str = "",
    ) -> dict[str, Any]:
        return self._inner.run(project_id, files, user_message, history_hint)
