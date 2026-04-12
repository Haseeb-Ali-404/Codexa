from __future__ import annotations

from typing import Any

from core.factory.agent_factory import create_agent


class PlannerAgent:
    """Facade over core planner; provider/model come from agents.config.json or overrides."""

    def __init__(self, model_name: str | None = None, **kwargs: Any) -> None:
        kw = dict(kwargs)
        if model_name is not None:
            kw["model"] = model_name
        self._inner = create_agent("planner", **kw)

    def extract_title(self, raw_text: str) -> str:
        return self._inner.extract_title(raw_text)

    def plan(self, request: str):
        return self._inner.plan(request)

    def parse_plan_from_raw(self, raw_text: str):
        return self._inner.parse_plan_from_raw(raw_text)

    async def astream_plan_text(self, request: str):
        async for chunk in self._inner.astream_plan_text(request):
            yield chunk
