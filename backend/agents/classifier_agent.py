from __future__ import annotations

from typing import Any

from core.factory.agent_factory import create_agent


class ClassifierAgent:
    def __init__(self, **kwargs: Any) -> None:
        self._inner = create_agent("classifier", **kwargs)

    def classify(self, message: str):
        return self._inner.classify(message)

    def classify_for_project(self, message: str, project_id: str | None, **kwargs):
        return self._inner.classify_for_project(message, project_id, **kwargs)
