from __future__ import annotations

import os
from typing import Callable

from dotenv import load_dotenv

load_dotenv()

_DEFAULT_ENV_BY_PROVIDER: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "google": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "together": "TOGETHER_API_KEY",
}


def default_env_name_for_provider(provider_id: str) -> str:
    key = provider_id.lower().strip()
    if key not in _DEFAULT_ENV_BY_PROVIDER:
        raise ValueError(f"No default API key env mapping for provider {provider_id!r}")
    return _DEFAULT_ENV_BY_PROVIDER[key]


def _maybe_reload_dotenv() -> None:
    if os.getenv("CODEXA_RELOAD_DOTENV", "").lower() in ("1", "true", "yes"):
        load_dotenv(override=True)


def resolve_api_key_for_provider(
    provider_id: str,
    api_key_env: str | None = None,
    env_getter: Callable[[str], str | None] | None = None,
) -> str | None:
    """
    Read API key from the environment on each call.
    Set CODEXA_RELOAD_DOTENV=1 to re-parse .env on every lookup (dev only).
    """
    _maybe_reload_dotenv()
    getter = env_getter or os.getenv
    env_name = api_key_env or default_env_name_for_provider(provider_id)
    return getter(env_name)


def make_key_resolver(
    provider_id: str,
    api_key_env: str | None = None,
    env_getter: Callable[[str], str | None] | None = None,
) -> Callable[[], str | None]:
    def _resolve() -> str | None:
        return resolve_api_key_for_provider(
            provider_id, api_key_env=api_key_env, env_getter=env_getter
        )

    return _resolve
