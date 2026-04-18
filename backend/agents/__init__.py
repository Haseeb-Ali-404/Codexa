from core.agents.chat_agent import ChatAgent as _ChatAgentCore
from core.agents.classifier_agent import ClassifierAgent as _ClassifierAgentCore
from core.agents.debugger_agent import DebuggerAgent as _DebuggerAgentCore
from core.agents.developer_agent import DeveloperAgent as _DeveloperAgentCore
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
    def __init__(self, model_name: str | None = None, **kwargs):
        self._inner = _make_agent("developer", model_name, **kwargs)

    def generate_project(self, project_name: str, steps: list, user_message: str):
        return self._inner.generate_project(project_name, steps, user_message)

    async def astream_developer_text(self, project_name: str, steps: list, user_message: str):
        async for chunk in self._inner.astream_developer_text(project_name, steps, user_message):
            yield chunk

    def parse_project_from_raw(self, raw: str):
        return self._inner.parse_project_from_raw(raw)


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

    def respond(self, project_id: str, user_message: str) -> str:
        return self._inner.respond(project_id, user_message)

    async def stream_respond(self, project_id: str, user_message: str):
        async for piece in self._inner.stream_respond(project_id, user_message):
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
        self._inner = _DebuggerAgentCore(verbose=verbose)

    def validate(self, project_json: dict) -> bool:
        return self._inner.validate(project_json)


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