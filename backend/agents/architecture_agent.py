from __future__ import annotations

from typing import Any

from core.factory.agent_factory import create_agent


class ArchitectAgent:
    def __init__(self, model_name: str | None = None, **kwargs: Any) -> None:
        kw = dict(kwargs)
        if model_name is not None:
            kw["model"] = model_name
        self._inner = create_agent("architect", **kw)

    def generate_architecture(self, project_json: dict, user_message: str):
        return self._inner.generate_architecture(project_json, user_message)

    async def agenerate_architecture(self, project_json: dict, user_message: str):
        return await self._inner.agenerate_architecture(project_json, user_message)
