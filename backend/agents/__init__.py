from core.agents.chat_agent import ChatAgent as _ChatAgentCore
from core.agents.classifier_agent import ClassifierAgent as _ClassifierAgentCore
from core.agents.debugger_agent import DebuggerAgent as _DebuggerAgentCore
from core.agents.developer_agent import DeveloperAgent as _DeveloperAgentCore
from core.agents.orchestrator_agent import OrchestratorAgent as _OrchestratorAgentCore
from core.agents.integrator_agent import IntegratorAgent as _IntegratorAgentCore
from core.agents.planner_agent import PlannerAgent as _PlannerAgentCore
from core.agents.architect_agent import ArchitectAgent as _ArchitectAgentCore

from core.factory.agent_factory import create_agent as _create_agent


def _make_agent(agent_type, model_name=None, **kwargs):
    kw = dict(kwargs)
    if model_name is not None:
        kw["model"] = model_name
    return _create_agent(agent_type, **kw)


class DeveloperAgent:
    """
    Primary: OrchestratorAgent (multi-call, Lovable-style).
    Fallback: legacy single-call DeveloperAgent if orchestrator fails.
    """
    def __init__(self, model_name: str | None = None, **kwargs):
        self._orchestrator = _make_agent("orchestrator", model_name, **kwargs)
        self._fallback = _make_agent("developer", model_name, **kwargs)

    def generate_project(
        self,
        project_name: str,
        steps: list,
        user_message: str,
        developer_plan: dict | None = None,
    ):
        try:
            result = self._orchestrator.generate_project(
                project_name,
                steps,
                user_message,
                developer_plan=developer_plan,
            )
            if result and "structure" in result and result["structure"]:
                return result
            print("[DeveloperAgent] Orchestrator returned empty structure, falling back")
        except Exception as e:
            print(f"[DeveloperAgent] Orchestrator failed ({e}), falling back to single-call")
        return self._fallback.generate_project(project_name, steps, user_message)

    async def astream_developer_text(
        self,
        project_name: str,
        steps: list,
        user_message: str,
        developer_plan: dict | None = None,
    ):
        try:
            async for chunk in self._orchestrator.astream_developer_text(
                project_name,
                steps,
                user_message,
                developer_plan=developer_plan,
            ):
                yield chunk
        except Exception as e:
            print(f"[DeveloperAgent] Orchestrator stream failed ({e}), falling back")
            async for chunk in self._fallback.astream_developer_text(project_name, steps, user_message):
                yield chunk

    def parse_project_from_raw(self, raw: str):
        try:
            return self._orchestrator.parse_project_from_raw(raw)
        except Exception:
            return self._fallback.parse_project_from_raw(raw)


class PlannerAgent:
    def __init__(self, model_name: str | None = None, **kwargs):
        self._inner = _make_agent("planner", model_name, **kwargs)

    def extract_title(self, raw_text: str) -> str:
        return self._inner.extract_title(raw_text)

    def plan(self, request: str):
        return self._inner.plan(request)

    def parse_plan_from_raw(self, raw_text: str):
        return self._inner.parse_plan_from_raw(raw_text)

    async def astream_plan_text(self, request: str):
        async for chunk in self._inner.astream_plan_text(request):
            yield chunk


class ArchitectAgent:
    def __init__(self, model_name: str | None = None, **kwargs):
        self._inner = _make_agent("architect", model_name, **kwargs)

    def generate_architecture(self, project_json: dict, user_message: str):
        return self._inner.generate_architecture(project_json, user_message)

    async def agenerate_architecture(self, project_json: dict, user_message: str):
        return await self._inner.agenerate_architecture(project_json, user_message)


class ChatAgent:
    def __init__(self, **kwargs):
        self._inner = _make_agent("chat", **kwargs)

    @staticmethod
    def convert_messages_to_text(messages: list) -> str:
        return _ChatAgentCore.convert_messages_to_text(messages)

    def respond(
        self,
        project_id: str,
        user_message: str,
        project_context: str | None = None,
    ) -> str:
        return self._inner.respond(project_id, user_message, project_context=project_context)

    async def stream_respond(
        self,
        project_id: str,
        user_message: str,
        project_context: str | None = None,
    ):
        async for piece in self._inner.stream_respond(
            project_id, user_message, project_context=project_context
        ):
            yield piece


class ClassifierAgent:
    def __init__(self, **kwargs):
        self._inner = _make_agent("classifier", **kwargs)

    def classify(self, message: str):
        return self._inner.classify(message)

    def classify_for_project(self, message: str, project_id: str | None, **kwargs):
        return self._inner.classify_for_project(message, project_id, **kwargs)


class DebuggerAgent:
    def __init__(self, verbose: bool = True, **kwargs):
        self._inner = _DebuggerAgentCore(verbose=verbose, **kwargs)

    def validate(self, project_json: dict) -> bool:
        return self._inner.validate(project_json)

    def validate_project_json_with_summary(self, project_json: dict) -> dict:
        return self._inner.validate_project_json_with_summary(project_json)

    def fix_flat_files(self, flat_files: list) -> dict:
        """Scan flat file list, inject missing npm/pip deps, return report."""
        from core.validation.dependency_injector import fix_flat_files as _fix
        return _fix(flat_files)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class Integrator:
    def __init__(self, **kwargs):
        self._kwargs = kwargs

    def generate_project(self, name: str, user_message: str | None = None):
        agent = _create_agent("integrator", **self._kwargs)
        return agent.generate_project(name, user_message)


class EditAgent:
    def __init__(self, **kwargs):
        self._inner = _make_agent("edit", **kwargs)

    def run(self, project_id: str, files: list[dict], user_message: str, history_hint: str = "") -> dict:
        return self._inner.run(project_id, files, user_message, history_hint)


from agents.project_pipeline_agent import ProjectPipeline

__all__ = [
    "DeveloperAgent",
    "PlannerAgent",
    "ArchitectAgent",
    "ChatAgent",
    "ClassifierAgent",
    "DebuggerAgent",
    "Integrator",
    "EditAgent",
    "ProjectPipeline",
]
