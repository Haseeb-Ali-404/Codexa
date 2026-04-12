from __future__ import annotations

from typing import Any

from core.factory.agent_factory import create_agent


class DeveloperAgent:
    def __init__(self, model_name: str | None = None, **kwargs: Any) -> None:
        kw = dict(kwargs)
        if model_name is not None:
            kw["model"] = model_name
        self._inner = create_agent("developer", **kw)

    def generate_project(self, project_name: str, steps: list, user_message: str):
        return self._inner.generate_project(project_name, steps, user_message)

    async def astream_developer_text(
        self, project_name: str, steps: list, user_message: str
    ):
        async for chunk in self._inner.astream_developer_text(
            project_name, steps, user_message
        ):
            yield chunk

    def parse_project_from_raw(self, raw: str):
        return self._inner.parse_project_from_raw(raw)
