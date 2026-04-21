from __future__ import annotations

import os
from typing import Any, Callable

from core.config.loader import get_agent_llm_spec
from core.providers.base import LLMCallOptions
from core.utils.credentials import default_env_name_for_provider
from core.utils.resilient import FallbackLLMClient, FallbackStep


def _steps_from_spec(spec: dict[str, Any]) -> list[FallbackStep]:
    steps: list[FallbackStep] = [
        FallbackStep(
            provider_id=spec["provider"],
            model=spec["model"],
            api_key_env=spec.get("api_key_env"),
        )
    ]
    for fb in spec.get("fallbacks") or []:
        steps.append(
            FallbackStep(
                provider_id=fb["provider"],
                model=fb["model"],
                api_key_env=fb.get("api_key_env"),
            )
        )
    return steps


def _call_options_from_spec(spec: dict[str, Any]) -> LLMCallOptions:
    return LLMCallOptions(
        temperature=spec.get("temperature"),
        max_tokens=spec.get("max_tokens"),
        timeout_seconds=spec.get("timeout_seconds", 120.0),
    )


def _build_env_getter(
    primary_provider: str,
    primary_api_key_env: str | None,
    forced_api_key: str | None,
    base_getter: Callable[[str], str | None],
) -> Callable[[str], str | None]:
    if not forced_api_key:
        return base_getter
    try:
        primary_default = default_env_name_for_provider(primary_provider)
    except ValueError:
        primary_default = None
    env_names = {primary_api_key_env, primary_default} - {None}

    def getter(name: str) -> str | None:
        if name in env_names:
            return forced_api_key
        return base_getter(name)

    return getter


def build_llm_client_for_agent(
    agent_type: str,
    overrides: dict[str, Any] | None = None,
    *,
    api_key: str | None = None,
    env_getter: Callable[[str], str | None] | None = None,
    config_path: str | None = None,
) -> tuple[FallbackLLMClient, LLMCallOptions]:
    spec = get_agent_llm_spec(agent_type, overrides, config_path=config_path)
    steps = _steps_from_spec(spec)
    base = env_getter or os.getenv
    getter = _build_env_getter(
        spec["provider"],
        spec.get("api_key_env"),
        api_key,
        base,
    )
    client = FallbackLLMClient(steps, env_getter=getter, agent_type=agent_type)
    return client, _call_options_from_spec(spec)


def create_agent(
    agent_type: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    fallbacks: list[dict[str, Any]] | None = None,
    api_key_env: str | None = None,
    config_path: str | None = None,
    env_getter: Callable[[str], str | None] | None = None,
    **kwargs: Any,
):
    """
    Factory: load agents.config.json (or CODEXA_AGENTS_CONFIG), merge overrides,
    inject LLM client + prompt-ready agent instance.

    Example:
        create_agent("planner", provider="groq", model="llama-3.3-70b-versatile")
    """
    overrides: dict[str, Any] = {}
    if provider:
        overrides["provider"] = provider
    if model:
        overrides["model"] = model
    if fallbacks is not None:
        overrides["fallbacks"] = fallbacks
    if api_key_env:
        overrides["api_key_env"] = api_key_env

    from core.agents.classifier_agent import ClassifierAgent
    from core.agents.developer_agent import DeveloperAgent
    from core.agents.orchestrator_agent import OrchestratorAgent
    from core.agents.integrator_agent import IntegratorAgent
    from core.agents.planner_agent import PlannerAgent
    from core.agents.debugger_agent import DebuggerAgent
    from core.agents.architect_agent import ArchitectAgent
    from core.agents.chat_agent import ChatAgent
    from core.agents.title_agent import TitleAgent
    from core.agents.edit_agent import EditAgent

    registry = {
        "planner": PlannerAgent,
        "developer": DeveloperAgent,
        "orchestrator": OrchestratorAgent,
        "debugger": DebuggerAgent,
        "classifier": ClassifierAgent,
        "integrator": IntegratorAgent,
        "architect": ArchitectAgent,
        "chat": ChatAgent,
        "title": TitleAgent,
        "edit": EditAgent,
    }

    key = agent_type.lower().strip()
    if key not in registry:
        raise ValueError(f"Unknown agent type: {agent_type!r}")

    if key == "debugger":
        return DebuggerAgent(**kwargs)

    if key == "integrator":
        return IntegratorAgent(
            config_path=config_path,
            env_getter=env_getter,
            **kwargs,
        )

    client, opts = build_llm_client_for_agent(
        key,
        overrides,
        api_key=api_key,
        env_getter=env_getter,
        config_path=config_path,
    )
    cls = registry[key]
    return cls(llm_client=client, llm_options=opts, **kwargs)
