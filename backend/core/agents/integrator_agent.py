from __future__ import annotations

from typing import Any, Callable


class IntegratorAgent:
    """
    Orchestrates planner → developer → debugger using config-driven agent instances.
    """

    def __init__(
        self,
        config_path: str | None = None,
        env_getter: Callable[[str], str | None] | None = None,
        **kwargs: Any,
    ) -> None:
        self._config_path = config_path
        self._env_getter = env_getter

    def _child_kwargs(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self._config_path is not None:
            out["config_path"] = self._config_path
        if self._env_getter is not None:
            out["env_getter"] = self._env_getter
        return out

    def generate_project(self, name: str, user_message: str | None = None) -> dict:
        from core.factory.agent_factory import create_agent

        kw = self._child_kwargs()
        um = user_message or name
        planner = create_agent("planner", **kw)
        plan = planner.plan(um)
        if not plan or "steps" not in plan:
            raise RuntimeError("Planner failed")

        developer = create_agent("developer", **kw)
        project_json = developer.generate_project(
            plan.get("title", name),
            plan["steps"],
            um,
        )
        if not project_json or "structure" not in project_json:
            raise RuntimeError("Developer failed")

        debugger = create_agent("debugger", **kw)
        ok = debugger.validate(project_json)

        return {
            "title": plan.get("title", name),
            "plan": plan["steps"],
            "project": project_json,
            "valid": ok,
        }
