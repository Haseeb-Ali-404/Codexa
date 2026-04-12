from __future__ import annotations

from typing import Any

from core.factory.agent_factory import create_agent


class Integrator:
    """Orchestration entrypoint using core IntegratorAgent."""

    def __init__(self, **kwargs: Any) -> None:
        self._kwargs = kwargs

    def generate_project(self, name: str, user_message: str | None = None):
        agent = create_agent("integrator", **self._kwargs)
        return agent.generate_project(name, user_message)
