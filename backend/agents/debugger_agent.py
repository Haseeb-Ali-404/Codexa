from __future__ import annotations

from core.agents.debugger_agent import DebuggerAgent as _CoreDebuggerAgent


class DebuggerAgent:
    def __init__(self, verbose: bool = True, **kwargs) -> None:  # noqa: ANN003
        _ = kwargs
        self._inner = _CoreDebuggerAgent(verbose=verbose)

    def validate(self, project_json: dict) -> bool:
        return self._inner.validate(project_json)
